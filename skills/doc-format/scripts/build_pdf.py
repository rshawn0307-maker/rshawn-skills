#!/usr/bin/env python3
# 本脚本把 DOCX 转成 PDF：走 LibreOffice 无头转换，再核对字体内嵌情况。
# 之所以不直接从 Markdown 渲染 PDF，是因为本机没有 pandoc、LaTeX、WeasyPrint，但有 LibreOffice。
# 用法：python3 scripts/build_pdf.py --input book.docx --output book.pdf --spec build/x.spec.yaml
#
# 关键事实（实测）：LibreOffice 只扫描 <fonts>/truetype/，把字体复制到上一级是无效的。
# 装齐规格要用的字体是防止「DOCX 好好的、PDF 里字被换掉」的唯一办法。

import argparse   # 用于解析命令行参数
import os         # 用于处理路径与文件移动
import re         # 用于从包装脚本里提取真实可执行文件路径
import shutil     # 用于查找可执行文件与移动文件
import subprocess # 用于调用 LibreOffice
import sys        # 用于输出错误
import tempfile   # 用于给 LibreOffice 准备一个干净的输出目录

# 把 scripts 目录加入模块路径，保证能导入公共库
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import spec_lib   # 导入公共库（中文字体文件名判定等）

# PDF 导出过滤器参数：显式要求「不要跳过空白页」。
# 为什么必须写这一条（实测，LibreOfficeDev 26.8.0.0.alpha0）：
#   中文图书按「章从奇数页起」排版，上一章正好收在奇数页时，中间那一页空白是版面的一部分。
#   LibreOffice 导出 PDF 时默认把这类空白页丢掉（IsSkipEmptyPages 默认值为 true），
#   实测把 16 页的稿子导成了 12 页 —— 页数一变，后面每一页的左右（奇偶）整体错位，
#   章从奇数页起看起来就像「没生效」；而页码域仍按 16 页计数，印出来的页码与实际页序对不上。
#   关掉这个选项，PDF 的页序才和真实排版一致。
PDF_EXPORT_FILTER = 'pdf:writer_pdf_Export:{"IsSkipEmptyPages":{"type":"boolean","value":"false"}}'

# 备用过滤器：不加任何参数，走 LibreOffice 的默认导出。
# 为什么要留这一手：极少数 LibreOffice 版本不接受「过滤器 + 参数串」的写法，会直接转换失败；
# 宁可退回默认行为（再照实报告空白页可能丢失），也不能因为一个可选参数把整份 PDF 生成搞挂。
FALLBACK_EXPORT_FILTER = "pdf"

# 按优先级查找 LibreOffice 的可执行文件。
# 为什么要把三个系统的常见位置都列上：这个 skill 不只在一个 agent、一台机器上跑，
# 别人机器上的 LibreOffice 未必在 PATH 里（macOS 拖进「应用程序」就不会在 PATH，
# Windows 装在 Program Files 也不会）。少一个兜底，换台机器就报「找不到 soffice」。
# 环境变量名：LibreOffice 装在非常规位置时，用户可以用它直接指定可执行文件。
# 与 spec_lib 里 DOC_FORMAT_FONT_MEMORY 的约定一致 —— 同一个 skill 里只保留一种覆盖方式。
SOFFICE_ENV = "DOC_FORMAT_SOFFICE"

# 各系统常见的安装位置，自动查找时逐个试。
# 为什么三个系统都要列：这个 skill 不只在一个 agent、一台机器上跑，
# 别人机器上的 LibreOffice 未必在 PATH 里（macOS 拖进「应用程序」就不在 PATH，
# Windows 装到 Program Files 也不在）。少一个兜底，换台机器就报「找不到」。
SOFFICE_CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",              # macOS 官方安装包
    os.path.expanduser("~/Applications/LibreOffice.app/Contents/MacOS/soffice"),   # macOS 装在用户目录
    "/usr/bin/soffice", "/usr/local/bin/soffice",                        # Linux 常见安装点
    "/usr/lib/libreoffice/program/soffice",                              # Linux 发行版包管理安装
    "/opt/libreoffice/program/soffice",                                  # Linux 手动解压安装
    "/snap/bin/libreoffice",                                             # Linux Snap 安装
    "/var/lib/flatpak/exports/bin/org.libreoffice.LibreOffice",          # Linux Flatpak 安装
    r"C:\Program Files\LibreOffice\program\soffice.exe",              # Windows 64 位
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",        # Windows 32 位
]

# 判断一个可执行文件是不是真的 LibreOffice。
# 为什么单查「用户手填的路径」：脚本自动找到的 soffice 基本不会错，手填的才容易填错。
# 填错时的表现特别难看 —— 脚本会拿那个程序去执行 --headless，换回来的是那个程序自己的报错
# （实测把路径填成 /bin/ls，得到的是 ls 的用法说明），用户完全看不懂自己在哪儿错了。
# 花半秒问一句版本，比让他对着报错猜半天划算。
def looks_like_libreoffice(path):
    try:                                             # 运行外部程序可能失败（无权限、不是可执行文件）
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30)   # 问它版本
    except Exception:                                # 任何异常都当作「确认不了」
        return False                                 # 不确认就不放行
    output = (result.stdout or "") + (result.stderr or "")   # 两个流都看，有的版本打在标准错误里
    return "libreoffice" in output.lower()           # 输出里出现 LibreOffice 才算本尊

# 按优先级查找 LibreOffice 的可执行文件。
def find_soffice():
    # 用户手动指定的路径优先：便携版、自编译、公司统一路径这类情况，自动查找一定找不到，
    # 这时让他指一下，比让他翻源码改路径省事。
    override = os.environ.get(SOFFICE_ENV)           # 读环境变量
    if override:                                     # 用户指定了
        if not os.path.exists(override):             # 路径不存在
            # 指定了却不存在，要说破：静默忽略会让人以为自己指对了，然后继续卡在同一个问题上。
            print(f"注意：环境变量 {SOFFICE_ENV} 指向的路径不存在，已忽略：{override}", file=sys.stderr)   # 提示
        elif looks_like_libreoffice(override):       # 存在，且确认是 LibreOffice
            return override                          # 用它
        else:                                        # 存在，但不是 LibreOffice
            # 说清楚「填错了」，并立刻给出下一步；否则用户会以为脚本坏了。
            print(f"注意：环境变量 {SOFFICE_ENV} 指向的不是 LibreOffice，已忽略：{override}", file=sys.stderr)   # 说破原因
            print("      它要继续往下自动查找了；如果你确定填的就是对的，请再确认一遍路径是不是 soffice 程序本身。", file=sys.stderr)   # 给出路
    for name in ("soffice", "libreoffice"):          # 依次尝试两个常见命令名
        path = shutil.which(name)                    # 在 PATH 中查找（最理想的情况）
        if path:                                     # 找到即返回
            return path                              # 返回可执行文件路径
    for candidate in SOFFICE_CANDIDATES:             # 逐个尝试各系统常见位置
        if os.path.exists(candidate):                # 存在就用它
            return candidate                         # 返回该路径
    return None                                      # 都找不到则返回空

# 找不到 LibreOffice 时给用户看的说明。
# 为什么写成函数而不是就地 print：这段要说清五件事（是什么、影响什么、三平台怎么装、
# 装完干什么、已经装了还找不到怎么办），塞在报错处会把主流程淹掉。
def libreoffice_help_text():
    return "\n".join([                               # 逐行拼成一段
        "这台电脑上没找到 LibreOffice，它是「Word 转 PDF」这一步要用的工具。",   # 一句话说清是什么
        "  影响到哪：Word 文件已经生成好了，能正常打开；只有 PDF 出不来。",       # 说清影响
        "  装它（按你的系统选一条）：",                                        # 给三条路
        "    macOS    brew install --cask libreoffice   （或去官网下 dmg，拖进「应用程序」）",
        "    Windows  去官网下载安装包，装到默认位置即可",                       # Windows 官方安装包
        "    Linux    sudo apt install libreoffice     （Fedora 用 sudo dnf install libreoffice）",
        "  装完不用改任何配置，重跑一次就行。",                                  # 说清下一步
        "  如果已经装了还报这个错，说明它装在非常规位置 —— 把 soffice 的完整路径填进环境变量：",
        f"    {SOFFICE_ENV}=/路径/到/soffice  python3 scripts/build_pdf.py ...",   # 给出兜底手段
    ])

# 从可能的包装脚本中提取真实的 LibreOffice 可执行文件路径
def resolve_real_soffice(soffice):
    real = os.path.realpath(soffice)                 # 先解析符号链接
    if os.path.getsize(real) > 1024 * 1024:          # 真实二进制通常远大于 1MB
        return real                                  # 直接返回该路径
    try:                                             # 尝试按文本读取包装脚本
        with open(real, "r", encoding="utf-8", errors="ignore") as handle:   # 打开脚本
            content = handle.read()                  # 读取内容
    except Exception:                                # 读取失败
        return real                                  # 退回原路径
    # 在脚本内容里查找以 soffice 结尾的绝对路径（LibreOffice 的标准路径结构）
    matches = re.findall(r"(/[^\s\"']*?/[^\s\"']*?\.app/Contents/MacOS/soffice)", content)   # 提取 .app 内路径
    if matches:                                      # 若找到
        candidate = matches[0].replace("${SCRIPT_DIR}/", "")   # 去掉变量前缀
        base = os.path.dirname(real)                 # 包装脚本所在目录
        # 把相对路径展开成绝对路径
        for prefix in ("", "../../"):                # 尝试两种基准
            path = os.path.normpath(os.path.join(base, prefix + candidate.lstrip("/")))   # 拼接并规范化
            if os.path.exists(path):                 # 若路径存在
                return path                          # 返回真实路径
    return real                                      # 都失败则退回原路径

# 定位 LibreOffice 自带的字体目录。这个目录是 LibreOffice 真正会读取字体的位置
def find_lo_font_dir(soffice):
    real = resolve_real_soffice(soffice)             # 解析出真实可执行文件路径
    current = real                                   # 从真实路径出发
    for _ in range(10):                              # 最多向上回溯 10 层
        current = os.path.dirname(current)           # 向上一级
        for relative in ("Contents/Resources/fonts", "share/fonts", "Contents/share/fonts"):   # 三种可能的字体目录
            candidate = os.path.join(current, relative)   # 拼接候选路径
            if os.path.isdir(candidate):             # 若目录存在
                return candidate                     # 返回该目录
    return None                                      # 找不到则返回空

# 系统可用的中文字体文件候选清单，按对中文排版的实用度排序
SYSTEM_CJK_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Songti.ttc",       # 宋体，正文首选
    "/System/Library/Fonts/Supplemental/Kaiti.ttc",        # 楷体（部分系统在此）
    "/System/Library/Fonts/Hiragino Sans GB.ttc",          # 冬青黑体，黑体替代
    "/System/Library/Fonts/STHeiti Light.ttc",             # 黑体细体
    "/System/Library/Fonts/STHeiti Medium.ttc",            # 黑体中黑
]

# 在 AssetsV2 资源目录中按文件名模糊查找字体（苹方、楷体等只存在于该目录）
def find_asset_font(keyword):
    base = "/System/Library/AssetsV2"                        # 苹果字体资源根目录
    if not os.path.isdir(base):                              # 若目录不存在
        return None                                          # 直接返回空
    for root, _, files in os.walk(base):                     # 递归遍历资源目录
        for name in files:                                   # 遍历文件名
            if keyword.lower() in name.lower() and name.lower().endswith((".ttc", ".ttf", ".otf")):   # 命中关键词
                return os.path.join(root, name)              # 返回完整路径
    return None                                              # 未找到

# 找出 LibreOffice 真正会读取的字体目录。
#
# 这个函数修的是一个实测出来的大坑：LibreOffice 只扫描 `<fonts>/truetype/`，
# 而旧代码把字体复制到了它的上一级 `<fonts>/`，于是「装字体」这一步其实一直没生效
# （实测：把 Times New Roman 放进 fonts/ 无效，放进 fonts/truetype/ 立刻生效，
#  PDF 里的字体名从 LiberationSerif 变回 TimesNewRomanPSMT）。
# 更糟的是旧的检测是递归找的，会把上一级那份无效副本当成「已安装」，于是连警告都不打。
def lo_font_install_dir(soffice):
    font_dir = find_lo_font_dir(soffice)                     # 先定位 LibreOffice 的字体根目录
    if not font_dir:                                         # 定位失败
        return None                                          # 返回空
    truetype = os.path.join(font_dir, "truetype")            # LibreOffice 实际扫描的子目录
    if os.path.isdir(truetype):                              # 子目录存在
        return truetype                                      # 用它
    return font_dir                                          # 没有子目录就退回根目录

# 检查 LibreOffice 的字体安装目录里是否已有中文字体。
# 只看安装目录本身，不递归找上一级 —— 否则会把无效副本误判成已安装。
def has_cjk_font(install_dir):
    if not install_dir or not os.path.isdir(install_dir):    # 目录不存在
        return False                                         # 视为没有
    for name in os.listdir(install_dir):                     # 遍历该目录下的文件
        if spec_lib.filename_looks_cjk(name):                # 文件名像中文字体
            return True                                      # 认定已有
    return False                                             # 没有

# 把一个字体文件复制进 LibreOffice 的字体目录。
# 不用 shutil.copy2：它会因为无法写 macOS 扩展属性而抛 PermissionError，
# 而文件其实已经复制成功了 —— 旧代码因此把成功报成失败。
def install_one_font(source, install_dir):
    target = os.path.join(install_dir, os.path.basename(source))   # 目标路径
    try:                                                           # 复制可能失败
        if os.path.exists(target) and os.path.getsize(target) == os.path.getsize(source):   # 已存在同尺寸文件
            return "已存在"                                          # 视为已装好
        shutil.copyfile(source, target)                            # 只复制内容，不复制元数据
        os.chmod(target, 0o644)                                    # 补上读权限
        return "已安装"                                             # 返回安装结果
    except Exception as error:                                     # 复制失败
        return f"失败（{error}）"                                    # 返回失败原因

# 把规格卡要求的字体装进 LibreOffice 的字体目录，并报告哪些没找到。
#
# 为什么必须做：DOCX 生成时我们已经不许替换字体了，但 DOCX → PDF 这一跳是 LibreOffice 做的，
# 它找不到字体就静默换一个。装进去是唯一的根治办法；装不进去的要在生成前就说清楚，
# 否则用户拿到一份字体已被换掉的 PDF 却毫不知情。
def ensure_fonts(soffice, spec=None):
    install_dir = lo_font_install_dir(soffice)                # 找到 LibreOffice 真正读取的目录
    if not install_dir:                                       # 定位失败
        print("警告：未能定位 LibreOffice 字体目录，PDF 里的中文可能渲染成方框", file=sys.stderr)   # 提示
        return False                                          # 返回失败
    # 第一批：保底中文字体。没有它，PDF 里的中文会整片变成空白或方框。
    sources = list(SYSTEM_CJK_FONT_CANDIDATES)                # 取常规路径候选
    for keyword in ("PingFang.ttc", "Kaiti.ttc"):             # 再补充资源目录中的字体
        found = find_asset_font(keyword)                      # 模糊查找
        if found:                                             # 若找到
            sources.append(found)                             # 加入候选清单
    # 第二批：规格卡点名要用的字体。中西文都要，缺哪个 LibreOffice 就会换哪个。
    wanted = []                                               # 规格要求的字体名
    if spec:                                                  # 传了规格卡才做这一步
        for _use, _required, actual, _is_cjk in spec_lib.collect_required_fonts(spec):   # 遍历全部字体槽位
            if actual and actual not in wanted:               # 去重后收集
                wanted.append(actual)                         # 记下实际要用的字体名
    missing = []                                              # 本机找不到文件、装不进去的字体
    for family in wanted:                                     # 逐个查找字体文件
        path = spec_lib.find_font_file(family)                # 在字体目录里找
        if path:                                              # 找到了
            sources.append(path)                              # 加入待安装清单
        else:                                                 # 没找到
            missing.append(family)                            # 记入缺失清单
    installed = []                                            # 实际装上的字体文件名
    for source in dict.fromkeys(sources):                     # 去重后逐个安装
        if not os.path.isfile(source):                        # 源文件不存在
            continue                                          # 跳过
        result = install_one_font(source, install_dir)        # 复制进 LibreOffice 字体目录
        if result == "已安装":                                 # 真的复制了
            installed.append(os.path.basename(source))        # 记入安装清单
    if installed:                                             # 有新增
        print("已为 LibreOffice 安装字体：" + "、".join(installed))   # 打印安装清单
    if missing:                                               # 有规格要求但本机找不到的字体
        print("", file=sys.stderr)                             # 空行分隔
        print("以下字体规格要求使用，但本机找不到字体文件，无法装给 LibreOffice：", file=sys.stderr)   # 说明
        for family in missing:                                # 逐个列出
            print(f"  · {family}", file=sys.stderr)            # 打印字体名
        print("LibreOffice 会用别的字体顶替它们，出来的 PDF 字形与规格不符。", file=sys.stderr)   # 说清后果
        print("解决办法：装上这些字体，或在规格卡里把它们换成已安装的字体。", file=sys.stderr)     # 给出路
    return not missing                                        # 全部装齐才算通过

# 执行转换
def build(input_path, output_path, spec_path=None):
    soffice = find_soffice()                         # 查找 LibreOffice
    if not soffice:                                  # 若未安装
        # 原来的提示只给了 macOS 的 brew 一条命令，Linux 与 Windows 的用户看了等于没说，
        # 也没写「装完怎么办」「已经装了还找不到怎么办」。这几件事现在一次说全。
        print(libreoffice_help_text(), file=sys.stderr)   # 打印三平台安装指引
        return 2                                     # 返回环境错误码
    if not os.path.exists(input_path):               # 若输入文件不存在
        print(f"输入文件不存在：{input_path}", file=sys.stderr)   # 提示
        return 2                                     # 返回错误码
    # 关键前置步骤：把规格要用的字体装进 LibreOffice 真正读取的目录。
    # 不做这一步，LibreOffice 会静默换字体：中文变方框或换成别的中文字体，
    # 西文被 LiberationSerif / LinuxLibertine 顶替 —— 都要生成了才看得出来。
    spec = spec_lib.load_spec(spec_path) if spec_path else None   # 有规格卡就读进来
    fonts_ok = ensure_fonts(soffice, spec)           # 安装字体，并报告装不进去的（幂等操作）
    if spec and not fonts_ok:                        # 规格要求的字体没装齐
        print("已中止：PDF 会用到被顶替的字体，生成出来的文件与规格不符。", file=sys.stderr)   # 说明中止原因
        return 4                                     # 用独立退出码 4 表示「字体缺失」
    output_dir = os.path.dirname(os.path.abspath(output_path)) or "."   # 计算输出目录
    os.makedirs(output_dir, exist_ok=True)           # 确保输出目录存在
    # 让 LibreOffice 先把 PDF 转到一个干净的临时目录里，成功之后再搬到目标路径。
    # 为什么不直接转进输出目录：① 输出目录里可能已经躺着一份同名 PDF（比如用户重跑一次），
    # 那样「文件存在」就不能证明这一步真的成功了，会把旧文件当成新产物交付；
    # ② 为了判断成功去删旧文件，又会在两次都失败时白白毁掉用户手上那份 PDF。
    # 转进临时目录两个问题都没有，代价只是一次同盘移动。
    staging_dir = tempfile.mkdtemp(prefix="doc-format-pdf-")   # 临时的转换输出目录
    produced = os.path.join(staging_dir, os.path.splitext(os.path.basename(input_path))[0] + ".pdf")   # 该目录下的产物路径
    target = os.path.abspath(output_path)            # 目标绝对路径
    # 调用 LibreOffice 无头模式转换，先带参数、失败再退回默认导出（见上面两个常量的说明）
    result = None                                    # 记录最后一次的转换结果
    # 每次尝试的原始输出先收着，等全部试完再说。
    # 为什么不试一次就打印一次：第一档失败、第二档成功是正常情况（老版本不吃导出参数），
    # 这时候打印「本次转换未成功」纯属自己吓自己 —— 用户会以为文件没做出来。
    attempt_notes = []                               # 收集每次尝试的原始输出
    for attempt, export_filter in enumerate((PDF_EXPORT_FILTER, FALLBACK_EXPORT_FILTER)):   # 逐个候选过滤器
        # 组装本次的转换命令。注意 --outdir 决定中间产物落点
        command = [
            soffice,                                 # 可执行文件
            "--headless",                            # 无界面模式
            "--norestore",                           # 不尝试恢复会话
            "--convert-to", export_filter,           # 目标格式（含导出参数）
            "--outdir", staging_dir,                 # 输出目录（临时目录）
            os.path.abspath(input_path),             # 输入文件绝对路径
        ]
        print("正在调用 LibreOffice 转换：", " ".join(command))   # 打印命令便于排查
        result = subprocess.run(command, capture_output=True, text=True)   # 执行命令并捕获输出
        if result.returncode == 0 and os.path.exists(produced):   # 这一步真的产出了文件
            if attempt > 0:                          # 走的是备用过滤器
                # 照实说破：退回默认导出意味着空白页可能被丢掉，章从奇数页起会因此错位
                print("注意：本机 LibreOffice 不接受导出参数，已退回默认导出；"
                      "若稿件要求「章从奇数页起」，PDF 的空白页可能被丢掉，页序需要人工核对。",
                      file=sys.stderr)               # 打到标准错误
            break                                    # 成功即结束重试
        # 这一步没成：先记下原因，继续试下一档；试完还不行再统一报给用户。
        attempt_notes.append(f"（过滤器 {export_filter}）" + (result.stderr or result.stdout or "").strip()[:300])   # 记录本次原因
    succeeded = result is not None and result.returncode == 0 and os.path.exists(produced)   # 是否拿到了产物
    if succeeded:                                    # 拿到了
        shutil.move(produced, target)                # 搬到用户指定的路径
    else:                                            # 两种写法都没成
        # 报错分两层：先给一句人话，再给原委。
        # 为什么不直接把 LibreOffice 的原文丢给用户：原文是给写程序的人看的，
        # 用户看到 "unrecognized option" 这类字眼，只会以为是自己那份文稿坏了。
        print("PDF 没生成出来：LibreOffice 这一步没成功（Word 文件本身是好的，能正常打开）。", file=sys.stderr)   # 人话结论
        detail = "\n".join(attempt_notes) or "（没有输出）"   # 取所有尝试的原始输出备用
        low = detail.lower()                         # 小写化便于匹配
        if "unrecognized option" in low or "unknown option" in low or "usage:" in low:   # 典型的「指错了程序」症状
            print(f"  看这样子，{soffice} 不是一个能用的 LibreOffice，请检查这个路径对不对。", file=sys.stderr)   # 指向真正的原因
        print("  怎么办：先自己打开 LibreOffice 新建一份文档试试，能正常用说明是文件的问题，", file=sys.stderr)   # 给第一条路
        print("          用不了就把它卸掉、重装到系统默认位置，再跑一次。", file=sys.stderr)   # 给第二条路
        print(f"  排查用原文：{detail[:400]}", file=sys.stderr)   # 原文留着给排查用
    shutil.rmtree(staging_dir, ignore_errors=True)   # 无论成败都清掉临时目录，不留垃圾
    if not succeeded:                                # 失败
        return 1                                     # 返回失败码
    if not os.path.exists(target):                   # 若目标仍不存在
        print("转换结束但未找到 PDF 产物", file=sys.stderr)   # 提示异常
        return 1                                     # 返回失败码
    size_kb = os.path.getsize(target) / 1024         # 计算文件大小（KB）
    print(f"已生成：{target}（{size_kb:.1f} KB）")     # 提示产物路径与大小
    return 0                                         # 返回成功码

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="把 DOCX 转为 PDF 并核对内嵌字体")   # 构造参数解析器
    parser.add_argument("--input", required=True, help="输入 DOCX 路径")            # 输入参数
    parser.add_argument("--output", required=True, help="输出 PDF 路径")            # 输出参数
    parser.add_argument("--spec", help="规格卡 YAML 路径；给了它才会把规格要用的字体装给 LibreOffice")   # 规格卡参数
    args = parser.parse_args()                                                     # 解析参数
    return build(args.input, args.output, args.spec)                               # 执行转换

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                                       # 用返回值作为退出码

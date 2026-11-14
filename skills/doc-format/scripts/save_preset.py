#!/usr/bin/env python3
# 本脚本把一次排版任务定下来的规格存成「用户预设」，下次可以一键复用。
#
# 为什么要有这一步：
#   用户每次都要重新回答一遍字号、字体、边距的问题，很烦。只要他把这次的规格点一次头，
#   就应该能存下来，下次直接说「用我的那个报告格式」。
#   来源有两类：① 本次确认过的规格卡；② 从用户现有的 DOCX 反推出来的规格。
#
# 命名要求（重要）：
#   每个预设必须有唯一的名字。重名会被拒绝并给出可用替代名，不允许覆盖已有预设。
#   名字由用户来定；用户不想取名时，脚本按内容自动生成一个带日期的候选名。
#
# 用法：
#   python3 scripts/save_preset.py --list                                  列出全部预设（内置 + 用户）
#   python3 scripts/save_preset.py --spec typography.spec.yaml --name "我的报告格式"
#   python3 scripts/save_preset.py --from-docx 旧稿.docx --name "单位报告模板"
#   python3 scripts/save_preset.py --spec a.yaml --name "季度报告" --note "每季度写给自己看"

import argparse   # 用于解析命令行参数
import datetime   # 用于生成带日期的默认预设名
import os         # 用于路径处理
import re         # 用于生成合法的预设标识
import shutil     # 用于把旧位置的预设搬到新位置
import sys        # 用于控制退出码与错误输出

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # 把 scripts 目录加入模块路径
import spec_lib   # 导入公共库

try:                                                             # YAML 读写在生成预设时要用
    import yaml                                                  # PyYAML
except ImportError:                                              # 依赖缺失
    print("缺少依赖 PyYAML，请运行：pip3 install pyyaml", file=sys.stderr)   # 提示安装
    raise SystemExit(2)                                          # 退出

# 项目根目录（本脚本位于 scripts/ 下，向上一级即根目录）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # 计算根目录
BUILTIN_DIR = os.path.join(ROOT, "references", "presets")                   # 内置预设目录（随 skill 更新）
# 用户预设不放 skill 目录里 —— 理由见 spec_lib.py 里「用户数据放哪」那段说明：
# 放里面的话，用户更新一次 skill 就全没了，还会污染 git 状态。
# 路径一律现取不缓存，这样环境变量能生效，测试也好隔离。

# 内置预设的标识清单，用于判断重名
def builtin_ids():
    if not os.path.isdir(BUILTIN_DIR):                                      # 目录不存在
        return set()                                                        # 返回空集
    return {                                                               # 收集内置预设标识
        os.path.splitext(name)[0]                                           # 去掉扩展名
        for name in os.listdir(BUILTIN_DIR)                                 # 遍历目录
        if name.endswith(".md") and not name.startswith("_")                # 只要 md 且不是下划线开头的内部文件
    }

# 用户预设清单：返回 [(标识, 显示名, 文件路径)]
# 两个位置都找：用户自己的目录在前，旧位置（曾经写在 skill 目录里）在后。
# 同名以新位置为准，迁移没做完或两边各留一份时，不至于读到旧的那份。
def user_presets():
    results = []                                                            # 初始化结果列表
    seen = set()                                                            # 已经出现过的标识
    for directory in (spec_lib.user_preset_dir(), spec_lib.legacy_user_preset_dir()):   # 逐个位置扫描
        if not os.path.isdir(directory):                                    # 目录不存在
            continue                                                        # 跳到下一个位置
        for name in sorted(os.listdir(directory)):                          # 遍历目录里的文件
            if not name.endswith(".md") or name.startswith("_"):            # 跳过非预设文件
                continue                                                    # 继续下一个
            preset_id = os.path.splitext(name)[0]                           # 标识即文件名
            if preset_id in seen:                                           # 这个标识前面已经出现过了
                continue                                                    # 跳过，新位置的那份优先
            seen.add(preset_id)                                             # 记下这个标识
            path = os.path.join(directory, name)                            # 拼出完整路径
            display = preset_id                                             # 默认显示名即标识
            try:                                                            # 试着读出 YAML 里的真实名字
                text = open(path, encoding="utf-8").read()                  # 读取文件
                match = re.search(r'^\s*name:\s*"?([^"\n]+)"?', text, re.M) # 找 meta.name
                if match:                                                   # 找到
                    display = match.group(1).strip()                        # 用 YAML 里的名字
            except Exception:                                               # 读取失败不影响列表
                pass                                                        # 忽略
            results.append((preset_id, display, path))                      # 加入结果
    return results                                                          # 返回列表

# 把旧位置（skill 目录里）的用户预设搬到用户自己的目录，返回搬了几个。
# 为什么要搬：老版本把预设写在 skill 目录里，用户一更新 skill 就全没了。
def migrate_legacy_presets():
    legacy = spec_lib.legacy_user_preset_dir()                              # 旧位置
    if not os.path.isdir(legacy):                                           # 旧位置不存在
        return 0                                                            # 没得搬
    names = [name for name in sorted(os.listdir(legacy))                    # 旧位置里要搬的文件
             if name.endswith(".md") and not name.startswith("_")]          # 只搬预设，不搬下划线开头的说明
    if not names:                                                           # 一个预设都没有
        return 0                                                            # 没得搬
    target = spec_lib.user_preset_dir()                                     # 新位置
    try:                                                                    # 建目录可能失败（比如目录只读）
        os.makedirs(target, exist_ok=True)                                  # 确保新位置存在
    except OSError:                                                         # 建不出来
        return 0                                                            # 放弃搬迁；读取路径仍会去旧位置找，不影响使用
    moved = 0                                                               # 已搬数量
    for name in names:                                                      # 逐个搬
        source = os.path.join(legacy, name)                                 # 源文件
        destination = os.path.join(target, name)                            # 目标文件
        if os.path.exists(destination):                                     # 新位置已经有同名预设
            continue                                                        # 不覆盖，留着旧的让用户自己决定
        try:                                                                # 移动也可能失败
            shutil.move(source, destination)                                # 移动过去（不是复制，免得留两份）
            moved += 1                                                      # 计数
        except OSError:                                                     # 失败就跳过这一个
            continue                                                        # 继续搬下一个
    if moved:                                                               # 真的搬了才提示
        print(f"提示：已把你之前存的 {moved} 个预设搬到 {target}")                # 告诉用户搬了多少、搬到哪
        print("      搬家的原因：预设原来放在 skill 目录里，更新 skill 时会连人带预设一起被替换掉。")   # 说明原因
    return moved                                                            # 返回搬了几个

# 打出一份不重复的预设标识：重名时自动加 -2、-3，仍然重名就带日期
def unique_id(raw, taken):
    base = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff-]+", "-", raw.strip()).strip("-") or "user-preset"   # 清洗成合法标识
    if base not in taken:                                                   # 不重名
        return base                                                         # 直接用
    for index in range(2, 20):                                              # 依次尝试加序号
        candidate = f"{base}-{index}"                                       # 构造候选
        if candidate not in taken:                                          # 不重名
            return candidate                                                # 返回候选
    return f"{base}-{datetime.date.today().isoformat()}"                    # 全部重名则带日期

# 把规格字典写成预设文件：一段中文说明 + 一段可直接读取的 YAML
def write_preset(preset_id, display_name, spec, note, source_desc):
    user_dir = spec_lib.user_preset_dir()                                   # 用户预设目录（现取，认环境变量）
    os.makedirs(user_dir, exist_ok=True)                                    # 确保用户预设目录存在
    target = os.path.join(user_dir, f"{preset_id}.md")                      # 目标文件路径
    today = datetime.date.today().isoformat()                               # 今天的日期
    meta = spec.setdefault("meta", {})                                      # 取 meta 段，缺失时新建
    meta["preset"] = preset_id                                              # 写入预设标识
    meta["name"] = display_name                                             # 写入显示名
    meta.setdefault("source_type", "自定义")                                  # 来源类型默认自定义
    meta["saved_at"] = today                                                # 记录保存日期
    body = yaml.safe_dump(spec, allow_unicode=True, sort_keys=False)        # 序列化成 YAML
    lines = [                                                               # 组装文件内容
        f"# 用户预设：{display_name}",                                        # 标题
        "",
        "> ## ⏱ 时效声明",
        ">",
        f"> 本预设由用户于 **{today}** 保存，来源：{source_desc}。",
        "> 它不是国家标准，也不随标准自动更新。若引用的标准发生换版，请重新确认并更新本文件。",
        ">",
        "> **用户改个别参数**（字号、边距等）→ 直接改。",
        "> **引用的标准换版或用户提出异议** → 先要出处，再联网复查，然后更新本文件。",
        "",
        "## 预设说明",
        "",
        note or "（用户未填写额外说明）",                                        # 用户填写的说明
        "",
        "## 怎么用",
        "",
        f"在规格卡里写 `meta.preset: {preset_id}`，或用下面的 YAML 直接生成文件。",
        "本预设的字体名不随机器走：换一台电脑要重新确认字体装没装（本机字体清单存在字体记忆里）。",
        "",
        "## YAML 参数",
        "",
        "```yaml",
        body.rstrip(),                                                      # YAML 正文
        "```",
        "",
    ]
    with open(target, "w", encoding="utf-8") as handle:                     # 打开目标文件
        handle.write("\n".join(lines))                                      # 写入内容
    return target                                                           # 返回写入路径

# 把段落上读到的行距翻译成规格卡用的写法，返回（模式, 倍数, 磅值）
def line_spacing_from_spec(paragraph_spec):
    value = paragraph_spec.get("line_value")                                # 行距原始值
    if not value:                                                           # 原文件里样式和段落都没写行距
        return "multiple", 1.0, None                                        # 没写就是单倍行距，这是 Word 的默认，不能替它猜
    rule = paragraph_spec.get("line_rule", "auto")                          # 行距规则，决定原始值的单位
    if rule in ("exact", "atLeast"):                                        # 固定值或最小值，单位是二十分之一磅
        return "exact", None, round(value / 20, 2)                          # 换算成磅
    return "multiple", round(value / 240, 2), None                          # auto 规则换算成倍数

# 从现有 DOCX 反推一份规格字典
def spec_from_docx(path):
    import inspect_docx                                                     # 复用反推脚本
    styles_xml = inspect_docx.read_member(path, "word/styles.xml")          # 读样式表
    document_xml = inspect_docx.read_member(path, "word/document.xml")      # 读正文
    styles = inspect_docx.parse_styles(styles_xml)                          # 解析样式表
    defaults = inspect_docx.parse_defaults(styles_xml)                      # 解析文档默认格式
    style_map = {item["style"]: item for item in styles}                    # 样式号到样式的映射
    default_ids = inspect_docx.default_style_ids(styles)                    # 文档默认的段落样式与字符样式
    document = inspect_docx.parse_document(document_xml)                    # 解析页面设置
    paragraphs = inspect_docx.parse_paragraphs(document_xml)                # 解析每个段落
    for paragraph in paragraphs:                                            # 逐段算出真正生效的格式
        paragraph["spec"] = inspect_docx.effective_spec(paragraph, style_map, defaults, default_ids)   # 挂回段落上
    # 按「谁的段落最多」定正文，而不是按「谁的字号最大」——
    # 字号最大的那一组往往是书名或版头，按字号挑会把大标题当成正文。
    groups = []                                                             # 表格外段落的分组
    for paragraph in paragraphs:                                            # 遍历所有段落
        if paragraph["in_table"]:                                           # 表格里的段落不参与正文判断
            continue                                                        # 跳过
        if not paragraph["text"]:                                           # 空段落只是空行，没有「正文该长什么样」这回事
            continue                                                        # 跳过，否则空行会靠数量把正文那一组顶掉
        signature = inspect_docx.spec_signature(paragraph["spec"])          # 算这一段的指纹
        for group in groups:                                                # 找有没有同类
            if group[0] == signature:                                       # 指纹一样
                group[1].append(paragraph)                                  # 归到这一组
                break                                                       # 结束查找
        else:                                                               # 没有同类
            groups.append((signature, [paragraph]))                         # 新开一组
    groups.sort(key=lambda group: -len(group[1]))                           # 段数多的排前面
    body = groups[0][1][0]["spec"] if groups else {}                        # 段数最多的那一组就是正文
    body_size = body.get("size_pt") or 12                                   # 正文字号，实在没有就按 12 磅
    line_mode, line_multiple, line_pt = line_spacing_from_spec(body)        # 正文行距
    indent_chars = body.get("first_line_indent_chars")                      # 正文首行缩进字符数
    align_map = {"both": "justify", "left": "left", "center": "center", "right": "right"}   # Word 的对齐说法换成规格卡的说法
    spec = {                                                                # 组装规格字典
        "meta": {"preset": "", "name": "", "source_type": "从现有文件反推"},   # meta 段
        "page": {                                                           # 页面段
            "size": "A4",                                                   # 只作占位：下面写了显式宽高，显式宽高优先
            "width_mm": round(document.get("page_width_mm") or 210),        # 反推的纸宽
            "height_mm": round(document.get("page_height_mm") or 297),      # 反推的纸高
            "margin_top_mm": round(document.get("margin_top_mm") or 25),    # 反推的上边距
            "margin_bottom_mm": round(document.get("margin_bottom_mm") or 25),   # 反推的下边距
            "margin_left_mm": round(document.get("margin_left_mm") or 30),  # 反推的左边距
            "margin_right_mm": round(document.get("margin_right_mm") or 25),   # 反推的右边距
        },
        "fonts": {                                                          # 字体段
            # 这里刻意不写 strategy：本项目没有「自动替换档」，字体要么装上，要么用户显式写 resolved
            "body": {                                                       # 正文
                "east_asian": body.get("east_asian") or "宋体",               # 反推的中文字体
                "latin": body.get("latin") or "Times New Roman",            # 反推的西文字体
                "size_pt": body_size,                                       # 反推的字号
                "size_label": spec_lib.size_label_of(body_size) or "",       # 对应的中文号数，不是标准号数就留空
            },
        },
        "paragraph": {                                                      # 段落段
            "indent_mode": "first_line" if indent_chars else "none",         # 原文件缩进了就首行缩进，没缩进就顶格
            "first_line_indent_chars": indent_chars or 0,                   # 反推的缩进字符数
            "line_spacing_mode": line_mode,                                 # 反推的行距模式
            "alignment": align_map.get(body.get("alignment"), "justify"),    # 反推的对齐
        },
        "headings": {},                                                     # 标题段落，下面填充
    }
    if line_pt is not None:                                                 # 是固定值行距
        spec["paragraph"]["line_spacing_pt"] = line_pt                      # 写磅值
    else:                                                                   # 是倍数行距
        spec["paragraph"]["line_spacing_value"] = line_multiple or 1.0      # 写倍数
    # 字号比正文大的组按字号从大到小排，依次当作一级、二级、三级标题
    heads = [group for group in groups[1:] if (group[0][1] or 0) > body_size]   # 挑出字号大于正文的组
    heads.sort(key=lambda group: -(group[0][1] or 0))                       # 字号大的排前面
    for level, (_, items) in enumerate(heads[:3], 1):                       # 最多反推三级标题
        item = items[0]["spec"]                                             # 拿这一组代表的格式
        size = item.get("size_pt") or body_size                             # 这一级的字号
        spec["headings"][f"level{level}"] = {                               # 写入该级
            "east_asian": item.get("east_asian") or spec["fonts"]["body"]["east_asian"],   # 中文字体
            "latin": item.get("latin") or spec["fonts"]["body"]["latin"],     # 西文字体
            "size_pt": size,                                                # 字号
            "size_label": spec_lib.size_label_of(size) or "",                # 中文号数
            "bold": bool(item.get("bold")),                                 # 原文件加粗就跟着加粗
            "alignment": align_map.get(item.get("alignment"), "left"),       # 原文件怎么对就怎么对
            "first_line_indent_chars": item.get("first_line_indent_chars") or 0,   # 标题的首行缩进
        }
    return spec                                                             # 返回规格字典

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="把本次规格存成用户预设，便于下次复用")   # 构造解析器
    parser.add_argument("--list", action="store_true", help="列出全部预设（内置 + 用户）")   # 列表开关
    parser.add_argument("--spec", help="规格卡 YAML 路径")                       # 来源一：规格卡
    parser.add_argument("--from-docx", help="从现有 DOCX 反推规格")               # 来源二：现有文档
    parser.add_argument("--name", help="预设的显示名（由用户取，必须唯一）")          # 预设名
    parser.add_argument("--note", default="", help="可选的说明，写清楚这个预设的用途")   # 说明
    args = parser.parse_args()                                                # 解析参数

    # 先把旧位置的用户预设搬到新位置，再往下走。
    # 放在最前面：不管用户这次是看列表还是存新预设，搬完他都能在正确的目录里看到自己的东西。
    migrate_legacy_presets()                                                  # 搬迁旧预设（没有就什么都不做）

    if args.list:                                                             # 列出预设
        print("内置预设：")                                                    # 小节标题
        print(f"  用户预设目录：{spec_lib.user_preset_dir()}")                   # 顺带说明用户预设存在哪
        for item in sorted(builtin_ids()):                                    # 遍历内置预设
            print(f"  - {item}")                                              # 打印标识
        users = user_presets()                                                # 取用户预设
        print(f"用户预设（{len(users)} 个）：")                                 # 小节标题
        for preset_id, display, _ in users:                                    # 遍历用户预设
            print(f"  - {preset_id}　{display}")                               # 打印标识与显示名
        if not users:                                                         # 没有用户预设
            # 这里不能写成「任务结束后问用户要不要存」——SKILL.md 硬规则 11 明确说
            # 只在「用户改动了规格」时才问，套内置预设没改参数就问是打扰用户。
            print("  （还没有。下次用户自定义了排版、或改了预设里的参数时，再问他要不要存）")   # 给出与规则一致的提示
        return 0                                                              # 正常退出

    if not args.name:                                                         # 必须提供名字
        print("缺少 --name。预设名由用户来取，脚本不替他决定。", file=sys.stderr)    # 打印错误
        print("如果用户说「你随便取一个」，请先向他提议一个名字再执行。", file=sys.stderr)   # 补充说明
        return 2                                                              # 返回用法错误
    taken = builtin_ids() | {preset_id for preset_id, _, _ in user_presets()}   # 收集已占用的标识
    preset_id = unique_id(args.name, taken)                                   # 生成唯一标识
    if preset_id != re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff-]+", "-", args.name.strip()).strip("-"):   # 标识被改过说明重名
        print(f"提示：名字「{args.name}」已被占用，改用「{preset_id}」以免覆盖已有预设。")   # 告知改名

    if args.spec:                                                             # 来源一：规格卡
        spec = spec_lib.load_spec(args.spec)                                  # 读取规格卡
        source_desc = f"规格卡 {os.path.basename(args.spec)}"                   # 描述来源
    elif args.from_docx:                                                      # 来源二：现有文档
        if not os.path.exists(args.from_docx):                                # 文件不存在
            print(f"文件不存在：{args.from_docx}", file=sys.stderr)              # 打印错误
            return 2                                                          # 返回错误码
        spec = spec_from_docx(args.from_docx)                                 # 反推规格
        source_desc = f"从现有文档 {os.path.basename(args.from_docx)} 反推"       # 描述来源
    else:                                                                     # 两个来源都没给
        print("必须提供 --spec 或 --from-docx 之一。", file=sys.stderr)          # 打印错误
        return 2                                                              # 返回错误码

    target = write_preset(preset_id, args.name, spec, args.note, source_desc)  # 写出预设
    print(f"已保存用户预设：{target}")                                          # 打印路径
    print(f"  预设标识：{preset_id}")                                          # 打印标识
    print(f"  显示名：{args.name}")                                            # 打印显示名
    print(f"  来源：{source_desc}")                                            # 打印来源
    # 以前这里写的是「在规格卡里写 meta.preset 为该标识」—— 那句是空头支票：
    # 没有任何代码读 meta.preset，用户照着写也调不出来。改成真能用的写法。
    print(f"  下次用法：把这个路径当作规格卡传进去 —— --spec {target}")          # 使用提示
    print(f"             （也可以只写标识「{preset_id}」，脚本会自己去预设目录里找）")   # 补充简写形式
    print("  提醒：预设里的字体名不随机器走，换一台电脑要重新确认字体装没装。")                        # 关键提醒
    return 0                                                                  # 正常退出

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                                  # 用返回值作为退出码

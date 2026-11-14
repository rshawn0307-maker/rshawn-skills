#!/usr/bin/env python3
# 本脚本检查中文文稿里的错别字、用词误用与标点问题，并可写出修正后的新文件。
#
# 为什么要有这一步：
#   排版再漂亮，正文里有「按耐不住」「迫不急待」「不径而走」也是不合格的交付物。
#   所以不管文稿来自 Markdown 还是用户丢来的 Word/PDF，调整格式之前都要走一遍错别字检查。
#
# 设计原则：
#   1. 分「确定错误」与「建议核实」两类。确定错误可以自动改，建议核实只提示、不擅自改。
#   2. 只改字，不改意思；遇到代码块、行内代码、公式、URL、表格分隔行一律跳过。
#   3. 永不覆盖原文件，只写 <原名>.typo-fixed.<扩展名>，并且逐条报告改了哪里。
#
# 用法：
#   python3 scripts/typo_check.py 文稿.md                   检查并出报告
#   python3 scripts/typo_check.py 文稿.md --write           检查并写出修正后的新文件
#   python3 scripts/typo_check.py 旧稿.docx                 检查 Word（只读，不写回）
#   python3 scripts/typo_check.py 旧稿.pdf                  检查 PDF（只读）

import argparse   # 用于解析命令行参数
import os         # 用于路径处理
import re         # 用于正则匹配
import sys        # 用于控制退出码与错误输出

# ─────────────────────────────────────────────────────────────
# 确定错误表：(错误写法, 正确写法, 说明)
# 收录标准：成语固定搭配误写、常用词固定误写。这些改法无歧义，可以自动修正。
# ─────────────────────────────────────────────────────────────
CERTAIN_TYPOS = [
    ("不径而走", "不胫而走", "胫：小腿。没有腿却能跑，形容传播迅速"),
    ("迫不急待", "迫不及待", "及：来得及。急迫得不能再等待"),
    ("按耐", "按捺", "捺：按下。「按耐」是常见误写"),
    ("按奈", "按捺", "同上，另一种误写"),
    ("相形见拙", "相形见绌", "绌：不足。跟别人比较显得不如"),
    ("再接再励", "再接再厉", "厉：磨快。原指公鸡相斗时磨嘴，后比喻继续努力"),
    ("变本加利", "变本加厉", "厉：猛烈。变得比原来更严重"),
    ("以经", "已经", "「以经」不成立，应为「已经」"),
    ("各行其事", "各行其是", "是：对的。各人按自己认为对的去做"),
    ("甘败下风", "甘拜下风", "拜：拜服"),
    ("一愁莫展", "一筹莫展", "筹：计策"),
    ("走头无路", "走投无路", "投：投奔"),
    ("情不自尽", "情不自禁", "禁：抑制"),
    ("弱不经风", "弱不禁风", "禁：承受"),
    ("义气用事", "意气用事", "意气：主观情绪"),
    ("娇揉造作", "矫揉造作", "矫：使曲变直"),
    ("烩炙人口", "脍炙人口", "脍：细切的肉；炙：烤肉"),
    ("默守成规", "墨守成规", "墨守：战国墨翟善于守城"),
    ("死皮癞脸", "死皮赖脸", "赖：耍赖"),
    ("黄梁美梦", "黄粱美梦", "粱：小米"),
    ("如法泡制", "如法炮制", "炮制：用烘炒等方法制作中药"),
    ("严惩不怠", "严惩不贷", "贷：宽恕"),
    ("棉里藏针", "绵里藏针", "绵：丝绵"),
    ("锱珠必较", "锱铢必较", "锱、铢：古代重量单位"),
    ("自抱自弃", "自暴自弃", "暴：糟蹋"),
    ("竭泽而鱼", "竭泽而渔", "渔：捕鱼"),
    ("以偏盖全", "以偏概全", "概：概括"),
    ("重蹈复辙", "重蹈覆辙", "覆：翻倒"),
    ("流言诽语", "流言蜚语", "蜚：同「飞」"),
    ("名声雀起", "名声鹊起", "鹊起：如鹊惊起，比喻名声兴起"),
    ("相儒以沫", "相濡以沫", "濡：沾湿"),
    ("深明大意", "深明大义", "义：道义"),
    ("题纲", "提纲", "提：提出。提纲指内容要点"),
    ("精减", "精简", "精简指去掉不必要的"),
    ("脉膊", "脉搏", "搏：跳动"),
    ("松驰", "松弛", "弛：放松"),
    ("渡假", "度假", "度：度过"),
    ("寻物启示", "寻物启事", "启事：公开说明事情"),
    ("招聘启示", "招聘启事", "同上"),
    ("大姆指", "大拇指", "拇：手的大指"),
    ("迫不得已", "迫不得已", "本条为正确写法，仅用于对照，不会触发修正"),
    ("不记其数", "不计其数", "计：计算"),
    ("谈笑风声", "谈笑风生", "生：产生，形容谈笑有说有笑"),
    ("名列前矛", "名列前茅", "茅：古代行军前哨所举的茅草"),
    ("再接再利", "再接再厉", "同上"),
    ("循规蹈距", "循规蹈矩", "矩：画方形的工具"),
    ("中流抵柱", "中流砥柱", "砥柱：黄河中的砥柱山"),
    ("病入膏盲", "病入膏肓", "肓：古代医学指心脏与膈膜之间"),
    ("要言不繁", "要言不烦", "烦：烦琐"),
    ("焕然冰释", "涣然冰释", "涣然：消散的样子"),
    ("甘之如怡", "甘之如饴", "饴：麦芽糖"),
    ("陈词烂调", "陈词滥调", "滥：空泛"),
    ("完壁归赵", "完璧归赵", "璧：玉璧"),
    ("座无虚度", "座无虚席", "席：座位"),
    ("渲泄", "宣泄", "宣：疏通"),
    ("蜇伏", "蛰伏", "蛰：动物冬眠"),
    ("纷至踏来", "纷至沓来", "沓：多而重复"),
    ("珊珊来迟", "姗姗来迟", "姗姗：行走缓慢从容"),
]

# ─────────────────────────────────────────────────────────────
# 建议核实表：(写法, 建议改法, 说明)
# 这些改法取决于语境，不能自动改，只能提示用户自己判断。
# ─────────────────────────────────────────────────────────────
SUGGESTED_FIXES = [
    ("其它", "其他", "现代汉语规范推荐用「其他」，「其它」多用于非正式场合"),
    ("帐户", "账户", "金融与信息系统场景规范用「账户」"),
    ("帐号", "账号", "同上"),
    ("帐目", "账目", "同上"),
    ("记帐", "记账", "同上"),
    ("结帐", "结账", "同上"),
    ("欠帐", "欠账", "同上"),
    ("登陆网站", "登录网站", "「登陆」指登上陆地，「登录」指进入系统"),
    ("截止到目前", "截至目前", "「截止」是不及物动词，后面不能带宾语；「截至」可以"),
    ("截止目前", "截至目前", "同上"),
    ("截止到", "截至", "「截至」本身已含「到」的意思，不必再加「到」"),
    ("截至到", "截至", "「截至」本身已含「到」的意思，「截至到」是语义重复"),
    ("一名共产党员", "一名共产党员", "本条为正确示范，不会触发"),
    ("做为", "作为", "规范写法为「作为」"),
    ("即使如此", "即使如此", "本条为正确示范，不会触发"),
    ("必须要", "必须", "「必须」本身已含「要」的意思，重复"),
    ("涉及到", "涉及", "「涉及」本身已含「到」的意思，重复"),
]

# 会被误判的场景：这些行不参与错别字检查（代码、公式、网址、纯结构行）
SKIP_LINE_PATTERNS = [
    re.compile(r"^\s*```"),                    # 代码块围栏
    re.compile(r"^\s*\|[\s:|-]+\|\s*$"),        # 表格分隔行
    re.compile(r"^\s*[-*_]{3,}\s*$"),           # 水平分隔线
    re.compile(r"^\s*<[^>]+>\s*$"),             # 纯 HTML 标签行
]

# 行内需要保护的内容：命中后临时替换掉，不参与错别字扫描
INLINE_PROTECT = [
    re.compile(r"`[^`]*`"),                     # 行内代码
    re.compile(r"\$[^$\n]*\$"),                 # 行内公式
    re.compile(r"https?://\S+"),                # 网址
    re.compile(r"<[^>\n]+>"),                   # 行内 HTML 标签
]

# 常见繁体字表：简体文稿里混入这些字通常是转换残留，需要提醒
TRADITIONAL_CHARS = "裡這個們來說時會後點還將為與對實現發應該當與讓從關開國學機構處標題導體響應轉換圖書聲畫"

# 把行内特殊内容（代码、公式、URL、标签）替换成占位符，返回占位后的文本与还原表
def protect_inline(line):
    protected = []                                          # 初始化还原表
    result = line                                           # 复制一份待处理文本
    for pattern in INLINE_PROTECT:                          # 遍历每种保护模式
        def repl(match):                                    # 定义替换回调
            protected.append(match.group(0))                # 把原内容存进还原表
            return f"\u0001{len(protected) - 1}\u0001"       # 用占位符替换
        result = pattern.sub(repl, result)                  # 执行替换
    return result, protected                                # 返回处理结果与还原表

# 还原被保护的内容
def restore_inline(text, protected):
    for index, value in enumerate(protected):               # 遍历还原表
        text = text.replace(f"\u0001{index}\u0001", value)   # 把占位符换回原内容
    return text                                             # 返回还原后的文本

# 判断某一行是否应该跳过错别字检查
def should_skip(line):
    for pattern in SKIP_LINE_PATTERNS:                      # 遍历跳过规则
        if pattern.search(line):                            # 命中任一规则
            return True                                     # 跳过该行
    return False                                            # 否则参与检查

# 检查单行文本，返回该行发现的问题列表
def check_line(line):
    issues = []                                             # 初始化问题列表
    safe, protected = protect_inline(line)                  # 先保护行内特殊内容
    for wrong, right, note in CERTAIN_TYPOS:                # 遍历确定错误表
        if wrong == right:                                  # 对照用的占位条目跳过
            continue                                        # 继续下一条
        if wrong in safe:                                   # 命中错误写法
            issues.append(("确定", wrong, right, note))       # 记为确定错误
    for wrong, right, note in SUGGESTED_FIXES:              # 遍历建议核实表
        if wrong == right:                                  # 对照用条目跳过
            continue                                        # 继续下一条
        if wrong in safe:                                   # 命中待核实写法
            issues.append(("建议", wrong, right, note))       # 记为建议核实
    # 规则：形容词/副词修饰动词时应用「地」，误写成「的」是高频问题
    match = re.search(r"(慢慢|好好|认真|认认真真|仔细|仔仔细细|努力|快速|积极|不断|继续|严格|全面|逐步|切实|扎实|深入|统筹|定期|及时|主动)的(做|干|写|说|讲|看|听|走|跑|推进|落实|检查|核对|把|将|完成|处理|开展)", safe)   # 匹配副词 + 的 + 动词
    if match:                                               # 命中
        issues.append(("建议", f"{match.group(1)}的{match.group(2)}", f"{match.group(1)}地{match.group(2)}", "副词修饰动词应用「地」"))   # 记为建议
    # 规则：动作 + 程度补语时应用「得」，误写成「的」是高频问题
    match = re.search(r"(做|干|写|说|讲|走|跑|来|想|考虑)的(好|对|快|慢|早|晚|清楚|明白|到位|不错)", safe)   # 匹配动作 + 的 + 补语
    if match:                                               # 命中
        issues.append(("建议", f"{match.group(1)}的{match.group(2)}", f"{match.group(1)}得{match.group(2)}", "动词后接程度补语应用「得」"))   # 记为建议
    # 规则：繁体字混入简体文稿
    hit_traditional = sorted({ch for ch in safe if ch in TRADITIONAL_CHARS})   # 找出命中的繁体字
    if hit_traditional:                                     # 若有命中
        issues.append(("建议", "".join(hit_traditional), "对应简体字", "检测到繁体字，若原意是简体文稿需转换"))   # 记为建议
    # 规则：重复标点
    for pair in ["。。", "，，", "；；", "：：", "、、"]:        # 遍历不该重复的标点
        if pair in safe:                                    # 命中重复
            issues.append(("确定", pair, pair[0], "标点重复"))   # 记为确定错误
    # 规则：省略号与破折号写法不规范
    if re.search(r"(?<![\w.])\.\.\.(?![\w.])", safe):        # 半角三点省略号
        issues.append(("建议", "...", "……", "中文省略号用六点「……」"))   # 记为建议
    if re.search(r"。。。", safe):                            # 中文句号当省略号
        issues.append(("确定", "。。。", "……", "中文省略号用六点「……」"))   # 记为确定
    # 规则：引号与括号不配对（同一行内数量不等）
    if safe.count("“") != safe.count("”"):                   # 中文双引号不配对
        issues.append(("建议", "“ 与 ”", "配对使用", f"本行左引号 {safe.count('“')} 个、右引号 {safe.count('”')} 个"))   # 记为建议
    if safe.count("（") != safe.count("）"):                  # 中文括号不配对
        issues.append(("建议", "（ 与 ）", "配对使用", f"本行左括号 {safe.count('（')} 个、右括号 {safe.count('）')} 个"))   # 记为建议
    # 规则：中文语境里夹杂半角标点
    if re.search(r"[\u4e00-\u9fff][,;?!](?![\dA-Za-z])", safe):   # 汉字后面跟半角标点
        issues.append(("建议", "半角标点", "全角标点", "中文语境应使用全角标点"))   # 记为建议
    # 规则：汉字之间夹了空格（多为误敲）
    # 注意：这里只匹配半角空格与制表符。全角空格 U+3000 是中文标题的正规用法（如「第一章　绪论」），
    # 而 Python 的 \s 会把 U+3000 也算进来，导致误报，所以必须显式列举。
    if re.search(r"[\u4e00-\u9fff][ \t][\u4e00-\u9fff]", safe):   # 汉字 半角空格 汉字
        issues.append(("建议", "汉字间空格", "去掉空格", "汉字之间通常不加空格"))   # 记为建议
    # 规则：中文标点前后多余空格
    if re.search(r"\s[，。、；：！？）”]", safe) or re.search(r"[（“]\s", safe):   # 标点旁有空格
        issues.append(("确定", "标点旁空格", "去掉空格", "中文标点前后不留空格"))   # 记为确定
    # 规则：连续多个空格（Markdown 缩进除外）
    if re.search(r"[\u4e00-\u9fff]{2,}", safe) and re.search(r"\S {2,}\S", safe):   # 中文行里有连续空格
        issues.append(("建议", "连续空格", "单个空格", "中文行内连续空格多为误敲"))   # 记为建议
    # 规则：行尾多余空格不在错别字范畴，交给 Markdown 规范化处理
    restore_inline(safe, protected)                         # 还原被保护内容（保持函数纯粹，供调试用）
    return issues                                           # 返回问题列表

# 从各种格式的文件里抽取纯文本行，供检查使用
def extract_lines(path):
    extension = os.path.splitext(path)[1].lower()           # 取扩展名
    if extension in (".md", ".markdown", ".txt", ".text"):  # 纯文本类型
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:   # 打开文件
            return handle.read().splitlines(), True          # 返回行列表与「可写回」标记
    if extension == ".docx":                                # Word 文档
        try:                                                # 依赖可能缺失
            from docx import Document                       # 导入 python-docx
        except ImportError:                                 # 缺失时
            print("检查 DOCX 需要 python-docx：pip3 install python-docx", file=sys.stderr)   # 提示
            raise SystemExit(2)                             # 退出
        document = Document(path)                           # 打开文档
        lines = [p.text for p in document.paragraphs]       # 取所有段落文本
        for table in document.tables:                       # 遍历表格
            for row in table.rows:                          # 遍历行
                lines.append(" | ".join(cell.text for cell in row.cells))   # 把单元格拼成一行
        return lines, False                                 # DOCX 不写回，交给 convert_docx 处理
    if extension == ".pdf":                                 # PDF 文档
        try:                                                # 依赖可能缺失
            import fitz                                     # PyMuPDF
        except ImportError:                                 # 缺失时
            print("检查 PDF 需要 PyMuPDF：pip3 install pymupdf", file=sys.stderr)   # 提示
            raise SystemExit(2)                             # 退出
        document = fitz.open(path)                          # 打开 PDF
        lines = []                                          # 初始化行列表
        for page in document:                               # 遍历每一页
            lines.extend(page.get_text().splitlines())      # 累加该页文本行
        return lines, False                                 # PDF 不写回
    print(f"不支持的文件类型：{extension}", file=sys.stderr)   # 其它类型直接报错
    raise SystemExit(2)                                     # 退出

# 执行检查，返回「确定错误」清单与「建议」清单
def scan(lines):
    certain = []                                            # 确定错误清单
    suggested = []                                          # 建议清单
    for index, line in enumerate(lines, start=1):           # 遍历每一行
        if should_skip(line):                               # 需要跳过的行
            continue                                        # 跳过
        if not line.strip():                                # 空行
            continue                                        # 跳过
        for kind, wrong, right, note in check_line(line):   # 检查该行
            record = (index, line.strip(), wrong, right, note)   # 组装记录
            if kind == "确定":                                # 确定错误
                certain.append(record)                      # 加入确定清单
            else:                                           # 建议
                suggested.append(record)                    # 加入建议清单
    return certain, suggested                               # 返回两个清单

# 应用确定错误的修正，返回修正后的文本与改动清单
def apply_fixes(text):
    changes = []                                            # 初始化改动清单
    result = text                                           # 复制待处理文本
    lines = result.split("\n")                              # 按行切分
    for index, line in enumerate(lines):                    # 遍历每一行
        if should_skip(line):                               # 跳过的行
            continue                                        # 不动
        safe, protected = protect_inline(line)              # 保护行内特殊内容
        original_safe = safe                                # 记录处理前文本
        for wrong, right, note in CERTAIN_TYPOS:            # 遍历确定错误表
            if wrong == right:                              # 对照条目跳过
                continue                                    # 继续
            if wrong in safe:                               # 命中
                safe = safe.replace(wrong, right)           # 执行替换
                changes.append((index + 1, wrong, right, note))   # 记录改动
        for wrong, right in [("。。", "。"), ("，，", "，"), ("；；", "；"), ("：：", "："), ("、、", "、")]:   # 重复标点
            if wrong in safe:                               # 命中
                safe = safe.replace(wrong, right)           # 替换成单个
                changes.append((index + 1, wrong, right, "标点重复"))   # 记录改动
        if "。。。" in safe:                                 # 中文句号当省略号
            safe = safe.replace("。。。", "……")             # 替换成规范省略号
            changes.append((index + 1, "。。。", "……", "中文省略号用六点"))   # 记录改动
        safe = re.sub(r"\s+([，。、；：！？）”])", r"\1", safe)   # 去掉中文标点前的空格
        safe = re.sub(r"([（“])\s+", r"\1", safe)             # 去掉左括号左引号后的空格
        if safe != original_safe:                           # 有改动才还原
            lines[index] = restore_inline(safe, protected)  # 还原被保护内容并写回该行
    return "\n".join(lines), changes                        # 返回全文与改动清单

# 打印检查报告
def report(path, certain, suggested):
    print(f"错别字与用词检查：{path}")                          # 打印标题
    print("=" * 66)                                         # 打印分隔线
    if not certain and not suggested:                       # 什么都没发现
        print("未发现问题。")                                  # 打印通过
        return 0                                            # 返回无问题
    if certain:                                             # 有确定错误
        print(f"【确定错误 {len(certain)} 处】可自动修正")        # 打印小节标题
        for line_no, text, wrong, right, note in certain:    # 逐条打印
            print(f"  第 {line_no} 行：「{wrong}」→「{right}」（{note}）")   # 打印改动
            print(f"            原文：{text[:70]}")           # 打印上下文
    if suggested:                                           # 有建议项
        print(f"【建议核实 {len(suggested)} 处】需人工判断，不自动改")   # 打印小节标题
        for line_no, text, wrong, right, note in suggested:  # 逐条打印
            print(f"  第 {line_no} 行：「{wrong}」→ 建议「{right}」（{note}）")   # 打印建议
            print(f"            原文：{text[:70]}")           # 打印上下文
    print("-" * 66)                                         # 打印分隔线
    print("提醒：确定错误可以用 --write 自动改；建议项必须人工判断，不要机械替换。")   # 使用提示
    return len(certain) + len(suggested)                    # 返回问题总数

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="中文文稿错别字与用词检查")   # 构造解析器
    parser.add_argument("input", help="待检查的文件（.md/.txt/.docx/.pdf）")   # 输入文件
    parser.add_argument("--write", action="store_true", help="写出修正后的新文件（仅支持纯文本类）")   # 落盘开关
    args = parser.parse_args()                                             # 解析参数
    if not os.path.exists(args.input):                                     # 输入不存在
        print(f"文件不存在：{args.input}", file=sys.stderr)                  # 打印错误
        return 2                                                           # 返回错误码
    lines, writable = extract_lines(args.input)                            # 抽取文本行
    certain, suggested = scan(lines)                                       # 执行检查
    count = report(args.input, certain, suggested)                         # 打印报告
    if args.write:                                                         # 若要求落盘
        if not writable:                                                   # 该格式不支持写回
            print(f"注意：{os.path.splitext(args.input)[1]} 不支持直接写回。")   # 提示
            print("       Word 文稿请用 convert_docx.py 重排；PDF 无法直接改字，需要拿到源文件。")   # 给出替代
            return 1                                                       # 返回失败码
        with open(args.input, "r", encoding="utf-8", errors="ignore") as handle:   # 重新读取原文
            original = handle.read()                                       # 取全文
        fixed, changes = apply_fixes(original)                             # 执行修正
        if not changes:                                                    # 没有可自动改的项
            print("没有可自动修正的确定错误，未写出新文件。")                    # 提示
            return 0 if count == 0 else 1                                  # 按有无问题返回
        base, extension = os.path.splitext(args.input)                     # 拆分文件名
        target = f"{base}.typo-fixed{extension}"                           # 构造新文件名
        with open(target, "w", encoding="utf-8") as handle:                # 打开新文件
            handle.write(fixed)                                            # 写出修正后全文
        print("-" * 66)                                                    # 打印分隔线
        print(f"已写出：{target}（原文件未改动）")                            # 提示产物
        print(f"共修改 {len(changes)} 处，逐条如下：")                        # 打印改动数
        for line_no, wrong, right, note in changes:                        # 逐条打印改动
            print(f"  第 {line_no} 行：「{wrong}」→「{right}」")              # 打印改动明细
    return 1 if count else 0                                               # 有问题返回 1

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                               # 用返回值作为退出码

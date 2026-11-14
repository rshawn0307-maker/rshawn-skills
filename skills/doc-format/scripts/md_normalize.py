#!/usr/bin/env python3
# 本脚本对 Markdown 源文件做排版前置规范化：合并硬换行、补中英文空格、全角化标点、规范引号与省略号、
# 检查标题层级与表格结构。规则依据 references/markdown-rules.md。
# 原则：只改格式，不改措辞；先出报告，落盘写新文件，不覆盖原文。
# 用法：python3 scripts/md_normalize.py book.md [--write] [--outdir 目录]
#   加 --write 时默认写到 源文件同级的 build/ 子目录，不覆盖原文，也不堆在书稿目录里

import argparse   # 用于解析命令行参数
import re         # 用于正则替换
import os         # 用于拼接输出路径
import sys        # 用于把「文件不存在」等提示写进标准错误并设置退出码

# 行内需要保护、不能做标点替换的内容：行内代码、行内公式、URL、HTML 标签、链接目标地址
# 为什么要保护「目标地址」：`![书](cover/减脂饮食全书-封面.jpg)` 里的 `.jpg` ，
# 句点前是汉字、后是字母，会被标点全角化规则判成「句号」改成 `。jpg`，图片与链接直接失效。
PROTECT_PATTERNS = [
    (re.compile(r"`[^`]*`"), "\u0001"),                       # 反引号包裹的行内代码
    (re.compile(r"\$[^$\n]*\$"), "\u0002"),                   # 行内数学公式
    (re.compile(r"https?://\S+"), "\u0003"),                  # 裸 URL
    (re.compile(r"<[^>\n]+>"), "\u0004"),                      # HTML 标签（含 <a id="x"></a> 锚点）
    # 目标里不许出现括号与方括号：不加这个限制时 `[示例](地址) 文字 ![图](图.png)`
    # 会被一口气吞成一整段（正则里的 [^)]* 会一路吃到后面那个 `)`），
    # 把后半句正文也当成链接目标保护起来，还原后位置错乱。
    (re.compile(r"(?<=\]\()[^()\[\]\n]*\)"), "\u0005"),      # 行内链接/图片的圆括号目标：](target)
    (re.compile(r"(?<=\]:\s)[^\s\n]+"), "\u0006"),             # 引用式链接的定义地址：[id]: target
]

# 半角标点到全角标点的映射表，键为半角，值为全角
PUNCT_MAP = {
    ",": "，",   # 逗号
    ".": "。",   # 句号
    ";": "；",   # 分号
    ":": "：",   # 冒号
    "?": "？",   # 问号
    "!": "！",   # 感叹号
    "(": "（",   # 左括号
    ")": "）",   # 右括号
}

# 判断字符是否属于「中文语境」：除汉字外，还要包含中文标点与全角符号
def is_cjk_context(ch):
    if not ch:                                   # 空字符不算中文语境
        return False
    if "\u4e00" <= ch <= "\u9fff":               # 中日韩统一表意文字
        return True
    if "\u3000" <= ch <= "\u303f":               # 中日韩符号与标点（含、《》等）
        return True
    if "\uff00" <= ch <= "\uffef":               # 全角字符区（含，。！？；：（）等）
        return True
    if ch in "“”‘’—…《》〈〉、·":                    # 中文常用标点（弯引号、破折号、省略号、书名号等）
        return True
    return False                                 # 其余不算中文语境

# 找出距离某个位置最近的非空白字符，用于跨空格判断标点所属语境
def nearest_non_space(text, start, step):
    index = start                                 # 从起始位置出发
    while 0 <= index < len(text):                 # 在合法范围内循环
        if not text[index].isspace():             # 找到非空白字符
            return text[index]                    # 返回该字符
        index += step                             # 按方向继续查找
    return ""                                     # 越界则返回空字符串

# 保护行内特殊内容：把行内代码、公式、URL、HTML 临时替换成占位符，处理完再还原
def protect(text):
    saved = []                                  # 存储被保护的原片段
    for pattern, marker in PROTECT_PATTERNS:    # 逐个模式处理
        # 用替换函数逐段替换，并记录原文
        def repl(match, marker=marker):
            saved.append(match.group(0))        # 记录原始片段
            return f"{marker}{len(saved) - 1}{marker}"   # 用「标记+序号+标记」占位
        text = pattern.sub(repl, text)          # 执行替换
    return text, saved                          # 返回处理后的文本与原文列表

# 还原被保护的内容
def restore(text, saved):
    # 必须反复还原到「不再变化」为止，单轮还原会漏。
    # 实测漏的场景：`[示例](https://example.com/a.b)` 里的地址先被 URL 规则保护成占位符，
    #   紧接着「行内链接目标」规则又把整段（连同里面的占位符）吞掉、再吐成另一个占位符；
    #   等轮到还原本体时，它已经被吐回来了，但那一轮已经过去，于是地址永远还不回来，
    #   最终产物里留下一串不可见占位符 —— 链接直接作废。
    for _ in range(len(saved) + 1):             # 最坏情况是层层嵌套，轮数取被保护片段数加一
        before = text                           # 记下本轮开始时的样子
        for index, original in enumerate(saved):    # 遍历所有被保护的原文
            for _, marker in PROTECT_PATTERNS:      # 遍历所有可能的标记
                text = text.replace(f"{marker}{index}{marker}", original)   # 还原占位符
        if text == before:                      # 本轮没有任何变化
            break                               # 说明还原完了，提前退出
    return text                                  # 返回还原后的文本

# 在中文与英文/数字之间补一个半角空格
def add_cjk_latin_space(text):
    # 中文后面紧跟英文字母或数字时补空格
    text = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9])", r"\1 \2", text)
    # 英文字母或数字后面紧跟中文时补空格
    text = re.sub(r"([A-Za-z0-9])([\u4e00-\u9fff])", r"\1 \2", text)
    # 合并可能因重复替换产生的连续空格
    text = re.sub(r"[ \t]{2,}", " ", text)
    # 删除全角标点前后的多余空格，中文排版中全角标点自带宽度，不需要再加空格
    text = re.sub(r"[ \t]+([，。；：！？、）》”’…—])", r"\1", text)
    text = re.sub(r"([（《“‘])[ \t]+", r"\1", text)
    # 全角句末标点后面紧跟中文时，删除多余空格
    text = re.sub(r"([，。；：！？、）》”’…—])[ \t]+(?=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef])", r"\1", text)
    return text                                  # 返回补空格后的文本

# 把中文语境下的半角标点替换为全角
def fullwidth_punct(text):
    # 总体说明：逐字符判断是否该全角化，前后至少一侧是中文才换。
    # 括号必须成对处理：左右括号各自判断会出现「（12:00)」这种半拉子 ——
    # 左括号前面是汉字「餐」于是被换成「（」，右括号前面是数字「0」不换，结果括号不配对（实测过）。
    # 做法：用栈记下每个左括号最终是不是全角，右括号跟随与它配对的那个左括号。
    result = []                                  # 逐字符构造结果
    open_stack = []                              # 左括号栈：元素表示该层左括号最终是否为全角
    for index, ch in enumerate(text):            # 遍历每个字符及其位置
        previous = nearest_non_space(text, index - 1, -1)         # 前一个非空白字符
        following = nearest_non_space(text, index + 1, 1)         # 后一个非空白字符
        # 只有当前字符在映射表里，且前后至少一侧是中文时，才做替换
        convert = ch in PUNCT_MAP and (is_cjk_context(previous) or is_cjk_context(following))   # 本字符是否该全角化
        # `![` 是图片语法，紧挨着方括号的那个感叹号绝不能全角化。
        # `与图片 ![图](a.png)` 里的 `!` 左边是汉字，会被判成中文语境下的感叹号改成 `！`，
        # 图片语法当场失效（实测：`与图片！[图](a.png)`）。
        if ch == "!" and following == "[":           # 感叹号后面紧跟方括号
            convert = False                          # 这是图片标记，跳过全角化
        # 数字后面的半角句点一律不当句号看。「附件：1. 城市防汛…」「1. 排查范围」「3.14」都属于这一类：
        # 中文正文的句子结尾不会用半角点，所以「数字 + .」几乎必然是序号点或小数点。
        # 全角化会把它们写成「附件：1。城市防汛…」（实测过）——附件号当场写错，
        # 而且要按「附件名首字」做回行对齐（§7.3.4）时，前缀宽度也会跟着算错。
        if ch == "." and index > 0 and text[index - 1] in "0123456789":   # 前一个字符是阿拉伯数字
            convert = False                          # 序号点 / 小数点，不换
        if ch in "（(":                           # 左括号（半角或已是全角）
            open_stack.append(ch == "（" or convert)   # 入栈：这一层左括号最终是不是全角
        elif ch in "）)":                         # 右括号（半角或已是全角）
            open_left = open_stack.pop() if open_stack else False   # 取出配对左括号的全角状态
            convert = convert or open_left        # 跟着配对的左括号走，避免只换半边
        if convert:                              # 需要全角化
            # 用 get 兜底：已是全角的「）」本来就不在映射表里，跟随左括号时不该在这里再查表。
            result.append(PUNCT_MAP.get(ch, ch))   # 替换为全角（已经是全角的原样保留）
        else:                                    # 其他情况
            result.append(ch)                    # 保持原样
    return "".join(result)                       # 拼回字符串

# 规范化引号、破折号与省略号
def curly_quotes(text):
    # 用计数器逐对替换：奇数次出现的直引号换成左引号，偶数次换成右引号
    out = []                                     # 逐字符构造结果
    double_open = True                           # 双引号开闭状态
    single_open = True                           # 单引号开闭状态
    for index, ch in enumerate(text):            # 遍历字符
        if ch == '"':                            # 遇到英文双引号
            out.append("“" if double_open else "”")   # 按状态输出中文引号
            double_open = not double_open        # 切换状态
        elif ch == "'":                          # 遇到英文单引号
            out.append("‘" if single_open else "’")   # 按状态输出中文引号
            single_open = not single_open        # 切换状态
        else:                                    # 其他字符
            out.append(ch)                       # 原样保留
    text = "".join(out)                          # 拼回字符串
    # 把两个或三个连字符替换为中文破折号。
    # 必须排除表格与分隔线场景：前后紧邻竖线或整个字段都是连字符时不能替换，否则会破坏 Markdown 结构
    text = re.sub(r"(?<![\|\s:])-{2,3}(?![\|\s:])(?=\S)", "——", text)
    # 把三个及以上英文句点替换为中文省略号
    text = re.sub(r"\.{3,}", "……", text)
    return text                                  # 返回规范后的文本

# 判断一行是否是 Markdown 表格的分隔行（如 |:---|:---:|---:|）
def is_table_separator(line):
    # 分隔行只由竖线、冒号、连字符和空白组成
    return bool(re.match(r"^\s*\|[\s:|-]+\|\s*$", line))

# 判断一行是否是 Markdown 分隔线（如 --- 或 *** 或 ___）
def is_horizontal_rule(line):
    # 分隔线只由三个以上的同一种符号组成
    return bool(re.match(r"^\s*([-*_])\1{2,}\s*$", line))

# 判断一行是否是 Markdown 块级结构行（标题、列表、引用、表格、分隔线、代码围栏）
def is_block_line(line):
    stripped = line.strip()                      # 去掉首尾空白
    if not stripped:                             # 空行视为结构分隔
        return True
    if stripped.startswith(("#", "-", "*", "+", ">", "|", "```", "~~~")):   # 常见块级标记
        return True
    if re.match(r"^\d+[.)]\s", stripped):        # 有序列表
        return True
    if re.match(r"^[-*_]{3,}$", stripped):       # 分隔线
        return True
    if re.match(r"^<[a-zA-Z][^>]*>.*</[a-zA-Z]+>$", stripped):   # 独占一行的 HTML 标签（如锚点 <a id="x"></a>）
        return True                              # 它属于块级结构，不能被当成正文并进上一段
    return False                                 # 其余视为正文

# 把两行合并为一行：中文之间直接拼接（中文不用空格分隔句子），英文之间用一个空格分隔
def join_lines(previous, current):
    left = previous.rstrip()                     # 去掉前一行右侧空白
    right = current.lstrip()                     # 去掉后一行左侧空白
    if not left:                                 # 若前一行是空的
        return right                             # 直接返回后一行
    if not right:                                # 若后一行是空的
        return left                              # 直接返回前一行
    # 两侧都是中文语境时直接拼接，避免在中文句子之间插入多余空格
    if is_cjk_context(left[-1]) and is_cjk_context(right[0]):
        return left + right                      # 无空格拼接
    # 其他情况用一个空格拼接，符合西文排版习惯
    return left + " " + right                    # 加空格拼接

# 合并被硬换行切断的自然段：连续的正文行若未形成完整句或下一行不是块级结构，则并入同一段
def merge_soft_wraps(lines):
    merged = []                                  # 初始化结果列表
    count = 0                                    # 合并次数计数
    in_code = False                              # 是否处于代码块内
    for raw in lines:                            # 遍历每一行
        stripped = raw.strip()                   # 去空白后的内容
        if stripped.startswith("```") or stripped.startswith("~~~"):   # 代码围栏
            in_code = not in_code                # 切换代码块状态
            merged.append(raw)                   # 原样保留
            continue                             # 处理下一行
        if in_code:                              # 代码块内部
            merged.append(raw)                   # 原样保留
            continue                             # 处理下一行
        # 判断当前行是否可以作为上一行的续行
        can_append = (
            merged                                   # 结果列表非空
            and stripped                             # 当前行不是空行
            and not is_block_line(raw)               # 当前行不是块级结构
            and not is_block_line(merged[-1])        # 上一行也不是块级结构
            and merged[-1].strip()                   # 上一行非空
        )
        # 引用行内部的软换行合并：CommonMark 里 `> 甲` 与 `> 乙` 属于同一个段落，
        # 不合并的话渲染出来会变成两段，每段各吃一个首行缩进。
        # 只在「引用前缀后面的内容不是块级结构」时才合并 —— 引用里的列表、表格、分隔线必须原样留着。
        if merged and is_quote_line(raw) and is_quote_line(merged[-1]):   # 上一行与当前行都是引用行
            previous_body = strip_quote_prefix(merged[-1])   # 上一行引用里的内容
            body = strip_quote_prefix(raw)                   # 当前行引用里的内容
            if (previous_body.strip() and body.strip()                       # 两行都有实际内容
                    and not is_block_line(previous_body)                     # 上一行不是列表/表格/分隔线
                    and not is_block_line(body)):                            # 当前行也不是
                merged[-1] = quote_prefix(merged[-1]) + join_lines(previous_body, body)   # 沿用原前缀，合并内容
                count += 1                                   # 合并计数加一
                continue                                     # 处理下一行
        if can_append:                           # 可以续接
            merged[-1] = join_lines(merged[-1], raw)   # 合并到上一行
            count += 1                           # 计数加一
        else:                                    # 不能续接
            merged.append(raw)                   # 作为新行加入
    return merged, count                         # 返回合并后的行列表与合并次数

# 剥掉行首的引用前缀（可能有多层，如 "> > "），返回引用内部的内容。
# 为什么需要它：块级结构的判断（表格分隔行、分隔线、列表标记）必须看「引用内部」的原文。
#   否则 `> |---|--|` 这一行既不像表格分隔行、也不像分隔线，会被当成正文交给标点规则，
#   把 `--` 改成 `——`（实测变成 `> |-——-|-——-|`），引用里的表格当场散架。
def strip_quote_prefix(line):
    match = re.match(r"^[ \t]*(?:>[ \t]?)+", line)   # 匹配一层或多层引用标记
    return line[match.end():] if match else line      # 有前缀就切掉，没有就原样返回

# 取出一行开头的引用前缀（如 "> " 或 "> > "），非引用行返回空串
def quote_prefix(line):
    match = re.match(r"^[ \t]*(?:>[ \t]?)+", line)   # 与上面同一个匹配规则
    return match.group(0) if match else ""            # 返回前缀本身

# 规范化「一条块级内容」：内容是列表项时只规范化标记之后的部分。
# 为什么单独抽出来：引用行内部也可能有列表（`> 1. 内容`），
#   如果引用分支只调用普通的正文规范化，`1.` 会被全角化成 `1。`，
#   引用里的列表就变成了普通文字，结构被悄悄改掉。
def normalize_block_content(text):
    list_match = re.match(r"^([ \t]*(?:[-*+]|\d+[.)])[ \t]+)(.*)$", text)   # 匹配「缩进 + 列表标记 + 内容」
    if list_match:                                  # 是列表项
        return list_match.group(1) + normalize_text_line(list_match.group(2))   # 标记原样，只规范化内容
    return normalize_text_line(text)                # 普通内容整行规范化

# 判断一行是不是引用行（以 `>` 标记开头）
def is_quote_line(line):
    return bool(quote_prefix(line))                   # 有引用前缀就算引用行

# 把一行拆成「前导缩进」与「正文」。
# 前导缩进是 Markdown 的结构信息（决定列表嵌套到第几层），
# 一旦被当成正文参与「合并连续空格」之类的替换，`  1.` 会被压成 ` 1.`，嵌套层级就漂了。
def split_indent(line):
    match = re.match(r"^[ \t]*", line)           # 匹配开头连续的空白
    indent = match.group(0)                      # 前导缩进部分
    return indent, line[len(indent):]            # 返回（缩进，正文）

# 处理正文行的规范化。传入的应当是「不含前导缩进、不含列表标记」的纯正文。
def normalize_text_line(line):
    indent, body = split_indent(line)            # 先摘下前导缩进，稍后原样接回
    text, saved = protect(body)                  # 保护特殊内容（代码、公式、URL、HTML、链接目标）
    text = curly_quotes(text)                    # 先规范引号与省略号，让后续标点判断能识别中文弯引号
    text = fullwidth_punct(text)                 # 再全角化标点
    text = add_cjk_latin_space(text)             # 补中英文之间的空格
    text = restore(text, saved)                  # 还原被保护内容
    return indent + text                         # 接回缩进并返回

# 主处理流程：读取文件、逐行规范化、合并软换行、输出报告
def normalize(path, write, outdir=None, return_text=False):
    # 文件不存在时给友好提示。抛 FileNotFoundError 会让用户看到一段 Python 调用栈，
    # 而真实原因只是路径给错了 —— 这类「看起来像 skill 坏了」的输出要一律消灭。
    if not os.path.exists(str(path)):                   # 路径不存在
        print(f"文件不存在：{path}", file=sys.stderr)      # 说清问题
        raise SystemExit(2)                             # 以用法错误退出
    with open(path, "r", encoding="utf-8") as handle:   # 以 UTF-8 读取源文件
        lines = handle.read().split("\n")               # 按行切分
    issues = []                                         # 初始化问题清单
    out = []                                            # 初始化输出行列表
    in_code = False                                     # 是否处于围栏代码块内
    heading_levels = []                                 # 记录标题层级用于检查跳跃
    merge_count = 0                                     # 软换行合并计数
    punct_count = 0                                     # 标点修正计数
    space_count = 0                                     # 中英文空格修正计数
    quote_count = 0                                     # 引号修正计数
    for index, raw in enumerate(lines):                 # 遍历每一行
        line_no = index + 1                             # 计算行号（从 1 开始）
        fence = raw.strip().startswith("```") or raw.strip().startswith("~~~")  # 是否为代码围栏
        if fence:                                       # 遇到围栏
            in_code = not in_code                       # 切换代码块状态
            out.append(raw)                             # 围栏行原样保留
            continue                                    # 跳过后续处理
        if in_code:                                     # 代码块内部
            out.append(raw)                             # 原样保留，绝不修改
            continue                                    # 跳过后续处理
        # 表格分隔行与水平分隔线属于纯结构语法，任何标点替换都会破坏 Markdown，必须原样保留。
        # 判断前先剥掉引用前缀：`> |---|--|` 里的分隔行也在引用内部，同样不能被标点规则碰到。
        structure_line = strip_quote_prefix(raw)        # 取引用内部的内容（非引用行原样）
        if is_table_separator(structure_line) or is_horizontal_rule(structure_line):
            out.append(raw)                             # 原样保留整行（含引用前缀）
            continue                                    # 跳过后续处理
        if raw.lstrip().startswith(("#",)):             # 标题行
            match = re.match(r"^(#{1,6})\s*(.*)$", raw.strip())   # 解析标题层级与文字
            if match:                                   # 解析成功
                level = len(match.group(1))             # 层级等于井号个数
                heading_levels.append((line_no, level)) # 记录层级与行号
                new_line = "#" * level + " " + normalize_text_line(match.group(2))  # 规范标题文字
                out.append(new_line)                    # 写入输出
                continue                                # 处理下一行
        # 引用行同样只规范化「标记之后」的内容，避免 `>` 前缀参与标点与空格规则。
        quote_match = re.match(r"^([ \t]*(?:>[ \t]?)+)(.*)$", raw)   # 拆成「引用前缀」与「引用内容」
        if quote_match:                                 # 是引用行
            prefix, content = quote_match.group(1), quote_match.group(2)   # 取下前缀与内容
            normalized = prefix + normalize_block_content(content)   # 前缀原样，内容按块级内容规范化
            if normalized != raw:                       # 若发生了变化
                space_count += 1                        # 计入修正（引用行只可能被补空格或标点）
            out.append(normalized)                      # 写入输出
            continue                                    # 处理下一行
        # 列表项要单独处理：`1.` 与 `-` 是 Markdown 语法，不是句子里的标点。
        # 若整行丢给标点全角化，`1. 第一……` 会变成 `1。第一……` ——
        # 标记没了，这一行就不再被 is_block_line 认得，接着会被「硬换行合并」与下一条列表项粘成一行。
        list_match = re.match(r"^([ \t]*(?:[-*+]|\d+[.)])[ \t]+)(.*)$", raw)   # 匹配「缩进 + 列表标记 + 内容」
        if list_match:                                  # 是列表项
            normalized = normalize_block_content(raw)   # 只规范化标记之后的内容
            if normalized != raw:                       # 若发生了变化
                space_count += 1                        # 计入空格修正（列表项只可能被补空格）
            out.append(normalized)                      # 写入输出
            continue                                    # 处理下一行
        normalized = normalize_text_line(raw)           # 规范化正文行
        if normalized != raw:                           # 若发生了变化
            if add_cjk_latin_space(raw) != raw:         # 判断是否属于空格修正
                space_count += 1                        # 空格修正计数加一
            if fullwidth_punct(raw) != raw:             # 判断是否属于标点修正
                punct_count += 1                        # 标点修正计数加一
            if curly_quotes(raw) != raw:                # 判断是否属于引号修正
                quote_count += 1                        # 引号修正计数加一
        out.append(normalized)                          # 写入输出
    # 合并被硬换行切断的自然段，这一步是排版成败的关键
    merged_lines, merge_count = merge_soft_wraps(out)
    # 检查标题层级是否跳跃
    for position in range(1, len(heading_levels)):      # 从第二个标题开始比较
        previous_level = heading_levels[position - 1][1]  # 上一个标题层级
        current_level = heading_levels[position][1]       # 当前标题层级
        if current_level > previous_level + 1:            # 若跳级
            issues.append((heading_levels[position][0], f"标题层级跳跃：从 {previous_level} 级直接到 {current_level} 级"))
    # 检查表格：每个表格块的列数是否一致、是否有分隔行
    table_blocks = []                                   # 初始化表格块列表
    current_block = []                                  # 当前表格块
    for index, raw in enumerate(out):                   # 遍历输出行
        if raw.strip().startswith("|"):                 # 表格行
            current_block.append((index + 1, raw))      # 记录行号与内容
        else:                                           # 非表格行
            if current_block:                           # 若刚结束一个表格块
                table_blocks.append(current_block)      # 收集该块
                current_block = []                      # 重置
    if current_block:                                   # 收尾处理
        table_blocks.append(current_block)              # 收集最后一个块
    for block in table_blocks:                          # 遍历每个表格块
        counts = {line.count("|") for _, line in block} # 统计各行列数
        if len(counts) > 1:                             # 列数不一致
            issues.append((block[0][0], f"表格列数不一致：出现 {sorted(counts)} 种竖线数量"))
        has_separator = any(re.match(r"^\s*\|[\s:|-]+\|\s*$", line) for _, line in block)  # 是否有分隔行
        if not has_separator:                           # 缺少分隔行
            issues.append((block[0][0], "表格缺少分隔行（|---|），Markdown 不会渲染成表格"))
    # 输出报告
    print(f"文件：{path}")                               # 打印文件名
    print(f"总行数：{len(lines)}")                        # 打印总行数
    print(f"中英文空格修正：{space_count} 行")              # 打印空格修正数
    print(f"标点全角化修正：{punct_count} 行")              # 打印标点修正数
    print(f"引号与省略号修正：{quote_count} 行")            # 打印引号修正数
    print(f"硬换行合并：{merge_count} 处（合并后段落数减少，避免每行都被首行缩进）")   # 打印合并数
    print(f"标题层级问题：{len([i for i in issues if '标题' in i[1]])} 处")   # 打印标题问题数
    print(f"表格问题：{len([i for i in issues if '表格' in i[1]])} 处")       # 打印表格问题数
    if issues:                                          # 若有问题
        print("-" * 60)                                 # 打印分隔线
        for line_no, message in issues:                 # 逐条打印问题
            print(f"  第 {line_no} 行：{message}")        # 带行号的提示
    result = "\n".join(merged_lines)                    # 用合并后的行拼回完整文本
    if write:                                           # 若要求落盘
        target = normalized_path(path, outdir)          # 计算输出路径（默认落在 build/ 子目录）
        os.makedirs(os.path.dirname(target), exist_ok=True)   # 目录不存在就建出来
        with open(target, "w", encoding="utf-8") as handle:   # 以 UTF-8 写入
            handle.write(result)                        # 写出规范化结果
        print("-" * 60)                                 # 打印分隔线
        print(f"已写出：{target}（原文件未改动）")           # 提示输出路径
    if return_text:                                     # 调用方要的是文本本身
        return len(issues), result                      # 一并返回问题数与规范化文本
    return len(issues)                                  # 否则只返回问题数量作为退出码依据

# 计算规范化稿的输出路径。
# 默认落在源文件同级的 build/ 子目录，而不是直接堆在书稿目录里 ——
# 书稿目录应该只留成品，规范化稿与规格卡都是中间产物。
def normalized_path(path, outdir=None):
    # 默认落在源文件同级的 build/；如果源文件已经在 build/ 里，就用它本身，
    # 免得再套一层 build/build/（spec_lib.staging_dir 用的是同一条约定）。
    parent = os.path.dirname(os.path.abspath(path))   # 源文件所在目录
    default_dir = parent if os.path.basename(parent) == "build" else os.path.join(parent, "build")   # 默认目录
    directory = outdir or default_dir                 # 命令行指定优先
    stem, ext = os.path.splitext(os.path.basename(path))   # 源文件名与扩展名
    return os.path.join(directory, f"{stem}.normalized{ext}")   # 拼出规范化稿路径

# 只做规范化、不落盘，返回规范化后的完整文本。
# 用途：生成脚本加 --normalize 时在内存里拿清洗过的稿子，不必在磁盘上留中间文件。
def normalized_text(path):
    _, text = normalize(path, False, return_text=True)     # 借用同一套流程，只是不写文件
    return text                                            # 返回文本

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="Markdown 排版前置规范化")   # 构造参数解析器
    parser.add_argument("input", help="待处理的 Markdown 文件路径")           # 位置参数：输入文件
    parser.add_argument("--write", action="store_true", help="写出规范化后的新文件（默认落在同级 build/ 子目录）")  # 落盘开关
    parser.add_argument("--outdir", help="指定规范化稿的输出目录（默认：源文件同级的 build/）")   # 输出目录
    args = parser.parse_args()                                             # 解析参数
    count = normalize(args.input, args.write, args.outdir)                 # 执行规范化
    return 1 if count else 0                                               # 有问题返回 1

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                               # 用返回值作为退出码

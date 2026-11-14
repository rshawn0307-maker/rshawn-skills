#!/usr/bin/env python3
# 本文件是排版脚本的公共库：负责读取规格卡、换算字号与行距、按策略解析字体名。
# 其他脚本（font_check / spec_check / build_docx / build_html / verify_output）都从这里导入。

import os         # 用于拼接字体目录路径、判断目录是否存在
import sys        # 用于在缺依赖时把错误写进 stderr
import glob       # 用于展开 /System/Library/AssetsV2 这类带通配的字体目录
import json       # 用于读写字体检测的磁盘缓存
import datetime   # 用于给字体记忆打上检测日期
# 正则：用于解析 Markdown 块、去行内标记、判断单元格是不是数字，以及识别图表题注
import re         # Python 标准库正则模块
import subprocess # 用于调用系统命令（fc-list、system_profiler）枚举字体

# 尝试导入 YAML 解析库，缺失时给出明确提示而不是抛裸异常
try:
    import yaml   # PyYAML，用于读取 typography.spec.yaml
except ImportError:  # 捕获导入失败
    print("缺少依赖 PyYAML，请运行：pip3 install pyyaml", file=sys.stderr)  # 提示安装命令
    raise SystemExit(2)  # 以退出码 2 结束，表示环境不满足

# 中文号数制与磅值的对照表，数值来源见 references/standards.md 第三节
SIZE_TABLE = {
    "初号": 42.0,   # 初号等于 42 磅
    "小初": 36.0,   # 小初等于 36 磅
    "一号": 26.0,   # 一号等于 26 磅
    "小一": 24.0,   # 小一等于 24 磅
    "二号": 22.0,   # 二号等于 22 磅
    "小二": 18.0,   # 小二等于 18 磅
    "三号": 16.0,   # 三号等于 16 磅（GB/T 9704 公文正文）
    "小三": 15.0,   # 小三等于 15 磅
    "四号": 14.0,   # 四号等于 14 磅
    "小四": 12.0,   # 小四等于 12 磅
    "五号": 10.5,   # 五号等于 10.5 磅（中文图书正文常用）
    "小五": 9.0,    # 小五等于 9 磅
    "六号": 7.5,    # 六号等于 7.5 磅
    "小六": 6.5,    # 小六等于 6.5 磅
    "七号": 5.5,    # 七号等于 5.5 磅
    "八号": 5.0,    # 八号等于 5 磅
}

# 中日韩统一表意文字的码点范围。多处脚本都要用到，写成一个出处，避免各写各的
CJK_START = "\u4e00"   # 范围起点
CJK_END = "\u9fff"     # 范围终点

# 判断一个字符串里有没有中文（含中日韩统一表意文字即视为有）
def is_cjk(text):
    # 遍历字符串中的每个字符
    for ch in text:
        # 用 Unicode 码点范围判断是否为中日韩字符
        if CJK_START <= ch <= CJK_END:
            return True   # 命中中文即返回真
    return False          # 全部不是中文则返回假

# 行内 HTML 标签白名单：这些标签在 Markdown 里没有等价写法，用户会直接手写。
# 为什么必须处理：Markdown 语法里根本没有下划线，用户表达「下划线」只能写 <u>…</u>；
# 早期版本不认它，于是生出的 Word 里原样印着「<u>本报告数据截至…</u>」这串标签（实测）。
INLINE_HTML_TAGS = ("u", "ins", "del", "s", "sub", "sup", "span", "b", "i", "em",
                    "strong", "small", "mark", "code", "kbd", "br")

# 去掉行内 HTML 标签，但保留标签包着的文字。
# 下划线、上标、下标这些「有实际排版含义」的标签由各载体的渲染器按原文还原，
# 这里只负责把标签符号本身摘掉，避免它以字面形式印在纸上。
def strip_inline_html(text):
    for tag in INLINE_HTML_TAGS:                                  # 逐个标签清理
        text = re.sub(rf"</?{tag}(?:\s[^>]*)?/?>", "", text, flags=re.IGNORECASE)   # 连同属性一起去掉
    return text

# 把带 <u>／<ins> 的文本拆成 [(文字, 是否下划线)]，供 DOCX 逐段设置下划线。
# 返回的片段按原顺序拼接一定等于「标签被剥掉后的原文」，不会丢字。
def split_underline(text):
    parts = []                                                    # 结果片段
    pattern = re.compile(r"<(u|ins)>(.*?)</\1>", re.IGNORECASE | re.DOTALL)   # 成对的下划线标签
    pos = 0                                                       # 上一次匹配结束的位置
    for match in pattern.finditer(text):                          # 逐个匹配
        if match.start() > pos:                                   # 标签之前还有普通文字
            parts.append((text[pos:match.start()], False))        # 记为非下划线片段
        parts.append((match.group(2), True))                      # 标签内的文字记为下划线片段
        pos = match.end()                                         # 游标移到标签之后
    if pos < len(text):                                           # 剩下还有普通文字
        parts.append((text[pos:], False))                         # 记为非下划线片段
    return parts or [(text, False)]                               # 没有任何标签时整体作一段

# 去掉 Markdown 的行内标记，只保留纯文本。
# 为什么收在公共库：build_docx 与 build_html 都要用它，各自实现会漂移
# （曾经两版对斜体的处理不一致，同一份 Markdown 出两种载体结果不同）。
def strip_inline(text):
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)        # 去掉图片语法
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)    # 链接只保留文字
    text = text.replace("**", "").replace("__", "")          # 去掉粗体标记
    text = re.sub(r"(?<!\*)\*(?!\*)", "", text)              # 去掉斜体标记
    text = text.replace("`", "")                             # 去掉行内代码标记
    text = strip_inline_html(text)                           # 去掉 <u> 这类行内 HTML 标签，保留其中文字
    return text.strip()                                      # 返回纯文本

# ─────────────────────────────────────────────────────────────
# Markdown 块解析：docx / html 两种载体共用这一份
#
# 为什么收在这里：build_docx 与 build_html 各自实现过一遍，两份代码九成相同、
# 剩下一成慢慢漂移（有序列表、引用、分隔线曾经一边支持一边不支持）。
# 同一份 Markdown 出多种载体，解析只能有一份。
#
# keep_inline 决定要不要剥掉 **加粗**、[链接](url) 这类行内标记：
#   · DOCX：正文最后是纯文本，剥掉（False）
#   · 公众号 HTML：行内标记要转成 <strong>、<a>，保留（True）
# 代码块永远原样保留，不做任何处理。
# ─────────────────────────────────────────────────────────────
# 文本里有没有「要按原文还原的下划线标签」。有就得把原始行一起带上，
# 因为 clean() 会把标签剥成纯文本，到渲染阶段就再也看不出哪里该加下划线了。
UNDERLINE_TAG_PATTERN = re.compile(r"</?(?:u|ins)(?:\s[^>]*)?>", re.IGNORECASE)

# 构造「文本 + 原文」两个字段。原文只在含下划线标签时才非空，避免给每个块都塞一份全文。
def _text_fields(raw_line, cleaned_text):
    raw = raw_line if UNDERLINE_TAG_PATTERN.search(raw_line) else ""   # 只有含标签才留原文
    return {"text": cleaned_text, "raw": raw}                          # 返回两个字段

# 把「被空行切开」的相邻引用块合并成一块，让引用分段只取决于内容、不取决于写法。
# 为什么必须合并：同一段引文，作者在段与段之间写不写「>」，解析结果完全不同 ——
#   · `> 第一段。` + 空行 + `> 第二段。`   → 解析成两个引用块（旧行为）
#   · `> 第一段。` + `>` + `> 第二段。`     → 解析成一个引用块的两段
# 两种写法表达的是同一个意思，排版却不一样：前者在两块之间会多出一份块外间距，
# 引文看上去被拆成了两拨（实测截图里就是这种「一会松一会紧」）。
# 这里只在解析末尾做合并：中间只被空行隔开的引用块合成一块，段列表直接拼接。
# 合并的边界很严格 —— 中间只要夹着别的块（段落、标题、表格…）就不动，
# 所以「引文 → 正文 → 引文」这种真正独立的两段引文绝不会被误并成一块。
def merge_adjacent_quotes(blocks):
    merged = []                                             # 合并后的块列表
    for block in blocks:                                    # 逐个检查解析出的块
        previous = merged[-1] if merged else None           # 取上一块（可能没有）
        if (block.get("type") == "quote"                   # 当前块是引用块
                and previous is not None                    # 且前面还有块
                and previous.get("type") == "quote"):       # 且上一块也是引用块（中间没夹别的块）
            paragraphs = previous.get("paragraphs") or []   # 取上一块已有的段落列表
            paragraphs = paragraphs + (block.get("paragraphs") or [])   # 拼接当前块的段落
            previous["paragraphs"] = paragraphs             # 写回段落列表
            previous["text"] = " ".join(paragraphs)         # 同步兼容字段（只认 text 的载体照旧能用）
        else:                                               # 不是相邻引用块
            merged.append(block)                            # 原样收进结果
    return merged                                           # 返回合并后的块列表

# 给解析出来的块做「结构体检」：这份稿子到底有没有层级，要不要先问用户。
#
# 为什么必须有一份公共判定：结构没定就往下走，是最贵的一种错误 ——
# 生成出来的 Word 里标题全部退化成正文段落，用户拿到的是「一整篇没有任何层次的文档」，
# 只能推倒重来。判定收在这里，三个生成脚本与前置体检脚本读的都是同一份结论，
# 不会出现「这个脚本说有结构、那个说没有」。
#
# 判定只描述事实，不替用户拍板：要不要分节、分成几节，一律由用户确认。
def source_structure_report(blocks):
    levels = {}                                            # 各级标题的数量，形如 {1: 2, 2: 5}
    paragraphs = 0                                         # 正文段落数（不含标题）
    lists = 0                                              # 列表项数
    quotes = 0                                             # 引用块数
    tables = 0                                             # 表格数
    chars = 0                                              # 正文字数（中文字符＋西文单词的粗略量，用于判断「是不是一大坨」）
    for block in blocks:                                   # 逐个块统计
        kind = block.get("type")                           # 块类型
        if kind == "heading":                              # 标题
            level = int(block.get("level") or 1)           # 取层级
            levels[level] = levels.get(level, 0) + 1       # 该层计数加一
        elif kind == "paragraph":                          # 正文段落
            paragraphs += 1                                # 段落计数加一
            chars += len(block.get("text") or "")          # 累计字数
        elif kind == "list":                               # 列表项
            lists += 1                                     # 列表计数加一
            chars += len(block.get("text") or "")          # 列表文字也算篇幅
        elif kind == "quote":                              # 引用块
            quotes += 1                                    # 引用计数加一
            chars += len(block.get("text") or "")          # 引用文字也算篇幅
        elif kind == "table":                              # 表格
            tables += 1                                    # 表格计数加一
            for row in block.get("rows") or []:            # 逐行
                for cell in row:                           # 逐格
                    chars += len(cell or "")               # 表格文字也算篇幅
    headings = sum(levels.values())                        # 标题总数
    # 跳级：有 H3 却没有 H2，Word 里会显示成层级断裂（用户看到的是「标题忽大忽小」）
    skipped = []                                           # 被跳过的层级
    if levels:                                             # 有标题才判断
        for level in range(1, max(levels) + 1):            # 从第 1 级查到最深一级
            if level not in levels:                        # 这一级一个标题都没有
                skipped.append(level)                      # 记为跳过
    flat = headings == 0                                   # 全篇没有标题＝没有结构
    # 「一大坨」：正文只有一个段落却写了很长 —— 用户直接粘过来的一段文字常是这样，
    # 连分段都没有。这种稿子即便套上规格也只是把一整块文字铺满几页，必须先跟用户确认怎么分段。
    blob = paragraphs <= 1 and chars >= 200                # 单段且字数可观
    questions = []                                         # 建议向用户确认的问题
    if flat:                                               # 没有结构
        questions.append("这份稿子一个标题都没有。你是要它保持没有标题（当一篇文章排），"
                         "还是要我按内容给出分节建议？")
        questions.append("如果要分节，分成几节、每节覆盖哪几段？（我给出建议，你增删）")
        # 篇名与小标题都是**内容项**，必须由用户点头；模型列出来只算建议，不算定稿。
        # 实测踩过的坑：只问了「分成几节」，标题文字直接照模型给的用了 —— 结构对、标题不合口味，
        # 用户照样要返工，等于白排一遍。
        questions.append("这份稿子要不要篇名（总标题）？我给 2–3 个候选，你选一个、自己写，或者不要。")
        questions.append("每一节的小标题文字以谁为准：照用我给的候选，还是你逐条改？")
    if blob:                                               # 连分段都没有
        questions.append("这份稿子只有一整段。要不要我按语义给出分段建议，你确认后再生成？")
    if skipped:                                            # 层级跳跃
        questions.append(f"标题层级里有跳级（缺第 {'、'.join(str(item) for item in skipped)} 级），"
                         "要不要我补齐层级，还是保持原样？")
    needs_confirmation = flat or blob                      # 只要命中任一条，就必须先问用户
    if flat and blob:                                      # 既没标题也没分段
        verdict = "无结构：既没有标题层级，也没有分段"
    elif flat:                                             # 只有标题缺失
        verdict = "无结构：全篇都是正文，没有标题层级"
    elif blob:                                             # 只有分段缺失
        verdict = "分段缺失：正文只有一整段"
    elif skipped:                                          # 有结构但层级断裂
        verdict = "结构可用，但标题层级有跳跃"
    else:                                                  # 正常
        verdict = "结构可用"
    return {"headings": headings,                          # 标题总数
            "levels": levels,                              # 各级标题数量
            "paragraphs": paragraphs,                      # 正文段落数
            "lists": lists,                                # 列表项数
            "quotes": quotes,                              # 引用块数
            "tables": tables,                              # 表格数
            "chars": chars,                                # 正文字数
            "skipped_levels": skipped,                     # 被跳过的层级
            "flat": flat,                                  # 有没有标题层级
            "blob": blob,                                  # 有没有分段
            "needs_confirmation": needs_confirmation,       # 要不要先问用户
            "verdict": verdict,                            # 中文判定
            "questions": questions}                        # 建议确认的问题清单

# 把结构体检结论写成给人看的中文报告。三个生成脚本与 structure_check.py 共用同一份措辞，
# 免得生成端说「正文 0 个标题」、体检端说「文档缺少层级」，用户以为是两件事。
def describe_structure(report):
    lines = []                                             # 逐行拼报告
    level_text = "、".join(f"{level} 级 {count} 个"    # 各级数量，如「1 级 1 个、2 级 3 个」
                          for level, count in sorted(report["levels"].items())) or "无"   # 没有任何标题时写「无」
    lines.append(f"结构体检：标题 {report['headings']} 个（{level_text}），"                # 标题统计
                 f"正文 {report['paragraphs']} 段，列表 {report['lists']} 项，"            # 段落与列表统计
                 f"引用 {report['quotes']} 处，表格 {report['tables']} 张，"                # 引用与表格统计
                 f"合计约 {report['chars']} 字")                                          # 篇幅
    lines.append(f"判定：{report['verdict']}")                                              # 中文判定
    for question in report["questions"]:                                                    # 逐条列出要问用户的问题
        lines.append(f"  待确认：{question}")                                                # 问题本身
    return "\n".join(lines)                                                                # 拼成完整报告

def parse_markdown_blocks(text, keep_inline=False):
    # 行内标记的处理方式：保留行内标记时只去空白，否则连标记一起剥掉。
    # 两种情况都要去空白 —— 表格单元格、标题文字前后带空格在三种载体里都是坏味道。
    def clean(value):
        return value.strip() if keep_inline else strip_inline(value)
    blocks = []                                              # 初始化块列表
    lines = text.split("\n")                                 # 按行切分
    index = 0                                                # 行索引游标
    while index < len(lines):                                # 逐行扫描
        line = lines[index]                                  # 取当前行
        stripped = line.strip()                              # 去首尾空白
        if not stripped:                                     # 空行
            index += 1                                       # 跳过
            continue                                         # 处理下一行
        if stripped.startswith("```") or stripped.startswith("~~~"):   # 围栏代码块
            index += 1                                       # 越过开始围栏
            buffer = []                                      # 收集代码行
            while index < len(lines) and not lines[index].strip().startswith(("```", "~~~")):   # 直到遇到结束围栏
                buffer.append(lines[index])                  # 收集一行
                index += 1                                   # 游标前进
            index += 1                                       # 越过结束围栏
            blocks.append({"type": "code", "text": "\n".join(buffer)})   # 记录代码块
            continue                                         # 处理下一块
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)    # 标题行
        if heading:                                          # 命中标题
            blocks.append({"type": "heading", "level": len(heading.group(1)),
                           "text": clean(heading.group(2))})   # 记录标题
            index += 1                                       # 游标前进
            continue                                         # 处理下一块
        if stripped.startswith("|"):                         # 表格块
            rows = []                                        # 收集表格行
            while index < len(lines) and lines[index].strip().startswith("|"):   # 连续表格行
                rows.append(lines[index].strip())            # 收集一行
                index += 1                                   # 游标前进
            aligns = []                                      # 记录每列对齐标记
            body_rows = rows                                 # 默认所有行都是数据行
            if len(rows) >= 2 and re.match(r"^\|[\s:|-]+\|$", rows[1]):   # 第二行是分隔行
                for cell in rows[1].strip("|").split("|"):   # 逐格解析对齐标记
                    cell = cell.strip()                      # 去空白
                    if cell.startswith(":") and cell.endswith(":"):   # 两侧冒号：居中
                        aligns.append("center")              # 居中
                    elif cell.endswith(":"):                 # 右侧冒号：右对齐
                        aligns.append("right")               # 右对齐
                    elif cell.startswith(":"):               # 左侧冒号：左对齐
                        aligns.append("left")                # 左对齐
                    else:                                    # 没有标记
                        aligns.append("")                    # 交给规格默认值（空串＝不干预）
                body_rows = [rows[0]] + rows[2:]             # 去掉分隔行
            data = [[clean(cell) for cell in row.strip("|").split("|")] for row in body_rows]   # 拆分单元格
            blocks.append({"type": "table", "rows": data, "aligns": aligns})   # 记录表格与对齐标记
            continue                                         # 处理下一块
        if stripped.startswith(">"):                         # 引用块
            # 引用块要分成「段」，不能一路拼成一段。
            # 实测踩过的坑：一个引用里隔了「>」空行，本来是两段，旧代码把空行也当成
            # 内容拼进去，结果两段合成一段、语义被改（引用里正是换段在表达递进关系）。
            # 分段规则一律「按内容」，不看作者怎么写空行，三种写法都要得到同样的分段：
            #   ① 空引用行（>）           → 分段（旧代码已支持）
            #   ② 段间只留一个普通空行     → 由后面 merge_adjacent_quotes 合并成一块再分段
            #   ③ 引用里的列表项（- / 1.） → 每一项自成一段（旧代码会并成一行，见下）
            paragraphs = []                                  # 引用内部的段落列表
            buffer = []                                      # 当前段落的行缓冲
            # 引用里的列表标记：一行以列表符号开头就说明「这是一项」，要另起一段。
            # 旧代码把整块引用的各行按「空引用行」分段，于是 `> - 第一条` / `> - 第二条`
            # 被并成一段排成「- 第一条 - 第二条」一行，引用里引的列表结构直接没了（实测）。
            list_marker = re.compile(r"^([-*+]\s+|\d+[.)]\s+|[一二三四五六七八九十]+、)")   # 列表/序数标记
            while index < len(lines) and lines[index].strip().startswith(">"):   # 连续的引用行
                # 去掉引用符号。连续多个 > 是「引用套引用」，本 skill 的载体（Word/公众号）
                # 都是平面渲染，留着就会把「>」原样印出来（实测出现过「> 内层。」），所以一并剥掉。
                content = re.sub(r"^(>\s*)+", "", lines[index].strip()).strip()   # 剥掉全部前导引用符号
                if content:                                  # 这一行有内容
                    if buffer and list_marker.match(content):   # 上一行还是普通内容，这一行是列表项
                        paragraphs.append(" ".join(buffer))   # 先把上一段收尾
                        buffer = []                           # 清空缓冲
                    buffer.append(content)                   # 收进当前段落
                elif buffer:                                 # 空引用行 = 段落分隔，且当前段有内容
                    paragraphs.append(" ".join(buffer))      # 收尾当前段落
                    buffer = []                              # 清空缓冲，准备下一段
                index += 1                                   # 游标前进
            if buffer:                                       # 收尾最后一段
                paragraphs.append(" ".join(buffer))          # 记录
            # 列表项自己也已经是独立一段了；保底逻辑不变
            if not paragraphs:                               # 整块都是空引用行
                paragraphs = [""]                            # 保底一个空段，避免下游拿不到东西
            blocks.append({"type": "quote",                  # 记录引用块
                           "text": clean(" ".join(paragraphs)),   # 兼容字段：并成一段的纯文本，供只认 text 的载体用
                           "paragraphs": [clean(p) for p in paragraphs]})   # 分段后的内容，供能分段的载体用
            continue                                         # 处理下一块
        if re.match(r"^[-*+]\s+", stripped):                  # 无序列表项
            body = re.sub(r"^[-*+]\s+", "", stripped)         # 去掉列表符号后的内容
            blocks.append({"type": "list", "ordered": False,
                           **_text_fields(body, clean(body))})   # 记录列表项（含可能的原文）
            index += 1                                       # 游标前进
            continue                                         # 处理下一块
        if re.match(r"^\d+[.)]\s+", stripped):                # 有序列表项
            body = re.sub(r"^\d+[.)]\s+", "", stripped)       # 去掉序号后的内容
            blocks.append({"type": "list", "ordered": True,
                           **_text_fields(body, clean(body))})   # 记录列表项（含可能的原文）
            index += 1                                       # 游标前进
            continue                                         # 处理下一块
        if re.match(r"^[-*_]{3,}$", stripped):               # 分隔线
            blocks.append({"type": "rule"})                  # 记录分隔线
            index += 1                                       # 游标前进
            continue                                         # 处理下一块
        # 独占一行的 HTML 锚点（如 <a id="dish-1"></a>）。
        # 为什么要单独认出来：它是网页的跳转目标，在 Word 里毫无意义。
        # 若当成普通段落，Word 会把这串标签原样印出来。各载体自己决定收不收：
        # HTML 要保留（公众号目录靠它跳转），DOCX 直接丢掉。
        anchor = re.match(r'^<a\s+id="([^"]+)"\s*>\s*</a>$', stripped)   # 只认「单独成行、只有 id」的锚点
        if anchor:                                           # 命中锚点
            blocks.append({"type": "anchor", "id": anchor.group(1)})   # 记录锚点 id
            index += 1                                       # 游标前进
            continue                                         # 处理下一块
        # 独占一行的图片。以前由 strip_inline 直接删掉，所有载体全都拿不到图片；
        # 现在解析成独立块，交给各载体自己决定怎么放（DOCX 插图、HTML 出 <img>）。
        image = re.match(r'^!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)$', stripped)   # 图片语法，目标里不允许空格
        if image:                                            # 命中图片
            blocks.append({"type": "image", "alt": image.group(1).strip(), "src": image.group(2)})   # 记录图片块
            index += 1                                       # 游标前进
            continue                                         # 处理下一块
        blocks.append({"type": "paragraph", **_text_fields(stripped, clean(stripped))})   # 其余按普通段落处理
        index += 1                                           # 游标前进
    return merge_adjacent_quotes(blocks)                     # 合并相邻引用块后返回（引用分段只看内容，不看写法）

# 判断一个 DOCX 段落是不是标题，是就返回层级（1-6），不是返回 0。
# 为什么收在公共库：convert_docx（给现成 Word 重排）与 extract_source（把 Word 抽成草稿）
# 各写过一份，其中一份不读大纲级别，于是「样式名被改过但大纲级别还在」的标题
# 一个脚本认、另一个不认。判定只能有一份。
def docx_heading_level(paragraph):
    name = (paragraph.style.name if paragraph.style is not None else "") or ""   # 取样式名，防御性处理
    match = re.search(r"Heading\s*(\d)", name)              # 英文样式名 Heading 1
    if match:                                                # 命中英文样式
        return int(match.group(1))                           # 返回层级
    match = re.search(r"标题\s*(\d)", name)                  # 中文样式名「标题 1」
    if match:                                                # 命中中文样式
        return int(match.group(1))                           # 返回层级
    # 样式名不可靠时，读段落属性里的 outlineLvl（大纲级别），它是 Word 判断层级的底层依据。
    # python-docx 只在安装了 docx 的环境里才有，所以延迟导入，避免影响只出 HTML 的场景。
    try:
        from docx.oxml.ns import qn                          # 命名空间工具
    except ImportError:                                      # 没装 python-docx
        return 0                                             # 只能靠样式名，判定结束
    ppr = paragraph._p.find(qn("w:pPr"))                     # 查找段落属性节点
    if ppr is not None:                                      # 若存在
        outline = ppr.find(qn("w:outlineLvl"))               # 查找大纲级别节点
        if outline is not None:                              # 若存在
            value = outline.get(qn("w:val"))                 # 取出级别值
            if value is not None and int(value) < 6:         # 只接受 0-5，对应 1-6 级
                return int(value) + 1                        # 换算成 1-6 级
    return 0                                                 # 不是标题

# 读取规格卡 YAML 文件，返回 Python 字典
# ─────────────────────────────────────────────────────────────
# 预设目录与读取路径
#
# 这里的教训（2026-09-20 实测）：`save_preset.py` 能把预设写进
# skill 目录里的 `references/presets/_user/`，但**没有任何一条读取路径认它** ——
# `load_spec()` 只吃纯 YAML，拿预设 .md 去喂它会抛
# `yaml.parser.ParserError: expected '<document start>'`；
# `infer_structure.load_preset_rules()` 又只在**内置**预设目录里找。
# 结果就是「能存、不能调」，闭环断在保存和读取之间。
# 下面把读取收进一个函数，内置与用户预设一视同仁。
# ─────────────────────────────────────────────────────────────

# skill 自身的根目录（本文件在 scripts/ 下，向上一级即根目录）
SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─────────────────────────────────────────────────────────────
# 两层结构：出厂规则 与 用户数据
#
# skill 目录里只放「出厂规则」：代码、内置预设、标准核验记录、问题清单的出厂版本。
# 这些东西随 git 更新整体替换，所以**一行都不该被用户改写** —— 改了下次 pull 就没了。
# 用户在使用过程中产生的东西（自存预设、遇到的问题、核验过的标准、查到的字体授权）
# 一律放进用户数据目录：
#
#   ~/.local/share/doc-format/            用户数据根目录（DOC_FORMAT_HOME 可覆盖）
#   ├── presets/                          用户自存预设 —— 用户的资产，丢了找不回来
#   ├── known-issues.md                   用户自己遇到的问题与处置
#   ├── standards.md                      用户核验或更正过的标准记录
#   └── fonts.md                          用户补充的字体授权与排字坑
#
#   ~/.cache/doc-format/font-memory.json  字体记忆 —— 缓存，删了下次自动重建
#
# 规矩三条：**运行时读两份**（出厂 + 用户）、**写只写用户目录**、**冲突时用户覆盖出厂**。
# 目标是「升级不覆盖用户数据」：用户 pull 新版本、重装 skill、换 agent，他自己攒的东西都不动。
# ─────────────────────────────────────────────────────────────
USER_HOME_ENV = "DOC_FORMAT_HOME"                                        # 覆盖用户数据根目录的环境变量

# 用户数据根目录：用户自己产生的一切都放这儿
def user_data_dir():
    override = os.environ.get(USER_HOME_ENV)                             # 先看环境变量有没有指定
    if override:                                                         # 指定了就用它
        return os.path.abspath(os.path.expanduser(override))             # 展开 ~ 并转成绝对路径
    return os.path.join(os.path.expanduser("~"), ".local", "share", "doc-format")   # 默认位置

# 用户自存预设目录
def user_preset_dir():
    return os.path.join(user_data_dir(), "presets")                       # 用户数据目录下的 presets/

# 旧位置：早期版本把用户预设写在 skill 目录里，老用户可能还有存货躺在那里
def legacy_user_preset_dir():
    return os.path.join(SKILL_ROOT, "references", "presets", "_user")     # 只用于兼容读取与搬迁

# 出厂参考文件路径（只读）：skill 目录里的那一份
def factory_reference(name):
    return os.path.join(SKILL_ROOT, "references", name)                   # 例如 references/known-issues.md

# 用户层参考文件路径（可写）：用户数据目录里的同名文件
def user_reference(name):
    return os.path.join(user_data_dir(), name)                            # 例如 …/doc-format/known-issues.md

# 一份参考文件的两层路径，**用户层在前** —— 调用方按顺序找，第一个命中的就是生效的那份
def reference_layers(name):
    return (user_reference(name), factory_reference(name))                # （用户，出厂）

# 把一份参考文件的两层内容都读出来，返回 [(来源, 文本)]，用户层在前；缺的那层自动跳过
def read_reference_layers(name):
    layers = []                                                           # 结果列表
    for path, label in zip(reference_layers(name), ("用户数据", "出厂规则")):   # 逐个位置读
        try:                                                              # 文件可能不存在
            with open(path, encoding="utf-8") as handle:                  # 打开文件
                layers.append((label, handle.read()))                      # 记下来源与全文
        except OSError:                                                    # 读不到就跳过这一层
            continue                                                       # 继续读下一层
    return layers                                                          # 返回所有读到的层

# 预设查找顺序：用户目录 → 旧位置 → 内置。
# 用户那份排在最前，是为了「用户改了出厂预设，升级不会把他的改动冲掉」——
# 他把自己改过的预设放进用户目录，同名就覆盖内置那份。
def preset_search_dirs():
    return (
        user_preset_dir(),                                               # 用户自存预设（优先，覆盖出厂）
        legacy_user_preset_dir(),                                        # 用户自存预设（旧位置，兼容用）
        os.path.join(SKILL_ROOT, "references", "presets"),               # 内置预设（出厂）
    )

# 预设文件里 YAML 参数块的匹配式。带 `yaml` 语言标记的围栏代码块才算，
# 免得把正文里其它代码块误当成参数。
YAML_BLOCK_RE = re.compile(r"```yaml[ \t]*\n(.*?)\n```", re.S)

# 按预设标识找预设文件，找到返回路径，找不到返回 None。
# 允许传「标识」或「带 .md 的标识」两种写法。
def preset_file(preset_id):
    if not preset_id:                                     # 空值直接返回
        return None                                       # 没有可找的
    name = str(preset_id).strip()                         # 去掉首尾空白
    if not name:                                          # 去空白后为空
        return None                                       # 没有可找的
    filename = name if name.endswith(".md") else name + ".md"   # 补上扩展名
    for directory in preset_search_dirs():                # 逐个预设目录查找
        candidate = os.path.normpath(os.path.join(directory, filename))   # 拼出候选路径并规范化
        if os.path.exists(candidate):                     # 命中
            return candidate                              # 返回路径
    return None                                           # 两处都没有

# 从预设文件正文里抽出 YAML 参数块；抽不到返回空串
def extract_yaml_block(text):
    match = YAML_BLOCK_RE.search(text or "")               # 找第一个 yaml 围栏块
    return match.group(1) if match else ""                 # 返回块内容或空串

# 读规格卡。三种入参都认：
#   ① 纯 YAML 规格卡（build/typography.spec.yaml）—— 整个文件就是 YAML
#   ② 预设文件的路径（~/.local/share/doc-format/presets/我的报告格式.md）—— YAML 在 ```yaml 代码块里
#   ③ 预设标识（book-cn、我的报告格式）—— 自动到内置与用户预设目录里找
# 读不到时打印人话提示并以退出码 2 结束，**不抛裸 traceback**：
# 这个函数被 10 个脚本调用，任何一个读到坏路径都会把 Python 调用栈糊到用户脸上，
# 用户会以为 skill 坏了（其实是参数写错），排错方向直接跑偏。
def load_spec(path):
    target = path                                          # 实际要读的文件
    if target is None or not os.path.exists(str(target)):  # 不是现成文件，可能是预设标识
        found = preset_file(target)                        # 按标识找预设
        if found is None:                                  # 也找不到
            print(f"找不到规格卡或预设：{path}", file=sys.stderr)              # 说清问题
            print("  · 规格卡：给一个 .yaml 文件路径", file=sys.stderr)         # 给出正确写法
            print("  · 预设：给预设标识（如 book-cn）或预设 .md 的路径", file=sys.stderr)   # 给出正确写法
            print("  · 看现有哪些预设：python3 scripts/save_preset.py --list", file=sys.stderr)   # 给出查法
            raise SystemExit(2)                            # 以用法错误退出，不留调用栈
        target = found                                     # 用找到的预设文件
    # 以 UTF-8 打开文件，避免中文注释导致解码失败
    with open(target, "r", encoding="utf-8") as handle:    # 读入文件
        text = handle.read()                               # 取出全文
    if str(target).endswith(".md"):                        # 预设文件：YAML 藏在代码块里
        block = extract_yaml_block(text)                   # 抽 YAML 块
        if not block:                                      # 抽不到
            print(f"这个预设文件里没有 ```yaml 代码块，读不出规格：{target}", file=sys.stderr)   # 说明原因
            raise SystemExit(2)                            # 以用法错误退出
        text = block                                       # 只用 YAML 块
    try:                                                   # YAML 可能写坏
        spec = yaml.safe_load(text)                        # 安全解析 YAML
    except yaml.YAMLError as error:                        # 解析失败
        print(f"规格卡 YAML 解析失败：{target}", file=sys.stderr)              # 说清是哪个文件
        print(f"  {error}", file=sys.stderr)                # 原样带上解析器的定位信息
        raise SystemExit(2)                                # 以用法错误退出，不留调用栈
    # 空文件会被解析成 None，需要转成空字典避免后续报错
    return spec if isinstance(spec, dict) else {}

# 返回某个源文件对应的「中间产物目录」：源文件同级的 build/ 子目录。
# 为什么要统一：规格卡、规范化稿、抽取稿、结构稿都是中间产物，
#   全堆在用户的书稿目录里会让交付目录一团乱（用户明确抱怨过）。
#   中间产物一律进 build/，书稿目录只留成品。md_normalize.normalized_path 用的是同一条约定。
def staging_dir(path):
    parent = os.path.dirname(os.path.abspath(path))   # 源文件所在目录
    if os.path.basename(parent) == "build":           # 已经在 build/ 里了
        return parent                                 # 直接用它，别再套一层 build/build/
    return os.path.join(parent, "build")              # 否则在源文件同级建 build/

# 读取 Markdown 源文件；normalize=True 时先在内存里做一遍规范化，不落盘、不留中间文件。
# 为什么要有这个开关：规范化稿默认会写到书稿同级的 build/ 子目录，
#   但用户只是想要成品时，中间文件没必要存在 —— 生成脚本直接吃内存里的清洗结果即可。
def read_markdown(path, normalize=False):
    # 文件不存在时给友好提示：这里同样被多个生成脚本共用，
    # 抛 FileNotFoundError 会让用户看到一段 Python 调用栈（实测过），
    # 而真实原因只是路径给错了。
    if not os.path.exists(str(path)):                   # 路径不存在
        print(f"输入文件不存在：{path}", file=sys.stderr)   # 说清问题
        raise SystemExit(2)                             # 以用法错误退出
    with open(path, "r", encoding="utf-8") as handle:   # 以 UTF-8 读取
        text = handle.read()                            # 读取全文
    if not normalize:                                   # 不需要规范化
        return text                                     # 直接返回原文
    import md_normalize                                 # 延迟导入，只有需要时才加载
    return md_normalize.normalized_text(path)           # 返回内存里规范化后的文本（沿用同一套规则与报告）

# 计算正文「一个空行」的高度（磅）。
# 中文排版里的「空一行」「空二行」都是相对于正文行距说的，不是标题自己的字号 ——
# 这样排出来的间距才能和版心的行网格对齐。
# 放在公共库的理由：生成端（build_docx）与校验端（verify_output）必须用同一个规则量同一件事，
# 否则会出现「生成时按 28 磅空一行、校验时按 1.2 倍字号算」这种两边对不上的假报警。
def body_line_height_pt(spec):
    paragraph_cfg = spec.get("paragraph") or {}            # 取正文段落配置
    if paragraph_cfg.get("line_spacing_mode") == "exact" and paragraph_cfg.get("line_spacing_pt"):   # 规格给了固定值行距
        return float(paragraph_cfg["line_spacing_pt"])     # 空行高度就是固定行距
    body_size = ((spec.get("fonts") or {}).get("body") or {}).get("size_pt") or 16   # 没有固定行距时取正文字号
    return float(body_size) * 1.2                          # 按 1.2 倍字号近似单倍行距

# 把磅值换算成 DOCX 的半磅单位（Word 的 w:sz 用半磅计数）
def pt_to_docx_sz(pt):
    # 半磅单位即磅值乘 2，并四舍五入取整
    return int(round(float(pt) * 2))

# 把固定值行距换算成 DOCX 的 w:line（二十分之一磅）
def pt_to_docx_line(pt):
    # 二十分之一磅即磅值乘 20，并四舍五入取整
    return int(round(float(pt) * 20))

# 把厘米换算成 DOCX 的 twips（二十分之一磅，1 英寸为 1440 twips）
def cm_to_twips(cm):
    # 先换算成英寸再乘 1440，得到 twips
    return int(round(float(cm) / 2.54 * 1440))

# 把毫米换算成 DOCX 的 twips
def mm_to_twips(mm):
    # 先换算成厘米，再复用厘米换算函数
    return cm_to_twips(float(mm) / 10.0)

# 把毫米换算成磅（PDF 坐标使用磅作为单位）
def mm_to_pt(mm):
    # 1 英寸为 25.4 毫米、72 磅，故毫米除以 25.4 再乘 72
    return float(mm) / 25.4 * 72.0

# ─────────────────────────────────────────────────────────────
# 纸张尺寸：把规格卡里的 `page.size` 名称翻译成毫米
#
# 为什么需要这张表：预设里一直写着 `size: A4`，但生成代码从来没人读它 ——
# 只有同时写了 width_mm/height_mm 才会真的设纸张，于是「声明 A4」的那些预设
# 落到 python-docx 默认模板的 Letter（215.9×279.4mm），A4 与 Letter 宽度差 5.9mm，
# 版心、每行字数、边距比例全跟着错。校验脚本又因为默认值兜底算出 210mm，
# 反而报「规格卡没写纸张宽度」，两边各说各话。这个 bug 一直藏到 2026-09-20 才被发现。
#
# 数值来源：ISO 216（A 系列）与 ISO 269、国内开本惯例，见 references/standards.md。
# 开本按「大 32 开 / 大 16 开」记 —— 中文书刊习惯用开本称呼，直接给成品尺寸。
# ─────────────────────────────────────────────────────────────

# 常用纸张尺寸表：键为规范名（比对前会把用户写法转成大写、去空格），值为 (宽mm, 高mm)
PAGE_SIZE_TABLE = {
    "A3": (297.0, 420.0),       # ISO 216 A3
    "A4": (210.0, 297.0),       # ISO 216 A4，公文与论文的国标指定幅面
    "A5": (148.0, 210.0),       # ISO 216 A5
    "B5": (176.0, 250.0),       # ISO B5（书刊常用 B5 指这个；国内另有 182×257 的「正 16 开」，不混用）
    "16K": (185.0, 260.0),      # 大 16 开成品尺寸
    "32K": (130.0, 184.0),      # 大 32 开成品尺寸
    "LETTER": (215.9, 279.4),   # 美制 Letter（8.5×11 英寸）
    "LEGAL": (215.9, 355.6),    # 美制 Legal（8.5×14 英寸）
}

# 中文写法与别名映射到表里的规范名。用户会写「A4」「a4」「16开」「大16开」，
# 都要认；认不出来就报错让用户写 width_mm/height_mm，绝不静默当成 A4。
PAGE_SIZE_ALIASES = {
    "A4纸": "A4",               # 常见口语写法
    "A3纸": "A3",               # 同上
    "A5纸": "A5",               # 同上
    "16开": "16K",              # 中文开本写法
    "大16开": "16K",            # 中文开本写法（大 16 开）
    "32开": "32K",              # 中文开本写法
    "大32开": "32K",            # 中文开本写法（大 32 开）
    "信纸": "LETTER",           # Letter 的常见中文叫法
}

# 把 `page.size` 归一成表里的键；归一不出来返回空串（表示「不认识」）
def normalize_page_size_name(name):
    key = re.sub(r"\s+", "", str(name or "")).upper()   # 去空格并转大写，容忍「A 4」「a4」
    key = PAGE_SIZE_ALIASES.get(key, key)                # 中文别名换成规范名
    return key                                           # 返回规范名（可能仍不在表里）

# 取规格声明的纸张尺寸，返回 (宽mm, 高mm)；任一边拿不到就返回 None。
# 优先级：① 显式 width_mm/height_mm（最精确，`size: custom` 走这条）
#         ② `size` 名称查表
# orientation 为 landscape 时宽高互换（横排页面）。
def page_size_mm(spec):
    page = spec.get("page") or {}                        # 取页面段
    width = page.get("width_mm")                         # 显式纸宽
    height = page.get("height_mm")                       # 显式纸高
    if not (width and height):                           # 没写全宽高，才去查名称表
        key = normalize_page_size_name(page.get("size"))   # 归一名称
        if key in PAGE_SIZE_TABLE:                       # 表里有
            width, height = PAGE_SIZE_TABLE[key]         # 取表里的毫米值
    if not (width and height):                           # 两种来源都没拿到
        return None, None                                # 返回空，交由调用方决定兜底或报错
    width, height = float(width), float(height)          # 统一成浮点
    if str(page.get("orientation") or "").lower().startswith("land"):   # 声明了横向
        width, height = height, width                    # 宽高互换
    return width, height                                 # 返回纸张尺寸

# 判断 `size` 是不是写了个不认识的名称；是的话返回提示文字，否则返回空串。
# 单独写一个函数是为了同一个提示能被生成端与校验端共用。
def unknown_page_size_note(spec):
    page = spec.get("page") or {}                        # 取页面段
    if page.get("width_mm") and page.get("height_mm"):   # 写了显式宽高，名称写什么都能出纸
        return ""                                        # 不提示
    key = normalize_page_size_name(page.get("size"))     # 归一名称
    if not key or key == "CUSTOM":                       # 没写，或明确写 custom 却没给宽高
        return ("规格卡没写纸张尺寸（page.size / page.width_mm），"
                "会退回 A4 兜底；想要别的幅面请写 page.size 或 width_mm + height_mm")
    if key in PAGE_SIZE_TABLE:                           # 认识这个名称
        return ""                                        # 不提示
    known = "、".join(sorted(PAGE_SIZE_TABLE))            # 列出支持的名称
    return (f"page.size 写的「{page.get('size')}」不在支持列表（{known}）里，"
            "会退回 A4 兜底；请改用列表里的名称，或直接写 width_mm + height_mm")

# ─────────────────────────────────────────────────────────────
# 字体检测：多后端取并集
#
# 设计原因（实测得出，不是想当然）：
#   1. 任何单一后端都会漏字体。macOS 上用 fc-list 只能看到 51 个中文字体族，
#      看不到 /System/Library/AssetsV2 里的苹方、楷体、兰亭黑；
#      而只用 fontTools 扫目录只能看到 108 个族，又看不到 fontconfig 索引的部分。
#   2. 换一台机器，可用后端完全不同。Linux 上通常有 fc-list；
#      Windows 上没有 fc-list，但有注册表和 C:\\Windows\\Fonts；
#      macOS 上 fc-list 只有装了 Homebrew fontconfig 才有。
#   所以：能用的后端全跑一遍，结果取并集。宁可多报「有」，也不要漏报成「没有」。
# ─────────────────────────────────────────────────────────────

# 判断当前操作系统，用于决定优先尝试哪些后端
def detect_platform():
    if sys.platform.startswith("darwin"):        # macOS
        return "macos"                           # 返回 macos
    if sys.platform.startswith("win"):           # Windows
        return "windows"                         # 返回 windows
    return "linux"                               # 其余一律按 Linux 处理（含 WSL）

# 返回本机可能存放中文字体的所有目录（只返回真实存在的）
def font_search_dirs():
    dirs = []                                     # 初始化目录列表
    platform = detect_platform()                  # 先判断平台
    if platform == "macos":                       # macOS 的字体位置
        dirs += [                                 # 用户与系统字体目录
            os.path.expanduser("~/Library/Fonts"),        # 用户自行安装的字体
            "/Library/Fonts",                             # 全机器共享的字体
            "/System/Library/Fonts",                      # 系统字体
            "/System/Library/Fonts/Supplemental",         # 系统附赠字体（宋体、楷体等）
        ]
        # Apple 把一部分中文字体放在 AssetsV2 的字体资产包里（苹方、楷体、兰亭黑等）
        dirs += sorted(glob.glob("/System/Library/AssetsV2/*Font*"))   # 通配展开所有字体资产目录
    elif platform == "windows":                   # Windows 的字体位置
        windir = os.environ.get("WINDIR", r"C:\\Windows")            # 取系统目录，缺省为 C:\\Windows
        dirs += [                                 # 系统字体目录
            os.path.join(windir, "Fonts"),                        # 系统字体
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),  # 当前用户字体
        ]
    else:                                         # Linux 的字体位置
        dirs += [                                 # 常见字体目录
            os.path.expanduser("~/.fonts"),                       # 用户字体（旧约定）
            os.path.expanduser("~/.local/share/fonts"),           # 用户字体（新约定）
            "/usr/share/fonts",                                   # 发行版字体
            "/usr/local/share/fonts",                             # 本地安装字体
        ]
    return [d for d in dirs if d and os.path.isdir(d)]                # 过滤掉不存在的目录

# 后端一：fontconfig 的 fc-list。Linux 与装了 fontconfig 的 macOS 可用
def families_from_fc_list():
    families = set()                                              # 初始化结果集合
    try:                                                          # fc-list 可能不存在，需要捕获异常
        result = subprocess.run(                                  # 调用 fc-list
            ["fc-list", ":lang=zh", "family"],                    # 只列出标记为中文的字体族
            capture_output=True,                                  # 捕获输出，避免刷屏
            text=True,                                            # 以文本形式返回
            timeout=30,                                           # 最多等 30 秒，避免卡死
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):        # 命令不存在或超时
        return families, "不可用"                                  # 返回空集与状态说明
    if result.returncode != 0:                                    # 命令执行失败
        return families, "执行失败"                                # 返回空集与状态说明
    for line in result.stdout.splitlines():                       # 逐行解析输出
        for part in line.split(","):                              # 一行可能含多个逗号分隔的别名
            name = part.strip()                                   # 去掉首尾空白
            if not name or name.lower() in {"regular", "bold", "light", "medium"}:   # 过滤样式名与空串
                continue                                          # 跳过该别名
            families.add(name)                                    # 收集字体族名
    return families, f"已用（{len(families)} 个族）"                # 返回结果与状态说明

# 中文字体文件名关键词表：当无法解析字体内部信息时，用文件名做粗判
CJK_FILENAME_KEYWORDS = (
    "song", "hei", "kai", "fang", "ming", "yahei", "yuanti", "sun", "han",   # 拼音类关键词
    "pingfang", "hiragino", "lantinghei", "stfang", "sthei", "stkai", "stsong",  # macOS 系关键词
    "noto sans cjk", "noto serif cjk", "source han", "sarasa", "lxgw", "wenkai",  # 开源系关键词
    "wqy", "wenquanyi", "droid sans fallback", "unifont",                    # Linux 常见中文回退字体
    "宋", "黑", "楷", "仿", "明", "雅黑", "苹方", "冬青", "华文", "思源", "文楷", "朱雀",  # 中文名关键词
)

# 中文字体「名字」特征表：用来判断 PDF/渲染结果里的某个字体名是不是中文字体。
# 与上面的文件名关键词表不是一回事：文件名里有 "sun""han" 这类短词，字体名（STSongti-SC-Regular）里没有，
# 所以两张表不能合并。以前这张表在 build_pdf / render_preview / verify_output 里各写了一份，
# 三份内容还不一样，同一次生成可能一个脚本说「有中文字体」另一个说「没有」。
CJK_FONT_NAME_MARKERS = (
    "song", "songti", "stsong", "stfang", "stkaiti", "stheiti", "sthei",   # 宋体/仿宋/楷体系
    "hei", "heiti", "kai", "kaiti", "fang", "fangsong", "ming",            # 黑体/楷体/仿宋/明朝体
    "pingfang", "hiragino", "lantinghei", "yuanti", "wenkai", "sarasa", "zhuque",   # macOS 与常见开源中文字体
    "noto", "source han", "sourcehan", "simsun", "simhei", "mincho", "gothic",     # Noto/思源/Windows/日文汉字字体
)

# 判断某个字体名是否像中文字体（用于 PDF 字体核对与渲图前的自检）
def looks_like_cjk_font(font_name):
    lowered = (font_name or "").lower()                       # 转小写便于匹配
    if ".notdef" in lowered or "lastresort" in lowered:       # 兜底字体说明没找到真正的中文字体
        return False                                          # 不算中文字体
    return any(marker in lowered for marker in CJK_FONT_NAME_MARKERS)   # 命中任一特征即算

# 判断某个字体文件名是否像中文字体（仅看文件名，属于粗判）
def filename_looks_cjk(filename):
    lowered = filename.lower()                                    # 转小写便于匹配
    for keyword in CJK_FILENAME_KEYWORDS:                         # 遍历关键词表
        if keyword in lowered:                                    # 命中任一关键词
            return True                                           # 判定为中文字体
    return False                                                  # 全部未命中

# 判断一个已经加载的字体对象是否覆盖中文。
# 为什么不用 cmap 判断：fontTools 解析一张中文字体的 cmap（三万字以上）要零点几秒，
#   108 个字体文件累计 8.9 秒（实测），而这一步只是为了回答「是不是中文字体」。
#   改用三个便宜特征，命中任一即算：文件名关键词、OS/2 声明覆盖 CJK、家族名关键词。
# 为什么不用「字形数量」这个更直觉的判据：Arial、Courier New、Apple Color Emoji 的字形数
#   都超过两千，会把它们当成中文字体混进「本机可用中文字体」清单里（实测多出 33 个西文字体）。
# 代价要如实记下（实测对比过改前改后两份清单）：
#   旧判据（解析 cmap 看能不能映射「中」字）在本机得到 350 个族、耗时 9.3 秒；
#   新判据得到 427 个族、耗时 0.9 秒，旧清单里有 6 个没捞回来：
#   AppleGothic、AppleMyungjo、GB18030 Bitmap、GungSeo、Osaka、궁서체 —— 都是日韩系统字体。
#   漏报的方向是安全的：只会让「本机可用中文字体」清单短一点，
#   不会把不存在的字体当成存在，也不会因此错误替换标准要求的字体
#   （宋体、黑体、楷体、仿宋、思源、Noto CJK、苹方、Songti SC、Heiti SC 一个没漏）。
def font_looks_cjk(font, path, family_names):
    if filename_looks_cjk(os.path.basename(path)):                # 特征一：文件名像中文字体
        return True                                               # 直接算
    try:                                                          # OS/2 表可能缺失
        ranges = [getattr(font["OS/2"], f"ulUnicodeRange{i}", 0) for i in (1, 2, 3, 4)]   # 四段 Unicode 范围位
        if len(ranges) > 1 and (ranges[1] >> 16) & 1:             # 特征二：位 48「CJK 统一表意文字」落在第二段第 16 位
            return True                                           # 字体自己声明覆盖 CJK
    except Exception:                                             # 读取失败
        pass                                                      # 继续看下一个特征
    for name in family_names:                                     # 特征三：家族名命中中文字体特征词
        # 这里刻意用「文件名关键词表」而不是「字体名特征表」：后者为 PDF 自检设计，
        # 只写 "noto" 就算数，会把 Noto Sans 这些纯西文字体全捞进来（实测多出 170 个族）。
        if filename_looks_cjk(name):                              # 命中即算
            return True                                           # 是中文字体
    return False                                                  # 三个特征都没命中

# 从字体文件的 name 表里读出所有族名（含本地化名），并判断该字体是否覆盖中文
def families_from_one_font_file(path, fonttools_ok):
    families = set()                                              # 初始化结果集合
    if not fonttools_ok:                                          # 没有 fontTools 时走文件名粗判
        if filename_looks_cjk(os.path.basename(path)):            # 文件名像中文字体
            families.add(os.path.splitext(os.path.basename(path))[0])   # 用去扩展名的文件名当族名
        return families                                           # 返回结果
    from fontTools.ttLib import TTFont, TTCollection               # 延迟导入，避免影响无依赖环境
    try:                                                          # 字体文件可能损坏，需要捕获异常
        if path.lower().endswith((".ttc", ".otc")):               # TTC/OTC 是多字体集合
            fonts = TTCollection(path, lazy=True).fonts           # 拆成多个字体对象
        else:                                                     # 普通 ttf/otf 单字体文件
            fonts = [TTFont(path, lazy=True)]                     # 包成列表统一处理
    except Exception:                                             # 文件损坏或格式不支持
        return families                                           # 返回空集，静默跳过
    for font in fonts:                                            # 逐个字体对象处理
        try:                                                      # 读取 name 表可能失败
            names = []                                            # 该字体的家族名列表
            for record in font["name"].names:                     # 遍历 name 表的所有记录
                if record.nameID in (1, 16):                      # 1 是家族名，16 是排版家族名
                    try:                                          # 记录可能是非 Unicode 编码
                        names.append(record.toUnicode())          # 转成字符串后记下
                    except Exception:                             # 转换失败则忽略该记录
                        pass                                      # 继续处理下一条
            if not font_looks_cjk(font, path, names):             # 用便宜特征判断是否为中文字体
                continue                                          # 不是中文字体则跳过
            families.update(n for n in names if n)                # 收下该字体的所有家族名
        except Exception:                                         # 某个字体对象读取失败
            continue                                              # 跳过，不影响其他字体
    return families                                               # 返回该文件贡献的族名

# 后端二：直接扫描字体目录并解析字体文件。跨平台通用，但速度较慢
def families_from_font_files():
    families = set()                                              # 初始化结果集合
    try:                                                          # fontTools 可能没装
        import logging                                            # 导入日志模块用于降噪
        import fontTools.ttLib                                    # 仅用于探测是否可导入
        logging.getLogger("fontTools").setLevel(logging.ERROR)    # 关闭 fontTools 的 warning 级日志
        logging.getLogger("fontTools.ttLib").setLevel(logging.ERROR)   # 关闭子模块日志
        fonttools_ok = True                                       # 标记依赖可用
    except ImportError:                                           # 导入失败
        fonttools_ok = False                                      # 标记依赖不可用，退回文件名粗判
    count = 0                                                     # 统计扫描到的字体文件数
    for root in font_search_dirs():                               # 遍历所有字体目录
        base_depth = root.rstrip("/").count("/")                  # 记录根目录层级，用于限制递归深度
        for dirpath, dirnames, filenames in os.walk(root):        # 递归遍历目录
            if dirpath.count("/") - base_depth >= 3:              # 超过 3 层就不再深入（AssetsV2 需要 3 层）
                dirnames[:] = []                                  # 清空待遍历子目录，实现剪枝
            for filename in filenames:                            # 遍历当前目录下的文件
                if not filename.lower().endswith((".ttf", ".otf", ".ttc", ".otc")):   # 只看字体文件
                    continue                                      # 非字体文件跳过
                count += 1                                        # 计数加一
                families |= families_from_one_font_file(os.path.join(dirpath, filename), fonttools_ok)   # 解析并合并族名
    return families, f"已用（扫描 {count} 个字体文件，{len(families)} 个族）"   # 返回结果与状态说明

# 后端三：Windows 注册表。Windows 上最权威的已安装字体清单
def families_from_windows_registry():
    families = set()                                              # 初始化结果集合
    try:                                                          # winreg 只在 Windows 上存在
        import winreg                                             # 导入注册表模块
    except ImportError:                                           # 非 Windows 平台
        return families, "不适用（非 Windows）"                     # 返回空集与说明
    keys = [                                                      # 两个注册表位置分别存系统字体与用户字体
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Fonts"),   # 系统级字体
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Fonts"),    # 用户级字体
    ]
    for hive, subkey in keys:                                     # 逐个位置读取
        try:                                                      # 键可能不存在
            with winreg.OpenKey(hive, subkey) as handle:          # 打开注册表键
                index = 0                                         # 从第 0 个值开始枚举
                while True:                                       # 循环直到抛异常表示枚举结束
                    try:                                          # 越界会抛 OSError
                        value, _ = winreg.EnumValue(handle, index)   # 读取一个值
                    except OSError:                               # 枚举结束
                        break                                     # 跳出循环
                    index += 1                                    # 索引加一
                    for part in str(value).split("&"):            # 一条值可能是「A & B & C」的多别名
                        name = part.strip()                       # 去掉空白
                        if name:                                  # 非空才收集
                            families.add(name)                    # 收集字体名
        except OSError:                                           # 键不存在或无权访问
            continue                                              # 跳过该位置
    return families, f"已用（注册表 {len(families)} 项）"           # 返回结果与状态说明

# 后端四：macOS 的 system_profiler。速度慢，但能覆盖多数系统字体
def families_from_macos_profiler():
    families = set()                                              # 初始化结果集合
    if detect_platform() != "macos":                              # 只在 macOS 上尝试
        return families, "不适用（非 macOS）"                       # 返回空集与说明
    try:                                                          # 命令可能不存在或超时
        result = subprocess.run(                                  # 调用 system_profiler
            ["system_profiler", "-json", "SPFontsDataType"],      # 以 JSON 输出字体信息
            capture_output=True, text=True, timeout=90,           # 最多等 90 秒，这个命令很慢
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):        # 不存在或超时
        return families, "不可用"                                  # 返回空集与说明
    try:                                                          # JSON 解析可能失败
        import json                                               # 导入 JSON 模块
        payload = json.loads(result.stdout or "{}")               # 解析输出，空串时按空对象处理
    except Exception:                                             # 解析失败
        return families, "解析失败"                                # 返回空集与说明
    def walk(node):                                               # 定义递归函数遍历 JSON 结构
        if isinstance(node, dict):                                # 遇到字典
            for key, value in node.items():                       # 遍历所有键值
                if key == "_name" and isinstance(value, str):     # 字体名存在 _name 字段里
                    families.add(value)                           # 收集字体名
                else:                                             # 其他字段继续递归
                    walk(value)                                   # 递归处理
        elif isinstance(node, list):                              # 遇到列表
            for item in node:                                     # 遍历列表元素
                walk(item)                                        # 递归处理
    walk(payload.get("SPFontsDataType", []))                      # 从字体数据段开始遍历
    return families, f"已用（{len(families)} 项）"                  # 返回结果与状态说明

# 缓存：同一进程内重复调用不必反复扫描
_FONT_CACHE = None                                                # 中文族名的模块级缓存
_FONT_ALL_CACHE = None                                            # 全部族名的模块级缓存
_BACKEND_CACHE = None                                             # 检测来源与后端状态

# ── 字体记忆：首次检测一次，之后只用记忆 ──
#
# 为什么从「每次实时检测」改成「记忆」：
#   全盘扫描一次约 9 秒（实测，绝大多数耗在解析字体文件的 cmap 上）。旧设计靠
#   「字体目录 mtime 变化」让缓存失效，而用户装一个字体就会改动目录 mtime ——
#   于是刚装完字体就必然重扫一遍，常规任务里也会因为缓存判不中而反复扫描。
#   用户要的是「首次检测一次，之后别再检」。
#
# 记忆里存三样东西：
#   ① cjk        —— 上次检测到的中文字体族
#   ② all        —— 上次检测到的全部字体族（含西文，用于 Times New Roman 这类检查）
#   ③ confirmed  —— 用户中途装上的字体（用户说了算，不必为它重扫全盘）
# 只有两种情况会重新全盘扫描：记忆文件不存在（首次使用），或用户显式要求（--refresh）。
FONT_MEMORY_VERSION = 2                                           # 记忆结构版本，改结构时递增即可作废旧记忆
FONT_MEMORY_ENV = "DOC_FORMAT_FONT_MEMORY"                        # 环境变量可覆盖记忆路径（便于测试与隔离）

# 返回字体记忆文件的路径
def font_memory_path():
    override = os.environ.get(FONT_MEMORY_ENV)                    # 先看环境变量有没有指定
    if override:                                                  # 指定了就用指定的
        return override                                           # 返回覆盖值
    return os.path.join(os.path.expanduser("~"), ".cache", "doc-format", "font-memory.json")   # 默认放用户缓存目录

# 读字体记忆。文件不存在、结构不对、版本不符都返回 None（表示需要做首次检测）
def load_font_memory():
    try:                                                          # 文件缺失、损坏、无权限都可能失败
        with open(font_memory_path(), "r", encoding="utf-8") as handle:   # 打开记忆文件
            payload = json.load(handle)                           # 解析 JSON
    except Exception:                                            # 任何异常
        return None                                               # 一律当成没有记忆
    if payload.get("version") != FONT_MEMORY_VERSION:             # 版本不符
        return None                                               # 弃用，触发重新检测
    if not isinstance(payload.get("cjk"), list):                  # 结构不对
        return None                                               # 弃用
    return payload                                                # 返回记忆内容

# 写字体记忆。写不进去也不能影响主流程
def save_font_memory(payload):
    target = font_memory_path()                                   # 记忆路径
    try:                                                          # 磁盘只读、路径异常等都可能失败
        os.makedirs(os.path.dirname(target), exist_ok=True)       # 确保目录存在
        body = dict(payload)                                      # 复制一份，避免改动调用方的字典
        body["version"] = FONT_MEMORY_VERSION                     # 写入结构版本
        with open(target, "w", encoding="utf-8") as handle:       # 打开写入
            json.dump(body, handle, ensure_ascii=False)           # 中文不转义，便于人工查看
        return True                                               # 写入成功
    except Exception:                                             # 写入失败
        return False                                              # 返回失败，调用方照常继续

# 真正扫描本机字体。只在「首次使用」或用户显式要求刷新时调用，一次约 9 秒。
# 返回 (中文字体集合, 全部字体集合, 后端状态说明)
def full_font_scan():
    families = set()                                              # 初始化中文字体并集
    backends = {}                                                 # 记录每个后端的状态，供报告使用
    # 第一档：常跑后端。fc-list 快而准，目录扫描覆盖它看不到的 AssetsV2 等位置
    for name, func in (                                          # 遍历常跑后端
        ("fc-list", families_from_fc_list),                       # 后端一：fontconfig
        ("字体文件扫描", families_from_font_files),                 # 后端二：目录扫描 + fontTools
    ):
        found, status = func()                                    # 执行后端，拿到结果与状态
        backends[name] = status                                   # 记录状态
        families |= found                                         # 并入结果集
    # 第二档：兜底后端。只有在第一档一无所获时才跑，因为它们慢（system_profiler 需 20 秒以上）
    # 而且会把非中文字体也一并列出来，污染「中文字体清单」的判断
    if not families:                                              # 第一档完全没结果，说明环境特殊
        for name, func in (                                       # 遍历兜底后端
            ("Windows 注册表", families_from_windows_registry),     # 兜底一：Windows 注册表
            ("system_profiler", families_from_macos_profiler),    # 兜底二：macOS 系统报告
        ):
            found, status = func()                                # 执行后端
            backends[name] = status                               # 记录状态
            families |= found                                     # 并入结果集
    else:                                                         # 第一档已有结果
        backends["兜底后端"] = "未启用（第一档已检测到字体）"          # 记录兜底未启用，避免用户误以为漏检
    # 过滤掉以点开头的内部字体（如 .Aqua Kana）和兜底字体，它们不是可供用户选择的字体
    families = {f for f in families if f and not f.startswith(".") and f != "LastResort"}   # 清洗结果
    return families, set(list_all_fonts_raw()), backends           # 连同全部字体一起返回

# 直接调用 fc-list 枚举全部字体族（不做记忆、不做缓存），供首次检测使用
def list_all_fonts_raw():
    families = set()                                              # 初始化结果集
    try:                                                          # fc-list 可能不存在或超时
        result = subprocess.run(                                  # 调用 fontconfig 列出全部族名
            ["fc-list", ":", "family"],                            # 冒号是「匹配全部字体」的 pattern，family 是要输出的字段
            capture_output=True, text=True, timeout=20,            # 捕获输出，最多等 20 秒
        )
        if result.returncode == 0:                                # 命令成功
            for line in result.stdout.splitlines():                # 逐行读取
                for part in line.split(","):                       # 一行里可能有多个别名，逗号分隔
                    name = part.strip()                            # 去掉首尾空白
                    if not name or name.lower() in {"regular", "bold", "light", "medium", "italic", "bold italic"}:   # 过滤样式名
                        continue                                   # 跳过样式名
                    families.add(name)                             # 收进结果集
    except Exception:                                             # 命令不存在、超时等
        families = set()                                          # 保持为空，表示无法枚举
    return families                                               # 返回结果

# 取字体集合：优先用记忆，没有记忆才做首次全盘检测
# 返回 (中文字体集合, 全部字体集合)
def font_sets(force=False):
    global _FONT_CACHE, _FONT_ALL_CACHE, _BACKEND_CACHE           # 声明要修改模块级缓存
    if _FONT_CACHE is not None and not force:                     # 进程内已有缓存且不强制刷新
        return _FONT_CACHE, (_FONT_ALL_CACHE or set())            # 直接返回
    memory = None if force else load_font_memory()                # 不是强制刷新才允许读记忆
    if memory:                                                    # 命中记忆
        cjk = set(memory.get("cjk") or [])                        # 取中文字体
        allf = set(memory.get("all") or [])                       # 取全部字体
        backends = dict(memory.get("backends") or {})             # 取后端状态
        # 用户中途装上的字体：只加记忆，不重扫全盘
        confirmed = memory.get("confirmed") or {}                 # 取已确认安装清单
        added = []                                                # 本次额外生效的字体
        for name, info in confirmed.items():                      # 逐个检查
            kind = (info or {}).get("kind", "cjk")                # 取字体类别
            allf.add(name)                                        # 全部字体里一定有它
            if kind == "cjk":                                     # 中文类的还要进中文字体清单
                cjk.add(name)                                     # 加入
            added.append(name)                                    # 记入生效清单
        scan_date = memory.get("scanned_at") or "未知"             # 取上次检测日期
        backends["来源"] = f"字体记忆（{scan_date} 检测），未重新扫描"   # 说明数据来源
        if added:                                                 # 有用户中途装的字体
            backends["用户新增"] = "、".join(sorted(added)[:8])     # 一并说明
        _FONT_CACHE, _FONT_ALL_CACHE, _BACKEND_CACHE = cjk, allf, backends   # 写入进程内缓存
        return _FONT_CACHE, _FONT_ALL_CACHE                       # 返回
    # 首次使用：全盘检测一次，然后写进记忆
    cjk, allf, backends = full_font_scan()                        # 执行完整扫描
    backends["来源"] = "首次全盘检测（已写入字体记忆，下次不再扫描）"      # 说明数据来源
    _FONT_CACHE, _FONT_ALL_CACHE, _BACKEND_CACHE = cjk, allf, backends   # 写入进程内缓存
    save_font_memory({                                            # 落盘记忆
        "scanned_at": datetime.date.today().isoformat(),          # 记下检测日期
        "cjk": sorted(cjk),                                       # 中文字体清单
        "all": sorted(allf),                                      # 全部字体清单
        "backends": {k: v for k, v in backends.items() if k != "来源"},   # 后端状态（去掉「来源」这项运行时信息）
        "confirmed": {},                                          # 用户中途装上的字体，初始为空
    })
    return _FONT_CACHE, _FONT_ALL_CACHE                           # 返回

# 枚举本机所有中文字体族名（首次检测一次，之后走记忆）
def list_cjk_fonts(force=False):
    return font_sets(force)[0]                                    # 取字体集合里的中文部分

# 枚举本机所有字体族（含西文），同样走记忆
def list_all_fonts(force=False):
    return font_sets(force)[1]                                    # 取字体集合里的全部部分

# 把「用户已安装某个字体」记进字体记忆，下次直接用，不必重扫全盘。
# 这是用户要求的机制：中途装上的字体只记一笔，不要每次都去自检。
def remember_font(name, kind="cjk", note=""):
    name = (name or "").strip()                                   # 规范化字体名
    if not name:                                                  # 空名字
        return False                                              # 直接失败
    memory = load_font_memory()                                   # 先读现有记忆
    if not memory:                                                # 还没有记忆（从未检测过）
        font_sets()                                               # 先做一次首次检测，把记忆建起来
        memory = load_font_memory()                               # 再读一次
        if not memory:                                            # 还是读不到（磁盘不可写）
            return False                                          # 返回失败
    confirmed = dict(memory.get("confirmed") or {})               # 取已确认清单
    confirmed[name] = {                                           # 写入这条字体
        "kind": kind,                                             # 中文还是西文
        "added_at": datetime.date.today().isoformat(),            # 记下日期，便于日后排查
        "note": note,                                             # 备注（例如用户是在哪一步装的）
    }
    memory["confirmed"] = confirmed                               # 放回记忆
    global _FONT_CACHE, _FONT_ALL_CACHE                           # 同步更新进程内缓存
    if _FONT_CACHE is not None:                                   # 已经加载过字体集合
        _FONT_ALL_CACHE = set(_FONT_ALL_CACHE or set()) | {name}  # 全部字体里加上它
        if kind == "cjk":                                         # 是中文类
            _FONT_CACHE = set(_FONT_CACHE) | {name}               # 中文字体里也加上
    return save_font_memory(memory)                               # 落盘

# 从记忆里移除一个字体（记错了、或用户卸载了字体时用）
def forget_font(name):
    name = (name or "").strip()                                   # 规范化字体名
    memory = load_font_memory()                                   # 读记忆
    if not memory:                                                # 没有记忆
        return False                                              # 返回失败
    confirmed = dict(memory.get("confirmed") or {})               # 取已确认清单
    if name not in confirmed:                                     # 记忆里本来就没有
        return False                                              # 返回失败
    del confirmed[name]                                           # 删掉这一条
    memory["confirmed"] = confirmed                               # 放回记忆
    return save_font_memory(memory)                               # 落盘

# 返回字体记忆的概况，供报告里说明「字体清单是哪来的、有多旧」
def font_memory_info():
    font_sets()                                                   # 确保字体集合已加载（可能触发首次检测）
    memory = load_font_memory() or {}                             # 读记忆（首次检测后一定有）
    source = (_BACKEND_CACHE or {}).get("来源", "未知")             # 取来源说明
    return {                                                      # 组织返回内容
        "来源": source,                                           # 来自记忆还是首次检测
        "检测日期": memory.get("scanned_at") or "未知",             # 上次全盘检测的日期
        "中文字体数": len(_FONT_CACHE or []),                      # 中文字体数量
        "全部字体数": len(_FONT_ALL_CACHE or []),                  # 全部字体数量
        "用户新增": sorted((memory.get("confirmed") or {}).keys()),   # 用户中途装上的字体
    }

# 返回本次字体检测用了哪些后端、各自状态如何，供报告里说明检测可信度
def font_detection_report():
    list_cjk_fonts()                                              # 确保已经跑过一次检测
    return dict(_BACKEND_CACHE or {})                             # 返回后端状态的副本

# ─────────────────────────────────────────────────────────────
# 字体替换候选表
#
# 设计原因：替代字体必须按平台给候选，再按「实时检测结果」挑第一个可用的。
#   原实现只写死了 macOS 的等价字体（STFangsong / Songti SC 等），
#   换到 Windows 上会被解析成不存在的字体，等于把问题从「缺字体」变成「静默掉字体」。
#   candidate 列表按优先级排列，越靠前越接近标准要求的字形。
# ─────────────────────────────────────────────────────────────

# 同类字体建议表：标准要求的字体 -> 各平台常见的同类字体（按接近程度排序）。
# 注意：本表**只用于生成给用户的候选清单**（font_check.py --suggest），
# 绝不在生成流程里自动挑一个顶上 —— 缺字体必须由用户决定装字体还是改用哪一个。
FALLBACK_CANDIDATES = {
    "仿宋_GB2312": {                                             # 公文正文规定的仿宋
        "macos": ["STFangsong", "华文仿宋", "Songti SC"],          # macOS：华文仿宋最接近
        "windows": ["FangSong", "仿宋", "FangSong_GB2312", "SimSun"],   # Windows：随系统自带仿宋
        "linux": ["Noto Serif CJK SC", "Source Han Serif SC", "AR PL UMing CN"],   # Linux：多为开源字体
    },
    "方正小标宋简体": {                                           # 公文标题与红头规定的小标宋
        "macos": ["Songti SC", "STSong"],                        # macOS：用宋体加粗近似
        "windows": ["SimSun", "宋体"],                            # Windows：宋体加粗近似
        "linux": ["Noto Serif CJK SC", "Source Han Serif SC"],    # Linux：开源宋体
    },
    "宋体": {                                                     # 标准里的宋体
        "macos": ["Songti SC", "STSong"],                        # macOS：宋体-简 / 华文宋体
        "windows": ["SimSun", "宋体"],                            # Windows：中易宋体
        "linux": ["Noto Serif CJK SC", "Source Han Serif SC", "AR PL UMing CN"],   # Linux：开源宋体
    },
    "SimSun": {                                                   # 宋体英文名
        "macos": ["Songti SC", "STSong"],                        # 同「宋体」
        "windows": ["SimSun"],                                   # 同「宋体」
        "linux": ["Noto Serif CJK SC", "Source Han Serif SC"],    # 同「宋体」
    },
    "黑体": {                                                     # 标准里的黑体
        "macos": ["Heiti SC", "PingFang SC", "Hiragino Sans GB"], # macOS：黑体-简优先
        "windows": ["SimHei", "黑体", "Microsoft YaHei"],         # Windows：中易黑体
        "linux": ["Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Zen Hei"],   # Linux：开源黑体
    },
    "SimHei": {                                                   # 黑体英文名
        "macos": ["Heiti SC", "PingFang SC"],                    # 同「黑体」
        "windows": ["SimHei"],                                   # 同「黑体」
        "linux": ["Noto Sans CJK SC", "Source Han Sans SC"],      # 同「黑体」
    },
    "楷体": {                                                     # 标准里的楷体
        "macos": ["Kaiti SC", "STKaiti"],                        # macOS：楷体-简 / 华文楷体
        "windows": ["KaiTi", "楷体", "KaiTi_GB2312"],             # Windows：随系统自带楷体
        "linux": ["AR PL UKai CN", "Noto Serif CJK SC"],          # Linux：开源楷体较少
    },
    "KaiTi": {                                                    # 楷体英文名
        "macos": ["Kaiti SC", "STKaiti"],                        # 同「楷体」
        "windows": ["KaiTi"],                                    # 同「楷体」
        "linux": ["AR PL UKai CN"],                              # 同「楷体」
    },
    "楷体_GB2312": {                                              # 公文层次序数第二层常用字体
        "macos": ["Kaiti SC", "STKaiti"],                        # macOS：楷体-简
        "windows": ["KaiTi_GB2312", "KaiTi", "楷体"],             # Windows：GB2312 楷体
        "linux": ["AR PL UKai CN", "LXGW WenKai"],               # Linux：开源楷体
    },
    "微软雅黑": {                                                 # Windows 界面字体
        "macos": ["PingFang SC", "Hiragino Sans GB"],            # macOS：苹方同为无衬线
        "windows": ["Microsoft YaHei"],                          # Windows：本身自带
        "linux": ["Noto Sans CJK SC", "Source Han Sans SC"],      # Linux：开源无衬线
    },
    "Microsoft YaHei": {                                          # 微软雅黑英文名
        "macos": ["PingFang SC", "Hiragino Sans GB"],            # 同「微软雅黑」
        "windows": ["Microsoft YaHei"],                          # 同「微软雅黑」
        "linux": ["Noto Sans CJK SC"],                           # 同「微软雅黑」
    },
    "等线": {                                                     # Windows 10 之后的默认正文字体
        "macos": ["PingFang SC"],                                # macOS：苹方
        "windows": ["DengXian", "等线"],                          # Windows：本身自带
        "linux": ["Noto Sans CJK SC"],                           # Linux：开源无衬线
    },
}

# 开源字体建议表：标准要求的字体 -> 免费商用的同类开源字体（按接近程度排序）。同样只作建议。
OPEN_SOURCE_CANDIDATES = {
    "仿宋_GB2312": ["Zhuque Fangsong", "朱雀仿宋", "Source Han Serif SC", "Noto Serif SC"],   # 朱雀仿宋是少见的开源仿宋
    "方正小标宋简体": ["Source Han Serif SC", "Noto Serif SC"],      # 开源宋体加粗近似小标宋
    "宋体": ["Source Han Serif SC", "Noto Serif SC"],               # 开源宋体
    "SimSun": ["Source Han Serif SC", "Noto Serif SC"],             # 开源宋体英文名
    "黑体": ["Source Han Sans SC", "Noto Sans SC"],                 # 开源黑体
    "SimHei": ["Source Han Sans SC", "Noto Sans SC"],               # 开源黑体英文名
    "楷体": ["LXGW WenKai", "霞鹜文楷", "Source Han Serif SC"],       # 霞鹜文楷是开源楷体风格
    "KaiTi": ["LXGW WenKai", "霞鹜文楷"],                            # 同上英文名
    "楷体_GB2312": ["LXGW WenKai", "霞鹜文楷"],                      # 同上
    "微软雅黑": ["Source Han Sans SC", "Noto Sans SC"],              # 开源无衬线
    "Microsoft YaHei": ["Source Han Sans SC", "Noto Sans SC"],       # 开源无衬线英文名
    "等线": ["Source Han Sans SC", "Noto Sans SC"],                  # 开源无衬线
}

# 在各候选里挑第一个本机真实可用的字体名；一个都不可用时返回首选候选
# 从候选表里挑出「本机真的装了」的字体名，只用作给用户的建议清单。
# 关键：本函数只产出建议，绝不在生成流程里替用户做决定 —— 这是本项目的字体铁律。
# 起因是一次实测：LibreOffice 静默把中文替换成 LinuxLibertine / DejaVuSans / FrankRuhlHofshi，
# 文件能打开、文本能提取，但字全错了，而且没有任何提示。
def suggest_replacements(required, available=None, include_all=False):
    # 未传入字体集合时实时枚举（进程内已有缓存，不会重复扫描）
    if available is None:
        available = list_cjk_fonts()
    required = (required or "").strip()                          # 规范化输入
    ordered = []                                                 # 按推荐优先级收集候选
    table = FALLBACK_CANDIDATES.get(required)                    # 查兼容候选表
    if table:                                                    # 表里有这个字体
        platform = detect_platform()                             # 判断当前平台
        ordered += table.get(platform, [])                       # 本平台候选优先
        for other in ("macos", "windows", "linux"):              # 其余平台候选作为补充
            if other != platform:                                # 跳过本平台避免重复
                ordered += table.get(other, [])                  # 追加候选
    ordered += OPEN_SOURCE_CANDIDATES.get(required, [])          # 再补上开源候选
    if include_all:                                              # 用户可以直接从本机全部字体里挑
        ordered += sorted(available)                             # 把本机所有中文字体都列上
    result = []                                                  # 最终去重后的可用清单
    for name in ordered:                                         # 逐个候选检查
        if name not in result and font_is_available(name, available):   # 本机确实装了且尚未收录
            result.append(name)                                  # 收进清单
    return result                                                # 返回建议清单

# 解析一个字体槽位最终该写进文件里的字体名。
#
# 铁律：**只认规格卡里显式写下的字体，绝不自动挑替身。**
# 用户写 resolved 就用 resolved；没写就用标准要求的字体名。是否装得上由校验环节负责，
# 装不上就中止生成，而不是悄悄换一个。
def resolve_font(required, resolved=None):
    required = (required or "").strip()                          # 规范化标准要求的字体名
    if not required or not is_cjk(required):                     # 空值或纯西文字体
        return required                                          # 原样返回，不做任何映射
    resolved = (resolved or "").strip()                          # 规范化用户指定的替代字体
    return resolved or required                                  # 用户指定优先，否则用原字体

# 从一个字体槽位配置里取出「标准要求」与「用户指定」两个字体名。
# 返回 None 表示这个槽位没有配中文字体，调用方直接跳过。
def font_slot(cfg):
    if not isinstance(cfg, dict):                                # 配置不是字典（可能是空值）
        return None                                              # 视为未配置
    required = (cfg.get("east_asian") or "").strip()             # 标准要求的中文字体
    if not required:                                             # 没写中文字体
        return None                                              # 视为未配置
    return required, (cfg.get("resolved") or "").strip()         # 返回「要求, 用户指定」

# ─────────────────────────────────────────────────────────────
# 字体名比对：判断「产物里实际用的字体」是不是「规格要求的那个」
#
# 为什么需要：DOCX 生成时我们已经不许替换了，但 PDF 那一跳是 LibreOffice 做的，
# 它会在自己找不到字体时静默换一个（实测换成了 LinuxLibertine / DejaVuSans /
# FrankRuhlHofshi），而旧的校验只要求「内嵌了某个中文字体」，压根查不出来。
# 比对难点：PDF 里存的是 PostScript 名，还带子集前缀，例如：
#   规格「Songti SC」  →  PDF「HQMZNO+STSongti-SC-Regular」
#   规格「Heiti SC」   →  PDF「KALLSJ+STHeitiSC-Medium」
# 所以要先归一化再比对。
# ─────────────────────────────────────────────────────────────
# 归一化时要剥掉的样式词与字重标记
FONT_STYLE_WORDS = (
    "regular", "italic", "bold", "medium", "light", "black", "semibold",   # 常见字重与姿态
    "psmt", "ps", "mt", "w3", "w6", "w8", "sc", "tc", "gb",                 # PostScript 后缀与地区缩写
)

# 把字体名归一化成便于比较的形式
def normalize_font_name(name):
    text = str(name or "").strip()                                    # 取字符串形态
    text = re.sub(r"^[A-Z]{6}\+", "", text)                           # 剥掉 PDF 的子集前缀，形如 HQMZNO+
    # 先把连字符与下划线换成空格，方便按词切分（STSongti-SC-Regular → STSongti SC Regular）
    text = re.sub(r"[-_]+", " ", text).lower()                        # 统一小写
    words = [w for w in re.split(r"\s+", text) if w]                   # 按空白切词
    kept = []                                                         # 保留词
    for word in words:                                                # 逐个判断
        stripped = re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", word)        # 去掉标点
        if not stripped:                                              # 空的跳过
            continue                                                  # 继续
        if stripped in FONT_STYLE_WORDS:                              # 是样式词
            # 只有前面已经留过词时才当后缀剥掉，否则「SC」这种词本身就是名字的一部分
            if kept:                                                  # 前面有词
                continue                                              # 当后缀剥掉
        kept.append(stripped)                                         # 保留
    return "".join(kept)                                              # 拼成归一化结果

# 判断产物里的字体名是否就是规格要求的那个（宽松匹配，宁可放过不可误杀）
def font_name_matches(actual_name, required_name):
    actual = normalize_font_name(actual_name)                         # 归一化实际字体名
    required = normalize_font_name(required_name)                     # 归一化要求字体名
    if not actual or not required:                                    # 有一个为空
        return False                                                  # 无法比较，判为不匹配
    if required in actual or actual in required:                      # 双向包含即可
        return True                                                   # 命中
    # 再退一步：按词比对。规格「Times New Roman」应能命中「TimesNewRomanPSMT」
    tokens = [t for t in re.split(r"\s+", re.sub(r"[-_]+", " ", str(required_name).lower())) if len(t) >= 4]
    return any(re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", t) in actual for t in tokens)   # 任一词命中即可

# LibreOffice 在渲染 PDF 时会自己带进来的一批字体，不是「被替换掉的字体」。
#
# 为什么需要这份白名单：LibreOffice 导出 PDF 时，资源表里会出现一些我们没声明的字体，
# 分三种情况，必须区别对待 ——
#   1. 真的在排正文：说明规格声明的字体没找到，被静默换掉了，必须报出来（例：PingFangHK 排表题）；
#   2. 只排符号：列表的「•」由 OpenSymbol 提供，Wingdings 等图符字体同理，属正常；
#   3. 压根没用到：LinuxLibertine 实测一个字都没排，只是被写进了资源表，属噪声。
# 2、3 两种不该报警，否则每次报告都有一堆假的「需确认」，真问题反而被淹没。
# 判定方式统一用「归一化后的包含匹配」，避免带子集前缀与样式后缀时漏配。
BUILTIN_RENDER_FONTS = (
    "opensymbol",                          # 列表项目符号（•、▪、‣）专用，LibreOffice 自带
    "symbol",                              # 希腊字母与数学符号
    "wingdings", "wingdings2", "wingdings3",   # Word 图符字体
    "webdings",                            # IE 时代的图符字体，Word 里仍可见
    "zapfdingbats",                        # PostScript 图符字体
    "linuxlibertine",                      # 实测：只出现在资源表，实际零字形使用
)

# 判断某个渲染期出现的字体名是否属于「LibreOffice 自带、不算换字」的那一类
def is_builtin_render_font(font_name):
    normalized = normalize_font_name(font_name)                        # 归一化字体名（剥子集前缀与样式后缀）
    if not normalized:                                                 # 名字为空
        return False                                                   # 无法判定，按「需确认」处理
    return any(name in normalized for name in BUILTIN_RENDER_FONTS)    # 命中白名单任意一项即可

# 在本机字体目录里按族名找一个字体文件，返回路径；找不到返回空串。
# 用途：把字体装进 LibreOffice 的字体目录，让 DOCX→PDF 那一跳不会因为缺字体而换掉字。
# 匹配方式：把族名切成词，要求文件名里含有全部有效词（长度 ≥3 且不是样式词）。
# 「Songti SC」这种带地区后缀的名字，切出来的 SC 只有两字母会被过滤掉，正好只按 Songti 匹配。
def find_font_file(family, search_dirs=None):
    words = []                                                    # 有效词列表
    for word in re.split(r"[\s\-_]+", str(family or "").lower()):  # 按空白与连字符切词
        word = re.sub(r"[^0-9a-z]", "", word)                      # 只保留字母数字
        if len(word) >= 3 and word not in FONT_STYLE_WORDS:        # 长度够且不是样式词
            words.append(word)                                     # 收进有效词
    if not words:                                                  # 没有有效词
        return ""                                                  # 无法匹配
    matches = []                                                   # 收集所有命中的文件
    for root in (search_dirs if search_dirs is not None else font_search_dirs()):   # 遍历字体目录
        for path in glob.glob(os.path.join(root, "**", "*"), recursive=True):       # 递归展开
            lowered = path.lower()                                 # 转小写便于比较
            if not lowered.endswith((".ttf", ".otf", ".ttc", ".otc")):              # 不是字体文件
                continue                                           # 跳过
            name = os.path.basename(lowered)                       # 取文件名
            if all(word in name for word in words):                # 全部有效词都出现
                matches.append(path)                               # 记下该候选
    if not matches:                                                # 一个都没命中
        return ""                                                  # 返回空串
    # 排序偏好：文件名带 regular 的最优先（正体），其次不含任何样式词的文件，最后才是 Bold/Italic 之类；
    # 同一档里取文件名最短的，避免挑到「Times New Roman Bold Italic.ttf」这种变体
    def rank(path):
        name = os.path.basename(path).lower()                      # 取文件名
        has_style = any(word in name for word in FONT_STYLE_WORDS)  # 是否带样式词
        return (0 if "regular" in name else (1 if not has_style else 2), len(name))   # 返回排序键
    return sorted(matches, key=rank)[0]                            # 返回最优候选

# 收集规格卡里所有要落到固定版式产物上的字体槽位（中文 + 西文）。
# 返回 [(用途, 标准要求字体, 实际使用字体, 是否中文)] 四元组。
# spec_check（体检）与各生成脚本（拦截）共用这一份，避免两处判定漂移。
def collect_required_fonts(spec):
    rows = []                                                    # 收集结果
    fonts = spec.get("fonts") or {}                              # 字体段
    # 内部小工具：把一个槽位的中文字体收进结果
    def add(use, cfg):
        slot = font_slot(cfg)                                    # 取槽位的两个字体名
        if slot is None:                                         # 未配置中文字体
            return                                               # 跳过
        required, resolved = slot                                # 拆开
        rows.append((use, required, resolve_font(required, resolved), True))   # 中文字体标记为 True
    # 内部小工具：把一个槽位的西文字体收进结果
    def add_latin(use, cfg):
        if not isinstance(cfg, dict):                            # 配置不是字典
            return                                               # 跳过
        latin = (cfg.get("latin") or "").strip()                 # 取西文字体
        if not latin:                                            # 没配西文字体
            return                                               # 跳过
        rows.append((use, latin, latin, False))                  # 西文字体标记为 False
    add("正文中文字体", fonts.get("body"))                        # 正文
    add_latin("正文西文字体", fonts.get("body"))                   # 正文西文
    add("图表注", fonts.get("caption"))                           # 图表注释
    add("代码块中文字体", fonts.get("code"))                       # 代码块中文
    add_latin("代码块西文字体", fonts.get("code"))                  # 代码块西文
    for level, cfg in (spec.get("headings") or {}).items():      # 各级标题
        add(f"标题 {level}", cfg)                                 # 逐个收集中文
        add_latin(f"标题 {level} 西文", cfg)                        # 逐个收集西文
    add("红头", spec.get("masthead"))                             # 公文版头
    # 签发人的两个字体槽位（GB/T 9704-2012 §7.2.6：「签发人」三字用 3 号仿宋、姓名用 3 号楷体）
    # 也要登记：以前它们不在清单里，规格声明了本机没有的仿宋也不拦，生成时才被 LibreOffice 静默换字。
    signer_cfg = (spec.get("masthead") or {}).get("signer")       # 取签发人配置
    add("签发人标签字体", signer_cfg if isinstance(signer_cfg, dict) else {})   # 「签发人」三字（3 号仿宋）
    signer_name_cfg = signer_cfg.get("name_font") if isinstance(signer_cfg, dict) else {}   # 姓名槽位
    add("签发人姓名字体", signer_name_cfg if isinstance(signer_name_cfg, dict) else {})   # 姓名（3 号楷体）
    add("页码", (spec.get("footer") or {}).get("page_number"))     # 页码
    # 页眉也要登记：setup_header 会读 header.east_asian 去排版，
    # 但以前没登记进这份清单，于是「规格声明了页眉字体、本机却没有」时门禁不拦，
    # 生成到最后才由 LibreOffice 静默换字 —— 门禁与生成读的字段必须一致。
    add("页眉", spec.get("header"))                               # 页眉
    return rows                                                  # 返回全部槽位

# 找出本机没有的字体槽位。
# 中文字体缺失会直接掉字或渲染成方框，是最致命的；西文字体缺失同样算缺失，
# 因为本项目的规则是「不自动替换」——要么装，要么用户从本机已有的字体里指定一个。
# 返回 (缺失列表, 西文是否可验证)：西文不可验证时（机器上枚举不到字体清单）降级为不阻断。
def missing_fonts(spec, available=None):
    if available is None:                                        # 未传入中文字体集合
        available = list_cjk_fonts()                             # 实时枚举中文字体
    all_fonts = list_all_fonts()                                 # 枚举全部字体（可能为空）
    missing = []                                                 # 收集缺失槽位
    for use, required, actual, is_cjk_font in collect_required_fonts(spec):   # 遍历所有槽位
        if is_cjk_font:                                          # 中文字体
            if not font_is_available(actual, available):         # 实际字体本机没有
                missing.append((use, required, actual))          # 记入缺失列表
        else:                                                    # 西文字体
            if not all_fonts:                                    # 这台机器枚举不到字体清单
                continue                                         # 无法验证，不误报
            if not font_is_available(actual, all_fonts):         # 实际字体本机没有
                missing.append((use, required, actual))          # 记入缺失列表
    return missing                                               # 返回缺失列表

# 生成「缺字体」的完整人类可读说明：列出缺什么、两条路怎么走、本机有什么可挑。
# 各生成脚本在动手前调用它；返回非空字符串就代表必须中止，不要生成半成品。
def font_block_message(spec, available=None):
    missing = missing_fonts(spec, available)                     # 找出缺失槽位
    if not missing:                                              # 一个都不缺
        return ""                                                # 返回空串，放行
    lines = ["以下字体在这台电脑上没有，按本项目规则不会自动替换，因此停止生成。", ""]   # 开头说明
    for use, required, actual in missing:                        # 逐条列出缺失项
        if actual != required:                                   # 用户已经指定了替代
            lines.append(f"· {use}：你指定的「{actual}」本机没有（规格原字体是「{required}」）")   # 说明替代也不在
        else:                                                    # 尚未指定替代
            lines.append(f"· {use}：规格要求的「{required}」本机没有")   # 说明缺什么
    lines.append("")                                             # 空行分隔
    lines.append("两条路，选一条：")                                # 给出选择
    lines.append("  A. 安装字体：装完重新跑一次，字体检测会立刻认出来。")   # 路径 A
    lines.append("  B. 换成本机已有的：从下面的清单里指定一个，写进规格卡对应槽位的 resolved 字段。")   # 路径 B
    lines.append("     公众号 HTML 例外：该载体只能用系统字体栈，属于载体限制，不算替身。")   # 例外说明
    for use, required, actual in missing:                        # 逐个缺失字体给出获取信息
        if actual != required:                                   # 用户指定的替代都缺，不必再查获取渠道
            continue                                             # 跳过
        lines.append("")                                         # 空行分隔
        lines.append(f"关于「{required}」：")                       # 标题
        lines.append(font_acquisition_advice(required))          # 复用获取决策树
        suggestions = suggest_replacements(required, available)   # 计算本机可用的同类字体
        if suggestions:                                          # 有可选项才打印
            lines.append("  ⑦ 本机已有的同类字体（任选其一，写进 resolved）：")   # 提示
            lines.append("     " + "、".join(suggestions[:12]))    # 最多列 12 个，避免刷屏
    return "\n".join(lines)                                      # 拼成完整说明

# 判断表格单元格内容是否为数字，供 resolve_column_alignments 判定「数字列」用。
# 只认纯数字、千分位、小数点、正负号与百分号；日期（2026-09-17）、带单位的数值（15px）都算文字，
# 只有在规格卡显式声明了 number_column_alignment 时，这个判定才会真正影响输出；
# 规格卡不声明就一律不干预表格对齐。
def is_numeric_cell(text):
    stripped = (text or "").strip()                               # 去掉首尾空白
    if not stripped:                                              # 空单元格
        return False                                              # 空单元格按文字处理
    return bool(re.match(r"^[-+]?[0-9][0-9,.]*%?$", stripped))     # 只匹配纯数字形态

# 判断预设的标题层级是否需要整体后移一位。
# 背景：公文与学术论文的预设里，「文档标题」（doc_title / title）与「层次 1」（level1）
# 是两个不同的东西 —— 公文里标题是二号小标宋居中，而「一、」是黑体正文段。
# 但 Markdown 只有一个第 1 级。所以约定：有文档标题时，Markdown 的 # 给文档标题，
# 层次序数整体后移一位（「一、」写成 ##）。
# 返回值：1 表示需要后移一位，0 表示不需要。
# 读的一方（resolve_heading）与写的一方（infer_structure）必须共用本函数，
# 否则推断出来的层级会被解析成另一级的样式。
def heading_shift(headings):
    headings = headings or {}                                     # 容错：没有标题段时按空字典处理
    covered = any(headings.get(key) for key in ("doc_title", "title", "chapter"))   # 是否已有封面级标题
    return 1 if (covered and headings.get("level1")) else 0        # 只有同时存在 level1 才是相对编号

# 算出「章」标题落在第几级，供页眉的 STYLEREF 域使用。
#
# 为什么需要：页眉排「当前章名」靠 Word 的 STYLEREF 域，它必须指向一个具体的标题级别。
# 早期默认写死 Heading 1，但书的标题体系不止一种：
#   · 常规做法：H1 就是章 → Heading 1
#   · 有独立书名页的做法：H1 是书名、H2 才是章 → Heading 2（实测踩过：页眉一直显示书名）
# 判定顺序：规格卡显式声明 > 按 headings 键名推断 > 退回第 1 级。
def chapter_heading_level(spec):
    header = spec.get("header") or {}                              # 取页眉配置
    explicit = header.get("chapter_level")                         # 显式声明的级别优先
    if explicit is not None:                                       # 声明了就照它来
        try:                                                       # 值可能是字符串
            return max(1, min(6, int(explicit)))                   # 收敛到 1-6 级
        except (TypeError, ValueError):                            # 值不合法
            pass                                                   # 忽略，继续走推断
    headings = spec.get("headings") or {}                          # 取标题配置
    if headings.get("chapter"):                                    # 用 chapter 键 → 它对应第 1 级
        return 1                                                   # 章在第 1 级
    # 书名占了第 1 级（doc_title/title），且第 2 级另有配置 → 章就在第 2 级
    if any(headings.get(key) for key in ("doc_title", "title", "thesis_title")) and \
       any(headings.get(key) for key in ("level2", "h2", "section")):   # 两个条件都成立
        return 2                                                   # 章在第 2 级
    return 1                                                       # 其余情况按第 1 级

# 计算一段文字的显示宽度，单位是「半个汉字宽」：中文按 2 计、西文按 1 计。
# 表格列宽估算与「表头装不装得下」的校验都用它，必须只有一份，否则两边结论会不一致。
def display_width(text):
    return sum(2 if ord(char) > 0x2E80 else 1 for char in (text or ""))   # 中日韩字符按 2 计，其余按 1 计

# 一个「半个汉字宽」在给定字号下有多宽（厘米）。
# 0.01764 的来源：1 磅 = 0.03528 厘米，半个汉字宽 = 0.5 个汉字 = 0.5 磅，故 0.5 × 0.03528 = 0.01764。
# 表格列宽、标题折行、版心容量三处换算共用它，免得各写一套系数、结论互相打架。
def unit_to_cm(size_pt):
    return float(size_pt) * 0.01764                                # 半汉字宽 → 厘米

# 一段文字在给定列宽下会折成几行。列宽的单位是「半个汉字宽」。
# 中文字符可以任意处断行，所以直接按宽度整除向上取整即可；含西文单词时会略微低估，
# 但只用于「会不会折行」的判断与预警，不用于精确排版，这个精度足够。
def wrapped_lines(text, width_units):
    total = display_width(text)                                    # 这段文字总共占多少半汉字宽
    if total <= 0:                                                 # 空文字
        return 1                                                   # 算一行
    width_units = float(width_units or 0)                          # 列宽可能是 0 或 None
    if width_units <= 0:                                           # 宽度非法
        return 1                                                   # 不做除零，算一行
    # 取整时要留 0.5% 的容差：列宽在「算法里的浮点值」与「文件里的 twips 整数」之间有舍入差，
    # 这点差会把「刚好放得下」误判成「多折一行」。实测：城市列刚好 4.0 格排「上海」，
    # 写进 DOCX 变成 3.995 格，校验端就报「上海折成 2 行」—— 用户会拿这条警告来质疑产物。
    return max(1, -(-total // max(1, int(width_units * 1.005))))     # 向上取整的整除写法，避免引入 math

# ─────────────────────────────────────────────────────────────
# 对齐取值：解析与校验
#
# 为什么需要单独一层：规格卡里能写四种对齐（left / center / right / outside），
# 但脚本真正能落地只有前三种，outside 要先按「这一页是单页还是双页」算成具体一侧。
# 早先的写法是 ALIGN_MAP.get(值, CENTER) —— 取值不认识就静默退回居中，
# 实测踩过两次：① 报告预设写的 position: right_bottom 从来没生效过，页码一直是居中的；
#              ② spec-schema 声明支持 outside，但 ALIGN_MAP 里没有，写 outside 也退回居中。
# 现在改成：outside 算成具体一侧；无法识别的取值退回默认值，并把原值报给调用方去提醒。
# ─────────────────────────────────────────────────────────────
ALIGNMENT_VALUES = ("left", "center", "right", "outside")          # 规格卡允许写的四种取值

def resolve_alignment(value, side=None, binding="left", default="center"):
    """把规格里的对齐取值解析成脚本能落地的 left / center / right。

    side：这一页是单页还是双页，取 "odd" / "even" / None。
          只有 outside（靠版心外侧）需要它 —— 单页的外侧在右、双页的外侧在左。
    binding：装订边，left（左侧装订，默认）或 right。右侧装订时内外侧左右互换。
    返回 (对齐值, 说明文本)：说明为空串表示一切正常；非空表示「规格写法有问题」，
    调用方应当把它打印给用户，不要静默吞掉。
    """
    text = str(value or "").strip().lower()                        # 规范化取值
    mirrored = str(binding or "left").strip().lower() == "right"   # 右侧装订：内外侧左右互换
    if not text:                                                   # 规格没写
        return default, ""                                         # 用调用方给的默认值
    if text in ("left", "center", "right"):                        # 三种直白取值
        return text, ""                                            # 原样返回
    if text == "outside":                                          # 靠版心外侧
        if side == "odd":                                          # 单页（右页，recto）
            return ("left" if mirrored else "right"), ""           # 外侧在右（右侧装订则在左）
        if side == "even":                                         # 双页（左页，verso）
            return ("right" if mirrored else "left"), ""           # 外侧在左（右侧装订则在右）
        # 没说单双页就判断不出外侧在哪边。退回「靠切口」这一侧，并如实说明。
        return ("left" if mirrored else "right"), (
            "规格把对齐写成 outside（靠版心外侧），但没有区分单页与双页，判断不出外侧在哪一边，"
            "已按" + ("左侧" if mirrored else "右侧") + "处理。"
            "要精确控制外侧，请同时写 odd_page / even_page（或 header 的单双页内容与对齐）。")
    # 走到这里说明取值不在合法集合里。绝不静默兜底 —— 实测「预设写了 right_bottom、
    # 页码被悄悄居中」就是这么来的。
    return default, (
        f"规格里的对齐取值「{value}」不是合法值（只支持 {'/'.join(ALIGNMENT_VALUES)}），"
        f"已退回 {default}。注意 right_bottom、bottom、top 这类写法都不合法，"
        f"「靠右下」请写 right、「靠版心外侧」请写 outside。")

# ─────────────────────────────────────────────────────────────
# 表格线型的合法取值
#
# 为什么把这份取值放进公共库：生成端（build_docx / convert_docx / build_html）与体检端
# （spec_check）必须认识同一批取值。实测踩过的坑是「登记了三个取值，其中一个根本没实现」——
# 规格里写 header_shading（表头加底纹），生成端只判了 grid、其余一律按三线表处理，
# 结果既没有底纹，连三线表那条表头线也一起丢了，比正常三线表还难看；
# 而体检端压根不校验这个字段，报告还是全绿。现在只有一处定义，谁要判断都必须来这里取。
#
# 为什么把 header_shading 从取值里删掉、而不是补上实现：底纹属于装饰，
# 本 skill 只做「合规 + 载体适配 + 校验」，不做美化（见 SKILL.md 硬规则 12）。
# 留着一个半成品的装饰选项，只会让用户选到一个比默认还差的结果。
# ─────────────────────────────────────────────────────────────
TABLE_STYLE_VALUES = ("three_line", "grid")                    # 规格卡允许写的两种表格线型

# 把规格里写的表格线型解析成合法取值；写法有问题时额外回一条说明，由调用方打印给用户
def resolve_table_style(value):
    """返回 (线型名, 说明)。

    说明为空串表示规格没问题。说明非空时，调用方必须把它打印给用户 ——
    静默忽略正是这个项目反复栽的坑：用户以为改了规格，拿到文件才发现没生效。
    """
    text = str(value or "").strip().lower()                    # 规范化取值：去掉空格并统一小写
    if not text:                                               # 规格没写这一项
        return "three_line", ""                                # 用默认的三线表，不需要说明
    if text in TABLE_STYLE_VALUES:                             # 写法合法
        return text, ""                                        # 原样返回
    return "three_line", (                                     # 写法不合法：退回默认值，并如实告知
        f"规格里的表格线型「{value}」不是合法值（只支持 {'/'.join(TABLE_STYLE_VALUES)}），"
        f"已按三线表处理。表头加底纹属于美化，本 skill 不做；要全框线请写 grid。")


# ─────────────────────────────────────────────────────────────
# 图表题注的识别
#
# 题注在源稿里就是一个普通段落（「表 1　八市轨道交通主要运营指标」），
# 没有任何 Markdown 语法标记。要用它，只能靠「以 表/图 + 编号 开头」这个特征来判断 ——
# 生成脚本（把题注挪到表上/表下）与校验脚本（核对题在表上还是表下）必须用同一份规则，
# 否则会出现「生成按一套挪、校验按另一套量」的扯皮。
# ─────────────────────────────────────────────────────────────
TABLE_CAPTION_RE = re.compile(
    r"^\s*(?:表|图|Table|Figure|Fig)\s*[0-9一二三四五六七八九十]+"
    r"(?:\s*[-–—.·]\s*[0-9]+)?[\s　:：、.．]")

# 判断一段文字是不是图表题注。太长的段落一律不算 ——
# 正文里恰好写到「表 2 显示了…」的句子不能被当成题注。
def is_caption_text(text, max_length=120):
    text = str(text or "").strip()                                 # 去掉首尾空白
    if not text or len(text) > max_length:                         # 空段或长段
        return False                                               # 不算题注
    return bool(TABLE_CAPTION_RE.match(text))                      # 用上面的模式判定

# 一个标题在给定版心里会不会折行、末行会不会只剩孤零零一两个字。
#
# 为什么要专门判「末行剩几个字」：标题折行本身很正常（长章名两行也好看），
# 真正难看的是折完之后末行只有一两个字 —— 实测踩过：报告标题二号字在 A4 版心里
# 折成「2026 年度华东地区城市轨道交通客运量分析报／告」，末行一个「告」字，
# 而预设里写的是三号，根本不折行。这类问题只在渲染图上看得出来，脚本必须自己算。
def heading_wrap_info(text, size_pt, available_cm):
    text = str(text or "")                                         # 容错：传进来 None 也当空串处理
    if not text.strip() or not size_pt or not available_cm:        # 空标题或参数不全
        return None                                                # 无从判断
    per_line = max(1, int(available_cm / unit_to_cm(size_pt)))     # 一行能放多少个半汉字
    if "\n" in text:                                               # 标题里带换行 ＝ 生成端已按 §7.3.1 人工断过行
        lines = [line.strip() for line in text.split("\n") if line.strip()]   # 逐行取出（忽略空行）
        if not lines:                                              # 断出来是空的（理论上不会发生）
            return None                                            # 无从判断
        widths = [display_width(line) for line in lines]            # 每一行的宽度
        info = {                                                   # 按人工断行的实际结果组装判断结果
            "文字": "／".join(lines),                                # 几行用「／」连起来，方便在报告里显示
            "字号": float(size_pt),                                 # 使用的字号
            "行数": len(lines),                                     # 人工断成了几行
            "末行宽度": widths[-1],                                  # 末行占多少个半汉字宽
            "每行宽度": per_line,                                    # 一行容量（半汉字宽）
            "版心_cm": round(available_cm, 2),                       # 版心宽度
            "一行最大字号": round(available_cm / max(1, sum(widths)) / 0.01764, 1),   # 想排成一行，字号上限
        }                                                          # 组装完毕
        # 人工断行是生成端自己挑的断点：每行放得下、末行也不短，就说明断得合格，不再报「折行难看」——
        # 否则会出现「生成端刚按国标断好行、校验端立刻报警」的自相矛盾报告。
        if max(widths) <= per_line and not heading_wrap_is_bad(info):   # 断得合格
            return None                                            # 不报
        return info                                                # 断完仍难看（比如末行只剩一个字）就照实报出去
    total = display_width(text)                                    # 没有人工断行：按自动折行估算
    if total <= per_line:                                          # 一行放得下
        return None                                                # 不折行，没什么可报的
    lines = -(-total // per_line)                                  # 折成几行
    remainder = total - (lines - 1) * per_line                     # 末行还剩多少宽度
    return {                                                       # 组装判断结果
        "文字": text,                                              # 标题原文
        "字号": float(size_pt),                                    # 使用的字号
        "行数": lines,                                             # 折成几行
        "末行宽度": remainder,                                      # 末行占多少个半汉字宽
        "每行宽度": per_line,                                        # 一行容量（半汉字宽），判断「末行偏短」时要用
        "版心_cm": round(available_cm, 2),                          # 版心宽度
        "一行最大字号": round(available_cm / total / 0.01764, 1),    # 想排成一行，字号上限
    }

# 判断一段文字是不是「散文」（正文句子）而不是标题。
#
# 为什么折行核对与人工断行都要先过这一关：公文预设把「（一）强化组织领导。各县（市、区）要……」
# 这类层次序数段落登记成了级别标题（按 GB/T 9704 §7.3.3，它们本来就是正文自然段、只是带序数），
# 于是一整段话会被当成「标题」去算折行 —— 必然报「末行太短、像倒梯形」，可那是正文的正常折行，
# 不是标题排得难看。判据用句末标点：标题里不会出现「。！？」（出现了就说明它是句子）。
def looks_like_prose(text):
    return bool(re.search(r"[。！？]", str(text or "")))            # 含句末标点＝散文

# 判断一次自动折行是不是「难看」——生成端（build_docx）与校验端（verify_output）共用这一条规则。
# 两种要报的情形：
#   ① 末行不足两个字（4 个半汉字宽）—— 俗称「孤字」，最刺眼；
#   ② 末行不足整行宽度的四分之一 —— 头重脚轻的倒梯形。
# 为什么不能只看「不足两个字」：实测公文标题自动折成 20 字／4 字，末行有 4 个字，
# 旧规则（只看 < 4 半汉字宽）不报，用户拿到手才发现难看。
def heading_wrap_is_bad(info):
    if not info:                                                   # 没有折行信息
        return False                                               # 不算难看
    per_line = float(info.get("每行宽度") or 0)                     # 一行容量（半汉字宽）
    if info["末行宽度"] < 4:                                        # 不到两个字
        return True                                                # 是孤字，要报
    return bool(per_line) and info["末行宽度"] < per_line / 4       # 否则看是否不足整行的四分之一

# 给标题找一个人工断行点（GB/T 9704-2012 §7.3.1）：
#   「分一行或多行居中排布；回行时，要做到词意完整，排列对称，长短适宜，间距恰当，
#     标题排列应当使用梯形或菱形。」
#
# 为什么需要它：Word（以及 LibreOffice）的自动折行只管「排满一行就断」，
# 实测公文标题被断成「……隐患排查整治工／作的通知」—— 把「工作」这个词切开了，
# 末行还只剩 4 个字（倒梯形）。编辑遇到这种情况是手工断行的，这里替用户做掉。
#
# 打分规则（单位：半汉字宽，越小越好）：
#   · 断点落在空格处最好（中文与数字之间的空格本来就是天然的断行点）；
#   · 其次落在标点之后（，、。：；！？））」』）；
#   · 两行宽度越接近越好（排列对称、长短适宜）；
#   · 断点两侧都不得超过每行容量。
# 返回 (第一行, 第二行)；以下三种情况返回 None（表示不人工干预，交给自动折行）：
#   · 一行本来就放得下；· 需要折三行以上（断行点组合太多，先不猜）；· 找不到合法断点。
def balanced_heading_break(text, size_pt, available_cm):
    text = (text or "").strip()                                  # 去掉首尾空白
    if not text or not size_pt or not available_cm:              # 参数不全
        return None                                              # 不做判断
    total = display_width(text)                                  # 标题总宽（半汉字宽）
    per_line = available_cm / unit_to_cm(size_pt)                # 一行能放多少个半汉字宽
    if total <= per_line:                                        # 一行放得下
        return None                                              # 不需要断行
    if total > per_line * 2:                                     # 折成三行以上
        return None                                              # 交给自动折行，由预警提示用户
    best = None                                                  # 最优断行方案
    best_score = None                                            # 最优得分
    for index in range(1, len(text)):                            # 逐个字符位置试断
        left = text[:index].rstrip()                             # 断点左侧（去掉行尾空格）
        right = text[index:].lstrip()                            # 断点右侧（去掉行首空格）
        if not left or not right:                                # 有一侧是空的
            continue                                             # 不是有效断点
        left_width = display_width(left)                         # 左行宽度
        right_width = display_width(right)                       # 右行宽度
        if left_width > per_line or right_width > per_line:      # 有一行装不下
            continue                                             # 跳过这个断点
        if text[index - 1] == " ":                               # 断在空格处
            penalty = 0.0                                        # 最自然，不罚分
        elif text[index - 1] in "，、。：；！？）)」』":             # 断在标点之后
            penalty = 6.0                                        # 次之，罚 6 个半汉字宽
        else:                                                    # 断在词中间（如「工／作」）
            penalty = 12.0                                       # 最差，罚 12 个半汉字宽
        score = abs(left_width - right_width) + penalty           # 得分：越均衡、断点越自然越好
        if best_score is None or score < best_score:              # 找到更优的
            best_score = score                                   # 记下得分
            best = (left, right)                                 # 记下方案
    return best                                                  # 返回最优方案（可能是 None）

# 标题里的人工断行标记：稿子（或规格）里写「｜」（也接受半角「|」）表示这里强制断行。
#
# 为什么要有这个出口：GB/T 9704-2012 §7.3.1 要求标题回行「词意完整」，可「词意」要懂中文才知道 ——
# 脚本没有词典，只能按「两行字数均衡」猜（见 balanced_heading_break），实测把「城市防汛」的
# 「防汛」切开了：断在「城市防／汛隐患」。脚本负责给出最均衡的自动断点并把它说破，
# 用户若不同意这个断点，就在稿子里用「｜」标在自己想断的位置上，生成时按用户标的来。
HEADING_BREAK_MARKS = ("｜", "|")                                # 全角竖线优先，半角顺带认

def heading_explicit_lines(text):
    raw = str(text or "")                                        # 容错
    for mark in HEADING_BREAK_MARKS:                             # 两种标记都换成换行
        raw = raw.replace(mark, "\n")                            # 换行符是后续统一处理的形态
    lines = [line.strip() for line in raw.split("\n") if line.strip()]   # 去掉空行
    return lines if len(lines) > 1 else None                     # 只有真的断了行才返回，否则交回自动断行

# 附件说明的「回行对齐点」有多宽（GB/T 9704-2012 §7.3.4）：
#   「如有附件，在正文下空一行左空二字编排『附件』二字，后标全角冒号和附件名称……
#     附件名称较长需回行时，应当与上一行附件名称的首字对齐。」
# 返回值单位是「字」：附件名称之前的「附件：」「附件：1. 」这一小段占多宽。
# 例：「附件：1. 城市防汛隐患排查台账」 → 4.5 字（「附件」2 字 +「：」1 字 +「1.」1 字 + 空格 0.5 字）
# → 回行文字与「城」对齐。
def attachment_prefix_chars(text):
    match = re.match(r"^\s*附件\s*[:：]?\s*(?:\d+\s*[.．、]?\s*)?", text or "")   # 附件 + 冒号 + 可选顺序号
    return display_width(match.group(0)) / 2.0 if match else 0.0    # 前缀宽度换算成字

# 把标题折行的判断结果拼成给用户看的一句话。生成脚本与校验脚本共用同一份措辞。
def describe_heading_wrap_text(info):
    if not info:                                                   # 没有可报的内容
        return ""                                                  # 返回空串
    text = f"标题「{info['文字']}」在 {info['字号']:g}pt 下会折成 {info['行数']} 行" \
           f"（版心 {info['版心_cm']}cm）"                            # 前半句：折了几行
    if info["末行宽度"] < 4:                                        # 末行不到两个字
        text += f"，末行只剩约 {info['末行宽度'] / 2:.1f} 个字，属于要避免的「孤字」"   # 说清难看的点
    elif heading_wrap_is_bad(info):                                 # 末行不到整行四分之一
        text += f"，末行只有约 {info['末行宽度'] / 2:.1f} 个字、不足整行的四分之一，" \
                f"是头重脚轻的倒梯形"                                   # 说清难看的点
    text += f"。想排成一行，字号需不大于 {info['一行最大字号']}pt。"      # 给出可执行的出路
    return text                                                    # 返回整句

# 单元格左右内边距合计（厘米），用于把「文字需要多宽」换算成「这一列应当多宽」。
#
# 理论值是 0.38cm（Word 默认左右各 0.19cm），但**照理论值算会出实测问题**：
# 大 32 开图书稿的表 1，「城市」列表头与数据「上海」都正好需要 4 个半汉字宽（0.741cm），
# 按 0.38cm 算出来的列宽 1.122cm 里，可用文字宽度是 21.03pt，而两个字正好需要 21.00pt ——
# 差 0.03pt 的「刚好放得下」，LibreOffice 实际渲染时左右各留 5.5pt（不是 5.4pt），
# 于是「城市」被折成「城／市」、「上海」被折成「上／海」（实测渲染图确认）。
# 因此这里按 0.22cm/边 估算，给每列留出约 0.06cm 的实际余量，避免把版面推到毫厘之争上。
CELL_PADDING_CM = 0.44

# 计算表格每列该分到多宽。生成脚本与校验脚本共用这一份，避免「生成一套算法、校验另一套」。
#
# 总体思路：先给每列算一个「理想宽度」= max(表头宽, 最长数据宽)，再决定让谁让出宽度。
#   ① 理想宽度总和 ≤ 版心：所有列都拿到理想宽度，富余按比例摊开，让表格铺满版心；
#   ② 理想宽度总和 > 版心：从理想宽度往下削，每一步挑「削一格让总折行数涨得最少」的那一列。
#
# ② 为什么不按比例削（早先的做法，实测翻车）：
#   比例削会平均地压每一列，于是「数据比表头宽」的列也被一起压扁 ——
#   实测：A4 报告第 3 张表，「线路」列表头只要 4 个半汉字宽、数据「上海 2 号线」要 11 个，
#   按表头等比压窄后这一列只剩 2 个汉字宽，数据被折成三行（上海／2 号／线）；
#   而旁边那个 30 个半汉字宽的长表头列，本来就该折成两行 —— 折它只多一行，代价小得多。
#   现在的贪心会把这些「削一格不增加折行数」或「增加折行数最少」的格子挑出来削，
#   实测同一张表削完是 [11, 21, 6, 14, 8]：「上海 2 号线」完整一行，只有长表头折成两行。
#
# 参数：rows 表格二维数据（含表头行）、size_pt 表格字号、available_cm 版心宽度（厘米）
# 返回：(每列宽度厘米列表（含内边距）, 预警信息字典或 None)
def plan_table_columns(rows, size_pt, available_cm, padding_cm=CELL_PADDING_CM):
    planned = plan_table_widths(rows, size_pt, available_cm, padding_cm)   # 先算出列宽
    if planned is None:                                                # 这张表没有列
        return [], None                                                # 无事可做
    column_cm, header_units, width_units, ideal_units, cm_per_unit, content_avail = planned   # 拆开结果
    info = describe_table_fit(rows, header_units, width_units, ideal_units, cm_per_unit,
                              content_avail, available_cm, size_pt)     # 按最终列宽算「到底会不会折行」
    return column_cm, info                                             # 返回列宽与预警

# 列宽分配的核心算法（只算宽度，不产出给人看的预警）。
#
# 为什么要把「算宽度」和「写预警」拆开：给用户建议字号时，需要在好几个字号下各算一遍宽度，
# 再挑出「折行最少」的那一档。如果直接复用 plan_table_columns，就会变成
# 「算宽度 → 写预警 → 又去算宽度」的无限递归，所以在最里层留一个纯函数。
#
# 返回 None 表示这张表没有列；否则返回
# (每列宽度厘米（含内边距）, 表头宽单位, 最终列宽单位, 理想列宽单位, 每单位厘米, 可用宽度厘米)
def plan_table_widths(rows, size_pt, available_cm, padding_cm=CELL_PADDING_CM):
    columns = max((len(row) for row in rows), default=0)           # 最大列数
    if not columns:                                                # 没有列
        return None                                                # 无事可做
    cm_per_unit = unit_to_cm(size_pt)                              # 一个「半个汉字宽」约多少厘米
    header_units = []                                              # 每列表头占多少半汉字宽
    data_units = []                                                # 每列最长数据占多少半汉字宽
    for col_index in range(columns):                               # 逐列统计
        head = rows[0][col_index] if col_index < len(rows[0]) else ""   # 该列表头文字
        header_units.append(max(1, display_width(head)))           # 表头宽度，至少算一格
        longest = 0                                                # 该列数据里最长的宽度
        for row_data in rows[1:]:                                  # 只看数据行
            if col_index < len(row_data):                          # 该行有这一列
                longest = max(longest, display_width(row_data[col_index]))   # 取最长
        data_units.append(max(longest, 2))                         # 数据宽度，下限两个字
    ideal_units = [max(head, data) for head, data in zip(header_units, data_units)]   # 每列理想宽度
    content_avail = max(available_cm - padding_cm * columns, 3.0)   # 扣掉内边距后能放文字的宽度（厘米）
    avail_units = content_avail / cm_per_unit                      # 换成「多少个半汉字宽」
    ideal_total = sum(ideal_units) or 1                            # 理想总宽，兼作除零保护

    if ideal_total <= avail_units:                                 # 情况一：所有列都能拿到理想宽度
        slack = avail_units - ideal_total                          # 富余宽度
        width_units = [w + slack * (w / ideal_total) for w in ideal_units]   # 按比例摊开，让表格铺满版心
    else:                                                          # 情况二：放不下，必须有人让出宽度
        width_units = [float(w) for w in ideal_units]              # 从理想宽度出发
        floor_units = 2.0                                          # 任何一列都不会被削到一个汉字宽以下
        # 削到装得下为止。每一步只在「还高于下限」的列里挑一列削 1 格，
        # 挑法是：优先挑「削了不会多折行」的列；都会多折行时挑「多折行最少」的；
        # 仍然并列就挑最宽的那一列（它的余量最大，削它最不心疼）。
        while sum(width_units) > avail_units:                      # 还超出版心
            best_key = None                                        # 本步最优列的比较键
            best_index = None                                      # 本步要削的列号
            for col_index in range(columns):                       # 逐列试算「削一格」的代价
                if width_units[col_index] - 1 < floor_units:       # 已经到下限
                    continue                                       # 不能削
                before = wrapped_lines(rows[0][col_index] if col_index < len(rows[0]) else "",
                                       width_units[col_index])     # 这一列表头现在的行数
                after = wrapped_lines(rows[0][col_index] if col_index < len(rows[0]) else "",
                                      width_units[col_index] - 1)  # 削一格后的行数
                for row_data in rows[1:]:                          # 数据行也要算进去
                    if col_index >= len(row_data):                 # 该行没有这一列
                        continue                                   # 跳过
                    before += wrapped_lines(row_data[col_index], width_units[col_index])       # 现在的行数
                    after += wrapped_lines(row_data[col_index], width_units[col_index] - 1)    # 削后的行数
                key = (after - before, -width_units[col_index], col_index)   # 代价升序 → 宽度降序 → 列号升序
                if best_key is None or key < best_key:         # 找到更优的一列
                    best_key, best_index = key, col_index      # 记下来
            if best_index is None:                             # 所有列都到下限了
                break                                          # 再削下去只会更难看，停手
            width_units[best_index] -= 1                       # 削掉这一格
    column_cm = [width / 1.0 * cm_per_unit + padding_cm for width in width_units]   # 换成厘米并加回内边距
    return column_cm, header_units, width_units, ideal_units, cm_per_unit, content_avail   # 返回全部中间结果

# 数一张表在给定列宽下一共折了多少行（表头与数据都算）。
# 用途只有一个：比较不同字号下哪种更整齐，数字越小越好看。
def table_wrap_cost(rows, header_units, width_units):
    cost = 0                                                   # 折行代价
    for col_index in range(len(header_units)):                  # 逐列
        head = rows[0][col_index] if col_index < len(rows[0]) else ""   # 该列表头
        cost += wrapped_lines(head, width_units[col_index]) - 1   # 表头多折出来的行数
        for row_data in rows[1:]:                               # 数据行
            if col_index < len(row_data):                       # 该行有这一列
                cost += wrapped_lines(row_data[col_index], width_units[col_index]) - 1   # 数据多折出来的行数
    return cost                                                 # 返回总折行数

# 这张表「调到多少号字最整齐」，供预警里给用户一个具体数字。
#
# 为什么必须给数字：「可选：调小表格字号」这种话用户没法执行 —— 调多小？调完还折不折？
# 实测大 32 开图书稿里有 5 张表都报折行，光说「可以调小字号」，用户只能自己反复试。
# 这里的做法是：从当前字号往下每 0.5 磅试一档，先找「一格都不折」的最大字号；
# 实在找不到，就退而求其次，给「折行最少」的那一档，并如实说明仍然会折。
# 参数：rows 表格数据、available_cm 版心宽度、current_size 当前表格字号
# 返回：{"字号": x, "还能折行": 是否仍会折行, "当前字号": current_size, "最小可试字号": min_size}
#
# min_size 默认 6.5 磅（小六）：这是中文印刷里表格还能认读的下限，
# 再往下（七号 5.5、八号 5）字号本身就成了缺陷，宁可让用户换开本或拆表，也不建议把字缩到看不清。
def suggest_table_size(rows, available_cm, current_size, min_size=6.5, step=0.5):
    best = None                                                 # 折行最少的那一档
    size = float(current_size)                                  # 从当前字号开始往下试
    while size >= min_size - 1e-9:                               # 一直到最小可试字号
        planned = plan_table_widths(rows, size, available_cm)    # 在这个字号下算一遍列宽
        if planned is not None:                                 # 表格有列
            _column_cm, header_units, width_units = planned[0], planned[1], planned[2]   # 取需要的中间结果
            cost = table_wrap_cost(rows, header_units, width_units)   # 这一档的折行代价
            if cost == 0:                                       # 一格都不折
                return {"字号": round(size, 1), "还能折行": False,
                        "当前字号": float(current_size), "最小可试字号": float(min_size)}   # 直接给这一档
            if best is None or cost < best[0]:                   # 目前折行最少的一档
                # 连明细一起记下来：好告诉用户「换成这个字号后还剩哪几处折行」，
                # 否则只能说「还会折」，用户没法判断这点折行能不能接受。
                header_wrap, data_wrap = table_wrap_details(rows, header_units, width_units)   # 这一档的折行明细
                best = (cost, round(size, 1), header_wrap, data_wrap)   # 一并记下
        size -= step                                            # 再小半磅
    if best is None:                                            # 一档都没算出来
        return None                                             # 无从建议
    return {"字号": best[1], "还能折行": True, "剩余表头折行": best[2], "剩余数据折行": best[3],
            "当前字号": float(current_size), "最小可试字号": float(min_size)}   # 返回折行最少的那一档

# 按最终列宽，算出「哪些列表头会折行、哪些列数据会折行」的明细。
# 抽成独立函数是为了给两个调用方共用：① 生成/校验时的预警；② 建议字号时报告「换了字号还剩几处折行」。
# 返回 (表头折行列表 [(列名, 行数)], 数据折行列表 [(列名, 最惨文本, 行数)])。
def table_wrap_details(rows, header_units, width_units):
    header_wrap = []                                               # 表头折行的列
    data_wrap = []                                                 # 数据折行的列
    for col_index in range(len(header_units)):                     # 逐列核对
        name = rows[0][col_index] if col_index < len(rows[0]) else f"第 {col_index + 1} 列"   # 列名
        if wrapped_lines(name, width_units[col_index]) > 1:        # 表头折行了
            header_wrap.append((name, wrapped_lines(name, width_units[col_index])))   # 记下折成几行
        worst_text, worst_lines = "", 1                            # 该列数据里折得最惨的单元格
        for row_data in rows[1:]:                                  # 逐行算
            if col_index >= len(row_data):                         # 该行没有这一列
                continue                                           # 跳过
            lines = wrapped_lines(row_data[col_index], width_units[col_index])   # 这个单元格几行
            if lines > worst_lines:                                # 比之前更惨
                worst_text, worst_lines = row_data[col_index], lines   # 记下来
        if worst_lines > 1:                                        # 这一列有数据被折了
            data_wrap.append((name, worst_text, worst_lines))      # 记下列名、最惨的文本、行数
    return header_wrap, data_wrap                                  # 返回两份明细

# 按最终列宽，如实算出「哪些列的表头会折行、哪些列的数据会折行」。
#
# 为什么必须按最终列宽回算：早先的预警是拿「表头总宽 > 版心」当判据的，
# 那个判据带了每列半格的安全余量，于是实测误报过 —— 生成时警告「表 1 表头会折行」，
# 打出来的 PDF 里表 1 的表头排得好好的。警告不准，用户下次就不信警告了。
# 现在改为：拿到分好的列宽，逐格算行数，折了才报，还报出折成几行、哪一个单元格最惨。
def describe_table_fit(rows, header_units, width_units, ideal_units, cm_per_unit,
                       content_avail, available_cm, size_pt=None):
    header_wrap, data_wrap = table_wrap_details(rows, header_units, width_units)   # 复用明细算法
    if not header_wrap and not data_wrap:                          # 一格都没折
        return None                                                # 不报警
    return {                                                       # 组装预警信息，交给调用方提示
        "列数": len(header_units),                                  # 表格列数
        "表头折行": header_wrap,                                    # 表头会折行的列（列名, 行数）
        "数据折行": data_wrap,                                      # 数据会折行的列（列名, 最惨文本, 行数）
        "表头所需_cm": round(sum(header_units) * cm_per_unit + CELL_PADDING_CM * len(header_units), 2),   # 表头排成一行需要多宽
        "版心可用_cm": round(content_avail, 2),                     # 版心实际给了多宽
        "版心_cm": round(available_cm, 2),                          # 版心宽度
        # 给出「调到多少号字」的具体建议，用户才能照着改规格卡。
        # 当前字号由调用方传入；缺省时按「一个半汉字宽 = 0.01764cm」反推，算出个大概也比不给强。
        "建议字号": suggest_table_size(rows, available_cm,
                                       size_pt if size_pt else (cm_per_unit / 0.01764) if cm_per_unit else 0),
    }

# 把磅值翻回中文号数（如 7.5 → 六号）；不是标准号数就返回空串。
# 为什么要翻：中文用户照着「六号」挑字号比照着「7.5pt」直观得多。
def size_label_of(size_pt):
    for label, value in SIZE_TABLE.items():                        # 逐个对照号数
        if abs(float(value) - float(size_pt)) < 0.05:               # 允许极小的浮点误差
            return label                                          # 命中号数
    return ""                                                     # 不是标准号数

# 把预警信息拼成给用户看的一段话。生成脚本与校验脚本共用同一份措辞，
# 免得「生成时这么报、校验时那么报」，用户不知道该信哪一条。
# 把「换了建议字号之后还剩哪几处折行」说成一句话，供建议里引用。
def describe_wrap_leftover(suggestion):
    header_wrap = suggestion.get("剩余表头折行") or []              # 剩余的表头折行
    data_wrap = suggestion.get("剩余数据折行") or []                # 剩余的数据折行
    parts = [f"表头「{name}」（{count} 行）" for name, count in header_wrap]   # 表头部分
    parts += [f"数据「{text}」（{count} 行）" for _name, text, count in data_wrap]   # 数据部分
    if not parts:                                                  # 一处都没有
        return "0 处"                                              # 如实说没有
    total = len(header_wrap) + len(data_wrap)                      # 总处数
    return f"{total} 处（" + "、".join(parts[:3]) + ("…" if len(parts) > 3 else "") + "）"   # 最多举三个例子

def describe_table_fit_text(info):
    if not info:                                                   # 没有预警
        return ""                                                  # 返回空串
    lines = [f"{info['列数']} 列表格：表头排成一行共需 {info['表头所需_cm']}cm，"
             f"本开本版心 {info['版心_cm']}cm（去掉单元格内边距后可用 {info['版心可用_cm']}cm）。"]
    if info["表头折行"]:                                            # 有表头折行
        parts = "、".join(f"{name}（{count} 行）" for name, count in info["表头折行"])   # 列名 + 行数
        lines.append(f"表头会折行：{parts}。")                       # 如实说明
    if info["数据折行"]:                                            # 有数据折行
        parts = "、".join(f"{name}（如「{text}」折成 {count} 行）"
                          for name, text, count in info["数据折行"])   # 列名 + 例子 + 行数
        lines.append(f"数据会折行：{parts}。")                       # 如实说明
    # 给出可执行的建议：一个具体字号，而不是「可以调小」这种没法照做的话。
    # 三种情况分开说清楚 —— ①算得出不折行的字号 ②调到最小仍会折行 ③这一档已经是折行最少的。
    suggestion = info.get("建议字号") or {}                          # 取建议字号
    if suggestion.get("字号"):                                       # 有具体数字
        current = suggestion.get("当前字号") or 0                    # 当前字号
        label = size_label_of(suggestion["字号"])                     # 建议字号的号数名（如「六号」）
        label_text = f"（{label}）" if label else ""                   # 有号数名才带上
        if not suggestion.get("还能折行"):                            # 调到这个字号就一格都不折
            lines.append(f"建议：在规格卡里把 figures_tables.table_size_pt 设为 {suggestion['字号']:g}pt"
                         f"{label_text}，当前是 {current:g}pt；调到这个字号表头与数据都不再折行。"
                         f"若不想缩小字号，就换更大开本或把这张表拆成两张。")   # 给出第一条出路
        elif suggestion["字号"] < suggestion.get("最小可试字号", 6.5) + 1e-9:   # 已经试到最小字号（6.5pt，小六）
            lines.append(f"建议：字号已经没法再小（最小试到 {suggestion['字号']:g}pt，再小就看不清了），"
                         f"但仍会折行的有 {describe_wrap_leftover(suggestion)}，"
                         f"说明这张表的内容本身比版心宽。请换更大开本，或把这张表拆成两张。")   # 如实说明只剩两条出路
        else:                                                        # 找到折行最少的一档
            lines.append(f"建议：把 figures_tables.table_size_pt 设为 {suggestion['字号']:g}pt"
                         f"{label_text}（当前 {current:g}pt）时折行最少，仍会折的只剩 "
                         f"{describe_wrap_leftover(suggestion)}；"
                         f"想一格都不折，只能换更大开本或把这张表拆成两张。")   # 给出最优折中
    else:                                                            # 算不出建议
        lines.append("建议：换更大开本／拆成两张表／在规格卡里用 figures_tables.table_size_pt 调小表格字号。")
    return "".join(lines)                                          # 拼成一段

# 决定表格每一列该用什么对齐方式。DOCX、公众号 HTML、重排现有 Word 三处共用这一份，
# 否则同一份 Markdown 出 DOCX 和出 HTML 会得到不同的表格对齐（这个坑踩过一次）。
#
# 判定优先级（三档，越靠前越优先）：
#   ① source_aligns 里有值 → 用源文件（Markdown 对齐标记）或原稿已有的对齐
#   ② 该列整列都是数字且规格卡声明了 number_column_alignment → 用数字列对齐
#   ③ 其余情况 → 用规格卡声明的 text_column_alignment
# 三档都拿不到值时返回空串，表示「不干预」，由各载体保持自己的默认，不写任何对齐。
# 另有一条配套规则：按「列」判定，不按「格」判定 —— 逐格判断会让同一列里
# 有的行左对齐、有的行右对齐，看起来像没排过版。
def resolve_column_alignments(rows, source_aligns, cfg):
    columns = max((len(row) for row in rows), default=0)          # 最大列数
    data_rows = rows[1:]                                          # 数据行（不含表头）
    text_align = cfg.get("text_column_alignment") or ""           # 规格卡声明的文字列对齐
    number_align = cfg.get("number_column_alignment") or ""       # 规格卡声明的数字列对齐
    result = []                                                   # 每列的对齐结果
    for index in range(columns):                                  # 逐列判断
        if index < len(source_aligns) and source_aligns[index]:   # ① 源文件/原稿已有明确对齐
            result.append(source_aligns[index])                   # 以它为准
            continue                                              # 下一列
        values = [row[index].strip() for row in data_rows
                  if index < len(row) and row[index].strip()]     # 该列全部非空内容
        if values and all(is_numeric_cell(value) for value in values):   # ② 整列都是数字
            result.append(number_align)                           # 用数字列对齐（未声明则为空）
        else:                                                     # ③ 整列含文字
            result.append(text_align)                             # 用文字列对齐（未声明则为空）
    return result                                                 # 返回每列的对齐方式

# 把「Markdown 的第 # 级标题」解析成预设里的那一段标题配置。
# 各预设的键名并不统一：公文写 doc_title + level1..4，书籍写 chapter + section，
# 论文写 title + level1..2，公众号写 h1/h2/h3。以前脚本只认 level{N}/h{N}，
# 于是 book-cn 的章标题、gov-doc 的公文标题都被静默忽略，只剩默认样式。
def resolve_heading(headings, level):
    headings = headings or {}                                     # 容错：没有标题段时按空字典处理
    shifted = heading_shift(headings)                              # 取级别偏移量（与 infer_structure 共用同一规则）
    if level == 1:                                                # 第 1 级标题
        for key in ("doc_title", "title", "chapter", "level1", "h1"):   # 依次尝试各种命名
            if headings.get(key):                                 # 命中
                return headings[key] or {}                        # 返回该段配置
    candidates = [f"level{level - shifted}", f"h{level}"]         # 普通级别：相对编号 与 h 编号
    if level == 2:                                                # 第 2 级
        candidates.append("section")                              # 书籍类预设用 section 表示第 2 级
    for key in candidates:                                        # 逐个尝试
        item = headings.get(key)                                  # 取该键
        if isinstance(item, dict) and item:                       # 命中且是有效配置
            return item                                           # 返回该段配置
    for parent_level in range(level - 1, 0, -1):                  # 缺哪一级，就沿用上一级的配置
        parent = resolve_heading(headings, parent_level)          # 递归取上一级
        if parent:                                                # 上一级有配置
            return dict(parent, inherited_from=parent_level)      # 标注继承来源，便于排查
    return {}                                                     # 都没有则返回空，调用方用默认值

# 判断字体是否真正可用：既要名字出现在字体列表里，也要能匹配到别名
def font_is_available(name, available):
    # 空名视为不需要检查
    if not name:
        return True
    # 精确命中
    if name in available:
        return True
    # 大小写不敏感命中
    lowered = {item.lower() for item in available}    # 构造小写索引
    return name.lower() in lowered                     # 返回是否命中

# ─────────────────────────────────────────────────────────────
# 字体获取与授权指南
#
# 用途：当用户机器上缺少标准要求的字体时，第一步不是替换，而是回答
#      「这个字体能不能免费、合法地拿到」。本表就是回答这个问题的数据源。
# 维护要求：每条 record 都必须写明 verified_at（核验日期）与 source（核验渠道）。
#          URL 与授权条款会变，使用前如距核验日期超过 6 个月，应先重新核验。
#          核验方式见 references/fonts.md 第四节。
# ─────────────────────────────────────────────────────────────
FONT_ACQUISITION = {
    # ── 一、开源可商用字体：可以免费下载，优先推荐 ──
    "Source Han Serif SC": {                                          # 思源宋体（简体）
        "display": "思源宋体 Source Han Serif SC",                     # 展示名
        "free_download": True,                                        # 可以免费获取
        "license": "SIL Open Font License 1.1（允许免费商用、允许嵌入文档）",   # 授权
        "source": "GitHub adobe-fonts/source-han-serif 仓库内 LICENSE.txt 原文",   # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": "https://github.com/adobe-fonts/source-han-serif/releases",   # 下载入口
        "note": "体积较大（每字重约 20-30MB），建议只装 Regular/Bold 两档",        # 备注
    },
    "思源宋体": {                                                      # 思源宋体的中文名
        "display": "思源宋体 Source Han Serif SC",                     # 展示名
        "free_download": True,                                        # 可以免费获取
        "license": "SIL Open Font License 1.1（允许免费商用、允许嵌入文档）",   # 授权
        "source": "GitHub adobe-fonts/source-han-serif 仓库内 LICENSE.txt 原文",   # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": "https://github.com/adobe-fonts/source-han-serif/releases",   # 下载入口
        "note": "同上，中文名入口",                                     # 备注
    },
    "Source Han Sans SC": {                                           # 思源黑体（简体）
        "display": "思源黑体 Source Han Sans SC",                      # 展示名
        "free_download": True,                                        # 可以免费获取
        "license": "SIL Open Font License 1.1（允许免费商用、允许嵌入文档）",   # 授权
        "source": "GitHub adobe-fonts/source-han-sans 仓库内 LICENSE.txt 原文",   # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": "https://github.com/adobe-fonts/source-han-sans/releases",    # 下载入口
        "note": "思源黑体有 SC/TC/JP/KR 多个子集，简体请选 SC",          # 备注
    },
    "思源黑体": {                                                      # 思源黑体的中文名
        "display": "思源黑体 Source Han Sans SC",                      # 展示名
        "free_download": True,                                        # 可以免费获取
        "license": "SIL Open Font License 1.1（允许免费商用、允许嵌入文档）",   # 授权
        "source": "GitHub adobe-fonts/source-han-sans 仓库内 LICENSE.txt 原文",   # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": "https://github.com/adobe-fonts/source-han-sans/releases",    # 下载入口
        "note": "同上，中文名入口",                                     # 备注
    },
    "LXGW WenKai": {                                                  # 霞鹜文楷
        "display": "霞鹜文楷 LXGW WenKai",                             # 展示名
        "free_download": True,                                        # 可以免费获取
        "license": "SIL Open Font License 1.1",                       # 授权
        "source": "GitHub API 读取 lxgw/LxgwWenKai 仓库 license 字段",   # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": "https://github.com/lxgw/LxgwWenKai/releases",     # 下载入口
        "note": "楷体风格的开源字体，可作楷体的免费替代；单字重约 24-27MB",        # 备注
    },
    "霞鹜文楷": {                                                      # 霞鹜文楷中文名
        "display": "霞鹜文楷 LXGW WenKai",                             # 展示名
        "free_download": True,                                        # 可以免费获取
        "license": "SIL Open Font License 1.1",                       # 授权
        "source": "GitHub API 读取 lxgw/LxgwWenKai 仓库 license 字段",   # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": "https://github.com/lxgw/LxgwWenKai/releases",     # 下载入口
        "note": "同上，中文名入口",                                     # 备注
    },
    "Zhuque Fangsong": {                                              # 朱雀仿宋
        "display": "朱雀仿宋 Zhuque Fangsong",                          # 展示名
        "free_download": True,                                        # 可以免费获取
        "license": "SIL Open Font License 1.1",                       # 授权
        "source": "GitHub API 读取 TrionesType/zhuque 仓库 license 字段",   # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": "https://github.com/TrionesType/zhuque",           # 下载入口
        "note": "基于开源字体制作的仿宋，是目前少见的「仿宋 + 免费商用」组合，公文场景值得优先考虑",   # 备注
    },
    "Noto Serif SC": {                                                # Noto 宋体
        "display": "Noto Serif SC（Google 版思源宋体）",                # 展示名
        "free_download": True,                                        # 可以免费获取
        "license": "SIL Open Font License 1.1",                       # 授权
        "source": "开源字体通行授权，思源系列的 Google 发行版",            # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": "https://fonts.google.com/noto/specimen/Noto+Serif+SC",   # 下载入口
        "note": "与思源宋体同源，字形一致，可按方便程度任选其一",           # 备注
    },
    "Noto Sans SC": {                                                 # Noto 黑体
        "display": "Noto Sans SC（Google 版思源黑体）",                 # 展示名
        "free_download": True,                                        # 可以免费获取
        "license": "SIL Open Font License 1.1",                       # 授权
        "source": "开源字体通行授权，思源系列的 Google 发行版",            # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": "https://fonts.google.com/noto/specimen/Noto+Sans+SC",    # 下载入口
        "note": "与思源黑体同源",                                       # 备注
    },

    # ── 二、随系统分发的商业字体：没有官方免费下载，需要授权或替代 ──
    "仿宋_GB2312": {                                                   # 公文正文指定字体
        "display": "仿宋_GB2312",                                      # 展示名
        "free_download": False,                                       # 无法官方免费下载
        "license": "商业字体，随中文版 Windows/Office 分发，归字体厂商所有；未获授权不得用于对外分发的文件中",   # 授权说明
        "source": "该字体无官方独立下载页；授权归属以字体厂商公示为准，使用前请自行核实",   # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": None,                                             # 没有下载入口
        "note": "Mac 上不存在合法免费来源。正式公文送审建议在装有该字体的 Windows 机器上生成；否则请把规格卡的字体改成用户指定的本机同类字体",   # 备注
    },
    "楷体_GB2312": {                                                   # 公文层次序数第二层常用
        "display": "楷体_GB2312",                                      # 展示名
        "free_download": False,                                       # 无法官方免费下载
        "license": "商业字体，随中文版 Windows/Office 分发",              # 授权说明
        "source": "无官方独立下载页",                                    # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": None,                                             # 没有下载入口
        "note": "可改用开源字体「霞鹜文楷」（免费安装），字形风格接近",                   # 备注
    },
    "方正小标宋简体": {                                                 # 公文标题与红头指定字体
        "display": "方正小标宋简体",                                     # 展示名
        "free_download": False,                                       # 无法官方免费下载
        "license": "方正字库商业字体，需按方正字库授权模式购买；方正另有少量免费商用字体，但「小标宋」不在其列",   # 授权说明
        "source": "方正字库官网 foundertype.com 授权说明页（本次未取到页面正文，条款以官网为准，使用前请复核）",   # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": "https://www.foundertype.com/",                    # 官网入口（需自行确认授权）
        "note": "公文标题严格档必须用它；改用开源字体可选思源宋体加粗，改用本机字体可选宋体加粗",   # 备注
    },
    "宋体": {                                                          # 中易宋体
        "display": "宋体 SimSun",                                      # 展示名
        "free_download": False,                                       # 无法官方免费下载
        "license": "商业字体，随中文版 Windows 分发；跨设备分发文档时嵌入该字体存在授权风险",   # 授权说明
        "source": "无官方独立下载页",                                    # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": None,                                             # 没有下载入口
        "note": "macOS 上可用系统自带的「宋体-简 Songti SC」或开源思源宋体替代",   # 备注
    },
    "SimSun": {                                                        # 宋体英文名
        "display": "宋体 SimSun",                                      # 展示名
        "free_download": False,                                       # 无法官方免费下载
        "license": "同「宋体」",                                        # 授权说明
        "source": "同「宋体」",                                         # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": None,                                             # 没有下载入口
        "note": "同「宋体」",                                           # 备注
    },
    "黑体": {                                                          # 中易黑体
        "display": "黑体 SimHei",                                      # 展示名
        "free_download": False,                                       # 无法官方免费下载
        "license": "商业字体，随中文版 Windows 分发",                     # 授权说明
        "source": "无官方独立下载页",                                    # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": None,                                             # 没有下载入口
        "note": "开源替代：思源黑体；macOS 可用「黑体-简 Heiti SC」",        # 备注
    },
    "SimHei": {                                                        # 黑体英文名
        "display": "黑体 SimHei",                                      # 展示名
        "free_download": False,                                       # 无法官方免费下载
        "license": "同「黑体」",                                        # 授权说明
        "source": "同「黑体」",                                         # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": None,                                             # 没有下载入口
        "note": "同「黑体」",                                           # 备注
    },
    "微软雅黑": {                                                      # Windows 界面字体
        "display": "微软雅黑 Microsoft YaHei",                          # 展示名
        "free_download": False,                                       # 无法官方免费下载
        "license": "微软委托定制、归微软所有，随 Windows 分发；不得单独提取分发",   # 授权说明
        "source": "无官方独立下载页",                                    # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": None,                                             # 没有下载入口
        "note": "开源替代：思源黑体；macOS 可用苹方",                     # 备注
    },
    "Microsoft YaHei": {                                               # 微软雅黑英文名
        "display": "微软雅黑 Microsoft YaHei",                          # 展示名
        "free_download": False,                                       # 无法官方免费下载
        "license": "同「微软雅黑」",                                     # 授权说明
        "source": "同「微软雅黑」",                                      # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": None,                                             # 没有下载入口
        "note": "同「微软雅黑」",                                        # 备注
    },
    "Times New Roman": {                                               # 中文排版常用西文字体
        "display": "Times New Roman",                                  # 展示名
        "free_download": False,                                       # 无法官方免费下载
        "license": "Monotype 商业字体，随 Windows / macOS / Microsoft Office 分发",   # 授权说明
        "source": "随系统或 Office 分发，无免费独立下载渠道",              # 核验渠道
        "verified_at": "2026-09-17",                                  # 核验日期
        "download": None,                                             # 没有下载入口
        "note": "缺失时的开源替代：Noto Serif / 思源宋体的西文字形",        # 备注
    },
}

# 按字体名查询获取指南，支持中英文别名与大小写不敏感匹配
def describe_font(name):
    if not name:                                                  # 空名直接返回空
        return None                                               # 返回空表示无信息
    if name in FONT_ACQUISITION:                                  # 精确命中
        return FONT_ACQUISITION[name]                             # 返回该条记录
    lowered = name.strip().lower()                                # 转小写便于模糊匹配
    for key, value in FONT_ACQUISITION.items():                   # 遍历全表
        if key.lower() == lowered:                                # 大小写不敏感命中
            return value                                          # 返回该条记录
    for key, value in FONT_ACQUISITION.items():                   # 再做一次包含匹配
        if key.lower() in lowered or lowered in key.lower():      # 双向包含
            return value                                          # 返回该条记录
    return None                                                   # 查不到返回空

# 生成某个缺失字体的完整决策树文本：先查能否免费下载，再给替代方案
def font_acquisition_advice(name):
    info = describe_font(name)                                    # 查询获取指南
    lines = []                                                    # 初始化输出行列表
    if info is None:                                              # 表中没有这个字体
        lines.append(f"「{name}」不在已知字体库中，需要联网核实：")     # 提示需要查证
        lines.append(f"  1. 搜索「{name} 官方下载」，确认是否可免费、合法获取")   # 第 1 步
        lines.append("  2. 若可免费获取：给出官方下载地址，安装后重新跑字体检测") # 第 2 步
        lines.append("  3. 若属商业字体：让用户在购买授权 / 兼容替代 / 开源替代中选一档")   # 第 3 步
        return "\n".join(lines)                                   # 返回文本
    lines.append(f"「{info['display']}」")                          # 打印字体展示名
    if info["free_download"]:                                     # 如果可免费下载
        lines.append("  ① 能否免费获取：可以，且授权允许免费商用")       # 回答第一个问题
        lines.append(f"  ② 授权：{info['license']}")                 # 打印授权
        lines.append(f"  ③ 下载：{info['download']}")                # 打印下载入口
    else:                                                         # 如果不可免费下载
        lines.append("  ① 能否免费获取：不能，没有官方免费下载渠道")       # 回答第一个问题
        lines.append(f"  ② 授权：{info['license']}")                 # 打印授权
        lines.append(f"  ③ 参考：{info['download'] or '无官方下载页'}")   # 打印参考入口
    lines.append(f"  ④ 备注：{info['note']}")                      # 打印备注
    lines.append(f"  ⑤ 核验：{info['verified_at']} 查自 {info['source']}")   # 打印核验溯源
    # 不再给出「自动替换成哪个」——本项目禁止替身，改为列出建议清单供用户自己选
    platform = detect_platform()                                  # 判断当前平台
    table = FALLBACK_CANDIDATES.get(name) or {}                   # 查兼容候选表
    near = (table.get(platform) or [])[:5]                        # 取本平台前 5 个候选
    lines.append(f"  ⑥ 若决定改用别的字体：本机同类候选 → {'、'.join(near) if near else '（无预设候选，可用 font_check.py --suggest 查）'}")   # 打印候选
    return "\n".join(lines)                                       # 返回文本

# ─────────────────────────────────────────────────────────────
# 公文版头必填项检查
#
# 红头（发文机关标志）、发文字号、签发人这些要素在用户交来的稿子里通常一个字都没有，
# 只能问用户。要是不问就生成，build_docx 会把红头渲染成光秃秃的「文件」两个字、
# 把发文字号渲染成「〔2026〕号」，而且不报任何错 —— 这正是「后台空转半天丢给用户一个垃圾」。
# 所以这里把必填项集中定义一次，spec_check.py（体检时拦）与 build_docx.py（生成时拦）共用。
# ─────────────────────────────────────────────────────────────
def masthead_missing_fields(spec):
    masthead = spec.get("masthead") or {}                      # 取版头配置
    if not masthead.get("enabled"):                            # 没启用红头就不用检查
        return []                                              # 返回空列表
    missing = []                                               # 收集缺失项
    # ① 发文机关名称：红头印的就是它，缺了红头无从谈起
    if not str(masthead.get("organization") or "").strip():    # 名称为空或只有空格
        missing.append({"label": "发文机关全称（红头文字）",       # 给用户看的名称
                        "path": "masthead.organization",        # 规格卡里的字段路径
                        "hint": "红头印的就是它，如「示例市人民政府」；问用户单位全称或规范简称"})   # 怎么补
    # ② 发文字号：机关代字、年份、顺序号三件套，缺任何一个都会印出残缺的号
    doc_number = masthead.get("doc_number") or {}              # 取发文字号配置
    if doc_number.get("enabled"):                              # 启用了发文字号才检查
        for key, label, hint in [("agency_code", "机关代字", "如「示例政」，问用户单位办公室或翻上一份同类文件；"
                                                          "用户明确表示这份文件不写机关代字时，写 agency_code_omitted: true"),
                                 ("year", "年份", "发文当年四位年份，如 2026"),
                                 ("serial", "发文顺序号", "不编虚位：1 就写 1，不写 01；也不要加「第」字")]:
            # agency_code_omitted 是用户明确说「就是不写机关代字」时的开关。
            # 为什么要单独一个开关：机关代字是内容项，脚本不能替用户编；但字段空着有两种完全不同的情况
            # ——「还没问过用户」和「用户明确不要」。前者必须拦下（否则印出残缺的号），后者要放行。
            if key == "agency_code" and doc_number.get("agency_code_omitted"):   # 用户明确不要机关代字
                continue                                       # 跳过这项检查
            if not str(doc_number.get(key) if doc_number.get(key) is not None else "").strip():   # 该子项为空
                missing.append({"label": f"发文字号的{label}",   # 缺失项名称
                                "path": f"masthead.doc_number.{key}",   # 字段路径
                                "hint": hint})                  # 怎么补
    # ③ 签发人：只有上行文才有，启用了就必须有姓名
    signer = masthead.get("signer") or {}                      # 取签发人配置
    if signer.get("enabled") and not str(signer.get("name") or "").strip():   # 启用了签发人却没写姓名
        missing.append({"label": "签发人姓名",                   # 缺失项名称
                        "path": "masthead.signer.name",         # 字段路径
                        "hint": "只有上行文才需要签发人；不签发就把 masthead.signer.enabled 改成 false"})   # 怎么补
    return missing                                             # 返回全部缺失项

# 版记（GB/T 9704-2012 §7.4）的必填项：启用版记就必须有印发机关和印发日期，
# 缺了会印出「〔印发机关〕〔印发日期〕」这种占位符。抄送机关是可选项，没有就不排那一行。
# 与 masthead_missing_fields 同样的道理：脚本不替用户编内容，缺项一律拦下。
def record_section_missing_fields(spec):
    record = spec.get("record_section") or {}                  # 取版记配置
    if not record.get("enabled"):                              # 没启用版记就不用检查
        return []                                              # 返回空列表
    missing = []                                               # 收集缺失项
    if not str(record.get("issuing_agency") or "").strip():    # 印发机关为空
        missing.append({"label": "印发机关",                     # 缺失项名称
                        "path": "record_section.issuing_agency",   # 字段路径
                        "hint": "公文印制主管部门的规范全称，通常是发文机关的办公厅（室）；问用户或翻上一份同类文件"})   # 怎么补
    if not str(record.get("issue_date") or "").strip():         # 印发日期为空
        missing.append({"label": "印发日期",                     # 缺失项名称
                        "path": "record_section.issue_date",     # 字段路径
                        "hint": "公文送印完毕的日期，用阿拉伯数字标全年月日，如「2026年9月18日」；月日不编虚位"})   # 怎么补
    return missing                                             # 返回全部缺失项

# ─────────────────────────────────────────────────────────────
# 公文主体要素（GB/T 9704-2012 §7.3）的识别形态与横向位置计算
#
# 为什么放进公共库：这些形态原本只写在 infer_structure.py 里，于是出现了「两层脱节」——
# 推断层认得出主送机关、发文机关署名、成文日期，渲染层却只知道它们是一段普通正文，
# 一律按「首行缩进二字」排版：主送机关没顶格、成文日期没右空四字。
# 用户拿到的就是不规范的公文，而且报告里还说「识别到了」。现在只有这一份定义，两层共用。
# ─────────────────────────────────────────────────────────────

# 各类要素的识别形态（只在预设声明了 structure_rules.detect_elements 时才启用）
ELEMENT_DETECTORS = {
    "recipient": re.compile(r"^[^。！？]{2,60}[：:]$"),   # 主送机关：以冒号结尾的短段落
    "attachment": re.compile(r"^附件\s*[:：]?\s*\S*"),    # 附件说明：以「附件」开头
    "date": re.compile(r"^[〇零一二三四五六七八九十\d]{2,4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日$"),   # 成文日期
    "signature": re.compile(r"^[\u4e00-\u9fff（）()]{2,30}(政府|局|委员会|办公室|厅|部|公司|集团|大学|学院|医院)$"),   # 发文机关署名
}

# 要素类型 → 给用户看的中文名
ELEMENT_LABELS = {
    "recipient": "主送机关", "signature": "发文机关署名", "date": "成文日期",   # 公文主体三要素
    "attachment": "附件说明", "heading": "标题", "body": "正文", "table": "表格",   # 其余块类型
}

# 取该规格声明要识别的要素形态。没声明就返回空字典 —— 等于「不识别、不干预」，
# 书籍、论文等体裁的规格卡里没有 structure_rules.detect_elements，因此不会被误判。
def element_detectors_for(spec):
    rules = spec.get("structure_rules") or {}                 # 取结构规则段
    declared = set(rules.get("detect_elements") or [])        # 该体裁要识别的要素名
    return {key: pattern for key, pattern in ELEMENT_DETECTORS.items() if key in declared}   # 只留声明的

# 按规格声明的要素形态给块打标签：命中者写入 block["preset_element"]。
# 位置约束与推断层完全一致（主送机关不在第 1 块、署名与日期只在文末三块内），
# 否则正文里一句「XX 局：」就会被当成主送机关。
# 返回 (块列表, 统计字典)，统计用于在生成时打印「识别到什么、按什么排的」。
def label_preset_elements(blocks, spec):
    detectors = element_detectors_for(spec)                   # 该规格要识别的要素
    if not detectors:                                         # 一个都没声明
        return blocks, {}                                     # 原样返回，不做任何标注
    counts = {}                                               # 各要素识别到的数量
    seen = set()                                              # 已用掉的要素名（同一要素只认一次）
    total = len(blocks)                                       # 块总数，用于算「文末三块」
    for index, block in enumerate(blocks):                    # 逐块扫描
        if block.get("type") != "paragraph":                  # 只有普通段落才可能是这些要素
            continue                                          # 标题、表格、引用等跳过
        first_line = (block.get("text") or "").strip().split("\n")[0].strip()   # 取首行做形态比对
        if not first_line:                                    # 空段落
            continue                                          # 跳过
        element = ""                                          # 本块的要素名
        if "recipient" in detectors and "recipient" not in seen and index > 0 \
                and detectors["recipient"].match(first_line):  # 主送机关
            element = "recipient"                              # 记为主送机关
        elif index >= total - 3 and "signature" in detectors and "signature" not in seen \
                and detectors["signature"].match(first_line):   # 文末的发文机关署名
            element = "signature"                              # 记为署名
        elif index >= total - 3 and "date" in detectors and "date" not in seen \
                and detectors["date"].match(first_line):        # 文末的成文日期
            element = "date"                                   # 记为日期
        elif "attachment" in detectors and detectors["attachment"].match(first_line):   # 附件说明
            element = "attachment"                             # 记为附件说明
        if not element:                                        # 什么都不是
            continue                                           # 保持普通正文
        block["preset_element"] = element                      # 打上标签，渲染层据此改排版
        seen.add(element)                                      # 登记已用掉
        counts[element] = counts.get(element, 0) + 1            # 统计累加
    return blocks, counts                                      # 返回块列表与统计

# 算出公文署名与成文日期各自的「左空字数」（GB/T 9704-2012 §7.3.5）。
#
# 条款原文（国家标准全文公开系统公开版本，核验记录见 references/presets/gov-doc-cn.md）：
#   §7.3.5.1 加盖印章的公文：成文日期一般右空四字编排；单一机关行文时，
#            一般在成文日期之上、以成文日期为准居中编排发文机关署名。
#   §7.3.5.2 不加盖印章的公文：在正文（或附件说明）下空一行右空二字编排发文机关署名，
#            在发文机关署名下一行编排成文日期，首字比发文机关署名首字右移二字；
#            如成文日期长于发文机关署名，应当使成文日期右空二字编排，并相应增加发文机关署名右空字数。
#
# 返回「左空字数」而不是磅值：中文横向定位以字为单位，磅值换算交给渲染层。
# 「字」按一个汉字宽计，阿拉伯数字算半个字（由 display_width 负责折算）。
def gov_signature_layout(signature_text, date_text, spec):
    signature_width = display_width(signature_text) / 2.0      # 署名宽度（字）
    date_width = display_width(date_text) / 2.0                # 成文日期宽度（字）
    chars_per_line = float((spec.get("page") or {}).get("chars_per_line") or 28)   # 每行字数，默认 28
    signature_cfg = (spec.get("body_elements") or {}).get("signature") or {}       # 取署名排版配置
    mode = str(signature_cfg.get("mode") or "with_seal").strip()                   # 印章模式
    notes = []                                                 # 需要转告用户的说明
    if mode not in ("with_seal", "without_seal"):              # 取值不认识（例如写成「盖章」）
        notes.append(f"body_elements.signature.mode 的值「{mode}」不是合法值"
                     f"（只支持 with_seal / without_seal），本次按盖章公文的排法处理。")   # 如实告知
        mode = "with_seal"                                     # 退回盖章那套
    if mode == "without_seal":                                 # 不加盖印章（§7.3.5.2）
        signature_left = chars_per_line - 2 - signature_width   # 署名右空二字
        date_left = signature_left + 2                          # 日期首字比署名首字右移二字
        if date_left + date_width > chars_per_line - 2:         # 日期比署名长，右空二字放不下
            date_left = chars_per_line - 2 - date_width         # 改为日期右空二字
            signature_left = date_left - 2                      # 署名相应左移，保持二字的错位关系
            notes.append("成文日期长于发文机关署名，按 §7.3.5.2 改为「日期右空二字、署名相应左移」。")
    else:                                                      # 加盖印章（§7.3.5.1）
        date_left = chars_per_line - 4 - date_width             # 成文日期右空四字
        signature_left = date_left + (date_width - signature_width) / 2   # 署名以成文日期为准居中
        if min(date_left, signature_left) < 0:                  # 算出来越出版心（内容太长）
            notes.append("按 §7.3.5 算出的署名/日期位置越出版心（署名或日期太长），已按从左边缘起排，"
                         "请核对发文机关名称与成文日期是否写全。")   # 如实告知，不静默
    signature_left = max(0.0, signature_left)                   # 负数一律按顶格处理
    date_left = max(0.0, date_left)                             # 同上
    return {"mode": mode,                                        # 采用的印章模式
            "signature_left_chars": round(signature_left, 2),     # 署名左空字数
            "date_left_chars": round(date_left, 2),               # 成文日期左空字数
            "notes": notes}                                      # 需要转告用户的说明

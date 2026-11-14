#!/usr/bin/env python3
# 本脚本是「抽取层」：把用户丢来的任意输入，统一转成一份保序的 Markdown 草稿 + 一份体检报告。
#
# 为什么需要它：
#   用户的输入五花八门 —— 聊天里直接粘一段文字、发一个 .docx、发一个 .pdf、发一个 .md。
#   后面的结构识别、规格套用都只认一种中间产物。如果每个脚本各自去解析各种格式，
#   解析逻辑会重复四遍，而且会漂移。所以统一收在这里，只做一件事：内容进来，草稿出去。
#
# 它只做抽取，不做判断：
#   - 不猜哪一段是标题（那是 infer_structure.py 的活）
#   - 不改一个字（错别字交给 typo_check.py）
#   - 不套任何格式（规格交给 build_*.py）
#
# 它只回答一个问题：这份输入自带结构吗？
#   自带结构 → 后面的识别层可以直接信任，跳过猜测
#   不带结构 → 后面的识别层必须去推断，并把推断结果交给用户确认
#
# 用法：
#   python3 scripts/extract_source.py 稿子.docx
#   python3 scripts/extract_source.py 稿子.pdf
#   python3 scripts/extract_source.py 稿子.md
#   python3 scripts/extract_source.py --text "用户直接粘在聊天里的一段文字"
#   python3 scripts/extract_source.py 稿子.docx --output 草稿.md
#   python3 scripts/extract_source.py 一.docx 二.docx      多个文件按顺序拼接

import argparse   # 用于解析命令行参数
import io         # 用于按 UTF-8 读写文件
import os         # 用于路径判断与拼接
import re         # 用于识别 Markdown 结构标记
import sys        # 用于控制退出码与错误输出
import tempfile   # 用于给纯文字模式选一个不污染项目的落地目录

# 把 scripts 目录加入模块路径，保证能导入公共库
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import spec_lib   # 导入公共库（DOCX 标题判定、汉字码点范围等）

# 支持的纯文本类扩展名
TEXT_EXTENSIONS = (".md", ".markdown", ".txt", ".text")   # Markdown 与纯文本

# 统计一段文字里的中文字符数
def count_cjk(text):
    return sum(1 for char in text if spec_lib.CJK_START <= char <= spec_lib.CJK_END)   # 逐字符判断码点范围（范围常量收在公共库）

# 判断一段 Markdown 文本是否自带结构。
# 判定依据：出现了标题标记、列表标记或表格分隔行，说明作者本来就分了层。
def markdown_has_structure(text):
    for line in text.split("\n"):                       # 逐行扫描
        stripped = line.strip()                         # 去掉首尾空白
        if re.match(r"^#{1,6}\s+\S", stripped):         # 命中 # 标题
            return True                                 # 有结构
        if re.match(r"^\|[\s:|-]+\|$", stripped):       # 命中表格分隔行
            return True                                 # 有结构
    return False                                        # 都没有，视为无结构

# ── 各格式的抽取实现 ───────────────────────────────────────────

# 抽取纯文本类文件（.md / .txt）
def extract_text_file(path):
    raw = io.open(path, encoding="utf-8", errors="replace").read()   # 读取全文，编码异常时替换而不是崩溃
    return raw, markdown_has_structure(raw), "按 UTF-8 直接读取"        # 纯文本天然保序

# 把 python-docx 的表格转成 Markdown 表格，保证内容不丢、顺序不变
def table_to_markdown(table):
    lines = []                                                          # 收集 Markdown 表格行
    for row_index, row in enumerate(table.rows):                        # 逐行遍历
        cells = [cell.text.strip().replace("|", "\\|").replace("\n", " ") for cell in row.cells]   # 取单元格文本并转义竖线
        lines.append("| " + " | ".join(cells) + " |")                   # 拼成一行
        if row_index == 0:                                              # 首行之后补分隔行
            lines.append("|" + "---|" * len(cells))                     # 分隔行，列数与表头一致
    return "\n".join(lines)                                             # 返回 Markdown 表格文本

# 抽取 DOCX。关键点：必须按文档正文里的真实顺序遍历，
# 因为 python-docx 的 document.paragraphs 会把表格跳过去，导致表格位置丢失。
def extract_docx(path):
    from docx import Document                       # 延迟导入，避免其他格式的用法被依赖问题连累
    from docx.oxml.ns import qn                     # 用于匹配 Word 的 XML 标签
    document = Document(path)                       # 打开文档
    body = document.element.body                    # 取正文根节点
    # 先建一次索引：XML 节点 → python-docx 对象。文档规模下 O(n) 建表，
    # 若在循环里逐个线性查找会退化成 O(n²)，几千段的书稿会明显变慢。
    paragraph_by_node = {paragraph._p: paragraph for paragraph in document.paragraphs}   # 段落索引
    table_by_node = {table._tbl: table for table in document.tables}                     # 表格索引
    parts = []                                      # 收集保序的内容块
    has_structure = False                           # 是否自带结构
    paragraph_count = 0                             # 统计段落数
    table_count = 0                                 # 统计表格数
    for child in body.iterchildren():               # 按正文里的真实顺序遍历子节点
        if child.tag == qn("w:p"):                  # 是段落
            paragraph = paragraph_by_node.get(child)   # 从索引里取，取不到就跳过
            if paragraph is None:                   # 极端情况下取不到
                continue                            # 继续下一个子节点，不让整篇失败
            text = paragraph.text.strip()           # 取段落文字
            level = spec_lib.docx_heading_level(paragraph)   # 公共判定：样式名不可靠时还会看大纲级别     # 判断是不是标题以及层级
            if level:                               # 是标题
                has_structure = True                # 标记自带结构
                parts.append("#" * min(level, 6) + " " + text)   # 转成 Markdown 标题
            elif text:                              # 普通正文且非空
                parts.append(text)                  # 原样保留
            if text:                                # 非空段落才计数
                paragraph_count += 1                # 段落计数加一
        elif child.tag == qn("w:tbl"):              # 是表格
            table = table_by_node.get(child)        # 从索引里取对应的表格
            if table is None:                       # 取不到
                continue                            # 跳过
            table_count += 1                        # 表格计数加一
            parts.append(table_to_markdown(table))  # 转成 Markdown 表格
            has_structure = True                    # 表格算作结构信息
    markdown = "\n\n".join(parts)                   # 用空行分隔各块，形成合法 Markdown
    note = f"DOCX 保序抽取（{paragraph_count} 段、{table_count} 表）"   # 生成说明
    return markdown, has_structure, note            # 返回结果

# 判断段落是不是标题：先看样式名，再看大纲级别
# 抽取 PDF 的文字层
def extract_pdf(path):
    import fitz                                     # PyMuPDF，用于读 PDF
    document = fitz.open(path)                      # 打开 PDF
    pages = []                                      # 收集每页文字
    for page in document:                           # 逐页遍历
        pages.append(page.get_text("text"))         # 按阅读顺序取纯文本
    document.close()                                # 关闭文档
    text = "\n\n".join(pages)                       # 页面之间用空行分隔
    note = f"PDF 文字层抽取（{len(pages)} 页），版式、图片、表格结构均已丢失"   # 说明会丢什么
    return text, False, note                        # PDF 永远视为「不带结构」

# 按扩展名分发到具体的抽取实现
def extract(path):
    if not os.path.exists(path):                    # 文件不存在
        raise FileNotFoundError(f"文件不存在：{path}")   # 抛出明确错误
    extension = os.path.splitext(path)[1].lower()   # 取小写扩展名
    if extension in TEXT_EXTENSIONS:                # 纯文本类
        return extract_text_file(path)              # 走文本抽取
    if extension == ".docx":                        # Word
        return extract_docx(path)                   # 走 DOCX 抽取
    if extension == ".pdf":                         # PDF
        return extract_pdf(path)                    # 走 PDF 抽取
    if extension == ".epub":                        # EPUB 输入输出均不支持，明确拒绝
        raise ValueError(
            "本 skill 不支持 EPUB，输入输出都不支持。EPUB 是流式排版产物，把它的 XHTML 抽出来重排，"
            "等于重做一本书，章节切分、脚注、图片归属都会乱。请提供 Word 或 Markdown 源文件。")
    raise ValueError(f"暂不支持的格式：{extension}。支持 .md / .txt / .docx / .pdf，或用 --text 直接粘贴文字。")

# 组装体检报告
def report(source, markdown, has_structure, note, output_path):
    lines = []                                                    # 逐行拼装
    lines.append(f"来源：{source}")                                 # 来源
    lines.append(f"抽取方式：{note}")                               # 抽取说明
    total = len(markdown.strip())                                 # 总字符数
    cjk = count_cjk(markdown)                                     # 中文字符数
    lines.append(f"篇幅：共 {total} 字符，其中中文 {cjk} 字")         # 篇幅统计
    paragraphs = [line for line in markdown.split("\n\n") if line.strip()]   # 按空行粗略分段
    lines.append(f"块数：约 {len(paragraphs)} 块（段落 / 标题 / 表格）")       # 块数统计
    lines.append(f"自带结构：{'有' if has_structure else '无'}")      # 结构判断
    if has_structure:                                             # 有结构时说清楚下一步
        lines.append("  → 源文件自带层级信息，结构识别层可直接采信，只需核对。")   # 指引
    else:                                                         # 无结构时给出警告
        lines.append("  → 源文件没有层级信息（没有标题样式、没有 Markdown 的 #、没有序号）。")
        lines.append("     必须走 infer_structure.py 推断层级，并把推断结果交给用户逐条确认，")
        lines.append("     不要直接当成正文生成，否则标题会退化成普通段落。")   # 明确后果
    if cjk == 0 and total > 0:                                    # 有内容但没中文
        lines.append("⚠️ 全文没有中文字符，请确认是不是抽取失败或文件本来就是西文。")   # 提醒
    if total == 0:                                                # 抽出来是空的
        lines.append("⚠️ 没有抽到任何文字。若是扫描件 PDF，需要先 OCR，本 skill 不做 OCR。")   # 提醒
    lines.append(f"草稿已写出：{output_path}")                       # 产物路径
    return "\n".join(lines)                                       # 返回报告文本

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="把任意输入统一抽取成保序的 Markdown 草稿")   # 构造解析器
    parser.add_argument("inputs", nargs="*", help="输入文件路径，可给多个（按给出顺序拼接）")     # 位置参数
    parser.add_argument("--text", help="直接给定文字（用户在聊天里粘贴的内容）")                 # 直接文字
    parser.add_argument("--output", help="草稿输出路径；默认写在第一个输入文件旁边")              # 输出路径
    args = parser.parse_args()                                                               # 解析参数

    if not args.inputs and not args.text:                       # 既没文件也没文字
        print("必须给出输入文件，或用 --text 直接粘贴文字。", file=sys.stderr)   # 提示用法
        return 2                                                # 返回用法错误码

    chunks = []                                                 # 收集各来源的草稿
    sources = []                                                # 收集来源说明
    flags = []                                                  # 收集「是否自带结构」
    notes = []                                                  # 收集抽取方式说明

    if args.text:                                               # 用户直接粘了文字
        chunks.append(args.text.strip())                        # 原样收下
        sources.append("聊天中直接粘贴的文字")                    # 记录来源
        flags.append(markdown_has_structure(args.text))         # 判断自带结构
        notes.append("直接取自输入文字")                          # 记录方式

    for path in args.inputs:                                    # 逐个处理文件
        try:                                                    # 抽取可能失败
            markdown, has_structure, note = extract(path)       # 执行抽取
        except Exception as error:                              # 抽取异常
            print(f"抽取失败：{error}", file=sys.stderr)          # 打印错误
            return 1                                            # 返回失败码
        chunks.append(markdown)                                 # 收集草稿
        sources.append(os.path.abspath(path))                   # 记录绝对路径
        flags.append(has_structure)                             # 记录结构标记
        notes.append(note)                                      # 记录方式

    markdown = "\n\n".join(chunk for chunk in chunks if chunk.strip())   # 拼接所有来源
    has_structure = any(flags)                                          # 任一来源有结构就算有

    if args.output:                                                     # 用户指定了输出路径
        output_path = args.output                                       # 用它
    else:                                                               # 否则自动命名
        base = os.path.splitext(os.path.basename(args.inputs[0]))[0] if args.inputs else "粘贴文字"   # 基准名
        # 没有输入文件时（纯 --text 模式）写到系统临时目录，避免把草稿落进调用者的项目目录里
        # 默认落在源文件同级的 build/ 子目录：抽取稿是中间产物，不该堆在用户的目录里。
        output_dir = spec_lib.staging_dir(args.inputs[0]) if args.inputs else tempfile.gettempdir()   # 基准目录
        os.makedirs(output_dir, exist_ok=True)                          # 目录不存在就建出来
        output_path = os.path.join(output_dir, base + ".抽取稿.md")       # 输出路径

    io.open(output_path, "w", encoding="utf-8").write(markdown + "\n")   # 写出草稿

    print("=" * 66)                                                     # 打印分隔线
    for index, source in enumerate(sources):                            # 逐个来源打印
        print(report(source, chunks[index], flags[index], notes[index], output_path))   # 打印该来源的报告
        print("-" * 66)                                                 # 打印分隔线

    return 0                                                            # 返回成功码

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                            # 用返回值作为退出码

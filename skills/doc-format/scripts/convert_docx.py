#!/usr/bin/env python3
# 本脚本把「用户已经有的 DOCX」重新套上指定排版规格，内容一字不动，只改样式。
#
# 为什么需要它：
#   用户手上的 Word 文件往往是自己或别人随手排的 —— 没有首行缩进、表格没居中、字号五花八门。
#   以前只能让用户把内容重新导成 Markdown 再生成，等于把已有文件扔掉重做。
#   本脚本直接在原文件上「换衣服」：段落文字、表格内容、图片全部保留，只重写样式。
#
# 注意：DOCX 里的直接格式（direct formatting）优先级高于样式，所以不能只改样式表，
#      必须逐个段落、逐个 run 把字体字号写进去，否则会出现「样式改了但看起来没变」。
#
# 用法：
#   python3 scripts/convert_docx.py --input 旧稿.docx --spec typography.spec.yaml --output 新稿.docx
#   python3 scripts/convert_docx.py --input 旧稿.docx --spec typography.spec.yaml --output 新稿.docx --report

import argparse   # 用于解析命令行参数
import os         # 用于路径处理
import sys        # 用于控制退出码与错误输出

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # 把 scripts 目录加入模块路径
import spec_lib   # 导入公共库
import build_docx  # 复用 build_docx 里已经写好并验证过的样式函数，避免重复实现

from docx import Document                    # python-docx 的文档对象
from docx.shared import Pt, RGBColor         # 长度与颜色单位
from docx.oxml.ns import qn                  # 用于拼 Word 的命名空间标签
from docx.oxml import OxmlElement            # 用于创建自定义 XML 节点

# 把整段文字里的所有 run 统一刷成目标样式。
# 之所以要逐个 run 处理：Word 里同一段的不同文字可能各带一套直接格式，只改段落样式盖不住。
def restyle_paragraph(paragraph, east_asian, latin, size_pt, bold, color_hex, spec):
    paragraph_cfg = spec.get("paragraph") or {}                                 # 取正文段落配置
    for run in paragraph.runs:                                                  # 遍历段落里的每个 run
        build_docx.style_run(run, east_asian, latin, size_pt, bold)             # 复用 build_docx 的 run 样式函数
        try:                                                                    # 颜色值可能非法
            run.font.color.rgb = RGBColor.from_string(color_hex.upper())        # 强制写入颜色，清掉继承来的主题色
        except Exception:                                                       # 解析失败时
            pass                                                                # 保持原有颜色，不阻断流程
    paragraph_format = paragraph.paragraph_format                               # 取段落格式对象
    mode = paragraph_cfg.get("line_spacing_mode", "multiple")                   # 取行距模式
    if mode == "exact" and paragraph_cfg.get("line_spacing_pt"):                # 固定值行距
        build_docx.set_line_spacing(paragraph, "exact", pt=paragraph_cfg["line_spacing_pt"])   # 复用行距函数
    elif paragraph_cfg.get("line_spacing_value"):                               # 倍数行距
        build_docx.set_line_spacing(paragraph, "multiple", value=paragraph_cfg["line_spacing_value"])   # 复用行距函数
    if paragraph_cfg.get("alignment") in build_docx.ALIGN_MAP:                  # 若配置了对齐方式
        paragraph_format.alignment = build_docx.ALIGN_MAP[paragraph_cfg["alignment"]]   # 写入对齐
    # 首行缩进：位置指针（paragraph_format）与底层 XML 都要写，才能保证 Word 与 LibreOffice 都认
    chars = paragraph_cfg.get("first_line_indent_chars")                        # 取首行缩进字符数
    if chars:                                                                   # 若要求缩进
        build_docx.set_first_line_indent_chars(paragraph, chars)                # 复用缩进函数
    else:                                                                       # 不要求缩进
        paragraph_format.first_line_indent = Pt(0)                              # 明确清零，清掉原有缩进
        ppr = paragraph._p.get_or_add_pPr()                                     # 取段落属性节点
        ind = ppr.find(qn("w:ind"))                                             # 查找缩进节点
        if ind is not None:                                                     # 若存在
            ppr.remove(ind)                                                     # 直接删掉，避免残留的字符级缩进生效

# 清理标题段落的缩进：标题不应该有首行缩进，这是最常见的「看着别扭」来源
# 设置标题的缩进：默认清零（清掉从正文继承来的缩进），
# 公文类预设要求层次标题「左空二字」时，按 first_line_indent_chars 写入字符级缩进
def clear_heading_indent(paragraph, indent_chars=0):
    paragraph.paragraph_format.first_line_indent = Pt(0)                        # 先清掉长度级缩进，避免与字符级缩进叠加
    ppr = paragraph._p.get_or_add_pPr()                                         # 取段落属性节点
    ind = ppr.find(qn("w:ind"))                                                 # 查找缩进节点
    if ind is None:                                                             # 若不存在
        ind = OxmlElement("w:ind")                                              # 创建缩进节点
        ppr.append(ind)                                                         # 挂到段落属性下
    ind.set(qn("w:firstLineChars"), str(int(float(indent_chars or 0) * 100)))    # 写入字符级缩进（百分之一字符）

# 重排所有表格：套上三线表或网格线，表头加粗，并按需应用规格声明的对齐（未声明就不干预）
def restyle_tables(document, spec, east_asian, latin, size_pt):
    cfg = spec.get("figures_tables") or {}                                      # 取图表配置
    table_count = 0                                                             # 统计处理的表格数
    cell_count = 0                                                              # 统计处理的单元格数
    column_from_source = 0                                                 # 沿用原文档对齐的列数（须在循环外初始化：文档无表格时循环不执行，仍要有定义）
    for table in document.tables:                                               # 遍历文档里所有表格
        table_count += 1                                                        # 表格计数加一
        # 表格整体位置同样不预设：规格卡显式声明才覆盖，否则保留原稿已有的位置
        table_align = cfg.get("table_alignment") or ""                          # 规格卡要求的表格位置
        if table_align in build_docx.TABLE_ALIGN_MAP:                           # 只有明确要求才改
            table.alignment = build_docx.TABLE_ALIGN_MAP[table_align]           # 应用表格整体对齐
        # 表格线型的合法取值收在公共库里，与 build_docx、spec_check 共用一份，避免各认各的。
        style_name, style_note = spec_lib.resolve_table_style(cfg.get("table_style"))   # 解析线型
        if style_note:                                                          # 规格里的写法有问题
            print(f"⚠ 表格：{style_note}")                                        # 当面说清，不静默兜底
        build_docx.set_table_borders(table, style_name)                          # 套用边框
        # 三线表那条「表头线」不在表格边框里，得单独给表头行加。
        # 这里以前是漏的：只调了 set_table_borders，三线表就只剩最上面和最下面两条线，
        # 中间那条分隔线没有，重排出来的表格比正常三线表还寡淡（实测）。
        if style_name == "three_line" and len(table.rows) > 0:                   # 三线表且有表头行
            build_docx.set_row_bottom_border(table.rows[0])                      # 给表头行补下边框
        # 逐列决定对齐，整列统一。判定规则收在 spec_lib.resolve_column_alignments，
        # 与 build_docx / build_html 共用一份，避免同一份规格在三个脚本里算出三种结果。
        # 本脚本多出来的一档是「原稿的态度」：原文档这一列显式设过同一个对齐，就先沿用它，
        # 它会被当成公共判定的「源文件对齐」，优先级最高 —— 用户原来的排版意图最不该被覆盖。
        data_rows = list(table.rows)[1:]                                        # 数据行（不含表头）
        column_count = max((len(row.cells) for row in table.rows), default=0)    # 表格的最大列数
        source_aligns = []                                                      # 原稿每列已有的对齐（供公共判定优先采用）
        for column_index in range(column_count):                                # 逐列读原稿
            cells = [row.cells[column_index] for row in data_rows if column_index < len(row.cells)]   # 该列全部数据格
            existing = {cell.paragraphs[0].paragraph_format.alignment for cell in cells if cell.text.strip()}   # 原文档里这一列显式设过的对齐
            if len(existing) == 1 and None not in existing:                     # 原文档整列显式设过同一个对齐
                source_aligns.append(build_docx.REVERSE_ALIGN.get(existing.pop(), ""))   # 反查成规格里的对齐名
                column_from_source += 1                                        # 计数：这一列沿用原文档
            else:                                                             # 原稿没有明确态度
                source_aligns.append("")                                      # 交给规格卡的声明去决定
        rows_for_align = [[cell.text for cell in row.cells] for row in table.rows]   # 表格内容（第 1 行为表头，与公共判定的约定一致）
        column_align = spec_lib.resolve_column_alignments(rows_for_align, source_aligns, cfg)   # 公共判定：每列该用什么对齐
        for row_index, row in enumerate(table.rows):                            # 遍历每一行
            is_header = row_index == 0                                          # 第一行当表头
            for column_index, cell in enumerate(row.cells):                     # 遍历每个单元格
                cell_count += 1                                                 # 单元格计数加一
                data_align = column_align[column_index] if column_index < len(column_align) else ""   # 该列统一的对齐方式，空串表示不干预
                for paragraph in cell.paragraphs:                               # 遍历单元格内的段落
                    if is_header:                                               # 表头行
                        # 表头优先跟随该列已有/规格指定的对齐，其次看规格卡显式声明的 header_alignment，都没有则不动
                        header_align = data_align or (cfg.get("header_alignment") or "")   # 表头对齐，空串表示不干预
                        target_align = build_docx.ALIGN_MAP.get(header_align)    # 换算成 Word 的对齐枚举，空串会得到 None
                        target_bold = True                                      # 表头加粗
                    else:                                                       # 内容行
                        target_align = build_docx.ALIGN_MAP.get(data_align)      # 用该列统一的对齐方式，空串会得到 None
                        target_bold = False                                     # 内容不加粗
                    if target_align is not None:                                # 若对齐可用
                        paragraph.paragraph_format.alignment = target_align      # 写入对齐
                    paragraph.paragraph_format.first_line_indent = Pt(0)        # 表格内不缩进
                    for run in paragraph.runs:                                  # 遍历 run
                        build_docx.style_run(run, east_asian, latin, size_pt, target_bold)   # 统一字体字号
    return table_count, cell_count, column_from_source                          # 返回统计结果（含沿用原文档对齐的列数）

# 主流程：读规格、读原文档、逐层刷样式、另存为新文件
def convert(spec_path, input_path, output_path, show_report):
    spec = spec_lib.load_spec(spec_path)                                        # 读取规格卡
    font_block = spec_lib.font_block_message(spec)                              # 检查规格要求的字体本机是否都有
    if font_block:                                                              # 有缺失字体
        print(font_block, file=sys.stderr)                                      # 打印缺字体说明
        return 4                                                                # 用独立退出码 4 表示「字体缺失」
    document = Document(input_path)                                             # 打开用户的现有文档
    body_cfg = (spec.get("fonts") or {}).get("body") or {}                       # 取正文字体配置
    east_asian = spec_lib.resolve_font(body_cfg.get("east_asian", "宋体"), body_cfg.get("resolved"))   # 解析中文字体
    latin = body_cfg.get("latin") or "Times New Roman"                           # 取西文字体
    body_size = float(body_cfg.get("size_pt") or 10.5)                           # 取正文字号
    heading_cfg = spec.get("headings") or {}                                     # 取标题配置

    build_docx.setup_page(document, spec)                                       # 重设纸张与页边距
    build_docx.setup_body_style(document, spec)                                 # 重设正文默认样式
    build_docx.setup_heading_styles(document, spec)                             # 重设各级标题样式
    # 页眉与页码共用「奇偶页不同」这一个文档级开关，所以先统一判断一次再分别写入，
    # 否则出现「页眉要奇偶不同、页码只写一套」时，偶数页页码会整片消失。
    odd_even = build_docx.needs_odd_even(spec)                                  # 判断整篇是否要分单双页
    if odd_even:                                                                # 需要分单双页
        document.settings.odd_and_even_pages_header_footer = True               # 打开文档级开关
    build_docx.setup_footer(document, spec, odd_even)                           # 重设页码
    build_docx.setup_header(document, spec, odd_even)                           # 重设页眉（若规格要求）

    body_count = 0                                                              # 正文段落计数
    heading_count = 0                                                           # 标题段落计数
    for paragraph in document.paragraphs:                                       # 遍历所有段落
        level = spec_lib.docx_heading_level(paragraph)                          # 判断是不是标题（公共判定）
        cfg = spec_lib.resolve_heading(heading_cfg, level) if level else {}      # 用统一解析取该级配置（兼容 chapter/doc_title 等命名）
        if cfg:                                                                 # 命中已配置的标题级别
            size_pt = float(cfg.get("size_pt") or body_size)                    # 标题字号，缺省跟随正文
            heading_east = spec_lib.resolve_font(cfg.get("east_asian", east_asian), cfg.get("resolved"))   # 标题中文字体
            heading_latin = cfg.get("latin") or latin                           # 标题西文字体
            color_hex = str(cfg.get("color", "000000")).lstrip("#")              # 标题颜色，默认纯黑
            restyle_paragraph(paragraph, heading_east, heading_latin, size_pt, bool(cfg.get("bold", True)), color_hex, spec)   # 套用标题样式
            clear_heading_indent(paragraph, cfg.get("first_line_indent_chars"))   # 按该级标题的缩进要求设置
            if cfg.get("alignment") in build_docx.ALIGN_MAP:                    # 若标题指定对齐
                paragraph.paragraph_format.alignment = build_docx.ALIGN_MAP[cfg["alignment"]]   # 写入对齐
            if cfg.get("page_break_before"):                                    # 若要求另起页
                paragraph.paragraph_format.page_break_before = True             # 设置段前分页
            heading_count += 1                                                  # 标题计数加一
        else:                                                                   # 其余按正文处理
            if not paragraph.text.strip():                                      # 空段落跳过，避免给空行也加缩进
                continue                                                        # 继续下一段
            restyle_paragraph(paragraph, east_asian, latin, body_size, False, "000000", spec)   # 套用正文样式
            body_count += 1                                                     # 正文计数加一

    table_count, cell_count, column_from_source = restyle_tables(document, spec, east_asian, latin, body_size)   # 重排表格

    output_dir = os.path.dirname(os.path.abspath(output_path)) or "."            # 取输出目录
    os.makedirs(output_dir, exist_ok=True)                                      # 确保目录存在
    document.save(output_path)                                                  # 另存为新文件，原文件不动

    print(f"已重排并另存：{output_path}")                                         # 打印产物路径
    print(f"  正文段落 {body_count} 个，标题 {heading_count} 个")                  # 打印段落统计
    print(f"  表格 {table_count} 个，单元格 {cell_count} 个")                      # 打印表格统计
    if table_count:                                                             # 有表格时说明对齐来源
        # 对齐不再由 skill 预设，所以要区分「沿用了原稿」「按规格显式要求设过」「完全没动」三种情况
        cfg_figures = spec.get("figures_tables") or {}                           # 取图表规范段
        declared = any(cfg_figures.get(key) for key in
                       ("header_alignment", "text_column_alignment",
                        "number_column_alignment", "table_alignment"))   # 规格是否显式声明过任何一项对齐
        if column_from_source:                                                   # 有条列沿用了原文档
            print(f"  表格对齐：沿用原文档 {column_from_source} 列")                 # 打印沿用情况
        elif declared:                                                           # 规格显式要求过对齐
            print("  表格对齐：按规格卡的显式要求设置")                              # 打印按规格设置
        else:                                                                    # 规格没要求、原稿也没设
            print("  表格对齐：未设置（规格未声明、原稿也没有，保持默认不干预）")        # 打印不干预
    print(f"  正文字体：{east_asian} / {latin}，字号 {body_size:g}pt")             # 打印实际使用的字体
    if not heading_count:                                                       # 一个标题都没识别到
        print("  ⚠️ 没有识别到任何标题。原文件的标题可能不是用 Word 内置「标题 1/2/3」样式写的，")
        print("     而是手动加粗放大的普通段落。这种情况标题样式不会生效，需要先人工调整源文件。")
    if (spec.get("masthead") or {}).get("enabled"):                              # 规格里启用了红头
        print("  ⚠️ 本脚本只改样式，不会生成版头（红头、发文字号、分隔线）—— 原稿里没有的段落它变不出来。")
        print("     要红头文件请走重做路径：extract_source.py 抽草稿 → infer_structure.py 推断层级 → build_docx.py 生成。")
    print("提示：原文件未被修改。请用 render_preview.py 渲染成图片目视核对，或跑 verify_output.py 合规校验。")
    if show_report:                                                             # 若要求打印小结
        print("说明：本脚本只改样式，不改文字。错别字检查请用 typo_check.py。")
    return 0                                                                    # 返回成功码

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="把现有 DOCX 重新套上排版规格（内容不变，只改样式）")   # 构造解析器
    parser.add_argument("--input", required=True, help="输入的 DOCX 路径")           # 输入文件
    parser.add_argument("--spec", required=True, help="规格卡 YAML 路径")            # 规格卡
    parser.add_argument("--output", required=True, help="输出的 DOCX 路径（必须是新文件）")   # 输出文件
    parser.add_argument("--report", action="store_true", help="额外打印处理说明")      # 报告开关
    args = parser.parse_args()                                                    # 解析参数
    if os.path.abspath(args.input) == os.path.abspath(args.output):               # 拒绝覆盖原文件
        print("输出路径不能与输入路径相同。本脚本只写新文件，不覆盖原稿。", file=sys.stderr)   # 打印错误
        return 2                                                                  # 返回用法错误码
    try:                                                                          # 捕获处理异常
        return convert(args.spec, args.input, args.output, args.report)            # 执行转换
    except Exception as error:                                                     # 任何异常
        print(f"重排失败：{error}", file=sys.stderr)                                # 打印错误
        return 1                                                                   # 返回失败码

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                                      # 用返回值作为退出码

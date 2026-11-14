#!/usr/bin/env python3
# 本脚本对生成后的真实产物逐条核对规格是否落实，输出「已落实 / 跳过 / 失败」三类结果。
# 核对的是实际文件内容，不是代码意图。用法：
#   python3 scripts/verify_output.py --spec typography.spec.yaml --docx book.docx
#   python3 scripts/verify_output.py --spec typography.spec.yaml --pdf  book.pdf
#   python3 scripts/verify_output.py --spec typography.spec.yaml --html article.html

import argparse   # 用于解析命令行参数
import os         # 用于拼接模块路径
import re         # 用于正则检索
import sys        # 用于控制退出码
import zipfile    # 用于解包 DOCX（DOCX 本质是 zip）

# 解析 OOXML 需要按命名空间取节点。verify_docx 刻意走裸 XML 而不依赖 python-docx，
# 所以这里直接用 lxml（本项目其它脚本已在用，不新增依赖）。
from lxml import etree   # XML 解析

# WordprocessingML 命名空间前缀，用于拼 XPath
W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

# 把 scripts 目录加入模块路径，保证能导入公共库
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import spec_lib   # 导入本项目的公共库
import build_html   # 复用 HTML 生成脚本的参数解析，保证校验默认值与生成时一致，不会各写一套

# 解析正文 XML，取出里面全部表格节点（供列宽核对使用）
def parse_tables(document_xml):
    # lxml 不接受「带 encoding 声明的 unicode 字符串」（会直接抛 ValueError），
    # 而 read_zip_member 读出来的是已经 .decode() 过的 str —— 必须先转回字节。
    # 这个坑曾经让表格核对静默失效：异常被 except 吞掉、返回空列表，
    # 报告上什么也不显示，看起来像「表格没问题」，其实根本没查。
    if isinstance(document_xml, str):                      # 调用方给的是已解码的字符串
        document_xml = document_xml.encode("utf-8")        # 转回字节
    try:                                                   # XML 可能不成形
        root = etree.fromstring(document_xml)              # 解析
    except Exception as error:                             # 解析失败
        # 不再静默吞掉：说清楚为什么没查成，否则「没报错」会被误读成「没问题」
        print(f"提示：表格列宽未能核对（正文 XML 解析失败：{error}）", file=sys.stderr)   # 打到标准错误
        return []                                          # 拿不到表格，返回空
    return root.findall(".//w:tbl", W_NS)                  # 找出所有表格节点

# 取一张表格的列宽（单位 twips），按 tblGrid 里的 gridCol 顺序返回。
# 为什么以 tblGrid 为准：Word 与 LibreOffice 在固定布局下都看它，单元格宽度只是参考值。
def table_grid_widths(table):
    grid = table.find("w:tblGrid", W_NS)                   # 取表格网格
    if grid is None:                                       # 没有网格
        return []                                          # 返回空
    widths = []                                            # 结果
    for col in grid.findall("w:gridCol", W_NS):            # 逐个网格列
        try:                                               # 宽度值可能缺失或非法
            widths.append(int(col.get(f"{{{W_NS['w']}}}w") or 0))   # 记录宽度
        except ValueError:                                 # 值不是数字
            widths.append(0)                               # 记为 0
    return widths                                          # 返回

# 数出正文里指定层级的标题有多少个（level=2 对应 Word 的「标题 2」，样式 id 为 Heading2）。
# 为什么要专门数一遍：规格要求「章从奇数页起」，但如果稿子里根本没有章标题，就没有任何东西可设置，
# 这时应该记「跳过」；早先没数，直接判「没找到 oddPage 分节符 = 失败」，
# 把一份本来合格的稿子判成了缺陷（实测在「极端稿-无标题」上复现）。
# 解析不了时返回 None（表示「不知道」），绝不能返回 0 —— 那会把「没查成」伪装成「确实没有」。
def count_heading_paragraphs(document_xml, level):
    if isinstance(document_xml, str):                          # 调用方给的是已解码字符串
        document_xml = document_xml.encode("utf-8")            # 转回字节，lxml 才肯解析
    try:                                                       # XML 可能不成形
        root = etree.fromstring(document_xml)                  # 解析正文
    except Exception as error:                                 # 解析失败
        print(f"提示：标题数量未能核对（正文 XML 解析失败：{error}）", file=sys.stderr)   # 说明为什么没查成
        return None                                            # 返回「不知道」
    wanted = f"Heading{level}"                                 # 目标样式 id
    return sum(1 for style in root.iter(f"{{{W_NS['w']}}}pStyle")   # 遍历全部段落样式引用
               if (style.get(f"{{{W_NS['w']}}}val") or "") == wanted)   # 命中目标样式就计数

# 取正文里全部标题段落的「级别 + 文字」。级别取自 w:pStyle（Heading1 / Heading2 …）。
# 用于标题折行核对：折行判断只需要文字、字号与版心宽度，字号从规格卡取，不必读样式表。
def heading_paragraph_list(document_xml):
    if isinstance(document_xml, str):                      # 调用方给的是已解码字符串
        document_xml = document_xml.encode("utf-8")        # 转回字节，lxml 才肯解析
    try:                                                   # XML 可能不成形
        root = etree.fromstring(document_xml)              # 解析正文
    except Exception:                                      # 解析失败
        return []                                          # 返回空，调用方按「没查成」处理
    result = []                                            # 结果列表
    for paragraph in root.iter(f"{{{W_NS['w']}}}p"):        # 遍历全部段落
        style = paragraph.find(f"w:pPr/w:pStyle", W_NS)     # 取段落样式引用
        if style is None:                                  # 没有样式
            continue                                       # 不是标题
        value = style.get(f"{{{W_NS['w']}}}val") or ""      # 样式 id
        if not value.startswith("Heading"):                # 不是内置标题样式
            continue                                       # 跳过
        try:                                               # 样式 id 后面的数字就是层级
            level = int(value.replace("Heading", ""))       # 取出级别
        except ValueError:                                 # 取不出来
            continue                                       # 跳过
        # 段落文字必须按「文档顺序」重拼：只看 w:t 节点会漏掉换行与制表符。
        # 生成端按 §7.3.1 给公文标题做的人工断行写的是 <w:br/>（不是文字），
        # 漏掉它就等于把断好的两行当成一整行，折行核对会对已经排好的标题误报。
        parts = []                                         # 段落文字片段
        for node in paragraph.iter():                      # 按文档顺序遍历全部子节点
            tag = node.tag.rsplit("}", 1)[-1]              # 取标签名（去掉命名空间花括号）
            if tag == "t":                                 # 文本节点
                parts.append(node.text or "")              # 收集文字
            elif tag in ("br", "cr"):                      # 换行 / 回车
                parts.append("\n")                         # 记成换行，人工断行的分界靠它
            elif tag == "tab":                             # 制表符
                parts.append("\t")                         # 记成制表符
        text = "".join(parts)                              # 拼成整段文字
        if text.strip():                                   # 空标题不计
            result.append((level, text))                   # 记下来
    return result                                          # 返回

# 数一张表格共有多少行、其中多少行写了「禁止跨页断行」（w:cantSplit）。
# 为什么值得单独核对：跨页表格出现「有框线、没有文字」的空行，根因就是行没设 cantSplit，
# 行被切在页边界上。生成端写了不等于文件里真有，必须回到成品里数一遍。
# 从成品的 XML 里量出这张表的线型事实，而不是相信生成代码说过什么。
# 为什么非要量：表格线型是「登记了没实现」的重灾区 —— 实测出现过
# 「规格写全框线、成品还是三线表」「三线表少了表头那条线」「改了线型根本没生效」，
# 而当时的报告全是绿的。只有从文件里量出来，写没写进去骗不了人。
def table_border_facts(table):
    """返回 (是否全框线, 表头有没有下方那条线, 自带的单元格竖线数)。"""
    borders = table.find("w:tblPr/w:tblBorders", W_NS)          # 取表格级的边框集合
    present = {}                                               # 六条边各自的线型
    if borders is not None:                                    # 有边框集合
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):   # 逐条边看
            node = borders.find(f"w:{edge}", W_NS)             # 取该边节点
            present[edge] = (node.get(f"{{{W_NS['w']}}}val") or "") if node is not None else ""   # 记下线型，没有就记空串
    # 四条边都不为空、也不是 none，才算真的全框线
    grid_like = all(present.get(edge) not in ("", "none", "nil") for edge in ("left", "right", "insideH", "insideV"))
    rows = table.findall("w:tr", W_NS)                         # 取表格的所有行
    header_bottom = False                                      # 表头底下有没有那条线
    cell_verticals = 0                                         # 单元格自带的竖线数（会盖过表格级线型）
    for row_index, row in enumerate(rows):                     # 逐行看
        for cell in row.findall("w:tc", W_NS):                 # 逐个单元格看
            cell_borders = cell.find("w:tcPr/w:tcBorders", W_NS)   # 取单元格自己的边框
            if cell_borders is None:                           # 没有就跳过
                continue                                       # 继续下一个
            for edge in ("left", "right"):                     # 只看左右两条竖线
                node = cell_borders.find(f"w:{edge}", W_NS)    # 取该边
                if node is not None and (node.get(f"{{{W_NS['w']}}}val") or "") not in ("", "none", "nil"):
                    cell_verticals += 1                        # 记一笔
            if row_index != 0:                                 # 表头线只看第一行
                continue                                       # 其余行不用看下边框
            bottom = cell_borders.find("w:bottom", W_NS)       # 取表头单元格的下边框
            if bottom is not None and (bottom.get(f"{{{W_NS['w']}}}val") or "") not in ("", "none", "nil"):
                header_bottom = True                           # 记下「有表头线」
    return grid_like, header_bottom, cell_verticals            # 返回三件事实

def table_row_split_stats(table):
    total = 0                                              # 总行数
    protected = 0                                          # 写了 cantSplit 的行数
    for row in table.findall("w:tr", W_NS):                # 逐行核对
        total += 1                                         # 计数
        trpr = row.find("w:trPr", W_NS)                    # 取行属性
        if trpr is not None and trpr.find("w:cantSplit", W_NS) is not None:   # 有禁止断行设置
            protected += 1                                 # 计数
    return total, protected                                # 返回

# 按成品里真实写着的列宽，组装与 spec_lib.describe_table_fit 同结构的信息字典。
#
# 为什么不在校验里直接调 plan_table_columns：那是「算该分多宽」的算法，
# 而校验要做的是「量已经写进文件的宽度够不够」—— 用同一份措辞、不同的数据来源，
# 才不会出现「生成说没问题、校验说有折行」这种自相矛盾。
def measured_table_fit(table, widths_twips, cm_per_unit, padding_cm, content_avail_cm):
    rows = table_all_cells(table)                          # 取整张表的全部单元格文字（含表头行）
    if not rows:                                           # 空表
        return None                                        # 不报
    columns = len(widths_twips)                            # 实际列数
    header_wrap = []                                       # 表头会折行的列
    data_wrap = []                                         # 数据会折行的列
    for col_index in range(columns):                       # 逐列核对
        have_cm = widths_twips[col_index] / 567.0 - padding_cm   # 这一列扣掉内边距后能放文字的宽度
        units = have_cm / cm_per_unit if cm_per_unit else 0      # 换算成「多少个半汉字宽」
        name = rows[0][col_index] if col_index < len(rows[0]) else f"第 {col_index + 1} 列"   # 列名
        if units > 0 and spec_lib.wrapped_lines(name, units) > 1:   # 表头折了
            header_wrap.append((name, spec_lib.wrapped_lines(name, units)))   # 记下折成几行
        worst_text, worst_lines = "", 1                    # 该列折得最惨的数据
        for row_data in rows[1:]:                          # 逐行看数据
            if col_index >= len(row_data) or units <= 0:   # 这行没有这一列，或宽度算不出来
                continue                                   # 跳过
            lines = spec_lib.wrapped_lines(row_data[col_index], units)   # 这一格折成几行
            if lines > worst_lines:                        # 更惨
                worst_text, worst_lines = row_data[col_index], lines   # 记下来
        if worst_lines > 1:                                # 有数据折行
            data_wrap.append((name, worst_text, worst_lines))   # 记下
    if not header_wrap and not data_wrap:                  # 一格都不折
        return None                                        # 不报
    board_cm = content_avail_cm or sum(widths_twips) / 567.0   # 版心宽度（取不到就用表格宽度）
    # 建议字号要一并算出来，措辞才能与生成端完全一致。
    # 实测踩过：这条信息最早只在生成端算，校验端的措辞停在旧版「可选：调小字号」，
    # 同一张表生成时说「设为 7.5pt 就不折行」、校验时说「可以调小字号」，用户不知道该信哪条。
    # 反推当前字号：一个半汉字宽 = 0.01764cm × 字号，这是 unit_to_cm 的逆运算。
    current_size = (cm_per_unit / 0.01764) if cm_per_unit else 0.0   # 当前表格字号
    return {                                               # 组装成与生成端同构的字典
        "列数": columns,                                   # 列数
        "表头折行": header_wrap,                           # 表头折行的列
        "数据折行": data_wrap,                             # 数据折行的列
        "表头所需_cm": round(sum(spec_lib.display_width(rows[0][i] if i < len(rows[0]) else "")
                                 for i in range(columns)) * cm_per_unit + padding_cm * columns, 2),   # 表头排成一行需要多宽
        "版心可用_cm": round(sum(widths_twips) / 567.0 - padding_cm * columns, 2),   # 表格实际给了多少可用宽度
        "版心_cm": round(board_cm, 2),                     # 版心宽度
        "建议字号": spec_lib.suggest_table_size(rows, board_cm, current_size) if current_size else None,   # 换成多少号字最整齐
    }

# 取一张表格的全部单元格文字，按行返回（第一行是表头）。
def table_all_cells(table):
    rows = []                                              # 结果
    for row in table.findall("w:tr", W_NS):                # 逐行
        rows.append(["".join(node.text or "" for node in cell.iter(f"{{{W_NS['w']}}}t"))
                     for cell in row.findall("w:tc", W_NS)])   # 把行内每个单元格的文字拼起来
    return rows                                            # 返回

# 按文档顺序找出「表格与它紧邻的题注」的先后关系。
# 返回 [(表序号, 题注文字, "above" / "below")]，只收录真正挨着表格的题注段。
def caption_positions(document_xml):
    if isinstance(document_xml, str):                      # 调用方给的是已解码字符串
        document_xml = document_xml.encode("utf-8")        # 转回字节
    try:                                                   # XML 可能不成形
        root = etree.fromstring(document_xml)              # 解析正文
    except Exception:                                      # 解析失败
        return []                                          # 返回空
    body = root.find(".//w:body", W_NS)                     # 取正文节点
    if body is None:                                       # 没有正文
        return []                                          # 返回空
    def text_of(node):                                     # 取一个段落的文字
        return "".join(t.text or "" for t in node.iter(f"{{{W_NS['w']}}}t"))   # 拼接全部文本节点
    children = [child for child in body
                if child.tag in (f"{{{W_NS['w']}}}p", f"{{{W_NS['w']}}}tbl")]   # 只看段落与表格，按文档顺序
    result = []                                            # 结果
    table_number = 0                                       # 表格计数
    for index, child in enumerate(children):               # 逐个节点
        if child.tag != f"{{{W_NS['w']}}}tbl":              # 不是表格
            continue                                       # 跳过
        table_number += 1                                  # 表格序号 +1
        above_text, below_text = "", ""                    # 紧邻题注的文字
        if index > 0 and children[index - 1].tag == f"{{{W_NS['w']}}}p":   # 前一个节点是段落
            if spec_lib.is_caption_text(text_of(children[index - 1])):      # 而且是题注
                above_text = text_of(children[index - 1])  # 记下「表上方」的题注
        if index + 1 < len(children) and children[index + 1].tag == f"{{{W_NS['w']}}}p":   # 后一个节点是段落
            if spec_lib.is_caption_text(text_of(children[index + 1])):      # 而且是题注
                below_text = text_of(children[index + 1])  # 记下「表下方」的题注
        for text, where in ((above_text, "above"), (below_text, "below")):   # 两种情况分别登记
            if text:                                       # 确实找到题注
                result.append((table_number, text.strip(), where))   # 记录
    return result                                          # 返回

# 按页面参数算出实际版心宽度（厘米）。页面宽度或左右边距缺失时返回 None（表示算不出来）。
# 核对成品纸张尺寸是否等于规格声明的尺寸。
# 为什么必须单独核对：`page.size: A4` 曾经是一个没人读的字段，生成端静默落到
# python-docx 默认模板的 Letter（215.9×279.4mm），而报告上「纸张」这一项根本不出现 ——
# 属于「没落实也不报错」里最隐蔽的一类。现在两端都走 spec_lib.page_size_mm，口径唯一。
# units 给出「毫米/点」的换算方式（DOCX 存 twips，PDF 存点）。
def check_page_size(report, spec, actual_mm):
    expected_width, expected_height = spec_lib.page_size_mm(spec)   # 规格声明的纸张尺寸
    if not (expected_width and expected_height):                    # 规格没声明尺寸
        report.skip("规格卡未声明纸张尺寸，无法核对成品幅面")            # 记跳过
        return                                                      # 不再往下比
    if actual_mm is None:                                           # 成品里读不出尺寸
        report.fail("无法从成品中读出纸张尺寸，幅面是否落实未知")        # 记失败
        return                                                      # 不再往下比
    width_mm, height_mm = actual_mm                                 # 解开成品的实测尺寸
    # 容差 0.5mm：毫米与 twips/点之间来回换算会有零点几毫米的取整误差，不算缺陷
    if abs(width_mm - expected_width) <= 0.5 and abs(height_mm - expected_height) <= 0.5:
        report.ok(f"纸张尺寸已落实：{expected_width:g}mm × {expected_height:g}mm")   # 记录通过
    else:                                                           # 对不上
        report.fail(f"纸张尺寸不符：规格要求 {expected_width:g}mm × {expected_height:g}mm，"
                    f"成品实际 {width_mm:.1f}mm × {height_mm:.1f}mm")   # 记录失败

# 从 DOCX 正文 XML 里读纸张尺寸（w:pgSz 的宽高是 twips）
def docx_page_size_mm(document_xml):
    if isinstance(document_xml, str):                          # 调用方给的是已解码字符串
        document_xml = document_xml.encode("utf-8")            # 转回字节，lxml 才肯解析
    try:                                                       # XML 可能不成形
        root = etree.fromstring(document_xml)                  # 解析正文
    except Exception as error:                                 # 解析失败
        print(f"提示：纸张尺寸未能核对（正文 XML 解析失败：{error}）", file=sys.stderr)   # 说明原因
        return None                                            # 返回「不知道」
    sizes = root.findall(".//w:sectPr/w:pgSz", W_NS)           # 全部节的纸张设置
    if not sizes:                                              # 一个都没有
        return None                                            # 返回「不知道」
    node = sizes[0]                                            # 取第一节的（各节尺寸一致）
    try:                                                       # 属性可能缺失或非法
        width_twips = float(node.get(f"{{{W_NS['w']}}}w"))     # 纸宽（twips）
        height_twips = float(node.get(f"{{{W_NS['w']}}}h"))    # 纸高（twips）
    except (TypeError, ValueError):                            # 读不出来
        return None                                            # 返回「不知道」
    return (width_twips / 1440 * 25.4, height_twips / 1440 * 25.4)   # twips → 英寸 → 毫米

def content_width_cm(spec):
    page = spec.get("page") or {}                          # 取页面配置
    # 纸张宽度走 spec_lib.page_size_mm：只看 width_mm 会让「写 size: A4 没写宽高」的规格卡
    # 算出版心宽度为空，于是标题折行、表格装不装得下这些核对统统被记成「跳过」——
    # 报告上写「跳过」，看起来像「这稿子没这块内容」，其实是核对根本没跑。
    width_mm = spec_lib.page_size_mm(spec)[0]              # 纸张宽度（显式宽高 → size 名称表）
    if not width_mm:                                       # 没有宽度就无从计算
        return None                                        # 返回「算不出来」
    # 左右边距有两种写法：通用写法（margin_left/right_mm）与书刊写法（订口/切口）
    left = page.get("margin_left_mm") or page.get("margin_inside_mm") or 0     # 左边距
    right = page.get("margin_right_mm") or page.get("margin_outside_mm") or 0   # 右边距
    return (float(width_mm) - float(left) - float(right)) / 10                 # 毫米换成厘米

# 结果收集器：分别记录已落实、跳过、失败三类条目
# 取正文里全部段落：返回 [(段落文字, 段落属性 XML, 整段 XML)]。
# 公文要素的核对必须落到「具体那一段」上：只查文字在不在文档里，查不出它有没有顶格、
# 有没有右空四字 —— 而这正是上一版漏掉的那类缺陷（要素在，位置全错）。
# 三个字段各有用途：文字用于认出是哪一段；段落属性（w:pPr）里有缩进与段前距；
# 整段 XML 里才有文字块的字体（w:rPr 挂在 w:r 上，不在 w:pPr 里 —— 这一点踩过坑：
# 只查段落属性会让「姓名字体」永远查不到，报告里出现一条假失败）。
def paragraph_entries(document_xml):
    if isinstance(document_xml, str):                      # 调用方给的是已解码字符串
        document_xml = document_xml.encode("utf-8")        # 转回字节，lxml 才肯解析
    try:                                                   # XML 可能不成形
        root = etree.fromstring(document_xml)              # 解析正文
    except Exception:                                      # 解析失败
        return []                                          # 返回空，调用方按「没查成」处理
    entries = []                                           # 结果列表
    for paragraph in root.iter(f"{{{W_NS['w']}}}p"):        # 遍历全部段落
        text = "".join(node.text or "" for node in paragraph.iter(f"{{{W_NS['w']}}}t"))   # 段落文字
        ppr = paragraph.find("w:pPr", W_NS)                 # 取段落属性节点
        ppr_xml = etree.tostring(ppr, encoding="unicode") if ppr is not None else ""   # 段落属性 XML
        entries.append((text, ppr_xml, etree.tostring(paragraph, encoding="unicode")))   # 记下三段信息
    return entries                                          # 返回全部段落

# 取一段段落属性 XML 里的某个数值属性（如 w:leftChars、w:before）；取不到返回 None。
def ppr_number(ppr_xml, name):
    match = re.search(r'w:%s="(-?\d+)"' % name, ppr_xml or "")   # 在段落属性里找该属性
    return int(match.group(1)) if match else None               # 取到就转成整数，取不到返回 None

# 核对公文主体要素与签发人的实际位置（GB/T 9704-2012 §7.2.5、§7.2.6、§7.3.2、§7.3.5）。
# 为什么单独一场核对：上一版公文里签发人一个字都没印、主送机关与成文日期被当成普通正文缩进两字，
# 而当时的合规报告全绿 —— 因为那套核对只查「有没有」，不查「排得对不对」。
# 这里对每一段都量实际写进文件的值：缩进 w:leftChars / w:firstLineChars、空行 w:before。
def verify_gov_elements(report, document, spec):
    masthead = spec.get("masthead") or {}                  # 取版头配置
    elements = spec_lib.element_detectors_for(spec)        # 该规格声明要识别哪几种要素
    signer = masthead.get("signer") or {}                  # 取签发人配置
    doc_number = masthead.get("doc_number") or {}          # 取发文字号配置
    signer_needed = bool(signer.get("enabled")) and bool(str(signer.get("name") or "").strip())   # 规格要求签发人吗
    if not elements and not signer_needed:                 # 这份规格不涉及公文要素
        return                                             # 什么都不用核对
    entries = paragraph_entries(document)                   # 取全部段落
    if not entries:                                        # 段落没解析出来
        report.skip("正文段落未能解析，公文要素的位置无法核对")   # 如实说明没查成
        return                                             # 返回
    signer_paragraph = ""                                  # 含签发人的那一段（整段 XML，字体在 w:rPr 里）
    signer_name = str(signer.get("name") or "").strip()      # 签发人姓名
    if signer_needed:                                      # 规格要求签发人
        for text, _ppr_xml, full_xml in entries:            # 逐段找
            if "签发人" in text and signer_name and signer_name in text:   # 同时含「签发人」与姓名
                signer_paragraph = full_xml                 # 记下整段 XML（字体在文字块属性里）
                break                                       # 找到就停
        if not signer_paragraph:                            # 一个字都没印出来
            report.fail("规格启用了签发人，但正文里找不到「签发人：姓名」。上行文缺签发人不合规（§7.2.6）")
        else:                                               # 印出来了
            report.ok(f"签发人已写入：{signer_name}")           # 记录通过
            name_slot = signer.get("name_font") or {}        # 姓名字体槽位
            name_font = spec_lib.resolve_font(name_slot.get("east_asian") or "楷体", name_slot.get("resolved"))   # 期望字体
            if name_font and name_font in signer_paragraph:  # 段落里有这个字体名
                report.ok(f"签发人姓名用了 §7.2.6 规定的楷体档位（{name_font}）")   # 记录通过
            elif name_font:                                 # 字体名没出现
                report.fail(f"签发人姓名未使用规格要求的字体 {name_font}（§7.2.6：姓名用 3 号楷体）")   # 记录失败
            if 'w:val="right"' in signer_paragraph:          # 用了右对齐制表位
                report.ok("签发人居右（按 §7.2.6 居右空一字，用右对齐制表位实现）")   # 记录通过
            else:                                           # 没有制表位
                report.fail("签发人没有居右（§7.2.6 要求居右空一字）")   # 记录失败
            number_skeleton = f"〔{doc_number.get('year')}〕{doc_number.get('serial')}号"   # 发文字号的骨架
            if doc_number.get("enabled"):                    # 规格要求发文字号
                same_line = any("签发人" in text and signer_name in text and number_skeleton in text
                                for text, _, _ in entries)  # 号与签发人在同一段吗
                if same_line:                               # 在同一段
                    report.ok("签发人与发文字号排在同一行（§7.2.5、§7.2.6）")   # 记录通过
                else:                                       # 不在同一段
                    report.fail("签发人没有和发文字号排在同一行（§7.2.5 要求二者同行）")   # 记录失败
    # 发文字号：上行文（position: left）必须居左空一字（§7.2.5）
    if doc_number.get("enabled") and str(doc_number.get("position") or "") == "left":   # 规格声明为上行文
        number_skeleton = f"〔{doc_number.get('year')}〕{doc_number.get('serial')}号"       # 号的骨架
        found = [ppr_xml for text, ppr_xml, _ in entries if number_skeleton in text]       # 含发文字号的那些段
        if found and ppr_number(found[0], "leftChars") == 100:   # 左边空一字（100 ＝ 1 字）
            report.ok("上行文的发文字号居左空一字（§7.2.5）")        # 记录通过
        elif found:                                        # 找到了但缩进不对
            report.fail(f"上行文的发文字号未居左空一字（§7.2.5），实测 w:leftChars="
                        f"{ppr_number(found[0], 'leftChars')}")   # 记录失败
    if not elements:                                       # 这份规格不涉及主体要素
        return                                             # 核对到此为止
    # 主体要素：先在成品里把三种要素认出来（用的是与生成端同一份识别形态）
    found_elements = {}                                    # 要素名 → (文字, 段落属性)
    for text, ppr_xml, _full_xml in entries:               # 逐段比对形态
        stripped = text.strip()                            # 去掉首尾空白
        if not stripped:                                   # 空段
            continue                                       # 跳过
        for key in ("recipient", "signature", "date", "attachment"):   # 四种主体要素（§7.3.2／§7.3.4／§7.3.5）
            pattern = spec_lib.ELEMENT_DETECTORS.get(key)   # 该要素的识别形态
            if key in elements and pattern and pattern.match(stripped) and key not in found_elements:   # 命中且尚未登记
                found_elements[key] = (stripped, ppr_xml)   # 记下来
                break                                       # 一段只算一种
    layout = spec_lib.gov_signature_layout(                # 按规格算出期望位置
        found_elements.get("signature", ("", ""))[0],       # 成品里的署名文字
        found_elements.get("date", ("", ""))[0],            # 成品里的成文日期文字
        spec)                                               # 规格卡
    line_pt = spec_lib.body_line_height_pt(spec)            # 一个空行的高度（磅）
    recipient = found_elements.get("recipient")             # 主送机关
    if recipient:                                           # 找到了就核对顶格
        ppr_xml = recipient[1]                              # 段落属性
        if ppr_number(ppr_xml, "firstLineChars") in (None, 0) and ppr_number(ppr_xml, "leftChars") in (None, 0):   # 没有任何缩进
            report.ok("主送机关居左顶格（§7.3.2）")               # 记录通过
        else:                                               # 有缩进
            report.fail(f"主送机关没有顶格（§7.3.2）：实测 w:firstLineChars="
                        f"{ppr_number(ppr_xml, 'firstLineChars')}、w:leftChars={ppr_number(ppr_xml, 'leftChars')}")   # 记录失败
        before = ppr_number(ppr_xml, "before")               # 段前距
        if before is not None and abs(before - line_pt * 20) < 20:   # 与「空一行」相差不到 1 磅
            report.ok("主送机关上方空了一行（§7.3.2「编排于标题下空一行位置」）")   # 记录通过
        else:                                               # 段前距不对
            report.fail(f"主送机关上方没有空一行（§7.3.2）：实测段前距 {before}（二十分之一磅），"
                        f"期望约 {int(line_pt * 20)}")            # 记录失败
    elif "recipient" in elements:                           # 规格要识别，但成品里没有
        report.warn("成品里没有认出主送机关（§7.3.2）：请确认原稿是否真的没写")   # 提示用户判断
    # 附件说明：核对其「回行与附件名称首字对齐」（§7.3.4 最后一句）。
    # 只做左空二字的附件说明，长附件名回行时会顶到版心左边缘、与「附件」二字齐平，
    # 看不出哪一行才是附件名称 —— 这一点在源码里看不出来，必须回成品里量缩进。
    attachment = found_elements.get("attachment")           # 附件说明
    if attachment:                                          # 成品里有附件说明
        prefix_chars = spec_lib.attachment_prefix_chars(attachment[0])   # 「附件：」+ 顺序号占几个字
        base = float(((spec.get("body_elements") or {}).get("attachment") or {})   # 预设声明的首行左空字数
                     .get("first_line_indent_chars") or 0)    # 取不到就按 0（顶格）算
        # 悬挂量读 w:hanging（长度单位，二十分之一磅）。生成端**故意不写 w:hangingChars**：
        # 字符单位与长度单位同时存在时 LibreOffice 会把悬挂算到回行上（实测，见 build_docx 的说明），
        # 所以校验端也跟着读长度单位，两边口径一致。
        size_pt = float(((spec.get("fonts") or {}).get("body") or {}).get("size_pt") or 16)   # 正文字号（附件说明用正文字号）
        hanging = ppr_number(attachment[1], "hanging")         # 实际写的悬挂量（二十分之一磅）
        left = ppr_number(attachment[1], "left")               # 实际写的左缩进（二十分之一磅）
        one_char = 20.0 * size_pt                              # 一个字等于多少个二十分之一磅
        hanging_chars = (hanging / one_char) if hanging is not None else None   # 悬挂量折算成「字」
        left_chars = (left / one_char) if left is not None else None            # 左缩进折算成「字」
        if not prefix_chars:                                # 认不出「附件：」前缀
            report.warn("成品里的附件说明没有「附件：」前缀，无法核对回行是否与附件名称首字对齐（§7.3.4）")   # 提示用户判断
        elif hanging is None:                               # 压根没写悬挂缩进
            report.fail(f"附件说明没有做回行对齐（§7.3.4）：查不到悬挂缩进，期望 {prefix_chars:g} 字")   # 记录失败
        elif abs(hanging_chars - prefix_chars) <= 0.05 and abs((left_chars or 0) - (base + prefix_chars)) <= 0.05:   # 两个数值都对（容差 0.05 字）
            report.ok(f"附件说明回行与附件名称首字对齐（§7.3.4）：左缩进 {base + prefix_chars:g} 字、悬挂 {prefix_chars:g} 字")   # 记录通过
        else:                                               # 数值对不上
            report.fail(f"附件说明的回行对齐不符（§7.3.4）：实测左缩进 {(left_chars or 0):g} 字、"
                        f"悬挂 {hanging_chars:g} 字，期望左缩进 {base + prefix_chars:g} 字、悬挂 {prefix_chars:g} 字")   # 记录失败
    elif "attachment" in elements:                          # 规格要识别，但成品里没有
        report.warn("成品里没有认出附件说明（§7.3.4）：请确认原稿是否真的没写附件")   # 提示用户判断
    for key, label in (("signature", "发文机关署名"), ("date", "成文日期")):   # 署名与日期
        item = found_elements.get(key)                      # 取该要素
        if not item:                                        # 没找到
            if key in elements:                             # 规格要识别这一项
                report.warn(f"成品里没有认出{label}：请确认原稿是否真的没写")   # 提示
            continue                                        # 下一项
        expected = layout["signature_left_chars"] if key == "signature" else layout["date_left_chars"]   # 期望左空字数
        actual = ppr_number(item[1], "leftChars")            # 实际左空字数（百分之一字）
        if actual is None:                                  # 没有写左缩进
            report.fail(f"{label}没有按 §7.3.5 定位：文档里查不到左空字数（期望 {expected} 字）")   # 记录失败
        elif abs(actual / 100.0 - expected) <= 0.05:         # 与期望一致（容差半个百分点）
            report.ok(f"{label}位置符合 §7.3.5（{layout['mode']}）：左空 {expected} 字")   # 记录通过
        else:                                               # 与期望不符
            report.fail(f"{label}的左空字数与 §7.3.5 不符（{layout['mode']}）："
                        f"实测 {actual / 100.0} 字，期望 {expected} 字")   # 记录失败
    if "signature" in found_elements:                       # 署名上方应当空一行
        before = ppr_number(found_elements["signature"][1], "before")   # 段前距
        if before is not None and abs(before - line_pt * 20) < 20:      # 与「空一行」相差不到 1 磅
            report.ok("署名之前空了一行（§7.3.5.2）")               # 记录通过
        else:                                               # 段前距不对
            report.fail(f"署名之前没有空一行（§7.3.5.2）：实测段前距 {before}，期望约 {int(line_pt * 20)}")   # 记录失败

# 结果收集器：分别记录已落实、跳过、失败三类条目
class Report:
    def __init__(self):                              # 初始化
        self.passed = []                             # 已落实清单
        self.skipped = []                            # 因载体限制跳过的清单
        self.warnings = []                           # 需人工确认的清单（不是载体限制，也不是明确失败）
        self.failed = []                             # 未落实的清单
    def ok(self, message):                           # 记录一条已落实
        self.passed.append(message)                  # 加入通过清单
    def skip(self, message):                         # 记录一条跳过
        self.skipped.append(message)                 # 加入跳过清单
    def warn(self, message):                         # 记录一条需人工确认
        self.warnings.append(message)                # 加入待确认清单
    def fail(self, message):                         # 记录一条失败
        self.failed.append(message)                  # 加入失败清单
    def print(self, title):                          # 打印完整报告
        print(f"排版合规报告  {title}")                # 打印标题
        print("=" * 60)                              # 打印分隔线
        print(f"[已落实] {len(self.passed)} 项")       # 打印通过数
        for item in self.passed:                     # 逐条打印通过项
            print("   通过", item)
        if self.warnings:                            # 若有需人工确认项
            print(f"[需确认] {len(self.warnings)} 项（可能是没用到，也可能是被替换了）")   # 打印待确认数
            for item in self.warnings:               # 逐条打印
                print("   确认", item)                # 打印待确认项
        if self.skipped:                             # 若有跳过项
            print(f"[已跳过] {len(self.skipped)} 项（载体限制，非缺陷）")   # 打印跳过数
            for item in self.skipped:                # 逐条打印跳过项
                print("   跳过", item)
        if self.failed:                              # 若有失败项
            print(f"[失败] {len(self.failed)} 项（需要修正）")   # 打印失败数
            for item in self.failed:                 # 逐条打印失败项
                print("   失败", item)
        if not self.failed:                          # 若没有失败
            print("-" * 60)                          # 打印分隔线
            print("全部规格已落实。")                   # 打印总结

# 读取 zip 容器内的某个文件内容，返回字符串
def read_zip_member(path, member):
    with zipfile.ZipFile(path) as archive:           # 打开 zip
        return archive.read(member).decode("utf-8", "ignore")   # 读取并解码

# 根据规格卡计算期望的字体名（按档位解析后）
def expected_fonts(spec):
    body = (spec.get("fonts") or {}).get("body") or {}                   # 取正文字体段
    return {
        "east_asian": spec_lib.resolve_font(body.get("east_asian", ""), body.get("resolved")),   # 期望的中文字体
        "latin": body.get("latin") or "Times New Roman",                            # 期望的西文字体
    }

# 校验 DOCX：解包读样式与正文 XML，逐条核对
def verify_docx(path, spec):
    report = Report()                                # 创建报告
    try:                                             # 尝试读取文件
        styles = read_zip_member(path, "word/styles.xml")       # 读取样式表
        document = read_zip_member(path, "word/document.xml")   # 读取正文
    except Exception as error:                       # 读取失败
        report.fail(f"无法解包 DOCX：{error}")         # 记录失败
        report.print(path)                           # 打印报告
        return report                                # 返回
    fonts = expected_fonts(spec)                     # 计算期望字体
    # 核对中文字体是否写入样式表
    if fonts["east_asian"] and fonts["east_asian"] in styles:   # 命中
        report.ok(f"中文字体已写入样式表：{fonts['east_asian']}")   # 记录通过
    else:                                            # 未命中
        report.fail(f"样式表中未找到中文字体 {fonts['east_asian']}")   # 记录失败
    # 核对西文字体
    if fonts["latin"] and fonts["latin"] in styles:   # 命中
        report.ok(f"西文字体已单独指定：{fonts['latin']}")   # 记录通过
    else:                                            # 未命中
        report.fail(f"样式表中未找到西文字体 {fonts['latin']}，英文与数字会用中文字体渲染")   # 记录失败
    # 核对正文字号（w:sz 为半磅值）
    body_size = ((spec.get("fonts") or {}).get("body") or {}).get("size_pt")   # 取正文字号
    if body_size:                                    # 若指定了字号
        half_points = str(spec_lib.pt_to_docx_sz(body_size))   # 换算为半磅值
        if f'w:val="{half_points}"' in styles:       # 在样式表中查找
            report.ok(f"正文字号已写入：{body_size}pt（w:sz={half_points}）")   # 记录通过
        else:                                        # 未找到
            report.fail(f"样式表中未找到正文字号 {body_size}pt（期望 w:sz={half_points}）")   # 记录失败
    # 核对首行缩进（字符级）
    indent_mode = (spec.get("paragraph") or {}).get("indent_mode", "first_line")   # 取缩进模式
    indent_chars = (spec.get("paragraph") or {}).get("first_line_indent_chars")    # 取缩进字符数
    if indent_mode == "first_line" and indent_chars:   # 印刷模式应写入缩进
        expected_chars = str(int(float(indent_chars) * 100))   # 换算成百分之一字符
        if f'w:firstLineChars="{expected_chars}"' in document or f'w:firstLineChars="{expected_chars}"' in styles:
            report.ok(f"首行缩进已生效：{indent_chars} 字符")   # 记录通过
        else:                                        # 未生效
            report.fail(f"未找到首行缩进 {indent_chars} 字符（期望 w:firstLineChars={expected_chars}），中文排版最常见的缺陷")   # 记录失败
    else:                                            # 屏幕模式
        report.skip("首行缩进按规格关闭（屏幕阅读模式）")   # 记录跳过
    # 核对行距
    paragraph = spec.get("paragraph") or {}          # 取段落配置
    if paragraph.get("line_spacing_mode") == "exact" and paragraph.get("line_spacing_pt"):
        expected_line = str(spec_lib.pt_to_docx_line(paragraph["line_spacing_pt"]))   # 换算行距值
        if f'w:line="{expected_line}"' in styles:    # 在样式表中查找
            report.ok(f"固定值行距已写入：{paragraph['line_spacing_pt']}pt")   # 记录通过
        else:                                        # 未找到
            report.fail(f"未找到固定值行距 {paragraph['line_spacing_pt']}pt")   # 记录失败
    # 核对页面尺寸与页边距
    page = spec.get("page") or {}                    # 取页面配置
    if page.get("margin_top_mm"):                    # 若设置了上边距
        expected_twips = str(spec_lib.mm_to_twips(page["margin_top_mm"]))   # 换算为 twips
        if f'w:top="{expected_twips}"' in document:   # 在正文 XML 中查找
            report.ok(f"页边距已写入：上 {page['margin_top_mm']}mm")   # 记录通过
        else:                                        # 未找到
            report.fail(f"未找到页边距设置 上 {page['margin_top_mm']}mm")   # 记录失败
    # 核对左右边距：单面稿写左/右，双面书刊写内侧/外侧，两种都要能查出没落实的情况。
    # 内外侧不能直接与 w:left/w:right 比大小 —— 得先按生成时的同一套规则折算成左/右，否则会把对的判成错的。
    inside = page.get("margin_inside_mm")            # 内侧边距
    outside = page.get("margin_outside_mm")          # 外侧边距
    if inside is not None and outside is not None:   # 规格用的是内外侧写法
        binding = page.get("binding") or "left"      # 取装订边
        if page.get("mirror_margins"):               # 镜像模式：左写内侧、右写外侧，由偶数页自动互换
            left_mm, right_mm = float(inside), float(outside)   # 与 build_docx.setup_page 保持一致
        elif binding == "right":                     # 单面且装订在右
            left_mm, right_mm = float(outside), float(inside)   # 内侧落在右边
        else:                                        # 单面且装订在左
            left_mm, right_mm = float(inside), float(outside)   # 内侧落在左边
        left_twips = f'w:left="{spec_lib.mm_to_twips(left_mm)}"'      # 期望的左边距标记
        right_twips = f'w:right="{spec_lib.mm_to_twips(right_mm)}"'   # 期望的右边距标记
        if left_twips in document and right_twips in document:        # 两条都在
            report.ok(f"内外侧页边距已折算写入：内侧 {inside}mm、外侧 {outside}mm")   # 记录通过
        else:                                        # 有一条没找到
            report.fail(f"内外侧页边距未按预期折算（期望左 {left_mm}mm、右 {right_mm}mm）")   # 记录失败
        if page.get("mirror_margins"):               # 要求镜像页边距
            # 镜像开关属于 settings.xml，不在 document.xml 里，要单独开包查
            settings_xml = ""                        # 先给个默认值，读不到也不至于抛异常
            try:                                     # settings.xml 理论上一定存在
                settings_xml = read_zip_member(path, "word/settings.xml")   # 读出设置部件
            except Exception:                        # 万一缺失
                settings_xml = ""                    # 当作没有
            if "w:mirrorMargins" in settings_xml:    # 找到镜像开关
                report.ok("镜像页边距已打开（settings.xml 中的 w:mirrorMargins）")   # 记录通过
            else:                                    # 没有开关
                report.fail("规格要求镜像页边距，但 settings.xml 里没有 w:mirrorMargins，偶数页边距不会互换")   # 记录失败
    # 核对纸张尺寸（放在页边距之后：幅面错了，边距、版心、每行字数全都跟着错）
    check_page_size(report, spec, docx_page_size_mm(document))   # 传入从 w:pgSz 读到的实测尺寸
    # 核对页眉
    header_cfg = spec.get("header") or {}            # 取页眉配置
    if header_cfg and header_cfg.get("enabled") is not False and \
            (header_cfg.get("odd_content") or header_cfg.get("even_content")):   # 规格确实要求页眉
        try:                                         # 尝试读取页眉部件
            headers = [name for name in zipfile.ZipFile(path).namelist() if name.startswith("word/header")]   # 找出页眉文件
            if not headers:                          # 一个页眉部件都没有
                report.fail("规格要求页眉，但文件里没有 header 部件")   # 记录失败
            else:                                    # 有页眉部件
                header_texts = [read_zip_member(path, name) for name in headers]   # 逐个读出
                joined = "".join(header_texts)       # 拼起来一起查
                tokens = [header_cfg.get("odd_content"), header_cfg.get("even_content")]   # 两侧登记的内容标记
                if any(str(tok).strip() == "chapter_name" for tok in tokens):   # 要用「当前章名」
                    if "STYLEREF" in joined:         # 找到 STYLEREF 域
                        report.ok("页眉已插入 STYLEREF 域（章名随页自动变化）")   # 记录通过
                    else:                            # 没有域
                        report.fail("页眉要求写当前章名，但没有找到 STYLEREF 域（会变成死文本）")   # 记录失败
                if any(str(tok).strip() in ("book_title", "document_title") for tok in tokens):   # 要用「书名」
                    book_title = str(header_cfg.get("book_title") or "").strip()   # 用户填的书名
                    if book_title and book_title in joined:   # 书名确实写进去了
                        report.ok(f"页眉已写入书名：{book_title}")   # 记录通过
                    elif not book_title:             # 没填书名
                        report.fail("页眉要求写书名，但规格卡没填 header.book_title（当前用的是规格名占位）")   # 记录失败
                if header_cfg.get("different_odd_even") and len(headers) < 2:   # 要求奇偶不同却只有一个页眉
                    report.fail("规格要求单双页页眉不同，但只生成了 1 个页眉部件，偶数页页眉会消失")   # 记录失败
                elif header_cfg.get("different_odd_even"):   # 两个页眉都在
                    report.ok(f"单双页页眉已分开编排（{len(headers)} 个页眉）")   # 记录通过
        except Exception as error:                   # 读取失败
            report.fail(f"页眉检查失败：{error}")        # 记录失败
    else:                                            # 规格没要求页眉
        report.skip("规格未要求页眉")                    # 记录跳过
    # 核对表格对齐。本 skill 不预设对齐风格，所以要分清「规格要求的」「源文件带来的」「根本没写」三种情况，
    # 不能像从前那样默认去找 center 标记 —— 那种写法会被正文里的居中段落误判为通过。
    cfg = spec.get("figures_tables") or {}           # 取图表配置
    if "<w:tbl>" in document:                        # 文档里有表格
        # 只截取表格内部的 XML，避免把表格外（标题、红头）的居中标记当成表格对齐
        table_xml = "".join(re.findall(r"<w:tbl>.*?</w:tbl>", document, re.S))   # 取出所有表格片段
        # 单元格内文字对齐：python-docx 把它写在单元格内段落的 w:pPr 里（不是 w:tcPr）
        cell_aligns = set(re.findall(r'<w:pPr>(?:(?!</w:pPr>).)*?<w:jc w:val="(\w+)"', table_xml, re.S))   # 单元格对齐值
        # 表格整体位置对齐：写在 w:tblPr 里，和单元格对齐是两回事，要分开判断
        table_aligns = set()                         # 表格整体对齐值集合
        for tbl_pr in re.findall(r"<w:tblPr>(.*?)</w:tblPr>", table_xml, re.S):   # 逐个取表格属性块
            table_aligns |= set(re.findall(r'<w:jc w:val="(\w+)"', tbl_pr))      # 收集其中的对齐值
        found_aligns = sorted(cell_aligns | table_aligns)   # 表格里实际用到的全部对齐值
        declared = {key: cfg.get(key) for key in ("header_alignment", "text_column_alignment",
                                                  "number_column_alignment", "table_alignment") if cfg.get(key)}   # 规格显式声明过的对齐
        if declared:                                 # 规格明确要求了对齐
            missing = [value for value in declared.values() if value not in found_aligns]   # 哪些要求没落实
            if missing:                              # 有要求没落实
                report.fail(f"规格声明了表格对齐 {'、'.join(missing)}，但表格里没找到对应标记")   # 记录失败
            else:                                    # 全部落实
                report.ok("表格对齐已按规格声明写入：" + "、".join(f"{k}={v}" for k, v in declared.items()))   # 记录通过
        elif found_aligns:                           # 规格没要求，但表格里确实有对齐标记
            report.ok("表格对齐来自源文件的对齐标记（规格未做预设）：" + "、".join(found_aligns))   # 记录通过
        else:                                        # 规格没要求，源文件也没有标记
            report.ok("表格对齐未做任何设置（规格未声明、源文件也没有标记，保持默认）")   # 记录通过
    else:                                            # 文档里没有表格
        report.skip("文档中不含表格，表格对齐无需核对")   # 记录跳过
    # 核对页码域
    page_cfg = (spec.get("footer") or {}).get("page_number") or {}   # 取页码配置
    if page_cfg.get("enabled"):                      # 若启用了页码
        try:                                         # 尝试读取页脚
            footers = [name for name in zipfile.ZipFile(path).namelist() if name.startswith("word/footer")]   # 找出页脚文件
            contents = [read_zip_member(path, name) for name in footers]   # 逐个读出页脚 XML
            has_field = any("PAGE" in text for text in contents)   # 是否找到 PAGE 域
            if has_field:                            # 找到页码域
                report.ok("页脚已插入自动页码域")         # 记录通过
            else:                                    # 未找到
                report.fail("页脚中未找到页码域（PAGE）")   # 记录失败
            # GB/T 9704-2012 §7.5：页码数字左右各一条一字线，规格开了 dash_rule 就必须真的写进去
            if page_cfg.get("dash_rule"):            # 规格要求一字线
                lined = [text for text in contents if "—" in text]   # 含一字线的页脚
                if lined:                            # 至少有一个页脚带一字线
                    report.ok(f"页码一字线已写入（{len(lined)} 个页脚）")   # 记录通过
                else:                                # 一个都没有
                    report.fail("规格要求页码加一字线，但页脚里没有找到「—」")   # 记录失败
            # 单双页要求不同时，必须有独立的单页码页脚与双页码页脚，否则偶数页会没有页码
            odd_side = page_cfg.get("odd_page")      # 单页码位置
            even_side = page_cfg.get("even_page")    # 双页码位置
            if odd_side and even_side and odd_side != even_side:   # 单双页确实不同
                if len(footers) >= 2:                # 至少两个页脚部件
                    report.ok(f"单双页页码已分开编排（{len(footers)} 个页脚）")   # 记录通过
                else:                                # 只有一个页脚
                    report.fail("规格要求单双页页码位置不同，但只生成了 1 个页脚，偶数页会没有页码")   # 记录失败
        except Exception as error:                   # 读取失败
            report.fail(f"页脚检查失败：{error}")       # 记录失败
    else:                                            # 未启用页码
        report.skip("规格未启用页码")                    # 记录跳过
    # 核对版记（GB/T 9704-2012 §7.4）
    record = spec.get("record_section") or {}        # 取版记配置
    if record.get("enabled"):                        # 启用了版记
        try:                                         # 尝试读取正文
            body = read_zip_member(path, "word/document.xml")   # 读出正文 XML
            agency = str(record.get("issuing_agency") or "").strip()   # 规格里的印发机关
            copy_to = str(record.get("copy_to") or "").strip()         # 规格里的抄送机关
            if agency and agency in body:            # 印发机关写进去了
                report.ok(f"版记已写入印发机关（{agency}）")   # 记录通过
            else:                                    # 没有印发机关
                report.fail("规格启用了版记，但正文里找不到印发机关")   # 记录失败
            # §7.4.3 最后一句：「……（即 1 不编为 01），后加『印发』二字」，
            # 即印发日期要写成「2026年9月16日印发」而不是光一个日期。
            date_text = str(record.get("issue_date") or "").strip()   # 规格里的印发日期
            suffix = str(record.get("date_suffix", "印发") or "")      # 日期后的「印发」二字（写空串＝用户不要这两个字）
            if date_text and suffix:                 # 规格给了日期、也要「印发」二字，才有得核对
                if date_text + suffix in body:       # 日期与「印发」连排地出现了
                    report.ok(f"版记印发日期后带「印发」二字（§7.4.3）：{date_text}{suffix}")   # 记录通过
                else:                                # 没有连排
                    report.fail(f"版记印发日期后缺「印发」二字（§7.4.3）：正文里查不到「{date_text}{suffix}」")   # 记录失败
            elif date_text:                          # 规格明确不要「印发」二字
                report.skip("规格把 record_section.date_suffix 写成了空串，按用户要求不加「印发」二字")   # 如实跳过
            # 版记的分隔线用段落边框实现：有抄送时是首条+中间+末条共 3 条，没有抄送时是首条+末条共 2 条
            border_count = body.count("<w:pBdr>")    # 段落边框集合数量
            expected = 3 if copy_to else 2           # 期望的边框数量
            if border_count >= expected:             # 数量够
                report.ok(f"版记分隔线已写入（{border_count} 条段落边框）")   # 记录通过
            else:                                    # 数量不足
                report.fail(f"版记分隔线不足：期望至少 {expected} 条，实际 {border_count} 条")   # 记录失败
        except Exception as error:                   # 读取失败
            report.fail(f"版记检查失败：{error}")      # 记录失败
    else:                                            # 未启用版记
        report.skip("规格未启用版记")                    # 记录跳过
    # 公文主体要素与签发人的位置核对（§7.2.5、§7.2.6、§7.3.2、§7.3.5）。
    # 放在版记之后、表格之前：这四项都属于「版头与主体」，与后面按元素逐个量的检查互不干扰。
    # 规格不涉及公文要素时，这个函数自己会直接返回，不会污染书籍、论文的报告。
    verify_gov_elements(report, document, spec)      # 逐段量实际的缩进与空行
    # 表格列宽是否真的装得下表头。
    # 为什么要回头量：生成脚本算出来的列宽有没有被正确写进 tblGrid、写得对不对，
    # 只有读真实文件才知道。实测踩过的坑是「城市」被折成「城／市」、「上海」被折成「上／海」，
    # 生成时一声不吭 —— 现在生成时预警，校验时再量一遍真实文件。
    figures_cfg = spec.get("figures_tables") or {}   # 取图表规范
    table_size_pt = float(figures_cfg.get("table_size_pt")           # 表格字号：优先用规格声明的
                          or ((spec.get("fonts") or {}).get("body") or {}).get("size_pt")   # 其次用正文字号
                          or 10.5)                   # 都没有就按五号估
    cm_per_unit = table_size_pt * 0.01764            # 一个「半个汉字宽」约多少厘米
    padding_cm = spec_lib.CELL_PADDING_CM            # 单元格左右内边距合计（与生成脚本共用同一个常量）
    squeezed_tables = []                             # 汇总有单元格要折行的表
    table_elements = parse_tables(document)          # 从正文 XML 里取出全部表格
    content_avail_cm = content_width_cm(spec)        # 版心宽度（厘米），没有就按表格自身宽度算
    for table_index, table in enumerate(table_elements, start=1):   # 逐张表格核对
        widths_twips = table_grid_widths(table)      # 取该表的列宽（twips）
        if not widths_twips or not any(widths_twips):   # 宽度没写或全是 0
            continue                                 # 无法核对，跳过
        # 按成品里真实写着的列宽，逐格算会不会折行。
        # 措辞与生成脚本共用 spec_lib.describe_table_fit_text，避免「生成时这么报、校验时那么报」。
        info = measured_table_fit(table, widths_twips, cm_per_unit, padding_cm, content_avail_cm)   # 组装与生成端同构的信息
        if info:                                     # 有单元格会折行
            squeezed_tables.append((table_index, spec_lib.describe_table_fit_text(info)))   # 汇总
    if squeezed_tables:                              # 有表格存在折行
        for index, detail in squeezed_tables:        # 逐张报出，一张一条，便于用户分别处置
            report.warn(f"第 {index} 张表：{detail}")   # 记为待确认
    elif table_elements:                             # 有表格且都没问题
        report.ok(f"{len(table_elements)} 张表格的列宽都装得下表头与数据")   # 记录通过
    # 核对表格行是否禁止跨页断行（w:cantSplit）。
    # 这是「跨页处凭空多出一条空行」的根因：行被切在页边界上，上一页只剩框线没有文字。
    if table_elements:                               # 有表格才核对
        unprotected = []                             # 没设防的行数明细
        total_rows = 0                               # 全部行数
        for table_index, table in enumerate(table_elements, start=1):   # 逐张表
            rows, protected = table_row_split_stats(table)   # 数行数与受保护行数
            total_rows += rows                       # 累计
            if protected < rows:                     # 有行会被切开
                unprotected.append(f"第 {table_index} 张表（{protected}/{rows} 行）")   # 记下明细
        if unprotected:                              # 有表格没设全
            report.warn("以下表格有行没有「禁止跨页断行」设置，跨页处可能出现有框线无文字的空行："
                        + "、".join(unprotected))   # 记为待确认
        elif total_rows:                             # 全部设上了
            report.ok(f"表格共 {total_rows} 行均已禁止跨页断行（跨页时不会留空行）")   # 记录通过
    # 核对表格线型：规格写的是三线表还是全框线，必须从成品里量出来。
    # 为什么单独列一项：实测踩过「规格写全框线、成品还是三线表」「三线表少了表头那条线」，
    # 而当时的报告全是绿的 —— 校验端不看表格边框，等于这一项没人管。
    if table_elements:                               # 有表格才核对
        declared_style = spec_lib.resolve_table_style((spec.get("figures_tables") or {}).get("table_style"))[0]   # 规格声明的线型
        wrong_style = []                             # 线型跟规格不一致的表
        missing_header = []                          # 三线表少了表头线的表
        cell_border_tables = []                      # 单元格自带竖线、可能盖过表格线型的表
        for table_index, table in enumerate(table_elements, start=1):   # 逐张表
            grid_like, header_bottom, cell_verticals = table_border_facts(table)   # 量出三件事实
            if declared_style == "grid" and not grid_like:          # 规格要全框线，成品却不是
                wrong_style.append(f"第 {table_index} 张表")        # 记下
            elif declared_style == "three_line":                    # 规格要三线表
                if grid_like:                                       # 成品却是全框线
                    wrong_style.append(f"第 {table_index} 张表")    # 记下
                elif not header_bottom:                             # 少了表头底下那条线
                    missing_header.append(f"第 {table_index} 张表")  # 记下
            if declared_style == "three_line" and cell_verticals:   # 三线表却带着单元格竖线
                cell_border_tables.append(f"第 {table_index} 张表")  # 记下（原稿自带，可能盖过线型）
        if wrong_style:                              # 线型没照规格做
            report.fail("以下表格的线型与规格不符（规格要"
                        + {"grid": "全框线", "three_line": "三线表"}.get(declared_style, declared_style)
                        + "）：" + "、".join(wrong_style))   # 记为失败
        if missing_header:                           # 三线表缺表头线
            report.fail("以下表格是三线表，却少了表头底下那条分隔线（正常应为顶线、表头线、底线三条）："
                        + "、".join(missing_header))   # 记为失败
        if cell_border_tables:                       # 单元格自带边框
            report.warn("以下表格的单元格自带竖线，会盖过规格里的表格线型，成品可能仍是全框线："
                        + "、".join(cell_border_tables))   # 记为待确认
        if not wrong_style and not missing_header and not cell_border_tables:   # 全都对得上
            report.ok(f"{len(table_elements)} 张表格的线型与规格一致（"
                      + {"grid": "全框线", "three_line": "三线表"}.get(declared_style, declared_style) + "）")   # 记录通过
    # 核对表题（图表题注）落在表格上方还是下方，是否与规格一致。
    declared_position = str(((spec.get("figures_tables") or {}).get("table_caption_position")
                             or "")).strip().lower()   # 规格要求的表题位置
    captions = caption_positions(document)           # 从成品里量出来的题注位置
    if not captions:                                 # 一个紧邻表格的题注都没找到
        report.skip("未找到紧邻表格的题注段（源稿可能没写表题），表题位置无需核对")   # 记录跳过
    elif not declared_position:                      # 源稿有题注，但规格没要求位置
        report.ok("规格未对表题位置做要求，题注保持源稿的位置未动")   # 记录通过
    else:                                            # 规格有明确要求，逐张核对
        wrong = [f"第 {index} 张表：表题在表{('上' if where == 'above' else '下')}"
                 for index, text, where in captions if where != declared_position]   # 位置不符的表
        if wrong:                                    # 有不符合的
            report.fail(f"规格要求表题在表{('上' if declared_position == 'above' else '下')}方，"
                        f"但实际是：{'；'.join(wrong)}")   # 记录失败
        else:                                        # 全部符合
            report.ok(f"{len(captions)} 处表题的位置与规格一致"
                      f"（表{('上' if declared_position == 'above' else '下')}方）")   # 记录通过
    # 标题折行核对：末行只剩一两个字的标题在版面上很扎眼（俗称「孤字」），
    # 而这一点在源码里看不出来，只有算一遍才知道。
    available_cm = content_width_cm(spec)            # 版心宽度（厘米）
    headings_cfg = spec.get("headings") or {}        # 取标题配置
    if available_cm is None:                         # 算不出宽度
        report.skip("规格卡没写纸张宽度，标题折行无法核对")   # 记录跳过
    else:                                            # 算得出来就核对
        orphans = []                                 # 末行是孤字的标题
        for level, text in heading_paragraph_list(document):   # 逐条标题
            size = (spec_lib.resolve_heading(headings_cfg, level) or {}).get("size_pt")   # 该级字号
            if not size:                             # 没写字号
                continue                             # 跳过
            if spec_lib.looks_like_prose(text):      # 带句末标点 ＝ 被登记成标题的正文自然段（公文层次序数就是这样）
                continue                             # 折行核对跳过它，免得把正文的正常折行报成「标题排得难看」
            info = spec_lib.heading_wrap_info(text, float(size), available_cm)   # 算折行（人工断过行的标题会返回 None）
            if spec_lib.heading_wrap_is_bad(info):     # 孤字或倒梯形（判据与生成端共用同一份）
                orphans.append(spec_lib.describe_heading_wrap_text(info))   # 记下来
        if orphans:                                  # 有折行难看的标题
            for item in orphans:                     # 逐条报出
                report.warn(f"标题折行：{item}")        # 记为待确认（改字号即可解决）
        else:                                        # 没有难看的折行
            report.ok("标题折行核对通过：没有孤字、也没有头重脚轻的倒梯形标题")   # 记录通过
    # 核对「章从奇数页起」是否真的写进了分节符。
    # 这里只查 DOCX 里有没有 oddPage 分节符；章到底落在奇数页还是偶数页，交给 verify_pdf 去量，
    # 因为真正决定落点的是「空白页有没有被保留」，那要等 PDF 出来才知道。
    chapter_level = spec_lib.chapter_heading_level(spec)   # 「章」落在第几级标题
    chapter_cfg = spec_lib.resolve_heading(spec.get("headings") or {}, chapter_level)   # 取「章」的配置
    if chapter_cfg.get("start_on_odd_page"):         # 规格要求章从奇数页起
        chapter_count = count_heading_paragraphs(document, chapter_level)   # 稿子里有多少个章标题
        if chapter_count == 0:                       # 明确数到 0 个（None 表示没查成，不算 0）
            report.skip(f"文稿中没有第 {chapter_level} 级标题（章），「章从奇数页起」无从设置")   # 记录跳过
        else:                                        # 有章，或者没查成
            odd_sections = document.count('w:val="oddPage"')   # 数文档里的 oddPage 分节符
            if odd_sections:                         # 确实写了
                report.ok(f"「章从奇数页起」已写入：{odd_sections} 个 oddPage 分节符"
                          f"（Word 会遵守，章后可能多出一页空白，属正常版面）")   # 记录通过
            else:                                    # 没写
                report.fail("规格要求「章从奇数页起」，但文档里没有 oddPage 分节符")   # 记录失败
    report.print(path)                               # 打印报告
    return report                                    # 返回报告

# 校验 PDF：检查字体内嵌与页数
def verify_pdf(path, spec):
    report = Report()                                # 创建报告
    try:                                             # 尝试导入 PyMuPDF
        import fitz                                  # PyMuPDF 的导入名
    except ImportError:                              # 缺失依赖
        report.fail("缺少依赖 PyMuPDF，请运行：pip3 install pymupdf")   # 记录失败
        report.print(path)                           # 打印报告
        return report                                # 返回
    if not os.path.exists(str(path)):                # 文件不存在时先拦下来
        # 不拦的后果实测过：PyMuPDF 直接抛 FileNotFoundError，用户看到一段 Python 调用栈。
        # 同一脚本核 DOCX 时早有 except 兜着，只有 PDF 这条路径漏了，这里补齐成一致行为。
        report.fail(f"文件不存在：{path}")             # 记失败
        report.print(path)                           # 打印报告
        return report                                # 返回
    try:                                             # 文件可能损坏或不是 PDF
        document = fitz.open(path)                   # 打开 PDF
    except Exception as error:                       # 打开失败
        report.fail(f"无法打开 PDF：{error}")          # 记失败
        report.print(path)                           # 打印报告
        return report                                # 返回
    report.ok(f"PDF 可正常打开，共 {document.page_count} 页")   # 记录页数
    # 核对纸张尺寸：PDF 的页面尺寸取自第一页的矩形（单位是点，72 点 = 1 英寸）
    if document.page_count:                          # 有页面才量
        rect = document[0].rect                      # 第一页的页面矩形
        check_page_size(report, spec, (rect.width / 72 * 25.4, rect.height / 72 * 25.4))   # 点 → 毫米
    embedded = set()                                 # 已内嵌字体集合
    not_embedded = set()                             # 未内嵌字体集合
    all_fonts_seen = set()                           # PDF 里出现过的全部字体名（含未内嵌的）
    for page_index in range(document.page_count):    # 遍历每一页
        for font in document.get_page_fonts(page_index):   # 遍历该页字体
            name = font[3]                           # 字体名在第 4 个字段
            embedded_flag = font[1]                  # 是否内嵌标记在第 2 个字段
            all_fonts_seen.add(name)                 # 无论是否内嵌都记下来，供字体替换检查用
            if embedded_flag:                        # 若已内嵌
                embedded.add(name)                   # 加入已内嵌集合
            else:                                    # 若未内嵌
                not_embedded.add(name)               # 加入未内嵌集合
    if embedded:                                     # 若有内嵌字体
        report.ok(f"已内嵌字体 {len(embedded)} 个：" + "、".join(sorted(embedded)[:6]))   # 记录通过
    if not_embedded:                                 # 若存在未内嵌字体
        report.fail("以下字体未内嵌，换台电脑会变形或显示方框：" + "、".join(sorted(not_embedded)))   # 记录失败
    # 检查中文是否真的渲染出来（看第一页文本是否包含中文）
    first_page_text = document[0].get_text() if document.page_count else ""   # 取第一页文本
    if re.search(r"[\u4e00-\u9fff]", first_page_text):                        # 若包含中文
        report.ok("PDF 中已渲染出中文文本，未出现字体缺失")                      # 记录通过
    else:                                                                     # 若没有中文
        report.fail("PDF 第一页未检出中文文本，可能字体未生效或内容是空白")        # 记录失败
    # 关键检查：含中文文本的 PDF 必须内嵌中文字体，否则换台电脑中文会变方框
    # 中文字体名判定收在 spec_lib，避免与 build_pdf / render_preview 各写一份、结论打架
    has_cjk_embedded = any(spec_lib.looks_like_cjk_font(name) for name in embedded)   # 是否内嵌中文字体
    if re.search(r"[\u4e00-\u9fff]", first_page_text):                        # 若文档含中文
        if has_cjk_embedded:                                                  # 且已内嵌中文字体
            report.ok("已内嵌中文字体，换台电脑中文不会变成方框")                # 记录通过
        else:                                                                 # 未内嵌中文字体
            report.fail("PDF 含中文文本但未内嵌任何中文字体。换台电脑打开中文会显示为方框，"
                        "需先给 LibreOffice 安装中文字体（见 references/fonts.md）")   # 记录失败
    # 关键检查：规格要求的字体，必须真的出现在 PDF 里。
    # 为什么必须查：DOCX 生成时已经禁止替换，但 DOCX → PDF 这一跳是 LibreOffice 做的，
    # 它找不到字体就静默换一个（实测换成了 LinuxLibertine / DejaVuSans / FrankRuhlHofshi），
    # 而上面的检查只要求「内嵌了某个中文字体」，换个中文字体也能蒙混过关。
    # 判定分两档：正文两种字体必须命中（否则整篇字都错了）；标题/红头/页码等
    # 记警告不判失败，因为规格配了但文档里可能根本没用到那一级。
    if all_fonts_seen:                                                        # PDF 里读到了字体才做这项检查
        seen_names = sorted(all_fonts_seen)                                   # 排序后便于打印
        for use, required, actual, is_cjk_font in spec_lib.collect_required_fonts(spec):   # 遍历规格里的字体槽位
            matched = [n for n in seen_names if spec_lib.font_name_matches(n, actual)]     # 找出命中的 PDF 字体
            is_body = use.startswith("正文")                                    # 是不是正文字体
            if matched:                                                          # 命中了
                report.ok(f"{use}「{actual}」已在 PDF 中确认（实际字体 {matched[0]}）")     # 记录通过
            elif is_body:                                                        # 正文字体没命中
                report.fail(f"{use}要求「{actual}」，但 PDF 里找不到对应字体，"
                            f"实际内嵌的是 {'、'.join(seen_names[:8])} —— 说明被 LibreOffice 替换了。"
                            f"请把该字体装进 LibreOffice 能读到的字体目录后重新生成 PDF")   # 记录失败
            else:                                                                # 其他槽位没命中
                report.warn(f"{use}「{actual}」未在 PDF 中出现（该级可能没用到，也可能被 LibreOffice 替换了，建议看一眼渲染图）")   # 记录待确认
    # 关键检查：查「真正参与排字的字体」，而不只是「资源表里列了哪些字体」。
    #
    # 为什么必须补这一条：上一项检查读的是 PDF 的字体资源表，而 LibreOffice 会把
    # 根本没用到、甚至只是内部备用的字体也写进资源表（实测列了 LinuxLibertineG，零字形使用）。
    # 于是「资源表里有规格要求的字体」与「正文真的用这个字体排」是两回事，中间有个洞：
    # 实测漏报事故 —— 规格声明中文用 Songti SC，题注那一处脚本漏了字体解析、写的是「宋体」，
    # 本机没有宋体，LibreOffice 静默换成 PingFangHK 去排 4 条表题，而资源表里 Songti SC 也在，
    # 检查全绿、人却看得出来表题字体不对。这类问题只能从文本 span 里读字体才查得出。
    #
    # 判定口径：把「渲染时真的排了字的字体」逐个对规格声明的字体；对不上的，
    # 若是 LibreOffice 自带的符号/噪声字体（白名单）就放过，其余记「需确认」并附上页码与例字，
    # 让人一眼能判断这是不是换错了字。
    rendered = {}                                    # 字体名 -> {页码集合, 中文例字, 西文例字}
    cjk_pattern = re.compile(r"[\u4e00-\u9fff]")     # 中文判定正则
    for page_number, page in enumerate(document, start=1):            # 逐页扫描
        for block in page.get_text("dict")["blocks"]:                 # 遍历文本块
            if block.get("type") != 0:                                # 非文本块（图片）
                continue                                              # 跳过
            for line in block.get("lines", []):                       # 遍历行
                for span in line.get("spans", []):                    # 遍历 span（字体信息在这一级）
                    span_text = (span.get("text") or "").strip()      # 取该 span 的文字
                    if not span_text:                                 # 空白的 span 没在排字
                        continue                                      # 跳过
                    font_name = span.get("font") or ""                # 取该 span 的字体名
                    if not font_name:                                 # 读不到字体名
                        continue                                      # 跳过
                    entry = rendered.setdefault(font_name, {"pages": [], "cjk": "", "latin": ""})   # 初始化记录
                    if page_number not in entry["pages"]:             # 该字体首次出现在这一页
                        entry["pages"].append(page_number)            # 记下页码
                    if cjk_pattern.search(span_text):                 # 这段文字含中文
                        if not entry["cjk"]:                          # 还没记过中文例字
                            entry["cjk"] = span_text[:12]             # 记下例字，最多 12 字
                    elif not entry["latin"]:                          # 纯西文
                        if not entry["latin"]:                        # 还没记过西文例字
                            entry["latin"] = span_text[:12]           # 记下例字
    if rendered:                                                          # 读到了实际排字的字体
        declared = [actual for _use, _required, actual, _is_cjk in spec_lib.collect_required_fonts(spec)]   # 规格声明的字体名
        unexpected = []                                                   # 未声明却真的在排字的字体
        for font_name, info in sorted(rendered.items()):                  # 逐个核对实际用到的字体
            if any(spec_lib.font_name_matches(font_name, name) for name in declared):   # 是规格声明过的
                continue                                                  # 通过
            if spec_lib.is_builtin_render_font(font_name):                # 是 LibreOffice 自带的符号/噪声字体
                continue                                                  # 通过
            unexpected.append((font_name, info))                          # 记为「未声明却在排字」
        if unexpected:                                                    # 存在可疑字体
            for font_name, info in unexpected:                            # 逐条报告
                pages_text = "、".join(str(p) for p in info["pages"][:6])  # 取前 6 个页码
                if len(info["pages"]) > 6:                                # 页码很多
                    pages_text += " 等"                                    # 省略后续页码
                sample = info["cjk"] or info["latin"]                     # 优先用中文例字做证据
                kind = "中文" if info["cjk"] else "西文"                    # 说明排的是中文还是西文
                report.warn(f"字体「{font_name}」在正文里真的排了{kind}（第 {pages_text} 页，例：「{sample}」），"
                            f"但规格卡里没声明它 —— 说明这一处被 LibreOffice 换过字，"
                            f"请对照渲染图确认；确属换字就补装字体或指定 resolved 后重新生成")   # 记录待确认
        else:                                                             # 没有可疑字体
            report.ok(f"PDF 里真正参与排字的字体共 {len(rendered)} 个，全部是规格声明的或 LibreOffice 自带的符号字体")   # 记录通过
    # 按规格核对页边距（用文本框坐标近似判断）
    page_cfg = spec.get("page") or {}                # 取页面配置
    if page_cfg.get("margin_top_mm") and document.page_count:   # 若设置了上边距
        first_page = document[0]                      # 取第一页
        page_height_pt = first_page.rect.height       # 取页面高度（磅）
        bottom_limit = page_height_pt - spec_lib.mm_to_pt(page_cfg.get("margin_bottom_mm", 35))   # 排除页脚区域的界线
        top_limit = spec_lib.mm_to_pt(page_cfg["margin_top_mm"])   # 上边距的磅值，用来划出页眉区
        # 要同时排掉页脚块（在下方）和页眉块（在上方）。
        # 实测踩过的坑：只排页脚、不排页眉，页眉文字正好落在上边距以内，被当成了「正文首块」，
        # 于是报「首个文本块距页顶 13.8mm，与规格 20mm 不符」—— 而实测正文首块在 24.6mm，
        # 页边距其实是正确的。校验脚本冤枉了生成脚本，会把人引到错的方向去改。
        all_blocks = first_page.get_text("blocks")    # 本页全部文本块
        header_blocks = [b for b in all_blocks if b[3] <= top_limit]   # 完全落在上边距之内的块 = 页眉
        body_blocks = [b for b in all_blocks if b[3] <= bottom_limit and b[3] > top_limit]   # 正文区（页眉页脚都排除）
        if body_blocks:                               # 若有正文块
            top_mm = min(b[1] for b in body_blocks) / 72 * 25.4   # 取最靠上的正文块并换算成毫米
            expected = float(page_cfg["margin_top_mm"])   # 期望的上边距
            # 公文版式里首个文本块是红头，按 GB/T 9704 §7.2.4 它位于版心上边缘之下 35mm，
            # 所以期望位置要把这段偏移加上；不加会把正确的公文误判成「页边距未生效」
            masthead_cfg = spec.get("masthead") or {}   # 取版头配置
            if masthead_cfg.get("enabled"):             # 若启用了红头
                expected += float(masthead_cfg.get("top_offset_mm") or 0)   # 加上红头的上边缘偏移
            # 判断标准：允许向上浮动 5mm（段前距、字体度量差异、红头定位的近似误差），
            # 向下浮动 25mm（标题等要素自身带段前距），超出区间才算边距出错
            if expected - 5 <= top_mm <= expected + 25:   # 在合理区间内
                note = ""                             # 附注：说明页眉区被排除掉了多少
                if header_blocks:                     # 确实有页眉块
                    header_mm = min(b[1] for b in header_blocks) / 72 * 25.4   # 页眉距页顶的距离
                    note = f"（已排除 {len(header_blocks)} 个页眉块，页眉在 {header_mm:.1f}mm 处）"   # 组装说明
                report.ok(f"正文首块距页顶约 {top_mm:.1f}mm，与规格 {expected}mm 相符{note}")   # 记录通过
            else:                                     # 超出容差
                report.fail(f"正文首块距页顶 {top_mm:.1f}mm，与规格 {expected}mm 不符，页边距可能未生效")   # 记录失败
    # 关键检查：正文页码必须连续，不能每章都从 1 重来。
    #
    # 为什么必须查：页码连续性只有印出来才看得见，前面的检查全都查不出来 ——
    # 「页脚有没有 PAGE 域」查的是有没有设置，不是数出来对不对。
    # 实测漏报事故（大 32 开图书，14 页）：生成脚本给每个正文章节都写了 w:start=1，
    # 而书刊为「章从奇数页起」按章切节，于是每章页码都从 1 重来，印出来是 1、2、1、2……
    # 报告里 17 项全绿，人翻开一看每页都是「1」。
    #
    # 判定口径：取每页页脚区的数字，要求「后一页的页码 = 首页码 + 两页之间的页数差」。
    # 这样处理空白页 —— 章从奇数页起会插入空白页，实测空白页照样占号但不印页脚
    # （本稿第 4 页空白，第 3 页 1、第 5 页 3，差 2 页正好对应 +2），
    # 若按「必须连号」判就会把正确版面误判成缺陷。
    page_number_cfg = (spec.get("footer") or {}).get("page_number") or {}   # 取页码配置
    if page_number_cfg.get("enabled") and document.page_count:              # 规格要求编页码才查
        margin_bottom = spec_lib.mm_to_pt(page_cfg.get("margin_bottom_mm", 35))   # 下边距磅值
        numbered = []                                          # [(页码序号, 页脚数字)]
        for page_index, page in enumerate(document, start=1):  # 逐页扫页脚
            footer_limit = page.rect.height - margin_bottom    # 页脚区上界线
            footer_text = " ".join(b[4] for b in page.get_text("blocks") if b[3] > footer_limit)   # 页脚文字
            found = re.findall(r"\d+", footer_text)             # 页脚里的数字
            if found:                                          # 有页码
                numbered.append((page_index, int(found[0])))   # 取第一个数字（页码通常在最前）
        if len(numbered) >= 2:                                 # 至少两页有页码才谈得上连续
            first_index, first_number = numbered[0]            # 首页码作为基准
            broken = []                                        # 不连续的页码
            for page_index, number in numbered[1:]:            # 逐页核对
                expected = first_number + (page_index - first_index)   # 按页差推算应有的页码
                if number != expected:                         # 页码对不上
                    broken.append((page_index, number, expected))   # 记下来
            if broken:                                         # 存在断号/重号
                detail = "；".join(f"第 {p} 页印的是 {n}（按连续推算应为 {e}）" for p, n, e in broken[:5])   # 组装证据
                report.fail(f"正文页码不连续：{detail}。常见原因是每个章节都被写入了起始页码，"
                            f"导致每章都从 1 重来；请检查规格卡 footer.page_number 与生成脚本的分节逻辑")   # 记录失败
            else:                                              # 页码连续
                report.ok(f"正文页码连续：第 {first_index} 页起为 {first_number}，"
                          f"末页（第 {numbered[-1][0]} 页）为 {numbered[-1][1]}，共 {len(numbered)} 页带页码")   # 记录通过
        elif numbered:                                         # 只有一页有页码
            report.ok(f"PDF 只有 1 页带页码（第 {numbered[0][0]} 页，页码 {numbered[0][1]}），无需核对连续性")   # 记录通过
        else:                                                  # 一页页码都没有
            report.warn("规格要求编页码，但页脚区一个数字都没检出，请打开渲染图确认页码是否真的排上了")   # 记录待确认
    # 实测「章是否真的落在奇数页」。
    # 为什么不只信 DOCX 里的分节符：分节符写对不等于排出来对 ——
    # 最典型的翻车方式是导出时把空白页丢掉（LibreOffice 默认如此，实测 16 页导成 12 页），
    # 页数一变，后面每一页的奇偶整体错位，章就从奇数页滑到了偶数页。
    # 所以这里直接量真实 PDF：找正文区里字号等于章标题字号的块，看它落在奇数页还是偶数页。
    chapter_cfg = spec_lib.resolve_heading(spec.get("headings") or {},
                                            spec_lib.chapter_heading_level(spec))   # 取「章」的配置
    chapter_size = float(chapter_cfg.get("size_pt") or 0)   # 章标题字号
    if chapter_cfg.get("start_on_odd_page") and chapter_size and document.page_count:   # 规格要求从奇数页起
        top_limit = spec_lib.mm_to_pt((spec.get("page") or {}).get("margin_top_mm") or 0)   # 排除页眉的界线
        chapter_pages = []                           # 找到的章标题落点（页号, 文字）
        even_pages = []                              # 其中落在偶数页的章
        for page_number, page in enumerate(document, start=1):   # 逐页找章标题
            for block in page.get_text("dict")["blocks"]:        # 遍历文本块
                if block.get("type") != 0 or block["bbox"][3] <= top_limit:   # 排除图片与页眉
                    continue                             # 跳过
                sizes = [span["size"] for line in block["lines"] for span in line["spans"]]   # 块内字号
                if not sizes or max(sizes) < chapter_size - 0.5:   # 不是章标题
                    continue                             # 跳过
                text_of_block = "".join(span["text"] for line in block["lines"]
                                        for span in line["spans"]).strip()   # 块文字
                if not text_of_block:                    # 空块没有意义
                    continue                             # 跳过
                chapter_pages.append((page_number, text_of_block[:20]))   # 记下这一章的落点
                if page_number % 2 == 0:                 # 章落在偶数页
                    even_pages.append((page_number, text_of_block[:20]))   # 单独记下来
                break                                    # 一页最多一个章标题
        if not chapter_pages:                        # 通篇没找到章标题
            # 稿子本来就没有章（比如整篇只有正文），这项无从核对。
            # 记「跳过」而不是「通过」—— 不能拿「什么都没查到」冒充「查过了且没问题」。
            report.skip("PDF 里没有找到章标题，无从核对「章从奇数页起」")   # 记录跳过
        elif even_pages:                             # 有章落在偶数页
            detail = "、".join(f"第 {page} 页「{name}」" for page, name in even_pages[:6])   # 组装明细
            report.warn(f"「章从奇数页起」在 PDF 里没有生效：{detail} 落在偶数页。"
                        f"最常见的原因是导出时丢掉了空白页（LibreOffice 默认行为，页数一少奇偶就整体错位）；"
                        f"本 skill 的 scripts/build_pdf.py 已显式保留空白页，"
                        f"若这份 PDF 不是它生成的，请换它重新导出后再核对")   # 记录为待确认
        else:                                        # 全部落在奇数页
            report.ok(f"各章均落在奇数页，与规格一致（共 {len(chapter_pages)} 章）")   # 记录通过
    report.print(path)                                # 打印报告
    return report                                     # 返回报告

# CSS 通用字族名：字体栈最后一项必须是其中之一，浏览器才不会退化成难看的默认字体
GENERIC_FAMILIES = {"sans-serif", "serif", "monospace", "system-ui", "cursive", "fantasy"}   # 通用字族集合

# 判断一条 font-family 的值是否为合规的字体栈（末位是通用字族）
def font_family_is_stack(value):
    last = value.split(",")[-1].strip().strip("'\"")   # 取字体栈的最后一项并去掉引号
    return last.lower() in GENERIC_FAMILIES            # 末位是通用字族才返回真

# 把产物里所有内联样式拆成一条条声明，并把每条声明里的连续空白压成单个空格。
# 这样做是为了能用「字面量相等」判断某条样式是否真的写进了文件，
# 而不是靠模糊的正则去猜，也不会因为生成时多一个空格就误判为不合格。
def collect_declarations(raw):
    declarations = set()                                          # 用集合去重，只看「有没有这条声明」
    for attr in re.findall(r'style="([^"]*)"', raw):              # 逐个取出 style 属性
        for piece in attr.split(";"):                             # 按分号拆成单条 CSS 声明
            piece = re.sub(r"\s+", " ", piece.strip())            # 去掉首尾空白并把内部空白压成一个空格
            if piece:                                             # 跳过空片段
                declarations.add(piece)                           # 收集该声明
    return declarations                                           # 返回声明集合

# 校验公众号 HTML：核对样式是否全部内联、关键参数是否与规格一致
def verify_html(path, spec):
    report = Report()                                             # 创建报告
    if not os.path.exists(path):                                  # 产物不存在
        report.fail(f"找不到文件：{path}")                          # 记录失败
        report.print(path)                                        # 打印报告
        return report                                             # 返回报告
    with open(path, encoding="utf-8", errors="ignore") as handle:  # 以 UTF-8 打开产物
        raw = handle.read()                                       # 读取全文
    if not raw.strip():                                           # 内容为空
        report.fail("HTML 是空文件")                                # 记录失败
        report.print(path)                                        # 打印报告
        return report                                             # 返回报告
    declarations = collect_declarations(raw)                      # 收集全部内联样式声明
    lowered = {item.lower() for item in declarations}              # 声明的小写副本，用于忽略大小写比对
    if raw.lstrip().startswith("<!DOCTYPE html>"):                 # 有文档类型声明
        report.ok("存在 <!DOCTYPE html> 声明")                      # 记录通过
    else:                                                         # 缺少声明
        report.fail("缺少 <!DOCTYPE html> 声明，部分编辑器会按怪异模式解析")   # 记录失败
    if re.search(r'charset\s*=\s*"?utf-8', raw, re.I):             # 声明了 UTF-8 编码（兼容两种写法）
        report.ok("已声明 charset=utf-8，中文不会乱码")               # 记录通过
    else:                                                         # 未声明编码
        report.fail("未声明 charset=utf-8，粘贴后可能中文乱码")         # 记录失败
    if "<style" in raw.lower():                                    # 出现 style 标签
        report.fail("存在 <style> 标签，公众号编辑器会整段丢弃，样式必须内联")   # 记录失败
    else:                                                         # 没有 style 标签
        report.ok("不含 <style> 标签（公众号会丢弃这类样式）")           # 记录通过
    if re.search(r"\sclass\s*=", raw):                            # 出现 class 属性
        report.fail("存在 class 属性，公众号不加载外部样式表，样式会掉")     # 记录失败
    else:                                                         # 没有 class 属性
        report.ok("不含 class 属性，样式全部内联")                     # 记录通过
    cfg = build_html.html_config(spec)                             # 复用生成脚本解析出的参数，包含各默认值
    html_cfg = spec.get("html") or {}                              # 取 html 段
    if html_cfg.get("allow_external_links"):                       # 规格允许保留外链
        report.skip("规格允许保留外链，未做外链检查")                     # 记录跳过
    elif re.search(r"<a\s", raw):                                  # 产物里出现 a 标签
        report.fail("正文中存在 <a> 链接，但规格要求去掉外链（公众号正文不放外链）")   # 记录失败
    else:                                                         # 没有外链
        report.ok("正文不含外链，符合公众号正文限制")                     # 记录通过
    if f"max-width:{cfg['max_width_px']}px" in declarations:        # 正文宽度上限
        report.ok(f"正文宽度上限已写入：{cfg['max_width_px']}px")        # 记录通过
    else:                                                         # 未写入
        report.fail(f"未找到正文宽度上限 {cfg['max_width_px']}px")       # 记录失败
    if f"font-size:{cfg['body_size']}px" in declarations:           # 正文字号
        report.ok(f"正文字号已写入：{cfg['body_size']}px")             # 记录通过
    else:                                                         # 未写入
        report.fail(f"未找到正文字号 {cfg['body_size']}px，读者拿到的字号会是默认值")   # 记录失败
    if f"line-height:{cfg['line_height']}" in declarations:         # 行高
        report.ok(f"行高已写入：{cfg['line_height']}")                 # 记录通过
    else:                                                         # 未写入
        report.fail(f"未找到行高 {cfg['line_height']}")                # 记录失败
    if f"color:{str(cfg['color']).lower()}" in lowered:             # 字色，忽略大小写
        report.ok(f"正文字色已写入：{cfg['color']}")                   # 记录通过
    else:                                                         # 未写入
        report.fail(f"未找到正文字色 {cfg['color']}")                  # 记录失败
    expected_indent = f"text-indent:{cfg['indent']}em" if cfg["indent"] else "text-indent:0"   # 期望的首行缩进
    if "<p" not in raw:                                           # 产物里没有任何正文段落（例如通篇是表格）
        report.skip("产物中没有正文段落，段落缩进无需核对")                 # 记录跳过
    elif expected_indent in declarations:                          # 段落区分方式
        report.ok(f"段落区分方式已按规格写入：{expected_indent}")          # 记录通过
    else:                                                         # 未写入
        report.fail(f"未找到段落区分设置，期望 {expected_indent}")        # 记录失败
    font_families = [item.split(":", 1)[1] for item in declarations if item.lower().startswith("font-family:")]   # 取全部字体族声明
    bad_stacks = [item for item in font_families if not font_family_is_stack(item)]   # 筛出末位不是通用字族的写法
    if not font_families:                                          # 没有字体族声明
        report.fail("正文容器没有设置 font-family，各平台会各显一套字体")     # 记录失败
    elif not bad_stacks:                                           # 全部是合规字体栈
        report.ok(f"字体使用系统字体栈（{len(font_families)} 处，末位均为通用字族）")   # 记录通过
    else:                                                         # 有非字体栈的写法
        report.fail(f"字体族末位不是通用字族：{bad_stacks}，缺兜底时平台会退回难看的默认字体")   # 记录失败
    east_asian = ((spec.get("fonts") or {}).get("body") or {}).get("east_asian")   # 规格卡指定的中文字体
    if east_asian and str(east_asian) in raw:                       # 产物里硬写了具体中文字体
        report.fail(f"产物中出现具体字体名「{east_asian}」：公众号不加载该字体，应改用系统字体栈")   # 记录失败
    else:                                                         # 没有硬指定
        report.ok("未硬指定具体中文字体，符合公众号限制")                    # 记录通过
    if re.search(r"[\u4e00-\u9fff]", raw):                         # 产物里有中文
        report.ok("产物中检测到中文正文")                                # 记录通过
    else:                                                         # 没有中文
        report.fail("产物中没有中文字符，可能是源文件没被正确读取")             # 记录失败
    if "<table" in raw:                                            # 产物里有表格
        # 表格对齐按「一致性」核对，而不是照着规格重算一遍：
        # 重算需要知道源 Markdown 里的对齐标记，校验器看不到源文件，重算会误报。
        # 这里查三件真正会出错的事：同一列内对齐是否跳变、对齐值是否合法、表头是否与该列脱节。
        tables = re.findall(r"<table\b.*?</table>", raw, re.S)     # 逐个取出表格
        problems = []                                              # 收集问题
        column_notes = []                                          # 每列的对齐摘要
        for table_index, table_html in enumerate(tables, 1):       # 遍历每个表格
            header_aligns = {}                                      # 表头各列的对齐
            column_aligns = {}                                      # 数据格每列的对齐集合
            for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table_html, re.S):   # 遍历每一行
                cells = re.findall(r"<(th|td)\b([^>]*)>(.*?)</\1>", row_html, re.S)   # 取行内单元格
                for col_index, (tag_name, attrs, content) in enumerate(cells):   # 逐格
                    style_match = re.search(r'style="([^"]*)"', attrs)   # 取 style 属性
                    style_text = style_match.group(1) if style_match else ""   # 没有样式属性时视为空串
                    align_match = re.search(r"text-align:\s*([a-z]+)", style_text)   # 取对齐声明
                    align = align_match.group(1) if align_match else "未设置"   # 没写对齐时记为「未设置」
                    if tag_name == "th":                            # 表头单元格
                        header_aligns[col_index] = align            # 记录表头对齐
                    else:                                           # 数据单元格
                        column_aligns.setdefault(col_index, set()).add(align)   # 记录该列出现过的对齐值
            for col_index in sorted(column_aligns):                  # 逐列检查
                values = column_aligns[col_index]                    # 该列出现过的对齐值
                name = f"第 {table_index} 个表第 {col_index + 1} 列"    # 定位用的名字
                if len(values) > 1:                                 # 同一列里对齐方式不统一
                    problems.append(f"{name}列内对齐跳变：{sorted(values)}，同一列必须整列统一")   # 记录问题
                    continue                                        # 不用再查表头
                data_align = sorted(values)[0]                       # 该列统一后的对齐
                header_align = header_aligns.get(col_index, "未设置")   # 该列表头的对齐
                if header_align not in (cfg["header_align"], data_align):   # 表头既不按规格也没跟随该列
                    problems.append(f"{name}表头对齐 {header_align} 与该列数据对齐 {data_align} 脱节")   # 记录问题
                column_notes.append(f"{name}={data_align}")          # 记录摘要
        if problems:                                                # 有问题
            report.fail("表格对齐有 " + str(len(problems)) + " 处问题：" + "；".join(problems[:3]))   # 记录失败
        elif column_notes:                                          # 全部一致
            report.ok("表格对齐整列统一，表头与数据同轴（" + "，".join(column_notes[:4]) + ("…" if len(column_notes) > 4 else "") + "）")   # 记录通过
        else:                                                       # 表格没有数据行
            report.skip("表格没有数据行，数据格对齐无需核对")                  # 记录跳过
        # 框线也要量：规格写全框线、产物却是三线表，属于「改了规格没生效」，必须报出来。
        declared_style = cfg["table_style"]                     # 规格声明的线型
        if declared_style == "grid":                            # 规格要全框线
            missing_grid = [str(index) for index, table_html in enumerate(tables, 1)   # 逐张检查
                            if "border:1px solid" not in table_html]   # 没画四边黑线的表
            if missing_grid:                                    # 有没照做的
                report.fail("第 " + "、".join(missing_grid) + " 张表：规格要求全框线，产物里却没有四边框线")   # 记为失败
            else:                                               # 全部照做了
                report.ok("表格按规格画了全框线")                     # 记录通过
    else:                                                          # 产物里没有表格
        report.skip("产物中不含表格，表格对齐无需核对")                       # 记录跳过
    if "<img" in raw:                                              # 产物里有图片
        image_cfg = cfg["image"] or {}                             # 取图片配置
        width_value = str(image_cfg.get("width", "100%"))          # 规格要求的图片宽度
        if f"width:{width_value}" in declarations:                 # 图片宽度写入
            report.ok(f"图片宽度按规格写入：{width_value}")              # 记录通过
        else:                                                      # 未写入
            report.fail(f"未找到图片宽度设置 {width_value}")              # 记录失败
        image_count = len(re.findall(r"<img\b", raw))              # 统计图片数量
        report.skip(f"正文含 {image_count} 张图片：粘贴到公众号后需要用户重新上传到素材库")   # 记录跳过并提醒
    else:                                                          # 产物里没有图片
        report.skip("产物中不含图片")                                   # 记录跳过
    report.print(path)                                             # 打印报告
    return report                                                  # 返回报告

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="核对产物是否符合规格卡")   # 构造参数解析器
    parser.add_argument("--spec", required=True, help="规格卡 YAML 路径")    # 规格卡参数
    parser.add_argument("--docx", help="待检查的 DOCX 路径")                 # DOCX 参数
    parser.add_argument("--pdf", help="待检查的 PDF 路径")                   # PDF 参数
    parser.add_argument("--html", help="待检查的公众号 HTML 路径")            # HTML 参数
    args = parser.parse_args()                                              # 解析参数
    spec = spec_lib.load_spec(args.spec)                                    # 读取规格卡
    failed = 0                                                              # 失败计数
    if args.docx:                                                           # 若提供 DOCX
        failed += len(verify_docx(args.docx, spec).failed)                  # 累加失败数
    if args.pdf:                                                            # 若提供 PDF
        failed += len(verify_pdf(args.pdf, spec).failed)                    # 累加失败数
    if args.html:                                                           # 若提供 HTML
        failed += len(verify_html(args.html, spec).failed)                  # 累加失败数
    return 1 if failed else 0                                               # 有失败返回 1

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                                # 用返回值作为退出码

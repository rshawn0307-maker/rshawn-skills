#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成人教版体育试讲备考讲义 Word 文档
覆盖01~10共10个项目、108个子技术

路径说明：脚本顶部 BASE_DIR / OUTPUT_PATH 使用 <项目根> 占位符
（原为旧 Windows 机器的 C:/Users/keira/... 路径），运行前请替换为本机实际路径。
"""

import os
import re
import glob
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

# === Configuration ===
BASE_DIR = r"<项目根>\01-Projects\试讲稿项目-进行中\人教版"
OUTPUT_PATH = r"<项目根>\01-Projects\试讲稿项目-进行中\人教版体育试讲备考讲义_v1.0.docx"

PROJECTS = [
    ("01", "篮球",   "01篮球"),
    ("02", "排球",   "02排球"),
    ("03", "足球",   "03足球"),
    ("04", "乒乓球", "04乒乓球"),
    ("05", "羽毛球", "05羽毛球"),
    ("06", "体操",   "06体操"),
    ("07", "田径",   "07田径"),
    ("08", "体能",   "08体能"),
    ("09", "健康课程","09健康课程"),
    ("10", "武术",   "10武术"),
]

INFO_BOX_BG   = "DAEEF3"
HEADER_ROW_BG = "D6E4F0"
FONT_NAME     = "微软雅黑"
FONT_SIZE     = Pt(10.5)
TOTAL_WIDTH_CM = 16.0  # total table width in cm (A4 with 2.5cm margins)


# === Utility Functions ===

def shade_cell(cell, color_hex):
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}" w:val="clear"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def set_table_fixed_layout(table):
    """Force table to fixed layout so column widths are respected."""
    tbl = table._tbl
    tblPr = tbl.tblPr
    for elem in tblPr.findall(qn('w:tblLayout')):
        tblPr.remove(elem)
    layout = parse_xml(f'<w:tblLayout {nsdecls("w")} w:type="fixed"/>')
    tblPr.append(layout)


def set_col_widths(table, widths_cm):
    """Set column widths on every cell (Word requires per-cell width in fixed layout)."""
    for row in table.rows:
        for j, w in enumerate(widths_cm):
            if j < len(row.cells):
                row.cells[j].width = Cm(w)


def compute_col_widths(rows, n_cols):
    """Compute column widths based on content.
    Short columns get enough width to fit on one line; long columns wrap naturally."""
    CHAR_W = 0.375   # cm per Chinese char at 10.5pt
    PADDING = 0.5     # cell padding total
    FIT_CAP = 8       # chars beyond this will wrap anyway, don't over-allocate

    max_visual_lens = [0] * n_cols
    for row in rows:
        for j in range(min(len(row), n_cols)):
            for line in row[j].split('\n'):
                vl = sum(2 if ord(c) > 127 else 1 for c in line)
                if vl > max_visual_lens[j]:
                    max_visual_lens[j] = vl

    if sum(max_visual_lens) == 0:
        return [TOTAL_WIDTH_CM / n_cols] * n_cols

    min_widths = []
    for vl in max_visual_lens:
        chars = min(vl / 2.0, FIT_CAP)
        min_widths.append(max(chars * CHAR_W + PADDING, 1.5))

    if sum(min_widths) > TOTAL_WIDTH_CM:
        widths = list(min_widths)
        while sum(widths) > TOTAL_WIDTH_CM:
            max_idx = widths.index(max(widths))
            widths[max_idx] -= 0.1
            if widths[max_idx] < 1.5:
                widths[max_idx] = 1.5
                break
        return widths

    remaining = TOTAL_WIDTH_CM - sum(min_widths)
    total_content = sum(max_visual_lens)
    widths = []
    for i in range(n_cols):
        extra = (max_visual_lens[i] / total_content) * remaining if total_content > 0 else 0
        widths.append(min_widths[i] + extra)

    scale = TOTAL_WIDTH_CM / sum(widths)
    return [w * scale for w in widths]


def set_run_font(run, size=None, bold=False, color=None):
    run.font.name = FONT_NAME
    run._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_NAME)
    if size:
        run.font.size = size
    run.font.bold = bold
    if color:
        run.font.color.rgb = color


def set_cell_font(cell, size=None, bold=False, color=None):
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            set_run_font(run, size, bold, color)


def parse_md_table(lines):
    rows = []
    for line in lines:
        line = line.strip()
        if line.startswith('|') and line.endswith('|'):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            rows.append(cells)
    rows = [r for r in rows if not all(re.match(r'^[-:]+$', c) for c in r)]
    return rows


def add_paragraph_with_commands(doc, text):
    p = doc.add_paragraph()
    if '[口令]' not in text:
        run = p.add_run(text)
        set_run_font(run)
        return p
    parts = text.split('[口令]')
    for i, part in enumerate(parts):
        if i > 0:
            run = p.add_run('[口令]')
            set_run_font(run, bold=True)
        if part:
            run = p.add_run(part)
            set_run_font(run)
    return p


# === Parsing Functions ===

def find_subtechs(project_dir):
    subtechs = []
    for script_path in sorted(glob.glob(os.path.join(project_dir, "*_试讲稿_v1.0.md"))):
        filename = os.path.basename(script_path)
        name_no_ext = filename.replace('_试讲稿_v1.0.md', '')
        parts = name_no_ext.split('_', 3)
        if len(parts) < 4:
            continue
        proj_num, proj_name, subtech_id, subtech_name = parts
        design_filename = f"{proj_num}_{proj_name}_{subtech_id}_{subtech_name}_教学设计_v1.0.md"
        design_path = os.path.join(project_dir, design_filename)
        subtechs.append({
            'id': subtech_id,
            'name': subtech_name,
            'script_path': script_path,
            'design_path': design_path,
        })
    return subtechs


def parse_teaching_design(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    result = {'objectives': '', 'key_points': '', 'difficult_points': '', 'venue_equipment': ''}

    in_design_table = False
    for line in lines:
        stripped = line.strip()
        if '教学设计说明' in stripped and stripped.startswith('#'):
            in_design_table = True
            continue
        if in_design_table:
            if stripped.startswith('#') and not stripped.startswith('|'):
                in_design_table = False
                continue
            if stripped.startswith('|'):
                cells = [c.strip() for c in stripped.split('|')[1:-1]]
                if len(cells) >= 2:
                    if '教学重点' in cells[0]:
                        result['key_points'] = cells[1]
                    elif '教学难点' in cells[0]:
                        result['difficult_points'] = cells[1]

    in_obj = False
    obj_lines = []
    for line in lines:
        stripped = line.strip()
        if '教学目标' in stripped and stripped.startswith('#'):
            in_obj = True
            continue
        if in_obj:
            if stripped.startswith('#') and not stripped.startswith('###') and '教学目标' not in stripped:
                break
            if stripped and not stripped.startswith('###'):
                obj_lines.append(stripped)
    result['objectives'] = '\n'.join(obj_lines)

    in_venue = False
    venue_lines = []
    for line in lines:
        stripped = line.strip()
        if '场地器材' in stripped and stripped.startswith('#'):
            in_venue = True
            continue
        if in_venue:
            if stripped.startswith('#'):
                break
            if stripped:
                venue_lines.append(stripped)
    result['venue_equipment'] = '\n'.join(venue_lines)

    return result


def parse_trial_script(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    body_elements = []
    score_anchors = []
    title = ''

    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        stripped = line.strip()

        if stripped.startswith('项目:') or stripped.startswith('项目：'):
            i += 1; continue
        if stripped.startswith('> 项目:') or stripped.startswith('> 项目：'):
            i += 1; continue
        if stripped.startswith('> 约束') or stripped.startswith('> 生成时间'):
            i += 1; continue

        if stripped.startswith('> 评分锚点'):
            anchor = stripped.replace('> 评分锚点：', '').replace('> 评分锚点:', '').strip()
            score_anchors.append(anchor)
            i += 1; continue

        if stripped == '---' or stripped == '***':
            i += 1; continue

        if stripped.startswith('# ') and not stripped.startswith('## '):
            title = stripped[2:].strip()
            i += 1; continue

        if stripped.startswith('#### '):
            body_elements.append(('heading4', stripped[5:].strip()))
            i += 1; continue
        if stripped.startswith('### '):
            body_elements.append(('heading3', stripped[4:].strip()))
            i += 1; continue
        if stripped.startswith('## '):
            body_elements.append(('heading2', stripped[3:].strip()))
            i += 1; continue

        if stripped.startswith('|'):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            rows = parse_md_table(table_lines)
            if rows:
                body_elements.append(('table', rows))
            continue

        if not stripped:
            i += 1; continue

        body_elements.append(('paragraph', stripped))
        i += 1

    return title, body_elements, score_anchors


# === Document Building Functions ===

def setup_styles(doc):
    style = doc.styles['Normal']
    style.font.name = FONT_NAME
    style.font.size = FONT_SIZE
    style.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_NAME)
    style.paragraph_format.line_spacing = 1.25
    style.paragraph_format.space_after = Pt(4)

    for level, size, color in [(1, Pt(18), RGBColor(0x1F,0x49,0x7D)),
                                (2, Pt(14), RGBColor(0x2E,0x74,0xB5)),
                                (3, Pt(12), RGBColor(0x4F,0x81,0xBD)),
                                (4, Pt(11), RGBColor(0x66,0x66,0x66))]:
        h = doc.styles[f'Heading {level}']
        h.font.name = FONT_NAME
        h.font.size = size
        h.font.bold = True
        h.font.color.rgb = color
        h.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_NAME)
        h.paragraph_format.space_before = Pt(10 if level <= 2 else 8)
        h.paragraph_format.space_after = Pt(4 if level <= 2 else 2)


def add_front_heading(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, size=Pt(18), bold=True, color=RGBColor(0x1F,0x49,0x7D))
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(6)
    return p


def add_front_subheading(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, size=Pt(14), bold=True, color=RGBColor(0x2E,0x74,0xB5))
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    return p


def add_cover_page(doc):
    for _ in range(6):
        doc.add_paragraph()
    for text, size, color, bold in [
        ('人教版体育试讲备考讲义', Pt(28), RGBColor(0x1F,0x49,0x7D), True),
        ('基于人教版《体育与健康》教师用书', Pt(14), RGBColor(0x66,0x66,0x66), False),
        ('v1.0', Pt(12), RGBColor(0x99,0x99,0x99), False),
        ('2026年8月', Pt(12), RGBColor(0x99,0x99,0x99), False),
    ]:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        set_run_font(run, size=size, bold=bold, color=color)
    for _ in range(4):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run('覆盖10个运动项目 · 108个子技术')
    set_run_font(run, size=Pt(12), color=RGBColor(0x99,0x99,0x99))
    doc.add_page_break()


def add_usage_instructions(doc):
    add_front_heading(doc, '使用说明')

    add_front_subheading(doc, '讲义结构')
    doc.add_paragraph('每个子技术包含三部分内容，按以下顺序阅读：')
    for text in [
        '设计要点卡片（蓝色信息框）—— 教学目标、教学重难点、场地器材，帮助快速建立教学认知框架。',
        '试讲稿正文 —— 可直接照念的完整试讲内容，包含简案大纲、四环节全文（开始/准备/基本/结束）、[口令]标记。',
        '评分检查清单 —— 该子技术所有评分锚点汇总，读完试讲稿后逐条自查。',
    ]:
        doc.add_paragraph(text, style='List Number')

    add_front_subheading(doc, '备考建议')
    for text in [
        '先读设计要点卡片，理解"教什么、为什么这么教"。',
        '通读试讲稿正文，感受10分钟试讲的节奏和内容密度。',
        '脱稿模拟试讲，用手机录音计时，控制在10分钟以内。',
        '对照评分检查清单，逐条核对是否覆盖，查漏补缺。',
    ]:
        doc.add_paragraph(text, style='List Number')

    add_front_subheading(doc, '时间约束')
    doc.add_paragraph('试讲总时长10分钟，各环节时长占比固定：')
    table = doc.add_table(rows=5, cols=3, style='Table Grid')
    table.autofit = False
    set_table_fixed_layout(table)
    for j, h in enumerate(['教学环节', '时长', '占比']):
        cell = table.cell(0, j)
        cell.text = h
        shade_cell(cell, HEADER_ROW_BG)
        set_cell_font(cell, bold=True)
    for i, row_data in enumerate([['开始部分','1分钟','10%'],['准备部分','2分钟','20%'],['基本部分','6分钟','60%'],['结束部分','1分钟','10%']]):
        for j, val in enumerate(row_data):
            cell = table.cell(i+1, j)
            cell.text = val
            set_cell_font(cell)
    set_col_widths(table, [8, 4, 4])

    add_front_subheading(doc, '字数范围')
    doc.add_paragraph('试讲稿字数范围为1800-2200字（按10分钟口语语速换算），超出范围需适当删减或补充。')

    add_front_subheading(doc, '导航方式')
    for text in [
        '目录页：文档开头的自动目录可点击跳转到对应项目。',
        '导航窗格：Word左侧导航窗格显示三级标题树（项目→子技术→环节），可展开折叠。',
        '页眉：每页页眉显示当前所在项目名称，方便定位。',
    ]:
        doc.add_paragraph(text, style='List Number')

    doc.add_page_break()


def add_scoring_criteria(doc):
    add_front_heading(doc, '通用评分标准')
    doc.add_paragraph('体育试讲评分采用六维度加权评分体系，满分5分。各维度及评分标准如下：')

    table = doc.add_table(rows=7, cols=5, style='Table Grid')
    table.autofit = False
    set_table_fixed_layout(table)
    for j, h in enumerate(['维度','权重','1分','3分','5分']):
        cell = table.cell(0, j)
        cell.text = h
        shade_cell(cell, HEADER_ROW_BG)
        set_cell_font(cell, bold=True)
    data = [
        ['教学设计合理性','20%','环节缺失或时长严重失衡','结构完整但缺乏层次','结构完整且层次清晰递进'],
        ['口令规范性','15%','多处模糊口令','口令基本清晰但欠精炼','口令准确精炼可直接执行'],
        ['安全组织','20%','存在安全隐患','安全但组织松散','安全且组织紧凑高效'],
        ['评分锚点覆盖率','15%','<60%','60-89%','≥90%'],
        ['差异化亮点','15%','无亮点','有1处亮点','≥2处创新且合理亮点'],
        ['可操作性','15%','考生无法直接使用','需少量调整可用','拿来即可直接照念'],
    ]
    for i, row_data in enumerate(data):
        for j, val in enumerate(row_data):
            cell = table.cell(i+1, j)
            cell.text = val
            set_cell_font(cell)
    set_col_widths(table, [3.0, 1.5, 4.0, 3.5, 4.0])

    doc.add_paragraph()
    add_front_subheading(doc, '评分锚点说明')
    doc.add_paragraph('每个子技术的试讲稿中内嵌评分锚点，本讲义将其汇总到每个子技术末尾的"评分检查清单"中。评分锚点覆盖以下评分项：')
    for item in [
        '教学组织 — 集合整队、分组练习、队形调动、回收器材',
        '安全管理 — 服装检查、见习生安排、热身提示、练习间距',
        '教态仪表 — 师生问好、精神面貌、示范姿态',
        '语言表达 — 情境导入、讲解清晰、评价反馈',
        '教法运用 — 探究学习、游戏设计、学练赛评完整链条',
        '讲解能力 — 技术要点准确、口诀化总结',
        '示范能力 — 示范面正确、站位合理',
        '错误纠正 — 集体纠正与个别纠正结合、纠错表',
        '教学设计 — 情境创设、区别对待、分层练习',
        '运动负荷 — 练习密度、运动密度、平均心率、放松活动',
        '综合素质 — 三维素养小结（运动能力/健康行为/体育品德）',
    ]:
        doc.add_paragraph(item, style='List Bullet')

    doc.add_page_break()


def add_toc(doc):
    add_front_heading(doc, '目录')
    paragraph = doc.add_paragraph()
    run = paragraph.add_run()
    run._r.append(parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="begin"/>'))
    run2 = paragraph.add_run()
    run2._r.append(parse_xml(f'<w:instrText {nsdecls("w")} xml:space="preserve"> TOC \\o "1-2" \\h \\z \\u </w:instrText>'))
    run3 = paragraph.add_run()
    run3._r.append(parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="separate"/>'))
    run4 = paragraph.add_run('（请在Word中右键此处选择"更新域"以生成目录）')
    run4.font.color.rgb = RGBColor(0x99,0x99,0x99)
    run5 = paragraph.add_run()
    run5._r.append(parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="end"/>'))
    doc.add_page_break()


def add_info_box(doc, design_data):
    rows_data = []
    if design_data['objectives']:
        rows_data.append(('教学目标', design_data['objectives']))
    if design_data['key_points']:
        rows_data.append(('教学重点', design_data['key_points']))
    if design_data['difficult_points']:
        rows_data.append(('教学难点', design_data['difficult_points']))
    if design_data['venue_equipment']:
        rows_data.append(('场地器材', design_data['venue_equipment']))
    if not rows_data:
        return

    table = doc.add_table(rows=len(rows_data), cols=2, style='Table Grid')
    table.autofit = False
    set_table_fixed_layout(table)
    for i, (label, content) in enumerate(rows_data):
        cell = table.cell(i, 0)
        cell.text = label
        shade_cell(cell, INFO_BOX_BG)
        set_cell_font(cell, bold=True)

        cell = table.cell(i, 1)
        lines = content.split('\n')
        for j, line in enumerate(lines):
            if j == 0:
                cell.text = line
            else:
                cell.add_paragraph(line)
        set_cell_font(cell)
    set_col_widths(table, [2.5, 13.5])
    doc.add_paragraph()


def add_table_to_doc(doc, rows):
    if not rows:
        return
    n_cols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=n_cols, style='Table Grid')
    table.autofit = False
    set_table_fixed_layout(table)
    for i, row in enumerate(rows):
        for j in range(n_cols):
            cell = table.cell(i, j)
            if j < len(row):
                cell.text = row[j]
            set_cell_font(cell, bold=(i == 0))
            if i == 0:
                shade_cell(cell, HEADER_ROW_BG)
    widths = compute_col_widths(rows, n_cols)
    set_col_widths(table, widths)
    doc.add_paragraph()


def add_score_checklist(doc, anchors):
    if not anchors:
        return
    doc.add_heading('评分检查清单', level=3)
    items = []
    for anchor in anchors:
        parts = re.split(r'\s*[-—]\s*', anchor, 1)
        if len(parts) == 2:
            items.append((parts[0].strip(), parts[1].strip()))
        else:
            items.append(('', anchor))

    table = doc.add_table(rows=len(items)+1, cols=2, style='Table Grid')
    table.autofit = False
    set_table_fixed_layout(table)
    for j, h in enumerate(['评分项', '得分动作']):
        cell = table.cell(0, j)
        cell.text = h
        shade_cell(cell, HEADER_ROW_BG)
        set_cell_font(cell, bold=True)
    for i, (item, action) in enumerate(items):
        cell = table.cell(i+1, 0)
        cell.text = item
        set_cell_font(cell)
        cell = table.cell(i+1, 1)
        cell.text = action
        set_cell_font(cell)
    set_col_widths(table, [3.5, 12.5])


def add_trial_script_body(doc, body_elements):
    for elem in body_elements:
        if elem[0] == 'heading2':
            doc.add_heading(elem[1], level=3)
        elif elem[0] == 'heading3':
            doc.add_heading(elem[1], level=4)
        elif elem[0] == 'heading4':
            p = doc.add_paragraph()
            run = p.add_run(elem[1])
            set_run_font(run, bold=True)
        elif elem[0] == 'table':
            add_table_to_doc(doc, elem[1])
        elif elem[0] == 'paragraph':
            add_paragraph_with_commands(doc, elem[1])


def set_section_header(section, project_name):
    section.header.is_linked_to_previous = False
    header = section.header
    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    p.text = ''
    run = p.add_run(project_name)
    set_run_font(run, size=Pt(9), color=RGBColor(0x99,0x99,0x99))

    section.footer.is_linked_to_previous = False
    footer = section.footer
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.text = ''
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run._r.append(parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="begin"/>'))
    run2 = p.add_run()
    run2._r.append(parse_xml(f'<w:instrText {nsdecls("w")} xml:space="preserve"> PAGE </w:instrText>'))
    run3 = p.add_run()
    run3._r.append(parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="end"/>'))


# === Main ===

def main():
    print("开始生成人教版体育试讲备考讲义...")
    doc = Document()
    setup_styles(doc)

    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    print("  生成封面...")
    add_cover_page(doc)
    print("  生成使用说明...")
    add_usage_instructions(doc)
    print("  生成通用评分标准...")
    add_scoring_criteria(doc)
    print("  生成目录...")
    add_toc(doc)

    total = 0
    for proj_num, proj_name, proj_dir_name in PROJECTS:
        project_dir = os.path.join(BASE_DIR, proj_dir_name)
        if not os.path.isdir(project_dir):
            print(f"  警告：目录不存在 - {project_dir}")
            continue

        subtechs = find_subtechs(project_dir)
        print(f"  项目 {proj_num} {proj_name}：{len(subtechs)} 个子技术")

        new_section = doc.add_section(WD_SECTION.NEW_PAGE)
        set_section_header(new_section, f"{proj_num} {proj_name}")

        doc.add_heading(f"{proj_num} {proj_name}", level=1)

        for subtech in subtechs:
            total += 1
            print(f"    {subtech['id']} {subtech['name']}")

            doc.add_page_break()
            doc.add_heading(f"{subtech['id']} {subtech['name']}", level=2)

            try:
                if os.path.exists(subtech['design_path']):
                    design_data = parse_teaching_design(subtech['design_path'])
                    add_info_box(doc, design_data)
            except Exception as e:
                print(f"      警告：解析教学设计失败 - {e}")

            try:
                _, body_elements, score_anchors = parse_trial_script(subtech['script_path'])
                add_trial_script_body(doc, body_elements)
            except Exception as e:
                print(f"      警告：解析试讲稿失败 - {e}")

            try:
                if score_anchors:
                    add_score_checklist(doc, score_anchors)
            except Exception as e:
                print(f"      警告：生成评分清单失败 - {e}")

    print(f"\n总计处理 {total} 个子技术")
    print(f"保存到 {OUTPUT_PATH}")
    doc.save(OUTPUT_PATH)
    print("完成！")


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""
fill_trial_daily_post.py v1.0
==============================

「体育试讲设计每日一练」帖子生成脚本。

流程：
  1. agent 拆解教师用书某一个小教学环节，写到 scripts/pending_trial_daily.json
  2. 跑本脚本：读取与预检 -> 用 python-docx 从零构建品牌化 DOCX -> 自动验证
     -> 快照 -> 原子提交 -> 删 JSON

输入：scripts/pending_trial_daily.json
输出：desktop-attachments/2 体育试讲每日一练-帖子内容编辑模板.docx（原地覆盖）

JSON schema（硬性）：
  sport            str   运动项目（如 篮球）
  chapter          str   章节路径（如 第三章 篮球运动教学内容）
  segment_name     str   教学环节名称（封面大标题）
  segment_type     str   game/practice/fitness
  difficulty       str   难度（如 ★★★）
  figure           str   图例引用说明（可空，如 "图3-2-7、图3-2-8"）
  figure_images    list  图例图片路径（agent 用 extract_pdf_image.py 提取，可空）
  method           str   活动方法
  rules            str   规则
  intent           str   活动设计意图
  organization     str   活动组织形式
  errors           list  易犯错误与纠正 [["易犯错误","纠正方法"], ...]，仅 practice 必填
  lecture_script   str   试讲逐字稿全文
  cta              str   引流文案（须与固定引流段一致）
  hashtags         str   话题标签
"""

import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = Path(os.environ.get("TRIAL_DAILY_WORKSPACE", SCRIPT_DIR.parent)).expanduser().resolve()
PROJECT_SCRIPT_DIR = WORKSPACE / "scripts"
SOURCE_TEMPLATE = WORKSPACE / "模板文件" / "2 体育试讲每日一练-帖子内容编辑模板.docx"
TEMPLATE_PATH = WORKSPACE / "desktop-attachments" / "2 体育试讲每日一练-帖子内容编辑模板.docx"
PENDING_JSON = PROJECT_SCRIPT_DIR / "pending_trial_daily.json"
SNAPSHOT_DIR = PROJECT_SCRIPT_DIR / "_snapshots_trial"
MAX_SNAPSHOTS = 10

COVER_TITLE = "体育试讲设计每日一练"
DRAIN_TEXT = "关注我，每天一个体育试讲设计，帮你备考上岸"
NAVY = RGBColor(0x0B, 0x32, 0x89)
CYAN = RGBColor(0x9F, 0xD8, 0xE8)
DARK = RGBColor(0x33, 0x33, 0x33)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x1E, 0x7A, 0x3C)
FONT = "微软雅黑"

SEGMENT_TYPES = {
    "game": "游戏 / 比赛环节",
    "practice": "练习环节",
    "fitness": "体能游戏环节",
}


def take_snapshot():
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    if not TEMPLATE_PATH.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    snap = SNAPSHOT_DIR / f"snapshot_{ts}.docx"
    shutil.copy(TEMPLATE_PATH, snap)
    snaps = sorted(SNAPSHOT_DIR.glob("snapshot_*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in snaps[MAX_SNAPSHOTS:]:
        old.unlink()
    return snap


def _require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空字符串")
    return value


def load_pending():
    with open(PENDING_JSON, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("pending_trial_daily.json 顶层必须是对象")
    required = [
        "sport", "chapter", "segment_name", "segment_type", "difficulty",
        "figure", "figure_images", "method", "rules", "intent",
        "organization", "errors", "lecture_script", "cta", "hashtags",
    ]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"JSON 缺字段：{missing}")
    for k in ("sport", "chapter", "segment_name", "segment_type", "difficulty", "figure",
              "method", "rules", "intent", "organization", "lecture_script", "cta", "hashtags"):
        _require_text(data[k], k)
    if data["segment_type"] not in SEGMENT_TYPES:
        raise ValueError(f"segment_type 必须是 {list(SEGMENT_TYPES)} 之一")
    if not isinstance(data["figure_images"], list):
        raise ValueError("figure_images 必须是列表")
    for p in data["figure_images"]:
        if not os.path.isfile(p):
            raise ValueError(f"图例图片不存在：{p}")
    if not isinstance(data["errors"], list):
        raise ValueError("errors 必须是列表")
    for row in data["errors"]:
        if not isinstance(row, list) or len(row) != 2 or not all(str(c).strip() for c in row):
            raise ValueError("errors 每行必须是 [易犯错误, 纠正方法] 两个非空字符串")
    if data["segment_type"] == "practice" and not data["errors"]:
        raise ValueError("practice 环节必须提供易犯错误与纠正(errors)")
    if data["cta"].strip() != DRAIN_TEXT:
        raise ValueError("cta 与固定引流段不一致（不许改引流文案）")
    for label, value in [
        ("method", data["method"]), ("rules", data["rules"]), ("intent", data["intent"]),
        ("organization", data["organization"]), ("lecture_script", data["lecture_script"]),
    ]:
        for ch in ("：", ":", "——"):
            if ch in value:
                raise ValueError(f"{label} 不得含「{ch}」（去 AI 味铁律）")
    return data


# ---------- 底层样式工具 ----------

def _set_font(run, size=14, bold=False, color=DARK, name=FONT):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:eastAsia"), name)


def _shade_cell(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)
    tcPr.append(shd)


def _set_cell_margins(cell, top="200", left="200", bottom="200", right="200"):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = tcPr.find(qn("w:tcMar"))
    if tcMar is None:
        tcMar = OxmlElement("w:tcMar")
        tcPr.append(tcMar)
    for name, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        el = tcMar.find(qn("w:" + name))
        if el is None:
            el = OxmlElement("w:" + name)
            tcMar.append(el)
        el.set(qn("w:w"), val)
        el.set(qn("w:type"), "dxa")


def _cell_vertical_center(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    vAlign = OxmlElement("w:vAlign")
    vAlign.set(qn("w:val"), "center")
    tcPr.append(vAlign)


def _add_para(cell, text, size=14, bold=False, color=DARK, align=WD_ALIGN_PARAGRAPH.LEFT,
              space_after=4, space_before=0, line=None):
    p = cell if isinstance(cell, str) else cell.add_paragraph()
    if isinstance(cell, str):
        p = cell
    p.alignment = align
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(space_before)
    if line:
        pf.line_spacing = line
    run = p.add_run(text)
    _set_font(run, size=size, bold=bold, color=color)
    return p


def _body_para(doc, text, size=13, bold=False, color=DARK, space_after=8, line=1.3):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.line_spacing = line
    run = p.add_run(text)
    _set_font(run, size=size, bold=bold, color=color)
    return p


def _section_title(doc, text, color=NAVY):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(18)
    pf.space_after = Pt(10)
    run = p.add_run(text)
    _set_font(run, size=17, bold=True, color=color)
    # 底部加粗下边框
    pPr = p._element.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "12")
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), "0B3289")
    pBdr.append(bottom)
    pPr.append(pBdr)
    return p


# ---------- 构建 ----------

def build_cover(doc, data):
    """封面：整页深蓝底 + 浅青标题 + 项目标签 + 环节名 + 难度。"""
    section = doc.sections[0]
    section.top_margin = Cm(0)
    section.bottom_margin = Cm(0)
    section.left_margin = Cm(0)
    section.right_margin = Cm(0)
    # 封面页不显示页眉页脚，避免白色边距里出现品牌文字
    try:
        section.header.is_linked_to_previous = False
        section.footer.is_linked_to_previous = False
        for hp in section.header.paragraphs:
            for r in list(hp.runs):
                r._element.getparent().remove(r._element)
        for fp in section.footer.paragraphs:
            for r in list(fp.runs):
                r._element.getparent().remove(r._element)
    except Exception:
        pass

    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    _shade_cell(cell, "0B3289")
    _set_cell_margins(cell, top="200", left="400", bottom="200", right="400")
    _cell_vertical_center(cell)

    # 顶部：固定小标题
    _add_para(cell, "体师备考知识库 · 教师编面试", size=12, bold=True, color=CYAN,
              align=WD_ALIGN_PARAGRAPH.CENTER, space_before=60, space_after=30)
    # 大标题
    _add_para(cell, COVER_TITLE, size=30, bold=True, color=CYAN,
              align=WD_ALIGN_PARAGRAPH.CENTER, space_after=40)
    # 项目标签
    _add_para(cell, f"【{data['sport']}】{SEGMENT_TYPES[data['segment_type']]}",
              size=16, bold=True, color=WHITE, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=50)
    # 环节名
    _add_para(cell, data["segment_name"], size=24, bold=True, color=WHITE,
              align=WD_ALIGN_PARAGRAPH.CENTER, space_after=30)
    # 章节 + 难度
    _add_para(cell, data["chapter"], size=12, color=RGBColor(0xC9, 0xDD, 0xF0),
              align=WD_ALIGN_PARAGRAPH.CENTER, space_after=16)
    _add_para(cell, f"难度：{data['difficulty']}", size=13, bold=True,
              color=RGBColor(0xF0, 0xC8, 0x6C), align=WD_ALIGN_PARAGRAPH.CENTER, space_after=60)

    # 行高撑满整页（A4 高约 16840 twips，内容已垂直居中，不留空段）
    trPr = table.rows[0]._tr.get_or_add_trPr()
    trh = OxmlElement("w:trHeight")
    trh.set(qn("w:val"), "16000")
    trh.set(qn("w:hRule"), "atLeast")
    trPr.append(trh)


def build_content(doc, data):
    """正文：页眉 + 图例 + 环节拆解 + 试讲逐字稿 + 引流。"""
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)

    # 页眉（必须先断开与前节链接，否则品牌文字会写进封面节）
    header = section.header
    header.is_linked_to_previous = False
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hr = hp.add_run("体师备考知识库")
    _set_font(hr, size=10, bold=True, color=NAVY)

    # 页脚：页码
    footer = section.footer
    footer.is_linked_to_previous = False
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    fp._element.append(fld)
    for r in fp.runs:
        _set_font(r, size=9, color=RGBColor(0x88, 0x88, 0x88))

    # ===== 图例区 =====
    if data["figure_images"]:
        _section_title(doc, "图例直观")
        if data["figure"]:
            _body_para(doc, data["figure"], size=11, bold=True, color=GREEN, space_after=6)
        for img in data["figure_images"]:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run()
            run.add_picture(img, width=Cm(12.5))
            p.paragraph_format.space_after = Pt(8)

    # ===== 环节拆解 =====
    _section_title(doc, "环节拆解")

    def _field(label, value):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_after = Pt(8)
        pf.line_spacing = 1.3
        r1 = p.add_run(f"{label}｜")
        _set_font(r1, size=13, bold=True, color=NAVY)
        r2 = p.add_run(value)
        _set_font(r2, size=13, bold=False, color=DARK)

    _field("环节名称", data["segment_name"])
    _field("活动类型", SEGMENT_TYPES[data["segment_type"]])
    _field("活动方法", data["method"])
    _field("规则", data["rules"])
    _field("活动设计意图", data["intent"])
    _field("活动组织形式", data["organization"])

    # 易犯错误与纠正（仅 practice）
    if data["errors"]:
        _section_title(doc, "易犯错误与纠正")
        tbl = doc.add_table(rows=len(data["errors"]) + 1, cols=2)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tblPr = tbl._tbl.tblPr
        for child in list(tblPr):
            tblPr.remove(child)
        tblW = OxmlElement("w:tblW"); tblW.set(qn("w:type"), "auto"); tblW.set(qn("w:w"), "0")
        jc = OxmlElement("w:jc"); jc.set(qn("w:val"), "center")
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement("w:" + edge)
            el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "6")
            el.set(qn("w:color"), "8EAADB"); el.set(qn("w:space"), "0")
            borders.append(el)
        layout = OxmlElement("w:tblLayout"); layout.set(qn("w:type"), "autofit")
        cell_mar = OxmlElement("w:tblCellMar")
        for name, w in (("top", "0"), ("left", "108"), ("bottom", "0"), ("right", "108")):
            m = OxmlElement("w:" + name); m.set(qn("w:w"), w); m.set(qn("w:type"), "dxa")
            cell_mar.append(m)
        for el in (tblW, jc, borders, layout, cell_mar):
            tblPr.append(el)
        for ri, row in enumerate(tbl.rows):
            trPr = row._tr.get_or_add_trPr()
            trh = OxmlElement("w:trHeight"); trh.set(qn("w:val"), "0"); trh.set(qn("w:hRule"), "atLeast")
            trPr.append(trh)
            jcr = OxmlElement("w:jc"); jcr.set(qn("w:val"), "center"); trPr.append(jcr)
            if ri == 0:
                trPr.append(OxmlElement("w:tblHeader"))
        for row in tbl.rows:
            for cell in row.cells:
                tcPr = cell._tc.get_or_add_tcPr()
                tcW = tcPr.find(qn("w:tcW"))
                if tcW is None:
                    tcW = OxmlElement("w:tcW"); tcPr.append(tcW)
                tcW.set(qn("w:type"), "auto"); tcW.set(qn("w:w"), "0")
                vAlign = OxmlElement("w:vAlign"); vAlign.set(qn("w:val"), "center"); tcPr.append(vAlign)
        _fill_table_cell(tbl.cell(0, 0), "易犯错误", header=True)
        _fill_table_cell(tbl.cell(0, 1), "纠正方法", header=True)
        for i, (err, corr) in enumerate(data["errors"], 1):
            _fill_table_cell(tbl.cell(i, 0), err, header=False)
            _fill_table_cell(tbl.cell(i, 1), corr, header=False)

    # ===== 试讲逐字稿 =====
    _section_title(doc, "试讲逐字稿")
    _body_para(doc, data["lecture_script"], size=13, color=DARK, space_after=10, line=1.4)

    # ===== 引流 =====
    doc.add_page_break()
    _body_para(doc, data["hashtags"], size=12, bold=True, color=NAVY, space_after=12)
    _body_para(doc, data["cta"], size=13, bold=True, color=NAVY, space_after=6)


def _fill_table_cell(cell, text, header=False):
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    if p.runs:
        p.runs[0].text = str(text)
        for r in p.runs[1:]:
            r._element.getparent().remove(r._element)
    else:
        p.add_run(str(text))
    run = p.runs[0]
    if header:
        _set_font(run, size=13, bold=True, color=WHITE)
        _shade_cell(cell, "0B3289")
    else:
        _set_font(run, size=13, bold=False, color=DARK)


def build_doc(data):
    doc = Document()
    # 默认样式字体
    style = doc.styles["Normal"]
    style.font.name = FONT
    style.font.size = Pt(13)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

    build_cover(doc, data)
    build_content(doc, data)
    return doc


def validate_output(doc, data):
    errors = []
    all_text = []
    for p in doc.paragraphs:
        all_text.append(p.text or "")
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                all_text.append(cell.text or "")
    text = "\n".join(all_text)
    for label, value in [
        ("sport", data["sport"]), ("segment_name", data["segment_name"]),
        ("method", data["method"]), ("rules", data["rules"]),
        ("intent", data["intent"]), ("organization", data["organization"]),
        ("lecture_script", data["lecture_script"]), ("hashtags", data["hashtags"]),
        ("cta", data["cta"]),
    ]:
        if value not in text:
            errors.append(f"关键词未命中：{label}")
    if data["errors"]:
        if len(doc.tables) < 2:
            errors.append("practice 环节应有易犯错误表格")
        elif doc.tables[-1].cell(0, 0).text.strip() != "易犯错误":
            errors.append("易犯错误表头异常")
    # 图例
    img_count = sum(len(p._element.findall(".//" + qn("w:drawing"))) for p in doc.paragraphs)
    if data["figure_images"] and img_count != len(data["figure_images"]):
        errors.append(f"图例图片数异常：{img_count}（期望 {len(data['figure_images'])}）")
    # 占位符残留
    leftovers = re.findall(r"[ＭＭ]?\{[A-Z_]+\}", text)
    if leftovers:
        errors.append(f"占位符残留：{leftovers}")
    if data["cta"] not in text:
        errors.append("固定引流段未命中")
    return errors


def main():
    temp_path = None
    stage = "读取待写入内容"
    try:
        print("[0/6] 读取待写入内容")
        data = load_pending()
        print(f"      环节：{data['segment_name']}（{SEGMENT_TYPES[data['segment_type']]}）")

        stage = "创建隔离构建副本"
        print("[1/6] 创建隔离构建副本")
        TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".trial_daily_build_", suffix=".docx", dir=TEMPLATE_PATH.parent)
        os.close(fd)
        temp_path = Path(temp_name)

        stage = "构建文档"
        print("[2/6] 构建文档")
        doc = build_doc(data)
        doc.save(temp_path)
        print(f"      已生成 {len(data['figure_images'])} 张图例，结构构建完成")

        stage = "自动验证"
        print("[3/6] 自动验证")
        check = Document(temp_path)
        errors = validate_output(check, data)
        if errors:
            raise RuntimeError("；".join(errors))
        print("      ✅ 构建验证通过")

        stage = "快照并原子提交"
        print("[4/6] 快照并原子提交")
        snap = take_snapshot()
        if snap:
            print(f"      快照：{snap.resolve()}")
        os.replace(temp_path, TEMPLATE_PATH)
        temp_path = None
        print(f"      ✅ 已原子提交：{TEMPLATE_PATH}")
        print("      ✅ 全部通过")
    except Exception as exc:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError as cleanup_exc:
                print(f"      ⚠️ 临时文件清理失败：{cleanup_exc}")
        print(f"      ❌ {stage}失败：{exc}")
        if TEMPLATE_PATH.exists():
            print("      旧工作副本未改动")
        else:
            print("      首次运行失败，未留下半成品工作副本")
        if PENDING_JSON.exists():
            print("[KEEP] pending_trial_daily.json 已原样保留，供排查")
        sys.exit(1)

    print("[收尾] 删除中间 JSON")
    try:
        PENDING_JSON.unlink()
    except Exception as exc:
        print(f"      ❌ DOCX 已通过并提交，但 JSON 删除失败：{exc}")
        sys.exit(2)
    print("      ✅ pending_trial_daily.json 已删除")
    print("完成")


if __name__ == "__main__":
    main()
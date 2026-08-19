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
import struct
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Inches, Pt, RGBColor

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
WORKSPACE = Path(os.environ.get("TRIAL_DAILY_WORKSPACE", SCRIPT_DIR.parent)).expanduser().resolve()
PROJECT_SCRIPT_DIR = WORKSPACE / "scripts"
SOURCE_TEMPLATE = WORKSPACE / "模板文件" / "2 体育试讲每日一练-帖子内容编辑模板.docx"
TEMPLATE_PATH = WORKSPACE / "desktop-attachments" / "2 体育试讲每日一练-帖子内容编辑模板.docx"
PENDING_JSON = PROJECT_SCRIPT_DIR / "pending_trial_daily.json"
SNAPSHOT_DIR = PROJECT_SCRIPT_DIR / "_snapshots_trial"
MAX_SNAPSHOTS = 10

COVER_TITLE = "体育试讲设计每日一练"
DRAIN_TEXT = "关注我，每天一个体育试讲设计，帮你备考上岸"
COVER_BG = SCRIPT_DIR / "cover_bg.png"   # 封面整页底层背景图（从用户模板提取）
COVER_BG_BLEED = 0.12      # 底层背景图出血比例：LibreOffice 对 behindDoc 整页锚定图会垂直缩水 ~7%，加出血保证贴齐底边
WATERMARK_TEXT = "世豪老师"              # 页眉水印文字（与用户模板一致）
NAVY = RGBColor(0x0B, 0x32, 0x89)
CYAN = RGBColor(0x9F, 0xD8, 0xE8)
DARK = RGBColor(0x33, 0x33, 0x33)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x1E, 0x7A, 0x3C)

# ---- 3:4 手机版版式契约（任务2；可被 config.default.json 覆盖） ----
CFG_PAGE = {"size_cm": [15.0, 20.0], "ratio": [3, 4]}
CFG_FONT = ["Hiragino Sans GB", "Heiti SC", "Songti SC", "PingFang SC", "Microsoft YaHei"]
BODY_PT = 18          # 正文/表格 ≥18
SECTION_PT = 26       # 栏目标题 24–28
LABEL_PT = 16         # 图注/标签 ≥16
CTA_PT = 18           # CTA ≥18
TABLE_COLS_PCT = [42, 58]
WATERMARK_OPACITY = 0.10   # 8%–12%


def load_page_config():
    """从 config.default.json 读取页面尺寸与字体契约（不存在时用默认值）。"""
    cfg_path = SKILL_DIR / "config.default.json"
    page = dict(CFG_PAGE)
    fonts = list(CFG_FONT)
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            pg = cfg.get("page") or {}
            if pg.get("size_cm"):
                page["size_cm"] = pg["size_cm"]
            if pg.get("ratio"):
                page["ratio"] = pg["ratio"]
            if pg.get("font_contract"):
                fonts = pg["font_contract"]
        except Exception:
            pass
    return page, fonts


def _first_available_font(fonts):
    """取本机可渲染的契约字体（fc-match 可命中即视为可用）。"""
    for f in fonts:
        r = subprocess.run(["fc-match", f], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip() and "not found" not in r.stdout.lower():
            return f
    return fonts[0]


PAGE_SIZE, FONT_CONTRACT = load_page_config()
FONT = _first_available_font(FONT_CONTRACT)

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
    for k in ("sport", "chapter", "segment_name", "segment_type", "difficulty",
              "method", "rules", "intent", "organization", "lecture_script", "cta", "hashtags"):
        _require_text(data[k], k)
    # 无教材图例的活动允许 figure 为空串（任务2：无引用时允许空图）
    if not isinstance(data["figure"], str):
        raise ValueError("figure 必须是字符串")
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


def _body_para(doc, text, size=BODY_PT, bold=False, color=DARK, space_after=4, line=1.15,
               align=WD_ALIGN_PARAGRAPH.LEFT):
    p = doc.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.line_spacing = line
    run = p.add_run(text)
    _set_font(run, size=size, bold=bold, color=color)
    return p


def _add_watermark(header, text=WATERMARK_TEXT):
    """在页眉追加 VML 斜向水印（灰 #C0C0C0，透明度 8%–12%）。

    要点：不用 DrawingML（LibreOffice 会把整页锚定形状翻页成多页空白）；
    VML 必须去掉 mso-position-*-relative 等相对定位（否则 LibreOffice 会把页眉撑高 ~4cm）。
    """
    op = hex(int(WATERMARK_OPACITY * 0xFFFFFF))[2:].zfill(6)  # 24bit 分数
    wm = (
        '<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:v="urn:schemas-microsoft-com:vml">'
        '<w:pPr><w:spacing w:line="2" w:lineRule="exact"/></w:pPr>'
        '<w:r><w:rPr><w:sz w:val="2"/></w:rPr><w:pict>'
        '<v:shape id="PowerPlusWaterMarkObject" o:spid="_x0000_s2049" o:spt="136" '
        'type="#_x0000_t136" '
        'style="position:absolute;left:0pt;top:0pt;height:30pt;width:435.9pt;'
        'rotation:-2949120f;z-index:-251657216;" fillcolor="#C0C0C0" filled="t" '
        'stroked="f" coordsize="21600,21600" adj="10800">'
        '<v:path/><v:fill on="t" opacity="' + op + '" focussize="0,0"/>'
        '<v:stroke on="f"/><v:imagedata o:title=""/>'
        '<o:lock v:ext="edit" aspectratio="t"/>'
        '<v:textpath on="t" fitshape="t" fitpath="t" trim="t" xscale="f" '
        'string="__WM__" style="font-family:Hiragino Sans GB;font-size:36pt;'
        'v-same-letter-heights:f;v-text-align:center;"/>'
        '</v:shape></w:pict></w:r></w:p>'
    )
    header._element.append(parse_xml(wm.replace("__WM__", text)))


def _anchor_cover_bg(para, image_path):
    """在给定段落内插入整页底层背景图（behindDoc 锚定，等比满铺 3:4 整页）。

    顶层左上对齐页边，并向下/向右略出血（COVER_BG_BLEED），以抵消 LibreOffice
    渲染 behindDoc 整页锚定图时的垂直缩水，确保底层图贴齐页面下底边、无白色空隙；
    出血部分被页面边界裁掉，其余渲染器（Word/WPS）按精确尺寸渲染时同样无副作用。
    """
    w_cm, h_cm = PAGE_SIZE["size_cm"]
    page_w = int(w_cm * 360000)   # EMU
    page_h = int(h_cm * 360000)
    scale = 1.0 + COVER_BG_BLEED
    run = para.add_run()
    run.add_picture(str(image_path), width=Emu(int(page_w * scale)), height=Emu(int(page_h * scale)))
    drawing = run._element.find(qn("w:drawing"))
    inline = drawing.find(qn("wp:inline"))
    anchor = OxmlElement("wp:anchor")
    for attr, val in (
        ("distT", "0"), ("distB", "0"), ("distL", "0"), ("distR", "0"),
        ("simplePos", "0"), ("relativeHeight", "251660288"), ("behindDoc", "1"),
        ("locked", "1"), ("layoutInCell", "1"), ("allowOverlap", "1"),
    ):
        anchor.set(attr, val)
    simple_pos = OxmlElement("wp:simplePos"); simple_pos.set("x", "0"); simple_pos.set("y", "0")
    pos_h = OxmlElement("wp:positionH"); pos_h.set("relativeFrom", "page")
    off_x = OxmlElement("wp:posOffset"); off_x.text = "0"; pos_h.append(off_x)
    pos_v = OxmlElement("wp:positionV"); pos_v.set("relativeFrom", "page")
    off_y = OxmlElement("wp:posOffset"); off_y.text = "0"; pos_v.append(off_y)
    wrap_none = OxmlElement("wp:wrapNone")
    kept = {}
    for child in list(inline):
        tag = child.tag
        for key in ("wp:extent", "wp:effectExtent", "wp:docPr", "wp:cNvGraphicFramePr", "a:graphic"):
            if tag == qn(key):
                kept[key] = child
    for key in ("wp:extent", "wp:docPr", "wp:cNvGraphicFramePr", "a:graphic"):
        if key not in kept:
            raise RuntimeError(f"封面背景图缺少 {key}")
    if "wp:effectExtent" not in kept:
        kept["wp:effectExtent"] = OxmlElement("wp:effectExtent")
    for child in (simple_pos, pos_h, pos_v, kept["wp:extent"], kept["wp:effectExtent"],
                  wrap_none, kept["wp:docPr"], kept["wp:cNvGraphicFramePr"], kept["a:graphic"]):
        anchor.append(child)
    drawing.remove(inline)
    drawing.append(anchor)
    return anchor


def _section_title(doc, text, color=NAVY, page_break_before=False):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(6)
    pf.space_after = Pt(4)
    pf.page_break_before = page_break_before
    run = p.add_run(text)
    _set_font(run, size=SECTION_PT, bold=True, color=color)
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

def _apply_page_size(section):
    """把节页面设为精确 3:4 手机版（15cm × 20cm，可配置）。"""
    w_cm, h_cm = PAGE_SIZE["size_cm"]
    section.page_width = Cm(w_cm)
    section.page_height = Cm(h_cm)


def build_cover(doc, data):
    """封面：整页深蓝底 + 浅青标题 + 项目标签 + 环节名 + 难度（3:4 单页）。"""
    section = doc.sections[0]
    _apply_page_size(section)
    section.top_margin = Cm(0)
    section.bottom_margin = Cm(0)
    section.left_margin = Cm(0)
    section.right_margin = Cm(0)
    # 封面页不显示页眉页脚品牌文字，同时叠加斜向水印
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
    _add_watermark(section.header)

    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # 封面表格浮动锚定整页（与用户模板一致），保证放大字号后仍恰好一页
    tblPr = table._tbl.tblPr
    for tag in ("w:tblW", "w:jc", "w:tblInd", "w:tblLayout", "w:tblCellMar", "w:tblLook"):
        for el in tblPr.findall(qn(tag)):
            tblPr.remove(el)
    tblpPr = OxmlElement("w:tblpPr")
    for attr, val in (("leftFromText", "180"), ("rightFromText", "180"), ("vertAnchor", "page"),
                      ("horzAnchor", "page"), ("tblpX", "391"), ("tblpY", "1")):
        tblpPr.set(qn("w:" + attr), val)
    tblPr.append(tblpPr)
    overlap = OxmlElement("w:tblOverlap"); overlap.set(qn("w:val"), "never"); tblPr.append(overlap)
    tblW = OxmlElement("w:tblW"); tblW.set(qn("w:w"), "12232"); tblW.set(qn("w:type"), "dxa"); tblPr.append(tblW)
    layout = OxmlElement("w:tblLayout"); layout.set(qn("w:type"), "autofit"); tblPr.append(layout)
    cell_mar = OxmlElement("w:tblCellMar")
    for name, w in (("top", "0"), ("left", "108"), ("bottom", "0"), ("right", "108")):
        m = OxmlElement("w:" + name); m.set(qn("w:w"), w); m.set(qn("w:type"), "dxa"); cell_mar.append(m)
    tblPr.append(cell_mar)
    for gc in table._tbl.tblGrid.findall(qn("w:gridCol")):
        gc.set(qn("w:w"), "12232")

    cell = table.cell(0, 0)
    # 底层背景图锚定封面单元格段落（behindDoc 铺满整页）；无图时回退纯深蓝底
    if COVER_BG.exists():
        _anchor_cover_bg(cell.paragraphs[0], COVER_BG)
    _shade_cell(cell, "0B3289")
    _set_cell_margins(cell, top="200", left="400", bottom="200", right="400")
    _cell_vertical_center(cell)

    # 顶部：固定小标题
    _add_para(cell, "体师备考知识库 · 教师编面试", size=18, bold=True, color=CYAN,
              align=WD_ALIGN_PARAGRAPH.CENTER, space_before=60, space_after=30)
    # 大标题
    _add_para(cell, COVER_TITLE, size=48, bold=True, color=CYAN,
              align=WD_ALIGN_PARAGRAPH.CENTER, space_after=40)
    # 项目标签
    _add_para(cell, f"【{data['sport']}】{SEGMENT_TYPES[data['segment_type']]}",
              size=22, bold=True, color=WHITE, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=50)
    # 环节名
    _add_para(cell, data["segment_name"], size=30, bold=True, color=WHITE,
              align=WD_ALIGN_PARAGRAPH.CENTER, space_after=30)
    # 难度（封面不再显示章节行，仅保留难度）
    _add_para(cell, f"难度：{data['difficulty']}", size=18, bold=True,
              color=RGBColor(0xF0, 0xC8, 0x6C), align=WD_ALIGN_PARAGRAPH.CENTER, space_after=60)

    # 行高撑满大部分页面，底部留出底层背景图的品牌信息条（与模板一致：15290 atLeast）
    trPr = table.rows[0]._tr.get_or_add_trPr()
    trh = OxmlElement("w:trHeight")
    trh.set(qn("w:val"), "15290")
    trh.set(qn("w:hRule"), "atLeast")
    trPr.append(trh)


def _split_script_short_lines(script, max_len=40):
    """逐字稿按教学阶段拆短段：按句读切分，每段 ≤45 字，避免大段文字堆页。"""
    parts = re.split(r"(?<=[。！？])", script)
    lines = []
    buf = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) > max_len:
            # 超长句切成 max_len 块
            if buf:
                lines.append(buf)
                buf = ""
            for i in range(0, len(part), max_len):
                lines.append(part[i:i + max_len])
            continue
        if buf and len(buf) + len(part) > max_len + 5:
            lines.append(buf)
            buf = ""
        buf += part
        if len(buf) >= max_len:
            lines.append(buf)
            buf = ""
    if buf:
        lines.append(buf)
    return [ln.strip() for ln in lines if ln.strip()]


def _png_dims(path):
    """读 PNG 宽高（纯 stdlib）。"""
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"非 PNG: {path}")
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def _figure_fit_cm(path, avail_w_cm, avail_h_cm, pref_w_cm=11.1):
    """按图像宽高比在可用区内等比适配，保证标题+图注+图同页不溢出。"""
    w_px, h_px = _png_dims(path)
    fw = min(pref_w_cm, avail_w_cm)
    fh = fw * h_px / w_px
    if fh <= avail_h_cm:
        return fw, fh
    fh = avail_h_cm
    fw = fh * w_px / h_px
    return fw, fh


def _fixed_table(doc, rows, cols, width_cm, col_pct):
    """固定总宽、42/58 列、禁 autofit、行不跨页 的错误纠正表。"""
    tbl = doc.add_table(rows=rows, cols=cols)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tblPr = tbl._tbl.tblPr
    for child in list(tblPr):
        tblPr.remove(child)
    total_dxa = int(width_cm / 2.54 * 1440)
    tblW = OxmlElement("w:tblW"); tblW.set(qn("w:w"), str(total_dxa)); tblW.set(qn("w:type"), "dxa")
    jc = OxmlElement("w:jc"); jc.set(qn("w:val"), "center")
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement("w:" + edge)
        el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "6")
        el.set(qn("w:color"), "8EAADB"); el.set(qn("w:space"), "0")
        borders.append(el)
    layout = OxmlElement("w:tblLayout"); layout.set(qn("w:type"), "fixed")
    cell_mar = OxmlElement("w:tblCellMar")
    for name, w in (("top", "40"), ("left", "108"), ("bottom", "40"), ("right", "108")):
        m = OxmlElement("w:" + name); m.set(qn("w:w"), w); m.set(qn("w:type"), "dxa")
        cell_mar.append(m)
    for el in (tblW, jc, borders, layout, cell_mar):
        tblPr.append(el)
    # 固定列宽 42/58
    grid = tbl._tbl.tblGrid
    for gc in grid.findall(qn("w:gridCol")):
        grid.remove(gc)
    for pct in col_pct:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(int(total_dxa * pct / 100)))
        grid.append(gc)
    for ri, row in enumerate(tbl.rows):
        trPr = row._tr.get_or_add_trPr()
        trh = OxmlElement("w:trHeight"); trh.set(qn("w:val"), "0"); trh.set(qn("w:hRule"), "atLeast")
        trPr.append(trh)
        cant = OxmlElement("w:cantSplit")  # 行不跨页
        trPr.append(cant)
        if ri == 0:
            trPr.append(OxmlElement("w:tblHeader"))
        for ci, cell in enumerate(row.cells):
            tcPr = cell._tc.get_or_add_tcPr()
            tcW = tcPr.find(qn("w:tcW"))
            if tcW is None:
                tcW = OxmlElement("w:tcW"); tcPr.append(tcW)
            tcW.set(qn("w:type"), "dxa")
            tcW.set(qn("w:w"), str(int(total_dxa * col_pct[ci] / 100)))
            vAlign = OxmlElement("w:vAlign"); vAlign.set(qn("w:val"), "center"); tcPr.append(vAlign)
    return tbl


def build_content(doc, data):
    """正文：页眉 + 图例 + 环节拆解 + 试讲逐字稿（分短段）+ 引流（3:4）。"""
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    _apply_page_size(section)
    section.top_margin = Cm(1.0)
    section.bottom_margin = Cm(1.0)
    section.left_margin = Cm(1.0)
    section.right_margin = Cm(1.0)
    usable_w_cm = PAGE_SIZE["size_cm"][0] - 2 * 1.0   # 13.0cm

    # 页眉（必须先断开与前节链接，否则品牌文字会写进封面节）
    header = section.header
    header.is_linked_to_previous = False
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hr = hp.add_run("体师备考知识库")
    _set_font(hr, size=10, bold=True, color=NAVY)
    _add_watermark(header)

    # 页脚：禁用页码（产品要求不显示页码，清空默认页脚文本）
    footer = section.footer
    footer.is_linked_to_previous = False
    for fpar in footer.paragraphs:
        for r in list(fpar.runs):
            r._element.getparent().remove(r._element)

    # ===== 图例区 =====
    if data["figure_images"]:
        _section_title(doc, "图例直观")
        # 图可占高（保守，避免 LibreOffice 把高图推下页）：页高-上下边距-页眉带-标题-图注-留白
        avail_h_cm = 11.0
        for img in data["figure_images"]:
            fw, fh = _figure_fit_cm(img, usable_w_cm, avail_h_cm)
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run()
            run.add_picture(img, width=Cm(fw), height=Cm(fh))
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.0
        if data["figure"]:
            _body_para(doc, data["figure"], size=LABEL_PT, bold=True, color=GREEN,
                       space_after=4, align=WD_ALIGN_PARAGRAPH.CENTER)

    # ===== 环节拆解 =====
    # 图例放大铺满首屏后，环节拆解标题另起一页置于最上端；
    # 用 page_break_before 把页断挂在标题上，避免独立 add_page_break 段落产生空白页
    _section_title(doc, "环节拆解", page_break_before=bool(data["figure_images"]))

    def _field(label, value):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_after = Pt(4)
        pf.line_spacing = 1.15
        r1 = p.add_run(f"{label}｜")
        _set_font(r1, size=LABEL_PT, bold=True, color=NAVY)
        r2 = p.add_run(value)
        _set_font(r2, size=BODY_PT, bold=False, color=DARK)

    _field("环节名称", data["segment_name"])
    _field("活动类型", SEGMENT_TYPES[data["segment_type"]])
    _field("活动方法", data["method"])
    _field("规则", data["rules"])
    _field("活动设计意图", data["intent"])
    _field("活动组织形式", data["organization"])

    # 易犯错误与纠正（仅 practice）
    if data["errors"]:
        _section_title(doc, "易犯错误与纠正")
        tbl = _fixed_table(doc, rows=len(data["errors"]) + 1, cols=2,
                           width_cm=usable_w_cm, col_pct=TABLE_COLS_PCT)
        _fill_table_cell(tbl.cell(0, 0), "易犯错误", header=True)
        _fill_table_cell(tbl.cell(0, 1), "纠正方法", header=True)
        for i, (err, corr) in enumerate(data["errors"], 1):
            _fill_table_cell(tbl.cell(i, 0), err, header=False)
            _fill_table_cell(tbl.cell(i, 1), corr, header=False)

    # ===== 试讲逐字稿（按教学阶段拆短段） =====
    _section_title(doc, "试讲逐字稿")
    lines = _split_script_short_lines(data["lecture_script"])
    for i, line in enumerate(lines):
        p = _body_para(doc, line, size=BODY_PT, color=DARK, space_after=4, line=1.3)
        # 最后 2 段与引流组同页，保证 CTA 同页前至少 2 行正文
        if i >= len(lines) - 2:
            p.paragraph_format.keep_with_next = True

    # ===== 引流（紧接逐字稿结尾，空一行直接写，不另起页） =====
    hs = _body_para(doc, data["hashtags"], size=LABEL_PT, bold=True, color=RGBColor(0x80, 0x80, 0x80),
                    align=WD_ALIGN_PARAGRAPH.CENTER, space_after=12)
    hs.paragraph_format.keep_with_next = True
    _body_para(doc, data["cta"], size=CTA_PT, bold=True, color=NAVY,
               align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)


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
        _set_font(run, size=BODY_PT, bold=True, color=WHITE)
        _shade_cell(cell, "0B3289")
    else:
        _set_font(run, size=BODY_PT, bold=False, color=DARK)


def build_doc(data):
    doc = Document()
    # 默认样式字体（3:4 版式契约）
    style = doc.styles["Normal"]
    style.font.name = FONT
    style.font.size = Pt(BODY_PT)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    # 默认页面尺寸（封面节）
    _apply_page_size(doc.sections[0])

    build_cover(doc, data)
    build_content(doc, data)
    return doc


def validate_output(doc, data):
    errors = []
    # 3:4 页面（所有节）
    for si, sec in enumerate(doc.sections):
        w, h = sec.page_width, sec.page_height
        if w and h:
            ratio = w / h
            if abs(ratio - 0.75) / 0.75 > 0.01:
                errors.append(f"第 {si + 1} 节页面非 3:4（{ratio:.4f}）")
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
        ("hashtags", data["hashtags"]),
        ("cta", data["cta"]),
    ]:
        if value not in text:
            errors.append(f"关键词未命中：{label}")
    # 逐字稿按短段拆分渲染，逐段校验存在性（内容不丢）
    script_lines = _split_script_short_lines(data["lecture_script"])
    missing_lines = [ln[:14] for ln in script_lines if ln not in text]
    if missing_lines:
        errors.append(f"逐字稿短段未命中：{missing_lines[:3]}…")
    if data["errors"]:
        if len(doc.tables) < 2:
            errors.append("practice 环节应有易犯错误表格")
        elif doc.tables[-1].cell(0, 0).text.strip() != "易犯错误":
            errors.append("易犯错误表头异常")
    # 图例（仅统计行内 figure，封面底层背景图为锚定图不计入）
    img_count = sum(len(p._element.findall(".//" + qn("wp:inline"))) for p in doc.paragraphs)
    if data["figure_images"] and img_count != len(data["figure_images"]):
        errors.append(f"图例图片数异常：{img_count}（期望 {len(data['figure_images'])}）")
    # 占位符残留
    leftovers = re.findall(r"[ＭＭ]?\{[A-Z_]+\}", text)
    if leftovers:
        errors.append(f"占位符残留：{leftovers}")
    if data["cta"] not in text:
        errors.append("固定引流段未命中")
    # 引流页样式：标签行居中+灰，引流段居中+深蓝（品牌铁律）
    body = [p for p in doc.paragraphs if p.text.strip()]
    if body:
        tag_p = body[-2] if body[-1].text.strip() == data["cta"] else None
        cta_p = body[-1] if body[-1].text.strip() == data["cta"] else None
        def _first_run_color(p):
            return p.runs[0].font.color.rgb if p and p.runs and p.font.color is not None else None
        if cta_p is None or cta_p.alignment != WD_ALIGN_PARAGRAPH.CENTER:
            errors.append("固定引流段必须居中")
        elif tag_p is None or tag_p.alignment != WD_ALIGN_PARAGRAPH.CENTER:
            errors.append("#标签行必须居中")
        elif tag_p is not None and tag_p.runs and tag_p.runs[0].font.color.rgb != RGBColor(0x80, 0x80, 0x80):
            errors.append("#标签行颜色必须为灰色 #808080")
        elif cta_p is not None and cta_p.runs and cta_p.runs[0].font.color.rgb != NAVY:
            errors.append("固定引流段颜色必须为深蓝 #0B3289")
        # 引流两行不另起一页：hashtags 段之前紧邻的段落不得含分页符（应空一行直连逐字稿）
        hs_elem = tag_p._element
        prev = hs_elem.getprevious() if tag_p is not None else None
        if prev is not None and prev.tag == qn("w:p"):
            for br in prev.findall(".//" + qn("w:br")):
                if br.get(qn("w:type")) == "page":
                    errors.append("引流两行不得另起一页，须紧接逐字稿后空一行")
                    break

    # 页眉斜向水印（品牌铁律：VML，透明度 8%–12%）
    for si, sec in enumerate(doc.sections):
        hx = sec.header._element.xml
        if "PowerPlusWaterMarkObject" not in hx:
            errors.append(f"第 {si + 1} 节页眉缺少水印")
        if "z-index:-" not in hx.replace(" ", ""):
            errors.append(f"第 {si + 1} 节水印未锚定到内容之下")

    # 封面整页底层背景图（behindDoc 锚定）
    anchors = doc.element.body.findall(".//" + qn("wp:anchor"))
    if not any(a.get("behindDoc") == "1" for a in anchors):
        errors.append("封面底层背景图缺失")

    # 封面大标题字号（48pt）
    title_ok = False
    for p in doc.paragraphs:
        for run in p.runs:
            if run.text.strip() == COVER_TITLE and run.font.size and run.font.size.pt >= 47:
                title_ok = True
    for tb in doc.tables:
        for row in tb.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for run in p.runs:
                        if run.text.strip() == COVER_TITLE and run.font.size and run.font.size.pt >= 47:
                            title_ok = True
    if not title_ok:
        errors.append("封面大标题字号须为 48pt")

    # 有图例时：图例放大（宽 ≥ 正文85% 或高填满可用区）+ 环节拆解另起一页
    if data["figure_images"]:
        usable_cm = PAGE_SIZE["size_cm"][0] - 2 * 1.0   # 13.0cm
        min_w = 0.85 * usable_cm * 360000
        avail_h_cm = 11.0
        min_h = 0.95 * avail_h_cm * 360000
        big_img = False
        for dw in doc.element.body.findall(".//" + qn("w:drawing")):
            if dw.find(qn("wp:inline")) is None:
                continue  # 封面底层锚定图不计入图例
            ext = dw.find(".//" + qn("wp:extent"))
            if ext is None or ext.get("cx") is None:
                continue
            cx = int(ext.get("cx"))
            cy = int(ext.get("cy") or 0)
            if cx >= min_w or cy >= min_h:
                big_img = True
        if not big_img:
            errors.append("图例未放大（宽须≥正文85%，或高填满可用区）")
        titles = [i for i, p in enumerate(doc.paragraphs) if p.text.strip() == "环节拆解"]
        if titles:
            title_p = doc.paragraphs[titles[0]]
            if not title_p.paragraph_format.page_break_before:
                errors.append("图例后环节拆解未另起一页")
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
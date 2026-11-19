#!/usr/bin/env python3
"""构建技巧线新模板 baseline（23 段 / 4 图 / 15 字段）—— Task 3 交付物。

用法：
    python3 build_tips_template.py [--out PATH] [--source-template PATH]

- --out 默认 <skill>/assets/tips-template-baseline.docx（相对本脚本 ../assets/）
- --source-template 默认 vault 旧 21 段活模板路径；**只读**，从不写回。
  注意：部署后 vault 活模板已变 23 段，再跑脚本须显式传归档的 21 段路径。

产出的 baseline 是 Task4 引擎的写入目标模板，其逐段 pPr/rPr 即
shared-engine-safety「样式指纹零漂移」的基准。

段位契约来源：task-3-brief 交付物 1 段位映射表（23 段 4 图 15 字段），
逐段样式模式取自旧 21 段模板对应段（详见各 build_* 注释）。

从旧模板只读提取并复用：
- word/media/* 4 张图：image1.jpeg（页眉品牌logo"总分总"，装饰段1）、
  image2.png（页脚横幅，装饰段13）、image3.png（封面背景图，段0）、
  image4.png（尾页图，段22）；字节全部不变。
- 品牌蓝（Heading 2 样式定义 w:color，预期 003153）与通用字体（微软雅黑）
  ——运行时从 styles.xml 提取并断言，与契约不符即拒绝构建（不臆造）。

字体铁律落地：旧模板遗留 Times New Roman 子集内嵌字体
（word/fonts/font1.odttf + fontTable embedRegular + settings embedTrueTypeFonts），
写盘前一律剥离——baseline 不含任何内嵌字体文件（Times New Roman 为通用系统字体，零视觉影响）。
写盘为固定时间戳重打包：重跑产出字节级一致的 docx（sha256 相同）。
- 引流段原文（旧段 19）、封面文本框双镜像结构（旧段 0 AlternateContent
  Choice wps:txbx + Fallback v:textbox）、封面/尾页图片段（旧段 0/20 深拷贝）。

图数口径（EXPECTED_IMG_TOTAL=4）：按 pic:pic（真实图片）计数；
封面文本框是形状（wps:wsp）不是图，不计入图数，故文档内
w:drawing 元素总数为 5（4 图 + 1 文本框）。
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu
from docx.text.paragraph import Paragraph
from docx.text.run import Run

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = SCRIPT_DIR.parent / "assets" / "tips-template-baseline.docx"
DEFAULT_SOURCE = (
    "/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/"
    "结构化/desktop-attachments/3 结构化答题技巧-帖子内容编辑模板.docx"
)

# ---- 契约常量（简报 Task3 交付物 1） ----
EXPECTED_PARAS = 23          # 段数
EXPECTED_IMG_TOTAL = 4       # 图数（pic:pic 计数：封面1+装饰2+尾页1）
EXPECTED_FIELDS = 15         # 字段数（tip_title + 14 内容字段）
BRAND_BLUE = "003153"        # 品牌蓝：旧模板 Heading 2 样式定义色值（预期，运行时提取核对）
CONTRACT_RED = "85120F"      # 段3 fix_summary / 段21 引流段 字色（旧模板实测一致）
CONTRACT_FONT = "微软雅黑"    # 通用字体（旧模板唯一显式字体）
SOURCE_PARAS = 21            # 旧模板段数（来源校验）
GRAY_SHD = "F2F2F2"          # 段12 对照点评浅灰底
COVER_PREFIX = "结构化答题技巧："   # 封面前缀，双镜像共 2 处
TITLE_FIELD = "tip_title"          # 15 字段之一（tips-content-strategy 字段职责表）

# 占位文本：content 段放字段名占位，引擎替换；emoji（👍/🙅‍♂️）由引擎按契约加段首
PLACEHOLDERS = {
    "card_point": "card_point 占位",
    "fix_summary": "fix_summary 占位",
    "demo": "demo 占位",
    "step1": "step1 占位",
    "step2": "step2 占位",
    "step3": "step3 占位",
    "case_normal": "case_normal 占位",
    "contrast_note": "contrast_note 占位",
    "boundary_scope": "boundary_scope 占位",
    "boundary_misuse": "boundary_misuse 占位",
    "boundary_evidence": "boundary_evidence 占位",
    "exercise": "exercise 占位",
    "self_check": "self_check 占位",
    "hashtags": "hashtags 占位",
}
SECTION_TITLES = {
    1: "卡点诊断",
    4: "定调版示范",
    6: "改法拆解",
    10: "对照点评",
    13: "适用边界",
    17: "迁移练习",
}
QUOTE_ATTRS = {"w:val": "clear", "w:color": "auto", "w:fill": GRAY_SHD}


def el(tag, attrs=None, *children):
    """OxmlElement 快捷构造（qn 命名空间，序列化不产生冗余 xmlns）。"""
    e = OxmlElement(tag)
    for k, v in (attrs or {}).items():
        e.set(qn(k), v)
    for c in children:
        e.append(c)
    return e


# ---- rPr 变体（样式模式取自旧模板对应段，见各注释） ----
def rpr_plain():
    """通用 run 字纹：旧模板 Normal 段默认（hint eastAsia + lang）。"""
    return el("w:rPr", None, el("w:rFonts", {"w:hint": "eastAsia"}),
              el("w:lang", {"w:val": "en-US", "w:eastAsia": "zh-CN"}))


def rpr_mark_plain():
    """段落标记 rPr（同 rpr_plain）。"""
    return rpr_plain()


def rpr_fix():
    """段3 fix_summary：b + bCs + color（旧段3 破题角度 rPr 模式）。"""
    return el("w:rPr", None, el("w:rFonts", {"w:hint": "eastAsia"}),
              el("w:b"), el("w:bCs"), el("w:color", {"w:val": CONTRACT_RED}),
              el("w:lang", {"w:val": "en-US", "w:eastAsia": "zh-CN"}))


def rpr_bold_underline():
    """段14/15/16/18/19：b + bCs + u single（旧段13 边界 rPr 模式）。"""
    return el("w:rPr", None, el("w:rFonts", {"w:hint": "eastAsia"}),
              el("w:b"), el("w:bCs"), el("w:u", {"w:val": "single"}),
              el("w:lang", {"w:val": "en-US", "w:eastAsia": "zh-CN"}))


def rpr_mark_bold_underline():
    """段落标记带 b + u（旧段13 pPr 内 rPr 模式）。"""
    return el("w:rPr", None, el("w:rFonts", {"w:hint": "eastAsia"}),
              el("w:b"), el("w:u", {"w:val": "single"}),
              el("w:lang", {"w:val": "en-US", "w:eastAsia": "zh-CN"}))


def rpr_hashtag():
    """段20 hashtags：sz 24（12pt，旧段18 rPr 模式）。"""
    return el("w:rPr", None, el("w:rFonts", {"w:hint": "eastAsia"}),
              el("w:sz", {"w:val": "24"}),
              el("w:lang", {"w:val": "en-US", "w:eastAsia": "zh-CN"}))


# ---- pPr 变体（样式模式取自旧模板对应段） ----
def ppr_title():
    """6 个蓝色标题段：pStyle 4（Heading 2，品牌蓝/微软雅黑在样式定义）+
    numPr numId=0 抑制标题编号 + bidi 0 + ind leftChars 0（旧段1「答题思路」pPr 原样）。"""
    return el("w:pPr", None,
              el("w:pStyle", {"w:val": "4"}),
              el("w:numPr", None, el("w:ilvl", {"w:val": "1"}), el("w:numId", {"w:val": "0"})),
              el("w:bidi", {"w:val": "0"}),
              el("w:ind", {"w:leftChars": "0"}),
              rpr_mark_plain())


def ppr_plain():
    """普通 Normal 段（旧段8/10 pPr 模式：bidi 0 + 段落标记 rPr）。"""
    return el("w:pPr", None, el("w:bidi", {"w:val": "0"}), rpr_mark_plain())


def ppr_fix():
    """段3：首行缩进 2 字符 firstLineChars=200（旧段3 pPr，firstLine 640 同步保留）。"""
    return el("w:pPr", None, el("w:bidi", {"w:val": "0"}),
              el("w:ind", {"w:left": "0", "w:leftChars": "0",
                           "w:firstLine": "640", "w:firstLineChars": "200"}),
              rpr_mark_plain())


def ppr_step():
    """段7/8/9：圆点项目符号 numPr ilvl=0 numId=12（旧段4/5/6 pPr 原样）。"""
    return el("w:pPr", None,
              el("w:numPr", None, el("w:ilvl", {"w:val": "0"}), el("w:numId", {"w:val": "12"})),
              el("w:bidi", {"w:val": "0"}), rpr_mark_plain())


def ppr_quote():
    """段12：Markdown引用样式 pStyle 99 + 浅灰底 shd F2F2F2（旧段9/11 pPr 原样）。"""
    return el("w:pPr", None,
              el("w:pStyle", {"w:val": "99"}),
              el("w:shd", QUOTE_ATTRS),
              el("w:bidi", {"w:val": "0"}), rpr_mark_plain())


def ppr_bold_underline():
    """段14/15/16/18/19：Normal + 段落标记 b+u（旧段13/14 pPr 模式）。"""
    return el("w:pPr", None, el("w:bidi", {"w:val": "0"}), rpr_mark_bold_underline())


def ppr_hashtag():
    """段20：endnote text 样式 pStyle 51（旧段18 pPr 原样）。"""
    return el("w:pPr", None, el("w:pStyle", {"w:val": "51"}),
              el("w:bidi", {"w:val": "0"}), el("w:rPr", None, el("w:rFonts", {"w:hint": "eastAsia"})))


def run_el(text, rpr):
    """w:r = rPr + w:t（无首尾空格，不需 xml:space=preserve）。"""
    t = el("w:t")
    t.text = text
    return el("w:r", None, rpr, t)


def new_para(sect_pr, ppr, *runs):
    """按契约新建段落并插入 sectPr 之前（正文末尾）。"""
    p = el("w:p", None, ppr, *runs)
    sect_pr.addprevious(p)
    return p


def set_txbx_texts(p_elem, text):
    """把文本框内某段的所有 w:t 归一为单个 text（镜像段落各调一次）。"""
    ts = p_elem.findall(".//" + qn("w:t"))
    if not ts:
        raise ValueError("封面文本框镜像段落缺 w:t")
    ts[0].text = text
    for extra in ts[1:]:
        extra.getparent().remove(extra)


def extract_brand_from_styles(styles_xml: bytes):
    """从旧模板 styles.xml 提取 Heading 2（styleId=4）品牌蓝与字体（只读）。"""
    m = re.search(r'<w:style [^>]*w:styleId="4".*?</w:style>', styles_xml.decode("utf-8"), re.S)
    if not m:
        raise ValueError("旧模板 styles.xml 缺 styleId=4（Heading 2）")
    block = m.group(0)
    color = re.search(r'<w:color w:val="([0-9A-Fa-f]{6})"', block)
    font = re.search(r'w:ascii="([^"]+)"', block)
    if not color or not font:
        raise ValueError("Heading 2 样式缺 w:color/w:ascii，品牌蓝色值提取失败")
    return color.group(1).upper(), font.group(1)


def extract_deco_media_names(zf: zipfile.ZipFile):
    """从页眉/页脚 rels 解析品牌装饰图 media 文件名（image1→段1，image2→段13）。"""
    def target(part_rels):
        data = zf.read(part_rels).decode("utf-8")
        m = re.search(r'Target="(media/[^"]+)"', data)
        if not m:
            raise ValueError(f"{part_rels} 无 image 关系")
        return "word/" + m.group(1)
    return target("word/_rels/header1.xml.rels"), target("word/_rels/footer1.xml.rels")


def build(out_path: Path, source_path: Path) -> None:
    # ---- 读源（只读）：整包校验 + 提取品牌蓝/字体/装饰图/引流段 ----
    if not source_path.is_file():
        sys.exit(f"[exit 1] 源模板不存在：{source_path}")
    src_doc = Document(str(source_path))
    src_paras = src_doc.paragraphs
    if len(src_paras) != SOURCE_PARAS:
        sys.exit(
            f"[exit 1] --source-template 段数 {len(src_paras)} != {SOURCE_PARAS}："
            "须传旧 21 段模板（部署后活模板已是 23 段，请传归档件）"
        )
    yinliu_text = src_paras[19].text  # 旧段19 引流段原文
    if not yinliu_text.startswith("关注我"):
        sys.exit(f"[exit 1] 旧段 19 不是引流段（应以「关注我」开头）：{yinliu_text[:20]!r}")

    with zipfile.ZipFile(str(source_path)) as zf:
        styles_xml = zf.read("word/styles.xml")
        brand_blue, brand_font = extract_brand_from_styles(styles_xml)
        if brand_blue != BRAND_BLUE:
            sys.exit(f"[exit 1] 提取品牌蓝 {brand_blue} != 契约 {BRAND_BLUE}，拒绝臆造")
        if brand_font != CONTRACT_FONT:
            sys.exit(f"[exit 1] 提取字体 {brand_font!r} != 契约 {CONTRACT_FONT!r}，拒绝臆造")
        deco_a_name, deco_b_name = extract_deco_media_names(zf)
        media = {
            name: zf.read(name)
            for name in zf.namelist()
            if name.startswith("word/media/") and zf.getinfo(name).file_size > 0
        }
    if len(media) != EXPECTED_IMG_TOTAL:
        sys.exit(f"[exit 1] 旧模板 media 图片数 {len(media)} != {EXPECTED_IMG_TOTAL}")

    # ---- 以旧模板为文档底座：样式表/编号/页眉页脚/sectPr 原样保留 ----
    doc = Document(str(source_path))
    body = doc.element.body
    sect_pr = body.find(qn("w:sectPr"))
    if sect_pr is None:
        sys.exit("[exit 1] 源模板无 sectPr")
    for p in body.findall(qn("w:p")):
        body.remove(p)

    # 段0 封面（Heading2）：旧段0 深拷贝（文本框双镜像 + 封面背景图 + 分页符），
    # 双镜像内改前缀 + tip_title 占位（引擎行为：替换标题，前缀 2 处同步）
    p0 = copy.deepcopy(src_paras[0]._p)
    txbx_list = p0.findall(".//" + qn("w:txbxContent"))
    if len(txbx_list) != 2:
        sys.exit(f"[exit 1] 封面文本框镜像数 {len(txbx_list)} != 2（需 Choice+VML 双镜像）")
    for txbx in txbx_list:
        box_paras = txbx.findall(qn("w:p"))
        if len(box_paras) < 2:
            sys.exit("[exit 1] 封面文本框镜像段落不足 2 段")
        set_txbx_texts(box_paras[0], COVER_PREFIX)          # 前缀（大字行）
        set_txbx_texts(box_paras[1], f"{TITLE_FIELD} 占位")  # 标题占位（引擎替换）
    sect_pr.addprevious(p0)

    # 段1 卡点诊断（Heading2 品牌蓝）+ 装饰图 A（页眉品牌logo字节，inline 0.6cm）
    _add_title(doc, sect_pr, SECTION_TITLES[1], media[deco_a_name], Emu(216000))
    # 段2 card_point（Normal）
    new_para(sect_pr, ppr_plain(), run_el(PLACEHOLDERS["card_point"], rpr_plain()))
    # 段3 fix_summary（Normal + firstLineChars=200 + 字色 85120F）
    new_para(sect_pr, ppr_fix(), run_el(PLACEHOLDERS["fix_summary"], rpr_fix()))
    # 段4 定调版示范（Heading2 品牌蓝）
    _add_title(doc, sect_pr, SECTION_TITLES[4])
    # 段5 demo（Normal，引擎加段首 👍）
    new_para(sect_pr, ppr_plain(), run_el(PLACEHOLDERS["demo"], rpr_plain()))
    # 段6 改法拆解（Heading2 品牌蓝）
    _add_title(doc, sect_pr, SECTION_TITLES[6])
    # 段7/8/9 step1-3（圆点项目符号 numId=12）
    for k in ("step1", "step2", "step3"):
        new_para(sect_pr, ppr_step(), run_el(PLACEHOLDERS[k], rpr_plain()))
    # 段10 对照点评（Heading2 品牌蓝）
    _add_title(doc, sect_pr, SECTION_TITLES[10])
    # 段11 case_normal（Normal，引擎加段首 🙅‍♂️）
    new_para(sect_pr, ppr_plain(), run_el(PLACEHOLDERS["case_normal"], rpr_plain()))
    # 段12 contrast_note（Markdown引用 + 浅灰底 F2F2F2）
    new_para(sect_pr, ppr_quote(), run_el(PLACEHOLDERS["contrast_note"], rpr_plain()))
    # 段13 适用边界（Heading2 品牌蓝）+ 装饰图 B（页脚横幅字节，inline 5cm）
    _add_title(doc, sect_pr, SECTION_TITLES[13], media[deco_b_name], Emu(1800000))
    # 段14/15/16 boundary_scope/misuse/evidence（b + u）
    for k in ("boundary_scope", "boundary_misuse", "boundary_evidence"):
        new_para(sect_pr, ppr_bold_underline(), run_el(PLACEHOLDERS[k], rpr_bold_underline()))
    # 段17 迁移练习（Heading2 品牌蓝）
    _add_title(doc, sect_pr, SECTION_TITLES[17])
    # 段18 exercise / 段19 self_check（b + u）
    for k in ("exercise", "self_check"):
        new_para(sect_pr, ppr_bold_underline(), run_el(PLACEHOLDERS[k], rpr_bold_underline()))
    # 段20 hashtags（endnote text 12pt）
    new_para(sect_pr, ppr_hashtag(), run_el(PLACEHOLDERS["hashtags"], rpr_hashtag()))
    # 段21 引流段：旧段19 深拷贝（endnote text + b + 85120F + jc=center，原文保留，引擎不动）
    sect_pr.addprevious(copy.deepcopy(src_paras[19]._p))
    # 段22 末图：旧段20 深拷贝（Normal + 尾页图）
    sect_pr.addprevious(copy.deepcopy(src_paras[20]._p))

    _self_check(doc, yinliu_text)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    _save_final(doc, out_path)
    print(f"[ok] baseline 写出：{out_path}")
    print(f"[ok] 段数 {EXPECTED_PARAS} / 图数 {EXPECTED_IMG_TOTAL}（pic:pic 计数）/ "
          f"字段 {EXPECTED_FIELDS} / 品牌蓝 {BRAND_BLUE} / 字体 {CONTRACT_FONT}")


def _save_final(doc, out_path: Path) -> None:
    """写盘收尾：① 剥离旧模板遗留内嵌字体（字体铁律：不内嵌字体文件）
    ② 固定时间戳重打包（重跑字节级一致，sha256 可直接作零漂移基准）。

    doc.save 先落临时文件，再逐条目重写：
    - 跳过 word/fonts/font1.odttf（Times New Roman 子集）与
      word/_rels/fontTable.xml.rels（唯一关系即指向 odttf）
    - fontTable.xml 去 <w:embedRegular/>；settings.xml 去 embedTrueTypeFonts/saveSubsetFonts
    - [Content_Types].xml 去 odttf 相关声明
    """
    import io
    import tempfile

    tmp_fd = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    tmp_path = Path(tmp_fd.name)
    tmp_fd.close()
    try:
        doc.save(str(tmp_path))
        with zipfile.ZipFile(str(tmp_path)) as zin, \
                zipfile.ZipFile(str(out_path), "w", zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                data = zin.read(name)
                if name == "word/_rels/fontTable.xml.rels" or name.startswith("word/fonts/"):
                    continue  # 内嵌字体与其关系文件：整体剥离
                if name == "word/fontTable.xml":
                    data = re.sub(rb"<w:embed(?:Regular|Bold|Italic|BoldItalic)\b[^>]*/>", b"", data)
                elif name == "word/settings.xml":
                    data = re.sub(
                        rb"<w:(?:embedTrueTypeFonts|saveSubsetFonts|embedSystemFonts)\b[^>]*/>",
                        b"", data)
                elif name == "[Content_Types].xml":
                    data = re.sub(
                        rb'<Default Extension="odttf"[^>]*/>', b"", data)
                    data = re.sub(
                        rb'<Override PartName="/word/fonts/[^"]*"[^>]*/>', b"", data)
                zi = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.create_system = 0
                zi.external_attr = 0o600 << 16
                zout.writestr(zi, data)
        _assert_no_embedded_fonts(out_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _assert_no_embedded_fonts(out_path: Path) -> None:
    """字体铁律终检：baseline 内不得有任何内嵌字体文件/嵌入声明。"""
    with zipfile.ZipFile(str(out_path)) as z:
        names = z.namelist()
        assert not [n for n in names if n.startswith("word/fonts/")], "存在内嵌字体文件"
        assert "word/_rels/fontTable.xml.rels" not in names
        ft = z.read("word/fontTable.xml")
        assert b"embedRegular" not in ft and b"embedBold" not in ft
        st = z.read("word/settings.xml")
        assert b"embedTrueTypeFonts" not in st and b"saveSubsetFonts" not in st
        ct = z.read("[Content_Types].xml")
        assert b"odttf" not in ct


def _add_title(doc, sect_pr, text, deco_bytes=None, deco_width=None):
    """蓝色标题段；deco_bytes 给定时在标题文字后追加 inline 装饰图（字节复用）。"""
    p = new_para(sect_pr, ppr_title(), run_el(text, rpr_plain()))
    if deco_bytes is not None:
        import io
        para = Paragraph(p, doc._body)
        run = para.add_run()
        run.add_picture(io.BytesIO(deco_bytes), width=deco_width)
        run._r.insert(0, el("w:rPr", None, el("w:rFonts", {"w:hint": "eastAsia"}),
                            el("w:lang", {"w:val": "en-US", "w:eastAsia": "zh-CN"})))


def _self_check(doc, yinliu_text):
    """构建后自检：任何断言失败即抛错，不写盘。"""
    body = doc.element.body
    paras = body.findall(qn("w:p"))
    assert len(paras) == EXPECTED_PARAS, f"段数 {len(paras)} != {EXPECTED_PARAS}"
    pics = body.findall(".//" + qn("pic:pic"))
    assert len(pics) == EXPECTED_IMG_TOTAL, f"pic:pic 图数 {len(pics)} != {EXPECTED_IMG_TOTAL}"
    # 封面前缀 2 处（双镜像）+ 标题占位 2 处
    p0_xml = _to_str(paras[0])
    assert p0_xml.count(escape(COVER_PREFIX)) == 2, "封面前缀非 2 处"
    title_ph = escape(f"{TITLE_FIELD} 占位")
    assert p0_xml.count(title_ph) == 2, "标题占位非 2 处"
    # 引流段原文 + 位置（段21），尾图段（段22）含图
    assert _para_text(paras[21]) == yinliu_text, "段21 引流段与旧段19 原文不一致"
    assert paras[22].findall(".//" + qn("pic:pic")), "段22 无尾图"
    # 正文引用的 r:embed 必须可解析
    rel_ids = set(doc.part.rels)
    for blip in body.findall(".//" + qn("a:blip")):
        rid = blip.get(qn("r:embed"))
        assert rid in rel_ids, f"r:embed {rid} 无对应关系"
    # 6 个固定标题文案与段位
    for idx, t in SECTION_TITLES.items():
        assert _para_text(paras[idx]) == t, f"段{idx} 标题应为 {t!r}，实为 {_para_text(paras[idx])!r}"
    # 占位文本与段位
    for idx, key in [(2, "card_point"), (3, "fix_summary"), (5, "demo"),
                     (7, "step1"), (8, "step2"), (9, "step3"),
                     (11, "case_normal"), (12, "contrast_note"),
                     (14, "boundary_scope"), (15, "boundary_misuse"),
                     (16, "boundary_evidence"), (18, "exercise"),
                     (19, "self_check"), (20, "hashtags")]:
        assert _para_text(paras[idx]) == PLACEHOLDERS[key], f"段{idx} 占位错误（{key}）"
    # 字段数（tip_title + 14 content 字段）
    assert len(PLACEHOLDERS) + 1 == EXPECTED_FIELDS, "字段数 != 15"


def _para_text(p_elem):
    return "".join(t.text or "" for t in p_elem.findall(".//" + qn("w:t")))


def _to_str(p_elem):
    from lxml import etree
    return etree.tostring(p_elem, encoding="unicode")


def main():
    ap = argparse.ArgumentParser(description="构建技巧线 23 段 4 图 baseline 模板（Task3）")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"输出 docx 路径（默认 {DEFAULT_OUT.name}）")
    ap.add_argument("--source-template", type=Path, default=Path(DEFAULT_SOURCE),
                    help="旧 21 段模板（只读；默认 vault 活模板路径）")
    args = ap.parse_args()
    build(args.out, args.source_template)


if __name__ == "__main__":
    main()

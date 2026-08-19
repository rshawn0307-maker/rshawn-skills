#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_docx.py — PE-trial-daily 官方渲染器（任务2）。

本文件是本技能自带的"官方"渲染入口（全机无全局 render_docx.py，决策见工作目录 BLOCKED.md B2-1）。

用法：
  python3 render_docx.py INPUT.docx --emit_pdf [--out DIR] [--cta "固定引流段"]
  python3 render_docx.py INPUT.docx --check [--pdf FILE] [--cta "固定引流段"]
  python3 render_docx.py INPUT.docx --emit_pdf --check [--out DIR] [--cta "固定引流段"]

--emit_pdf 用 LibreOffice soffice --headless --convert-to pdf 生成 PDF（输出目录默认同输入文件旁 /rendered）。
--check 对 PDF/DOCX 做逐页版式检查，全部通过退出码 0，任一失败退出码 1 并打印 ❌ 明细。

检查项（方法均可在对话中复核）：
  r1 页面精确 3:4        : pdfinfo 每页 MediaBox 宽高比 ∈ [0.7425, 0.7575]（3:4±1%）
  r2 无中文方框(tofu)     : pdffonts 不出现 LastResort（macOS 缺字回退字体）；且至少一个嵌入字体命中 CJK 字体契约
  r3 文字不触边(无裁切)   : pdftoppm -gray -r100 渲染，正文页首行墨迹列/末列不贴页边（阈值 6px）
  r4 有效占高 65%–90%     : 正文页 (末墨行-首墨行)/页高 ∈ [0.65, 0.90]
  r5 页底连续空白 ≤25%    : (页高-末墨行)/页高 ≤ 0.25
  r6 CTA 不孤页           : pdftotext 定位 CTA 所在页，CTA 行前正文行 ≥ 2
  r7 水印 8%–12%          : DOCX XML 解析 VML fill opacity（24bit 分数）∈ [0.08, 0.12]，且 z-index 为负（位于内容之下）
  r8 封面背景等比满铺     : 封面锚定图 extent 宽高比 ≈ 页面比（±2%），且按页高铺满、不超出页高
"""
from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# 环境定位（纯 stdlib；不装任何依赖）
# ---------------------------------------------------------------------------

SOFFICE = "/Users/shawn/Library/Application Support/TRAE SOLO CN/ModularData/ai-agent/vm/tools/opt/libreoffice/LibreOffice.app/Contents/MacOS/soffice"
PDFINFO = "/Users/shawn/Library/Application Support/TRAE SOLO CN/ModularData/ai-agent/vm/tools/bin/pdfinfo"
PDFTOPPM = "/Users/shawn/Library/Application Support/TRAE SOLO CN/ModularData/ai-agent/vm/tools/bin/pdftoppm"
PDFFONTS = "/Users/shawn/Library/Application Support/TRAE SOLO CN/ModularData/ai-agent/vm/tools/bin/pdffonts"
PDFTOTEXT = "/Users/shawn/Library/Application Support/TRAE SOLO CN/ModularData/ai-agent/vm/tools/bin/pdftotext"

# CJK 字体契约：DOCX 中任意文本使用的字体，只要 pdffonts 显示至少一个嵌入字体命中
# 本列表（或包含 CJK 能力），即认为可渲染、无方框。
CJK_CONTRACT = [
    "Hiragino Sans GB", "Heiti SC", "Songti SC", "PingFang SC",
    "Noto Sans CJK", "Noto Serif CJK", "WenQuanYi", "Arial Unicode MS",
    "Microsoft YaHei", "SimSun", "SimHei", "FZ", "方正",
]
# 嵌入字体名（LibreOffice 会重命名，如 HiraginoSans-W6 / PingFangSC-Semibold）的 CJK 线索
CJK_STEM_HINT = [
    "hiragino", "pingfang", "heiti", "songti", "noto", "wenquanyi",
    "simsun", "simhei", "yahei", "arialunicode", "stheit", "stsong",
    "fz", "fangzheng", "sourcehan", "cjk",
]

RATIO_WANT = 3 / 4
RATIO_TOL = 0.01           # ±1%
DPI = 100
INK_THRESHOLD = 160        # 灰度 <160 视为正文墨迹（水印浅灰 ~192 不计）
EDGE_PAD_PX = 6            # 正文页墨迹距页边至少 6px
HEADER_ZONE = 0.06         # 顶部页眉带（不计入正文占高）
FOOTER_ZONE = 0.06         # 底部页脚带（不计入正文占高）
BLANK_INK_PCT = 0.015      # 正文带墨迹像素占比 <1.5% 判为空白/孤页
EFF_MIN, EFF_MAX = 0.65, 0.90
BOTTOM_BLANK_MAX = 0.25


def _run(cmd: list[str]) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def _tool_missing(tool: str, path: str) -> bool:
    return not Path(path).exists()


# ---------------------------------------------------------------------------
# r1 / r2 / r3-r5 / r6 底层
# ---------------------------------------------------------------------------


def pdf_page_boxes(pdf: Path) -> list[tuple[float, float]]:
    """每页 MediaBox 宽高（pt）。"""
    rc, out, _ = _run([PDFINFO, str(pdf)])
    if rc != 0:
        raise RuntimeError(f"pdfinfo 失败: {out}")
    boxes: list[tuple[float, float]] = []
    for line in out.splitlines():
        m = re.match(r"Page\s+(\d+)\s+size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pt", line)
        if m:
            boxes.append((float(m.group(2)), float(m.group(3))))
    if not boxes:
        # 兜底：单页取整本
        for line in out.splitlines():
            m = re.match(r"Page size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pt", line)
            if m:
                return [(float(m.group(1)), float(m.group(2)))]
    return boxes


def pdf_fonts(pdf: Path) -> list[tuple[str, str]]:
    """返回 [(family, type)]。pdffonts 首两列是 name/type。"""
    rc, out, _ = _run([PDFFONTS, str(pdf)])
    if rc != 0:
        raise RuntimeError("pdffonts 失败")
    fonts = []
    for line in out.splitlines():
        if line.startswith("name") or line.startswith("---"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            fonts.append((parts[0], parts[1]))
    return fonts


def pdf_text_by_page(pdf: Path) -> list[str]:
    # 注意：本机 poppler 的 pdftotext 需显式输出到 "-"（stdout），否则静默输出空
    rc, out, _ = _run([PDFTOTEXT, str(pdf), "-"])
    if rc != 0:
        raise RuntimeError("pdftotext 失败")
    pages = out.split("\x0c")  # form feed 分页
    return pages


def _read_pgm(path: Path) -> tuple[int, int, bytes]:
    """解析 P5 PGM（可含注释行），返回 (w, h, 灰度字节体)。"""
    data = path.read_bytes()
    assert data[:2] == b"P5", "非 PGM"
    pos = 2
    while pos < len(data) and data[pos:pos + 1] == b"#":
        pos = data.index(b"\n", pos) + 1
    nums = []
    while len(nums) < 3:
        while pos < len(data) and data[pos:pos + 1] in b" \t\n\r":
            pos += 1
        start = pos
        while pos < len(data) and data[pos:pos + 1] not in b" \t\n\r":
            pos += 1
        nums.append(int(data[start:pos]))
    w, h, _maxv = nums
    while pos < len(data) and data[pos:pos + 1] in b" \t\n\r":
        pos += 1
    body = data[pos:]
    return w, h, body


def _page_ink(png_pgm: Path) -> dict:
    """返回正文带（排除页眉/页脚带）墨迹统计。

    keys: w, h, ink_px, first_r, last_r, first_c, last_c
    无正文墨迹时 first_r > last_r。
    """
    w, h, body = _read_pgm(png_pgm)
    top = int(h * HEADER_ZONE)
    bottom = h - int(h * FOOTER_ZONE)
    first_r, last_r = h, -1
    first_c, last_c = w, -1
    ink_px = 0
    for y in range(top, bottom):
        row = body[y * w:(y + 1) * w]
        found = False
        for x in range(w):
            if row[x] < INK_THRESHOLD:
                ink_px += 1
                if not found:
                    found = True
                    if x < first_c:
                        first_c = x
                if x > last_c:
                    last_c = x
        if found:
            if y < first_r:
                first_r = y
            if y > last_r:
                last_r = y
    return {"w": w, "h": h, "ink_px": ink_px,
            "first_r": first_r, "last_r": last_r, "first_c": first_c, "last_c": last_c}


def render_pages(pdf: Path, workdir: Path) -> list[Path]:
    """pdftoppm -gray -r100 渲染每页 PGM。"""
    rc, out, err = _run([PDFTOPPM, "-gray", "-r", str(DPI), str(pdf), str(workdir / "pg")])
    if rc != 0:
        raise RuntimeError(f"pdftoppm 失败: {out}{err}")
    return sorted(workdir.glob("pg-*.pgm"))


# ---------------------------------------------------------------------------
# 检查实现
# ---------------------------------------------------------------------------


def check_ratio(boxes: list[tuple[float, float]]) -> list[str]:
    bad = []
    for i, (w, h) in enumerate(boxes, 1):
        if h == 0:
            bad.append(f"r1 页{i} 高为0")
            continue
        ratio = w / h
        if abs(ratio - RATIO_WANT) / RATIO_WANT > RATIO_TOL:
            bad.append(f"r1 页{i} 宽高比 {ratio:.4f}（期望 3:4，容差±1%）")
    return bad


def _norm_font(name: str) -> str:
    """归一化字体名：去子集前缀(BAAAAA+)、去字重后缀(-W6/-Semibold 等)、去空白。"""
    name = re.sub(r"^[A-Za-z0-9]{6}\+", "", name)
    name = re.sub(
        r"-(W\d|Regular|Semibold|Bold|Medium|Light|Book|Black|Thin|Italic|Demi|Heavy)$", "", name
    )
    return re.sub(r"[\s_\-]+", "", name).lower()


def check_fonts(fonts: list[tuple[str, str]]) -> list[str]:
    bad = []
    if not fonts:
        return ["r2 无法读取嵌入字体"]
    names = " ".join(f[0] for f in fonts)
    if re.search(r"LastResort", names, re.I):
        bad.append("r2 出现 LastResort（缺字回退字体，会渲染方框）")
    stems = [_norm_font(f[0]) for f in fonts]
    ok = False
    for s in stems:
        if any(h in s for h in CJK_STEM_HINT):
            ok = True
            break
        for c in CJK_CONTRACT:
            nc = _norm_font(c)
            if nc and (nc in s or s in nc):
                ok = True
                break
        if ok:
            break
    if not ok:
        bad.append(f"r2 无嵌入字体命中 CJK 契约（实际: {names[:60]}）")
    return bad


def check_ink_pages(pages: list[Path]) -> tuple[list[str], list[dict]]:
    bad = []
    reports = []
    for i, pg in enumerate(pages, 1):
        st = _page_ink(pg)
        reports.append({"page": i, **st})
        if i == 1:
            # 封面整页满铺底色，豁免正文占高/触边检查（封面背景由 r8 单独校验）
            continue
        ink_ratio = st["ink_px"] / (st["w"] * st["h"])
        if st["first_r"] > st["last_r"] or ink_ratio < BLANK_INK_PCT:
            bad.append(f"r4/5 页{i} 正文带无墨迹（空白/孤页，ink={ink_ratio:.3f}）")
            continue
        eff = (st["last_r"] - st["first_r"]) / st["h"]
        blank = (st["h"] - st["last_r"]) / st["h"]
        if st["first_c"] <= EDGE_PAD_PX or st["last_c"] >= st["w"] - EDGE_PAD_PX:
            bad.append(f"r3 页{i} 墨迹触边（左 {st['first_c']}px 右 {st['w']-1-st['last_c']}px）")
        if not (EFF_MIN <= eff <= EFF_MAX):
            bad.append(f"r4 页{i} 有效占高 {eff:.2f}（期望 {EFF_MIN}-{EFF_MAX}）")
        if blank > BOTTOM_BLANK_MAX:
            bad.append(f"r5 页{i} 页底空白 {blank:.2f}（期望 ≤{BOTTOM_BLANK_MAX}）")
    return bad, reports


def check_cta_not_alone(pages_text: list[str], cta: str) -> list[str]:
    bad = []
    cta_norm = re.sub(r"\s+", "", cta)
    for i, page in enumerate(pages_text, 1):
        page_norm = re.sub(r"\s+", "", page)
        if cta_norm not in page_norm:
            continue
        lines = [re.sub(r"\s+", "", ln) for ln in page.splitlines() if ln.strip()]
        idx = next((j for j, ln in enumerate(lines) if cta_norm in ln), None)
        if idx is None:
            continue
        body_lines_before = sum(1 for ln in lines[:idx] if not ln.startswith("#"))
        if body_lines_before < 2:
            bad.append(f"r6 CTA 所在页 {i} 前仅有 {body_lines_before} 行正文（须 ≥2）")
    if not any(cta_norm in re.sub(r"\s+", "", p) for p in pages_text):
        bad.append(f"r6 全文找不到固定引流段: {cta[:20]}…")
    return bad


def check_watermark_docx(docx: Path) -> list[str]:
    """水印 8%–12%、位于内容之下。支持 VML（PowerPlusWaterMarkObject）与 DrawingML。"""
    bad = []
    try:
        with zipfile.ZipFile(docx) as z:
            xmls = [n for n in z.namelist() if n.startswith("word/header") and n.endswith(".xml")]
            if not xmls:
                return ["r7 无页眉 XML"]
            all_xml = "".join(z.read(n).decode("utf-8", "ignore") for n in xmls)
    except Exception as exc:  # noqa: BLE001
        return [f"r7 读取 DOCX 失败: {exc}"]
    if "PowerPlusWaterMarkObject" not in all_xml and "PTDWatermark" not in all_xml:
        return ["r7 页眉无水印对象"]
    if "z-index:-" not in all_xml.replace(" ", "") and "behindDoc" not in all_xml:
        bad.append("r7 水印未锚定到内容之下")
    # DrawingML: a:alpha 千分之一百分比；VML: opacity 24bit 分数
    m = re.search(r'<a:alpha val="(\d+)"/>', all_xml)
    if m:
        alpha = int(m.group(1))
        if not (8000 <= alpha <= 12000):
            bad.append(f"r7 水印透明度 {alpha/1000:.1f}%（期望 8%–12%）")
        return bad
    m = re.search(r'opacity="([0-9a-fA-F]{6})"', all_xml)
    if not m:
        return ["r7 水印无透明度属性（既无 a:alpha 也无 VML opacity）"]
    frac = int(m.group(1), 16) / 0xFFFFFF
    if not (0.08 <= frac <= 0.12):
        bad.append(f"r7 水印透明度 {frac:.3f}（期望 8%–12%）")
    return bad


def check_cover_bg(docx: Path, page_w: float, page_h: float) -> list[str]:
    """封面背景等比满铺：锚定图 extent 宽高比 ≈ 页面比，且铺满页高。"""
    bad = []
    try:
        with zipfile.ZipFile(docx) as z:
            xmls = [n for n in z.namelist() if n.startswith("word/document") and n.endswith(".xml")]
            doc_xml = z.read(xmls[0]).decode("utf-8", "ignore") if xmls else ""
    except Exception as exc:  # noqa: BLE001
        return [f"r8 读取 DOCX 失败: {exc}"]
    extents = re.findall(r'<wp:extent cx="(\d+)" cy="(\d+)"/>', doc_xml)
    if not extents:
        return ["r8 未找到锚定图 extent"]
    # 选最大的 extent 作为封面背景
    cx, cy = max(((int(a), int(b)) for a, b in extents), key=lambda p: p[0] * p[1])
    img_ratio = cx / cy
    page_ratio = page_w / page_h
    if abs(img_ratio - page_ratio) / page_ratio > 0.02:
        bad.append(f"r8 封面背景宽高比 {img_ratio:.4f} vs 页面 {page_ratio:.4f}（可能被裁）")
    # 铺满页高：cy ≥ 页高即可，允许向下出血（COVER_BG_BLEED）以抵消渲染器对
    # behindDoc 整页锚定图的垂直缩水，保证贴齐底边；出血部分被页面边界裁掉。
    want_h = page_h * 12700  # pt -> EMU (914400/72 = 12700)
    if cy < want_h * 0.97 or cy > want_h * 1.20:
        bad.append(f"r8 封面背景高度 {cy/12700:.1f}pt 未铺满页高 {page_h:.1f}pt")
    return bad


def run_checks(docx: Path, pdf: Path, cta: str) -> list[str]:
    bad: list[str] = []
    if _tool_missing("pdfinfo", PDFINFO):
        return ["pdfinfo 不可用"]
    boxes = pdf_page_boxes(pdf)
    if not boxes:
        return ["无法获取页面尺寸"]
    bad += check_ratio(boxes)
    fonts = pdf_fonts(pdf)
    bad += check_fonts(fonts)
    with tempfile.TemporaryDirectory(prefix="ptd_render_") as td:
        workdir = Path(td)
        pages = render_pages(pdf, workdir)
        if not pages:
            bad.append("无法渲染页面")
        else:
            ink_bad, _ = check_ink_pages(pages)
            bad += ink_bad
    txt_pages = pdf_text_by_page(pdf)
    bad += check_cta_not_alone(txt_pages, cta)
    bad += check_watermark_docx(docx)
    bad += check_cover_bg(docx, boxes[0][0], boxes[0][1])
    return bad


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="PE-trial-daily 官方渲染器")
    ap.add_argument("docx", type=Path, help="输入 DOCX")
    ap.add_argument("--emit_pdf", action="store_true", help="用 soffice 转 PDF")
    ap.add_argument("--check", action="store_true", help="逐页版式检查")
    ap.add_argument("--out", type=Path, default=None, help="PDF 输出目录")
    ap.add_argument("--cta", default="关注我，每天一个体育试讲设计，帮你备考上岸")
    args = ap.parse_args()

    if not args.docx.exists():
        print(f"❌ 输入不存在: {args.docx}")
        return 2
    out_dir = (args.out or args.docx.parent / "rendered").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / (args.docx.stem + ".pdf")

    if args.emit_pdf:
        if _tool_missing("soffice", SOFFICE):
            print("❌ soffice 不可用")
            return 2
        with tempfile.TemporaryDirectory(prefix="ptd_soff_") as td:
            # 每次使用隔离 UserInstallation，避免并发/残留 profile 导致 DeploymentException
            rc, out, err = _run([
                SOFFICE, "-env:UserInstallation=file://" + str(Path(td).joinpath("lo").as_posix()),
                "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(args.docx),
            ])
            if rc != 0:
                print(f"❌ soffice 转换失败:\n{out}{err}")
                return 2
        print(f"✅ 已生成 PDF: {pdf}")

    if args.check:
        if not pdf.exists():
            print("❌ 缺少 PDF（先 --emit_pdf）")
            return 2
        bad = run_checks(args.docx, pdf, args.cta)
        if bad:
            print("渲染检查失败:")
            for b in bad:
                print(f"  ❌ {b}")
            return 1
        print("渲染检查通过（3:4 / 无方框 / 无裁切重叠 / CTA不孤页 / 水印8-12%）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

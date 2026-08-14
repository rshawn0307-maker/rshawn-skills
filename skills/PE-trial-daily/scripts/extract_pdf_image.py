#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从人教版教师用书 PDF 提取图例图片（基于 OCR 页索引定位）。

所有教师用书 PDF 均为纯扫描件（无文本层），必须先用 macOS Vision OCR
建立 ocr_index/{sport}.json 索引（见 build_ocr_index.py），才能把 MD 中的
图例引用（如 图3-2-7）映射到 PDF 页码。

用法:
    python3 extract_pdf_image.py <sport> <figure_ref> [--caption "图例说明"] [--outdir DIR]

参数:
    sport      运动项目名（如 篮球），对应 人教版教师用书-{sport}.pdf
    figure_ref 图例引用（如 图3-2-7，或 图3-2-7、图3-2-8）
    --caption  图例说明文字（可选，用于输出文件名）
    --outdir   输出目录（默认 _extracted_images/）

输出:
    提取成功的图片路径（每张一行），写入 stdout。
    未找到时返回空，退出码 0。
"""
import argparse
import json
import os
import re
import sys

import fitz  # PyMuPDF

TEACHER_BOOK_DIR = "/Users/shawn/Desktop/AI工作区/03-Resources/各版本体育教材/人教版"
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
OCR_INDEX_DIR = os.path.join(SKILL_DIR, "ocr_index")
DEFAULT_OUTDIR = os.path.join(SKILL_DIR, "_extracted_images")


def normalize_ref(ref):
    """图3-2-7 / 图 3 - 2 - 7 / 图3- 2- 7 归一化为去掉空格与连字符的紧凑串。"""
    return re.sub(r"[\s\-\.]", "", ref)


def find_pdf_path(sport):
    for c in (
        os.path.join(TEACHER_BOOK_DIR, f"人教版教师用书-{sport}.pdf"),
        os.path.join(TEACHER_BOOK_DIR, f"人教版教师用书-{sport}.pdf"),
    ):
        if os.path.isfile(c):
            return c
    return None


def load_ocr_index(sport):
    """读取或构建 OCR 页索引，返回 {page(str): text}。"""
    path = os.path.join(OCR_INDEX_DIR, f"{sport}.json")
    if not os.path.isfile(path):
        # 懒构建：调用 build_ocr_index.py
        import subprocess
        subprocess.run(
            [sys.executable, os.path.join(SKILL_DIR, "build_ocr_index.py"), sport],
            check=True,
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_pages_with_ref(index, ref):
    """在 OCR 索引中查找含图例引用的页码，返回页码列表（int）。"""
    ref_norm = normalize_ref(ref)
    if not ref_norm:
        return []
    hits = []
    for pno, text in index.items():
        if ref_norm in normalize_ref(text):
            hits.append(int(pno))
    hits.sort()
    return hits


def extract_page_images(pdf_path, pages, sport, figure_ref, outdir, max_pages=2):
    """从指定页渲染整页图（应用页面旋转），返回保存路径列表。

    教师用书每页为一张扫描大图，直接渲染整页可自动应用 rotation=180，
    避免内嵌 xref 提取带来的上下颠倒问题。
    """
    saved = []
    doc = fitz.open(pdf_path)
    tag = normalize_ref(figure_ref).replace("-", "_")
    for pno in pages[:max_pages]:
        page = doc[pno]
        # 2 倍缩放渲染，兼顾清晰度与体积
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        if pix.width < 80 or pix.height < 80:
            continue
        fname = f"图例_{sport}_{tag}_p{pno}.png"
        fpath = os.path.join(outdir, fname)
        pix.save(fpath)
        saved.append(fpath)
    doc.close()
    return saved


def main():
    parser = argparse.ArgumentParser(description="从教师用书 PDF 提取图例图片")
    parser.add_argument("sport", help="运动项目名，如 篮球")
    parser.add_argument("figure_ref", help="图例引用，如 图3-2-7 或 图3-2-7、图3-2-8")
    parser.add_argument("--caption", default="", help="图例说明文字")
    parser.add_argument("--outdir", default=DEFAULT_OUTDIR)
    args = parser.parse_args()

    pdf_path = find_pdf_path(args.sport)
    if not pdf_path:
        print(f"ERROR: 未找到 PDF: 人教版教师用书-{args.sport}.pdf", file=sys.stderr)
        sys.exit(1)

    index = load_ocr_index(args.sport)
    os.makedirs(args.outdir, exist_ok=True)

    # 支持逗号分隔多个图例
    refs = [r.strip() for r in re.split(r"[、,，]", args.figure_ref) if r.strip()]
    saved = []
    for ref in refs:
        pages = find_pages_with_ref(index, ref)
        if not pages:
            print(f"WARN: OCR 索引未命中图例 {ref}", file=sys.stderr)
            continue
        saved.extend(extract_page_images(pdf_path, pages, args.sport, ref, args.outdir))

    saved = list(dict.fromkeys(saved))
    for s in saved:
        print(s)
    if not saved:
        print(f"WARN: 图例 {args.figure_ref} 未提取到图片", file=sys.stderr)


if __name__ == "__main__":
    main()
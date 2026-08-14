#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建教师用书 OCR 页索引（一次性，缓存到 ocr_index/{sport}.json）。

用法:
    python3 build_ocr_index.py <sport> [_sport2 ...]

所有 PDF 均为纯扫描件（无文本层），必须用 macOS Vision OCR 建索引，
才能把 MD 中的图例引用（如 图3-2-7）映射到 PDF 页码。

输出:
    ocr_index/{sport}.json  ->  { "0": "page0文本", "1": "page1文本", ... }
"""
import json
import os
import subprocess
import sys

TEACHER_BOOK_DIR = "/Users/shawn/Desktop/AI工作区/03-Resources/各版本体育教材/人教版"
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_DIR = os.path.join(SKILL_DIR, "ocr_index")
SWIFT_BATCH = os.path.join(SKILL_DIR, "ocr_batch.swift")


def build_index(sport):
    pdf = os.path.join(TEACHER_BOOK_DIR, f"人教版教师用书-{sport}.pdf")
    if not os.path.isfile(pdf):
        print(f"SKIP: 未找到 {pdf}", file=sys.stderr)
        return None

    out = os.path.join(INDEX_DIR, f"{sport}.json")
    if os.path.isfile(out):
        print(f"SKIP: 索引已存在 {out}")
        return out

    os.makedirs(INDEX_DIR, exist_ok=True)

    # 先拿页数
    import pymupdf
    doc = pymupdf.open(pdf)
    total = doc.page_count
    doc.close()
    print(f"OCR {sport}: {total} 页 ...", file=sys.stderr)

    index = {}
    # 分块进度输出，逐页累加
    proc = subprocess.run(
        ["swift", SWIFT_BATCH, pdf, "0", str(total)],
        capture_output=True, text=True, timeout=3600,
    )
    if proc.returncode != 0:
        # 输出可能部分行已在 stdout
        print(f"WARN: swift 返回码 {proc.returncode}: {proc.stderr[:500]}", file=sys.stderr)

    for line in proc.stdout.splitlines():
        if not line.startswith("PAGE\t"):
            continue
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        pno = int(parts[1])
        text = parts[2].replace("␊", "\n")
        index[str(pno)] = text

    with open(out, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print(f"OK: {len(index)} 页 -> {out}")
    return out


def main():
    sports = sys.argv[1:]
    if not sports:
        print("用法: python3 build_ocr_index.py <sport> [sport...]")
        sys.exit(1)
    for s in sports:
        build_index(s)


if __name__ == "__main__":
    main()
# -*- coding: utf-8 -*-
"""
fill_tips_post.py v1
==========================

「结构化答题技巧·每日一练」帖子生成脚本（技巧教学型）。

自动化流程：
  1. agent 把新技巧稿写到 scripts/pending_tips.json
  2. agent 调本脚本
  3. 脚本读 json → 写 docx → 验证 → 删 json

输入文件：scripts/pending_tips.json
输出文件：模板位置 .docx（原地覆盖）

JSON schema（硬性，13 个顶层 key）：
  tip_title          封面钩子标题（≤20 字，不带"答题技巧："前缀）
  question_type      适用题型（如 综合分析题）
  tip_intro          技巧一句话（破题角度）
  step1..step3       思路步骤拆解（3 条）
  case_normal        普通答法（真题片段）
  case_normal_note   普通答法点评
  case_high          高分答法（同题对照）
  case_high_note     高分答法点评
  pitfalls           避坑提醒
  tip_takeaway       一句话总结
  hashtags           话题标签（#标签 #标签）
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


# ===== 路径配置 =====
SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
TEMPLATE_PATH = WORKSPACE / "desktop-attachments" / "3 结构化答题技巧-帖子内容编辑模板.docx"
PENDING_JSON = SCRIPT_DIR / "pending_tips.json"
BACKUP_PATH = SCRIPT_DIR / "_backup_template_技巧原版.docx"
SNAPSHOT_DIR = SCRIPT_DIR / "_snapshots_tips"
MAX_SNAPSHOTS = 10

COVER_PREFIX = "答题技巧："      # 段[0] 文本框前缀（2 镜像同步）
HASHTAG_COLOR = "85120F"        # 引流段颜色（品牌铁律，段[15] 固定）


def take_snapshot():
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    if not TEMPLATE_PATH.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_path = SNAPSHOT_DIR / f"snapshot_{ts}.docx"
    shutil.copy(TEMPLATE_PATH, snapshot_path)
    snapshots = sorted(SNAPSHOT_DIR.glob("snapshot_*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in snapshots[MAX_SNAPSHOTS:]:
        old.unlink()
    return snapshot_path


# ===== 段位映射（技巧教学型） =====
REPLACE_MAP = [
    (2, "question_type"),
    (3, "tip_intro"),
    (4, "step1"),
    (5, "step2"),
    (6, "step3"),
    (7, "case_normal"),
    (8, "case_normal_note"),
    (9, "case_high"),
    (10, "case_high_note"),
    (11, "pitfalls_lead"),
    (12, "pitfalls"),
    (13, "tip_takeaway"),
    (14, "hashtags"),
]


def resolve_content(content: dict, key: str):
    return content[key]


def replace_textbox_question(paragraph, new_question: str):
    """替换段内所有文本框的第 2 个 <w:t>（封面大标题），保留第 1 个前缀。"""
    modified = 0
    for txbx in paragraph._element.iter(qn('w:txbxContent')):
        text_runs = txbx.findall('.//' + qn('w:t'))
        if len(text_runs) >= 2:
            text_runs[1].text = new_question
            modified += 1
        elif len(text_runs) == 1:
            text_runs[0].text = new_question
            modified += 1
    return modified


def set_textbox_prefix(paragraph, prefix: str):
    """段[0] 文本框前缀统一设为 prefix（2 镜像同步）。"""
    for txbx in paragraph._element.iter(qn('w:txbxContent')):
        text_runs = txbx.findall('.//' + qn('w:t'))
        if text_runs:
            text_runs[0].text = prefix


def ensure_pagebreak_before(paragraph):
    pPr = paragraph._element.find(qn('w:pPr'))
    if pPr is None:
        pPr = paragraph._element.makeelement(qn('w:pPr'), {})
        paragraph._element.insert(0, pPr)
    if pPr.find(qn('w:pageBreakBefore')) is None:
        pgBreak = OxmlElement('w:pageBreakBefore')
        pPr.append(pgBreak)


def replace_run_text_safely(paragraph, new_text: str):
    """找第一个纯文本 run（无 drawing）写入，图片 run 完全不动。"""
    runs = paragraph.runs
    if not runs:
        paragraph.add_run(new_text)
        return

    target = None
    for r in runs:
        has_t = bool(r._element.findall('.//' + qn('w:t')))
        has_d = bool(r._element.findall('.//' + qn('w:drawing')))
        if has_t and not has_d:
            target = r
            break

    if target is None:
        paragraph.add_run(new_text)
        return

    target.text = new_text

    for r in runs:
        if r is target:
            continue
        has_d = bool(r._element.findall('.//' + qn('w:drawing')))
        if has_d:
            continue
        r.text = ""


def validate_output():
    doc = Document(TEMPLATE_PATH)
    errors = []

    if len(doc.paragraphs) != 17:
        errors.append(f"段数异常: {len(doc.paragraphs)} (期望 17)")

    img_total = sum(len(p._element.findall('.//' + qn('w:drawing'))) for p in doc.paragraphs)
    if img_total != 5:
        errors.append(f"图片总数: {img_total} (期望 5)")

    p15 = doc.paragraphs[15]
    r0 = p15.runs[0]
    if not (p15.alignment == 1 and r0.bold is True and str(r0.font.color.rgb) == HASHTAG_COLOR):
        errors.append("引流段样式丢失（段[15] 须加粗 + #85120F + 居中）")

    # 段[0] 文本框：2 个 + 前缀"答题技巧："
    txbx_count = 0
    for txbx in doc.paragraphs[0]._element.iter(qn('w:txbxContent')):
        txbx_count += 1
        text_runs = txbx.findall('.//' + qn('w:t'))
        if len(text_runs) < 2:
            errors.append(f"段[0] 文本框结构异常：<w:t> 数量 {len(text_runs)}")
        elif text_runs[0].text != COVER_PREFIX:
            errors.append(f"段[0] 文本框前缀被改动: {text_runs[0].text!r}")
    if txbx_count != 2:
        errors.append(f"段[0] 文本框数: {txbx_count} (期望 2)")

    # 段[7] 应有 pageBreakBefore（正文从第 3 页开始）
    p7_pPr = doc.paragraphs[7]._element.find(qn('w:pPr'))
    if p7_pPr is None or p7_pPr.find(qn('w:pageBreakBefore')) is None:
        errors.append("段[7] 缺 pageBreakBefore（正文应从第 3 页开始）")

    return errors


def main():
    if not PENDING_JSON.exists():
        print(f"[ERROR] 待写入文件不存在: {PENDING_JSON}")
        print("        请先 agent 把新内容写到 pending_tips.json")
        sys.exit(1)

    if not TEMPLATE_PATH.exists():
        print(f"[ERROR] 模板不存在: {TEMPLATE_PATH}")
        sys.exit(1)

    print(f"[0/4] 快照备份")
    snap = take_snapshot()
    if snap:
        print(f"      {snap.name}")

    with open(PENDING_JSON, 'r', encoding='utf-8') as f:
        content = json.load(f)

    print(f"[1/4] 读取待写入内容: {PENDING_JSON}")
    print(f"      字段数: {len(content)} (期望 13)")

    doc = Document(TEMPLATE_PATH)

    if "tip_title" not in content:
        print(f"[ERROR] pending_tips.json 缺 'tip_title' 字段")
        sys.exit(1)

    print(f"[2/4] 写入 段[0] 文本框封面标题（前缀改 {COVER_PREFIX}）")
    set_textbox_prefix(doc.paragraphs[0], COVER_PREFIX)
    modified = replace_textbox_question(doc.paragraphs[0], content["tip_title"])
    print(f"      修改了 {modified} 个文本框（期望 2：drawing 镜像 + VML fallback）")

    print(f"[2.5/4] 写入 {len(REPLACE_MAP)} 个段位（正文）")
    for para_idx, key in REPLACE_MAP:
        para = doc.paragraphs[para_idx]
        new_text = resolve_content(content, key)
        replace_run_text_safely(para, new_text)

    print(f"[2.6/4] 锁定版式：段[7] 正文首段强制 pageBreakBefore")
    ensure_pagebreak_before(doc.paragraphs[7])

    print(f"[3/4] 保存到 {TEMPLATE_PATH.name}")
    doc.save(TEMPLATE_PATH)

    print(f"[4/4] 自动验证")
    errors = validate_output()
    if errors:
        print(f"[FAIL] 发现 {len(errors)} 个问题:")
        for e in errors:
            print(f"  - {e}")
        print(f"[KEEP] pending_tips.json 保留，便于排查")
        sys.exit(1)

    print(f"[OK] 全部验证通过！")
    print(f"     ✅ 段数 17")
    print(f"     ✅ 5 张图片全在")
    print(f"     ✅ 引流段样式保留")
    print(f"[CLEAN] 清理 pending_tips.json")
    PENDING_JSON.unlink()

    print(f"\n{'='*50}")
    print(f"模板已更新: {TEMPLATE_PATH}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
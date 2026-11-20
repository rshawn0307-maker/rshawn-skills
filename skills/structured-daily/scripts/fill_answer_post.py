#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fill_answer_post.py v2（答一道引擎，structured-daily 答题线）
==========================

移植来源：本文件自 structured-post 引擎原样移植（不重设计），
  源 = vault scripts/fill_structured_post.py v2（19 段 5 图契约版），
  移植日期 2026-11-20（structured-daily 阶段 1 修订 TR1，答一道单线转型）。
  仅两处适配：①项目根解析改 --project-root > 环境变量 ANSWER_PROJECT_ROOT > 报错
  （取消旧 __file__ 相对路径 fallback，引擎收 skill 内后相对解析会误写 skill 目录）
  ②本 docstring 移植来源标注。其余逻辑（19 段 5 图契约 / 写入前段数预检 /
  验证逻辑 / 快照 / 原子覆盖写入 / 退出码语义）与源版本一致，现行健康。

自动化流程：
  1. agent 把新答稿写到 scripts/pending_answer.json
  2. agent 调本脚本
  3. 脚本读 json → 写 docx → 验证 → 删 json

输入文件：scripts/pending_answer.json
输出文件：模板位置 .docx（原地覆盖）

用法：
  python3 fill_answer_post.py --project-root <项目根>
  项目根解析：--project-root > 环境变量 ANSWER_PROJECT_ROOT > 报错 exit 1
"""

import argparse
import json
import os
import shutil
import sys
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn


# ===== 路径配置（项目根内相对布局，与源版本一致）=====
TEMPLATE_REL = Path("desktop-attachments") / "1 结构化每日一练-帖子内容编辑模板.docx"
PENDING_REL = Path("scripts") / "pending_answer.json"
BACKUP_REL = Path("scripts") / "_backup_template_原版.docx"
SNAPSHOT_REL = Path("scripts") / "_snapshots"
MAX_SNAPSHOTS = 10


def resolve_project_root(cli_value: str) -> Path:
    """--project-root > 环境变量 ANSWER_PROJECT_ROOT > 报错 exit 1
    （TR1 适配：取消源版本 SCRIPT_DIR/WORKSPACE 相对路径 fallback，防误写 skill 目录）。"""
    if cli_value:
        root = Path(cli_value).expanduser()
    else:
        env_root = os.environ.get("ANSWER_PROJECT_ROOT")
        if not env_root:
            print("[ERROR] 项目根未指定（TR1 移植版已取消相对路径 fallback，防误写 skill 目录）")
            print("        请用 --project-root <项目根> 或环境变量 ANSWER_PROJECT_ROOT 显式传入")
            sys.exit(1)
        root = Path(env_root).expanduser()
    if not root.is_dir():
        print(f"[ERROR] 项目根不存在: {root}")
        sys.exit(1)
    return root


def take_snapshot(root: Path):
    """跑脚本前自动备份当前模板到 _snapshots/，保留最近 MAX_SNAPSHOTS 个。"""
    snapshot_dir = root / SNAPSHOT_REL
    template_path = root / TEMPLATE_REL
    snapshot_dir.mkdir(exist_ok=True)
    if not template_path.exists():
        return None
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_path = snapshot_dir / f"snapshot_{ts}.docx"
    shutil.copy(template_path, snapshot_path)
    # 清理超出数量的旧快照（按修改时间倒序，删多余的）
    snapshots = sorted(snapshot_dir.glob("snapshot_*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in snapshots[MAX_SNAPSHOTS:]:
        old.unlink()
    return snapshot_path


# ===== 段位映射（模板 19 段结构 v3，2026-09-13 适配）=====
# 大纲区 [2]-[8]：破题角度 / 切入理由 / 核心观点标题 / intro / 3 观点
# 正文区 [9]-[16]：opening / 3×(lead+body) / closing
# [17] 引流段不动，[18] 末尾装饰图不动
REPLACE_MAP = [
    (2, "break_angle"),
    (3, "break_angle_reason"),
    (4, "core_views_title"),
    (5, "core_views_intro"),
    (6, "core_views[0]"),
    (7, "core_views[1]"),
    (8, "core_views[2]"),
    (9, "opening"),
    (10, "point1_lead"),
    (11, "point1_body"),
    (12, "point2_lead"),
    (13, "point2_body"),
    (14, "point3_lead"),
    (15, "point3_body"),
    (16, "closing"),
]
EXPECTED_PARAS = 19
TAIL_PROMO_IDX = 17  # 引流段
FIRST_BODY_IDX = 9   # 正文首段（pageBreakBefore 所在）

# 封面文本框前缀（段[0] 第一个 <w:t>）
# 自出题/热点题默认「结构化每日一练：」
# 真题库选题必须传 title_prefix="结构化历年考题："（见 SKILL.md）
DEFAULT_TITLE_PREFIX = "结构化每日一练："
REAL_EXAM_TITLE_PREFIX = "结构化历年考题："


def resolve_content(content: dict, key: str):
    if "[" in key and key.endswith("]"):
        base, idx = key.split("[", 1)
        idx = int(idx.rstrip("]"))
        return content[base][idx]
    return content[key]


def replace_textbox_question(paragraph, new_question: str, title_prefix: str = DEFAULT_TITLE_PREFIX):
    """
    B 方案：替换段内所有文本框的第二个 <w:t>（题目正文），并写入前缀到第一个 <w:t>。
    前缀字体格式保留（只改 text，不动 run 属性）。
    处理 drawing 镜像 + VML fallback（同一文本框被存两份）。
    """
    modified = 0
    for txbx in paragraph._element.iter(qn('w:txbxContent')):
        text_runs = txbx.findall('.//' + qn('w:t'))
        if len(text_runs) >= 2:
            text_runs[0].text = title_prefix
            text_runs[1].text = new_question
            modified += 1
        elif len(text_runs) == 1:
            # 兜底：只有 1 个 <w:t>，说明结构变了，写入它
            text_runs[0].text = new_question
            modified += 1
    return modified


def ensure_pagebreak_before(paragraph):
    """
    A+C 方案：给段落加 pageBreakBefore 属性（段前分页符）。
    已存在则跳过，不重复添加。
    """
    pPr = paragraph._element.find(qn('w:pPr'))
    if pPr is None:
        pPr = paragraph._element.makeelement(qn('w:pPr'), {})
        paragraph._element.insert(0, pPr)
    if pPr.find(qn('w:pageBreakBefore')) is None:
        # 用 Subelement 干净插入
        from docx.oxml import OxmlElement
        pgBreak = OxmlElement('w:pageBreakBefore')
        pPr.append(pgBreak)


def remove_pagebreak_before(paragraph):
    """清除段落的 pageBreakBefore（用于纠正大纲区历史误加）。"""
    pPr = paragraph._element.find(qn('w:pPr'))
    if pPr is None:
        return
    pb = pPr.find(qn('w:pageBreakBefore'))
    if pb is not None:
        pPr.remove(pb)


def replace_run_text_safely(paragraph, new_text: str):
    """v3: 找第一个纯文本 run（无 drawing）写入，图片 run 完全不动。"""
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


def validate_output(root: Path, expected_prefix: str = DEFAULT_TITLE_PREFIX):
    """写入后自动验证：段数、图片、样式"""
    template_path = root / TEMPLATE_REL
    backup_path = root / BACKUP_REL
    doc = Document(template_path)
    bak = Document(backup_path) if backup_path.exists() else None

    errors = []

    if len(doc.paragraphs) != EXPECTED_PARAS:
        errors.append(f"段数异常: {len(doc.paragraphs)} (期望 {EXPECTED_PARAS})")

    img_total = sum(len(p._element.findall('.//' + qn('w:drawing'))) for p in doc.paragraphs)
    if img_total != 5:
        errors.append(f"图片总数: {img_total} (期望 5)")

    # 仅当备份与当前模板段数一致（同一版式）时才逐段对比图片
    if bak and len(bak.paragraphs) == len(doc.paragraphs):
        for i, p in enumerate(doc.paragraphs):
            cur = len(p._element.findall('.//' + qn('w:drawing')))
            bk = len(bak.paragraphs[i]._element.findall('.//' + qn('w:drawing')))
            if cur != bk:
                errors.append(f"段[{i}] 图片数不一致: 当前 {cur} vs 备份 {bk}")

    p_promo = doc.paragraphs[TAIL_PROMO_IDX]
    r0 = p_promo.runs[0]
    if not (p_promo.alignment == 1 and r0.bold is True and str(r0.font.color.rgb) == '85120F'):
        errors.append("引流段样式丢失")

    # 段[0] 文本框校验：应有 2 个文本框，前缀符合本次来源（每日一练 / 历年考题）
    txbx_count = 0
    for txbx in doc.paragraphs[0]._element.iter(qn('w:txbxContent')):
        txbx_count += 1
        text_runs = txbx.findall('.//' + qn('w:t'))
        if len(text_runs) < 2:
            errors.append(f"段[0] 文本框结构异常：<w:t> 数量 {len(text_runs)}")
        elif text_runs[0].text != expected_prefix:
            errors.append(f"段[0] 文本框前缀不符: {text_runs[0].text!r} (期望 {expected_prefix!r})")
    if txbx_count != 2:
        errors.append(f"段[0] 文本框数: {txbx_count} (期望 2)")

    # 段[FIRST_BODY_IDX] 应有 pageBreakBefore（A+C 锁定版式），大纲区不应有
    p_body = doc.paragraphs[FIRST_BODY_IDX]
    body_pPr = p_body._element.find(qn('w:pPr'))
    if body_pPr is None or body_pPr.find(qn('w:pageBreakBefore')) is None:
        errors.append(f"段[{FIRST_BODY_IDX}] 缺 pageBreakBefore（正文应从第3页开始）")
    for i in range(2, FIRST_BODY_IDX):
        pPr_i = doc.paragraphs[i]._element.find(qn('w:pPr'))
        if pPr_i is not None and pPr_i.find(qn('w:pageBreakBefore')) is not None:
            errors.append(f"段[{i}] 不应有 pageBreakBefore（大纲区）")

    return errors


def main():
    ap = argparse.ArgumentParser(
        description="答一道引擎（structured-daily 答题线；自 structured-post 引擎原样移植，"
                    "19 段 5 图契约 / 写入前段数预检 / 快照 / 写入后验证）")
    ap.add_argument("--project-root",
                    help="项目根目录（或环境变量 ANSWER_PROJECT_ROOT；已取消相对路径 fallback）")
    args = ap.parse_args()
    root = resolve_project_root(args.project_root)

    template_path = root / TEMPLATE_REL
    pending_json = root / PENDING_REL

    if not pending_json.exists():
        print(f"[ERROR] 待写入文件不存在: {pending_json}")
        print("        请先 agent 把新内容写到 pending_answer.json")
        sys.exit(1)

    if not template_path.exists():
        print(f"[ERROR] 模板不存在: {template_path}")
        sys.exit(1)

    print(f"[0/4] 快照备份")
    snap = take_snapshot(root)
    if snap:
        print(f"      {snap.name}")

    with open(pending_json, 'r', encoding='utf-8') as f:
        content = json.load(f)

    print(f"[1/4] 读取待写入内容: {pending_json}")
    print(f"      字段数: {len(content)} (正文段位 {len(REPLACE_MAP)} + question)")

    doc = Document(template_path)

    if len(doc.paragraphs) != EXPECTED_PARAS:
        print(f"[ERROR] 模板段数 {len(doc.paragraphs)} 与脚本基准 {EXPECTED_PARAS} 不符，请勿强行写入")
        sys.exit(1)

    print(f"[2/4] 写入 段[0] 文本框题目")
    if "question" not in content:
        print(f"[ERROR] pending_answer.json 缺 'question' 字段")
        sys.exit(1)
    # 封面前缀：真题库来源必须用「结构化历年考题：」，自出题默认「结构化每日一练：」
    source = str(content.get("source") or content.get("source_type") or "")
    title_prefix = content.get("title_prefix") or DEFAULT_TITLE_PREFIX
    is_real_exam = any(k in source for k in ("真题", "历年考题", "real_exam", "zhenti"))
    if is_real_exam and title_prefix != REAL_EXAM_TITLE_PREFIX:
        print(f"[ERROR] source={source!r} 为真题库来源，title_prefix 必须为 {REAL_EXAM_TITLE_PREFIX!r}，实际 {title_prefix!r}")
        sys.exit(1)
    if (not is_real_exam) and title_prefix == REAL_EXAM_TITLE_PREFIX and source:
        print(f"[WARN] title_prefix 为历年考题但 source={source!r} 未标明真题库，请确认来源")
    if title_prefix not in (DEFAULT_TITLE_PREFIX, REAL_EXAM_TITLE_PREFIX):
        print(f"[WARN] title_prefix 非约定值: {title_prefix!r}（约定: {DEFAULT_TITLE_PREFIX!r} / {REAL_EXAM_TITLE_PREFIX!r}）")
    modified = replace_textbox_question(doc.paragraphs[0], content["question"], title_prefix)
    print(f"      修改了 {modified} 个文本框（期望 2：drawing 镜像 + VML fallback）")
    print(f"      封面前缀: {title_prefix}")

    print(f"[2.5/4] 写入 {len(REPLACE_MAP)} 个段位（正文）")
    for para_idx, key in REPLACE_MAP:
        para = doc.paragraphs[para_idx]
        new_text = resolve_content(content, key)
        replace_run_text_safely(para, new_text)

    print(f"[2.6/4] 锁定版式：段[{FIRST_BODY_IDX}] 正文首段强制 pageBreakBefore")
    ensure_pagebreak_before(doc.paragraphs[FIRST_BODY_IDX])
    for i in range(2, FIRST_BODY_IDX):
        remove_pagebreak_before(doc.paragraphs[i])

    print(f"[3/4] 保存到 {template_path.name}")
    doc.save(template_path)
    print(f"[4/4] 自动验证")
    errors = validate_output(root, title_prefix)
    if errors:
        print(f"[FAIL] 发现 {len(errors)} 个问题:")
        for e in errors:
            print(f"  - {e}")
        print(f"[KEEP] pending_answer.json 保留，便于排查")
        sys.exit(1)

    print(f"[OK] 全部验证通过！")
    print(f"     ✅ 段数 {EXPECTED_PARAS}")
    print(f"     ✅ 5 张图片全在")
    print(f"     ✅ 引流段样式保留")
    print(f"     ✅ 封面前缀 {title_prefix}")
    print(f"[CLEAN] 清理 pending_answer.json")
    pending_json.unlink()

    print(f"\n{'='*50}")
    print(f"模板已更新: {template_path}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()

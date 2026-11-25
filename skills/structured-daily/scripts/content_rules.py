#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""content_rules —— structured-daily 出厂规则门禁（R0/R14，--line answer）。

TR1（2026-11-20，答一道单线转型）：R1-R15 技巧线规则随技巧线退役删除
（git 历史可找回）；R0/R14 线无关骨架保留，--line answer 从"阶段 2 预留"
改正常启用，R14 answer 扩展字段（审题五维记录 / closing_type）启用必填。

流水线位置（君上裁定，修正 spec B3 内部矛盾）：R0/R14 跑在
独立审稿（写 review_conclusion）＋盲测试答（写 blind_test_result）
之后，作最终出厂程序门禁：草稿 → 电车站诊断 → human-writing 改写 →
check_prose 清零 → 回核读源 → 独立审稿 → 盲测试答 → content_rules
exit0 → CHECKPOINT → 引擎。

CLI:
    python3 content_rules.py --line answer --pending PATH --meta PATH
    --line tips 保留（R14 按线校验骨架；技巧线已退役，现行生产用 answer）。
    pending 校验与引擎消费契约同表防漂移：tips=pending_tips.json 15 字段；
    answer=pending_answer.json（question + 引擎 REPLACE_MAP 15 键必填，
    core_views 恰 3 元素，source/title_prefix/cover_meta 可选，多余字段拒绝——引擎对
    多余键宽容，此处 fail-closed 收紧）。

退出码: 0=全过 / 1=有规则未过（逐条打印 [FAIL] R<n>: 原因）/
        2=参数或 JSON 加载错误。

规则:
    R0 读源记录必填     --pending 给定而 --meta 缺失/不存在 → 拒
    R14 审稿记录完整    核心字段 + 对应线扩展字段非空
                        （tips: card_point 等 10 字段；answer: 审题五维记录
                        / closing_type）+ tip_id/question_id 二选一非空
                        + review_conclusion=="通过" 且 blind_test_result==
                        "通过"；任一不满足 → 拒
"""

import argparse
import json
import os
import sys

# ---------------------------------------------------------------------------
# 字段契约（与 references/shared-sourcing.md draft_meta schema 一致）
# ---------------------------------------------------------------------------

# R14 核心必填字段（线无关）
CORE_FIELDS = [
    "skill_version",
    "line",
    "method_points",
    "point_labels",
    "sources",
    "quote_excerpts",
    "applicable_conditions",
    "review_conclusion",
    "render_check",
    "blind_test_result",
]

# line=="tips" 时 tips 扩展必填字段（退役线骨架保留；tip_id/question_id 二选一单独处理）
TIPS_EXT_FIELDS = [
    "card_point",
    "cognitive_gain",
    "shared_context",
    "key_change",
    "actionable_demo",
    "demo_source",
    "demo_calibration_check",
    "exercise_criteria",
    "self_check_criteria",
    "title_candidates",
]

# line=="answer" 时 answer 扩展必填字段（TR1 启用）
ANSWER_EXT_FIELDS = [
    "审题五维记录",
    "closing_type",
]

# tips pending 15 字段（与已退役引擎 fill_tips_post.py SCHEMA_KEYS 一致，历史契约）
TIPS_PENDING_FIELDS = [
    "tip_title", "card_point", "fix_summary", "demo",
    "step1", "step2", "step3",
    "case_normal", "contrast_note",
    "boundary_scope", "boundary_misuse", "boundary_evidence",
    "exercise", "self_check", "hashtags",
]

# answer pending（与引擎 fill_answer_post.py 消费契约同表防漂移）：
# 必填字符串键 + core_views（恰 3 元素列表）+ 可选键
ANSWER_PENDING_STR_FIELDS = [
    "question",
    "break_angle", "break_angle_reason",
    "core_views_title", "core_views_intro",
    "opening",
    "point1_lead", "point1_body",
    "point2_lead", "point2_body",
    "point3_lead", "point3_body",
    "closing",
]
ANSWER_PENDING_LIST_FIELD = "core_views"   # 恰 3 个非空字符串（引擎 core_views[0..2]）
ANSWER_PENDING_OPTIONAL_FIELDS = ["source", "title_prefix", "cover_meta"]


def _missing(value):
    """非空判断：None / 空串（含纯空白）/ 空列表 / 空字典 视为缺失。"""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


# ---------------------------------------------------------------------------
# 规则实现（R0/R14 线无关骨架保留，不改逻辑）
# ---------------------------------------------------------------------------

def check_r0(ctx):
    """R0 读源记录必填：--pending 给定而 --meta 缺失或文件不存在 → 拒。"""
    args = ctx["args"]
    if args.pending:
        if not args.meta:
            ctx["failures"].append("R0 读源记录必填：缺 --meta")
            return
        if not os.path.isfile(args.meta):
            ctx["failures"].append(
                "R0 读源记录必填：缺 --meta（文件不存在：%s）" % args.meta
            )


def check_r14(ctx):
    """R14 审稿记录完整 + 结论通过：核心字段 + 对应线扩展字段全非空，
    且 review_conclusion=="通过" 且 blind_test_result=="通过"。"""
    meta = ctx["meta"]
    if meta is None:
        return  # meta 不可用时由 R0/加载错误兜底，R14 不重复报

    details = []

    # 1) 核心必填字段
    for field in CORE_FIELDS:
        if _missing(meta.get(field)):
            details.append("核心字段 %s 缺失/为空" % field)

    # 2) 选题 id 二选一非空
    if _missing(meta.get("tip_id")) and _missing(meta.get("question_id")):
        details.append("选题 id 缺失：tip_id 与 question_id 均为空")

    # 3) 按线扩展字段必填
    if meta.get("line") == "tips":
        for field in TIPS_EXT_FIELDS:
            if _missing(meta.get(field)):
                details.append("tips 扩展字段 %s 缺失/为空" % field)
    if meta.get("line") == "answer":
        for field in ANSWER_EXT_FIELDS:
            if _missing(meta.get(field)):
                details.append("answer 扩展字段 %s 缺失/为空" % field)

    # 4) 两结论必须 == "通过"
    if meta.get("review_conclusion") != "通过":
        details.append(
            "review_conclusion=%r 非\"通过\"（须独立审稿后写）"
            % meta.get("review_conclusion")
        )
    if meta.get("blind_test_result") != "通过":
        details.append(
            "blind_test_result=%r 非\"通过\"（须盲测试答后写）"
            % meta.get("blind_test_result")
        )

    if details:
        ctx["failures"].append("R14 审稿记录不全/未通过：" + "；".join(details))


# ---------------------------------------------------------------------------
# 规则注册（按序执行）
# ---------------------------------------------------------------------------

RULES = {
    "R0": check_r0,
    "R14": check_r14,
}


# ---------------------------------------------------------------------------
# 加载与 CLI
# ---------------------------------------------------------------------------

def load_meta(path):
    """加载 draft_meta JSON（UTF-8 无 BOM：utf-8 读取，带 BOM 将解析失败被拒）。
    语法/读取错误返回 (None, err)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, str(e)


def load_tips_pending(path):
    """加载 pending_tips.json（历史契约 15 字段）。返回 (dict, err)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, str(e)
    if not isinstance(data, dict):
        return None, "顶层须为 JSON object"
    missing = [k for k in TIPS_PENDING_FIELDS
               if not isinstance(data.get(k), str) or not data[k].strip()]
    if missing:
        return None, "15 字段缺失/为空: %s" % ", ".join(missing)
    extra = sorted(set(data.keys()) - set(TIPS_PENDING_FIELDS))
    if extra:
        return None, "发现多余字段: %s" % ", ".join(extra)
    return data, None


def load_answer_pending(path):
    """加载 pending_answer.json（与引擎 fill_answer_post.py 消费契约同表：
    question + REPLACE_MAP 15 键必填、core_views 恰 3 元素、
    source/title_prefix 可选非空、多余字段拒绝）。返回 (dict, err)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, str(e)
    if not isinstance(data, dict):
        return None, "顶层须为 JSON object"
    missing = [k for k in ANSWER_PENDING_STR_FIELDS
               if not isinstance(data.get(k), str) or not data[k].strip()]
    if missing:
        return None, "必填字段缺失/为空: %s" % ", ".join(missing)
    cv = data.get(ANSWER_PENDING_LIST_FIELD)
    if (not isinstance(cv, list) or len(cv) != 3
            or not all(isinstance(x, str) and x.strip() for x in cv)):
        return None, "core_views 须为恰 3 个非空字符串的列表（引擎写 core_views[0..2]）"
    allowed = set(ANSWER_PENDING_STR_FIELDS) | {ANSWER_PENDING_LIST_FIELD} | set(ANSWER_PENDING_OPTIONAL_FIELDS)
    extra = sorted(set(data.keys()) - allowed)
    if extra:
        return None, "发现多余字段: %s" % ", ".join(extra)
    for k in ANSWER_PENDING_OPTIONAL_FIELDS:
        if k in data and (not isinstance(data[k], str) or not data[k].strip()):
            return None, "可选字段 %s 给定时须为非空字符串" % k
    return data, None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="structured-daily 出厂规则门禁（R0/R14；--line answer 现行启用）"
    )
    parser.add_argument(
        "--line", required=True, choices=["tips", "answer"],
        help="产出线：answer 现行单线启用；tips 为退役线骨架保留",
    )
    parser.add_argument(
        "--pending", default=None,
        help="pending 路径（answer=pending_answer.json；tips=pending_tips.json 历史契约）",
    )
    parser.add_argument(
        "--meta", default=None, help="draft_meta.json 路径",
    )
    args = parser.parse_args(argv)

    ctx = {"args": args, "meta": None, "pending": None, "failures": []}

    # R0：读源记录必填（meta 缺失或文件不存在）
    check_r0(ctx)
    if ctx["failures"]:
        for fail in ctx["failures"]:
            print("[FAIL] %s" % fail)
        return 1

    # meta 与 pending 必须齐备（全量门禁）
    if not args.meta:
        print("[FAIL] 参数不足：未提供 --meta，读源记录无可检对象")
        return 2
    if not args.pending:
        print("[FAIL] 参数不足：未提供 --pending（内容无可检对象）")
        return 2

    meta, err = load_meta(args.meta)
    if err is not None:
        print("[FAIL] META 加载失败（须 UTF-8 无 BOM 合法 JSON）：%s" % err)
        return 2
    if not isinstance(meta, dict):
        print("[FAIL] META 加载失败：顶层须为 JSON object")
        return 2
    ctx["meta"] = meta

    if args.line == "answer":
        pending, err = load_answer_pending(args.pending)
    else:
        pending, err = load_tips_pending(args.pending)
    if err is not None:
        print("[FAIL] PENDING 加载失败（须 UTF-8 无 BOM 合法 JSON，与引擎契约同表）：%s" % err)
        return 2
    ctx["pending"] = pending

    # 按注册顺序执行规则
    for name in RULES:
        RULES[name](ctx)

    if ctx["failures"]:
        for fail in ctx["failures"]:
            print("[FAIL] %s" % fail)
        return 1

    print("[OK] content_rules 全过（R0/R14，--line %s）" % args.line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

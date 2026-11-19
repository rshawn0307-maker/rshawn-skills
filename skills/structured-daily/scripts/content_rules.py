#!/usr/bin/env python3
"""content_rules —— structured-daily 出厂规则门禁（最终出厂程序）。

流水线位置（君上裁定，修正 spec B3 内部矛盾）：全量 R0-R15 跑在
独立审稿（写 review_conclusion）＋盲测试答（写 blind_test_result）
之后，作最终出厂门禁：草稿 → 电车站诊断 → human-writing 改写 →
check_prose 清零 → 回核读源 → 独立审稿 → 盲测试答 → content_rules
全量 exit0 → CHECKPOINT → 引擎。

本脚本为阶段 1 Task2 骨架：只实现 R0/R14 + 规则注册框架；
R1-R13/R15（pending 内容校验）由 Task5 实现。

CLI:
    python3 content_rules.py --line tips --pending PATH --meta PATH

退出码: 0=全过 / 1=有规则未过（逐条打印 [FAIL] R<n>: 原因）/
        2=参数或 JSON 加载错误。
"""

import argparse
import json
import os
import sys

# ---------------------------------------------------------------------------
# 字段契约（与 references/shared-sourcing.md draft_meta schema 一致）
# ---------------------------------------------------------------------------

# R14 核心必填字段（两线必填）
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

# line=="tips" 时 tips 扩展必填字段（tip_id/question_id 二选一单独处理）
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
# 规则实现（Task2 骨架：R0/R14）
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

    # 1) 核心必填字段（两线）
    for field in CORE_FIELDS:
        if _missing(meta.get(field)):
            details.append("核心字段 %s 缺失/为空" % field)

    # 2) 选题 id 二选一非空
    if _missing(meta.get("tip_id")) and _missing(meta.get("question_id")):
        details.append("选题 id 缺失：tip_id 与 question_id 均为空")

    # 3) line=="tips" 时 tips 扩展字段必填
    if meta.get("line") == "tips":
        for field in TIPS_EXT_FIELDS:
            if _missing(meta.get(field)):
                details.append("tips 扩展字段 %s 缺失/为空" % field)

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
# 规则注册框架（Task5 扩展 R1-R13/R15 在此登记）
# ---------------------------------------------------------------------------

RULES = {
    "R0": check_r0,
    # R1-R13: pending 内容校验 —— Task5 实现
    "R14": check_r14,
    # R15: —— Task5 实现
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_meta(path):
    """加载 draft_meta JSON（UTF-8 无 BOM：utf-8 读取，带 BOM 将解析失败被拒）。
    语法/读取错误返回 (None, err)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, str(e)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="structured-daily 出厂规则门禁（Task2 骨架：R0/R14）"
    )
    parser.add_argument(
        "--line", required=True, choices=["tips", "answer"],
        help="产出线：阶段 1 只实现 tips；answer 阶段 2 启用",
    )
    parser.add_argument(
        "--pending", default=None,
        help="pending_tips.json 路径（15 字段 Task4 定稿；本任务仅作 R0 触发条件）",
    )
    parser.add_argument(
        "--meta", default=None, help="draft_meta.json 路径",
    )
    args = parser.parse_args(argv)

    # answer 线预留：阶段 2 启用
    if args.line == "answer":
        print("[SKIP] --line answer：答题线规则阶段 2 启用（当前仅实现 tips）")
        return 2

    ctx = {"args": args, "meta": None, "failures": []}

    # R0：读源记录必填（meta 缺失或文件不存在）
    check_r0(ctx)
    if ctx["failures"]:
        for fail in ctx["failures"]:
            print("[FAIL] %s" % fail)
        return 1

    # meta 存在才加载（--pending 未给且 --meta 未给时无输入可检，按参数错误拒）
    if args.meta:
        meta, err = load_meta(args.meta)
        if err is not None:
            print("[FAIL] META 加载失败（须 UTF-8 无 BOM 合法 JSON）：%s" % err)
            return 2
        if not isinstance(meta, dict):
            print("[FAIL] META 加载失败：顶层须为 JSON object")
            return 2
        ctx["meta"] = meta
    else:
        print("[FAIL] 参数不足：未提供 --pending/--meta，无可检对象")
        return 2

    # 按注册顺序执行规则
    for name in RULES:
        RULES[name](ctx)

    if ctx["failures"]:
        for fail in ctx["failures"]:
            print("[FAIL] %s" % fail)
        return 1

    print("[OK] content_rules 全过（R0/R14，其余Task5）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

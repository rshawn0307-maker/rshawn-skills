#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_v3_gates.py — v3 门禁反例回归（对应审核计划验收要求）。

7 类反例必须全部被拦截，正例（评审同版本+证据齐全）必须放行：
  R1 题文错配            → topic_text_mismatch
  R2 假星级              → fabricated_difficulty
  R3 方向/动作改错        → factlock unclassified（程序层）+ 评审 action_logic_ok=false（评审层）
  R4 重复句凑时长          → script_repetition_high
  R5 只有安全套话          → safety_not_executable
  R6 必需图例缺失          → workflow extract 门 STOP
  R7 内容修改后沿用旧审核   → validate_review 版本不一致
附带：误收选题 select 门 STOP、断裂标点、时长标注不一致、无理由登记。

用法：python3 test_v3_gates.py  （退出码 0 = 全部拦截）
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import ptd_core as core  # noqa: E402
import ptd_workflow as wf  # noqa: E402
import build_fixtures  # noqa: E402


def main() -> int:
    lib = core.BookLibrary()
    view = core.build_generatable_view()
    entries = {e["id"]: e for e in view["entries"]}
    fixtures = {f["draft"]["id"]: f for f in build_fixtures.build_all()}
    base = copy.deepcopy(fixtures["PTD-000-乒乓球-平击球"]["draft"])
    base_entry = entries["PTD-000-乒乓球-平击球"]
    results: list[tuple[str, bool, str]] = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    # R1 题文错配
    d = copy.deepcopy(base)
    for st in d["flow"]:
        st["script"] = "同学们好，今天我们学习广播体操。伸展运动，四八拍。"
    r = core.score_draft(d, base_entry, lib)
    check("R1 题文错配拦截", "topic_text_mismatch" in r["hard_gates"], r["hard_gates"])

    # R2 假星级
    d = copy.deepcopy(base)
    d["fields"]["difficulty"] = {"kind": "index_stars", "display": "★★★"}
    r = core.score_draft(d, base_entry, lib)
    check("R2 假星级拦截", "fabricated_difficulty" in r["hard_gates"], r["hard_gates"])

    # R3 方向改错（程序层：反转教材方向 token 应产生未归类）
    d = copy.deepcopy(base)
    if "同侧脚的外侧前方" in "".join(st.get("script", "") for st in d["flow"]):
        pass  # 平击球稿无方向词，改用参数化说明：借原地运球 fixture 验证
    yd = copy.deepcopy(fixtures["PTD-244-篮球-原地运球"]["draft"])
    yd_entry = entries["PTD-244-篮球-原地运球"]
    joined = "".join(st.get("script", "") for st in yd["flow"])
    if "同侧脚的外侧前方" in joined:
        for st in yd["flow"]:
            st["script"] = st["script"].replace("同侧脚的外侧前方", "对侧脚的外侧前方")
        r = core.score_draft(yd, yd_entry, lib)
        check("R3 方向改错拦截（程序层）", r["factlock"]["unclassified"] > 0, r["factlock"]["violations"][:2])
    else:
        check("R3 方向改错拦截（程序层）", False, "原地运球稿未含方向句，用例需更新")
    # R3 评审层：action_logic_ok=false 必须不放行
    review_false = {
        "schema": core.SCHEMA_REVIEW, "id": base["id"],
        "draft_sha": core.draft_hash(base), "reviewer": "agent",
        "checked": {k: True for k in core.REVIEW_CHECKS} | {"action_logic_ok": False},
        "suggestion_notes": [{"where": "flow", "why": "x"}], "verdict": "pass",
    }
    ok, errs = core.validate_review(review_false, base)
    check("R3 动作冲突评审拦截", (not ok) and any("动作逻辑" in e for e in errs), errs[:2])

    # R4 重复句凑时长（构造 ≥2 对近重复句）
    d = copy.deepcopy(base)
    rep = "大家注意看老师的示范动作一起跟着做。做完以后大家注意看老师的示范动作一起跟着做。"
    d["flow"][1]["script"] = rep + "然后我们再练下一组。"
    d["flow"][2]["script"] = rep + "注意安全保持距离。"
    r = core.score_draft(d, base_entry, lib)
    check("R4 重复句凑时长拦截", "script_repetition_high" in r["hard_gates"], r["hard_gates"])

    # R5 只有安全套话（最小草稿构造，避免基础稿残留可执行词）
    d5 = {"segment": {"meta": {"安全": "注意安全，保护好器材，合理安排运动负荷，注意天气变化"}},
          "flow": [{"stage": "小结", "script": "这节课练得认真，收拾好东西准备下课。"}],
          "config": {"speech_rate_chars_per_min": 230}}
    exec_ok, cats5 = core.check_safety_executable(d5)
    check("R5 安全套话拦截（不可执行即不通过）", (not exec_ok) and len(cats5) >= 3, f"exec={exec_ok} cats={cats5}")

    # R6 必需图例缺失（workflow extract 门）
    entry = dict(entries["PTD-045-体能-半米字移动"])
    entry["figure_policy"] = "use_extracted"
    d6 = {"id": entry["id"], "schema": core.SCHEMA_DRAFT,
          "source_view_entry": entry, "render": {"figure_images": []}}
    try:
        wf.gate_extract(d6, entry, lib)
        check("R6 必需图例缺失拦截", False, "未拦截")
    except wf.GateStop:
        check("R6 必需图例缺失拦截", True)

    # R7 沿用旧审核
    review_old = {
        "schema": core.SCHEMA_REVIEW, "id": base["id"], "draft_sha": "0" * 16,
        "reviewer": "agent", "checked": {k: True for k in core.REVIEW_CHECKS},
        "suggestion_notes": [{"where": "flow", "why": "x"}], "verdict": "pass",
    }
    d = copy.deepcopy(base)
    d["flow"][0]["script"] += "大家听明白了吗。"
    ok, errs = core.validate_review(review_old, d)
    check("R7 沿用旧审核拦截", (not ok) and any("版本不一致" in e for e in errs), errs[:1])

    # 附加 A：误收选题 select 门
    try:
        wf.gate_select({"id": "PTD-016-乒乓球-课外作业建议",
                        "schema": core.SCHEMA_DRAFT,
                        "source_view_entry": entries["PTD-016-乒乓球-课外作业建议"]})
        check("A1 误收选题拦截", False, "未拦截")
    except wf.GateStop:
        check("A1 误收选题拦截", True)

    # 附加 B：断裂标点
    d = copy.deepcopy(base)
    d["flow"][0]["script"] = d["flow"][0]["script"].replace("。", "。。", 1)
    r = core.score_draft(d, base_entry, lib)
    check("A2 断裂标点拦截", "broken_punctuation" in r["hard_gates"], r["hard_gates"])

    # 附加 C：时长标注与分段合计不一致
    d = copy.deepcopy(base)
    d["segment"]["meta"]["时长"] = "约300秒（口播约280秒＋示范停顿约20秒）"
    r = core.score_draft(d, base_entry, lib)
    check("A3 时长标注不一致拦截", "duration_annotation_mismatch" in r["hard_gates"], r["hard_gates"])

    # 正例：fixtures/ 平击球（含被引用段落证据）在补齐 adapted_note 与时长标注后应通过硬门中的引用关
    d = copy.deepcopy(fixtures["PTD-000-乒乓球-平击球"]["draft"])
    for _, blk in core.iter_blocks(d):
        if blk.get("adapted_facts") and not (blk.get("adapted_note") or "").strip():
            blk["adapted_note"] = "教学口令化改写，动作与判定保持教材原文"
    br = core.duration_breakdown(d)
    d["segment"]["meta"]["时长"] = f"约{round(br['total_sec'])}秒（口播约{round(br['speech_sec'])}秒＋示范停顿约{round(br['demo_pause_sec'])}秒）"
    d.setdefault("notes", {})["human_rewrite_applied"] = True
    r = core.score_draft(d, base_entry, lib)
    check("P1 补证+理由+时长标注后引用关通过", "cross_ref_evidence_missing" not in r["hard_gates"], r["hard_gates"])

    failed = [n for n, ok, _ in results if not ok]
    for n, ok, detail in results:
        print(("  ✅ " if ok else "  ❌ ") + n + ("" if ok else f"  {detail}"))
    print(f"\n反例回归 {len(results)} 项，通过 {len(results) - len(failed)}，失败 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

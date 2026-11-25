#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_content_rules —— content_rules.py R0/R14 自测（answer 用例）。

TR1（2026-11-20 答一道单线转型）缩减版：R1-R15 技巧线规则随技巧线退役删除，
本自测同步缩减为 R0/R14 用例（answer 线为主，含 1 条 tips 骨架验证）。

运行：python3 scripts/test_content_rules.py [关键字...]
- 全过 exit 0；任一用例失败 / 0 用例（筛选不中或框架坏）/ 用例 <10 → exit 1
  （不允许假绿）。
- 沙箱纪律：所有临时 JSON fixture 只写系统临时目录（tempfile），真实 vault 不触碰。

用例构成（13 条）：
- R0：缺 --meta / --meta 文件不存在；
- R14 answer：golden 全过 / 缺审题五维记录 / 缺 closing_type /
  review_conclusion 未通过 / blind_test_result 未通过 / 核心字段缺失；
- answer pending 加载：缺必填字段 / core_views 非 3 元素（exit 2）；
- answer pending 可选字段：cover_meta 放行 / 多余字段拒绝（exit 2）；
- R14 tips 骨架：line=="tips" 扩展字段齐全 → exit 0。
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_CLI = os.path.join(HERE, "content_rules.py")

MIN_CASES = 10


def write_json(tmpdir, name, obj):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))
    return path


def run_cli(*cli_args):
    proc = subprocess.run(
        [sys.executable, RULES_CLI] + list(cli_args),
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


GOLDEN_ANSWER_PENDING = {
    "source": "模拟题库",
    "question": "单位推行错峰上下班，有同事抱怨接送孩子受影响，你怎么看？",
    "break_angle": "破题角度：从制度目标与个体负担的平衡切入。",
    "break_angle_reason": "切入理由：题干张力在制度善意与职工实际困难之间。",
    "core_views_title": "核心观点",
    "core_views_intro": "（三个递进）：",
    "core_views": ["1. 制度目标成立。", "2. 负担落在配套缺口。", "3. 关键在补位。"],
    "opening": "错峰上下班本身是好政策，方向我肯定。",
    "point1_lead": "第一，先看制度要解决什么问题。",
    "point1_body": "集中上下班造成拥挤，错峰把高峰摊开。",
    "point2_lead": "第二，再看负担落在谁头上。",
    "point2_body": "接送孩子时间是刚性的，职工被夹在中间。",
    "point3_lead": "第三，关键在补位不在回退。",
    "point3_body": "设弹性缓冲，与学校协商衔接。",
    "closing": "好制度要看它有没有把受影响的人安排好。",
}

GOLDEN_ANSWER_META = {
    "skill_version": "3.0.0",
    "line": "answer",
    "question_id": "zx-01",
    "method_points": 3,
    "point_labels": ["制度目标", "负担落点", "补位机制"],
    "sources": ["01_题库与训练/模拟题/综合分析题/综合分析-01-错峰上下班.md#定调版逐字稿"],
    "quote_excerpts": ["错峰上下班本身是好政策"],
    "applicable_conditions": ["题干仅限公开场景，涉密数据不入稿"],
    "审题五维记录": "设问：怎么看；身份：考生；对象：同事与单位；限制条件：制度已推行、接送刚需；主要争点：制度善意与个体负担",
    "closing_type": "判据式",
    "review_conclusion": "通过",
    "render_check": "近似通过",
    "blind_test_result": "通过",
}

GOLDEN_TIPS_META = {
    "skill_version": "3.0.0",
    "line": "tips",
    "tip_id": "zz-03",
    "method_points": 3,
    "point_labels": ["a", "b", "c"],
    "sources": ["x.md#y"],
    "quote_excerpts": ["引句"],
    "applicable_conditions": ["仅限公开题干"],
    "review_conclusion": "通过",
    "render_check": "近似通过",
    "blind_test_result": "通过",
    "card_point": "卡在内容空洞",
    "cognitive_gain": "误以为示范要更长，实际要先立骨",
    "shared_context": "同题境",
    "key_change": "先立总起句",
    "actionable_demo": "问自己：总起句有立场词吗",
    "demo_source": "新写标示范",
    "demo_calibration_check": "通过",
    "exercise_criteria": "新场景写出立骨句",
    "self_check_criteria": "自查立骨句有立场词",
    "title_candidates": ["痛点式", "改法式", "栏目式"],
}

TIPS_PENDING = {
    "tip_title": "综合分析不会分层？一句话立骨",
    "card_point": "适用综合分析题：卡在想到哪说到哪。",
    "fix_summary": "改法一句话：先给判断句立骨。",
    "demo": "示范：我不同意，理由有三。",
    "step1": "第一步 判断：先明确立场。",
    "step2": "第二步 展开：按题骨拆三点。",
    "step3": "第三步 检查：回读是否回扣。",
    "case_normal": "普通答法：我觉得有好有坏。",
    "contrast_note": "点评：没有先给题骨。",
    "boundary_scope": "适用：观点类综合分析。",
    "boundary_misuse": "常见误用：写成复述题干；纠正：句中必须含立场词。",
    "boundary_evidence": "出处：整理自方法论立骨一节。",
    "exercise": "练习：针对新场景先写一句立骨句再展开。",
    "self_check": "自查：①有立场词吗 ②回扣了吗",
    "hashtags": "#公考面试 #结构化面试",
}

CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


@case("R0 缺 --meta 拒")
def case_r0_no_meta(check):
    with tempfile.TemporaryDirectory(prefix="rules_test_") as tmp:
        pending = write_json(tmp, "pending_answer.json", GOLDEN_ANSWER_PENDING)
        rc, out = run_cli("--line", "answer", "--pending", pending)
        check(rc == 1, "exit=%s" % rc)
        check("R0" in out, "未报 R0")


@case("R0 --meta 文件不存在拒")
def case_r0_meta_missing_file(check):
    with tempfile.TemporaryDirectory(prefix="rules_test_") as tmp:
        pending = write_json(tmp, "pending_answer.json", GOLDEN_ANSWER_PENDING)
        rc, out = run_cli("--line", "answer", "--pending", pending,
                          "--meta", os.path.join(tmp, "nope.json"))
        check(rc == 1, "exit=%s" % rc)
        check("R0" in out and "不存在" in out, "未报 R0 文件不存在")


@case("golden answer 全过 exit0")
def case_golden(check):
    with tempfile.TemporaryDirectory(prefix="rules_test_") as tmp:
        pending = write_json(tmp, "pending_answer.json", GOLDEN_ANSWER_PENDING)
        meta = write_json(tmp, "draft_meta.json", GOLDEN_ANSWER_META)
        rc, out = run_cli("--line", "answer", "--pending", pending, "--meta", meta)
        check(rc == 0, "exit=%s out=%s" % (rc, out[-300:]))
        check("R0/R14" in out, "未报全过")


@case("answer pending 含 cover_meta 可选字段 exit0")
def case_pending_cover_meta(check):
    with tempfile.TemporaryDirectory(prefix="rules_test_") as tmp:
        pending = dict(GOLDEN_ANSWER_PENDING)
        pending["cover_meta"] = "2024年6月5日 · 咸阳 · 综合管理A"
        p = write_json(tmp, "pending_cover_meta.json", pending)
        meta = write_json(tmp, "draft_meta.json", GOLDEN_ANSWER_META)
        rc, out = run_cli("--line", "answer", "--pending", p, "--meta", meta)
        check(rc == 0, "exit=%s out=%s" % (rc, out[-300:]))


@case("answer pending 多余字段 exit2")
def case_pending_extra_field(check):
    with tempfile.TemporaryDirectory(prefix="rules_test_") as tmp:
        pending = dict(GOLDEN_ANSWER_PENDING)
        pending["unknown_key"] = "x"
        p = write_json(tmp, "pending_extra.json", pending)
        meta = write_json(tmp, "draft_meta.json", GOLDEN_ANSWER_META)
        rc, out = run_cli("--line", "answer", "--pending", p, "--meta", meta)
        check(rc == 2, "exit=%s out=%s" % (rc, out[-300:]))
        check("多余字段" in out, "未报多余字段: %s" % out[-300:])


@case("R14 answer 缺审题五维记录拒")
def case_r14_missing_shenti(check):
    with tempfile.TemporaryDirectory(prefix="rules_test_") as tmp:
        meta = dict(GOLDEN_ANSWER_META)
        del meta["审题五维记录"]
        pending = write_json(tmp, "pending_answer.json", GOLDEN_ANSWER_PENDING)
        meta_path = write_json(tmp, "draft_meta.json", meta)
        rc, out = run_cli("--line", "answer", "--pending", pending, "--meta", meta_path)
        check(rc == 1, "exit=%s" % rc)
        check("审题五维记录" in out, "未报缺审题五维记录")


@case("R14 answer 缺 closing_type 拒")
def case_r14_missing_closing_type(check):
    with tempfile.TemporaryDirectory(prefix="rules_test_") as tmp:
        meta = dict(GOLDEN_ANSWER_META)
        del meta["closing_type"]
        pending = write_json(tmp, "pending_answer.json", GOLDEN_ANSWER_PENDING)
        meta_path = write_json(tmp, "draft_meta.json", meta)
        rc, out = run_cli("--line", "answer", "--pending", pending, "--meta", meta_path)
        check(rc == 1, "exit=%s" % rc)
        check("closing_type" in out, "未报缺 closing_type")


@case("R14 review_conclusion 未通过拒")
def case_r14_review_not_passed(check):
    with tempfile.TemporaryDirectory(prefix="rules_test_") as tmp:
        meta = dict(GOLDEN_ANSWER_META)
        meta["review_conclusion"] = "待审"
        pending = write_json(tmp, "pending_answer.json", GOLDEN_ANSWER_PENDING)
        meta_path = write_json(tmp, "draft_meta.json", meta)
        rc, out = run_cli("--line", "answer", "--pending", pending, "--meta", meta_path)
        check(rc == 1, "exit=%s" % rc)
        check("review_conclusion" in out, "未报 review_conclusion")


@case("R14 blind_test_result 未通过拒")
def case_r14_blind_not_passed(check):
    with tempfile.TemporaryDirectory(prefix="rules_test_") as tmp:
        meta = dict(GOLDEN_ANSWER_META)
        meta["blind_test_result"] = "未过"
        pending = write_json(tmp, "pending_answer.json", GOLDEN_ANSWER_PENDING)
        meta_path = write_json(tmp, "draft_meta.json", meta)
        rc, out = run_cli("--line", "answer", "--pending", pending, "--meta", meta_path)
        check(rc == 1, "exit=%s" % rc)
        check("blind_test_result" in out, "未报 blind_test_result")


@case("R14 核心字段缺失拒（sources 为空）")
def case_r14_core_missing(check):
    with tempfile.TemporaryDirectory(prefix="rules_test_") as tmp:
        meta = dict(GOLDEN_ANSWER_META)
        meta["sources"] = []
        pending = write_json(tmp, "pending_answer.json", GOLDEN_ANSWER_PENDING)
        meta_path = write_json(tmp, "draft_meta.json", meta)
        rc, out = run_cli("--line", "answer", "--pending", pending, "--meta", meta_path)
        check(rc == 1, "exit=%s" % rc)
        check("核心字段 sources" in out, "未报核心字段 sources")


@case("answer pending 缺必填字段 exit2")
def case_pending_missing_field(check):
    with tempfile.TemporaryDirectory(prefix="rules_test_") as tmp:
        pending = dict(GOLDEN_ANSWER_PENDING)
        del pending["closing"]
        pending_path = write_json(tmp, "pending_answer.json", pending)
        meta = write_json(tmp, "draft_meta.json", GOLDEN_ANSWER_META)
        rc, out = run_cli("--line", "answer", "--pending", pending_path, "--meta", meta)
        check(rc == 2, "exit=%s" % rc)
        check("closing" in out, "未报缺 closing")


@case("answer pending core_views 非 3 元素 exit2")
def case_pending_core_views(check):
    with tempfile.TemporaryDirectory(prefix="rules_test_") as tmp:
        pending = dict(GOLDEN_ANSWER_PENDING)
        pending["core_views"] = ["只有一条"]
        pending_path = write_json(tmp, "pending_answer.json", pending)
        meta = write_json(tmp, "draft_meta.json", GOLDEN_ANSWER_META)
        rc, out = run_cli("--line", "answer", "--pending", pending_path, "--meta", meta)
        check(rc == 2, "exit=%s" % rc)
        check("core_views" in out, "未报 core_views")


@case("R14 tips 骨架：line==tips 扩展齐全 exit0")
def case_tips_skeleton(check):
    with tempfile.TemporaryDirectory(prefix="rules_test_") as tmp:
        pending_path = write_json(tmp, "pending_tips.json", TIPS_PENDING)
        meta = write_json(tmp, "draft_meta.json", GOLDEN_TIPS_META)
        rc, out = run_cli("--line", "tips", "--pending", pending_path, "--meta", meta)
        check(rc == 0, "exit=%s out=%s" % (rc, out[-300:]))


def main() -> int:
    selected = [entry for entry in CASES if not sys.argv[1:]
                or any(key in entry[0] for key in sys.argv[1:])]
    if len(selected) < MIN_CASES:
        print("用例数 %s < 下限 %s（筛选不中或框架坏）" % (len(selected), MIN_CASES),
              file=sys.stderr)
        return 1

    failures = []
    for name, fn in selected:
        problems = []

        def check(ok, message, _problems=problems):
            if not ok:
                _problems.append(message)

        fn(check)
        status = "PASS" if not problems else "FAIL"
        print(f"[{status}] {name}")
        for problem in problems:
            print(f"  - {problem}")
        if problems:
            failures.append(name)

    passed = len(selected) - len(failures)
    print(f"\n{passed}/{len(selected)} 用例通过")
    if failures:
        print("失败用例：%s" % "、".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

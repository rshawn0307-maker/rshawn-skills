#!/usr/bin/env python3
"""test_content_rules —— content_rules.py R0/R14 自测骨架。

运行：python3 scripts/test_content_rules.py
- 全过 exit 0；任一用例失败或 0 用例（框架坏）→ exit 1（不允许假绿）。
- 沙箱纪律：所有临时 JSON 只写系统临时目录（tempfile），不碰真实 vault。
- Task5 扩展 R1-R13/R15 时向 CASES 追加用例即可。
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_CLI = os.path.join(HERE, "content_rules.py")


def make_meta(**overrides):
    """完整 draft_meta 样例（两线核心 + tips 扩展 + 两结论通过）。"""
    meta = {
        "skill_version": "3.0.0",
        "line": "tips",
        "tip_id": "tips-2026-0001",
        "method_points": 3,
        "point_labels": ["点1", "点2", "点3"],
        "sources": ["综合分析题_方法论提炼.md#小节名"],
        "quote_excerpts": ["原文短句一"],
        "applicable_conditions": ["教师注：仅限公开题干"],
        "review_conclusion": "通过",
        "render_check": "发布端通过",
        "blind_test_result": "通过",
        "card_point": "卡点描述",
        "cognitive_gain": "认知增量描述",
        "shared_context": "同题境对照",
        "key_change": "关键改动",
        "actionable_demo": "可照做问句",
        "demo_source": "新写标示范",
        "demo_calibration_check": "字数/定调/三禁回核结论",
        "exercise_criteria": "练习判据",
        "self_check_criteria": "自查判据",
        "title_candidates": ["痛点式", "具体改法式", "原栏目式"],
    }
    meta.update(overrides)
    return meta


def write_json(tmpdir, name, obj, bom=False):
    path = os.path.join(tmpdir, name)
    data = json.dumps(obj, ensure_ascii=False, indent=2)
    if bom:
        data = "\ufeff" + data
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)
    return path


def run_cli(*cli_args):
    proc = subprocess.run(
        [sys.executable, RULES_CLI] + list(cli_args),
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


PENDING = "/tmp/nonexistent-pending-tips.json"  # 本任务 pending 内容不校验，路径仅为 R0 触发


@case("1. R0 缺 meta 拒：给 --pending 不给 --meta → 非0 且报 R0")
def t_r0_missing_arg():
    rc, out = run_cli("--line", "tips", "--pending", PENDING)
    return rc != 0 and "R0" in out


@case("2. R0 meta 文件不存在拒：--meta 指向不存在路径 → 非0 且报 R0")
def t_r0_meta_not_found():
    rc, out = run_cli("--line", "tips", "--pending", PENDING,
                      "--meta", "/tmp/nonexistent-draft-meta.json")
    return rc != 0 and "R0" in out


@case("3. R14 核心字段缺失拒：删 review_conclusion → 非0 且报 R14")
def t_r14_core_missing():
    with tempfile.TemporaryDirectory() as tmp:
        meta = make_meta()
        del meta["review_conclusion"]
        path = write_json(tmp, "meta.json", meta)
        rc, out = run_cli("--line", "tips", "--pending", PENDING, "--meta", path)
        return rc != 0 and "R14" in out


@case("4. R14 tips 扩展字段缺失拒：line=tips 删 cognitive_gain → 非0 且报 R14")
def t_r14_tips_ext_missing():
    with tempfile.TemporaryDirectory() as tmp:
        meta = make_meta()
        del meta["cognitive_gain"]
        path = write_json(tmp, "meta.json", meta)
        rc, out = run_cli("--line", "tips", "--pending", PENDING, "--meta", path)
        return rc != 0 and "R14" in out


@case("5. R14 review_conclusion 非'通过'拒：写'待审' → 非0 且报 R14")
def t_r14_review_pending():
    with tempfile.TemporaryDirectory() as tmp:
        meta = make_meta(review_conclusion="待审")
        path = write_json(tmp, "meta.json", meta)
        rc, out = run_cli("--line", "tips", "--pending", PENDING, "--meta", path)
        return rc != 0 and "R14" in out


@case("6. R14 blind_test_result 非'通过'拒：写'未过' → 非0 且报 R14")
def t_r14_blind_failed():
    with tempfile.TemporaryDirectory() as tmp:
        meta = make_meta(blind_test_result="未过")
        path = write_json(tmp, "meta.json", meta)
        rc, out = run_cli("--line", "tips", "--pending", PENDING, "--meta", path)
        return rc != 0 and "R14" in out


@case("7. R14 全过放行：完整 meta 两结论通过 → exit 0 且 [OK]")
def t_all_pass():
    with tempfile.TemporaryDirectory() as tmp:
        path = write_json(tmp, "meta.json", make_meta())
        rc, out = run_cli("--line", "tips", "--pending", PENDING, "--meta", path)
        return rc == 0 and "[OK]" in out


@case("8. answer 线预留：--line answer → 非0 且提示阶段 2 启用")
def t_answer_reserved():
    rc, out = run_cli("--line", "answer",
                      "--pending", PENDING, "--meta", "/tmp/whatever.json")
    return rc != 0 and "阶段 2" in out


@case("9. BOM 拒：带 BOM 的合法 JSON meta → 非0 且报 META 加载失败")
def t_bom_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        path = write_json(tmp, "meta_bom.json", make_meta(), bom=True)
        rc, out = run_cli("--line", "tips", "--pending", PENDING, "--meta", path)
        return rc != 0 and "META 加载失败" in out


def main():
    if not CASES:
        print("[FAIL] 0 用例：测试框架未注册任何用例")
        return 1
    failed = 0
    for name, fn in CASES:
        try:
            ok = fn()
        except Exception as e:  # 用例自身异常视为失败，不假绿
            ok = False
            print("[FAIL] %s（用例异常：%s）" % (name, e))
            failed += 1
            continue
        if ok:
            print("[PASS] %s" % name)
        else:
            print("[FAIL] %s" % name)
            failed += 1
    total = len(CASES)
    print("---")
    print("%d/%d 用例通过" % (total - failed, total))
    if failed:
        print("[FAIL] content_rules 自测未全过")
        return 1
    print("[OK] content_rules 自测全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_fill_answer_post —— fill_answer_post.py（答一道引擎）回归测试（沙箱）。

运行：python3 scripts/test_fill_answer_post.py [关键字...]
- 全过 exit 0；任一用例失败、用例数 <10 或真实模板 sha256 变化 → exit 1（不允许假绿）。
- 沙箱纪律：模板源用 skill 内 assets/answer-template-baseline.docx（可用环境变量
  ANSWER_TEST_PROJECT_ROOT 注入替代模板所在项目根，默认不读 vault），全程只写
  系统临时目录里的副本；结束断言 vault 模板 1 与 assets baseline 的 sha256 前后不变。
- 覆盖 11 用例：黄金路径全契约（exit0 / pending 清理 / 快照 / 19 段 5 图 / 字段
  命中 / 封面前缀）/ 真题库前缀黄金路径 / --help / exit1 六种（无 pending / 无
  模板 / 缺 question / 段数漂移 / 真题错前缀 / 项目根未传）/ env ANSWER_PROJECT_ROOT。
- 引擎退出码语义 = 源版本（structured-post v2）：0 成功 / 1 环境或验证失败
  （写入前预检失败时模板字节不变）。
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "fill_answer_post.py")
BASELINE = os.path.join(HERE, "..", "assets", "answer-template-baseline.docx")

DEFAULT_VAULT_ROOT = "/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/结构化"
REAL_TPL = os.path.join(DEFAULT_VAULT_ROOT, "desktop-attachments",
                        "1 结构化每日一练-帖子内容编辑模板.docx")

MIN_CASES = 10

# 模板契约（与引擎常量同源）
EXPECTED_PARAS = 19
EXPECTED_DRAWING = 5
GOLDEN = {
    "source": "模拟题库",
    "question": "单位推行错峰上下班，有同事抱怨接送孩子受影响，你怎么看？",
    "break_angle": "破题角度：从制度目标与个体负担的平衡切入，不站队单向否定。",
    "break_angle_reason": "切入理由：题干张力在制度善意与职工实际困难之间，答平衡点最切题。",
    "core_views_title": "核心观点",
    "core_views_intro": "（三个递进：先看制度为什么立，再看负担出在哪，最后落在怎么补位）：",
    "core_views": ["1. 制度目标是提效率减拥堵，方向要肯定。",
                   "2. 抱怨的根源是一刀切执行没留弹性。",
                   "3. 用弹性时段与托底服务把负担接住。"],
    "opening": "错峰上下班本身是好政策，方向我肯定；同事的抱怨也不是矫情，是配套没跟上。",
    "point1_lead": "第一，先看这项制度要解决什么问题。",
    "point1_body": "单位集中上下班造成人流拥挤，错峰是把高峰摊开，整体效率是提升的。",
    "point2_lead": "第二，再看负担落在谁头上。",
    "point2_body": "接送孩子的时间是刚性的，职工被夹在中间，抱怨指向政策协同缺了一块。",
    "point3_lead": "第三，解决的关键在补位不在回退。",
    "point3_body": "我会建议设弹性缓冲半小时、统计职工子女入学时段与学校协商衔接。",
    "closing": "说到底，好制度要看它有没有把受影响的人安排好。",
}


def sha256(path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def pristine_template_bytes() -> bytes:
    """沙箱模板源：ANSWER_TEST_PROJECT_ROOT 注入项目根时读其模板，否则读 skill 内 baseline。"""
    override = os.environ.get("ANSWER_TEST_PROJECT_ROOT")
    if override:
        src = Path(override) / "desktop-attachments" / "1 结构化每日一练-帖子内容编辑模板.docx"
    else:
        src = Path(BASELINE)
    return src.read_bytes()


def make_sandbox(tmpdir, template_bytes=None, pending="golden"):
    """在 tmpdir/proj 下搭项目根沙箱；pending: "golden"=合法样本 | dict | None。"""
    root = Path(tmpdir) / "proj"
    (root / "desktop-attachments").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    tpl = root / "desktop-attachments" / "1 结构化每日一练-帖子内容编辑模板.docx"
    tpl.write_bytes(pristine_template_bytes() if template_bytes is None else template_bytes)
    pending_path = root / "scripts" / "pending_answer.json"
    if pending == "golden":
        pending_path.write_text(json.dumps(GOLDEN, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    elif isinstance(pending, dict):
        pending_path.write_text(json.dumps(pending, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    return root, tpl, pending_path


def run_engine(root, use_flag=True):
    """跑引擎子进程；始终清掉外部 ANSWER_PROJECT_ROOT 防串环境。"""
    env = dict(os.environ)
    env.pop("ANSWER_PROJECT_ROOT", None)
    cmd = [sys.executable, ENGINE]
    if use_flag:
        cmd += ["--project-root", str(root)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout + proc.stderr


def doc_shape(path):
    doc = Document(str(path))
    paras = len(doc.paragraphs)
    drawing = sum(len(p._element.findall(".//" + qn("w:drawing"))) for p in doc.paragraphs)
    return doc, paras, drawing


CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


@case("golden 黄金路径全契约")
def case_golden(check):
    with tempfile.TemporaryDirectory(prefix="fill_answer_test_") as tmpdir:
        root, tpl, pending_path = make_sandbox(tmpdir)
        rc, out = run_engine(root)
        check(rc == 0, "exit=%s out=%s" % (rc, out[-300:]))
        check(not pending_path.exists(), "pending 未清理")
        snaps = list((root / "scripts" / "_snapshots").glob("snapshot_*.docx"))
        check(len(snaps) == 1, "快照数=%s" % len(snaps))
        doc, paras, drawing = doc_shape(tpl)
        check(paras == EXPECTED_PARAS, "段数=%s" % paras)
        check(drawing == EXPECTED_DRAWING, "w:drawing=%s" % drawing)
        check("破题角度" in (doc.paragraphs[2].text or ""), "段[2] 大纲未写入")
        check("pageBreakBefore" in doc.paragraphs[9]._element.xml, "段[9] 缺分页符")
        prefixes = [txbx.findall(".//" + qn("w:t"))[0].text
                    for txbx in doc.paragraphs[0]._element.iter(qn("w:txbxContent"))]
        check(prefixes == ["结构化每日一练：", "结构化每日一练："], "封面前缀镜像=%r" % prefixes)


@case("golden 真题库前缀（结构化历年考题：）")
def case_real_exam(check):
    with tempfile.TemporaryDirectory(prefix="fill_answer_test_") as tmpdir:
        pending = dict(GOLDEN)
        pending["source"] = "真题库"
        pending["title_prefix"] = "结构化历年考题："
        root, tpl, _ = make_sandbox(tmpdir, pending=pending)
        rc, out = run_engine(root)
        check(rc == 0, "exit=%s out=%s" % (rc, out[-300:]))
        doc, _, _ = doc_shape(tpl)
        prefixes = [txbx.findall(".//" + qn("w:t"))[0].text
                    for txbx in doc.paragraphs[0]._element.iter(qn("w:txbxContent"))]
        check(prefixes == ["结构化历年考题：", "结构化历年考题："], "封面前缀镜像=%r" % prefixes)


@case("help --help 可运行")
def case_help(check):
    env = dict(os.environ)
    env.pop("ANSWER_PROJECT_ROOT", None)
    proc = subprocess.run([sys.executable, ENGINE, "--help"], capture_output=True, text=True, env=env)
    check(proc.returncode == 0, "exit=%s" % proc.returncode)
    check("--project-root" in proc.stdout, "未展示 --project-root")


@case("exit1 无 pending")
def case_no_pending(check):
    with tempfile.TemporaryDirectory(prefix="fill_answer_test_") as tmpdir:
        root, tpl, pending_path = make_sandbox(tmpdir, pending=None)
        rc, out = run_engine(root)
        check(rc == 1, "exit=%s" % rc)
        check("待写入文件不存在" in out, "未报 pending 缺失")
        check(sha256(tpl) == sha256(Path(tpl)), "模板状态异常")


@case("exit1 无模板")
def case_no_template(check):
    with tempfile.TemporaryDirectory(prefix="fill_answer_test_") as tmpdir:
        root, tpl, _ = make_sandbox(tmpdir)
        tpl.unlink()
        rc, out = run_engine(root)
        check(rc == 1, "exit=%s" % rc)
        check("模板不存在" in out, "未报模板缺失")


@case("exit1 缺 question 字段（模板字节不变）")
def case_missing_question(check):
    with tempfile.TemporaryDirectory(prefix="fill_answer_test_") as tmpdir:
        pending = dict(GOLDEN)
        del pending["question"]
        root, tpl, pending_path = make_sandbox(tmpdir, pending=pending)
        before = sha256(tpl)
        rc, out = run_engine(root)
        check(rc == 1, "exit=%s" % rc)
        check("缺 'question' 字段" in out, "未报缺 question")
        check(sha256(tpl) == before, "模板字节被改动")
        check(pending_path.exists(), "pending 被清理（失败应保留）")


@case("exit1 段数漂移（写入前预检拦截，模板字节不变）")
def case_drift(check):
    with tempfile.TemporaryDirectory(prefix="fill_answer_test_") as tmpdir:
        root, tpl, pending_path = make_sandbox(tmpdir)
        doc = Document(str(tpl))
        el = doc.paragraphs[16]._element
        el.getparent().remove(el)
        doc.save(str(tpl))
        before = sha256(tpl)
        rc, out = run_engine(root)
        check(rc == 1, "exit=%s" % rc)
        check("不符" in out and "19" in out, "未报段数基准不符")
        check(sha256(tpl) == before, "模板字节被改动")
        check(pending_path.exists(), "pending 被清理（失败应保留）")


@case("exit1 真题库来源错前缀")
def case_real_exam_wrong_prefix(check):
    with tempfile.TemporaryDirectory(prefix="fill_answer_test_") as tmpdir:
        pending = dict(GOLDEN)
        pending["source"] = "真题库"
        pending["title_prefix"] = "结构化每日一练："
        root, tpl, _ = make_sandbox(tmpdir, pending=pending)
        before = sha256(tpl)
        rc, out = run_engine(root)
        check(rc == 1, "exit=%s" % rc)
        check("结构化历年考题" in out, "未报真题前缀铁律")
        check(sha256(tpl) == before, "模板字节被改动")


@case("exit1 项目根未传（无 flag 无 env）")
def case_no_root(check):
    env = dict(os.environ)
    env.pop("ANSWER_PROJECT_ROOT", None)
    proc = subprocess.run([sys.executable, ENGINE], capture_output=True, text=True, env=env)
    check(proc.returncode == 1, "exit=%s" % proc.returncode)
    check("项目根未指定" in proc.stdout, "未报项目根未指定")


@case("env ANSWER_PROJECT_ROOT 传根可运行")
def case_env_root(check):
    with tempfile.TemporaryDirectory(prefix="fill_answer_test_") as tmpdir:
        root, tpl, pending_path = make_sandbox(tmpdir)
        env = dict(os.environ)
        env.pop("ANSWER_PROJECT_ROOT", None)
        env["ANSWER_PROJECT_ROOT"] = str(root)
        proc = subprocess.run([sys.executable, ENGINE], capture_output=True, text=True, env=env)
        check(proc.returncode == 0, "exit=%s out=%s" % (proc.returncode, proc.stdout[-300:]))
        check(not pending_path.exists(), "pending 未清理")


@case("缺大纲字段报 KeyError 退出 1（源版本语义原样保留）")
def case_missing_outline_key(check):
    with tempfile.TemporaryDirectory(prefix="fill_answer_test_") as tmpdir:
        pending = dict(GOLDEN)
        del pending["break_angle"]
        root, tpl, _ = make_sandbox(tmpdir, pending=pending)
        before = sha256(tpl)
        rc, out = run_engine(root)
        check(rc == 1, "exit=%s" % rc)
        check("KeyError" in out, "未按源版本语义抛 KeyError")
        check(sha256(tpl) == before, "预检后写入前模板字节被改动")


def main() -> int:
    selected = [entry for entry in CASES if not sys.argv[1:]
                or any(key in entry[0] for key in sys.argv[1:])]
    if len(selected) < MIN_CASES:
        print("用例数 %s < 下限 %s（筛选不中或框架坏）" % (len(selected), MIN_CASES),
              file=sys.stderr)
        return 1

    # 沙箱纪律锚点：真实 vault 模板 1 与 skill 内 baseline 的 sha256 全程不变
    real_before = sha256(REAL_TPL) if os.path.isfile(REAL_TPL) else None
    baseline_before = sha256(BASELINE)

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

    if real_before is not None:
        real_after = sha256(REAL_TPL)
        if real_after != real_before:
            failures.append("真实 vault 模板 1 sha256 变化（沙箱纪律被破坏）")
            print("[FAIL] 真实 vault 模板 1 sha256 变化: %s -> %s" % (real_before[:12], real_after[:12]))
    if sha256(BASELINE) != baseline_before:
        failures.append("assets baseline sha256 变化")
        print("[FAIL] assets baseline sha256 变化")

    passed = len(selected) - len(failures)
    print(f"\n{passed}/{len(selected)} 用例通过")
    if failures:
        print("失败用例：%s" % "、".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

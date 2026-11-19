#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_fill_tips_post —— fill_tips_post.py v3.0 回归测试（沙箱）。

运行：python3 scripts/test_fill_tips_post.py
- 全过 exit 0；任一用例失败、用例数 <12 或真实 vault 模板 sha256 变化 → exit 1（不允许假绿）。
- 沙箱纪律：TIPS_TEST_PROJECT_ROOT 注入真实项目根（默认 vault 路径）只作只读模板源，
  全程只写系统临时目录里的副本；结束断言真实 vault 模板 sha256 前后不变。
- 覆盖 16 用例：黄金路径全契约 / exit2 七种（缺字段/多字段/超长标题/坏 JSON/BOM/空字段）
  / exit1 五种（模板损坏/无 pending/模板缺失/21 段预检拦截/项目根未传）/
  env 传根两种 / exit3 样式损坏拦截 / exit4 清理失败回滚。
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "fill_tips_post.py")
sys.path.insert(0, HERE)
import fill_tips_post as eng  # noqa: E402  常量与指纹捕获与引擎同源；CLI 行为全部走子进程

DEFAULT_REAL_ROOT = "/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/结构化"
DRIFT_21_DEFAULT = ("/Users/shawn/Documents/GitHub/rshawn-skills/.chuigong/sdd/"
                    "structured-daily-stage1/snapshots/task-3-before/模板3_漂移21段.docx")


def resolve_real_root() -> Path:
    """TIPS_TEST_PROJECT_ROOT 环境变量注入真实项目根（默认 vault 路径）。"""
    return Path(os.environ.get("TIPS_TEST_PROJECT_ROOT", DEFAULT_REAL_ROOT)).expanduser()


GOLDEN = {
    "tip_title": "综合分析不会分层？一句话立骨",
    "card_point": "适用综合分析题：你卡在想到哪说到哪，是因为没有先立总起句再展开。",
    "fix_summary": "改法一句话：先给判断句立骨，再按题骨展开三点。以下以公开题干为例。",
    "demo": "示范：我不同意这个做法，理由有三。第一……第二……第三……题骨先行，逐点回扣。",
    "step1": "第一步 判断：先明确立场，用一句话给结论，不绕。",
    "step2": "第二步 展开：按题骨拆三点，每点先亮分论句再给理由。",
    "step3": "第三步 检查：回读每点是否回扣总起句，缺了就补一句勾连。",
    "case_normal": "普通答法：我觉得这个做法有好有坏，一方面……另一方面……没有先立总起句。",
    "contrast_note": "点评：普通答法不是说错了，而是没有先给题骨，听者抓不住分层逻辑。",
    "boundary_scope": "适用：观点类综合分析；不适用：演讲题与情境模拟。",
    "boundary_misuse": "常见误用：把立骨句写成复述题干；纠正动作：句中必须含立场词。",
    "boundary_evidence": "出处：本技巧整理自讲义《综合分析题_方法论提炼》立骨一节。",
    "exercise": "练习：针对『该不该给小学生布置电子作业』先写一句立骨句再展开三点。",
    "self_check": "自查：①立骨句有立场词吗 ②三点是否回扣总起 ③适用题型判断了吗",
    "hashtags": "#公考面试 #结构化面试 #综合分析 #上岸 #答题技巧",
}

REAL_ROOT = None          # main() 里初始化
PRISTINE = None           # 真实模板字节（只读快照，用于沙箱拷贝与指纹基准）


def make_sandbox(tmpdir, template_bytes=None, pending="golden"):
    """在 tmpdir/proj 下搭项目根沙箱；pending: "golden"=合法15字段 | dict | bytes | None。"""
    root = Path(tmpdir) / "proj"
    (root / "desktop-attachments").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    tpl = root / eng.TEMPLATE_REL
    tpl.write_bytes(PRISTINE if template_bytes is None else template_bytes)
    pending_path = root / eng.PENDING_REL
    if pending == "golden":
        pending_path.write_text(json.dumps(GOLDEN, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    elif isinstance(pending, dict):
        pending_path.write_text(json.dumps(pending, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    elif isinstance(pending, bytes):
        pending_path.write_bytes(pending)
    return root, tpl, pending_path


def run_engine(root, use_flag=True, tips_env_root="__unset__"):
    """跑引擎子进程。tips_env_root 为 "__unset__"/None 时清掉外部 TIPS_PROJECT_ROOT 防串环境。"""
    env = dict(os.environ)
    if tips_env_root in ("__unset__", None):
        env.pop("TIPS_PROJECT_ROOT", None)
    else:
        env["TIPS_PROJECT_ROOT"] = str(tips_env_root)
    cmd = [sys.executable, ENGINE]
    if use_flag:
        cmd += ["--project-root", str(root)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout + proc.stderr


def cleanup_sandbox(root: Path) -> None:
    """清沙箱；先恢复 scripts 目录权限（exit4 用例会被 chmod 555）。"""
    scripts = root / "scripts"
    try:
        if scripts.exists():
            os.chmod(scripts, 0o755)
    except OSError:
        pass
    shutil.rmtree(root, ignore_errors=True)


def _joined(p_el) -> str:
    return "".join(t.text or "" for t in p_el.findall(".//" + qn("w:t")))


def golden_contract_errors(tpl_path: Path) -> list:
    """黄金路径全契约独立核验（引擎写完后由测试侧复检，不信任引擎自述）。"""
    errors = []
    doc = Document(str(tpl_path))
    paras = doc.paragraphs
    if len(paras) != eng.EXPECTED_PARAS:
        return [f"段数 {len(paras)} != 23"]
    pics = sum(len(p._element.findall(".//" + qn("pic:pic"))) for p in paras)
    if pics != eng.EXPECTED_IMG_TOTAL:
        errors.append(f"pic:pic={pics} != 4")
    txbxs = list(paras[0]._element.iter(qn("w:txbxContent")))
    if len(txbxs) != eng.EXPECTED_TXBX:
        errors.append(f"txbxContent={len(txbxs)} != 2")
    for txbx in txbxs:
        text_ps = [tp for tp in txbx.iter(qn("w:p")) if tp.findall(".//" + qn("w:t"))]
        if len(text_ps) != 2:
            errors.append("封面镜像文本段落 != 2（前缀行 + 标题行）")
            continue
        if _joined(text_ps[0]) != eng.COVER_PREFIX:
            errors.append(f"封面镜像前缀缺失/被改: {_joined(text_ps[0])!r}")
        if _joined(text_ps[1]) != GOLDEN["tip_title"]:
            errors.append(f"封面镜像标题未命中: {_joined(text_ps[1])!r}")
    for idx, key in eng.BODY_REPLACE_MAP:
        expect = eng.EMOJI_PREFIX.get(idx, "") + GOLDEN[key]
        got = paras[idx].text or ""
        if expect not in got:
            errors.append(f"字段未命中: {key} @段[{idx}]")
    if not (paras[5].text or "").startswith("👍"):
        errors.append("段[5] 缺引擎自动加的 👍 段首")
    if not (paras[11].text or "").startswith("🙅\u200d♂️"):
        errors.append("段[11] 缺引擎自动加的 🙅‍♂️ 段首")
    if GOLDEN["tip_title"] in GOLDEN["card_point"] + GOLDEN["demo"] + GOLDEN["hashtags"]:
        errors.append("测试数据自检失败：tip_title 不应内嵌在正文字段")
    # 引流段[21] 原文 + 样式不动
    if (paras[21].text or "") != eng.DRAIN_TEXT:
        errors.append("段[21] 引流段原文被改动")
    r21 = paras[21].runs[0] if paras[21].runs else None
    if r21 is None or not (paras[21].alignment == 1 and r21.bold is True
                           and str(r21.font.color.rgb) == eng.DRAIN_COLOR):
        errors.append("段[21] 引流段样式漂移（居中/加粗/#85120F）")
    # 固定标题段原文不动
    for idx, expected_text in eng.FIXED_HEADING_PARAS:
        if (paras[idx].text or "") != expected_text:
            errors.append(f"段[{idx}] 固定标题被改动")
    # 末图[22] 不动
    if len(paras[22]._element.findall(".//" + qn("pic:pic"))) != 1:
        errors.append("段[22] 末图丢失")
    # 样式指纹零漂移（pristine vs 输出，含封面文本框内段落）
    fp_before = eng.capture_style_fingerprint(Document(BytesIO(PRISTINE)))
    fp_after = eng.capture_style_fingerprint(doc)
    if fp_before != fp_after:
        errors.append("样式指纹漂移（逐段 pPr/rPr 与写入前不一致）")
    return errors


CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


@case("1. 黄金路径全契约：23 段模板 + 15 字段 pending → exit0（段数/pic:pic/txbx/15字段/"
      "双镜像前缀/emoji/引流段/指纹零漂移/pending 清理/快照）")
def t_golden():
    tmp = tempfile.mkdtemp(prefix="tips_t4_golden_")
    try:
        root, tpl, pending = make_sandbox(tmp)
        rc, out = run_engine(root)
        if rc != 0:
            print(f"      引擎 exit={rc}\n      {out.strip()[:800]}")
            return False
        errs = golden_contract_errors(tpl)
        if errs:
            for e in errs:
                print(f"      {e}")
            return False
        if pending.exists():
            print("      pending 未清理")
            return False
        snaps = sorted((root / eng.SNAPSHOTS_REL).glob("snapshot_*.docx"))
        if len(snaps) != 1 or snaps[0].read_bytes() != PRISTINE:
            print(f"      快照异常: {len(snaps)} 个 / 字节不等于写入前")
            return False
        if "样式指纹零漂移" not in out:
            print("      输出缺样式指纹零漂移自述")
            return False
        return True
    finally:
        cleanup_sandbox(Path(tmp))


@case("2. 缺字段（删 hashtags）→ exit2 且点名缺失字段")
def t_missing_field():
    tmp = tempfile.mkdtemp(prefix="tips_t4_miss_")
    try:
        root, _, _ = make_sandbox(tmp, pending={k: v for k, v in GOLDEN.items()
                                                if k != "hashtags"})
        rc, out = run_engine(root)
        return rc == 2 and "hashtags" in out and "缺少" in out
    finally:
        cleanup_sandbox(Path(tmp))


@case("3. 多字段（加 foo_bar）→ exit2 且点名多余字段")
def t_extra_field():
    tmp = tempfile.mkdtemp(prefix="tips_t4_extra_")
    try:
        bad = dict(GOLDEN)
        bad["foo_bar"] = "多余字段"
        root, _, _ = make_sandbox(tmp, pending=bad)
        rc, out = run_engine(root)
        return rc == 2 and "foo_bar" in out and "多余" in out
    finally:
        cleanup_sandbox(Path(tmp))


@case("4. 超长标题（21 字 > 20）→ exit2 且报超长")
def t_title_too_long():
    tmp = tempfile.mkdtemp(prefix="tips_t4_long_")
    try:
        bad = dict(GOLDEN, tip_title="这个标题特别特别长肯定超过了二十字限制啊呀")  # 21 字
        assert len(bad["tip_title"]) > eng.TITLE_MAX_CHARS
        root, _, _ = make_sandbox(tmp, pending=bad)
        rc, out = run_engine(root)
        return rc == 2 and "超长" in out and "tip_title" in out
    finally:
        cleanup_sandbox(Path(tmp))


@case("5. 坏 JSON（语法错）→ exit2 且模板字节不变")
def t_bad_json():
    tmp = tempfile.mkdtemp(prefix="tips_t4_badjson_")
    try:
        root, tpl, _ = make_sandbox(tmp, pending='{"tip_title": "缺尾括号'.encode("utf-8"))
        rc, out = run_engine(root)
        return (rc == 2 and "语法错误" in out
                and tpl.read_bytes() == PRISTINE)
    finally:
        cleanup_sandbox(Path(tmp))


@case("6. UTF-8 BOM pending → exit2 且报 BOM")
def t_bom():
    tmp = tempfile.mkdtemp(prefix="tips_t4_bom_")
    try:
        data = b"\xef\xbb\xbf" + json.dumps(GOLDEN, ensure_ascii=False).encode("utf-8")
        root, _, _ = make_sandbox(tmp, pending=data)
        rc, out = run_engine(root)
        return rc == 2 and "BOM" in out
    finally:
        cleanup_sandbox(Path(tmp))


@case("7. 空字段（demo 为空白）→ exit2 且点名字段")
def t_empty_field():
    tmp = tempfile.mkdtemp(prefix="tips_t4_empty_")
    try:
        bad = dict(GOLDEN, demo="   ")
        root, _, _ = make_sandbox(tmp, pending=bad)
        rc, out = run_engine(root)
        return rc == 2 and "demo" in out and "非空" in out
    finally:
        cleanup_sandbox(Path(tmp))


@case("8. 模板损坏（非 docx 字节）→ exit1 且模板字节不变")
def t_corrupt_template():
    tmp = tempfile.mkdtemp(prefix="tips_t4_corrupt_")
    try:
        garbage = b"this is not a docx zip"
        root, tpl, _ = make_sandbox(tmp, template_bytes=garbage)
        rc, out = run_engine(root)
        return rc == 1 and "无法解析" in out and tpl.read_bytes() == garbage
    finally:
        cleanup_sandbox(Path(tmp))


@case("9. 无 pending → exit1")
def t_no_pending():
    tmp = tempfile.mkdtemp(prefix="tips_t4_nopending_")
    try:
        root, _, pending = make_sandbox(tmp, pending=None)
        rc, out = run_engine(root)
        return rc == 1 and "pending" in out
    finally:
        cleanup_sandbox(Path(tmp))


@case("10. 模板缺失 → exit1")
def t_missing_template():
    tmp = tempfile.mkdtemp(prefix="tips_t4_notpl_")
    try:
        root, tpl, _ = make_sandbox(tmp)
        tpl.unlink()
        rc, out = run_engine(root)
        return rc == 1 and "模板不存在" in out
    finally:
        cleanup_sandbox(Path(tmp))


@case("11. TIPS_TEST_PROJECT_ROOT 环境变量注入真实项目根 → 正确解析且黄金路径 exit0")
def t_env_test_root():
    os.environ["TIPS_TEST_PROJECT_ROOT"] = str(REAL_ROOT)
    if resolve_real_root() != REAL_ROOT:
        print("      环境变量注入后解析不一致")
        return False
    tmp = tempfile.mkdtemp(prefix="tips_t4_envroot_")
    try:
        root, tpl, _ = make_sandbox(tmp)
        rc, out = run_engine(root)
        return rc == 0 and not golden_contract_errors(tpl)
    finally:
        cleanup_sandbox(Path(tmp))


@case("12. 段数预检拦截：21 段漂移模板（Task3 before 快照副本）→ exit1 且模板字节不变")
def t_para_precheck():
    drift_path = Path(os.environ.get("TIPS_TEST_DRIFT_21", DRIFT_21_DEFAULT))
    if not drift_path.exists():
        print(f"      21 段漂移模板不存在: {drift_path}")
        return False
    drift_bytes = drift_path.read_bytes()
    tmp = tempfile.mkdtemp(prefix="tips_t4_21para_")
    try:
        root, tpl, _ = make_sandbox(tmp, template_bytes=drift_bytes)
        rc, out = run_engine(root)
        return (rc == 1 and "段数" in out and "21" in out
                and tpl.read_bytes() == drift_bytes)
    finally:
        cleanup_sandbox(Path(tmp))


@case("13. 样式损坏拦截：模板正文段缺文本 run（写入被迫新增无 rPr run）→ exit3 指纹漂移"
      "且模板字节不变")
def t_style_corruption():
    doc = Document(BytesIO(PRISTINE))
    p2 = doc.paragraphs[2]._element
    for r in list(p2.findall(qn("w:r"))):
        p2.remove(r)  # 抽掉段[2]（card_point）唯一文本 run：引擎只能新增无样式 run
    buf = BytesIO()
    doc.save(buf)
    corrupted = buf.getvalue()
    tmp = tempfile.mkdtemp(prefix="tips_t4_style_")
    try:
        root, tpl, _ = make_sandbox(tmp, template_bytes=corrupted)
        rc, out = run_engine(root)
        return (rc == 3 and "样式指纹漂移" in out
                and tpl.read_bytes() == corrupted)
    finally:
        cleanup_sandbox(Path(tmp))


@case("14. exit4 回滚：scripts 目录 chmod 555 令 pending 清理失败 → exit4、"
      "模板字节回滚==写入前、pending 保留")
def t_exit4_rollback():
    tmp = tempfile.mkdtemp(prefix="tips_t4_exit4_")
    try:
        root, tpl, pending = make_sandbox(tmp)
        os.chmod(root / "scripts", 0o555)  # 清理 unlink 需目录写权限，555 必失败
        rc, out = run_engine(root)
        ok = (rc == 4 and "回滚" in out
              and tpl.read_bytes() == PRISTINE
              and pending.exists())
        if not ok:
            print(f"      exit={rc} 回滚字节一致={tpl.read_bytes() == PRISTINE} "
                  f"pending 保留={pending.exists()}\n      {out.strip()[:600]}")
        return ok
    finally:
        cleanup_sandbox(Path(tmp))


@case("15. TIPS_PROJECT_ROOT 环境变量传根（无 --project-root）→ 正确解析 exit0")
def t_engine_env_root():
    tmp = tempfile.mkdtemp(prefix="tips_t4_tipspenv_")
    try:
        root, tpl, _ = make_sandbox(tmp)
        rc, out = run_engine(root, use_flag=False, tips_env_root=root)
        return rc == 0 and not golden_contract_errors(tpl)
    finally:
        cleanup_sandbox(Path(tmp))


@case("16. 项目根未传（无 --project-root 无环境变量，fallback 已取消）→ exit1 要求显式传")
def t_no_root():
    tmp = tempfile.mkdtemp(prefix="tips_t4_noroot_")
    try:
        root, _, _ = make_sandbox(tmp)
        rc, out = run_engine(root, use_flag=False, tips_env_root=None)
        return rc == 1 and "显式" in out and "fallback" in out
    finally:
        cleanup_sandbox(Path(tmp))


def main() -> int:
    global REAL_ROOT, PRISTINE
    if len(CASES) < 12:
        print(f"[FAIL] 用例数 {len(CASES)} < 12：框架不完整，拒绝假绿")
        return 1
    REAL_ROOT = resolve_real_root()
    tpl_real = REAL_ROOT / eng.TEMPLATE_REL
    if not tpl_real.exists():
        print(f"[FAIL] 真实模板不存在: {tpl_real}"
              f"（检查 TIPS_TEST_PROJECT_ROOT，默认 vault 路径）")
        return 1
    PRISTINE = tpl_real.read_bytes()
    sha_before = hashlib.sha256(PRISTINE).hexdigest()
    print(f"[SETUP] 真实项目根: {REAL_ROOT}")
    print(f"[SETUP] 真实模板 sha256 前: {sha_before}")
    print("---")

    failed = 0
    for name, fn in CASES:
        try:
            ok = fn()
        except Exception as e:  # 用例自身异常视为失败，不假绿
            ok = False
            print(f"[FAIL] {name}（用例异常: {type(e).__name__}: {e}）")
            failed += 1
            continue
        if ok:
            print(f"[PASS] {name}")
        else:
            print(f"[FAIL] {name}")
            failed += 1
    total = len(CASES)
    print("---")

    sha_after = hashlib.sha256(tpl_real.read_bytes()).hexdigest()
    print(f"[SETUP] 真实模板 sha256 后: {sha_after}")
    vault_ok = sha_after == sha_before
    if not vault_ok:
        print("[FAIL] 真实 vault 模板 sha256 变化——沙箱纪律被破坏！")

    print(f"{total - failed}/{total} 用例通过（要求 >=12）")
    if failed or not vault_ok:
        print("[FAIL] fill_tips_post 回归未全过")
        return 1
    print("[OK] fill_tips_post 回归全过；真实 vault 模板 sha256 前后一致（vault 未被触碰）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

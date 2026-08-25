# -*- coding: utf-8 -*-
"""PE-trial-daily 统一测试入口（任务1 扩展版）。

隔离测试：在临时工作区构建 pending_trial_daily.json，运行 fill_trial_daily_post.py，
验证生成 DOCX 的结构契约（封面、图例、环节拆解、易犯错误表格、试讲逐字稿、引流页）；
并覆盖任务1 核心库 ptd_core 的可生成视图、dry-run 迁移、事实锁定、诚实性硬门、
三类片段流程与 100 分量表放行线（含故意制造坏草稿的反向用例）。

用法:
    python3 test_fill_trial_daily_post.py

退出码 0 当且仅当全部用例通过；任一失败打印 ❌ 用例名 + 原因。skipped=0。
"""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import RGBColor

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import ptd_core  # noqa: E402
import build_fixtures  # noqa: E402
import ptd_workflow  # noqa: E402
import render_docx  # noqa: E402
import fill_trial_daily_post as fill  # noqa: E402

CYAN_LEGACY = "关注我，每天一个体育试讲设计，帮你备考上岸"
FILL_SCRIPT = SCRIPT_DIR / "fill_trial_daily_post.py"

# ---------------------------------------------------------------------------
# 用例注册器
# ---------------------------------------------------------------------------

CASES = []


def case(fn):
    CASES.append((fn.__name__, fn))
    return fn


def _assert(cond, detail=""):
    if not cond:
        raise AssertionError(detail or "断言失败")


# ---------------------------------------------------------------------------
# 只读源缓存
# ---------------------------------------------------------------------------

_cache = {}


def _view():
    if "view" not in _cache:
        _cache["view"] = ptd_core.build_generatable_view()
    return _cache["view"]


def _fixtures():
    if "fixtures" not in _cache:
        _cache["fixtures"] = build_fixtures.build_all()
    return _cache["fixtures"]


def _lib():
    if "lib" not in _cache:
        _cache["lib"] = ptd_core.BookLibrary()
    return _cache["lib"]


def _entry(view, rid):
    return next(e for e in view["entries"] if e["id"] == rid)


# ===========================================================================
# 可生成视图 / 稳定 ID
# ===========================================================================


@case
def view_total_313():
    _assert(len(_view()["entries"]) == 313, f"entries={len(_view()['entries'])}")


@case
def view_ids_unique():
    ids = [e["id"] for e in _view()["entries"]]
    _assert(len(set(ids)) == len(ids), "稳定 ID 存在重复")


@case
def view_difficulty_missing_171():
    st = _view()["stats"]
    _assert(st["difficulty_missing"] == 171, f"difficulty_missing={st['difficulty_missing']}")


@case
def view_generatable_302_blockers_11():
    st = _view()["stats"]
    _assert(st["generatable"] == 302, f"generatable={st['generatable']}")
    _assert(st["blockers"] == 11, f"blockers={st['blockers']}")


@case
def view_blockers_all_wushu_no_pdf():
    blk = [e for e in _view()["entries"] if e["generatable_blockers"]]
    _assert(len(blk) == 11, f"blocked={len(blk)}")
    for e in blk:
        _assert("武术" in e["book_file"], f"{e['id']} 阻塞非武术")
        _assert("figure_required_but_pdf_missing" in e["generatable_blockers"], e["id"])
        _assert(not e["book_pdf_available"], f"{e['id']} 应无 PDF")


@case
def view_use_extracted_implies_pdf():
    for e in _view()["entries"]:
        if e["figure_policy"] == "use_extracted":
            _assert(e["book_pdf_available"], f"{e['id']} use_extracted 但缺 PDF")


@case
def view_needs_ocr_verify_15():
    n = sum(1 for e in _view()["entries"] if "figure_needs_ocr_verify" in e["flags"])
    _assert(n == 15, f"needs_ocr_verify={n}")


@case
def view_p1_no_figure_generatable():
    e = _entry(_view(), "PTD-000-乒乓球-平击球")
    _assert(e["figure_policy"] == "none", e["figure_policy"])
    _assert(e["generatable"], "P1 应可生成")


@case
def view_p2_figures_ok():
    e = _entry(_view(), "PTD-244-篮球-原地运球")
    _assert(e["figure_policy"] == "use_extracted", e["figure_policy"])
    _assert(e["figures"] and all(f["match"] == "ok" for f in e["figures"]), e["figures"])


@case
def view_p3_misattribution_kept_not_deleted():
    e = _entry(_view(), "PTD-048-体能-照镜子")
    _assert("figure_misattribution_suspect" in e["flags"], "照镜子误收应留证")
    _assert(e["figure_policy"] == "misattributed_treat_as_none", e["figure_policy"])
    _assert(e["generatable"], "误收按无图处理，仍可生成")


@case
def view_misattribution_suspect_total_28():
    st = _view()["stats"]
    _assert(st["figure_misattribution_suspect"] == 28, st["figure_misattribution_suspect"])


# ===========================================================================
# dry-run 迁移表（孤儿不丢）
# ===========================================================================


@case
def migration_rows_3_dry_run():
    m = _view()["migration_dryrun"]
    _assert(m["mode"] == "dry-run", m["mode"])
    _assert(len(m["rows"]) == 3, f"rows={len(m['rows'])}")


@case
def migration_orphan_kept_classified():
    m = _view()["migration_dryrun"]
    row = next(r for r in m["rows"] if r["progress_name"] == "技巧大赛")
    _assert(row["disposition"] == "orphan_keep_classified", row["disposition"])
    _assert(row["view_id"] is None, "孤儿不应被硬匹配")


@case
def migration_other_two_migrate():
    m = _view()["migration_dryrun"]
    by = {r["progress_name"]: r for r in m["rows"]}
    _assert(by["半米字移动"]["view_id"] == "PTD-045-体能-半米字移动", by["半米字移动"])
    _assert(by["抢背后滚球"]["view_id"] == "PTD-046-体能-抢背后滚球", by["抢背后滚球"])
    _assert(by["半米字移动"]["disposition"] == by["抢背后滚球"]["disposition"] == "migrate")


# ===========================================================================
# 三类片段流程 / 片段要素 / 量表
# ===========================================================================


@case
def flows_cover_three_types():
    _assert({"practice", "game", "fitness"} <= set(ptd_core.FLOWS), set(ptd_core.FLOWS))


@case
def flow_stage_counts():
    _assert(len(ptd_core.FLOWS["practice"]) == 5, len(ptd_core.FLOWS["practice"]))
    _assert(len(ptd_core.FLOWS["game"]) == 5, len(ptd_core.FLOWS["game"]))
    _assert(len(ptd_core.FLOWS["fitness"]) == 4, len(ptd_core.FLOWS["fitness"]))


@case
def flow_sec_ranges_valid():
    for t, stages in ptd_core.FLOWS.items():
        for s in stages:
            lo, hi = s["sec_range"]
            _assert(0 < lo <= hi <= 120, f"{t} {s['stage']} {s['sec_range']}")
            _assert(s["stage"] and s["purpose"], f"{t} 缺 stage/purpose")


@case
def segment_fields_complete():
    want = ["学段", "片段位置", "时长", "重点", "器材", "安全", "分层", "评价"]
    _assert(ptd_core.SEGMENT_FIELDS == want, ptd_core.SEGMENT_FIELDS)


@case
def scale_matches_frozen_thresholds():
    _assert(ptd_core.SCALE == {
        "教材事实": 30, "考编可用": 20, "安全": 20, "教学": 15, "口语": 10, "证据": 5,
    }, ptd_core.SCALE)
    _assert(ptd_core.RELEASE == {
        "total_min": 85, "textbook_min": 27, "safety_min": 16, "hard_gate_max": 0,
    }, ptd_core.RELEASE)


# ===========================================================================
# fixture 正向：总分/分项/硬门/时长
# ===========================================================================


@case
def fixture_all_release():
    for f in _fixtures():
        _assert(f["result"]["release"], f"{f['draft']['id']} 未放行")


@case
def fixture_total_ge85():
    for f in _fixtures():
        _assert(f["result"]["total"] >= 85, f"{f['draft']['id']} total={f['result']['total']}")


@case
def fixture_textbook_ge27():
    for f in _fixtures():
        _assert(f["result"]["scores"]["教材事实"] >= 27, f"{f['draft']['id']} 教材={f['result']['scores']['教材事实']}")


@case
def fixture_safety_ge16():
    for f in _fixtures():
        _assert(f["result"]["scores"]["安全"] >= 16, f"{f['draft']['id']} 安全={f['result']['scores']['安全']}")


@case
def fixture_hard_zero():
    for f in _fixtures():
        _assert(f["result"]["hard_gates"] == [], f"{f['draft']['id']} hard={f['result']['hard_gates']}")


@case
def fixture_factlock_unclassified_zero():
    for f in _fixtures():
        _assert(f["result"]["factlock"]["unclassified"] == 0,
                f"{f['draft']['id']} unclassified={f['result']['factlock']['unclassified']}")


@case
def fixture_duration_in_2to4min():
    for f in _fixtures():
        d = f["result"]["estimated_duration_sec"]
        _assert(120 <= d <= 240, f"{f['draft']['id']} dur={d}s")


@case
def fixture_flow_stages_match_template():
    for f in _fixtures():
        want = [s["stage"] for s in ptd_core.FLOWS[f["view"]["activity_type"]]]
        got = [st["stage"] for st in f["draft"]["flow"]]
        _assert(got == want, f"{f['draft']['id']} {got} != {want}")


@case
def fixture_covers_practice_and_fitness():
    types = {f["view"]["activity_type"] for f in _fixtures()}
    _assert("practice" in types and "fitness" in types, types)


@case
def difficulty_empty_no_fabricated_stars():
    for f in _fixtures():
        d = f["draft"]["fields"]["difficulty"]
        if not f["view"]["index_difficulty"]:
            _assert(d["kind"] != "index_stars", f"{f['draft']['id']} 空难度不得编星")
            _assert("★" not in d.get("display", ""), f"{f['draft']['id']} display 含星")
            _assert(d["kind"] == "index_empty_adapted", f"{f['draft']['id']} kind={d['kind']}")


@case
def p2_errors_textbook_legit_not_faked():
    f = _fixtures()[1]  # P2 篮球原地运球（索引 has_errors=True）
    _assert(f["view"]["index_has_errors"], "P2 应标记有教材纠错")
    rows = f["draft"]["fields"]["errors"]["rows"]
    _assert(len(rows) == 3, f"P2 纠错行数={len(rows)}")
    for i, r in enumerate(rows):
        _assert(r["error"]["provenance"] == "textbook", f"P2 纠错[{i}] 应教材原文")
        _assert(r["fix"]["provenance"] == "textbook", f"P2 纠正[{i}] 应教材原文")
    _assert(ptd_core.check_honesty(f["draft"], f["view"]) == [], "P2 教材纠错不应误判为造假")


# ===========================================================================
# 反向用例：坏草稿必须被拒绝（先红后绿已在修复期验证）
# ===========================================================================


def _neg_base():
    return copy.deepcopy(_fixtures()[0]["draft"]), _fixtures()[0]["view"]


@case
def neg_textbook_no_evidence_rejected():
    draft, view = _neg_base()
    draft["fields"]["method"]["evidence"] = []
    res = ptd_core.score_draft(draft, view, _lib())
    _assert(not res["release"], "教材块缺证据仍放行")
    _assert(res["scores"]["教材事实"] < 27, f"教材={res['scores']['教材事实']}")


@case
def neg_evidence_line_mismatch_rejected():
    draft, view = _neg_base()
    draft["fields"]["method"]["evidence"][0]["line"] = 999999
    res = ptd_core.score_draft(draft, view, _lib())
    _assert(not res["release"], "行号与摘录不符仍放行")


@case
def neg_adapted_unregistered_token_rejected():
    draft, view = _neg_base()
    draft["flow"][1]["script"] += "。每个人跳三次"
    res = ptd_core.score_draft(draft, view, _lib())
    _assert(not res["release"], "未归类事实 token 仍放行")
    _assert("factlock_unclassified_gt0" in res["hard_gates"], res["hard_gates"])


@case
def neg_fabricated_difficulty_rejected():
    draft, view = _neg_base()
    draft["fields"]["difficulty"] = {"kind": "index_stars", "display": "★★", "provenance": "textbook"}
    res = ptd_core.score_draft(draft, view, _lib())
    _assert(not res["release"], "空难度编星仍放行")
    _assert("fabricated_difficulty" in res["hard_gates"], res["hard_gates"])


@case
def neg_practice_errors_faked_rejected():
    draft, view = _neg_base()
    _assert(view["activity_type"] == "practice" and not view["index_has_errors"], "前置：P1 无教材纠错标记")
    for r in draft["fields"]["errors"]["rows"]:
        r["error"]["provenance"] = "textbook"
        r["fix"]["provenance"] = "textbook"
    res = ptd_core.score_draft(draft, view, _lib())
    _assert(not res["release"], "practice 纠错冒充教材原文仍放行")
    _assert(any(h.startswith("practice_errors_faked") for h in res["hard_gates"]), res["hard_gates"])


@case
def neg_duration_out_of_range_rejected():
    draft, view = _neg_base()
    draft["config"]["segment_duration_sec"] = [10, 20]
    res = ptd_core.score_draft(draft, view, _lib())
    _assert(not res["release"], "口播时长超范围仍放行")
    _assert("script_duration_out_of_range" in res["hard_gates"], res["hard_gates"])


@case
def neg_no_textbook_block_rejected():
    draft, view = _neg_base()
    for k in ("method", "intent"):
        draft["fields"][k]["provenance"] = "adapted"
    res = ptd_core.score_draft(draft, view, _lib())
    _assert(not res["release"], "无教材原文支撑仍放行")
    _assert(res["scores"]["教材事实"] < 27, f"教材={res['scores']['教材事实']}")


# ===========================================================================
# excerpt_at 行级证据校验
# ===========================================================================


@case
def excerpt_at_valid_line_true():
    book = "人教版教师用书-乒乓球.md"
    line = 952
    raw = _lib().lines(book)[line]
    _assert(_lib().excerpt_at(book, line, raw), "真实行+整行摘录应通过")


@case
def excerpt_at_empty_line_rejected():
    book = "人教版教师用书-乒乓球.md"
    lines = _lib().lines(book)
    empty = next((i for i, ln in enumerate(lines) if not ln.strip()), None)
    _assert(empty is not None, "教材中应存在空行供测试")
    _assert(not _lib().excerpt_at(book, empty, "任意内容"), "空行不得通过行级校验")


@case
def excerpt_at_wrong_line_rejected():
    book = "人教版教师用书-乒乓球.md"
    _assert(not _lib().excerpt_at(book, 100, "完全不存在的内容内容内容"), "错误行不得通过")


# ===========================================================================
# 任务2：3:4 版式契约（XML 级快查 + 官方渲染集成）
# ===========================================================================

LAYOUT_TITLES = {"环节拆解", "易犯错误与纠正", "试讲逐字稿", "图例直观"}


def _doc_runs(doc):
    """遍历段落与表格单元格里的所有 run。"""
    for p in doc.paragraphs:
        for r in p.runs:
            yield r
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for r in p.runs:
                        yield r


@case
def layout_page_size_3_4():
    fr = _fill_result()
    _assert(fr["doc"] is not None)
    for si, sec in enumerate(fr["doc"].sections):
        ratio = sec.page_width / sec.page_height
        _assert(abs(ratio - 0.75) / 0.75 <= 0.01, f"第{si+1}节页宽高比 {ratio:.4f}")


@case
def layout_cover_brand_bg_full_page():
    fr = _fill_result()
    doc = fr["doc"]
    _assert(doc is not None)
    anchors = [a for a in doc.element.body.findall(".//" + qn("wp:anchor"))
               if a.get("behindDoc") == "1"]
    _assert(anchors, "封面底层图缺失")
    anchor = anchors[0]
    _assert(anchor.get("layoutInCell") == "0", "封面底图仍受单元格裁切")
    extent = anchor.find(qn("wp:extent"))
    _assert(extent is not None, "封面底图缺少尺寸")
    _assert(abs(int(extent.get("cx") or 0) - int(doc.sections[0].page_width)) <= 635,
            "封面底图宽度未精确贴页")
    _assert(abs(int(extent.get("cy") or 0) - int(doc.sections[0].page_height)) <= 635,
            "封面底图高度未精确贴页")
    for tag in ("wp:positionH", "wp:positionV"):
        pos = anchor.find(qn(tag))
        off = pos.find(qn("wp:posOffset")) if pos is not None else None
        _assert(pos is not None and pos.get("relativeFrom") == "page" and
                off is not None and off.text == "0", f"{tag} 未贴齐页边")
    shd = doc.tables[0].cell(0, 0)._tc.get_or_add_tcPr().find(qn("w:shd"))
    _assert(shd is None, "封面单元格底色会遮住底部标语和 SHTr")


@case
def layout_font_cjk_contract():
    fr = _fill_result()
    style = fr["doc"].styles["Normal"]
    rpr = style._element.rPr
    east = rpr.rFonts.get(qn("w:eastAsia")) if rpr is not None and rpr.rFonts is not None else None
    _assert(east and any(c in east for c in
            ("Hiragino", "Heiti", "Songti", "PingFang", "Microsoft YaHei", "Noto", "WenQuanYi")),
            f"Normal eastAsia 字体 {east} 不在 CJK 契约")


@case
def layout_body_min_18pt():
    fr = _fill_result()
    for r in _doc_runs(fr["doc"]):
        t = (r.text or "").strip()
        if t in LAYOUT_TITLES or t.startswith("#") or t in ("易犯错误", "纠正方法"):
            continue
        if r.font.size and any(k in t for k in ("两腿微屈", "同学们好", "降低重心", "好收球")):
            _assert(r.font.size.pt >= 18, f"正文 {t[:12]} 字号 {r.font.size.pt}")


@case
def layout_section_title_24_28pt():
    fr = _fill_result()
    for r in _doc_runs(fr["doc"]):
        if (r.text or "").strip() in LAYOUT_TITLES:
            _assert(r.font.size and 24 <= r.font.size.pt <= 28,
                    f"栏目 {r.text} 字号 {r.font.size and r.font.size.pt}")


@case
def layout_caption_label_min_16pt():
    fr = _fill_result()
    for r in _doc_runs(fr["doc"]):
        t = (r.text or "").strip()
        if t.startswith("图") and "3-2-7" in t:
            _assert(r.font.size and r.font.size.pt >= 16, f"图注 {t[:12]} {r.font.size and r.font.size.pt}")
        if t.startswith("#"):
            _assert(r.font.size and r.font.size.pt >= 16, f"标签 {t[:12]} {r.font.size and r.font.size.pt}")


@case
def layout_cta_min_18pt():
    fr = _fill_result()
    for r in _doc_runs(fr["doc"]):
        if (r.text or "").strip() == CYAN_LEGACY:
            _assert(r.font.size and r.font.size.pt >= 18, f"CTA 字号 {r.font.size and r.font.size.pt}")


@case
def layout_script_split_short_lines():
    fr = _fill_result()
    scripts = [p.text for p in fr["doc"].paragraphs
               if p.text and any(k in p.text for k in ("同学们好", "看我示范", "跟我做", "低运球", "好收球"))]
    _assert(len(scripts) >= 3, f"逐字稿仅 {len(scripts)} 段（应按短段拆分）")
    for s in scripts:
        _assert(len(s) <= 45, f"短段过长 {len(s)} 字")


@case
def layout_table_fixed_42_58():
    fr = _fill_result()
    err_tbl = None
    for t in fr["doc"].tables:
        if len(t.columns) == 2 and t.cell(0, 0).text.strip() == "易犯错误":
            err_tbl = t
            break
    _assert(err_tbl is not None, "未找到易犯错误表")
    tblPr = err_tbl._tbl.tblPr
    layout = tblPr.find(qn("w:tblLayout"))
    _assert(layout is not None and layout.get(qn("w:type")) == "fixed", "表格须固定布局(fixed)")
    grid = err_tbl._tbl.tblGrid.findall(qn("w:gridCol"))
    _assert(len(grid) == 2, f"gridCol={len(grid)}")
    w1, w2 = int(grid[0].get(qn("w:w"))), int(grid[1].get(qn("w:w")))
    _assert(abs(w1 / (w1 + w2) - 0.42) < 0.03, f"列宽比 {w1}/{w1 + w2}")
    _assert(len(err_tbl._tbl.findall(".//" + qn("w:cantSplit"))) >= 2, "表格行缺 cantSplit（行会跨页）")


@case
def layout_watermark_opacity_8_12():
    fr = _fill_result()
    for sec in fr["doc"].sections:
        x = sec.header._element.xml
        m = re.search(r'opacity="([0-9a-fA-F]{6})"', x)
        _assert(m, "水印无 opacity 属性")
        frac = int(m.group(1), 16) / 0xFFFFFF
        _assert(0.08 <= frac <= 0.12, f"水印透明度 {frac:.3f}（期望 8%–12%）")


@case
def render_full_checks_pass():
    """官方 render_docx.py --emit_pdf --check 全页检查（3:4/无方框/无裁切/CTA不孤页/水印）。"""
    fr = _fill_result()
    _assert(fr["docx_path"].exists(), "缺少输出 DOCX")
    r = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "render_docx.py"), str(fr["docx_path"]),
         "--emit_pdf", "--check", "--out", str(fr["ws"] / "rendered")],
        capture_output=True, text=True, env=dict(os.environ),
    )
    _assert(r.returncode == 0, f"渲染检查失败:\n{r.stdout}\n{r.stderr}")


# ===========================================================================
# 任务3：工作流（锁 / 状态机 / OCR缓存 / 图例STOP / IMA幂等）
# ===========================================================================


@case
def wf_deps_check_runs():
    missing = ptd_workflow.check_deps()
    _assert(isinstance(missing, list), "check_deps 应返回 list")
    _assert("python-docx 不可导入" not in missing, f"docx 缺失: {missing}")


@case
def wf_lock_exclusive_two_processes():
    ws = Path(tempfile.mkdtemp(prefix="wf_lock_"))
    try:
        _assert(ptd_workflow.acquire_lock(ws, timeout=1), "主进程应拿到锁")
        # 子进程尝试拿同一把锁 -> 必须失败（双进程只有一个成功）
        code = ("import sys; sys.path.insert(0, %r); import ptd_workflow as w;"
                "ok = w.acquire_lock(__import__('pathlib').Path(%r), timeout=1);"
                "print('LOCK', ok); sys.exit(0)")
        r = subprocess.run([sys.executable, "-c", code % (str(SCRIPT_DIR), str(ws))],
                           capture_output=True, text=True, env=dict(os.environ))
        _assert(r.returncode == 0 and r.stdout.strip() == "LOCK False",
                f"并发锁应只有一个成功: rc={r.returncode} out={r.stdout!r}")
        ptd_workflow.release_lock(ws)
        # 释放后子进程能拿到
        r2 = subprocess.run([sys.executable, "-c", code % (str(SCRIPT_DIR), str(ws))],
                            capture_output=True, text=True, env=dict(os.environ))
        _assert(r2.returncode == 0 and r2.stdout.strip() == "LOCK True",
                f"释放后应能拿到锁: {r2.stdout!r}")
    finally:
        ptd_workflow.release_lock(ws)


@case
def wf_state_idempotent_terminal():
    ws = Path(tempfile.mkdtemp(prefix="wf_state_"))
    ch = ptd_workflow.content_hash({"a": 1})
    _assert(not ptd_workflow.is_idempotent_done(ws, "PTD-X", ch), "初始不应幂等")
    ptd_workflow.advance(ws, "PTD-X", ch, "progress_commit")
    _assert(ptd_workflow.is_idempotent_done(ws, "PTD-X", ch), "终态应幂等跳过")
    ch2 = ptd_workflow.content_hash({"a": 2})
    _assert(not ptd_workflow.is_idempotent_done(ws, "PTD-X", ch2), "content_hash 变则应重跑")


@case
def wf_state_write_atomic_valid():
    ws = Path(tempfile.mkdtemp(prefix="wf_atom_"))
    for i in range(5):
        ptd_workflow.advance(ws, f"PTD-{i}", ptd_workflow.content_hash({"n": i}), "docx_commit")
        st = json.loads(ptd_workflow.state_path(ws).read_text(encoding="utf-8"))
        _assert(f"PTD-{i}" in st["entries"], f"第{i}次写入后状态应有效")
    _assert(not list(ws.glob(".wf_*")), "临时状态文件应清理")


@case
def wf_content_hash_stable():
    a = ptd_workflow.content_hash({"x": [1, 2], "s": "中文"})
    b = ptd_workflow.content_hash({"s": "中文", "x": [1, 2]})
    _assert(a == b, "content_hash 应稳定（与键序无关）")


@case
def wf_ocr_cache_hit_fingerprint():
    ws = Path(tempfile.mkdtemp(prefix="wf_ocr_"))
    pdf = ptd_core.BOOKS_DIR_DEFAULT / "人教版教师用书-乒乓球.pdf"
    _assert(pdf.exists(), "缺测试 PDF")
    cache_path = ws / "ocr_test.json"
    fp = ptd_workflow.pdf_fingerprint(pdf)
    cache_path.write_text(json.dumps({
        "fingerprint": fp, "page_count": 9, "coverage": 1.0, "pages": {"0": [{"text": "图3-2-7 原地低运球", "bbox": [0.1, 0.2, 0.5, 0.3]}]},
    }, ensure_ascii=False), encoding="utf-8")
    got = ptd_workflow.build_ocr_cache(pdf, cache_path, ws / "no.swift", log=lambda *a: None)
    _assert(got.get("fingerprint") == fp and got["page_count"] == 9, "指纹命中应直接读缓存")


@case
def wf_ocr_no_cache_on_subprocess_fail():
    ws = Path(tempfile.mkdtemp(prefix="wf_ocrf_"))
    pdf = ptd_core.BOOKS_DIR_DEFAULT / "人教版教师用书-乒乓球.pdf"
    cache_path = ws / "ocr_fail.json"
    got = ptd_workflow.build_ocr_cache(pdf, cache_path, ws / "nonexistent.swift", log=lambda *a: None)
    _assert(got == {}, "子进程非0 应返回空缓存")
    _assert(not cache_path.exists(), "子进程非0 不得落缓存")
    _assert(not list(ws.glob(".ocr_*")), "临时 OCR 文件应清理")


@case
def wf_ocr_cache_records_fingerprint_pages_coverage():
    ws = Path(tempfile.mkdtemp(prefix="wf_ocrf2_"))
    cache_path = ws / "ocr2.json"
    cache_path.write_text(json.dumps({
        "fingerprint": {"sha256_head": "abc", "size": 1, "mtime": 2},
        "page_count": 12, "coverage": 0.75, "pages": {},
    }), encoding="utf-8")
    pdf = ptd_core.BOOKS_DIR_DEFAULT / "人教版教师用书-乒乓球.pdf"
    # 指纹不匹配 -> 触发重建 -> swift 失败 -> 空且不落新缓存
    got = ptd_workflow.build_ocr_cache(pdf, cache_path, ws / "nonexistent.swift", log=lambda *a: None)
    _assert(got == {} and cache_path.exists(), "指纹不匹配时应重建；失败保留旧缓存")
    old = json.loads(cache_path.read_text(encoding="utf-8"))
    _assert("fingerprint" in old and "page_count" in old and "coverage" in old,
            "OCR 缓存必须记录指纹/页数/覆盖率")


@case
def wf_figure_stop_rule_pdf_missing():
    ws = Path(tempfile.mkdtemp(prefix="wf_fig_"))
    entry = {"id": "PTD-090-武术-抱拳礼", "figure_policy": "figure_required_but_pdf_missing",
             "figures": [{"ref": "图3-1-1"}]}
    try:
        ptd_workflow.resolve_figures(entry, None, {"pages": {}}, ws / "fig", log=lambda *a: None)
        _assert(False, "有引用但缺 PDF 应 STOP")
    except ptd_workflow.FigureStop:
        pass


@case
def wf_figure_needs_ocr_stop_when_no_caption():
    ws = Path(tempfile.mkdtemp(prefix="wf_fig2_"))
    entry = {"id": "PTD-001", "figure_policy": "needs_ocr_verify",
             "figures": [{"ref": "图3-2-3"}]}
    try:
        ptd_workflow.resolve_figures(entry, Path("/tmp/x.pdf"), {"pages": {}}, ws / "fig",
                                     log=lambda *a: None)
        _assert(False, "needs_ocr_verify 但 OCR 未命中 caption 应 STOP")
    except ptd_workflow.FigureStop:
        pass


@case
def wf_figure_no_refs_empty_figure_ok():
    ws = Path(tempfile.mkdtemp(prefix="wf_fig3_"))
    entry = {"id": "PTD-000", "figure_policy": "none", "figures": []}
    paths, note = ptd_workflow.resolve_figures(entry, None, {"pages": {}}, ws / "fig",
                                               log=lambda *a: None)
    _assert(paths == [] and note == "no_refs_empty_figure", f"无引用应空图: {note}")


@case
def wf_figure_misattributed_empty_ok():
    ws = Path(tempfile.mkdtemp(prefix="wf_fig4_"))
    entry = {"id": "PTD-048", "figure_policy": "misattributed_treat_as_none",
             "figures": [{"ref": "图3-2-3", "match": "suspect"}]}
    paths, note = ptd_workflow.resolve_figures(entry, None, {"pages": {}}, ws / "fig",
                                               log=lambda *a: None)
    _assert(paths == [] and note == "misattributed_treat_as_none", f"误收应空图: {note}")


@case
def wf_ima_idempotent_no_duplicate_note():
    ws = Path(tempfile.mkdtemp(prefix="wf_ima_"))
    ima = ptd_workflow.FakeIMA(ws)
    content = {"title": "体育试讲设计每日一练｜原地运球", "body": "逐字稿…"}
    r1 = ima.upload("PTD-000", content)
    r2 = ima.upload("PTD-000", content)
    _assert(not r1["replayed"], "首次应新建")
    _assert(r2["replayed"], "重复运行应幂等重放，不新建笔记")
    recs = json.loads((ws / "ima_records.json").read_text(encoding="utf-8"))
    _assert(len(recs) == 1, f"应只有 1 条 IMA 记录: {len(recs)}")
    rec = r2["record"]
    _assert(rec["content_hash"] and rec["note_id"] and rec["stage"], "IMA 记录缺字段")
    _assert(rec["stable_id"] == "PTD-000", "IMA 记录缺 stable_id")


@case
def wf_workflow_dryrun_advances_states():
    ws = Path(tempfile.mkdtemp(prefix="wf_run_"))
    view = {"id": "PTD-000", "figure_policy": "none", "figures": []}
    rc = ptd_workflow.run_workflow(ws, "PTD-000", view, dry_run=True)
    _assert(rc == 0, f"dry-run 退出码 {rc}")
    st = ptd_workflow.read_state(ws)
    _assert("PTD-000" in st["entries"], "dry-run 应写入状态")
    _assert(not (ws / "workflow.lock").exists(), "运行结束应释放锁")


# ===========================================================================
# 任务4：反向验证（故意制造坏输入 → 先红；好输入全绿；正式数据哈希不变）
# ===========================================================================


@case
def rev_short_script_rejected():
    draft, view = _neg_base()
    draft["flow"] = [{"stage": "导入与示范", "sec": 30, "provenance": "adapted",
                      "evidence": [{"book_file": "人教版教师用书-乒乓球.md", "line": 952,
                                    "excerpt": "正手平击球与正手平击发球动作相同。"}],
                      "adapted_facts": [], "script": "同学们好，今天学平击球。看示范。"}]
    res = ptd_core.score_draft(draft, view, _lib())
    _assert(not res["release"], "短稿（口播不足 2 分钟）仍放行")
    _assert("script_duration_out_of_range" in res["hard_gates"], res["hard_gates"])


@case
def rev_direction_reversed_rejected():
    """human-writing 后教材方向被静默反转（同侧→对侧），事实锁定必须拒绝。"""
    f = _fixtures()[1]  # P2 篮球原地运球（教材原文：同侧脚外侧前方）
    draft = copy.deepcopy(f["draft"])
    assert "同侧脚的外侧前方" in draft["flow"][3]["script"], "前置：原稿含同侧方向"
    draft["flow"][3]["script"] = draft["flow"][3]["script"].replace("同侧脚的外侧前方", "对侧脚的外侧前方")
    res = ptd_core.score_draft(draft, f["view"], _lib())
    _assert(not res["release"], "方向被静默反转仍放行")
    _assert(res["factlock"]["unclassified"] > 0, "反转后应有未归类事实 token")


@case
def rev_figure_width_1cm_rejected():
    fr = _fill_result()
    _assert(fr["doc"] is not None, "缺 docx")
    # 把内联图例 extent 改为 1cm×1cm（图宽 1cm，既不够宽也不够高）
    for p in fr["doc"].paragraphs:
        for dw in p._element.findall(".//" + qn("w:drawing")):
            inline = dw.find(qn("wp:inline"))
            if inline is None:
                continue
            ext = inline.find(qn("wp:extent"))
            if ext is not None:
                ext.set("cx", "360000")
                ext.set("cy", "360000")
    errors = fill.validate_output(fr["doc"], fr["pending"])
    _assert(any("图例未放大" in e for e in errors), f"1cm 图应被拒: {errors}")


@case
def rev_cover_bg_overflow_rejected():
    fr = _fill_result()
    anchor = next(a for a in fr["doc"].element.body.findall(".//" + qn("wp:anchor"))
                  if a.get("behindDoc") == "1")
    extent = anchor.find(qn("wp:extent"))
    extent.set("cx", str(round(int(extent.get("cx")) * 1.12)))
    extent.set("cy", str(round(int(extent.get("cy")) * 1.12)))
    errors = fill.validate_output(fr["doc"], fr["pending"])
    _assert(any("禁止放大出血" in e for e in errors), f"出血底图应被拒: {errors}")


@case
def rev_cover_bg_cell_clipping_rejected():
    fr = _fill_result()
    anchor = next(a for a in fr["doc"].element.body.findall(".//" + qn("wp:anchor"))
                  if a.get("behindDoc") == "1")
    anchor.set("layoutInCell", "1")
    tc_pr = fr["doc"].tables[0].cell(0, 0)._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), "0B3289")
    tc_pr.append(shd)
    errors = fill.validate_output(fr["doc"], fr["pending"])
    _assert(any("layoutInCell" in e for e in errors), f"单元格裁切应被拒: {errors}")
    _assert(any("单元格必须透明" in e for e in errors), f"不透明底色应被拒: {errors}")


@case
def rev_cta_color_changed_rejected():
    fr = _fill_result()
    _assert(fr["doc"] is not None)
    changed = False
    for p in fr["doc"].paragraphs:
        if p.text.strip() == CYAN_LEGACY and p.runs:
            p.runs[0].font.color.rgb = RGBColor(0xFF, 0x00, 0x00)
            changed = True
    _assert(changed, "未找到 CTA 段落")
    errors = fill.validate_output(fr["doc"], fr["pending"])
    _assert(any("固定引流段颜色" in e for e in errors), f"CTA 改色应被拒: {errors}")


@case
def rev_cta_orphan_page_rejected():
    pages = ["逐字稿第一行\n逐字稿第二行\n#标签\n" + CYAN_LEGACY,
             "只有 CTA 的孤页\n" + CYAN_LEGACY]
    bad = render_docx.check_cta_not_alone(pages, CYAN_LEGACY)
    _assert(bad, f"CTA 孤页应被拒: {bad}")
    _assert(any("仅" in b for b in bad), f"应指出正文行数不足: {bad}")


@case
def rev_ocr_partial_failure_not_verifiable():
    cache = {"page_count": 10, "coverage": 0.4, "pages": {"0": [{"text": "图3-2-7 原地低运球", "bbox": [0.1, 0.2, 0.5, 0.3]}]}}
    hits = ptd_workflow.find_caption_in_ocr(cache, "图3-2-9")
    _assert(hits == [], "部分 OCR 未覆盖的图例不应命中")
    _assert(cache["coverage"] < 0.5, "覆盖率应被记录")
    # needs_ocr_verify 且 OCR 未命中 → STOP
    entry = {"id": "PTD-X", "figure_policy": "needs_ocr_verify", "figures": [{"ref": "图3-2-9"}]}
    try:
        ptd_workflow.resolve_figures(entry, Path("/tmp/x.pdf"), cache, Path("/tmp/xfig"),
                                     log=lambda *a: None)
        _assert(False, "部分 OCR 失败不应放行图例")
    except ptd_workflow.FigureStop:
        pass


@case
def rev_data_hashes_unchanged():
    import hashlib
    idx = hashlib.sha256(ptd_core.INDEX_DEFAULT.read_bytes()).hexdigest()
    prog = hashlib.sha256(ptd_core.PROGRESS_DEFAULT.read_bytes()).hexdigest()
    _assert(idx == "bd0e2adf2d4a284a052bb6eb252d630968d8db18c1392e61cc040dd737253856",
            f"activity_index.json 哈希已变: {idx}")
    _assert(prog == "4846fdb20879d989f65d0cf16b59910539d99356f7ef07d96086df4ecd3f52cf",
            f"progress_trial.json 哈希已变: {prog}")


# ===========================================================================
# 填充管线集成（原入口，单例缓存）
# ===========================================================================

_fill_cache = None


def _fill_result():
    global _fill_cache
    if _fill_cache is not None:
        return _fill_cache
    tmp = Path(tempfile.mkdtemp(prefix="trial_test_"))
    ws = tmp / "workspace"
    (ws / "scripts").mkdir(parents=True)
    (ws / "desktop-attachments").mkdir(parents=True)

    # 生成一张测试用 PNG（覆盖图例插入路径）
    w = h = 64
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))

    def chunk(tag, data):
        c = tag + data
        return struct_pack(len(data)) + c + zlib_crc(c)

    import struct
    import zlib
    def struct_pack(n):
        return struct.pack(">I", n)
    def zlib_crc(c):
        return struct.pack(">I", zlib.crc32(c))

    fig = ws / "fig.png"
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    fig.write_bytes(png)

    pending = {
        "sport": "篮球",
        "chapter": "第三章 篮球运动教学内容 | 二、运球",
        "segment_name": "原地运球",
        "segment_type": "practice",
        "difficulty": "★★",
        "figure": "图3-2-7 原地低运球、图3-2-8 原地高运球",
        "figure_images": [str(fig)],
        "method": "两腿微屈上体稍前倾，以肘为轴前臂屈伸，用手指和指根触球，球落点在同侧脚外侧前方。",
        "rules": "降低重心抬头观察，不低头看球，另一侧手臂护球。",
        "intent": "建立正确手指触球手型与按压节奏，体会高低运球差异。",
        "organization": "散点站位每人一球，间隔一臂距离，巡回指导统一口令。",
        "errors": [
            ["掌心按拍球", "体会手指和指根触球，掌心空出"],
            ["低头看球", "手势报数游戏引导抬头"]
        ],
        "lecture_script": "同学们好，我们先复习原地运球。每人拿一个球拉开距离，记住手指触球按拍有力控制落点。看我示范，两腿微屈上体前倾，以肘为轴用手指指根触球，掌心空出。跟我做，一二三四。低运球十下，高运球十下。我转一圈看，小王做得很稳。小李你掌心太紧了，空出来。抬头看我手势，报数几个就运几个。运球不是拍球，要有迎球缓冲。这节课把手感练出来，下节课学行进间运球。好收球做放松。",
        "cta": CYAN_LEGACY,
        "hashtags": "#教师编 #体育教师 #体育试讲 #试讲设计 #一次上岸",
    }
    (ws / "scripts" / "pending_trial_daily.json").write_text(
        json.dumps(pending, ensure_ascii=False), encoding="utf-8"
    )

    env = dict(os.environ)
    env["TRIAL_DAILY_WORKSPACE"] = str(ws)
    result = subprocess.run(
        [sys.executable, str(FILL_SCRIPT)],
        capture_output=True, text=True, env=env,
    )
    docx_path = ws / "desktop-attachments" / "2 体育试讲每日一练-帖子内容编辑模板.docx"
    doc = None
    if docx_path.exists():
        doc = Document(str(docx_path))
    _fill_cache = {
        "ws": ws, "result": result, "docx_path": docx_path, "doc": doc,
        "out": result.stdout + result.stderr, "pending": pending,
    }
    return _fill_cache


@case
def fill_pipeline_script_exit_green():
    fr = _fill_result()
    _assert(fr["result"].returncode == 0, f"退出码={fr['result'].returncode}\n{fr['out']}")
    _assert("✅ 全部通过" in fr["out"], "缺成功提示\n" + fr["out"])
    _assert("✅ pending_trial_daily.json 已删除" in fr["out"], "pending 未删除\n" + fr["out"])


@case
def fill_pipeline_docx_structure():
    fr = _fill_result()
    _assert(fr["doc"] is not None, "输出 DOCX 不存在")
    doc = fr["doc"]
    text = "\n".join(p.text or "" for p in doc.paragraphs)
    for t in doc.tables:
        for r in t.rows:
            for c in r.cells:
                text += "\n" + (c.text or "")

    checks = {}
    checks["封面标题"] = "体育试讲设计每日一练" in text
    checks["项目标签"] = "【篮球】练习环节" in text
    checks["环节名"] = "原地运球" in text
    checks["活动方法"] = "两腿微屈上体稍前倾" in text
    checks["规则"] = "降低重心抬头观察" in text
    checks["设计意图"] = "建立正确手指触球手型" in text
    checks["组织形式"] = "散点站位每人一球" in text
    checks["易犯错误表"] = "易犯错误" in text and "纠正方法" in text
    checks["试讲逐字稿"] = "试讲逐字稿" in text
    checks["引流段"] = CYAN_LEGACY in text
    checks["话题标签"] = "#教师编 #体育教师" in text
    img_count = sum(
        len(p._element.findall(".//" + qn("wp:inline"))) for p in doc.paragraphs
    )
    checks["图例图片"] = img_count == 1
    anchors = doc.element.body.findall(".//" + qn("wp:anchor"))
    checks["封面底层图"] = any(a.get("behindDoc") == "1" for a in anchors)
    checks["页眉水印"] = all(
        "PowerPlusWaterMarkObject" in s.header._element.xml for s in doc.sections
    )
    title_sizes = [
        r.font.size.pt for p in doc.paragraphs for r in p.runs
        if r.text.strip() == "体育试讲设计每日一练" and r.font.size
    ]
    for tb in doc.tables:
        for row in tb.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    title_sizes += [
                        r.font.size.pt for r in p.runs
                        if r.text.strip() == "体育试讲设计每日一练" and r.font.size
                    ]
    checks["封面标题48pt"] = any(s >= 47 for s in title_sizes)
    titles = [i for i, p in enumerate(doc.paragraphs) if p.text.strip() == "环节拆解"]
    checks["环节拆解另起一页"] = bool(titles) and bool(
        doc.paragraphs[titles[0]].paragraph_format.page_break_before
    )
    body = [p for p in doc.paragraphs if p.text.strip()]
    hs_p = body[-2] if body and body[-1].text.strip() == CYAN_LEGACY else None
    no_page_break = True
    if hs_p is not None:
        prev = hs_p._element.getprevious()
        if prev is not None and prev.tag == qn("w:p"):
            for br in prev.findall(".//" + qn("w:br")):
                if br.get(qn("w:type")) == "page":
                    no_page_break = False
    checks["引流不另起页"] = no_page_break

    failed = [k for k, v in checks.items() if not v]
    _assert(not failed, f"未通过: {failed}")


# ===========================================================================
# 主入口
# ===========================================================================


def main():
    failed = 0
    for name, fn in CASES:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - 用例隔离，吞异常会掩盖失败
            failed += 1
            print(f"  ❌ {name}: {exc}")
        else:
            print(f"  ✅ {name}")
    total = len(CASES)
    print(f"\n用例 {total} 个，通过 {total - failed}，失败 {failed}，跳过 0")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

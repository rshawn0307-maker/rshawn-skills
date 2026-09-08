#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ptd_workflow.py — PE-trial-daily 工作流编排（v3：真门禁版）。

v2 的工作流入口是演示性运行（dry-run 只走一段、PDF 传 None、FakeIMA 兜底成功）。
v3 起编排真实门禁，每个状态推进都以实际检查为前提，成功提示只在检查完成后出现：

  select          草稿存在、source_view_entry 与 id 一致、无误收选题 blocker
  extract         教材证据在章节边界内、图例策略可满足（缺 PDF/图 → STOP）
  factlock        core.run_factlock：unclassified == 0
  rewrite_review  human-writing 改写标记存在 + 内容评审记录与草稿同版本（draft_sha）
  render_verify   进程内执行 fill_trial_daily_post.py（评分门+格式验证+渲染检查+原子提交）
  docx_commit     成品 DOCX 存在且新于草稿，渲染检查证据 PDF 存在
  progress_commit 进度一致性校验（已完成则幂等跳过；新选题由 agent 按 SKILL.md 写进度）
  upload_done     默认明确跳过，不冒充成功

--dry-run 只推进到 rewrite_review 且不写任何正式文件，输出带 [演练] 标注。
"""
from __future__ import annotations

import argparse
import json
import os
import runpy
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
FILL_SCRIPT = SCRIPT_DIR / "fill_trial_daily_post.py"  # 固定常量，不做任何拼接
sys.path.insert(0, str(SCRIPT_DIR))
import ptd_core as core  # noqa: E402

STATES = [
    "select", "extract", "factlock", "rewrite_review",
    "render_verify", "docx_commit", "progress_commit", "upload_done",
]
LOCK_STALE_SEC = 60


class GateStop(Exception):
    """门禁未过：携带 (状态名, 原因)。"""


def state_path(ws: Path) -> Path:
    return ws / "workflow_state.json"


def read_state(ws: Path) -> dict:
    p = state_path(ws)
    if not p.exists():
        return {"entries": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": {}}


def write_state(ws: Path, state: dict) -> None:
    import tempfile
    p = state_path(ws)
    fd, tmp = tempfile.mkstemp(prefix=".wf_", suffix=".json", dir=str(ws))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def advance(ws: Path, stable_id: str, note: str = "", to: str = "") -> None:
    st = read_state(ws)
    entry = st.setdefault("entries", {}).setdefault(stable_id, {})
    if to:
        entry["stage"] = to
        entry["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if note:
        entry.setdefault("log", []).append(note)
    write_state(ws, st)


def acquire_lock(ws: Path, timeout: float = 10.0) -> bool:
    ws.mkdir(parents=True, exist_ok=True)
    lock = ws / "workflow.lock"
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"{os.getpid()}\t{time.time()}\n")
            return True
        except FileExistsError:
            try:
                age = time.time() - lock.stat().st_mtime
            except OSError:
                age = 0
            if age > LOCK_STALE_SEC:
                try:
                    lock.unlink()
                except OSError:
                    pass
                continue
            if time.time() > deadline:
                return False
            time.sleep(0.2)


def release_lock(ws: Path) -> None:
    try:
        (ws / "workflow.lock").unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 各状态门禁（真实检查）
# ---------------------------------------------------------------------------


def load_draft(draft_path: Path) -> dict:
    if not draft_path.exists():
        raise GateStop(("select", f"草稿不存在：{draft_path}"))
    try:
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise GateStop(("select", f"草稿 JSON 损坏：{exc}"))
    if draft.get("schema") != core.SCHEMA_DRAFT:
        raise GateStop(("select", f"schema 须为 {core.SCHEMA_DRAFT}"))
    return draft


def gate_select(draft: dict) -> dict:
    view = draft.get("source_view_entry") or {}
    if view.get("id") != draft.get("id"):
        raise GateStop(("select", "source_view_entry.id 与草稿 id 不一致"))
    if "miscollected_topic" in (view.get("flags") or []):
        raise GateStop(("select", "误收选题（非教学活动，如课外作业建议）不得进入生成"))
    if view.get("generatable_blockers"):
        raise GateStop(("select", f"视图 blocker：{view['generatable_blockers']}"))
    return view


def gate_extract(draft: dict, view: dict, lib: core.BookLibrary) -> str:
    book = view.get("book_file", "")
    md_line = int(view.get("md_line", 0))
    try:
        lines = lib.lines(book)
    except FileNotFoundError as exc:
        raise GateStop(("extract", str(exc)))
    start, end = core.find_section_bounds(lines, md_line)
    if not (start <= md_line < end):
        raise GateStop(("extract", f"md_line {md_line} 不在章节边界 [{start},{end}) 内"))
    section = lib.section_text(book, start, end)
    if not section.strip():
        raise GateStop(("extract", "章节边界内文本为空"))
    hint = core.detect_method_cross_reference(section)
    if hint and "method_cross_reference" not in (view.get("flags") or []):
        raise GateStop(("extract", "边界内检测到前文引用但视图未标记，请重跑 build_generatable_view.py"))
    # 图例策略：有引用但缺 PDF/图 → STOP（不跳过、不占位）
    policy = view.get("figure_policy", "none")
    images = (draft.get("render") or {}).get("figure_images") or []
    if policy in ("use_extracted", "needs_ocr_verify") and not images:
        raise GateStop(("extract", f"figure_policy={policy} 但草稿未提供已提取图例"))
    if images and policy in ("none", "misattributed_treat_as_none"):
        raise GateStop(("extract", f"figure_policy={policy} 不应有图例图片（防误配图）"))
    return f"边界 [{start},{end})，{len(section)} 字" + (f"，前文引用→{hint}" if hint else "")


def gate_factlock(draft: dict, view: dict, lib: core.BookLibrary) -> str:
    fact = core.run_factlock(draft, lib)
    if fact["unclassified"] > 0:
        bad = [
            v for v in fact["violations"]
            if v["type"] in ("unadapted_fact_token", "textbook_token_not_in_evidence", "adapted_no_reason")
        ]
        raise GateStop(("factlock", f"未归类 token {fact['unclassified']}，如 {bad[:3]}"))
    return f"已核验 {fact['checked_blocks']} 块 / {fact['token_total']} token"


def gate_rewrite_review(draft: dict, draft_dir: Path) -> str:
    notes = draft.get("notes") or {}
    if not notes.get("human_rewrite_applied"):
        raise GateStop(
            ("rewrite_review", "缺 notes.human_rewrite_applied=true（human-writing 改写未执行或未标记）")
        )
    review_path = draft_dir / "review_trial_daily.json"
    if not review_path.exists():
        raise GateStop(("rewrite_review", f"缺内容评审记录 {review_path.name}"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    ok, errors = core.validate_review(review, draft)
    if not ok:
        raise GateStop(("rewrite_review", "；".join(errors[:3])))
    return "评审记录同版本且五项全过"


def gate_render_verify(workspace: Path) -> str:
    """进程内执行 fill（评分门+评审门+构建+格式验证+soffice 渲染检查+原子提交）。"""
    argv_backup = sys.argv
    code = 0
    try:
        sys.argv = ["fill_trial_daily_post.py", "--workspace", str(workspace)]
        try:
            runpy.run_path(str(FILL_SCRIPT), run_name="__main__")
        except SystemExit as exc:
            code = int(exc.code or 0)
    finally:
        sys.argv = argv_backup
    if code != 0:
        raise GateStop(("render_verify", f"fill 失败（exit={code}），问题稿不得生成正式成品"))
    return "fill 全门禁通过并已提交"


def gate_docx_commit(workspace: Path, draft_path: Path) -> str:
    template_path = workspace / "desktop-attachments" / "2 体育试讲每日一练-帖子内容编辑模板.docx"
    evidence = workspace / "desktop-attachments" / "rendered" / "render_check.pdf"
    if not template_path.exists():
        raise GateStop(("docx_commit", "成品 DOCX 不存在"))
    if template_path.stat().st_mtime < draft_path.stat().st_mtime:
        raise GateStop(("docx_commit", "成品 DOCX 早于草稿（提交顺序异常）"))
    if not evidence.exists():
        raise GateStop(("docx_commit", "渲染检查证据 render_check.pdf 缺失（渲染检查未执行）"))
    return f"DOCX mtime {time.strftime('%H:%M:%S', time.localtime(template_path.stat().st_mtime))}，渲染证据在档"


def gate_progress_commit(progress_path: Path, name: str) -> str:
    prog = json.loads(progress_path.read_text(encoding="utf-8"))
    if name in prog.get("done", []):
        return f"「{name}」已在 done，幂等跳过"
    raise GateStop((
        "progress_commit",
        f"「{name}」未在进度 done 中——新选题完成后由 agent 按 SKILL.md 步骤更新进度并回读校验；"
        "本工作流不做隐式写入",
    ))


# ---------------------------------------------------------------------------
# 编排入口
# ---------------------------------------------------------------------------


def run_workflow(draft_path: Path, ws: Path, workspace: Path,
                 dry_run: bool = False) -> int:
    try:
        import docx  # noqa: F401
    except ImportError:
        print("❌ 依赖预检失败：python-docx 不可导入")
        return 2
    if not acquire_lock(ws, timeout=5):
        print("❌ 未获得工作区锁（另一进程正在进行）")
        return 3
    progress_path = workspace / "scripts" / "progress_trial.json"
    tag = "[演练] " if dry_run else ""
    draft = {"id": "unknown"}
    try:
        lib = core.BookLibrary()
        view: dict = {}
        for state in STATES:
            if state == "select":
                draft = load_draft(draft_path)
                view = gate_select(draft)
                note = draft["id"]
            elif state == "extract":
                note = gate_extract(draft, view, lib)
            elif state == "factlock":
                note = gate_factlock(draft, view, lib)
            elif state == "rewrite_review":
                note = gate_rewrite_review(draft, draft_path.parent)
            elif state == "render_verify":
                if dry_run:
                    print(f"{tag}止步于 rewrite_review（dry-run 不构建成品）")
                    break
                note = gate_render_verify(workspace)
            elif state == "docx_commit":
                note = gate_docx_commit(workspace, draft_path)
            elif state == "progress_commit":
                note = gate_progress_commit(progress_path, view.get("activity_name", ""))
            else:  # upload_done
                note = "未启用上传，明确跳过（不冒充成功）"
            advance(ws, draft.get("id", "unknown"), f"{state}: {note}", to=state)
            print(f"{tag}→ {state}：{note}")
        print(f"{tag}工作流结束（状态见 {state_path(ws)}）")
        return 0
    except GateStop as exc:
        state, reason = exc.args[0]
        print(f"🔴 {tag}{state} 门禁未过：{reason}")
        try:
            advance(ws, draft.get("id", "unknown"), f"STOP@{state}: {reason}")
        except Exception:
            pass
        return 4
    finally:
        release_lock(ws)


def main() -> int:
    ap = argparse.ArgumentParser(description="PE-trial-daily 工作流编排（v3 真门禁）")
    ap.add_argument("--draft", type=Path, required=True, help="草稿 draft@3 路径")
    ap.add_argument("--ws", type=Path, default=Path("/tmp/ptd_wf_ws"), help="状态工作区")
    ap.add_argument("--workspace", type=Path,
                    default=Path("/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编"),
                    help="项目工作区（含 desktop-attachments 与 scripts/progress_trial.json）")
    ap.add_argument("--dry-run", action="store_true", help="只推进前四个门禁，不写正式文件")
    args = ap.parse_args()
    return run_workflow(args.draft, args.ws, args.workspace, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())

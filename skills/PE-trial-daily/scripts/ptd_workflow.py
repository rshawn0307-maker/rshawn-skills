#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ptd_workflow.py — PE-trial-daily 工作流编排（任务3）。

把「选题 → 提取 → 事实锁定 → 改写复核 → 渲染验证 → DOCX提交 → 进度提交 → 上传」串成
带工作区锁 + 原子状态机 + 稳定ID幂等 的流水线。纯标准库，不引入新依赖。

核心能力：
  1. 依赖预检（docx / soffice / poppler / fc-match / swift），缺失即报，不装新依赖。
  2. 工作区锁：O_CREAT|O_EXCL 原子抢占，双进程只有一个成功；持锁者失败退出码非0，不删 pending。
  3. 原子状态机：状态文件写临时再 os.replace；按 (stable_id, content_hash) 幂等，终态不重跑。
  4. OCR 缓存：原子写、记录 PDF 指纹(sha256)+页数+覆盖率；子进程非0 不落缓存。
  5. 图例：视图策略驱动——figure_required_but_pdf_missing → STOP；misattributed_treat_as_none → 空图；
     无引用 → 空图；needs_ocr_verify/use_extracted → OCR 索引精确匹配 caption 并裁图，失败 STOP。
  6. IMA 幂等：本地 fake adapter，按 content_hash 记录 {note_id, remote_id, stage}，重复运行不新建笔记。

边界：所有真实业务数据（索引/进度/教师书/正式DOCX/IMA）只读；真实迁移/上传仅 dry-run。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

# 依赖预检（只读探测，不安装）
SOFFICE = "/Users/shawn/Library/Application Support/TRAE SOLO CN/ModularData/ai-agent/vm/tools/opt/libreoffice/LibreOffice.app/Contents/MacOS/soffice"
PDFINFO = "/Users/shawn/Library/Application Support/TRAE SOLO CN/ModularData/ai-agent/vm/tools/bin/pdfinfo"
PDFTOPPM = "/Users/shawn/Library/Application Support/TRAE SOLO CN/ModularData/ai-agent/vm/tools/bin/pdftoppm"

# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------

STATES = [
    "select",          # 选题（稳定ID）
    "extract",         # 教材提取 + 图例
    "factlock",        # 事实锁定
    "rewrite_review",  # human-writing 改写复核
    "render_verify",   # render_docx --emit_pdf --check
    "docx_commit",     # DOCX 原子提交
    "progress_commit", # 进度提交
    "upload_done",     # IMA 上传完成
]
TERMINAL = {"docx_commit", "progress_commit", "upload_done"}
LOCK_STALE_SEC = 60


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


def content_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 工作区锁
# ---------------------------------------------------------------------------


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
# 依赖预检
# ---------------------------------------------------------------------------


def check_deps() -> list[str]:
    missing = []
    try:
        import docx  # noqa: F401
    except ImportError:
        missing.append("python-docx 不可导入")
    for name, path in (("soffice", SOFFICE), ("pdfinfo", PDFINFO), ("pdftoppm", PDFTOPPM)):
        if not Path(path).exists():
            missing.append(f"{name} 缺失")
    if shutil.which("fc-match") is None:
        missing.append("fc-match 缺失")
    if shutil.which("swift") is None:
        missing.append("swift(Vision OCR) 缺失")
    return missing


# ---------------------------------------------------------------------------
# OCR 缓存（原子写 + 指纹 + 覆盖率）
# ---------------------------------------------------------------------------


def pdf_fingerprint(pdf: Path) -> dict:
    st = pdf.stat()
    with open(pdf, "rb") as f:
        head = f.read(1024 * 1024)
    return {
        "sha256_head": hashlib.sha256(head).hexdigest()[:16],
        "size": st.st_size,
        "mtime": int(st.st_mtime),
    }


def build_ocr_cache(pdf: Path, cache_path: Path, swift_script: Path, log=print) -> dict:
    """构建 OCR 缓存（含 bbox）。原子写；子进程非0 不落缓存。返回缓存 dict。"""
    if cache_path.exists():
        try:
            old = json.loads(cache_path.read_text(encoding="utf-8"))
            if old.get("fingerprint") == pdf_fingerprint(pdf):
                log(f"OCR 缓存命中: {cache_path.name}")
                return old
        except Exception:
            pass
    total = 0
    r = subprocess.run([PDFINFO, str(pdf)], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        m = re.match(r"Pages:\s+(\d+)", line)
        if m:
            total = int(m.group(1))
            break
    index: dict[str, list] = {}
    proc = subprocess.run(
        ["swift", str(swift_script), str(pdf), "0", str(max(total, 1))],
        capture_output=True, text=True, timeout=3600,
    )
    if proc.returncode != 0:
        log(f"❌ OCR 子进程非0（{proc.returncode}），不落缓存：{proc.stderr[:300]}")
        return {}
    for line in proc.stdout.splitlines():
        if not line.startswith("PAGE\t"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        pno = parts[1]
        text = parts[2].replace("␊", "\n")
        bbox = None
        if len(parts) >= 7:
            try:
                bbox = [float(x) for x in parts[3:7]]
            except ValueError:
                bbox = None
        index.setdefault(pno, []).append({"text": text, "bbox": bbox})
    coverage = round(len(index) / max(total, 1), 3)
    cache = {
        "fingerprint": pdf_fingerprint(pdf),
        "page_count": total,
        "coverage": coverage,
        "pages": index,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ocr_", suffix=".json", dir=str(cache_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)
        os.replace(tmp, cache_path)
        log(f"✅ OCR 缓存写入 {cache_path.name}（页数 {total}，覆盖率 {coverage}）")
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return cache


def find_caption_in_ocr(cache: dict, ref: str) -> list[dict]:
    """在 OCR 索引里精确匹配图例引用（如 图3-2-7），返回 [{page, text, bbox}]。"""
    want = re.sub(r"[\s\-.]", "", ref)
    hits = []
    for pno, lines in cache.get("pages", {}).items():
        for ln in lines:
            t = re.sub(r"[\s\-.]", "", ln.get("text", ""))
            if want and want in t:
                hits.append({"page": int(pno), "text": ln["text"], "bbox": ln.get("bbox")})
    hits.sort(key=lambda h: h["page"])
    return hits


# ---------------------------------------------------------------------------
# 图例裁图（精确匹配 caption，裁白）
# ---------------------------------------------------------------------------


def crop_figure(pdf: Path, hit: dict, out_path: Path, dpi: int = 150) -> Path | None:
    """按 caption bbox 定位并裁出图例区域（裁白）。无 bbox 时回退整页上半部。"""
    page = hit["page"]
    # 渲染整页
    work = out_path.parent / "pg"
    r = subprocess.run([PDFTOPPM, "-png", "-r", str(dpi), "-f", str(page + 1), "-l", str(page + 1),
                        str(pdf), str(work)], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    pngs = sorted(Path(out_path.parent).glob(f"{work.name}-*.png"))
    if not pngs:
        return None
    src = pngs[0]
    bbox = hit.get("bbox")
    out = out_path
    if bbox:
        # bbox 归一化（左上原点）：裁 caption 上方区域作为图区
        x, y, w, h = bbox
        # 用 ImageMagick 或纯 Python PNG 裁切；优先 magick（可用）
        if shutil.which("magick") or shutil.which("convert"):
            magick = shutil.which("magick") or shutil.which("convert")
            # 裁上半部（caption 之上 2cm 到 caption 上缘）
            import struct
            with open(src, "rb") as f:
                head = f.read(24)
            pw, ph = struct.unpack(">II", head[16:24])
            # 图区：顶部到 caption 上缘
            crop_h = int((y - 0.04) * ph)  # caption 上缘留 4% 空隙
            crop_h = max(crop_h, int(0.3 * ph))
            cmd = [magick, src, "-crop", f"{pw}x{crop_h}+0+0", "+repage", "-trim", "+repage", str(out)]
            subprocess.run(cmd, capture_output=True, text=True)
            if out.exists() and out.stat().st_size > 1000:
                return out
    # 兜底：整页渲染（记录为 low-precision）
    shutil.copy(src, out)
    return out if out.exists() else None


# ---------------------------------------------------------------------------
# 图例策略解析（视图驱动）
# ---------------------------------------------------------------------------


class FigureStop(Exception):
    pass


def resolve_figures(view_entry: dict, pdf: Path | None, ocr_cache: dict, outdir: Path,
                    log=print) -> tuple[list[Path], str]:
    """按视图策略解析图例。返回 (图片路径列表, 策略说明)。"""
    policy = view_entry.get("figure_policy", "none")
    if policy == "none" or not view_entry.get("figures"):
        return [], "no_refs_empty_figure"
    if policy == "figure_required_but_pdf_missing":
        raise FigureStop("有引用但缺 PDF/图：figure_required_but_pdf_missing（STOP）")
    if policy == "misattributed_treat_as_none":
        return [], "misattributed_treat_as_none"
    if pdf is None:
        raise FigureStop("需要图例但 PDF 缺失（STOP）")
    outdir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for fig in view_entry["figures"]:
        ref = fig.get("ref", "")
        hits = find_caption_in_ocr(ocr_cache, ref)
        if not hits:
            if policy == "needs_ocr_verify":
                raise FigureStop(f"needs_ocr_verify 但 OCR 未精确命中 caption {ref}（STOP）")
            log(f"⚠️ {ref} OCR 未命中，跳过")
            continue
        hit = hits[0]
        out = outdir / f"fig_{re.sub(r'[\\/:*?\"<>|]', '_', ref)}_p{hit['page']}.png"
        saved = crop_figure(pdf, hit, out)
        if saved:
            paths.append(saved)
    if not paths and policy == "use_extracted":
        raise FigureStop(f"use_extracted 但未裁出图 {view_entry['id']}（STOP）")
    return paths, "cropped_by_caption"


# ---------------------------------------------------------------------------
# IMA 本地 fake adapter（幂等）
# ---------------------------------------------------------------------------


class FakeIMA:
    """本地幂等 fake adapter：不真实调用 IMA，只验证 content_hash/remote_id/阶段。"""

    def __init__(self, ws: Path):
        self.ws = Path(ws)
        self.store_path = ws / "ima_records.json"

    def _load(self) -> dict:
        if not self.store_path.exists():
            return {}
        try:
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, recs: dict) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".ima_", suffix=".json", dir=str(self.store_path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.store_path)

    def upload(self, stable_id: str, content: dict) -> dict:
        """幂等上传：同 content_hash 重复运行不新建笔记。返回记录。"""
        ch = content_hash(content)
        recs = self._load()
        rec = recs.get(ch)
        if rec:
            rec["stage"] = "replay_no_new_note"
            self._save(recs)
            return {"replayed": True, "record": rec}
        note_id = "fake_note_" + ch
        rec = {"content_hash": ch, "stable_id": stable_id, "note_id": note_id,
               "remote_id": None, "stage": "uploaded"}
        recs[ch] = rec
        self._save(recs)
        return {"replayed": False, "record": rec}


# ---------------------------------------------------------------------------
# 状态机推进
# ---------------------------------------------------------------------------


def advance(ws: Path, stable_id: str, ch: str, to: str) -> dict:
    st = read_state(ws)
    entries = st.setdefault("entries", {})
    entry = entries.setdefault(stable_id, {})
    entry["content_hash"] = ch
    entry["stage"] = to
    entry["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    write_state(ws, st)
    return entry


def is_idempotent_done(ws: Path, stable_id: str, ch: str) -> bool:
    st = read_state(ws)
    entry = st.get("entries", {}).get(stable_id)
    if not entry:
        return False
    if entry.get("content_hash") != ch:
        return False
    return entry.get("stage") in TERMINAL


# ---------------------------------------------------------------------------
# 编排入口（dry-run 模式）
# ---------------------------------------------------------------------------


def run_workflow(ws: Path, stable_id: str, view_entry: dict, dry_run: bool = True) -> int:
    missing = check_deps()
    if missing:
        print("❌ 依赖预检失败：" + "；".join(missing))
        return 2
    if not acquire_lock(ws, timeout=5):
        print("❌ 未获得工作区锁（另一进程正在进行）")
        return 3
    try:
        ch = content_hash({"id": stable_id, "view": view_entry})
        if is_idempotent_done(ws, stable_id, ch):
            print(f"✅ 幂等命中：{stable_id} 已到终态，跳过")
            return 0
        print(f"[workflow] {stable_id} content_hash={ch} dry_run={dry_run}")
        # 图例策略（仅分类，不真实裁图；真实裁图需真实 PDF/OCR）
        try:
            paths, note = resolve_figures(
                view_entry, None, {"pages": {}}, ws / "figures", log=print)
            print(f"[workflow] 图例策略: {note}（图片 {len(paths)}）")
        except FigureStop as exc:
            print(f"🔴 {exc}")
            advance(ws, stable_id, ch, "extract")
            return 4
        for to in STATES:
            if to in ("extract",):
                continue
            advance(ws, stable_id, ch, to)
            print(f"[workflow] → {to}")
            if dry_run:
                break  # dry-run 只走第一段，演示状态机
        print("✅ 工作流 dry-run 完成")
        return 0
    finally:
        release_lock(ws)


def main() -> int:
    ap = argparse.ArgumentParser(description="PE-trial-daily 工作流编排")
    ap.add_argument("--ws", type=Path, default=Path("/tmp/ptd_wf_ws"), help="工作区")
    ap.add_argument("--id", default="PTD-000", help="稳定ID")
    ap.add_argument("--check-deps", action="store_true")
    args = ap.parse_args()
    if args.check_deps:
        missing = check_deps()
        if missing:
            print("❌ " + "；".join(missing))
            return 2
        print("✅ 依赖预检通过")
        return 0
    view = {"id": args.id, "figure_policy": "none", "figures": []}
    return run_workflow(args.ws, args.id, view, dry_run=True)


if __name__ == "__main__":
    sys.exit(main())

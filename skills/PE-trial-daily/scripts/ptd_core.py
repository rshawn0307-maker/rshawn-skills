#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PE-trial-daily 核心库（v3）。

纯标准库实现，不依赖 python-docx，可被测试与渲染层共同引用。
在 v2（稳定ID/可生成视图/factlock/100分量表）基础上新增：
  A. 误收选题拦截（课外作业建议等非教学活动 → 视图层 blocker，选题即停）
  B. 章节边界识别（section_start/end_line，提取时只读本活动，避免读到下一个活动）
  C. 前文引用检测（"动作方法同××" → 视图 flag，草稿必须补被引用段落证据）
  D. 时长口径统一（口播字数时间 + 明确登记的示范/停顿秒数；页面标注须与合计一致）
  E. 新硬门：题文错配 / 近重复凑时长 / 断裂标点 / 引用证据缺失 / 安全不可执行 /
     教学加工无理由（adapted_facts 必须伴随 adapted_note）
  F. 冻结阈值不变：总分≥85、教材≥27、安全≥16、硬门0

设计原则：对 activity_index.json、progress_trial.json、教师用书 MD/PDF 一律只读。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径与配置
# ---------------------------------------------------------------------------

SKILL_DIR = Path(__file__).resolve().parent.parent
BOOKS_DIR_DEFAULT = Path(
    "/Users/shawn/Desktop/AI工作区/03-Resources/各版本体育教材/人教版"
)
INDEX_DEFAULT = Path(
    "/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编/scripts/activity_index.json"
)
PROGRESS_DEFAULT = Path(
    "/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编/scripts/progress_trial.json"
)

SCHEMA_DRAFT = "pe-trial-daily/draft@3"
SCHEMA_VIEW = "pe-trial-daily/generatable-view@3"
SCHEMA_REVIEW = "pe-trial-daily/review@1"


def load_config(path: Path | None = None) -> dict:
    """加载配置；默认读技能内 config.default.json，允许覆盖。"""
    default = json.loads((SKILL_DIR / "config.default.json").read_text(encoding="utf-8"))
    if path and Path(path).exists():
        override = json.loads(Path(path).read_text(encoding="utf-8"))
        default.update(override)
    return default


# ---------------------------------------------------------------------------
# 稳定 ID 与记录指纹
# ---------------------------------------------------------------------------


def stable_id(seq: int, sport: str, name: str) -> str:
    return f"PTD-{seq:03d}-{sport}-{name}"


def record_sha(record: dict) -> str:
    payload = "|".join(
        str(record.get(k, ""))
        for k in ("sport", "activity_name", "activity_type", "book_file", "md_line", "difficulty")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 教师用书只读访问
# ---------------------------------------------------------------------------


class BookLibrary:
    """按行缓存教师用书 MD（只读）。"""

    def __init__(self, books_dir: Path = BOOKS_DIR_DEFAULT):
        self.books_dir = Path(books_dir)
        self._lines: dict[str, list[str]] = {}

    def lines(self, book_file: str) -> list[str]:
        if book_file not in self._lines:
            p = self.books_dir / book_file
            if not p.exists():
                raise FileNotFoundError(f"教师用书不存在：{p}")
            self._lines[book_file] = p.read_text(encoding="utf-8").splitlines()
        return self._lines[book_file]

    def line_text(self, book_file: str, line0: int) -> str:
        ls = self.lines(book_file)
        return ls[line0].strip() if 0 <= line0 < len(ls) else ""

    def pdf_for(self, book_file: str) -> Path | None:
        stem = Path(book_file).stem
        pdf = self.books_dir / f"{stem}.pdf"
        return pdf if pdf.exists() else None

    def excerpt_at(self, book_file: str, line0: int, excerpt: str) -> bool:
        """校验 excerpt 确实出现在 book 的 line0 行（容许空白差异）。

        行号必须真正可核验，因此以下情况一律判否，不得放行：
        - 行号越界或为负；
        - 目标行为空行（旧实现里 norm("") 会被任意字符串包含，导致错误行号静默通过）；
        - excerpt 为空。
        反向包含（目标行内容被 excerpt 包含，用于 MD 折行导致行内文本偏短的情况）
        额外要求目标行归一化后不短于 4 字，避免 ">" 之类的 Markdown 标记行冒充证据。
        """
        if line0 < 0:
            return False
        lines = self.lines(book_file)
        if line0 >= len(lines):
            return False
        norm = lambda s: re.sub(r"\s+", "", s)
        actual = norm(lines[line0])
        want = norm(excerpt)
        if not actual or not want:
            return False
        if want in actual:
            return True
        return len(actual) >= 4 and actual in want

    def section_text(self, book_file: str, start: int, end: int) -> str:
        """取 [start, end) 行的原文（章节边界内提取用）。"""
        ls = self.lines(book_file)
        start = max(0, start)
        end = min(len(ls), end)
        return "\n".join(ls[start:end])


# ---------------------------------------------------------------------------
# 章节边界与误收选题（v3）
# ---------------------------------------------------------------------------

# 非教学活动的误收选题：索引把它们收成 practice，但它们不是可试讲的教学环节
MISCOLLECTED_TOPIC_RE = re.compile(
    r"课外作业|作业建议|课后作业|课外练习|课后练习|课外活动建议"
)

# 活动标题行（归一化后）：`2. 半米字移动` / `3. 抢背后滚球` / `(3)趣味单双数追逐赛(★★★)`
SECTION_HEADING_RE = re.compile(r"^(?:\d+\s*[\.、]|[（(]\s*\d+\s*[)）])")
# 小节标题行：`(一)基础性练习与游戏` / `( 二 )易犯错误与纠正方法`
SUBSECTION_HEADING_RE = re.compile(r"^[（(]\s*[一二三四五六七八九十]+\s*[)）]")


def _norm_heading_line(ln: str) -> str:
    s = ln.strip()
    s = re.sub(r"^[\s>#]+", "", s)
    s = s.replace("**", "").replace("*", "")
    return s.strip()


def is_heading_line(ln: str) -> bool:
    s = _norm_heading_line(ln)
    if not s or len(s) > 50 or "【" in s or "。" in s:
        return False  # 标题行短、不含正文标记；正文/表格续行不误判
    return bool(SECTION_HEADING_RE.match(s) or SUBSECTION_HEADING_RE.match(s))


def find_section_bounds(lines: list[str], md_line: int) -> tuple[int, int]:
    """识别活动章节边界 [start, end)。

    start：从 md_line 向上找到最近的活动标题行（含）；找不到则取 0。
    end：从 start+1 向下找到下一个标题行（不含）；找不到则取文件尾。
    提取只允许读取边界内文本；越界读到的"下一个活动"内容不得进入成品。
    """
    n = len(lines)
    start = 0
    for i in range(min(md_line, n - 1), -1, -1):
        if is_heading_line(lines[i]):
            start = i
            break
    end = n
    for j in range(start + 1, n):
        if is_heading_line(lines[j]):
            end = j
            break
    return start, end


def detect_method_cross_reference(section_text: str) -> str | None:
    """检测"动作方法引用前文"（如 平击球：与正(反)手平击发球动作相同）。

    返回被引用对象提示（尽力提取），无引用返回 None。
    """
    t = re.sub(r"[\s>*#]", "", section_text)
    m = re.search(r"与(.{2,16}?)(?:动作|方法)?相同", t)
    if m:
        return m.group(1)
    if re.search(r"动作相同|方法相同|同上|动作同", t):
        return "前文动作"
    return None


# ---------------------------------------------------------------------------
# 图例归属复核（误收检测）
# ---------------------------------------------------------------------------

FIG_REF_RE = re.compile(r"图\s*-?\s*(\d)\s*-\s*(\d)\s*-\s*(\d+[A-Za-z]?)\s*(.*)")


def normalize_fig_ref(ref: str) -> str:
    m = re.match(r"图\s*-?\s*(\d)\s*-\s*(\d)\s*-\s*(\d+[A-Za-z]?)", ref)
    return f"图{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ref.strip()


def _is_caption_line(ln: str) -> "re.Match | None":
    """图注行：剥掉引用符号/加粗/空白后以 图x-x-x 开头（行内括号引用不算）。"""
    cleaned = re.sub(r"^[\s>*]+", "", ln)
    return FIG_REF_RE.match(cleaned)


def find_caption(lines: list[str], ref: str) -> tuple[int, str] | None:
    """在书中定位图注行，返回 (行号0based, 图注描述)。只认行首图注，不认行内引用。"""
    m0 = re.match(r"图\s*-?\s*(\d)\s*-\s*(\d)\s*-\s*(\d+[A-Za-z]?)", ref)
    want_key = (m0.group(1), m0.group(2), m0.group(3)) if m0 else None
    for i, ln in enumerate(lines):
        m = _is_caption_line(ln)
        if not m:
            continue
        key = (m.group(1), m.group(2), m.group(3))
        if want_key and key != want_key:
            continue
        desc = m.group(4).strip().strip("*").strip()
        return i, desc
    return None


def caption_matches_activity(desc: str, activity_name: str) -> bool:
    """图注描述与活动名是否相符（共享>=2个汉字或互为包含）。"""
    dn = re.sub(r"[^\u4e00-\u9fff]", "", desc)
    an = re.sub(r"[^\u4e00-\u9fff]", "", activity_name)
    if not dn or not an:
        return not dn and not an
    if dn in an or an in dn:
        return True
    common = set(dn) & set(an)
    return len(common) >= 2


# ---------------------------------------------------------------------------
# 可生成视图
# ---------------------------------------------------------------------------


@dataclass
class ViewRecord:
    id: str
    seq: int
    record_sha: str
    sport: str
    activity_name: str
    activity_type: str
    book_file: str
    md_line: int
    index_difficulty: str
    difficulty_policy: str
    index_has_errors: bool = False
    figures: list = field(default_factory=list)
    figure_policy: str = "none"
    book_pdf_available: bool = True
    flags: list = field(default_factory=list)
    generatable: bool = True
    generatable_blockers: list = field(default_factory=list)
    section_start_line: int = 0
    section_end_line: int = 0
    method_cross_reference: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "seq": self.seq,
            "record_sha": self.record_sha,
            "sport": self.sport,
            "activity_name": self.activity_name,
            "activity_type": self.activity_type,
            "book_file": self.book_file,
            "md_line": self.md_line,
            "index_difficulty": self.index_difficulty,
            "index_has_errors": self.index_has_errors,
            "difficulty_policy": self.difficulty_policy,
            "figures": self.figures,
            "figure_policy": self.figure_policy,
            "book_pdf_available": self.book_pdf_available,
            "flags": self.flags,
            "generatable": self.generatable,
            "generatable_blockers": self.generatable_blockers,
            "section_start_line": self.section_start_line,
            "section_end_line": self.section_end_line,
            "method_cross_reference": self.method_cross_reference,
        }


def build_view_record(record: dict, seq: int, lib: BookLibrary) -> ViewRecord:
    sport = record["sport"]
    name = record["activity_name"]
    atype = record["activity_type"]
    book = record["book_file"]
    md_line = int(record["md_line"])
    rid = stable_id(seq, sport, name)

    flags: list[str] = []
    blockers: list[str] = []

    # ---- v3：误收选题拦截（派生视图标记并阻止，原索引只读保留） ----
    if MISCOLLECTED_TOPIC_RE.search(name):
        flags.append("miscollected_topic")
        blockers.append("miscollected_topic_not_teaching_activity")

    # ---- 难度策略：索引为空绝不编星 ----
    diff = (record.get("difficulty") or "").strip()
    difficulty_policy = "index_stars" if diff else "adapted_label"
    if not diff:
        flags.append("difficulty_missing")

    # ---- 图例归属复核 ----
    figures: list[dict] = []
    fig_policy = "none"
    refs = record.get("figure_refs") or []
    try:
        lines = lib.lines(book)
    except FileNotFoundError:
        lines = []
        flags.append("book_md_missing")
        blockers.append("book_md_missing")

    for ref in refs:
        cap = find_caption(lines, ref) if lines else None
        if cap is None:
            figures.append(
                {"ref": normalize_fig_ref(ref), "status": "caption_not_found", "match": "unknown"}
            )
            flags.append("figure_caption_not_found")
            continue
        cap_line, desc = cap
        ok = caption_matches_activity(desc, name)
        figures.append(
            {
                "ref": normalize_fig_ref(ref),
                "caption": desc,
                "caption_line": cap_line,
                "match": "ok" if ok else "suspect",
                "status": "attributed" if ok else "misattribution_suspect",
            }
        )
        if not ok:
            flags.append("figure_misattribution_suspect")

    pdf = lib.pdf_for(book)
    book_pdf_available = pdf is not None
    if not book_pdf_available:
        flags.append("book_pdf_missing")
    if refs:
        ok_refs = [f for f in figures if f.get("match") == "ok"]
        nf_refs = [f for f in figures if f.get("status") == "caption_not_found"]
        if ok_refs:
            if book_pdf_available:
                fig_policy = "use_extracted"
            else:
                fig_policy = "figure_required_but_pdf_missing"
                blockers.append("figure_required_but_pdf_missing")
        elif nf_refs:
            if book_pdf_available:
                fig_policy = "needs_ocr_verify"
                flags.append("figure_needs_ocr_verify")
            else:
                fig_policy = "figure_required_but_pdf_missing"
                blockers.append("figure_required_but_pdf_missing")
        else:
            fig_policy = "misattributed_treat_as_none"

    # ---- v3：章节边界 + 前文引用检测 ----
    section_start, section_end = 0, len(lines) if lines else 0
    cross_ref = None
    if lines:
        section_start, section_end = find_section_bounds(lines, md_line)
        section_text = lib.section_text(book, section_start, section_end)
        cross_ref = detect_method_cross_reference(section_text)
        if cross_ref:
            flags.append("method_cross_reference")

    vr = ViewRecord(
        id=rid,
        seq=seq,
        record_sha=record_sha(record),
        sport=sport,
        activity_name=name,
        activity_type=atype,
        book_file=book,
        md_line=md_line,
        index_difficulty=diff,
        index_has_errors=bool(record.get("has_errors")),
        difficulty_policy=difficulty_policy,
        figures=figures,
        figure_policy=fig_policy,
        book_pdf_available=book_pdf_available,
        flags=flags,
        generatable=not blockers,
        generatable_blockers=blockers,
        section_start_line=section_start,
        section_end_line=section_end,
        method_cross_reference=cross_ref,
    )
    return vr


def build_generatable_view(
    index_path: Path = INDEX_DEFAULT,
    books_dir: Path = BOOKS_DIR_DEFAULT,
    progress_path: Path = PROGRESS_DEFAULT,
) -> dict:
    lib = BookLibrary(books_dir)
    records = json.loads(Path(index_path).read_text(encoding="utf-8"))
    entries = [build_view_record(r, i, lib).to_dict() for i, r in enumerate(records)]

    done_names = []
    if Path(progress_path).exists():
        prog = json.loads(Path(progress_path).read_text(encoding="utf-8"))
        for e in prog.get("done", []):
            if isinstance(e, str):
                done_names.append(e)
            elif isinstance(e, dict):
                done_names.append(e.get("activity_name") or e.get("name") or "")

    view = {
        "schema": SCHEMA_VIEW,
        "generated_from": {
            "index": str(Path(index_path)),
            "progress": str(Path(progress_path)),
            "books_dir": str(Path(books_dir)),
        },
        "stats": {},
        "entries": entries,
        "migration_dryrun": build_migration_dryrun(done_names, entries),
    }
    st = {
        "total": len(entries),
        "generatable": sum(1 for e in entries if e["generatable"]),
        "difficulty_missing": sum(1 for e in entries if "difficulty_missing" in e["flags"]),
        "miscollected_topic": sum(1 for e in entries if "miscollected_topic" in e["flags"]),
        "method_cross_reference": sum(
            1 for e in entries if "method_cross_reference" in e["flags"]
        ),
        "figure_misattribution_suspect": sum(
            1 for e in entries if "figure_misattribution_suspect" in e["flags"]
        ),
        "figure_caption_not_found": sum(
            1 for e in entries if "figure_caption_not_found" in e["flags"]
        ),
        "book_pdf_missing": sum(1 for e in entries if "book_pdf_missing" in e["flags"]),
        "blockers": sum(1 for e in entries if e["generatable_blockers"]),
    }
    view["stats"] = st
    return view


def build_migration_dryrun(done_names: list[str], entries: list[dict]) -> dict:
    """旧进度 -> 新视图 的 dry-run 迁移表。孤儿只分类留证，绝不丢。"""
    by_name = {e["activity_name"]: e for e in entries}
    rows = []
    for name in done_names:
        e = by_name.get(name)
        if e:
            blocked = bool(e["generatable_blockers"])
            rows.append(
                {
                    "progress_name": name,
                    "view_id": e["id"],
                    "disposition": "migrate",
                    "note": "按活动名唯一匹配到视图记录"
                    + ("（注意：该记录在 v3 视图中带 blocker，历史成品需复核）" if blocked else ""),
                }
            )
        else:
            rows.append(
                {
                    "progress_name": name,
                    "view_id": None,
                    "disposition": "orphan_keep_classified",
                    "note": "活动名不在 313 条索引内，归类为孤儿进度，保留证据，不删除",
                    "evidence": "activity_index 全量名称匹配失败",
                }
            )
    return {
        "mode": "dry-run",
        "warning": "仅演练，不写回 progress_trial.json；真实迁移需人工裁决",
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# 事实锁定 factlock
# ---------------------------------------------------------------------------

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
CJK_NUM_UNIT_RE = re.compile(r"[一二三四五六七八九十百两]+\s*(?:米|个|次|组|秒|分|人|台|步|臂|张|轮|圈|面)")
DIRECTION_LEXICON = [
    "左外侧", "右外侧", "同侧", "对侧", "异侧", "外侧", "内侧", "左侧", "右侧", "上方", "下方",
    "前方", "后方", "中间", "胸前", "腹前", "身前", "左", "右", "前", "后", "反向",
    "倒退", "背对", "转身", "逆时针", "顺时针",
]
EQUIPMENT_LEXICON = [
    "篮球", "排球", "足球", "乒乓球", "羽毛球", "网球", "球拍", "球台", "球网", "栏架",
    "标志筒", "标志桶", "标志盘", "纸牌", "纸条", "体操垫", "垫子", "跳绳", "篮筐",
    "秒表", "口哨", "球篮", "栏板", "横箱", "山羊", "单杠", "双杠",
]
SAFETY_LEXICON = [
    "安全", "平坦", "间隔", "距离", "保护", "帮助", "碰撞", "摔倒", "滑倒",
    "踩", "热身", "准备活动", "放松", "整理", "慢速", "逐步", "循序渐进",
    "负荷", "休息", "检查", "密度", "场地", "推搡",
]
TECHNIQUE_LEXICON = [
    "运球", "按拍", "触球", "滑步", "俯卧撑", "原地跳", "引拍", "随挥", "还原",
    "准备姿势", "击球", "落点", "反弹", "迎球", "缓冲", "握拍", "攻球", "发球",
    "冲刺", "变向", "跨越", "高抬腿", "抱球", "传球", "抛球", "移动", "屈伸",
    "前倾", "微屈", "按拍球", "推击", "下旋", "上旋", "抽球", "挡球",
    "起跑", "追逐", "报数", "蹲踞", "触摸", "滚动",
]
SAFETY_CATEGORIES = {
    "场地": ["场地", "平坦", "检查"],
    "器材": ["器材", "栏架", "球台", "标志", "网球"],
    "间距": ["间隔", "距离", "间距", "一臂"],
    "保护": ["保护", "帮助", "分层", "推搡"],
    "负荷": ["负荷", "休息", "放松", "强度", "密度"],
}
# 安全安排必须是能执行的口令：出现检查/听信号/停止/路线类可执行动词
SAFETY_EXECUTABLE_RE = re.compile(
    r"检查|间隔|距离|一臂|听到|听口令|口令|哨音|立即停止|停止练习|马上停止|停下|"
    r"退回|回到|举手|报告|不推|别推|不互相|慢跑|走回"
)


def extract_fact_tokens(text: str) -> list[dict]:
    """抽取事实 token：数字（含中文数字+单位）、方向、器材、安全、技术词。"""
    tokens: list[dict] = []
    spans: list[tuple[int, int]] = []

    def add(span: tuple[int, int], token: str, category: str):
        if any(s <= span[0] < e for s, e in spans):
            return
        tokens.append({"token": token, "category": category, "span": span})
        spans.append(span)

    for m in CJK_NUM_UNIT_RE.finditer(text):
        add(m.span(), m.group(0), "number")
    for m in NUMBER_RE.finditer(text):
        add(m.span(), m.group(0), "number")
    for lex, cat in (
        (DIRECTION_LEXICON, "direction"),
        (EQUIPMENT_LEXICON, "equipment"),
        (SAFETY_LEXICON, "safety"),
        (TECHNIQUE_LEXICON, "technique"),
    ):
        for term in lex:
            start = 0
            while True:
                i = text.find(term, start)
                if i < 0:
                    break
                add((i, i + len(term)), term, cat)
                start = i + len(term)
    tokens.sort(key=lambda t: t["span"][0])
    return tokens


def _evidence_text(block: dict) -> str:
    parts = [ev.get("excerpt", "") for ev in block.get("evidence") or []]
    return " ".join(parts)


def iter_blocks(draft: dict):
    """遍历草稿中所有内容块。"""
    for st in draft.get("flow") or []:
        yield f"flow[{st.get('stage')}]", st
    for key in ("method", "rules", "intent", "organization"):
        blk = draft.get("fields", {}).get(key)
        if blk:
            yield f"fields.{key}", blk
    err_rows = (draft.get("fields", {}).get("errors") or {}).get("rows") or []
    for i, row in enumerate(err_rows):
        for side in ("error", "fix"):
            if row.get(side):
                yield f"fields.errors[{i}].{side}", row[side]
    for fig in draft.get("figures") or []:
        if fig.get("caption"):
            yield f"figures[{fig.get('ref')}].caption", {
                "text": fig["caption"],
                "provenance": fig.get("provenance", "textbook"),
                "evidence": fig.get("evidence") or [],
            }


def _block_text(block: dict) -> str:
    """块的受检文本：字段正文 text 与口语稿 script 都必须过事实锁定。"""
    t = block.get("text", "")
    s = block.get("script", "")
    return f"{t} {s}".strip() if t and s else (t or s)


def run_factlock(draft: dict, lib: BookLibrary | None = None) -> dict:
    """事实锁定复核。返回 {unclassified, violations[], checked_blocks, token_total}。

    规则（v3）：
      - provenance=textbook 的块必须有 evidence(book_file+line+excerpt)，
        且块内全部事实 token 都能在 excerpt 并集中找到；
      - provenance=adapted/generic 的块中，未被任何证据覆盖的事实 token
        必须显式登记在该块 adapted_facts，且块必须带非空 adapted_note 说明
        加工理由（"教学建议有理由"是可执行检查，不再允许无理由批量登记）；
      - unclassified 必须为 0 才放行（硬门）。
    """
    lib = lib or BookLibrary()
    all_evidence_text = " ".join(_evidence_text(b) for _, b in iter_blocks(draft))
    violations: list[dict] = []
    token_total = 0
    blocks = 0

    for where, block in iter_blocks(draft):
        blocks += 1
        text = _block_text(block)
        prov = block.get("provenance", "generic")
        ev_text = _evidence_text(block)
        if prov == "textbook":
            evs = block.get("evidence") or []
            if not evs or any(
                not ev.get("book_file") or ev.get("line") is None or not ev.get("excerpt")
                for ev in evs
            ):
                violations.append(
                    {"where": where, "type": "textbook_no_evidence", "token": None}
                )
            for ev in evs:
                if lib and ev.get("book_file") and ev.get("line") is not None:
                    try:
                        if not lib.excerpt_at(ev["book_file"], int(ev["line"]), ev.get("excerpt", "")):
                            violations.append(
                                {"where": where, "type": "evidence_line_mismatch", "token": ev.get("excerpt", "")[:20]}
                            )
                    except FileNotFoundError:
                        violations.append(
                            {"where": where, "type": "evidence_book_missing", "token": ev.get("book_file")}
                        )
        else:
            # v3：登记了 adapted_facts 就必须给出加工理由
            if block.get("adapted_facts") and not (block.get("adapted_note") or "").strip():
                violations.append(
                    {"where": where, "type": "adapted_no_reason", "token": None}
                )
        for tok in extract_fact_tokens(text):
            token_total += 1
            token = tok["token"]
            if token in ev_text:
                continue
            if token in all_evidence_text and prov != "textbook":
                continue  # 被草稿其他教材证据覆盖
            if token in (block.get("adapted_facts") or []):
                continue
            if prov == "textbook":
                violations.append(
                    {"where": where, "type": "textbook_token_not_in_evidence", "token": token}
                )
            else:
                violations.append(
                    {"where": where, "type": "unadapted_fact_token", "token": token}
                )

    unclassified = sum(
        1
        for v in violations
        if v["type"] in ("unadapted_fact_token", "textbook_token_not_in_evidence", "adapted_no_reason")
    )
    return {
        "unclassified": unclassified,
        "violations": violations,
        "checked_blocks": blocks,
        "token_total": token_total,
    }


def draft_hash(draft: dict) -> str:
    payload = json.dumps(
        {k: v for k, v in draft.items() if k not in ("factlock", "qa")},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 难度与纠错的诚实性
# ---------------------------------------------------------------------------


def check_honesty(draft: dict, view_entry: dict) -> list[str]:
    """硬门检查：编星、practice 纠错冒充教材原文、误收选题。返回硬门违规列表。"""
    hard: list[str] = []
    if "miscollected_topic" in (view_entry.get("flags") or []):
        hard.append("miscollected_topic")
    diff = draft.get("fields", {}).get("difficulty") or {}
    kind = diff.get("kind", "")
    index_diff = (view_entry.get("index_difficulty") or "").strip()
    if kind == "index_stars" and not index_diff:
        hard.append("fabricated_difficulty")
    display = diff.get("display", "")
    stars_in_display = re.search(r"[★☆]{1,4}", display)
    if stars_in_display and not index_diff and kind != "quoted":
        hard.append("fabricated_difficulty")

    if view_entry.get("activity_type") == "practice":
        rows = (draft.get("fields", {}).get("errors") or {}).get("rows") or []
        idx_has_err = view_entry.get(
            "index_has_errors", view_entry.get("_index_has_errors", True)
        )
        if not idx_has_err:
            for i, row in enumerate(rows):
                for side in ("error", "fix"):
                    blk = row.get(side) or {}
                    if blk.get("provenance") == "textbook":
                        hard.append(f"practice_errors_faked_textbook[{i}].{side}")
    return hard


# ---------------------------------------------------------------------------
# v3 内容门（题文匹配 / 重复 / 断裂标点 / 时长标注 / 安全可执行 / 引用证据）
# ---------------------------------------------------------------------------


def _cjk(s: str) -> str:
    return re.sub(r"[^\u4e00-\u9fff]", "", s)


def name_variants(name: str) -> list[str]:
    """展开活动名中的括号可选段：左(右)转弯走 → [左右转弯走, 左转弯走, 转弯走]。"""
    variants = [name]
    m = re.search(r"[（(]([^（）()]+)[）)]", name)
    if m:
        head = name[: m.start()]
        tail = name[m.end():]
        inner = m.group(1)
        for extra in ("", inner):
            variants.append(head + extra + tail)
    return [v for v in dict.fromkeys(_cjk(v) for v in variants) if len(v) >= 2]


def check_topic_match(draft: dict, view_entry: dict) -> bool:
    """题文一致：逐字稿必须讲到本活动（或其名称变体），且方法核心技术词入稿。"""
    script = "".join(st.get("script", "") for st in draft.get("flow") or [])
    script_cjk = _cjk(script)
    if not script_cjk:
        return False
    variants = name_variants(view_entry.get("activity_name", ""))
    if not variants:
        return True
    if not any(v in script_cjk for v in variants):
        return False
    # 方法核心动作 token 至少 1 个进入逐字稿（防"报活动名不讲活动"）
    method_text = (draft.get("fields", {}).get("method") or {}).get("text", "")
    method_tokens = [
        t["token"]
        for t in extract_fact_tokens(method_text)
        if t["category"] in ("technique", "equipment")
    ]
    if method_tokens and not any(t in script for t in method_tokens):
        return False
    return True


def _norm_sent(s: str) -> str:
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s)


def _bigrams(s: str) -> set:
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else set()


def near_duplicate_pairs(script_text: str, min_len: int = 8, thresh: float = 0.80) -> list:
    """近重复句对检测（字符 bigram Jaccard 相似度）。

    返回 [(句A, 句B, 相似度)]；用于拦截"连续重复指导语凑时长"。
    """
    sents = [_norm_sent(s) for s in re.split(r"[。！？]", script_text)]
    sents = [s for s in sents if len(s) >= min_len]
    pairs: list[tuple[str, str, float]] = []
    for i in range(len(sents)):
        for j in range(i + 1, len(sents)):
            a, b = sents[i], sents[j]
            if a == b:
                pairs.append((a, b, 1.0))
                continue
            ga, gb = _bigrams(a), _bigrams(b)
            if not ga or not gb:
                continue
            jac = len(ga & gb) / len(ga | gb)
            if jac >= thresh:
                pairs.append((a, b, round(jac, 3)))
    return pairs


BROKEN_PUNCT_RE = re.compile(r"[。！？；][，、]|[，、][。！？；]|([，。！？；、])\1+")


def check_broken_punctuation(script_text: str) -> list[str]:
    """断裂标点检测：双标点、句号后紧跟顿号等孤立标点。"""
    hits = [m.group(0) for m in BROKEN_PUNCT_RE.finditer(script_text)]
    return hits[:5]


def duration_breakdown(draft: dict) -> dict:
    """统一时长口径：口播时间（字数/语速）+ 明确登记的示范/停顿秒数。"""
    rate = (draft.get("config") or {}).get("speech_rate_chars_per_min", 230)
    stages = draft.get("flow") or []
    speech_chars = sum(len(st.get("script", "")) for st in stages)
    speech_sec = speech_chars / rate * 60.0
    demo_sec = 0.0
    per_stage: list[dict] = []
    for st in stages:
        d = float(st.get("demo_sec") or 0) + float(st.get("pause_sec") or 0)
        demo_sec += d
        per_stage.append(
            {"stage": st.get("stage"), "chars": len(st.get("script", "")), "demo_pause_sec": d}
        )
    return {
        "speech_sec": round(speech_sec, 1),
        "demo_pause_sec": round(demo_sec, 1),
        "total_sec": round(speech_sec + demo_sec, 1),
        "speech_chars": speech_chars,
        "per_stage": per_stage,
    }


def parse_duration_annotation(text: str) -> float | None:
    """从时长标注提取合计秒数（取标注中最大的数字，即合计值）。"""
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text or "")]
    return max(nums) if nums else None


def check_duration_annotation(draft: dict) -> tuple[bool, float | None, float]:
    """页面时长标注须与（口播+示范停顿）合计一致，容差 15 秒。"""
    meta = (draft.get("segment") or {}).get("meta") or {}
    declared = parse_duration_annotation(meta.get("时长", ""))
    computed = duration_breakdown(draft)["total_sec"]
    if declared is None:
        return False, None, computed
    return abs(declared - computed) <= 15.0, declared, computed


def check_cross_ref_evidence(draft: dict, view_entry: dict) -> bool:
    """前文引用条目：method 必须补被引用段落（位于本条 md_line 之前）的证据。"""
    if "method_cross_reference" not in (view_entry.get("flags") or []):
        return True
    md_line = int(view_entry.get("md_line", 0))
    method = draft.get("fields", {}).get("method") or {}
    for ev in method.get("evidence") or []:
        ln = ev.get("line")
        if ln is not None and int(ln) < md_line:
            return True
    return False


def check_safety_executable(draft: dict) -> tuple[bool, list]:
    """安全安排必须是能执行的口令（场地检查/行动路线/停止条件），不能只有"注意安全"。"""
    meta = (draft.get("segment") or {}).get("meta") or {}
    safety_text = " ".join(
        [str(meta.get("安全", ""))]
        + [st.get("script", "") for st in draft.get("flow") or []]
    )
    cats = [c for c, kws in SAFETY_CATEGORIES.items() if any(k in safety_text for k in kws)]
    executable = bool(SAFETY_EXECUTABLE_RE.search(safety_text))
    return (len(cats) >= 3 and executable), cats


# ---------------------------------------------------------------------------
# 片段流程模板（practice / game / fitness）
# ---------------------------------------------------------------------------

FLOWS: dict[str, list[dict]] = {
    "practice": [
        {"stage": "导入与示范", "sec_range": [30, 45], "purpose": "建立完整动作表象"},
        {"stage": "分解学练", "sec_range": [60, 90], "purpose": "按要点分步练习"},
        {"stage": "纠错与对比", "sec_range": [30, 45], "purpose": "针对易犯错误纠正"},
        {"stage": "巩固运用", "sec_range": [30, 60], "purpose": "游戏化巩固"},
        {"stage": "小结评价", "sec_range": [15, 30], "purpose": "回扣重点"},
    ],
    "game": [
        {"stage": "规则讲解", "sec_range": [30, 45], "purpose": "讲清方法与胜负"},
        {"stage": "示范试玩", "sec_range": [30, 60], "purpose": "一轮演示降低误解"},
        {"stage": "正式比赛", "sec_range": [60, 90], "purpose": "全员参与"},
        {"stage": "判定与追问", "sec_range": [20, 40], "purpose": "执行规则回扣素养"},
        {"stage": "小结", "sec_range": [15, 30], "purpose": "提炼要点"},
    ],
    "fitness": [
        {"stage": "动作示范与激活", "sec_range": [30, 45], "purpose": "示范约定动作"},
        {"stage": "跟随练习", "sec_range": [60, 120], "purpose": "主体负荷"},
        {"stage": "变式挑战", "sec_range": [30, 60], "purpose": "拓展变化"},
        {"stage": "放松与小结", "sec_range": [30, 45], "purpose": "恢复并回扣要点"},
    ],
}

SEGMENT_FIELDS = [
    "学段", "片段位置", "时长", "重点", "器材", "安全", "分层", "评价",
]


def flow_stage_names(atype: str) -> list[str]:
    return [s["stage"] for s in FLOWS.get(atype, [])]


# ---------------------------------------------------------------------------
# 100 分量表与放行线（冻结阈值，不得改动）
# ---------------------------------------------------------------------------

SCALE = {"教材事实": 30, "考编可用": 20, "安全": 20, "教学": 15, "口语": 10, "证据": 5}
RELEASE = {"total_min": 85, "textbook_min": 27, "safety_min": 16, "hard_gate_max": 0}

BANNED_CHARS_RE = re.compile(r"[：:——;;；]")


def score_draft(draft: dict, view_entry: dict, lib: BookLibrary | None = None) -> dict:
    """按冻结量表打分并给出放行判定。确定性、可复核。

    v3 分工：程序负责可验证检查（事实/时长/重复/标点/安全口令/题文/引用证据）；
    动作逻辑、建议依据、纠错有效性、可讲性由内容评审记录实责（fill 层校验）。
    """
    lib = lib or BookLibrary()
    fact = run_factlock(draft, lib)
    hard = check_honesty(draft, view_entry)
    scores: dict[str, float] = {}
    detail: dict[str, list[str]] = {}

    # ---- 教材事实 30 ----
    tb = 0.0
    blocks = list(iter_blocks(draft))
    tb_blocks = [b for _, b in blocks if b.get("provenance") == "textbook"]
    ev_ok = all(
        b.get("evidence")
        and all(ev.get("book_file") and ev.get("line") is not None and ev.get("excerpt") for ev in b["evidence"])
        for b in tb_blocks
    ) and tb_blocks
    tb += 6.0 if ev_ok else 0.0
    if not ev_ok:
        detail.setdefault("教材事实", []).append("教材块缺证据字段")
    ev_match = all(
        v["type"] not in ("textbook_token_not_in_evidence", "evidence_line_mismatch", "evidence_book_missing")
        for v in fact["violations"]
    )
    tb += 12.0 if ev_match else 0.0
    if not ev_match:
        detail.setdefault("教材事实", []).append("教材token或行号校验未过")
    honest = not any(h.startswith("fabricated_difficulty") or h.startswith("practice_errors_faked") for h in hard)
    tb += 6.0 if honest else 0.0
    if not honest:
        detail.setdefault("教材事实", []).append("难度或纠错冒充教材")
    has_core_textbook = any(
        (draft.get("fields", {}).get(k) or {}).get("provenance") == "textbook" for k in ("method", "rules")
    )
    tb += 6.0 if has_core_textbook else 0.0
    if not has_core_textbook:
        detail.setdefault("教材事实", []).append("方法或规则无教材原文支撑")
    # v3：前文引用必须补被引用段落证据（硬门）
    if not check_cross_ref_evidence(draft, view_entry):
        hard.append("cross_ref_evidence_missing")
        detail.setdefault("教材事实", []).append("前文引用未补被引用段落证据")
    scores["教材事实"] = round(tb, 1)

    # ---- 考编可用 20 ----
    ex = 0.0
    seg = draft.get("segment") or {}
    seg_meta = seg.get("meta") or {}
    present = [f for f in SEGMENT_FIELDS if (seg_meta.get(f) or "").strip()]
    ex += round(8.0 * len(present) / len(SEGMENT_FIELDS), 1)
    if len(present) < len(SEGMENT_FIELDS):
        detail.setdefault("考编可用", []).append(f"片段要素缺失: {sorted(set(SEGMENT_FIELDS)-set(present))}")
    script_text = "".join(st.get("script", "") for st in draft.get("flow") or [])
    br = duration_breakdown(draft)
    dur = br["total_sec"]
    lo, hi = draft.get("config", {}).get("segment_duration_sec", [120, 240])
    if lo <= dur <= hi:
        ex += 6.0
    elif lo * 0.9 <= dur <= hi * 1.1:
        ex += 3.0
        detail.setdefault("考编可用", []).append(f"含示范停顿时长 {dur:.0f}s 略超范围")
    else:
        detail.setdefault("考编可用", []).append(
            f"含示范停顿时长 {dur:.0f}s（口播 {br['speech_sec']:.0f}s + 示范停顿 {br['demo_pause_sec']:.0f}s）超范围"
        )
        hard.append("script_duration_out_of_range")
    # v3：页面时长标注与分段合计一致（硬门）
    anno_ok, declared, computed = check_duration_annotation(draft)
    if not anno_ok:
        hard.append("duration_annotation_mismatch")
        detail.setdefault("考编可用", []).append(
            f"时长标注 {declared} 与合计 {computed:.0f}s 不一致（容差15s）或标注缺失"
        )
    want = flow_stage_names(seg.get("type") or view_entry.get("activity_type", "practice"))
    got = [st.get("stage") for st in draft.get("flow") or []]
    stage_ok = [w for w in want if w in got]
    ex += round(6.0 * len(stage_ok) / max(1, len(want)), 1)
    if len(stage_ok) < len(want):
        detail.setdefault("考编可用", []).append(f"流程缺阶段: {sorted(set(want)-set(got))}")
    scores["考编可用"] = round(ex, 1)

    # ---- 安全 20 ----
    sf = 0.0
    safety_text = " ".join(
        [str(seg_meta.get("安全", ""))]
        + [st.get("script", "") for st in draft.get("flow") or []]
    )
    cats = [c for c, kws in SAFETY_CATEGORIES.items() if any(k in safety_text for k in kws)]
    sf += min(15.0, 3.0 * len(cats))
    if len(cats) < 5:
        detail.setdefault("安全", []).append(f"安全维度覆盖 {len(cats)}/5: {cats}")
    equip_terms = [t for t in re.split(r"[、,，/\s]+", seg_meta.get("器材", "")) if len(t) >= 2]
    equip_mentioned = any(t in safety_text for t in equip_terms) or any(
        k in safety_text for k in ("检查", "摆放", "收放")
    )
    sf += 5.0 if equip_mentioned else 0.0
    if not equip_mentioned:
        detail.setdefault("安全", []).append("未见器材检查/收放提示")
    if not cats:
        hard.append("safety_missing_entirely")
    # v3：安全安排必须可执行（能执行的口令），不能只有安全套话（硬门）
    exec_ok, cats2 = check_safety_executable(draft)
    if cats and not exec_ok:
        hard.append("safety_not_executable")
        detail.setdefault("安全", []).append(
            f"安全安排缺可执行口令（类别 {cats2}）——须含场地检查/行动路线/停止条件类指令"
        )
    scores["安全"] = round(sf, 1)

    # ---- 教学 15 ----
    td = 0.0
    rows = (draft.get("fields", {}).get("errors") or {}).get("rows") or []
    specific_fix = any(
        len(re.sub(r"[^\u4e00-\u9fff]", "", (r.get("fix") or {}).get("text", ""))) >= 8 for r in rows
    ) or (view_entry.get("activity_type") in ("game", "fitness") and any(
        "判定" in (st.get("script") or "") or "规则" in (st.get("script") or "") for st in draft.get("flow") or []
    ))
    td += 5.0 if specific_fix else 0.0
    if not specific_fix:
        detail.setdefault("教学", []).append("纠错/判定不具体")
    if rows:
        recheck = any(
            re.search(r"再看|再试|再次|复查|检查|观察|确认", (r.get("fix") or {}).get("text", ""))
            for r in rows
        )
        if recheck:
            detail.setdefault("教学", []).append("纠错含再次检查（三件套达标）")
        else:
            detail.setdefault("教学", []).append("纠错缺再次检查（建议补复核动作）")
    org_text = (draft.get("fields", {}).get("organization") or {}).get("text", "") + script_text
    td += 5.0 if any(k in org_text for k in ("组", "队形", "轮换", "散点", "面对面")) else 0.0
    if "组" not in org_text and "队形" not in org_text:
        detail.setdefault("教学", []).append("组织形式不明确")
    td += 5.0 if any("示范" in (st.get("script") or "") for st in draft.get("flow") or []) else 0.0
    if not any("示范" in (st.get("script") or "") for st in draft.get("flow") or []):
        detail.setdefault("教学", []).append("无示范环节")
    scores["教学"] = round(td, 1)

    # ---- 口语 10 ----
    oral = 0.0
    banned = BANNED_CHARS_RE.findall(script_text)
    oral += 4.0 if not banned else 0.0
    if banned:
        detail.setdefault("口语", []).append(f"逐字稿含禁用标点 {''.join(sorted(set(banned)))}")
    # v3：断裂标点（孤立标点/双标点）→ 硬门
    broken = check_broken_punctuation(script_text)
    if broken:
        hard.append("broken_punctuation")
        detail.setdefault("口语", []).append(f"断裂标点 {broken}")
    # v3：近重复句 → 1 对扣 3 分，≥2 对硬门（拦截重复指导语凑时长）
    dup = near_duplicate_pairs(script_text)
    if len(dup) >= 2:
        hard.append("script_repetition_high")
        detail.setdefault("口语", []).append(
            f"近重复句 {len(dup)} 对（如「{dup[0][0][:12]}…」）——重复指导语凑时长"
        )
    elif len(dup) == 1:
        detail.setdefault("口语", []).append(f"近重复句 1 对（{dup[0][0][:12]}…）扣 3 分")
    else:
        oral += 3.0
    sents = [s for s in re.split(r"[。！？]", script_text) if s.strip()]
    if sents:
        med = sorted(len(s) for s in sents)[len(sents) // 2]
        oral += 3.0 if med <= 45 else 1.0
        if med > 45:
            detail.setdefault("口语", []).append(f"句长中位数 {med} 字偏长")
    scores["口语"] = round(oral, 1)

    # ---- 证据 5 ----
    ev = 0.0
    if fact["unclassified"] == 0:
        ev += 3.0
    else:
        detail.setdefault("证据", []).append(f"未归类事实token/缺加工理由 {fact['unclassified']}")
        hard.append("factlock_unclassified_gt0")
    excerpts = [e.get("excerpt", "") for _, b in blocks for e in (b.get("evidence") or [])]
    if excerpts and all(len(x) >= 4 for x in excerpts):
        ev += 2.0
    elif not tb_blocks:
        detail.setdefault("证据", []).append("无教材证据excerpt")
    else:
        detail.setdefault("证据", []).append("excerpt 过短")
    scores["证据"] = round(ev, 1)

    # ---- v3：题文一致（硬门） ----
    if not check_topic_match(draft, view_entry):
        hard.append("topic_text_mismatch")
        detail.setdefault("教材事实", []).append(
            "逐字稿未讲到本活动名称/变体或方法核心技术词（题文错配）"
        )

    total = round(sum(scores.values()), 1)
    release = (
        total >= RELEASE["total_min"]
        and scores["教材事实"] >= RELEASE["textbook_min"]
        and scores["安全"] >= RELEASE["safety_min"]
        and len(hard) == 0
    )
    return {
        "scores": scores,
        "total": total,
        "hard_gates": sorted(set(hard)),
        "release": release,
        "factlock": fact,
        "detail": detail,
        "script_chars": len(script_text),
        "duration": br,
    }


def estimate_duration_sec(script_text: str, draft: dict) -> float:
    """兼容入口：v3 统一口径 = 口播 + 示范/停顿。"""
    return duration_breakdown(draft)["total_sec"]


# ---------------------------------------------------------------------------
# 内容评审记录（v3：内容评审实责，与成品同版本）
# ---------------------------------------------------------------------------

REVIEW_CHECKS = {
    "action_logic_ok": "动作逻辑与教材一致（无改变核心动作/规则的加工）",
    "suggestions_labeled": "新增组织/提示/纠错均标为教学建议且登记理由",
    "correction_effective": "纠错含具体表现、纠正办法、再次检查",
    "tellable": "考生可依据成稿完成示范、组织、纠错和评价",
    "safety_executable": "安全安排为可执行口令（场地检查/行动路线/停止条件）",
}


def validate_review(review: dict, draft: dict, view_entry: dict = None) -> tuple[bool, list[str]]:
    """校验内容评审记录：schema、对象、版本（draft_sha）、逐项结论。

    内容修改后沿用旧评审结果 → draft_sha 不匹配 → 拒绝。
    """
    errors: list[str] = []
    if review.get("schema") != SCHEMA_REVIEW:
        errors.append(f"评审记录 schema 须为 {SCHEMA_REVIEW}")
    if review.get("id") != draft.get("id"):
        errors.append("评审记录 id 与草稿不一致")
    want_sha = draft_hash(draft)
    if review.get("draft_sha") != want_sha:
        errors.append(
            f"评审记录版本不一致（review.draft_sha={review.get('draft_sha')}，当前草稿={want_sha}）——"
            "内容已修改，须重新评审，不得沿用旧审核结果"
        )
    checked = review.get("checked") or {}
    for k, label in REVIEW_CHECKS.items():
        if checked.get(k) is not True:
            errors.append(f"评审未通过：{label}（{k}={checked.get(k)}）")
    if (review.get("verdict") or "") != "pass":
        errors.append(f"评审结论 verdict={review.get('verdict')}（须为 pass）")
    if not (review.get("suggestion_notes") or []):
        errors.append("评审记录缺 suggestion_notes（教学建议理由不得为空）")
    return (not errors, errors)

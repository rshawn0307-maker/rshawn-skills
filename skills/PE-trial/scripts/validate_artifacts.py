#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pe-trial 产物验证器（仅标准库）。

覆盖（对应任务书任务2清单）：
  运动技能/健康课结构、19/21 锚点声称不符、时长求和、教材源冲突、
  危险保护(VETO-SAFETY)、解析失败串锚、缺伴随文件、零项目、重复ID、
  11列表格/表宽超限、A4版式/页边距、中文字体声明、EXAM_PROFILE 字段。

用法：
  validate_artifacts.py --suite <净稿.md|套件目录> --profile <profile.json> [--textbook <教材.md>]
  validate_artifacts.py --docx <讲义.docx>
  validate_artifacts.py --profile <profile.json>
选项 --json 输出机器可读结果。

退出码：0=无错误（可有警告）；1=有错误或 VETO；2=用法/IO 错误。
"""
import argparse
import json
import os
import re
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# ---------- R1 评分矩阵（与 references/scoring-rubric.md R1 冻结一致） ----------
R1_IDS = {
    "VETO-SAFETY", "VETO-KNOW",
    "A1", "A2", "A3", "A3a", "B1", "B2", "B2a", "B3", "B4",
    "C1", "C1a", "C2", "C2a", "D1", "E1", "E2", "F1", "F2", "G1",
}
R1_LIVE_IDS = {"A3a", "B2a", "C1a", "C2a"}
_ID_ALT = "|".join(sorted(R1_IDS, key=len, reverse=True))
# 净稿纯净性：出现任一 R1 ID 即 F4（A4 纸张等正常词不在集合内，不误报）
CLEAN_ID_RE = re.compile(r"(?<![A-Za-z0-9-])(?:%s)(?![A-Za-z0-9])" % _ID_ALT)
# 自检表第一列：`ID` 或 `ID [LIVE]`（允许加粗/反引号）
ID_CELL_RE = re.compile(r"^\s*\**`?(%s)`?\**\s*(\[LIVE\])?\s*$" % _ID_ALT)
# 形似 R1 ID 但不在冻结集合（如 X99/A9/B2【LIVE】）=> 拒绝串锚
ID_LIKE_RE = re.compile(r"^[A-Z]{1,2}\d{1,2}[a-z]?\s*(\[LIVE\]|【LIVE】)?$")

PROFILE_FIELDS = [
    "exam_type", "region_year", "stage_grade", "standard", "textbook_pages",
    "deliverable_type", "prep_minutes", "trial_minutes", "defense",
    "skill_demo", "student_mode", "equipment",
]
PROFILE_NAME_RE = re.compile(
    r"\b(EXAM_PROFILE|exam_type|region_year|stage_grade|textbook_pages|"
    r"deliverable_type|prep_minutes|trial_minutes|student_mode|"
    r"media_allowed|word_target|segment_split)\b")

SELF_SCORE_RE = re.compile(
    r"(本稿|全文|正文)[约共]?\s*\d{3,4}\s*字|字数[：:]\s*\d|满分|"
    r"评分[：:]\s*\d|得分[：:]?\s*\d|\d+\s*分（总评）|平均分\s*\d")
PLACEHOLDER_RE = re.compile(r"XXX|\{\}|待补|待填|TODO|TBD")
ANCHOR_LINE_RE = re.compile(r"^\s*>\s*评分锚点")

HIGH_RISK_WORDS = (
    "山羊", "分腿腾越", "跳马", "跳箱", "横箱", "纵箱", "单杠", "双杠",
    "投掷", "实心球", "铅球", "标枪", "铁饼", "跨栏", "爬绳", "肋木",
    "腾越", "杠上",
)
PROTECT_WORDS = (
    "保护帮助", "保护与帮助", "保护垫", "体操垫", "垫子", "统一方向",
    "同方向", "安全距离", "安全提示", "分组保护", "保护者", "助跑区",
    "沙坑", "器材检查", "场地检查", "清点器材",
)
OPPOSED_THROW_RE = re.compile(r"相向[^。；\n]{0,12}(投掷|对扔|对掷|互掷)")

SKILL_PHASES = ("开始部分", "准备部分", "基本部分", "结束部分")
HEALTH_PHASES = ("游戏导入", "游戏探究", "游戏拓展", "总结评价")

TITLE_TS_RE = re.compile(r"^(#{1,6})\s+(.+?)（\s*(\d+(?:\.\d+)?)\s*分钟\s*）\s*$")
CLAIM_COUNT_RE = re.compile(r"共\s*(\d+)\s*项")
TECH_NO_RE = re.compile(r"(\d{2}-\d{2})")
EVIDENCE_RE = re.compile(r"[：:]\s*\d+|\d+\s*[-–—]\s*\d+")

COMPANIONS = ("备课提纲", "板书设计", "队形图", "自检表")


class Report(object):
    def __init__(self, target):
        self.target = target
        self.veto = []
        self.errors = []
        self.warnings = []
        self.stats = {}

    def error(self, code, msg, path=None, line=None):
        self.errors.append({"code": code, "file": path, "line": line, "msg": msg})

    def veto_hit(self, code, msg, path=None, line=None):
        self.veto.append({"code": code, "file": path, "line": line, "msg": msg})

    def warn(self, code, msg, path=None, line=None):
        self.warnings.append({"code": code, "file": path, "line": line, "msg": msg})

    @property
    def ok(self):
        return not self.errors and not self.veto

    def to_dict(self):
        return {"target": self.target, "ok": self.ok, "veto": self.veto,
                "errors": self.errors, "warnings": self.warnings,
                "stats": self.stats}

    def render_text(self):
        lines = ["validate: %s" % self.target]
        for v in self.veto:
            lines.append("[veto ] %-24s %s%s %s" % (
                v["code"], _loc(v), "" if v["code"].startswith("VETO") else "", v["msg"]))
        for e in self.errors:
            lines.append("[error] %-24s %s %s" % (e["code"], _loc(e), e["msg"]))
        for w in self.warnings:
            lines.append("[warn ] %-24s %s %s" % (w["code"], _loc(w), w["msg"]))
        if self.stats:
            lines.append("[stats] %s" % json.dumps(self.stats, ensure_ascii=False))
        lines.append("RESULT: %s (errors=%d veto=%d warnings=%d)" % (
            "PASS" if self.ok else "FAIL", len(self.errors), len(self.veto),
            len(self.warnings)))
        return "\n".join(lines)


def _loc(item):
    f = item.get("file") or "-"
    if item.get("line"):
        return "%s:%s" % (f, item["line"])
    return f


# ---------- EXAM_PROFILE ----------
def validate_profile(profile, rep):
    for f in PROFILE_FIELDS:
        if f not in profile:
            rep.error("PROFILE-MISSING-FIELD", "EXAM_PROFILE 缺字段 %s" % f)
    enums = {
        "exam_type": {"tuhuan", "ntce", "other"},
        "deliverable_type": {"full_lesson", "interview_segment"},
        "student_mode": {"no_student", "with_student"},
        "defense": {"none", "structured", "defense"},
    }
    for k, allow in enums.items():
        v = profile.get(k)
        if v is not None and v not in allow:
            rep.error("PROFILE-BAD-ENUM", "%s=%r 不在 %s" % (k, v, sorted(allow)))
    tm = profile.get("trial_minutes")
    if tm is not None and not (isinstance(tm, (int, float)) and tm > 0):
        rep.error("PROFILE-BAD-NUMBER", "trial_minutes=%r 必须为正数" % (tm,))
    pm = profile.get("prep_minutes")
    if pm is not None and pm is not False and not isinstance(pm, (int, float, type(None))):
        rep.error("PROFILE-BAD-NUMBER", "prep_minutes=%r 非法" % (pm,))
    return rep


def load_profile(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------- Markdown 套件 ----------
def read_lines(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().splitlines()


def strip_md(text):
    return re.sub(r"[#>*`|\-\s]", "", text)


def validate_transcript(path, profile, textbook, rep):
    lines = read_lines(path)
    text = "\n".join(lines)
    fname = os.path.basename(path)
    full_lesson = profile.get("deliverable_type") == "full_lesson"
    rep.stats["transcript"] = fname

    # --- 课型探测与结构（运动技能/健康课） ---
    h_hits = [p for p in HEALTH_PHASES if p in text]
    s_hits = [p for p in SKILL_PHASES if p in text]
    if len(h_hits) >= 2 and len(h_hits) >= len(s_hits):
        kind, phases, need = "health", h_hits, HEALTH_PHASES
    elif len(s_hits) >= 2:
        kind, phases, need = "skills", s_hits, SKILL_PHASES
    else:
        kind = None
        rep.error("STRUCTURE", "无法判定课型：健康课/运动技能环节标记均不足")
    rep.stats["lesson_kind"] = kind
    if kind == "health":
        missing = [p for p in HEALTH_PHASES if p not in text]
        if full_lesson and missing:
            rep.error("STRUCTURE", "健康课缺环节：%s" % "、".join(missing), path)
        elif not full_lesson and "游戏探究" not in text:
            rep.error("STRUCTURE", "面试片段须含核心环节 游戏探究", path)
    elif kind == "skills":
        missing = [p for p in SKILL_PHASES if p not in text]
        if full_lesson and missing:
            rep.error("STRUCTURE", "运动技能课缺环节：%s" % "、".join(missing), path)
        elif not full_lesson and "基本部分" not in text:
            rep.error("STRUCTURE", "面试片段须含核心环节 基本部分", path)
        rep.stats["phases_found"] = "/".join(s_hits)

    # --- 时长求和（F2 硬门） ---
    stamps = []  # (level, minutes, lineno, title)
    for i, ln in enumerate(lines, 1):
        m = TITLE_TS_RE.match(ln)
        if m:
            stamps.append((len(m.group(1)), float(m.group(3)), i, m.group(2)))
    if stamps:
        top = min(s[0] for s in stamps)
        total = sum(s[1] for s in stamps if s[0] == top)
        rep.stats["duration_sum"] = total
        target = profile.get("trial_minutes")
        if target is None:
            rep.warn("DURATION-SUM", "画像无 trial_minutes，未校验时长和")
        elif abs(total - float(target)) > 0.5 + 1e-9:
            rep.error("DURATION-SUM",
                      "顶层环节时长和 %.1f ≠ trial_minutes %s（±0.5 硬门）"
                      % (total, target), path)
    else:
        rep.error("DURATION-SUM", "未找到任何环节标题时间戳（如 基本部分（6分钟））", path)

    # --- 净稿纯净性（F4/F5） ---
    for i, ln in enumerate(lines, 1):
        if ANCHOR_LINE_RE.search(ln):
            rep.error("CLEANLINESS", "旧版评分锚点行混入净稿", path, i)
            continue
        m = CLEAN_ID_RE.search(ln)
        if m:
            rep.error("CLEANLINESS", "R1 评分 ID %s 混入净稿" % m.group(0), path, i)
        m = PROFILE_NAME_RE.search(ln)
        if m:
            rep.error("CLEANLINESS", "EXAM_PROFILE 元信息 %s 混入净稿" % m.group(0), path, i)
        m = SELF_SCORE_RE.search(ln)
        if m:
            rep.error("CLEANLINESS", "自报统计/评分语：%s" % m.group(0), path, i)
        m = PLACEHOLDER_RE.search(ln)
        if m:
            rep.error("CLEANLINESS", "占位符 %s" % m.group(0), path, i)

    # --- 字数诊断（F1 警告级） ---
    body = strip_md(text)
    wc = len(body)
    rep.stats["word_count"] = wc
    wt = profile.get("word_target")
    if isinstance(wt, (list, tuple)) and len(wt) == 2:
        lo, hi = float(wt[0]), float(wt[1])
        if wc < lo * 0.8 or wc > hi * 1.2:
            rep.warn("WORD-COUNT", "字数 %d 偏离画像区间 %s ±20%%（诊断级）" % (wc, wt), path)

    # --- 高危保护（VETO-SAFETY） ---
    risky = [w for w in HIGH_RISK_WORDS if w in text or w in fname]
    rep.stats["high_risk"] = risky
    if risky:
        mate = _companion_text(path, "队形图")
        guard_text = text + "\n" + mate
        protected = [w for w in PROTECT_WORDS if w in guard_text]
        if not protected:
            rep.veto_hit("VETO-SAFETY",
                         "高危项目（%s）净稿+队形图无任何保护帮助/安全措施词"
                         % "、".join(risky), path)
        if OPPOSED_THROW_RE.search(text):
            rep.veto_hit("VETO-SAFETY", "出现相向投掷组织（S1 危险组织）", path)

    # --- 教材源冲突（T1） ---
    if textbook is not None:
        title = _tech_title(path, lines)
        if title:
            norm = re.sub(r"\s+", "", title)
            if norm and norm not in re.sub(r"\s+", "", textbook):
                rep.error("TEXTBOOK-SOURCE-CONFLICT",
                          "子技术《%s》未出现在教材源，涉嫌超教材范围（T1）" % title, path)
    return rep


def _tech_title(path, lines):
    for ln in lines[:6]:
        m = re.match(r"^#\s+(.+?)\s*$", ln)
        if m:
            t = re.sub(r"^\d{2}-\d{2}\s*", "", m.group(1))   # 去行首编号
            t = re.sub(r"[（(][^（()）]*[）)]", "", t)         # 去括注
            t = re.sub(r"(试讲稿?|净稿|考场版|考场净稿)$", "", t).strip()
            return t or None
    stem = os.path.basename(path)
    m = re.match(r"\d{2}_.+?_(\d{2}-\d{2})_(.+?)_(试讲稿|备课提纲|板书设计|队形图|自检表)_v", stem)
    if m:
        return m.group(2)
    return None


def _companion_text(transcript_path, kind):
    no = TECH_NO_RE.search(os.path.basename(transcript_path))
    if not no:
        return ""
    d = os.path.dirname(os.path.abspath(transcript_path))
    for fn in os.listdir(d):
        if kind in fn and no.group(1) in fn and fn.endswith(".md"):
            try:
                with open(os.path.join(d, fn), "r", encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                return ""
    return ""


def validate_companions(path, profile, rep):
    fname = os.path.basename(path)
    no = TECH_NO_RE.search(fname)
    if not no:
        rep.warn("MISSING-COMPANION", "文件名无法解析子技术编号，跳过伴随文件检查")
        return
    d = os.path.dirname(os.path.abspath(path))
    present = set()
    for fn in os.listdir(d):
        if no.group(1) in fn and fn.endswith(".md"):
            for c in COMPANIONS:
                if c in fn:
                    present.add(c)
    full_lesson = profile.get("deliverable_type") == "full_lesson"
    checklist = ["备课提纲", "队形图", "自检表"] + (["板书设计"] if full_lesson else [])
    for c in checklist:
        if c not in present:
            rep.error("MISSING-COMPANION", "缺伴随文件：%s（子技术 %s）" % (c, no.group(1)), path)
    if not full_lesson and "板书设计" not in present:
        sc = _companion_text(path, "自检表")
        if sc and "板书并入净稿" not in sc:
            rep.error("MISSING-COMPANION",
                      "面试片段无板书设计且自检表未标注 板书并入净稿", path)


def validate_selfcheck(path, rep):
    lines = read_lines(path)
    text = "\n".join(lines)
    ids = []
    bad_rows = []
    for i, ln in enumerate(lines, 1):
        if not ln.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if not cells or set(cells[0]) <= set("-: ") or cells[0] in ("ID",):
            continue
        if not ID_CELL_RE.match(cells[0]):
            if ID_LIKE_RE.match(cells[0].strip("*` ")) and cells[0] not in ("ID",):
                bad_rows.append((i, cells[0]))
            continue  # 非锚点行（说明列等）忽略
        rid = cells[0].strip("*`").split()[0]
        if rid not in R1_IDS:
            bad_rows.append((i, cells[0]))
            continue
        state = cells[2] if len(cells) > 2 else ""
        rest = "|".join(cells[3:]) if len(cells) > 3 else ""
        if re.search(r"满分|优秀|\d+\s*分|得分", state):
            rep.error("SELF-SCORE", "自检表出现自评分：%s" % state, path, i)
        if state == "通过" and not EVIDENCE_RE.search(rest):
            rep.error("SELF-CHECK-EVIDENCE",
                      "ID %s 判 通过 但缺证据行号（文件:行号）" % rid, path, i)
        if rid in ids:
            rep.error("DUPLICATE-ID", "R1 ID %s 重复出现（凑数锚点）" % rid, path, i)
        ids.append(rid)
    for i, cell in bad_rows:
        rep.error("PARSE-BAD-ANCHOR-ROW",
                  "自检表锚点行无法解析（非法 ID：%s），拒绝串锚" % cell, path, i)
    m = CLAIM_COUNT_RE.search(text)
    if m:
        claim = int(m.group(1))
        if claim != len(ids):
            rep.error("ANCHOR-CLAIM-MISMATCH",
                      "声称 共%d项 但实际锚点行 %d（19/21 类虚报）" % (claim, len(ids)),
                      path)
    rep.stats["selfcheck_ids"] = len(ids)
    return rep


def validate_suite(target, profile, textbook, rep):
    if os.path.isdir(target):
        transcripts = []
        for root, _dirs, files in os.walk(target):
            for fn in files:
                if "试讲稿" in fn and fn.endswith(".md"):
                    transcripts.append(os.path.join(root, fn))
        if not transcripts:
            rep.error("ZERO-PROJECT", "目录内没有任何试讲稿（零项目）", target)
            return rep
        rep.stats["transcript_count"] = len(transcripts)
        for t in sorted(transcripts):
            validate_transcript(t, profile, textbook, rep)
            validate_companions(t, profile, rep)
            sc = _companion_text(t, "自检表")
            scp = None
            no = TECH_NO_RE.search(os.path.basename(t))
            d = os.path.dirname(os.path.abspath(t))
            if no:
                for fn in os.listdir(d):
                    if "自检表" in fn and no.group(1) in fn and fn.endswith(".md"):
                        scp = os.path.join(d, fn)
            if scp:
                validate_selfcheck(scp, rep)
            elif no:
                rep.error("MISSING-COMPANION", "缺伴随文件：自检表（子技术 %s）"
                          % no.group(1), t)
    else:
        validate_transcript(target, profile, textbook, rep)
        validate_companions(target, profile, rep)
        sc = _companion_text(target, "自检表")
        if sc:
            scp = _companion_path(target)
            if scp:
                validate_selfcheck(scp, rep)
        else:
            rep.error("MISSING-COMPANION", "缺伴随文件：自检表", target)
    return rep


def _companion_path(transcript_path):
    no = TECH_NO_RE.search(os.path.basename(transcript_path))
    if not no:
        return None
    d = os.path.dirname(os.path.abspath(transcript_path))
    for fn in os.listdir(d):
        if "自检表" in fn and no.group(1) in fn and fn.endswith(".md"):
            return os.path.join(d, fn)
    return None


# ---------- DOCX（stdlib zipfile + ElementTree） ----------
A4_W, A4_H = 11906, 16838          # twips：21cm / 29.7cm
MARGIN = 1417                       # 2.5cm
TABLE_MAX = 9072                    # 16cm
COL_MAX = 10                        # 11 列即报错


def _q(tag):
    return "{%s}%s" % (W_NS, tag)


def validate_docx(path, rep):
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        rep.error("DOCX-UNREADABLE", "无法打开 docx：%s" % exc, path)
        return rep
    with zf:
        names = zf.namelist()
        if "word/document.xml" not in names:
            rep.error("DOCX-UNREADABLE", "缺少 word/document.xml", path)
            return rep
        doc = ET.fromstring(zf.read("word/document.xml"))
        # 页面尺寸
        pgszs = doc.iter(_q("pgSz"))
        seen_pg = False
        for pg in pgszs:
            seen_pg = True
            w, h = int(pg.get(_q("w"), "0")), int(pg.get(_q("h"), "0"))
            if abs(w - A4_W) > 10 or abs(h - A4_H) > 10:
                rep.error("PAGE-SETUP",
                          "页面非 A4 竖版：w=%s h=%s（应 11906×16838 twips=21×29.7cm）"
                          % (w, h), path)
        if not seen_pg:
            rep.error("PAGE-SETUP", "未找到 pgSz（页面尺寸未显式设置）", path)
        # 页边距
        for mar in doc.iter(_q("pgMar")):
            for side in ("top", "bottom", "left", "right"):
                v = mar.get(_q(side))
                if v is None or abs(int(v) - MARGIN) > 10:
                    rep.error("PAGE-SETUP",
                              "页边距 %s=%s（应 %d twips=2.5cm ±10）"
                              % (side, v, MARGIN), path)
        # 表格
        tbl_count = 0
        for tbl in doc.iter(_q("tbl")):
            tbl_count += 1
            cols = [int(c.get(_q("w"), "0")) for c in tbl.iter(_q("gridCol"))]
            if len(cols) >= 11:
                rep.error("TABLE-TOO-MANY-COLS",
                          "表格 %d 列（≥11 列禁止，将不可读/超宽）" % len(cols), path)
            if cols and sum(cols) > TABLE_MAX + 10:
                rep.error("TABLE-TOO-WIDE",
                          "表格总宽 %d twips=%.2fcm 超 16cm 上限"
                          % (sum(cols), sum(cols) / 567.0), path)
            tw = tbl.find("./%s" % _q("tblPr"))
            if tw is not None:
                twel = tw.find(_q("tblW"))
                if twel is not None and twel.get(_q("type")) == "dxa":
                    wv = int(twel.get(_q("w"), "0"))
                    if wv > TABLE_MAX + 10:
                        rep.error("TABLE-TOO-WIDE",
                                  "tblW=%d twips=%.2fcm 超 16cm 上限"
                                  % (wv, wv / 567.0), path)
        rep.stats["tables"] = tbl_count
        # 中文字体声明
        font_ok = False
        if "word/styles.xml" in names:
            st = ET.fromstring(zf.read("word/styles.xml"))
            for rf in st.iter(_q("rFonts")):
                ea = rf.get(_q("eastAsia"))
                if ea and ea.strip():
                    font_ok = True
                    break
        if not font_ok:
            rep.error("FONT-MISSING",
                      "styles.xml 未显式声明中文字体（w:eastAsia）", path)
    return rep


# ---------- main ----------
def build_argparser():
    p = argparse.ArgumentParser(description="pe-trial 产物验证器（stdlib）")
    p.add_argument("--suite", help="净稿 md 或套件目录")
    p.add_argument("--profile", help="EXAM_PROFILE JSON")
    p.add_argument("--textbook", help="教材 md（教材源冲突校验）")
    p.add_argument("--docx", help="讲义 docx（版式校验）")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    return p


def main(argv=None):
    args = build_argparser().parse_args(argv)
    if not (args.suite or args.docx or args.profile):
        print("用法错误：需 --suite / --docx / --profile 至少一项", file=sys.stderr)
        return 2
    target = args.suite or args.docx or args.profile
    rep = Report(target)
    profile = {}
    if args.profile:
        try:
            profile = load_profile(args.profile)
        except (OSError, ValueError) as exc:
            print("画像读取失败：%s" % exc, file=sys.stderr)
            return 2
        validate_profile(profile, rep)
    textbook = None
    if args.textbook:
        try:
            with open(args.textbook, "r", encoding="utf-8") as fh:
                textbook = fh.read()
        except OSError as exc:
            print("教材读取失败：%s" % exc, file=sys.stderr)
            return 2
    if args.docx:
        if not os.path.isfile(args.docx):
            print("docx 不存在：%s" % args.docx, file=sys.stderr)
            return 2
        validate_docx(args.docx, rep)
    if args.suite:
        if not os.path.exists(args.suite):
            print("suite 不存在：%s" % args.suite, file=sys.stderr)
            return 2
        if not profile:
            rep.error("PROFILE-MISSING", "套件校验必须提供 --profile")
        else:
            validate_suite(args.suite, profile, textbook, rep)
    out = json.dumps(rep.to_dict(), ensure_ascii=False, indent=1) if args.json \
        else rep.render_text()
    print(out)
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())

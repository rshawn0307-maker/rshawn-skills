#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""content_rules.py v1.0 -- 结构化答题技巧 内容自检器（内容层，不碰引擎与模板）

用法:
    python3 content_rules.py --pending <pending_tips.json> [--meta <draft_meta.json>] [--index <tips_index.json>]
    python3 content_rules.py --check-index <tips_index.json>          # 只查索引错链/来源
    python3 content_rules.py --pending <...> --self-test-stdin < meta.json   # 供测试注入 meta 字符串

退出码:
    0 通过
    1 用法/文件错误（路径不存在、JSON 解析失败）
    5 内容规则不通过（errors 逐条列出）

规则来源: references/content-strategy.md（2026-09-06 修订版）+ SKILL.md「一期一技巧」。
draft_meta.json（可选，写稿工作区内部文件，不进模板）:
    {"tip_id": "...", "method_points": 2|3|4, "point_labels": ["..."],
     "focus_keywords": ["..."], "sources": ["文件#小节", ...]}

检查项（与 test_content_rules.py 用例一一对应）:
    R1 索引错链: src 文件存在 + 题型目录与 types 一致 + name/note 与 src 正文共享实词
    R2 来源缺失: src 为空或文件不存在
    R3 标题兑现: 标题内容词必须出现在正文（破题/步骤/对照/避坑）
    R4 对照同题同条件: 高分版不靠堆字（长度 ≤1.8×）且与普通版有同题锚点词
    R5 步数服从原方法: 两点法 step3 须为应用/检查；四点法标签须全部覆盖；三点法 1:1
    R6 适用边界: pitfalls 须含边界/误用/纠正线索
    R7 无虚构权威: 禁"考官内心"等推测语（标题栏目句式"考官想听的："除外）；
       百分比须有出处/示范标记；经历腔须标示范
    R8 总结是练习: tip_takeaway 须含微练习/自检线索
    R9 一期一技巧: meta.focus_keywords 至少一个出现在破题（meta 缺省时跳过）
    R10 emoji 纪律: 每字段 ≤2 个，超出调色板即报
"""

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_USAGE, EXIT_RULES = 0, 1, 5

# ---------- 词表 ----------

# 标题里的功能词，不计入"内容词"
TITLE_STOPWORDS = {
    "别再", "别", "怎么", "什么", "多久", "如何", "为什么", "第一", "一句话",
    "答题", "面试", "考生", "公考", "结构化", "技巧", "每日", "一练", "吗", "呢",
}
# 泛政务词（二字窗口级），不作"同题锚点"
GENERIC_BIGRAMS = {
    "我们", "我会", "领导", "群众", "考生", "单位", "工作", "问题", "情况",
    "进行", "相关", "如果", "可以", "这个", "一个", "自己", "同事", "现场",
    "各位", "考官", "答题", "完毕", "处理", "解决", "所以", "但是", "然后",
    "普通", "高分", "答法", "第一步", "第二步", "第三步",
}
# R4: 高分版长度相对普通版上限
CASE_LEN_RATIO_MAX = 1.8
# R5: step3 作为"应用/检查步"的线索词（两点法专用）
CHECK_CUES = ("自查", "自检", "检查", "检验", "验证", "复盘", "问自己",
              "试着", "练习", "应用", "落到", "对照", "核一遍", "过一遍")
# R6: pitfalls 边界线索词
BOUNDARY_CUES = ("适用", "不适用", "边界", "仅", "只", "前提", "误用", "别用",
                 "慎用", "纠正", "例外", "为准", "规则", "权限", "制度", "调整",
                 "超出", "条件", "若", "如果")
# R7: 虚构权威禁语（一字不差）。
# 注意："考官想听的："是用户 2026-09-07 定稿的标题栏目句式，不在禁语表内；
# 禁的是正文里替考官编内心独白、无依据评分规则和凭空统计。
BANNED_AUTHORITY = ("考官内心", "考官会想", "考官普遍", "阅卷人内心",
                    "听了就加分", "一票否决", "考官必给")
# R7: 无出处百分比的豁免标记（同字段出现即放行）
SOURCE_MARKERS = ("出处", "据", "报告", "文件", "显示", "举例", "比如", "例如",
                  "示范", "设定", "假设", "来源")
# R7: 经历腔标记 -> 必须同字段出现"示范"类标记
EXPERIENCE_MARKERS = ("我当年", "我上岸", "我考场上", "那年我", "我考的时候")
SIMULATION_MARKERS = ("示范", "设定", "假如", "比如", "例如", "场景")
# R8: takeaway 练习/自检线索
TAKEAWAY_CUES = ("？", "?", "自查", "自检", "练习", "试着", "问自己", "检查",
                 "写出", "列出", "下次", "翻回", "对照")
# R10: emoji 调色板（base 字符，忽略变体选择符）
EMOJI_BASE_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2300-\u23FF\u2B00-\u2BFF]")
EMOJI_PALETTE_BASE = set("❗️🙅❌✅📌💡⏰🗣")
PERCENT_RE = re.compile(r"\d+(?:\.\d+)?%")


def _err(errors, rule, msg):
    errors.append(f"[{rule}] {msg}")


def _body_of(pending: dict) -> str:
    keys = ("tip_intro", "step1", "step2", "step3",
            "case_normal", "case_high", "pitfalls", "case_normal_note", "case_high_note")
    return "".join(pending.get(k, "") for k in keys)


def _content_tokens(text: str, min_len: int = 2) -> list:
    parts = re.split(r"[，。？?！!：:、；;（）()《》\"\"\"'·\s\n…—-]+", text)
    return [p for p in (s.strip() for s in parts) if len(p) >= min_len]


def _bigrams(text: str) -> set:
    """全部连续二字窗口（中文无分词依赖的轻量匹配单元）。"""
    return {text[i:i + 2] for i in range(len(text) - 1)}


_PUNCT_RE = re.compile(r"[\s，。？?！!：:、；;（）()《》\"\"\"'·…—\-，。\n\r\t]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")


def _content_bigrams(text: str) -> set:
    """只保留实词窗口：剥标点/空白后取二字窗口，剔除泛词与纯数字。"""
    cleaned = "".join(_CJK_RE.findall(text or ""))
    return {b for b in _bigrams(cleaned) if b not in GENERIC_BIGRAMS and not b.isdigit()}


def _strip_case_prefix(text: str) -> str:
    text = re.sub(r"^[🙅\u200d♂️👍]+\s*", "", text or "")
    text = re.sub(r"^(普通答法|高分答法)[：:]\s*", "", text)
    return text


# ---------- R3 标题兑现 ----------

def check_title_fulfilled(pending: dict, errors: list) -> None:
    title = pending.get("tip_title", "")
    body = _body_of(pending)
    segments = [t for t in _content_tokens(title) if t not in TITLE_STOPWORDS and not t.isdigit()]
    unaddressed = [seg for seg in segments
                   if seg not in body and not (_bigrams(seg) & _bigrams(body))]
    if unaddressed:
        _err(errors, "R3-标题兑现",
             f"标题分句 {unaddressed} 均未在正文展开，标题承诺未兑现: {title!r}")


# ---------- R4 对照同题同条件 ----------

def check_case_parity(pending: dict, errors: list) -> None:
    normal = _strip_case_prefix(pending.get("case_normal", ""))
    high = _strip_case_prefix(pending.get("case_high", ""))
    if not normal or not high:
        return
    n_ratio = len(high) / max(len(normal), 1)
    if n_ratio > CASE_LEN_RATIO_MAX:
        _err(errors, "R4-对照堆字",
             f"高分版 {len(high)} 字 ≈ 普通版 {len(normal)} 字的 {n_ratio:.1f} 倍"
             f"（上限 {CASE_LEN_RATIO_MAX}×），疑靠堆字取胜，请裁到同一关键改动")
    n_bg = _content_bigrams(normal)
    h_bg = _content_bigrams(high)
    anchor = n_bg & h_bg
    if not anchor:
        _err(errors, "R4-对照同题",
             "普通版与高分版无共同内容词，疑似不同题或不同条件，对照必须同题同身份同条件")


# ---------- R5 步数服从原方法 ----------

def _label_covered(label: str, text: str) -> bool:
    return label in text or bool(_bigrams(label) & _bigrams(text))


def check_step_method(pending: dict, meta: dict | None, errors: list) -> None:
    if not meta:
        return
    points = meta.get("method_points")
    labels = meta.get("point_labels") or []
    steps = [pending.get("step1", ""), pending.get("step2", ""), pending.get("step3", "")]
    if points == 2:
        if labels:
            missing = [lb for lb in labels
                       if not (_label_covered(lb, steps[0]) or _label_covered(lb, steps[1]))]
            if missing:
                _err(errors, "R5-两点法", f"原方法要点 {missing} 未落在 step1/step2")
        if not any(cue in steps[2] for cue in CHECK_CUES):
            _err(errors, "R5-两点法",
                 f"原方法只有两点，step3 应写应用或检查（线索词 {list(CHECK_CUES[:6])}…），"
                 f"不得凭空造第三点；当前 step3: {steps[2][:40]!r}")
    elif points == 4:
        all_steps = "".join(steps)
        missing = [lb for lb in labels if not _label_covered(lb, all_steps)]
        if missing:
            _err(errors, "R5-四点法",
                 f"原方法 4 要点须按原逻辑分组全部呈现（可分组不可删），缺失: {missing}")
    elif points == 3:
        for i, lb in enumerate(labels[:3]):
            if lb and not _label_covered(lb, steps[i]):
                _err(errors, "R5-三点法", f"要点 {lb!r} 未落在 step{i + 1}")


# ---------- R6 适用边界 ----------

def check_boundary(pending: dict, errors: list) -> None:
    pitfalls = pending.get("pitfalls", "")
    if not any(cue in pitfalls for cue in BOUNDARY_CUES):
        _err(errors, "R6-适用边界",
             f"避坑提醒缺少适用边界/常见误用/纠正动作（线索词如 {list(BOUNDARY_CUES[:8])}…）: {pitfalls[:40]!r}")


# ---------- R7 无虚构权威 ----------

def check_no_invented_authority(pending: dict, errors: list) -> None:
    for key in ("tip_title", "tip_intro", "step1", "step2", "step3",
                "case_normal", "case_normal_note", "case_high", "case_high_note",
                "pitfalls", "tip_takeaway"):
        text = pending.get(key, "")
        for banned in BANNED_AUTHORITY:
            if banned in text:
                _err(errors, "R7-虚构权威", f"{key} 出现禁语 {banned!r}：不替考官发言、不写无依据评分规则")
        if PERCENT_RE.search(text) and not any(m in text for m in SOURCE_MARKERS):
            _err(errors, "R7-无出处统计", f"{key} 出现百分比且无出处/示范标记: {PERCENT_RE.search(text).group()!r}")
        if any(m in text for m in EXPERIENCE_MARKERS) and not any(m in text for m in SIMULATION_MARKERS):
            _err(errors, "R7-冒充经历", f"{key} 疑似冒充作者经历，模拟例子须标'示范/设定'")


# ---------- R8 总结是练习 ----------

def check_takeaway(pending: dict, errors: list) -> None:
    takeaway = pending.get("tip_takeaway", "")
    if not any(cue in takeaway for cue in TAKEAWAY_CUES):
        _err(errors, "R8-总结是练习",
             f"一句话总结应改为微练习或自检问题（线索词 {list(TAKEAWAY_CUES[:7])}…）: {takeaway[:40]!r}")


# ---------- R9 一期一技巧 ----------

def check_focus(pending: dict, meta: dict | None, errors: list) -> None:
    if not meta:
        return
    kws = meta.get("focus_keywords") or []
    if kws and not any(k in pending.get("tip_intro", "") for k in kws):
        _err(errors, "R9-一期一技巧", f"破题未点出本期焦点 {kws}，一期只教一个主要技巧")


# ---------- R10 emoji 纪律 ----------

def check_emoji(pending: dict, errors: list) -> None:
    for key, text in pending.items():
        if not isinstance(text, str) or key == "tip_title":
            continue
        bases = EMOJI_BASE_RE.findall(text)
        if len(bases) > 2:
            _err(errors, "R10-emoji", f"{key} emoji 数 {len(bases)} 超过每段 2 个上限")
        outside = [ch for ch in dict.fromkeys(bases) if ch not in EMOJI_PALETTE_BASE]
        if outside:
            _err(errors, "R10-emoji", f"{key} 使用调色板外 emoji: {outside}（限 ❗️🙅❌✅📌💡⏰🗣）")


# ---------- R1/R2 索引检查 ----------

TYPE_DIR = {"综合分析题": "综合分析题", "应急应变题": "应急应变题", "人际关系题": "人际关系题",
            "组织计划题": "组织计划题", "自我认知题": "自我认知题", "言语表达题": "言语表达题"}


def _strip_frontmatter(text: str) -> str:
    """剥掉 YAML frontmatter（--- 包裹段），避免标签/引用文件名制造假共词。"""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def check_index(index_path: Path, errors: list) -> None:
    data = json.loads(index_path.read_text(encoding="utf-8"))
    root = Path(data.get("_meta", {}).get("source_root", ""))
    tips = data.get("tips", [])
    if data.get("_meta", {}).get("count") not in (None, len(tips)):
        _err(errors, "R1-索引元数据", f"_meta.count={data['_meta'].get('count')} 与实际 {len(tips)} 条不一致")
    for t in tips:
        tid, src = t.get("id", "?"), (t.get("src") or "").strip()
        if not src:
            _err(errors, "R2-来源缺失", f"{tid} 的 src 为空")
            continue
        path = root / src
        if not path.is_file():
            _err(errors, "R2-来源缺失", f"{tid} 的 src 文件不存在: {src}")
            continue
        # 题型目录一致性（common/通用条目豁免）
        types = t.get("types") or []
        is_generic = (not types) or types == ["全部题型"]
        if not is_generic:
            expected_dir = TYPE_DIR.get(types[0])
            if expected_dir and not src.startswith(expected_dir + "/"):
                _err(errors, "R1-错链", f"{tid} types={types} 但 src 在 {src.split('/')[0]} 目录: {src}")
        # note/name 须与 src 正文共享实词（抓跨主题错链；技巧级 note 不必写场景名，
        # 与原文改写共享领域词汇即可，阈值 2 个实词窗口）。
        # 全部题型（横切技巧）豁免：横切 note 概括的是例子的气质，不复述例词。
        if not is_generic:
            claim = _content_bigrams(t.get("name", "") + t.get("note", ""))
            try:
                body = _content_bigrams(_strip_frontmatter(
                    path.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                body = set()
            shared = claim & body
            if len(shared) < 2:
                _err(errors, "R1-错链",
                     f"{tid} 的 name/note 与 src 正文共享实词不足（{sorted(shared)[:6]}），疑错链: {src}")


# ---------- 入口 ----------

def run_content_checks(pending: dict, meta: dict | None) -> list:
    errors: list = []
    check_title_fulfilled(pending, errors)
    check_case_parity(pending, errors)
    check_step_method(pending, meta, errors)
    check_boundary(pending, errors)
    check_no_invented_authority(pending, errors)
    check_takeaway(pending, errors)
    check_focus(pending, meta, errors)
    check_emoji(pending, errors)
    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description="结构化答题技巧 内容自检器")
    ap.add_argument("--pending", help="pending_tips.json 路径")
    ap.add_argument("--meta", help="draft_meta.json 路径（可选）")
    ap.add_argument("--index", help="同时检查索引（tips_index.json 路径）")
    ap.add_argument("--check-index", help="只检查索引错链/来源")
    args = ap.parse_args()

    errors: list = []
    if args.check_index:
        p = Path(args.check_index)
        if not p.is_file():
            print(f"[ERROR] 索引不存在: {p}")
            sys.exit(EXIT_USAGE)
        try:
            check_index(p, errors)
        except json.JSONDecodeError as e:
            print(f"[ERROR] 索引 JSON 解析失败: {e}")
            sys.exit(EXIT_USAGE)

    if args.pending:
        p = Path(args.pending)
        if not p.is_file():
            print(f"[ERROR] pending 不存在: {p}")
            sys.exit(EXIT_USAGE)
        try:
            pending = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[ERROR] pending JSON 解析失败: {e}")
            sys.exit(EXIT_USAGE)
        meta = None
        if args.meta:
            mp = Path(args.meta)
            if not mp.is_file():
                print(f"[ERROR] meta 不存在: {mp}")
                sys.exit(EXIT_USAGE)
            meta = json.loads(mp.read_text(encoding="utf-8"))
        errors.extend(run_content_checks(pending, meta))

    if args.index:
        p = Path(args.index)
        if not p.is_file():
            print(f"[ERROR] 索引不存在: {p}")
            sys.exit(EXIT_USAGE)
        check_index(p, errors)

    if not args.pending and not args.check_index and not args.index:
        ap.print_help()
        sys.exit(EXIT_USAGE)

    if errors:
        print(f"[FAIL] 内容自检发现 {len(errors)} 个问题:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(EXIT_RULES)
    print("[OK] 内容自检通过")


if __name__ == "__main__":
    main()

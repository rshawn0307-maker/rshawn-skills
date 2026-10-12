#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内容门禁：pending_wushi.json vs《公务员务实手册》源稿。

三层检查：
  1. verbatim 一致性（R4-R8）—— 场景/步骤/红线/嵌入句/假大空对照必须与源稿逐字全等
     （normalize 口径：NFC + 弯引号归一 + 去空白与零宽字符）。源稿是唯一事实源，
     verbatim 字段不做禁词扫描（源稿本身已人工验收，R10 若扫 verbatim 会把
     源稿引用性用词误杀成死锁期，如应急岗「不演『万能剧』」）。
  2. 禁词扫描（R9/R10）—— 只扫自由文案字段；fake_compare.fake 是对照表里
     被批判的假大空原句，引用即本意，同样不扫。
     R9 七禁词仅对 body_note / pub_tips 做引号内豁免（品牌既定「痛点对照」
     批判写法）；titles / cover_hook / tags 不豁免。R10 合规词一律不豁免。
  3. 自由文案约束（R11-R17）—— 标题/钩子/正文/tags/长度上限。

成功后写 <pending>.passed 标记，gen_wushi_cards.py 凭该标记拒绝未过门禁的渲染。

用法:
  python3 check_wushi_content.py --pending pending_wushi.json [--source-dir DIR]
退出码: 0=全部通过  1=存在 FAIL（逐条打印，不许跳过）
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wushi_source import (  # noqa: E402
    DEFAULT_SOURCE_DIR, load_source, match_business, normalize, source_path,
)

FORBIDDEN_KONG = ["加强领导", "提高认识", "完善机制", "建立健全", "强化意识", "营造氛围", "形成合力"]
FORBIDDEN_COMPLY = [
    "保过", "包过", "稳过", "必过", "万能", "直接背", "押题", "内部渠道",
    "百分百", "一次过", "包上岸", "送分", "躺赢", "原题",
]
WENHAO_RE = re.compile(r"第\s*[0-9０-９]+\s*号|〔\d+〕")
QUOTE_SPAN_RE = re.compile(r"「[^」]*」|『[^』]*』")
ZW_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")

REQUIRED_FIELDS = [
    "issue", "post", "source_file", "business", "scene", "steps",
    "redlines", "embed", "fake_compare", "cover_hook", "titles",
    "body_note", "tags", "pub_tips", "human_writing",
]

# 长度上限（源稿 48 期实测最大值 + 余量；场景 50、嵌入句 102、步骤体 50、红线项 20）
LIMITS = {"scene": 120, "embed": 140, "step_body": 90, "step_lead": 12, "redline": 40}

results = []


def check(rid, ok, detail=""):
    results.append((rid, bool(ok), detail))


def free_fields(p):
    """禁词扫描范围：自由文案字段（verbatim 字段与 fake_compare 不在列）。"""
    out = [("$." + k, str(p[k])) for k in ("cover_hook", "body_note", "pub_tips")]
    out += [(f"$.titles[{i}]", str(t)) for i, t in enumerate(p["titles"])]
    out += [(f"$.tags[{i}]", str(t)) for i, t in enumerate(p["tags"])]
    return out


def scan_text(s):
    """零宽字符剥离后的可扫描文本（防零宽夹禁词）。"""
    return ZW_RE.sub("", str(s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pending", required=True)
    ap.add_argument("--source-dir", default=DEFAULT_SOURCE_DIR)
    args = ap.parse_args()

    # R0 可读 + schema + 类型
    pending_path = Path(args.pending)
    try:
        p = json.loads(pending_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] R0 pending 不可读: {e}")
        sys.exit(1)
    if not isinstance(p, dict):
        print("[FAIL] R0 pending 顶层必须是对象")
        sys.exit(1)

    missing = [k for k in REQUIRED_FIELDS if k not in p]
    check("R0-schema", not missing, f"缺失字段: {missing}" if missing else "字段齐全")
    types_ok = (
        isinstance(p.get("scene"), str) and isinstance(p.get("embed"), str)
        and isinstance(p.get("business"), str) and isinstance(p.get("post"), str)
        and isinstance(p.get("steps"), list) and all(
            isinstance(s, dict) and isinstance(s.get("lead"), str)
            and isinstance(s.get("body"), str) for s in p["steps"])
        and isinstance(p.get("redlines"), list) and all(isinstance(x, str) for x in p["redlines"])
        and isinstance(p.get("fake_compare"), dict)
        and isinstance(p.get("human_writing"), dict)
        and isinstance(p.get("titles"), list) and isinstance(p.get("tags"), list)
    )
    check("R0-types", types_ok,
          "字段类型正确" if types_ok else "类型错误（steps 须为 [{lead,body}]、redlines/titles/tags 须为 list、fake_compare/human_writing 须为 dict）")
    check("R0-issue", bool(re.fullmatch(r"\d{3}", str(p.get("issue")))),
          f"issue={p.get('issue')}（须三位数字）")
    if missing or not types_ok:
        _report()
        sys.exit(1)

    # R2 源稿定位
    post = str(p["post"]).strip()
    expected = f"{post}岗-公务员务实.md"
    check("R2-post", os.path.basename(str(p["source_file"])) == expected,
          f"source_file={p['source_file']} 期望 {expected}")
    src = source_path(args.source_dir, post)
    src_ok = os.path.isfile(src)
    check("R2-exists", src_ok, "源稿就位" if src_ok else f"源稿不存在: {src}")
    if not (results[-1][1] and results[-2][1]):
        _report()
        sys.exit(1)

    text, businesses, fake_rows = load_source(src)

    # R3 业务定位：必须唯一命中
    hits = match_business(businesses, str(p["business"]))
    if len(hits) == 1:
        check("R3-business", True, f"业务「{hits[0]['title']}」定位成功")
    else:
        check("R3-business", False,
              f"业务「{p['business']}」命中 {len(hits)} 条，候选: {[b['title'] for b in businesses]}")
        _report()
        sys.exit(1)
    b = hits[0]

    # R4-R7 verbatim 一致性
    check("R4-scene", normalize(p["scene"]) == normalize(b["scene"]),
          "场景 verbatim 一致" if normalize(p["scene"]) == normalize(b["scene"])
          else f"场景不一致:\n  pending: {p['scene']}\n  源稿  : {b['scene']}")

    ps, ss = p["steps"], b["steps"]
    check("R5-steps-count", len(ps) == len(ss),
          f"步骤数 pending={len(ps)} 源稿={len(ss)}")
    for i in range(min(len(ps), len(ss))):
        pn, sn = normalize(ps[i].get("lead", "")), normalize(ss[i]["lead"])
        pb, sb = normalize(ps[i].get("body", "")), normalize(ss[i]["body"])
        ok = pn == sn and pb == sb
        check(f"R5-step{i+1}", ok,
              f"第{i+1}步 verbatim 一致" if ok else
              f"第{i+1}步不一致:\n  pending: [{ps[i].get('lead','')}|{ps[i].get('body','')}]\n"
              f"  源稿  : [{ss[i]['lead']}|{ss[i]['body']}]")

    pr = [normalize(x) for x in p["redlines"]]
    sr = [normalize(x) for x in b["redlines"]]
    check("R6-redlines", pr == sr,
          f"红线 verbatim 一致（{len(sr)} 条）" if pr == sr else
          f"红线不一致:\n  pending: {p['redlines']}\n  源稿  : {b['redlines']}")

    check("R7-embed", normalize(p["embed"]) == normalize(b["embed"]),
          "嵌入句 verbatim 一致" if normalize(p["embed"]) == normalize(b["embed"])
          else f"嵌入句不一致:\n  pending: {p['embed']}\n  源稿  : {b['embed']}")
    check("R7-embed-end", bool(re.search(r"[。！？]$", str(p["embed"]).strip())),
          "嵌入句以句读收尾（单句闭环）")

    # R8 假大空对照必须取自源稿表
    fc = p["fake_compare"]
    ok8 = any(normalize(fc.get("fake")) == normalize(r["fake"])
              and normalize(fc.get("real")) == normalize(r["real"]) for r in fake_rows)
    check("R8-fake-compare", ok8 and bool(fake_rows),
          "对照行取自源稿表" if ok8 else
          f"对照行不在源稿表中（源稿 {len(fake_rows)} 行: {[(r['fake'], r['real']) for r in fake_rows]}）")

    # R9/R10 禁词扫描：只扫自由文案字段（见模块 docstring 的范围与豁免说明）
    bad9, bad10 = [], []
    for path, s in free_fields(p):
        t = scan_text(s)
        bad10 += [(path, w) for w in FORBIDDEN_COMPLY if w in t]
        t9 = QUOTE_SPAN_RE.sub("", t) if path in ("$.body_note", "$.pub_tips") else t
        bad9 += [(path, w) for w in FORBIDDEN_KONG if w in t9]
    check("R9-kong", not bad9, "七禁词 0 命中" if not bad9 else f"命中: {bad9}")
    check("R10-comply", not bad10, "合规词 0 命中" if not bad10 else f"命中: {bad10}")

    # R14 不得编造文号（自由文案字段）
    bad_w = [(path, s) for path, s in free_fields(p) if WENHAO_RE.search(scan_text(s))]
    check("R14-wenhao", not bad_w, "无编造文号" if not bad_w else f"疑似文号: {bad_w}")

    # R11-R13 自由文案约束
    titles = p["titles"]
    ok_t = len(titles) == 3 and all(
        isinstance(t, str) and t.strip() and len(t) <= 20 for t in titles)
    check("R11-titles", ok_t,
          f"标题 3 个且均 ≤20 字（长度: {[len(t) for t in titles]}）"
          if ok_t else f"标题须 3 个且各 ≤20 字（实际: {[len(str(t)) for t in titles]}）")
    if ok_t:
        check("R11-titles-distinct", len({normalize(t) for t in titles}) == 3, "标题互不相同")

    hook = str(p["cover_hook"]).strip()
    check("R12-hook", 0 < len(hook) <= 24, f"cover_hook {len(hook)} 字（1–24）")

    tags = p["tags"]
    check("R13-tags", len(tags) >= 6 and all(
        isinstance(t, str) and t.strip().startswith("#") for t in tags),
        f"tags ≥6 且带 #（实际 {len(tags)} 个）")

    check("R15-body", len(str(p["body_note"]).strip()) >= 50,
          f"正文 {len(str(p['body_note']).strip())} 字（≥50，防偷懒占位）")

    hw = p["human_writing"]
    check("R16-human-writing", hw.get("status") in ("used", "fallback")
          and (hw.get("status") != "fallback" or str(hw.get("note", "")).strip()),
          f"human_writing.status={hw.get('status')}"
          + ("（fallback 须给 note）" if hw.get("status") == "fallback"
             and not str(hw.get("note", "")).strip() else ""))

    # R17 渲染长度上限（超限交给人判，不许引擎静音截断）
    over = []
    if len(str(p["scene"])) > LIMITS["scene"]:
        over.append(("$.scene", f"{len(str(p['scene']))}>{LIMITS['scene']}"))
    if len(str(p["embed"])) > LIMITS["embed"]:
        over.append(("$.embed", f"{len(str(p['embed']))}>{LIMITS['embed']}"))
    for i, st in enumerate(p["steps"]):
        if len(st["body"]) > LIMITS["step_body"]:
            over.append((f"$.steps[{i}].body", f"{len(st['body'])}>{LIMITS['step_body']}"))
        if len(st["lead"]) > LIMITS["step_lead"]:
            over.append((f"$.steps[{i}].lead", f"{len(st['lead'])}>{LIMITS['step_lead']}"))
    for i, r in enumerate(p["redlines"]):
        if len(r) > LIMITS["redline"]:
            over.append((f"$.redlines[{i}]", f"{len(r)}>{LIMITS['redline']}"))
    check("R17-limits", not over, "各字段长度在渲染上限内" if not over else f"超限: {over}")

    _report()
    fails = [r for r in results if not r[1]]
    if not fails:
        marker = Path(str(pending_path) + ".passed")
        marker.write_text("ok\n", encoding="utf-8")
        print(f"[OK] 门禁标记已写: {marker}")
    sys.exit(0 if not fails else 1)


def _report():
    for rid, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {rid}: {detail}")
    n_ok = sum(1 for _, ok, _ in results if ok)
    print(f"— 共 {len(results)} 项，通过 {n_ok}，失败 {len(results) - n_ok} —")


if __name__ == "__main__":
    main()

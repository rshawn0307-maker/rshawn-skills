#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_voice.py — 内容「反程序化」门禁（结构化双线）

检查的不是错别字，是读者能感觉到的模板腔：
  R1 框架密度：answer 必须有 mindmap（≥4 分支、≥12 叶子），叶子要具体
  R2 开篇判断：opening 必须有取舍/定性判断，不能只复述题干
  R3 推进变化：三条 lead 不得同一种开头；「我」开头 ≤1；「第X步」≤1
  R4 现场细节：每个 point body 至少 2 个可核查细节（数字/角色/动作）
  R5 注水标语：体现了/彰显了/标志着/多措并举/高度重视… 一律 0
  R6 句子节奏：平均 ≤32 字、最长 ≤55，短句占比 ≥15%
  R7 边界意识：全篇至少一处说明适用边界（如果/遇到/前提/不适用）

用法：
  python3 check_voice.py --mode answer --final <final.json>
  python3 check_voice.py --mode tips   --final <final.json>
exit 0 = 无 FAIL（WARN 会打印但放行）；exit 1 = 有 FAIL。
"""
import argparse
import json
import re
import sys

BANNED = ["体现了", "彰显了", "标志着", "生动诠释", "有力推动", "有效提升",
          "多措并举", "综合施策", "高度重视", "加强管理", "持续推进", "全面落实"]
JUDGE = ["我认为", "本质", "核心", "必须", "不能", "关键是", "区别在", "问题在",
         "先", "优先级", "取舍", "宁可", "而不是"]
ROLE = ["保安", "窗口", "社区", "商家", "领导", "同事", "群众", "企业", "部门",
        "村委", "物业", "医院", "学校", "平台", "志愿者", "当事人"]
ACTION = ["打电话", "走访", "登记", "回访", "广播", "公示", "排查", "回访", "约谈",
          "答复", "告知", "上报", "协调", "通报", "公示", "留档", "签收"]
DETAIL = re.compile(r"\d+\s*(?:个|天|小时|分钟|工作日|元|%|米|人|次|份|户|家|条|张)")
BOUNDARY = re.compile(r"如果|遇到|一旦|前提|不适用|边界|除非|否则")


def sentences(text):
    return [s.strip() for s in re.split(r"[。！？；]", text) if s.strip()]


def body_of_answer(d):
    keys = ["opening", "point1_body", "point2_body", "point3_body", "closing"]
    return "。".join(str(d.get(k, "")) for k in keys)


def check_answer(d):
    fails, warns = [], []

    # R1 mindmap 密度
    mm = d.get("mindmap") or {}
    branches = mm.get("branches") or []
    if not mm:
        fails.append("R1 缺 mindmap：答一道必须给思维导图，否则框架密度不足")
    else:
        if len(branches) < 4:
            fails.append(f"R1 分支只有 {len(branches)} 条（要求 ≥4）")
        leaves = []
        def walk(n):
            kids = n.get("children") or []
            if not kids:
                leaves.append(n.get("label", ""))
            for k in kids:
                walk(k)
        for b in branches:
            walk(b)
        if len(leaves) < 12:
            fails.append(f"R1 叶子合计 {len(leaves)} 个（要求 ≥12）")
        short = [x for x in leaves if len(x) < 6]
        if short:
            fails.append(f"R1 叶子过短/过抽象（{len(short)} 个 <6 字）：{short[:3]}")

    # R2 开篇判断
    opening = str(d.get("opening", ""))
    if not any(w in opening for w in JUDGE):
        warns.append("R2 开篇未见取舍/定性判断（建议写成「必须是先X后Y，因为…」）")

    # R3 推进变化
    leads = [str(d.get(f"point{i}_lead", "")) for i in (1, 2, 3)]
    heads = [x[:2] for x in leads]
    if len(set(heads)) < 3:
        warns.append(f"R3 三条 lead 开头重复：{heads}")
    if sum(1 for x in leads if x.startswith("我")) > 1:
        fails.append("R3 三条 lead 里「我」开头超过 1 条（模板腔）")
    if sum(body_of_answer(d).count(f"第{x}步") for x in "一二三四五") > 1:
        fails.append("R3 「第X步」出现超过 1 次（把答案写成操作手册）")

    # R4 每点现场细节
    for i in (1, 2, 3):
        body = str(d.get(f"point{i}_body", ""))
        n_num = len(DETAIL.findall(body))
        n_role = sum(1 for w in ROLE if w in body)
        n_act = sum(1 for w in ACTION if w in body)
        score = n_num + min(n_role, 2) + min(n_act, 2)
        if score < 2:
            fails.append(f"R4 point{i}_body 现场细节不足（数字/角色/动作合计 {score} < 2）")

    # R5 注水标语（正文；引文保真区不豁免——本门禁只查新写稿）
    text = body_of_answer(d)
    for w in BANNED:
        if w in text:
            fails.append(f"R5 命中注水标语「{w}」")

    # R6 节奏
    sents = sentences(text)
    if sents:
        avg = sum(len(s) for s in sents) / len(sents)
        mx = max(len(s) for s in sents)
        short_ratio = sum(1 for s in sents if len(s) <= 12) / len(sents)
        if avg > 32:
            warns.append(f"R6 平均句长 {avg:.1f} 字（建议 ≤32）")
        if mx > 55:
            warns.append(f"R6 最长句 {mx} 字（建议 ≤55）")
        if short_ratio < 0.15:
            warns.append(f"R6 短句占比 {short_ratio:.0%}（建议 ≥15%，长短交替）")

    # R7 边界意识
    if not BOUNDARY.search(text):
        warns.append("R7 全篇没有适用边界（加一句「如果…就…」「遇到…则…」）")
    return fails, warns


def check_tips(d):
    fails, warns = [], []
    text_parts = [str(d.get("overview_intro", ""))]
    for t in d.get("tiers", []):
        for p in t.get("points", []):
            text_parts.append(str(p.get("lead", "")) + "。" + str(p.get("body", "")))
    text = "。".join(text_parts)

    for w in BANNED:
        if w in text:
            fails.append(f"R5 命中注水标语「{w}」")
    if sum(text.count(f"第{x}步") for x in "一二三四五") > 1:
        fails.append("R3 「第X步」出现超过 1 次")
    # 每档具体抓手：AIR 整档至少 1 个，Pro/Pro Max 逐点至少 1 个
    for ti, t in enumerate(d.get("tiers", []), 1):
        scores = []
        for p in t.get("points", []):
            body = str(p.get("body", ""))
            s = len(DETAIL.findall(body)) + sum(1 for w in ROLE if w in body) + \
                sum(1 for w in ACTION if w in body)
            scores.append(s)
        if ti == 1:
            if scores and max(scores) == 0:
                fails.append("R4 AIR 档整档缺具体抓手（数字/角色/动作全 0）")
        else:
            for pi, s in enumerate(scores, 1):
                if s < 1:
                    fails.append(f"R4 第 {ti} 档第 {pi} 点缺具体抓手（数字/角色/动作 0）")
    return fails, warns


def main(argv=None):
    ap = argparse.ArgumentParser(description="内容反程序化门禁")
    ap.add_argument("--mode", choices=["answer", "tips"], required=True)
    ap.add_argument("--final", required=True)
    args = ap.parse_args(argv)
    d = json.loads(open(args.final, encoding="utf-8").read())
    fails, warns = check_answer(d) if args.mode == "answer" else check_tips(d)
    for w in warns:
        print(f"[WARN] {w}")
    for f in fails:
        print(f"[FAIL] {f}")
    if fails:
        print(f"共 {len(fails)} 项 FAIL，返工后再跑")
        return 1
    print(f"[PASS] 无 FAIL（{len(warns)} 项 WARN）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

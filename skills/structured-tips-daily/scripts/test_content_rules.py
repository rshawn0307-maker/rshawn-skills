#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_content_rules.py v2.0 -- 内容自检器自测（content_rules.py 的配套测试）

测试对象：本 skill 的 scripts/content_rules.py（内容层规则）。
不依赖真实项目数据；索引用例使用内联 fixture，另有一条用例对真实索引跑索引检查
（真实索引须处于已校准状态，用例失败说明索引被改坏，不是检查器的问题）。

安全约定：全程进程内调用（无 subprocess、无 shell）；CLI 行为通过改写 sys.argv
调用 content_rules.main() 并捕获 SystemExit 验证退出码。

用法：
    python3 test_content_rules.py                # 全量
    python3 test_content_rules.py 错链 标题      # 按关键字筛选（仅做用例名包含匹配）

2026-09-08 v2.0：按内容审核反例清单补拦截用例（7 类反例 + 条件词负样本）：
    R0 读源记录必填 / R14 审稿记录与审稿结论 / R4-点评有据（停电"随口保证"反例、
    "没说明 vs 说错"正例、无锚点点评）/ R4-偷加事实（数字）/ R5-多点法（五点法漏教）/
    R7-模糊归因（某调查）/ R7-来源不符（虚假来源）/ R8 空洞反问与回顾式练习 /
    R4 对照 1.5× 边界 / 条件词（可能/若/待核实）不误杀。
用例与规则对应（不通过即 exit 1，筛选 0 用例也 exit 1，不允许假绿）。
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import content_rules as cr  # noqa: E402

REAL_INDEX = Path.home() / "Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/结构化/scripts/tips_index.json"

GOOD_PENDING = {
    "tip_title": "调研对象列完了，分别问什么？",
    "question_type": "适用题型：组织计划题·调研类",
    "tip_intro": "破题角度：调研问得空，多半是对象和信息没对上。这期教你调研对象该问什么。",
    "step1": "第一步：先把对象分层，独居老人问送餐就医安全，同住老人问文娱社交。",
    "step2": "第二步：给每类人定一个调研重点，问题跟着重点走。",
    "step3": "第三步：答完自查，每个对象后面跟的是不是它最想要的信息。",
    "case_normal": "普通答法：我会围绕辖区养老需求开展调研，发放问卷了解老人的需要，再汇总上报。",
    "case_normal_note": "点评：调研只会发问卷，对象笼统，问不出差别，收上来多是泛泛报告。",
    "case_high": "高分答法：示范。调研同样的养老需求，独居老人上门问送餐就医，同住老人问文娱，机构家属问护理费用。",
    "case_high_note": "点评：改动只有一处，每个对象后面跟了它最想要的信息，需求清单能排序。",
    "pitfalls_lead": "避坑提醒：",
    "pitfalls": "这招适用于需求差异大的调研；如果对象需求单一，按规则分层反而添步骤，只保留核实底数即可。",
    "tip_takeaway": "下次写调研时，试着给每类人补一句：我最想从他这知道什么？",
    "hashtags": "#公考面试 #结构化面试 #组织计划 #答题技巧 #上岸",
}

# v2.0 完整读源与审稿记录（draft_meta.json 必填版）
GOOD_META = {
    "skill_version": "2.2.0",
    "tip_id": "zzzz-03",
    "method_points": 2,
    "point_labels": ["分层", "重点"],
    "focus_keywords": ["对象", "问什么"],
    "sources": [
        "02_答题方法与框架/组织计划方法论提炼.md#调研对象",
        "题库/组织计划题/组织计划-03-养老调研.md",
    ],
    "quote_excerpts": ["调研对象要分层，每类对象围绕其最关心的信息设问"],
    "applicable_conditions": "需求差异明显的群体；题骨前提：先摸底数",
    "shared_context": "同一道社区养老调研题，考生身份是街道工作人员，题干给定辖区有独居和同住老人",
    "key_change": "每个调研对象后面跟一个它最想要的信息",
    "actionable_demo": "问'最近一次去医院，出行是谁帮忙安排的？'答出靠家属安排的，优先补出行支持",
    "exercise_criteria": "新场景：社区活动室改造需求调研；自检要素：对象分层、每类配信息、信息落清单",
    "title_candidates": ["调研对象列完了，分别问什么？", "调研别再泛泛问，对象配问题",
                         "考官想听的：调研分别问什么"],
    "review_conclusion": "通过",
}


def errs_for(pending: dict, meta: dict | None = None) -> list:
    return cr.run_content_checks(json.loads(json.dumps(pending)), meta)


def errs_for_req(pending: dict, meta: dict | None = None) -> list:
    """带 require_meta=True 的进程内检查（模拟 CLI 门禁）。"""
    return cr.run_content_checks(json.loads(json.dumps(pending)), meta, require_meta=True)


def has_err(errors: list, tag: str) -> bool:
    return any(tag in e for e in errors)


def make_index(tmp: Path, tips: list, seq: int, source_root: str = "/nonexistent-root") -> Path:
    data = {"_meta": {"source_root": source_root, "count": len(tips)}, "tips": tips}
    p = tmp / f"index_fixture_{seq}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def invoke_main(argv_tail: list) -> tuple[int, str]:
    """进程内跑 content_rules.main()：改 argv + 捕获 stdout/SystemExit。"""
    saved_argv, saved_stdout = sys.argv, sys.stdout
    sys.argv = ["content_rules.py"] + [str(a) for a in argv_tail]
    buf = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            cr.main()
    except SystemExit as e:  # noqa: BLE001 main 用 sys.exit 报退出码
        code = e.code if isinstance(e.code, int) else 1
    finally:
        sys.argv, sys.stdout = saved_argv, saved_stdout
    return code, buf.getvalue()


# ---------- 用例 ----------

def case_golden():
    """干净样例 + 完整读源审稿记录全量通过。"""
    errors = errs_for(GOOD_PENDING, GOOD_META)
    return (not errors, f"黄金样例应零错误，实际: {errors}")


def case_golden_no_meta():
    """无 meta（单测级）时跳过步数/焦点/审稿记录检查，其余仍须通过。"""
    errors = errs_for(GOOD_PENDING, None)
    return (not errors, f"无 meta 黄金样例应零错误，实际: {errors}")


def case_r0_meta_required_via_main():
    """R0: CLI --pending 缺 --meta 即拒绝（读源与审稿记录必填）。"""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "pending_fixture.json"
        p.write_text(json.dumps(GOOD_PENDING, ensure_ascii=False), encoding="utf-8")
        code, out = invoke_main(["--pending", p])
        ok = code == 5 and "R0-读源记录" in out
        return (ok, f"缺 meta 应 exit 5 且点名 R0，实际 exit={code}\n{out}")


def case_r14_record_incomplete():
    """R14: 旧版三字段 meta（无审稿记录）应逐项点名缺失。"""
    old_meta = {"method_points": 2, "point_labels": ["分层", "重点"],
                "focus_keywords": ["对象"]}
    errors = errs_for_req(GOOD_PENDING, old_meta)
    ok = (has_err(errors, "R14-审稿记录") and has_err(errors, "R14-审稿结论")
          and sum("R14-审稿记录" in e for e in errors) >= 3)
    return (ok, f"应检出审稿记录多字段缺失与审稿结论缺失，实际: {errors}")


def case_r14_review_not_passed():
    """R14: review_conclusion 不是'通过'不得放行。"""
    meta = dict(GOOD_META)
    meta["review_conclusion"] = "整体还行，个别点评再看看"
    errors = errs_for_req(GOOD_PENDING, meta)
    return (has_err(errors, "R14-审稿结论"),
            f"审稿未通过应拦截，实际: {errors}")


def case_index_wrong_link():
    """R1: src 主题与 name/note 无关（复刻真实 zhf-06 错链）。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src_dir = tmp / "综合分析题"
        src_dir.mkdir()
        (src_dir / "综合分析-01-指尖形式主义.md").write_text("# 指尖形式主义", encoding="utf-8")
        idx = make_index(tmp, [{"id": "x-01", "name": "被领导误会：先分清信息差",
                                "types": ["综合分析题"], "src": "综合分析题/综合分析-01-指尖形式主义.md",
                                "note": "被领导误会先别急着解释"}], seq=1, source_root=str(tmp))
        errors = []
        cr.check_index(idx, errors)
        return (any("共享实词不足" in e for e in errors),
                f"应检出主题词不匹配错链，实际: {errors}")


def case_index_type_dir_mismatch():
    """R1: types 与 src 目录不一致。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        d = tmp / "人际关系题"
        d.mkdir()
        (d / "人际关系-07-领导误会.md").write_text("# 领导误会", encoding="utf-8")
        idx = make_index(tmp, [{"id": "x-02", "name": "领导误会：私下澄清",
                                "types": ["综合分析题"], "src": "人际关系题/人际关系-07-领导误会.md",
                                "note": "不当众解释"}], seq=2, source_root=str(tmp))
        errors = []
        cr.check_index(idx, errors)
        return (any("types" in e for e in errors), f"应检出 types 与目录不一致，实际: {errors}")


def case_index_source_missing():
    """R2: src 文件不存在 / src 为空。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        idx = make_index(tmp, [
            {"id": "x-03", "name": "某技巧", "types": [], "src": "综合分析题/不存在.md", "note": "n"},
            {"id": "x-04", "name": "另技巧", "types": [], "src": "", "note": "n"},
        ], seq=3, source_root=str(tmp))
        errors = []
        cr.check_index(idx, errors)
        ok = sum(1 for e in errors if "R2-来源缺失" in e) >= 2
        return (ok, f"应检出文件不存在与 src 为空两类来源缺失，实际: {errors}")


def case_index_count_mismatch():
    """R1: _meta.count 与实际条数不一致。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        idx = make_index(tmp, [{"id": "x-05", "name": "技巧", "types": [], "src": "", "note": "n"}], seq=4)
        idx_data = json.loads(idx.read_text(encoding="utf-8"))
        idx_data["_meta"]["count"] = 36
        idx.write_text(json.dumps(idx_data, ensure_ascii=False), encoding="utf-8")
        errors = []
        cr.check_index(idx, errors)
        return (any("_meta.count" in e for e in errors), f"应检出 count 元数据不一致，实际: {errors}")


def case_title_unfulfilled():
    """R3: 标题说的正文没讲。"""
    bad = dict(GOOD_PENDING)
    bad["tip_title"] = "答辩时怎么让声音不发抖？"
    errors = errs_for(bad, None)
    return (has_err(errors, "R3-标题兑现"), f"应检出标题未兑现，实际: {errors}")


def case_parity_padded():
    """R4: 高分版靠堆字取胜。"""
    bad = dict(GOOD_PENDING)
    bad["case_high"] = "高分答法：示范。调研同样的养老需求，" + "我会认真了解各方面情况并且做好记录整理和上报工作，" * 4
    errors = errs_for(bad, None)
    return (has_err(errors, "R4-对照堆字"), f"应检出对照堆字，实际: {errors}")


def case_ratio_boundary_15x():
    """R4: 1.5× 口径——约 1.2× 放行，约 2× 拦截（去前缀计）。"""
    pass_case = dict(GOOD_PENDING)
    pass_case["case_high"] = ("高分答法：示范。同样调研养老需求，我把对象拆开问，"
                              "每类配一个最想要的信息，需求能直接排序。")
    errors_pass = errs_for(pass_case, None)
    fail_case = dict(pass_case)
    fail_case["case_high"] = pass_case["case_high"] + "并认真做好记录，形成需求清单，便于后续对接部门逐项落实到位。"
    errors_fail = errs_for(fail_case, None)
    ok = (not has_err(errors_pass, "R4-对照堆字")) and has_err(errors_fail, "R4-对照堆字")
    return (ok, f"1.2× 应放行（实际: {errors_pass}），2× 应拦截（实际: {errors_fail}）")


def case_parity_different_question():
    """R4: 高分版换了题/换了条件。"""
    bad = dict(GOOD_PENDING)
    bad["case_high"] = "高分答法：示范。先成立舆情监测专班，逐条比对转发链条，再统一口径对外发声。"
    errors = errs_for(bad, None)
    ok = has_err(errors, "R4-对照同题")
    return (ok, f"应检出对照疑似换题，实际: {errors}")


def case_note_allege_unfounded():
    """R4-点评有据（停电试点反例）：原话没承诺时间，点评却批'随口保证'。"""
    bad = dict(GOOD_PENDING)
    bad["case_normal"] = ("普通答法：我会先安抚群众情绪，向大家说明停电是突发情况，"
                          "请大家耐心等待，同时联系供电部门尽快抢修，争取早日恢复供电。")
    bad["case_normal_note"] = "点评：“争取早日恢复”听着积极，其实是随口保证。到点没恢复，信任就没了。"
    errors = errs_for(bad, GOOD_META)
    ok = has_err(errors, "R4-点评有据") and any("随口保证" in e for e in errors)
    return (ok, f"应检出批评无据（指控词原话无对应），实际: {errors}")


def case_note_absence_vs_misstate():
    """R4 正例：'没有说明X'式公允批评不误杀（区分没说明与说错）。"""
    case = dict(GOOD_PENDING)
    case["case_normal"] = ("普通答法：我会先安抚群众情绪，向大家说明停电是突发情况，"
                           "请大家耐心等待，同时联系供电部门尽快抢修，争取早日恢复供电。")
    case["case_normal_note"] = "点评：“争取早日恢复”听着积极，但没有说明下一次什么时候通报消息，群众只能一直等。"
    errors = errs_for(case, GOOD_META)
    return (not has_err(errors, "R4-点评有据"),
            f"'没有说明'式批评不应拦截，实际: {errors}")


def case_note_no_anchor():
    """R4-点评有据：点评与普通答法无共同实词（没评这句话）。"""
    bad = dict(GOOD_PENDING)
    bad["case_normal_note"] = "点评：整体状态气质不错，临场表现值得保持。"
    errors = errs_for(bad, None)
    return (has_err(errors, "R4-点评有据"), f"应检出点评无锚点，实际: {errors}")


def case_new_fact_added():
    """R4-偷加事实：高分版无来源新数字拦截；'比如'示例豁免。"""
    bad = dict(GOOD_PENDING)
    bad["case_high"] = "高分答法：示范。调研同样的养老需求，我把对象拆开问，2 小时内汇总需求清单对接部门。"
    errors_bad = errs_for(bad, None)
    ok_bad = has_err(errors_bad, "R4-偷加事实")
    good = dict(GOOD_PENDING)
    good["case_high"] = "高分答法：示范。调研同样的养老需求，我把对象拆开问，比如 2 小时内汇总需求清单。"
    errors_good = errs_for(good, None)
    ok_good = not has_err(errors_good, "R4-偷加事实")
    return (ok_bad and ok_good,
            f"无来源新数字应拦（实际: {errors_bad}），'比如'示例应放行（实际: {errors_good}）")


def case_two_point_method_invented_step3():
    """R5: 两点法凭空造第三步 + 丢要点。"""
    bad = dict(GOOD_PENDING)
    bad["step2"] = "第二步：问题跟着对象走，逐类列出关注点。"
    bad["step3"] = "第三步：要高度重视调研成果转化，深入推进落实。"
    meta = {"method_points": 2, "point_labels": ["分层", "重点"]}
    errors = errs_for(bad, meta)
    ok = has_err(errors, "R5-两点法") and sum("R5-两点法" in e for e in errors) >= 2
    return (ok, f"应同时检出造第三点与要点缺失，实际: {errors}")


def case_four_point_method_missing_label():
    """R5: 四点法分组后丢关键条件。"""
    meta = {"method_points": 4, "point_labels": ["底数", "分层", "方式", "转化"]}
    errors = errs_for(GOOD_PENDING, meta)
    ok = has_err(errors, "R5-多点法") and any("底数" in e and "方式" in e for e in errors)
    return (ok, f"应检出四点中缺失的 底数/方式，实际: {errors}")


def case_five_point_method_missing_labels():
    """R5（审计反例）：五点法漏教须拦截。"""
    meta = {"method_points": 5, "point_labels": ["底数", "分层", "重点", "方式", "转化"]}
    errors = errs_for(GOOD_PENDING, meta)
    err_text = "".join(e for e in errors if "R5-多点法" in e)
    ok = has_err(errors, "R5-多点法") and all(w in err_text for w in ("底数", "方式", "转化"))
    return (ok, f"五点法缺 底数/方式/转化 应全部点名，实际: {errors}")


def case_boundary_missing():
    """R6: 避坑没有边界/误用/纠正。"""
    bad = dict(GOOD_PENDING)
    bad["pitfalls"] = "别一上来就说高度重视，要切实保障调研质量，多措并举抓好落实。"
    errors = errs_for(bad, None)
    return (has_err(errors, "R6-适用边界"), f"应检出遗漏适用边界，实际: {errors}")


def case_invented_authority():
    """R7: 考官内心/无出处统计/冒充经历三连。"""
    bad = dict(GOOD_PENDING)
    bad["case_normal_note"] = "点评：考官内心：又来一个背模板的，听了就加分。"
    bad["tip_intro"] = "破题角度：73% 的考生调研都答空。这期教你调研对象该问什么。"
    bad["case_high"] = "高分答法：我当年考场上就是这么答的，独居老人上门问送餐就医。"
    errors = errs_for(bad, None)
    ok = (has_err(errors, "R7-虚构权威") and has_err(errors, "R7-无出处统计")
          and has_err(errors, "R7-冒充经历"))
    return (ok, f"应同时检出三类虚构权威问题，实际: {errors}")


def case_vague_attribution():
    """R7（审计反例）：'据某调查显示'式虚假来源直接拦截。"""
    bad = dict(GOOD_PENDING)
    bad["tip_intro"] = "破题角度：据某调查显示，多数考生调研都答空。这期教你调研对象该问什么。"
    errors = errs_for(bad, None)
    ok = has_err(errors, "R7-模糊归因") and any("某调查" in e for e in errors)
    return (ok, f"应检出模糊归因，实际: {errors}")


def case_cite_source_mismatch():
    """R7（审计反例）：具体引用与读源记录 sources 对不上。"""
    bad = dict(GOOD_PENDING)
    bad["case_high"] = "高分答法：示范。数据显示分层问需的调研更易转化，独居老人上门问送餐就医。"
    meta = dict(GOOD_META)
    meta["sources"] = ["02_答题方法与框架/人际关系方法论提炼.md#情绪优先"]
    errors = errs_for(bad, meta)
    ok = has_err(errors, "R7-来源不符") and any("sources" in e for e in errors)
    return (ok, f"引用与 sources 对不上应拦截，实际: {errors}")


def case_takeaway_not_practice():
    """R8: 总结是感想不是练习。"""
    bad = dict(GOOD_PENDING)
    bad["tip_takeaway"] = "说到底，调研考验的是责任心。"
    errors = errs_for(bad, None)
    return (has_err(errors, "R8-总结是练习"), f"应检出总结不是练习，实际: {errors}")


def case_takeaway_hollow_question():
    """R8（审计反例）：空洞反问冒充练习。"""
    bad = dict(GOOD_PENDING)
    bad["tip_takeaway"] = "说到底，调研答得好不好，是不是就看用心？"
    errors = errs_for(bad, None)
    ok = has_err(errors, "R8-总结是练习") and any("纯反问" in e for e in errors)
    return (ok, f"空洞反问应拦截，实际: {errors}")


def case_takeaway_review_style():
    """R8（审计反例）：回顾原答案式练习应换成新场景任务。"""
    bad = dict(GOOD_PENDING)
    bad["tip_takeaway"] = "改写一下你上次的应急答案，看三样有没有分开。"
    errors = errs_for(bad, None)
    ok = has_err(errors, "R8-练习迁移") and any("新场景" in e for e in errors)
    return (ok, f"回顾式练习应拦截，实际: {errors}")


def case_normal_gongkao_words_not_flagged():
    """负样本：正常公考用语与必要条件词（若/可能/待核实）不误杀。"""
    ok_case = dict(GOOD_PENDING)
    ok_case["pitfalls"] = ("这套问法适用于需求差异明显的调研；若上级已统一部署指标，"
                           "以制度为准套用既有口径即可，别为了分层另起炉灶。")
    ok_case["case_normal"] = "普通答法：我会按轻重缓急安排调研，先容缺受理问卷设计，再汇总上报。"
    ok_case["case_high"] = "高分答法：示范。同样按轻重缓急排任务，但先给每类对象定好要问的重点再上门。"
    ok_case["case_high_note"] = "点评：和普通版一样按轻重缓急安排调研，改动在先给每类对象定重点，答完可自查一遍。"
    errors = errs_for(ok_case, GOOD_META)
    return (not errors, f"正常公考用语与条件词不应报错，实际: {errors}")


def case_emoji_discipline():
    """R10: emoji 超量/调色板外。"""
    bad = dict(GOOD_PENDING)
    bad["tip_intro"] = "破题角度：调研问得空 🎯🔥✨ 这期教你调研对象该问什么。"
    errors = errs_for(bad, None)
    ok = has_err(errors, "R10-emoji") and sum("R10-emoji" in e for e in errors) >= 2
    return (ok, f"应检出 emoji 超量与调色板外，实际: {errors}")


def case_title_brand_style():
    """候选句式：标题与正文用'考官想听'均不触发 R7；'考官内心'仍拦截。"""
    brand = dict(GOOD_PENDING)
    brand["tip_title"] = "考官想听的：调研分别问什么"
    brand["tip_intro"] = "破题角度：考官想听的是每个对象后面都跟着问题。这期教你调研对象分别问什么。"
    errors = errs_for(brand, None)
    ok_no_flag = not has_err(errors, "R7-虚构权威")
    flagged = dict(brand)
    flagged["case_normal_note"] = "点评：考官内心：又来一个背模板的。"
    errors2 = errs_for(flagged, None)
    ok_flag = has_err(errors2, "R7-虚构权威")
    return (ok_no_flag and ok_flag,
            f"标题句式应放行（实际: {errors}），正文考官内心应拦截（实际: {errors2}）")


def case_golden_via_main():
    """入口: 黄金样例 + 完整 meta 走 main() 须 exit 0。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        p = tmp / "pending_fixture.json"
        m = tmp / "meta_fixture.json"
        p.write_text(json.dumps(GOOD_PENDING, ensure_ascii=False), encoding="utf-8")
        m.write_text(json.dumps(GOOD_META, ensure_ascii=False), encoding="utf-8")
        code, out = invoke_main(["--pending", p, "--meta", m])
        return (code == 0, f"黄金样例应 exit 0，实际 exit={code}\n{out}")


def case_real_index_via_main():
    """入口: 真实已校准索引走 main() 须 exit 0（失败=索引被改坏）。"""
    if not REAL_INDEX.is_file():
        return (True, "跳过：真实索引不存在（非本机环境）")
    code, out = invoke_main(["--check-index", REAL_INDEX])
    return (code == 0, f"真实索引应通过，exit={code}\n{out}")


def case_bad_pending_via_main():
    """入口: 坏 pending 应 exit 5 并逐条报错（缺 meta 时 R0 一并点名）。"""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "pending_fixture.json"
        bad = dict(GOOD_PENDING)
        bad["tip_takeaway"] = "说到底，调研考验的是责任心。"
        p.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        code, out = invoke_main(["--pending", p])
        ok = code == 5 and "R8-总结是练习" in out and "R0-读源记录" in out
        return (ok, f"应 exit 5 且点名 R8 与 R0，实际 exit={code}\n{out}")


CASES = [
    ("golden", case_golden),
    ("golden无meta单测级", case_golden_no_meta),
    ("R0缺meta入口", case_r0_meta_required_via_main),
    ("R14记录不全", case_r14_record_incomplete),
    ("R14审稿未通过", case_r14_review_not_passed),
    ("索引错链", case_index_wrong_link),
    ("索引题型目录", case_index_type_dir_mismatch),
    ("来源缺失", case_index_source_missing),
    ("索引count元数据", case_index_count_mismatch),
    ("标题未兑现", case_title_unfulfilled),
    ("对照堆字", case_parity_padded),
    ("对照1.5倍边界", case_ratio_boundary_15x),
    ("对照换题", case_parity_different_question),
    ("点评凭空指控", case_note_allege_unfounded),
    ("点评没说明vs说错", case_note_absence_vs_misstate),
    ("点评无锚点", case_note_no_anchor),
    ("偷加数字事实", case_new_fact_added),
    ("两点法造第三步", case_two_point_method_invented_step3),
    ("四点法丢条件", case_four_point_method_missing_label),
    ("五点法漏教", case_five_point_method_missing_labels),
    ("遗漏适用边界", case_boundary_missing),
    ("虚构权威", case_invented_authority),
    ("模糊归因某调查", case_vague_attribution),
    ("来源不符", case_cite_source_mismatch),
    ("总结不是练习", case_takeaway_not_practice),
    ("空洞反问", case_takeaway_hollow_question),
    ("回顾式练习", case_takeaway_review_style),
    ("正常用语不误报", case_normal_gongkao_words_not_flagged),
    ("emoji纪律", case_emoji_discipline),
    ("标题候选句式放行", case_title_brand_style),
    ("golden入口带meta", case_golden_via_main),
    ("真实索引入口", case_real_index_via_main),
    ("坏pending入口", case_bad_pending_via_main),
]


def main() -> None:
    keywords = sys.argv[1:]
    selected = [(name, fn) for name, fn in CASES
                if not keywords or any(k in name for k in keywords)]
    if not selected:
        print(f"[FAIL] 关键字 {keywords} 筛选出 0 个用例，不允许假绿")
        sys.exit(1)
    failed = 0
    for name, fn in selected:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001 用例自身异常一律算失败
            ok, detail = False, f"{type(e).__name__}: {e}"
        mark = "✅" if ok else "❌"
        print(f"{mark} {name}" + ("" if ok else f"\n   {detail}"))
        if not ok:
            failed += 1
    print(f"\n{'=' * 46}\n内容自检器自测: {len(selected) - failed}/{len(selected)} 通过")
    if failed:
        print(f"[FAIL] {failed} 个用例失败")
        sys.exit(1)
    print("[OK] 全部通过")


if __name__ == "__main__":
    main()

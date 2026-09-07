#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_content_rules.py v1.0 -- 内容自检器自测（content_rules.py 的配套测试）

测试对象：本 skill 的 scripts/content_rules.py（内容层规则）。
不依赖真实项目数据；索引用例使用内联 fixture，另有一条用例对真实索引跑索引检查
（真实索引须处于已校准状态，用例失败说明索引被改坏，不是检查器的问题）。

安全约定：全程进程内调用（无 subprocess、无 shell）；CLI 行为通过改写 sys.argv
调用 content_rules.main() 并捕获 SystemExit 验证退出码。

用法：
    python3 test_content_rules.py                # 全量
    python3 test_content_rules.py 错链 标题      # 按关键字筛选（仅做用例名包含匹配）

用例与规则对应（不通过即 exit 1，筛选 0 用例也 exit 1，不允许假绿）：
    索引错链(R1) / 来源缺失(R2) / 标题未兑现(R3) / 对照堆字+换条件(R4)
    两点法造第三步(R5) / 四点法丢条件(R5) / 遗漏适用边界(R6)
    虚构权威+无出处统计+冒充经历(R7) / 总结不是练习(R8)
    正常公考用语不误报(R-负样本) / 干净样例黄金路径 / 真实索引入口
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
    "step1": "第一步：先把调研对象分层，独居老人问送餐就医安全，同住老人问文娱社交。",
    "step2": "第二步：给每类人定一个调研重点，问题跟着重点走。",
    "step3": "第三步：答完自查，每个对象后面跟的是不是它最想要的信息。",
    "case_normal": "普通答法：我会围绕辖区养老需求开展调研，发放问卷了解老人的需要，再汇总上报。",
    "case_normal_note": "点评：对象笼统，问不出差别，成果只能是一份泛泛报告。",
    "case_high": "高分答法：示范。调研同样的养老需求，独居老人上门问送餐就医，同住老人问文娱，机构家属问护理费用。",
    "case_high_note": "点评：对象和信息一一对上，清单能直接对接部门。",
    "pitfalls_lead": "避坑提醒：",
    "pitfalls": "这招适用于需求差异大的调研；如果对象需求单一，按规则分层反而添步骤，只保留核实底数即可。",
    "tip_takeaway": "下次写调研对象时，试着给每类人补一句：我最想从他这知道什么？",
    "hashtags": "#公考面试 #结构化面试 #组织计划 #答题技巧 #上岸",
}
GOOD_META = {"method_points": 2, "point_labels": ["分层", "重点"], "focus_keywords": ["对象", "问什么"]}


def errs_for(pending: dict, meta: dict | None = None) -> list:
    return cr.run_content_checks(json.loads(json.dumps(pending)), meta)


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
    """干净样例 + meta 全量通过。"""
    errors = errs_for(GOOD_PENDING, GOOD_META)
    return (not errors, f"黄金样例应零错误，实际: {errors}")


def case_golden_no_meta():
    """无 meta 时跳过步数/焦点检查，其余仍须通过。"""
    errors = errs_for(GOOD_PENDING, None)
    return (not errors, f"无 meta 黄金样例应零错误，实际: {errors}")


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


def case_parity_different_question():
    """R4: 高分版换了题/换了条件。"""
    bad = dict(GOOD_PENDING)
    bad["case_high"] = "高分答法：示范。先成立舆情监测专班，逐条比对转发链条，再统一口径对外发声。"
    errors = errs_for(bad, None)
    ok = has_err(errors, "R4-对照同题")
    return (ok, f"应检出对照疑似换题，实际: {errors}")


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
    ok = has_err(errors, "R5-四点法") and any("底数" in e and "方式" in e for e in errors)
    return (ok, f"应检出四点中缺失的 底数/方式，实际: {errors}")


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


def case_takeaway_not_practice():
    """R8: 总结是感想不是练习。"""
    bad = dict(GOOD_PENDING)
    bad["tip_takeaway"] = "说到底，调研考验的是责任心。"
    errors = errs_for(bad, None)
    return (has_err(errors, "R8-总结是练习"), f"应检出总结不是练习，实际: {errors}")


def case_normal_gongkao_words_not_flagged():
    """负样本：正常公考用语（轻重缓急/容缺/以制度为准）不误报。"""
    ok_case = dict(GOOD_PENDING)
    ok_case["pitfalls"] = ("这套问法适用于需求差异明显的调研；若上级已统一部署指标，"
                           "以制度为准套用既有口径即可，别为了分层另起炉灶。")
    ok_case["case_normal"] = "普通答法：我会按轻重缓急安排调研，先容缺受理问卷设计，再汇总上报。"
    ok_case["case_high"] = "高分答法：示范。同样按轻重缓急排任务，但先给每类对象定好要问的重点再上门。"
    errors = errs_for(ok_case, GOOD_META)
    return (not errors, f"正常公考用语不应报错，实际: {errors}")


def case_emoji_discipline():
    """R10: emoji 超量/调色板外。"""
    bad = dict(GOOD_PENDING)
    bad["tip_intro"] = "破题角度：调研问得空 🎯🔥✨ 这期教你调研对象该问什么。"
    errors = errs_for(bad, None)
    ok = has_err(errors, "R10-emoji") and sum("R10-emoji" in e for e in errors) >= 2
    return (ok, f"应检出 emoji 超量与调色板外，实际: {errors}")


def case_title_brand_style():
    """定稿句式：标题与正文用"考官想听"均不触发 R7；"考官内心"仍拦截。"""
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


def case_real_index_via_main():
    """入口: 真实已校准索引走 main() 须 exit 0（失败=索引被改坏）。"""
    if not REAL_INDEX.is_file():
        return (True, "跳过：真实索引不存在（非本机环境）")
    code, out = invoke_main(["--check-index", REAL_INDEX])
    return (code == 0, f"真实索引应通过，exit={code}\n{out}")


def case_bad_pending_via_main():
    """入口: 坏 pending 应 exit 5 并逐条报错。"""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "pending_fixture.json"
        bad = dict(GOOD_PENDING)
        bad["tip_takeaway"] = "说到底，调研考验的是责任心。"
        p.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        code, out = invoke_main(["--pending", p])
        ok = code == 5 and "R8-总结是练习" in out
        return (ok, f"应 exit 5 且点名 R8，实际 exit={code}\n{out}")


CASES = [
    ("golden", case_golden),
    ("golden无meta", case_golden_no_meta),
    ("索引错链", case_index_wrong_link),
    ("索引题型目录", case_index_type_dir_mismatch),
    ("来源缺失", case_index_source_missing),
    ("索引count元数据", case_index_count_mismatch),
    ("标题未兑现", case_title_unfulfilled),
    ("对照堆字", case_parity_padded),
    ("对照换题", case_parity_different_question),
    ("两点法造第三步", case_two_point_method_invented_step3),
    ("四点法丢条件", case_four_point_method_missing_label),
    ("遗漏适用边界", case_boundary_missing),
    ("虚构权威", case_invented_authority),
    ("总结不是练习", case_takeaway_not_practice),
    ("正常用语不误报", case_normal_gongkao_words_not_flagged),
    ("emoji纪律", case_emoji_discipline),
    ("标题定稿句式放行", case_title_brand_style),
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

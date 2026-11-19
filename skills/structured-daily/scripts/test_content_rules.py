#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_content_rules —— content_rules.py R0-R15 全量自测。

运行：python3 scripts/test_content_rules.py [关键字...]
- 全过 exit 0；任一用例失败 / 0 用例（筛选不中或框架坏）/ 用例 <30 → exit 1
  （不允许假绿）。
- 沙箱纪律：所有临时 JSON/索引/题库 fixture 只写系统临时目录（tempfile），
  经环境变量 TIPS_PROJECT_ROOT 注入；真实 vault 只读（R1/R2 各一条真实
  正例，vault 缺失时跳过），绝不写入。

用例构成：
- Task2 的 9 用例保留（R0/R14；golden 用例适配为全量 R0-R15 通过口径）；
- 现行 structured-tips-daily 33 用例有效项移植（适配 15 字段/新规则，
  1.5× 长度硬拦反例按 F3 取消，改为长示范正例放行）；
- Task5 新增：R1 错链 / R2 来源缺失 / R3 标题 / R4 三子检查（含取消 1.5×
  正例）/ R5 两点三点四点 / R6 三分 / R7 三类 / R8 回顾式纯反问 / R9 焦点 /
  R10 调色板 / R11 问句 / R12 认知增量与翻案腔不作线索 / R13 口径四查 /
  R15 自查三查 / 正常公考用语不误杀 / pending schema 加载。
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_CLI = os.path.join(HERE, "content_rules.py")

# 真实 vault（只读；R1/R2 真实正例用，缺失则跳过）
REAL_VAULT_ROOT = "/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/结构化"
REAL_INDEX = os.path.join(REAL_VAULT_ROOT, "scripts", "tips_index.json")

MIN_CASES = 30  # 用例数下限，防框架坏后假绿


def write_json(tmpdir, name, obj, bom=False):
    path = os.path.join(tmpdir, name)
    data = json.dumps(obj, ensure_ascii=False, indent=2)
    if bom:
        data = "\ufeff" + data
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)
    return path


def run_cli(*cli_args, env=None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.run(
        [sys.executable, RULES_CLI] + list(cli_args),
        capture_output=True, text=True, env=full_env,
    )
    return proc.returncode, proc.stdout + proc.stderr


CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


# ---------------------------------------------------------------------------
# 沙箱 fixture：临时 vault（索引 + 题库 + 方法论文件），env 注入 TIPS_PROJECT_ROOT
# ---------------------------------------------------------------------------

SRC_BODY = (
    "# 组织计划题：养老调研\n\n## 题干\n\n"
    "> 某街道要对辖区养老需求开展调研，辖区有独居老人和同住老人。你怎么组织？\n\n"
    "## 思路大纲\n\n调研对象要分层，先摸底数，每个调研对象后面跟一个它最想要的信息。\n\n"
    "## 定调版逐字稿\n\n"
    "养老调研先把对象分层，每个调研对象后面跟一个它最想要的信息。"
    "独居老人上门问送餐就医安不安全，同住老人问文娱活动够不够。\n\n"
    "## 教师注（不计入作答）\n\n- 仅限公开题干，涉密数据不入稿。\n"
)

METHOD_BODY = (
    "# 组织计划题方法论提炼\n\n## 调研对象\n\n"
    "调研对象要分层，每类对象围绕其最关心的信息设问，需求能排序。\n"
)


def make_sandbox(tmp):
    """搭沙箱 vault：scripts/tips_index.json + 题库/方法论文件。返回路径 dict。"""
    src_dir = os.path.join(tmp, "题库", "组织计划题")
    os.makedirs(src_dir, exist_ok=True)
    method_dir = os.path.join(tmp, "方法论")
    os.makedirs(method_dir, exist_ok=True)
    idx_dir = os.path.join(tmp, "scripts")
    os.makedirs(idx_dir, exist_ok=True)
    src_abs = os.path.join(src_dir, "组织计划-03-养老调研.md")
    with open(src_abs, "w", encoding="utf-8") as f:
        f.write(SRC_BODY)
    method_abs = os.path.join(method_dir, "组织计划题方法论提炼.md")
    with open(method_abs, "w", encoding="utf-8") as f:
        f.write(METHOD_BODY)
    index = {
        "_meta": {"source_root": os.path.join(tmp, "题库"), "count": 1},
        "tips": [{
            "id": "zz-03",
            "name": "养老调研：对象分层问需求",
            "types": ["组织计划题"],
            "src": "组织计划题/组织计划-03-养老调研.md",
            "note": "每个调研对象后面跟一个它最想要的信息",
        }],
    }
    idx_abs = write_json(idx_dir, "tips_index.json", index)
    return {
        "env": {"TIPS_PROJECT_ROOT": tmp},
        "src": src_abs,
        "method": method_abs,
        "index": idx_abs,
    }


def rewrite_index(sb, tips):
    """用给定 tips 列表重写沙箱索引（R1 错链类用例）。"""
    data = {"_meta": {"source_root": os.path.dirname(os.path.dirname(sb["src"])),
                      "count": len(tips)},
            "tips": tips}
    with open(sb["index"], "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 黄金样例（15 字段 + 完整 meta 两结论通过；沙箱内全量 R0-R15 应 exit 0）
# ---------------------------------------------------------------------------

def golden_pending():
    return {
        "tip_title": "调研对象列完了，分别问什么？",
        "card_point": "组织计划题·调研类：你卡在调研问得空——对象笼统，问题跟着模板走，"
                      "收上来全是泛泛报告。问题出在对象和信息没对上。",
        "fix_summary": "改法一句话：本期只教每个调研对象后面跟一个它最想要的信息；"
                       "题骨前提是先摸清辖区底数。",
        "demo": "养老调研答得空，根子多半是没有先问信息要用在哪儿。我的判断是，"
                "先把调研对象分层，每个对象后面跟一个它最想要的信息。"
                "独居老人上门问送餐就医安不安全，同住老人问文娱活动够不够，"
                "机构家属问护理费用怎么算。问出来的需求能排序，清单就能落地。",
        "step1": "第一步：先把对象分层，独居老人、同住老人、机构家属各是一类。",
        "step2": "第二步：给每类对象分别定一个它最想要的信息，问题跟着信息走。",
        "step3": "第三步：答完自查一遍，问自己：每个对象后面跟的是不是它最想要的信息？",
        "case_normal": "普通答法：我会围绕辖区养老需求开展调研，发放问卷了解老人的需要，再汇总上报。",
        "contrast_note": "点评：普通答法调研只会发问卷，对象笼统，没有说明每类老人各自最想要什么信息，"
                         "收上来容易是泛泛报告，需求理不出差别。示范的改动只有一处："
                         "每个对象后面跟一个它最想要的信息。",
        "boundary_scope": "适用于对象需求差异明显的调研题；若题目只要求摸底数、对象需求单一，"
                          "只保留核实底数即可，不强行分层。",
        "boundary_misuse": "常见误用：把分层当成罗列对象名单，只列类别不配信息。"
                           "纠正：每一类后面必须补上它最想要的信息，列完名单先自问一遍。",
        "boundary_evidence": "教师注：本题仅限公开题干，涉密数据不入稿；分层问法出处见读源记录来源文件。",
        "exercise": "换一道新场景：社区活动室改造需求调研，请你写出三类改造对象，"
                    "并给每类对象补上它最想要的一条改造信息。",
        "self_check": "1.对象是否分了层，每层是不是同一类人？2.每个对象后面有没有跟一个"
                      "它最想要的信息？3.适用判断：对象需求单一时，这一问法不适用。",
        "hashtags": "#公考面试 #结构化面试 #组织计划 #答题技巧 #上岸",
    }


def golden_meta(sb):
    return {
        "skill_version": "3.0.0",
        "line": "tips",
        "tip_id": "zz-03",
        "method_points": 2,
        "point_labels": ["分层", "信息"],
        "sources": [sb["method"] + "#调研对象", sb["src"] + "#定调版逐字稿"],
        "quote_excerpts": [
            "每个调研对象后面跟一个它最想要的信息",
            "养老调研先把对象分层，独居老人上门问送餐就医",
        ],
        "applicable_conditions": ["教师注：仅限公开题干，涉密数据不入稿"],
        "review_conclusion": "通过",
        "render_check": "发布端通过",
        "blind_test_result": "通过",
        "card_point": golden_pending()["card_point"],
        "cognitive_gain": "以为调研问得空是多问几句的事，实际把找对象和配信息并成了一步，"
                          "漏了给每类对象配一个它最想要的信息",
        "shared_context": "同一道社区养老调研题，考生身份是街道工作人员，"
                          "题干给定辖区有独居老人和同住老人",
        "key_change": "每个调研对象后面跟一个它最想要的信息",
        "actionable_demo": "问独居老人：最近一次去医院，出行是谁帮忙安排的？",
        "demo_source": "题库/组织计划题/组织计划-03-养老调研.md#定调版逐字稿",
        "demo_calibration_check": "通过",
        "exercise_criteria": "新场景任务：对象分层+每类配一条最想要的信息+信息落清单",
        "self_check_criteria": "三条自查要素含一个适用判断",
        "title_candidates": [
            "痛点式：调研对象列完了分别问什么（卡点钩子）",
            "具体改法式：对象后面跟一个它最想要的信息",
            "原栏目式：考官想听的：调研分别问什么",
        ],
    }


def run_variant(tmp, sb, pending_over=None, meta_over=None,
                drop_pending=(), drop_meta=(), bom_meta=False, env=None):
    """写沙箱 pending/meta（在黄金样例上打补丁）并跑 CLI，返回 (rc, out)。
    env=None 默认沙箱注入；显式传 env=False 走真实 vault（只读正例）。"""
    pending = golden_pending()
    for k in drop_pending:
        pending.pop(k, None)
    if pending_over:
        pending.update(pending_over)
    pp = write_json(tmp, "pending_tips.json", pending)
    meta = golden_meta(sb)
    for k in drop_meta:
        meta.pop(k, None)
    if meta_over:
        meta.update(meta_over)
    mp = write_json(tmp, "draft_meta.json", meta, bom=bom_meta)
    cli_env = sb["env"] if env is None else (None if env is False else env)
    return run_cli("--line", "tips", "--pending", pp, "--meta", mp, env=cli_env)


# ---------------------------------------------------------------------------
# Task2 的 9 用例（保留，golden 用例适配为 R0-R15 全量通过口径）
# ---------------------------------------------------------------------------

@case("1. R0 缺 meta 拒：给 --pending 不给 --meta → 非0 且报 R0")
def t_r0_missing_arg():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        pp = write_json(tmp, "pending_tips.json", golden_pending())
        rc, out = run_cli("--line", "tips", "--pending", pp, env=sb["env"])
        return rc != 0 and "R0" in out


@case("2. R0 meta 文件不存在拒：--meta 指向不存在路径 → 非0 且报 R0")
def t_r0_meta_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        pp = write_json(tmp, "pending_tips.json", golden_pending())
        rc, out = run_cli("--line", "tips", "--pending", pp,
                          "--meta", "/tmp/nonexistent-draft-meta.json", env=sb["env"])
        return rc != 0 and "R0" in out


@case("3. R14 核心字段缺失拒：删 review_conclusion → 非0 且报 R14")
def t_r14_core_missing():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, drop_meta=["review_conclusion"])
        return rc != 0 and "R14" in out


@case("4. R14 tips 扩展字段缺失拒：line=tips 删 cognitive_gain → 非0 且报 R14")
def t_r14_tips_ext_missing():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, drop_meta=["cognitive_gain"])
        return rc != 0 and "R14" in out


@case("5. R14 review_conclusion 非'通过'拒：写'待审' → 非0 且报 R14")
def t_r14_review_pending():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, meta_over={"review_conclusion": "待审"})
        return rc != 0 and "R14" in out


@case("6. R14 blind_test_result 非'通过'拒：写'未过' → 非0 且报 R14")
def t_r14_blind_failed():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, meta_over={"blind_test_result": "未过"})
        return rc != 0 and "R14" in out


@case("7. 全量 R0-R15 全过放行：完整 15 字段 pending + 完整 meta 两结论通过 → exit 0 且 [OK]")
def t_all_pass():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb)
        return rc == 0 and "[OK]" in out, out if rc != 0 else ""


@case("8. answer 线预留：--line answer → 非0 且提示阶段 2 启用")
def t_answer_reserved():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        pp = write_json(tmp, "pending_tips.json", golden_pending())
        rc, out = run_cli("--line", "answer", "--pending", pp,
                          "--meta", sb["index"], env=sb["env"])
        return rc != 0 and "阶段 2" in out


@case("9. BOM 拒：带 BOM 的合法 JSON meta → 非0 且报 META 加载失败")
def t_bom_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, bom_meta=True)
        return rc != 0 and "META 加载失败" in out


# ---------------------------------------------------------------------------
# R1/R2 索引与来源（沙箱索引 fixture + 真实 vault 只读正例）
# ---------------------------------------------------------------------------

@case("10. R1 错链拒：索引 name/note 与 src 正文无共享实词 → 非0 且报 R1")
def t_r1_wrong_link():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rewrite_index(sb, [{
            "id": "zz-03", "name": "被领导误会：先分清信息差",
            "types": ["组织计划题"],
            "src": "组织计划题/组织计划-03-养老调研.md",
            "note": "被领导误会先别急着解释",
        }])
        rc, out = run_variant(tmp, sb)
        return rc != 0 and "R1" in out and "共享实词不足" in out


@case("11. R1 题型目录拒：types 与 src 目录不一致 → 非0 且报 R1")
def t_r1_type_dir_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rewrite_index(sb, [{
            "id": "zz-03", "name": "养老调研：对象分层问需求",
            "types": ["综合分析题"],
            "src": "组织计划题/组织计划-03-养老调研.md",
            "note": "每个调研对象后面跟一个它最想要的信息",
        }])
        rc, out = run_variant(tmp, sb)
        return rc != 0 and "R1" in out and "目录" in out


@case("12. R2 来源缺失拒：sources 指向不存在文件 → 非0 且报 R2")
def t_r2_source_missing():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, meta_over={
            "sources": [os.path.join(tmp, "方法论", "不存在的方法论.md#小节")]})
        return rc != 0 and "R2" in out and "不存在" in out


@case("13. 真实 vault 只读正例：真实索引条目 R1/R2 不报错（vault 缺失则跳过）")
def t_real_vault_r1_r2():
    if not os.path.isfile(REAL_INDEX):
        return True  # 跳过：非本机环境
    with tempfile.TemporaryDirectory() as tmp:
        with open(REAL_INDEX, "r", encoding="utf-8") as f:
            index = json.load(f)
        entry = index["tips"][0]
        src_abs = os.path.join(index["_meta"]["source_root"], entry["src"])
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, env=False, meta_over={
            "tip_id": entry["id"],
            "sources": [src_abs + "#定调版逐字稿"],
        })
        # 断言用规则专名而非"R1/R2"子串（"[OK] …R0-R15" 含 R1 字样）
        return ("索引错链" not in out and "来源缺失" not in out,
                out if ("索引错链" in out or "来源缺失" in out) else "")


# ---------------------------------------------------------------------------
# R3/R4（含取消 1.5× 后的长示范正例）
# ---------------------------------------------------------------------------

@case("14. R3 标题未兑现拒：标题说的正文没讲 → 非0 且报 R3")
def t_r3_title_unfulfilled():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "tip_title": "上台一紧张就大脑空白？"})
        return rc != 0 and "R3" in out


@case("15. R3 标题候选句式正例：'考官想听的：'前缀剥离后兑现 → 放行")
def t_r3_brand_prefix_ok():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "tip_title": "考官想听的：调研分别问什么"})
        return rc == 0, out if rc != 0 else ""


@case("16. R4 换题拒：示范与普通答法无共同内容词 → 非0 且报 R4-对照同题")
def t_r4_different_question():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "demo": "先成立舆情监测专班，逐条比对转发链条，再统一口径对外发声。"})
        return rc != 0 and "R4-对照同题" in out


@case("17. R4 偷加数字拒：示范多出题干没有的数字 → 非0；'比如'示例标记豁免 → 放行")
def t_r4_new_fact():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc1, out1 = run_variant(tmp, sb, pending_over={
            "demo": golden_pending()["demo"] + "2 小时内把需求清单汇总上报。"})
        ok_bad = rc1 != 0 and "R4-偷加事实" in out1
        rc2, out2 = run_variant(tmp, sb, pending_over={
            "demo": golden_pending()["demo"] + "比如 2 小时内把需求清单汇总上报。"})
        ok_good = "R4-偷加事实" not in out2
        return ok_bad and ok_good, out1 if not ok_bad else out2 if not ok_good else ""


@case("18. R4 取消 1.5×：长示范（显著长于普通答法）正例放行，不硬拦长度")
def t_r4_no_length_cap():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        long_demo = golden_pending()["demo"] + (
            "同时把问法也分开。对独居老人先问吃饭看病，再问出行安不安全；"
            "对同住老人问活动场地和课程安排；对机构家属问护理记录能不能随时查，"
            "费用明细有没有人核对。每一类问完，当场把答案记到对应的清单栏里，"
            "回来的路上就能看出哪一类缺口最大，需要现场追问的当场补问，"
            "不用等回办公室再翻记录。")
        rc, out = run_variant(tmp, sb, pending_over={"demo": long_demo})
        return rc == 0 and "R4" not in out, out if rc != 0 else ""


@case("19. R4 点评凭空指控拒：指控词在普通答法原话无对应 → 非0 且报 R4-点评有据")
def t_r4_allege_unfounded():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        variant = golden_pending()
        variant["case_normal"] = ("普通答法：我会先安抚老人情绪，说明正在协调，"
                                  "争取早日把调研结果反馈给大家。")
        rc, out = run_variant(tmp, sb, pending_over={
            "case_normal": variant["case_normal"],
            "contrast_note": "点评：'争取早日反馈'听着积极，其实是随口保证。到点没反馈，信任就没了。"})
        return rc != 0 and "R4-点评有据" in out and "随口保证" in out


@case("20. R4 '没说明 vs 说错'正例放行：'没有说明X'式公允批评不误杀")
def t_r4_absence_vs_misstate():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        variant = golden_pending()
        variant["case_normal"] = ("普通答法：我会先安抚老人情绪，说明正在协调，"
                                  "争取早日把调研结果反馈给大家。")
        rc, out = run_variant(tmp, sb, pending_over={
            "case_normal": variant["case_normal"],
            "contrast_note": "点评：'争取早日反馈'听着积极，但没有说明下一次什么时候通报进展，"
                             "老人只能一直等。"})
        return "R4-点评有据" not in out, out if "R4-点评有据" in out else ""


@case("21. R4 点评无锚点拒：点评与普通答法无共同实词 → 非0 且报 R4-点评有据")
def t_r4_note_no_anchor():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "contrast_note": "点评：整体状态气质不错，临场表现值得保持。"})
        return rc != 0 and "R4-点评有据" in out


# ---------------------------------------------------------------------------
# R5/R6
# ---------------------------------------------------------------------------

@case("22. R5 两点造第三步拒：method_points=2 step3 无应用/检查线索 → 非0 且报 R5-两点法")
def t_r5_two_point_invented():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "step3": "第三步：要高度重视调研成果转化，深入推进落实。"})
        return rc != 0 and "R5-两点法" in out and "第三点" in out


@case("23. R5 四点丢关键条件拒：method_points=4 标签未全覆盖 → 非0 且逐个点名")
def t_r5_four_point_missing():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, meta_over={
            "method_points": 4,
            "point_labels": ["底数", "分层", "方式", "转化"]})
        return rc != 0 and "R5-多点法" in out and "底数" in out and "方式" in out


@case("24. R5 三点法 1:1 拒：method_points=3 标签未对应落步 → 非0 且报 R5-三点法")
def t_r5_three_point_misaligned():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, meta_over={
            "method_points": 3,
            "point_labels": ["摸底", "问法", "清单"]})
        return rc != 0 and "R5-三点法" in out


@case("25. R6 边界三分缺一拒：boundary_misuse 无误用+纠正线索 → 非0 且报 R6")
def t_r6_boundary_missing():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "boundary_misuse": "用的时候多注意方式方法就行。"})
        return rc != 0 and "R6" in out and "boundary_misuse" in out


@case("26. R6 教师注条件未吸收拒：applicable_conditions 条目 evidence 无对应 → 非0")
def t_r6_condition_not_absorbed():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, meta_over={
            "applicable_conditions": ["教师注：演练录音一律不得带出教室"]})
        return rc != 0 and "R6" in out and "未吸收" in out


# ---------------------------------------------------------------------------
# R7/R8/R9/R10
# ---------------------------------------------------------------------------

@case("27. R7 虚构权威三连拒：考官内心禁语/无出处百分比/冒充经历 → 非0 逐类点名")
def t_r7_invented_authority():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "step2": golden_pending()["step2"] + "73% 的考生调研都答空。",
            "contrast_note": golden_pending()["contrast_note"] + "考官内心：又来一个背模板的，听了就加分。",
            "demo": golden_pending()["demo"] + "我当年考场上就是这么答的。"})
        ok = ("R7-虚构权威" in out and "R7-无出处统计" in out and "R7-冒充经历" in out)
        return ok, out if not ok else ""


@case("28. R7 模糊归因拒：'据某调查显示' → 非0 且报 R7-模糊归因")
def t_r7_vague_attribution():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "card_point": golden_pending()["card_point"] + "据某调查显示，多数考生调研都答空。"})
        return rc != 0 and "R7-模糊归因" in out and "某调查" in out


@case("29. R7 来源不符拒：具体引用与 sources 对不上 → 非0 且报 R7-来源不符")
def t_r7_cite_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        other = os.path.join(tmp, "方法论", "人际关系方法论提炼.md")
        with open(other, "w", encoding="utf-8") as f:
            f.write("# 人际关系方法论提炼\n\n## 情绪优先\n\n先处理情绪，再处理事情。\n")
        rc, out = run_variant(tmp, sb, meta_over={
            "sources": [other + "#情绪优先"]},
            pending_over={
                "demo": golden_pending()["demo"] + "数据显示分层问需的调研更容易转化。"})
        return rc != 0 and "R7-来源不符" in out


@case("30. R8 回顾式练习拒：'改写你上次的答案'无新场景 → 非0 且报 R8")
def t_r8_review_style():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "exercise": "改写一下你上次的调研答案，看对象和信息有没有分开。"})
        return rc != 0 and "R8" in out and "回顾" in out


@case("31. R8 纯反问拒：exercise 无任务动词的空洞反问 → 非0 且报 R8")
def t_r8_hollow_question():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "exercise": "说到底，调研答得好不好，是不是就看用心？"})
        return rc != 0 and "R8" in out and "纯反问" in out


@case("32. R9 破题未点卡点拒：fix_summary 与 card_point 无共享实词 → 非0 且报 R9")
def t_r9_focus_missing():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "fix_summary": "改法一句话：本期只教先摸底数再定问卷；题骨前提是先摸清辖区底数。"})
        return rc != 0 and "R9" in out


@case("33. R10 emoji 超限拒：单字段 4 个调色板内 emoji → 非0 且报 R10")
def t_r10_emoji_over():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "card_point": golden_pending()["card_point"] + "❗️❌✅📌"})
        return rc != 0 and "R10" in out and "2 个上限" in out


@case("34. R10 调色板外拒：字段出现调色板外 emoji → 非0 且报 R10")
def t_r10_emoji_outside_palette():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "fix_summary": golden_pending()["fix_summary"] + "🎯"})
        return rc != 0 and "R10" in out and "调色板外" in out


# ---------------------------------------------------------------------------
# R11/R12/R13/R15
# ---------------------------------------------------------------------------

@case("35. R11 可照做问句缺失拒：step1-3 与 actionable_demo 全无问句/动作 → 非0 且报 R11")
def t_r11_not_actionable():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb,
                              pending_over={"step3": "第三步：落实到清单上就行。"},
                              meta_over={"actionable_demo": "注意对象和信息要对上"})
        return rc != 0 and "R11" in out


@case("36. R12 认知增量缺失拒：card_point 无诊断线索词 → 非0 且报 R12")
def t_r12_gain_missing():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, meta_over={
            "card_point": "组织计划题·调研类：调研问得空，是模板化套话太多，"
                          "其实要更深入才能出彩。"})
        return rc != 0 and "R12" in out


@case("37. R12 翻案腔词不作线索拒：纯翻案腔 card_point 无诊断词 → 非0 且报 R12")
def t_r12_fanchang_not_cue():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, meta_over={
            "card_point": "组织计划题·调研类：看似是问得空，实则是套话太多，"
                          "真正要做的是更深入，本质在深挖。"})
        return rc != 0 and "R12" in out


@case("38. R12 翻案腔正例不误杀：含翻案腔词但有问题出在诊断 → 全过放行")
def t_r12_fanchang_positive_ok():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, meta_over={
            "card_point": golden_pending()["card_point"]
                          + "这不是口才问题，真正要做的是把对象和信息对上。"})
        return rc == 0, out if rc != 0 else ""


@case("39. R13 示范口径不符拒：demo_calibration_check 非'通过' → 非0 且报 R13")
def t_r13_calibration_failed():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, meta_over={
            "demo_calibration_check": "字数待回核"})
        return rc != 0 and "R13" in out and "通过" in out


@case("40. R13 demo_source 缺失/类型不明拒：写'原创'未标类型 → 非0 且报 R13")
def t_r13_demo_source_untyped():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, meta_over={"demo_source": "原创"})
        return rc != 0 and "R13" in out and "demo_source" in out


@case("41. R13 引用对不上拒：quote_excerpts 与 demo 无关 → 非0 且报 R13")
def t_r13_quote_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, meta_over={
            "quote_excerpts": ["人际冲突先处理情绪，再处理事情，最后处理工作"]})
        return rc != 0 and "R13" in out and "对不上" in out


@case("42. R13 场景故事开头拒：demo 首句含故事线索违反三禁 → 非0 且报 R13")
def t_r13_story_opening():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "demo": "那天早上，一位老人上门来问养老钱的事，我想起辖区的调研台账。"
                    "先把调研对象分层，每个对象后面跟一个它最想要的信息。"
                    "独居老人上门问送餐就医安不安全，同住老人问文娱活动够不够。"})
        return rc != 0 and "R13" in out and "故事开头" in out


@case("43. R13 片段正例放行：demo 是 opening+body 片段（远短于整篇 700-800 字）→ 放行")
def t_r13_fragment_ok():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        short_demo = ("养老调研先把对象分层，每个对象后面跟一个它最想要的信息。"
                      "独居老人上门问送餐就医安不安全，同住老人问文娱活动够不够。"
                      "先把调研对象分层。")
        rc, out = run_variant(tmp, sb, pending_over={"demo": short_demo})
        return rc == 0 and "R13" not in out, out if rc != 0 else ""


@case("44. R15 自查判据缺失拒：self_check 单条无分条 → 非0 且报 R15")
def t_r15_too_few():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "self_check": "答完记得复盘一遍就好。"})
        return rc != 0 and "R15" in out and "自检要素" in out


@case("45. R15 自查超量拒：4 条自检要素 → 非0 且报 R15")
def t_r15_too_many():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "self_check": "1.对象分层了吗？2.每类配信息了吗？3.需求能排序吗？"
                          "4.适用判断：单项摸底不适用。"})
        return rc != 0 and "R15" in out and "4 条" in out


@case("46. R15 自查与练习重复拒：self_check 复述 exercise 迁移任务 → 非0 且报 R15")
def t_r15_duplicate_exercise():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "self_check": "换一道社区活动室改造需求调研的题，写出三类改造对象，"
                          "并给每类对象补上它最想要的一条改造信息。"})
        return rc != 0 and "R15" in out and "重复" in out


# ---------------------------------------------------------------------------
# 防误杀正例 + 加载器基础设施
# ---------------------------------------------------------------------------

@case("47. 正常公考用语与条件词不误杀：若/以…为准/可能 等条件表述 → 全过放行")
def t_normal_gongkao_words_ok():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc, out = run_variant(tmp, sb, pending_over={
            "card_point": golden_pending()["card_point"]
                          + "若上级已统一部署摸底指标，以制度为准套用既有口径即可。",
            "boundary_scope": golden_pending()["boundary_scope"]
                              + "如果题目只给了一个对象，可能不必分层。"})
        return rc == 0, out if rc != 0 else ""


@case("48. pending schema 拒：缺字段/多字段 → exit 2 且报 PENDING 加载失败")
def t_pending_schema():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        rc1, out1 = run_variant(tmp, sb, drop_pending=["self_check"])
        ok1 = rc1 == 2 and "PENDING 加载失败" in out1 and "self_check" in out1
        extra = golden_pending()
        extra["foo_bar"] = "多余字段"
        pp = write_json(tmp, "pending_extra.json", extra)
        mp = write_json(tmp, "meta_ok.json", golden_meta(sb))
        rc2, out2 = run_cli("--line", "tips", "--pending", pp, "--meta", mp, env=sb["env"])
        ok2 = rc2 == 2 and "多余字段" in out2
        return ok1 and ok2, out1 if not ok1 else out2 if not ok2 else ""


@case("49. pending 缺失拒：不传 --pending → exit 2 参数不足（全量门禁须齐备）")
def t_pending_required():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        mp = write_json(tmp, "meta_ok.json", golden_meta(sb))
        rc, out = run_cli("--line", "tips", "--meta", mp, env=sb["env"])
        return rc == 2 and "--pending" in out


@case("50. 坏 pending JSON 拒：语法错误 → exit 2 且报 PENDING 加载失败")
def t_bad_pending_json():
    with tempfile.TemporaryDirectory() as tmp:
        sb = make_sandbox(tmp)
        pp = os.path.join(tmp, "bad.json")
        with open(pp, "w", encoding="utf-8") as f:
            f.write("{\"tip_title\": ")
        mp = write_json(tmp, "meta_ok.json", golden_meta(sb))
        rc, out = run_cli("--line", "tips", "--pending", pp, "--meta", mp, env=sb["env"])
        return rc == 2 and "PENDING 加载失败" in out


# ---------------------------------------------------------------------------
# 运行器（筛选 0 用例/用例数不足/任一失败 → exit 1，不假绿）
# ---------------------------------------------------------------------------

def main():
    keywords = sys.argv[1:]
    selected = [(name, fn) for name, fn in CASES
                if not keywords or any(k in name for k in keywords)]
    if not selected:
        print("[FAIL] 关键字 %s 筛选出 0 个用例，不允许假绿" % keywords)
        return 1
    if not keywords and len(selected) < MIN_CASES:
        print("[FAIL] 用例数 %d 低于下限 %d，不允许假绿" % (len(selected), MIN_CASES))
        return 1
    failed = 0
    for name, fn in selected:
        try:
            result = fn()
            ok = result[0] if isinstance(result, tuple) else result
            detail = result[1] if isinstance(result, tuple) and not result[0] else ""
        except Exception as e:  # 用例自身异常一律算失败
            ok, detail = False, "%s: %s" % (type(e).__name__, e)
        if ok:
            print("[PASS] %s" % name)
        else:
            print("[FAIL] %s" % name)
            if detail:
                print("       %s" % detail.replace("\n", "\n       ")[:800])
            failed += 1
    total = len(selected)
    print("---")
    print("%d/%d 用例通过" % (total - failed, total))
    if failed:
        print("[FAIL] content_rules 自测未全过")
        return 1
    print("[OK] content_rules 自测全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""content_rules —— structured-daily 出厂规则门禁（最终出厂程序，R0-R15 全量）。

流水线位置（君上裁定，修正 spec B3 内部矛盾）：全量 R0-R15 跑在
独立审稿（写 review_conclusion）＋盲测试答（写 blind_test_result）
之后，作最终出厂门禁：草稿 → 电车站诊断 → human-writing 改写 →
check_prose 清零 → 回核读源 → 独立审稿 → 盲测试答 → content_rules
全量 exit0 → CHECKPOINT → 引擎。

程序只查可核验词语线索；认知增量是否真增、可照做是否真能照做、示范
结构是否符合定调版口径等语义判断由独立审稿＋盲测负责（shared-gates.md
步 7/8，未验证假设 2）。

CLI:
    python3 content_rules.py --line tips --pending PATH --meta PATH
    --line answer 预留阶段 2（exit 2）。
    vault 定位：环境变量 TIPS_PROJECT_ROOT > 默认 vault 项目根。
    R1/R2 只读 vault tips_index.json 与题库/来源文件核实路径，绝不写入 vault。

退出码: 0=全过 / 1=有规则未过（逐条打印 [FAIL] R<n>: 原因）/
        2=参数或 JSON 加载错误。

规则（技巧线 --line tips；R4 含三个子检查；R0/R14 为 Task2 实现保留）:
    R0 读源记录必填     --pending 给定而 --meta 缺失/不存在 → 拒
    R1 索引错链         meta.tip_id 命中 vault tips_index.json 条目；src 文件存在；
                        题型目录与 types 一致；name/note 与 src 正文共享实词
                        （横切条目豁免）
    R2 来源缺失         meta.sources 非空且每条"文件#小节"的文件存在（vault 内相对
                        路径或绝对路径，只读核实）
    R3 标题兑现         tip_title 内容词（去前缀/停用词）在卡点/改法/示范/步骤有对应；
                        卡点+改法是否真兑现语义归审稿
    R4 对照同题同条件   示范与普通答法共享题境实词；【1.5× 长度硬拦已取消（F3，
                        君上裁定：定调版示范可能长于普通版，长度比不作检查）】；
                        R4-偷加事实：demo 数字须出自普通答法/题干引文或有
                        "比如/示范"示例标记；R4-点评有据：contrast_note 锚定
                        case_normal 原话，指控词在原话无对应表述即拒（程序只拦
                        凭空指控，"没有说明X"与"说错了X"的区分归审稿）
    R5 步数服从原方法   两点法 step3 须为应用/检查（不凭空造第三点）；三点法 1:1；
                        四点+ 按原逻辑分组进三步且 point_labels 全覆盖不丢关键条件
    R6 适用边界三分     boundary_scope 适用线索 / boundary_misuse 误用+纠正动作 /
                        boundary_evidence 证据线索；meta.applicable_conditions 中
                        条件性教师注条目须被 boundary_evidence 吸收
    R7 无虚构权威       禁替考官发言（"考官想听的："标题句式除外）/无出处百分比/
                        冒充经历/模糊归因；具体引用与 meta.sources 对不上拒
    R8 练习迁移         exercise 须含任务动词+正文没出现过的场景词；回顾式/纯反问拒
    R9 一期一技巧       meta.card_point（或 focus_keywords）至少一个实词在
                        fix_summary 破题；只教一个主技巧语义归审稿
    R10 emoji 纪律      每字段 emoji ≤2 且限调色板 ❗️🙅❌✅📌💡⏰🗣（引擎自动加的
                        段首 👍/🙅‍♂️ 不在 pending JSON 内，天然不计）
    R11 可照做          step1-3 至少一个含能直接问出口的问句（？/? 或 问自己/怎么问/
                        问什么 线索）或可执行动作模板（具体动词+对象）；
                        meta.actionable_demo 非空且含问句/动作线索
    R12 认知增量        card_point 含诊断线索词（卡在/误区/以为/问题出在…）；
                        翻案腔词（不是…而是/看似…实则 等）**不作线索**；
                        meta.cognitive_gain 含具体误区线索（"要深入"类空泛不算）；
                        是否真认知增量归独立审稿
    R13 示范定调版口径  meta.demo_source 标明"引用题库定调版出处"或"新写标示范"；
                        引用型 demo 须与 meta.quote_excerpts 定调版逐字稿对得上
                        （无 excerpts 时以 sources 兜底）；demo 含 opening 破题定调+body 段片段结构线索；
                        破题定调三禁线索（不场景故事开头/不先讲经历，编题干外事件
                        归审稿+回核）；meta.demo_calibration_check=="通过"；
                        【不硬卡整篇 700-800 字——demo 是 opening+1 body 片段，
                        君上裁定】
    R14 审稿记录完整    （Task2 实现保留）核心+线扩展字段非空 + 两结论=="通过"
    R15 自查判据        self_check 2-3 条自检要素（1./2. 或 ①②③ 或 分号/问号分条）
                        +一个适用判断；与 exercise 的迁移任务不重复
"""

import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# 字段契约（与 references/shared-sourcing.md draft_meta schema 一致）
# ---------------------------------------------------------------------------

# R14 核心必填字段（两线必填）
CORE_FIELDS = [
    "skill_version",
    "line",
    "method_points",
    "point_labels",
    "sources",
    "quote_excerpts",
    "applicable_conditions",
    "review_conclusion",
    "render_check",
    "blind_test_result",
]

# line=="tips" 时 tips 扩展必填字段（tip_id/question_id 二选一单独处理）
TIPS_EXT_FIELDS = [
    "card_point",
    "cognitive_gain",
    "shared_context",
    "key_change",
    "actionable_demo",
    "demo_source",
    "demo_calibration_check",
    "exercise_criteria",
    "self_check_criteria",
    "title_candidates",
]

# pending 15 字段（Task4 定稿，与引擎 fill_tips_post.py SCHEMA_KEYS 一致）
PENDING_FIELDS = [
    "tip_title", "card_point", "fix_summary", "demo",
    "step1", "step2", "step3",
    "case_normal", "contrast_note",
    "boundary_scope", "boundary_misuse", "boundary_evidence",
    "exercise", "self_check", "hashtags",
]

# vault 定位（R1/R2 只读）：环境变量优先，默认 vault 项目根（与引擎约定一致）
DEFAULT_VAULT_ROOT = "/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/结构化"
GK_TRAINING_ROOT = "/Users/shawn/Desktop/AI工作区/02-Areas/公考面试结构化培训"


def _missing(value):
    """非空判断：None / 空串（含纯空白）/ 空列表 / 空字典 视为缺失。"""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def _as_str_list(value):
    """宽松取字符串列表：list 取非空项；单个字符串包成列表；其余为空列表。"""
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


# ---------------------------------------------------------------------------
# 词语线索工具（认词语不认语义，语义归独立审稿）
# ---------------------------------------------------------------------------

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
# R4-偷加事实: 数字前的示例标记豁免窗口（不收单字"如"，避免"如果"误豁免）
EXAMPLE_MARKERS = ("比如", "例如", "假设", "示范", "设定", "举例", "譬如", "口径")
# R4-点评有据: 点评与普通答法共享实词下限
NOTE_ANCHOR_MIN_SHARED = 2
# R4-点评有据: (点评指控词, 普通答法原话须出现的证据词根)；原话无词根即"批评无据"
ALLEGE_ACT_PAIRS = (
    ("随口保证", ("保证", "承诺", "担保", "打包票", "拍胸脯", "一定", "肯定", "确保", "绝对")),
    ("随口承诺", ("保证", "承诺", "一定", "肯定", "确保")),
    ("空头承诺", ("保证", "承诺", "一定", "肯定", "确保")),
    ("空头支票", ("保证", "承诺", "一定", "肯定", "确保")),
    ("拍胸脯", ("保证", "承诺", "一定", "肯定", "确保")),
    ("打包票", ("保证", "承诺", "一定", "肯定", "确保")),
    ("当场许诺", ("保证", "承诺", "一定", "肯定", "马上就办", "立刻办")),
    ("大包大揽", ("包在", "保证", "承诺", "一定", "交给")),
    ("教前辈做事", ("建议", "应该", "您要", "按制度", "按流程", "规范", "支招")),
    ("态度生硬", ("赶紧", "快点", "别吵", "急什么", "催什么", "没办法", "不能办")),
    ("指责群众", ("你们自己", "怪你们", "怨你们", "不听劝", "早跟你们")),
    ("空喊口号", ("高度重视", "切实", "狠抓", "强化", "完善", "落实", "抓紧", "务必")),
    ("越权", ("我直接决定", "我来定", "我说了算", "直接拍板", "自行决定")),
    ("擅自决定", ("我直接决定", "我来定", "我说了算", "直接拍板", "自行决定")),
    ("隐瞒", ("不报", "瞒着", "不告诉", "先不说", "不上报")),
    ("敷衍", ("走个流程", "走形式", "随便", "应付", "糊弄")),
)
# R5: step3 作为"应用/检查步"的线索词（两点法专用）
CHECK_CUES = ("自查", "自检", "检查", "检验", "验证", "复盘", "问自己",
              "试着", "练习", "应用", "落到", "对照", "核一遍", "过一遍")
# R6: 三字段各自线索词
SCOPE_CUES = ("适用", "不适用", "仅", "只", "前提", "边界", "条件", "若",
              "如果", "限制", "范围", "慎用", "例外", "为准")
MISUSE_CUES = ("误用", "用错", "错在", "容易", "当成", "混淆", "别用", "不要",
               "误区", "陷阱", "常见错", "习惯性", "想当然", "滥")
CORRECT_CUES = ("纠正", "改成", "改为", "换成", "应改", "应该", "应当", "正确",
                "记住", "回到", "补上", "才对", "要改", "前提是", "必须", "自问")
EVIDENCE_CUES = ("教师注", "出处", "来源", "依据", "文件", "规定", "权限", "安全",
                 "涉密", "脱敏", "仅限", "不得", "数据", "为准", "官方")
# R6: 教师注条目里的"条件性"线索——带这些词的条目必须被 boundary_evidence 吸收
CONDITION_CUES = ("仅限", "只限", "不得", "须", "需", "应", "前提", "适用", "禁",
                  "慎", "涉密", "权限", "安全", "公开", "题干", "为准", "数据",
                  "来源", "注：")
# R7: 虚构权威禁语（一字不差）。"考官想听的："是标题候选句式，不在禁语表内；
# 禁的是正文里替考官编内心独白、无依据评分规则和凭空统计。
BANNED_AUTHORITY = ("考官内心", "考官会想", "考官普遍", "阅卷人内心",
                    "听了就加分", "一票否决", "考官必给")
# R7: 无出处百分比的豁免标记（同字段出现即放行）
SOURCE_MARKERS = ("出处", "据", "报告", "文件", "显示", "举例", "比如", "例如",
                  "示范", "设定", "假设", "来源")
# R7: 经历腔标记 -> 必须同字段出现"示范"类标记
EXPERIENCE_MARKERS = ("我当年", "我上岸", "我考场上", "那年我", "我考的时候")
SIMULATION_MARKERS = ("示范", "设定", "假如", "比如", "例如", "场景")
# R7: 模糊归因（无具体来源的引用）直接拦截——"某调查"不可证伪，一律不写
VAGUE_ATTRIBUTION = ("某调查", "某报告", "某研究", "某机构", "某媒体",
                     "有调查显示", "有研究表明", "有统计显示", "专家表示",
                     "专家认为", "网友纷纷表示", "普遍反映")
# R7: 具体引用线索 -> 与 meta.sources 比对
CITE_CUES = ("调查显示", "研究表明", "报告显示", "数据显示", "统计显示",
             "官方数据", "媒体报道", "文件明确", "文件要求")
# R8: 任务动词（有任务才算练习）
TASK_VERBS = ("写出", "列出", "设计", "回答", "作答", "改写", "换成", "换一道",
              "换一个", "套", "试着", "补上", "补一句", "补一个", "加上", "标出",
              "找出", "圈出", "判断", "默写", "拟一条", "拟出", "翻译成",
              "准备", "说明", "提问", "模拟")
# R8: 回顾式练习线索（缺新场景标记即拦）
REVIEW_CUES = ("你上次", "上次的", "刚才那道", "原文里", "讲义里", "这道原题",
               "上面的示范", "刚才的示范", "本文里", "上文", "这篇里")
# R8: 新场景标记
NEW_SCENARIO_CUES = ("换成", "换一道", "换一个", "另一道", "另一个场景", "新场景",
                     "换到", "一道新题", "换个场景", "假设新")
# R11: 问句/动作线索（能直接问出口或照做）
ASK_CUES = ("问自己", "怎么问", "问什么", "该问", "先问", "提问", "开口问",
            "一问", "问一句", "自问")
ACTION_VERB_CUES = ("写出", "列出", "圈出", "标出", "补上", "对照", "核对",
                    "检查", "数一遍", "划出", "勾出", "拟", "替换", "换成",
                    "打勾", "填", "记下")
# R12: 诊断线索词（认知增量）。翻案腔词（不是/而是/看似/实则/其实/真正/本质/
# 恰恰/反而）**有意不在表内**——它们不作认知增量线索（君上裁定）。
DIAGNOSIS_CUES = ("卡在", "卡点", "卡住", "误区", "误以为", "以为", "原来",
                  "问题出在", "症结", "难点", "弄混", "混淆", "弄反", "踩坑",
                  "漏掉", "漏了", "忽略", "想当然", "惯性", "习惯性",
                  "容易错", "错在", "常见错")
# R13: 场景故事开头线索（只查 demo 首句；编题干外事件语义归审稿+回核）
STORY_OPEN_CUES = ("那天", "有一天", "某天", "去年", "上周", "昨天", "前天",
                   "记得有一次", "我想起", "想象一下", "假设这样一个场景",
                   "接到电话", "敲门", "走进", "清晨", "深夜", "凌晨",
                   "忽然", "突然接")
# R13: demo 片段结构最小线索（opening 破题定调句 + body 段；片段不卡整篇字数）
DEMO_MIN_CHARS = 60
DEMO_MIN_SENTS = 2
# R15: 适用判断线索
APPLICABLE_JUDGE_CUES = ("什么时候用", "何时用", "不适用", "适用", "仅", "只",
                         "前提", "若", "如果", "边界", "别用", "慎用", "条件")
# R15: 自检要素分条线索
CIRCLED_NUM_RE = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]")
ARABIC_ITEM_RE = re.compile(r"(?:^|[^\d])[1-9][\.、]")
SHI_ITEM_RE = re.compile(r"[一二三四五]是")
# R10: emoji（base 字符，忽略变体选择符）
EMOJI_BASE_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2300-\u23FF\u2B00-\u2BFF]")
EMOJI_PALETTE_BASE = set("❗️🙅❌✅📌💡⏰🗣")
PERCENT_RE = re.compile(r"\d+(?:\.\d+)?%")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
# R1: 题型目录映射
TYPE_DIR = {"综合分析题": "综合分析题", "应急应变题": "应急应变题", "人际关系题": "人际关系题",
            "组织计划题": "组织计划题", "自我认知题": "自我认知题", "言语表达题": "言语表达题"}

_PUNCT_RE = re.compile(r"[，。？?！!：:、；;（）()《》\"\"\"'·\s\n…—\-]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")


def _content_tokens(text, min_len=2):
    parts = _PUNCT_RE.split(text or "")
    return [p for p in (s.strip() for s in parts) if len(p) >= min_len]


def _bigrams(text):
    """全部连续二字窗口（中文无分词依赖的轻量匹配单元）。"""
    text = text or ""
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _content_bigrams(text):
    """只保留实词窗口：剥标点/空白后取二字窗口，剔除泛词与纯数字。"""
    cleaned = "".join(_CJK_RE.findall(text or ""))
    return {b for b in _bigrams(cleaned) if b not in GENERIC_BIGRAMS and not b.isdigit()}


def _strip_case_prefix(text, kind="case"):
    """剥段首 emoji 与段前缀（引擎在发布端自动加 emoji，JSON 内不应有）。"""
    text = re.sub(r"^[🙅\u200d♂️👍❗️✅📌]+\s*", "", text or "")
    if kind == "demo":
        text = re.sub(r"^(定调版示范|示范)[：:]\s*", "", text)
    else:
        text = re.sub(r"^(普通答法|高分答法)[：:]\s*", "", text)
    return text


def _strip_frontmatter(text):
    """剥掉 YAML frontmatter（--- 包裹段），避免标签/文件名制造假共词。"""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def _body_core(pending):
    """R3 标题兑现对照正文：卡点/改法/示范/三步。"""
    keys = ("card_point", "fix_summary", "demo", "step1", "step2", "step3")
    return "".join(pending.get(k, "") for k in keys)


def _body_all(pending, exclude=None):
    """R8 新场景对照正文：除 exercise 外全部内容字段。"""
    return "".join(v for k, v in pending.items() if k != exclude)


def _label_covered(label, text):
    return label in text or bool(_bigrams(label) & _bigrams(text))


# ---------------------------------------------------------------------------
# vault 只读定位（R1/R2；环境变量 TIPS_PROJECT_ROOT 供沙箱测试覆盖）
# ---------------------------------------------------------------------------

def _vault_root():
    return os.environ.get("TIPS_PROJECT_ROOT") or DEFAULT_VAULT_ROOT


def _vault_index_path():
    return os.path.join(_vault_root(), "scripts", "tips_index.json")


def _resolve_source(rel, ctx):
    """来源路径只读解析：绝对路径直查；相对路径依次试 索引source_root/vault根/
    公考培训根/模拟题根。找不到返回 None。"""
    rel = (rel or "").strip()
    if not rel:
        return None
    if os.path.isabs(rel):
        return rel if os.path.isfile(rel) else None
    roots = []
    if ctx.get("index_source_root"):
        roots.append(ctx["index_source_root"])
    roots.append(_vault_root())
    roots.append(GK_TRAINING_ROOT)
    roots.append(os.path.join(GK_TRAINING_ROOT, "01_题库与训练", "模拟题"))
    for root in roots:
        cand = os.path.join(root, rel)
        if os.path.isfile(cand):
            return cand
    return None


# ---------------------------------------------------------------------------
# 规则实现（R0/R14 为 Task2 实现保留，不改逻辑）
# ---------------------------------------------------------------------------

def check_r0(ctx):
    """R0 读源记录必填：--pending 给定而 --meta 缺失或文件不存在 → 拒。"""
    args = ctx["args"]
    if args.pending:
        if not args.meta:
            ctx["failures"].append("R0 读源记录必填：缺 --meta")
            return
        if not os.path.isfile(args.meta):
            ctx["failures"].append(
                "R0 读源记录必填：缺 --meta（文件不存在：%s）" % args.meta
            )


def check_r1(ctx):
    """R1 索引错链：tip_id 命中 vault 索引；src 存在；types 与目录一致；
    name/note 与 src 正文共享实词（横切条目豁免）。只读 vault。"""
    meta = ctx["meta"]
    if meta is None:
        return
    tip_id = meta.get("tip_id")
    if _missing(tip_id):
        return  # 选题 id 缺失由 R14 报，R1 不重复
    index_path = _vault_index_path()
    if not os.path.isfile(index_path):
        ctx["failures"].append("R1 索引错链：vault tips_index.json 不存在: %s" % index_path)
        return
    data, err = load_meta(index_path)
    if err is not None or not isinstance(data, dict):
        ctx["failures"].append("R1 索引错链：索引 JSON 解析失败: %s" % index_path)
        return
    source_root = (data.get("_meta") or {}).get("source_root")
    if source_root:
        ctx["index_source_root"] = os.path.expanduser(str(source_root))
    tips = data.get("tips") or []
    entry = None
    for t in tips:
        if isinstance(t, dict) and t.get("id") == tip_id:
            entry = t
            break
    if entry is None:
        ctx["failures"].append(
            "R1 索引错链：tip_id %r 在索引中不存在（索引共 %d 条）" % (tip_id, len(tips))
        )
        return
    src = (entry.get("src") or "").strip()
    if not src:
        ctx["failures"].append("R1 索引错链：条目 %s 的 src 为空" % tip_id)
        return
    path = _resolve_source(src, ctx)
    if path is None:
        ctx["failures"].append(
            "R1 索引错链：条目 %s 的 src 文件不存在: %s" % (tip_id, src)
        )
        return
    types = entry.get("types") or []
    is_generic = (not types) or types == ["全部题型"]
    if not is_generic:
        expected_dir = TYPE_DIR.get(types[0])
        if expected_dir and not src.replace("\\", "/").startswith(expected_dir + "/"):
            ctx["failures"].append(
                "R1 索引错链：条目 %s types=%s 但 src 在 %s 目录: %s"
                % (tip_id, types, src.replace("\\", "/").split("/")[0], src)
            )
    # 技巧级 name/note 与原文改写共享领域词汇即可（阈值 2 个实词窗口）；
    # 横切条目（全部题型）概括的是例子气质，豁免。
    if not is_generic:
        claim = _content_bigrams((entry.get("name") or "") + (entry.get("note") or ""))
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                body = _content_bigrams(_strip_frontmatter(f.read()))
        except OSError:
            body = set()
        shared = claim & body
        if len(shared) < 2:
            ctx["failures"].append(
                "R1 索引错链：条目 %s 的 name/note 与 src 正文共享实词不足（%s），疑错链: %s"
                % (tip_id, sorted(shared)[:6], src)
            )


def check_r2(ctx):
    """R2 来源缺失：meta.sources 非空且每条"文件#小节"文件存在（只读核实）。"""
    meta = ctx["meta"]
    if meta is None:
        return
    sources = meta.get("sources")
    if _missing(sources):
        ctx["failures"].append("R2 来源缺失：meta.sources 为空（读源记录须给\"文件#小节\"）")
        return
    if not isinstance(sources, list):
        ctx["failures"].append("R2 来源缺失：meta.sources 须为字符串列表")
        return
    for s in sources:
        if not isinstance(s, str) or not s.strip():
            ctx["failures"].append("R2 来源缺失：sources 存在空条目")
            continue
        file_part = s.split("#", 1)[0].strip()
        if not file_part:
            ctx["failures"].append("R2 来源缺失：来源 %r 缺文件路径" % s)
            continue
        if _resolve_source(file_part, ctx) is None:
            ctx["failures"].append("R2 来源缺失：来源文件不存在: %s" % s)


def check_r3(ctx):
    """R3 标题兑现：tip_title 内容词（去前缀/停用词）在卡点/改法/示范/步骤有对应。"""
    pending = ctx["pending"]
    title = (pending.get("tip_title") or "").strip()
    stripped = re.sub(r"^(结构化答题技巧|考官想听的?)[：:]\s*", "", title)
    body = _body_core(pending)
    tokens = [t for t in _content_tokens(stripped)
              if t not in TITLE_STOPWORDS and not t.isdigit()]
    unaddressed = [seg for seg in tokens
                   if seg not in body and not (_bigrams(seg) & _bigrams(body))]
    if unaddressed:
        ctx["failures"].append(
            "R3 标题兑现：标题分句 %s 未在正文（卡点/改法/示范/步骤）展开，"
            "标题承诺未兑现: %r" % (unaddressed, title)
        )


def check_r4(ctx):
    """R4 对照同题同条件（三个子检查）：
    - R4-对照同题：示范与普通答法共享题境实词（长度比不作检查——F3 已取消 1.5×）；
    - R4-偷加事实：demo 数字须出自普通答法/题干引文或带示例标记；
    - R4-点评有据：点评锚定普通答法原话，凭空指控拦截。"""
    meta = ctx["meta"]
    pending = ctx["pending"]
    normal = _strip_case_prefix(pending.get("case_normal") or "")
    demo = _strip_case_prefix(pending.get("demo") or "", kind="demo")

    if normal and demo:
        # 同题锚点（长度不比——定调版示范可能长于普通版）
        anchor = _content_bigrams(normal) & _content_bigrams(demo)
        if not anchor:
            ctx["failures"].append(
                "R4-对照同题：示范与普通答法无共同内容词，疑似不同题或不同条件，"
                "对照必须同题同身份同条件（示范长于普通版不算问题，长度不作检查）"
            )
        # 偷加事实：demo 数字 ⊆ 普通答法+卡点+改法+题干引文，或带示例标记
        known_parts = [pending.get("case_normal") or "",
                       pending.get("card_point") or "",
                       pending.get("fix_summary") or ""]
        if isinstance(meta, dict):
            known_parts += _as_str_list(meta.get("quote_excerpts"))
        known = "".join(known_parts)
        for m in NUM_RE.finditer(demo):
            num = m.group()
            if num in known:
                continue
            window = demo[max(0, m.start() - 6):m.start()]
            if any(mark in window for mark in EXAMPLE_MARKERS):
                continue
            ctx["failures"].append(
                "R4-偷加事实：示范出现普通答法/题干没有的数字 %r，改进版不得偷加"
                "题干外事实；示例数字请前缀'比如/假设/示范'" % num
            )

    # 点评有据
    note = re.sub(r"^点评[：:]\s*", "", pending.get("contrast_note") or "")
    if note and normal:
        shared = _content_bigrams(note) & _content_bigrams(normal)
        if len(shared) < NOTE_ANCHOR_MIN_SHARED:
            ctx["failures"].append(
                "R4-点评有据：点评与普通答法共享实词不足（%s），批评须对应普通版一句原话"
                % sorted(shared)[:6]
            )
        for allege, evidences in ALLEGE_ACT_PAIRS:
            if allege in note and not any(ev in normal for ev in evidences):
                ctx["failures"].append(
                    "R4-点评有据：点评指控 %r，但普通答法原话没有对应表述（如 %s），"
                    "涉嫌凭空批评；原话只是'没说明'的，点评须写成'没有说明X'"
                    "而非'说错了X'" % (allege, list(evidences[:4]))
                )


def check_r5(ctx):
    """R5 步数服从原方法：两点法 step3 应用/检查；三点法 1:1；四点+ 全覆盖。"""
    meta = ctx["meta"]
    if meta is None:
        return
    points = meta.get("method_points")
    labels = meta.get("point_labels") or []
    steps = [ctx["pending"].get("step1", ""),
             ctx["pending"].get("step2", ""),
             ctx["pending"].get("step3", "")]
    if points == 2:
        if labels:
            missing = [lb for lb in labels
                       if not (_label_covered(lb, steps[0]) or _label_covered(lb, steps[1]))]
            if missing:
                ctx["failures"].append(
                    "R5-两点法：原方法要点 %s 未落在 step1/step2" % missing
                )
        if not any(cue in steps[2] for cue in CHECK_CUES):
            ctx["failures"].append(
                "R5-两点法：原方法只有两点，step3 应写应用或检查（线索词 %s…），"
                "不得凭空造第三点；当前 step3: %r"
                % (list(CHECK_CUES[:6]), steps[2][:40])
            )
    elif points is not None and points >= 4:
        # 四点及以上（含五点法）：按原逻辑分组呈现，可分组不可删
        all_steps = "".join(steps)
        missing = [lb for lb in labels if not _label_covered(lb, all_steps)]
        if missing:
            ctx["failures"].append(
                "R5-多点法：原方法 %s 要点须按原逻辑分组全部呈现（可分组不可删），"
                "缺失: %s" % (points, missing)
            )
    elif points == 3:
        for i, lb in enumerate(labels[:3]):
            if lb and not _label_covered(lb, steps[i]):
                ctx["failures"].append(
                    "R5-三点法：要点 %r 未落在 step%d" % (lb, i + 1)
                )


def check_r6(ctx):
    """R6 适用边界三分：scope 适用线索 / misuse 误用+纠正 / evidence 证据线索；
    教师注条件性条目须被 evidence 吸收。"""
    meta = ctx["meta"]
    pending = ctx["pending"]
    scope = pending.get("boundary_scope") or ""
    misuse = pending.get("boundary_misuse") or ""
    evidence = pending.get("boundary_evidence") or ""
    details = []
    if not any(cue in scope for cue in SCOPE_CUES):
        details.append("boundary_scope 缺适用/不适用线索（如 %s…）" % list(SCOPE_CUES[:6]))
    if not (any(cue in misuse for cue in MISUSE_CUES)
            and any(cue in misuse for cue in CORRECT_CUES)):
        details.append(
            "boundary_misuse 缺常见误用+纠正动作线索（误用类如 %s；纠正类如 %s）"
            % (list(MISUSE_CUES[:5]), list(CORRECT_CUES[:5]))
        )
    if not any(cue in evidence for cue in EVIDENCE_CUES):
        details.append(
            "boundary_evidence 缺教师注权限/安全提示或数据出处线索（如 %s）"
            % list(EVIDENCE_CUES[:6])
        )
    if isinstance(meta, dict):
        # 吸收核对：剥"教师注："头再比实词（头本身相同不算吸收）
        ev_body = re.sub(r"^教师注[：:]\s*", "", evidence)
        ev_bg = _content_bigrams(ev_body)
        for cond in _as_str_list(meta.get("applicable_conditions")):
            cond_body = re.sub(r"^教师注[：:]\s*", "", cond)
            if (any(cue in cond for cue in CONDITION_CUES)
                    and not (_content_bigrams(cond_body) & ev_bg)):
                details.append("教师注条件未吸收进 boundary_evidence: %r" % cond)
    if details:
        ctx["failures"].append("R6 适用边界三分：" + "；".join(details))


def check_r7(ctx):
    """R7 无虚构权威：禁替考官发言/无出处百分比/冒充经历/模糊归因/来源不符。
    扫全部 pending 内容字段 + meta 记录字段。"""
    pending = ctx["pending"]
    meta = ctx["meta"]
    texts = {}
    for key in PENDING_FIELDS:
        if isinstance(pending.get(key), str):
            texts[key] = pending[key]
    if isinstance(meta, dict):
        for key in ("cognitive_gain", "actionable_demo", "shared_context", "key_change",
                    "demo_source", "exercise_criteria", "self_check_criteria",
                    "demo_calibration_check", "review_conclusion"):
            v = meta.get(key)
            if isinstance(v, str):
                texts["meta." + key] = v
        tc = meta.get("title_candidates")
        if isinstance(tc, list):
            texts["meta.title_candidates"] = "".join(str(x) for x in tc)
    for key, text in texts.items():
        for banned in BANNED_AUTHORITY:
            if banned in text:
                ctx["failures"].append(
                    "R7-虚构权威：%s 出现禁语 %r：不替考官发言、不写无依据评分规则"
                    % (key, banned)
                )
        m = PERCENT_RE.search(text)
        if m and not any(mk in text for mk in SOURCE_MARKERS):
            ctx["failures"].append(
                "R7-无出处统计：%s 出现百分比且无出处/示范标记: %r" % (key, m.group())
            )
        if (any(mk in text for mk in EXPERIENCE_MARKERS)
                and not any(mk in text for mk in SIMULATION_MARKERS)):
            ctx["failures"].append(
                "R7-冒充经历：%s 疑似冒充作者经历，模拟例子须标'示范/设定'" % key
            )
        for vague in VAGUE_ATTRIBUTION:
            if vague in text:
                ctx["failures"].append(
                    "R7-模糊归因：%s 出现 %r：无具体来源的引用不可证伪，"
                    "给具体出处（与 sources 对应）或删除" % (key, vague)
                )
        if isinstance(meta, dict):
            for cue in CITE_CUES:
                if cue in text:
                    src_text = "".join(_as_str_list(meta.get("sources")))
                    if not src_text or not (_content_bigrams(text) & _content_bigrams(src_text)):
                        ctx["failures"].append(
                            "R7-来源不符：%s 引用 %r 但与读源记录 sources 对不上，"
                            "涉嫌虚假来源" % (key, cue)
                        )


def check_r8(ctx):
    """R8 练习迁移：exercise 须含任务动词+正文没出现过的场景词；回顾式/纯反问拒。"""
    pending = ctx["pending"]
    ex = pending.get("exercise") or ""
    if not any(v in ex for v in TASK_VERBS):
        ctx["failures"].append(
            "R8-练习迁移：exercise 应为新场景微练习：任务动词（写出/列出/设计/回答/"
            "换成…）+新场景；纯反问不算练习: %r" % ex[:40]
        )
        return
    if any(c in ex for c in REVIEW_CUES) and not any(c in ex for c in NEW_SCENARIO_CUES):
        ctx["failures"].append(
            "R8-练习迁移：练习是回顾原答案（'自检你上次的答案'类），"
            "应换成正文没出现过的新场景任务"
        )
    new_bg = _content_bigrams(ex) - _content_bigrams(_body_all(pending, exclude="exercise"))
    if not new_bg:
        ctx["failures"].append(
            "R8-练习迁移：exercise 场景词全部来自正文，未迁移到正文没出现过的新场景"
        )


def check_r9(ctx):
    """R9 一期一技巧：meta.card_point（或 focus_keywords）至少一个实词在
    fix_summary 破题。"""
    meta = ctx["meta"]
    if meta is None:
        return
    fix_bg = _content_bigrams(ctx["pending"].get("fix_summary") or "")
    kws = []
    cp = meta.get("card_point")
    if isinstance(cp, str) and cp.strip():
        kws.append(cp)
    fk = meta.get("focus_keywords")
    if isinstance(fk, list):
        kws += [str(k) for k in fk if str(k).strip()]
    if not kws:
        return  # card_point 缺失由 R14 报
    if not any(_content_bigrams(k) & fix_bg for k in kws):
        ctx["failures"].append(
            "R9-一期一技巧：fix_summary 破题未点出本期卡点/焦点（card_point=%r…），"
            "一期只教一个主要技巧" % (kws[0][:30])
        )


def check_r10(ctx):
    """R10 emoji 纪律：每字段 emoji ≤2 且限调色板。引擎自动加的段首 👍/🙅‍♂️
    不在 pending JSON 内，天然不计入。"""
    pending = ctx["pending"]
    for key in PENDING_FIELDS:
        text = pending.get(key)
        if not isinstance(text, str):
            continue
        bases = EMOJI_BASE_RE.findall(text)
        if len(bases) > 2:
            ctx["failures"].append(
                "R10-emoji：%s emoji 数 %d 超过每字段 2 个上限" % (key, len(bases))
            )
        outside = [ch for ch in dict.fromkeys(bases) if ch not in EMOJI_PALETTE_BASE]
        if outside:
            ctx["failures"].append(
                "R10-emoji：%s 使用调色板外 emoji: %s（限 ❗️🙅❌✅📌💡⏰🗣；"
                "段首 👍/🙅‍♂️ 由引擎自动加不计）" % (key, outside)
            )


def check_r11(ctx):
    """R11 可照做：step1-3 至少一个含能问出口的问句或可执行动作；
    meta.actionable_demo 非空且含问句/动作线索。"""
    pending = ctx["pending"]
    meta = ctx["meta"]

    def actionable(text):
        return ("？" in text or "?" in text
                or any(cue in text for cue in ASK_CUES)
                or any(v in text for v in ACTION_VERB_CUES))

    steps = [pending.get("step1") or "", pending.get("step2") or "", pending.get("step3") or ""]
    if not any(actionable(s) for s in steps):
        ctx["failures"].append(
            "R11-可照做：step1-3 无一含能直接问出口的问句（？/? 或 问自己/怎么问/"
            "问什么）或可执行动作（具体动词+对象），读者无法照做"
        )
    if isinstance(meta, dict):
        ad = str(meta.get("actionable_demo") or "")
        if ad.strip() and not actionable(ad):
            ctx["failures"].append(
                "R11-可照做：meta.actionable_demo 无具体问句/动作线索: %r" % ad[:30]
            )


def check_r12(ctx):
    """R12 认知增量：card_point 含诊断线索词；cognitive_gain 含具体误区线索。
    翻案腔词（不是…而是/看似…实则 等）不作线索；是否真认知增量归独立审稿。"""
    meta = ctx["meta"]
    if meta is None:
        return
    cp = str(meta.get("card_point") or "")
    if not any(cue in cp for cue in DIAGNOSIS_CUES):
        ctx["failures"].append(
            "R12-认知增量：card_point 无诊断线索词（卡在/误区/以为/问题出在…）；"
            "翻案腔词（不是…而是/看似…实则）不作线索，是否真有认知增量由独立审稿判定: %r"
            % cp[:30]
        )
    gain = str(meta.get("cognitive_gain") or "")
    if not any(cue in gain for cue in DIAGNOSIS_CUES):
        ctx["failures"].append(
            "R12-认知增量：meta.cognitive_gain 未描述具体误区（须含 以为/误区/错/"
            "漏/当成 等具体性线索，'要深入'类空泛话不算）: %r" % gain[:30]
        )


def check_r13(ctx):
    """R13 示范定调版口径：demo_source 标明类型；引用型与 quote_excerpts/sources
    定调版逐字稿对得上；demo 含 opening+body 片段结构线索；三禁线索；
    demo_calibration_check=="通过"。不硬卡整篇 700-800 字（demo 是片段）。"""
    meta = ctx["meta"]
    pending = ctx["pending"]
    if meta is None:
        return
    demo = _strip_case_prefix(pending.get("demo") or "", kind="demo")
    ds = str(meta.get("demo_source") or "")
    details = []

    # demo_source 类型标明
    is_new = "新写" in ds
    is_ref = any(mk in ds for mk in (".md", "#", "题库", "定调版", "逐字稿", "出处"))
    if ds.strip() and not (is_new or is_ref):
        details.append(
            "demo_source 未标明类型（须'引用题库定调版出处'或'新写标示范'）: %r" % ds
        )

    # 引用型核对：quote_excerpts（逐字稿原文短句）为主；无 excerpts 时 sources 兜底
    # （sources 是路径串，路径域词噪声大，不作主依据）
    if ds.strip() and not is_new and is_ref:
        quotes = _as_str_list(meta.get("quote_excerpts"))
        if not quotes:
            quotes = _as_str_list(meta.get("sources"))
        demo_bg = _content_bigrams(demo)
        matched = False
        for q in quotes:
            qb = _content_bigrams(q)
            if not qb:
                continue
            if len(qb & demo_bg) >= max(3, (len(qb) + 1) // 2):
                matched = True
                break
        if quotes and not matched:
            details.append(
                "引用型 demo 与 meta.quote_excerpts/sources 题库定调版逐字稿对不上"
                "（无一句共享实词达半），涉嫌来源不符"
            )

    # 回核结论
    if str(meta.get("demo_calibration_check") or "").strip() != "通过":
        details.append(
            "meta.demo_calibration_check=%r 非\"通过\"（示范须回核字数/破题定调/三禁）"
            % meta.get("demo_calibration_check")
        )

    # 片段结构线索：opening 破题定调 + body 段（≥2 句；不卡整篇 700-800 字）
    sents = [s for s in re.split(r"[。！？?!；;\n]", demo) if s.strip()]
    if len(demo) < DEMO_MIN_CHARS or len(sents) < DEMO_MIN_SENTS:
        details.append(
            "demo 缺 opening 破题定调 + body 段的片段结构线索（须≥%d 句且非一句话；"
            "demo 是片段，不卡整篇 700-800 字）" % DEMO_MIN_SENTS
        )

    # 三禁线索（程序查首句故事开头与经历腔；编题干外事件归审稿+回核）
    first = sents[0] if sents else ""
    story = [c for c in STORY_OPEN_CUES if c in first]
    if story:
        details.append(
            "demo 首句疑似场景故事开头（含 %s），违反破题定调三禁" % story
        )
    exp = [c for c in EXPERIENCE_MARKERS if c in demo]
    if exp:
        details.append(
            "demo 疑似先讲作者经历（%s），违反破题定调三禁；模拟须标'示范'" % exp
        )

    if details:
        ctx["failures"].append("R13-示范定调版口径：" + "；".join(details))


def check_r14(ctx):
    """R14 审稿记录完整 + 结论通过：核心字段 + 对应线扩展字段全非空，
    且 review_conclusion=="通过" 且 blind_test_result=="通过"。"""
    meta = ctx["meta"]
    if meta is None:
        return  # meta 不可用时由 R0/加载错误兜底，R14 不重复报

    details = []

    # 1) 核心必填字段（两线）
    for field in CORE_FIELDS:
        if _missing(meta.get(field)):
            details.append("核心字段 %s 缺失/为空" % field)

    # 2) 选题 id 二选一非空
    if _missing(meta.get("tip_id")) and _missing(meta.get("question_id")):
        details.append("选题 id 缺失：tip_id 与 question_id 均为空")

    # 3) line=="tips" 时 tips 扩展字段必填
    if meta.get("line") == "tips":
        for field in TIPS_EXT_FIELDS:
            if _missing(meta.get(field)):
                details.append("tips 扩展字段 %s 缺失/为空" % field)

    # 4) 两结论必须 == "通过"
    if meta.get("review_conclusion") != "通过":
        details.append(
            "review_conclusion=%r 非\"通过\"（须独立审稿后写）"
            % meta.get("review_conclusion")
        )
    if meta.get("blind_test_result") != "通过":
        details.append(
            "blind_test_result=%r 非\"通过\"（须盲测试答后写）"
            % meta.get("blind_test_result")
        )

    if details:
        ctx["failures"].append("R14 审稿记录不全/未通过：" + "；".join(details))


def _count_check_items(s):
    """R15 自检要素条数：1./2. 或 ①②③ 或 一是二是 或 分号/问号分条。"""
    circled = len(CIRCLED_NUM_RE.findall(s))
    arabic = len(ARABIC_ITEM_RE.findall(s))
    shi = len(SHI_ITEM_RE.findall(s))
    counts = [c for c in (circled, arabic, shi) if c >= 2]
    if counts:
        return max(counts)
    if "；" in s or ";" in s:
        return len([seg for seg in re.split(r"[；;]", s) if seg.strip()])
    q = s.count("？") + s.count("?")
    if q >= 2:
        return q
    return 1


def check_r15(ctx):
    """R15 自查判据：self_check 2-3 条自检要素 + 一个适用判断；
    与 exercise 的迁移任务不重复。"""
    pending = ctx["pending"]
    sc = pending.get("self_check") or ""
    details = []
    items = _count_check_items(sc)
    if items < 2 or items > 3:
        details.append(
            "自检要素 %d 条（须 2-3 条，分条线索 1./2. 或 ①②③ 或 一是二是 或 分号/问号）"
            % items
        )
    if not any(cue in sc for cue in APPLICABLE_JUDGE_CUES):
        details.append(
            "缺适用判断线索（什么时候用/不适用/若…则，如 %s）"
            % list(APPLICABLE_JUDGE_CUES[:6])
        )
    sc_bg = _content_bigrams(sc)
    ex_bg = _content_bigrams(pending.get("exercise") or "")
    if sc_bg and ex_bg:
        overlap = len(sc_bg & ex_bg) / max(1, len(sc_bg))
        if overlap >= 0.8 and any(v in sc for v in TASK_VERBS):
            details.append(
                "self_check 与 exercise 重复（共享实词约 %.0f%% 且含任务动词），"
                "自查须与练习分离" % (overlap * 100)
            )
    if details:
        ctx["failures"].append("R15-自查判据：" + "；".join(details))


# ---------------------------------------------------------------------------
# 规则注册（按序执行；R4 含三个子检查于 check_r4 内）
# ---------------------------------------------------------------------------

RULES = {
    "R0": check_r0,
    "R1": check_r1,
    "R2": check_r2,
    "R3": check_r3,
    "R4": check_r4,
    "R5": check_r5,
    "R6": check_r6,
    "R7": check_r7,
    "R8": check_r8,
    "R9": check_r9,
    "R10": check_r10,
    "R11": check_r11,
    "R12": check_r12,
    "R13": check_r13,
    "R14": check_r14,
    "R15": check_r15,
}


# ---------------------------------------------------------------------------
# 加载与 CLI
# ---------------------------------------------------------------------------

def load_meta(path):
    """加载 draft_meta JSON（UTF-8 无 BOM：utf-8 读取，带 BOM 将解析失败被拒）。
    语法/读取错误返回 (None, err)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, str(e)


def load_pending(path):
    """加载 pending_tips.json（Task4 定稿 15 字段，与引擎 SCHEMA_KEYS 一致：
    恰好 15 个顶层 key、全部非空字符串）。返回 (dict, err)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, str(e)
    if not isinstance(data, dict):
        return None, "顶层须为 JSON object"
    missing = [k for k in PENDING_FIELDS
               if not isinstance(data.get(k), str) or not data[k].strip()]
    if missing:
        return None, "15 字段缺失/为空: %s" % ", ".join(missing)
    extra = sorted(set(data.keys()) - set(PENDING_FIELDS))
    if extra:
        return None, "发现多余字段（引擎同样拒绝）: %s" % ", ".join(extra)
    return data, None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="structured-daily 出厂规则门禁（R0-R15 全量，最终出厂程序）"
    )
    parser.add_argument(
        "--line", required=True, choices=["tips", "answer"],
        help="产出线：阶段 1 只实现 tips；answer 阶段 2 启用",
    )
    parser.add_argument(
        "--pending", default=None,
        help="pending_tips.json 路径（Task4 定稿 15 字段）",
    )
    parser.add_argument(
        "--meta", default=None, help="draft_meta.json 路径",
    )
    args = parser.parse_args(argv)

    # answer 线预留：阶段 2 启用
    if args.line == "answer":
        print("[SKIP] --line answer：答题线规则阶段 2 启用（当前仅实现 tips）")
        return 2

    ctx = {"args": args, "meta": None, "pending": None,
           "failures": [], "index_source_root": None}

    # R0：读源记录必填（meta 缺失或文件不存在）
    check_r0(ctx)
    if ctx["failures"]:
        for fail in ctx["failures"]:
            print("[FAIL] %s" % fail)
        return 1

    # meta 与 pending 必须齐备（全量门禁）
    if not args.meta:
        print("[FAIL] 参数不足：未提供 --meta，读源记录无可检对象")
        return 2
    if not args.pending:
        print("[FAIL] 参数不足：未提供 --pending（15 字段内容无可检对象）")
        return 2

    meta, err = load_meta(args.meta)
    if err is not None:
        print("[FAIL] META 加载失败（须 UTF-8 无 BOM 合法 JSON）：%s" % err)
        return 2
    if not isinstance(meta, dict):
        print("[FAIL] META 加载失败：顶层须为 JSON object")
        return 2
    ctx["meta"] = meta

    pending, err = load_pending(args.pending)
    if err is not None:
        print("[FAIL] PENDING 加载失败（须 UTF-8 无 BOM 合法 JSON，恰好 15 字段）：%s" % err)
        return 2
    ctx["pending"] = pending

    # 按注册顺序执行规则
    for name in RULES:
        RULES[name](ctx)

    if ctx["failures"]:
        for fail in ctx["failures"]:
            print("[FAIL] %s" % fail)
        return 1

    print("[OK] content_rules 全过（R0-R15）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

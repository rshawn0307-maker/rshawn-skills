---
name: structured-daily
description: 一条技能两种出图模式（旧版「总分总」纸感 VI，1080×1440 PNG 直出，不走 Word）。说「考官视角 / 展开说说 / 万能展开法 / 这题怎么展开 / 讲点技巧」→ 技巧线：封面＋分档展开法（AIR/Pro/Pro Max）＋避坑＋品牌页；说「答一道 / 出题 / 每日一练 / 结构化面试练习」→ 答题线：封面＋思维导图＋逐字稿（自动分页）＋收尾引流＋品牌页。两线都走「六条底色＋反程序化门禁」（check_voice：框架密度/取舍判断/推进变化/现场细节/边界意识）；答题线另走完整 10 步门禁（humanizer-zh 诊断/改写、盲测、CHECKPOINT）。渲染引擎 scripts/render_cards.py（PIL 直出，Songti SC＋品牌 logo），内容契约见 references/content-voice.md，视觉契约见 references/DESIGN.md。
version: 4.2.0（v4 双模式 + 内容反程序化 + humanizer-zh 去 AI 味，2026-11-26）
author: Shawn × AI（2026-11 重构：答一道单线 → 双模式合并；旧 Word 模板效果改为 PNG 直出）
metadata:
  triggers:
    - 考官视角
    - 展开说说
    - 万能展开法
    - 这题怎么展开
    - 讲点技巧
    - 答一道
    - 出题
    - 出一道题
    - 每日一练
    - 结构化面试练习
    - 做一篇结构化帖子
  outputs:
    - "答一道：vault 图片输出/第N期-{题型}-{主题}/（5–8 张 1080×1440 PNG + 笔记文案.md）"
    - "考官视角：vault 图片输出/展开说说-{主题}/（5–7 张 1080×1440 PNG + 笔记文案.md）"
    - "答一道进度：vault 图片输出/progress_answer.json（渲染成功后才追加 done）"
  prerequisites:
    - python3 + Pillow（本机实测 12.x）
    - 字体 Songti SC（/System/Library/Fonts/Supplemental/Songti.ttc）＋ SourceHanSansSC-Bold（~/Library/Fonts）
    - 品牌 logo：~/Desktop/AI工作区/01-Projects/公考橙皮书/assets/logo-zfz.png
    - humanizer-zh（去 AI 味诊断＋改写；check_prose 为 skill 内副本，来源 human-writing v1.2.0）
    - node + ima-skill（仅 IMA 上传，可选）
---

# 结构化双线出图（考官视角 / 答一道）

一条技能，两种模式。**共用同一套「总分总」纸感 VI**：深枣红封面、米金页脚带、宋体正文、右上竖排 logo、正文水印 —— 即旧 Word 模板的视觉效果，现在由 `scripts/render_cards.py` 直接渲染成 PNG，不再产出 docx。

## 模式判定（先判模式，再开工）

| 用户说法 | 模式 | 产物 |
|---|---|---|
| 考官视角 / 展开说说 / 万能展开法 / 这题怎么展开 / 讲点技巧 | **tips** | 封面 → 万能展开法总述 → AIR/Pro/Pro Max 分档 → 避坑/练习 → 品牌页（5–7 张） |
| 答一道 / 出题 / 每日一练 / 结构化面试练习 / 做一篇结构化帖子 | **answer** | 封面 → 思维导图 → 逐字稿（自动分页）→ 收尾引流 → 品牌页（5–8 张） |

两条线都禁止输出 Word/PDF；唯一发布载体是 PNG＋笔记文案.md。

## 模式 A：考官视角（tips）内容骨架

参考已跑出高流量的同类帖子结构，**一题一份、一档一层次**：

1. **封面**：`cover_title` 用带引号的题干核心短语（如「畅通群众监督渠道」），`cover_line2` 用追问句（如「具体怎么畅通？」）。
2. **总述页**：`overview_title` 用「面试中「X」万能展开法（分 N 档，直接套用）」；`overview_intro` 讲清闭环（怎么提、谁来接、何时回、有保障），并按档位说明每点句数（AIR 1–2 句、Pro 2–4 句），不要写「每点 12 句」这类与实际不符的话。
3. **分档递进**（`tiers`，至少 2 档，默认 3 档）：
   - `AIR 版`：3 个维度，时间紧张/追问时用，每点 1–2 句；
   - `Pro 版`：4 个维度（渠道/受理/反馈/保障 之类），逻辑最完整，推荐首选，每点 2–4 句；
   - `Pro Max 版`：在 Pro 上加 1 个差异化动作，拉开差距（如「群众监督员」「监督随手拍」）。
   - 每档 `points[]` 的 `lead` 是抓手（如「多元渠道覆盖」），`body` 是做法＋数字＋闭环；禁止空话（「加强管理」「高度重视」）。
4. **避坑**（`takeaway`）与**练习**（`practice`）可选：说明适用边界、误用方式、换题自查。
5. **引流**（`cta`）：一行红字，默认「关注我，后续分享更多面试实战技巧和考场避坑指南，帮你少走弯路，一次上岸」。
6. **品牌页**：引擎固定输出，不需数据。

口径：一档内每点必须「可落地、有实效、护权益」三者至少占其一；数据须有权威出处，现场不估算，拿不准就定性说。

## 模式 B：答一道（answer）内容骨架

沿用既有答题线，不改方法论：出题（热点自出 / 真题库 / 模拟题库）→ 审题五维 → 三观点大纲 → 定调版逐字稿（正文 700–800 汉字，硬边界 680–820）→ 门禁 → 出图。

- **封面**：`title_prefix` 作顶部 kicker（每日一练 / 历年考题），`question` 为题面（≤80 字，每行缩进）。
- **思维导图**（`mindmap`，answer 模式必填）：根「核心观点」＋ **≥4 条分支**（每条 3–5 个叶子，合计 **≥12 个叶子**，可再嵌一层）。叶子必须写具体抓手（「1 个工作日签收」「逐家电话回访」），不写抽象名词。这是旧版高流量帖的核心页；缺省会被 `check_voice` R1 判 FAIL。
- **逐字稿页**：`opening` ＋ 三组 `pointN_lead/pointN_body` ＋ `closing`，引擎按版面自动分页。
- **收尾引流**：`closing` 后画分隔线＋`cta` 红字。
- **品牌页**：引擎固定输出。

## 工作流

### 模式 B（答一道，10 步，一步不跳）

> **唯一豁免路径**：用户直接给出已达标的 final JSON（或承上轮已走完步 1–9 的定稿）时，可只执行步 10，并在报告里写明「沿用已定稿数据，步 1–9 未重跑」。除此以外不许跳步。

| 步 | 动作 | 依据 |
|---|---|---|
| 1 | 出题（题库优先：真题库/模拟题库定调版 → 讲义 → 热点自出需先写 `fact_card` 3 个可核查事实；题干 ≤80 字）→ 题干确认弹窗 → 四源读源＋审题五维 → 大纲 7 字段＋逐字稿 8 字段＋**mindmap（≥4 分支/≥12 叶子）** → `draft_meta` 落盘 | `references/content-voice.md`、`references/shared-sourcing.md`、`references/shared-calibration.md` |
| 2 | humanizer-zh 诊断（读其 31 条 AI 模式清单，扫描大纲与解说段，只出问题清单不改稿；逐字稿引文保真区不扫） | `references/shared-gates.md`、`~/.zcode/skills/humanizer-zh/SKILL.md` |
| 3 | humanizer-zh 改写（另起会话，按问题清单重写；只动措辞不改答题结构，事实/数字/教学事实源保真） | 同上 |
| 4 | `check_prose.py` 红线清零 + `check_voice.py` 反程序化 FAIL 清零（引文保真区不进 prose 检查） | `references/content-voice.md`、`references/shared-gates.md` |
| 5 | 回核读源 | 同上 |
| 6 | 独立审稿（8 查项，`review_conclusion=="通过"`） | 同上 |
| 7 | 盲测试答（四项判据，`blind_test_result=="通过"`） | `references/blind-test-protocol.md` |
| 8 | `content_rules.py --line answer` 出厂门禁（R0/R14 exit 0） | `scripts/content_rules.py` |
| 9 | CHECKPOINT 复核（两处弹窗记录齐备，**缺一不进渲染**） | `references/shared-gates.md` |
| 10 | 出图：写 final JSON（含 `mindmap`）→ `python3 scripts/render_cards.py --mode answer --final <json> --project-root <项目根> --outdir <期目录> --period-id <draft-id> --note <笔记文案.md>` → 引擎先跑版面自检（`verify_layout`），再目检全部 PNG → 报告张数/来源/是否写了 progress | `scripts/render_cards.py`、`references/DESIGN.md` |

**outdir 在 vault 之外**（演练、评测、临时目录）：省略 `--project-root` 与 `--period-id`，不写 progress、不追加期号，报告注明「未写期号进度」。不传 `--note` 时引擎不生成 `笔记文案.md`，交付清单里不要声称有。

### 模式 A（考官视角，6 步）

1. 定题：热点/政策/社会现象里选有张力的一问；封面标题 ≤14 字，追问句 ≤10 字。
2. 写总述＋分档 `points`（每档 2–4 点，lead＋body）。两道门禁：①红线自查——把每档「lead＋body」用「。」连接成检查文本（不要用「：」连接），跑 `python3 scripts/check_prose.py <临时文件>`；②反程序化——写 final JSON 后跑 `python3 scripts/check_voice.py --mode tips --final <json>`，FAIL 清零（AIR 整档 ≥1 个具体抓手，Pro/Pro Max 逐点 ≥1）。
3. 独立审稿：三查「是否每点都能落地」「数字是否有出处」「档位之间是否真递进」。审稿必须换视角：另起会话或派子 agent；无法另起时在报告标「自审，未独立」，不得声称已过独立审稿。
4. 写 final JSON（`mode=tips`）。
5. 出图：`python3 scripts/render_cards.py --mode tips --final <json> --outdir <目录>`；引擎先跑 `verify_layout`（内容页不得越 96/96 版心、不得压页脚）。
6. 目检：封面层级、分档标题不得落页尾孤行、避坑/练习是否落在末页；报告张数与每页要点。

模式 A 不做盲测（不是答题训练），但必须过禁用词与审稿两关。

## final JSON schema

### 模式 B（answer）

必填 13 字段：`question`、`break_angle`、`break_angle_reason`、`core_views_title`、`core_views_intro`、`opening`、`point1_lead`、`point1_body`、`point2_lead`、`point2_body`、`point3_lead`、`point3_body`、`closing`；`core_views` 必须恰 3 条非空字符串。

可选：
- `source`（`真题库` 时 `title_prefix` 必须为「结构化历年考题：」，否则引擎 FAIL）；
- `title_prefix`（默认「结构化每日一练：」）；
- `cover_meta`（封面题目信息行，如「2024年6月5日 · 咸阳 · 综合管理A」，引擎画在封面题面下方）；
- `cta`（默认沿用固定引流句）；
- `mindmap`（answer 必填）：`{"root":"核心观点","branches":[{"label":"一、…","children":[{"label":"…"},{"label":"…","children":[…]}]}]}`；分支 ≥4 条、叶子合计 ≥12 个（≤18），叶子 ≥6 字且为具体动作/时限/主体；超出单页会报「思维导图超出单页」需精简。

### 模式 A（tips）

必填：`cover_title`、`overview_title`、`overview_intro`、`tiers`（≥2 档，每档 `title` + `points[].lead`）。
可选：`cover_line2`、`kicker`、`tiers[].intro`、`takeaway{title,body}`、`practice`、`practice_title`、`cta`。

示例：

```json
{
  "mode": "tips",
  "cover_title": "“畅通群众监督渠道”",
  "cover_line2": "具体怎么畅通？",
  "overview_title": "面试中“畅通群众监督渠道”万能展开法（分 3 档，直接套用）",
  "overview_intro": "不讲“拓宽渠道”空话，讲清“怎么提、谁来接、何时回、有保障”的闭环。",
  "tiers": [
    {"title": "1.  AIR 版（3 个维度，时间紧张/追问时用）", "intro": "我会重点做好三件事。",
     "points": [{"lead": "多元渠道覆盖", "body": "线上新媒体＋线下传统渠道，让不同群体都有便捷反映途径；"}]},
    {"title": "2.  Pro 版（4 个维度，逻辑最完整，推荐首选）", "points": [{"lead": "全域渠道无死角", "body": "…"}]},
    {"title": "3.  Pro Max 版（加 1 个差异化动作，拉开差距）", "points": [{"lead": "群众监督员队伍", "body": "…"}]}
  ],
  "takeaway": {"title": "避坑提醒", "body": "…"},
  "cta": "关注我，后续分享更多面试实战技巧和考场避坑指南，帮你少走弯路，一次上岸"
}
```

## Pre-flight（缺一不开工）

```bash
python3 -c "import PIL; print(PIL.__version__)"
ls /System/Library/Fonts/Supplemental/Songti.ttc ~/Library/Fonts/SourceHanSansSC-Bold.otf
ls ~/Desktop/AI工作区/01-Projects/公考橙皮书/assets/logo-zfz.png
python3 scripts/render_cards.py --mode answer --final <json> --outdir <临时目录> --check   # 只校验数据，不写图
```

字体或 logo 缺失：引擎不静默降级——logo 缺失时页眉画红圆替代（不阻断）；字体缺失直接报错退出。

**项目根**：`~/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/结构化`（`--outdir` 仍在 `图片输出/`，唯一 vault 写授权）。

## 文件清单

| 位置 | 文件 | 用途 |
|---|---|---|
| skill | `scripts/render_cards.py` | **现行唯一引擎**：双模式 PIL 渲染（旧版 VI，1080×1440，封面/导图/内页/品牌页） |
| skill | `scripts/test_render_cards.py` | 引擎回归测试（双模式渲染、校验规则、导图溢出、折行避头尾） |
| skill | `references/DESIGN.md` | 视觉契约唯一事实源（v4：色板/字号梯/组件/两套页型/反模式） |
| skill | `references/shared-{calibration,sourcing,gates}.md` | 答题线方法论与门禁（不变） |
| skill | `references/content-voice.md` | **内容契约**：六条底色＋反程序化五条＋内容源优先级＋正面样例 |
| 外部 | `humanizer-zh`（同 skills 根目录） | 步 2 诊断 / 步 3 改写的唯一去 AI 味 skill（只读；31 条模式，保留事实与答题结构） |
| skill | `scripts/check_voice.py` / `scripts/test_check_voice.py` | 反程序化门禁（R1 框架密度/R2 开篇取舍/R3 推进变化/R4 现场细节/R5 注水标语/R6 节奏/R7 边界）＋10 用例 |
| skill | `references/shared-engine-safety.md` | 引擎安全机制与失败回退（v4 口径） |
| skill | `test-prompts.json` / `scripts/testdata/` | 达尔文测试集与固定输入夹具（dev/holdout 四条）；**测试资产**，评测快照会剔除 `test-prompts.json`，不得把夹具内容当正式选题 |
| skill | `references/blind-test-protocol.md` | 答题线盲测协议（不变） |
| skill | `scripts/check_prose.py` / `content_rules.py` | 红线检查 / 出厂门禁（不变） |
| skill | `scripts/render_answer_cards.py` | v3「简洁风」旧引擎与测试 —— **归档保留，不再执行**（供回滚） |
| skill | `scripts/fill_answer_post.py` / `assets/answer-template-baseline.docx` | docx 旧产线 —— **归档保留，不再执行** |
| vault | `图片输出/第N期-题型-主题/` | 答一道期目录（PNG＋笔记文案.md；`progress_answer.json` 追加 done） |
| vault | `图片输出/展开说说-{主题}/` | 考官视角目录（PNG＋笔记文案.md，不占期号） |

## 自测（改引擎必跑）

```bash
python3 scripts/test_render_cards.py      # 渲染：双模式/校验/导图/折行/右缘
python3 scripts/test_check_voice.py       # 内容：反程序化门禁 10 用例
python3 scripts/test_check_prose.py       # check_prose（不变）
python3 scripts/test_content_rules.py     # R0/R14（不变）
```

旧引擎 `test_render_answer_cards.py` 仅回滚时跑。

## 失败处理

- 校验失败（缺字段/档位不足/真题前缀不符/导图过大）：`--check` 即暴露，不建目录、不落盘。
- 渲染失败：不写 progress、不留半套图；修数据后重跑。
- `verify_layout` FAIL：先看报告的页码与右缘数值。缩进/折行导致的越界属引擎缺陷，修引擎并补回归，不许靠减字掩盖；确认是文本确实过长时才删字（模式 A 每点 body ≤120 字；模式 B 按 680–820 硬边界）。

## 硬禁令（真实踩过的坑）

1. **不许新建第二渲染入口**。有人会另写 `render_tips_paged.py` 之类脚本重排——成品一旦出自第二入口，就绕过了 `verify_layout`、回归测试与契约。版面问题改 `render_cards.py` 并补测试，不许旁路。
2. **不许把 `scripts/testdata/` 的内容当正式选题发布**。夹具里的导图/题面可能互不对应，只用于引擎回归；正式出稿必须自拟且导图与题干对齐。
3. **不许自审冒充独立审稿**。另起会话/子 agent 才叫独立；做不到就在报告标「自审，未独立」。
4. **不许注水凑页**。张数由内容与分页决定，禁止为凑 5–8 张加空段或重复观点；张数超出范围先查内容长度，不是加页。
5. **不许用中文冒号连接检查文本**。`check_prose` 会把「lead：body」判成红线；用「。」连接后再检。

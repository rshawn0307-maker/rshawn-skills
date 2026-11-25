---
name: structured-daily
description: 一条技能两种出图模式（旧版「总分总」纸感 VI，1080×1440 PNG 直出，不再走 Word）。说「考官视角 / 展开说说 / 万能展开法 / 这题怎么展开」→ 出技巧线：封面＋分档展开法（AIR/Pro/Pro Max）＋避坑＋品牌页；说「答一道 / 出题 / 每日一练 / 结构化面试练习」→ 出答题线：封面＋思维导图＋逐字稿（自动分页）＋收尾引流＋品牌页。两线共享出题/审题/逐字稿门禁、电车站诊断、check_prose 红线、独立审稿与盲测验收；渲染引擎 scripts/render_cards.py（PIL 直出，字体 Songti SC ＋ 品牌 logo）。视觉契约见 references/DESIGN.md（v4 旧版复刻）。
version: 4.0.0（v4 双模式 + 旧版纸感 VI 复刻，2026-11-25）
author: Shawn × AI（2026-11 重构：答一道单线 → 双模式合并；旧 Word 模板效果改为 PNG 直出）
metadata:
  triggers:
    - 考官视角
    - 展开说说
    - 万能展开法
    - 这题怎么展开
    - 答一道
    - 出题
    - 出一道题
    - 每日一练
    - 结构化面试练习
    - 做一篇结构化帖子
  outputs:
    - "答一道：vault 图片输出/第N期-{题型}-{主题}/（6–8 张 1080×1440 PNG + 笔记文案.md）"
    - "考官视角：vault 图片输出/展开说说-{主题}/（5–7 张 1080×1440 PNG + 笔记文案.md）"
    - "答一道进度：vault 图片输出/progress_answer.json（渲染成功后才追加 done）"
  prerequisites:
    - python3 + Pillow（本机实测 12.x）
    - 字体 Songti SC（/System/Library/Fonts/Supplemental/Songti.ttc）＋ SourceHanSansSC-Bold（/Users/shawn/Library/Fonts）
    - 品牌 logo：/Users/shawn/Desktop/AI工作区/01-Projects/公考橙皮书/assets/logo-zfz.png
    - 电车站 tramstop-skill（去 AI 味诊断）；human-writing（改写；check_prose 为 skill 内副本）
    - node + ima-skill（仅 IMA 上传，可选）
---

# 结构化双线出图（考官视角 / 答一道）

一条技能，两种模式。**共用同一套「总分总」纸感 VI**：深枣红封面、米金页脚带、宋体正文、右上竖排 logo、正文水印 —— 即旧 Word 模板的视觉效果，现在由 `scripts/render_cards.py` 直接渲染成 PNG，不再产出 docx。

## 模式判定（先判模式，再开工）

| 用户说法 | 模式 | 产物 |
|---|---|---|
| 考官视角 / 展开说说 / 万能展开法 / 这题怎么展开 / 讲点技巧 | **tips** | 封面 → 万能展开法总述 → AIR/Pro/Pro Max 分档 → 避坑/练习 → 品牌页（5–7 张） |
| 答一道 / 出题 / 每日一练 / 结构化面试练习 / 做一篇结构化帖子 | **answer** | 封面 → 思维导图 → 逐字稿（自动分页）→ 收尾引流 → 品牌页（6–8 张） |

两条线都禁止输出 Word/PDF；唯一发布载体是 PNG＋笔记文案.md。

## 模式 A：考官视角（tips）内容骨架

参考已跑出高流量的同类帖子结构，**一题一份、一档一层次**：

1. **封面**：`cover_title` 用带引号的题干核心短语（如「畅通群众监督渠道」），`cover_line2` 用追问句（如「具体怎么畅通？」）。
2. **总述页**：`overview_title` 用「面试中「X」万能展开法（分 N 档，直接套用）」；`overview_intro` 讲清闭环（怎么提、谁来接、何时回、有保障），并声明每点约 12 句话、可落地。
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
- **思维导图**（`mindmap`，强烈建议提供）：根「核心观点」＋ 3–4 条分支（每条 3–5 个叶子，可再嵌一层）。这是旧版高流量帖的核心页，缺省时退化为「答题思路」页。
- **逐字稿页**：`opening` ＋ 三组 `pointN_lead/pointN_body` ＋ `closing`，引擎按版面自动分页。
- **收尾引流**：`closing` 后画分隔线＋`cta` 红字。
- **品牌页**：引擎固定输出。

## 工作流

### 模式 B（答一道，10 步，一步不跳）

| 步 | 动作 | 依据 |
|---|---|---|
| 1 | 出题（三选一，题干 ≤80 字，`len()` 自检）→ 题干确认弹窗 → 四源读源＋审题五维 → 大纲 7 字段＋逐字稿 8 字段＋**思维导图树** → `draft_meta` 落盘 | `references/shared-sourcing.md`、`references/shared-calibration.md` |
| 2 | 电车站诊断（tramstop 模式一） | `references/shared-gates.md` |
| 3 | human-writing 改写（另起会话） | 同上 |
| 4 | `check_prose.py` 红线清零（引文保真区不进检查） | `references/shared-gates.md` |
| 5 | 回核读源 | 同上 |
| 6 | 独立审稿（8 查项，`review_conclusion=="通过"`） | 同上 |
| 7 | 盲测试答（四项判据，`blind_test_result=="通过"`） | `references/blind-test-protocol.md` |
| 8 | `content_rules.py --line answer` 出厂门禁（R0/R14 exit 0） | `scripts/content_rules.py` |
| 9 | CHECKPOINT 复核（两处弹窗记录齐备） | `references/shared-gates.md` |
| 10 | 出图：写 16 键 final JSON（含 `mindmap`）→ `python3 scripts/render_cards.py --mode answer --final <json> --project-root <项目根> --outdir <期目录> --period-id <draft-id>` → 目检全部 PNG → 报告 | `scripts/render_cards.py`、`references/DESIGN.md` |

### 模式 A（考官视角，6 步）

1. 定题：热点/政策/社会现象里选有张力的一问；封面标题 ≤14 字，追问句 ≤10 字。
2. 写总述＋分档 `points`（每档 2–4 点，lead＋body），禁用词自查（`check_prose.py` 同口径：体现/彰显/凸显/高度重视/加强管理…）。
3. 独立审稿：三查「是否每点都能落地」「数字是否有出处」「档位之间是否真递进」。
4. 写 final JSON（`mode=tips`）。
5. 出图：`python3 scripts/render_cards.py --mode tips --final <json> --outdir <目录>`。
6. 目检：封面、分档页是否溢版、避坑/练习是否落在末页；报告张数与每页要点。

模式 A 不做盲测（不是答题训练），但必须过禁用词与审稿两关。

## final JSON schema

### 模式 B（answer）

必填 13 字段：`question`、`break_angle`、`break_angle_reason`、`core_views_title`、`core_views_intro`、`opening`、`point1_lead`、`point1_body`、`point2_lead`、`point2_body`、`point3_lead`、`point3_body`、`closing`；`core_views` 必须恰 3 条非空字符串。

可选：
- `source`（`真题库` 时 `title_prefix` 必须为「结构化历年考题：」，否则引擎 FAIL）；
- `title_prefix`（默认「结构化每日一练：」）；
- `cover_meta`（封面题目信息行，如「2024年6月5日 · 咸阳 · 综合管理A」）；
- `cta`（默认沿用固定引流句）；
- `mindmap`：`{"root":"核心观点","branches":[{"label":"一、…","children":[{"label":"…"},{"label":"…","children":[…]}]}]}`；分支 3–4 条、叶子合计 ≤18 个，超出会报「思维导图超出单页」需精简。

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
    {"title": "1.  AIR 版（3 个维度，时间紧张/追问时用）", "intro": "我会重点做好三件事：",
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
ls /System/Library/Fonts/Supplemental/Songti.ttc /Users/shawn/Library/Fonts/SourceHanSansSC-Bold.otf
ls "/Users/shawn/Desktop/AI工作区/01-Projects/公考橙皮书/assets/logo-zfz.png"
python3 scripts/render_cards.py --mode answer --final <json> --check   # 只校验数据
```

字体或 logo 缺失：引擎不静默降级——logo 缺失时页眉画红圆替代（不阻断）；字体缺失直接报错退出。

**项目根**：`/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/结构化`（`--outdir` 仍在 `图片输出/`，唯一 vault 写授权）。

## 文件清单

| 位置 | 文件 | 用途 |
|---|---|---|
| skill | `scripts/render_cards.py` | **现行唯一引擎**：双模式 PIL 渲染（旧版 VI，1080×1440，封面/导图/内页/品牌页） |
| skill | `scripts/test_render_cards.py` | 引擎回归测试（双模式渲染、校验规则、导图溢出、折行避头尾） |
| skill | `references/DESIGN.md` | 视觉契约唯一事实源（v4：色板/字号梯/组件/两套页型/反模式） |
| skill | `references/shared-{calibration,sourcing,gates,engine-safety}.md` | 答题线方法论与门禁（不变） |
| skill | `references/blind-test-protocol.md` | 答题线盲测协议（不变） |
| skill | `scripts/check_prose.py` / `content_rules.py` | 红线检查 / 出厂门禁（不变） |
| skill | `scripts/render_answer_cards.py` | v3「简洁风」旧引擎与测试 —— **归档保留，不再执行**（供回滚） |
| skill | `scripts/fill_answer_post.py` / `assets/answer-template-baseline.docx` | docx 旧产线 —— **归档保留，不再执行** |
| vault | `图片输出/第N期-题型-主题/` | 答一道期目录（PNG＋笔记文案.md；`progress_answer.json` 追加 done） |
| vault | `图片输出/展开说说-{主题}/` | 考官视角目录（PNG＋笔记文案.md，不占期号） |

## 自测（改引擎必跑）

```bash
python3 scripts/test_render_cards.py      # 新引擎：双模式/校验/导图/折行
python3 scripts/test_check_prose.py       # check_prose（不变）
python3 scripts/test_content_rules.py     # R0/R14（不变）
```

旧引擎 `test_render_answer_cards.py` 仅回滚时跑。

## 失败处理

- 校验失败（缺字段/档位不足/真题前缀不符/导图过大）：`--check` 即暴露，不建目录、不落盘。
- 渲染失败：不写 progress、不留半套图；修数据后重跑。
- 目检发现溢版：先减字数（模式 A 每点 body ≤120 字；模式 B 按 680–820 硬边界），不要改引擎常量绕开。

---
name: structured-daily
description: 自动化生成「结构化每日一练」答题帖 docx：出题（热点自出 / 真题库 / 模拟题库三选一）＋审题五维＋思路大纲＋定调版逐字稿（opening+三观点 lead/body+closing，正文 700–800 汉字不含标点，硬边界 680–820），电车站诊断/改写、check_prose 门禁、独立审稿、盲测验收、pending_answer 套版式出稿一气呵成，保留模板配图/引流段样式。用户说「答一道 / 出题 / 出一道题 / 每日一练 / 结构化面试练习 / 做一篇结构化帖子」等出题作答类表述时触发。本技能接替 structured-post（触发词全盘接替，防双触发由 TR3 归档旧技能保证）；原双线（技巧线/答题线）已收敛为本答一道单线。
version: 3.0.0
author: Shawn × AI（2026-11 重构；TR1 答一道单线转型）
metadata:
  triggers:
    - 答一道
    - 出题
    - 出一道题
    - 每日一练
    - 结构化面试练习
    - 做一篇结构化帖子
  outputs:
    - 覆盖 vault docx 模板（desktop-attachments/1 结构化每日一练-帖子内容编辑模板.docx）
    - scripts/_snapshots/ 快照（最多 10 个）
  prerequisites:
    - python3 + python-docx 1.2.0
    - 电车站 tramstop-skill（去 AI 味诊断）
    - human-writing（改写；check_prose 已收录为 skill 内副本 `scripts/check_prose.py`，上游更新手动同步）
    - node + ima-skill（仅 IMA 上传，可选）
---

# 结构化每日一练（答一道）

技术技能：答一道单线——出题＋思路框架（破题角度+3 观点）＋定调版逐字稿，学生直接参考练习。

> **接替说明（历史，全文件唯一处）**：本技能由双线（技巧线/答题线）收敛为答一道单线，触发词全盘接替旧 structured-post；旧技巧线资产已删除（git 历史可找回），旧技能归档由 TR3 落地。本文件其余部分不再涉及旧线。

## 工作流总览（答一道 10 步，一步不跳）

| 步 | 动作 | 依据 |
|---|---|---|
| 1 | 出题 + 读源 + 审题 + 草稿：题目三选一（热点自出 / 真题库 / 模拟题库，题干 ≤80 字硬上限，写完 `len()` 自检）→ 题干确认弹窗（CHECKPOINT 第一处，用户选"换一道"回本步）→ 四源读源（讲义定源一本通对应章节）+ 审题五维 + 读源四要素 → 大纲区 7 字段 + 逐字稿 8 字段草稿（定调版口径）→ draft_meta 落盘（answer 扩展字段必填） | 本文件「出题规则」「封面前缀铁律」、`references/shared-sourcing.md`（四源/审题五维/draft_meta schema）、`references/shared-calibration.md`（定调版口径） |
| 2 | 电车站诊断 agent（tramstop 模式一，读 checklist 四层扫描）：扫大纲与解说段；逐字稿引自题库定调版时为教学事实源保真区，不扫措辞不改一字 | `references/shared-gates.md` 步 2 与「电车站诊断 agent 契约」 |
| 3 | human-writing 改写 agent（另起会话，白熊隔离）：只动大纲/解说措辞（新写逐字稿含措辞），逐字稿引文保真；保留字段前缀 | `references/shared-gates.md` 步 3 与「human-writing 改写 agent 契约」 |
| 4 | check_prose.py 程序红线清零：检查文本=改写后大纲/解说＋新写逐字稿 8 字段（引文保真区不进检查文本）；FAIL 项清零才过，不可用即 STOP 无降级 | `references/shared-gates.md` 步 4 |
| 5 | 回核读源：改写稿对四源回核，术语/条件/方法含义不丢；教学事实源严禁改写 | `references/shared-gates.md` 步 5 |
| 6 | 独立审稿（换视角/评审代理）：8 查项逐项证据，`review_conclusion=="通过"` 才进盲测；任一查项不过回步 3 | `references/shared-gates.md` 步 6 与「独立审稿查项」 |
| 7 | 盲测试答出厂验收：学生 persona 只读帖子全文（题目+思路大纲+逐字稿），独立产出新题完整定调版答题；判据四项全过 `blind_test_result=="通过"`，未过回炉（回步 3） | `references/blind-test-protocol.md`、`references/shared-gates.md` 步 7 |
| 8 | content_rules 出厂程序门禁：`python3 scripts/content_rules.py --line answer --pending <pending_answer> --meta <draft_meta>`，R0/R14 exit 0 才进 CHECKPOINT | `scripts/content_rules.py`、`references/shared-gates.md` 步 8 |
| 9 | CHECKPOINT 复核：两处弹窗记录齐备（①步 1 题干确认 ②步 4 后成稿前后对比 3-5 处），缺一不进渲染 | `references/shared-gates.md` 步 9 与「CHECKPOINT 用户弹窗」 |
| 10 | 出稿：draft 写入 `pending_answer.json` → 引擎生成 docx（exit 0）→ 渲染近似检查 → 向用户报告 | `references/shared-engine-safety.md`、`references/shared-gates.md` 步 10 |
| 后置 | 发布后第 7 天数据回填：阅读/收藏/反馈关键词写入 vault `scripts/daily_metrics.json`；收藏率=收藏÷第 7 天阅读；不阻塞出厂 | vault `scripts/daily_metrics.json` |

IMA 上传是可选附加步（仅用户明确要求时执行）：node + ima-skill。

## 出题规则（步 1，自出题适用；真题库/模拟题库题干已固定，只做字数与可答性检查）

- **题干必须 ≤80 字（硬上限）**：超过 80 字阅读节奏断档、热点反差感丢失；写完先 `len(question)` 自检，超就砍。
- 选题优先近期热点且适合结构化题目的话题：有矛盾张力、能多角度展开；热点话题、政策类、社会现象为首选题材；避免过于专业的岗位题，用户指定岗位时按指定岗位出题。
- **真题库/模拟题库选题**：题干照录，用户确认后作答，不再自出题；路径与双根口径见 `references/shared-sourcing.md`（题库双根：模拟题根＋真题根）。
- **收尾类型在草稿阶段定**：判据式（40–60 汉字）或总结式（80–100 汉字），记入 draft_meta `closing_type`；口径见 `references/shared-calibration.md`。

## Pre-flight 检查（缺一不开工）

### ① 项目根核实

**项目根** = vault 路径 `/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/结构化`。核实模板存在：

```bash
ls "/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/结构化/desktop-attachments/1 结构化每日一练-帖子内容编辑模板.docx" && echo "✅ 路径正确" || echo "❌ 路径错，先确认"
```

引擎不依赖 cwd，一律用 `--project-root "<项目根>"` 显式传入（或环境变量 `ANSWER_PROJECT_ROOT`）。

**模板防混用**：desktop-attachments 下若同时有 `2 展开说说-帖子内容编辑模板.docx` 等其他系列模板，那是另一套，**别混用**——脚本不通用，跑错模板会破坏版式。

### ② Python 环境

```bash
python3 -c "import docx; print(docx.__version__)"   # 期望 1.2.0
```

- **命令陷阱**：本机用 `python3` / `pip3`，不是 `python`。
- **包名陷阱**：装包用 `pip install python-docx`，不是 `pip install docx`（会装同名垃圾包）。

### ③ 引擎唯一入口

唯一执行引擎是 **skill 内 `scripts/fill_answer_post.py`**（自 structured-post 引擎 v2 原样移植：19 段 5 图契约 / 写入前段数预检 / 快照 / 写入后验证，exit 0/1）。项目根 `scripts/` 下遗留的 `fill_structured_post.py`（旧 post 引擎）**已废弃勿用**；旧 `fill_tips_post.py` 已随技巧线退役删除。安全机制与失败回退见 `references/shared-engine-safety.md`。

## 文件清单

| 位置 | 文件 | 用途 |
|---|---|---|
| skill | `SKILL.md` | 本文件：工作流总览 / 出题规则 / Pre-flight / 模板铁律 |
| skill | `references/shared-calibration.md` | 定调版口径唯一事实源（字数/8 字段/三禁/收尾两型） |
| skill | `references/shared-sourcing.md` | 四源读源（讲义定源一本通）+ 审题五维 + draft_meta 统一 schema |
| skill | `references/shared-gates.md` | 门禁栈 10 步流水线 + 诊断/改写契约 + 独立审稿 8 查项 |
| skill | `references/shared-engine-safety.md` | 引擎安全机制、失败回退与沙箱回归纪律 |
| skill | `references/blind-test-protocol.md` | 盲测试答出厂验收协议（学生 persona / 判据四项 / 白盒禁令） |
| skill | `scripts/fill_answer_post.py` | 答一道引擎（19 段 5 图 / 写入前段数预检 / 快照 / 写入后验证，exit 0/1） |
| skill | `scripts/test_fill_answer_post.py` | 引擎回归测试（沙箱临时副本；真实模板 sha256 前后断言） |
| skill | `scripts/content_rules.py` | 出厂规则门禁（R0 读源记录 / R14 审稿记录，`--line answer`） |
| skill | `scripts/test_content_rules.py` | content_rules 自测（R0/R14 answer 用例） |
| skill | `scripts/check_prose.py` | 通用红线检查：human-writing v1.2.0 副本+公考高危词叠加+字段前缀冒号豁免 |
| skill | `scripts/test_check_prose.py` | check_prose 自测（6 用例） |
| skill | `scripts/test-prompts.json` | 冻结自测提示集（答题线 3 场景：全流程 / 失败边界 / 盲测出厂） |
| skill | `assets/answer-template-baseline.docx` | 模板 baseline（19 段 5 图，只读复制自 vault 模板 1，sha256 一致；沙箱回归与漂移恢复用） |
| vault | `desktop-attachments/1 结构化每日一练-帖子内容编辑模板.docx` | 活模板（唯一写目标，覆盖写入） |
| vault | `scripts/pending_answer.json` | 中间文件（引擎读取成功后自动删除） |
| vault | `scripts/_snapshots/` | 引擎自动快照（最多 10 个，超出按修改时间倒序清理） |
| vault | `scripts/daily_metrics.json` | 发布后指标回填（第 7 天，轻量效果回收） |

**事实源约定**：读源/选题素材事实源在 vault（方法论/一本通/题库双根/教师注，见 `references/shared-sourcing.md`）；效果指标事实源为 vault `scripts/daily_metrics.json`。答一道线不设索引与 progress 台账（T2 裁定保持现状）。

## 模板铁律（19 段 5 图契约，本表为准）

- 模板契约：**19 段 / w:drawing 5 图 / 16 必填字段**；引擎 `scripts/fill_answer_post.py` 按下表段位写入（表自引擎 `REPLACE_MAP` 提取）。
- **图数口径：`w:drawing == 5`**（引擎 validate 按此口径，现行健康）；封面文本框双镜像 `txbxContent == 2`（drawing 镜像 + VML fallback）。
- **字体铁律**：通用字体（微软雅黑等），不引云字体、不内嵌字体文件。
- **写目标唯一**：vault `desktop-attachments/1 结构化每日一练-帖子内容编辑模板.docx`；`assets/answer-template-baseline.docx` 为其只读 baseline（sha256 一致），只用于沙箱回归与漂移恢复，**永远不作为写目标**。

### 19 段段位映射表（逐段）

| 段 | 内容 | 引擎行为 |
|---|---|---|
| 0 | 封面文本框：前缀 + 题目正文 | 写入 `title_prefix` + `question`，2 镜像同步，前缀字体保留 |
| 1 | 标题"答题思路"（Heading 2） | 不动 |
| 2 | `break_angle`（破题角度） | 替换 |
| 3 | `break_angle_reason`（切入理由） | 替换 |
| 4 | `core_views_title`（核心观点标题） | 替换 |
| 5 | `core_views_intro`（观点导语） | 替换 |
| 6 | `core_views[0]` | 替换 |
| 7 | `core_views[1]` | 替换 |
| 8 | `core_views[2]` | 替换 |
| 9 | `opening`（正文首段） | 替换 + 强制 pageBreakBefore（正文从第 3 页开始，大纲区分页符清除） |
| 10 | `point1_lead` | 替换 |
| 11 | `point1_body` | 替换 |
| 12 | `point2_lead` | 替换 |
| 13 | `point2_body` | 替换 |
| 14 | `point3_lead` | 替换 |
| 15 | `point3_body` | 替换 |
| 16 | `closing`（收束段） | 替换 |
| 17 | 引流段（居中 + 加粗 + #85120F） | 不动（原文与样式冻结） |
| 18 | 末尾装饰图 | 不动 |

- 固定不动段：1（标题）、17（引流段）、18（末图）；写入只找"第一个纯文本 run"，图片 run 完全不动。
- 5 图分布含封面文本框形状（引擎按 w:drawing 总数 5 校验，与模板 1 实测一致）。

### 封面前缀铁律（随来源切换）

封面文本框前缀由 `title_prefix` 控制，引擎写入段[0] 两个镜像并按该值校验：

| 题目来源 | `source` | `title_prefix` |
|---------|----------|----------------|
| 热点自出题 | 可省略或 `自出题` | `"结构化每日一练："`（可省略，默认值） |
| **真题库选题** | **`"真题库"`** | **必须** `"结构化历年考题："` |
| 模拟题库选题 | `"模拟题库"` | `"结构化每日一练："`（可省略，默认值） |

真题库来源时**必须同时**写 `source` 与 `title_prefix`；`source` 含「真题」却漏传或传错前缀时引擎直接报错退出，防止静默用错封面。报告里写明本次来源类型和封面前缀。

### pending_answer.json schema（16 必填 + 2 可选，与引擎 REPLACE_MAP 同表）

必填（缺任一引擎即拒）：`question` ＋ 大纲区 7 字段（`break_angle` / `break_angle_reason` / `core_views_title` / `core_views_intro` / `core_views`[恰 3 元素]）＋ 逐字稿 8 字段（`opening` / `point1_lead` / `point1_body` / `point2_lead` / `point2_body` / `point3_lead` / `point3_body` / `closing`）。可选：`source`、`title_prefix`（语义见封面前缀铁律）。开场/收尾类型、诊断结论只进 draft_meta，不进 pending（引擎不消费）。JSON 字符串内部用中文双引号或转义 `\"`，推荐 Python `json.dump` 生成。

## 失败处理 / 回归测试

- 失败回退：引擎任何失败先看 `scripts/_snapshots/` 最新快照；写入失败时 `[KEEP] pending_answer.json 保留`，按报错逐项修后重跑。快照机制与沙箱回归纪律统一见 `references/shared-engine-safety.md`。
- 三套自测（改引擎/规则/检查器后必跑，全过才算交付）：
  ```bash
  python3 scripts/test_fill_answer_post.py   # 引擎沙箱 11 用例
  python3 scripts/test_content_rules.py      # R0/R14 answer 用例
  python3 scripts/test_check_prose.py        # check_prose 6 用例
  ```

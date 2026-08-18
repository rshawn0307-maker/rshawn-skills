---
name: PE-trial-daily
description: 自动化生成「体育试讲设计每日一练」小红书帖子 docx，并可同步上传到 ima 知识库「A-00 体育试讲设计每日一练」。基于 python-docx 从零构建品牌化 DOCX，从教师用书提取教学环节（热身游戏/体能游戏/练习环节），拆解成环节名称、活动方法、规则、设计意图、组织形式、易犯错误及纠正，最后串联成试讲逐字稿，含图例插图。触发词：体育试讲每日一练、试讲设计每日一练、出一期体育试讲设计。
---

# 体育试讲设计每日一练 · 自动出帖

## 适用场景

从人教版教师用书（313 个活动，9 个运动项目）中，每天拆解一个教学环节，生成一篇小红书帖子 docx：

- 第 1 页封面：整页底层背景图（behindDoc 锚定铺满，从「封面底版」提取）+ 品牌标题「体育试讲设计每日一练」（48pt 居中浅青）+ 运动项目标签 + 环节名称 + 难度，恰好一页
- 页面固定精确 3:4 手机版（15cm × 20cm，可配置 `config.default.json`）；正文/表格 ≥18pt，栏目标题 24–28pt，图注/标签 ≥16pt，CTA ≥18pt；字体用本机可渲染的 CJK 契约（Hiragino Sans GB 等）
- 第 2 页起：图例区（如教师用书有图例，等比放大，宽 ≥ 正文85% 或高填满可用区，与标题+图注同页）+ 环节拆解（名称/类型/方法/规则/意图/组织形式）+ 易犯错误与纠正表格（仅 practice 环节，固定总宽 42/58 列、禁 autofit、行不跨页）+ 试讲逐字稿（按教学阶段拆短段）+ 引流
- 引流行：#标签行 居中 + 灰色（#808080），固定引流段 居中 + 深蓝（#0B3289），两者均加粗；CTA 同页前至少保留 2 行正文

## 内容事实层（v2，任务1）

本技能已引入 v2「内容事实层」，核心库 `scripts/ptd_core.py` 负责稳定 ID、可生成视图、dry-run 迁移、事实锁定与 100 分量表，细节见 `references/r1-schema-and-scale.md`。要点：

- 稳定 ID `PTD-{seq}-{sport}-{name}`：重跑按 ID 幂等；原 313 条索引只读保留，新增视图是派生层。
- 字段区分 `provenance`：`textbook`（教材原文，必带 `book_file+行号+excerpt`）与 `adapted`（明确教学加工，事实 token 必须被证据覆盖或显式登记 `adapted_facts`）。
- 难度缺失绝不编星（`index_empty_adapted`）；practice 无教材纠错时，纠错不得标教材原文。
- 图例策略：`use_extracted`（确认归属+有 PDF）/ `misattributed_treat_as_none`（误收留证）/ `needs_ocr_verify`（无法核验，生成须 OCR 确认否则 STOP）/ `figure_required_but_pdf_missing`（有引用但缺 PDF/图 → STOP，非可生成）。
- 100 分量表（教材30/考编可用20/安全20/教学15/口语10/证据5），放行线总分≥85、教材≥27、安全≥16、硬门0；human-writing 改写后必须重跑事实锁定复核。
- 可生成视图 + dry-run 迁移表用 `scripts/build_generatable_view.py` 生成（默认输出到 /tmp，只读源数据）。

封面版式铁律（与「2 体育试讲每日一练-帖子内容编辑模板.docx」一致）：
- 封面大标题字号 48pt（浅青 #9FD8E8），整页铺底层背景图 `scripts/cover_bg.png`（behindDoc=1 锚定，置于文字下层）
- 封面必须恰好一页：封面表格浮动锚定整页（vertAnchor=page、行高 15290 atLeast），放大字号后仍不溢出到第 2 页
- 所有页面页眉叠加斜向水印「世豪老师」（VML PowerPlusWaterMarkObject，灰 #C0C0C0），封面页不放品牌文字只放水印
- 有图例时：图例等比放大（宽 ≥ 正文85% 或高填满可用区），与「图例直观」标题和图注同页；随后「环节拆解」标题用 page_break_before 另起一页置于最上端

内容结构铁律：
- 环节拆解必须覆盖全部 6 个维度（名称、类型、方法、规则、意图、组织形式）
- 试讲逐字稿必须包含：课堂导入 → 示范讲解 → 组织练习 → 个别纠错 → 互动游戏 → 课堂小结
- practice 环节必须有易犯错误与纠正表格
- 图例引用（如"图3-2-7"）必须先用 extract_pdf_image.py 提取真实图片，不许留空
- 引流两行（#标签行 + 固定引流段）紧接试讲逐字稿结尾后空一行直接写，不另起一页

## 关键路径（Pre-flight 必查）

| 路径 | 说明 |
|------|------|
| `/Users/shawn/Desktop/AI工作区/03-Resources/各版本体育教材/人教版/` | 教师用书源（MD + PDF，只读，9 本） |
| 本 skill 的 `scripts/fill_trial_daily_post.py` | 填充脚本（自带源，随 skill 分发） |
| 本 skill 的 `scripts/ptd_core.py` | 核心库（稳定 ID/可生成视图/事实锁定/100 分量表） |
| 本 skill 的 `scripts/build_generatable_view.py` | 生成可生成视图 + dry-run 迁移表 |
| 本 skill 的 `config.default.json` | 显式配置（地区/学段/片段时长/3:4 版式阈值） |
| 本 skill 的 `references/r1-schema-and-scale.md` | v2 内容层规范（schema/量表/流程/图例策略） |
| `/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编/scripts/activity_index.json` | 活动索引（313 条，只读） |
| `/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编/scripts/ocr_index/` | OCR 页索引（缓存，用于图例定位） |
| `/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编/scripts/progress_trial.json` | 选题进度 |
| `/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编/scripts/_snapshots_trial/` | 快照（回退用） |

Python：使用当前会话提供的 python3（已装 python-docx；未装 PyMuPDF/fitz，图像提取走 pdftoppm/poppler 链）。
调用统一加 `env -u PYTHONHOME -u PYTHONPATH`（外层会话注入的 PYTHONHOME/PYTHONPATH 会让 bundled python 崩溃）。

## 工作流编排（v3，任务3）

`scripts/ptd_workflow.py` 提供带锁 + 原子状态机的流水线编排：

- 依赖预检：`python3 ptd_workflow.py --check-deps`（docx/soffice/poppler/fc-match/swift，缺失即报，不装新依赖）。
- 工作区锁：`O_EXCL` 原子抢占，双进程只有一个成功；持锁失败者退出码非0，不删 pending。
- 状态机：`select → extract → factlock → rewrite_review → render_verify → docx_commit → progress_commit → upload_done`；
  状态文件临时写 + `os.replace` 原子提交；按 `(stable_id, content_hash)` 幂等，终态不重跑。
- OCR 缓存：`build_ocr_cache()` 原子写、记录 PDF 指纹(sha256)/页数/覆盖率；子进程非0 不落缓存。
- 图例：视图策略驱动——`figure_required_but_pdf_missing` → STOP；`misattributed_treat_as_none`/无引用 → 空图；
  `needs_ocr_verify`/`use_extracted` → OCR 索引精确匹配 caption 并裁图（`ocr_batch.swift` 已输出 bbox），失败 STOP。
- IMA：`FakeIMA` 本地 fake adapter 按 content_hash 幂等（记录 note_id/remote_id/stage，重复运行不新建笔记），仅本地验证不真实调用。

## 工作流（6 步）

### 步骤 1：选题

1. 读 `scripts/progress_trial.json`。确认它是合法 JSON，`done` 是无重复的 activity_name 列表，`last_done` 为空或存在于 `done`。任一项不满足，执行 🔴 STOP，不得选题或写文件。
2. 领导指定时，按运动项目+环节名定位。若唯一命中但已在 `done`，报告并 🔴 STOP。
3. 领导没指定时，从 `activity_index.json` 中选第一个 name 不在 `progress_trial.json` 的 `done` 中的活动。按 activity_index.json 原始顺序遍历。
4. 没有未完成活动时，报告 313 个全部完成并 🔴 STOP。

### 步骤 2：从教师用书提取内容

1. 根据活动索引中的 `book_file` 和 `md_line`，定位到对应 MD 文件中的原始内容段落。
2. 读取该活动附近的内容块，提取：
   - `【动作方法】` / `【活动方法】` / `【游戏方法】` → 活动方法
   - 方法附近关于规则/安全的描述 → 规则
   - 附近 `【素养要点】` 或上下文 → 设计意图
   - 上下文中的组织形式描述 → 活动组织形式
   - `【易犯错误与纠正方法】` → 易犯错误对
3. 检查 `figure_refs`，若含图例引用，调用 `extract_pdf_image.py` 提取图片。
4. 根据活动类型、方法、规则、意图、组织形式串联成试讲逐字稿。

### 步骤 3：写内容 JSON

按下面 schema 生成 `scripts/pending_trial_daily.json`：

```json
{
  "sport": "篮球",
  "chapter": "第三章 篮球运动教学内容 | 二、运球",
  "segment_name": "原地运球",
  "segment_type": "practice",
  "difficulty": "★★",
  "figure": "图3-2-7 原地低运球、图3-2-8 原地高运球",
  "figure_images": [".../图例_篮球_图327_p42.png"],
  "method": "活动方法描述（来自教师用书原文）",
  "rules": "规则描述",
  "intent": "活动设计意图",
  "organization": "活动组织形式",
  "errors": [
    ["易犯错误1", "纠正方法1"],
    ["易犯错误2", "纠正方法2"]
  ],
  "lecture_script": "试讲逐字稿全文（300-500字）",
  "cta": "关注我，每天一个体育试讲设计，帮你备考上岸",
  "hashtags": "#教师编 #体育教师 #体育试讲 #试讲设计 #一次上岸"
}
```

硬性要求：
- `segment_type` 必须是 `game` / `practice` / `fitness` 之一
- `practice` 类型必须提供 `errors`（至少 1 条）
- `figure_images` 各路径必须存在（agent 先用 extract_pdf_image.py 提取）
- `method` / `rules` / `intent` / `organization` / `lecture_script` 不得含中文冒号、ASCII 冒号、破折号（去 AI 味铁律）
- 图例引用必须与 activity_index.json 中的 figure_refs 一致

### 步骤 4：去 AI 味儿（必跑）

触发 human-writing skill，对 `lecture_script` 重写。若 human-writing 不可用，🔴 STOP，不得静默降级。硬禁令：
- 禁「体现/彰显/凸显/值得注意的是/此外/综上所述」等 AI 腔
- 禁三段式机械排比
- 读起来像老师在课堂说话，自然、有节奏、有停顿

### 步骤 5：跑脚本 + 验证 + 收尾

```bash
TRIAL_DAILY_WORKSPACE="/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编" python3 "$(dirname "$0")/fill_trial_daily_post.py"
```
> 说明：一律从「当前 skill 路径」运行脚本（`$(dirname "$0")`），不使用任何 `.trae-cn` 等环境绝对路径。

只有输出同时出现 `✅ 全部通过` 和 `✅ pending_trial_daily.json 已删除`，才算生成成功。

成功后再更新 `scripts/progress_trial.json`：把本期活动名称追加进 `done`，将同一名称写入 `last_done`，将上海时区当天日期按 `YYYY-MM-DD` 写入 `last_date`。重新读取 JSON，确认三处均命中。

向领导报告：运动项目、环节名称、输出 docx 路径、验证通过项（图例数、段落数、表格数、占位符零残留、引流段未动）。

### 步骤 6：上传到 ima 知识库（领导要求时执行）

生成 DOCX 后，如需同步到 ima 知识库「A-00 体育试讲设计每日一练」，按以下流程：

1. 生成 md 版：整理成 markdown（标题、运动项目、图例引用、环节拆解、试讲逐字稿、话题标签），保存到 `体育教师编/每日试讲知识点md/YYYY-MM-DD-环节名称.md`。
2. 定位知识库：`search_knowledge_base`（query "SHTr"）→ 取「SHTr | 体师知识库」的 `kb_id`。
3. 定位文件夹：逐级进入「2 面试（试讲 说课 结构化）持续更新...」→「A-00 体育试讲设计每日一练」，取目标 `folder_id`。
4. 创建笔记：notes 模块 `import_doc`（`content_format=1`，content 为 md 全文）→ 得 `note_id`。
5. 加入知识库：`add_knowledge`（`media_type=11`，`note_info.content_id=note_id`，`knowledge_base_id`，`folder_id`）。
6. 校验：`add_knowledge` 返回 `code=0` 即成功。

> 笔记写入前必须校验 content 为合法 UTF-8；`title` 用「体育试讲设计每日一练｜{环节名称}」。

## 失败恢复

| 触发条件 | 一线处理 | 仍失败时的兜底 |
|---|---|---|
| 任一关键路径缺失、Python 不能导入 `docx` 或 `fitz` | 🔴 STOP，报告缺失路径或原始报错 | 获准后使用 `/tmp/tyt_venv` 安装 |
| `activity_index.json` 或 `progress_trial.json` 缺失/损坏 | 🔴 STOP，修复进度 | 无权威记录时请领导确认 |
| 指定活动重复、定位不唯一或全库已完成 | 🔴 STOP，报告已完成项 | 请领导改选 |
| JSON 字段校验失败 | 根据原始错误只修 JSON，再重跑 | 不改脚本阈值 |
| 图例提取失败 | 尝试其他图例格式查找，若仍失败则跳过图例 | 报告缺失图例，不阻止生成 |
| DOCX 成功但进度写入失败 | 保留成功 DOCX，只修复并复核进度 JSON | 不重跑填充脚本 |
| 脚本写入失败 | 自动回滚到快照 | 快照无时用彩色图例段替代 |

## 🔴 STOP 与反例黑名单

- 不修改教师用书源、源 PDF、品牌底版或固定引流段
- 不在进度缺失、重复选题、定位不唯一时继续写文件
- 不在脚本成功前更新进度，也不为补写进度而重跑成功填充脚本
- 不绕过校验、不静默降级、不用外部常识修补教师用书没有给出的事实
- 不试图用 Google 搜索或联网知识补充活动内容
- 无图例时不得留空占位符，直接跳过图例区

## 模板与脚本铁律

- 教师用书源、脚本只读；只允许覆盖 `desktop-attachments/` 工作副本与 `scripts/` 下自己的文件
- 脚本每次跑前自动快照到 `_snapshots_trial/`（保留最近 10），写入或验证失败时会自动恢复本轮快照
- 固定引流段、封面大标题、品牌页眉页脚、封面底层背景图 `scripts/cover_bg.png` 不许改

## 验证清单（每次跑完必查）

```
□ 封面 = 整页底层背景图(behindDoc) + 品牌标题(48pt浅青) + 项目标签 + 环节名 + 难度，恰好一页
□ 封面大标题字号 = 48pt（浅青 #9FD8E8）
□ 封面底层图 = scripts/cover_bg.png 已锚定铺满（behindDoc=1，置于文字下层）
□ 页眉斜向水印「世豪老师」= 所有节页眉均含 PowerPlusWaterMarkObject（灰 #C0C0C0）
□ 图例区 = 真实图片（如有），等比放大（宽≥正文85% 或高填满可用区），非占位符
□ 有图例时 = 「环节拆解」标题 page_break_before 另起一页置于最上端
□ 环节拆解 = 6 维度全部覆盖（名称/类型/方法/规则/意图/组织形式）
□ 易犯错误表格 = 仅 practice 环节，表头"易犯错误"+"纠正方法"，蓝底白字
□ 试讲逐字稿 = 教学流程完整（导入→示范→组织→纠错→互动→小结）
□ 引流 = #标签行居中且灰色(#808080)，固定引流段居中且深蓝(#0B3289)，均加粗，紧接逐字稿后空一行不另起页
□ 占位符零残留
□ cta 固定引流段原样保留
□ 脚本两条成功提示均出现后，progress_trial.json 才更新且回读通过
□ 已完成活动未重复
□ human-writing 已实际执行，无静默降级
□ （若上传）ima 笔记已创建并加入「A-00 体育试讲设计每日一练」，add_knowledge 返回 code=0
```
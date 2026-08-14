---
name: PE-trial-daily
description: 自动化生成「体育试讲设计每日一练」小红书帖子 docx，并可同步上传到 ima 知识库「A-00 体育试讲设计每日一练」。基于 python-docx 从零构建品牌化 DOCX，从教师用书提取教学环节（热身游戏/体能游戏/练习环节），拆解成环节名称、活动方法、规则、设计意图、组织形式、易犯错误及纠正，最后串联成试讲逐字稿，含图例插图。触发词：体育试讲每日一练、试讲设计每日一练、出一期体育试讲设计。
---

# 体育试讲设计每日一练 · 自动出帖

## 适用场景

从人教版教师用书（313 个活动，9 个运动项目）中，每天拆解一个教学环节，生成一篇小红书帖子 docx：

- 第 1 页封面：深蓝底 + 品牌标题「体育试讲设计每日一练」+ 运动项目标签 + 环节名称 + 难度
- 第 2 页起：图例区（如教师用书有图例，整页渲染）+ 环节拆解（名称/类型/方法/规则/意图/组织形式）+ 易犯错误与纠正表格（仅 practice 环节）+ 试讲逐字稿 + 引流页

内容结构铁律：
- 环节拆解必须覆盖全部 6 个维度（名称、类型、方法、规则、意图、组织形式）
- 试讲逐字稿必须包含：课堂导入 → 示范讲解 → 组织练习 → 个别纠错 → 互动游戏 → 课堂小结
- practice 环节必须有易犯错误与纠正表格
- 图例引用（如"图3-2-7"）必须先用 extract_pdf_image.py 提取真实图片，不许留空

## 关键路径（Pre-flight 必查）

| 路径 | 说明 |
|------|------|
| `/Users/shawn/Desktop/AI工作区/03-Resources/各版本体育教材/人教版/` | 教师用书源（MD + PDF，只读，9 本） |
| `本 skill 的 scripts/fill_trial_daily_post.py` | 填充脚本（自带源，随 skill 分发） |
| `/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编/scripts/activity_index.json` | 活动索引（313 条，只读） |
| `/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编/scripts/ocr_index/` | OCR 页索引（缓存，用于图例定位） |
| `/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编/scripts/progress_trial.json` | 选题进度 |
| `/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编/scripts/_snapshots_trial/` | 快照（回退用） |

Python：使用当前会话提供的 python3（已装 python-docx 和 PyMuPDF）。若运行时缺失，可临时安装到 /tmp 环境。

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
TRIAL_DAILY_WORKSPACE="/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编" python3 /Users/shawn/.trae-cn/skills/PE-trial-daily/scripts/fill_trial_daily_post.py
```

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
- 固定引流段、封面大标题、品牌页眉页脚不许改

## 验证清单（每次跑完必查）

```
□ 封面 = 深蓝底 + 品牌标题 + 项目标签 + 环节名 + 难度，无页眉残留
□ 图例区 = 真实图片（如有），非占位符
□ 环节拆解 = 6 维度全部覆盖（名称/类型/方法/规则/意图/组织形式）
□ 易犯错误表格 = 仅 practice 环节，表头"易犯错误"+"纠正方法"，蓝底白字
□ 试讲逐字稿 = 教学流程完整（导入→示范→组织→纠错→互动→小结）
□ 占位符零残留
□ cta 固定引流段原样保留
□ 脚本两条成功提示均出现后，progress_trial.json 才更新且回读通过
□ 已完成活动未重复
□ human-writing 已实际执行，无静默降级
□ （若上传）ima 笔记已创建并加入「A-00 体育试讲设计每日一练」，add_knowledge 返回 code=0
```
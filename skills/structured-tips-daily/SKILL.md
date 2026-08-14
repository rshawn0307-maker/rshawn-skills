---
name: structured-tips-daily
description: 自动化生成"结构化答题技巧·每日一练"小红书爆款图文帖子 docx。围绕公考结构化面试的答题技巧和思路，用上岸过来人+考官视角，按小红书爆款节奏（标题钩子/短句/emoji/普通vs高分对照/避坑提醒/话题标签）产出。基于固定 docx 模板（17 段）+ python-docx 脚本自动替换，从题库索引选题防重复，答题须经 human-writing 去 AI 味儿。触发词：出一期答题技巧、技巧每日一练、答题思路、结构化答题技巧。
author: Shawn × AI（2026-08 沉淀）
version: 1.0.0
metadata:
  triggers:
    - 出一期答题技巧
    - 技巧每日一练
    - 答题思路
    - 结构化答题技巧
    - 出一期答题思路
  outputs:
    - 覆盖 .docx
    - _snapshots_tips/*.docx
  prerequisites:
    - python-docx
    - human-writing（去 AI 味儿）
    - ima-skill（上传 IMA）
install_method: upload
---

# 结构化答题技巧·每日一练

## 适用场景

用户做"公务员结构化面试·答题技巧"系列小红书爆款图文帖子（如"应急应变别平均用力""综合分析别停在现象层"），需要：

1. **出一个答题技巧**（上岸过来人 + 考官视角，有观点、可操作、接地气）
2. **按小红书节奏打磨**（标题钩子/短句/emoji/普通 vs 高分对照/避坑提醒/话题标签）
3. **自动套入固定 docx 模板**（17 段，含配图 + 引流段）
4. **保留模板所有版式**（封面文本框、分页符、引流段样式）
5. **从题库索引选题**，已完成技巧不重复推

## 技巧教学型骨架（每期固定）

```
封面钩子标题（≤20 字，数字/反差/悬念/利益四选一）
→ 适用题型
→ 技巧一句话（破题角度）
→ 思路步骤拆解（3 步）
→ 真题片段：普通答法 vs 高分答法（同题对照）
→ 普通答法点评 / 高分答法点评
→ 避坑提醒
→ 一句话总结
→ 话题标签
→ [固定引流段，模板自带，不动]
```

## 触发条件

用户说以下任意一种：
- "出一期答题技巧" / "技巧每日一练"
- "答题思路" / "结构化答题技巧"
- 类似表述

## 必看·Pre-flight 检查（🔴 STOP — 开干前 60 秒必跑，缺一不开工）

**3 件事不验证就动手 → 必踩坑**：

### ① 项目路径核实

**项目根**（本 skill 的「工作区根」）= `<项目根>/01-Projects/自媒体内容库-持续项目/结构化`
（Obsidian vault `AI工作区` 下；自媒体库已作为长期项目归档于此。下文 `<项目根>` 均指此目录；为占位符，原为旧 Windows 路径，使用前替换为本机实际路径）

`<项目根>` 下应有 `scripts/fill_tips_post.py` + `desktop-attachments/3 结构化答题技巧-帖子内容编辑模板.docx`。

```bash
ls "<项目根>/scripts/fill_tips_post.py" \
  && echo "✅ 路径正确" \
  || echo "❌ 路径错，找老板确认"
```

> **注**：脚本用 `__file__` 自定位（`WORKSPACE = SCRIPT_DIR.parent`），不依赖 cwd；Pre-flight 只需确认脚本文件存在。

### ② 模板铁律·双脚本分流

工作区里如果同时有 `fill_structured_post.py`（答一道 17 段）和 `fill_zhankai_post.py`（展开说说 48 段），**那是其他独立脚本，别混用**。本 skill 只用 `fill_tips_post.py` + `3 结构化答题技巧-帖子内容编辑模板.docx`。
# 🔴 STOP if 混用 — 字段映射不同，强混用会炸段位

### ③ Python 环境核实

```bash
python -c "import docx; from docx import Document; print('docx', docx.__version__)"
# 期望输出：docx 1.2.0（python-docx 包）
```

**【包名陷阱·重要】**：`pip install docx` 会装**同名垃圾包 0.2.4**（不支持 Python 3，会报 `ModuleNotFoundError: No module named 'exceptions'`）。**必须装 `python-docx`**：

```bash
pip install python-docx
# 验证：python -c "import docx; print(docx.__version__)"  → 1.2.0
# 🔴 STOP if ModuleNotFoundError — 装 python-docx（不是 docx）后重试
```

## 文件清单

| 路径 | 用途 | 注意事项 |
|------|------|----------|
| `<项目根>/desktop-attachments/3 结构化答题技巧-帖子内容编辑模板.docx` | 模板（覆盖写入目标） | **绝不能改文件名/移动位置** |
| `<项目根>/scripts/fill_tips_post.py` | 主脚本（答题技巧专用） | — |
| `<项目根>/scripts/tips_index.json` | 技巧索引（36 条，含来源路径） | 选题池，只读 |
| `<项目根>/scripts/progress_tips.json` | 已完成技巧记录 | 选题时过滤，跑完更新 |
| `<项目根>/scripts/pending_tips.json` | 中间文件 | 脚本读取后自动删除 |
| `<项目根>/模板文件/3 结构化答题技巧-帖子内容编辑模板.docx` | 源模板副本（基线备份） | — |
| `<项目根>/scripts/_snapshots_tips/` | 自动快照 | 保留最近 10 个 |

**快照机制**：脚本每次跑前自动生成 `snapshot_YYYYMMDD_HHMMSS.docx`。**跑挂不要慌，snapshots 里一定有最新可回退版本**。

## 工作流（5 步走完）

### 步骤 1：查索引选题

从 `scripts/tips_index.json` 的 tips 里挑一条**未在 `progress_tips.json` 的 done_ids 中出现**的技巧。

- **选题优先**：用户指定题型 → 过滤该题型；未指定 → 按题型轮转（综合分析→应急应变→人际关系→组织计划→自我认知→言语表达→通用）
- **已完成跳过**：done_ids 里有的 id 不重复推
- 索引外也可补充热点技巧，但须在 JSON 里 `added:true` 标记

**🔴 CHECKPOINT · STOP** → 用 `AskUserQuestion` 弹窗选项让用户确认选题（选项如："OK，就这个"、"换一个"），**不要让用户打字**。用户选"换一个"→ 回到本步骤重选。

### 步骤 2：写技巧内容

按技巧教学型骨架的 13 个字段写草稿（见步骤 3 schema）。**小红书爆款规范**（详见 `references/content-strategy.md`）：

- **标题钩子 ≤20 字**，必须含数字/反差/悬念/利益之一；禁止纯主题词（"应急应变"不合格，"应急应变别再平均用力，先排序再出招"合格）
- **单段 ≤4 行，行内 ≤30 字**，短句 8-20 字为主
- **数字用阿拉伯数字**（"30 个考生"）
- **emoji 每段 ≤2 个**，限调色板：`❗️ 🙅 ❌ ✅ 📌 💡 ⏰ 🗣`；禁止堆砌
- **普通 vs 高分对照**是本 skill 特色：同题给两个答法片段 + 各自点评，读者能直接抄
- **避坑提醒**给 2-5 句"绝对不能说的官话"，是"赚到感"关键
- **话题标签 5-8 个**，固定 `#公考面试 #结构化面试 #上岸`，其余按题型/主题补

### 步骤 2.5：去 AI 味儿（必跑，套用 human-writing）

**写完初稿 → 必跑 human-writing → 才能进 pending_tips.json**。这是硬步骤。

重点扫（human-writing 硬禁令）：
- "体现/彰显/凸显""深入推进/全面落实" 等公考 AI 高危词 → 改具体事实
- 三段式凑数（2 件事别扩成 3 件）
- 破折号清零（"——"一律改逗号或句号）
- 否定式排比（"不是 X，是 Y" 最多保留 1 处作开篇钩子）
- 模糊归因（"专家认为""业内人士表示"）
- 万能收束（"总之，…"）

**优先路径**：直接触发 human-writing skill 对 13 个字段逐个/合并重写。
**降级**：skill 调用失败时按 structured-post 的 6 条内联规则手动检查重写，并在同目录写 `human-writing_fallback.txt` 标注。

**🔴 CHECKPOINT · STOP** → 把 humanize 前后对比关键改写点展示给用户（3-5 处），`AskUserQuestion` 确认（选项如："够自然，继续"、"还是像AI，再调"）。

### 步骤 3：写 pending_tips.json

按以下 schema 严格填写（13 个顶层 key）：

```json
{
  "tip_title": "应急应变别再平均用力，先排序再出招",
  "question_type": "适用题型：应急应变题",
  "tip_intro": "破题角度：考官看的是轻重缓急的排序能力，不是面面俱到。",
  "step1": "第一步：先定优先级，把最紧急、最伤人的事排第一。",
  "step2": "第二步：止损优先，先把事态控制住，再谈调查和追责。",
  "step3": "第三步：处置+善后闭环，给结果也给交代。",
  "case_normal": "普通答法：遇到这种情况，我会先了解情况，再上报领导……",
  "case_normal_note": "点评：平均用力，没有排序，考官看不到你的判断力。",
  "case_high": "高分答法：第一，先疏散人群切断危险源……",
  "case_high_note": "点评：有明确先后顺序，每个动作都有具体抓手。",
  "pitfalls_lead": "避坑提醒：",
  "pitfalls": "别一上来就'上报领导'当万能开头；别把'安抚'说得空泛。",
  "tip_takeaway": "说到底，应急应变衡量的不是话术，是你能不能分清轻重。",
  "hashtags": "#公考面试 #结构化面试 #应急应变 #答题技巧 #上岸"
}
```

写入路径：`<项目根>/scripts/pending_tips.json`（写之前先跑 Pre-flight #① 确认父目录）

**【JSON 引号陷阱】**：JSON 字符串内部只能用**中文双引号""或转义符\"**，不要用 ASCII 双引号嵌套。推荐用 Python 生成。

### 步骤 4：跑脚本

```bash
cd "<项目根>"
python scripts/fill_tips_post.py
```

期望输出：
```
[0/4] 快照备份: snapshot_YYYYMMDD_HHMMSS.docx
[1/4] 读取待写入内容: ...
[2/4] 写入 段[0] 文本框封面标题（前缀改 答题技巧：）
[2.5/4] 写入 13 个段位（正文）
[2.6/4] 锁定版式：段[7] 正文首段强制 pageBreakBefore
[3/4] 保存
[4/4] 自动验证 → ✅ 全部通过
```

### 步骤 5：更新完成记录 + 向用户报告

1. 把本次技巧 id 追加进 `scripts/progress_tips.json` 的 done_ids
2. 报告内容：
   - 技巧已生成（标题 + 适用题型）
   - .docx 已更新，路径：`<项目根>/desktop-attachments/3 结构化答题技巧-帖子内容编辑模板.docx`
   - 验证通过项：段数 17 / 5 张图 / 引流段样式 / 封面「答题技巧：」前缀 / 段[7] pageBreakBefore
   - 去 AI 味儿自评

### 步骤 6：上传 IMA 笔记

脚本跑完、验证通过后上传。**不存本地 md 文件，直接上传**。

1. 生成时间戳 `YYYYMMDD_HHMMSS`
2. 构造标题：`{技巧关键词}_{timestamp}`（如 `应急排序_20260814_153000`）
3. 将步骤 3 内容格式化为 Markdown（H1 为笔记标题，含适用题型、步骤、对照、避坑、总结、标签）
4. 写临时 md 到工作区临时目录，调用：
```bash
node <skill目录>/scripts/upload_to_ima.js "<临时md文件路径>" "<笔记标题>"
```
5. 脚本自动同步到「总分总」知识库的「00_结构化答题技巧」文件夹（找不到文件夹降级到根目录，不阻断）

**IMA 失败重试**：返回 `⚠️ IMA上传失败` 则检查 ima_api.cjs 存在 + 登录状态，重试 1 次；仍失败跳过上传，本地已跑完不受影响，报告标注"IMA 未同步"。

## 模板铁律（绝对不能动）

**字体铁律**：模板字体已统一为通用字体（微软雅黑等），不要重新引入 WPS 云字体或内嵌字体文件。

| 段位 | 内容 | 脚本行为 |
|------|------|----------|
| 段[0] | 封面文本框（"答题技巧："前缀 + 大标题） | 替换标题，前缀统一"答题技巧："（2 镜像） |
| 段[2] | 适用题型 | 替换 |
| 段[3] | 技巧一句话（破题） | 替换 |
| 段[4-6] | 思路步骤 3 步 | 替换 |
| 段[7] | 普通答法 | 替换 + 强制 pageBreakBefore |
| 段[8] | 普通答法点评 | 替换 |
| 段[9] | 高分答法 | 替换 |
| 段[10] | 高分答法点评 | 替换 |
| 段[11] | "避坑提醒："引导 | 替换 |
| 段[12] | 避坑内容 | 替换 |
| 段[13] | 一句话总结 | 替换 |
| 段[14] | 话题标签 | 替换 |
| 段[15] | 引流段（橙色加粗居中） | **不动**（保留原文） |
| 段[16] | 末尾装饰图 | 不动 |

## 关键修复历史（避坑）

1. **不要预设 run[0] 是文本 run**：段[6] 的 run[0] 实际是图文混合 run，必须找"第一个纯文本 run"
2. **图片 run 完全不动**：包括 `<w:drawing>` 元素和其 text
3. **文本框改 2 处**：drawing 镜像 + VML fallback，前缀"答题技巧："要 2 处同步
4. **pageBreakBefore 加在 pPr 里**：用 OxmlElement('w:pageBreakBefore') 干净插入，不要动 run
5. **段数恒定 17**：脚本里有校验，超出就报错
6. **JSON 引号嵌套**：用中文""或转义\"，别用 ASCII 双引号嵌套
7. **模板前缀已改**：新模板段[0] 前缀是"答题技巧："，不是"结构化每日一练："

## 验证清单（每次跑完必查）

```
□ 段数 = 17
□ 5 张图片全在
□ 引流段样式：加粗 + 颜色 #85120F + 居中（段[15]）
□ 段[0] 文本框：2 个镜像 + 前缀"答题技巧："完整
□ 段[7] 有 pageBreakBefore
□ 旧技巧关键词零残留
□ 新技巧关键词全命中
□ 去 AI 味儿标记：无 human-writing_fallback.txt（有=走了降级）
□ progress_tips.json 已追加本次 id
□ IMA 笔记已上传（note_id 已记录在报告中）
□ IMA 知识库已同步（笔记已关联"总分总"→"00_结构化答题技巧"）
```

## 失败回退

如果脚本验证失败：
1. **不要慌**——snapshot 已保存
2. 看 `[KEEP] pending_tips.json 保留` 的提示
3. 检查 errors 列表
4. 回退方式：从 `<项目根>/scripts/_snapshots_tips/` 复制最新 snapshot 覆盖回模板路径

## 工具链速查

| 操作 | 命令/工具 |
|------|----------|
| 写 json | `write_file(path, json_string)` 或 Python json.dump |
| 跑脚本 | `terminal(command=...)` 用有 docx 的 python |
| 看 docx 段数 | `python -c "from docx import Document; print(len(Document('路径').paragraphs))"` |
| 看文本框 | 搜 `<w:txbxContent>`，找 `<w:t>` 子元素 |
| 看图片 | 搜 `<w:drawing>`，找段内分布 |
| 看 pageBreakBefore | 搜 `<w:pageBreakBefore>`，在 `<w:pPr>` 里 |
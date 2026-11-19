---
name: structured-daily
description: 自动化生成"结构化答题技巧·每日一练"小红书图文帖子 docx。卡点驱动 + 定调版示范：先诊断读者卡在哪，再用普通答法 vs 示范对照讲透关键改动，教读者真能照做、可迁移的结构化答题技巧。用户说"出一期答题技巧 / 技巧每日一练 / 答题思路 / 结构化答题技巧 / 出一期答题思路"或类似含糊表述（如"来一期技巧""讲讲答题方法""出个技巧帖"）时触发本技能技巧线。本技能含两条工作流线（技巧线 / 答题线）：阶段 1 只启用技巧线，本 description 只覆盖技巧线触发词；答题线（逐题作答出稿）阶段 2 才启用，当前暂由 structured-post 承接，本技能暂不响应该线请求，避免双触发。
version: 3.0.0
author: Shawn × AI（2026-11 重构）
metadata:
  triggers:
    - 出一期答题技巧
    - 技巧每日一练
    - 答题思路
    - 结构化答题技巧
    - 出一期答题思路
  outputs:
    - 覆盖 vault docx 模板原子替换（desktop-attachments/3 结构化答题技巧-帖子内容编辑模板.docx）
    - _snapshots_tips 快照（最多 10 个）
  prerequisites:
    - python3 + python-docx 1.2.0
    - 电车站 tramstop-skill（去 AI 味诊断）
    - human-writing（改写 + check_prose 红线清零）
    - node + ima-skill（仅 IMA 上传，可选）
---

# 结构化每日一练

技术技能：两条工作流线（技巧线 / 答题线）共用一套共享 references（定调口径 / 读源 / 门禁 / 引擎安全），线间差异只在内容策略与模板。阶段 1 只启用技巧线，答题线相关文件与字段在阶段 2 填充。

## 两线触发路由表

| 用户表述 | 路由 | 状态 |
|---|---|---|
| 出一期答题技巧 / 技巧每日一练 / 答题思路 / 结构化答题技巧 / 出一期答题思路（及类似含糊表述） | 技巧线工作流（本文件） | 阶段 1 active |
| 答一道 / 出题 / 每日一练（逐题作答线表述） | 答题线 | 阶段 2 启用；当前暂用 structured-post，本技能不响应，避免双触发 |
| 裸"每日一练"（歧义：技巧帖还是逐题作答帖） | 阶段 2 弹窗选线 | 阶段 2 启用；阶段 1 答题线未启用，遇歧义先向用户确认走技巧线还是 structured-post |

## 工作流总览（技巧线 6 步）

| 步 | 动作 | 依据 |
|---|---|---|
| 1 | 查索引选题（按卡点，2-3 候选弹窗给用户挑） | `references/tips-card-point-taxonomy.md`（Task7 填充）、`references/shared-sourcing.md` |
| 2 | 写前读源（四源 + 审题五维 + 读源四要素） | `references/shared-sourcing.md` |
| 3 | 写 15 字段草稿 + draft_meta 记录 | `references/tips-content-strategy.md`、`references/shared-sourcing.md`（draft_meta schema） |
| 4 | 去 AI 味流水线（诊断 → 改写 → 程序红线清零 → 回核读源） | `references/shared-gates.md` 步 2-5 |
| 5 | 门禁验收：content_rules + 独立审稿 + 盲测出厂 + CHECKPOINT 弹窗 | `references/shared-gates.md` 步 6-9、`references/blind-test-protocol.md`（Task8 填充） |
| 6 | 引擎生成 docx + progress 更新 + 渲染近似检查 + 报告 | `references/shared-engine-safety.md`、`references/shared-gates.md` 步 10 |

IMA 上传是可选附加步（仅用户明确要求时执行）：node + ima-skill。

## Pre-flight 检查（缺一不开工）

### ① 项目根核实

**项目根** = vault 路径 `/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/结构化`。核实模板与索引存在：

```bash
ls "/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/结构化/desktop-attachments/3 结构化答题技巧-帖子内容编辑模板.docx" \
   "/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/结构化/scripts/tips_index.json" && echo "✅ 路径正确" || echo "❌ 路径错，先确认"
```

引擎不依赖 cwd，一律用 `--project-root "<项目根>"` 显式传入。

### ② Python 环境

```bash
python3 -c "import docx; print(docx.__version__)"   # 期望 1.2.0
```

- **命令陷阱**：本机用 `python3` / `pip3`，不是 `python`（含所有文档示例与手工操作）。
- **包名陷阱**：装包用 `pip install python-docx`，不是 `pip install docx`（会装同名垃圾包）。

### ③ 引擎归属

唯一执行引擎是 **skill 内 `scripts/fill_tips_post.py`**（Task4 填充）。项目根 `scripts/` 下遗留的 v1 `fill_tips_post.py` **已废弃勿用**（无写入前预检、先保存后验证，危险）。安全模式与退出码契约见 `references/shared-engine-safety.md`。

## 文件清单

| 位置 | 文件 | 用途 |
|---|---|---|
| skill | `SKILL.md` | 本文件：两线路由 / 工作流总览 / Pre-flight / 契约入口 |
| skill | `references/shared-calibration.md` | 定调版口径单一事实源（技巧线示范与答题线逐字稿共用） |
| skill | `references/shared-sourcing.md` | 四源读源 + 权威讲义链 + draft_meta 统一 schema |
| skill | `references/shared-gates.md` | 门禁栈 + 去 AI 味 10 步流水线 |
| skill | `references/shared-engine-safety.md` | 引擎安全机制模式 + 退出码 0-4 契约 |
| skill | `references/tips-content-strategy.md` | 技巧线 15 字段职责表 + 内容规范 |
| skill | `references/tips-card-point-taxonomy.md` | 卡点标签体系（stub，Task7 填充） |
| skill | `references/blind-test-protocol.md` | 盲测试答出厂验收协议（stub，Task8 填充） |
| skill | `scripts/` | 引擎与自检脚本（现仅 .gitkeep 占位；Task4/5/6 填充） |
| skill | `assets/` | 模板 baseline 与资产（现仅 .gitkeep 占位；Task3 填充） |
| vault | `desktop-attachments/3 结构化答题技巧-帖子内容编辑模板.docx` | 技巧线模板（覆盖目标；Task3 换 23 段新模板） |
| vault | `scripts/tips_index.json` | 技巧索引（选题池；Task7 加卡点标签） |
| vault | `scripts/progress_tips.json` | 已完成记录（done_ids 选题过滤，跑完更新） |
| vault | `scripts/_draft_tips/` | 草稿与 draft_meta 工作区（pending） |
| vault | `scripts/_snapshots_tips/` | 引擎自动快照（最多 10 个） |
| vault | `scripts/tips_metrics.json` | 发布后指标回填（Task9 定 schema） |

**事实源约定**：选题与进度读 vault `scripts/` 下 `tips_index.json` 与 `progress_tips.json`；skill 内同名文件（如有）仅为出厂参考，不作为事实源。

## 模板铁律（C2 段位契约占位，**Task3 定稿**）

- 技巧线新模板契约：**23 段 4 图，15 字段**映射进段位；具体段位映射表 Task3 定稿后回填本节，当前为占位。
- **字体铁律**：模板字体通用，不引云字体、不内嵌字体文件。
- 段位契约三要素（占位）：段数 23 / 图 4 / 字段 15。
- 旧 18 段段位表随 v2 技能（structured-tips-daily）冻结，不再作为本技能契约。

## 失败处理 / 回归测试 / 脚本行为要点

统一引用 `references/shared-engine-safety.md`（安全模式 10 条 / 退出码 0-4 / 沙箱纪律 / 快照与 exit4 回滚 / 引擎收 skill 内 / 项目根解析 fallback 取消），本文件不重复细节。

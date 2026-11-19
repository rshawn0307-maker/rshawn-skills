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

唯一执行引擎是 **skill 内 `scripts/fill_tips_post.py`（v3.0）**（已落地：15 字段 / 23 段 / pic:pic==4 计数 / 安全模式 exit0-4）。项目根 `scripts/` 下遗留的 v1 `fill_tips_post.py` **已废弃勿用**（无写入前预检、先保存后验证，危险）。安全模式与退出码契约见 `references/shared-engine-safety.md`。

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
| skill | `scripts/fill_tips_post.py` | 技巧线引擎 v3.0（15 字段 / 23 段 / pic:pic==4 计数 / 安全模式 exit0-4） |
| skill | `scripts/test_fill_tips_post.py` | 引擎回归测试（沙箱临时副本；真实 vault 模板 sha256 前后断言） |
| skill | `scripts/build_tips_template.py` | 模板 baseline 可复现构建脚本（Task3） |
| skill | `scripts/content_rules.py` | 门禁规则（R0/R14 骨架，Task5 扩展） |
| skill | `scripts/test_content_rules.py` | content_rules 自测（Task2） |
| skill | `assets/tips-template-baseline.docx` | 技巧线模板 baseline（23 段 4 图，已部署 vault 模板 3） |
| vault | `desktop-attachments/3 结构化答题技巧-帖子内容编辑模板.docx` | 技巧线活模板（已部署 23 段 baseline，与 assets/tips-template-baseline.docx 一致） |
| vault | `scripts/tips_index.json` | 技巧索引（选题池；Task7 加卡点标签） |
| vault | `scripts/progress_tips.json` | 已完成记录（done_ids 选题过滤，跑完更新） |
| vault | `scripts/_draft_tips/` | 草稿与 draft_meta 工作区（pending） |
| vault | `scripts/_snapshots_tips/` | 引擎自动快照（最多 10 个） |
| vault | `scripts/tips_metrics.json` | 发布后指标回填（Task9 定 schema） |

**事实源约定**：选题与进度读 vault `scripts/` 下 `tips_index.json` 与 `progress_tips.json`；skill 内同名文件（如有）仅为出厂参考，不作为事实源。

## 模板铁律（C2 段位契约，Task3 已定稿，本表为准）

- 技巧线模板契约：**23 段 / pic:pic 4 图 / 15 字段**；引擎 `scripts/fill_tips_post.py` v3.0 按下表段位写入。
- **图数口径：`pic:pic == 4`**（真实图片元素计数）。`w:drawing == 5` 不作图数契约——多出的 1 个是封面文本框形状（`w:drawing` 包裹 wps 文本框）；封面文本框双镜像 `txbxContent == 2`（drawing txbxContent + VML fallback），引擎预检与验证均按此口径。
- **字体铁律**：通用字体（微软雅黑 / 宋体 / Wingdings 等），不引云字体、不内嵌字体文件。
- **品牌蓝 003153**：6 个蓝色标题段继承 Heading 2 样式定义色（styleId=4），run 不写显式色值。
- **样式指纹零漂移基准**：以 baseline 实际逐段 pPr/rPr 为准；**段 3 基准含 b+bCs**（首行缩进 2 字符 firstLineChars=200 + color 85120F + b + bCs），沿旧版式保留。
- 旧 18 段段位表随 v2 技能（structured-tips-daily）冻结，不再作为本技能契约。

### C2 段位映射表（23 段逐段）

| 段 | 内容 | 样式 | 引擎行为（v3.0） |
|---|---|---|---|
| 0 | 封面文本框：前缀"结构化答题技巧：" + tip_title | Heading 2 + 封面背景图（品牌"总分总"） | 双镜像同步：前缀 + 标题各 2 处（drawing txbxContent + VML fallback） |
| 1 | "卡点诊断" | Heading 2，品牌蓝 003153 + 装饰图 | 不动 |
| 2 | card_point | Normal | 替换 |
| 3 | fix_summary | Normal，firstLineChars=200 首行缩进 2 字符 + color 85120F + **b + bCs** | 替换（rPr 原样保留） |
| 4 | "定调版示范" | Heading 2，品牌蓝 | 不动 |
| 5 | demo | Normal | 替换 + 段首 👍（引擎自动加，JSON 不含） |
| 6 | "改法拆解" | Heading 2，品牌蓝 | 不动 |
| 7 | step1 | Normal，numPr 圆点项目符号（numId=12） | 替换 |
| 8 | step2 | 同段 7 | 替换 |
| 9 | step3 | 同段 7 | 替换 |
| 10 | "对照点评" | Heading 2，品牌蓝 | 不动 |
| 11 | case_normal | Normal | 替换 + 段首 🙅‍♂️（引擎自动加，JSON 不含） |
| 12 | contrast_note | Markdown引用（pStyle 99）+ 浅灰底 shd F2F2F2 | 替换 |
| 13 | "适用边界" | Heading 2，品牌蓝 + 装饰图 | 不动 |
| 14 | boundary_scope | Normal，run b + bCs + u single | 替换 |
| 15 | boundary_misuse | 同段 14 | 替换 |
| 16 | boundary_evidence | 同段 14 | 替换 |
| 17 | "迁移练习" | Heading 2，品牌蓝 | 不动 |
| 18 | exercise | 同段 14 | 替换 |
| 19 | self_check | 同段 14 | 替换 |
| 20 | hashtags | endnote text（pStyle 51），sz 24（12pt） | 替换 |
| 21 | 引流段（原文冻结） | endnote text + b + color 85120F + jc center | 不动（原文 + 样式冻结） |
| 22 | 末图 | Normal + 图 | 不动 |

- 固定不动段：1 / 4 / 6 / 10 / 13 / 17（蓝色标题）、21（引流段）、22（末图）。
- 4 图分布：段 0 封面背景（品牌"总分总"）、段 1 / 段 13 标题旁装饰图、段 22 末图。
- 引流段原文（冻结）："关注我，后续分享更多面试实战技巧和考场避坑指南，帮你少走弯路，一次上岸"。

## 失败处理 / 回归测试 / 脚本行为要点

统一引用 `references/shared-engine-safety.md`（安全模式 10 条 / 退出码 0-4 / 沙箱纪律 / 快照与 exit4 回滚 / 引擎收 skill 内 / 项目根解析 fallback 取消），本文件不重复细节。

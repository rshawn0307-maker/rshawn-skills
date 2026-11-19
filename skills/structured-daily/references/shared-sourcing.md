# 读源与权威讲义链（shared-sourcing）

四源读源步骤、权威讲义链与 draft_meta 统一 schema。两线共用；路径为 vault 内相对路径（Task2 已只读核实全部存在，2026-11-19 定稿）。

## 四源（修死链）

### 1. 方法论（首要方法源）

`02-Areas/公考面试结构化培训/02_答题方法与框架/各题型方法论/<题型>_方法论提炼.md`（**6+1**：6 份题型方法论提炼——综合分析题 / 应急应变题 / 人际关系题 / 组织计划题 / 自我认知题 / 言语表达题；+1 份 `无领导_结构化小组_科学决策_题型扩围整理.md` 为扩围整理可选参照，不作强制方法源）

### 2. 讲义（对外唯一成品）

`02-Areas/公考面试结构化培训/02_答题方法与框架/讲义/一本通/公考结构化面试一本通.md` 对应章节。

**旧《公考面试结构化备考讲义》2026-11-16 整链退役归档，死链废弃**（旧 tips SKILL `skills/structured-tips-daily/SKILL.md` **L141** 具名引用该死链，Task2 grep 核实）。退役归档在 `02-Areas/公考面试结构化培训/_archive/20261116-双轨制退役/`。

### 3. 题库

src 指向 `02-Areas/公考面试结构化培训/01_题库与训练/模拟题/<题型>题/*.md` 全文（题干 + 思路大纲 + 定调版逐字稿 + 教师注）；真题库根 `02-Areas/公考面试结构化培训/01_题库与训练/全国历年真题/陕西/陕西事业单位`（答题线，阶段 2）。

### 4. 教师注

题库原文末尾，适用条件，必须吸收进边界段（boundary_evidence）。

## 审题五维（答题线必用，技巧线选题参照）

设问 / 身份 / 对象 / 限制条件 / 主要争点；**限制条件不能丢 / 改 / 加**。

## 读源四要素（内部记录）

原方法是什么 / 适用条件 / 关键动作 / 出处（文件#小节）。

## 纪律

- 资料冲突回查原文裁决，不拼新口诀，不改教学原文。
- **方法源同步铁律**：改方法论若进书须同步 `02-Areas/公考面试结构化培训/02_答题方法与框架/讲义/_sources/一本通/方法篇.md`；H4（`^#### `）标题数**以方法篇.md 实际数为准（当前 133，Task2 grep 核实，fail-closed：改方法论进书须同步并回核实际 H4 数）**——本次重构不改方法论原文，不触发。

## draft_meta 统一 schema（两线共用按线扩展，缺记录 R0 拒放行）

| 字段 | 线 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| skill_version | 共 | string | 两线必填 | "3.0.0" |
| line | 共 | string | 两线必填 | "tips" 或 "answer" |
| tip_id / question_id | 共 | string | 两线必填（tips 填 tip_id / answer 填 question_id，二选一非空） | 选题 id |
| method_points / point_labels | 共 | number / string[] | 两线必填 | 要点数如实 |
| sources[] | 共 | string[] | 两线必填 | "文件#小节" |
| quote_excerpts[] | 共 | string[] | 两线必填 | 逐条原文短句 |
| applicable_conditions[] | 共 | string[] | 两线必填 | 教师注权限/安全原样 |
| review_conclusion | 共 | string | 两线必填 | **独立审稿后写**；=="通过" 才放行（R14），此前为"待审"等值一律拒 |
| render_check | 共 | string | 两线必填 | "近似通过" 或 "发布端通过" |
| blind_test_result | 共 | string | 两线必填 | **盲测试答后写**；=="通过" 才出厂（R14），此前为"未过"等值一律拒 |
| card_point | tips | string | line=="tips" 必填 | 本期卡点 |
| cognitive_gain | tips | string | line=="tips" 必填 | 认知增量点：读者原来想错了什么 |
| shared_context / key_change | tips | string | line=="tips" 必填 | 对照同题境 / 关键改动 |
| actionable_demo | tips | string | line=="tips" 必填 | 可照做问句/动作 |
| demo_source | tips | string | line=="tips" 必填 | 引用题库定调版段落出处 或 "新写标示范" |
| demo_calibration_check | tips | string | line=="tips" 必填 | 字数/破题定调/三禁回核结论 |
| exercise_criteria / self_check_criteria | tips | string | line=="tips" 必填 | 练习判据 / 自查判据 |
| title_candidates[3] | tips | string[3] | line=="tips" 必填 | 痛点式/具体改法式/原栏目式 + 理由 |
| 审题五维记录 / closing_type | answer | —（阶段 2 定型） | 阶段 2 | answer 扩展字段，阶段 2 启用 |

**R0/R14 校验语义**（代码见 `scripts/content_rules.py`）：

- **R0 读源记录必填**：--pending 给定而 --meta 缺失或文件不存在 → 拒。
- **R14 审稿记录完整 + 结论通过**：核心字段（两线必填）+ 对应线扩展字段全部非空，且 `review_conclusion=="通过"` 且 `blind_test_result=="通过"`；任一不满足 → 拒。
- 两结论分别在**独立审稿**与**盲测试答**之后写入；全量 content_rules（R0-R15）跑在独立审稿＋盲测之后，作**最终出厂门禁**（流水线顺序君上裁定，shared-gates.md 表由 Task6 同步）。

标注：Task2（2026-11-19）已只读核实四源路径全部存在、定稿 schema（19 字段行）；R0/R14 校验代码为 scripts/content_rules.py 骨架，Task5 扩展 R1-R13/R15。

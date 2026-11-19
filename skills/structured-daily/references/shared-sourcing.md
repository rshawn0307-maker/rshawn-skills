# 读源与权威讲义链（shared-sourcing）

四源读源步骤、权威讲义链与 draft_meta 统一 schema。两线共用；路径为 vault 内相对路径（Task2 验证实际存在后定稿）。

## 四源（修死链）

### 1. 方法论（首要方法源）

`02-Areas/公考面试结构化培训/02_答题方法与框架/各题型方法论/<题型>_方法论提炼.md`（6 份：综合分析题 / 应急应变题 / 人际关系题 / 组织计划题 / 自我认知题 / 言语表达题）

### 2. 讲义（对外唯一成品）

`02-Areas/公考面试结构化培训/02_答题方法与框架/讲义/一本通/公考结构化面试一本通.md` 对应章节。

**旧《公考面试结构化备考讲义》2026-11-16 整链退役归档，死链废弃**（旧 tips SKILL L142 具名引用必修）。退役归档在 `公考面试结构化培训/_archive/20261116-双轨制退役/`。

### 3. 题库

src 指向 `01_题库与训练/模拟题/<题型>题/*.md` 全文（题干 + 思路大纲 + 定调版逐字稿 + 教师注）；真题库根 `01_题库与训练/全国历年真题/陕西/陕西事业单位`（答题线，阶段 2）。

### 4. 教师注

题库原文末尾，适用条件，必须吸收进边界段（boundary_evidence）。

## 审题五维（答题线必用，技巧线选题参照）

设问 / 身份 / 对象 / 限制条件 / 主要争点；**限制条件不能丢 / 改 / 加**。

## 读源四要素（内部记录）

原方法是什么 / 适用条件 / 关键动作 / 出处（文件#小节）。

## 纪律

- 资料冲突回查原文裁决，不拼新口诀，不改教学原文。
- **方法源同步铁律**：改方法论若进书须同步 `讲义/_sources/一本通/方法篇.md`（H4 标题数契约 134，fail-closed）——本次重构不改方法论原文，不触发。

## draft_meta 统一 schema（两线共用按线扩展，缺记录 R0 拒放行）

| 字段 | 线 | 说明 |
|---|---|---|
| skill_version | 共 | "3.0.0" |
| line | 共 | "tips" 或 "answer" |
| tip_id / question_id | 共 | 选题 id |
| method_points / point_labels | 共 | 要点数如实 |
| sources[] | 共 | "文件#小节" |
| quote_excerpts[] | 共 | 逐条原文短句 |
| applicable_conditions[] | 共 | 教师注权限/安全原样 |
| review_conclusion | 共 | =="通过" 才放行（R14） |
| render_check | 共 | "近似通过" 或 "发布端通过" |
| blind_test_result | 共 | =="通过" 才出厂（R14） |
| card_point | tips | 本期卡点 |
| cognitive_gain | tips | 认知增量点：读者原来想错了什么 |
| shared_context / key_change | tips | 对照同题境 / 关键改动 |
| actionable_demo | tips | 可照做问句/动作 |
| demo_source | tips | 引用题库定调版段落出处 或 "新写标示范" |
| demo_calibration_check | tips | 字数/破题定调/三禁回核结论 |
| exercise_criteria / self_check_criteria | tips | 练习判据 / 自查判据 |
| title_candidates[3] | tips | 痛点式/具体改法式/原栏目式 + 理由 |
| 审题五维记录 / closing_type | answer | 阶段 2 |

标注：本文件 Task2 验证四源路径实际存在、定稿 schema；Task5 实现 R0/R14 校验代码。

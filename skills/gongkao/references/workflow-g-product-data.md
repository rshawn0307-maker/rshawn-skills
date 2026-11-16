# 工作流 G：产品题库 JSON 输出

本工作流只处理面向网页、小程序或共享后端的题目数据。普通出题和一本通维护仍使用原有 Markdown 工作流。

## 1. 必读合同

按以下顺序读取，不得凭记忆重建字段和编码：

1. `product/question-schema-v2.json`：字段、类型、ID 和版本规则。
2. `product/interview-rubric-v1.2.json`：公共与题型专属评分维度。
3. `product/error-tags-v1.1.json`：合法错因编码、触发与排除边界。
4. `product/retest-policy-v1.json`：复测保留项、变化项和改善证据。

当前产品快照固定为 `question-schema-v2`、`rubric-v1.2`、`error-tags-v1.1`。合同版本不匹配时停止转换并报告，不要混用新旧编码。

## 2. 输出边界

- 每道题输出一个 JSON 对象和一个 `.json` 文件。
- 默认文件名为 `{question_id}.json`。
- 不把多个题目塞进单个不受约束的数组；批量清单和导入包留给上层导入流程处理。
- JSON 是产品数据合同，Markdown 是教研阅读资产。用户同时需要 Markdown 和产品 JSON 时，两份内容必须来自同一道已确认题目。
- 产品 JSON 默认不上传 IMA，不修改原 Markdown。

## 3. 题目 ID

格式：`gkq_<题型代码>_<6位序号>`。

| 题型 | 编码 |
|---|---|
| 综合分析 | `ca` |
| 组织计划 | `op` |
| 人际关系 | `ir` |
| 应急应变 | `er` |
| 自我认知 | `sa` |
| 言语表达 | `ve` |

分配 ID 前：

1. 优先使用用户或题库注册表提供的 ID。
2. 否则扫描目标输出目录全部 JSON 的 `question_id`，按题型取下一个未使用序号。
3. 目标目录不存在或无法确认完整题库边界时，先展示建议 ID 并等待确认。
4. 同一道题修改内容时保留 ID、递增 `content_version`；核心情境或考查能力变化时创建新 ID。
5. 禁止复用已退役题目的 ID。

## 4. 内容映射

| Markdown/教研内容 | JSON 字段 |
|---|---|
| 题型 | `question_type` |
| 细分题型 | `subtype` |
| 主题 | `title` |
| 题干 | `prompt` |
| 难度 | `difficulty` |
| 来源 | `source` |
| 答题逐字稿 | `reference_answer`（单字符串，完整参考作答） |
| 思路大纲 | 仅保留在 Markdown，不单独进入产品 JSON |
| 目标时长 210 秒 | `timing.answering_seconds` |
| 得分点 | `scoring.score_points` |
| 失分点 | `scoring.losing_points` |
| 复测方向 | `retest` |

`reference_answer` 在 v2 合同中是单个字符串，不得再写成 `outline` / `sample_answer` 对象，也不得附加其他版本分支。`timing` 统一为 `thinking_seconds: 30`、`answering_seconds: 210`。

来源、审核人或时间无法确认时不得伪造。新生成未审核题使用 `status: draft` 和 `reviewed_by: null`。

## 5. 评分维度

每题必须恰好包含：

- `common.task_role` 15分
- `common.structure_logic` 15分
- `common.expression_naturalness` 10分
- `common.fluency_time` 10分
- 当前题型在量表中定义的3个专属维度，共50分

`score_points[].code` 直接使用量表维度编码，`max_points` 使用量表权重，7项合计100分。每项 `description` 必须改写为与当前题目有关的可观察得分点，不能只复制维度名称。

`scoring.rubric_version` 固定填 `rubric-v1.2`。该量表当前为训练校准版，不得对外宣称为官方评分标准。

## 6. 错因候选

- 每个 `losing_points[].error_tag_candidates` 只能使用 `error-tags-v1.1` 中存在且适用于当前题型的编码。
- 每个失分点要写清可观察表现，不能只写“内容不好”“逻辑不清”。
- 同一证据可能命中公共与专属标签时，候选列表可以保留两者，正式点评时按标签库优先级只选一个首要错因。
- 无法引用作答证据的内容不应设计为正式错因。

## 7. 复测约束

`retest.target_competency_codes` 必须包含 `competencies.primary.code`。  
`retest.target_error_tag_codes` 必须来自本题失分点的合法候选。  
`variation_requirements` 至少说明：

- 保持哪个题型和目标能力。
- 必须改变哪些情境、主体或对象。
- 哪种只换地名、数字或人名的做法属于伪变式。
- 复测成功要观察到什么具体行为。

有现成关联题时写入 `related_question_ids`；没有时保留空数组，不得编造 ID。

## 8. 校验与写入

先在临时文件或待确认内容中生成完整 JSON，再运行：

```bash
python3 <skill目录>/scripts/validate_product_question.py <题目.json>
```

校验器同时检查：

- Schema 版本为 `question-schema-v2`，字段与跨字段一致。
- `reference_answer` 为单字符串，`timing` 为 30/210。
- 评分维度是否与当前题型量表完全一致，`rubric_version` 为 `rubric-v1.2`。
- 评分分值是否等于量表权重并合计100。
- 能力和错因编码是否合法，错因是否来自 `error-tags-v1.1`。
- 复测目标是否来自当前题目的能力与错因。

🔴 **CHECKPOINT：展示题目 ID、7个评分点、错因候选和复测要求。用户确认后才写入正式输出目录。**

批量处理时先完成并校验每类1道样例。用户确认字段与教研含义后，再转换剩余题目。

## 9. 完成报告

报告至少包含：

- 输出文件数量和路径。
- 使用的 Schema、量表、错因和复测规则版本。
- 题目 ID 范围。
- 校验通过数量和失败数量。
- 待人工审核题目。
- 是否同步 IMA；默认写“未同步，产品 JSON 不默认上传”。
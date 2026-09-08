# R1 · v3 内容事实层规范

> 本文是 SKILL.md 的细节下沉文档，记录「可生成视图（v3 扩展）」「dry-run 迁移」「事实锁定」
> 「100 分量表与硬门」「图例策略」的权威定义。源数据（activity_index.json /
> progress_trial.json / 教师用书 MD/PDF）一律只读，本层绝不写回。
> 片段规范与草稿/评审 schema 见 `r2-fragment-and-review.md`。

## 1. 稳定 ID 与可生成视图（schema view@3）

- 稳定 ID：`PTD-{seq:03d}-{sport}-{name}`，seq 为 activity_index.json 原始顺序下标（0 基）。
- 记录指纹 `record_sha`：`sport|activity_name|activity_type|book_file|md_line|difficulty` 的 sha256 前 16 位。
- 视图由 `build_generatable_view.py` 生成（默认输出 /tmp/ptd_view），每条记录含：
  `id / seq / record_sha / sport / activity_name / activity_type / book_file / md_line /
  index_difficulty / index_has_errors / difficulty_policy / figures / figure_policy /
  book_pdf_available / flags / generatable / generatable_blockers`，
  **v3 新增**：`section_start_line / section_end_line / method_cross_reference`。
- 原 313 条索引只读保留；视图是派生层，误收项只分类并留证，不静默删除。

### 1.1 误收选题拦截（v3）

- `activity_name` 命中 `课外作业|作业建议|课后作业|课外练习|课后练习|课外活动建议` →
  flag `miscollected_topic` + blocker `miscollected_topic_not_teaching_activity`（v3 实测 10 条）。
- 命中即不可生成：选题阶段换候选，不得进入提取与草稿。

### 1.2 章节边界（v3）

- `find_section_bounds(lines, md_line)`：start=从 md_line 向上最近的活动标题行；
  end=再向下最近的标题行。标题识别：`N.` / `（N）`（含中文数字小节），行长 ≤50、不含【与句号，
  防正文/表格续行误判。
- 提取只允许读取 `[section_start_line, section_end_line)` 内文本，避免把下一个活动读进成品。

### 1.3 前文引用（v3）

- 边界内文本命中 `与××动作/方法相同|同上|动作同` → flag `method_cross_reference`（实测 31 条），
  并尽力提取被引用对象（如 平击球 → 正(反)手平击发球）。
- 草稿硬门：method 的 evidence 必须含至少一条**行号小于本条 md_line** 的证据（被引用段落），
  否则 `cross_ref_evidence_missing`。

### 1.4 难度策略（不编星）

- `index_difficulty` 非空 → `index_stars`（教材星级，诚实引用）。
- 为空 → `adapted_label`，display 明示「教材未标难度，按入门基础层处理」，禁止 ★/☆。
- 硬门 `fabricated_difficulty`：索引为空却声明星级或 display 含星。

### 1.5 图例策略（有引用但缺 PDF/图必须 STOP；v3 起"跳过图例放行"作废）

| figure_policy | 条件 | 生成行为 |
|---|---|---|
| `none` | 无 figure_refs | 允许空图 |
| `use_extracted` | ≥1 图注在 MD 确认归属 且 本教材有 PDF | 精确匹配 caption 并裁图使用 |
| `misattributed_treat_as_none` | 全部图注已确认误收 | 按无图处理，留证据不删除 |
| `needs_ocr_verify` | 存在无法在 MD 核验的引用 且 有 PDF | 生成前必须 OCR 核验并精确裁图，失败即 STOP |
| `figure_required_but_pdf_missing` | 有引用且需图 但 缺 PDF/图 | 非可生成（blocker），生成时 STOP |

不变量：`use_extracted ⇒ book_pdf_available`；非可生成记录必有 blocker。

## 2. dry-run 迁移表

覆盖 progress_trial.json 全部旧进度：唯一命中视图 → `migrate`（v3 起若该记录带 blocker，
note 中提示历史成品需复核）；不在索引内 → `orphan_keep_classified`。仅演练，不写回。

## 3. 字段溯源（provenance / evidence）

- 每个内容块带 `provenance`：`textbook`（教材原文）或 `adapted`（教学加工）。
- 教材原文块必须带 `evidence`：`[{book_file, line(0基), excerpt}]`，行级校验见 `excerpt_at`
  （行号越界/空行/空摘录判否；反向包含要求目标行 ≥4 字）。
- **v3**：教学加工块登记 `adapted_facts` 时必须同时给非空 `adapted_note`（加工理由）；
  无理由登记计 `adapted_no_reason` → unclassified>0 → 硬门。
  "把新增事实批量塞进 adapted_facts 便视为通过"的做法取消。

## 4. 100 分量表与放行线（冻结阈值，不得改动）

| 维度 | 满分 |
|---|---|
| 教材事实 | 30 |
| 考编可用 | 20 |
| 安全 | 20 |
| 教学 | 15 |
| 口语 | 10 |
| 证据 | 5 |

放行线：总分 ≥ 85、教材 ≥ 27、安全 ≥ 16、硬门 = 0。

硬门全集（v3）：
`fabricated_difficulty`、`practice_errors_faked_textbook[*]`、`factlock_unclassified_gt0`、
`script_duration_out_of_range`、`safety_missing_entirely`、
`miscollected_topic`、`topic_text_mismatch`、`script_repetition_high`、`broken_punctuation`、
`duration_annotation_mismatch`、`cross_ref_evidence_missing`、`safety_not_executable`。

程序检查与内容评审的分工：上表全部可程序判定；动作逻辑、建议依据、纠错有效性、可讲性
由评审记录实责（r2 §3），两者都过才放行。

## 5. 事实锁定（factlock）

- 对 flow 各段与 fields.method/rules/intent/organization/errors 行/figures 全部块复核。
- 教材块缺 evidence、行号与摘录不符、token 不在摘录并集 → violation。
- 教学加工块 token 未覆盖未登记 → `unadapted_fact_token`；登记无理由 → `adapted_no_reason`。
- human-writing 改写逐字稿后必须重跑 score_draft（含 factlock）再放行。

## 6. 配置（config.default.json）

`region`、`grade_band_default`（水平三）、`segment_duration_sec=[120,240]`（含示范与停顿）、
`speech_rate_chars_per_min=230`、`page`（3:4 版式阈值）与 `product_claim`。
地区/学段/时长可按选题显式覆盖。

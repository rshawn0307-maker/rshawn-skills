# R1 · v2 内容事实层规范（任务1）

> 本文是 SKILL.md 的细节下沉文档，记录「可生成视图」「dry-run 迁移」「事实锁定」「片段流程」
> 「100 分量表」与「图例策略」的权威定义。源数据（activity_index.json / progress_trial.json /
> 教师用书 MD/PDF）一律只读，本层绝不写回。

## 1. 稳定 ID 与可生成视图

- 稳定 ID：`PTD-{seq:03d}-{sport}-{name}`，seq 为 activity_index.json 原始顺序下标（0 基），
  与序号无关的字段变更不改变 ID，重跑按 ID 幂等。
- 记录指纹 `record_sha`：对 `sport|activity_name|activity_type|book_file|md_line|difficulty`
  拼接串的 sha256 前 16 位，用于检测源记录是否变化。
- 可生成视图由 `build_generatable_view.py` 生成（默认输出 `/tmp/ptd_view`），每条记录含：
  `id / seq / record_sha / sport / activity_name / activity_type / book_file / md_line /
  index_difficulty / index_has_errors / difficulty_policy / figures / figure_policy /
  book_pdf_available / flags / generatable / generatable_blockers`。
- 原 313 条索引只读保留；视图是新增派生层，误收项只分类并留证，不静默删除。

### 1.1 难度策略（不编星）

- `index_difficulty` 非空 → `index_stars`（教材星级，诚实引用）。
- 为空 → `adapted_label`，draft 中 kind=`index_empty_adapted`，display 明示
  「教材未标难度，教学按入门基础层处理」，禁止出现 ★/☆。
- 硬门 `fabricated_difficulty`：索引为空却声明 `index_stars`，或 display 含星但索引为空。

### 1.2 图例策略（有引用但缺 PDF/图必须 STOP）

| figure_policy | 条件 | 生成行为 |
|---|---|---|
| `none` | 无 figure_refs | 允许空图 |
| `use_extracted` | ≥1 图注在 MD 确认归属 且 本教材有 PDF | 精确匹配 caption 并裁图使用 |
| `misattributed_treat_as_none` | 全部图注已确认但不属于本活动（误收） | 按无图处理，留证据不删除 |
| `needs_ocr_verify` | 存在无法在 MD 核验的引用 且 有 PDF | 生成前必须 OCR 核验并精确裁图，失败即 STOP（任务3强制执行） |
| `figure_required_but_pdf_missing` | 有引用且需图 但 缺 PDF/图 | 非可生成（blocker），生成时 STOP |

不变量：`use_extracted ⇒ book_pdf_available`；非可生成记录必有 blocker。

## 2. dry-run 迁移表

`migration_dryrun` 覆盖 progress_trial.json 全部旧进度：
- 活动名唯一命中视图 → `migrate`（记 view_id）。
- 活动名不在 313 条索引内 → `orphan_keep_classified`（保留证据，绝不删除）。
- 当前为纯 dry-run，真实写回 progress_trial.json 需领导裁决后执行。

## 3. 字段溯源（provenance / evidence）

- 每个内容块带 `provenance`：`textbook`（教材原文）或 `adapted`（明确教学加工）。
- 教材原文块必须带 `evidence`：`[{book_file, line(0基), excerpt}]`。
- `excerpt_at(book_file, line, excerpt)` 行级校验：行号越界/负、目标行空、excerpt 空 → 判否；
  摘录与行内文本归一化后需互相包含（反向包含要求目标行 ≥4 字，防 Markdown 标记行冒充）。
- 教学加工块中的事实 token（数字/方向/器材/安全/技术词）必须被本块 evidence 或
  全草稿其他教材证据覆盖，否则必须显式登记到 `adapted_facts`；未覆盖即未归类，硬门。

## 4. 片段流程模板

- practice（5 段）：导入与示范 → 分解学练 → 纠错与对比 → 巩固运用 → 小结评价
- game（5 段）：规则讲解 → 示范试玩 → 正式比赛 → 判定与追问 → 小结
- fitness（4 段）：动作示范与激活 → 跟随练习 → 变式挑战 → 放松与小结

片段要素 8 项：学段 / 片段位置 / 时长 / 重点 / 器材 / 安全 / 分层 / 评价。

## 5. 100 分量表与放行线（冻结阈值，不得改动）

| 维度 | 满分 |
|---|---|
| 教材事实 | 30 |
| 考编可用 | 20 |
| 安全 | 20 |
| 教学 | 15 |
| 口语 | 10 |
| 证据 | 5 |

放行线：总分 ≥ 85、教材 ≥ 27、安全 ≥ 16、硬门 = 0。
硬门包括：`fabricated_difficulty`、`practice_errors_faked_textbook[*]`、
`factlock_unclassified_gt0`、`script_duration_out_of_range`、`safety_missing_entirely`。

## 6. 事实锁定（factlock）

- 对 flow 各段与 fields.method/rules/intent/organization/errors 行/figures 全部块复核。
- 教材块缺 evidence、行号与摘录不符、token 不在摘录并集 → violation。
- 教学加工块 token 未覆盖未登记 → `unadapted_fact_token` → unclassified>0 → 硬门。
- human-writing 改写逐字稿后必须重跑 score_draft（含 factlock）再放行。

## 7. 配置（config.default.json）

`region`（默认通用）、`grade_band_default`（水平三）、`segment_duration_sec=[120,240]`、
`speech_rate_chars_per_min=230`、`page`（3:4 版式阈值，见任务2）与 `product_claim`。
地区/学段/时长均可按选题显式覆盖。

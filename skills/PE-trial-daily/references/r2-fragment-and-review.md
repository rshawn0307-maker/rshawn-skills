# R2 · v3 片段规范与草稿/评审 Schema

> 本文定义「三类片段流程」「片段八要素」「时长口径」「draft@3 schema」「review@1 评审记录」。
> 与 SKILL.md 五道门禁配套：本 schema 的每个必填项都有对应门禁校验。

## 1. 三类片段流程（取代"完整课堂六环节"）

片段是可嵌入完整试讲的 2—4 分钟教学片段，**不套用完整课堂六环节**，不写"上课/下课"。

- practice（5 段）：导入与示范 → 分解学练 → 纠错与对比 → 巩固运用 → 小结评价
- game（5 段）：规则讲解 → 示范试玩 → 正式比赛 → 判定与追问 → 小结
- fitness（4 段）：动作示范与激活 → 跟随练习 → 变式挑战 → 放松与小结

结尾回扣本期目标并衔接后续教学（"下节课我们在这个基础上……"），**不固定安排家庭作业**。

## 2. 片段八要素（segment.meta，全部必填）

学段（默认水平三为示例设置，须声明）/ 片段位置（嵌入完整试讲的哪个部分）/ 时长 /
重点（本期重点，一眼一条）/ 器材（器材与场地）/ 安全（可执行口令：场地检查+行动路线+停止条件）/
分层（不同基础学生的安排）/ 评价（可观察的评价标准）。

## 3. 时长口径（统一，杜绝口径打架）

```
合计秒数 = Σ 各阶段口播秒数（字符数 ÷ speech_rate_chars_per_min × 60）
         + Σ 各阶段 demo_sec/pause_sec（示范、练习等待、停顿，显式登记）
```

- 每阶段 flow 项必须登记 `demo_sec` / `pause_sec`（可为 0），**不得靠拉长句子凑时长**。
- `segment.meta.时长` 写法：`约{合计}秒（口播约{X}秒＋示范停顿约{Y}秒）`；
  硬门 `duration_annotation_mismatch` 校验标注与计算合计一致（容差 15 秒）。
- 合计须落在 `segment_duration_sec=[120,240]`，否则 `script_duration_out_of_range`。
- 页面逐字稿按阶段渲染，阶段标注 `阶段名（约N秒）`，N=该阶段口播+示范停顿；
  页面标注与分段合计一致可逐页复核。

## 4. draft@3 schema（scripts/pending_trial_daily.json）

```json
{
  "schema": "pe-trial-daily/draft@3",
  "id": "PTD-046-体能-抢背后滚球",
  "record_sha": "…",
  "segment": {
    "type": "fitness | game | practice",
    "meta": {"学段":"…","片段位置":"…","时长":"约180秒（口播约150秒＋示范停顿约30秒）",
             "重点":"…","器材":"…","安全":"…","分层":"…","评价":"…"}
  },
  "config": {"segment_duration_sec": [120,240], "speech_rate_chars_per_min": 230},
  "render": {
    "sport": "体能", "chapter": "…", "segment_name": "抢背后滚球",
    "difficulty_display": "★★ 或 教材未标难度，按入门基础层处理",
    "figure": "图3-2-2 半米字移动（可空串）",
    "figure_images": ["/abs/path.png"],
    "cta": "关注我，每天一个体育试讲设计，帮你备考上岸",
    "hashtags": "#教师编 #体育教师 #体育试讲 #试讲设计 #一次上岸"
  },
  "fields": {
    "difficulty": {"kind": "index_stars | index_empty_adapted | quoted", "display": "…",
                    "provenance": "…", "adapted_note": "…"},
    "method":  {"text": "…", "provenance": "textbook", "evidence": [{"book_file":"…","line":0,"excerpt":"…"}]},
    "rules":   {"text": "…", "provenance": "…", "evidence": […], "adapted_facts": […], "adapted_note": "…"},
    "intent":  {"text": "…", "provenance": "…", "evidence": […], "adapted_facts": […], "adapted_note": "…"},
    "organization": {"text": "…", "provenance": "…", "adapted_facts": […], "adapted_note": "…"},
    "errors": {"rows": [{"error": {"text":"…","provenance":"…",…},
                          "fix":  {"text":"…（含再次检查）","provenance":"…",…}}]}
  },
  "figures": [{"ref": "图3-2-2", "caption": "…", "provenance": "textbook", "evidence": […]}],
  "flow": [
    {"stage": "规则讲解", "script": "…（本活动的动作与规则，禁套话）",
     "demo_sec": 10, "pause_sec": 5,
     "provenance": "adapted", "evidence": […], "adapted_facts": […], "adapted_note": "…"}
  ],
  "source_view_entry": {"…build_generatable_view.py 输出的本条视图记录，含 v3 新字段…"},
  "notes": {"human_rewrite_applied": true, "sport": "…"}
}
```

硬性约束（fill load_draft 校验）：flow ≥3 阶段；fields 四块 text 非空且无 `：:——`；
practice 必有 errors.rows；figure_images 指向存在的文件；cta 与固定引流段一致；
adapted_facts 非空 ⇒ adapted_note 非空；script 内不得出现 `。。` 等断裂标点（硬门）。

## 5. review@1 评审记录（scripts/review_trial_daily.json）

```json
{
  "schema": "pe-trial-daily/review@1",
  "id": "PTD-046-体能-抢背后滚球",
  "draft_sha": "<ptd_core.draft_hash(草稿) 前 16 位>",
  "reviewer": "agent（内容评审）",
  "checked": {
    "action_logic_ok": true,
    "suggestions_labeled": true,
    "correction_effective": true,
    "tellable": true,
    "safety_executable": true
  },
  "suggestion_notes": [
    {"where": "flow[规则讲解]", "why": "起跑时机改为'看线不看到人'属于可执行化改写，动作与判定未变"},
    {"where": "fields.rules", "why": "补充轮换顺序为组织需要，教材未规定，已标教学建议"}
  ],
  "verdict": "pass"
}
```

五项 checked 的含义与判定依据（评审实责，逐项给 true/false）：

| 项 | 含义 | 判 false 的典型 |
|---|---|---|
| action_logic_ok | 动作逻辑与教材一致 | 加"听球声/转身起跑"等教材没有的动作环节 |
| suggestions_labeled | 新增玩法/提示/纠错均标教学建议且登记理由 | 把积分制、输方表演当教材规则 |
| correction_effective | 纠错含具体表现+纠正办法+再次检查 | 只有"动作规范一点" |
| tellable | 考生能依据成稿完成示范、组织、纠错、评价 | 组织只有"分组练习"四个字 |
| safety_executable | 安全为可执行口令（场地/路线/停止条件） | 只有"注意安全" |

版本绑定：`draft_sha` 不一致 = 内容修改后沿用旧审核 → 硬拦，重新评审后才可生成。

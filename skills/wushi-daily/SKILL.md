---
name: wushi-daily
description: 自动生成「公务员务实·岗位业务」小红书图文。每期一个岗位一个业务：从《公务员务实手册》16 岗源稿逐字提取场景/编号步骤/红线/答题嵌入句，答一道 VI 简洁风 6 卡（1080×1440，PIL）加笔记文案；双脚本门禁（verbatim 事实校验、假大空七禁词）防事实漂移，progress 防重复出期。触发词：出一期务实、务实每日一练、岗位业务图文、务实卡片。
---

# 公务员务实·岗位业务小红书 · 自动出帖

把《公务员务实手册》已验收源稿（16 岗 × 每岗 3 业务 = 48 期库存）逐期转成小红书图文。每期 = 1 岗位 + 1 业务，卡片上的步骤、红线、嵌入句**逐字来自源稿**，只有标题/正文/tags 是自由文案。

## 适用边界

- 适用：出「岗位业务」系列图文（一岗一业务：步骤/红线/嵌入句）。
- 不适用：真题解析与每日一练答题帖（structured-post / structured-tips-daily）、手册整体宣传（已有《公务员务实手册小红书图文》目录）。

## Pre-flight（全过才动手）

1. 源稿目录存在 16 个 `{岗}岗-公务员务实.md`：
   `/Users/shawn/Desktop/AI工作区/02-Areas/公考面试结构化培训/03_热点与素材/公务员务实/`（已内置为脚本默认，勿改）
2. 字体齐全：`/Users/shawn/Library/Fonts/HarmonyOS_Sans_SC_{Black,Bold,Medium,Regular}.ttf`
3. `python3 -c "import PIL"` 可用；总品牌 logo 在位：`/Users/shawn/Desktop/AI工作区/01-Projects/公考橙皮书/assets/logo-zfz.png`（页眉贴图用，缺失即 STOP）
4. 进度文件 `/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/公务员务实/progress_wushi.json`；不存在则首建
   `{"done": [], "last_done": "", "last_date": ""}`（该目录即输出基准目录：进度文件与 `第{N}期-*` 期目录都在其下，渲染脚本已内置，勿改）

## 数据流

```
源稿 md --(逐字摘录)--> pending_wushi.json
        --check_wushi_content.py--> 门禁退出码 0（自动写 <pending>.passed 标记）
        --gen_wushi_cards.py--> 6 张 PNG + 笔记文案.md（凭 .passed 标记渲染，双 ✅ 后自动删 pending 与标记）
        --(手动)--> progress.done 追加
```

## 工作流（8 步）

1. **Pre-flight**：四项全过。
2. **选题**：
   - 用户指定「公安 接处警」→ 岗位 = 源稿文件名前缀（去"岗"字）；业务名须与源稿 `### 业务 N：X` 的 X 完全一致（也接受 `业务1` 写法）。
   - 自动：源目录文件名 sorted 升序 × 每岗业务 1→3，取第一个不在 `progress.done` 的组合。
   - 命中 done → 🔴 STOP，报告已出期，不得重出。
3. **逐字取源**：读源稿对应业务，把 场景 / 编号步骤（lead+body 按首个冒号拆）/ 红线（分号拆项）/ 答题嵌入句（去外层「」）**原样复制**进 `pending_wushi.json`。不许改写、缩写、润色——门禁做 normalize 后全等校验。
4. **自由文案**（写进 pending 同一文件）：`titles` 3 个（各 ≤20 字）、`cover_hook`（≤24 字）、`body_note`（小红书正文，emoji 分段，**必过 human-writing 去 AI 味**；工具不可用不许静默跳过，置 `status=fallback` 并在 note 说明）、`tags` ≥6 个、`pub_tips`、`fake_compare`（从源稿「假大空改写对照」表选一行原样抄）。
5. **门禁**：`python3 ~/.zcode/skills/wushi-daily/scripts/check_wushi_content.py --pending <路径>` → 必须退出码 0。FAIL 逐条修复 pending 后重跑；**只许改 pending，不许改源稿、不许改脚本阈值**。
6. **渲染**：`python3 ~/.zcode/skills/wushi-daily/scripts/gen_wushi_cards.py --pending <路径>` → 缺省自动写规范位置 `第{期号}-{岗位}-{业务名}/`；看到 `✅ 全部通过（6 图 + 笔记文案.md）` + `✅ pending 已删除` 两个标记才算成功。
7. **更新进度**：仅在第 5、6 步双成功后：done 追加 `"{岗位}-{业务名}"`，同步 `last_done` / `last_date`（当天）。脚本成功前不得更新进度；进度写失败只修进度、不重跑脚本。
8. **验证清单**（下方）全勾 → 报告期号、选题、文件清单。

## pending_wushi.json schema

| 字段 | 类型 | 约束 | 来源 |
| --- | --- | --- | --- |
| issue | str | 三位数字如 "001" | 递推 |
| post | str | 不带"岗"字，如 "公安" | 源稿文件名 |
| source_file | str | `"{post}岗-公务员务实.md"` | 固定格式 |
| business | str | 与源稿 `### 业务 N：X` 的 X 完全一致 | 源稿 |
| scene | str | verbatim | 源稿 |
| steps | list[{lead, body}] | verbatim，lead 允许空 | 源稿（首个冒号拆） |
| redlines | list[str] | verbatim（源稿分号拆项，保序去尾句号） | 源稿 |
| embed | str | verbatim（去外层「」） | 源稿 |
| fake_compare | {fake, real} | 必须能在源稿对照表找到该行 | 源稿表 |
| cover_hook | str | 1–24 字 | 自由文案 |
| titles | list[str]×3 | 各 ≤20 字，互不相同 | 自由文案 |
| body_note | str | ≥50 字，emoji 分段 | 自由文案（过 human-writing） |
| tags | list[str] | ≥6 个，均以 # 开头 | 自由文案 |
| pub_tips | str | 发布小贴士 | 自由文案 |
| human_writing | {status, note} | status ∈ used/fallback；fallback 须给 note | 执行记录 |

## 脚本与退出码

- `check_wushi_content.py`：0 = 全过（并写 `<pending>.passed` 标记）；1 = 有 FAIL（逐条 `[FAIL] R编号` 打印）。规则：R4-R8 verbatim 一致性（normalize 口径 = NFC + 弯引号归一 + 去空白/零宽字符）；R9 七禁词与 R10 合规词（保过/包过/稳过/必过/万能/直接背/押题/内部渠道/百分百/一次过/包上岸/送分/躺赢/原题）**只扫自由文案字段**——verbatim 字段靠 R4-R8 对已验收源稿保真，`fake_compare.fake` 是被批判的假大空原句本就不扫；R9 仅 body_note/pub_tips 豁免「」『』引号内内容（痛点对照批判写法），titles/cover_hook/tags 不豁免，R10 一律不豁免；R11-R13 自由文案约束、R14 无编造文号、R16 human-writing 记录、R17 渲染长度上限（scene≤120/embed≤140/步骤体≤90/红线项≤40）。
- `gen_wushi_cards.py`：无 `.passed` 标记直接拒绝渲染（防绕过门禁）；先全部渲染进内存再统一落盘（失败不留半套图）；成功打印双 ✅ 并自动删 pending 与标记；失败保留、非零退出。`--check --outdir <期目录>` 可单独复核 logo 区域像素。
- 版式细节（尺寸/色值/每卡结构/自适应档位）见 [references/card-layout.md](references/card-layout.md)，仅在调版式时读。

## 🔴 STOP 与反例黑名单

- 不许改源稿；不许"优化"源稿文字再上卡。
- 不许跳过门禁、`|| true`、改脚本阈值或白名单。
- human-writing 不可用不许静默跳过（必须 fallback 标记 + note）。
- 门禁或渲染失败不许更新 progress。
- 已做选题不许重出；一次只出一期。
- 自由文案不许编造数据、文号、案件名；政策表述保持文件名级。
- verbatim 字段不许转述后填入（normalize 后全等，转述必 FAIL）。

## 验证清单

- [ ] check_wushi_content.py 退出码 0
- [ ] gen_wushi_cards.py 双 ✅
- [ ] 期目录 6 张 PNG + 笔记文案.md 齐全
- [ ] `gen_wushi_cards.py --check --outdir <期目录>` PASS
- [ ] progress.done 已追加且与期目录一致
- [ ] 笔记文案口径：无 保过/包过/万能/直接背 类表述

## 失败处理

- 门禁 FAIL：按 [FAIL] 行逐条改 pending，重跑门禁。
- 渲染 FAIL（版面放不下等）：该业务数据异常时 STOP 上报，不许截断文字、不许手改源稿。
- pending 被误删：回到第 3 步重新摘录（源稿是唯一事实源）。
- progress_wushi.json 损坏/截断：**不许当空进度重出**。以基准目录下既有 `第{N}期-*` 目录反推重建 done（目录名 = 期号-岗位-业务名），issue = 已有最大期号 + 1（首期 = "001"）；重建后向用户报告重建结果。期号一律由此递推，不许凭记忆。
- `.passed` 标记丢失但 pending 未变：重跑一次门禁即可（秒级），不许跳过。
- 期目录已存在但 progress 未记（上次渲染成功后中断在更新进度前）：重跑门禁 + 渲染（幂等覆盖同目录）→ 补记 progress；**不许新开期号、不许换选题**。
- R3/R5 计数异常或 R17 超限（源稿本该全库同构）：视为源稿结构漂移，STOP 上报；不许改 parser、不许改门禁阈值、不许就地"适配"——由人确认源稿变化后再升级本 skill。

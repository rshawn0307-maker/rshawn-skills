# 🧰 rshawn-skills

Shawn 的个人 AI Agent Skill 合集，遵循 Agent Skills 开放标准。每个 skill 都是自包含目录（`SKILL.md` + 可选 `scripts/`、`references/`），适用于 Claude Code、Codex、Cursor、Trae 等支持 Agent Skills 的工具。

## Skill 目录

### 🧑‍💻 原创自研

自己写的工作流与工具，按需修改、随取随用。

| Skill | 一句话说明 | 讲解 |
| --- | --- | --- |
| [gongkao](#gongkao) | 公考面试结构化讲义全产品工具（6 个工作流） | [查看](#gongkao) |
| [ima-skill](#ima-skill) | 统一的 IMA 笔记与知识库操作技能 | [查看](#ima-skill) |
| [PE-lecture](#PE-lecture) | 教师编笔试"举一反三"讲稿生成与反例沉淀 | [查看](#PE-lecture) |
| [PE-trial](#PE-trial) | 体育试讲稿教学产物全流程生成（考试规则可配置 + 独立验真） | [查看](#PE-trial) |
| [PE-trial-daily](#PE-trial-daily) | 体育试讲设计每日一练：拆解教学环节 + 图例 + 试讲逐字稿 docx 自动生成 | [查看](#PE-trial-daily) |
| [structured-post](#structured-post) | "结构化每日一练"帖子 docx 自动生成 | [查看](#structured-post) |
| [structured-tips-daily](#structured-tips-daily) | "结构化答题技巧·每日一练"小红书爆款图文帖子 docx 自动生成 | [查看](#structured-tips-daily) |
| [PE-bishi-daily](#pe-bishi-daily) | "每天一个体育笔试知识点"帖子 docx 自动生成（可同步 ima 知识库） | [查看](#pe-bishi-daily) |
| [PE-bishi-jd-daily](#pe-bishi-jd-daily) | 体育笔试简答题每日一练：简答题 + 参考答案 + 要点解析表，保留原版模板与生成门槛 | [查看](#pe-bishi-jd-daily) |
| [wushi-daily](#wushi-daily) | "公务员务实·岗位业务"小红书图文自动生成（PIL 6 卡 + 双脚本事实门禁） | [查看](#wushi-daily) |

### 🌟 社区精选 · 转载

收录自开源社区，说明列均标注来源；每个目录内都有 `ORIGIN.md` 出处声明，khazix / 花叔系列另有对应的一键同步脚本。

**花叔系列**（收录自 [alchaincyf](https://github.com/alchaincyf)）

| Skill | 一句话说明 | 讲解 |
| --- | --- | --- |
| [darwin-skill](#darwin-skill) | 让所有 Skill 自主进化：9 维评估 + 独立评分 + 棘轮机制（来源：花叔） | [查看](#darwin-skill) |
| [huashu-design](#huashu-design) | 用 HTML 做高保真原型/PPT/动画/可视化与专家评审（来源：花叔） | [查看](#huashu-design) |
| [huashu-report](#huashu-report) | 机构级研究报告与学术论文：研报/白皮书/调研/arXiv 论文/16:9 咨询 deck（来源：花叔） | [查看](#huashu-report) |
| [huashu-art-motion](#huashu-art-motion) | 艺术与视频动画：36 种实做风格＋16 种迁移配方、镜头表工作流、9 种解说动画语法、口播整片管线（来源：花叔） | [查看](#huashu-art-motion) |
| [huashu-motion](#huashu-motion) | 商业级动效/发布片/解说视频：片子即代码，浏览器 studio 指着画面改，自动配乐与口播（来源：花叔） | [查看](#huashu-motion) |
| [huashu-mac-use](#huashu-mac-use) | 操控无 API 的 macOS 原生 app：四层控制面、零焦点写入、窗口级取证截图（来源：花叔） | [查看](#huashu-mac-use) |
| [huashu-gpt-image](#huashu-gpt-image) | GPT-image 生图方法论：真实参考名替代形容词，单图 playbook、批量网格、失败模式树（来源：花叔） | [查看](#huashu-gpt-image) |
| [huashu-md-html](#huashu-md-html) | md 流水线：万物（PDF/DOCX/EPUB/网页/音频）转干净 md，md 加工成出版级 HTML/DOCX，四套反 AI slop 主题（来源：花叔） | [查看](#huashu-md-html) |
| [tramstop-skill](#tramstop-skill) | 电车站.skill：证据驱动的去 AI 味，四层 AI 味模型 + 真实素材注入（来源：花叔） | [查看](#tramstop-skill) |
| [huashu-icon-set](#huashu-icon-set) | 端到端生成风格统一的图标集：4×4 网格批量 + 逐个精度兜底（来源：花叔） | [查看](#huashu-icon-set) |
| [huashu-md-to-pdf](#huashu-md-to-pdf) | Markdown 转苹果风专业 PDF：书籍级排版、自动封面目录（来源：花叔） | [查看](#huashu-md-to-pdf) |
| [huashu-article-edit](#huashu-article-edit) | 标准化文章编辑：先列修改项确认范围，增量保存，变更有记录（来源：花叔） | [查看](#huashu-article-edit) |
| [huashu-topic-gen](#huashu-topic-gen) | 选题生成：3-4 个方案，含标题、大纲、优劣分析和工作量评估（来源：花叔） | [查看](#huashu-topic-gen) |
| [huashu-script-polish](#huashu-script-polish) | 视频脚本口语化：去书面腔，短句化，标注停顿重音（来源：花叔） | [查看](#huashu-script-polish) |
| [huashu-speech-coach](#huashu-speech-coach) | 演讲教练：Patrick Winston「How to Speak」方法论（来源：花叔） | [查看](#huashu-speech-coach) |
| [huashu-skill-updater](#huashu-skill-updater) | 花叔系 skill 更新检查：对比远程最新 commit 报告落后项（来源：花叔） | [查看](#huashu-skill-updater) |

> 🐦 **资源库（不入库分发）**：[alchaincyf/huashu-bird-sticker](https://github.com/alchaincyf/huashu-bird-sticker) — 全球鸟类贴纸库，11064 种现生鸟各一张白边贴纸 + 结构化数据（分类/43 语种鸟名/数据库编号），1.4GB。PolyForm Shield 1.0.0 授权（唯一限制：不得用于竞品观鸟 App）。本仓库不存储内容，端上已安装。

**khazix系列**（收录自 [KKKKhazix](https://github.com/KKKKhazix)）

| Skill | 一句话说明 | 讲解 |
| --- | --- | --- |
| [leader](#leader) | 把一句话想法拆成 AI agent 能独立跑完的目标任务书（来源：khazix） | [查看](#leader) |
| [neat-freak](#neat-freak) | 项目知识收尾：让文档、规则、记忆与代码现状一致（来源：khazix） | [查看](#neat-freak) |
| [human-writing](#human-writing) | 通用中文创作与改稿，去 AI 味儿（来源：khazix） | [查看](#human-writing) |
| [storage-analyzer](#storage-analyzer) | macOS / Windows 只读存储分析与交互式清理报告（来源：khazix） | [查看](#storage-analyzer) |
| [khazix-writer](#khazix-writer) | 数字生命卡兹克公众号长文写作风格：素材→成稿（来源：khazix） | [查看](#khazix-writer) |

## 安装（通用方法）

### 方法一：让 Agent 帮你安装

对你的 Agent 说：

> 帮我安装这个 skill：`https://github.com/rshawn0307-maker/rshawn-skills/tree/main/skills/<skill 名>`

支持从 GitHub 安装 Skill 的工具会自动 clone 并注册。

### 方法二：手动复制目录

将 `skills/<skill 名>/` 整个目录复制到你的工具对应的 skills 目录：

- Claude Code：`~/.claude/skills/<skill 名>/`
- Codex：`~/.codex/skills/<skill 名>/`
- Cursor：`.cursor/skills/<skill 名>/`
- Trae：`~/.trae-cn/skills/<skill 名>/`
- 其他 runtime：参考对应工具的 skills 目录约定

### 方法三：不支持 Skill 的工具

复制 `SKILL.md` 的内容作为项目规则文件（如 `CLAUDE.md` / `AGENTS.md`）的参考，或直接粘贴给 Agent 作为系统提示词。

> 提示：少数 skill 依赖同仓库的兄弟 skill（例如 structured-post、structured-tips-daily 依赖 human-writing，ima-skill 供多个 skill 调用），建议一起安装到同一个 skills 根目录。

> 提示：huashu-design（约 40MB，含风格标本与案例资源）、huashu-art-motion（约 74MB，含示例素材与渲染引擎脚本）、huashu-md-html（约 15MB，含主题与示例）、huashu-gpt-image（约 10MB）与 huashu-motion（约 22MB，含 CLI、模板、字体与示例）体积较大，请整目录复制，不要只拷 SKILL.md。

## Skill 详解

### 🧑‍💻 原创自研

#### gongkao

公考面试结构化讲义全产品工具。覆盖题目生成、方法论提炼、框架模板、过渡句库、素材库、讲义组装 6 个工作流，支持从单题生成到完整讲义产品的全生命周期。每道题含 frontmatter 元信息、题干、思路大纲和 800-1000 字逐字稿，并经 Python 多模式验证（字数 + AI 痕迹 + 用语禁忌 + 结构完整性）后写入对应目录。

触发词：面试题库、出面试题、公考面试题、批量出题、题库填充、面试逐字稿、生成方法论、生成框架、生成过渡句、生成素材、组装讲义、更新讲义、导出讲义。

#### ima-skill

统一的 IMA OpenAPI 技能（v1.1.10），支持笔记管理和知识库操作：搜索/浏览/创建/追加笔记、插入本地图片到笔记，上传文件、添加网页到知识库、知识库内容搜索与原文获取。需要自行配置 IMA OpenAPI 凭证（`IMA_OPENAPI_CLIENTID` / `IMA_OPENAPI_APIKEY` 或 `~/.config/ima/`）。

触发词：知识库、笔记、备忘录、帮我记一下、上传文件到知识库、搜一下知识库里有没有 XX、插入图片到笔记。

> 本地补丁（v1.1.10 起生效）：主 SKILL.md「API 调用模板」示例中的端点 `openapi/list_docs` 在服务端不存在（HTTP 404），已改为 `openapi/note/v1/list_note`。上游若在后续版本修正，同步时可回退该行。

#### PE-lecture

教师编体育笔试"举一反三"讲稿的成体系生成与反例沉淀。基于招教体育讲义库，按 8 节结构 + 引用/口诀/双链硬约束批量产出讲稿；内置 R1-R20 实战反例（拆分为独立 references/核心反例_R1-R20.md）、六维度横评机制（全库审核打分）、双视角授课提示与 v2 修订说明模板，md→Word 采用通用提示词（v3.8 替代旧合并脚本，v3.9 新增代码思维导图/时间线转图提示词）。另有讲义库完整 SOP v3.4 与版本记录/专项经验两个维护型 reference。

> 注意：本 skill 涉及大量业务工作区路径，文档中统一使用 `<项目根>`、`<用户目录>`、`<临时目录>`、`<Python 环境>` 占位符，使用前请替换为实际路径。

#### PE-trial

生成体育试讲稿教学产物（教学设计/试讲稿/队形图/自检表），含初始化、子技术识别、并行生产、六维度横评、问题修复、备考讲义生成全流程，支持基于教材批量开发新运动项目。考试规则由 `references/exam-profile.md` 的 EXAM_PROFILE 驱动（时长/是否配学生/器材/评分口径等可配置），产物规格与评分口径分别落在 `references/artifacts-spec.md` 与 `references/scoring-rubric.md`（含 VETO 项的评分矩阵）。

配套 `scripts/validate_artifacts.py`（纯 stdlib，无第三方依赖）可脱离生成器独立验真：校验净稿套件完整性、EXAM_PROFILE 一致性、教材源冲突与 docx 版式，支持 `--json` 输出；`tests/` 下 22 个单测覆盖正反例。

> 用法：`generate_lecture.py` 已改为显式 CLI，`--base-dir <产物库根>` 与 `--out <输出 docx>` 为必填参数，无需再改脚本内常量；另有 `--projects` / `--only` / `--font` 过滤项，`--check`（构建渲染自检但不写 final）与 `--dry-run`（只做发现与解析统计）。退出码：0 成功 / 2 用法或 IO 错误 / 3 零项目 / 4 解析异常 / 5 渲染自检失败。

#### PE-trial-daily

自动化生成「体育试讲设计每日一练」小红书帖子 docx，并可同步上传 ima 知识库「A-00 体育试讲设计每日一练」。基于 python-docx 从零构建品牌化 DOCX（深蓝封面 + 图例区 + 六维度环节拆解 + 易犯错误表格 + 试讲逐字稿 + 引流页），从人教版教师用书 313 个活动中每日拆解一个教学环节（热身游戏/体能游戏/练习环节），拆解成环节名称、活动方法、规则、设计意图、组织形式，练习环节另含易犯错误与纠正，最后串联成试讲逐字稿。内置选题进度追踪、快照回滚、原子提交与全字段校验。

图例处理：教师用书 PDF 均为纯扫描件（无文本层），内置 `build_ocr_index.py`（macOS Swift Vision OCR）+ `extract_pdf_image.py` 建立页索引并把 MD 中的「图3-2-7」映射到 PDF 页码渲染整页图，自动修正 180° 旋转。

触发词：体育试讲每日一练、试讲设计每日一练、出一期体育试讲设计。

> 注意：本 skill 涉及大量业务工作区路径，文档中为本机绝对路径，使用前请替换为实际路径。

#### structured-post

自动化生成"结构化每日一练"小红书/公众号帖子 docx。基于固定 docx 模板 + python-docx 脚本，自动替换题目文本框、正文段落、分页符并保留配图/引流段样式，答题须经 human-writing 去 AI 味儿（v1.3.2：新增 Pre-flight 三项检查、分题型高分要素、用语禁忌与 IMA 笔记上传）。

触发词：答一道、出题、做一篇结构化帖子、每日一练。

#### PE-bishi-daily

自动化生成「每天一个体育笔试知识点」小红书帖子 docx，并可同步上传到 ima 知识库「A-0 每日一个知识点（笔试）」。基于「体育笔试每日一练」固定模板 + python-docx 脚本，从「讲义库举一反三讲稿」（128 篇）中按模块顺序选题，自动套版式：封面大标题 + 单选题引出知识点，中间 2 页考点解析（图表优先，表格自适应列宽），最后一页考法提醒 + 话题标签 + 引流段，答题须经 human-writing 去 AI 味儿。内置选题进度追踪、快照回滚与全字段校验；ima 上传走 ima-skill（凭证在 ~/.config/ima/）。

触发词：每天一个体育笔试知识点、体育笔试每日一练、出一期体育笔试知识点。

> 注意：本 skill 涉及大量业务工作区路径，文档中为本机绝对路径，使用前请替换为实际路径。

#### PE-bishi-jd-daily

[查看技能文件](skills/PE-bishi-jd-daily/SKILL.md)。基于 PE-bishi-daily 的简答题版本，沿用讲义库举一反三讲稿、固定品牌模板、图表优先布局和原有生成条件。首页用一道简答题替换单选题，正文给出完整参考答案，再用 1–2 张表拆解答题要点、关键词与易漏点；保留 4 段解析引导、5 条考法提醒、话题标签和固定引流段。须经 human-writing 改写与内容复核，支持按要求上传到同一 ima 知识库。

自带填充脚本与隔离回归测试，保留 17 段正文、2 个 drawing、2 处封面镜像、表格自适应和原子提交校验。简答题版使用独立 pending、选题进度、输出和快照，避免影响单选题版；不编造分值或官方评分标准。

触发词：体育笔试简答题每日一练、每天一个体育笔试简答题知识点、出一期体育笔试简答题。

> 注意：沿用本机讲稿与源模板路径，使用前需确认实际路径、可导入 python-docx 的 Python 环境与独立简答题进度。`SPORTS_JD_DAILY_WORKSPACE` 应指向「体育教师编」目录本身，首次启用须确认该版本发布记录；模板与讲稿不随 skill 分发。

#### structured-tips-daily

自动化生成"结构化答题技巧·每日一练"小红书爆款图文帖子 docx。围绕公考结构化面试的答题技巧和思路，用上岸过来人 + 考官视角，按小红书爆款节奏（标题钩子/短句/emoji/普通 vs 高分对照/避坑提醒/话题标签）打磨。基于固定 docx 模板（17 段）+ python-docx 脚本自动替换，从题库索引（tips_index.json，36 条覆盖六大题型）选题防重复，答题须经 human-writing 去 AI 味儿，可同步 ima 知识库「总分总」→「00_结构化答题技巧」。

触发词：出一期答题技巧、技巧每日一练、答题思路、结构化答题技巧。

#### wushi-daily

自动化生成「公务员务实·岗位业务」小红书图文。每期一个岗位一个业务，从《公务员务实手册》16 岗已验收源稿（16 岗 × 每岗 3 业务 = 48 期库存）中逐字提取真实场景、编号步骤、红线与答题嵌入句，用 PIL 渲染答一道 VI 简洁风 6 卡（1080×1440）并配笔记文案——卡片上的步骤、红线、嵌入句全部逐字来自源稿，只有标题/正文/tags 是自由文案。内置双脚本门禁（verbatim 事实校验 + 假大空七禁词）防事实漂移，选题进度追踪防重复出期。

触发词：出一期务实、务实每日一练、岗位业务图文、务实卡片。

> 注意：本 skill 依赖本机源稿目录、HarmonyOS Sans SC 字体、PIL 环境与品牌 logo（Pre-flight 四项检查，缺失即停），使用前请确认路径有效。

### 🌟 社区精选 · 转载

**花叔系列**

#### darwin-skill

让所有 Skill 自主进化：9 维评分（结构 + 效果 + meta-skill 黑名单）+ 独立 judge agent 盲评 + 棘轮机制（只保留改进、自动回滚退步）+ 人在回路确认，并生成可视化成果卡片。触发词：优化 skill、skill 评分、自动优化、skill 质量检查、达尔文、darwin。

> 来源：[alchaincyf/darwin-skill](https://github.com/alchaincyf/darwin-skill)（作者：花叔 alchaincyf）

> 同步：上游更新后可运行 `bash scripts/sync-huashu.sh` 一键拉取最新版（见下方「同步花叔来源 skill」）。

#### huashu-design

用 HTML 做高保真原型、PPT/幻灯片、动画、信息图与专家评审的「设计师」skill：任何新视觉设计 100% 先出三个方向初稿给用户选（硬门，指定风格/品牌也不豁免），选定后才进入标准流程。内置核心原则 #0 事实验证（涉及具体产品先 WebSearch，不做记忆断言）、反 AI slop 硬约束、品牌资产协议、App/iOS 原型专属守则、Gate 文件协议（direction-approved.md 等）以及动画/视频导出（SFX+BGM、HyperFrames 后端）完整链路。触发词：做原型、PPT、幻灯片、动画、设计风格、评审、UI mockup、导出 MP4/GIF。

> 注意：本 skill 体积较大（约 30MB，含动画模板、音效与案例资源），安装时请完整复制整个目录。

> 来源：[alchaincyf/huashu-design](https://github.com/alchaincyf/huashu-design)（作者：花叔 alchaincyf）

> 同步：上游更新后可运行 `bash scripts/sync-huashu.sh` 一键拉取最新版（见下方「同步花叔来源 skill」）。

#### huashu-report

做机构级研究报告与学术论文的 skill：覆盖行业研报、白皮书、年度调研、数据洞察、arXiv 论文与 16:9 咨询 deck 型报告（一页一结论）。开工先按读者用途从六种报告原型（学术/咨询 deck/调查/研报/论文/科普）中选型，写下报告的一句话结论、找到外部基准；核心方法是依次扮演研究员（定口径、给机制、定位文献）、编辑、信息设计师、数据可视化师四个角色，并执行「每个数字都要有分母」「图表标题写结论」等五条硬规矩。规范提炼自 2026 年顶级机构报告实测，单篇文章与纯演示 PPT 不适用（走 huashu-design）。触发词：写报告、行业报告、白皮书、调研报告、数据洞察、论文、咨询 deck。

> 来源：[alchaincyf/huashu-report](https://github.com/alchaincyf/huashu-report)（作者：花叔 alchaincyf）

> 同步：上游更新后可运行 `bash scripts/sync-huashu.sh` 一键拉取最新版（见下方「同步花叔来源 skill」）。

#### huashu-art-motion

用代码画画的「艺术动画」skill（v1.2.0 起采用镜头表工作流）：开工先锁画风写镜头表（画风/色板/角色三行 + 每镜时间段/物/动词/镜头/屏上字/做法），`storyboard_lint.py` 红灯不许写代码；再按镜头表逐镜产出（9 种解说动画语法可按口播参数渲片段、36 种实做风格＋16 种可迁移研究配方的 scenes、人物用 AI 生帧＋代码合成），ffmpeg 硬切拼接成片，`qa.py` 查跳变、`deliver.py` 门禁绿灯才交付（红灯不复制成片）。支持复刻拆解、指定艺术风格、口播整片三条路线，口播可选已有录音/系统声音/语音复刻。触发词：复刻这个动画、梵高/莫奈那种风格、艺术动画、解说动画、Kurzgesagt/Vox/3b1b 风格、口播做片。

> 注意：本 skill 体积较大（约 74MB，含示例素材与渲染引擎脚本），安装时请完整复制整个目录；渲染依赖 uv + Playwright（Chromium）与 FFmpeg。

> 来源：[alchaincyf/huashu-art-motion](https://github.com/alchaincyf/huashu-art-motion)（作者：花叔 alchaincyf）

> 同步：上游更新后可运行 `bash scripts/sync-huashu.sh` 一键拉取最新版（见下方「同步花叔来源 skill」）。

#### huashu-motion

让 agent 直接做出可编辑的商业级动效片：发布片、产品宣传片、解说视频。片子是代码（`index.html` + GSAP，用本机 Chrome 逐帧渲染），导演流程先读产品与品牌、给三个方向、写 treatment 与节奏谱、先做最难镜头；内置 `om check`/`om still`/`om qa` 做帧级自查（裁切、遮挡、低对比、单帧闪跳、死时间），`om sound` 按场景自动配乐与音效（也可自己写 ABC 乐谱），`om voice` 做口播与字幕，`om render` 导出 mp4/mov/webm/gif（可开运动模糊）。`om studio` 在浏览器里直播预览，用户点画面写一句意见，agent 用 `om inbox`/`om look`/`om done` 只改那一处，版本历史可 `om undo`。触发词：发布片、宣传片、产品视频、动效、解说视频、launch video。

> 注意：本 skill 体积约 22MB（含 CLI、模板、字体与示例），安装时请完整复制整个目录；运行时依赖 Node ≥22、Chrome 与 FFmpeg，装完用 `om doctor` 自检。

> 来源：[alchaincyf/huashu-motion](https://github.com/alchaincyf/huashu-motion)（作者：花叔 alchaincyf）

> 同步：上游更新后可运行 `bash scripts/sync-huashu-motion.sh` 一键拉取最新版（见下方「同步 huashu-motion 来源 skill」）。

#### huashu-mac-use

操控没有 API 的 macOS 原生 app 并留下可复现取证：四层控制面（内嵌 Chromium 的 app 走 CDP 零焦点 → AX 树 → 窗口坐标 → 像素），读完全后台、写默认不抢焦点（postToPid 直投 + 终端闸/全机锁/在场闸三道闸，借焦点时屏幕四角闪取景框提示），写操作自动差分回执 `effect=confirmed/noop`，写前 `--dry` 预演；后台截指定窗口（被遮挡也能截）+ 取证规范（收据、禁词表、原图归档）；`probe.sh` 探测陌生 app 能否自动化，支持产品实测与多模型同题跑批。明确停手线：不可逆动作、终端/IDE 回车、TCC 弹窗、银行医疗类 app 一律交还用户。触发词：操作原生 app、截这个窗口、点点这个菜单、这个 app 能不能自动化、产品实测跑批。

> 注意：本 skill 首次使用需跑 `scripts/build.sh` 编译 Swift 内核（约 20 秒，要求 Xcode Command Line Tools）；本仓库副本不含编译产物。运行依赖 macOS 辅助功能与屏幕录制权限。

> 来源：[alchaincyf/huashu-mac-use](https://github.com/alchaincyf/huashu-mac-use)（作者：花叔 alchaincyf）

> 同步：本 skill 未纳入一键脚本（需保留本机编译内核 `scripts/mac`），上游更新后参照其目录内 `ORIGIN.md` 的命令手动同步。
#### huashu-gpt-image

GPT-image 的 prompt 工程方法论：用真实参考名替代形容词堆砌，含单图 playbook、批量网格生成与失败模式树，配图/封面生图任务直接可用。触发词：生图、配图、封面、GPT-image。

> 来源：[alchaincyf/huashu-gpt-image](https://github.com/alchaincyf/huashu-gpt-image)（作者：花叔 alchaincyf）。同步：`bash scripts/sync-huashu.sh`

#### huashu-md-html

md 流水线 skill：把万物（PDF/DOCX/EPUB/网页/音频）转成干净 md，再把 md 加工成出版级 HTML/DOCX，内置四套反 AI slop 主题。触发词：转 markdown、md 转 HTML、出版级排版。

> 来源：[alchaincyf/huashu-md-html](https://github.com/alchaincyf/huashu-md-html)（作者：花叔 alchaincyf）。同步：`bash scripts/sync-huashu.sh`
> 注意：本 skill 约 15MB（含主题与示例），请整目录复制；Python 依赖见目录内 requirements.txt。

#### tramstop-skill

电车站.skill：证据驱动的去 AI 味，四层 AI 味模型 + 真实素材注入，来自四版本盲测实验。触发词：去 AI 味、电车站。

> 来源：[alchaincyf/tramstop-skill](https://github.com/alchaincyf/tramstop-skill)（来源：花叔 alchaincyf）。同步：`bash scripts/sync-huashu.sh`

#### huashu-md-to-pdf

Markdown 转苹果风专业 PDF：书籍级排版、自动封面目录。 触发词见目录内 SKILL.md。

> 来源：内置收录自 [alchaincyf/huashu-skills](https://github.com/alchaincyf/huashu-skills)（作者：花叔）。同步：`bash scripts/sync-huashu.sh`

#### huashu-article-edit

标准化文章编辑：先列修改项确认范围，增量保存，变更有记录。 触发词见目录内 SKILL.md。

> 来源：内置收录自 [alchaincyf/huashu-skills](https://github.com/alchaincyf/huashu-skills)（作者：花叔）。同步：`bash scripts/sync-huashu.sh`

#### huashu-topic-gen

选题生成：3-4 个方案，含标题、大纲、优劣分析和工作量评估。 触发词见目录内 SKILL.md。

> 来源：内置收录自 [alchaincyf/huashu-skills](https://github.com/alchaincyf/huashu-skills)（作者：花叔）。同步：`bash scripts/sync-huashu.sh`

#### huashu-script-polish

视频脚本口语化：去书面腔，短句化，标注停顿重音。 触发词见目录内 SKILL.md。

> 来源：内置收录自 [alchaincyf/huashu-skills](https://github.com/alchaincyf/huashu-skills)（作者：花叔）。同步：`bash scripts/sync-huashu.sh`

#### huashu-speech-coach

演讲教练：Patrick Winston「How to Speak」方法论。 触发词见目录内 SKILL.md。

> 来源：内置收录自 [alchaincyf/huashu-skills](https://github.com/alchaincyf/huashu-skills)（作者：花叔）。同步：`bash scripts/sync-huashu.sh`

#### huashu-skill-updater

花叔系 skill 更新检查：对比远程最新 commit 报告落后项。 触发词见目录内 SKILL.md。

> 来源：内置收录自 [alchaincyf/huashu-skills](https://github.com/alchaincyf/huashu-skills)（作者：花叔）。同步：`bash scripts/sync-huashu.sh`

#### huashu-icon-set

端到端为项目生成风格统一的图标集：4×4 网格批量生成 + 逐个精度兜底 + 智能抠图（豆包环境专用，依赖内置 image_gen）。触发词：图标集、icon、生成图标。

> 来源：[alchaincyf/huashu-icon-set](https://github.com/alchaincyf/huashu-icon-set)（作者：花叔 alchaincyf）。同步：`bash scripts/sync-huashu.sh`

**khazix系列**

#### leader

把一句话的想法拆成 AI agent 能独立跑完的目标任务书。先进代码库实测、必要时联网调研，再一次性提问（≤5 个），产出一份 ≤4000 字符、直接粘进 /goal 就能跑的任务书，含实测数字、白名单地界、防作弊验收和断点续跑。

触发词：帮我给 agent 写个目标、详细拆一下这个目标、写个任务书/brief、写个 goal 提示词、把活分给几个 agent 并行。

> 来源：[khazix-skills](https://github.com/KKKKhazix/khazix-skills)（作者 KKKKhazix）

> 同步：上游更新后可运行 `bash scripts/sync-khazix.sh` 一键拉取最新版（见下方「同步 khazix 来源 skill」）。

#### neat-freak

知识收尾与治理：核对项目文档、规则文件（CLAUDE.md/AGENTS.md）、获准维护的记忆和工作区残留与代码、真实运行态是否一致，让下一次会话或接手的人从唯一现役答案开始。触发词：洁癖、/neat、把文档和记忆整理一下、收尾时把文档同步掉。

> 来源：[khazix-skills](https://github.com/KKKKhazix/khazix-skills)（作者 KKKKhazix）

> 同步：上游更新后可运行 `bash scripts/sync-khazix.sh` 一键拉取最新版（见下方「同步 khazix 来源 skill」）。

#### human-writing

通用中文创作与改稿 Skill。用于知乎回答、公众号文章、博客、评论、人物故事、历史叙事、教程、评测、小说、口播和演讲稿等，默认写成一个见过事、查过材料、愿意把来龙去脉讲清楚的人在说话，保留中文互联网长文的活人感和自然韵律。成稿正文严禁冒号、破折号、"不是……而是……"及同类翻案句，并清除商业黑话和模型惯用黑话。

> 来源：[KKKKhazix/human-writing](https://github.com/KKKKhazix/human-writing)（作者 KKKKhazix）

> 同步：上游更新后可运行 `bash scripts/sync-khazix.sh` 一键拉取最新版（见下方「同步 khazix 来源 skill」）。

#### storage-analyzer

macOS / Windows 只读存储分析助手：扫描整机磁盘占用，把占用大户分为 🟢 可自动清理 / 🟡 需人工判断 / 🔴 谨慎清理 三级，生成可折叠、命令可一键复制的交互式 HTML 报告，并支持在网页上安全清理（移废纸篓/直接删）。扫描全程只读，删除命令仅展示不代跑。

> 来源：[khazix-skills](https://github.com/KKKKhazix/khazix-skills)（作者 KKKKhazix）

> 同步：上游更新后可运行 `bash scripts/sync-khazix.sh` 一键拉取最新版（见下方「同步 khazix 来源 skill」）。

#### khazix-writer

复刻「数字生命卡兹克」公众号长文写作风格的 skill：撰写公众号文章、续写、扩写、按素材出稿（PDF / brief / 新闻链接 / 语音转文字均可），说「帮我把这个写成文章」「用我的风格写一下」也会触发；内置卡兹克的选题眼光、行文节奏与语言习惯。短内容（小红书帖 / 推特 / 朋友圈）与纯标题摘要生成不适用（后者用 wechat-title）。触发词：写文章、写稿子、帮我写、续写、扩写、公众号文章、长文、出稿、按我的风格写。

> 来源：[khazix-skills](https://github.com/KKKKhazix/khazix-skills)（作者 KKKKhazix）

> 同步：上游更新后可运行 `bash scripts/sync-khazix.sh` 一键拉取最新版（见下方「同步 khazix 来源 skill」）。

## 同步 khazix 来源 skill

仓库里的 `neat-freak`、`storage-analyzer`、`leader`、`khazix-writer` 收录自 [khazix-skills](https://github.com/KKKKhazix/khazix-skills)，`human-writing` 收录自其独立仓库 [KKKKhazix/human-writing](https://github.com/KKKKhazix/human-writing)。每个目录内都有 `ORIGIN.md` 注明出处。上游更新后，一条命令即可同步最新版：

```bash
bash scripts/sync-khazix.sh        # 只更新文件并打印变更
bash scripts/sync-khazix.sh --push # 更新并自动 commit + push
```

脚本会从 khazix-skills 拉取最新代码、覆盖对应 skill 目录，并自动保留/补回 `SKILL.md` 顶部的来源声明和 `ORIGIN.md`。若某个 skill 在上游已改名或删除，脚本会跳过并提示。

`gongkao`、`structured-post`、`structured-tips-daily` 三个 skill 的工作流依赖 human-writing，其规则引用一律以 human-writing 最新版为准（不锁版本号）。human-writing 更新后运行同步脚本，脚本会自动校验这三个 skill 的引用与硬禁令要点（冒号/破折号/翻案腔）是否齐全，缺失会明确提示。

## 同步花叔来源 skill

仓库里的 `darwin-skill`、`huashu-design`、`huashu-report`、`huashu-art-motion` 收录自花叔（alchaincyf）的八个独立仓库，另有六个内置轻量 skill 收录自 huashu-skills 仓库。每个目录内都有 `ORIGIN.md` 注明出处。上游更新后，一条命令即可同步最新版：

```bash
bash scripts/sync-huashu.sh        # 只更新文件并打印变更
bash scripts/sync-huashu.sh --push # 更新并自动 commit + push
```

脚本会从上游仓库拉取最新代码、覆盖对应 skill 目录，并自动保留/补回 `SKILL.md` 顶部的来源声明和 `ORIGIN.md`。若某个 skill 在上游已改名或删除，脚本会跳过并提示。注意 huashu-design（约 40MB 设计资源）与 huashu-art-motion（约 74MB 示例素材与渲染引擎脚本）体积较大，同步时会整体覆盖。

## 同步 huashu-motion 来源 skill

仓库里的 `huashu-motion` 收录自 [alchaincyf/huashu-motion](https://github.com/alchaincyf/huashu-motion)。上游是多端分发 monorepo：skill 本体在 `skills/huashu-motion/`，但 `bin/om` 要调用仓库根的 CLI，不能只拷 skill 子目录。脚本会重建扁平化布局（`SKILL.md`/`references/`/`bin/` + `cli/ runtime/ templates/ fonts/ studio/ examples/` + `package.json` 等，剔除 `docs/ site/ test/`），把 `bin/om` 的查找路径从 `../../../cli/om.js` 改成 `../cli/om.js`，并自动补回来源声明与 `ORIGIN.md`。上游更新后，一条命令即可同步最新版：

```bash
bash scripts/sync-huashu-motion.sh        # 只更新文件并打印变更
bash scripts/sync-huashu-motion.sh --push # 更新并自动 commit + push
```

注意：脚本走 git clone，github.com 直连易失败，请挂代理后运行。

## 许可

本仓库为个人作品，供学习交流使用。部分 skill 内容涉及具体业务场景与个人工作流，请按需修改后使用。

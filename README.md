# 🧰 rshawn-skills

Shawn 的个人 AI Agent Skill 合集，遵循 Agent Skills 开放标准。每个 skill 都是自包含目录（`SKILL.md` + 可选 `scripts/`、`references/`），适用于 Claude Code、Codex、Cursor、Trae 等支持 Agent Skills 的工具。

## Skill 目录

### 🧑‍💻 原创自研

自己写的工作流与工具，按需修改、随取随用。

| Skill | 一句话说明 | 讲解 |
| --- | --- | --- |
| [gongkao](#gongkao) | 公考面试结构化讲义全产品工具（6 个工作流） | [查看](#gongkao) |
| [ima-skill](#ima-skill) | 统一的 IMA 笔记与知识库操作技能 | [查看](#ima-skill) |
| [pe-lecture](#pe-lecture) | 教师编笔试"举一反三"讲稿生成与反例沉淀 | [查看](#pe-lecture) |
| [pe-trial](#pe-trial) | 体育试讲稿教学产物全流程生成 | [查看](#pe-trial) |
| [structured-post](#structured-post) | "结构化每日一练"帖子 docx 自动生成 | [查看](#structured-post) |
| [tiyu-bishi-meiri](#tiyu-bishi-meiri) | "每天一个体育笔试知识点"帖子 docx 自动生成 | [查看](#tiyu-bishi-meiri) |
| [zhankai](#zhankai) | "展开说说"系列小红书长帖 docx 自动生成 | [查看](#zhankai) |

### 🌟 社区精选 · 转载

收录自开源社区，说明列均标注来源；每个目录内都有 `ORIGIN.md` 出处声明，khazix / 花叔 / dashi 系列另有对应的一键同步脚本。

**花叔系列**（收录自 [alchaincyf](https://github.com/alchaincyf)）

| Skill | 一句话说明 | 讲解 |
| --- | --- | --- |
| [darwin-skill](#darwin-skill) | 让所有 Skill 自主进化：9 维评估 + 独立评分 + 棘轮机制（来源：花叔） | [查看](#darwin-skill) |
| [huashu-design](#huashu-design) | 用 HTML 做高保真原型/PPT/动画/可视化与专家评审（来源：花叔） | [查看](#huashu-design) |

**khazix系列**（收录自 [KKKKhazix](https://github.com/KKKKhazix)）

| Skill | 一句话说明 | 讲解 |
| --- | --- | --- |
| [leader](#leader) | 把一句话想法拆成 AI agent 能独立跑完的目标任务书（来源：khazix） | [查看](#leader) |
| [neat-freak](#neat-freak) | 项目知识收尾：让文档、规则、记忆与代码现状一致（来源：khazix） | [查看](#neat-freak) |
| [human-writing](#human-writing) | 通用中文创作与改稿，去 AI 味儿（来源：khazix） | [查看](#human-writing) |
| [storage-analyzer](#storage-analyzer) | macOS / Windows 只读存储分析与交互式清理报告（来源：khazix） | [查看](#storage-analyzer) |

**其他社区精选**

| Skill | 一句话说明 | 讲解 |
| --- | --- | --- |
| [dashi-ppt](#dashi-ppt) | 生成可浏览器编辑的 HTML 演示，支持导出 PPTX / PDF（来源：chuspeeism） | [查看](#dashi-ppt) |
| [docx](#docx) | 专业 Word 文档创建/编辑/修订/批注（来源：appautomaton） | [查看](#docx) |
| [defuddle](#defuddle) | 网页转干净 Markdown，收藏前先去噪（来源：kepano） | [查看](#defuddle) |
| [json-canvas](#json-canvas) | 生成和编辑 Obsidian Canvas 画布文件（来源：kepano） | [查看](#json-canvas) |
| [obsidian-bases](#obsidian-bases) | 创建编辑 Obsidian Bases 数据库视图（来源：kepano） | [查看](#obsidian-bases) |
| [obsidian-markdown](#obsidian-markdown) | Obsidian 专有 Markdown 语法规范（来源：kepano） | [查看](#obsidian-markdown) |
| [quiz](#quiz) | 根据已读资料生成测验题（来源：Readwise） | [查看](#quiz) |
| [xiaohongshu-images](#xiaohongshu-images) | 生成 3:4 小红书配图（来源：iamzifei） | [查看](#xiaohongshu-images) |
| [xiaohongshu-note-analyzer](#xiaohongshu-note-analyzer) | 小红书笔记发布前审核与优化（来源：softbread） | [查看](#xiaohongshu-note-analyzer) |
| [find-skills](#find-skills) | 搜索并安装 Agent Skills，安装规则已按个人要求修改（来源：vercel-labs） | [查看](#find-skills) |

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

> 提示：少数 skill 依赖同仓库的兄弟 skill（例如 structured-post、zhankai 依赖 human-writing，ima-skill 供多个 skill 调用），建议一起安装到同一个 skills 根目录。

> 提示：huashu-design 体积较大（约 30MB，含动画模板、音效与案例资源），请整目录复制，不要只拷 SKILL.md。

## Skill 详解

### 🧑‍💻 原创自研

#### gongkao

公考面试结构化讲义全产品工具。覆盖题目生成、方法论提炼、框架模板、过渡句库、素材库、讲义组装 6 个工作流，支持从单题生成到完整讲义产品的全生命周期。每道题含 frontmatter 元信息、题干、思路大纲和 800-1000 字逐字稿，并经 Python 多模式验证（字数 + AI 痕迹 + 用语禁忌 + 结构完整性）后写入对应目录。

触发词：面试题库、出面试题、公考面试题、批量出题、题库填充、面试逐字稿、生成方法论、生成框架、生成过渡句、生成素材、组装讲义、更新讲义、导出讲义。

#### ima-skill

统一的 IMA OpenAPI 技能，支持笔记管理和知识库操作：搜索/浏览/创建/追加笔记，上传文件、添加网页到知识库、知识库内容搜索与原文获取。需要自行配置 IMA OpenAPI 凭证（`IMA_OPENAPI_CLIENTID` / `IMA_OPENAPI_APIKEY` 或 `~/.config/ima/`）。

触发词：知识库、笔记、备忘录、帮我记一下、上传文件到知识库、搜一下知识库里有没有 XX。

#### pe-lecture

教师编体育笔试"举一反三"讲稿的成体系生成与反例沉淀。基于招教体育讲义库，按 8 节结构 + 引用/口诀/双链硬约束批量产出讲稿；内置 R1-R20 实战反例（拆分为独立 references/核心反例_R1-R20.md）、六维度横评机制（全库审核打分）、双视角授课提示与 v2 修订说明模板，md→Word 采用通用提示词（v3.8 替代旧合并脚本，v3.9 新增代码思维导图/时间线转图提示词）。另有讲义库完整 SOP v3.4 与版本记录/专项经验两个维护型 reference。

> 注意：本 skill 涉及大量业务工作区路径，文档中统一使用 `<项目根>`、`<用户目录>`、`<临时目录>`、`<Python 环境>` 占位符，使用前请替换为实际路径。

#### pe-trial

生成体育试讲稿教学产物（教学设计/试讲稿/队形图/自检表），含初始化、子技术识别、并行生产、六维度横评、问题修复、备考讲义生成全流程，支持基于教材批量开发新运动项目。

> 注意：`generate_lecture.py` 顶部的 `BASE_DIR` / `OUTPUT_PATH` 使用 `<项目根>` 占位符，运行前请替换为实际路径。

#### structured-post

自动化生成"结构化每日一练"小红书/公众号帖子 docx。基于固定 docx 模板 + python-docx 脚本，自动替换题目文本框、正文段落、分页符并保留配图/引流段样式，答题须经 human-writing 去 AI 味儿（v1.3.2：新增 Pre-flight 三项检查、分题型高分要素、用语禁忌与 IMA 笔记上传）。

触发词：答一道、出题、做一篇结构化帖子、每日一练。

#### tiyu-bishi-meiri

自动化生成「每天一个体育笔试知识点」小红书帖子 docx。基于「体育笔试每日一练」固定模板 + python-docx 脚本，从「讲义库举一反三讲稿」（128 篇）中按模块顺序选题，自动套版式：封面大标题 + 单选题引出知识点，中间 2 页考点解析（图表优先，表格自适应列宽），最后一页考法提醒 + 话题标签 + 引流段，答题须经 human-writing 去 AI 味儿。内置选题进度追踪、快照回滚与全字段校验。

触发词：每天一个体育笔试知识点、体育笔试每日一练、出一期体育笔试知识点。

> 注意：本 skill 涉及大量业务工作区路径，文档中为本机绝对路径，使用前请替换为实际路径。

#### zhankai

自动化生成"考官想听的·展开说说"系列小红书长帖 docx。站在公务员结构化面试考官视角剖析答题思路，按小红书节奏打磨（标题钩子/短句/emoji/互动钩子/话题标签），基于固定 docx 模板（48 段 + 1 表格）自动替换内容。

触发词：展开说说、做一篇考官想听的、出一期长帖、跑第 N 期。

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

**其他社区精选**

#### dashi-ppt

基于预置视觉主题生成可离线打开、可在浏览器编辑的 HTML 演示，支持导出 PPTX / PDF。使用前先把需求整理成 JSON 计划，再调用内置生成器产出 `index.html` 和 `assets/`。触发词：做 PPT、演示文稿、幻灯片、汇报材料。

> 注意：需要 Node.js 20+ 和 npm，首次生成时会在 skill 内置 `project/` 目录安装依赖；上游采用 AGPL-3.0 许可。

> 来源：[chuspeeism/dashi-ppt-skill](https://github.com/chuspeeism/dashi-ppt-skill)（作者 chuspeeism）

> 同步：上游更新后可运行 `bash scripts/sync-dashi.sh` 一键拉取最新版（见下方「同步 dashi-ppt 来源 skill」）。

#### docx

专业 Word 文档创建/编辑/分析，支持修订记录、批注、格式保留和文本提取，适用于新建、修改、审阅等文档任务。（来源：appautomaton）

#### defuddle

网页转干净 Markdown：用 Defuddle CLI 提取正文、去除导航和杂讯以节省 token；以 `.md` 结尾的 URL 直接读取原文即可。（来源：kepano）

#### json-canvas

创建和编辑 JSON Canvas（`.canvas`）文件：节点、连线、分组和连接关系，适合 Obsidian 画布、思维导图、流程图。（来源：kepano）

#### obsidian-bases

创建和编辑 Obsidian Bases（`.base`）文件：视图、筛选、公式、汇总，把笔记变成数据库式表格视图。（来源：kepano）

#### obsidian-markdown

Obsidian 专有 Markdown 语法规范：wikilink、嵌入、callout、properties、标签等 Obsidian 特定写法。（来源：kepano）

#### quiz

根据最近读过的资料生成测验题，检验理解和记忆效果。（来源：Readwise）

#### xiaohongshu-images

把 Markdown/HTML 内容转成 3:4 比例的小红书配图。（来源：iamzifei）

#### xiaohongshu-note-analyzer

小红书笔记发布前审核与优化：内容质量、关键词优化、标题吸引力、敏感内容风险、商业化程度、互动潜力分析。（来源：softbread）

#### find-skills

搜索并安装 Agent Skills。本仓库版本已按个人要求修改安装规则：安装前确认目标 agent、默认装到当前对话所在 agent、禁止全局安装。（来源：vercel-labs）

## 同步 khazix 来源 skill

仓库里的 `neat-freak`、`storage-analyzer`、`leader` 收录自 [khazix-skills](https://github.com/KKKKhazix/khazix-skills)，`human-writing` 收录自其独立仓库 [KKKKhazix/human-writing](https://github.com/KKKKhazix/human-writing)。每个目录内都有 `ORIGIN.md` 注明出处。上游更新后，一条命令即可同步最新版：

```bash
bash scripts/sync-khazix.sh        # 只更新文件并打印变更
bash scripts/sync-khazix.sh --push # 更新并自动 commit + push
```

脚本会从 khazix-skills 拉取最新代码、覆盖对应 skill 目录，并自动保留/补回 `SKILL.md` 顶部的来源声明和 `ORIGIN.md`。若某个 skill 在上游已改名或删除，脚本会跳过并提示。

`gongkao`、`structured-post`、`zhankai` 三个 skill 的工作流依赖 human-writing，其规则引用一律以 human-writing 最新版为准（不锁版本号）。human-writing 更新后运行同步脚本，脚本会自动校验这三个 skill 的引用与硬禁令要点（冒号/破折号/翻案腔）是否齐全，缺失会明确提示。

## 同步花叔来源 skill

仓库里的 `darwin-skill`、`huashu-design` 收录自花叔（alchaincyf）的两个独立仓库。每个目录内都有 `ORIGIN.md` 注明出处。上游更新后，一条命令即可同步最新版：

```bash
bash scripts/sync-huashu.sh        # 只更新文件并打印变更
bash scripts/sync-huashu.sh --push # 更新并自动 commit + push
```

脚本会从上游仓库拉取最新代码、覆盖对应 skill 目录，并自动保留/补回 `SKILL.md` 顶部的来源声明和 `ORIGIN.md`。若某个 skill 在上游已改名或删除，脚本会跳过并提示。注意 huashu-design 包含约 30MB 设计资源（动画模板、音效、案例图），同步时会整体覆盖。

## 同步 dashi-ppt 来源 skill

仓库里的 `dashi-ppt` 收录自 [chuspeeism/dashi-ppt-skill](https://github.com/chuspeeism/dashi-ppt-skill)。目录内含 `ORIGIN.md` 出处声明与上游 `LICENSE`（AGPL-3.0）。上游更新后，一条命令即可同步最新版：

```bash
bash scripts/sync-dashi.sh        # 只更新文件并打印变更
bash scripts/sync-dashi.sh --push # 更新并自动 commit + push
```

脚本会从上游仓库拉取最新代码、覆盖 skill 目录（并保留 LICENSE），自动补回 `SKILL.md` 顶部的来源声明和 `ORIGIN.md`。若上游目录已改名或删除，脚本会跳过并提示。

## 许可

本仓库为个人作品，供学习交流使用。部分 skill 内容涉及具体业务场景与个人工作流，请按需修改后使用。

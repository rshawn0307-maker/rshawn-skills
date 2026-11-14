# 字体策略：首次检测一次 · 装入字体记忆 · 装上或用你指定的 · 禁止替身

> **这一份是「出厂层」，只读。** 它随 skill 版本发布，你改了下次更新就没了。
> 你自己查到的字体授权信息、踩过的排字坑，记到**用户数据目录**里那份：
> 跑 `python3 scripts/user_data.py --path fonts.md` 拿到路径。
> 字体记忆（哪些字体装没装）不在这个文件里，它是缓存，存在 `~/.cache/doc-format/font-memory.json`。

排版规格里写了一个本机没有的字体，是这个流程最隐蔽的坑：Markdown 看着没问题，生成的产物里却是方框、默认字体或另一种字形。

## 铁律（四条）

1. **字体清单只在首次使用时全盘检测一次，之后一律读字体记忆，不要每次任务都自检。**
   记忆文件：`~/.cache/doc-format/font-memory.json`（中文字体、全部字体、检测日期）。
   它固定放在这台机器的用户缓存目录，**不随 `DOC_FORMAT_HOME` 搬家** —— 「装没装字体」是这台机器的属性，
   跟用户数据放在哪个目录无关，换数据目录不该让它重扫一遍全盘。
   换一台电脑要重新首次检测 —— 不同平台字体环境完全不同：Windows 有仿宋_GB2312 却没有苹方；
   macOS 有宋体-简却没有仿宋；Linux 可能两者都没有但装了思源。
   本文档里出现的任何字体名，都只是**示例**，不是结论。

   用户中途装上了新字体，**不要重扫全盘**，用 `font_check.py --remember <字体名>` 记一笔即可。
   只有用户明确要求、或怀疑记忆坏了，才用 `--refresh`。

   为什么这样定：全盘扫描要 1 秒以上，而 `spec_check` / `build_docx` / `verify_output`
   是三个独立进程，各扫一遍就是白烧；旧设计还用「字体目录 mtime」判缓存失效，
   用户装一个字体就必然触发重扫。

2. **禁止替身。脚本永远不会自动挑一个「差不多的」字体顶上去。**
   曾经的做法是按 macOS / Windows / Linux 分别准备候选表，缺字体时自动挑第一个本机可用的。
   这个做法已经废除，原因是实测事故：LibreOffice 静默把中文替换成
   `LinuxLibertine` / `DejaVuSans` / `FrankRuhlHofshi`，文件能打开、文本能提取，
   但字全错了，而且没有任何提示。**自动替换等于把错误藏起来。**

3. **缺字体只有两条路，都由用户拍板：**
   - **A. 装上它。** 先查这个字体能不能免费、合法地拿到；能就给出官方地址，装完重跑检测。
   - **B. 换成本机已有的。** 由用户从本机实际装了的字体里**亲自指定一个**，
     写进规格卡对应槽位的 `resolved` 字段。脚本只提供候选清单，不替用户选。
   两条都不选，就**中止生成**（`build_docx.py` / `convert_docx.py` 返回退出码 4），
   不产出半成品。

4. **用户指定的替代必须留下痕迹。** `resolved` 写在规格卡里，生成报告里也要出现
   「X 槽位用 Y 代替标准要求的 Z」，不能只在对话里说一句就算数。

---

## 一、首次使用时检测一次（多后端取并集），之后读记忆

```bash
python3 scripts/font_check.py --list                 # 列出本机中文字体 + 用了哪些检测后端（走记忆）
python3 scripts/font_check.py --has "仿宋_GB2312"     # 只问某个字体在不在
python3 scripts/font_check.py --remember 仿宋_GB2312  # 用户刚装好：记一笔，以后不再为它检测
python3 scripts/font_check.py --refresh              # 重新全盘检测（少用）
python3 scripts/font_check.py --guide 仿宋_GB2312     # 问这个字体能不能免费拿到
```

### 为什么要多后端

单一后端一定会漏字体，这是实测结论，不是推测：

| 后端 | 覆盖范围 | 已知盲区 |
|---|---|---|
| `fc-list :lang=zh`（fontconfig） | Linux 标配；macOS 需 Homebrew 安装 | macOS 上**看不到** `/System/Library/AssetsV2` 里的字体资产包 |
| 字体目录扫描 + `fontTools` | 跨平台通用，能读字体内部 name 表 | 速度较慢（约 4-8 秒）；依赖 `fontTools` |
| Windows 注册表 | Windows 上最权威 | 只能拿到字体名，判断不了是否覆盖中文 |
| `system_profiler -json SPFontsDataType` | macOS 系统报告 | 极慢（20 秒以上），且会把西文字体一并列出 |

实测例证（同一台 macOS）：`fc-list` 报出 136 个族，目录扫描报出 293 个族，两者并集 350 个。
只用 `fc-list` 会漏掉一批；只用目录扫描又会漏掉 fontconfig 索引到的另一批。**所以取并集。**

### 检测后端的启用策略

- **第一档（常跑）**：`fc-list`、字体目录扫描。两者都跑，结果取并集。
- **第二档（兜底）**：Windows 注册表、`system_profiler`。**只有当第一档一无所获时才跑**，因为它们慢且会把非中文字体也列出来，污染「中文字体清单」。
- 检测结果在同一个进程内缓存；`font_check.py --list` 末尾会打印每个后端的状态，报告里要能看出检测是否可信。

### 检测的判定标准

「是不是中文字体」的判定方式：用 `fontTools` 读字体的 `cmap` 表，看它**能不能映射出「中」字（U+4E2D）**。
这比看字体名可靠得多 —— 名字里带 Song/Hei 的不一定是中文字体，名字是纯英文的（如 `PingFang SC`）反而是标准中文字体。

没有 `fontTools` 时退回文件名关键词粗判，并**在报告里标注这是粗判结果**。

### 平台差异提醒

| 平台 | 注意点 |
|---|---|
| macOS | 苹方、楷体、兰亭黑在 `/System/Library/AssetsV2/*Font*` 里，普通字体目录扫不到；系统目录字体需要递归 3 层 |
| Windows | 字体在 `%WINDIR%\Fonts` 与 `%LOCALAPPDATA%\Microsoft\Windows\Fonts`；没有 `fc-list` |
| Linux | `fc-list` 最可靠；`~/.fonts` 与 `~/.local/share/fonts` 是用户字体位置 |
| 云端 / 容器 | 可能一个中文字体都没有，此时**必须**走「获取」而非「替换」 |

---

## 二、字体缺失时的处置顺序（决策树）

对每一个「标准要求但本机没有」的字体，逐级往下走，**不要跳级**：

```
① 这个字体能不能免费、合法地拿到？
   ├─ 能 → 给出官方下载地址 + 安装方法 → 问用户是否安装
   │        └─ 用户同意 → 安装 → 重新跑 font_check.py 复查 → 进入严格档
   │        └─ 用户拒绝 → 进入 ②
   └─ 不能（商业字体、随系统分发、无免费渠道）→ 进入 ②
② 让用户从「本机已有的字体」里指定一个替代
   ├─ 跑 `font_check.py --suggest <字体名>` 拿到同类候选清单（脚本只给清单，不替用户选）
   ├─ 用户也可以从 `font_check.py --list` 的全部中文字体里挑任意一个
   ├─ 免费开源的思源宋体 / 思源黑体 / 霞鹜文楷 / 朱雀仿宋属于路径 A：下载安装，而不是「替代」
   └─ 用户也可以选择自行购买并安装商业字体，同样属于路径 A
③ 把用户选定的字体写进规格卡对应槽位的 resolved 字段（「X 替代 Y」），生成后在报告里复核
```

**向用户提问时的话术模板：**

```
你的电脑上没有「仿宋_GB2312」（GB/T 9704-2012 规定的公文正文字体）。
我先查了获取渠道：

  这个字体没有官方免费下载渠道。它随中文版 Windows/Office 分发，属于商业字体，
  对外分发文件时嵌入它存在授权风险。

所以只有两条路，你选一条：

  A. 装上字体 —— 二选一：
       ① 买正版授权装「仿宋_GB2312」本身（送审最稳妥，字体名与标准完全一致）；
       ② 装「朱雀仿宋」或「思源宋体」（SIL OFL 开源协议，免费商用），
          装好后把规格卡里的正文字体改成它——这是你自己选的，不是我替你换的。
  B. 改用本机已有的 —— 你的电脑上有「华文仿宋 STFangsong」，字形接近。
     同意的话我把它写进规格卡的 resolved 字段，报告里会写明「用 STFangsong 代替仿宋_GB2312」。

我不会替你选，也不会自动挑一个「差不多的」字体顶上。
```

**安装字体后的复查是强制动作。** 装完必须重新跑 `font_check.py --has "<字体名>"` 确认真的被系统识别（macOS 上双击安装偶尔会装到用户目录而部分程序读不到）。

### 安装方法速查

| 平台 | 安装方式 |
|---|---|
| macOS | 双击字体文件 → 「安装字体」；或把文件复制到 `~/Library/Fonts/`（当前用户）或 `/Library/Fonts/`（全机器） |
| Windows | 右键字体文件 → 「为所有用户安装」；或复制到 `%WINDIR%\Fonts` |
| Linux | 复制到 `~/.local/share/fonts/` 后执行 `fc-cache -f -v` |

---

## 三、字体获取与授权清单

**核验日期：2026-09-17。** 下表每个字体的 `free_download` 与 `license` 字段都有明确出处，程序化数据在 `scripts/spec_lib.py` 的 `FONT_ACQUISITION` 表里，两边必须一致。

**时效声明：字体厂商的授权政策与下载地址会变。距核验日期超过 6 个月，或用户对下表提出异议时，必须先联网复核再引用（复核方法见第四节）。**

### 3.1 开源可商用（可以免费下载，优先推荐）

| 字体 | 授权 | 官方下载 | 适用场景 |
|---|---|---|---|
| 思源宋体 Source Han Serif SC | SIL OFL 1.1 | https://github.com/adobe-fonts/source-han-serif/releases | 正文宋体、公文标题近似替代 |
| 思源黑体 Source Han Sans SC | SIL OFL 1.1 | https://github.com/adobe-fonts/source-han-sans/releases | 标题黑体 |
| Noto Serif SC / Noto Sans SC | SIL OFL 1.1 | https://fonts.google.com/noto | 与思源同源，Google 发行版 |
| 霞鹜文楷 LXGW WenKai | SIL OFL 1.1 | https://github.com/lxgw/LxgwWenKai/releases | 楷体替代，适合正文与引文 |
| 朱雀仿宋 Zhuque Fangsong | SIL OFL 1.1 | https://github.com/TrionesType/zhuque | **仿宋替代**，公文场景少见的免费合规选项 |

**核验渠道**：`adobe-fonts/source-han-serif`、`adobe-fonts/source-han-sans` 仓库内 `LICENSE.txt` 原文（curl 直取）；`lxgw/LxgwWenKai`、`TrionesType/zhuque` 通过 GitHub API 的 license 字段读取，均返回 `OFL-1.1`。

**注意体积**：思源系列单字重约 20-30MB，霞鹜文楷 Regular 约 24MB。建议只装 Regular + Bold 两档，不要整包安装。

### 3.2 商业字体（无官方免费下载）

| 字体 | 归属与授权 | 免费渠道 | 替代建议 |
|---|---|---|---|
| 仿宋_GB2312 | 商业字体，随中文版 Windows/Office 分发 | **无** | 开源：朱雀仿宋 / 思源宋体；兼容：华文仿宋 STFangsong |
| 楷体_GB2312 | 商业字体，随中文版 Windows/Office 分发 | **无** | 开源：霞鹜文楷；兼容：Kaiti SC（楷体-简） |
| 方正小标宋简体 | 方正字库商业字体，需购买授权 | **无** | 开源：思源宋体加粗；兼容：宋体加粗 |
| 宋体 SimSun | 商业字体，随中文版 Windows 分发 | **无** | 开源：思源宋体；兼容：Songti SC（宋体-简，macOS 自带） |
| 黑体 SimHei | 商业字体，随中文版 Windows 分发 | **无** | 开源：思源黑体；兼容：Heiti SC（黑体-简） |
| 微软雅黑 Microsoft YaHei | 归微软所有，随 Windows 分发，不得单独提取 | **无** | 开源：思源黑体；兼容：PingFang SC（苹方） |
| Times New Roman | Monotype 商业字体，随 Windows/macOS/Office 分发 | **无** | 开源：Noto Serif / 思源宋体的西文字形 |

**核验渠道**：这些字体均无官方独立下载页；授权归属以各字体厂商官网公示为准。方正字库官网 `foundertype.com` 的授权模式页本次**未能取到正文**，涉及方正的条款请在使用前自行到官网复核。

**待复核项（下次维护时优先处理）：**

- 方正字库曾公布过若干「免费商用」基础字体（坊间常提到方正黑体、方正书宋、方正仿宋、方正楷体四款）。本次核验**未能从官网页面直接确认**该清单的现行内容与适用条件，因此**不写入本表**。如用户提出需求，请联网复核官网授权说明后再回答。
- 各字体厂商的授权条款措辞会调整，引用前以官网原文为准。

### 3.3 合规提醒

- **不要把「系统自带」等同于「可以随意分发」。** 随 Windows 分发的字体（仿宋_GB2312、宋体、微软雅黑等）在本机使用通常没问题，但把字体文件本身提取出来分发、或在对外发布且嵌入字体的 PDF 中使用，可能触及授权边界。
- **需要对外分发的文件，优先改用开源字体（装上去，而不是「替代」）。** 思源系列、霞鹜文楷、朱雀仿宋都明确允许嵌入与再分发。
- 本 skill 不提供法律意见。涉及正式对外发布、商业用途、法律风险时，提示用户以字体厂商授权条款为准。

---

## 四、怎么自己复核第三节

距核验日期超过 6 个月，或用户质疑表格内容时，按下面方式重新核验，并把新的日期与渠道写回本文件与 `FONT_ACQUISITION` 表：

```bash
# 开源字体：直接读官方仓库的 LICENSE 原文（最权威，不受搜索结果干扰）
curl -s -L https://raw.githubusercontent.com/adobe-fonts/source-han-serif/release/LICENSE.txt | head -10
curl -s -L https://raw.githubusercontent.com/adobe-fonts/source-han-sans/release/LICENSE.txt   | head -10

# 用 GitHub API 查任意开源字体仓库的授权标识
curl -s https://api.github.com/repos/lxgw/LxgwWenKai/license | grep -o '"spdx_id": *"[^"]*"'

# 开源字体的最新版与体积（判断下载成本）
curl -s https://api.github.com/repos/lxgw/LxgwWenKai/releases/latest | grep -E '"name"|"size"'

# 商业字体：到厂商官网授权页核对（搜索引擎结果不可作为唯一依据）
#   方正字库   https://www.foundertype.com/
```

**核验纪律：**

- 搜索摘要、博客、论坛帖子**不算出处**。必须落到官方页面或官方仓库原文。
- 查不到就写「未能核实」，不要写一个看起来很合理的数字糊过去。
- 核验完必须更新 `verified_at` 与 `source` 两个字段，否则下次没人知道这条信息有多旧。

---

## 五、缺字体时的两条路（没有第三档）

以前这里写的是「严格档 / 兼容档 / 开源档」三档，其中兼容档会自动挑一个近似的字体顶上。
**这个做法已经废除**，原因见铁律第 2 条。现在只有两条路，都由用户拍板。

### 路径 A：装上字体

按标准原文指定字体名（如 `仿宋_GB2312`、`方正小标宋简体`），先查能不能免费、合法地拿到：

- 能免费拿到 → 给出官方下载地址与安装方法，用户装完重跑检测，然后把字体名原样写进规格卡。
- 拿不到（商业字体）→ 说明授权情况，请用户自行购买安装，或改走路径 B。
- 也可以改用开源字体（思源宋体 / 思源黑体 / 霞鹜文楷 / 朱雀仿宋，均为 SIL OFL 1.1）：
  这属于「换一个要求的字体」，是用户的决定，不是替身。

- 优点：打印出来与标准一致，送审不会因为字体被打回。
- 代价：需要用户自行安装并解决授权。
- 适用：正式公文送审、需要盖章归档的场合。

### 路径 B：改用本机已有的字体

用户从**本机实际装了的字体**里亲自指定一个，写进规格卡对应槽位的 `resolved` 字段。

```yaml
fonts:
  body:
    east_asian: 仿宋_GB2312      # 标准要求的字体
    resolved: STFangsong        # 用户指定用它代替；不写就必须装上仿宋_GB2312
```

`scripts/spec_lib.py` 的 `FALLBACK_CANDIDATES` 与 `OPEN_SOURCE_CANDIDATES`
**现在只是建议清单的数据源**（供 `font_check.py --suggest` 用），不参与任何自动决策。

- 优点：零额外操作，本机立刻可用。
- 代价：与标准原字体有细微差异，严格送审可能被挑。
- 适用：日常场景，且用户明确接受这个差异。

### 供参考的对应关系（仅作建议，不是自动映射）

| 标准要求 | macOS 上常见的同类字体 | Windows 上常见的同类字体 | 说明 |
|---|---|---|---|
| 仿宋_GB2312 | STFangsong（华文仿宋） | FangSong（仿宋） | 字形最接近 |
| 方正小标宋简体 | Songti SC 加粗 | SimSun 加粗 | 接近小标宋的庄重感 |
| 宋体（SimSun） | Songti SC | SimSun | 同类衬线宋体 |
| 黑体（SimHei） | Heiti SC | SimHei | 同类无衬线黑体 |
| 楷体（KaiTi） | Kaiti SC | KaiTi | 同类楷体 |
| 微软雅黑（Microsoft YaHei） | PingFang SC | Microsoft YaHei | 同为无衬线 |

**用哪一个是用户的选择，不是脚本的推论。** 表中列出的字体只是「本机有的话可以作为候选」，
脚本会用 `font_check.py --suggest` 把本机真实存在的候选列给用户看。

## 六、中英文混排的字体搭配

中文排版的一个常见疏漏：**只设了中文字体，英文和数字跟着用中文字体渲染**，结果是难看的西文。正确做法是中西文分别指定：

| 场景 | 中文 | 西文与数字 |
|---|---|---|
| 图书正文 | 宋体 | Times New Roman |
| 学术论文 | 宋体 | Times New Roman |
| 公文 | 仿宋 | Times New Roman |
| 现代风格 | 思源宋体 | Source Serif / Georgia |
| 屏幕、公众号 | 系统默认 | 系统默认 |

DOCX 中通过 `w:rFonts` 的 `w:ascii` 与 `w:eastAsia` 分别指定；公众号侧通过 CSS `font-family` 的回退链实现。

**西文字体同样要检测。** 上面的多后端检测只覆盖中文字体；西文字体缺失时（如 Linux 容器里没有 Times New Roman），应在报告里提示并建议改用 `Noto Serif` 等等价字体。

---

## 七、致命陷阱：LibreOffice 的字体（两个实测出来的坑）

**这一节的两个结论都是复现过的，改代码前先读完。**

### 坑一：字体必须装进 `fonts/truetype/`，装到上一级无效

本机 `soffice` 指向的是 `LibreOfficeDev.app`（headless 版），它**不使用 macOS 的 CoreText 系统字体**，
只读取自己包内的这个目录：

```
<LibreOfficeDev.app>/Contents/Resources/fonts/truetype/
```

**注意是 `truetype` 子目录。** 把字体复制到它的上一级 `fonts/` 是完全无效的 ——
实测：`Times New Roman.ttf` 放进 `fonts/` 后转换，PDF 里仍然是 `LiberationSerif`；
放进 `fonts/truetype/` 后立刻变成 `TimesNewRomanPSMT`。

旧版 `build_pdf.py` 正好复制错了地方，而且它的「是否已安装中文字体」用的是**递归**检测，
会把上一级那份无效副本当成已安装 —— 于是这一步一直没生效，还不报错。
现在改为 `lo_font_install_dir()`（定位真实的 `truetype/`）+ 只查该目录的 `has_cjk_font()`。

`build_pdf.py --spec <规格卡>` 会做两件事：

1. 把保底中文字体装进去（没有它，中文会整片渲染成空白）；
2. 把**规格卡点名要用的每一个字体**（中西文都算）找出来装进去。

第 2 步里找不到文件的字体会被列出来并**中止生成**（退出码 4），
因为 LibreOffice 一定会拿别的字体顶替它们，生成出来的 PDF 与规格不符。

### 坑二：DOCX 里的「主题字体」会压掉显式字体

Word 内置样式（`Heading 1` 等）默认引用主题字体，`w:rFonts` 上会同时出现：

```xml
<w:rFonts w:eastAsiaTheme="majorEastAsia" w:eastAsia="黑体" ... />
```

按 OOXML 规则，**`w:eastAsiaTheme` 的优先级高于 `w:eastAsia`**，
所以我们写进去的显式字体名会被无视，渲染时用的是主题字体。

实测证据：同一份 DOCX，保留主题属性时 PDF 里的标题中文字体是被顶替的宋体；
删掉主题属性后立刻变成 `STHeitiSC-Medium`，即规格要求的「黑体」。

`build_docx.py` 的 `clear_theme_fonts()` 负责在写入显式字体后删掉这四个属性
（`asciiTheme`、`hAnsiTheme`、`eastAsiaTheme`、`cstheme`）。

### 校验方式

`verify_output.py` 现在会**按规格逐个核对 PDF 里实际用的字体**：

- 正文的中文与西文字体必须命中，否则判失败，并打印 PDF 里真实的字体清单
  （`LinuxLibertine` / `DejaVuSans` / `FrankRuhlHofshi` 这些就是替换的痕迹）；
- 标题、红头、页码等槽位未命中记为「需确认」—— 那一级可能根本没用到，也可能被替换了。

字体名比对收在 `spec_lib.font_name_matches()`：先剥掉 PDF 的子集前缀（`HQMZNO+`）
与样式后缀，再归一化比较，所以「Songti SC」能匹配上「STSongti-SC-Regular」。

**但最终确认仍要肉眼看一眼渲染图** —— 用 `scripts/render_preview.py` 把 PDF 渲染成 PNG。

## 八、PDF 必须内嵌字体

不内嵌字体的 PDF，在没装该字体的电脑上会被替换成别的字体，或者干脆显示成方框。校验环节 `verify_output.py` 会检查这一点。

| 情形 | 结果 |
|---|---|
| 字体已内嵌且子集化 | 理想状态 |
| 字体已内嵌但未子集化 | 可用，但文件体积偏大 |
| 字体未内嵌 | 不合格，必须重新生成 |

---

## 附录：一次实际检测输出示例（仅作格式示例，不是任何机器的结论）

2026-09-17 在一台 macOS 上跑 `font_check.py --list` 的结果摘录：

```
操作系统：macos
检测后端：
  - fc-list：已用（136 个族）
  - 字体文件扫描：已用（扫描 721 个字体文件，293 个族）
  - 兜底后端：未启用（第一档已检测到字体）

本机中文字体共 350 个： 苹方-简 / 宋体-简 / 黑体-简 / 楷体-简 / 华文仿宋 / 冬青黑体简体中文 / ...
```

**读这份示例时要注意：** 它只能说明「格式长这样」。你要用的是**在用户机器上现场跑出来的结果**，不是这份示例。

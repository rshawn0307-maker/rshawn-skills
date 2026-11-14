# 规格卡字段定义

规格卡是本 skill 的唯一交付前契约：**用户确认它，脚本读它，校验器对着它核对。**

人机双读结构：

- **中文说明层**：每条规格写清「是什么 + 数值 + 为什么 + 出处」。给人看。
- **YAML 参数层**：机器直接读。给脚本看。

两个现成起点：

- `assets/spec-template.yaml` —— 填空骨架，字段名齐全、取值位留空，适合从零自定义。

**`--spec` 接受三种入参**，别再去手工抽 YAML 段：

| 入参 | 例子 | 说明 |
|---|---|---|
| YAML 规格卡 | `--spec build/typography.spec.yaml` | 常规用法，整个文件就是 YAML |
| 预设文件路径 | `--spec ~/.local/share/doc-format/presets/我单位的报告格式.md` | 预设 `.md` 里的 ```yaml 代码块会被自动抽出来 |
| 预设标识 | `--spec book-cn`、`--spec 我单位的报告格式` | 自动在内置预设目录与用户预设目录两处查找 |
- `references/presets/gov-doc-cn.md` 里的 YAML 段 —— 完整可运行实例（公文 / docx+pdf），可直接通过 `spec_check`，适合照着改。

## 顶层结构

| 字段 | 必填 | 说明 |
|---|---|---|
| `meta` | 是 | 规格身份：预设名、来源类型、标准号、核验日期、目标载体 |
| `page` | 是 | 纸张与页面参数。左右边距可写「左/右」，双面书刊写「内侧/外侧」（`margin_inside_mm` / `margin_outside_mm`）；后者配合 `mirror_margins` 由偶数页自动互换 |

**`page` 里必写一项：纸张尺寸。** 两种写法，优先级从高到低：

| 写法 | 例子 | 说明 |
|---|---|---|
| 显式宽高 | `width_mm: 140` + `height_mm: 203` | 最精确，非标准开本（如大 32 开）走这条，`size` 可写 `custom` |
| 名称 | `size: A4` | 查表换算，可选 `A3` `A4` `A5` `B5` `16K` `32K` `Letter` `Legal`，也认「16开」「大32开」「A4纸」这类中文写法 |

另可写 `orientation: landscape` 让宽高互换（横排页面）。

**两项都没写会退回 A4 并打印警告**；写了不认识的名称（如 `B7`）同样报警告并退回 A4，
绝不会静默按 A4 出纸还不吭声 —— 幅面错了，版心、每行字数、边距比例会全部跟着错。
`spec_check.py` 会在体检时报这条警告，`verify_output.py` 会拿成品里的实际幅面与规格对账。
| `fonts` | 是 | 字体与三档策略 |
| `paragraph` | 是 | 正文段落格式 |
| `headings` | 是 | 标题层级体系 |
| `figures_tables` | 视情况 | 图表规范（有图表时必填） |
| `footer` / `header` | 视情况 | 页码与页眉页脚 |
| `references` | 视情况 | 参考文献著录标准 |
| `masthead` | 公文专用 | 版头（红头、发文字号、分隔线） |
| `body_elements` | 公文专用 | 主体要素（主送机关、附件说明、发文机关署名、成文日期）的位置，见下文 |
| `record_section` | 公文专用 | 版记 |
| `binding` | 视情况 | 装订要求 |
| `html` | 公众号专用 | 内联样式参数 |
| `excluded` | 视情况 | 因载体限制被跳过的项，登记下来供交付说明用。**当前没有脚本读它**，合规报告里的跳过项是校验时按产物实测得出的，不是从这里读的 |
| `screen` | 公众号专用 | 屏幕阅读参数（`body` / `quote` / `image` 三段，单位是 px 与 em，不是 pt） |

## 只给人看、脚本不读的字段

规格卡里有一批字段是**记录与说明性质**：它们写清了当时的判断和来源，但生成脚本不读，
写什么都不改变输出。**留着它们是为了让规格卡能自解释**，不是为了当开关用。
把它们跟真正生效的字段混在一起，会让人以为「改了就有用」—— 这个 skill 已经栽过好几次。

| 字段 | 为什么留 |
|---|---|
| `size_label`（字号的中文号数） | `size_pt` 才是脚本读的；号数写给人看，方便对照「三号 = 16pt」 |
| `meta.*`（`verified_at` / `recheck_after` / `standard_note` / `verified_at_note`） | 时效与出处记录，`spec_check.py` 只读 `verified_at` / `recheck_after` 做超期判断，其余供人看 |
| `excluded` | 因载体限制跳过的项，登记下来写进交付说明；合规报告里的跳过项是校验端按产物实测的，不从这儿读 |
| `saved_from` | 这份规格从哪来（内置预设 / 自定义问询 / 从现有文件反推） |
| `lines_per_page` / `chars_per_line` | 国标算出来的结果值（22 行 × 28 字），供人核对，不参与排版计算 |
| `binding.staple_offset_from_edge_mm` / `flat_staple_to_spine_mm` | 钉位与平订距书脊，交给印装环节的说明，对文件本身无影响 |
| `meta.recheck_rule` | 复查规则（「用户改个别参数直接改，标准换版才复检」），写给人和下一个 agent 看的 |
| `masthead.space_before_anchor` | 说明「这段空行从哪儿起算」，供人读懂上方那个数值 |
| `screen`/`html` 里的 `emphasis.method`、`chinese_latin_spacing.mode` | 记录「为什么不用下划线 / 为什么手工加空格」这类决定；中英空格实际由 `md_normalize.py` 在源文件阶段补 |

**下面这几个不是「给人看」，是「当前没实现」，用之前必须知道：**

| 字段 | 当前状态 |
|---|---|
| `meta.school_template` / `meta.journal_template` | 学校 / 期刊模板路径。**当前没有脚本读它**，填了不会按模板排。拿到学校模板时要人工对照改预设里的数值 |
| `figures_tables.numbering_scheme` | 图表编号样式（`图1_表1` 之类）。**当前不读**，图表编号按源稿里的文字原样排 |
| `references.*`（含 `standard` / `fallback_standard` / `note`） | 参考文献著录标准。**当前不读**，参考文献按源稿里的文字原样排，脚本不做著录格式转换 |
| `masthead.security_level` / `urgency` / `copy_number` / `joint_issuance` | 公文的份号、密级和保密期限、紧急程度、联合行文。**当前既不问也不排**，预设里留着空位只表示「国标有这几项」 |

## 关键字段约定

### `meta.source_type`

只有三种合法值，决定这条规格是否需要标出处：

| 值 | 含义 | 要求 |
|---|---|---|
| `国标` | 有国家标准号 | 必须填 `standard`，且该标准必须能在标准核验记录里找到（出厂那份或用户数据目录里那份，两层都算） |
| `惯例` | 出版社或行业通行做法 | `standard` 必须为 `null`，不得编造标准号 |
| `平台` | 特定平台技术约束 | `standard` 为 `null` |

### 字号表达：`size_pt` 必须配 `size_label`

中国用户习惯用号数（「五号」「小三」），但脚本需要磅值。两个字段都写：

```yaml
size_pt: 10.5        # 脚本读这个
size_label: 五号      # 给人看这个
```

号数与磅值的对照表见 `references/standards.md` 第三节。

### 行距：`line_spacing_mode`

| 值 | 含义 | 中文排版建议 |
|---|---|---|
| `exact` | 固定值，单位磅 | **中文正文首选**。中文字面大，固定值比倍数更好控 |
| `multiple` | 倍数 | 学位论文、商务报告常用 |

固定值转 DOCX 的参数要乘 20（Word 的 `w:line` 用二十分之一磅）：

```
w:line = line_spacing_pt × 20
例：28pt → w:line="560" w:lineRule="exact"
```

字号转 DOCX 的 `w:sz` 要乘 2（半磅单位）：

```
w:sz = size_pt × 2
例：10.5pt → w:sz="21"
```

### 首行缩进：用字符数，不用长度

```yaml
first_line_indent_chars: 2
```

**永远不要写 `first_line_indent_cm`。** 中文排版的首行缩进是「两个汉字宽度」，随字号变化。用字符数才能自适应；用厘米会在换字号后失准。

DOCX 对应 `w:ind w:firstLineChars="200"`（200 表示 2 字符）；公众号侧按屏幕惯例改用段间距，不做首行缩进。

### 字体：三档策略

```yaml
fonts:
  body:
    east_asian: 仿宋_GB2312       # 标准要求的字体
    latin: Times New Roman      # 西文与数字单独指定
    resolved: <本机替代字体>      # 可选；仅当本机没有上面的字体、且用户明确同意改用时才填
```

**中西文字体必须分开指定。** 只设中文字体，会让英文和数字用中文字体渲染，观感很差。

**没有「自动替换档」。** 规格要求什么字体，就用什么字体；本机没有就中止生成，
由用户在两条路里选一条：装上该字体，或从本机已有的字体里指定一个，写进 `resolved`。

`FALLBACK_CANDIDATES` 与 `OPEN_SOURCE_CANDIDATES` 现在**只是建议清单的数据源**
（`font_check.py --suggest`），不再参与生成流程的任何决策。原因是一次实测：
LibreOffice 静默把中文替换成 LinuxLibertine / DejaVuSans / FrankRuhlHofshi，
文件能打开、文本能提取，但字全错了，而且没有任何提示。

`resolved` 只写在本机确实装了的字体上；换一台机器要重新确认一次（字体清单存在字体记忆里，不随规格卡走）。

### 代码块字体：`fonts.code`

```yaml
fonts:
  code:
    east_asian: 楷体
    latin: Courier New          # 等宽体；不写就沿用正文字体
    size_pt: 9                  # 不写则取正文的 95%
```

代码块**必须显式声明字体**，不能靠默认值。`build_docx.py` 早先把代码块字体写死成 `Consolas`，
而 macOS 上普遍没有这个字体，LibreOffice 就自己挑了 `LinuxLibertineG` —— 一种比例衬线体，
代码块里对好的列全部错位。规则与正文字体一致：规格写什么就用什么，本机没有就中止，不自动替换。

### 图表题注字体：`fonts.caption`

```yaml
fonts:
  caption:
    east_asian: 宋体            # 不填则整槽沿用正文字体
    latin: Times New Roman     # 不填则沿用正文
    size_pt: 9                 # 不填则用 figures_tables.caption_size_pt，再退回正文字号
```

图表题注（图片下方的图注、表格上/下方的表题）默认沿用正文字体，多数场景不用填这一槽。
期刊、论文、出版社要求「题注用更小的字号或另一种字体」时才需要显式声明。

两条约束：

- **字号判断顺序**：`figures_tables.caption_size_pt` 优先，其次本槽位的 `size_pt`，最后才退回正文字号。
- **替代字体不跨槽位借用**：只写了 `east_asian`（比如「黑体」）而没写 `resolved` 时，
  脚本不会拿正文的 `resolved`（比如「Songti SC」）来顶替 —— 那等于自动替身，是被禁止的；
  正确做法是把本槽位的 `resolved` 也写上，或先装上该字体。

另外：本槽位与页眉字体都已在 `spec_lib.collect_required_fonts()` 里登记，
**生成前**就会检查本机有没有这些字体，缺字体直接中止，不会生成到一半才由 LibreOffice 换字。

### 段落区分方式：`indent_mode`

```yaml
indent_mode: first_line    # 印刷稿：首行缩进，段间距 0
indent_mode: spacing       # 屏幕稿：无缩进，段间距 1em
```

**这是纸媒与屏媒最重要的分野。** 同一篇稿子出纸质版和公众号版，这一项必须不同。

### `excluded`：被跳过的项必须显式登记

```yaml
excluded:
  - item: 页边距
    reason: 公众号无页概念，只能设左右内边距，上下由平台控制
  - item: 页码
    reason: 公众号没有页的概念
  - item: 首行缩进
    reason: 屏幕阅读惯例改用段间距
```

这些登记是给人和交付说明看的：**当前没有脚本读 `excluded`**，它不会自动让生成脚本跳过什么，合规报告里的跳过项也是校验端按产物实测得出的。**真正的要求是：做不到就说破，不允许静默跳过。**

### `meta` 的时效字段

| 字段 | 说明 |
|---|---|
| `verified_at` | 该规格引用的标准/惯例的核验日期，格式 `YYYY-MM-DD` |
| `recheck_after` | 超过这个日期必须先联网复查再使用；通常取核验日期 + 1 年 |
| `saved_from` | 规格来源：`内置预设` \| `自定义问询` \| `从现有文件反推` |
| `standard` | `source_type` 为国标时必填，且必须能在标准核验记录里找到（两层都查：出厂与用户数据目录，同一条以用户那份为准） |

**规则：** 展示规格卡时，`verified_at` 与 `recheck_after` 必须一并告诉用户；超过 `recheck_after` 的规格卡不允许直接使用，要先跑 `check_standard_updates.py` 复查。

### 用户预设

用户自存预设放在用户自己的目录 `~/.local/share/doc-format/presets/`（**不在 skill 目录里**，
免得用户更新 skill 时把自己的预设一起换掉），文件名即预设标识，必须全局唯一
（重名会被 `save_preset.py` 拒绝并自动加序号）。

查找顺序是 **用户目录 → 旧位置 → 内置**：你放一份与内置同名的预设进用户目录，就覆盖内置那份 ——
这样你改过的出厂预设，升级 skill 时不会被冲掉。整个用户数据根目录可用环境变量
`DOC_FORMAT_HOME` 覆盖（测试与隔离用），路径也可以直接问 `python3 scripts/user_data.py --dir`。

| 约定 | 说明 |
|---|---|
| 命名 | 由用户取，建议带用途或单位，如「办公室周报（2026版）」 |
| 内容 | 一段中文说明 + 完整 YAML 参数 + 时效声明 |
| 来源 | 内置预设改造 / 完全自定义 / 从现成 DOCX 反推 |
| 复用 | 在规格卡里写 `meta.preset: <标识>`，或直接说「用这个预设生成」 |
| 注意 | 预设只保存排版参数与字体名，**换一台电脑后字体要重新确认一次**（本机字体清单存在字体记忆里） |

### `screen`：屏幕阅读专用字段

`screen` 只在 `meta.carriers` 含 `html` 时生效，下面分三段，单位是 px 与 em，**不要写成 pt**：

```yaml
screen:
  body:      # 字号、行高（倍数）、字色、对齐、左右内边距、字间距
  quote:     # 引用块左侧竖线、背景、内边距、字色
  image:     # 图片宽度、圆角、上下留白
```

**为什么单独包一层 `screen`：**规格卡里已经有一个叫 `body` 的东西 —— `fonts.body` 是「纸上正文用什么字体」。
屏幕阅读这组如果再叫顶层 `body`，同名不同义，
读规格卡的人和改脚本的人都容易拿错。包进 `screen` 之后，`screen.body` 说的是「屏幕上正文长什么样」。

`screen` 与 `paragraph` 的分工：

- `paragraph` 描述纸质排版的段落行为（首行缩进、固定值行距）
- `screen.body` 描述屏幕阅读的段落行为（段间距、倍数行高、左对齐）

两者不可混用：把纸质书的五号固定行距搬到公众号上，在手机上会挤成一团；把公众号的段间距搬到书上，正文会散开。

### `figures_tables` 的四个对齐字段：默认不干预

| 字段 | 含义 | 状态 |
|---|---|---|
| `header_alignment` | 表头对齐 | **可选**，不写就不动 |
| `text_column_alignment` | 文字列对齐 | **可选**，不写就不动 |
| `number_column_alignment` | 数字列对齐 | **可选**，不写就不动 |
| `table_alignment` | **表格整体在页面上的位置**（`left` / `center` / `right`） | **可选**，不写就不动 |

注意 `table_alignment` 管的是表格块的位置，与上面三个「单元格内文字对齐」是两件事，互不影响。

**本 skill 不预设表格对齐风格。** 这四个字段是「用户明确提要求时才填」的开关，预设里一律不填。
只有两种情况会写入对齐：

1. 源 Markdown 写了显式对齐标记（`|:---|` 左、`|---:|` 右、`|:---:|` 中）—— 以源文件意图为准，
   标记按 GFM 规则管整列，表头也跟着走。
2. 规格卡里显式声明了上面四个字段 —— 以用户要求为准。

两者都没有时，**脚本完全不写 `text-align` / `paragraph.alignment`**，保持 Word 与浏览器的默认。
`build_docx.py` / `build_html.py` / `convert_docx.py` 三个脚本遵循同一套规则，
否则同一个 Markdown 出 DOCX 和出 HTML 会不一致。

判定「数字列」的规则（仅在填了 `number_column_alignment` 时才用到）：单元格内容只由数字、
千分位、小数点、正负号、百分号组成才算数字列；`2026-09-17`、`15px` 这类含其他字符的仍按文字列。

一条仍然保留的配套规则：**对齐按「列」判定，不按「格」判定。** 逐格判断会让同一列里有的行
左对齐、有的行右对齐，看起来像没排过版。

### 图表题注：`table_caption_position` / `figure_caption_position`

这两个字段以前预设里登记了、脚本却一行没读，于是「表题在表上方」从来没生效过。现在：

| 字段 | 取值 | 行为 |
|---|---|---|
| `table_caption_position` | `above` \| `below` | 源稿里紧邻表格的那一段题注（以「表 1 …」开头）会被搬到表格的上方或下方。**不写则保持源稿位置不动**（不干预原则） |
| `figure_caption_position` | `above` \| `below` | 图注（取图片的替代文字）排在图片上方还是下方。不写沿用「在图下方」 |
| `caption_alignment` | `center` \| `left` \| `right` \| `outside` | 题注对齐。不写则沿用正文对齐 |
| `caption_size_pt` | 磅 | 题注字号。不写则与正文同号 |

题注段是无语法标记的普通段落，靠「以 表/图 + 编号 开头」识别（规则在 `spec_lib.is_caption_text`，
生成与校验共用同一份）。取值范围不合法会被 `spec_check.py` 拦下。

### 页码：`footer.page_number`

| 字段 | 说明 |
|---|---|
| `enabled` | 是否插入页码。公众号没有页的概念，必须为 `false` |
| `position` | `center` \| `left` \| `right` \| `outside`，两边页码相同时的位置。**取值不合法会被 `spec_check.py` 拦下**；`outside` 是「靠版心外侧」，单页在右、双页在左（右侧装订则相反） |
| `odd_page` / `even_page` | 分别指定单页、双页的页码位置。**二者都有且不同时优先于 `position`**，脚本会自动打开 `evenAndOddHeaders` 并生成两个页脚 |
| `different_odd_even` | 说「单双页不同」的开关；真正决定是否分两套的是 `odd_page`/`even_page` 是否给出且不同 |
| `dash_rule` | 页码左右各加一条一字线（`—`），公文 §7.5 要求 |
| `dash_offset_mm` | 一字线上边缘距版心下边缘的毫米数，公文规定 7mm |

公文要求页码用**半角**阿拉伯数字，但这一项不需要字段：OOXML 里数字走西文字体（`ascii`/`hAnsi`），
写出来的就是半角；只有源文件里写成全角码点（Ｕ＋ＦＦ１０ 段）才会是全角，脚本不会那样写。

`dash_offset_mm` 的单位是「距版心下边缘」而不是「距页面底边」。脚本会把它换算成页脚距，
换算时按 `dash_offset_mm + 字号 × 1.5` 反推页脚下沉量（系数 1.5 为实测值，见 `build_docx.py` 注释）。

### 页眉：`header`

| 字段 | 说明 |
|---|---|
| `enabled` | 是否要页眉。没有 `header` 段、或显式 `false` 时不排 |
| `image` / `image_height_mm` | 页眉放图片（如公司 logo）时的图片路径与高度；路径按**源稿所在目录**解析，高度默认 8mm。写了 `image` 而没写 `odd_content` / `even_content` 时，两侧都排图片 |
| `odd_content` / `even_content` | 单页、双页页眉的内容标记，见下表。**只填一侧时，另一侧沿用同一个内容** —— 奇偶页开关一旦打开，没写的那一侧页眉会整片消失，那是肉眼可见的缺陷 |
| `different_odd_even` | 单双页是否不同。它与页码共用同一个文档级开关 `w:evenAndOddHeaders`（见下） |
| `book_title` | 内容标记用到 `book_title` 时必填。书名是内容不是格式，脚本不会替你编 |
| `alignment` | `center`（默认）\| `left` \| `right` \| `outside`。取值不合法会被 `spec_check.py` 拦下，不会静默退回居中 |
| `east_asian` / `latin` / `size_pt` | 页眉字体字号 |

内容标记：

| 标记 | 写进页眉的东西 | 实现方式 |
|---|---|---|
| `chapter_name` | 当前页所属章的标题 | `STYLEREF "Heading 1"` 域，章一换页眉自动跟着换。直接写死文字会在第二章开始全错 |
| `book_title` / `document_title` | 书名 | 取 `header.book_title`；没填时退回 `meta.name` 并打印提醒，`spec_check` 与 `verify_output` 都会报出来 |
| `none` / 空 | 这一侧不排页眉 | —— |
| `image` / `logo` | 一张图片（公司 logo 等） | 取 `header.image`；找不到文件会报警并留空。只给高度，宽度按原图比例 |
| 其它字符串 | 原样照写 | 用户自定义文字 |

**页眉内容由用户决定，任何预设都不预置。** 因为「页眉放什么」是内容而不是格式：
有的书要章名，有的报告要公司名或 logo，有的单位要求放发文字号，学术论文常放论文题目。
问询时把下面这些方向一次报给用户，让他挑：

1. **不放页眉**（`enabled: false`）—— 最省事，也最常见；
2. **章名 / 章节名**（`chapter_name`）—— 书刊、学位论文常用；
3. **书名 / 报告名 / 论文题目**（`book_title`，需填 `header.book_title`）；
4. **机构名、公司全称、项目名**（任意文字，如 `××轨道交通集团有限公司`）；
5. **公司 logo 等图片**（`image`，可配 `image_height_mm`）；
6. **左右分置**：如单页放机构名、双页放报告名（`odd_content` / `even_content` 分别写）。

**页眉与页码共用「奇偶页不同」这一个开关。** `w:evenAndOddHeaders` 是文档级设置，不在节属性里：
只要页眉或页脚任意一方要求单双页不同，整篇就会打开它，**另一方也必须把单页、双页两套都写出来**。
只写一套时，空着的那一侧会整片消失 —— 实测踩过：书刊开了偶数页页眉后，偶数页页码一起没了。

### 公文主体要素：`body_elements`（公文专用）

`body_elements` 管的是 GB/T 9704-2012 §7.3 里那四种**主体要素**：主送机关、附件说明、
发文机关署名、成文日期。它们在源稿里既不是标题、也不该按普通正文排 ——
「居左顶格」（主送机关）与「首行缩进二字」（正文）是互斥的。修之前它们被当成普通正文，
主送机关与成文日期一律被缩进了两字。要识别这几种段落，必须在预设里声明形态：

```yaml
structure_rules:
  detect_elements: [recipient, signature, date, attachment]   # 声明要识别哪几种；不声明＝不识别、不干预
body_elements:
  recipient:                      # 主送机关 §7.3.2
    space_before_lines: 1         # 「编排于标题下空一行位置」
    first_line_indent_chars: 0    # 「居左顶格」
  attachment:                     # 附件说明 §7.3.4
    space_before_lines: 1         # 「正文下空一行」
    first_line_indent_chars: 2    # 「左空二字」（回行对齐见下面一段，不需要在这里配数值）
  signature:                      # 署名与成文日期 §7.3.5（两者的横向位置是联动的）
    mode: with_seal               # with_seal 盖章 | without_seal 不盖章
    space_before_lines: 1         # 署名之前空一行
    first_line_indent_chars: 0
```

| 字段 | 说明 |
|---|---|
| `space_before_lines` | 该要素上方的空行数，按正文行距折算；写 `0` 表示不留空 |
| `first_line_indent_chars` | 首行缩进字数，`0` 就是顶格 |
| `signature.mode` | 只有两个合法值：`with_seal`（加盖印章，§7.3.5.1）、`without_seal`（不加盖印章，§7.3.5.2）。两套算法不同，**必须问用户**这份公文是哪种 |

**附件说明的回行对齐（§7.3.4）不需要配数值，由前缀实际宽度算出来。** 国标要求
「附件名称较长需回行时，应当与上一行附件名称的首字对齐」，实现成悬挂缩进：

| | 值 | 例子（`附件：1. 城市防汛隐患排查台账`） |
|---|---|---|
| 首行左空 | `first_line_indent_chars`（2 字） | 从「附」字开始 |
| 左缩进（回行位） | 2 字 + 前缀宽 | 2 + 4.5 = 6.5 字，停在「城」字 |
| 悬挂量 | 前缀宽 | 4.5 字 |

这三项一律用**长度单位**（磅）写入 OOXML，这一处**故意不写字符单位**（`w:leftChars` 等）。
理由有两条，都是实测逼出来的：① 字符单位按「段落默认字号的字宽」折算，而这两处的字号常与默认
字号不同（版记 4 号、正文 3 号），折算必然偏差；② 字符单位与 `w:hanging` 同时存在时，
LibreOffice 会把悬挂算到**回行**上而不是首行上（实测六种写法各导一份 PDF 量位置：
只写 `w:left` + `w:hanging` 时首行 2.00 字/回行 6.50 字，正确；同时写 `w:hangingChars` +
`w:hanging` 变成首行 6.50 字/回行 11.00 字，正好写反）。

前缀宽由 `spec_lib.attachment_prefix_chars` 量「附件：」+ 顺序号（`附件：1. ` = 4.5 字，
`附件：` = 3 字）。**不写成固定值**：附件多寡不同、顺序号位数不同，写死必然在某一类上失准。
版记里的抄送机关走同一套（§7.4.2「回行时与冒号后的首字对齐」，前缀＝「抄送：」3 字）。

`mode` 决定署名与成文日期的横向位置（宽度按一个汉字算，阿拉伯数字算半个字）：

| mode | 成文日期 | 发文机关署名 |
|---|---|---|
| `with_seal`（§7.3.5.1） | 右空四字 | 在成文日期之上、以成文日期为准居中 |
| `without_seal`（§7.3.5.2） | 首字比署名首字右移二字；比署名长时改为右空二字 | 右空二字；日期更长时相应左移 |

**识别不到就报、不替用户编：** 预设把这三项登记在 `required_elements` 里，一处都没识别到时，
生成时会打印提醒 —— 是原稿真没写，还是写法与形态不符（如署名不在文末三行内），交给用户判断。

**版头里的签发人**（§7.2.6）属于 `masthead.signer`，与 `body_elements` 无关，只有上行文才有：

```yaml
masthead:
  doc_number:
    position: left              # 上行文：发文字号居左空一字，与最后一个签发人姓名同一行
    agency_code_omitted: false  # 见下
  signer:
    enabled: true
    name: 张三                  # 【启用时必填】内容项，脚本不编
    label_font: {east_asian: 仿宋_GB2312}   # §7.2.6：「签发人」三字用 3 号仿宋
    name_font: {east_asian: 楷体}            # §7.2.6：姓名用 3 号楷体
    size_pt: 16                 # 3 号
    position: right             # 居右空一字，与发文字号同一行
```

两个字体槽位是完整的字体档位，因此会进缺字体门禁（缺了要么装、要么在槽位里写 `resolved`）。

**`agency_code_omitted`：** 机关代字是内容项，脚本不能替用户编。字段空着有两种完全不同的情况 ——
「还没问过用户」（必须拦下，否则印出残缺的号）与「用户明确表示这份文件不写机关代字」（要放行）。
后者写 `agency_code_omitted: true`，发文字号就按「〔年份〕序号号」印。

### 版记：`record_section`（公文专用）

| 字段 | 说明 |
|---|---|
| `enabled` | 是否生成版记。`false` 时整段不输出，其余字段可为空 |
| `issuing_agency` | **启用时必填**，印发机关规范全称，左空一字 |
| `issue_date` | **启用时必填**，印发日期，右空一字，月日不编虚位 |
| `date_suffix` | 印发日期后缀，默认 `印发`。§7.4.3 末句要求日期「后加『印发』二字」，故印成「2026年9月16日印发」。**写成空串 `""` 表示这份不要这两个字**（与不写这一项是两种意思，脚本不吞空串） |
| `copy_to` | 可选，抄送机关；留空时只有首条与末条两条分隔线 |
| `east_asian` / `size_pt` | 版记字形与字号，公文为 4 号仿宋 |
| `first_last_divider_mm` | 首条与末条分隔线粗细，公文 0.35mm |
| `middle_divider_mm` | 中间分隔线粗细，公文 0.25mm |

**版记内容不能由脚本编造：** 印发机关通常就是发文机关的办公厅（室），但必须问用户或翻上一份同类
文件确认。`spec_check.py` 与 `build_docx.py` 都会在缺 `issuing_agency` / `issue_date` 时中止
（退出码 3），确需待补稿才加 `--allow-placeholders`。

### 相对间距：国标写「空 N 行」或「多少 mm」，就照它写

中文排版里要素之间的距离常用「空一行」「空二行」表示，这类字段按行算，不按磅算：

```yaml
headings:
  doc_title:
    space_before_lines: 2       # 本级标题在上一要素下空二行（公文标题：红色分隔线下空二行）
    space_before_anchor: red_separator_line   # 空行从哪儿起算，供人阅读，脚本不读
masthead:
  top_offset_mm: 35             # 红头上边缘距版心上边缘，国标给的就是毫米，直接用毫米
  doc_number:
    blank_lines_above: 2        # 发文字号在红头下空二行
  separator_line:
    offset_below_doc_number_mm: 4   # 分隔线在发文字号下 4mm
```

**一个「空行」有多高** ＝ 正文行距：`paragraph.line_spacing_mode: exact` 时取 `line_spacing_pt`；
没给固定值时退回 1.2 倍正文字号。按正文行距而不是按标题自身字号算，间距才能和版心的行网格对齐。

### 标题的段前距与段后距：四种写法

标题上下要不要留空、留多少，是「看起来挤不挤」的关键。四个字段写在**该级标题之下**：

```yaml
headings:
  level1:
    space_before_lines: 1       # 段前空一行（行高按正文行距折算）
    space_after_lines: 0.5      # 段后半行
  chapter:
    space_before_pt: 0          # 也可以直接用磅值；另起页的标题应当写 0，别把整页内容往下推
    space_after_pt: 15.6
```

| 写法 | 单位 | 什么时候用 |
|---|---|---|
| `space_before_lines` / `space_after_lines` | 行（可小数） | 标准或惯例用「空 N 行」表述时（公文、书刊最多） |
| `space_before_pt` / `space_after_pt` | 磅 | 手上有明确磅值；或要显式写 `0` 表示「就是不留空」 |
| 两者都不写 | —— | 脚本按惯例补上「段前空一行、段后半行」，**并在生成时打印一行说明**，告诉你这是脚本默认值、要改就写上面四项 |

**为什么不写也算「有值」：** 早期版本的标题样式只写了段前距、从不写段后距（预设里登记了也没用），
标题下边紧贴正文，整页看起来很挤。现在两种情况都会给间距：显式声明按声明值，没声明按惯例值并说明。

**一个例外：** 公文类预设的四个层次序数（「一、」「（一）」「1.」「（1）」）是**正文自然段**，
不是标题块，预设里显式写了 `space_before_pt: 0` / `space_after_pt: 0` ——
给它们加段间距会破坏 GB/T 9704 §5.2.3「每面 22 行」的行网格。

**已知近似**（写进规格卡时不必回避，但要心里有数）：

| 字段 | 实现方式 | 误差来源 |
|---|---|---|
| `top_offset_mm` | 红头段落的段前距 | 字体 ascent/descent 不同，实测偏差约 1mm |
| `offset_below_doc_number_mm` | 发文字号段落的段落下框线 | 边框位置由 `w:space` 换算，实测偏差约 0.2mm |
| `space_before_lines` / `blank_lines_above` | 段落段前距 | 行高按上面的规则推算，接近精确 |

`verify_output.py` 校验首页位置时会把 `masthead.top_offset_mm` 计入期望值，容差 ±5mm。

### 分节：`start_on_odd_page` 与前置页页码

```yaml
headings:
  level2:                        # 「章」那一级
    size_pt: 22
    line_spacing_pt: 30          # 可选：本级标题单独指定行距
    start_on_odd_page: true      # 每章从奇数页（右页）起

footer:
  page_number:
    enabled: true
    body_start_at: 1                                   # 正文页码从 1 重新数
    body_start_heading: 第一章 绪论                      # 正文从哪个标题开始
    front_matter:
      cover: none                                      # 封面不编页码
      cover_end_heading: 前言                           # 封面到哪个标题为止
```

| 字段 | 说明 |
|---|---|
| `headings.<级>.shape_rule` | 标题的**排列形状**（如公文标题的「梯形或菱形」，§7.3.1）。声明了它，生成端才会替长标题**人工断行**：先按两行长短最均衡挑断点（`spec_lib.balanced_heading_break`），不再由 Word 按「排满一行就断」把词切两半。不声明＝不干预，该级标题保持自动折行。自动断点按字数猜、没有词典，可能仍切断词意 —— 生成时会把那两行打印出来，用户可改用源稿里的 `｜` 标记指定断点（见 `references/markdown-rules.md` 第三节） |
| `headings.<级>.start_on_odd_page` | 该级每个标题都从奇数页起。实现方式是 OOXML 分节符 `w:type=oddPage` |
| `headings.<级>.line_spacing_pt` | 本级标题单独的行距。**不写就继承正文行距**，而正文行距比标题字号还小时会把标题压叠，脚本会自动改成单倍并警告 |
| `footer.page_number.body_start_at` | 正文起始页码。写了它，正文与前置页会分成两节 |
| `footer.page_number.body_start_heading` | **正文从哪个标题开始**（标题文字，需完全一致）。不写就无法定位分界，页码整项跳过并警告 |
| `footer.page_number.front_matter.cover_end_heading` | 封面到哪个标题为止。**不写则封面与前言算作同一节**，无法只免掉封面的页码，脚本会明确警告 |

**「章从奇数页起」会多出空白页，这是正常版面，不是缺陷。** 上一章若正好收在奇数页，
下一章要从奇数页起就必须空掉一页。麻烦出在导出环节：LibreOffice 转 PDF 时**默认丢弃空白页**
（`IsSkipEmptyPages` 默认 `true`），实测把 16 页的稿子导成 12 页 —— 页数一变，
后面每一页的左右（奇偶）整体错位，页码域仍按 16 页计数，印出来的页码与实际页序对不上。

`build_pdf.py` 已经显式关掉这个选项。**换别的工具导出时要注意同一件事**，
`verify_output.py` 会直接量真实 PDF 里各章的落点，落在偶数页就报「需确认」并指向这个原因。

## 规格校验规则（`spec_check.py` 会检查）

**错误（阻断生成）**

| 规则 | 说明 |
|---|---|
| `meta.source_type` 为 `国标` 但 `standard` 为空 | 声称国标却没给出标准号 |
| 字号为正文字号小于标题字号 | 层级倒挂 |
| 页边距过小（任一边 < 10mm） | 装订会吃掉正文 |
| 对公众号 HTML 要求了页边距或页码 | 无页概念，必须告知跳过并写进报告 |
| 字体在本机不存在，且未写 `resolved` | 会掉字或渲染成方框，生成时中止（退出码 4） |
| 写了 `resolved` 但那个字体本机也没有 | 同样中止，替代字体必须是本机真的装了的 |
| 启用了 `masthead` 但必填项为空（机关名称、机关代字、年份、顺序号、签发人姓名） | 不拦住就会印出光秃秃的「文件」两个字和「〔2026〕号」，用户拿到手才发现。`build_docx.py` 也会中止并返回退出码 3；确实要待补稿才加 `--allow-placeholders` |
| 启用了 `record_section` 但 `issuing_agency` / `issue_date` 为空 | 版记是公文的生效凭证，印发机关与日期写错或留空等于伪造公文要件。同样由 `build_docx.py` 以退出码 3 中止 |
| 页眉用了 `book_title` 但 `header.book_title` 为空 | 警告，不阻断：会退回用规格名占位，`verify_output` 会把它列为「失败」提醒交付前补上 |
| `body_elements.signature.mode` 取值不是 `with_seal` / `without_seal` | 署名与成文日期的位置会退回盖章那套排法，用户以为选了「不盖章」，出来却是盖章的版式 |

**警告（提示但不阻断）**

| 规则 | 说明 |
|---|---|
| 行距固定值小于字号 × 1.2 | 中文会挤在一起 |
| 首行缩进用了长度单位而非字符数 | 换字号后失准 |
| 只设了中文字体未设西文字体 | 英文数字会难看 |
| 引用了 GB/T 7714-2015 但未说明原因 | 该版本已废止 |
| 引用了 GB/T 7713.1-2006 但未说明原因 | 已被 2025 版替代 |
| 缺少 `meta.verified_at` 或 `meta.recheck_after` | 无法判断规格有多旧 |
| 已超过 `meta.recheck_after` | 必须先联网复查标准现行性 |
| `carriers` 含 `html` 但缺少 `html` 段 | 无法保证样式内联，粘进公众号会掉样式 |

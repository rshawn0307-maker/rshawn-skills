# 预设：中文图书

> ## ⏱ 时效声明
>
> **数据核验日期：2026-09-17**　核验渠道：国内出版社通行排版惯例（无强制国标）。
>
> **使用本预设前，必须核对它是否仍与最新标准/惯例一致。** 分两种情况处理：
>
> - **用户只是想在预设基础上改个别参数**（字号、边距、行距等）→ 直接改，不必去查标准。
> - **用户指出某条规定已变化，或距核验日期已超过 12 个月** → 必须复检，不得沿用本文件：
>   1. 先请用户提供出处（标准原文、学校/单位最新模板、期刊投稿须知）；
>   2. 用户拿不出出处时，联网到官方渠道复查；
>   3. 确认后把结论写进你自己那份 `standards.md`（路径问 `python3 scripts/user_data.py --path standards.md`），
>      并更新规格卡的 `verified_at` 字段。**要改这条预设本身，先另存一份到用户预设目录再改** ——
>      直接改出厂预设，下次更新 skill 就被覆盖了。
>
> **复检渠道：**
> - **以目标出版社的《著译编者须知》或排版规范为准**，各社要求不同
> - 若用户手上有出版社下发的排版要求文件，优先按该文件执行
> - 本预设无标准号，所有数值都属可调惯例
>
> **提示义务：** 展示本预设时，要主动告诉用户「这份预设是 X 年 X 月核验的，
> 如果你手上的模板/须知与它不一致，以你手上的为准」。不要默认预设一定正确。

| 项 | 值 |
|---|---|
| 来源类型 | **出版社惯例**（无强制国标，可调） |
| 标准号 | **无**。本预设不引用任何国标编号 |
| 适用载体 | DOCX（编辑稿）、PDF（印刷稿） |

## 一、为什么这个预设没有国标号

图书开本、正文字号、版心比例由出版社与责任编辑决定，属行业惯例而非强制标准。常见的「GB/T 788 图书和杂志开本及其幅面尺寸」在国家标准全文公开系统中检索不到，**本 skill 不引用该编号**（见 `references/standards.md` 第一节「未能核验的标准」）。

因此本预设的一切数值都是**可调的惯例值**，用户想改就改，不存在「违反国标」的问题。

## 二、用中文向用户介绍这个预设

```
中文图书（出版社惯例，无强制国标）

  开本        大 32 开，成品 140mm × 203mm（另有 16 开 185mm × 260mm）
  页边距      上 20mm、下 20mm、订口（内侧）22mm、切口（外侧）18mm
              ← 左右不对称，因为装订会吃掉内侧空间；
                双面印刷时靠镜像页边距（settings.xml 的 w:mirrorMargins）在偶数页自动互换内侧与外侧
  正文        五号宋体（10.5pt），西文 Times New Roman
  行距        固定值 15.6pt（约 1.5 倍）
  首行缩进     2 字符
  段间距      0（中文图书靠缩进区分段落，不靠段间距）
  章标题      二号或小二黑体，另起页，从奇数页（右页）起，标题下空一行
  节标题      小三或四号黑体，上空一行、下空半行
  页眉        不预置，由用户决定放什么（章名／书名／机构名／logo），小五号
  页码        小五号，居中或外侧
  表格        表题在表上方；对齐不预设，按源文件或你的要求来
  图注        图题在图下方，小五号，居中

  以上均为惯例，不是国标，可按你的偏好调整
```

## 三、必须问用户的项

| 项 | 为什么问 | 建议默认 |
|---|---|---|
| 开本 | 32 开与 16 开视觉差异极大 | 大 32 开 |
| 是否双面印刷 | 决定页边距是否左右对称、奇偶页页眉是否不同 | 是 |
| 正文是否用固定值行距 | 固定值与倍数的观感不同 | 固定值 15.6pt |
| 章标题是否另起页、是否从奇数页起 | 图书惯例，但需确认 | 另起页、奇数页起 |
| 页眉内容 | **放什么由用户决定，预设不预置**：不放／章名／书名／机构名／logo 图片 | 先问；答「不放」就关闭页眉 |
| 书名（页眉要用） | 页眉要印书名时才有用，书名是内容不是格式，脚本不会替你编 | 用到 `book_title` 时才必填（不填会退回用规格名占位） |
| 前置页如何编页码 | 封面、前言、目录、正文的页码规则不同 | 封面无码、前言目录用罗马数字、正文从 1 起 |
| 表格是否用三线表 | 图书与学术惯例不同 | 图书用全框线或三线表均可 |
| 字体缺失时 | 印刷需嵌入字体或转曲 | 缺哪个就问用户：装字体，或指定本机已有的（写进 `resolved`） |

## 四、YAML 参数

```yaml
meta:
  preset: book-cn
  name: 中文图书
  source_type: 惯例
  standard: null
  verified_at: "2026-09-17"
  recheck_after: "2027-09-17"   # 超过此日期必须先复检再使用
  recheck_rule: 用户只改个别参数则直接改；引用标准变化或超期时必须联网复检并更新
  carriers: [docx, pdf]

page:
  size: custom
  width_mm: 140                   # 大 32 开成品宽度
  height_mm: 203                  # 大 32 开成品高度
  margin_top_mm: 20
  margin_bottom_mm: 20
  margin_inside_mm: 22            # 订口，比切口宽
  margin_outside_mm: 18           # 切口
  mirror_margins: true            # 左右页镜像，双面印刷必需（原来还写了一个 two_sided，没人读，已删）
  binding: left

fonts:
  # 本机缺字体时的规则：装上它，或在对应槽位显式写 resolved（禁止自动替身）
  body:
    east_asian: 宋体
    latin: Times New Roman
    size_pt: 10.5
    size_label: 五号
  code:                           # 代码块必须显式声明字体，不能靠默认值
    east_asian: 宋体
    latin: Courier New            # 等宽体；本机没有就中止，不自动替换
    size_pt: 9

paragraph:
  line_spacing_mode: exact
  line_spacing_pt: 15.6
  first_line_indent_chars: 2
  space_before_pt: 0
  space_after_pt: 0
  alignment: justify

blocks:
  # 表格、图片、代码块、引用块、分隔线这些「没有首行缩进」的块级元素，与上下正文之间的空。
  # 正文段间距为 0（中文图书靠缩进分段），所以这几类块必须自己留空，否则会与正文粘成一坨。
  # 图书里留得比报告小一点，免得版面被切得太散。
  space_before_lines: 0.5         # 块与上文之间空半行（惯例值，可改）
  space_after_lines: 0.5          # 与下文之间空半行
  caption_gap_lines: 0.3          # 表题/图注与它标注的表、图之间的小空（太大会看不出它在标注谁）

headings:
  chapter:                        # 章标题
    east_asian: 黑体
    size_pt: 22                   # 二号
    line_spacing_pt: 30           # 标题自己定死行距；不写就继承正文行距，可能把标题压叠
    alignment: center
    page_break_before: true
    start_on_odd_page: true       # 从右页起；上一章收在奇数页时中间会插一页空白，属正常版面
    space_before_pt: 0            # 另起页的标题不要再加段前距，否则整页内容被往下推
    space_after_lines: 1          # 标题下空一行再排正文（惯例值，可改）
  section:                        # 节标题
    east_asian: 黑体
    size_pt: 15                   # 小三
    alignment: left
    space_before_lines: 1         # 上空一行，与上文正文拉开（惯例值，可改）
    space_after_lines: 0.5        # 下空半行，别让标题贴着正文

header:
  # 【页眉内容由用户决定，预设不预置】图书最常见的三种做法，挑一种填进去：
  #   ① 不放页眉：enabled: false（最省事）
  #   ② 奇章名 / 偶书名：odd_content: chapter_name，even_content: book_title，并填下面的 book_title
  #   ③ 放机构名或 logo：odd_content: "××出版社"，或 image: logo.png（图片按源稿目录解析）
  # 其余可选值见 references/spec-schema.md「页眉：header」一节。
  enabled: false
  different_odd_even: true        # 单双页不同；与页码共用同一个文档级开关
  odd_content: ""                 # 单页页眉内容（留空 = 还没定）
  even_content: ""                # 双页页眉内容（只填一侧时另一侧沿用同一个内容）
  book_title: ""                  # 用到 book_title 时必填；不填会退回用规格名占位并提醒
  image: ""                       # 放 logo 时写图片路径（相对源稿目录），并配 image_height_mm
  image_height_mm: 8              # 页眉图片高度，默认 8mm；太大就会把正文往下挤
  alignment: center               # 页眉居中（可改 left / right / outside）
  size_pt: 9
  size_label: 小五

footer:
  page_number:
    enabled: true
    size_pt: 9
    position: center
    body_start_heading: ""        # 【启用前置页页码时必填】正文从哪个标题开始，须与标题文字完全一致
    front_matter:
      cover: none                 # 封面不编页码
      cover_end_heading: ""       # 【要只免掉封面页码时必填】封面到哪个标题为止；不填则封面与前言同节
      preface_toc: roman          # 前言与目录用罗马数字
    body_start_at: 1              # 正文从 1 重新开始

figures_tables:
  table_caption_position: above
  figure_caption_position: below
  caption_size_pt: 9
  caption_alignment: center
  table_style: three_line

# ── 结构识别规则（infer_structure.py 读取）───────────────
structure_rules:
  family: book    # 层次序数规则族：gov（公文四级）| book（章节六级）| screen（屏幕粗分）
  detect_elements: []    # 本体裁不做公文要素识别
required_elements:    # 体裁门槛：缺了就不能当正式文件交付，必须问用户
  - key: chapters
    label: 章节结构
ask_elements:    # 内容里没有、只能问用户的项
  - key: book_meta
    label: 书籍信息
    ask: 书名、作者、出版社、开本是？封面与版权页要用
```

## 五、载体适配注意

| 项 | DOCX | PDF |
|---|---|---|
| 开本尺寸 | `w:pgSz` 自定义宽高 | 保留 |
| 镜像页边距 | `w:mirrorMargins` | 保留 |
| 章从奇数页起 | 需手动插入空白页 | 保留 |
| 奇偶页不同页眉 | `w:evenAndOddHeaders` | 保留 |
| 前置页页码规则 | 需分节符 + 分节页码格式 | 保留 |
| 首行缩进 | `w:ind w:firstLineChars="200"` | 保留 |

**图书是纸媒参数用得最满的场景。** 开本、镜像页边距、奇偶页页眉、前置页页码规则都只在 DOCX / PDF 上有意义；换成屏幕载体（公众号）时按「意图层」翻译：保留正文缩进与标题层级，丢掉开本、页边距、页码、奇偶页页眉。

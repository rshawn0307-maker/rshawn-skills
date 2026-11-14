# 预设：商务报告 / 通用文档

> ## ⏱ 时效声明
>
> **数据核验日期：2026-09-17**　核验渠道：国内企业与机构通行排版惯例（无强制国标）。
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
> - **以用户所在单位的公文/报告模板为准**（多数单位有内部模板）
> - 若单位模板引用了 GB/T 9704，实际应按公文预设处理
> - 本预设无标准号，所有数值都属可调惯例
>
> **提示义务：** 展示本预设时，要主动告诉用户「这份预设是 X 年 X 月核验的，
> 如果你手上的模板/须知与它不一致，以你手上的为准」。不要默认预设一定正确。

| 项 | 值 |
|---|---|
| 来源类型 | **行业惯例**（无强制国标） |
| 标准号 | **无** |
| 适用载体 | DOCX（协作修改）、PDF（对外发送） |

## 一、用中文向用户介绍这个预设

```
商务报告（行业惯例，无强制国标）

  纸张        A4
  页边距      上下 25.4mm、左右 31.8mm（Word 中文默认值）
  正文        小四宋体（12pt），西文 Times New Roman
  行距        1.5 倍
  首行缩进     2 字符（也可以改用段间距，见下方选项）
  一级标题    三号黑体，左对齐，上空一行、下空半行
  二级标题    四号黑体，左对齐，上空一行、下空半行
  三级标题    小四加粗，左对齐，上空半行、下空半行
  页眉        不预置，由用户决定放什么（报告名／公司名／logo），小五号
  页码        小五号，居中或右下
  表格        表题在表上方；对齐不预设，按源文件或你的要求来
```

## 二、必须问用户的项

| 项 | 为什么问 | 建议默认 |
|---|---|---|
| 用首行缩进还是段间距 | 打印稿习惯用缩进，屏幕阅读习惯用段间距 | 打印用缩进，屏幕用段间距 |
| 是否加封面与目录 | 长报告需要，短报告不需要 | 超过 10 页才加 |
| 表格风格 | 全框线（数据报表常用）vs 三线表（书刊常用） | 全框线；表头加底纹属于美化，本 skill 不做 |
| 是否有品牌规范 | 企业往往有 VI 手册规定的字体与色值 | 询问是否有 |
| 页码位置 | 居中或右下 | 右下 |

## 三、YAML 参数

```yaml
meta:
  preset: report-cn
  name: 商务报告
  source_type: 惯例
  standard: null
  verified_at: "2026-09-17"
  recheck_after: "2027-09-17"   # 超过此日期必须先复检再使用
  recheck_rule: 用户只改个别参数则直接改；引用标准变化或超期时必须联网复检并更新
  carriers: [docx, pdf]

page:
  size: A4
  width_mm: 210
  height_mm: 297
  margin_top_mm: 25.4
  margin_bottom_mm: 25.4
  margin_left_mm: 31.8
  margin_right_mm: 31.8

fonts:
  # 本机缺字体时的规则：装上它，或在对应槽位显式写 resolved（禁止自动替身）
  body:
    east_asian: 宋体
    latin: Times New Roman
    size_pt: 12
    size_label: 小四

paragraph:
  indent_mode: first_line       # first_line（印刷习惯）| spacing（屏幕习惯）
  first_line_indent_chars: 2
  line_spacing_mode: multiple
  line_spacing_value: 1.5
  space_before_pt: 0
  space_after_pt: 0             # indent_mode 为 spacing 时改为 10

headings:
  # 段前段后距用「空 N 行」表达，行高按正文行距折算 —— 这正是中文排版的习惯说法。
  # 这几行是本项目早期版本漏掉的一项：预设里从来没登记，脚本也从来没写进文件，
  # 结果标题上下都紧贴着文字，整页看起来像挤成一团（用户实测反馈）。
  level1:
    east_asian: 黑体
    size_pt: 16                 # 三号
    alignment: left
    space_before_lines: 1       # 上空一行（惯例值，可改）
    space_after_lines: 0.5      # 下空半行
  level2:
    east_asian: 黑体
    size_pt: 14                 # 四号
    alignment: left
    space_before_lines: 1
    space_after_lines: 0.5
  level3:
    east_asian: 黑体
    size_pt: 12                 # 小四
    bold: true
    alignment: left
    space_before_lines: 0.5
    space_after_lines: 0.5

figures_tables:
  table_caption_position: above
  figure_caption_position: below
  table_style: grid             # grid（全框线）| three_line（三线表）

blocks:
  # 表格、图片、代码块、引用块、分隔线这些「没有首行缩进」的块级元素，与上下正文之间的空。
  # 正文段间距为 0（中文纸媒靠首行缩进分段），所以这几类块必须自己留空，否则会与正文粘成一坨。
  space_before_lines: 0.5         # 块与上文之间空半行（惯例值，可改）
  space_after_lines: 0.5          # 与下文之间空半行
  caption_gap_lines: 0.3          # 表题/图注与它标注的表、图之间的小空

footer:
  page_number:
    enabled: true
    size_pt: 9
    position: right                # 曾误写成 right_bottom，那不是合法值（会被静默当居中）。合法值：left/center/right/outside

header:
  # 【页眉内容由用户决定，预设不预置】商务报告最常见的三种做法，挑一种填进去：
  #   ① 不放页眉：enabled: false（最省事）
  #   ② 放报告名：odd_content: book_title，并填下面的 book_title
  #   ③ 放公司名或 logo：odd_content: "××轨道交通集团有限公司"，或 image: logo.png
  # 其余可选值见 references/spec-schema.md「页眉：header」一节。
  # 注意：这一项必须写在顶层，不能嵌在 footer 里 —— 旧版就误嵌成 footer.header，脚本读不到，
  # 于是「规格里关了页眉」和「规格里没写页眉」在产物上没有任何区别，用户以为设了其实没生效。
  enabled: false
  odd_content: ""                # 单页页眉内容（留空 = 还没定）
  even_content: ""               # 双页页眉内容（只填一侧时另一侧沿用同一个内容）
  book_title: ""                 # 用到 book_title 时必填
  image: ""                      # 放 logo 时写图片路径（相对源稿目录）
  image_height_mm: 8             # 页眉图片高度，默认 8mm
  alignment: center              # 页眉居中（可改 left / right / outside）
  size_pt: 9

# ── 结构识别规则（infer_structure.py 读取）───────────────
structure_rules:
  family: book    # 层次序数规则族：gov（公文四级）| book（章节六级）| screen（屏幕粗分）
  detect_elements: []    # 本体裁不做公文要素识别
required_elements: []    # 本体裁无硬性内容门槛
ask_elements:    # 内容里没有、只能问用户的项
  - key: report_meta
    label: 报告信息
    ask: 报告标题、作者或单位、日期是？封面要用
```

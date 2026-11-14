# 预设：学位论文

> ## ⏱ 时效声明
>
> **数据核验日期：2026-09-17**　核验渠道：国标 GB/T 7713.1-2025《学位论文编写规则》。
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
> - `openstd.samr.gov.cn` 检索「GB/T 7713.1」确认现行版本
> - **优先以用户所在学校研究生院发布的最新学位论文格式模板为准**，校级模板与国标冲突时听学校的
> - 参考文献部分同时受 GB/T 7714 约束，见 `references/presets/paper-cn.md`
>
> **提示义务：** 展示本预设时，要主动告诉用户「这份预设是 X 年 X 月核验的，
> 如果你手上的模板/须知与它不一致，以你手上的为准」。不要默认预设一定正确。

| 项 | 值 |
|---|---|
| 来源类型 | **国标框架 + 校级模板优先** |
| 标准号 | GB/T 7713.1-2025《信息与文献 编写规则 第1部分：学位论文》 |
| 标准状态 | 现行（2025-08-01 发布，2026-02-01 实施），替代 GB/T 7713.1-2006（已废止） |
| 适用载体 | DOCX（送审通常要求）、PDF（归档） |

## 一、本预设的诚实边界

**已核实：** 标准编号、名称、现行状态、发布与实施日期、替代关系（见 `references/standards.md`）。

**未核实：** 该标准的具体条款数值（页边距、字号等）。本 skill **没有**取得 GB/T 7713.1-2025 的正文，因此下方版式数值全部标注为「惯例」，**不得作为国标引用**。

**最重要的实操规则：**

> 学位论文的实际格式**以学校研究生院发布的最新模板为准**。国标只规定框架性要求（结构、要素、编写规则），具体版式各校差异极大，且校级模板经常不跟随国标更新。
>
> 所以本预设的正确用法是：**先问用户要学校模板**。拿到模板就跑 `scripts/inspect_docx.py` 反推它的规格，然后用那份规格生成，而不是用下面的惯例值。

## 二、用中文向用户介绍这个预设

```
学位论文（GB/T 7713.1-2025 框架 + 校级模板优先）

  ⚠️ 各校模板差异大，请先提供你学校研究生院的官方模板
     我会先读一遍它的规格，再按它生成

  若要使用下面的通用惯例值，请确认：
  纸张        A4
  页边距      上下 25mm、左 30mm、右 25mm（左侧留装订线）
  正文        小四宋体（12pt），行距 1.5 倍或固定值 20-22pt
  首行缩进     2 字符
  章标题      三号或小三黑体，居中，另起页，标题下空一行
  节标题      四号黑体，顶格或缩进，上空一行、下空半行
  页眉        通常为「学校名称 + 学位论文」，五号或小五号
  页码        正文用阿拉伯数字，目录用罗马数字，封面无页码
  参考文献    GB/T 7714-2025 或学校指定的版本

  以上数值均属惯例，非国标规定，务必与学校模板核对
```

## 三、必须问用户的项

| 项 | 为什么问 | 建议默认 |
|---|---|---|
| 学校研究生院模板文件 | 校级模板优先于国标惯例 | 请用户提供 |
| 学位层次 | 硕士与博士要求不同 | 硕士 |
| 参考文献标准版本 | GB/T 7714-2025 已生效，但多数模板仍用 2015 | 跟随学校模板 |
| 正文字号与行距 | 各校差异大 | 小四宋体、1.5 倍行距 |
| 页边距 | 各校差异大，需留装订线 | 上 25mm 下 25mm 左 30mm 右 25mm |
| 目录页码样式 | 罗马数字与阿拉伯数字的切换点各校不同 | 正文起用阿拉伯数字 |
| 页眉内容 | **放什么由用户决定，预设不预置**：不放／学校名+「学位论文」／论文题目／校徽 logo | 先问；学校模板有规定就照模板 |
| 是否双面打印 | 影响奇偶页页眉 | 单面 |
| 字体缺失时 | 涉及版权与一致性 | 问用户：装字体，或指定本机已有的（写进 `resolved`） |

## 四、YAML 参数

```yaml
meta:
  preset: thesis-cn
  name: 学位论文
  source_type: 国标框架_校级模板优先
  standard: GB/T 7713.1-2025
  standard_note: 仅核实标准编号与现行状态，条款数值未核实，下方数值均为惯例
  verified_at: "2026-09-17"
  recheck_after: "2027-09-17"   # 超过此日期必须先复检再使用
  recheck_rule: 用户只改个别参数则直接改；引用标准变化或超期时必须联网复检并更新
  carriers: [docx, pdf]
  school_template: ""             # 学校模板路径。注意：当前没有脚本读它，填了不会自动按模板排 ——
                                  # 拿到学校模板时要人工对照，改下面各个数值

page:
  size: A4
  margin_top_mm: 25
  margin_bottom_mm: 25
  margin_left_mm: 30              # 左侧留装订线，故大于右侧
  margin_right_mm: 25
  binding: left

fonts:
  # 本机缺字体时的规则：装上它，或在对应槽位显式写 resolved（禁止自动替身）
  body:
    east_asian: 宋体
    latin: Times New Roman
    size_pt: 12
    size_label: 小四

paragraph:
  line_spacing_mode: multiple
  line_spacing_value: 1.5
  first_line_indent_chars: 2
  alignment: justify

headings:
  # 段前段后距用「空 N 行」表达（行高按正文行距折算）。
  # 各校模板对章标题上下的空行规定不一（有的空一行、有的空两行），所以这里写的是惯例值，
  # 拿到学校模板后请按模板改。
  chapter:
    east_asian: 黑体
    size_pt: 16                   # 三号
    alignment: center
    page_break_before: true
    space_before_pt: 0            # 另起页的章标题不再加段前距
    space_after_lines: 1          # 标题下空一行（惯例值，请与学校模板核对）
  level2:                         # 1.1
    east_asian: 黑体
    size_pt: 14                   # 四号
    alignment: left
    space_before_lines: 1         # 上空一行（惯例值）
    space_after_lines: 0.5        # 下空半行
  level3:                         # 1.1.1
    east_asian: 黑体
    size_pt: 12                   # 小四
    alignment: left
    space_before_lines: 0.5       # 上空半行
    space_after_lines: 0.5

footer:
  page_number:
    enabled: true
    position: center
    # 前置部分（摘要、目录）用罗马数字，正文起用阿拉伯数字，封面不编页码。
    # 键名必须与 build_docx.apply_front_matter_numbering 读的一致 —— 写过 front_matter_style /
    # body_style / cover_no_number 这三个名字，但没有任何一行代码读它们，等于白写。
    # 正文永远是阿拉伯数字，没有开关可配。
    front_matter:
      cover: none                 # 封面不编页码
      cover_end_heading: ''       # 封面到哪个标题为止；留空则封面与前置合并成一节，封面会跟着编罗马数字
      preface_toc: roman          # 摘要与目录用罗马数字
    body_start_at: 1              # 正文从第 1 页起
    body_start_heading: ''        # 【必填，不填整项跳过、仍在 1 起通排】正文从哪个标题开始，如「第 1 章　绪论」

blocks:
  # 表格、图片、代码块、引用块、分隔线这些「没有首行缩进」的块级元素，与上下正文之间的空。
  # 学位论文正文靠首行缩进分段（段间距 0），所以这几类块必须自己留空；
  # 学校模板另有规定时以模板为准。
  space_before_lines: 0.5         # 块与上文之间空半行（惯例值，可改）
  space_after_lines: 0.5          # 与下文之间空半行
  caption_gap_lines: 0.3          # 表题/图注与它标注的表、图之间的小空

header:
  # 【页眉内容由用户决定，预设不预置】各校要求不同，务必以学校模板为准，这里不预置内容：
  #   ① 不放页眉：enabled: false
  #   ② 「学校名 + 学位论文」：odd_content: "××大学硕士学位论文"（双页可放论文题目）
  #   ③ 奇偶页不同：odd_content 放论文题目、even_content 放「学校名 + 学位论文」
  #   ④ 放校徽 logo：image: logo.png（图片按源稿目录解析，高度用 image_height_mm 控制）
  # 其余可选值见 references/spec-schema.md「页眉：header」一节。
  enabled: false
  odd_content: ""                 # 单页页眉内容（留空 = 还没定）
  even_content: ""                # 双页页眉内容（只填一侧时另一侧沿用同一个内容）
  book_title: ""                  # 用到 book_title 时填论文题目
  image: ""                       # 放校徽时写图片路径（相对源稿目录）
  image_height_mm: 8              # 页眉图片高度，默认 8mm
  alignment: center               # 页眉居中（可改 left / right / outside）
  size_pt: 9
  size_label: 小五

references:
  standard: GB/T 7714-2025        # 以学校模板指定版本为准
  note: 很多学校模板仍停留在 GB/T 7714-2015，务必确认

structure:                        # 学位论文必备要素
  order:
    - 封面
    - 中文摘要与关键词
    - 英文摘要与关键词
    - 目录
    - 正文
    - 参考文献
    - 致谢
    - 附录
    - 学位论文原创性声明与授权书

# ── 结构识别规则（infer_structure.py 读取）───────────────
structure_rules:
  family: book    # 层次序数规则族：gov（公文四级）| book（章节六级）| screen（屏幕粗分）
  detect_elements: []    # 本体裁不做公文要素识别
required_elements:    # 体裁门槛：缺了就不能当正式文件交付，必须问用户
  - key: abstract
    label: 摘要与关键词
  - key: references_section
    label: 参考文献
ask_elements:    # 内容里没有、只能问用户的项
  - key: author_info
    label: 作者信息
    ask: 作者姓名、学号、专业、导师、培养单位分别是？封面与题名页要用
  - key: ref_standard
    label: 参考文献标准
    ask: 参考文献按哪版著录？GB/T 7714-2025 已生效，但多数学校模板仍停在 2015 版
```

## 五、载体适配注意

| 项 | DOCX | PDF |
|---|---|---|
| 页边距与编号 | 需要分节符切换页码格式 | 通过 LibreOffice 保留 |
| 页码格式切换 | 前置部分与正文之间插入分节符，取消「链接到前一节」 | 保留 |
| 目录 | 用目录域，交付前提醒用户按 F9 更新 | 转换时已固定 |

#!/usr/bin/env python3
# 本脚本把 Markdown 按规格卡生成 DOCX，把「首行缩进、字体、字号、行距、表格对齐、页码」真正写进样式。
# 用法：python3 scripts/build_docx.py --spec typography.spec.yaml --input book.md --output book.docx

import argparse   # 用于解析命令行参数
import os         # 用于处理路径
import sys        # 用于控制退出码与错误输出
from copy import deepcopy   # 深拷贝节属性节点：分节时每节要一份独立的 sectPr，不能共用同一个对象

# 把 scripts 目录加入模块路径，保证能导入公共库
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import spec_lib   # 导入本项目的公共库

# 尝试导入 python-docx，缺失时给出明确提示
try:
    from docx import Document                                  # 文档对象
    from docx.text.paragraph import Paragraph                  # 段落对象：把已有的 w:p 元素包一层，才能直接设段前段后
    from docx.shared import Pt, Mm, Cm, RGBColor               # 常用单位与颜色
    from docx.enum.text import WD_ALIGN_PARAGRAPH              # 段落对齐枚举
    from docx.enum.table import WD_TABLE_ALIGNMENT              # 表格对齐枚举
    from docx.enum.text import WD_TAB_ALIGNMENT                 # 制表位对齐枚举（版记用）
    from docx.oxml.ns import qn                                # XML 命名空间工具
    from docx.oxml import OxmlElement                          # 用于构造底层 XML 元素
except ImportError:                                            # 捕获导入失败
    print("缺少依赖 python-docx，请运行：pip3 install python-docx", file=sys.stderr)   # 提示安装
    raise SystemExit(2)                                        # 以环境错误码退出

# 对齐名称到 python-docx 枚举的映射
ALIGN_MAP = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,        # 左对齐
    "center": WD_ALIGN_PARAGRAPH.CENTER,    # 居中
    "right": WD_ALIGN_PARAGRAPH.RIGHT,      # 右对齐
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,  # 两端对齐
}

# 上面的反查表：python-docx 枚举 → 对齐名称。convert_docx.py 反推原文档已经设过的对齐时要用
REVERSE_ALIGN = {value: key for key, value in ALIGN_MAP.items()}   # 枚举与名称互换

# 表格整体在页面上的位置（与单元格内文字对齐无关）。
# 与单元格对齐同样遵循「不预设」原则：规格卡写了才生效，没写就不动。
TABLE_ALIGN_MAP = {
    "left": WD_TABLE_ALIGNMENT.LEFT,        # 表格靠左
    "center": WD_TABLE_ALIGNMENT.CENTER,    # 表格居中
    "right": WD_TABLE_ALIGNMENT.RIGHT,      # 表格靠右
}

# 清掉 rFonts 上的「主题字体」引用（asciiTheme / hAnsiTheme / eastAsiaTheme / cstheme）。
#
# 为什么必须清：Word 内置样式（Heading 1 等）默认用主题字体，元素上会同时带
# w:eastAsiaTheme="majorEastAsia" 和 w:eastAsia="黑体" 两个属性。按 OOXML 规则，
# 主题属性的优先级更高，于是我们写的显式字体名会被无视 ——
# 实测证据：同一份 DOCX，保留主题属性时 PDF 里的标题中文字体是被顶替的宋体；
# 删掉主题属性后立刻变成 STHeitiSC-Medium，即规格要求的黑体。
def clear_theme_fonts(rfonts):
    if rfonts is None:                                     # 没有字体节点
        return                                             # 直接返回
    for attr in ("w:asciiTheme", "w:hAnsiTheme",                # 遍历四个主题字体属性
                 "w:eastAsiaTheme", "w:cstheme"):          # 中外文与复杂文种
        if rfonts.get(qn(attr)) is not None:               # 属性存在
            del rfonts.attrib[qn(attr)]                    # 删掉它，让显式字体名生效

# 设置文本块的中英文字体、字号与字重
def style_run(run, east_asian, latin, size_pt, bold=False):
    run.font.size = Pt(float(size_pt))          # 设置字号（磅）
    run.bold = bool(bold)                       # 设置是否加粗
    run.font.name = latin or east_asian         # 设置西文字体名（python-docx 默认字段）
    rpr = run._element.get_or_add_rPr()         # 取得或创建字符属性节点
    fonts = rpr.find(qn("w:rFonts"))            # 查找字体节点
    if fonts is None:                           # 若不存在
        fonts = OxmlElement("w:rFonts")         # 创建字体节点
        rpr.append(fonts)                       # 挂到字符属性下
    fonts.set(qn("w:ascii"), latin or east_asian)      # 设置西文字体
    fonts.set(qn("w:hAnsi"), latin or east_asian)      # 设置高位西文字体
    fonts.set(qn("w:eastAsia"), east_asian)            # 设置中文字体（关键：不设会导致中文回退）
    clear_theme_fonts(fonts)                           # 清掉主题字体，否则上面的显式字体会被压掉

# 把段落的行距写入底层 XML，支持固定值与倍数两种模式
def set_line_spacing(paragraph, mode, pt=None, value=None):
    ppr = paragraph._p.get_or_add_pPr()         # 取得或创建段落属性节点
    spacing = ppr.find(qn("w:spacing"))         # 查找行距节点
    if spacing is None:                         # 若不存在
        spacing = OxmlElement("w:spacing")      # 创建行距节点
        ppr.append(spacing)                     # 挂到段落属性下
    if mode == "exact" and pt:                  # 固定值模式
        spacing.set(qn("w:line"), str(spec_lib.pt_to_docx_line(pt)))   # 写入行距（二十分之一磅）
        spacing.set(qn("w:lineRule"), "exact")                          # 指定为固定值
    elif mode == "multiple" and value:          # 倍数模式
        spacing.set(qn("w:line"), str(int(float(value) * 240)))         # 倍数乘 240 得到行距
        spacing.set(qn("w:lineRule"), "auto")                          # 指定为自动

# 取得（或创建）段落的 w:ind 缩进节点。三种缩进（首行、左右、悬挂）都要往这个节点上写属性，
# 抽成一个函数，免得三处各写一遍「查找节点 + 不存在就创建」的样板代码、日后改漏一处。
def get_or_add_ind(paragraph):
    ppr = paragraph._p.get_or_add_pPr()         # 取得或创建段落属性节点
    ind = ppr.find(qn("w:ind"))                 # 查找缩进节点
    if ind is None:                             # 若不存在
        ind = OxmlElement("w:ind")              # 创建缩进节点
        ppr.append(ind)                         # 挂到段落属性下
    return ind                                  # 返回缩进节点，由调用方写具体属性

# 用「字符数」设置首行缩进，这是中文排版的正确做法（厘米会随字号失准）
def set_first_line_indent_chars(paragraph, chars):
    if not chars:                               # 若未指定缩进
        return                                  # 直接返回
    ind = get_or_add_ind(paragraph)             # 取得或创建缩进节点
    ind.set(qn("w:firstLineChars"), str(int(float(chars) * 100)))   # 200 表示 2 字符

# 给段落设置左右「字符单位」缩进：公文页码的「居右空一字」「居左空一字」都靠它实现。
# 同时写字符单位（w:leftChars/rightChars，Word 认）与长度单位（w:left/right，LibreOffice 认），
# 只写其中一种会出现「Word 里对、导出 PDF 后跑偏」。
def set_side_indent_chars(paragraph, size_pt, left_chars=0, right_chars=0):
    ind = get_or_add_ind(paragraph)                             # 取得或创建缩进节点
    if left_chars:                                              # 需要左侧空出若干字
        ind.set(qn("w:leftChars"), str(int(float(left_chars) * 100)))    # 字符单位：100 表示 1 字
        ind.set(qn("w:left"), str(int(float(size_pt) * float(left_chars) * 20)))   # 长度单位：磅换算成二十分之一磅
    if right_chars:                                             # 需要右侧空出若干字
        ind.set(qn("w:rightChars"), str(int(float(right_chars) * 100)))  # 字符单位
        ind.set(qn("w:right"), str(int(float(size_pt) * float(right_chars) * 20)))  # 长度单位

# 给段落设置「悬挂缩进」的整套横向位置：左缩进 + 悬挂量（可带右缩进）。
#
# 用途是公文里那两条「回行要与上一行某字对齐」的规定：
#   §7.3.4 附件说明：「附件名称较长需回行时，应当与上一行附件名称的首字对齐」
#   §7.4.2 抄送机关：「『抄送』二字后加全角冒号和抄送机关名称，回行时与冒号后的首字对齐」
# 两处是同一个动作：左缩进 = 左空字数 + 前缀宽度（前缀＝「附件：1. 」「抄送：」），悬挂 = 前缀宽度，
# 于是首行落在「左空一字/二字」处，回行恰好停在名称首字上。
#
# 为什么单独写一个函数、而且**只写长度单位、不写字符单位**：都是实测逼出来的。
# ① 字符单位（w:leftChars 等）是按「段落默认字号的字宽」折算的，而这两处的字号往往不等于
#    默认字号（版记是 4 号、正文是 3 号），字符单位必然折算偏差 —— 实测抄送首行被推到 1.58 字处。
# ② 字符单位与 w:hanging 同时存在时，LibreOffice 会把悬挂算到**回行**上而不是首行上 ——
#    实测六种写法各导一份 PDF 逐行量位置：只写 left+hanging 首行 2.00 字/回行 6.50 字（正确），
#    同时写 hangingChars+hanging 变成首行 6.50 字/回行 11.00 字（正好把两行位置写反了）。
# 长度单位没有这两个问题，Word 与 LibreOffice 都认，所以这里是唯一一处不用字符单位的地方。
#
# 另外：OOXML 里 w:firstLine 与 w:hanging 互斥，同时写在同一段落上行为未定义，
# 所以用了悬挂缩进的段落不能再调 set_first_line_indent_chars（首行位置由「左缩进 − 悬挂」隐含给出）。
def set_hanging_layout(paragraph, size_pt, left_chars, hanging_chars, right_chars=0):
    if not hanging_chars:                       # 认不出前缀（例如正文没按「附件：」写）时退出
        return                                  # 交给调用方按普通缩进处理
    ind = get_or_add_ind(paragraph)             # 取得或创建缩进节点
    # 左缩进与悬挂都用长度单位：磅 → 二十分之一磅
    ind.set(qn("w:left"), str(int(float(size_pt) * float(left_chars) * 20)))         # 回行停靠位置
    ind.set(qn("w:hanging"), str(int(float(size_pt) * float(hanging_chars) * 20)))   # 首行往左拉回的量
    if right_chars:                             # §7.4.2 抄送机关还要右侧空一字
        ind.set(qn("w:right"), str(int(float(size_pt) * float(right_chars) * 20)))   # 右缩进，同样用长度单位

# 在段落里插入一个 Word 域（field code）。页码用 PAGE，页眉取当前章名用 STYLEREF。
# 域是「打开文档时由 Word 计算」的占位内容，所以必须写成 begin / instrText / end 三段，
# 只写文字的话就是死文本，页码不会更新、章名不会随页变化。
def add_field(paragraph, instruction, east_asian, latin, size_pt):
    run = paragraph.add_run()                   # 新建一个文本块承载域
    style_run(run, east_asian, latin, size_pt)  # 应用字体样式
    begin = OxmlElement("w:fldChar")            # 创建域开始标记
    begin.set(qn("w:fldCharType"), "begin")     # 指定类型为 begin
    instr = OxmlElement("w:instrText")          # 创建域指令节点
    instr.set(qn("xml:space"), "preserve")      # 保留空格（域指令里的空格有语义）
    instr.text = instruction                    # 指令内容，如 PAGE、STYLEREF "Heading 1"
    end = OxmlElement("w:fldChar")              # 创建域结束标记
    end.set(qn("w:fldCharType"), "end")         # 指定类型为 end
    run._element.append(begin)                  # 把开始标记加入文本块
    run._element.append(instr)                  # 把域指令加入文本块
    run._element.append(end)                    # 把结束标记加入文本块

# 在段落里插入 PAGE 域，实现自动页码
def add_page_number_field(paragraph, east_asian, latin, size_pt):
    add_field(paragraph, "PAGE", east_asian, latin, size_pt)   # PAGE 域即当前页码

# 给段落加底边框，用于模拟公文的红色分隔线
# pBdr 在 OOXML 的 pPr 里必须排在 tabs / spacing / ind / jc 之前，
# 直接 append 到末尾属于乱序：Word 可能判定文件损坏，LibreOffice 会直接不画这条线。
PPR_AFTER_PBDR = ("w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct",
                  "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd",
                  "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents",
                  "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment", "w:outlineLvl")

# 取得（或创建）段落的边框集合。一个段落只允许有一个 w:pBdr，
# 上下边框必须挂在同一个集合里；写两个 w:pBdr 属于非法 XML，LibreOffice 会直接不画线。
def get_paragraph_borders(ppr):
    borders = ppr.find(qn("w:pBdr"))                        # 先看是否已有边框集合
    if borders is not None:                                 # 已有就复用
        return borders                                      # 返回已有集合
    borders = OxmlElement("w:pBdr")                         # 创建边框集合
    for tag in PPR_AFTER_PBDR:                              # 按顺序找第一个「应该排在 pBdr 之后」的现有节点
        node = ppr.find(qn(tag))                            # 查找该节点
        if node is not None:                                # 找到了
            node.addprevious(borders)                       # 把边框插到它前面
            return borders                                  # 插入完成并返回
    ppr.append(borders)                                     # 一个都没有，说明 pBdr 排最后
    return borders                                          # 返回新建的集合

def set_paragraph_bottom_border(paragraph, color_hex, size_eighth_pt=12, space_pt=1):
    ppr = paragraph._p.get_or_add_pPr()                     # 取得或创建段落属性节点
    borders = get_paragraph_borders(ppr)                     # 取得（或创建）段落边框集合
    old = borders.find(qn("w:bottom"))                       # 若已有下边框
    if old is not None:                                      # 避免重复
        borders.remove(old)                                  # 先删掉
    bottom = OxmlElement("w:bottom")                         # 创建下边框节点
    bottom.set(qn("w:val"), "single")                        # 单线
    bottom.set(qn("w:sz"), str(size_eighth_pt))              # 线宽（八分之一磅）
    bottom.set(qn("w:space"), str(int(round(float(space_pt)))))   # 与文字的距离（磅），w:space 只接受整数
    bottom.set(qn("w:color"), color_hex.replace("#", ""))    # 边框颜色
    borders.append(bottom)                                   # 把下边框加入边框集合

# 给段落加顶边框，用于模拟版记的首条分隔线与中间分隔线
def set_paragraph_top_border(paragraph, color_hex, size_eighth_pt=8, space_pt=0):
    ppr = paragraph._p.get_or_add_pPr()                     # 取得或创建段落属性节点
    borders = get_paragraph_borders(ppr)                     # 取得（或创建）段落边框集合
    old = borders.find(qn("w:top"))                          # 若已有上边框
    if old is not None:                                      # 避免重复
        borders.remove(old)                                  # 先删掉
    top = OxmlElement("w:top")                               # 创建上边框节点
    top.set(qn("w:val"), "single")                           # 单线
    top.set(qn("w:sz"), str(int(size_eighth_pt)))            # 线宽（八分之一磅）
    top.set(qn("w:space"), str(int(round(float(space_pt)))))  # 与文字的距离（磅）
    top.set(qn("w:color"), color_hex.replace("#", ""))       # 边框颜色
    borders.append(top)                                      # 把上边框加入边框集合

# 把毫米线宽换算成 OOXML 的八分之一磅单位（w:sz 的单位）
def mm_to_eighth_pt(mm):
    return max(1, int(round(float(mm) * 72 / 25.4 * 8)))     # 1mm = 72/25.4 磅，再乘 8 得到八分之一磅

# 给段落加左边框（引文左侧那条竖线）。
# 中文与英文排版都用左侧竖线标识引文，比「多缩进两个字」清楚得多 ——
# 旧版引用只做了缩进，交出去的稿子里引文和正文长得一模一样，读者分不出哪句是引的（实测）。
def set_paragraph_left_border(paragraph, color_hex="808080", size_eighth_pt=18, space_pt=8):
    ppr = paragraph._p.get_or_add_pPr()                      # 取得或创建段落属性节点
    borders = get_paragraph_borders(ppr)                     # 取得（或创建）段落边框集合
    old = borders.find(qn("w:left"))                         # 若已有左边框
    if old is not None:                                      # 避免重复
        borders.remove(old)                                  # 先删掉
    left = OxmlElement("w:left")                             # 创建左边框节点
    left.set(qn("w:val"), "single")                          # 单线
    left.set(qn("w:sz"), str(int(size_eighth_pt)))           # 线宽（八分之一磅），18/8 ≈ 2.25pt
    left.set(qn("w:space"), str(int(round(float(space_pt)))))   # 竖线与文字的距离（磅）
    left.set(qn("w:color"), color_hex.replace("#", ""))      # 边框颜色，默认中灰
    borders.append(left)                                     # 把左边框加入边框集合
    # w:pBdr 的子元素有固定顺序（top → left → bottom → right → between → bar），
    # 顺序错了 Word 会认为文件损坏。这里按规范重排一遍，保证与已有边框共存时也合法。
    order = ["top", "left", "bottom", "right", "between", "bar"]   # 规范顺序表
    def border_rank(node):                                   # 计算某个边框节点的顺序位次
        tag = node.tag.split("}")[-1]                        # 取本地名（去掉命名空间）
        return order.index(tag) if tag in order else len(order)   # 不在表里的排最后
    for node in sorted(list(borders), key=border_rank):      # 按规范顺序遍历
        borders.append(node)                                 # 重新 append（对已有节点是移动位置）

# 按「文字 + 原文」写一个段落，把 <u>…</u> 还原成真正的下划线。
# 为什么必须走原文：解析阶段已经把标签剥成纯文本了（不剥的话标签会原样印在纸上，
# 实测输出里印着「<u>本报告数据截至…</u>」），所以到这一步只有块里带的 raw 才知道哪儿该加线。
def add_rich_paragraph(document, block, east_asian, latin, size_pt, style=None):
    raw = block.get("raw") or ""                             # 原始行（可能含下划线标签）
    if not raw:                                              # 没有下划线标签
        return document.add_paragraph(block.get("text") or "", style=style) if style \
            else document.add_paragraph(block.get("text") or "")   # 保持原有写法，不引入无谓差异
    paragraph = document.add_paragraph(style=style) if style else document.add_paragraph()   # 新建空段落
    for piece, underlined in spec_lib.split_underline(raw):   # 按标签切成若干片
        piece = spec_lib.strip_inline(piece)                  # 片内可能还夹着别的行内标记
        if not piece:                                         # 空片不写
            continue                                          # 跳过
        run = paragraph.add_run(piece)                        # 写入这一片
        style_run(run, east_asian, latin, size_pt)            # 应用字体字号
        if underlined:                                        # 该片要求下划线
            run.font.underline = True                         # 打开下划线
    return paragraph                                          # 返回段落

# 把段落锚定到「版心下边缘」的底部框架上。
# 版记必须贴在公文最后一面的版心下边缘（GB/T 9704-2012 §7.4.1），
# 靠 framePr 的 vAnchor="margin" + yAlign="bottom" 实现：锚在版心（页边距以内）区域的底部。
# framePr 在 OOXML 里有固定的元素顺序，必须插在 pStyle 之后、其余属性之前；
# 直接 append 到 pPr 末尾会让 Word 认为文件损坏。
def set_page_bottom_frame(paragraph, width_twips, height_twips, y_twips):
    ppr = paragraph._p.get_or_add_pPr()                      # 取得或创建段落属性节点
    frame = OxmlElement("w:framePr")                         # 创建框架属性节点
    # 必须给出明确的宽高：实测 LibreOffice 不渲染「auto」尺寸框架里的段落边框，
    # 版记的三条分隔线就会整条消失（Word 里没这问题，但导出 PDF 会漏）。
    frame.set(qn("w:w"), str(int(width_twips)))              # 框架宽度＝版心宽度
    frame.set(qn("w:h"), str(int(height_twips)))             # 框架高度＝版记内容高度的估算值
    frame.set(qn("w:hRule"), "atLeast")                      # 内容比估算高时允许向下撑开
    frame.set(qn("w:wrap"), "around")                        # 允许正文环绕（版记独占底部，实际不会重叠）
    frame.set(qn("w:vAnchor"), "margin")                     # 垂直锚定到版心区域
    frame.set(qn("w:hAnchor"), "margin")                     # 水平锚定到版心区域
    # 用「距版心上边缘的绝对偏移」而不是 yAlign="bottom"：
    # 版记有多行（抄送 + 印发机关和印发日期），若每行都 yAlign="bottom"，
    # 多个框架会锚在同一位置互相重叠，实测 LibreOffice 会直接不画任何边框线。
    # 改成逐行给不同的 y，框架互不重叠，三条分隔线才能画出来。
    frame.set(qn("w:y"), str(int(y_twips)))                  # 距版心上边缘的偏移（二十分之一磅）
    frame.set(qn("w:xAlign"), "center")                      # 水平居中
    style = ppr.find(qn("w:pStyle"))                         # 查找段落样式节点
    if style is not None:                                    # 若段落有样式节点
        style.addnext(frame)                                 # 插到样式节点之后，保持 OOXML 元素顺序
    else:                                                    # 没有样式节点
        ppr.insert(0, frame)                                 # 插到属性节点最前面

# 生成版记（GB/T 9704-2012 §7.4）：抄送机关、印发机关和印发日期，以及首/末粗线、中间细线。
# 版记整体贴在公文最后一面的版心下边缘，靠页面底部框架实现（见 set_page_bottom_frame）。
def add_record_section(document, spec):
    cfg = spec.get("record_section") or {}                   # 取版记配置
    if not cfg.get("enabled"):                               # 未启用则返回
        return
    east_asian = spec_lib.resolve_font(cfg.get("east_asian") or "仿宋_GB2312", cfg.get("resolved"))   # §7.4.2/§7.4.3 规定 4 号仿宋
    latin = cfg.get("latin") or "Times New Roman"            # 取西文字体
    size_pt = float(cfg.get("size_pt") or 14)                # 4 号字等于 14 磅
    thick = mm_to_eighth_pt(cfg.get("first_last_divider_mm", 0.35))   # 首末分隔线用粗线（§7.4.1）
    thin = mm_to_eighth_pt(cfg.get("middle_divider_mm", 0.25))        # 中间分隔线用细线（§7.4.1）
    copy_to = str(cfg.get("copy_to") or "").strip()          # 抄送机关；空则不排这一行
    agency = str(cfg.get("issuing_agency") or "").strip() or "〔印发机关〕"   # 印发机关，空则用占位符
    date_text = str(cfg.get("issue_date") or "").strip()     # 印发日期原文（可能是空的）
    # §7.4.3：「用阿拉伯数字将年、月、日标全，年份应标全称，月、日不编虚位（即 1 不编为 01），
    # 后加『印发』二字」—— 所以日期要与「印发」连排，写成「2026年9月16日印发」。
    # 默认值给「印发」而不是用 or 兜底：显式写成空串（date_suffix: ""）表示「这份文件不要这两个字」，
    # 那不写和没写就是两种意思，不能用 or 把空串吃掉。
    date_suffix = cfg.get("date_suffix", "印发")             # 日期后的「印发」二字
    if date_text:                                           # 用户给了真实日期
        date_text += str(date_suffix or "")                  # 按国标在日期后补「印发」二字
    else:                                                   # 没给日期
        date_text = "〔印发日期〕"                             # 用占位符；占位符不拼「印发」，免得被误当成成稿日期
    page = spec.get("page") or {}                            # 取页面配置，用于算版心尺寸
    body_width_mm = content_width_mm(spec)                   # 版心宽度（统一走 content_width_mm）
    content_height_mm = (float(page.get("height_mm") or 297) - float(page.get("margin_top_mm") or 37)
                         - float(page.get("margin_bottom_mm") or 35))   # 版心高度 = 纸高 − 上下页边距
    made = []                                                # 记录本版记的全部段落与各自高度，最后统一排位置
    # 每行能排多少个 4 号字，以及单行高度（1.2 倍字高），都用于估算框架尺寸与纵向偏移
    chars_per_line = max(1, int(body_width_mm / (size_pt / 72 * 25.4)))   # 每行字数
    line_twips = size_pt * 1.2 * 20                          # 单行高度（二十分之一磅）
    def wrapped_lines(text):                                 # 估算一段文字占几行
        return max(1, -(-len(text) // chars_per_line))       # 向上取整
    if copy_to:                                              # 有抄送机关才排这一行
        line = document.add_paragraph()                      # 新建抄送段落
        copy_text = "抄送：" + copy_to                        # 抄送整行文字（「抄送：」是惯例写法）
        run = line.add_run(copy_text)                        # 写入抄送内容
        style_run(run, east_asian, latin, size_pt)           # 应用 4 号仿宋
        # 行距必须与上面 line_twips 的估算口径（1.2 倍字高）严格一致。
        # 原来写的是 1.0「单倍行距」，而「单倍」取的是字体默认行高（Kaiti SC 实测约 1.35 倍字高），
        # 比按 1.2 倍算出来的框架高度更高 —— 抄送机关回行成两行时，第二行会溢出框架、
        # 压在下面「印发机关和印发日期」那一行上（实测渲染图确认，两行文字重叠成一团）。
        # 用固定值行距后，实际行高与框架高度一致，估算几行就是几行的位置。
        line.paragraph_format.line_spacing = Pt(size_pt * 1.2)   # 固定行距，与 line_twips 的估算口径一致
        # §7.4.2：左右各空一字；「抄送」二字后加全角冒号和抄送机关名称，回行时与冒号后的首字对齐。
        # 回行对齐用悬挂缩进（与 §7.3.4 附件说明同一套做法）：左缩进 = 空一字 + 「抄送：」前缀宽，
        # 悬挂 = 前缀宽 → 首行落回「左空一字」处，长抄送名单回行时停在冒号后的首字上。
        copy_prefix = spec_lib.display_width("抄送：") / 2.0   # 「抄送：」占几个字（3 个）
        set_hanging_layout(line, size_pt, 1 + copy_prefix, copy_prefix, right_chars=1)   # 首行左空一字、回行对齐冒号后首字
        set_paragraph_top_border(line, "000000", thick)      # 首条分隔线（粗线，在第一个要素之上）
        made.append((line, wrapped_lines(copy_text) * line_twips))   # 收进列表（含估算高度）
        # 版记各段都带框架，而 OOXML 规定「连续且框架属性相同的段落属于同一个框架」。
        # 实测 LibreOffice 把「抄送」和下面的「印发」并成一个框架后，只画最后一段的边框，
        # 首条分隔线整条消失。在两段之间插一个 1 磅高的空段落打断连续性，三条线才都能画出来。
        filler = document.add_paragraph()                    # 新建空段落（只会落在上一段之后）
        filler.paragraph_format.line_spacing = Pt(1)         # 行高固定 1 磅，肉眼几乎不可见
        filler.paragraph_format.space_before = Pt(0)         # 段前距清零
        filler.paragraph_format.space_after = Pt(0)          # 段后距清零
    line = document.add_paragraph()                          # 新建印发机关和印发日期段落
    line.paragraph_format.line_spacing = Pt(size_pt * 1.2)   # 固定行距，口径与上面抄送行、框架高度一致
    # §7.4.3：印发机关左空一字、印发日期右空一字，二者编排在同一行。
    # 左空一字用段首缩进，「印发机关 → 印发日期」之间用右对齐制表位撑开，日期正好落在右侧空一字处。
    set_side_indent_chars(line, size_pt, left_chars=1)       # 左侧空一字
    # 制表位位置是「相对版心左边缘」算的（不是相对段首缩进），所以只需减掉右侧要空的那一字；
    # 左侧那一字由段首缩进负责。写成版心宽 − 2 字会让印发日期多空一字（实测过）。
    tab_pt = (body_width_mm - size_pt / 72 * 25.4) / 25.4 * 72   # 制表位位置：版心宽 − 右侧一字
    line.paragraph_format.tab_stops.add_tab_stop(Pt(tab_pt), WD_TAB_ALIGNMENT.RIGHT)   # 右对齐制表位
    agency_run = line.add_run(agency + "\t" + date_text)     # 印发机关 + 制表符 + 印发日期
    style_run(agency_run, east_asian, latin, size_pt)        # 应用 4 号仿宋
    if copy_to:                                              # 前面已排抄送行，本行上方就是中间分隔线
        set_paragraph_top_border(line, "000000", thin)       # 中间分隔线（细线）
    else:                                                    # 没有抄送行，本行就是版记第一个要素
        set_paragraph_top_border(line, "000000", thick)      # 首条分隔线（粗线）
    set_paragraph_bottom_border(line, "000000", thick, space_pt=0)   # 末条分隔线（粗线），与版心下边缘重合
    made.append((line, line_twips))                          # 印发机关和印发日期固定占一行
    frame_width_twips = body_width_mm / 25.4 * 72 * 20     # 版心宽度换算成二十分之一磅
    # 从版心底部往上排：末条分隔线要与版心下边缘重合，所以整块版记的底边对齐版心下边缘，
    # 再按各行高度自上而下分配 y 偏移（y 是「距版心上边缘」的距离）。
    total_twips = sum(height for _, height in made)           # 版记总高度
    cursor = (content_height_mm / 25.4 * 72 * 20) - total_twips   # 版记第一行距版心上边缘的偏移
    for paragraph, height in made:                           # 逐段套上底部框架
        set_page_bottom_frame(paragraph, frame_width_twips, height, cursor)   # 排到各自的 y 上
        cursor += height                                     # 游标下移一行高度

# 计算版心宽度（毫米）。左右边距有两种登记方式，这里要都能算对：
# 单面稿写 margin_left_mm / margin_right_mm，双面书刊写 margin_inside_mm / margin_outside_mm。
# 只认前者会让书刊的版心宽度偏大（拿默认值兜底），图片一插就超出页面。
def content_width_mm(spec):
    page = spec.get("page") or {}                            # 取页面配置
    # 纸宽优先用 page_size_mm 解析（显式宽高 → page.size 名称表 → 兜底 A4），
    # 不能只看 width_mm：预设写 `size: A4` 却没写宽高的（paper-cn、thesis-cn 就是这样）
    # 会拿到 210 这个「兜底值」，跟实际出纸的 Letter 对不上，版心宽度就假了。
    width = spec_lib.page_size_mm(spec)[0]                   # 取解析出的纸宽
    width = float(width or 210)                              # 解析不到才退回 A4 兜底
    inside = page.get("margin_inside_mm")                    # 内侧边距
    outside = page.get("margin_outside_mm")                  # 外侧边距
    if inside is not None and outside is not None:           # 书刊写法：内外侧之和就是左右边距之和
        return width - float(inside) - float(outside)        # 直接相减，不必区分装订边
    left = float(page.get("margin_left_mm") or 25)           # 左边距
    right = float(page.get("margin_right_mm") or 25)         # 右边距
    return width - left - right                              # 返回版心宽度

# 给标题段落设置大纲级别。Word 的目录域（TOC）只收录有大纲级别的段落，
# 把「目录」这两个字自身设成「正文」（级别 9）它就不会自己列自己。
def set_outline_level(paragraph, level):
    ppr = paragraph._p.get_or_add_pPr()                      # 取得或创建段落属性
    outline = ppr.find(qn("w:outlineLvl"))                   # 查找已有的大纲级别节点
    if outline is None:                                      # 没有就新建
        outline = OxmlElement("w:outlineLvl")                # 创建节点
        ppr.append(outline)                                  # 挂到段落属性下
    outline.set(qn("w:val"), str(level))                     # 9 表示「正文」，不进目录

# 插入 Word 目录域（TOC）。域是「打开文档时由 Word 计算」的，
# 所以插入后 Word 里可能先是空的，按 F9（或右键→更新域）才会生成带页码的目录。
def add_toc_field(paragraph, levels, east_asian, latin, size_pt):
    add_field(paragraph, f'TOC \\o "{levels}" \\h \\z \\u', east_asian, latin, size_pt)   # TOC 域；\h 让条目可跳转
    # 域结果先放一句提示，用户打开时就知道该做什么，而不是看到一个可疑的空白。
    run = paragraph.add_run("（在 Word 里按 F9 或右键「更新域」生成目录与页码）")   # 提示文字
    style_run(run, east_asian, latin, size_pt)               # 应用字体字号

# 插入一张图片。图片按版心宽度等比缩放并居中。
# 路径是相对 Markdown 文件所在目录解析的 —— 源文件里写的是 cover/xxx.jpg 这种相对路径。
def add_image(document, block, spec, base_dir):
    src = str(block.get("src") or "")                        # 取图片路径
    path = resolve_image_path(src, base_dir)                 # 解析成真实路径（含向上回溯）
    if not os.path.exists(path):                             # 找不到文件
        print(f"警告：图片文件不存在，已跳过：{src}")           # 如实报告，不假装插入了
        return []                                            # 返回空列表表示没有插入任何段落
    cfg = spec.get("figures_tables") or {}                   # 取图表配置
    width_mm = cfg.get("image_width_mm")                     # 规格卡可以指定图片宽度
    if width_mm:                                             # 指定了就照它
        width = Mm(float(width_mm))                          # 直接用绝对宽度
    else:                                                    # 没指定
        width = Mm(content_width_mm(spec))                   # 默认铺满版心宽度（保持原始比例）
    # 图注排在图的上方还是下方由规格卡决定（中文惯例：图题在图下方）。
    # 这一项以前预设里登记了、脚本却从不读，所以永远只排在下方，写 above 也没用。
    caption_position = str(cfg.get("figure_caption_position") or "below").strip().lower()   # 图注位置
    alt = str(block.get("alt") or "").strip()                # 取替代文字
    created = []                                             # 记下本次插入的段落，供块级间距统一处理
    if alt and caption_position == "above":                  # 图注在上：必须先生成图注段落，再放图片
        created.append(add_caption_paragraph(document, alt, spec, cfg))   # 先写图注（图注本身仍按「声明了才设」的规则排版）
    paragraph = document.add_paragraph()                     # 图片要放在段落里
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER          # 图片居中
    # 正文样式是「固定值行距」，行框高度被钉死在一行文字那么高（如 15.6pt）。
    # 图片是行内元素，会跟着被裁成一条细缝 —— 实测封面被压成一条横带。
    # 图片段落必须改成单倍行距（自动行高），行框才会长到容纳整张图。
    paragraph.paragraph_format.line_spacing = 1.0            # 单倍行距，让行框跟着图片长大
    paragraph.add_run().add_picture(path, width=width)       # 插入图片并设定宽度
    created.append(paragraph)                                # 图片段落也记下来
    if alt and caption_position != "above":                  # 图注在下（默认）：图片之后写图注
        created.append(add_caption_paragraph(document, alt, spec, cfg))   # 后写图注
    return created                                           # 返回插入的段落列表

# 统一写一个图表题注段落（图注与表题共用）。
#
# 「不干预」原则同样适用于题注：规格卡写了 caption_alignment / caption_size_pt 才设，
# 没写就沿用正文的字体字号与对齐（题注只是不缩进）。这样预设里登记了才生效，
# 用户没要求时不会被脚本擅自改成居中小字。
# 唯一无条件做的一件事是把行距改成单倍 —— 正文常写「固定值 15.6pt」，
# 那个固定值会把题注的行框钉死、把字裁掉一截，这是技术故障而不是排版偏好。
def add_caption_paragraph(document, text, spec, cfg=None):
    cfg = cfg if cfg is not None else (spec.get("figures_tables") or {})   # 调用方没传就现取
    paragraph = document.add_paragraph()                     # 新建题注段落
    paragraph.paragraph_format.line_spacing = 1.0            # 单倍行距，别继承正文固定值行距
    fonts = spec.get("fonts") or {}                          # 取字体段
    body_cfg = fonts.get("body") or {}                       # 正文字体配置，作为题注的兜底来源
    # 题注可以单独声明字体（fonts.caption 槽位，collect_required_fonts 里登记为「图表注」），
    # 没声明就整槽沿用正文。注意是「整槽」而不是逐字段拼：
    # 若 caption 只写了 east_asian 而没写 resolved，绝不能去借正文的 resolved 当替代，
    # 否则「黑体」会被悄悄换成正文的「Songti SC」—— 那又是自动替身，明令禁止。
    # 实测踩过的坑：这里以前直接取 body_cfg 的原始字体名、没走 resolve_font，
    # 规格写「宋体」（本机没有）就原样写进 DOCX，LibreOffice 渲染时静默换成 PingFangHK，
    # 4 条表题的汉字整段变成黑体，而校验器只查字体资源表、查不出「列了没用到」的差别，报告全绿。
    caption_cfg = fonts.get("caption") if isinstance(fonts.get("caption"), dict) else {}   # 题注字体槽位
    if caption_cfg.get("east_asian"):                        # 题注自己声明了中文字体
        east_asian = spec_lib.resolve_font(caption_cfg.get("east_asian"), caption_cfg.get("resolved"))   # 用它自己的替代
    else:                                                    # 没声明就沿用正文槽位
        east_asian = spec_lib.resolve_font(body_cfg.get("east_asian") or "", body_cfg.get("resolved"))   # 正文也要解析替代
    latin = caption_cfg.get("latin") or body_cfg.get("latin") or "Times New Roman"   # 西文两级兜底
    body_size = float(body_cfg.get("size_pt") or 12)         # 正文字号（题注没写字号时用它）
    caption_size = cfg.get("caption_size_pt") or caption_cfg.get("size_pt")   # 题注字号：图表配置优先，其次字体槽位
    size_pt = float(caption_size) if caption_size else body_size   # 只有声明了才改字号
    raw_align = cfg.get("caption_alignment")                 # 规格卡声明的题注对齐
    if raw_align:                                            # 只有声明了才设对齐
        # 取值不合法必须报出来，不能像旧代码那样静默退回居中
        alignment, note = spec_lib.resolve_alignment(raw_align, default="center")   # 解析对齐
        if note:                                             # 规格写法有问题
            print(f"⚠ 图表题注：{note}")                       # 如实提醒，不静默兜底
        paragraph.alignment = ALIGN_MAP[alignment]           # 应用对齐
    run = paragraph.add_run(text)                            # 写入题注文字
    style_run(run, east_asian, latin, size_pt)               # 应用字体字号
    return paragraph                                         # 返回段落，调用方偶尔要改它

# 表格属性里必须排在 w:tblBorders 之后的节点（顺序抄自 ECMA-376 的 CT_TblPrBase）。
# Word 对这个顺序有要求，插错位置有的版本会直接报「文件已损坏」。
TBLPR_AFTER_BORDERS = ("w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook")   # 排在边框之后的节点名

# 单元格属性里必须排在 w:tcBorders 之后的节点（顺序同样抄自 ECMA-376 的 CT_TcPrBase）
TCPR_AFTER_BORDERS = ("w:shd", "w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark")

# 把新造的边框节点插到合法位置：排在这些「本应在我后面」的节点之前，都没有就放末尾
def insert_ordered(parent, node, successors):
    for tag in successors:                                  # 逐个找「本应排在我后面」的节点
        found = parent.find(qn(tag))                        # 在当前属性节点下找它
        if found is not None:                               # 找到了
            found.addprevious(node)                         # 插到它前面，顺序就对了
            return node                                     # 插入完成
    parent.append(node)                                     # 一个都没找到，放末尾即可
    return node                                             # 插入完成

# 设置表格边框样式：三线表只保留顶线、表头下线、底线；网格表保留全部
def set_table_borders(table, style, color_hex="000000"):
    tbl_pr = table._tbl.tblPr                              # 取得表格属性节点
    # 先把原有的同名字点摘干净，再写新的。
    # 不摘会出大问题：给别人现成的 Word 换线型时，原表格属性里本来就带着一套边框，
    # 直接添加就变成同一个节点下挂了两套边框，而 Word 只认第一套 ——
    # 实测「把全框线改成三线表，出来的还是全框线」，根因就是这两套并存。
    for old in tbl_pr.findall(qn("w:tblBorders")):          # 找出所有已存在的边框集合
        tbl_pr.remove(old)                                  # 逐个摘掉
    borders = OxmlElement("w:tblBorders")                   # 创建全新的表格边框集合
    # 定义四种边的线型，三线表模式下左右与内部竖线设为 none
    definitions = [
        ("top", "single", 12),                              # 顶线较粗
        ("left", "single" if style == "grid" else "none", 4),   # 左线
        ("bottom", "single", 12),                           # 底线较粗
        ("right", "single" if style == "grid" else "none", 4),  # 右线
        ("insideH", "single" if style == "grid" else "none", 4),  # 水平内线
        ("insideV", "single" if style == "grid" else "none", 4),  # 垂直内线
    ]
    for name, val, size in definitions:                     # 逐个构造边框元素
        element = OxmlElement(f"w:{name}")                  # 创建对应边框节点
        element.set(qn("w:val"), val)                       # 设置线型
        element.set(qn("w:sz"), str(size))                  # 设置线宽
        element.set(qn("w:space"), "0")                     # 设置间距
        element.set(qn("w:color"), color_hex)               # 设置颜色
        borders.append(element)                             # 加入边框集合
    insert_ordered(tbl_pr, borders, TBLPR_AFTER_BORDERS)    # 挂到表格属性下的合法位置

# 把 Markdown 里的相对图片路径解析成真实路径。
# 为什么不能只按「Markdown 所在目录」找：源稿的图片路径（cover/封面.jpg）是相对书稿根目录写的，
#   而规范化稿默认落在书稿同级的 build/ 子目录里 —— 只认 Markdown 所在目录的话，
#   从 build/ 里的稿子生成时图片永远找不到，封面会被静默跳过（实测）。
# 做法：从 Markdown 所在目录开始，逐级向上回溯找，取第一个真实存在的。
def resolve_image_path(src, base_dir):
    if os.path.isabs(src):                                   # 绝对路径直接用
        return src                                           # 无需回溯
    candidates = []                                          # 依次尝试的候选路径
    directory = os.path.abspath(base_dir)                    # 从 Markdown 所在目录开始
    for _ in range(3):                                       # 最多向上回溯三层，避免误撞无关目录
        candidates.append(os.path.join(directory, src))      # 记下这一层拼出来的路径
        parent = os.path.dirname(directory)                  # 上一级目录
        if parent == directory:                              # 已经到文件系统根
            break                                            # 停止回溯
        directory = parent                                   # 继续向上
    for candidate in candidates:                             # 从最近的一层开始试
        if os.path.exists(candidate):                        # 找到真实文件
            return candidate                                 # 用它
    return candidates[0]                                     # 都没找到就返回最近的一层，交给调用方报错

# 把 Markdown 的 `---` 分隔线画成 Word 里真正的横线。
# 早先这里只加一个空段落占位，等于把用户写的分隔线悄悄删掉 ——
# 渲染出来是一段空白，读者根本看不出这里原本有分隔线。
# Word 画横线的标准做法是给段落加下边框（w:pBdr/w:bottom）。
def add_horizontal_rule(document):
    paragraph = document.add_paragraph("")                     # 空段落作为横线的载体
    ppr = paragraph._p.get_or_add_pPr()                         # 取得段落属性节点
    borders = OxmlElement("w:pBdr")                             # 创建边框集合
    bottom = OxmlElement("w:bottom")                            # 只画下边框
    bottom.set(qn("w:val"), "single")                           # 单线
    bottom.set(qn("w:sz"), "6")                                 # 0.75 磅，比正文略细，不抢视线
    bottom.set(qn("w:space"), "1")                              # 线与文字之间留一点间距
    bottom.set(qn("w:color"), "auto")                           # 颜色跟随文字色，自动适配深色模式
    borders.append(bottom)                                      # 把下边框放进边框集合
    ppr.append(borders)                                         # 挂到段落属性下
    return paragraph                                            # 返回该段落，便于调用方继续调整

# 给表头行加下边框，形成三线表的中间那条线
def set_row_bottom_border(row, color_hex="000000", size_eighth_pt=6):
    for cell in row.cells:                                  # 遍历表头行的每个单元格
        tc_pr = cell._tc.get_or_add_tcPr()                  # 取得或创建单元格属性节点
        # 只动「下边框」这一项：单元格上原有的左右框线是别人写好的，不该顺手删掉。
        # 但同名的下边框必须先把旧的摘掉 —— 一个单元格属性里挂两条 w:bottom 时 Word 只认第一条，
        # 原稿本来就带下边框的话，新写的这条等于白写（实测重排后表头线粗细没变）。
        borders = tc_pr.find(qn("w:tcBorders"))             # 找现有的单元格边框集合
        if borders is None:                                 # 原来没有
            borders = OxmlElement("w:tcBorders")            # 新建一个
            insert_ordered(tc_pr, borders, TCPR_AFTER_BORDERS)   # 挂到合法位置
        for old in borders.findall(qn("w:bottom")):         # 找出已存在的下边框
            borders.remove(old)                             # 摘掉，避免同一条边写两遍
        bottom = OxmlElement("w:bottom")                    # 创建下边框
        bottom.set(qn("w:val"), "single")                   # 单线
        bottom.set(qn("w:sz"), str(size_eighth_pt))         # 线宽
        bottom.set(qn("w:space"), "0")                      # 间距
        bottom.set(qn("w:color"), color_hex)                # 颜色
        borders.append(bottom)                              # 加入边框集合
        tc_pr.append(borders)                               # 挂到单元格属性下

# 打开「镜像页边距」：双面印刷时，偶数页（背面）的左右边距自动与奇数页互换，
# 这样每一页的装订侧都能拿到较大的「内侧」边距。
# 注意：w:mirrorMargins 属于 settings.xml（CT_Settings），不是 sectPr 的子元素。
# 早先写进 sectPr 既不符合 schema，LibreOffice 也完全不理会（实测），导出 PDF 后偶数页边距不会互换。
MIRROR_MARGINS_TAG = "w:mirrorMargins"                       # 元素名，单独拎出来便于阅读

# settings.xml 里排在 w:mirrorMargins 之后的元素，顺序抄自 ECMA-376 的 CT_Settings，
# 也就是 python-docx 源文件 docx/oxml/settings.py 里那份 _tag_seq（它定义完就 del 掉了，
# 运行期取不到，所以在这里抄成常量）。插错位置 Word 会判定文件损坏，必须按序插入。
SETTINGS_AFTER_MIRROR = (
    "w:alignBordersAndEdges", "w:bordersDoNotSurroundHeader", "w:bordersDoNotSurroundFooter",
    "w:gutterAtTop", "w:hideSpellingErrors", "w:hideGrammaticalErrors", "w:activeWritingStyle",
    "w:proofState", "w:formsDesign", "w:attachedTemplate", "w:linkStyles",
    "w:stylePaneFormatFilter", "w:stylePaneSortMethod", "w:documentType", "w:mailMerge",
    "w:revisionView", "w:trackRevisions", "w:doNotTrackMoves", "w:doNotTrackFormatting",
    "w:documentProtection", "w:autoFormatOverride", "w:styleLockTheme", "w:styleLockQFSet",
    "w:defaultTabStop", "w:autoHyphenation", "w:consecutiveHyphenLimit", "w:hyphenationZone",
    "w:doNotHyphenateCaps", "w:showEnvelope", "w:summaryLength", "w:clickAndTypeStyle",
    "w:defaultTableStyle", "w:evenAndOddHeaders", "w:bookFoldRevPrinting", "w:bookFoldPrinting",
    "w:bookFoldPrintingSheets", "w:drawingGridHorizontalSpacing", "w:drawingGridVerticalSpacing",
    "w:displayHorizontalDrawingGridEvery", "w:displayVerticalDrawingGridEvery",
    "w:doNotUseMarginsForDrawingGridOrigin", "w:drawingGridHorizontalOrigin",
    "w:drawingGridVerticalOrigin", "w:doNotShadeFormData", "w:noPunctuationKerning",
    "w:characterSpacingControl", "w:printTwoOnOne", "w:strictFirstAndLastChars",
    "w:noLineBreaksAfter", "w:noLineBreaksBefore", "w:savePreviewPicture",
    "w:doNotValidateAgainstSchema", "w:saveInvalidXml", "w:ignoreMixedContent",
    "w:alwaysShowPlaceholderText", "w:doNotDemarcateInvalidXml", "w:saveXmlDataOnly",
    "w:useXSLTWhenSaving", "w:saveThroughXslt", "w:showXMLTags", "w:alwaysMergeEmptyNamespace",
    "w:updateFields", "w:hdrShapeDefaults", "w:footnotePr", "w:endnotePr", "w:compat",
    "w:docVars", "w:rsids", "m:mathPr", "w:attachedSchema", "w:themeFontLang",
    "w:clrSchemeMapping", "w:doNotIncludeSubdocsInStats", "w:doNotAutoCompressPictures",
    "w:forceUpgrade", "w:captions", "w:readModeInkLockDown", "w:smartTagType",
    "sl:schemaLibrary", "w:shapeDefaults", "w:doNotEmbedSmartTags", "w:decimalSymbol",
    "w:listSeparator",
)

def set_mirror_margins(document):
    settings_elm = document.settings.element                 # 取得 settings 部件根节点
    if settings_elm.find(qn(MIRROR_MARGINS_TAG)) is not None:   # 已经开过就不重复加
        return                                               # 直接返回
    mirror = OxmlElement(MIRROR_MARGINS_TAG)                 # 创建镜像页边距开关
    settings_elm.insert_element_before(mirror, *SETTINGS_AFTER_MIRROR)   # 插到第一个后继元素之前

# 设置页面的纸张尺寸与页边距
def setup_page(document, spec):
    page = spec.get("page") or {}                            # 取页面段
    section = document.sections[0]                           # 取第一节
    # 纸张尺寸：显式 width_mm/height_mm 优先，其次查 `page.size` 名称表（A4/A5/16K…）。
    # 以前只认显式宽高，导致写了 `size: A4` 的预设静默出成 Letter（python-docx 默认模板幅面），
    # 宽出 5.9mm、每行字数与边距比例全部跟着错，而报告上什么也不显示 —— 属于「没落实也不报错」。
    size_width_mm, size_height_mm = spec_lib.page_size_mm(spec)   # 解析纸张尺寸
    if size_width_mm and size_height_mm:                     # 两种来源有一个成立
        section.page_width = Mm(size_width_mm)               # 设置纸张宽度
        section.page_height = Mm(size_height_mm)             # 设置纸张高度
    else:                                                    # 解析不出尺寸：不静默
        print(f"⚠ 纸张尺寸未声明，已按 A4 兜底：{spec_lib.unknown_page_size_note(spec)}")
    for key, attr in [("margin_top_mm", "top_margin"), ("margin_bottom_mm", "bottom_margin")]:
        if page.get(key):                                    # 若设置了上/下边距
            setattr(section, attr, Mm(float(page[key])))     # 写入节属性
    # 首页不同（w:titlePg）：封面 / 标题页单独用一套页眉页脚，这里留空，于是首页既没有页眉也没有页码。
    # 不打开这个开关时，标题页会顶着一个「第 1 章 …」的页眉和页码 1，翻开来就知道排错了。
    if page.get("different_first_page"):                     # 规格声明了「首页不排页眉页脚」
        section.different_first_page_header_footer = True     # 打开 Word 的「首页不同」
        # 光开开关还不够：Word 与 LibreOffice 找不到「首页」页眉页脚部件时，会退回用普通那一套，
        # 首页照样印出页眉和页码。必须真的把这两个部件建出来并挂上引用，它们才是「空」而不是「没有」。
        section.first_page_header.paragraphs[0].text = ""     # 创建首页页眉部件并留空
        section.first_page_footer.paragraphs[0].text = ""     # 创建首页页脚部件并留空
    # 左右边距有两种登记方式：单面稿写「左/右」，双面书刊写「内侧/外侧」。
    # 「内侧/外侧」不能直接写进 w:pgMar —— 左页与右页的内侧是相反的两边，
    # 所以要么按装订边折算成左/右（单面），要么交给镜像页边距去逐页互换（双面）。
    inside = page.get("margin_inside_mm")                    # 内侧边距（装订侧）
    outside = page.get("margin_outside_mm")                  # 外侧边距（切口侧）
    binding = page.get("binding") or "left"                  # 装订边，默认左侧
    if inside is not None and outside is not None:           # 内外侧都登记了
        if page.get("mirror_margins"):                       # 双面印刷：交给镜像
            set_mirror_margins(document)                     # 打开镜像开关
            # 镜像模式下 Word/LibreOffice 会在偶数页自动把左右互换，
            # 所以 w:pgMar 里 left 要写「内侧」、right 要写「外侧」，由镜像去翻面。
            left_mm, right_mm = float(inside), float(outside)   # 左=内侧、右=外侧
        elif binding == "right":                             # 单面印刷且装订在右
            left_mm, right_mm = float(outside), float(inside)   # 内侧边距落在右边
        else:                                                # 单面印刷且装订在左（默认）
            left_mm, right_mm = float(inside), float(outside)   # 内侧边距落在左边
        section.left_margin = Mm(left_mm)                    # 写入左边距
        section.right_margin = Mm(right_mm)                  # 写入右边距
    else:                                                    # 没登记内外侧，退回左/右写法
        for key, attr in [("margin_left_mm", "left_margin"), ("margin_right_mm", "right_margin")]:
            if page.get(key):                                # 若设置了该边距
                setattr(section, attr, Mm(float(page[key])))  # 写入节属性
        if page.get("mirror_margins"):                       # 只写了左/右但也要求双面互换
            set_mirror_margins(document)                     # 同样打开镜像开关
# 配置正文样式（Normal），这是全文默认排版
def setup_body_style(document, spec):
    fonts = (spec.get("fonts") or {}).get("body") or {}       # 取正文字体段
    east_asian = spec_lib.resolve_font(fonts.get("east_asian", ""), fonts.get("resolved"))   # 解析中文字体
    latin = fonts.get("latin") or "Times New Roman"           # 取西文字体，默认 Times New Roman
    size_pt = fonts.get("size_pt") or 10.5                    # 取字号，默认五号
    style = document.styles["Normal"]                         # 取默认样式
    style.font.size = Pt(float(size_pt))                      # 设置字号
    style.font.name = latin                                   # 设置西文字体
    style.font.color.rgb = RGBColor(0, 0, 0)                  # 正文颜色设为纯黑，避免继承主题色
    rpr = style.element.get_or_add_rPr()                      # 取得样式字符属性
    rfonts = rpr.find(qn("w:rFonts"))                         # 查找字体节点
    if rfonts is None:                                        # 若不存在
        rfonts = OxmlElement("w:rFonts")                      # 创建字体节点
        rpr.append(rfonts)                                    # 挂到字符属性下
    rfonts.set(qn("w:ascii"), latin)                          # 设置西文字体
    rfonts.set(qn("w:hAnsi"), latin)                          # 设置高位西文字体
    rfonts.set(qn("w:eastAsia"), east_asian)                  # 设置中文字体
    clear_theme_fonts(rfonts)                                 # 清掉主题字体，否则正文字体会被主题压掉
    paragraph = spec.get("paragraph") or {}                   # 取段落段
    pf = style.paragraph_format                             # 取段落格式
    if paragraph.get("alignment") in ALIGN_MAP:               # 若指定了对齐方式
        pf.alignment = ALIGN_MAP[paragraph["alignment"]]      # 设置对齐
    if paragraph.get("space_before_pt") is not None:          # 若指定了段前距
        pf.space_before = Pt(float(paragraph["space_before_pt"]))   # 设置段前距
    if paragraph.get("space_after_pt") is not None:           # 若指定了段后距
        pf.space_after = Pt(float(paragraph["space_after_pt"]))     # 设置段后距
    # 行距写入。python-docx 的 line_spacing 对固定值用 Pt，对倍数用浮点数
    if paragraph.get("line_spacing_mode") == "exact" and paragraph.get("line_spacing_pt"):
        pf.line_spacing = Pt(float(paragraph["line_spacing_pt"]))   # 固定值行距
    elif paragraph.get("line_spacing_mode") == "multiple" and paragraph.get("line_spacing_value"):
        pf.line_spacing = float(paragraph["line_spacing_value"])    # 倍数行距
    return east_asian, latin, size_pt                         # 返回解析后的字体信息

# 正文「一个空行」的高度：唯一实现在 spec_lib（校验端 verify_output 要用同一套算法量间距，
# 两份实现迟早会算出两个数，然后报告里出现对不上的假报警）。这里只做个别名，调用处不用改。
body_line_height_pt = spec_lib.body_line_height_pt        # 别名指向公共库里的唯一实现

# 读取「块级元素」的段前段后（单位：正文空行数），换算成磅。
#
# 为什么单独立一套：正文段落靠首行缩进分段、段间距为 0（中文纸媒惯例），
# 但**表格、图片、代码块、引用块、分隔线**没有首行缩进，前后也不留空，
# 就会跟上下正文粘成一坨 —— 实测大 32 开图书稿里，表格贴上方的正文、
# 表题贴下方的标题、引用块内三段引文连成一片，整页看起来「很挤」。
# 这几类块级元素的间距属于排版必需要素，不能靠用户自己想得到，所以给默认值并打印说明。
def block_space_pt(spec, key, default_lines):
    blocks_cfg = spec.get("blocks") if isinstance(spec.get("blocks"), dict) else {}   # 取块级间距段
    raw = blocks_cfg.get(key)                              # 取这一项声明的值
    if raw is None:                                        # 没声明
        return float(default_lines) * body_line_height_pt(spec)   # 用默认值（按正文行高折算）
    try:                                                   # 值可能写错（字符串、负数）
        lines = float(raw)                                 # 尝试转成数字
    except (TypeError, ValueError):                        # 转不了
        print(f"⚠ blocks.{key} 的值「{raw}」不是数字，已按默认 {default_lines} 行处理。")   # 如实提醒
        lines = float(default_lines)                       # 退回默认值
    return max(0.0, lines) * body_line_height_pt(spec)     # 负值按 0 处理，其余按行高折算

# 配置各级标题样式
def setup_heading_styles(document, spec):
    headings = spec.get("headings") or {}                     # 取标题段
    undeclared_levels = []                                    # 没声明段前距的标题级别（用于最后统一提醒）
    for level in range(1, 7):                                 # 遍历 1 到 6 级
        # 预设的标题键名不统一（doc_title / title / chapter / level1 / h1），
        # 交给公共库统一解析，避免公文标题、书籍章标题被静默忽略
        cfg = spec_lib.resolve_heading(headings, level)        # 取该级配置
        if not isinstance(cfg, dict):                          # 没有配置则跳过
            continue                                           # 继续下一级
        style_name = f"Heading {level}"                        # Word 内置标题样式名
        if style_name not in [s.name for s in document.styles]:   # 若样式不存在
            continue                                            # 跳过
        style = document.styles[style_name]                    # 取样式对象
        size_pt = cfg.get("size_pt")                           # 取字号
        if size_pt:                                            # 若指定了字号
            style.font.size = Pt(float(size_pt))               # 设置字号
        style.font.bold = bool(cfg.get("bold", True))          # 设置字重，默认加粗
        # 显式设置标题颜色，覆盖 Word 主题色（默认标题是蓝色，公文等场景要求全黑）
        color_hex = str(cfg.get("color", "000000")).lstrip("#")   # 取颜色，默认纯黑
        try:                                                   # 颜色值可能非法
            style.font.color.rgb = RGBColor.from_string(color_hex.upper())   # 写入颜色
        except Exception:                                      # 解析失败时
            style.font.color.rgb = RGBColor(0, 0, 0)           # 退回纯黑
        east_asian = spec_lib.resolve_font(cfg.get("east_asian", ""), cfg.get("resolved"))   # 解析中文字体
        latin = cfg.get("latin") or "Times New Roman"          # 取西文字体
        rpr = style.element.get_or_add_rPr()                   # 取得样式字符属性
        rfonts = rpr.find(qn("w:rFonts"))                      # 查找字体节点
        if rfonts is None:                                     # 若不存在
            rfonts = OxmlElement("w:rFonts")                   # 创建字体节点
            rpr.append(rfonts)                                 # 挂到字符属性下
        rfonts.set(qn("w:ascii"), latin)                       # 设置西文字体
        rfonts.set(qn("w:hAnsi"), latin)                       # 设置高位西文字体
        rfonts.set(qn("w:eastAsia"), east_asian)               # 设置中文字体
        clear_theme_fonts(rfonts)                              # 清掉主题字体，否则标题字体会被主题压掉
        pf = style.paragraph_format                            # 取段落格式
        # 标题行距必须自己定死，不能留空去继承正文。
        # 实测踩过的坑：正文行距「固定值 15.6pt」写在 Normal 样式上，标题样式没写行距，
        # 于是 22pt 的标题被塞进 15.6pt 的行框 —— 标题一旦折成两行就直接重叠糊成一团
        # （页 1 那行「2026 年度华东地区城市轨道」和「交通客运量分析报告」叠在一起）。
        # 规则：规格卡显式给了 line_spacing_pt 就按它来，但小于字号时改用单倍并报警；
        #      没给就一律单倍行距（auto），单倍永远不小于字号，不会有重叠风险。
        heading_size = float(size_pt) if size_pt else 0.0      # 本级标题字号
        declared_line_pt = cfg.get("line_spacing_pt")          # 规格卡显式声明的行距
        if declared_line_pt:                                   # 声明了就按声明的来
            declared_line_pt = float(declared_line_pt)         # 转成数值
            if heading_size and declared_line_pt < heading_size:   # 固定值小于字号必然重叠
                print(f"警告：第 {level} 级标题的行距固定值 {declared_line_pt}pt 小于字号 {heading_size}pt，"
                      f"行与行会重叠，已改用单倍行距。要固定值请改成不小于字号的数值。")
                pf.line_spacing = 1.0                          # 退回单倍行距
            else:                                              # 行距够大
                pf.line_spacing = Pt(declared_line_pt)         # 用固定值
        else:                                                  # 没声明
            pf.line_spacing = 1.0                              # 默认单倍，绝不继承正文的固定值
        if cfg.get("alignment") in ALIGN_MAP:                  # 若指定对齐
            pf.alignment = ALIGN_MAP[cfg["alignment"]]         # 设置对齐
        if cfg.get("page_break_before"):                       # 若要求另起页
            pf.page_break_before = True                        # 设置段前分页
        # ── 标题的段前距与段后距 ───────────────────────────────
        # 这两项以前只有段前一项被读取，段后距**从来没有写进文件**（预设里登记了也没用）。
        # 后果是标题上边被顶死、下边紧贴正文，整页看起来「挤成一坨」。
        # 现在四种写法都支持：space_before_pt / space_before_lines / space_after_pt / space_after_lines。
        # 「空 N 行」的行高按**正文行距**换算，不按标题自身字号，否则标题越大间距越离谱。
        line_height = body_line_height_pt(spec)                # 一行的实际高度（磅）
        if cfg.get("space_before_lines"):                      # 若声明了空行数
            pf.space_before = Pt(float(cfg["space_before_lines"]) * line_height)   # 换算成磅写入段前距
        elif cfg.get("space_before_pt") is not None:           # 若直接给了磅值（0 也算声明）
            pf.space_before = Pt(float(cfg["space_before_pt"]))   # 直接写入段前距
        else:                                                  # 两种情况都没声明
            # 只记「规格卡里真的写了这一级」的级别：4~6 级常常是从上一级继承来的，
            # 把继承来的级别也报一遍，会让用户以为自己漏写了 6 处配置。
            if not cfg.get("inherited_from"):                  # 不是继承来的
                undeclared_levels.append(level)                # 记下来，最后统一提醒一次
            # 默认给「段前空一行」；另起页的章标题不需要段前空行（新页开头本来就没有上文）。
            pf.space_before = Pt(0 if cfg.get("page_break_before") else line_height)   # 写入默认段前距
        if cfg.get("space_after_lines"):                       # 若声明了段后空行数
            pf.space_after = Pt(float(cfg["space_after_lines"]) * line_height)   # 换算成磅写入段后距
        elif cfg.get("space_after_pt") is not None:            # 若直接给了磅值（0 也算声明）
            pf.space_after = Pt(float(cfg["space_after_pt"]))  # 直接写入段后距
        else:                                                  # 没声明段后距
            # 默认给「段后半行」：标题与正文之间留出可见的呼吸感，又不至于把版面撑散。
            pf.space_after = Pt(line_height * 0.5)             # 写入默认段后距
        # 标题首行缩进：默认清零，避免从正文样式继承缩进导致标题也被缩进；
        # 但公文类预设的层次标题按 GB/T 9704 要求「左空二字」，由预设的 first_line_indent_chars 指定
        heading_indent = float(cfg.get("first_line_indent_chars") or 0)   # 取该级标题要求的缩进字符数
        ppr = style.element.get_or_add_pPr()                   # 取得样式段落属性
        ind = ppr.find(qn("w:ind"))                            # 查找缩进节点
        if ind is None:                                        # 若不存在
            ind = OxmlElement("w:ind")                         # 创建缩进节点
            ppr.append(ind)                                    # 挂到段落属性下
        ind.set(qn("w:firstLineChars"), str(int(heading_indent * 100)))   # 写入字符级缩进（百分之一字符）
    # 规格卡没写标题段前距时，脚本按默认值给了间距。必须说破，否则用户不知道
    # 「这份间距是脚本默认的、不是他选的」，下次想改也不知道改哪儿。
    if undeclared_levels:                                     # 有声明的缺口
        print(f"说明：第 {'、'.join(str(level) for level in undeclared_levels)} 级标题的段前距未在规格卡里声明，"
              f"已按中文惯例给「段前空一行、段后半行」（按正文行距 {body_line_height_pt(spec):.1f}pt 折算）。"
              f"要精确控制请在规格卡的对应标题下写 space_before_pt / space_after_pt（单位磅）。")

# ─────────────────────────────────────────────────────────────
# 分节：让章从奇数页起、给前置页与正文分别编页码
#
# 为什么必须用「节」而不是拿空段落凑页数：生成的时候根本不知道哪一章会排到第几页，
# 奇偶性要等排版引擎把整篇排完才算得出来。OOXML 里唯一能表达「这一节从奇数页开始」的
# 只有分节符的 w:type，所以这个判断必须交给 Word / LibreOffice，而不是我们猜。
#
# 一个极易搞反的地方：分节符里的 sectPr 描述的是「排在它前面的那一节」，
# 而其中的 w:type 描述的是「这一节从什么样的页面开始」。
# 因此要让某一章从奇数页起，分节符要挂在「这一章的末尾」，而不是开头。
#
# w:sectPr 的子元素顺序是规定死的（type → pgSz → pgMar → … → pgNumType → … → docGrid），
# 顺序写错 Word 会判定文件损坏，所以下面按官方顺序表插入，不随手 append。
SECTION_CHILD_ORDER = (
    "headerReference", "footerReference", "footnotePr", "endnotePr", "type",
    "pgSz", "pgMar", "paperSrc", "pgBorders", "lnNumType", "pgNumType", "cols",
    "formProt", "vAlign", "noEndnote", "titlePg", "textDirection", "bidi",
    "rtlGutter", "docGrid", "printerSettings", "sectPrChange",
)

# 把节点插进 sectPr 的合法位置（不是简单 append，见上面的顺序表说明）
def insert_sectpr_child(sectpr, element):
    tag = element.tag.split("}")[-1]                      # 取本地名（去掉命名空间）
    old = sectpr.find(qn(f"w:{tag}"))                     # 同名单值节点只能有一个
    if old is not None:                                   # 已有旧的
        sectpr.remove(old)                                # 先删掉，避免重复
    rank = SECTION_CHILD_ORDER.index(tag)                 # 该节点的规定位次
    for node in list(sectpr):                             # 找第一个排在它后面的现有节点
        local = node.tag.split("}")[-1]                   # 现有节点的本地名
        if local in SECTION_CHILD_ORDER and SECTION_CHILD_ORDER.index(local) > rank:   # 确实排在后面
            node.addprevious(element)                     # 插到它前面，顺序就对了
            return                                        # 插入完成
    sectpr.append(element)                                # 没有更靠后的节点，追加到最后

# 设置这一节的起始方式（nextPage 下一页 / oddPage 下一个奇数页）
def set_section_start_type(sectpr, value):
    node = OxmlElement("w:type")                          # 创建 w:type 节点
    node.set(qn("w:val"), value)                          # 取值 nextPage 或 oddPage
    insert_sectpr_child(sectpr, node)                     # 按合法位置插入

# 设置这一节的页码格式与起始值（fmt 如 decimal / lowerRoman；start 为起始页码）
def set_section_page_number(sectpr, fmt=None, start=None):
    node = OxmlElement("w:pgNumType")                     # 创建页码类型节点
    if fmt:                                               # 指定了格式
        node.set(qn("w:fmt"), fmt)                        # 写入格式
    if start:                                             # 指定了起始值
        node.set(qn("w:start"), str(int(start)))          # 写入起始页码
    insert_sectpr_child(sectpr, node)                     # 按合法位置插入

# 在「某个元素之前」结束当前节：把分节属性挂到它前面那个段落上。
# 挂在已有段落上是 Word 的标准做法；前面若正好是表格，就只能补一个空段落来承载。
def attach_section_break(before_element, sectpr):
    previous = before_element.getprevious()               # 本节最后一个元素
    if previous is not None and previous.tag == qn("w:p"):   # 正好是段落
        ppr = previous.find(qn("w:pPr"))                  # 取段落属性
        if ppr is None:                                   # 还没有段落属性
            ppr = OxmlElement("w:pPr")                    # 新建一个
            previous.insert(0, ppr)                       # 插到段落最前面
        old = ppr.find(qn("w:sectPr"))                    # 已有分节属性
        if old is not None:                               # 有就替换掉
            ppr.remove(old)                               # 先删
        ppr.append(sectpr)                                # sectPr 必须是 pPr 的最后一个子元素
        return                                            # 挂好了
    paragraph = OxmlElement("w:p")                        # 前面不是段落，补一个空段落
    ppr = OxmlElement("w:pPr")                            # 它的段落属性
    ppr.append(sectpr)                                    # 挂上分节属性
    paragraph.append(ppr)                                 # 组装段落
    before_element.addprevious(paragraph)                 # 插到目标元素之前

# 判断某个元素之前，正文里还有没有「真正的内容」（有文字的段落、图片或表格）。
# 为什么需要：见 apply_chapter_page_starts 里「书名页分节符」那段说明 —— 空白的书稿
# 不该被判成有书名页。空段落不算内容：解析器从不产出空段落，它只会是分节符的载体。
def has_content_before(document, element):
    for node in document.element.body.iterchildren():     # 按文档顺序遍历正文子元素
        if node is element:                               # 走到目标元素
            return False                                  # 它之前没遇到任何内容
        if node.tag == qn("w:tbl"):                       # 遇到表格
            return True                                   # 表格就是内容
        if node.tag == qn("w:p"):                         # 遇到段落
            has_text = any((run.text or "").strip() for run in node.iter(qn("w:t")))   # 段落里有没有文字
            has_image = (node.find(".//" + qn("w:drawing")) is not None               # 有没有嵌入式图片
                         or node.find(".//" + qn("w:pict")) is not None)              # 有没有 VML 图片
            if has_text or has_image:                     # 有文字或图片才算内容
                return True                               # 判定为前面有内容
    return False                                          # 没找到目标元素，按「没有内容」处理

# 让每个章都从奇数页开始。
# 做法：第 i 章的分节属性挂在「第 i+1 章之前」，最后一章用正文级 sectPr ——
# 因为 sectPr 描述的是它前面那一节（见本段开头的说明）。
def apply_chapter_page_starts(document, chapter_elements):
    if not chapter_elements:                              # 没有章
        return                                            # 无事可做
    base = deepcopy(document.sections[0]._sectPr)         # 以第一节属性为模板（页边距、页眉页脚都在里面）
    body_sectpr = document.element.body.find(qn("w:sectPr"))   # 正文级 sectPr，描述最后一节
    # 第 1 章之前那道分节符，本意是「结束书名页那一节」，好让书名页与正文分别编页码。
    # 但只有书稿里真的排了书名页（章标题之前还有内容）时才需要这一刀：
    # 实测踩过的坑 —— 稿子的第一块就是章标题（报告类文稿常见），书名页根本不存在，
    # 这一刀却照样插下去，于是凭空多出一整个空白节，印出来是「只有页码 i、一个字都没有」的一页。
    if has_content_before(document, chapter_elements[0]):   # 章标题之前确实还有内容
        first_break = deepcopy(base)                      # 第 1 章之前那个分节符：用来结束书名页那一节
        set_section_start_type(first_break, "nextPage")   # 书名页之后正常翻页即可
        attach_section_break(chapter_elements[0], first_break)   # 挂在第 1 章之前
    # 章标题之前什么都没有：不插这一刀，第 1 章就是文档第一块，不会多出空白页
    for index in range(len(chapter_elements)):            # 逐章设置「从奇数页起」
        if index + 1 < len(chapter_elements):             # 还有下一章
            sectpr = deepcopy(base)                       # 复制一份属性
            set_section_start_type(sectpr, "oddPage")     # 这一节从奇数页开始
            attach_section_break(chapter_elements[index + 1], sectpr)   # 挂到下一章之前 = 本章末尾
        elif body_sectpr is not None:                     # 最后一章
            set_section_start_type(body_sectpr, "oddPage")   # 直接改正文级属性

# 数出某个元素落在第几节（0 基）。用于判断哪些节属于前置页、哪些属于正文。
def section_index_of(document, element):
    index = 0                                             # 起始为第 0 节
    for node in document.element.body.iterchildren():     # 按文档顺序遍历正文子元素
        if node is element:                               # 走到目标元素
            return index                                  # 返回当前节号
        if node.tag == qn("w:p"):                         # 是段落
            ppr = node.find(qn("w:pPr"))                  # 取段落属性
            if ppr is not None and ppr.find(qn("w:sectPr")) is not None:   # 它带着分节属性
                index += 1                                # 说明这一节到此结束，节号加一
    return index                                          # 走到最后也没遇到，按当前节号算

# 前置页与正文分别编页码，并支持「封面不编页码」。
#
# 规格卡要提供定位信息，脚本才知道刀切在哪：
#   · footer.page_number.body_start_heading  → 正文从哪个标题开始（必填，否则整项跳过）
#   · footer.page_number.front_matter.cover_end_heading → 封面到哪个标题为止（可选）
# 只有前者时，封面与前言会被算成同一节，无法只免掉封面的页码 —— 这时明确警告，
# 而不是把封面和前言混作一节悄悄糊过去（第一版就是这么错的，实测前言整页没有页码）。
#
# 返回值是「需要告诉用户的说明」列表，空列表表示一切正常。
def apply_front_matter_numbering(document, spec, body_start_element, cover_end_element):
    page_number_cfg = (spec.get("footer") or {}).get("page_number") or {}   # 取页码配置
    front = page_number_cfg.get("front_matter") or {}     # 取前置页页码规则
    body_start_at = page_number_cfg.get("body_start_at")  # 正文起始页码
    if not front and body_start_at is None:               # 规格没提前置页
        return []                                         # 不需要处理
    if body_start_element is None:                        # 规格提了，但没给正文分界
        return ["规格卡声明了前置页页码规则，却没说正文从哪个标题开始"
                "（footer.page_number.body_start_heading），无法定位分界，本次已跳过：页码仍从 1 起通排。"]
    notes = []                                            # 收集要告诉用户的说明
    cover_none = str(front.get("cover") or "").strip().lower() in ("none", "no", "无", "不编")   # 封面是否不编页码
    cover_end_heading = str(front.get("cover_end_heading") or "").strip()   # 封面到哪个标题为止
    template = document.sections[0]._sectPr               # 以第一节属性为模板
    # ① 封面单独成节（规格给了封面结束位置，且确实在正文里找到这个标题）
    cover_split = cover_none and cover_end_heading and cover_end_element is not None   # 能不能切出封面
    if cover_split:                                       # 可以切
        cover_sect = deepcopy(template)                   # 封面那一节的属性
        set_section_start_type(cover_sect, "nextPage")    # 封面之后正常翻页
        attach_section_break(cover_end_element, cover_sect)   # 在封面结束处切一刀
    elif cover_none and cover_end_heading:                # 规格写了标题名，但正文里找不到
        notes.append(f"规格里写了 front_matter.cover_end_heading=「{cover_end_heading}」，"
                     f"但正文里找不到这个标题，封面无法单独成节。")
    # ② 正文起始处切一刀
    #
    # 特例：封面结束点与正文起始点是同一个标题时（稿子没有前言/目录，封面之后直接就是正文），
    # 两刀落在同一个段落上。第二次 attach 会把第一次写进去的分节属性顶掉（同一段落只能有一个
    # sectPr），结果是封面节消失、页脚引用也被从唯一的一节上摘掉 —— 整篇页码与页眉全没了。
    # 这时只切一刀：封面节之后的那一节天然就是正文（实测 section_index_of 会算出 1，页码正常）。
    same_split_point = cover_split and body_start_element is cover_end_element   # 两刀是否落在一处
    if same_split_point:                                  # 落在一处，只保留封面那一刀
        print("说明：front_matter.cover_end_heading 与 body_start_heading 指向同一个标题，"
              "本次只在封面之后切一刀（封面之后的下一节即为正文）。")
    else:                                                 # 正常情况：切两刀
        body_sect = deepcopy(template)                    # 正文那一节的属性
        set_section_start_type(body_sect, "nextPage")     # 正文另起一页
        attach_section_break(body_start_element, body_sect)   # 切分
    # ③ 逐节设置页码格式
    body_index = section_index_of(document, body_start_element)   # 正文落在第几节
    cover_index = section_index_of(document, cover_end_element) if cover_split else None   # 封面落在第几节
    roman_names = {"roman": "lowerRoman", "lowerroman": "lowerRoman",
                   "lowerRoman": "lowerRoman", "upperroman": "upperRoman",
                   "upperRoman": "upperRoman", "decimal": "decimal"}   # 规格里可能出现的写法
    preface_fmt = roman_names.get(str(front.get("preface_toc") or "").strip(), "lowerRoman")   # 前言目录的页码格式
    sections = document.sections                          # 现在的全部节
    front_started = False                                 # 前置页的起始页码是否已经写过（只写一次）
    for index in range(len(sections)):                    # 逐节设置
        sectpr = sections[index]._sectPr                  # 该节属性
        if index >= body_index:                           # 正文及其后
            # 只有正文的第一节才写「起始页码」，后面的节必须接着数。
            #
            # 实测踩过的坑（大 32 开图书稿，14 页）：本循环原来给每个 index >= body_index
            # 的节都写了 w:start=1，而书刊每章都是一个独立的节（apply_chapter_page_starts
            # 为了「章从奇数页起」按章切节，且它在本函数之前执行），于是每章页码都从 1 重来，
            # 印出来是 1、2、1、2……页脚全是 1 —— 而校验器只查「页脚有没有 PAGE 域」，查不出重号。
            # 语义澄清：body_start_at 说的是「正文这一段从第几页起算」，是整段的起点，
            # 不是「每一节都从它起算」。
            if index == body_index:                       # 正文的第一节
                set_section_page_number(sectpr, fmt="decimal", start=int(body_start_at or 1))   # 阿拉伯数字，按规格起算
            else:                                         # 正文里的后续节（章/节分节）
                set_section_page_number(sectpr, fmt="decimal")   # 只声明十进制格式，不写 start，页码自然续接
        elif cover_index is not None and index < cover_index:   # 封面
            continue                                      # 封面不设页码格式，反正它连页脚都被摘掉了
        else:                                             # 前言、目录
            # 与正文同一个道理（见上面那段说明）：只有前置页的第一节才写「起始页码 i」，
            # 后面的前置节只声明罗马数字格式、不写 start，页码自然续接。
            # 实测踩过的坑：原来每个前置节都写 start=1，前置页只有两页时就印出两个「i」。
            if front_started:                             # 已经不是第一节前置页
                set_section_page_number(sectpr, fmt=preface_fmt)   # 只声明格式，不写起始值
            else:                                         # 前置页的第一节
                set_section_page_number(sectpr, fmt=preface_fmt, start=1)   # 罗马数字，从 1 起
                front_started = True                      # 记下起始值已经写过
    # ④ 封面不编页码：删掉封面节的页脚引用。
    # OOXML 规定没有 footerReference 的节沿用上一节的页脚，而第一节没有上一节，于是它就是空的。
    # 早期写的「断开继承 + 清空页脚段落」是错的：所有节共用同一个页脚部件，
    # python-docx 在已有引用时不会新建部件，清空等于把正文的页码一起清掉（实测复现）。
    if cover_split:
        cover_sectpr = sections[0]._sectPr                # 第一节就是封面
        for reference in cover_sectpr.findall(qn("w:footerReference")):   # 逐个页脚引用
            cover_sectpr.remove(reference)                # 删掉，封面就没有页码
        # 页眉引用也必须一起摘掉。旧代码只摘页脚，结果书名页上印着正文的页眉：
        # 实测大 32 开图书版的书名页顶部排着「第一章 …」——书名页时正文一个标题都还没有，
        # STYLEREF 域取不到东西，就取了后面最近的标题，肉眼一看就是错的。
        for reference in cover_sectpr.findall(qn("w:headerReference")):   # 逐个页眉引用
            cover_sectpr.remove(reference)                # 删掉，封面/书名页就没有页眉
    elif cover_none:                                      # 要求封面不编页码，但定位不到封面
        notes.append("规格要求「封面不编页码」，但没有 front_matter.cover_end_heading 指明封面到哪为止，"
                     "封面与前言会落在同一节里，无法只免掉封面。请补上 cover_end_heading；"
                     "本次未对封面单独免号。")
    return notes                                          # 返回说明列表

# 禁止一个表格行被切在页边界上（OOXML 的 w:cantSplit）。
#
# 为什么必须有：表格排到页面底部时，排版引擎默认允许把一行从中间切开 ——
# 上半行留在上一页、下半行挪到下一页，上一页的残段就变成「有框线、没有文字」的空行。
# 实测（大 32 开图书稿的表 2）：跨页处凭空多出一条空行，看起来像排版出错。
# 写入 w:cantSplit 后，整行要么在这一页、要么整行挪到下一页，空行消失。
# w:trPr 的子元素顺序是规定死的，cantSplit 必须排在 tlHeader 之前；重复写入属于非法 XML，
# 所以先删旧的再追加。
def forbid_row_split(row):
    try:                                                       # 行属性节点在个别版本里可能取不到
        trpr = row._tr.get_or_add_trPr()                       # 取得或创建行属性节点
    except AttributeError:                                     # 取不到就如实报告失败
        return False                                           # 调用方会累计失败行数并提醒用户
    for old_node in trpr.findall(qn("w:cantSplit")):            # 清掉可能存在的旧节点
        trpr.remove(old_node)                                  # 同一个设置只能有一份
    element = OxmlElement("w:cantSplit")                       # 创建「禁止跨页断行」节点
    element.set(qn("w:val"), "true")                           # 打开开关
    trpr.append(element)                                       # 挂到行属性下
    return True                                                # 报告成功

# 生成表格
def add_table(document, block, spec, body_font):
    rows = block["rows"]                                       # 取表格数据
    aligns = block["aligns"]                                   # 取 Markdown 对齐标记
    if not rows:                                               # 空表直接返回
        return
    cfg = spec.get("figures_tables") or {}                     # 取图表规范
    columns = max(len(row) for row in rows)                    # 计算最大列数
    # 逐列决定对齐方式：规则收在 spec_lib.resolve_column_alignments，三种载体共用一份，
    # 源文件对齐标记优先，其次是规格卡显式声明的数字列/文字列对齐，都没有就不干预。
    column_align = spec_lib.resolve_column_alignments(rows, aligns, cfg)   # 每列的数据对齐方式，空串表示不干预
    table = document.add_table(rows=0, cols=columns)           # 创建空表格
    # 表格整体在页面上的位置同样不预设：规格卡显式声明 table_alignment 才设置，否则保持 Word 默认。
    # 注意这与「单元格内文字对齐」是两件事 —— 那个由 column_align 控制。
    table_align = cfg.get("table_alignment") or ""              # 规格卡要求的表格位置，未声明则为空
    if table_align in TABLE_ALIGN_MAP:                          # 只有明确要求才写入
        table.alignment = TABLE_ALIGN_MAP[table_align]          # 应用表格整体对齐
    # 按内容估算列宽。python-docx 默认把各列设成等宽，长内容列频繁折行，看起来像没排过版。
    # 算法本身收在 spec_lib.plan_table_columns，校验脚本共用同一份，
    # 免得「生成时一套算法、校验时另一套」——那头两个脚本会得出不同结论，谁也说不清该信谁。
    east_asian, latin, _body_size_pt = body_font               # 先解包正文字体（字号稍后单独定）
    # 表格字号可以比正文小一号（书刊惯例）：表格信息密度高，小一号更省地方也更好看。
    # 规格卡没写就跟正文同号，不擅自改。
    size_pt = float(cfg.get("table_size_pt") or _body_size_pt)   # 表格实际字号
    # 可用宽度一律走 content_width_mm：它同时认得「左/右」与「内侧/外侧」两种边距写法。
    # 早先这里只认 margin_left_mm / margin_right_mm，书刊写的是内侧/外侧，于是退回按 A4 估的 16cm，
    # 表格在 140mm 的小开本上直接冲出页面右边缘（实测被裁掉半列）。
    available_cm = content_width_mm(spec) / 10                 # 版心宽度（厘米）
    column_cm, fit_info = spec_lib.plan_table_columns(rows, size_pt, available_cm)   # 计算列宽与「装不下」的预警
    if fit_info:                                               # 这张表有单元格会折行
        # 不能静默放过：表头被折成两行是肉眼一眼就能看出的难看，而且用户不知道是为什么。
        # 给出量化原因与三条出路，让他自己选，而不是我们偷偷把字缩小或把表砍掉。
        # 措辞与 verify_output.py 共用 spec_lib 里的同一份，免得「生成时这么报、校验时那么报」。
        print(f"⚠ 表格排版预警：{spec_lib.describe_table_fit_text(fit_info)}")
    table.autofit = False                                      # 关掉自动调整，否则 Word 会忽略我们算好的列宽
    # 只设置单元格宽度是不够的：Word 与 LibreOffice 在固定布局下以 tblGrid 为准，
    # 网格不改就还是等宽，长内容列照样折行。这里把网格与表宽一起写死。
    grid = table._tbl.find(qn("w:tblGrid"))                    # 取表格网格节点
    if grid is not None:                                       # 网格存在
        for col_index, col in enumerate(grid.findall(qn("w:gridCol"))):   # 逐列改宽度
            if col_index < len(column_cm):                     # 防止列数不一致
                # 1 厘米 ≈ 567 二十分之一磅。这里用四舍五入而不是截断：
                # 截断会让每一列都比算法算好的宽度窄一点点，宽度的这一丁点损失
                # 正好会把「刚好放得下的内容」挤成两行（实测：城市列的「上海」）。
                col.set(qn("w:w"), str(round(column_cm[col_index] * 567)))   # 写入列宽（twips）
    tbl_width = table._tbl.tblPr.find(qn("w:tblW"))            # 取表宽节点
    if tbl_width is not None:                                  # 节点存在
        tbl_width.set(qn("w:type"), "dxa")                     # 改成绝对宽度
        tbl_width.set(qn("w:w"), str(int(sum(column_cm) * 567)))   # 写入各列宽度之和
    # 表格线型的合法取值收在公共库里，生成端与体检端共用一份，不会各认各的。
    style_name, style_note = spec_lib.resolve_table_style(cfg.get("table_style"))   # 解析线型
    if style_note:                                             # 规格里的写法有问题
        print(f"⚠ 表格：{style_note}")                          # 当面说清，不静默兜底
    set_table_borders(table, style_name)                       # 设置边框（取值已在上一步归一化）
    breakable_rows = 0                                         # 有多少行没能设成「禁止跨页断行」
    for row_index, row_data in enumerate(rows):                # 逐行写入
        row = table.add_row()                                  # 新增一行
        cells = row.cells                                      # 取该行的单元格
        # 禁止这一行被切在页边界上（w:cantSplit）。
        # 不设的后果实测过：一张表正好排到页面底部，Word / LibreOffice 把某一行从中间切开，
        # 上半行留在上一页、下半行挪到下一页，上一页的残段就成了「有框线、没有文字」的空行。
        if not forbid_row_split(row):                          # 写入开关（极少数情况下 XML 结构不认）
            breakable_rows += 1                                 # 记下来，最后如实告知
        for col_index in range(columns):                       # 逐列写入
            value = row_data[col_index] if col_index < len(row_data) else ""   # 取单元格文本
            cell = cells[col_index]                            # 取单元格对象
            cell.width = Cm(column_cm[col_index])              # 按内容权重分配列宽
            cell.text = ""                                     # 清空默认内容
            paragraph = cell.paragraphs[0]                     # 取单元格段落
            run = paragraph.add_run(value)                     # 写入文本
            style_run(run, east_asian, latin, size_pt)         # 应用字体样式
            # 决定对齐方式。只有拿到明确来源才设置，拿不到就完全不动，保持默认。
            if row_index == 0:                                 # 表头行
                # 表头优先跟随该列的 Markdown 标记（GFM 规则里标记本就管整列，含表头）；
                # 没有标记时再看规格卡显式声明的 header_alignment；都没有则不设置。
                align = column_align[col_index] or (cfg.get("header_alignment") or "")   # 表头对齐方式，空串表示不干预
            else:                                              # 数据行
                align = column_align[col_index]                # 用该列统一的对齐方式，空串表示不干预
            if align in ALIGN_MAP:                             # 仅在有明确对齐要求时设置
                paragraph.alignment = ALIGN_MAP[align]         # 应用对齐
    if style_name == "three_line" and len(table.rows) > 0:     # 三线表需要给表头加下边框
        set_row_bottom_border(table.rows[0])                   # 给表头行加下边框
    if len(table.rows) > 0:                                    # 表格跨页时的表头重复
        # 长表格一定会被分页断开（实测 30 天菜单表断成两页），断到第二页时如果不重复表头，
        # 读者只看到一串数字，不知道哪列是什么。w:tblHeader 就是 Word 的「在各页顶端重复出现」开关。
        header_trpr = table.rows[0]._tr.get_or_add_trPr()      # 取表头行的行属性
        repeat_header = OxmlElement("w:tblHeader")             # 创建「重复表头」节点
        repeat_header.set(qn("w:val"), "true")                 # 打开开关
        header_trpr.append(repeat_header)                      # 挂到行属性下
    if breakable_rows:                                         # 有行没能设上「禁止断行」
        print(f"⚠ 有 {breakable_rows} 行未能写入「禁止跨页断行」设置，跨页处可能出现空行，请目视核对。")

# 判断页码是否需要分单双页编排：显式开关打开，或单双页要求的位置不同
def page_number_uses_odd_even(cfg):
    if cfg.get("different_odd_even"):                          # 显式要求奇偶页不同
        return True                                            # 直接采用
    odd = cfg.get("odd_page")                                  # 单页码位置
    even = cfg.get("even_page")                                # 双页码位置
    return bool(odd and even and odd != even)                  # 两者都有且不同，才需要分开编排

# 整篇文档是否要启用「奇偶页不同」。
# 页眉与页脚共用这同一个开关（w:evenAndOddHeaders 是文档级设置），
# 所以只要任意一方要求，就必须整篇打开，并且**另一方也要把单页、双页两套都写出来** ——
# 否则空着的那一侧会整片消失（实测：书刊开了偶数页页眉后，偶数页页码一起没了）。
def needs_odd_even(spec):
    footer_cfg = (spec.get("footer") or {}).get("page_number") or {}   # 取页码配置
    header_cfg = spec.get("header") or {}                              # 取页眉配置
    return page_number_uses_odd_even(footer_cfg) or bool(header_cfg.get("different_odd_even"))   # 任一方要求即打开

# 往一个页脚里写入页码：按需加左右一字线，并按给定位置对齐
def write_page_number(footer, cfg, alignment, east_asian, latin, size_pt):
    paragraph = footer.paragraphs[0]                           # 取页脚首段
    paragraph.alignment = ALIGN_MAP.get(alignment, WD_ALIGN_PARAGRAPH.CENTER)   # 设置页码位置
    # 页脚不要继承正文的固定值行距：正文行距 28pt 会把页脚行框撑高，
    # 页码就会离版心下边缘比标准要求的 7mm 更远。单倍行距让行高紧贴字号。
    paragraph.paragraph_format.line_spacing = 1.0              # 单倍行距
    # GB/T 9704-2012 §7.5：单页码居右空一字，双页码居左空一字。
    # 「空一字」是页码与版心边缘之间留出一个字宽，用字符级缩进实现。
    if alignment == "right":                                   # 居右的页码
        set_side_indent_chars(paragraph, size_pt, right_chars=1)   # 右侧空一字
    elif alignment == "left":                                  # 居左的页码
        set_side_indent_chars(paragraph, size_pt, left_chars=1)    # 左侧空一字
    dash_rule = bool(cfg.get("dash_rule"))                     # 是否要一字线
    if dash_rule:                                              # 需要一字线
        left_dash = paragraph.add_run("— ")                    # 数字左侧的一字线（紧跟一个空格）
        style_run(left_dash, east_asian, latin, size_pt)       # 应用字体字号
    # 页码数字走西文字体（style_run 会把 w:ascii 设成 latin），西文字体渲染阿拉伯数字即半角，
    # 满足 §7.5「4 号半角宋体阿拉伯数字」里的半角要求。
    add_page_number_field(paragraph, east_asian, latin, size_pt)   # 插入 PAGE 域
    if dash_rule:                                              # 需要一字线
        right_dash = paragraph.add_run(" —")                   # 数字右侧的一字线
        style_run(right_dash, east_asian, latin, size_pt)      # 应用字体字号

# 生成页脚页码
def setup_footer(document, spec, odd_even=False):
    cfg = (spec.get("footer") or {}).get("page_number") or {}  # 取页码配置
    if not cfg.get("enabled"):                                 # 未启用则返回
        return
    east_asian = spec_lib.resolve_font(cfg.get("east_asian", "宋体"), cfg.get("resolved"))   # 解析中文字体
    latin = cfg.get("latin") or "Times New Roman"              # 取西文字体（数字用它渲染即为半角）
    size_pt = cfg.get("size_pt") or 9                          # 取字号，默认小五
    section = document.sections[0]                             # 取第一节
    # GB/T 9704-2012 §7.5：一字线上距版心下边缘 7mm。
    # footer_distance 是「页面下边缘 → 页脚底边」的距离，所以要减去页脚自身高度、再减 7mm，
    # 才等于「版心下边缘之下 7mm」。页脚高度按单倍行距估算，允许 1mm 级误差。
    offset_mm = cfg.get("dash_offset_mm")                      # 取一字线距版心下边缘的距离
    margin_bottom = (spec.get("page") or {}).get("margin_bottom_mm")   # 取下页边距（即版心下边缘位置）
    if offset_mm is not None and margin_bottom:                # 两项都有才计算
        # 系数 1.5 是实测定出来的：把「页面下边缘→页脚底边」的距离换算成
        # 「一字线（取行框上沿）距版心下边缘 7mm」。系数随字体行框高低略有出入，
        # 实测误差约 0.1mm；换字体后请用 render_preview.py 重新目视核对。
        footer_height_mm = size_pt * 1.5 / 72 * 25.4           # 页脚单行高度估算：1.5 倍字高换算成毫米
        section.footer_distance = Mm(max(0.0, float(margin_bottom) - float(offset_mm) - footer_height_mm))   # 写入页脚位置
    # 页码位置的取值必须先解析再落地。
    # 旧写法是 ALIGN_MAP.get(值, 居中)，取值不认识就静默退回居中 ——
    # 实测踩过两次：报告预设写的 position: right_bottom 从来没生效过（页码一直居中）；
    # 规格文档声明支持的 outside 也从来没生效过。现在 outside 会按单双页算成具体一侧，
    # 认不出来的取值会把原值报给用户，不再悄悄兜底。
    notes = []                                                 # 需要告诉用户的说明
    if odd_even:                                               # 整篇要求单双页不同
        odd_value = cfg.get("odd_page") or cfg.get("position", "center")     # 单页码位置
        even_value = cfg.get("even_page") or cfg.get("position", "center")   # 双页码位置
        odd_align, odd_note = spec_lib.resolve_alignment(odd_value, side="odd")     # 解析单页码（外侧＝右）
        even_align, even_note = spec_lib.resolve_alignment(even_value, side="even")   # 解析双页码（外侧＝左）
        write_page_number(section.footer, cfg, odd_align, east_asian, latin, size_pt)   # 单页码页脚
        write_page_number(section.even_page_footer, cfg, even_align, east_asian, latin, size_pt)   # 双页码页脚
        for note in (odd_note, even_note):                     # 两条说明去重后登记
            if note and note not in notes:                     # 有内容且没记过
                notes.append(note)                             # 记下来
    else:                                                      # 单双页一致
        align, note = spec_lib.resolve_alignment(cfg.get("position", "center"))   # 解析页码位置
        if note:                                               # 取值有问题
            notes.append(note)                                 # 记下来
        write_page_number(section.footer, cfg, align, east_asian, latin, size_pt)   # 只写一个页脚
    for note in notes:                                         # 逐条打印
        print(f"⚠ 页码位置：{note}")                             # 不静默吞掉
    return notes                                               # 返回给调用方（build 里统一打印时已打印，这里保留返回值）

# 页眉里能写的三种内容标记（预设里就是这么写的）：
#   chapter_name → 用 STYLEREF 域取「当前页所属章的标题」，章一换页眉自动跟着换
#   book_title   → 取规格卡里的书名（header.book_title），没填时退回 meta.name 并提醒
#   none / 空    → 这一侧不写页眉
# 其它字符串一律原样写进页眉，供用户自定义。

# 往一个页眉里写内容。返回 True 表示这一侧真的写了东西，供调用方决定是否要打开奇偶页开关。
def write_header(header, token, spec, east_asian, latin, size_pt, alignment, base_dir=None):
    token = str(token or "").strip()                         # 取内容标记并去掉首尾空白
    if not token or token == "none":                         # 空或 none 表示这一侧不排页眉
        return False                                         # 报告「没写」
    paragraph = header.paragraphs[0]                         # 取页眉首段
    paragraph.alignment = ALIGN_MAP.get(alignment, WD_ALIGN_PARAGRAPH.CENTER)   # 设置页眉对齐，默认居中
    # 页眉不要继承正文的固定值行距：正文行距 28pt 会把页眉行框撑高，页眉文字远离版心上边缘
    paragraph.paragraph_format.line_spacing = 1.0            # 单倍行距
    if token in ("image", "logo"):                           # 这一侧要排图片（公司 logo 一类）
        return write_header_image(paragraph, spec, base_dir)   # 交给专门的函数处理
    if token == "chapter_name":                              # 要写「当前章名」
        # STYLEREF 域：Word/LibreOffice 会显示「当前页之前、最近一个指定样式标题」的文字。
        # 指向哪一级标题由规格卡决定：标题层级深浅不同的书，「章」可能是 Heading 1，也可能是 Heading 3。
        # 写死成 Heading 1 的话，页眉会取到书名或篇名，跟页面对不上。
        # 取值顺序：规格卡显式写的 stylerel_style > 按标题体系自动推断 > 第 1 级。
        # 光靠默认值是不够的：这份书稿把书名放在 H1、章放在 H2，实测奇数页页眉一直显示书名，
        # 因为默认的 Heading 1 抓的是书名（chapter_heading_level 就是为这件事加的）。
        style_name = str((spec.get("header") or {}).get("stylerel_style") or "").strip()   # 规格卡显式指定的样式名
        if not style_name:                                   # 没显式指定
            style_name = f"Heading {spec_lib.chapter_heading_level(spec)}"   # 按标题体系推断章在第几级
        add_field(paragraph, f'STYLEREF "{style_name}" \\* MERGEFORMAT', east_asian, latin, size_pt)   # 插入 STYLEREF 域
        return True                                          # 报告「写了」
    if token in ("book_title", "document_title"):            # 要写「书名」
        header_cfg = spec.get("header") or {}                # 取页眉配置
        text = str(header_cfg.get("book_title") or "").strip()   # 优先用用户填的书名
        if not text:                                         # 用户没填书名
            # 书名是内容不是格式，脚本不能替用户编，但也不能让偶数页页眉空着。
            # 退回规格名并明确提示，让用户知道这里需要自己填。
            text = str((spec.get("meta") or {}).get("name") or "").strip()   # 退回规格名
            print(f"提醒：规格卡没填 header.book_title，偶数页页眉暂用「{text}」。"
                  f"正式文件请把书名填进规格卡。")            # 打印提醒
        if not text:                                         # 连规格名都没有
            return False                                     # 没东西可写
        run = paragraph.add_run(text)                        # 写入书名文字
        style_run(run, east_asian, latin, size_pt)           # 应用字体字号
        return True                                          # 报告「写了」
    run = paragraph.add_run(token)                           # 其它情况按自定义文字处理
    style_run(run, east_asian, latin, size_pt)               # 应用字体字号
    return True                                              # 报告「写了」

# 在页眉里插入一张图片（例如公司 logo）。
#
# 为什么要支持：用户明确提过「页眉有人要放公司 logo，有人要放书名」，而旧版页眉只能排文字，
# 想放 logo 就只能自己在 Word 里手动插，等于 skill 没帮上忙。
# 图片路径按 Markdown 图片同样的规则解析（相对源稿目录），规格卡里写 header.image 即可；
# 高度用 header.image_height_mm 控制（默认 8mm，页眉位置有限，太大就会顶掉正文）。
# 找不到文件时如实报警并返回 False，不假装插入了。
def write_header_image(paragraph, spec, base_dir=None):
    cfg = spec.get("header") or {}                           # 取页眉配置
    src = str(cfg.get("image") or "").strip()                # 取图片路径
    if not src:                                              # 只写了 image 这个标记、没写路径
        print("⚠ 页眉要求放图片，但规格卡里没有 header.image 路径，这一侧页眉留空。")   # 说破，不静默
        return False                                         # 报告没写
    path = resolve_image_path(src, base_dir or os.getcwd())  # 解析真实路径（与正文图片同一套规则）
    if not os.path.exists(path):                             # 找不到文件
        print(f"⚠ 页眉图片不存在，已跳过：{src}（按源稿所在目录解析）")   # 如实报告
        return False                                         # 报告没写
    height_mm = cfg.get("image_height_mm") or 8              # 默认高度 8mm
    try:                                                     # 高度可能写成非法值
        height = Mm(float(height_mm))                        # 换算成 docx 的长度单位
    except (TypeError, ValueError):                          # 值非法
        print(f"⚠ 页眉图片高度「{height_mm}」不是数字，已按 8mm 处理。")   # 提醒并退回默认值
        height = Mm(8)                                       # 用默认高度
    paragraph.add_run().add_picture(path, height=height)     # 只给高度，宽度按原图比例自动缩放
    return True                                              # 报告「写了」

# 生成页眉（书刊常见：单页排章名、双页排书名）
def setup_header(document, spec, odd_even=False, base_dir=None):
    cfg = spec.get("header") or {}                           # 取页眉配置
    if not cfg or cfg.get("enabled") is False:               # 没有页眉段，或显式关掉
        return                                               # 直接返回
    # 页眉放什么由用户决定（预设里不写死）。这里只把「声明了图片路径却没写内容标记」
    # 这一种情况补成图片 —— 用户写了 header.image 显然就是要用它当页眉。
    # 可选内容：chapter_name（当前章名）/ book_title（书名、报告名、论文题目）/
    #          image（图片，如公司 logo）/ none（这一侧不排）/ 任意文字（如公司全称）。
    if str(cfg.get("image") or "").strip() and not str(cfg.get("odd_content") or "").strip() \
            and not str(cfg.get("even_content") or "").strip():   # 只给了图片路径
        cfg["odd_content"] = "image"                         # 单页也排图片
        cfg["even_content"] = "image"                        # 双页也排图片
    odd_token = cfg.get("odd_content")                       # 单页页眉内容
    even_token = cfg.get("even_content")                     # 双页页眉内容
    # 只登记了一侧时，另一侧沿用同一个内容。理由：奇偶页开关一旦打开，没写的那一侧页眉会整片消失，
    # 那是肉眼可见的缺陷，比「两侧一样」更糟。
    odd_token = odd_token or even_token                      # 单页缺内容就借用双页
    even_token = even_token or odd_token                     # 双页缺内容就借用单页
    if not str(odd_token or "").strip() and not str(even_token or "").strip():   # 两侧都没内容
        return                                               # 没有可排的东西
    east_asian = spec_lib.resolve_font(cfg.get("east_asian", "宋体"), cfg.get("resolved"))   # 解析中文字体
    latin = cfg.get("latin") or "Times New Roman"            # 取西文字体
    size_pt = cfg.get("size_pt") or 9                        # 取页眉字号，默认小五
    # 页眉对齐与页码同理：取值要先解析。outside 会按单双页算成具体一侧，
    # 认不出来的取值要报出来，不能静默退回居中（旧代码就是 get(值, 居中)）。
    raw_alignment = cfg.get("alignment") or "center"         # 规格写的页眉对齐
    alignment, alignment_note = spec_lib.resolve_alignment(raw_alignment, default="center")   # 解析成可落地的取值
    if alignment_note:                                       # 取值不合法
        print(f"⚠ 页眉对齐：{alignment_note}")                 # 如实提醒
    section = document.sections[0]                           # 取第一节
    if odd_even:                                             # 整篇要求单双页不同
        write_header(section.header, odd_token, spec, east_asian, latin, size_pt, alignment, base_dir)   # 单页页眉
        write_header(section.even_page_header, even_token, spec, east_asian, latin, size_pt, alignment, base_dir)   # 双页页眉
    else:                                                    # 单双页一致
        write_header(section.header, odd_token, spec, east_asian, latin, size_pt, alignment, base_dir)   # 只写一个页眉

# 生成公文版头（红头 + 发文字号 + 红色分隔线）
def add_masthead(document, spec):
    masthead = spec.get("masthead") or {}                      # 取版头配置
    if not masthead.get("enabled"):                            # 未启用则返回
        return
    east_asian = spec_lib.resolve_font(masthead.get("east_asian", ""), masthead.get("resolved"))   # 解析红头字体
    latin = masthead.get("latin") or "Times New Roman"         # 取西文字体
    size_pt = masthead.get("size_pt") or 42                    # 取红头字号，默认初号
    # 机关名称为空时印成显眼的占位符，而不是让红头变成孤零零的「文件」两个字。
    # 正常情况下走不到这里：build() 已经在生成前把缺项拦掉了，只有 --allow-placeholders 才放行。
    organization = str(masthead.get("organization") or "").strip() or "〔发文机关全称〕"   # 取发文机关名称，空则用占位符
    text = organization + ("文件" if masthead.get("with_word_file") else "")   # 拼接红头文字
    paragraph = document.add_paragraph()                       # 新建段落
    paragraph.alignment = ALIGN_MAP.get(masthead.get("alignment", "center"), WD_ALIGN_PARAGRAPH.CENTER)   # 居中
    # 红头字号（初号 42pt）远大于正文，若沿用 Normal 样式里的「固定值行距」，
    # 28pt 的行框装不下 42pt 的字，文字会向上溢出到页边距以外（实测天头会从 37mm 变成 29mm）。
    # 因此红头段落强制改为单倍行距，让行框跟着字号长大。
    pf = paragraph.paragraph_format                           # 取红头段落格式
    pf.line_spacing = 1.0                                     # 单倍行距（自动行高）
    # GB/T 9704-2012 §7.2.4：发文机关标志「上边缘至版心上边缘为 35mm」。
    # 段前距 = 目标偏移 − 单倍行距下文字上方多出的空白（约 0.2 倍字高，随字体略有差异）。
    # 这里只能取近似值：真正精确的空白取决于字体自身的 ascent/descent，Word 与 LibreOffice 也不一致。
    top_offset_mm = float(masthead.get("top_offset_mm") or 0)   # 取上边缘偏移，未声明则不加段前距
    if top_offset_mm > 0:                                     # 若规格声明了偏移
        gap_pt = size_pt * 0.2                                # 行框在文字上方的空白（约 0.2 字高）
        pf.space_before = Pt(max(0.0, spec_lib.mm_to_pt(top_offset_mm) - gap_pt))   # 写入段前距
    run = paragraph.add_run(text)                              # 写入红头文字
    style_run(run, east_asian, latin, size_pt)                 # 应用字体样式
    color_hex = (masthead.get("color_hex") or "#FF0000").lstrip("#")   # 取颜色值
    run.font.color.rgb = RGBColor.from_string(color_hex.upper())       # 设置红色
    doc_number = masthead.get("doc_number") or {}              # 取发文字号配置
    signer = masthead.get("signer") or {}                      # 取签发人配置（§7.2.6）
    signer_name = str(signer.get("name") or "").strip()         # 签发人姓名
    signer_enabled = bool(signer.get("enabled")) and bool(signer_name)   # 启用且真的填了姓名才算数
    # 发文字号与签发人印在同一行（§7.2.5、§7.2.6），所以两者有一个启用就要建这一段。
    # 修正的旧缺陷：这段以前只在「启用发文字号」时建，签发人那一格没有任何代码读它 ——
    # 预设登记了、规格卡能写、生成时不报错，文件里却一个字都没有。
    if doc_number.get("enabled") or signer_enabled:            # 版头需要这一行
        number_paragraph = document.add_paragraph()            # 新建段落
        # GB/T 9704-2012 §7.2.5：发文字号编排在发文机关标志下「空二行」位置。
        # 用段前距模拟空行，空行高度按正文行距（见 body_line_height_pt）。
        blank_lines_value = doc_number.get("blank_lines_above", 2)   # 取上方空行数，没写就是 2 行
        blank_lines = 2 if blank_lines_value is None else int(blank_lines_value)   # 显式写 0 表示不留空行
        if blank_lines > 0:                                    # 若需要空行
            number_paragraph.paragraph_format.space_before = Pt(blank_lines * body_line_height_pt(spec))   # 写入段前距
        # 发文字号格式：机关代字〔年份〕顺序号号
        position = "left" if doc_number.get("position") == "left" else "center"   # 上行文居左，其余居中
        number_paragraph.alignment = ALIGN_MAP.get(position, WD_ALIGN_PARAGRAPH.CENTER)   # 设置对齐
        body_size = ((spec.get("fonts") or {}).get("body") or {}).get("size_pt") or 16    # 取正文字号
        if doc_number.get("enabled"):                          # 启用发文字号才写号
            # 逐项兜底成占位符，避免印出「〔2026〕号」这种残缺号（只在 --allow-placeholders 下才会出现）。
            # agency_code_omitted 是「用户明确表示这份文件不写机关代字」的开关：机关代字属于内容项，
            # 脚本不能替用户编；但也不能因为字段空着就默默印一个占位符出来，所以两种情况分开处理。
            omitted = bool(doc_number.get("agency_code_omitted"))   # 用户是否明确不要机关代字
            agency_code = str(doc_number.get("agency_code") or "").strip()   # 机关代字
            if not agency_code and not omitted:                # 既没写代字、也没声明省略
                agency_code = "〔机关代字〕"                     # 用显眼的占位符顶上，不留空
            number_year = str(doc_number.get("year") or "").strip() or "〔年份〕"              # 年份，空则占位
            number_serial = str(doc_number.get("serial") or "").strip() or "〔顺序号〕"        # 顺序号，空则占位
            number_text = f"{agency_code}〔{number_year}〕{number_serial}号"   # 拼接发文字号
            number_run = number_paragraph.add_run(number_text)     # 写入发文字号
            style_run(number_run, east_asian, latin, body_size)    # 应用字号
            if position == "left":                             # §7.2.5：上行文的发文字号居左空一字
                set_side_indent_chars(number_paragraph, body_size, left_chars=1)   # 左侧空出一字
        if signer_enabled:                                     # §7.2.6：签发人与发文字号同行、居右空一字
            if position != "left":                             # 居中排的发文字号说明这不是上行文
                print("⚠ 签发人按 §7.2.6 只用于上行文，但规格里的发文字号是居中排（下行文）。"
                      "已照样写入，请核对是否真的需要签发人。")   # 如实提醒，不擅自改规格
            add_signer_runs(number_paragraph, signer, spec, body_size)   # 写入「签发人：姓名」
        if masthead.get("separator_line", {}).get("enabled"):  # 若启用分隔线
            # GB/T 9704-2012 §7.2.7：分隔线印在发文字号之下 4mm 处。
            # 分隔线用段落下框线实现，w:space 是「边框线到文字的距离」，按规格值换算成磅写入。
            line_cfg = masthead["separator_line"]              # 取分隔线配置
            offset_pt = spec_lib.mm_to_pt(float(line_cfg.get("offset_below_doc_number_mm") or 4))   # 4mm 换算成磅
            set_paragraph_bottom_border(number_paragraph, line_cfg.get("color_hex", "#FF0000"), space_pt=offset_pt)   # 加红色下边框

# 写入签发人（GB/T 9704-2012 §7.2.6）：
#   原文：「由『签发人』三字加全角冒号和签发人姓名组成，居右空一字，编排在发文机关标志下空二行位置。
#          『签发人』三字用 3 号仿宋体字，签发人姓名用 3 号楷体字。」
# 它和发文字号印在同一行，所以直接写进发文字号那一段；居右靠右对齐制表位实现
# （制表位按「距版心左边缘」计算，与版记印发日期的做法一致，因此只减掉右侧要空的那一字）。
# 两个字体槽位都由规格卡声明，字体会一并进入缺字体门禁 —— 不再出现「预设写了字体、生成时没人管」。
def add_signer_runs(paragraph, signer, spec, body_size):
    label_slot = signer.get("label_font") if isinstance(signer.get("label_font"), dict) else {}   # 「签发人」三字的字体槽位
    name_slot = signer.get("name_font") if isinstance(signer.get("name_font"), dict) else {}     # 姓名的字体槽位
    label_font = spec_lib.resolve_font(label_slot.get("east_asian") or "仿宋_GB2312", label_slot.get("resolved"))   # 解析「签发人」字体
    name_font = spec_lib.resolve_font(name_slot.get("east_asian") or "楷体", name_slot.get("resolved"))   # 解析姓名用字体
    size_pt = float(signer.get("size_pt") or body_size or 16)   # §7.2.6 规定 3 号字；没写就沿用正文字号
    latin = ((spec.get("fonts") or {}).get("body") or {}).get("latin") or "Times New Roman"   # 西文沿用正文槽位
    position = str(signer.get("position") or "right").strip()   # 国标是居右空一字
    if position == "right":                                     # 居右：用右对齐制表位把内容推到版心右边缘内一字
        tab_pt = (content_width_mm(spec) - size_pt / 72 * 25.4) / 25.4 * 72   # 制表位＝版心宽 − 右侧一字
        paragraph.paragraph_format.tab_stops.add_tab_stop(Pt(tab_pt), WD_TAB_ALIGNMENT.RIGHT)   # 登记右对齐制表位
        prefix = "\t"                                           # 制表符负责把后面的字推到右边
    else:                                                       # 声明了非右侧位置
        print(f"⚠ masthead.signer.position 的值「{position}」不是 right；"
              f"§7.2.6 规定签发人居右空一字，这里按紧接发文字号排。")   # 如实提醒，不静默照排
        prefix = "　"                                           # 用一个全角空格隔开，免得两段内容粘在一起
    label_run = paragraph.add_run(prefix + "签发人：")            # 「签发人」三字加全角冒号
    style_run(label_run, label_font, latin, size_pt)            # 应用 3 号仿宋
    name_run = paragraph.add_run(str(signer.get("name") or "").strip())   # 签发人姓名
    style_run(name_run, name_font, latin, size_pt)              # 应用 3 号楷体

# 公文主体要素的段落排版（GB/T 9704-2012 §7.3）。
#   §7.3.2 主送机关：编排于标题下空一行位置，居左顶格，回行时仍顶格。
#   §7.3.4 附件说明：在正文下空一行左空二字编排。
#   §7.3.5 发文机关署名与成文日期：横向位置由 spec_lib.gov_signature_layout 算出（条款原文写在那里）。
# 关键点：这几种段落一律不套正文的「首行缩进二字」——
# 修之前的表现就是它们全被当成普通正文：主送机关与成文日期缩进两字、署名跟着正文左空二字。
# 位置一律用「左空字数」表达（set_side_indent_chars），不用厘米：字号一变厘米就算不准了。
def add_subject_element(document, block, spec, body_font, element, layout):
    east_asian, latin, size_pt = body_font                   # 解包正文字体（公文要素都用 3 号仿宋）
    paragraph = add_rich_paragraph(document, block, east_asian, latin, float(size_pt))   # 建段落（下划线等行内标记照旧保留）
    paragraph.alignment = ALIGN_MAP["left"]                  # 这几种要素都从左边缘起排，不用两端对齐
    layout = layout or {}                                    # 位置计算结果可能为空（稿子里没有署名与日期）
    cfg = (spec.get("body_elements") or {}).get(element)      # 取该要素的排版配置
    cfg = cfg if isinstance(cfg, dict) else {}                # 配置缺失时按空字典处理
    lines = cfg.get("space_before_lines")                     # 该要素上方的空行数（国标里的「空一行」）
    if lines:                                                 # 声明了才加；写 0 表示不空
        paragraph.paragraph_format.space_before = Pt(float(lines) * body_line_height_pt(spec))   # 按正文行高折算成磅
    indent = cfg.get("first_line_indent_chars")               # 该要素的首行缩进字数（0＝顶格）
    if element == "attachment":                                # §7.3.4：附件说明（下面这段是回行对齐，不只是缩进）
        # §7.3.4 最后一句：「附件名称较长需回行时，应当与上一行附件名称的首字对齐」。
        # 附件名往往很长（「城市防汛隐患排查整治工作领导小组成员名单」之类），一定会回行；
        # 只做「左空二字」的话，回行文字会顶到版心左边缘、与「附件」二字齐平，看不出哪一行才是名称。
        prefix_chars = spec_lib.attachment_prefix_chars(block.get("text"))   # 「附件：」+ 顺序号占几个字
        base = float(indent or 0)                              # 首行左空字数（预设里是 2）
        if prefix_chars:                                       # 认出了「附件：」前缀，才算得出对齐点
            set_hanging_layout(paragraph, float(size_pt), base + prefix_chars, prefix_chars)   # 首行左空二字、回行对齐附件名首字
        elif indent:                                           # 认不出前缀（正文没按「附件：」写）时退回普通缩进
            set_first_line_indent_chars(paragraph, indent)      # 只做首行缩进，至少不会比原来更差
    elif indent:                                               # 其余要素：只有声明了非零值才写缩进
        set_first_line_indent_chars(paragraph, indent)          # 写入字符级缩进（与厘米无关，字号变了也不失准）
    if element == "signature":                                # §7.3.5：发文机关署名
        set_side_indent_chars(paragraph, float(size_pt), left_chars=layout.get("signature_left_chars") or 0)   # 写入左空字数
    elif element == "date":                                   # §7.3.5：成文日期
        set_side_indent_chars(paragraph, float(size_pt), left_chars=layout.get("date_left_chars") or 0)   # 写入左空字数
    # 主送机关两项都是 0（空行由 space_before_lines 给、缩进为 0 即顶格），这里自然什么都不加。
    return paragraph                                          # 返回段落，调用方偶尔要改它

# 表题段长什么样：交给公共库 spec_lib.is_caption_text 判断（题注识别规则的唯一出处），
# 校验脚本核对「题在表上还是表下」时用的是同一份规则，不会出现两边口径不一致。
def is_table_caption(block):
    if block.get("type") != "paragraph":                       # 只有普通段落才可能当题注
        return False                                           # 标题、表格、图片都不算
    return spec_lib.is_caption_text(block.get("text"))         # 交给公共库按统一规则判定

# 按规格卡把表题排到表格的上方或下方。
#
# 为什么必须在生成之前、按块序列处理：源稿里的表题就是一个普通段落（「表 1　八市…」），
# 表题写在表格下方还是上方，parse_markdown_blocks 无从知道我们的意图 ——
# 它只按出现顺序切块。而 add_table 只看得到表格块，改不了它前后段落的先后。
# 所以正确的位置是这里：在块序列上把题注段摘出来，按规格插到表格的上方或下方。
#
# 注意：不做这一步的表题会退化成普通正文段（带首行缩进、正文字号），
# 既不好看，也不符合「题注比正文小一号、可居中」的常规。
def reorder_table_captions(blocks, spec):
    cfg = spec.get("figures_tables") or {}                     # 取图表配置
    declared = str(cfg.get("table_caption_position") or "").strip().lower()   # 规格声明的表题位置
    position = declared                                         # 实际采用的位置
    if declared and declared not in ("above", "below"):         # 写了但不合法
        print(f"⚠ 规格里的 figures_tables.table_caption_position=「{declared}」不是合法值"
              f"（只支持 above / below），本次保持源稿里表题原来的位置不动。")
        position = ""                                          # 不合法＝不干预，保持源稿顺序
    # 规格卡没声明位置时 **不重排**：源稿把表题写在哪就留在哪。
    # 这与本项目「没要求就不干预」的原则一致 —— 免得用户只是想让文字小一号居中，
    # 结果表题被从表下挪到了表上。
    marked = 0                                                 # 找到几张表的表题
    for index, block in enumerate(blocks):                     # 逐块扫描
        if block.get("type") != "table":                       # 只关心表格
            continue                                           # 其余跳过
        for neighbour in (index - 1, index + 1):               # 紧邻表格的前一段与后一段
            if 0 <= neighbour < len(blocks) and is_table_caption(blocks[neighbour]):   # 是题注段
                blocks[neighbour]["table_caption"] = True      # 打上标记，渲染时按题注排版
                marked += 1                                    # 计数
                break                                          # 一张表只认一个题注
    if not marked:                                             # 一张表的题注都没找到
        return blocks                                          # 原样返回，不做无用功
    result = []                                                # 重排后的块序列
    for index, block in enumerate(blocks):                     # 再扫一遍，按位置摆放
        if block.get("table_caption") and position:             # 题注段且规格要求重排：挪到表格处统一处理
            continue                                           # 这里先跳过，避免重复输出
        if block.get("type") == "table":                       # 遇到表格
            caption = None                                     # 它对应的题注
            for neighbour in (index - 1, index + 1):           # 前后各看一段
                if 0 <= neighbour < len(blocks) and blocks[neighbour].get("table_caption"):   # 找到题注
                    caption = blocks[neighbour]                # 记下
                    break                                      # 够了
            if caption is not None and position == "above":    # 题在表上
                result.append(caption)                         # 先放题注
            result.append(block)                               # 再放表格
            if caption is not None and position == "below":    # 题在表下
                result.append(caption)                         # 表格之后放题注
            continue                                           # 这一块处理完了
            # 位置未声明（position 为空）时，题注块会在它自己那一轮被原样追加，
            # 这里不做任何搬运 —— 既不重复输出，也不改变源稿顺序。
        result.append(block)                                   # 其余块原样保留
    return result                                              # 返回重排结果

# 把段前距或段后距写到某个段落上，只在「比现有间距更大」时才写。
#
# 为什么取最大值而不是直接覆盖：这里的块级间距是「最小间隔」，不是强制值。
# 表格上方如果正好是个标题（它自己的段后距可能空了一整行），覆盖会把这个标题
# 跟正文的间距改小，等于按用户没要求的方向改动版面。取最大值则只补不足、不收多余。
def set_paragraph_space(paragraph, attribute, pt):
    if paragraph is None or pt <= 0:                       # 没段落或不需要间距
        return                                             # 什么都不做
    target = float(pt)                                     # 想要达到的间距
    if attribute == "space_before":                        # 段前距要扣掉上一段已有的段后距
        # Word 与 LibreOffice 都会把「上一段的段后距 + 本段的段前距」相加，
        # 所以两边各写半行就变成整整一行 —— 实测两段紧挨的引用各写 0.5 行后被撑成 1 行，
        # 同一段引文看起来像断开的两块。这里把上一段已经给出的量扣掉，保证最终间隔就是目标值。
        target = max(0.0, target - paragraph_direct_space_pt(previous_paragraph_element(paragraph._p), "after"))   # 扣掉上一段已有的段后距
    current = getattr(paragraph.paragraph_format, attribute)   # 段落自己已有的间距（不读样式继承值）
    existing = current.pt if current is not None else 0.0  # 没写过就是 0
    if target > float(existing):                           # 只有更大才写
        setattr(paragraph.paragraph_format, attribute, Pt(target))   # 写入段前距或段后距

# 读某个段落元素自己写的段前距或段后距（磅）。kind 取 "before" 或 "after"；没写或写坏都返回 0。
# 只读段落自己写的值，不追样式继承 —— 块级间距是直接写在段落上的格式，与样式值的叠加由排版引擎负责；
# 这里只关心「这条缝上前面已经出过多少间距」，免得两边各写半行被引擎加成整整一行。
def paragraph_direct_space_pt(paragraph_element, kind):
    if paragraph_element is None:                          # 没有这个段落
        return 0.0                                         # 没有可叠加的间距
    ppr = paragraph_element.find(qn("w:pPr"))              # 取该段落的属性节点
    spacing = ppr.find(qn("w:spacing")) if ppr is not None else None   # 取间距节点
    if spacing is None:                                    # 没写间距
        return 0.0                                         # 视为 0
    raw = spacing.get(qn(f"w:{kind}"))                     # 取想要的属性值（二十分之一磅）
    try:                                                   # 值可能缺失或非法
        return max(0.0, float(raw) / 20.0)                 # 换算成磅
    except (TypeError, ValueError):                        # 缺失或非法
        return 0.0                                         # 视为 0

# 取一个段落元素（w:p）里的纯文字，用于判断它是不是题注。
def paragraph_element_text(paragraph_element):
    return "".join(node.text or "" for node in paragraph_element.iter(qn("w:t")))   # 把全部 w:t 拼起来

# 取某个正文元素前面「紧邻」的段落元素；遇到表格就停手，返回 None。
#
# 为什么遇到表格要停：表格是块级屏障，它两边的段落并不是彼此的邻居。
# 实测踩过：表题在表格下方时，去找「题注的上一段」会越过表格取到表格上方的正文，
# 于是把那段已有 0.5 行的段后距当成「这条缝上已经出过的间距」扣掉，
# 题注与表格之间的小空（0.3 行）被算成 0 而没写进去。
# 其余非段落节点（书签、修订标记、分节属性等）不是内容，直接跳过继续往前找。
def previous_paragraph_element(element):
    node = element.getprevious()                           # 取前一个兄弟节点
    while node is not None:                                # 一直往前找
        if node.tag == qn("w:p"):                           # 是段落
            return node                                    # 找到了
        if node.tag == qn("w:tbl"):                         # 是表格
            return None                                    # 表格挡住，不算相邻
        node = node.getprevious()                          # 其它节点跳过，继续往前
    return None                                            # 走到头也没找到

# 取某个正文元素后面「紧邻」的段落元素；同样遇到表格就停手，返回 None。
def next_paragraph_element(element):
    node = element.getnext()                               # 取后一个兄弟节点
    while node is not None:                                # 一直往后找
        if node.tag == qn("w:p"):                           # 是段落
            return node                                    # 找到了
        if node.tag == qn("w:tbl"):                         # 是表格
            return None                                    # 表格挡住，不算相邻
        node = node.getnext()                              # 其它节点跳过，继续往后
    return None                                            # 走到头也没找到

# 把段落元素包成 python-docx 的 Paragraph，方便直接设段前段后。
def wrap_paragraph(document, element):
    if element is None:                                    # 没有段落
        return None                                        # 返回空
    return Paragraph(element, document._body)              # 用正文作为父容器包一层

# 给块级元素补段前段后，并让题注贴住它标注的表/图。
#
# 为什么必须做（实测现象，大 32 开图书稿）：
#   · 表格与它上方的正文之间是 0 间距，表格像贴上去的；
#   · 表题与下一个标题之间也是 0 间距，「表 2 线路制式结构」直接顶住「2.2 高峰断面运能」；
#   · 代码块、引用块、分隔线同样四面贴死，引用块内的三段引文连成一片（引文没有首行缩进）。
# 这一条是「段前段后仍然没解决」的真正根因：以前只给标题算了段前段后，其它块级元素一个都没算。
#
# 实现要点：表格本身没有段落可以承载间距，所以表格的间距写在它紧邻的段落上；
# 紧邻的是题注时，题注只留「小空」（贴住表/图），对外的空改由题注外侧那一段承担。
def apply_block_spacing(document, spec, groups):
    before_pt = block_space_pt(spec, "space_before_lines", 0.5)   # 块级元素与上文之间的空（默认半行）
    after_pt = block_space_pt(spec, "space_after_lines", 0.5)     # 与下文之间的空（默认半行）
    gap_pt = block_space_pt(spec, "caption_gap_lines", 0.3)       # 题注与它标注的表/图之间的空（默认 0.3 行）
    if not (isinstance(spec.get("blocks"), dict) and spec.get("blocks")):   # 规格卡没声明块级间距
        # 与标题间距同样的处理：用默认值，但必须说破这是脚本默认、不是用户选的。
        print(f"说明：规格卡没写块级间距，本次按默认值给出（块前 {before_pt / body_line_height_pt(spec):g} 行、"
              f"块后 {after_pt / body_line_height_pt(spec):g} 行、题注贴表 {gap_pt / body_line_height_pt(spec):g} 行）。"
              f"要改就在规格卡的 blocks 段里写 space_before_lines / space_after_lines / caption_gap_lines。")
    body = document.element.body                            # 取正文容器
    for table_element in body.iter(qn("w:tbl")):             # 逐张表格
        above = previous_paragraph_element(table_element)    # 表格上一个段落
        below = next_paragraph_element(table_element)        # 表格下一个段落
        above_caption = above is not None and spec_lib.is_caption_text(paragraph_element_text(above))   # 上面是题注
        below_caption = below is not None and spec_lib.is_caption_text(paragraph_element_text(below))   # 下面是题注
        if above_caption:                                    # 题注在表上
            set_paragraph_space(wrap_paragraph(document, above), "space_after", gap_pt)   # 题注贴住表格
            # 对外的空落在题注更外侧那一段上，否则题注与上文之间是 0 间距
            set_paragraph_space(wrap_paragraph(document, previous_paragraph_element(above)), "space_after", before_pt)
        else:                                                # 表上没有题注
            set_paragraph_space(wrap_paragraph(document, above), "space_after", before_pt)   # 由上一段承担表前的空
        if below_caption:                                    # 题注在表下
            set_paragraph_space(wrap_paragraph(document, below), "space_before", gap_pt)   # 题注贴住表格
            set_paragraph_space(wrap_paragraph(document, next_paragraph_element(below)), "space_before", after_pt)
        else:                                                # 表下没有题注
            set_paragraph_space(wrap_paragraph(document, below), "space_before", after_pt)   # 由下一段承担表后的空
    for group in groups:                                     # 逐组处理图片/代码块/引用块/分隔线
        paragraphs = [item for item in group["paragraphs"] if item is not None]   # 该组包含的段落
        if not paragraphs:                                   # 空的组
            continue                                         # 跳过
        set_paragraph_space(paragraphs[0], "space_before", before_pt)   # 首段承担块前的空
        set_paragraph_space(paragraphs[-1], "space_after", after_pt)    # 末段承担块后的空
        if group["kind"] == "quote":                         # 引用块
            # 引文没有首行缩进，段与段之间再不留空就分不出是几段（实测三段引文连成一片）。
            # 末段的段后距与上面那次写入同值，重复设置无副作用。
            for paragraph in paragraphs:                     # 逐段
                set_paragraph_space(paragraph, "space_after", after_pt)   # 段后留空，兼作块后的空
        elif group["kind"] == "image":                        # 图片（图片段落与它的题注同组）
            for index, paragraph in enumerate(paragraphs):    # 逐段看是不是题注
                if not spec_lib.is_caption_text(paragraph_element_text(paragraph._p)):   # 不是题注（就是图片那一段）
                    continue                                 # 跳过
                if index == 0:                               # 题注在图片上方
                    set_paragraph_space(paragraph, "space_after", gap_pt)    # 朝图片那一侧留小空
                else:                                        # 题注在图片下方
                    set_paragraph_space(paragraph, "space_before", gap_pt)   # 朝图片那一侧留小空


# 主流程：读取 Markdown 与规格卡，生成 DOCX
def build(spec_path, input_path, output_path, allow_placeholders=False, normalize=False,
          allow_flat=False):
    spec = spec_lib.load_spec(spec_path)                       # 读取规格卡
    # 生成前先拦字体：规格要求的中文字体本机没有，又没由用户指定替代，就直接中止。
    # 以前这里会「兼容档」自动挑一个近似的字体顶上，结果字体被静默换掉、用户拿到手才发现，
    # 所以现在改成硬拦：要么装字体，要么用户显式在规格卡里写 resolved。
    font_block = spec_lib.font_block_message(spec)             # 计算缺字体说明
    if font_block:                                             # 有缺失字体
        print(font_block, file=sys.stderr)                     # 打印完整的缺字体说明与两条路
        return 4                                               # 用独立退出码 4 表示「字体缺失」
    # 生成前先拦公文版头与版记的必填项。缺了机关名称/机关代字/顺序号就生成，
    # 红头会变成光秃秃的「文件」两个字、发文字号会变成「〔2026〕号」，而且不报错 ——
    # 这种半成品交到用户手里比报错更糟，所以默认直接中止，只有用户明确要「待补稿」时才放行。
    missing = (spec_lib.masthead_missing_fields(spec)           # 版头缺失的必填项
               + spec_lib.record_section_missing_fields(spec))  # 加上版记缺失的必填项
    if missing:                                                # 有缺项
        if not allow_placeholders:                             # 默认不放行
            print("生成中止：公文版头/版记还缺必填项，缺一项都出不了合格的文件。", file=sys.stderr)   # 说明中止原因
            for item in missing:                               # 逐项列出缺什么、怎么补
                print(f"  - {item['label']}（{item['path']}）：{item['hint']}", file=sys.stderr)
            print("为什么不让生成：红头、发文字号、版记是公文成立的要素，脚本不会替你编，"
                  "编错了出的是事故。请先向用户逐项问清并写进规格卡。", file=sys.stderr)
            print("确实要一份留占位符的练习稿/待补稿时，加 --allow-placeholders 再跑。", file=sys.stderr)
            return 3                                           # 用独立退出码 3 表示「规格不完整」
        print("警告：版头/版记必填项为空，将按占位符生成。这份只能当练习稿或待补稿，不能当正式文件用。")   # 放行时也要说清
        for item in missing:                                   # 逐项提示哪些是占位符
            print(f"  占位 - {item['label']}（{item['path']}）")   # 提示缺失项
    markdown_text = spec_lib.read_markdown(input_path, normalize)   # 读取源文件；--normalize 时在内存里先清洗一遍
    # 图片（正文插图与页眉 logo）的相对路径都以源稿所在目录为基准，所以提前算出来。
    base_dir = os.path.dirname(os.path.abspath(input_path))    # Markdown 所在目录
    wrap_warnings = []                                         # 标题折行的预警，全部收集完再统一打印
    # 块级元素分组：图片、代码块、引用块、分隔线各自成组，渲染完统一补段前段后。
    # 表格不放进来 —— 表格是 w:tbl 元素、没有段落承载间距，统一在 apply_block_spacing 里扫出来处理。
    block_groups = []                                          # 元素形如 {"kind": ..., "paragraphs": [...]}
    blocks = spec_lib.parse_markdown_blocks(markdown_text)     # 用公共解析器切成块（DOCX 输出纯文本，默认剥掉行内标记）
    # 结构闸门：稿子没有层级（或连分段都没有）时，先停下来跟用户确认结构，不要生成。
    # 为什么放在生成的最前面：结构是骨架，骨架没定就排版，标题会退化成正文段落，
    # 产出的是「一整篇没有层次的文档」，用户只能推倒重来 —— 反复生成最费时间也最费 token。
    # 用户明确说过「就是不要标题」时才用 --allow-flat 放行。
    structure = spec_lib.source_structure_report(blocks)       # 先做结构体检
    if structure["needs_confirmation"] and not allow_flat:     # 需要确认结构且没有放行
        print(spec_lib.describe_structure(structure), file=sys.stderr)   # 先报事实（标题几个、正文几段、多少字）
        print("⛔ 已停止生成：这份稿子需要先跟用户确认结构。", file=sys.stderr)   # 明确说破
        print("   建议：跑 scripts/structure_check.py 拿到待确认清单，逐条问过用户、"
              "按确认结果补好层级后再生成；用户确认「就是不要标题」时加 --allow-flat 放行。",
              file=sys.stderr)                                  # 给出可执行的下一步
        return 5                                               # 退出码 5＝结构未确认
    blocks = reorder_table_captions(blocks, spec)              # 按规格把表题挪到表格上方或下方，并标记为题注段
    # 公文主体要素：按预设声明的形态给段落打标签（主送机关/附件说明/发文机关署名/成文日期），
    # 再算出署名与成文日期的横向位置。没声明 structure_rules.detect_elements 的体裁（书籍、论文）
    # 一律不打标签，因此这段代码对它们完全无影响 —— 符合「规格没要求就不干预」。
    blocks, element_counts = spec_lib.label_preset_elements(blocks, spec)   # 打标签（就地写入 block["preset_element"]）
    if element_counts:                                         # 识别到了要素才需要往下算
        print("公文要素识别：" + "、".join(f"{spec_lib.ELEMENT_LABELS.get(key, key)} {count} 处"
                                          for key, count in element_counts.items()))   # 让用户看到识别结果，可核对
    signature_text = next((item.get("text") or "" for item in blocks
                           if item.get("preset_element") == "signature"), "")   # 署名的文字，用于算横向位置
    date_text = next((item.get("text") or "" for item in blocks
                      if item.get("preset_element") == "date"), "")   # 成文日期的文字，同上
    element_layout = (spec_lib.gov_signature_layout(signature_text, date_text, spec)
                      if (signature_text or date_text) else {})   # 署名与日期的左空字数
    for note in element_layout.get("notes") or []:             # 位置计算过程中的提醒
        print(f"⚠ {note}")                                      # 逐条说破，不静默兜底
    # 公文缺主送机关/署名/成文日期就不成立（预设的 required_elements 声明了这一点），
    # 但脚本不能替用户编内容，所以只报不改：让用户判断是原稿真没写，还是写法与形态不符。
    # 注意 required_elements 是规格卡的**顶层**键（与 structure_rules 平级），不是它的子键 ——
    # 写错层级会让这段提醒静默不执行：稿子里缺要素，生成时一声不响。
    for entry in spec.get("required_elements") or []:      # 逐项核对预设声明的体裁门槛
        key = entry.get("key") if isinstance(entry, dict) else entry   # 兼容字典与字符串两种写法
        if key in ("recipient", "signature", "date") and not element_counts.get(key):   # 这一项一处都没识别到
            print(f"⚠ 稿子里没有识别到{spec_lib.ELEMENT_LABELS.get(key, key)}。按国标这三项缺一不可，"
                  f"请确认是原稿没写，还是写法与形态不符（如署名不在文末三行内）。")   # 提醒用户判断
    document = Document()                                      # 新建文档
    setup_page(document, spec)                                 # 设置页面
    body_font = setup_body_style(document, spec)               # 配置正文样式
    setup_heading_styles(document, spec)                       # 配置标题样式
    odd_even = needs_odd_even(spec)                            # 统一判断是否要分单双页（页眉页脚共用同一个开关）
    if odd_even:                                               # 需要分单双页
        document.settings.odd_and_even_pages_header_footer = True   # 打开文档级开关（w:evenAndOddHeaders）
    setup_footer(document, spec, odd_even)                     # 配置页脚页码
    setup_header(document, spec, odd_even, base_dir)           # 配置页眉（若配置了）
    add_masthead(document, spec)                               # 生成版头（若配置了）
    paragraph_cfg = spec.get("paragraph") or {}                # 取段落配置
    headings = spec.get("headings") or {}                      # 取标题配置（标题折行核对要用字号）
    indent_chars = paragraph_cfg.get("first_line_indent_chars")   # 取首行缩进字符数
    indent_mode = paragraph_cfg.get("indent_mode", "first_line")   # 取缩进模式
    east_asian, latin, size_pt = body_font                     # 解包正文字体
    toc_cfg = spec.get("toc") or {}                            # 取目录配置
    toc_heading = str(toc_cfg.get("source_heading") or "").strip()   # 哪个标题下面挂的是手写目录
    toc_skip_level = 0                                         # 正在跳过的手写目录块：记录该标题的层级，0 表示没在跳
    # 分节要用到的两个收集器：章标题段落、正文起始标题段落。
    # 为什么要等到最后再统一分节：分节属性描述的是「它前面那一节」，
    # 设置第 i 章的起始方式时必须知道第 i+1 章在哪，所以只能先记下来、最后统一处理。
    chapter_level = spec_lib.chapter_heading_level(spec)       # 算出「章」落在第几级标题
    chapter_cfg = spec_lib.resolve_heading(spec.get("headings") or {}, chapter_level)   # 该级标题的配置
    chapter_start_on_odd = bool(chapter_cfg.get("start_on_odd_page"))   # 章是否要求从奇数页起
    chapter_elements = []                                      # 各章标题的 XML 元素，按出现顺序
    body_start_heading = str(((spec.get("footer") or {}).get("page_number") or {})
                             .get("body_start_heading") or "").strip()   # 正文从哪个标题开始
    body_start_element = None                                  # 正文起始标题的 XML 元素
    # 封面的结束位置也要认出来：只有知道封面到哪为止，才谈得上「封面不编页码」，
    # 否则封面和前言会被算成同一节，前言的罗马页码会被一起误免（实测踩过）。
    cover_end_heading = str((((spec.get("footer") or {}).get("page_number") or {})
                             .get("front_matter") or {}).get("cover_end_heading") or "").strip()   # 封面到哪个标题为止
    cover_end_element = None                                   # 封面结束标题的 XML 元素
    for block in blocks:                                       # 遍历每个块
        kind = block["type"]                                   # 取块类型
        # 手写目录要整块跳掉：它下面是一串指向网页锚点的列表，
        # 在 Word 里既跳不动、又和自动目录重复。跳到一个「同级或更高级」的标题为止。
        if toc_skip_level:                                     # 正在跳过中
            if kind == "heading" and block["level"] <= toc_skip_level:   # 遇到同级或更高级的标题
                toc_skip_level = 0                             # 停止跳过，这个标题要正常输出
            else:                                              # 其余内容都属于手写目录
                continue                                       # 一律丢弃
        if kind == "anchor":                                   # HTML 锚点
            continue                                           # Word 里没有意义，直接跳过（否则会印出 <a id="x"></a>）
        if kind == "image":                                    # 图片
            created = add_image(document, block, spec, base_dir)   # 插入图片（找不到文件时会打印警告）
            if created:                                        # 真的插进去了才登记分组
                block_groups.append({"kind": "image", "paragraphs": created})   # 登记图片组
            continue                                           # 处理下一块
        if kind == "heading":                                  # 标题
            heading_cfg = spec_lib.resolve_heading(headings, min(block["level"], 6))   # 取这一级的标题配置
            heading_size = heading_cfg.get("size_pt")          # 这一级要求的字号
            heading_text = block["text"]                       # 标题文字（下面可能被人工断行改写成两行）
            available_cm = content_width_mm(spec) / 10         # 版心宽度（厘米），断行与折行预警都按它算
            manual_break = None                                # 人工断行的结果（None ＝ 没断，交给 Word 自动折）
            # 只有预设显式声明了「标题排列形状」的才做人工断行 —— 目前只有公文标题：
            # §7.3.1 要求「回行时，要做到词意完整，排列对称，长短适宜，间距恰当，
            # 标题排列应当使用梯形或菱形」。Word 的自动折行只管排满一行就断，实测会把
            # 「……隐患排查整治工／作的通知」这种词切断，这一句正是为此加的。
            # 图书、论文、报告没有这条硬要求，贸然替用户断行反而会改掉他熟悉的排版，所以不声明就不动。
            # 折行核对与人工断行都只针对「像标题的文字」：公文预设把「（一）强化组织领导。各县（市、区）
            # 要……」这类层次序数段落登记成了级别标题（国标里它们本就是正文自然段、只是带序数），
            # 一整段话拿来算折行必然报「末行太短」—— 那是正文的正常折行，报了就是噪音。
            title_like = not spec_lib.looks_like_prose(block["text"])   # 不含句末标点才算「像标题」
            explicit_lines = spec_lib.heading_explicit_lines(block["text"])   # 稿子里用「｜」标好的人工断行
            if explicit_lines:                                 # 用户已经在稿子里指定了断点（优先级最高）
                manual_break = explicit_lines                  # 直接采用
                heading_text = "\n".join(explicit_lines)       # 按用户标的位置断成两行
            elif heading_size and title_like and str(heading_cfg.get("shape_rule") or "").strip():   # 有字号、像标题、且声明了排列形状
                manual_break = spec_lib.balanced_heading_break(heading_text, float(heading_size), available_cm)   # 自动找一个「长短均衡」的断点
                if manual_break:                               # 找到了合适的断点
                    heading_text = "\n".join(manual_break)      # 断成两行（python-docx 会写成 <w:br/>，仍在同一个居中段落里）
                    # 自动断点只能按字数猜、没有词典，可能把词切开（实测「城市防／汛隐患」）。
                    # 说破断在哪儿，并给出改写办法 —— 与其让用户拿到文件才发现，不如生成时讲清楚。
                    print(f"ℹ 标题「{block['text']}」按 §7.3.1 自动断成两行"
                          f"（{manual_break[0]}｜{manual_break[1]}）：两行长短已对齐，但断点是按字数猜的，"
                          f"可能切断了词意。若想换个位置断，把标题按你想断的地方用「｜」写开即可"
                          f"（例：{manual_break[0]}｜{manual_break[1]} 改成 前半句｜后半句）。")
            paragraph = document.add_heading(heading_text, level=min(block["level"], 6))   # 添加标题
            # 标题折行核对：折出来的末行只剩一两个字（孤字）、或不足整行四分之一（倒梯形）时，
            # 当场算给用户看，并给出「字号调到多少以内能排成一行」。
            # 这类毛病在源码里看不出来（规格卡写多少就是多少），只有渲染出来才发现，
            # 与其等用户拿到文件抱怨，不如生成时就说破。
            # 人工断行成功的不再预警：断点是我们自己按 §7.3.1 挑的（两行已对称），再报一次就是自相矛盾。
            if heading_size and title_like and not manual_break:   # 有字号、像标题、且这一级没做人工断行
                wrap_info = spec_lib.heading_wrap_info(block["text"], float(heading_size), available_cm)   # 算自动折行
                # 标题折成两行本身很正常（书名页上的长标题、长章名都常折行），
                # 只报真正难看的：孤字与倒梯形，判据见 spec_lib.heading_wrap_is_bad（生成端与校验端共用）。
                if spec_lib.heading_wrap_is_bad(wrap_info):     # 折得难看
                    wrap_warnings.append(spec_lib.describe_heading_wrap_text(wrap_info))   # 收集起来最后统一打印
            # 分节登记：这一级是「章」且规格要求从奇数页起 → 记下它，最后统一插分节符
            if chapter_start_on_odd and min(block["level"], 6) == chapter_level:   # 命中章标题
                chapter_elements.append(paragraph._p)          # 记下段落元素
            if body_start_heading and block["text"].strip() == body_start_heading:   # 命中正文起始标题
                body_start_element = paragraph._p              # 记下段落元素，供页码分节用
            if cover_end_heading and block["text"].strip() == cover_end_heading:   # 命中封面结束标题
                cover_end_element = paragraph._p              # 记下段落元素，供封面单独成节用
            if toc_heading and block["text"].strip() == toc_heading:   # 这就是挂手写目录的那个标题
                if toc_cfg.get("enabled"):                     # 规格卡要求换成自动目录
                    set_outline_level(paragraph, 9)            # 把「目录」二字设为正文级，免得目录里列出自己
                    toc_para = document.add_paragraph()        # 新建一段放目录域
                    add_toc_field(toc_para, toc_cfg.get("levels", "1-3"),
                                  east_asian, latin, float(size_pt))   # 插入 TOC 域
                    toc_skip_level = block["level"]            # 记下层级，开始丢弃手写目录块
                continue                                       # 该标题已处理完
        elif kind == "paragraph":                              # 正文段落
            element = block.get("preset_element")               # 这一段被预设判成了哪种公文要素（见 label_preset_elements）
            if block.get("table_caption"):                      # 表格题注：按图表题注规则排版
                # 题注不缩进、字号小一号、按 caption_alignment 对齐。
                # 生成之前已按 table_caption_position 摆好它和表格的先后（见 reorder_table_captions）。
                add_caption_paragraph(document, block["text"], spec)   # 写题注
            elif element:                                       # 公文主体要素：主送机关/附件说明/署名/成文日期
                # 必须走这条路，不能再走下面的「普通正文」：正文那套会加上首行缩进二字，
                # 主送机关的「居左顶格」、成文日期的「右空四字」就全废了（修之前就是这样）。
                add_subject_element(document, block, spec, body_font, element, element_layout)   # 按 §7.3 排版
            else:                                              # 普通正文段落
                paragraph = add_rich_paragraph(document, block, east_asian, latin, float(size_pt))   # 添加段落（含 <u> 下划线还原）
                # 只有印刷模式才加首行缩进；屏幕模式的缩进由规格显式关闭
                if indent_mode == "first_line" and indent_chars:    # 印刷模式
                    set_first_line_indent_chars(paragraph, indent_chars)   # 写入字符级缩进
        elif kind == "quote":                                  # 引用
            # 引用块要「看得出来是引用」。旧版只做缩进，结果引文与正文长得一样；
            # 而且旧版在左缩进之外又补了两个全角空格，等于缩进四字，间距也对不上。
            # 现在：左缩进两字 + 右缩进一字 + 左侧竖线，引文与正文一眼可分。
            quote_paragraphs = []                              # 本引用块的段落，供块级间距使用
            for quote_text in (block.get("paragraphs") or [block.get("text") or ""]):   # 逐段写（多段引用不再被并成一段）
                paragraph = document.add_paragraph(quote_text)   # 添加该段落
                quote_format = paragraph.paragraph_format          # 取段落格式
                quote_format.left_indent = Pt(float(size_pt) * 2)  # 整体左缩进两字
                quote_format.right_indent = Pt(float(size_pt))     # 右缩进一字，避免引文顶到版心右边缘
                set_paragraph_left_border(paragraph)               # 加左侧竖线
                quote_paragraphs.append(paragraph)                 # 记下来
            block_groups.append({"kind": "quote", "paragraphs": quote_paragraphs})   # 登记引用组
        elif kind == "list":                                   # 列表
            style = "List Number" if block.get("ordered") else "List Bullet"   # 选择列表样式
            add_rich_paragraph(document, block, east_asian, latin, float(size_pt), style=style)   # 添加列表项（同样支持 <u>）
        elif kind == "code":                                   # 代码块
            # 代码块字体必须由规格卡声明，不能写死。
            # 旧版写死 "Consolas"，本机没有这个字体，LibreOffice 就自己挑了 LinuxLibertineG
            # （比例衬线体，根本不是等宽），代码块对的列都对齐不了（实测）。
            # 规则：规格卡声明了就用声明的（会被字体闸门检查），没声明就沿用正文字体，
            #       绝不凭空引入一个本机可能没有的字体名。
            code_cfg = (spec.get("fonts") or {}).get("code") or {}   # 代码块字体配置
            code_east = spec_lib.resolve_font(code_cfg.get("east_asian") or east_asian,
                                              code_cfg.get("resolved"))   # 代码块中文字体
            code_latin = code_cfg.get("latin") or latin          # 代码块西文字体，默认沿用正文
            code_size = float(code_cfg.get("size_pt") or float(size_pt) * 0.95)   # 代码块字号，默认比正文小一点
            code_paragraphs = []                               # 本代码块的段落，供块级间距使用
            for code_line in block["text"].split("\n"):         # 逐行写入
                paragraph = document.add_paragraph(code_line)   # 添加段落
                paragraph.paragraph_format.left_indent = Pt(float(size_pt) * 2)   # 左缩进两字
                for run in paragraph.runs:                      # 遍历文本块
                    style_run(run, code_east, code_latin, code_size)   # 按规格声明的代码字体
                code_paragraphs.append(paragraph)               # 记下来
            block_groups.append({"kind": "code", "paragraphs": code_paragraphs})   # 登记代码块组
        elif kind == "rule":                                   # 分隔线
            rule_paragraph = add_horizontal_rule(document)      # 画一条真正的横线（不是空段落）
            block_groups.append({"kind": "rule", "paragraphs": [rule_paragraph]})   # 登记分隔线组
        elif kind == "table":                                  # 表格
            add_table(document, block, spec, body_font)         # 生成表格
    # 分节必须放在正文全部写完、版记之前：它要按「章的位置」回头改文档结构。
    if chapter_elements:                                       # 有章且规格要求从奇数页起
        apply_chapter_page_starts(document, chapter_elements)   # 逐章分节，让每章从奇数页起
        # 必须说破「会多出空白页」，否则用户会以为中间那页空白是排版出错。
        # 这里也曾写错过一句话：早先以为 LibreOffice 忽略 w:type=oddPage，
        # 实测（LibreOfficeDev 26.8.0.0.alpha0）推翻了它 —— LO 其实认这个设置、也确实插了空白页，
        # 真正的问题是它的 PDF 导出默认把空白页丢掉（IsSkipEmptyPages 默认为 true），
        # 16 页的稿子导成 12 页，后面每一页的奇偶整体错位，看起来才像「没生效」。
        # build_pdf.py 已显式关掉该选项，所以用本 skill 出 PDF 时空白页会被保留。
        print("说明：已按规格写入「章从奇数页起」的分节符：上一章若收在奇数页，中间会插一页空白。")
        print("      生成 PDF 请用本 skill 的 scripts/build_pdf.py（它会保留空白页）；"
              "换别的工具导出时，注意别把空白页丢掉，否则后面的页码奇偶会整体错位。")
    # 前置页与正文分别编页码（规格没提就什么也不做，返回空列表）
    for note in apply_front_matter_numbering(document, spec, body_start_element, cover_end_element):   # 处理页码分节
        print(f"⚠ {note}")                                      # 逐条明确说破，不静默跳过
    # 块级间距要放在全部正文块渲染完之后：它要按最终的 XML 顺序找「表格紧邻的段落」。
    # 也必须放在 add_record_section 之前，免得给版记那两个段落加上版记里不需要的空。
    apply_block_spacing(document, spec, block_groups)          # 给表格/图片/代码块/引用块/分隔线补段前段后
    add_record_section(document, spec)                         # 生成版记（若配置了）
    document.save(output_path)                                 # 保存文件
    for index, warning in enumerate(wrap_warnings):             # 逐条打印标题折行预警
        prefix = "⚠" if index == 0 else " "                     # 第一条带警示符，后续对齐缩进
        print(f"{prefix} 标题排版：{warning}")                    # 打印，让用户决定是否改字号
    print(f"已生成：{output_path}")                              # 提示输出路径
    print(f"块数量：段落/标题/表格共 {len(blocks)} 个")            # 提示块数量
    return 0                                                    # 返回成功码

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="按规格卡从 Markdown 生成 DOCX")   # 构造参数解析器
    parser.add_argument("--spec", required=True, help="规格卡 YAML 路径")          # 规格卡参数
    parser.add_argument("--input", required=True, help="输入 Markdown 路径")       # 输入参数
    parser.add_argument("--output", required=True, help="输出 DOCX 路径")          # 输出参数
    parser.add_argument("--allow-placeholders", action="store_true",                 # 放行开关，默认关闭
                        help="允许红头必填项留空并用占位符生成。只在用户明确要「练习稿/待补稿」时使用，"
                             "正式文件不能用")                                        # 参数说明
    parser.add_argument("--normalize", action="store_true",                    # 源文件清洗开关，默认关闭
                        help="生成前在内存里做一遍源文件规范化（不落盘、不留中间文件）")   # 参数说明
    parser.add_argument("--allow-flat", action="store_true",                   # 结构放行开关，默认关闭
                        help="允许「没有标题层级」的稿子照样生成。只在用户明确说过"
                             "「这篇就是不要标题」时使用；否则应先问清结构再生成")   # 参数说明
    args = parser.parse_args()                                                    # 解析参数
    return build(args.spec, args.input, args.output, args.allow_placeholders, args.normalize,
                 args.allow_flat)                                                 # 执行生成

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                                      # 用返回值作为退出码

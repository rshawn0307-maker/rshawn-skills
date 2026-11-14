#!/usr/bin/env python3
# 本脚本反推一个现成 DOCX 的排版规格：读出它当前真实生效的字体、字号、行距、缩进、对齐与页边距。
# 用途：用户丢来一个已有的 Word 文件时，先告诉他「你现在用的是这样」，再问要不要换成预设。
# 用法：python3 scripts/inspect_docx.py old.docx
#
# 取值顺序（关键）：段落上直接写的 > 样式里定义的 > 文档默认。
# 为什么必须这样：政务系统和单位模板导出的 Word，习惯把字体、字号、缩进直接写在每一段上，
# 样式表里反而留着一份旧的、早被覆盖的值。只看样式表，会把「标题 18pt」这种过期值报给用户，
# 而文件里真正渲染出来的是段落上写死的 22pt —— 给用户一份错的规格，比不给还糟。

import argparse   # 用于解析命令行参数
import re         # 用于正则提取属性值
import sys        # 用于控制退出码与错误输出
import zipfile    # 用于解包 DOCX

# 对齐枚举值的中文说法，报告里直接给用户看中文
ALIGN_TEXT = {
    "both": "两端对齐",        # Word 里的「两端对齐」，公文与图书正文的常规做法
    "justify": "两端对齐",     # 同一个意思的另一种写法
    "left": "左对齐",          # 左对齐
    "center": "居中",          # 居中
    "right": "右对齐",         # 右对齐
    "distribute": "分散对齐",   # 分散对齐
}

# 读取 zip 内指定文件的内容
def read_member(path, member):
    with zipfile.ZipFile(path) as archive:                      # 打开压缩包
        return archive.read(member).decode("utf-8", "ignore")   # 读取并解码

# 从一段 XML 里抠出指定标签的整块内容；找不到就返回空串
def block(xml, tag):
    match = re.search(rf"<{tag}(?: [^>]*)?>.*?</{tag}>", xml, re.S)   # 标签可能带属性，也可能不带
    return match.group(0) if match else ""                            # 命中就返回整块，否则返回空串

# 从一段 XML 里删掉指定标签的整块内容，用于「先摘掉内层、再解析外层」
def drop_block(xml, tag):
    return re.sub(rf"<{tag}(?: [^>]*)?>.*?</{tag}>", "", xml, flags=re.S)   # 直接替换成空串

# 从 <w:rPr> 块里读字符格式：中文字体、西文字体、字号、加粗
def read_rpr(rpr_xml):
    info = {}                                                   # 初始化结果字典
    if not rpr_xml:                                             # 压根没有这段属性
        return info                                             # 直接返回空结果
    fonts = re.search(r"<w:rFonts[^>]*>", rpr_xml)              # 找字体节点
    if fonts:                                                   # 找到了
        east = re.search(r'w:eastAsia="([^"]+)"', fonts.group(0))    # 提取中文字体
        latin = re.search(r'w:ascii="([^"]+)"', fonts.group(0))      # 提取西文字体
        if east:                                                # 有中文字体就记
            info["east_asian"] = east.group(1)                  # 记录中文字体名
        if latin:                                               # 有西文字体就记
            info["latin"] = latin.group(1)                      # 记录西文字体名
    size = re.search(r'<w:sz w:val="(\d+)"', rpr_xml)           # 字号节点，单位是半磅
    if size:                                                    # 有字号就记
        info["size_pt"] = int(size.group(1)) / 2                # 半磅换算成磅
    bold = re.search(r'<w:b(?: [^>]*)?/?>', rpr_xml)            # 加粗节点，可能带属性
    if bold:                                                    # 找到加粗节点
        off = re.search(r'w:val="(?:0|false)"', bold.group(0))   # 看看是不是明确写成「关掉」
        info["bold"] = not off                                  # 没有关掉标记就是真加粗
    return info                                                 # 返回字符格式

# 从 <w:pPr> 块里读段落格式：样式号、对齐、缩进、行距、段前段后
def read_ppr(ppr_xml):
    info = {}                                                   # 初始化结果字典
    if not ppr_xml:                                             # 压根没有这段属性
        return info                                             # 直接返回空结果
    # 段落的 <w:pPr> 里还可能嵌着「段落标记自己的字符格式」<w:rPr>，先摘掉，
    # 否则里面表示字间距的 <w:spacing w:val="20"/> 会被误当成行距读出来。
    clean = drop_block(ppr_xml, "w:rPr")                        # 去掉内层的 rPr
    style = re.search(r'<w:pStyle w:val="([^"]+)"', clean)      # 这一段用了哪个样式
    if style:                                                   # 有就记
        info["style"] = style.group(1)                          # 记录样式号
    just = re.search(r'<w:jc w:val="([^"]+)"', clean)           # 对齐方式
    if just:                                                    # 有就记
        info["alignment"] = just.group(1)                       # 记录对齐值
    spacing = re.search(r"<w:spacing([^>]*)/?>", clean)         # 行距与段前段后距装在同一个节点里
    if spacing:                                                 # 找到了
        attrs = spacing.group(1)                                # 取出属性串
        line = re.search(r'w:line="(\d+)"', attrs)              # 行距原始值
        rule = re.search(r'w:lineRule="([^"]+)"', attrs)        # 行距规则，决定原始值的单位
        if line:                                                # 有行距就记
            info["line_value"] = int(line.group(1))             # auto 时单位是 1/240 行；exact 与 atLeast 时是 1/20 磅
            info["line_rule"] = rule.group(1) if rule else "auto"   # 规则缺省按 OOXML 默认的 auto 处理
        before = re.search(r'w:before="(\d+)"', attrs)          # 段前距
        after = re.search(r'w:after="(\d+)"', attrs)            # 段后距
        if before:                                              # 有段前距就记
            info["space_before_pt"] = int(before.group(1)) / 20 # 二十分之一磅换算成磅
        if after:                                               # 有段后距就记
            info["space_after_pt"] = int(after.group(1)) / 20   # 二十分之一磅换算成磅
    indent = re.search(r"<w:ind([^>]*)/?>", clean)              # 缩进节点
    if indent:                                                  # 找到了
        chars = re.search(r'w:firstLineChars="(\d+)"', indent.group(1))   # 以「字符」为单位的首行缩进
        twips = re.search(r'w:firstLine="(\d+)"', indent.group(1))        # 以长度为单位的首行缩进
        if chars:                                               # 有字符单位就记
            info["first_line_indent_chars"] = int(chars.group(1)) / 100   # 单位是百分之一字符
        if twips:                                               # 有长度单位就记
            info["first_line_indent_cm"] = int(twips.group(1)) / 1440 * 2.54   # 缇换算成厘米
    return info                                                 # 返回段落格式

# 从 styles.xml 中解析出每种样式定义的字体、字号、行距、缩进
def parse_styles(styles_xml):
    results = []                                                # 初始化结果列表
    # 逐个匹配每个 w:style 块（样式名在开标签的属性里，属性顺序不固定，所以单独抠）
    for match in re.finditer(r"<w:style ([^>]*)>(.*?)</w:style>", styles_xml, re.S):
        attrs = match.group(1)                                  # 开标签的属性串
        body = match.group(2)                                   # 样式的全部内容
        style_id = re.search(r'w:styleId="([^"]+)"', attrs)     # 抠出样式标识
        if not style_id:                                        # 没有标识的样式没法引用
            continue                                            # 跳过
        info = {"style": style_id.group(1)}                     # 先记下样式号
        kind = re.search(r'w:type="([^"]+)"', attrs)            # 样式的类型：段落样式还是字符样式
        if kind:                                                # 有类型就记
            info["type"] = kind.group(1)                        # 记录类型
        is_default = re.search(r'w:default="([^"]+)"', attrs)   # 是不是这一类里默认的那个样式
        if is_default:                                          # 是默认样式就记
            info["default"] = is_default.group(1)               # 记录默认标记
        based = re.search(r'<w:basedOn w:val="([^"]+)"', body)  # 这个样式继承了谁
        if based:                                               # 有继承关系就记
            info["based_on"] = based.group(1)                   # 记录父样式号
        name = re.search(r'<w:name w:val="([^"]+)"', body)      # 样式的显示名
        if name:                                                # 有显示名就记
            info["name"] = name.group(1)                        # 记录显示名
        ppr = block(body, "w:pPr")                              # 抠出段落格式块
        rpr = block(drop_block(body, "w:pPr"), "w:rPr")         # 先摘掉段落格式，再抠字符格式，避免抓到内层那个
        info.update(read_rpr(rpr))                              # 叠上字符格式
        info.update(read_ppr(ppr))                              # 叠上段落格式
        results.append(info)                                    # 加入结果列表
    return results                                              # 返回样式列表

# 读文档默认格式：段落和样式都没写时用的兜底值
def parse_defaults(styles_xml):
    defaults = {}                                               # 初始化结果字典
    block_xml = block(styles_xml, "w:docDefaults")              # 抠出文档默认设置块
    if block_xml:                                               # 找到了
        defaults.update(read_rpr(block(block_xml, "w:rPr")))    # 叠上默认字符格式
        defaults.update(read_ppr(block(block_xml, "w:pPr")))    # 叠上默认段落格式
    return defaults                                             # 返回默认格式

# 把样式的继承链摊平：标题样式常基于正文样式，字体字号是从父样式继承来的
def resolve_style(style_id, style_map, limit=6):
    merged = {}                                                 # 摊平后的结果
    chain = []                                                  # 从子到父收集到的样式链
    current = style_id                                          # 从当前样式开始往上爬
    hops = 0                                                    # 已经爬了几层
    while current and hops < limit:                             # 还没爬到顶也没超过层数上限
        item = style_map.get(current)                           # 取这一层样式
        if not item:                                            # 找不到就停
            break                                               # 退出循环
        chain.append(item)                                      # 记下这一层
        current = item.get("based_on")                          # 继续往上找父样式
        hops += 1                                               # 层数加一
    for item in reversed(chain):                                # 从最顶上的父样式开始往下叠
        for key, value in item.items():                         # 逐项叠加
            if key not in ("style", "based_on", "name", "type", "default"):   # 这些是样式的身份信息，不是格式，跳过
                merged[key] = value                             # 子样式覆盖父样式
    return merged                                               # 返回摊平后的格式

# 找出文档默认的段落样式与字符样式（Word 里那个通常叫 Normal 的）
def default_style_ids(styles):
    ids = {}                                                    # 结果字典：类型 → 样式号
    for item in styles:                                         # 遍历所有样式
        if item.get("type") and item.get("default") in ("1", "true"):   # 标了「我是默认」的那个样式
            ids[item["type"]] = item["style"]                    # 按类型记下样式号
    return ids                                                  # 返回结果

# 从 document.xml 中解析页面设置；保留给「把现有文件存成预设」那一步复用
def parse_document(document_xml):
    info = {}                                                   # 初始化结果字典
    sect = re.search(r"<w:sectPr.*?</w:sectPr>", document_xml, re.S)   # 查找节属性
    if sect:                                                    # 若存在
        block_text = sect.group(0)                              # 取节属性文本
        for key, label in [("top", "margin_top_mm"), ("bottom", "margin_bottom_mm"),
                           ("left", "margin_left_mm"), ("right", "margin_right_mm")]:   # 逐边解析
            margin = re.search(rf'<w:pgMar[^>]*w:{key}="(-?\d+)"', block_text)   # 提取该边距
            if margin:                                          # 若存在
                info[label] = int(margin.group(1)) / 1440 * 25.4   # 缇换算成毫米
        width = re.search(r'<w:pgSz[^>]*w:w="(\d+)"', block_text)     # 提取页面宽度
        height = re.search(r'<w:pgSz[^>]*w:h="(\d+)"', block_text)    # 提取页面高度
        if width:                                               # 记录页面宽度
            info["page_width_mm"] = int(width.group(1)) / 1440 * 25.4
        if height:                                              # 记录页面高度
            info["page_height_mm"] = int(height.group(1)) / 1440 * 25.4
    info["table_count"] = document_xml.count("<w:tbl>")          # 统计表格数量
    info["paragraph_count"] = document_xml.count("<w:p ") + document_xml.count("<w:p>")   # 统计段落数量
    return info                                                 # 返回结果

# 把正文切成「表格外」和「表格内」两类片段
def split_regions(document_xml):
    regions = []                                                # 结果列表：每项是（是否在表格里，片段文本）
    depth = 0                                                   # 当前表格嵌套深度
    last = 0                                                    # 上一个切点
    for match in re.finditer(r"<w:tbl[ >]|</w:tbl>", document_xml):   # 逐个找表格的起止标签
        chunk = document_xml[last:match.start()]                # 取出两个标签之间的片段
        if chunk:                                               # 片段非空才留
            regions.append((depth > 0, chunk))                  # 深度大于零说明这段在表格里
        last = match.end()                                      # 移动切点
        if match.group(0).startswith("<w:tbl"):                 # 遇到表格开头
            depth += 1                                          # 进入表格
        else:                                                   # 遇到表格结尾
            depth -= 1                                          # 退出表格
    tail = document_xml[last:]                                  # 最后剩下的片段
    if tail:                                                    # 非空才留
        regions.append((depth > 0, tail))                       # 记下收尾片段
    return regions                                              # 返回全部片段

# 把正文拆成一个个段落，读出每段的直接格式，并标出它在不在表格里
def parse_paragraphs(document_xml):
    paragraphs = []                                             # 结果列表
    for in_table, chunk in split_regions(document_xml):         # 先按表格内外切开
        for match in re.finditer(r"<w:p(?: [^>]*)?>.*?</w:p>", chunk, re.S):   # 逐个抠出段落
            para = match.group(0)                               # 这一段的完整 XML
            ppr = block(para, "w:pPr")                          # 段落格式块
            mark_rpr = block(ppr, "w:rPr")                      # 段落标记自己的字符格式
            run_rpr = {}                                        # 第一个有实际文字的内容块的字符格式
            fallback_rpr = {}                                   # 整段只有空白时，拿第一个内容块的格式兜底
            pieces = []                                         # 这一段的文字碎片
            for run in re.finditer(r"<w:r(?: [^>]*)?>.*?</w:r>", para, re.S):   # 逐个看内容块
                run_xml = run.group(0)                          # 这个内容块的 XML
                piece = re.search(r"<w:t(?: [^>]*)?>(.*?)</w:t>", run_xml, re.S)   # 里面的文字
                if not piece:                                   # 没有文字的内容块（比如图片）跳过
                    continue                                    # 继续找下一个
                chunk_text = re.sub(r"<[^>]+>", "", piece.group(1))   # 剥掉标签留下纯文字
                chunk_rpr = read_rpr(block(run_xml, "w:rPr"))    # 读这个内容块的字符格式
                if not fallback_rpr:                            # 还没有兜底格式
                    fallback_rpr = chunk_rpr                     # 拿它当兜底
                # 落款、缩进这类段落，开头往往是一个只装空格的文字块，
                # 所以字符格式要认第一个「有实际文字」的块，不能见到第一个块就收工。
                if not run_rpr and chunk_text.strip():          # 找到第一个有实际文字的块
                    run_rpr = chunk_rpr                          # 用它决定这一段的字符格式
                pieces.append(chunk_text)                       # 把这截文字收集起来
            if not run_rpr:                                     # 整段都是空白或没有文字块
                run_rpr = fallback_rpr                          # 退回兜底格式
            text = "".join(pieces).strip()                      # 把各截文字拼回完整一段
            paragraphs.append({                                 # 记下这一段
                "in_table": in_table,                           # 在不在表格里
                "text": text.strip(),                           # 段落文字
                "ppr": read_ppr(ppr),                           # 段落格式
                "mark_rpr": read_rpr(mark_rpr),                 # 段落标记的字符格式
                "run_rpr": run_rpr,                             # 正文内容块的字符格式
            })
    return paragraphs                                           # 返回全部段落

# 按「文档默认 → 默认样式 → 指定样式 → 段落标记 → 内容块 → 段落」的顺序，算出这一段最终生效的格式
def effective_spec(paragraph, style_map, defaults, default_ids):
    spec = {}                                                   # 最终生效的格式
    spec.update(defaults)                                       # 第一层：文档默认格式
    if default_ids.get("character"):                            # 第二层：文档默认的字符样式
        spec.update(resolve_style(default_ids["character"], style_map))   # 叠上默认字符样式
    if default_ids.get("paragraph"):                            # 第三层：文档默认的段落样式
        spec.update(resolve_style(default_ids["paragraph"], style_map))   # 段落不写样式号时，格式就来自这里
    style_id = paragraph["ppr"].get("style")                    # 这一段单独引用了哪个样式
    if style_id:                                                # 单独指了样式
        spec.update(resolve_style(style_id, style_map))          # 第四层：这个样式（含它的继承链）
    spec.update(paragraph["mark_rpr"])                          # 第五层：段落标记上写的
    spec.update(paragraph["run_rpr"])                           # 第六层：内容块上写的
    spec.update(paragraph["ppr"])                               # 第七层：段落上写的，优先级最高
    return spec                                                 # 返回最终格式

# 把 OOXML 的行距属性翻译成人话。
#
# 关键区别在 w:lineRule：auto 的 w:line 是「1/240 行」的倍数（240 = 单倍、360 = 1.5 倍），
# exact / atLeast 的 w:line 才是「1/20 磅」。旧版不管规则、一律按磅打印，
# 于是「单倍行距」被印成「行距 12pt（auto）」—— 用户会误以为那是一行文字固定占 12 磅，
# 而这两者在排版上完全不是一回事（前者随字号变，后者钉死）。
def describe_line_spacing(info):
    value = info.get("line_value")                              # 行距原始值
    if not value:                                               # 没写行距
        return ""                                              # 返回空串
    rule = info.get("line_rule", "auto")                        # 行距规则，缺省按 OOXML 默认的 auto
    if rule == "exact":                                         # 固定值
        return f"行距 固定值 {value / 20:g}pt"                    # 例如「固定值 15.6pt」
    if rule == "atLeast":                                       # 最小值
        return f"行距 最小值 {value / 20:g}pt"                    # 例如「最小值 20pt」
    multiple = value / 240                                      # auto：换成倍数
    if abs(multiple - 1) < 1e-9:                                # 正好 240
        return "行距 单倍"                                       # 说「单倍」，不要说「12pt」
    return f"行距 {multiple:g} 倍"                               # 其它倍数（1.5 倍、2 倍…）

# 把一段的格式压成一个「指纹」，指纹相同的段落会被归成一组
def spec_signature(spec):
    return (                                                    # 用元组当指纹，可比较可去重
        spec.get("east_asian"),                                 # 中文字体
        spec.get("size_pt"),                                    # 字号
        spec.get("alignment"),                                  # 对齐
        spec.get("first_line_indent_chars"),                    # 首行缩进
        spec.get("line_rule"),                                  # 行距规则
        spec.get("line_value"),                                 # 行距值
    )

# 把一组格式说成一句人话，给用户看
def describe_spec(spec):
    parts = []                                                  # 一句句拼起来
    east = spec.get("east_asian")                               # 中文字体
    latin = spec.get("latin")                                   # 西文字体
    if east and latin and east != latin:                        # 中西文用的不是同一个字体，分开说
        parts.append(f"中文字体 {east}，西文 {latin}")            # 两个都写上
    elif east:                                                  # 只有中文字体，或中西文同名
        parts.append(f"中文字体 {east}")                          # 写一个就够
    elif latin:                                                 # 只写了西文位置，中文字体是空的
        parts.append(f"中文字体没单独写，只在西文位置写了 {latin}")  # 如实说，不替文件猜
    if spec.get("size_pt"):                                     # 有字号
        parts.append(f"字号 {spec['size_pt']:g}pt")              # 写上磅数
    if spec.get("bold"):                                        # 加粗了
        parts.append("加粗")                                     # 标注出来
    line_text = describe_line_spacing(spec)                     # 行距
    if line_text:                                               # 有行距信息
        parts.append(line_text)                                 # 写上
    indent_chars = spec.get("first_line_indent_chars")          # 字符单位的首行缩进
    if indent_chars:                                            # 缩进了
        parts.append(f"首行缩进 {indent_chars:g} 字符")           # 写字符数
    elif indent_chars == 0 or spec.get("first_line_indent_cm") == 0:   # 明确写成不缩进
        parts.append("首行不缩进")                                # 说清楚没缩进
    elif spec.get("first_line_indent_cm"):                      # 只有长度单位的缩进
        parts.append(f"首行缩进 {spec['first_line_indent_cm']:.2f}cm")   # 写厘米数
    if spec.get("space_before_pt") or spec.get("space_after_pt"):   # 有段前或段后距
        parts.append(f"段前 {spec.get('space_before_pt', 0):g}pt／段后 {spec.get('space_after_pt', 0):g}pt")   # 一起写出来
    if spec.get("alignment"):                                   # 有对齐设置
        parts.append(f"对齐 {ALIGN_TEXT.get(spec['alignment'], spec['alignment'])}")   # 翻成中文
    return "，".join(parts) if parts else "（这一层没有任何格式设置）"   # 什么都没读到就说明一下

# 按给定的取值函数，统计一组段落里各项出现的次数
def count_by(paragraphs, pick):
    counts = {}                                                 # 计数结果
    for paragraph in paragraphs:                                # 逐段累加
        key = pick(paragraph)                                   # 取这一段的分类键
        counts[key] = counts.get(key, 0) + 1                    # 对应计数加一
    return counts                                               # 返回计数

# 逐段打印生效规格，用来核对自动分组合不合理
def print_detail(paragraphs):
    print("【逐段明细】")                                        # 分节标题
    for index, paragraph in enumerate(paragraphs, 1):            # 按顺序编号
        spec = paragraph["spec"]                                 # 这一段的生效规格
        size = f"{spec['size_pt']:g}pt" if spec.get("size_pt") else "字号没写"   # 字号
        indent = spec.get("first_line_indent_chars")             # 首行缩进字符数
        indent_text = f"缩进 {indent:g} 字符" if indent else "不缩进"   # 缩进说法
        align = ALIGN_TEXT.get(spec.get("alignment"), "对齐没写")   # 对齐说法
        where = "表格里" if paragraph["in_table"] else "正文"        # 在不在表格里
        text = paragraph["text"][:24]                            # 段落文字，截断方便看
        print(f"  {index:>3} [{where}] {spec.get('east_asian') or '字体没写'} {size} {indent_text} {align} | {text}")   # 一行一段

# 把计数结果按从多到少排好，拼成一句话
def format_counts(counts):
    ordered = sorted(counts.items(), key=lambda item: -item[1])   # 多的排前面
    return "，".join(f"{key} {value} 段" for key, value in ordered)   # 拼成「居中 40 段，左对齐 6 段」

# 打印反推结果，全部用中文
def report(path, styles, document, paragraphs):
    body = [item for item in paragraphs if not item["in_table"]]      # 表格外的段落
    inside = [item for item in paragraphs if item["in_table"]]        # 表格里的段落
    # 空段落只是排版用的空行，它没有文字，也就没有「正文该长什么样」这回事。
    # 把它们算进分组，它们往往会靠数量把「正文」那一组顶掉，于是缩进、字体全报错。
    body_texted = [item for item in body if item["text"]]             # 有文字的正文段落
    inside_texted = [item for item in inside if item["text"]]         # 有文字的表格段落
    print(f"现有文件规格反推：{path}")                                 # 打印标题
    print("=" * 60)                                                  # 打印分隔线
    print("【页面设置】")                                             # 分节标题
    if document.get("page_width_mm"):                               # 解析到页面宽度才打印
        print(f"  纸张：{document['page_width_mm']:.0f}mm × {document.get('page_height_mm', 0):.0f}mm")   # 打印纸张
    for key, label in [("margin_top_mm", "上边距"), ("margin_bottom_mm", "下边距"),
                       ("left_margin_mm", "左边距"), ("margin_right_mm", "右边距")]:   # 逐边打印
        value = document.get(key) or document.get(key.replace("left_margin_mm", "margin_left_mm"))   # 兼容两种键名
        if value is not None:                                       # 解析到才打印
            print(f"  {label}：{value:.1f}mm")                       # 打印该边距
    blank_count = len(body) - len(body_texted)                        # 空段落个数
    print(f"  段落：{len(paragraphs)} 段（表格里 {len(inside)} 段，空段落 {blank_count} 段）")   # 打印段落总数
    print(f"  表格：{document.get('table_count', 0)} 个")             # 打印表格数
    groups = []                                                     # 表格外段落的分组
    for paragraph in body_texted:                                   # 只拿有文字的段落归类
        signature = spec_signature(paragraph["spec"])               # 算这一段的指纹
        for group in groups:                                        # 看有没有现成的同类
            if group[0] == signature:                               # 指纹一样
                group[1].append(paragraph)                          # 加进这一组
                break                                               # 不用再找
        else:                                                       # 没有同类
            groups.append((signature, [paragraph]))                 # 新开一组
    groups.sort(key=lambda group: (-len(group[1]), -(group[0][1] or 0)))   # 段数多的在前，段数相同字号大的在前
    if groups:                                                      # 有表格外段落才分析
        main_signature, main_paras = groups[0]                      # 段数最多的那一组就是正文
        print("【正文实际用的规格】")                                 # 分节标题
        print(f"  共 {len(main_paras)} 段（全篇最多的那一组）")       # 说明这是主体
        print(f"  {describe_spec(main_paras[0]['spec'])}")           # 打印正文规格
        sample = next((item["text"][:28] for item in main_paras if item["text"]), "")   # 找一句正文当例子
        if sample:                                                  # 有例子就打印
            print(f"  例：{sample}")                                 # 打印例子
        main_size = main_signature[1]                               # 正文的字号，可能压根没写
        if main_size:                                               # 有明确字号才能比大小
            heads = [group for group in groups[1:] if (group[0][1] or 0) > main_size]   # 字号比正文大的组
        else:                                                       # 正文没有明确字号
            heads = []                                              # 没法比，就不做标题判断
        print("【字号比正文大的段落（一般就是标题）】")                 # 分节标题
        if heads:                                                   # 有标题就逐个打印
            for _, items in heads:                                  # 遍历每个标题组
                print(f"  共 {len(items)} 段：{describe_spec(items[0]['spec'])}")   # 打印这一组的规格
                sample = next((item["text"][:28] for item in items if item["text"]), "")   # 找句例子
                if sample:                                          # 有例子就打印
                    print(f"    例：{sample}")                       # 打印例子
        elif main_size:                                             # 有字号，但没人比它大
            print("  没有，全篇字号一致。")                           # 说明情况
        else:                                                       # 正文连字号都没写
            print("  正文没有写明字号，没法判断哪些段落是标题。")       # 说明情况
        others = [group for group in groups[1:] if (group[0][1] or 0) <= (main_size or 0)]   # 其余零散段落
        if others:                                                  # 有就简单列一下
            print("【其它段落】")                                    # 分节标题
            for _, items in others[:5]:                             # 最多列五组
                print(f"  共 {len(items)} 段：{describe_spec(items[0]['spec'])}")   # 打印这一组的规格
                sample = next((item["text"][:28] for item in items if item["text"]), "")   # 找句例子
                if sample:                                          # 有例子就打印
                    print(f"    例：{sample}")                       # 打印例子
    else:                                                           # 表格外一段都没有
        print("【正文实际用的规格】")                                 # 分节标题
        print("  这个文件除表格外没有正文段落。")                      # 说明情况
    print("【表格里的文字】")                                        # 分节标题
    if inside_texted:                                               # 表格里有文字
        align_counts = count_by(inside_texted, lambda item: ALIGN_TEXT.get(item["spec"].get("alignment"), "跟段落样式走"))   # 统计对齐
        print(f"  对齐：{format_counts(align_counts)}")               # 打印对齐分布
        size_counts = count_by(inside_texted, lambda item: f"{item['spec']['size_pt']:g}pt" if item["spec"].get("size_pt") else "跟段落样式走")   # 统计字号
        print(f"  字号：{format_counts(size_counts)}")                # 打印字号分布
    else:                                                           # 没有表格内容
        print("  这个文件里没有表格内容。")                            # 说明情况
    print("【正文段落实际对齐分布】")                                 # 分节标题
    if body_texted:                                                 # 有正文段落才统计
        align_counts = count_by(body_texted, lambda item: ALIGN_TEXT.get(item["spec"].get("alignment"), "没写对齐"))   # 统计对齐
        print(f"  {format_counts(align_counts)}")                    # 打印对齐分布
    else:                                                           # 没有正文段落
        print("  没有正文段落可统计。")                                # 说明情况
    print("【样式表里定义的规格（仅供参考，会被段落上的写法覆盖）】")       # 分节标题
    interesting = [item for item in styles if item.get("east_asian") or item.get("size_pt")]   # 只挑有信息的样式
    for item in interesting[:12]:                                   # 最多展示 12 条
        parts = [f"样式 {item['style']}"]                            # 起始片段
        if item.get("east_asian"):                                  # 中文字体
            parts.append(f"中文 {item['east_asian']}")               # 写上
        if item.get("latin"):                                       # 西文字体
            parts.append(f"西文 {item['latin']}")                    # 写上
        if item.get("size_pt"):                                     # 字号
            parts.append(f"字号 {item['size_pt']:g}pt")              # 写上
        line_text = describe_line_spacing(item)                     # 行距翻译成人话
        if line_text:                                               # 有就写上
            parts.append(line_text)                                 # 追加
        if item.get("space_before_pt") or item.get("space_after_pt"):   # 段前段后距不为零
            parts.append(f"段前 {item.get('space_before_pt', 0):g}pt／段后 {item.get('space_after_pt', 0):g}pt")   # 写上
        if item.get("first_line_indent_chars"):                     # 字符级首行缩进
            parts.append(f"首行缩进 {item['first_line_indent_chars']:g} 字符")   # 写上
        elif item.get("first_line_indent_cm"):                      # 长度级首行缩进
            parts.append(f"首行缩进 {item['first_line_indent_cm']:.2f}cm")   # 写上
        if item.get("alignment"):                                   # 对齐
            parts.append(f"对齐 {ALIGN_TEXT.get(item['alignment'], item['alignment'])}")   # 翻成中文
        print("  " + "，".join(parts))                               # 打印该样式的规格
    if not interesting:                                             # 样式表里什么格式都没写
        print("  样式表里没有定义字体或字号。")                        # 说明情况
    print("-" * 60)                                                 # 打印分隔线
    print("提示：以上就是文件里真正生效的规格（段落上写的优先，样式次之）。")   # 使用提示
    print("      要用预设替换的话，先把上面每一项跟用户确认一遍差异。")       # 使用提示

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="反推现有 DOCX 的排版规格")   # 构造参数解析器
    parser.add_argument("input", help="待分析的 DOCX 路径")                  # 位置参数：文件
    parser.add_argument("--detail", action="store_true", help="逐段列出每一段的生效规格，用于核对分组")   # 可选开关
    args = parser.parse_args()                                             # 解析参数
    try:                                                                   # 尝试解包
        styles_xml = read_member(args.input, "word/styles.xml")             # 读取样式表
        document_xml = read_member(args.input, "word/document.xml")         # 读取正文
    except Exception as error:                                             # 解包失败
        print(f"无法读取 DOCX：{error}", file=sys.stderr)                    # 打印错误
        return 2                                                           # 返回错误码
    styles = parse_styles(styles_xml)                                      # 解析样式表
    defaults = parse_defaults(styles_xml)                                  # 解析文档默认格式
    style_map = {item["style"]: item for item in styles}                   # 样式号到样式的映射，供继承链查找
    default_ids = default_style_ids(styles)                                # 找出默认段落样式与默认字符样式
    document = parse_document(document_xml)                                # 解析页面设置
    paragraphs = parse_paragraphs(document_xml)                            # 解析每个段落
    for paragraph in paragraphs:                                           # 逐段算出最终生效的格式
        paragraph["spec"] = effective_spec(paragraph, style_map, defaults, default_ids)   # 把结果挂回段落上
    report(args.input, styles, document, paragraphs)                       # 打印报告
    if args.detail:                                                        # 用户要看逐段明细
        print_detail(paragraphs)                                           # 打印每一段
    return 0                                                               # 返回成功码

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                               # 用返回值作为退出码

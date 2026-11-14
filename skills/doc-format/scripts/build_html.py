#!/usr/bin/env python3
# 本脚本把 Markdown 按规格卡渲染成 HTML，专门服务于公众号 / 屏幕阅读类预设。
#
# 它只做一件事：把预设里定义的参数忠实翻译成 HTML。
#   html.*                  → 正文宽度上限、样式是否内联、外链是否保留
#   screen.body.*           → 字号、行高、字色、对齐、左右内边距、字间距
#   paragraph.*             → 段间距与首行缩进（屏幕场景用段间距，不用缩进）
#   headings.h1/h2/h3       → 各级标题的字号、字重、上下留白
#   screen.quote.*          → 引用块的左侧竖线、背景、内边距、字色
#   screen.image.*          → 图片宽度、圆角、上下留白
#   figures_tables.*        → 表头与数据格的对齐方式
#
# 屏幕阅读参数统一放在 screen 段下，与 fonts.body（纸上正文字体）在结构上分开，
# 避免「同一个 body 键其实是两件事」这种误读。
#
# 交付边界：产物只有一个 HTML 文件，图片按预设规则直接渲染成 <img>。
# 脚本不生成「粘贴用/预览用」双版本，也不生成素材清单 —— 图片粘进公众号后要用户自己重新上传，
# 视频与 GIF 无法靠粘贴进入正文，这两件事由 skill 在对话里提醒用户，不靠脚本造占位文件。
#
# 用法：
#   python3 scripts/build_html.py --spec typography.spec.yaml --input article.md --output article.html

import argparse   # 用于解析命令行参数
import html       # 用于转义 HTML 特殊字符
import os         # 用于路径处理
import re         # 用于解析 Markdown
import sys        # 用于控制退出码与错误输出

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # 把 scripts 目录加入模块路径
import spec_lib   # 导入公共库

# 把「样式键值对」拼成内联的 style="..." 属性。
# 之所以全部内联：公众号编辑器会丢弃 <style> 标签与 class 选择器，只保留元素上的内联样式。
def style_attr(pairs):
    parts = []                                                       # 初始化样式片段列表
    for key, value in pairs:                                         # 遍历样式键值
        if value is None or value == "":                             # 跳过空值
            continue                                                 # 继续下一项
        parts.append(f"{key}:{value}")                               # 拼成一条 CSS 声明
    return f' style="{";".join(parts)}"' if parts else ""            # 拼成完整属性，无样式时返回空串

# 从规格卡里取出本脚本需要的全部参数，缺失时按屏幕阅读惯例给默认值
def html_config(spec):
    # 屏幕阅读参数优先取 screen 段；为兼容早期规格卡，仍接受顶层 body/quote/image
    screen = spec.get("screen") or {}                                 # 取屏幕阅读段
    body = screen.get("body") or spec.get("body") or {}              # 屏幕阅读正文段
    paragraph = spec.get("paragraph") or {}                          # 段落段
    headings = spec.get("headings") or {}                            # 标题段
    quote = screen.get("quote") or spec.get("quote") or {}           # 引用段
    image = screen.get("image") or spec.get("image") or {}           # 图片段
    html_cfg = spec.get("html") or {}                                # HTML 段
    figures = spec.get("figures_tables") or {}                       # 图表规范段
    return {                                                         # 返回整理后的配置字典
        "max_width_px": html_cfg.get("max_width_px", 677),           # 正文宽度上限
        "allow_external_links": html_cfg.get("allow_external_links", False),   # 是否保留外链
        "body_size": body.get("font_size_px", 15),                   # 正文字号
        "line_height": body.get("line_height", 1.75),                # 行高倍数
        "color": body.get("color", "#3F3F3F"),                       # 正文字色
        "align": body.get("text_align", "left"),                     # 对齐方式
        "pad_left": body.get("padding_left_px", 16),                 # 左内边距
        "pad_right": body.get("padding_right_px", 16),               # 右内边距
        "letter_spacing": body.get("letter_spacing", "0.5px"),       # 字间距
        "para_margin": paragraph.get("margin_bottom_em", 1.0),       # 段间距
        "indent": paragraph.get("text_indent", 0),                   # 首行缩进，屏幕场景默认 0
        "headings": headings,                                        # 标题配置
        "quote": quote,                                              # 引用配置
        "image": image,                                              # 图片配置
        # 表格对齐不预设风格：规格卡没写就是空串，渲染时完全不动 text-align，保持浏览器默认。
        # 想强制某种对齐时，在规格卡的 figures_tables 段显式写 header_alignment / text_column_alignment / number_column_alignment。
        "header_align": figures.get("header_alignment") or "",               # 表头对齐，未声明则不干预
        # 下面两项直接用规格卡里的字段名，好让 spec_lib.resolve_column_alignments 能直接读，
        # 不用再各起一套别名（别名是漂移的温床）
        "text_column_alignment": figures.get("text_column_alignment") or "",      # 文字列对齐，未声明则不干预
        "number_column_alignment": figures.get("number_column_alignment") or "",  # 数字列对齐，未声明则不干预
        # 表格线型也要读进来。以前这里是写死的三线表：规格里改了线型，HTML 照旧出三线表，
        # 一句话都不说 —— 用户以为改了规格，拿到文件才发现没生效（实测）。
        "table_style": spec_lib.resolve_table_style(figures.get("table_style"))[0],   # 表格线型（归一化后）
    }

# 各级标题在规格卡没配字号时的兜底字号，按层级递减
HEADING_DEFAULTS = {1: 20, 2: 18, 3: 16, 4: 15, 5: 15, 6: 15}        # 一到六级的默认字号

# 取某一级标题的内联样式
def heading_style(cfg, level):
    headings = cfg["headings"] or {}                                  # 取标题配置
    item = spec_lib.resolve_heading(headings, level)                  # 兼容 doc_title / chapter / levelN / hN 各种键名
    # 字号优先用屏幕单位 px；预设只写了纸质磅值时按 1pt≈1.33px 换算，跨载体复用同一张规格卡才不至于丢字号
    size = item.get("font_size_px") or (round(float(item["size_pt"]) * 1.33) if item.get("size_pt") else None)   # 取字号
    size = size or HEADING_DEFAULTS.get(level, 16)                    # 都没有则用兜底字号
    return style_attr([                                               # 拼样式
        ("font-size", f"{size}px"),                                   # 字号
        ("font-weight", "bold" if item.get("bold", True) else "normal"),   # 字重
        ("line-height", str(cfg["line_height"])),                     # 行高与正文一致
        ("color", "#000000"),                                         # 标题用纯黑
        ("margin", f"{item.get('margin_top_em', 1.4)}em 0 {item.get('margin_bottom_em', 0.8)}em"),   # 上下留白
        ("text-align", item.get("alignment", "left")),                # 对齐
    ])

# 取正文段落的内联样式。屏幕阅读用段间距区分段落，因此首行缩进通常为 0
def paragraph_style(cfg):
    return style_attr([
        ("font-size", f"{cfg['body_size']}px"),                       # 字号
        ("line-height", str(cfg["line_height"])),                     # 行高
        ("color", cfg["color"]),                                      # 字色
        ("text-align", cfg["align"]),                                 # 对齐
        ("letter-spacing", cfg["letter_spacing"]),                    # 字间距
        ("margin", f"0 0 {cfg['para_margin']}em"),                    # 段间距
        ("text-indent", f"{cfg['indent']}em" if cfg["indent"] else "0"),   # 首行缩进
        ("word-break", "break-word"),                                 # 长英文与网址自动换行
    ])

# 取图片的内联样式，参数全部来自预设的 image 段
def image_style(cfg):
    image = cfg["image"] or {}                                        # 取图片配置
    return style_attr([
        ("width", image.get("width", "100%")),                        # 图片宽度
        ("border-radius", f"{image.get('border_radius_px', 4)}px"),   # 圆角
        ("margin", f"{image.get('margin_top_em', 1.0)}em 0 {image.get('margin_bottom_em', 1.0)}em"),   # 上下留白
        ("display", "block"),                                         # 块级显示，避免行内间隙
    ])

# 把 Markdown 行内语法转成带内联样式的 HTML
def inline_to_html(text, cfg):
    # 第一步：抽出图片，换成占位标记，稍后用图片样式渲染
    images = []                                                       # 收集本行解析到的图片
    def image_repl(match):
        alt = match.group(1)                                          # 图片替代文字
        src = match.group(2)                                          # 图片地址
        images.append({"alt": alt, "src": src})                       # 记录图片信息
        return f"\u0001IMG{len(images) - 1}\u0001"                    # 用占位标记替换
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", image_repl, text)       # 处理图片语法
    # 第二步：抽出链接。预设不允许外链时（公众号默认），只保留链接文字、不生成 a 标签
    def link_repl(match):
        label = match.group(1)                                        # 链接文字
        url = match.group(2)                                          # 链接地址
        if not cfg["allow_external_links"]:                           # 预设不允许外链（公众号默认）
            return label                                              # 只保留链接文字，不生成 a 标签
        link_style = style_attr([                                     # 允许外链时给链接加上样式
            ("color", cfg["color"]),                                  # 链接颜色跟随正文字色
            ("text-decoration", "underline"),                         # 加下划线，与普通文字区分
        ])
        safe_url = html.escape(url, quote=True)                       # 转义链接地址里的特殊字符
        return f'<a href="{safe_url}"{link_style}>{label}</a>'         # 拼出可点链接
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, text)        # 处理链接语法
    # 第三步：转义剩余的 HTML 特殊字符，避免用户文本破坏结构
    text = html.escape(text, quote=False)                             # 转义 < > &
    # 第四步：按顺序还原行内语法。粗体必须在斜体之前处理，否则加粗用的两个星号会被斜体规则吃错
    text = re.sub(r"\*\*([^*]+)\*\*", r'<strong style="font-weight:bold">\1</strong>', text)   # 粗体
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r'<em style="font-style:italic">\1</em>', text)   # 斜体
    text = re.sub(                                                    # 行内代码
        r"`([^`]+)`",                                                 # 匹配反引号包裹的内容
        lambda m: "<span" + style_attr([                              # 用 span 加样式模拟代码格式
            ("font-family", "Menlo,Consolas,monospace"),              # 等宽字体
            ("background", "#F2F2F2"),                                # 浅灰底色
            ("padding", "2px 4px"),                                   # 内边距
            ("border-radius", "3px"),                                 # 圆角
            ("font-size", f"{cfg['body_size'] - 1}px"),               # 比正文小一号
        ]) + ">" + m.group(1) + "</span>",                            # 拼出完整标签
        text)
    # 第五步：把图片占位标记换成真正的 img 标签，样式取自预设的 image 段
    for index, item in enumerate(images):                             # 遍历本行图片
        tag = ('<img src="' + html.escape(item["src"], quote=True) + '"'
               + ' alt="' + html.escape(item["alt"] or "", quote=True) + '"'
               + image_style(cfg) + ">")                              # 拼出 img 标签
        text = text.replace(f"\u0001IMG{index}\u0001", tag)           # 替换占位标记
    return text                                                       # 返回行内 HTML

# 渲染表格：对齐方式由 spec_lib.resolve_column_alignments 统一判定（源文件标记优先，
# 其次规格卡显式声明的数字列/文字列对齐，都没有就不写 text-align）。
# 只用横向框线（顶线、表头下线、底线）形成三线表，不画竖线。
def render_table(rows, aligns, cfg):
    if not rows:                                                       # 空表
        return ""                                                      # 返回空串
    column_align = spec_lib.resolve_column_alignments(rows, aligns, cfg)   # 先按列算好对齐方式（公共判定）
    # 线型决定框线怎么画：全框线是四边都画黑线；三线表只在行与行之间画浅灰横线打底，
    # 上中下三条主线的加粗放在下面按行处理。
    grid_mode = cfg["table_style"] == "grid"                           # 规格要的是全框线
    border_rules = [("border", "1px solid #000000")] if grid_mode else [("border-bottom", "1px solid #E0E0E0")]
    common = [                                                         # 单元格通用样式
        ("padding", "8px 10px"),                                       # 内边距
        ("font-size", f"{cfg['body_size']}px"),                        # 字号
        ("line-height", "1.6"),                                        # 行高
    ] + border_rules                                                   # 按线型加上框线
    parts = ["<table" + style_attr([("width", "100%"), ("border-collapse", "collapse"), ("margin", "1em 0")]) + ">"]   # 表格开始标签
    for row_index, row in enumerate(rows):                             # 遍历每一行
        parts.append("<tr>")                                           # 行开始标签
        for cell_index, cell in enumerate(row):                        # 遍历单元格，同时记住列号
            tag = "th" if row_index == 0 else "td"                     # 表头用 th，内容用 td
            styles = list(common)                                      # 复制通用样式
            if row_index == 0:                                         # 表头行
                # 表头优先跟随该列的 Markdown 标记（GFM 里标记本就管整列，含表头）；
                # 没有标记时再看规格卡显式声明的 header_alignment；都没有就不写 text-align。
                header_align = column_align[cell_index] or cfg["header_align"]   # 表头对齐方式，空串表示不干预
                if header_align:                                       # 只有拿到明确对齐要求才写
                    styles.append(("text-align", header_align))        # 写入表头对齐
                styles.append(("font-weight", "bold"))                 # 加粗
                if not grid_mode:                                      # 只有三线表需要单独画出顶线
                    styles.append(("border-top", "1.5px solid #000000"))   # 上框线
            else:                                                      # 数据行
                if column_align[cell_index]:                           # 只有拿到明确对齐要求才写
                    styles.append(("text-align", column_align[cell_index]))   # 整列统一对齐，不在行与行之间跳
            if row_index == len(rows) - 1 and not grid_mode:           # 三线表且是最后一行
                styles.append(("border-bottom", "1.5px solid #000000"))   # 下框线，与顶线呼应，形成三线表
            parts.append(f"<{tag}" + style_attr(styles) + ">" + inline_to_html(cell, cfg) + f"</{tag}>")   # 单元格内容
        parts.append("</tr>")                                          # 行结束标签
    parts.append("</table>")                                           # 表格结束标签
    return "".join(parts)                                              # 返回表格 HTML

# 渲染全部块为 HTML 主体
def render_blocks(blocks, cfg):
    parts = []                                                         # 初始化输出片段列表
    for block in blocks:                                               # 遍历所有块
        kind = block["type"]                                           # 取块类型
        if kind == "heading":                                          # 标题
            level = block["level"]                                     # 取标题层级
            parts.append(f"<h{level}{heading_style(cfg, level)}>{inline_to_html(block['text'], cfg)}</h{level}>")
        elif kind == "paragraph":                                      # 普通段落
            parts.append(f"<p{paragraph_style(cfg)}>{inline_to_html(block['text'], cfg)}</p>")
        elif kind == "list":                                           # 列表项
            marker = "• " if not block["ordered"] else "· "             # 统一用项目符号，屏幕阅读下更稳
            parts.append(f"<p{paragraph_style(cfg)}>{marker}{inline_to_html(block['text'], cfg)}</p>")
        elif kind == "quote":                                          # 引用块
            quote = cfg["quote"] or {}                                 # 取引用配置
            # 引用按「段」渲染：源文里换了段，引用里也必须换段。
            # 旧代码把整块引用并成一段文字（block["text"]），多段引文会挤成一个长条（实测）。
            inner = []                                                 # 引用内部的各个段落
            for quote_index, quote_paragraph in enumerate(block.get("paragraphs") or [block["text"]]):   # 逐段渲染
                inner.append("<p" + style_attr([                       # 每个引用段落各起一个 p，段与段才会分开
                    ("margin", "0" if quote_index == 0 else "0.9em 0 0"),   # 段间留白；首段不留上边距，避免引用块顶部发空
                    ("text-indent", "0"),                              # 引用内部不再首行缩进（整块已经缩进过了）
                ]) + ">" + inline_to_html(quote_paragraph, cfg) + "</p>")   # 段落内容
            parts.append('<blockquote' + style_attr([
                ("border-left", f"{quote.get('border_left_px', 3)}px solid {quote.get('border_color', '#D0D0D0')}"),   # 左侧竖线
                ("background", quote.get("background", "#F7F7F7")),     # 背景色
                ("padding", f"{quote.get('padding_px', 12)}px"),        # 内边距
                ("color", quote.get("color", "#666666")),               # 字色
                ("margin", f"1em 0 {cfg['para_margin']}em"),            # 上下留白
                ("font-size", f"{cfg['body_size']}px"),                 # 字号
                ("line-height", str(cfg["line_height"])),               # 行高
            ]) + ">" + "".join(inner) + "</blockquote>")                # 把各段落拼进引用块
        elif kind == "code":                                           # 代码块
            escaped = html.escape(block["text"], quote=False)           # 转义代码内容
            parts.append('<pre' + style_attr([
                ("background", "#F5F5F5"),                              # 浅灰底色
                ("border-radius", "4px"),                               # 圆角
                ("padding", "12px"),                                    # 内边距
                ("overflow-x", "auto"),                                 # 横向可滚动
                ("font-family", "Menlo,Consolas,monospace"),            # 等宽字体
                ("font-size", f"{max(cfg['body_size'] - 2, 11)}px"),    # 字号比正文小
                ("line-height", "1.6"),                                 # 行高
            ]) + ">" + escaped + "</pre>")
        elif kind == "table":                                          # 表格
            parts.append(render_table(block["rows"], block.get("aligns") or [], cfg))   # 传入该表的对齐标记
        elif kind == "rule":                                           # 分隔线
            parts.append('<hr' + style_attr([("border", "none"), ("border-top", "1px solid #E0E0E0"), ("margin", "1.6em 0")]) + ">")
        elif kind == "anchor":                                         # HTML 锚点
            # 公众号目录靠锚点跳转，这里必须保留（Word 那边会丢掉它）
            parts.append(f'<a id="{html.escape(block["id"], quote=True)}"></a>')
        elif kind == "image":                                          # 图片
            # 公众号的图片必须由作者在编辑器里重新上传到素材库，这里只留占位与文件名，
            # 不能假装图片已经进了公众号（外链图片会被微信过滤掉）。
            src = html.escape(block["src"], quote=True)                 # 图片地址
            alt = html.escape(block["alt"])                             # 替代文字
            parts.append(f'<p{paragraph_style(cfg)}><img src="{src}" alt="{alt}" '
                         f'style="max-width:100%;height:auto;"></p>')   # 宽度不超容器
    return "\n".join(parts)                                             # 返回拼好的主体

# 主流程：读规格、解析 Markdown、渲染、写出单个 HTML
def build(spec_path, input_path, output_path, title=None, normalize=False, allow_flat=False):
    spec = spec_lib.load_spec(spec_path)                                # 读取规格卡
    cfg = html_config(spec)                                             # 取渲染参数
    markdown = spec_lib.read_markdown(input_path, normalize)            # 读取源文件；--normalize 时在内存里先清洗一遍
    blocks = spec_lib.parse_markdown_blocks(markdown, keep_inline=True)   # 公共解析器，保留行内标记供 HTML 转换
    # 结构闸门：与 DOCX 同一道判定。公众号稿子经常是「一大段文字直接丢过来」，
    # 没有小标题的文章在手机上是一整屏密密麻麻的字，必须先跟用户确认结构再生成。
    structure = spec_lib.source_structure_report(blocks)                # 结构体检
    if structure["needs_confirmation"] and not allow_flat:              # 需要确认结构且没有放行
        print(spec_lib.describe_structure(structure), file=sys.stderr)  # 先报事实
        print("⛔ 已停止生成：这份稿子需要先跟用户确认结构。", file=sys.stderr)   # 明确说破
        print("   建议：跑 scripts/structure_check.py 拿到待确认清单，逐条问过用户、"
              "按确认结果补好层级后再生成；用户确认「就是不要标题」时加 --allow-flat 放行。",
              file=sys.stderr)                                          # 给出可执行的下一步
        return 5                                                       # 退出码 5＝结构未确认
    document_title = title or next(                                     # 取文档标题：优先命令行指定
        (b["text"] for b in blocks if b["type"] == "heading" and b["level"] == 1),   # 其次用一级标题
        os.path.splitext(os.path.basename(input_path))[0])              # 最后退回文件名
    body_html = render_blocks(blocks, cfg)                              # 渲染正文
    shell = ('<div' + style_attr([                                      # 外层容器承载正文基础样式
        ("max-width", f"{cfg['max_width_px']}px"),                      # 宽度上限
        ("margin", "0 auto"),                                           # 水平居中
        ("padding", f"16px {cfg['pad_right']}px 16px {cfg['pad_left']}px"),   # 左右内边距
        ("font-family", "-apple-system,BlinkMacSystemFont,'Helvetica Neue','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif"),   # 系统字体栈，不硬指定字体
        ("color", cfg["color"]),                                        # 字色
        ("font-size", f"{cfg['body_size']}px"),                         # 字号
        ("line-height", str(cfg["line_height"])),                       # 行高
        ("text-align", cfg["align"]),                                   # 对齐
    ]) + ">\n" + body_html + "\n</div>")                                 # 拼出完整容器
    document = ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
                f"<title>{html.escape(document_title)}</title>\n</head>\n"
                '<body style="margin:0;padding:0;background:#FFFFFF;">\n'
                f"{shell}\n</body>\n</html>\n")                          # 拼出完整文档
    output_dir = os.path.dirname(os.path.abspath(output_path)) or "."    # 取输出目录
    os.makedirs(output_dir, exist_ok=True)                               # 确保目录存在
    with open(output_path, "w", encoding="utf-8") as handle:             # 打开输出文件
        handle.write(document)                                           # 写出 HTML
    print(f"已生成：{output_path}")                                       # 打印产物路径
    print(f"  标题：{document_title}")                                    # 打印文档标题
    print(f"  正文：{cfg['body_size']}px / 行高 {cfg['line_height']} / 字色 {cfg['color']}")   # 打印核心参数
    print(f"  宽度上限：{cfg['max_width_px']}px；样式全部内联，不含 <style> 标签与 class")   # 说明内联
    print(f"  外链：{'保留为可点链接' if cfg['allow_external_links'] else '按预设去掉，只留链接文字'}")   # 说明外链处理
    print("  说明：中文与西文之间的空格由 md_normalize.py 在源文件阶段处理，本脚本不再补。")   # 说明空格来源
    # 规格里的线型写法不合法时，这里必须说破：用户可能以为自己改了规格，其实是写错了。
    style_note = spec_lib.resolve_table_style((spec.get("figures_tables") or {}).get("table_style"))[1]   # 取线型的说明
    if style_note:                                                      # 有说明就是写法有问题
        print(f"  注意：{style_note}")                                    # 当面说清
    return 0                                                            # 返回成功码

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="按规格卡把 Markdown 渲染成内联样式的 HTML")   # 构造参数解析器
    parser.add_argument("--spec", required=True, help="规格卡 YAML 路径")            # 规格卡路径
    parser.add_argument("--input", required=True, help="输入的 Markdown 路径")       # 输入文件
    parser.add_argument("--output", required=True, help="输出的 HTML 路径")          # 输出文件
    parser.add_argument("--title", help="覆盖文档标题")                             # 标题覆盖项
    parser.add_argument("--normalize", action="store_true",                        # 源文件清洗开关，默认关闭
                        help="生成前在内存里做一遍源文件规范化（不落盘、不留中间文件）")   # 参数说明
    parser.add_argument("--allow-flat", action="store_true",                       # 结构放行开关，默认关闭
                        help="允许「没有标题层级」的稿子照样生成。只在用户明确说过"
                             "「这篇就是不要标题」时使用；否则应先问清结构再生成")      # 参数说明
    args = parser.parse_args()                                                     # 解析参数
    if not os.path.exists(args.input):                                             # 输入不存在
        print(f"输入文件不存在：{args.input}", file=sys.stderr)                       # 打印错误
        return 2                                                                   # 返回错误码
    try:                                                                           # 捕获渲染异常
        return build(args.spec, args.input, args.output, args.title, args.normalize,
                     args.allow_flat)                                              # 执行渲染
    except Exception as error:                                                      # 渲染出错
        print(f"生成失败：{error}", file=sys.stderr)                                  # 打印错误
        return 1                                                                   # 返回失败码

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                                       # 用返回值作为退出码

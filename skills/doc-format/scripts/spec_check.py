#!/usr/bin/env python3
# 本脚本对规格卡做体检：检查国标引用是否可靠、参数是否自相矛盾、载体能力是否匹配、字体是否可用。
# 依据 references/spec-schema.md 的「规格校验规则」。
# 用法：python3 scripts/spec_check.py typography.spec.yaml

import argparse   # 用于解析命令行参数
import datetime   # 用于比较规格卡的复检日期是否已过期
import sys        # 用于控制退出码
import os         # 用于拼接模块路径

# 把 scripts 目录加入模块路径，保证能导入同目录下的公共库
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import spec_lib   # 导入本项目的公共库

# 从一份 standards.md 文本的表格里读出「标准号 → 状态」。
# 表格格式：第 1 列标准号、第 3 列状态；遇到「未能核验」那张表就停，
# 那张表列的是不得引用的标准，不是可引用的清单。
def parse_standard_table(text):
    table = {}                                            # 标准号 → 状态
    for line in text.split("\n"):                         # 逐行扫描
        if "未能核验" in line:                             # 走到「未能核验的标准」表就停
            break                                         # 那张表里是「不得引用」的说明，不是可引用的清单
        if not line.startswith("|"):                      # 只看表格行
            continue                                      # 跳过非表格行
        cells = [cell.strip().replace("**", "") for cell in line.strip("|").split("|")]   # 拆分单元格并去掉加粗标记
        if len(cells) < 3:                                # 列数不够
            continue                                      # 跳过
        number, status = cells[0], cells[2]               # 第 1 列标准号，第 3 列状态
        if not number.startswith("GB"):                   # 表头或说明行
            continue                                      # 跳过
        table[number] = status                            # 记录状态
    return table                                          # 返回这张表解析出来的结果

# 读出「标准号 → 状态」，出厂层与用户层都读，**用户层覆盖出厂层**。
#
# 为什么不再在代码里写一份清单：以前这里硬编码了一串标准号，与 standards.md 各存一份，
# 标准更新时改了一处漏一处 —— 要么放行了已废止的标准，要么拦住了刚发布的现行标准。
# 现在核验记录只有 standards.md 一个出处，代码只负责读。
#
# 为什么要读两层：用户自己新核验的标准写在用户数据目录里，升级 skill 覆盖不到；
# 只读出厂那份的话，用户刚核验完的新标准会被判成「未登记」，直接把他的生成拦住。
def load_verified_standards():
    layers = spec_lib.read_reference_layers("standards.md")   # 两层：用户层在前，出厂层在后
    if not layers:                                            # 两层都没有
        return None                                           # 返回 None，调用方转成警告
    merged = {}                                               # 合并结果
    for _label, text in reversed(layers):                     # 先叠出厂层，再叠用户层 —— 后来的覆盖先前的
        merged.update(parse_standard_table(text))             # 逐层合并
    return merged or None                                     # 空表按读不到处理

# 检查国标引用是否可靠：声称国标必须有标准号，且标准号要在已核验清单里
def check_standard(meta):
    errors = []                                  # 初始化错误列表
    warnings = []                                # 初始化警告列表
    source_type = meta.get("source_type", "")    # 取规格来源类型
    standard = meta.get("standard")              # 取标准号
    if source_type == "国标" and not standard:    # 声称国标却没写标准号
        errors.append("来源类型为国标，但未填写标准号，属于不可核验的引用")
    if source_type in ("惯例", "平台") and standard:   # 惯例却写了标准号
        warnings.append(f"来源类型为{source_type}，却填写了标准号 {standard}，请确认不是编造")
    if standard:                                 # 若填了标准号
        verified = load_verified_standards()     # 读已核验清单（出厂 + 用户，用户优先）
        if verified is None:                     # 清单读不到
            warnings.append("读不到标准核验记录（出厂与用户两层都没有），无法核验标准号是否已登记，请人工确认")
        elif standard not in verified:           # 不在清单内
            errors.append(f"标准号 {standard} 未出现在已核验清单中（出厂层与你的用户层都查过），不得引用")
        elif "废止" in verified[standard]:        # 登记了但状态是废止
            warnings.append(f"{standard} 在标准核验记录里的状态为「废止」，"
                            f"请改用现行版本，或说明沿用旧版的理由")
    # 时效字段检查：没有核验日期就无法判断这份规格有多旧
    verified_at = meta.get("verified_at")        # 取核验日期
    recheck_after = meta.get("recheck_after")    # 取复检日期
    today = datetime.date.today().isoformat()    # 取今天日期
    if not verified_at:                          # 缺少核验日期
        warnings.append("缺少 meta.verified_at，无法判断这份规格有多旧；展示给用户时必须说明核验日期")
    if not recheck_after:                        # 缺少复检日期
        warnings.append("缺少 meta.recheck_after，无法判断何时该复检；建议填核验日期 + 1 年")
    if recheck_after and recheck_after < today:  # 已过复检日期
        errors.append(f"meta.recheck_after 为 {recheck_after}，已过期（今天 {today}）。"
                      f"必须先跑 check_standard_updates.py 联网复查标准现行性，再决定是否沿用")
    return errors, warnings                      # 返回错误与警告

# 检查页面参数是否自相矛盾
def check_page(spec):
    errors = []                                  # 初始化错误列表
    warnings = []                                # 初始化警告列表
    page = spec.get("page") or {}                # 取页面段
    # 逐边检查页边距是否过小
    for key, label in [("margin_top_mm", "上边距"), ("margin_bottom_mm", "下边距"),
                       ("margin_left_mm", "左边距"), ("margin_right_mm", "右边距")]:
        value = page.get(key)                    # 取该边距数值
        if value is None:                        # 未设置则跳过
            continue
        if float(value) < 10:                    # 小于 10mm 视为过小
            errors.append(f"{label} 为 {value}mm，过小，装订会吃掉正文或无法打印")
        elif float(value) < 15:                  # 小于 15mm 给出警告
            warnings.append(f"{label} 为 {value}mm，偏小，请确认打印机可打印范围")
    # 纸张尺寸必须能解析出来。写 `size: A4` 却没有任何代码认识它，是真实发生过的 bug
    # （2026-09-20 发现）：声明 A4 的预设静默出成 Letter，报告上还什么都不显示。
    # 只对纸质载体提这条。公众号（wechat-cn）本来就没有「纸张」这个概念，
    # 对它报「没写纸张尺寸」是纯噪音 —— 预设里也根本没有 page 段。
    carriers = (spec.get("meta") or {}).get("carriers") or ["docx"]   # 目标载体，缺省按纸质算
    wants_paper = any(c in ("docx", "pdf") for c in carriers)         # 是否要出纸质文件
    note = spec_lib.unknown_page_size_note(spec) if wants_paper else ""   # 取纸张尺寸的提示文字
    if note:                                     # 有提示就是有问题
        warnings.append(note)                    # 记为警告（生成端会兜底 A4，不至于出废纸）
    return errors, warnings                      # 返回错误与警告

# 检查正文字号与标题字号是否层级倒挂，以及行距是否过小
def check_typography(spec):
    errors = []                                  # 初始化错误列表
    warnings = []                                # 初始化警告列表
    body = (spec.get("fonts") or {}).get("body") or {}      # 取正文字体段
    body_size = body.get("size_pt")                          # 取正文字号
    if body_size:                                            # 若设置了正文字号
        for level, cfg in (spec.get("headings") or {}).items():   # 遍历各级标题
            if not isinstance(cfg, dict):                    # 跳过非字典项
                continue
            size = cfg.get("size_pt")                        # 取标题字号
            if size and float(size) < float(body_size):      # 标题比正文小
                errors.append(f"标题 {level} 字号 {size}pt 小于正文 {body_size}pt，层级倒挂")
    paragraph = spec.get("paragraph") or {}                  # 取段落段
    mode = paragraph.get("line_spacing_mode")                # 取行距模式
    if mode == "exact" and paragraph.get("line_spacing_pt") and body_size:   # 固定值行距
        ratio = float(paragraph["line_spacing_pt"]) / float(body_size)       # 行距与字号之比
        if ratio < 1.2:                                                     # 比值过小
            warnings.append(f"固定值行距 {paragraph['line_spacing_pt']}pt 仅为字号的 {ratio:.2f} 倍，中文会挤在一起，建议 1.4 倍以上")
    if paragraph.get("first_line_indent_cm"):                # 若用了厘米表达缩进
        warnings.append("首行缩进使用了长度单位，换字号后会失准，应改为 first_line_indent_chars")
    if body.get("east_asian") and not body.get("latin"):     # 只设中文未设西文
        warnings.append("只指定了中文字体未指定西文字体，英文与数字会用中文字体渲染，观感差")
    return errors, warnings                                  # 返回错误与警告

# 检查公文版头的必填项。红头、发文字号这些内容用户稿子里通常没有，只能问用户；
# 空着就生成的话，红头会印成光秃秃的「文件」两个字，发文字号会印成「〔2026〕号」，
# 用户拿到手才发现，所以必须在体检这一步就拦住。判定逻辑与 build_docx 共用 spec_lib。
def check_masthead(spec):
    errors = []                                  # 初始化错误列表
    warnings = []                                # 初始化警告列表
    missing = spec_lib.masthead_missing_fields(spec)   # 取出缺失的必填项
    for item in missing:                         # 逐项登记为错误
        errors.append(f"红头必填项缺失：{item['label']}（{item['path']}）。{item['hint']}。"
                      f"这一项不能由脚本编造，也不要留空生成")
    return errors, warnings                      # 返回错误与警告

# 检查公文主体要素（GB/T 9704-2012 §7.3）的排版配置。
# 为什么单列一项：signature.mode 决定署名与成文日期怎么排（盖章、不盖章是两套算法），
# 写成别的词时生成端会退回默认（盖章）那套 —— 用户以为选了「不盖章」，拿到手的却是盖章版式。
# 同类的教训已经吃过一次：报告预设里写的 position: right_bottom 取值不合法，一直静默按居中排。
def check_body_elements(spec):
    errors = []                                  # 初始化错误列表
    warnings = []                                # 初始化警告列表（本项不产生警告）
    cfg = spec.get("body_elements")              # 取主体要素段
    if not isinstance(cfg, dict) or not cfg:     # 没声明：该体裁不涉及公文主体要素
        return errors, warnings                  # 直接返回
    signature = cfg.get("signature")             # 取署名配置
    mode = str(signature.get("mode") or "").strip() if isinstance(signature, dict) else ""   # 取印章模式
    if mode and mode not in ("with_seal", "without_seal"):   # 写了但不合法
        errors.append(f"body_elements.signature.mode 的值「{mode}」不是合法值，"
                      f"只支持 with_seal（加盖印章，§7.3.5.1）或 without_seal（不加盖印章，§7.3.5.2）")
    for key in ("recipient", "attachment", "signature"):     # 逐种要素核对数值字段
        entry = cfg.get(key)                                 # 取该要素配置
        if not isinstance(entry, dict):                      # 不是字典（没写或写错）
            continue                                         # 跳过
        for field in ("space_before_lines", "first_line_indent_chars"):   # 两个数值字段
            value = entry.get(field)                         # 取值
            if value is None:                                # 没写就按默认，不算错
                continue                                     # 跳过
            try:                                             # 尝试转成数字
                float(value)                                 # 能转就合法
            except (TypeError, ValueError):                  # 转不了
                errors.append(f"body_elements.{key}.{field} 的值「{value}」不是数字，"
                              f"生成时无法换算成间距与缩进")     # 记录错误
    return errors, warnings                              # 返回错误与警告

# 检查版记（GB/T 9704-2012 §7.4）的必填项，与 build_docx 生成时的拦截共用同一份判定
def check_record_section(spec):
    errors = []                                  # 初始化错误列表
    warnings = []                                # 初始化警告列表
    missing = spec_lib.record_section_missing_fields(spec)   # 取出缺失的必填项
    for item in missing:                         # 逐项登记为错误
        errors.append(f"版记必填项缺失：{item['label']}（{item['path']}）。{item['hint']}。"
                      f"这一项不能由脚本编造，也不要留空生成")
    return errors, warnings                      # 返回错误与警告

# 检查页眉：页眉里要写「书名」时，书名属于内容而不是格式，脚本不能替用户编。
# 这里只警告不阻断 —— 阻断会让所有还没填书名的书稿都生成不出来，而页眉缺一处并不影响文件成立。
def check_header(spec):
    errors = []                                  # 初始化错误列表（本项不产生错误）
    warnings = []                                # 初始化警告列表
    cfg = spec.get("header") or {}               # 取页眉配置
    if not cfg or cfg.get("enabled") is False:   # 没有页眉段或显式关掉
        return errors, warnings                  # 无需检查
    tokens = [str(cfg.get("odd_content") or "").strip(), str(cfg.get("even_content") or "").strip()]   # 两侧登记的内容标记
    if not any(tok in ("book_title", "document_title") for tok in tokens):   # 不涉及书名
        return errors, warnings                  # 无需检查
    if not str(cfg.get("book_title") or "").strip():   # 要写书名却没填
        warnings.append("页眉要求写书名（book_title / document_title），但规格卡没填 header.book_title。"
                        "不填会退回用规格名占位，正式文件请向用户确认书名后填入")
    if cfg.get("different_odd_even") and not any(
            str(cfg.get(key) or "").strip() for key in ("odd_content", "even_content")):   # 开了奇偶不同却两侧都空
        warnings.append("页眉声明了单双页不同，但 odd_content 与 even_content 都是空的，等于整篇没有页眉")
    return errors, warnings                      # 返回错误与警告

# 检查对齐类取值是否合法：页码位置、页眉对齐、题注对齐、表题/图题位置。
#
# 为什么要专门查这一项：这些字段以前全是「取值不认识就静默退回居中」，
# 于是报告预设里写的 position: right_bottom 排出来一直是居中，谁也没发现 ——
# 直到有人拿生成的文件跟规格卡逐条对，才发现预设跟产物对不上。
# 现在生成端会报出非法取值，体检端更要提前拦住：让用户在这里改掉，而不是等到生成后看警告。
def check_alignments(spec):
    errors = []                                  # 初始化错误列表
    warnings = []                                # 初始化警告列表
    allowed = "/".join(spec_lib.ALIGNMENT_VALUES)   # 合法对齐取值的说明文字
    # ① 页码位置（含单页、双页两个专用字段）
    page_number = (spec.get("footer") or {}).get("page_number") or {}   # 取页码配置
    for key, label in (("position", "页码位置"), ("odd_page", "单页码位置"), ("even_page", "双页码位置")):
        value = str(page_number.get(key) or "").strip()      # 取该字段的值
        if value and value not in spec_lib.ALIGNMENT_VALUES:  # 写了但不合法
            errors.append(f"footer.page_number.{key}（{label}）的值「{value}」不是合法值，只支持 {allowed}")
    # ② 页眉对齐
    header = spec.get("header") or {}                        # 取页眉配置
    value = str(header.get("alignment") or "").strip()        # 取页眉对齐
    if value and value not in spec_lib.ALIGNMENT_VALUES:      # 写了但不合法
        errors.append(f"header.alignment 的值「{value}」不是合法值，只支持 {allowed}")
    # ③ 图表题注：位置只有 above / below，对齐走与页码相同的取值集合
    figures = spec.get("figures_tables") or {}                # 取图表配置
    for key, label in (("table_caption_position", "表题位置"), ("figure_caption_position", "图题位置")):
        value = str(figures.get(key) or "").strip().lower()    # 取该字段的值
        if value and value not in ("above", "below"):          # 只有上下两种可能
            errors.append(f"figures_tables.{key}（{label}）的值「{value}」不是合法值，只支持 above/below")
    caption_align = str(figures.get("caption_alignment") or "").strip()   # 取题注对齐
    if caption_align and caption_align not in spec_lib.ALIGNMENT_VALUES:  # 写了但不合法
        errors.append(f"figures_tables.caption_alignment 的值「{caption_align}」不是合法值，只支持 {allowed}")
    # ④ 页眉两侧都要重排时，如果用了 outside，得说清单双页，否则算不出外侧在哪边
    if value == "outside" and not header.get("different_odd_even"):   # 页眉用外侧却没分单双页
        warnings.append("header.alignment 写了 outside（靠版心外侧），但没开 different_odd_even，"
                        "脚本只能固定按右侧处理。要真正左右分排请把单双页页眉分开")
    # ⑤ 容易放错位置的字段：页眉必须写在顶层，不能嵌进 footer 里。
    # 为什么专门查这个：实测踩过 —— 商务报告预设里误写成 footer.header，脚本只读顶层 header，
    # 于是「规格里关了页眉」和「规格里根本没写页眉」在产物上没有任何区别，
    # 用户以为改了其实没生效，而且不报错、不提示，只能靠肉眼发现页眉还在。
    nested_header = (spec.get("footer") or {}).get("header") if isinstance(spec.get("footer"), dict) else None
    if isinstance(nested_header, dict):                      # 确实嵌错位置了
        errors.append("footer.header 放错位置了：页眉要写成顶层的 header，不能嵌在 footer 里，"
                      "否则脚本读不到、设置了也不生效。请把这一段整体移到顶层")
    # ⑥ 块级间距必须是数字或留空；写了负值或字符串就地报错，而不是等到生成时才发现
    blocks_cfg = spec.get("blocks") if isinstance(spec.get("blocks"), dict) else {}   # 取块级间距段
    for key, label in (("space_before_lines", "块前空行"), ("space_after_lines", "块后空行"),
                       ("caption_gap_lines", "题注与表/图之间的小空")):
        raw = blocks_cfg.get(key)                            # 取该字段
        if raw is None:                                      # 没写就用默认值，不算错
            continue                                         # 跳过
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):   # 写了非数字
            errors.append(f"blocks.{key}（{label}）的值「{raw}」不是数字，请写空行数（如 0.5）")
        elif float(raw) < 0:                                 # 负值
            errors.append(f"blocks.{key}（{label}）的值「{raw}」是负数，间距不能为负")
    return errors, warnings                      # 返回错误与警告

# 检查表格线型：取值只支持三线表与全框线，写别的一律拦下
# 为什么单独查这一项：实测踩过「规格里写 header_shading，生成端只判了 grid、其余一律按三线表处理」，
# 用户既没拿到底纹，连三线表的表头线也一起丢了，而那时的体检端压根不看这个字段，报告还是全绿。
def check_table_style(spec):
    errors = []                                            # 初始化错误列表
    warnings = []                                          # 初始化警告列表
    figures = spec.get("figures_tables") or {}             # 取图表配置
    value = figures.get("table_style")                     # 取表格线型
    if value is None or str(value).strip() == "":          # 没写这一项
        return errors, warnings                            # 按默认的三线表处理，不必报错
    name, note = spec_lib.resolve_table_style(value)       # 交给公共库判定
    if note:                                               # 公共库给了说明，说明写法有问题
        errors.append(f"figures_tables.table_style 的值「{value}」不合法，"
                      f"只支持 {'/'.join(spec_lib.TABLE_STYLE_VALUES)}。"
                      f"表头加底纹属于美化，本 skill 不做；要全框线请写 grid")
    # 全框线是合法取值（商务报告预设本来就用它），不再额外提醒 ——
    # 内置预设每次生成都弹一句「请确认是有意为之」，属于噪音，用户看多了就不看了。
    return errors, warnings                                # 返回错误与警告

# 检查字体可用性：规格要求或用户指定的字体，本机必须真的有。
# 本项目的字体铁律是「不自动替换」，所以这里缺失一律按阻断性错误处理 ——
# 以前会按兼容档自动挑一个近似的字体顶上，字体被静默换掉，用户拿到文件才发现。
def check_fonts(spec):
    errors = []                                  # 初始化错误列表
    warnings = []                                # 初始化警告列表
    available = spec_lib.list_cjk_fonts()        # 枚举本机中文字体
    for use, required, actual in spec_lib.missing_fonts(spec, available):   # 遍历缺失的字体槽位
        advice = spec_lib.describe_font(required)                           # 查字体获取指南
        if advice and advice.get("free_download"):                          # 可以免费获取
            hint = (f"可免费获取（{advice['license']}）：{advice['download']}；"   # 给出下载入口
                    f"装完请重新跑 font_check.py 复查")
        elif advice:                                                        # 属商业字体
            hint = f"无官方免费下载（{advice['license']}）；不能自动替代。"   # 不提供「自动替代」
        else:                                                               # 字体库中没有这个字体
            hint = "字体库中没有该字体的获取信息，需联网核实能否免费下载"        # 提示联网核实
        near = spec_lib.suggest_replacements(required, available)           # 计算本机同类候选
        near_hint = f"本机同类候选：{'、'.join(near[:8])}。" if near else ""   # 组织候选提示
        if actual != required:                                              # 用户已经指定了替代
            errors.append(f"{use}：你指定的「{actual}」本机没有（规格原字体是「{required}」）。{hint}")   # 替代也不在
        else:                                                               # 尚未指定替代
            errors.append(f"{use}：规格要求的「{required}」本机没有，且没有指定替代。"              # 说明缺什么
                          f"{hint}{near_hint}请二选一：装上这个字体，或把候选之一写进规格卡的 resolved 字段")   # 给出两条路
    # 西文字体：本机枚举不到字体清单时无法验证，这时只提示不报错，避免误伤
    if not spec_lib.list_all_fonts():                                       # 枚举不到全部字体
        body = (spec.get("fonts") or {}).get("body") or {}                  # 取正文字体段
        if (body.get("latin") or "").strip():                               # 配了西文字体
            warnings.append("本机无法枚举西文字体清单（缺少 fc-list），西文字体是否真的存在未能验证")   # 提示无法验证
    return errors, warnings                      # 返回错误与警告

# 检查目标载体与规格段是否配套：要出 HTML 却没写 html 段，样式就无法保证内联
def check_html_carrier(spec):
    errors = []                                  # 初始化错误列表
    warnings = []                                # 初始化警告列表
    carriers = (spec.get("meta") or {}).get("carriers") or []   # 取目标载体列表
    if "html" not in carriers:                   # 不含 html 载体
        return errors, warnings                  # 无需检查
    html_cfg = spec.get("html")                  # 取 html 段
    if not isinstance(html_cfg, dict):           # 缺失 html 段
        errors.append("目标载体含 html（公众号），但规格卡缺少 html 段，"
                      "无法保证样式内联，粘进公众号会掉样式")
        return errors, warnings                  # 返回
    if not html_cfg.get("inline_css", True):     # 未要求内联样式
        errors.append("html.inline_css 不是 true。公众号编辑器会丢弃 <style> 标签，样式必须内联")
    if html_cfg.get("allow_external_links"):     # 允许外链
        warnings.append("html.allow_external_links 为真，但公众号正文会去掉外部链接，"
                        "需提醒用户把链接改放到「阅读原文」或评论区")
    screen = spec.get("screen") or {}            # 取屏幕阅读段
    body = screen.get("body") or spec.get("body") or {}   # 取屏幕阅读正文段（兼容早期顶层写法）
    if body and float(body.get("line_height", 0) or 0) < 1.5:   # 屏幕行高过小
        warnings.append(f"屏幕阅读行高 {body.get('line_height')} 偏小（建议 1.6-1.8），手机上会挤")
    if not screen and not spec.get("body"):      # 既没有 screen 段也没有旧的顶层 body 段
        warnings.append("目标载体含 html，但规格卡缺少 screen 段，"
                        "字号行高将退回脚本默认值（15px / 1.75），建议显式写出来")
    return errors, warnings                      # 返回错误与警告

# 主流程：读取规格卡并汇总各类检查结果
def run(path):
    spec = spec_lib.load_spec(path)              # 读取规格卡
    all_errors = []                              # 汇总错误
    all_warnings = []                            # 汇总警告
    for name, checker in [("标准引用", lambda: check_standard(spec.get("meta") or {})),
                          ("页面参数", lambda: check_page(spec)),
                          ("字号与段落", lambda: check_typography(spec)),
                          ("字体可用性", lambda: check_fonts(spec)),
                          ("公文版头", lambda: check_masthead(spec)),
                          ("公文主体要素", lambda: check_body_elements(spec)),
                          ("公文版记", lambda: check_record_section(spec)),
                          ("页眉", lambda: check_header(spec)),
                          ("对齐取值", lambda: check_alignments(spec)),
                          ("表格线型", lambda: check_table_style(spec)),
                          ("HTML 载体", lambda: check_html_carrier(spec))]:
        errors, warnings = checker()             # 执行单项检查
        for item in errors:                      # 收集错误
            all_errors.append(f"[{name}] {item}")
        for item in warnings:                    # 收集警告
            all_warnings.append(f"[{name}] {item}")
    print(f"规格体检：{path}")                     # 打印标题
    print("=" * 60)                              # 打印分隔线
    if all_errors:                               # 若有错误
        print(f"错误 {len(all_errors)} 项（会阻断生成）：")   # 打印错误数量
        for item in all_errors:                  # 逐条打印
            print("  x", item)
    if all_warnings:                             # 若有警告
        print(f"警告 {len(all_warnings)} 项（不阻断，但需告知用户）：")   # 打印警告数量
        for item in all_warnings:                # 逐条打印
            print("  !", item)
    if not all_errors and not all_warnings:      # 全部通过
        print("全部检查通过。")                    # 打印通过信息
    return len(all_errors)                       # 返回错误数量作为退出码依据

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="排版规格卡体检")   # 构造参数解析器
    parser.add_argument("spec", help="规格卡 YAML 路径")            # 位置参数：规格卡
    args = parser.parse_args()                                     # 解析参数
    return 1 if run(args.spec) else 0                              # 有错误返回 1

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                       # 用返回值作为退出码

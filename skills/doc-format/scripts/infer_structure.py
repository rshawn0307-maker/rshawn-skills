#!/usr/bin/env python3
# 本脚本是「结构识别层」：从一份没有层级的草稿里推断出文档结构，并输出「待确认清单」。
#
# 为什么需要它：
#   小白用户丢来的 Word 或一段文字，往往没有任何层级 —— 没有 Word 的标题样式、
#   没有 Markdown 的 #。这时如果直接套规格生成，标题会退化成普通段落，
#   出来的是「一份全部都是正文的文档」，也就是用户口中的垃圾。
#
# 本脚本做什么：
#   按体裁规律，用正则识别出标题、层次、主送机关、成文日期等要素，
#   逐条给出「凭什么这么判」，并列出「拿不准、必须问用户」的项。
#
# 本脚本不做什么：
#   - 不生成任何文件（生成交给 build_*.py）
#   - 不替用户拍板。拿不准的一律进「待确认清单」，由模型转述给用户确认。
#   - 不做 OCR、不改错别字、不动措辞。
#
# 规则从哪来：
#   层次规则族、要识别哪些要素、这类体裁缺什么就不合格、哪些必须问用户，
#   全部写在 references/presets/<预设>.md 的 structure_rules / required_elements /
#   ask_elements 三段里。本脚本只负责执行，不把体裁知识写死在自己身上 ——
#   否则加一个体裁就要改一次代码。预设读不到时才回退到内置默认值。
#
# 用法：
#   python3 scripts/infer_structure.py 草稿.md --preset gov-doc-cn
#   python3 scripts/infer_structure.py 草稿.md              # 不给预设则按书籍论文规则
#   python3 scripts/infer_structure.py 草稿.md --write       # 另存带层级的 Markdown

import argparse   # 用于解析命令行参数
import io         # 用于按 UTF-8 读写文件
import os         # 用于路径处理
import re         # 用于模式匹配
import sys        # 用于控制退出码与错误输出

# 让本脚本能 import 同目录的 spec_lib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # 把 scripts 目录加入模块路径
import spec_lib                                                  # 复用预设读取能力（预设查找顺序也由它统一维护）

# ── 层次序数的识别规则（按规则族分组）────────────────────────────
# 公文层次序数，按 GB/T 9704-2012 §7.3.3：
#   第一层「一、」第二层「（一）」第三层「1.」第四层「（1）」
# 注意「一、」在公文里是第 1 层，在书籍里却排在第 3 层（前面还有章、节），
# 这就是必须分规则族的原因。
GOV_LEVELS = [
    (re.compile(r"^[一二三四五六七八九十]+\s*、"), 1),        # 一、
    (re.compile(r"^[（(][一二三四五六七八九十]+[）)]"), 2),    # （一）
    (re.compile(r"^\d+\s*[.．]\s*\S"), 3),                  # 1.
    (re.compile(r"^[（(]\d+[）)]"), 4),                      # （1）
]

# 书籍 / 论文 / 报告类：章在最外层，往下才是节与中文序号
BOOK_LEVELS = [
    (re.compile(r"^第\s*[一二三四五六七八九十百千\d]+\s*[章篇]"), 1),   # 第一章
    (re.compile(r"^第\s*[一二三四五六七八九十百千\d]+\s*节"), 2),       # 第一节
    (re.compile(r"^[一二三四五六七八九十]+\s*、"), 3),                 # 一、
    (re.compile(r"^[（(][一二三四五六七八九十]+[）)]"), 4),             # （一）
    (re.compile(r"^\d+\s*[.．]\s*\S"), 5),                           # 1.
    (re.compile(r"^[（(]\d+[）)]"), 6),                               # （1）
]

# 屏幕阅读：只做「有没有小标题」的粗分，不追求六层
SCREEN_LEVELS = [
    (re.compile(r"^[一二三四五六七八九十]+\s*、"), 1),        # 一、
    (re.compile(r"^[（(][一二三四五六七八九十]+[）)]"), 2),    # （一）
    (re.compile(r"^\d+\s*[.．]\s*\S"), 3),                  # 1.
]

# 规则族名 → 该族的层次规则。预设里 structure_rules.family 写的就是这些名字
LEVEL_FAMILIES = {"gov": GOV_LEVELS, "book": BOOK_LEVELS, "screen": SCREEN_LEVELS}   # 族名到规则的映射

# ── 各类要素的识别形态（只在预设声明了 detect_elements 时才启用）──
# 唯一出处是 spec_lib：渲染层（build_docx.py）要用同一份判断来决定怎么排这几种段落。
# 以前这里自己存一份、渲染层完全不知道有这些要素，于是「推断层认得出、渲染层排错」，
# 报告说识别到了主送机关，生成出来却是缩进两字的普通正文。
ELEMENT_DETECTORS = spec_lib.ELEMENT_DETECTORS   # 识别形态
ELEMENT_LABELS = spec_lib.ELEMENT_LABELS         # 类型 → 中文名

# 有些体裁门槛是靠「章节标题里出现某个词」来体现的，不是靠段落形态。
# 例如学位论文要求有摘要、关键词、参考文献，这三项通常就是一个二级标题加正文。
# 只按要素形态去识别会漏判，所以这里给出关键词表。
SECTION_KEYWORDS = {
    "abstract": ("摘要", "关键词", "abstract", "keywords"),        # 摘要与关键词
    "references_section": ("参考文献", "引用文献", "references"),   # 参考文献表
}

# 句末标点：标题一般不以这些结尾
SENTENCE_END = ("。", "！", "？", "；", "：", "…")   # 中文句末标点集合

# 从预设文件里读出结构规则三段
def load_preset_rules(preset_id):
    # 内置预设和用户自存预设都要找，查找顺序收在 spec_lib.preset_file() 里统一维护，
    # 免得这里和别处各写一份、漏掉某一处（历史上就漏过一次：存得进、读不出）。
    path = spec_lib.preset_file(preset_id)                        # 按标识找预设文件
    if path is None:                                              # 哪处都没有
        return None                                               # 返回空，调用方回退默认
    text = io.open(path, encoding="utf-8").read()                 # 读入预设全文
    match = re.search(r"```yaml\n(.*?)```", text, re.S)           # 抽 YAML 段
    if not match:                                                 # 抽不到
        return None                                               # 回退默认
    import yaml                                                   # 延迟导入，避免无谓依赖
    spec = yaml.safe_load(match.group(1)) or {}                   # 解析 YAML
    rules = spec.get("structure_rules") or {}                     # 结构规则段
    return {
        "family": rules.get("family") or "book",                                                  # 规则族
        # 输出 Markdown 时的层级偏移量。与 spec_lib.resolve_heading 共用同一规则：
        # 预设里若「文档标题」与「层次 1」分开（公文、学术论文就是），
        # 则 # 留给文档标题，层次序数整体后移一位，这样生成时才能映射回正确的样式。
        "shift": spec_lib.heading_shift(spec.get("headings")),                                    # 层级偏移量
        "detect_elements": rules.get("detect_elements") or [],                                    # 要识别的要素
        "required_elements": spec.get("required_elements") or [],                                 # 体裁门槛
        "ask_elements": spec.get("ask_elements") or [],                                           # 必问清单
    }

# 把一个块按给定的层级规则判级别
def detect_level(text, level_rules):
    for pattern, level in level_rules:      # 逐条规则尝试
        if pattern.match(text):             # 命中
            return level, pattern.pattern   # 返回层级与该条规则的说明
    return 0, ""                            # 都不命中则视为普通正文

# 把草稿切成块。空行分隔；Markdown 的 # 标题与表格整块保留
def split_blocks(markdown):
    blocks = []                                     # 收集块
    for chunk in re.split(r"\n\s*\n", markdown):    # 按空行切分
        text = chunk.strip()                        # 去首尾空白
        if text:                                    # 非空才收
            blocks.append(text)                     # 加入结果
    return blocks                                   # 返回块列表

# 主流程：识别结构
def infer(blocks, rules, first_block_title=False):
    level_rules = LEVEL_FAMILIES.get(rules["family"], BOOK_LEVELS)   # 取该族的层次规则
    detect = set(rules["detect_elements"])                           # 要识别的要素集合

    items = []            # 每一块的判定结果
    uncertain = []        # 拿不准、必须问用户的项
    missing = []          # 体裁要件缺口
    seen = set()          # 已识别到的要素类型，保证主送机关这类只取一次

    for index, text in enumerate(blocks):                          # 逐块判断
        first_line = text.split("\n")[0].strip()                   # 取首行（表格块只看首行）
        is_table = first_line.startswith("|")                      # 是不是表格
        heading_match = re.match(r"^(#{1,6})\s+\S", first_line)    # 是不是 Markdown 标题

        if heading_match:                                          # 已经是 Markdown 标题
            level = len(heading_match.group(1))                    # 数 # 的个数定层级
            items.append({"text": text, "type": "heading", "level": level,
                          "reason": f"Markdown 标题标记（{level} 个 #）"})   # 直接采信
            continue                                               # 下一块

        if is_table:                                               # 表格
            items.append({"text": text, "type": "table", "level": 0, "reason": "Markdown 表格"})   # 原样保留
            continue                                               # 下一块

        level, rule = detect_level(first_line, level_rules)        # 试层次序数
        if level:                                                  # 命中层次
            items.append({"text": text, "type": "heading", "level": level,
                          "reason": f"层次序数匹配 {rule}"})         # 记为标题
            continue                                               # 下一块

        # 公文类要素：只在本块还没被占用、且预设声明了要识别时才判
        if "recipient" in detect and "recipient" not in seen and index > 0 \
                and ELEMENT_DETECTORS["recipient"].match(first_line):       # 主送机关
            seen.add("recipient")                                              # 登记
            items.append({"text": text, "type": "recipient", "level": 0,
                          "reason": "以冒号结尾的短段落，符合主送机关形态"})     # 记录
            continue                                                           # 下一块

        if index >= len(blocks) - 3:                                           # 只在靠近文末处找署名与日期
            if "signature" in detect and "signature" not in seen \
                    and ELEMENT_DETECTORS["signature"].match(first_line):      # 发文机关署名
                seen.add("signature")                                          # 登记
                items.append({"text": text, "type": "signature", "level": 0,
                              "reason": "位于文末、形态符合发文机关署名"})        # 记录
                continue                                                       # 下一块
            if "date" in detect and "date" not in seen \
                    and ELEMENT_DETECTORS["date"].match(first_line):           # 成文日期
                seen.add("date")                                               # 登记
                items.append({"text": text, "type": "date", "level": 0,
                              "reason": "位于文末、形态符合成文日期"})            # 记录
                continue                                                       # 下一块

        if "attachment" in detect and ELEMENT_DETECTORS["attachment"].match(first_line):   # 附件说明
            seen.add("attachment")                                                     # 登记
            items.append({"text": text, "type": "attachment", "level": 0,
                          "reason": "以「附件」开头"})                                  # 记录
            continue                                                                   # 下一块

        items.append({"text": text, "type": "body", "level": 0, "reason": "未命中任何结构特征"})   # 普通正文

    # 首块单独处理：很可能是文档标题，但必须让用户确认，不能替用户认定
    if items and items[0]["type"] == "body" and first_block_title:   # 用户已经确认第 1 块是标题
        items[0]["type"] = "heading"                             # 就按文档标题处理
        items[0]["level"] = 1                                    # 第 1 级＝该预设里的文档标题
        items[0]["is_doc_title"] = True                          # 打上标记：输出 Markdown 时它不能跟着层级后移
        items[0]["reason"] = "用户已确认：第 1 块是文档标题"           # 依据写清楚，便于回看
    elif items and items[0]["type"] == "body":                   # 首块被当成正文，且用户没确认
        head = items[0]["text"].split("\n")[0]                    # 取首行
        short = len(head) <= 40                                   # 是否够短
        no_end = not head.endswith(SENTENCE_END)                  # 是否不以句末标点结尾
        uncertain.append({
            "item": f"第 1 块「{head[:24]}{'…' if len(head) > 24 else ''}」",
            "question": ("这看起来是文档标题（短、不以句末标点结尾），确认要作为标题吗？" if short and no_end
                         else "这一块是文档标题，还是正文的第一段？"),
            "reason": "首块、长度短、结尾无句末标点" if short and no_end else "长度偏长或以句末标点结尾，不像标题",
        })

    # 层次跳跃检查：Markdown 与 Word 的层级树不允许跳级
    levels = [item["level"] for item in items if item["type"] == "heading"]   # 所有标题的层级
    for previous, current in zip(levels, levels[1:]):                         # 相邻对比
        if current > previous + 1:                                            # 跳级
            uncertain.append({
                "item": f"层级从 {previous} 跳到 {current}",
                "question": "中间少了一级，是原稿漏写，还是这两层其实是同一层？",
                "reason": "层次序数出现跳级，层级树会不平",
            })

    heading_count = sum(1 for item in items if item["type"] == "heading")     # 标题总数
    if heading_count == 0:                                                    # 一个标题都没有
        uncertain.append({
            "item": "整篇没有识别到任何标题层级",
            "question": "这篇里哪些内容算是小标题？还是说全部都是正文？",
            "reason": "没有 Word 标题样式、没有 Markdown 的 #、也没有层次序数",
        })

    # 体裁门槛：对照预设声明的 required_elements，缺哪项就报哪项
    for entry in rules["required_elements"]:                                  # 逐项核对
        key = entry.get("key")                                                # 要素键
        label = entry.get("label") or ELEMENT_LABELS.get(key, key)             # 中文名
        if key == "chapters" or key == "heading":                             # 章节类门槛看标题数
            if heading_count == 0:                                            # 没有层级
                missing.append(f"未识别到{label}。本体裁要求分章分节，需要向用户确认怎么分。")   # 报缺口
            continue                                                          # 下一项
        if key in SECTION_KEYWORDS:                                           # 靠章节标题关键词体现的门槛
            heading_texts = [item["text"] for item in items if item["type"] == "heading"]   # 所有标题文字
            if not any(word in heading for heading in heading_texts for word in SECTION_KEYWORDS[key]):   # 没有任何标题命中关键词
                missing.append(f"未识别到{label}。本体裁这项通常要有，需要向用户确认。")   # 报缺口
            continue                                                          # 下一项
        if key not in seen:                                                   # 要素没识别到
            missing.append(f"未识别到{label}。本体裁缺这项不合规，需要向用户确认。")   # 报缺口

    return items, uncertain, missing                                          # 返回三个结果

# 把判定结果渲染成带层级的 Markdown。
# shift 为该预设的层级偏移量：公文与学术论文的预设把「文档标题」单独占掉第 1 级，
# 所以层次序数要整体后移一位（「一、」写成 ##），生成时才能还原成黑体层次标题。
def render_markdown(items, shift=0):
    lines = []                                                  # 收集输出行
    for item in items:                                          # 逐块渲染
        if item["type"] == "heading":                           # 标题
            # 文档标题（用户确认过的首块）不参与后移：它本来就该写在 # 上。
            # 后移是给「层次序数」用的（该预设把第 1 级留给文档标题，一、二、要退到第 2 级）。
            # 不给它开这个例外的话，确认过的标题会被写成 ##，与正文里的层号混成同一级。
            offset = 0 if item.get("is_doc_title") else shift    # 文档标题不加偏移量
            level = min(item["level"] + offset, 6)              # 加上偏移量并限制在 6 级以内
            lines.append("#" * level + " " + item["text"])      # 按层级加 # 号
        else:                                                   # 其余原样
            lines.append(item["text"])                          # 直接保留
        lines.append("")                                        # 块间留空行
    return "\n".join(lines).rstrip() + "\n"                      # 收尾

# 打印识别报告
def print_report(path, preset, rules, items, uncertain, missing):
    print("=" * 66)                                                          # 分隔线
    print(f"结构识别：{path}")                                                 # 标题
    print(f"采用规则：{preset or '（未指定预设）'}  规则族 {rules['family']}")     # 用了哪套规则
    if rules.get("shift"):                                                        # 该预设需要层级后移
        print(f"层级偏移：+{rules['shift']}（该预设把第 1 级留给文档标题，"
              f"层次序数在输出的 Markdown 里整体后移一位）")                       # 说明偏移原因
    print("-" * 66)                                                          # 分隔线
    print("【识别到的结构】")                                                   # 分节
    for index, item in enumerate(items, 1):                                  # 逐块打印
        label = ELEMENT_LABELS.get(item["type"], item["type"])               # 类型中文名
        if item["type"] == "heading":                                        # 标题额外标层级
            label += f" L{item['level']}"                                     # 补层级
        preview = item["text"].split("\n")[0][:28]                           # 取首行预览
        print(f"  {index:>3}. [{label}] {preview}")                           # 打印一块
        print(f"       依据：{item['reason']}")                               # 打印判定依据
    print("-" * 66)                                                          # 分隔线
    counts = {}                                                              # 统计各类型数量
    for item in items:                                                       # 逐块统计
        counts[item["type"]] = counts.get(item["type"], 0) + 1                # 累加
    print("【统计】" + "，".join(f"{ELEMENT_LABELS.get(k, k)} {v}" for k, v in counts.items()))   # 打印统计
    print("-" * 66)                                                          # 分隔线
    if uncertain:                                                            # 有待确认项
        print(f"【拿不准，必须问用户】共 {len(uncertain)} 项")                   # 分节标题
        for index, entry in enumerate(uncertain, 1):                         # 逐条打印
            print(f"  {index}. {entry['item']}")                             # 项
            print(f"     问：{entry['question']}")                            # 问法
            print(f"     依据：{entry['reason']}")                            # 依据
    else:                                                                    # 没有疑问
        print("【拿不准，必须问用户】无")                                        # 打印无
    print("-" * 66)                                                          # 分隔线
    asks = rules["ask_elements"]                                             # 预设里声明的必问项
    if missing or asks:                                                      # 有缺口或必问项
        print(f"【必须问用户】共 {len(missing) + len(asks)} 项")                 # 分节标题
        for index, entry in enumerate(missing, 1):                           # 先打印门槛缺口
            print(f"  {index}. {entry}")                                     # 打印缺口
        for offset, entry in enumerate(asks, len(missing) + 1):              # 再打印预设声明的必问项
            label = entry.get("label") or entry.get("key")                    # 中文名
            print(f"  {offset}. {label}：{entry.get('ask', '请向用户确认')}")    # 打印问法
    else:                                                                    # 既没缺口也没必问
        print("【必须问用户】无")                                              # 打印无
    print("=" * 66)                                                          # 分隔线
    print("提醒：以上只是推断结果，不是结论。必须把「拿不准」与「必须问用户」的项逐条问过用户，")   # 使用提醒
    print("      得到答复后再生成文件。不要直接拿推断结果去生成。")                # 强调不可直接生成

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="从无层级的草稿里推断文档结构")   # 构造解析器
    parser.add_argument("input", help="输入草稿路径（extract_source.py 的产物）")   # 输入
    parser.add_argument("--preset", help="目标体裁预设，如 gov-doc-cn；不给则按书籍论文规则")   # 体裁
    parser.add_argument("--write", action="store_true", help="另存带层级的 Markdown")   # 落盘开关
    parser.add_argument("--title", action="store_true",
                        help="第 1 块是文档标题（用户已确认）。不加这个开关时，首块一律只进「待确认清单」，不会替用户认定")   # 标题确认开关
    args = parser.parse_args()                                                   # 解析参数

    if not os.path.exists(args.input):                                           # 输入不存在
        print(f"文件不存在：{args.input}", file=sys.stderr)                        # 打印错误
        return 2                                                                 # 返回用法错误码

    markdown = io.open(args.input, encoding="utf-8", errors="replace").read()     # 读入草稿
    blocks = split_blocks(markdown)                                              # 切块
    if not blocks:                                                               # 空稿
        print("草稿里没有内容，无法识别结构。", file=sys.stderr)                    # 打印错误
        return 1                                                                 # 返回失败码

    rules = load_preset_rules(args.preset) if args.preset else None               # 读预设规则
    if rules is None:                                                            # 预设读不到
        rules = {"family": "book", "shift": 0, "detect_elements": [],
                 "required_elements": [], "ask_elements": []}   # 回退默认（无预设时不做偏移）
        if args.preset:                                                          # 用户给了预设但读不到
            print(f"提示：读不到预设 {args.preset} 的结构规则，已回退到默认（书籍论文规则）。", file=sys.stderr)   # 提示

    items, uncertain, missing = infer(blocks, rules, args.title)                  # 执行识别（--title 表示首块已由用户确认为标题）
    print_report(args.input, args.preset, rules, items, uncertain, missing)        # 打印报告

    if args.write:                                                               # 用户要求落盘
        # 结构稿同样是中间产物，默认落在源文件同级的 build/ 子目录
        output = os.path.join(spec_lib.staging_dir(args.input),
                              os.path.splitext(os.path.basename(args.input))[0] + ".结构稿.md")   # 输出路径
        os.makedirs(os.path.dirname(output), exist_ok=True)                        # 目录不存在就建出来
        io.open(output, "w", encoding="utf-8").write(render_markdown(items, rules["shift"]))   # 写出，套用该预设的层级偏移
        print(f"带层级的草稿已写出：{output}")                                      # 打印路径
        print("注意：这只是推断结果，仍须用户确认后才能拿去生成文件。")                 # 再次强调

    return 0                                                                     # 返回成功码

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                                     # 用返回值作为退出码

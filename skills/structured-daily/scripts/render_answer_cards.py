#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""结构化每日一练·答一道 小红书 7 卡渲染引擎（PIL 直出，v3 版式）。

用法:
  python3 render_answer_cards.py --project-root DIR --final <draft_final.json> \
      --type <题型> --topic <主题> [--outdir DIR]
  python3 render_answer_cards.py --project-root DIR --check --outdir <期目录>
      # 只复核已生成期目录的 logo 像素与 7 图存在，不重渲染

行为约定:
  - 门禁通过后直接渲染 7 张 1080×1440 PNG + 笔记文案.md；
    docx 产线（fill_answer_post.py + 模板）已退出产线归档保留，不再执行；
  - 期号读 <project-root>/图片输出/progress_answer.json 的 done 数+1（三位补零），
    无则建；给了 --outdir 且目录名含「第NNN期」时按该期重渲染（不推进期号）；
  - 正文只折行、永不截断：wrap_text 像素折行 + 行首避头标点 + 行尾不悬挂开引号；
    内容超高先自动降字号档位（正文 44→42），仍超高 FAIL exit 非 0 并指出卡片；
  - 字体（HarmonyOS Sans SC 四档）或品牌 logo 缺失即 STOP exit 非 0，不静默降级；
  - 输出限制在 <project-root>/图片输出/ 内，拒绝目录穿越；
  - 笔记文案由 final JSON 字段确定性拼装＋固定标签，不新增事实。

视觉契约见 references/DESIGN.md（OpenDesign 九段式，token 与常量同表）。
色值/字体/logo/wrap 与 wushi-daily references/card-layout.md 同源（v3 已分叉：本引擎退役金色）。

v3 版式（2026-11-22 opendesign 审查后重设计，7 卡）:
  - 字号梯 6 档：L0 132 封面主标 / L1 84 内页分节标题 / L2 56 引文·题干·观点句 /
    L3 44 正文 / L4 35 次级正文 / L5 28 页脚·微标。相邻档比 1.571/1.500/1.273/1.257/1.250
    （全部 ≥1.25 且 ≤1.6，六档同时落在 DESIGN.md §3 的区间带内）；
  - 字重 4 档：Black（≥76 显示）／Bold（56 标题、观点句）／Medium（44 正文）／
    Regular（36 次级、28 微标）——字重×字号交叉建层级，不再单靠字号；
  - 唯一强调色枣红 #87110f，面积 ≤8%（封面色块 ≤12%），每卡 ≤3 处；
    金棕 #e3c79f 已退役（暖米底＋黄铜＋espresso 深墨＝AI 指纹组合，见 DESIGN.md §9）；
  - 内页页眉＝logo 56 + 字标 28；页脚＝28 微标（去装饰横线，避免页脚抢读）；
  - 01 封面：logo 印章 96 + 右上「第 N 期 · 题型」28 + 88..132px 主题排进枣红色块
    （圆角 24，色块即视觉锚 ≥8%）+ 56px 副标 1 行 + 可选 28px 题目信息行
    （final `cover_meta`，真题元信息如「2024年6月5日 · 咸阳 · 综合管理A」；缺省不占位）；
  - 02 题目：来源微标 + 题干 56（行高 1.45）+ 枣红 3px 短线 + 破题句 56 枣红 Bold +
    破题理由 36；整组垂直居中，不再留半页空白；
  - 03 答题思路：L1 标题「答题思路」84 + 导语 36 + 三条观点（枣红编号方块 40 + 44px 正文）；
  - 04/05/06 逐字稿三页（按观点拆页，正文 44 才排得下 772 字）：右上「逐字稿 i/3」28 微标，
    观点句 56 Bold + 正文 44 Medium，开场与收尾用 36 次级；卡 06 底部标字数时长；
  - 07 收尾：金句 56 Bold 居中（opening 末句规则不变）+ 收尾话 36 + 枣红 CTA 条 120。
"""
import argparse
import datetime
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1440

# —— VI 色板（v3：强调色唯一化，金棕退役）——
BG = (255, 248, 236)        # fff8ec 米白画布底
INK = (39, 30, 27)          # 271e1b 墨色主文字（对比 15.7:1）
INK2 = (74, 60, 54)         # 4a3c36 次级文字（对比 10.1:1）
INK3 = (140, 127, 118)      # 8c7f76 三级文字/页脚/微标（对比 3.7:1）
CRIMSON = (135, 17, 15)     # 87110f 唯一强调色（对比 9.5:1）
CREAM_W = (255, 248, 236)   # fff8ec 枣红底上的文字（与 BG 同值不同角色）
RULE = (226, 215, 200)      # e2d7c8 中性发丝线（结构，不作装饰）
HERO_SUB = (236, 220, 196)  # ecdcc4 枣红 CTA 条上的副行

FONT_DIR = "/Users/shawn/Library/Fonts"
FONT_FILES = {
    "black": "HarmonyOS_Sans_SC_Black.ttf",
    "bold": "HarmonyOS_Sans_SC_Bold.ttf",
    "med": "HarmonyOS_Sans_SC_Medium.ttf",
    "reg": "HarmonyOS_Sans_SC_Regular.ttf",
}
LOGO_PATH = "/Users/shawn/Desktop/AI工作区/01-Projects/公考橙皮书/assets/logo-zfz.png"
BRAND_SLOGAN = "先答一道，把最影响得分的地方找出来"  # 品牌话术（卡 07 CTA 副行）
COVER_SUB = "把最影响得分的地方找出来"              # 封面副标 12 字（T04 上限），品牌话术截取
CTA_MAIN = "答一道 · 每日一练"                      # 卡 07 CTA 主行
FOOTER_LEFT = "结构化每日一练 · 答一道"             # 页脚左（统一）
NOTE_GUIDE = "想要完整逐字稿，评论区打「1」"        # 笔记文案固定引导
NOTE_TAGS = ["#结构化面试", "#公考面试", "#答题思路", "#每日一练", "#上岸"]
WORDMARK = "结构化每日一练"                         # 内页页眉字标
SPEECH_CPS = 3.5                                    # 口播速率（字/秒），字数小字估算用
IMG_DIR = "图片输出"
PROGRESS_NAME = "progress_answer.json"

# ---- 字号梯（v3 六档，见 DESIGN.md §3）----
T_L0 = 132        # 封面主标（132–160 区间下沿，6 字主题实测 792+字距可容）
T_L0_MIN = 88     # 主标自动降档下限
T_L1 = 84         # 内页分节标题（76–88 区间）
T_L2 = 56         # 引文/题干/观点句
T_L3 = 44         # 正文（42–46 区间，T05 硬下限 42）
T_L3_MIN = 42
T_L4 = 35         # 次级正文/注释（35 而非 36：44/35=1.257、35/28=1.250，相邻档比全 ≥1.25）
T_L5 = 28         # 页脚/微标（28–30 区间）

LH_COVER = 1.18   # 封面主标行高
LH_TITLE = 1.25   # L1 标题
LH_QUOTE = 1.45   # L2 引文/题干
LH_BODY = 1.60    # L3 正文（1.60–1.80）
LH_NOTE = 1.55    # L4 次级正文
LH_MICRO = 1.30   # L5 微标

# ---- 版面骨架 ----
MARGIN = 84
TX_X, TX_W = MARGIN, W - 2 * MARGIN        # 84 / 912 版心（每行 18–24 汉字）
SAFE = 64                                   # 四边绝对禁区
ZONE_BOT = 1290                             # 内容区下沿（页脚文字之上留白）
HEADER_LOGO_INNER = 56
HEADER_LOGO_XY = (MARGIN, 28)
HEADER_TEXT_X, HEADER_TEXT_Y = MARGIN + 56 + 16, 56
HEADER_WORDMARK_SIZE = T_L5
HEADER_LOGO_COVER = 96
FOOTER_SIZE = T_L5
FOOTER_TEXT_Y = 1372                        # 页脚 28 微标（无装饰横线）
LOGO_BOX = (84, 72, 180, 168)               # 封面 logo 像素校验框（96px 贴图位）
LOGO_BOX_INNER = (84, 28, 140, 84)          # 内页 logo 像素校验框（56px 贴图位）
RADIUS_SMALL = 12                           # 形态锁：小元素（≤64px 高）
RADIUS_LARGE = 24                           # 形态锁：大块（CTA/封面色块）
RULE_W = 3                                  # 最小线宽 3px（1px 缩到手机即消失）

# ---- 卡 01 封面 ----
COVER_ZONE = (240, 1240)     # 封面内容区（色块+副标整组在此垂直居中）
COVER_PAD_X = 44             # 色块横向内边距（呼吸）
COVER_PAD_Y = 20             # 色块纵向内边距（紧贴字形，实测面积 11.1% ≤12%）
COVER_SUB_GAP = 76           # 色块→副标
COVER_META_GAP = 18          # 副标→题目信息行（cover_meta 可选，真题元信息）

# ---- 卡 02 题目 ----
Q_LABEL_Y = 300              # 来源微标

# ---- 卡 03 答题思路 ----
SQ_SIZE = 40                 # 观点编号方块（v3 放大到 40，缩略图可辨）
SQ_NUM_SIZE = 24
SQ_GAP = 20                  # 方块→观点正文
VIEW_GAP = 30                # 观点之间

# ---- 卡 04/05/06 逐字稿 ----
SCRIPT_ZONE_TOP = 176        # 逐字稿无 L1 标题，内容上探到页眉之下
SCRIPT_LEAD_SIZE = T_L2      # 观点句 56 Bold（固定，作阅读锚）
SCRIPT_BODY_TIERS = (T_L3, T_L3_MIN)   # 正文 44 → 42（T05 硬下限，再低即 FAIL）
LEAD_BODY_GAP = 26
PARA_BODY_GAP = 34
SCRIPT_NOTE_Y = 1252         # 卡 06 底部字数时长小字
GROUP_GAP = 56

# ---- 卡 07 收尾 ----
GOLDEN_MAX = 60              # opening 末句超此字数回退 closing
GOLDEN_ZONE = (260, 1086)    # 金句+收尾话整组在（正文区→CTA）内垂直居中
GOLDEN_CLOSING_GAP = 56      # 金句→收尾话（同组内距）
CTA_H = 120                  # 枣红 CTA 条高（912×120＝7.0% 面积，≤8%）
CTA_Y = 1150

CARD_FILES = ["01-封面.png", "02-题目.png", "03-答题思路.png",
              "04-逐字稿一.png", "05-逐字稿二.png", "06-逐字稿三.png",
              "07-收尾引流.png"]

# final JSON 16 必填键（与引擎 REPLACE_MAP/技能 schema 同表）
REQUIRED_FIELDS = [
    "question", "break_angle", "break_angle_reason", "core_views_title",
    "core_views_intro", "opening",
    "point1_lead", "point1_body", "point2_lead", "point2_body",
    "point3_lead", "point3_body", "closing",
]  # core_views 单独校验（恰 3 条非空）

SCRIPT_KEYS = ("opening", "point1_body", "point2_body", "point3_body", "closing")

SCRIPT_PAGE_LABELS = ("逐字稿 1/3", "逐字稿 2/3", "逐字稿 3/3")


class CardOverflow(Exception):
    """某一卡在所有档位下都放不下（绝不截断，交人工精简）。"""

    def __init__(self, card):
        super().__init__(card)
        self.card = card


# --------------------------------------------------------------------------
# 字体与资源
# --------------------------------------------------------------------------
@lru_cache(maxsize=64)
def _cached_font(dir_path, name, size):
    return ImageFont.truetype(str(Path(dir_path) / name), size)


def _font(kind, size):
    return _cached_font(FONT_DIR, FONT_FILES[kind], int(size))


def F_BLACK(s):
    return _font("black", s)


def F_BOLD(s):
    return _font("bold", s)


def F_MED(s):
    return _font("med", s)


def F_REG(s):
    return _font("reg", s)


def ensure_assets():
    """字体四档 + 品牌 logo 必须齐；缺即 STOP，不静默降级。"""
    if not Path(FONT_DIR).is_dir():
        sys.exit(f"[FAIL] 字体目录不存在: {FONT_DIR} —— STOP，不静默降级")
    missing = [n for n in FONT_FILES.values() if not (Path(FONT_DIR) / n).is_file()]
    if missing:
        sys.exit(f"[FAIL] 字体缺失: {FONT_DIR} 缺 {'、'.join(missing)} —— STOP，不静默降级")
    for n in FONT_FILES.values():
        p = Path(FONT_DIR) / n
        try:
            with p.open("rb") as fh:
                fh.read(4)
        except OSError as exc:
            sys.exit(f"[FAIL] 字体不可读: {p} —— {exc}")
    if not Path(LOGO_PATH).is_file():
        sys.exit(f"[FAIL] 品牌 logo 缺失: {LOGO_PATH} —— STOP")


def glyph_height(s, f):
    box = f.getbbox(s if s else "国")
    return box[3] - box[1]


def require_glyph(f, *chars):
    """字形缺失即 STOP（历史教训 I-1：HarmonyOS 缺 U+2717/U+2713）。"""
    for s in chars:
        if not s:
            continue
        if glyph_height(s, f) <= 0:
            path = getattr(f, "path", FONT_DIR)
            sys.exit(f"[FAIL] 字体缺字形: {s!r} @ {path} —— STOP")


def safe_path(base, name):
    base_res = Path(base).resolve()
    p = (base_res / name).resolve()
    if not p.is_relative_to(base_res):
        raise ValueError(f"路径越界: {name!r}（base={base_res}）")
    return p


# --------------------------------------------------------------------------
# 折行（只折行不截断：避头标点 + 行尾不悬挂开引号 + 末行孤字借字）
# --------------------------------------------------------------------------
NO_LINE_START = "、，。：；！？·）》」』%,.;:!?)]"
NO_LINE_END = "「『（《"
TAIL_PUNCT = "。，、；：！？"


def tw(d, s, f):
    if not s:
        return 0
    box = d.textbbox((0, 0), s, font=f)
    return box[2] - box[0]


def _is_ascii_alnum(ch):
    """ASCII 字母数字（数字串、英文词、型号/电话号不可内部断开）。"""
    return ch.isascii() and ch.isalnum()


def _alnum_run_start(s):
    """s 末尾连续 ASCII 字母数字段的起始下标（无则 len(s)）。"""
    j = len(s)
    while j > 0 and _is_ascii_alnum(s[j - 1]):
        j -= 1
    return j


def wrap_text_widths(d, text, f, width_for_line):
    """按逐行宽度函数折行；不丢字、不截断。

    铁律（I-2 教训：`马上打119和120` 曾被折成「马上打11 / 9和120」）：
    数字串/英文串不内部断开；整串超行宽时才允许被迫切分。
    """
    lines, cur = [], ""
    for ch in text:
        if cur and tw(d, cur + ch, f) > width_for_line(len(lines)):
            if ch in NO_LINE_START and len(cur) >= 2:
                lines.append(cur[:-1])
                cur = cur[-1] + ch
            elif cur[-1] in NO_LINE_END and len(cur) >= 2:
                lines.append(cur[:-1])
                cur = cur[-1] + ch
            elif _is_ascii_alnum(ch):
                # 把 cur 末尾的数字/英文串整体挪到下一行，绝不腰斩
                j = _alnum_run_start(cur)
                if 0 < j < len(cur):
                    lines.append(cur[:j])
                    cur = cur[j:] + ch
                else:
                    lines.append(cur)
                    cur = ch
            else:
                lines.append(cur)
                cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    # 末行孤字借字（1 字，或 2 字且第二字是收尾标点）
    if len(lines) >= 2 and len(lines[-2]) > 3:
        tail = lines[-1]
        if len(tail) == 1 or (len(tail) == 2 and tail[1] in TAIL_PUNCT):
            borrow = lines[-2][-1]
            if (borrow not in NO_LINE_START and borrow not in NO_LINE_END
                    and not (_is_ascii_alnum(borrow) and tail and _is_ascii_alnum(tail[0]))):
                lines[-2] = lines[-2][:-1]
                lines[-1] = borrow + tail
    return lines


def wrap_text(d, text, f, max_w):
    return wrap_text_widths(d, text, f, lambda _i: max_w)


def n_lines(d, text, f, max_w):
    return max(1, len(wrap_text(d, text, f, max_w)))


def fit_display(d, text, base, min_size, max_w=TX_W, max_lines=1):
    """标题类：逐档 -2px 只缩不截；超 max_lines 或到底即 None（交调用方 FAIL）。"""
    size = base
    while size >= min_size:
        f = F_BLACK(size)
        lines = wrap_text(d, text, f, max_w)
        if len(lines) <= max_lines:
            return size, lines, f
        size -= 2
    return None


def _balanced_lines(d, text, f, max_w):
    """两行均衡（避免「长行＋孤字」）——折行结果均衡重排。"""
    lines = wrap_text(d, text, f, max_w)
    if len(lines) != 2:
        return lines
    if len(lines[1]) < len(lines[0]) - 2:
        n = len(text)
        for cut in range((n + 1) // 2, n):
            head, tail = text[:cut], text[cut:]
            if not tail:
                break
            if tail[0] in NO_LINE_START or head[-1] in NO_LINE_END:
                continue
            if _is_ascii_alnum(head[-1]) and _is_ascii_alnum(tail[0]):
                continue  # 不腰斩数字/英文串
            if len(tail) < 2:
                continue
            return [head, tail]
    return lines


# --------------------------------------------------------------------------
# 基础绘制
# --------------------------------------------------------------------------
def rounded(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def new_card():
    im = Image.new("RGB", (W, H), BG)
    return im, ImageDraw.Draw(im)


_MEASURE_CTX = None


def _measure_draw():
    """离屏 draw 只用于测量折行（与真实 draw 结果一致）。"""
    global _MEASURE_CTX
    if _MEASURE_CTX is None:
        _MEASURE_CTX = ImageDraw.Draw(Image.new("RGB", (8, 8), BG))
    return _MEASURE_CTX


def draw_lines(d, x, y, lines, f, size, lh, fill, center_x=None):
    """逐行定行高绘制（行高＝size×lh，保证全帖一致）。返回结束 y。"""
    adv = int(round(size * lh))
    for i, ln in enumerate(lines):
        if center_x is None:
            d.text((x, y + i * adv), ln, font=f, fill=fill, anchor="la")
        else:
            d.text((center_x, y + i * adv), ln, font=f, fill=fill, anchor="ma")
    return y + adv * len(lines)


def block(text, size, lh, fill, kind, x=TX_X, y=0, max_w=TX_W, center_x=None):
    """测量 + 绘制一体（返回结束 y）。"""
    d = _measure_draw()
    f = _font(kind, size)
    lines = wrap_text(d, text, f, max_w)
    adv = int(round(size * lh))
    return lines, adv * len(lines), f, adv


@lru_cache(maxsize=8)
def _logo_src():
    return Image.open(LOGO_PATH).convert("RGB")


_logo_cache = {}


def rounded_logo(size):
    if size in _logo_cache:
        return _logo_cache[size]
    im = _logo_src().resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1),
                                           radius=int(size * 0.22), fill=255)
    im.putalpha(mask)
    _logo_cache[size] = im
    return im


def logo_cover(im):
    im.paste(rounded_logo(HEADER_LOGO_COVER), (MARGIN, 72), rounded_logo(HEADER_LOGO_COVER))


def logo_header(im, d):
    lg = rounded_logo(HEADER_LOGO_INNER)
    im.paste(lg, HEADER_LOGO_XY, lg)
    d.text((HEADER_TEXT_X, HEADER_TEXT_Y), WORDMARK, font=F_BOLD(HEADER_WORDMARK_SIZE),
           fill=INK, anchor="lm")


def footer(d, idx):
    """页脚＝28 微标；无装饰横线（页脚不抢读，T#9）。"""
    d.text((MARGIN, FOOTER_TEXT_Y), FOOTER_LEFT, font=F_REG(FOOTER_SIZE),
           fill=INK3, anchor="la")
    d.text((W - MARGIN, FOOTER_TEXT_Y), f"{idx:02d}/{len(CARD_FILES):02d}",
           font=F_REG(FOOTER_SIZE), fill=INK3, anchor="ra")


def micro_label(d, text, y, fill=INK3, x=MARGIN, anchor="la", size=T_L5, kind="reg"):
    d.text((x, y), text, font=_font(kind, size), fill=fill, anchor=anchor)


def script_badge(p):
    total = sum(len(p[k]) for k in SCRIPT_KEYS)
    secs = int(round(total / SPEECH_CPS / 10) * 10)
    return f"全文 {total} 字 · 约 {secs} 秒"


def strip_done_mark(s):
    return re.sub(r"答题完毕[。.!！~]?\s*$", "", s).strip() or s


def opening_golden(p):
    op = p.get("opening", "") or ""
    idx = op.rfind("。")
    last = op[idx + 1:] if idx >= 0 else ""
    if not last:
        parts = [x for x in re.split(r"[。！？]", op) if x.strip()]
        last = parts[-1] if parts else ""
    last = last.strip()
    if last.strip("。，、；：！？") and len(last) <= GOLDEN_MAX:
        return last
    return strip_done_mark(p.get("closing", ""))


# --------------------------------------------------------------------------
# 01 封面
# --------------------------------------------------------------------------
def card1_cover(im, d, p, ctx):
    logo_cover(im)
    d.text((W - MARGIN, 108), f"第 {ctx['issue']} 期 · {ctx['type']}",
           font=F_MED(T_L5), fill=INK3, anchor="ra")

    topic = ctx["topic"]
    inner_w = TX_W - 2 * COVER_PAD_X
    got = fit_display(d, topic, T_L0, T_L0_MIN, max_w=inner_w, max_lines=1)
    if got is None:
        got = fit_display(d, topic, T_L0, T_L0_MIN, max_w=inner_w, max_lines=2)
    if got is None:
        sys.exit(f"[FAIL] 封面主题超长：{len(topic)} 字在 {T_L0_MIN}px 下限档仍排不进"
                 f" {inner_w}px 宽 2 行，不许截断——请精简主题（建议 ≤10 字）")
    size, lines, f = got
    if len(lines) == 2:
        lines = _balanced_lines(d, topic, f, inner_w)
    adv = int(round(size * LH_COVER))
    # 色块紧贴最长一行（左对齐、非满宽 banner）：既是视觉锚，又不像默认通栏条
    text_w = max(tw(d, ln, f) for ln in lines)
    field_h = adv * len(lines) + 2 * COVER_PAD_Y
    # 整组（色块 + 副标）在 zone 内垂直居中：上下留白对称，避免下半张死白
    meta = (ctx.get("cover_meta") or "").strip()
    sub_h = int(round(T_L2 * LH_TITLE))
    meta_h = (COVER_META_GAP + int(round(T_L5 * LH_MICRO))) if meta else 0
    group_h = field_h + COVER_SUB_GAP + sub_h + meta_h
    zone_top, zone_bot = COVER_ZONE
    y0 = zone_top + max(0, (zone_bot - zone_top - group_h) // 2)
    rounded(d, (MARGIN, y0, MARGIN + text_w + 2 * COVER_PAD_X, y0 + field_h),
            RADIUS_LARGE, fill=CRIMSON)
    ty = y0 + COVER_PAD_Y
    for i, ln in enumerate(lines):
        d.text((MARGIN + COVER_PAD_X, ty + i * adv), ln, font=f, fill=CREAM_W, anchor="la")

    sub_y = y0 + field_h + COVER_SUB_GAP
    d.text((MARGIN, sub_y), COVER_SUB, font=F_MED(T_L2), fill=INK, anchor="la")
    if meta:
        d.text((MARGIN, sub_y + sub_h + COVER_META_GAP), meta,
               font=F_REG(T_L5), fill=INK3, anchor="la")
    footer(d, 1)


# --------------------------------------------------------------------------
# 02 题目 + 破题
# --------------------------------------------------------------------------
def card2_question(im, d, p, ctx):
    logo_header(im, d)
    measure_ctx = _measure_draw()
    blocks = []

    # 来源微标
    src = ctx["source_badge"]
    blocks.append(("micro", src))

    # 题干 L2
    q = p["question"]
    f_q = F_MED(T_L2)
    q_lines = wrap_text(measure_ctx, q, f_q, TX_W)
    blocks.append(("question", q_lines))

    # 3px 枣红短线（结构分隔，唯一强调色）
    blocks.append(("rule", None))

    # 破题句 L2 Bold 枣红
    ba = p["break_angle"]
    f_ba = F_BOLD(T_L2)
    ba_lines = wrap_text(measure_ctx, ba, f_ba, TX_W)
    blocks.append(("break", ba_lines))

    # 破题理由 L4
    reason = p["break_angle_reason"]
    f_r = F_MED(T_L4)
    r_lines = wrap_text(measure_ctx, reason, f_r, TX_W)
    blocks.append(("reason", r_lines))

    # 高度合成
    adv_q = int(round(T_L2 * LH_QUOTE))
    adv_r = int(round(T_L4 * LH_NOTE))
    h_micro = int(round(T_L5 * LH_MICRO))
    h_q = adv_q * len(q_lines)
    h_ba = adv_q * len(ba_lines)
    h_reason = adv_r * len(r_lines)
    gap_micro_q = 40
    gap_q_rule = 44
    gap_rule_ba = 40
    gap_ba_reason = 44
    total = (h_micro + gap_micro_q + h_q + gap_q_rule + RULE_W + gap_rule_ba
             + h_ba + gap_ba_reason + h_reason)
    # 卡 02 无降档档位（题干/破题句/理由是固定字号），撑爆必须 FAIL 而不是
    # 静默把内容推出画布。历史上这里缺闸门，超长题干 rc=0 出一张压到画外
    # 的图，属于「不许截断」铁律的漏网。
    if total > ZONE_BOT - SCRIPT_ZONE_TOP:
        raise CardOverflow(2)
    top = SCRIPT_ZONE_TOP + max(0, (ZONE_BOT - SCRIPT_ZONE_TOP - total) // 2)

    y = top
    d.text((MARGIN, y), src, font=F_REG(T_L5), fill=CRIMSON, anchor="la")
    y += h_micro + gap_micro_q
    y = draw_lines(d, TX_X, y, q_lines, f_q, T_L2, LH_QUOTE, INK)
    y += gap_q_rule
    d.rectangle((MARGIN, y, MARGIN + 96, y + RULE_W), fill=CRIMSON)
    y += RULE_W + gap_rule_ba
    y = draw_lines(d, TX_X, y, ba_lines, f_ba, T_L2, LH_QUOTE, CRIMSON)
    y += gap_ba_reason
    y = draw_lines(d, TX_X, y, r_lines, f_r, T_L4, LH_NOTE, INK2)
    footer(d, 2)


# --------------------------------------------------------------------------
# 03 答题思路
# --------------------------------------------------------------------------
def card3_views(im, d, p, ctx):
    logo_header(im, d)
    mc = _measure_draw()
    title = p["core_views_title"] or "答题思路"
    size, lines, f = fit_display(d, title, T_L1, 76, max_w=TX_W, max_lines=1) or (T_L1, [title], F_BLACK(T_L1))
    adv_t = int(round(size * LH_TITLE))
    title_y = 150
    y = draw_lines(d, TX_X, title_y, lines, f, size, LH_TITLE, INK)
    y += 34

    intro = p.get("core_views_intro", "")
    f_i = F_MED(T_L4)
    i_lines = wrap_text(mc, intro, f_i, TX_W)
    y = draw_lines(d, TX_X, y, i_lines, f_i, T_L4, LH_NOTE, INK2)
    y += 44

    views = p["core_views"][:3]
    text_x = TX_X + SQ_SIZE + SQ_GAP
    text_w = TX_W - SQ_SIZE - SQ_GAP
    for body_size in (T_L3, T_L3_MIN):
        f_v = _font("med", body_size)
        adv_v = int(round(body_size * LH_BODY))
        v_lines = [wrap_text(mc, v, f_v, text_w) for v in views]
        need = y + sum(adv_v * len(vl) for vl in v_lines) + VIEW_GAP * (len(v_lines) - 1)
        if need <= ZONE_BOT:
            break
    else:
        raise CardOverflow(3)

    for i, vl in enumerate(v_lines):
        adv = int(round(body_size * LH_BODY))
        rounded(d, (TX_X, y, TX_X + SQ_SIZE, y + SQ_SIZE), RADIUS_SMALL, fill=CRIMSON)
        d.text((TX_X + SQ_SIZE / 2, y + SQ_SIZE / 2), str(i + 1),
               font=F_BOLD(SQ_NUM_SIZE), fill=CREAM_W, anchor="mm")
        y = draw_lines(d, text_x, y, vl, f_v, body_size, LH_BODY, INK)
        y += VIEW_GAP
    footer(d, 3)


# --------------------------------------------------------------------------
# 04/05/06 逐字稿三页
# --------------------------------------------------------------------------
def _script_groups(p):
    return [
        [("para", p["opening"]), ("point", 0, p["point1_lead"], p["point1_body"])],
        [("point", 1, p["point2_lead"], p["point2_body"])],
        [("point", 2, p["point3_lead"], p["point3_body"])],
    ]


def _group_height(g, lead_s, body_s, lead_f, body_f, mc):
    lead_w = TX_W - SQ_SIZE - SQ_GAP
    adv_l = int(round(lead_s * LH_QUOTE))
    adv_b = int(round(body_s * LH_BODY))
    adv_p = int(round(T_L4 * LH_NOTE))
    if g[0] == "para":
        return int(round(T_L4 * LH_NOTE)) * len(wrap_text(mc, g[1], _font("med", T_L4), TX_W))
    _, _, lead, body = g
    hl = adv_l * len(wrap_text(mc, lead, lead_f, lead_w))
    hb = adv_b * len(wrap_text(mc, body, body_f, TX_W))
    return hl + LEAD_BODY_GAP + hb


def _draw_group(d, g, y, lead_s, body_s):
    mc = _measure_draw()
    if g[0] == "para":
        f = F_MED(T_L4)
        lines = wrap_text(mc, g[1], f, TX_W)
        return draw_lines(d, TX_X, y, lines, f, T_L4, LH_NOTE, INK2)
    _, idx, lead, body = g
    lead_w = TX_W - SQ_SIZE - SQ_GAP
    f_l = F_BOLD(lead_s)
    lead_lines = wrap_text(mc, lead, f_l, lead_w)
    adv_l = int(round(lead_s * LH_QUOTE))
    rounded(d, (TX_X, y, TX_X + SQ_SIZE, y + SQ_SIZE), RADIUS_SMALL, fill=CRIMSON)
    d.text((TX_X + SQ_SIZE / 2, y + SQ_SIZE / 2), str(idx + 1),
           font=F_BOLD(SQ_NUM_SIZE), fill=CREAM_W, anchor="mm")
    tx = TX_X + SQ_SIZE + SQ_GAP
    y2 = draw_lines(d, tx, y, lead_lines, f_l, lead_s, LH_QUOTE, INK)
    if len(lead_lines) == 1:
        y = y2 + max(LEAD_BODY_GAP, SQ_SIZE - adv_l + LEAD_BODY_GAP)
    else:
        y = y2 + LEAD_BODY_GAP
    f_b = _font("med", body_s)
    body_lines = wrap_text(mc, body, f_b, TX_W)
    return draw_lines(d, TX_X, y, body_lines, f_b, body_s, LH_BODY, INK2)


def _render_script(im, d, p, page_no):
    logo_header(im, d)
    micro_label(d, SCRIPT_PAGE_LABELS[page_no], 60, fill=INK3, x=W - MARGIN, anchor="ra")
    mc = _measure_draw()
    groups = _script_groups(p)[page_no]
    zone_bot = SCRIPT_NOTE_Y - 40 if page_no == 2 else ZONE_BOT
    lead_s = SCRIPT_LEAD_SIZE

    chosen = None
    for body_s in SCRIPT_BODY_TIERS:
        lead_f = F_BOLD(lead_s)
        body_f = _font("med", body_s)
        hs = [_group_height(g, lead_s, body_s, lead_f, body_f, mc) for g in groups]
        total = sum(hs) + GROUP_GAP * (len(groups) - 1)
        if total <= zone_bot - SCRIPT_ZONE_TOP:
            chosen = (body_s, hs, total)
            break
    if chosen is None:
        raise CardOverflow(4 + page_no)
    body_s, hs, total = chosen

    y = SCRIPT_ZONE_TOP
    for i, g in enumerate(groups):
        if i:
            y += GROUP_GAP
        y = _draw_group(d, g, y, lead_s, body_s)

    if page_no == 2:
        d.text((W // 2, SCRIPT_NOTE_Y), script_badge(p), font=F_REG(T_L5),
               fill=INK3, anchor="ma")
    footer(d, 4 + page_no)
    print(f"[OK] 逐字稿 {page_no + 1}/3：观点句 {lead_s}px / 正文 {body_s}px，高 {total}px")


def card4_script1(im, d, p, ctx):
    _render_script(im, d, p, 0)


def card5_script2(im, d, p, ctx):
    _render_script(im, d, p, 1)


def card6_script3(im, d, p, ctx):
    _render_script(im, d, p, 2)


# --------------------------------------------------------------------------
# 07 收尾：金句 + 收尾话 + CTA
# --------------------------------------------------------------------------
def card7_close(im, d, p, ctx):
    logo_header(im, d)
    mc = _measure_draw()

    # 金句（opening 末句；超长回退 closing）
    golden = opening_golden(p)
    size = None
    for s in (T_L2, 52, 48, T_L3):
        f = F_BOLD(s)
        lines = _balanced_lines(mc, golden, f, TX_W)
        adv = int(round(s * LH_QUOTE))
        if adv * len(lines) <= 320:
            size, g_lines, g_f = s, lines, f
            break
    if size is None:
        raise CardOverflow(7)
    adv = int(round(size * LH_QUOTE))
    g_h = adv * len(g_lines)
    closing = strip_done_mark(p["closing"])
    f_c = F_MED(T_L4)
    c_lines = wrap_text(mc, closing, f_c, TX_W)
    c_adv = int(round(T_L4 * LH_NOTE))
    c_h = c_adv * len(c_lines)
    # 金句 + 收尾话作一组垂直居中：卡中部不留断裂空洞，余量分给上下呼吸区
    zone_top, zone_bot = GOLDEN_ZONE
    group_h = g_h + GOLDEN_CLOSING_GAP + c_h
    gy = zone_top + max(0, (zone_bot - zone_top - group_h) // 2)
    d.rectangle((MARGIN, gy - 60, MARGIN + 96, gy - 60 + RULE_W), fill=CRIMSON)
    draw_lines(d, TX_X, gy, g_lines, g_f, size, LH_QUOTE, INK, center_x=W // 2)
    draw_lines(d, TX_X, gy + g_h + GOLDEN_CLOSING_GAP, c_lines, f_c, T_L4, LH_NOTE, INK2)

    # CTA
    rounded(d, (MARGIN, CTA_Y, W - MARGIN, CTA_Y + CTA_H), RADIUS_LARGE, fill=CRIMSON)
    d.text((W // 2, CTA_Y + 42), CTA_MAIN, font=F_BOLD(T_L3), fill=CREAM_W, anchor="mm")
    d.text((W // 2, CTA_Y + 88), BRAND_SLOGAN, font=F_REG(T_L5), fill=HERO_SUB, anchor="mm")
    footer(d, 7)


# --------------------------------------------------------------------------
# 笔记文案
# --------------------------------------------------------------------------
def make_note_title(p, topic):
    ba = (p.get("break_angle") or "").strip()
    tail = ""
    if ba:
        parts = [x for x in re.split(r"[，。；！？,;.!?]", ba) if x.strip()]
        cand = parts[-1].strip() if parts else ""
        if 4 <= len(cand) <= 10:
            tail = cand
    if tail:
        title = f"{topic}，{tail}"
    else:
        title = f"{topic}怎么答？{len(p.get('core_views') or [])} 步思路＋逐字稿"
    if len(title) > 20:
        title = f"{topic} 每日一练"
    return title


NOTE_TEMPLATE = """---
title: {title}
type: 素材
业务线: 公考面试
板块: 结构化每日一练
updated: {date}
tags:
  - 类型/素材
  - 业务线/公考结构化
---

# {title}

> 期号：第 {issue} 期 · {type}
> 视觉：答一道 VI（米白底 #fff8ec · 墨 #271e1b · 枣红 #87110f 唯一强调色），
> 总分总 logo，7 卡（封面／题目／思路／逐字稿 ×3／收尾）；版式契约见
> structured-daily references/DESIGN.md。

## 题目

{question}

## 答题思路

**破题角度**：{break_angle}
{break_angle_reason}

**{core_views_title}**
{core_views_intro}

{core_views}

## 逐字稿

**开场**
{opening}

**{p1_lead}**
{p1_body}

**{p2_lead}**
{p2_body}

**{p3_lead}**
{p3_body}

**收尾**
{closing}

## 本期金句

> {golden}

## 配图

- 共 7 张：`{img_first}` … `{img_last}`

{guide}

{tags}
"""


def write_note(p, ctx, outdir):
    views = list(p.get("core_views") or [])
    while len(views) < 3:
        views.append("")
    lines = []
    for i, v in enumerate(views[:3], 1):
        lines.append(f"{i}. {v}")
    body = NOTE_TEMPLATE.format(
        title=ctx["note_title"],
        date=datetime.date.today().isoformat(),
        issue=ctx["issue"],
        type=ctx["type"],
        question=p["question"],
        break_angle=p["break_angle"],
        break_angle_reason=p["break_angle_reason"],
        core_views_title=p["core_views_title"],
        core_views_intro=p["core_views_intro"],
        core_views="\n".join(lines),
        opening=p["opening"],
        p1_lead=p["point1_lead"], p1_body=p["point1_body"],
        p2_lead=p["point2_lead"], p2_body=p["point2_body"],
        p3_lead=p["point3_lead"], p3_body=p["point3_body"],
        closing=p["closing"],
        golden=opening_golden(p),
        img_first=CARD_FILES[0],
        img_last=CARD_FILES[-1],
        guide=NOTE_GUIDE,
        tags=" ".join(NOTE_TAGS + [f"#{ctx['type']}"]),
    )
    (outdir / "笔记文案.md").write_text(body, encoding="utf-8")


# --------------------------------------------------------------------------
# 校验 / 渲染 / 进度
# --------------------------------------------------------------------------
def _crimson_ratio(im, box):
    crop = im.crop(box).convert("RGB")
    # Pillow 14 起 getdata() 弃用；用 tobytes 逐像素三元组解析，等价且无警告
    raw = crop.tobytes()
    px = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    hit = sum(1 for r, g, b in px if max(abs(r - CRIMSON[0]), abs(g - CRIMSON[1]),
                                         abs(b - CRIMSON[2])) < 60)
    return hit / max(1, len(px))


def check_logos(outdir):
    ok = True
    for i, name in enumerate(CARD_FILES):
        path = Path(outdir) / name
        if not path.is_file():
            print(f"[FAIL] --check 缺文件: {name}")
            ok = False
            continue
        with Image.open(path) as im:
            im = im.convert("RGB")
            if im.size != (W, H):
                print(f"[FAIL] --check 尺寸不符: {name} {im.size}")
                ok = False
                continue
            box = LOGO_BOX if i == 0 else LOGO_BOX_INNER
            pct = _crimson_ratio(im, box)
        flag = "PASS" if pct >= 0.5 else "FAIL"
        if flag == "FAIL":
            ok = False
        print(f"[{flag}] logo {name}: 枣红占比 {pct:.0%}（≥50%）")
    return ok


def read_done(img_root):
    path = Path(img_root) / PROGRESS_NAME
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        sys.exit(f"[FAIL] 进度文件损坏: {path} —— {exc}")
    done = data.get("done")
    if not isinstance(done, list):
        sys.exit(f"[FAIL] 进度文件格式错: {path} 缺 done 数组")
    return done


def append_done(img_root, qid):
    path = Path(img_root) / PROGRESS_NAME
    done = read_done(img_root)
    if qid in done:
        print(f"[NOTE] done 已含 {qid}，不重复追加")
        return
    done.append(qid)
    path.write_text(json.dumps({"done": done}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def derive_qid(final_path):
    stem = Path(final_path).stem
    for pre in ("draft_", "final_"):
        if stem.startswith(pre):
            stem = stem[len(pre):]
    if stem.endswith("_final"):
        stem = stem[: -len("_final")]
    return stem


def sanitize_name(s):
    return re.sub(r"[/\\:]", "／", s)


def derive_outdir(project_root, issue, type_, topic):
    return Path(project_root) / IMG_DIR / f"第{issue}期-{sanitize_name(type_)}-{sanitize_name(topic)}"


def validate_final(p):
    for k in REQUIRED_FIELDS:
        if not (p.get(k) or "").strip():
            sys.exit(f"[FAIL] final 缺字段: {k}")
    views = p.get("core_views")
    if not (isinstance(views, list) and len(views) == 3
            and all(isinstance(v, str) and v.strip() for v in views)):
        sys.exit("[FAIL] core_views 须为恰 3 条非空字符串")
    # 封面前缀铁律（SKILL.md「封面前缀铁律」节）：真题库来源必须标「历年考题」微标，
    # 否则图上会静默显示「每日一练」——v3 图卡没有 docx 那种封面文本框可校验，
    # 所以校验落在这里。历史教训 I-4：v3 首版漏了这一闸门，contract 写了却无程序保障。
    source = (p.get("source") or "").strip()
    prefix = (p.get("title_prefix") or "").strip()
    is_real_exam = any(k in source for k in ("真题", "历年考题", "real_exam", "zhenti"))
    if is_real_exam and "历年考题" not in prefix:
        sys.exit(f"[FAIL] source={source!r} 为真题库来源，title_prefix 必须含「历年考题」，"
                 f"实际 {prefix!r} —— 否则封面 / 卡 02 会静默标「每日一练」")
    if prefix and not is_real_exam and "历年考题" in prefix:
        print(f"[WARN] title_prefix 标「历年考题」但 source={source!r} 未标明真题库，请确认来源")


def build_ctx(args, p, issue):
    type_ = args.type
    topic = args.topic
    badge = "历年考题" if "历年考题" in (p.get("title_prefix") or "") else "每日一练"
    return {"issue": issue, "type": type_, "topic": topic, "source_badge": badge,
            "cover_meta": (p.get("cover_meta") or "").strip(),
            "note_title": make_note_title(p, topic)}


CARDS = [
    ("01-封面", card1_cover),
    ("02-题目", card2_question),
    ("03-答题思路", card3_views),
    ("04-逐字稿一", card4_script1),
    ("05-逐字稿二", card5_script2),
    ("06-逐字稿三", card6_script3),
    ("07-收尾引流", card7_close),
]


def render_all(p, ctx):
    _measure_draw()
    out = []
    for i, (name, fn) in enumerate(CARDS):
        im, d = new_card()
        try:
            fn(im, d, p, ctx)
        except CardOverflow as exc:
            sys.exit(f"[FAIL] 卡{exc.card} 内容超高：最低档仍放不下，不许截断——请人工精简")
        out.append((CARD_FILES[i], im))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="结构化每日一练·答一道 7 卡渲染")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--final")
    ap.add_argument("--type")
    ap.add_argument("--topic")
    ap.add_argument("--outdir")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    img_root = project_root / IMG_DIR

    if args.check:
        if not args.outdir:
            sys.exit("[FAIL] --check 需要 --outdir")
        outdir = Path(args.outdir).resolve()
        if not outdir.is_relative_to(img_root):
            sys.exit(f"[FAIL] outdir 不在 {img_root} 内: {outdir}")
        if not check_logos(outdir):
            sys.exit(1)
        print(f"✅ --check 通过（7 图 logo 像素校验）→ {outdir}")
        return

    if not args.final:
        sys.exit("[FAIL] 需要 --final")
    if not args.type or not args.topic:
        sys.exit("[FAIL] 需要 --type 与 --topic")

    final_path = Path(args.final)
    if not final_path.is_file():
        sys.exit(f"[FAIL] final 不存在: {final_path}")
    p = json.loads(final_path.read_text(encoding="utf-8"))
    validate_final(p)
    ensure_assets()

    done = read_done(img_root)
    if args.outdir:
        outdir = Path(args.outdir).resolve()
        if not outdir.is_relative_to(img_root):
            sys.exit(f"[FAIL] outdir 不在 {img_root} 内: {outdir}")
        m = re.search(r"第(\d{3})期", outdir.name)
        issue = m.group(1) if m else f"{len(done) + 1:03d}"
    else:
        issue = f"{len(done) + 1:03d}"
        outdir = derive_outdir(project_root, issue, args.type, args.topic)

    ctx = build_ctx(args, p, issue)
    cards = render_all(p, ctx)

    outdir.mkdir(parents=True, exist_ok=True)
    # 重渲染同为 7 卡：清掉期目录里旧版本残留的卡片 PNG，保持一期内聚
    for stale in sorted(outdir.glob("*.png")):
        if stale.name not in CARD_FILES:
            stale.unlink()
            print(f"[NOTE] 清理旧版残留: {stale.name}")
    for name, im in cards:
        im.save(safe_path(outdir, name), "PNG")
    write_note(p, ctx, outdir)

    if not check_logos(outdir):
        print("[FAIL] logo 像素校验未通过，进度不追加")
        sys.exit(1)
    append_done(img_root, derive_qid(final_path))
    print(f"✅ 全部通过（7 图 + 笔记文案.md）→ {outdir}")


if __name__ == "__main__":
    main()

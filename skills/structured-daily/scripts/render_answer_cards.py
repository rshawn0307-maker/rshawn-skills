#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""结构化每日一练·答一道 小红书 6 卡渲染引擎（答一道 VI 简洁风，PIL 直出）。

用法:
  python3 render_answer_cards.py --project-root DIR --final <draft_final.json> \
      --type <题型> --topic <主题> [--outdir DIR]
  python3 render_answer_cards.py --project-root DIR --check --outdir <期目录>
      # 只复核已生成期目录的 logo 像素与 6 图存在，不重渲染

行为约定:
  - 门禁通过后直接渲染 6 张 1080×1440 PNG + 笔记文案.md；
    docx 产线（fill_answer_post.py + 模板）已退出产线归档保留，不再执行；
  - 期号读 <project-root>/图片输出/progress_answer.json 的 done 数+1（三位补零），
    无则建；全部渲染 + logo 校验成功后才追加 done（任何失败不写进度）；
  - 正文只折行、永不截断：wrap_text 像素折行 + 行首避头标点 + 行尾不悬挂开引号；
    内容超高先自动降字号档位（每档 -2px），仍超高 FAIL exit 非 0 并指出卡片；
  - 字体（HarmonyOS Sans SC 四档）或品牌 logo 缺失即 STOP exit 非 0，不静默降级；
  - 输出限制在 <project-root>/图片输出/ 内，拒绝目录穿越；
  - 笔记文案由 final JSON 字段确定性拼装＋固定标签，不新增事实。

视觉契约见 wushi-daily references/card-layout.md（色值/字体/logo/wrap/白卡软投影同源）。

TR4.1 版式改版（huashu-design 过版，1080 宽正文≥36px/标签≥28px）:
  - 全卡删右上角期数徽章；内页（02-06）页眉压缩：logo 56px + 字标 28px，眉标删除，
    页眉区 ≤110px；封面保留眉标并提到 28px；页脚文字提到 28px；
  - 封面副标题弃用 cover_hook 务实句，固定品牌 slogan（开口练 hero 原话，与卡6 CTA 副行呼应）；
  - 02 题干 40px 起档 + 来源徽章缩为白卡上方小胶囊；03 编号方块收缩 26px、观点正文 30px；
  - 04/05 逐字稿卡满版直排（无白卡装饰，组间 GOLD 2px 金线分隔）：正文 36px/lead 40px、
    左右边距 48、页签+步骤小胶囊标签+26px 编号方块，卡 05 页脚上方字数小字；
    分页重排为 上=开场+第一/二步、下=第三步+收尾（36px 下两页体量均衡，原切分下页超区）；
  - 06 金句 48px 起档、×/√ 行 36/40px，CTA 维持。
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
BG = (251, 246, 237)        # fbf6ed 米色画布底
INK = (39, 30, 27)          # 271e1b 墨色主文字
CRIMSON = (135, 17, 15)     # 87110f 枣红主色/编号方块/logo
CREAM_W = (255, 248, 236)   # fff8ec 枣红底上的文字
GOLD = (227, 199, 159)      # e3c79f 金棕分隔线/描边
GOLD_BG = (239, 224, 201)   # efe0c9 徽章胶囊底
BEIGE = (243, 233, 218)     # f3e9da 米杏对照条底
GRAY = (117, 103, 95)       # 75675f 暖灰辅助文字
BORDER = (226, 215, 200)    # e2d7c8 白卡描边
CARD_W = (255, 255, 255)    # 白卡
RED_BG = (247, 235, 233)    # f7ebe9 红系行底
RED_TXT = (170, 44, 40)     # aa2c28 红线文字
HERO_SUB = (236, 220, 196)  # ecdcc4 枣红卡上的浅金副字
SHADOW = (238, 227, 214)    # eee3d6 白卡软投影

FONT_DIR = "/Users/shawn/Library/Fonts"
FONT_FILES = {
    "black": "HarmonyOS_Sans_SC_Black.ttf",
    "bold": "HarmonyOS_Sans_SC_Bold.ttf",
    "med": "HarmonyOS_Sans_SC_Medium.ttf",
    "reg": "HarmonyOS_Sans_SC_Regular.ttf",
}
LOGO_PATH = "/Users/shawn/Desktop/AI工作区/01-Projects/公考橙皮书/assets/logo-zfz.png"
SERIES_INTRO = "把考场真实答法，搬进你的答案"   # 封面页眉眉标（仅封面保留）
BRAND_SLOGAN = "先答一道，把最影响得分的地方找出来"  # 封面副标题＝卡6 CTA 副行（开口练 hero 原话）
FAKE_DEMO = "一方面……另一方面，加强管理"        # 卡6 假大空对照条·固定示范句（不篡改正文）
REAL_DEMO = "先查人、后修电，三本账对得上"      # 卡6 具体做法对照·固定示范句
# 对照条符号：HarmonyOS Sans SC 缺 U+2717/U+2713 字形（textbbox 高 0，渲染为空白），
# 改用同字体有真实字形的 ×/√；渲染前有 require_glyph 断言防再犯。
MARK_NO = "×"
MARK_YES = "√"
CTA_MAIN = "答一道 · 每日一练"                  # 卡6 CTA 主行
FOOTER_LEFT = "结构化每日一练 · 答一道"         # 页脚左上（统一）
NOTE_GUIDE = "想要完整逐字稿，评论区打「1」"    # 笔记文案固定引导
NOTE_TAGS = ["#结构化面试", "#公考面试", "#答题思路", "#每日一练", "#上岸"]
WORDMARK = "结构化每日一练"                     # 页眉字标
SPEECH_CPS = 3.5                                # 逐字稿口播速率（字/秒，≈210 字/分钟），字数小字估算用
IMG_DIR = "图片输出"
PROGRESS_NAME = "progress_answer.json"

# ---- 页眉/页脚（TR4.1：内页压缩 ≤110px，全卡无右上徽章）----
HEADER_LOGO_COVER = 112          # 封面 logo 尺寸（px）
HEADER_LOGO_INNER = 56           # 内页 logo 尺寸（px，原 112 压缩）
HEADER_LOGO_XY = (70, 26)        # 内页 logo 贴图左上角
HEADER_TEXT_X, HEADER_TEXT_Y = 142, 54   # 内页字标（与 logo 垂直居中）
HEADER_WORDMARK_COVER_SIZE = 52  # 封面字标
HEADER_WORDMARK_SIZE = 28        # 内页字标（达标签底线）
EYEBROW_SIZE = 28                # 封面眉标（26→28 达标签底线）
FOOTER_SIZE = 28                 # 页脚文字（26→28 达标签底线）
FOOTER_LINE_Y = 1352
FOOTER_TEXT_Y = 1388
LOGO_BOX = (70, 58, 182, 170)          # 封面 logo 像素校验框（与 112px 贴图位一致）
LOGO_BOX_INNER = (70, 26, 126, 82)     # 内页 logo 像素校验框（与 56px 贴图位一致）

# ---- 内页统一版面：大标 y=200（F_BLACK 72），内容区 300–1330，卡内文字宽 820 ----
TITLE_Y, TITLE_SIZE = 200, 72
ZONE_TOP, ZONE_BOT = 300, 1330
TX_X, TX_W = 130, 820
CARD_PAD = 44  # 大卡内边距（上下）

# ---- 卡2 题目 ----
QUESTION_TIERS = (40, 38, 36, 34, 32, 30)  # 题干 40 起档（34→40，huashu 底线上）
SOURCE_CAPSULE_Y = ZONE_TOP                # 来源徽章小胶囊（保留缩小）y
SOURCE_ZONE_TOP = ZONE_TOP + 64            # 题干白卡居中区的上界

# ---- 卡3 答题思路：编号方块收缩 26px（装饰），观点正文 30px ----
# 君上裁定（修复轮 1）：观点正文 30px 为长期口径＝清单条目（core_views）按
# huashu 标签底线 ≥28px 口径处理（非 36px 正文档）；降档表 vw 各档均 ≥28，
# 仍放不下即 CardOverflow FAIL（只降其他字段，不下穿 28）。
SQ_SIZE = 26
SQ_NUM_SIZE = 16
OUTLINE_TIERS = ((36, 29, 34, 28, 30), (34, 27, 32, 26, 28),
                 (32, 25, 30, 25, 28), (30, 23, 28, 24, 28))
#            (破题 Bold, 理由 Med, 观点题 Bold, 导语 Med, 观点正文 Med)

# ---- 卡4/5 逐字稿：满版直排（无白卡，金线分组），左右边距 48 ----
SCRIPT_X, SCRIPT_W = 48, 984
SCRIPT_ZONE_TOP = 112
SCRIPT_ZONE_BOT = 1330
SCRIPT_NOTE_Y = 1312              # 卡05 页脚上方字数小字（24px 灰，辅助标注）
SCRIPT_LEAD_SIZE = 40             # lead 设计档
SCRIPT_BODY_SIZE = 36             # 正文设计档（huashu 底线）
SCRIPT_LEAD_GAP = 6               # 行距适度收紧
SCRIPT_LINE_GAP = 6
LEAD_BODY_GAP = 8
SCRIPT_TAG_GAP = 22               # 页签胶囊与首组间距
SCRIPT_GROUP_GAP = 40             # 组间距（金线居中：上下各 19 + 线 2，防贴字）
SCRIPT_TIERS = ((40, 36), (38, 34), (36, 32), (34, 30), (32, 28))  # 超高自动降档，仍超高 FAIL
STEP_TAGS = ("第一步", "第二步", "第三步")
LABEL_SIZE = 28                   # 页签/开场定调/收尾 小标签（达标签底线）
LABEL_PAD_X, LABEL_PAD_Y = 16, 8
TAG_PAD_X, TAG_PAD_Y = 18, 8

# ---- 卡6 收尾 ----
GOLDEN_TIERS = (48, 44, 40, 36, 32)  # 金句 48 起档（44→48）
FAKE_SIZE, REAL_SIZE = 36, 40        # ×行 36 / √行 40（36→40）

CARD_FILES = ["01-封面.png", "02-题目.png", "03-答题思路.png",
              "04-逐字稿上.png", "05-逐字稿下.png", "06-收尾引流.png"]

# final JSON 16 必填键（与引擎 REPLACE_MAP/技能 schema 同表）
REQUIRED_FIELDS = [
    "question", "break_angle", "break_angle_reason", "core_views_title",
    "core_views_intro", "opening",
    "point1_lead", "point1_body", "point2_lead", "point2_body",
    "point3_lead", "point3_body", "closing",
]  # core_views 单独校验（恰 3 条非空）

SCRIPT_KEYS = ("opening", "point1_body", "point2_body", "point3_body", "closing")


class CardOverflow(Exception):
    """某卡内容在最低字号档位仍超高（只折行不截断的硬失败）。"""

    def __init__(self, card):
        super().__init__(card)
        self.card = card


# ------------------------------------------------------------ 字体/资产
@lru_cache(maxsize=None)
def _cached_font(dir_path, name, size):
    return ImageFont.truetype(str(Path(dir_path) / name), size)


def _font(kind, size):
    return _cached_font(FONT_DIR, FONT_FILES[kind], size)


def F_BLACK(s):
    return _font("black", s)


def F_BOLD(s):
    return _font("bold", s)


def F_MED(s):
    return _font("med", s)


def F_REG(s):
    return _font("reg", s)


def ensure_assets():
    """字体四档 + 品牌 logo 缺失/不可读即 STOP exit 非 0，不静默降级；
    并断言绘制符号在对应字体有真实字形（防缺字形渲染成空白）。"""
    missing = [n for n in FONT_FILES.values()
               if not (Path(FONT_DIR) / n).is_file()]
    if missing:
        raise SystemExit(f"[FAIL] 字体缺失: {FONT_DIR} 缺 {missing} —— STOP，不静默降级")
    try:
        for kind in FONT_FILES:
            _cached_font.cache_clear()
            _font(kind, 24)
    except Exception as e:  # 字体文件存在但损坏/不可读
        raise SystemExit(f"[FAIL] 字体不可读: {FONT_DIR} —— {e} —— STOP，不静默降级")
    finally:
        _cached_font.cache_clear()
    require_glyph(F_MED(FAKE_SIZE), MARK_NO)
    require_glyph(F_BOLD(REAL_SIZE), MARK_YES)
    if not Path(LOGO_PATH).is_file():
        raise SystemExit(f"[FAIL] 品牌 logo 缺失: {LOGO_PATH} —— STOP，不静默降级")


_probe_draw = None


def glyph_height(s, f):
    """textbbox 高度：字体缺该字形时为 0（渲染即空白）。"""
    global _probe_draw
    if _probe_draw is None:
        _probe_draw = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    b = _probe_draw.textbbox((0, 0), s, font=f)
    return b[3] - b[1]


def require_glyph(f, *chars):
    """绘制前字形断言：任一符号 bbox 高 ≤0 即 STOP exit 非 0，不静默画空白。"""
    for s in chars:
        if glyph_height(s, f) <= 0:
            raise SystemExit(
                f"[FAIL] 字体缺字形: {s!r} @ {getattr(f, 'path', '?')}"
                " —— STOP，不静默降级")


# ------------------------------------------------------------ 基础绘制
def safe_path(base, name):
    """解析路径并限制在 base 内，拒绝目录穿越与子目录逃逸。"""
    base_res = Path(base).resolve()
    full = (base_res / str(name)).resolve()
    if not (full == base_res or full.is_relative_to(base_res)):
        raise ValueError(f"路径越界: {name!r}（base={base_res}）")
    return full


def tw(d, s, f):
    b = d.textbbox((0, 0), s, font=f)
    return b[2] - b[0]


def rounded(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def shadow_card(im, d, box, r=36, fill=CARD_W):
    x0, y0, x1, y1 = box
    rounded(d, [x0 + 4, y0 + 10, x1 + 4, y1 + 10], r, fill=SHADOW)
    rounded(d, box, r, fill=fill, outline=BORDER, width=2)


NO_LINE_START = "、，。：；！？·）》」』%,.;:!?)]"
NO_LINE_END = "「『（《"


def wrap_text_widths(d, text, f, width_for_line):
    """按像素折行（每行宽度由 width_for_line(行号) 给出）；行首不带避头标点
    （标点连同前一字移入下行）、行尾不悬挂开引号括号；末行孤字向上借字。
    只折行、永不截断（"".join(lines) == 原文）。"""
    lines, cur = [], ""
    for ch in str(text):
        max_w = width_for_line(len(lines))
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if cur and tw(d, cur + ch, f) > max_w:
            if ch in NO_LINE_START and len(cur) >= 2:
                # 避头标点：标点不作行首，连同前一字移入下行
                lines.append(cur[:-1])
                cur = cur[-1] + ch
            elif cur[-1] in NO_LINE_END:
                # 行尾不悬挂开引号/括号：开引号移入下行
                lines.append(cur[:-1])
                cur = cur[-1] + ch
            else:
                lines.append(cur)
                cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    if len(lines) >= 2 and len(lines[-1]) == 1 and len(lines[-2]) > 3:
        lines[-1] = lines[-2][-1] + lines[-1]
        lines[-2] = lines[-2][:-1]
    return lines


def wrap_text(d, text, f, max_w):
    """wrap_text_widths 的等宽版（逐字稿首行缩进折行走 widths 版）。"""
    return wrap_text_widths(d, text, f, lambda _i: max_w)


def draw_wrapped(d, xy, text, f, fill, max_w, line_gap=10, center_x=None):
    x, y = xy
    for ln in wrap_text(d, text, f, max_w):
        if center_x is not None:
            d.text((center_x, y), ln, font=f, fill=fill, anchor="ma")
        else:
            d.text((x, y), ln, font=f, fill=fill, anchor="la")
        y += f.size + line_gap
    return y


def n_lines(d, text, f, max_w):
    return max(1, len(wrap_text(d, text, f, max_w)))


def fit_title(d, text, base, min_size, max_w=940):
    """超宽标题逐档缩（每档 -2px），只缩不截。"""
    s = base
    while s > min_size and tw(d, text, F_BLACK(s)) > max_w:
        s -= 2
    return s


def fit_bold(d, text, base, min_size, max_w=900):
    """Bold 文本超宽逐档缩（每档 -2px），只缩不截。"""
    s = base
    while s > min_size and tw(d, text, F_BOLD(s)) > max_w:
        s -= 2
    return s


def capsule(d, x, y, text, *, bg, fg, pad_x=LABEL_PAD_X, pad_y=LABEL_PAD_Y):
    """28px Bold 小胶囊标签；返回高度。"""
    f = F_BOLD(LABEL_SIZE)
    w = tw(d, text, f)
    h = LABEL_SIZE + 2 * pad_y
    rounded(d, [x, y, x + w + 2 * pad_x, y + h], h // 2, fill=bg)
    d.text((x + pad_x + w / 2, y + h / 2), text, font=f, fill=fg, anchor="mm")
    return h


def new_card():
    im = Image.new("RGB", (W, H), BG)
    return im, ImageDraw.Draw(im)


_logo_cache = None


def rounded_logo(size):
    """总品牌真 logo（枣红方块白字竖排「总分总」）缩放 + 圆角，带缓存。
    缺失时报错退出，不许静默降级为手绘。"""
    global _logo_cache
    if _logo_cache is None or _logo_cache.size != (size, size):
        logo = Path(LOGO_PATH)
        if not logo.is_file():
            raise SystemExit(f"[FAIL] 品牌 logo 缺失: {LOGO_PATH}")
        im = Image.open(logo).convert("RGB").resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255
        )
        rgba = im.convert("RGBA")
        rgba.putalpha(mask)
        _logo_cache = rgba
    return _logo_cache


def logo_header_cover(im, d):
    """封面页眉：真 logo 112 + 字标 52 + 眉标 28（眉标仅封面保留）；右上不画任何徽章。"""
    lg = rounded_logo(HEADER_LOGO_COVER)
    im.paste(lg, (70, 58), lg)
    d.text((206, 74), WORDMARK, font=F_BOLD(HEADER_WORDMARK_COVER_SIZE),
           fill=INK, anchor="la")
    d.text((208, 142), SERIES_INTRO, font=F_MED(EYEBROW_SIZE), fill=GRAY, anchor="la")


def logo_header_inner(im, d):
    """内页页眉（02-06）：真 logo 56 + 字标 28 垂直居中；眉标/右上徽章不画。
    页眉区总高 ≤110px（logo 26–82）。"""
    lg = rounded_logo(HEADER_LOGO_INNER)
    im.paste(lg, HEADER_LOGO_XY, lg)
    d.text((HEADER_TEXT_X, HEADER_TEXT_Y), WORDMARK,
           font=F_BOLD(HEADER_WORDMARK_SIZE), fill=INK, anchor="lm")


def footer_note(d, idx):
    """统一页脚：左上系列名 + 右上页码 0N/06 + GOLD 细线；文字 28px 达标签底线。"""
    d.line([70, FOOTER_LINE_Y, W - 70, FOOTER_LINE_Y], fill=GOLD, width=2)
    d.text((70, FOOTER_TEXT_Y), FOOTER_LEFT, font=F_REG(FOOTER_SIZE),
           fill=GRAY, anchor="lm")
    d.text((W - 70, FOOTER_TEXT_Y), f"{idx:02d}/06", font=F_REG(FOOTER_SIZE),
           fill=GRAY, anchor="rm")


def inner_title(d, text):
    d.text((W // 2, TITLE_Y), text, font=F_BLACK(TITLE_SIZE), fill=INK, anchor="mm")


def script_badge(p):
    """字数小字（卡05 页脚上方）：全文 N 字 · 约 M 秒（以字段实测字数为准，秒数十位取整）。"""
    total = sum(len(str(p[k])) for k in SCRIPT_KEYS)
    secs = int(round(total / SPEECH_CPS / 10.0) * 10)
    return f"全文 {total} 字 · 约 {secs} 秒"


def strip_done_mark(s):
    """金句卡取 closing 时去掉口播收尾标记「答题完毕」（只减不增，不篡改正文）。"""
    s = str(s).strip()
    stripped = re.sub(r"答题完毕[。.!！!~]?\s*$", "", s).strip()
    return stripped or s


# ------------------------------------------------------------ 卡1 封面
def card1_cover(im, d, p, ctx):
    """logo 头（眉标=SERIES_INTRO 28px，无右上徽章）+ 系列名 96 墨 + 主题大字 132 枣红
    （超宽缩）+ 金短线 + 固定品牌 slogan Bold 46 枣红 + 页脚。
    副标题弃用 cover_hook（务实句退役），固定用开口练 slogan，与卡6 CTA 副行首尾呼应。"""
    logo_header_cover(im, d)
    t1 = WORDMARK
    s1 = fit_title(d, t1, 96, 56)
    y1 = 560
    d.text((W // 2, y1), t1, font=F_BLACK(s1), fill=INK, anchor="mm")
    t2 = ctx["topic"]
    s2 = fit_title(d, t2, 132, 64)
    y2 = y1 + int(s1 * 0.78) + 40
    d.text((W // 2, y2), t2, font=F_BLACK(s2), fill=CRIMSON, anchor="mm")
    y_div = y2 + int(s2 * 0.78) + 46
    d.line([W // 2 - 110, y_div, W // 2 + 110, y_div], fill=GOLD, width=6)
    s_h = fit_bold(d, BRAND_SLOGAN, 46, 28, 900)
    d.text((W // 2, y_div + 112), BRAND_SLOGAN, font=F_BOLD(s_h), fill=CRIMSON, anchor="mm")
    footer_note(d, 1)


# ------------------------------------------------------------ 卡2 题目
def card2_question(im, d, p, ctx):
    """大标「题目」+ 来源徽章缩为金底小胶囊（28px，白卡上方左对齐）
    + 题干白卡（Medium 40 起档自适应、≤6 行倾向）。"""
    logo_header_inner(im, d)
    inner_title(d, "题目")
    zone = ZONE_BOT - SOURCE_ZONE_TOP
    chosen = None
    for allow_long in (True, False):  # 先找 ≤6 行档，找不到再放宽行数
        for qf in QUESTION_TIERS:
            f_q = F_MED(qf)
            lines = wrap_text(d, p["question"], f_q, TX_W)
            card_h = len(lines) * (qf + 18) + 150
            if card_h <= zone and (allow_long and len(lines) <= 6
                                   or not allow_long):
                chosen = (qf, lines, card_h)
                break
        if chosen:
            break
    if chosen is None:
        raise CardOverflow("02-题目")
    qf, lines, card_h = chosen
    f_q = F_MED(qf)
    content_h = len(lines) * (qf + 18)
    y0 = SOURCE_ZONE_TOP + (zone - card_h) // 2
    # 打磨环 R1：来源胶囊吸附在题干卡上方（随卡移动），不再悬空在内容区顶
    f_s = F_BOLD(LABEL_SIZE)
    sw = tw(d, ctx["source_badge"], f_s)
    sh = LABEL_SIZE + 2 * LABEL_PAD_Y
    cy = max(SOURCE_CAPSULE_Y, y0 - sh - 20)
    rounded(d, [80, cy, 80 + sw + 2 * LABEL_PAD_X, cy + sh], sh // 2, fill=GOLD_BG)
    d.text((80 + LABEL_PAD_X + sw / 2, cy + sh / 2),
           ctx["source_badge"], font=f_s, fill=CRIMSON, anchor="mm")
    shadow_card(im, d, [80, y0, 1000, y0 + card_h], 40)
    draw_wrapped(d, (TX_X, y0 + (card_h - content_h) // 2), p["question"],
                 f_q, INK, TX_W, line_gap=18)
    footer_note(d, 2)


# ------------------------------------------------------------ 卡3 答题思路
def card3_outline(im, d, p, ctx):
    """大标「答题思路」+ 破题角度（枣红 Bold）+ 切入理由 + 核心观点标题 + 导语
    + 3 条编号观点（编号方块收缩 26px 装饰块，观点正文 30px）。
    档位自动降，仍超高 FAIL。"""
    logo_header_inner(im, d)
    inner_title(d, "答题思路")
    zone = ZONE_BOT - ZONE_TOP
    chosen = None
    for af, rf, vf, inf, vw in OUTLINE_TIERS:
        la = n_lines(d, p["break_angle"], F_BOLD(af), TX_W)
        lr = n_lines(d, p["break_angle_reason"], F_MED(rf), TX_W)
        lv = n_lines(d, p["core_views_title"], F_BOLD(vf), TX_W)
        li = n_lines(d, p["core_views_intro"], F_MED(inf), TX_W)
        vs = [n_lines(d, v, F_MED(vw), TX_W - SQ_SIZE - 22) for v in p["core_views"]]
        h = (la * (af + 12) + 8 + lr * (rf + 9) + 34
             + lv * (vf + 14) + 8 + li * (inf + 8) + 14
             + sum(max(SQ_SIZE, n * (vw + 8)) + 20 for n in vs))
        if h + 2 * CARD_PAD <= zone:
            chosen = (af, rf, vf, inf, vw, la, lr, lv, li, vs, h)
            break
    if chosen is None:
        raise CardOverflow("03-答题思路")
    af, rf, vf, inf, vw, la, lr, lv, li, vs, h = chosen
    y0 = ZONE_TOP + (zone - h - 2 * CARD_PAD) // 2
    shadow_card(im, d, [80, y0, 1000, y0 + h + 2 * CARD_PAD], 40)
    y = y0 + CARD_PAD
    y = draw_wrapped(d, (TX_X, y), p["break_angle"], F_BOLD(af), CRIMSON,
                     TX_W, line_gap=12) + 8
    y = draw_wrapped(d, (TX_X, y), p["break_angle_reason"], F_MED(rf), GRAY,
                     TX_W, line_gap=9) + 34
    y = draw_wrapped(d, (TX_X, y), p["core_views_title"], F_BOLD(vf), INK,
                     TX_W, line_gap=14) + 8
    y = draw_wrapped(d, (TX_X, y), p["core_views_intro"], F_MED(inf), GRAY,
                     TX_W, line_gap=8) + 14
    f_v = F_MED(vw)
    for i, (v, n) in enumerate(zip(p["core_views"], vs), start=1):
        rounded(d, [TX_X, y, TX_X + SQ_SIZE, y + SQ_SIZE], 8, fill=CRIMSON)
        d.text((TX_X + SQ_SIZE // 2, y + SQ_SIZE // 2), str(i),
               font=F_BOLD(SQ_NUM_SIZE), fill=CREAM_W, anchor="mm")
        draw_wrapped(d, (TX_X + SQ_SIZE + 22, y + 1), v, f_v, INK,
                     TX_W - SQ_SIZE - 22, line_gap=8)
        y += max(SQ_SIZE, n * (vw + 8)) + 20
    footer_note(d, 3)


# ------------------------------------------------- 卡4/5 逐字稿（上/下）
# TR4.1 内容为王重排：两页满版直排（无白卡装饰），页签小胶囊 + 组间金线；
# 分页重平衡：上=开场定调+第一/二步，下=第三步+收尾（36px 正文下体量均衡，
# 原切分（开场+第一步 / 后两步+收尾）的下页约 1228px 超出可用区，会破 36px 底线）。
def _script_groups(p):
    return (
        (("label", "开场定调", p["opening"], INK),
         ("step", 0, p["point1_lead"], p["point1_body"], GRAY),
         ("step", 1, p["point2_lead"], p["point2_body"], GRAY)),
        (("step", 2, p["point3_lead"], p["point3_body"], GRAY),
         ("label", "收尾", p["closing"], INK)),
    )


def _step_head_w(d, idx):
    """步骤组首行头部宽：26px 编号方块 + 「第N步」28px + 间距。"""
    return SQ_SIZE + 14 + tw(d, STEP_TAGS[idx], F_BOLD(LABEL_SIZE)) + 18


def _group_measure(d, g, lf, bf):
    if g[0] == "label":
        return (LABEL_SIZE + 2 * LABEL_PAD_Y + 8
                + n_lines(d, g[2], F_MED(bf), SCRIPT_W) * (bf + SCRIPT_LINE_GAP))
    _, idx, lead, body, _fill = g
    head_w = _step_head_w(d, idx)
    nl = len(wrap_text_widths(d, lead, F_BOLD(lf),
                              lambda i, _hw=head_w: SCRIPT_W - _hw if i == 0 else SCRIPT_W))
    nb = n_lines(d, body, F_MED(bf), SCRIPT_W)
    return nl * (lf + SCRIPT_LEAD_GAP) + LEAD_BODY_GAP + nb * (bf + SCRIPT_LINE_GAP)


def _draw_group(d, g, y, lf, bf):
    if g[0] == "label":
        _, text, body, fill = g
        h = capsule(d, SCRIPT_X, y, text, bg=CRIMSON, fg=CREAM_W)
        draw_wrapped(d, (SCRIPT_X, y + h + 8), body, F_MED(bf), fill,
                     SCRIPT_W, line_gap=SCRIPT_LINE_GAP)
        return
    _, idx, lead, body, fill = g
    f_lead = F_BOLD(lf)
    head_w = _step_head_w(d, idx)
    lines = wrap_text_widths(d, lead, f_lead,
                             lambda i, _hw=head_w: SCRIPT_W - _hw if i == 0 else SCRIPT_W)
    sq_y = y + (lf - SQ_SIZE) // 2 + 2  # 编号方块与 lead 首行视觉居中
    rounded(d, [SCRIPT_X, sq_y, SCRIPT_X + SQ_SIZE, sq_y + SQ_SIZE], 8, fill=CRIMSON)
    d.text((SCRIPT_X + SQ_SIZE // 2, sq_y + SQ_SIZE // 2), str(idx + 1),
           font=F_BOLD(SQ_NUM_SIZE), fill=CREAM_W, anchor="mm")
    d.text((SCRIPT_X + SQ_SIZE + 14, y + 2), STEP_TAGS[idx],
           font=F_BOLD(LABEL_SIZE), fill=CRIMSON, anchor="la")
    yy = y
    for i, ln in enumerate(lines):
        d.text((SCRIPT_X + head_w if i == 0 else SCRIPT_X, yy), ln,
               font=f_lead, fill=INK, anchor="la")
        yy += lf + SCRIPT_LEAD_GAP
    yy += LEAD_BODY_GAP
    draw_wrapped(d, (SCRIPT_X, yy), body, F_MED(bf), fill, SCRIPT_W,
                 line_gap=SCRIPT_LINE_GAP)


def gold_rule(d, y):
    """组间细金线（GOLD 2px，替代白卡装饰）。"""
    d.line([SCRIPT_X, y, SCRIPT_X + SCRIPT_W, y], fill=GOLD, width=2)


def _render_script_page(im, d, p, page_no, groups):
    logo_header_inner(im, d)
    page_name = "上" if page_no == 0 else "下"
    zone_bot = SCRIPT_ZONE_BOT if page_no == 0 else SCRIPT_NOTE_Y - 34
    tag = f"答题逐字稿 · {page_name}"
    tag_h = capsule(d, SCRIPT_X, SCRIPT_ZONE_TOP, tag,
                    bg=GOLD_BG, fg=CRIMSON, pad_x=TAG_PAD_X, pad_y=TAG_PAD_Y)
    content_top = SCRIPT_ZONE_TOP + tag_h + SCRIPT_TAG_GAP
    chosen = None
    for lf, bf in SCRIPT_TIERS:
        hs = [_group_measure(d, g, lf, bf) for g in groups]
        total = sum(hs) + SCRIPT_GROUP_GAP * (len(groups) - 1)
        if total <= zone_bot - content_top:
            chosen = (lf, bf, hs, total)
            break
    if chosen is None:
        raise CardOverflow(f"0{4 + page_no}-逐字稿（{page_name}）")
    lf, bf, hs, total = chosen
    # 打磨 R2（君上裁定）：卡 04 内容近满保持顶对齐；卡 05 内容块（第三步+收尾+金线）
    # 在其可用区（页眉下界～字数注记上界）内垂直居中——版式原则「内容在剩余版面垂直
    # 居中」（wushi card-layout / huashu「留白要是构图，不是内容缺席」）；字数注记固定在底。
    y = content_top
    if page_no == 1:
        y += max(0, (zone_bot - content_top - total) // 2)
    for k, (g, h) in enumerate(zip(groups, hs)):
        if k:
            gold_rule(d, y - SCRIPT_GROUP_GAP // 2 - 1)
        _draw_group(d, g, y, lf, bf)
        y += h + SCRIPT_GROUP_GAP
    # 页脚（简报全卡要求：底部保留含页码）；卡 05 字数注记 y=1312 与页脚线 1352
    # 间距 22px 并存已验证（修复轮 1 C1：重写时漏调 footer_note，审查指出已补）
    footer_note(d, 4 + page_no)
    print(f"[OK] 逐字稿（{page_name}）档位 lead/body = {lf}/{bf}")


def card4_script_a(im, d, p, ctx):
    """逐字稿上：页签 + 「开场定调」+ 第一/二步（满版直排，金线分隔）。"""
    _render_script_page(im, d, p, 0, _script_groups(p)[0])


def card5_script_b(im, d, p, ctx):
    """逐字稿下：页签 + 第三步 + 「收尾」+ 页脚上方字数小字（全文 N 字 · 约 M 秒）。"""
    _render_script_page(im, d, p, 1, _script_groups(p)[1])
    d.text((W // 2, SCRIPT_NOTE_Y), script_badge(p), font=F_MED(24),
           fill=GRAY, anchor="mm")


# ------------------------------------------------------------ 卡6 收尾引流
def card6_close(im, d, p, ctx):
    """大标「背下来 · 开口就用」+ 金句卡（48 起档）
    + 米杏假大空对照条（×36/√40，固定示范句）+ 枣红 CTA 条（副行=品牌 slogan）。"""
    logo_header_inner(im, d)
    inner_title(d, "背下来 · 开口就用")
    zone = ZONE_BOT - ZONE_TOP
    golden = str(p.get("golden_line") or "").strip() or strip_done_mark(p["closing"])
    f_fake, f_real = F_MED(FAKE_SIZE), F_BOLD(REAL_SIZE)
    require_glyph(f_fake, MARK_NO)
    require_glyph(f_real, MARK_YES)
    nf = n_lines(d, MARK_NO + " " + FAKE_DEMO, f_fake, 840)
    nr = n_lines(d, MARK_YES + " " + REAL_DEMO, f_real, 840)
    h_c = 26 + nf * (FAKE_SIZE + 12) + 12 + nr * (REAL_SIZE + 14) + 26
    cta_h = 140
    chosen = None
    for gf in GOLDEN_TIERS:
        f_g = F_BOLD(gf)
        ng = n_lines(d, golden, f_g, TX_W)
        h_g = ng * (gf + 16) + 96
        if h_g + h_c + cta_h + 2 * 20 <= zone:
            chosen = (gf, ng, h_g)
            break
    if chosen is None:
        raise CardOverflow("06-收尾引流")
    gf, ng, h_g = chosen
    total = h_g + h_c + cta_h + 2 * 20
    y = ZONE_TOP + (zone - total) // 2
    # 金句白卡（居中折行）
    shadow_card(im, d, [80, y, 1000, y + h_g], 40)
    draw_wrapped(d, (0, y + 48), golden, F_BOLD(gf), INK, TX_W,
                 line_gap=16, center_x=W // 2)
    y += h_g + 20
    # 假大空对照条（固定示范句，米杏底：× 灰 / √ 枣红）
    rounded(d, [80, y, 1000, y + h_c], 32, fill=BEIGE)
    yy = draw_wrapped(d, (120, y + 26), MARK_NO + " " + FAKE_DEMO, f_fake, GRAY,
                      840, line_gap=12)
    draw_wrapped(d, (120, yy + 12), MARK_YES + " " + REAL_DEMO, f_real, CRIMSON,
                 840, line_gap=12)
    y += h_c + 20
    # 枣红 CTA 条
    rounded(d, [80, y, 1000, y + cta_h], 36, fill=CRIMSON)
    d.text((W // 2, y + 54), CTA_MAIN, font=F_BOLD(44), fill=CREAM_W, anchor="mm")
    d.text((W // 2, y + 106), BRAND_SLOGAN, font=F_MED(26), fill=HERO_SUB, anchor="mm")
    footer_note(d, 6)


# ------------------------------------------------------------ 笔记文案
def make_note_title(p, topic):
    """标题 ≤20 字，确定性拼装：topic + break_angle 提炼尾句；提炼不出用固定句式。"""
    topic = str(topic).strip()
    segs = [s.strip(" 　「」『』\"\"") for s in
            re.split(r"[，。；！？,;.!?" "]+", str(p["break_angle"]))]
    segs = [s for s in segs if len(s) >= 4]
    title = ""
    if segs:
        tail = segs[-1]
        if 4 <= len(tail) <= 10:
            title = f"{topic}，{tail}"
    if not (title and len(title) <= 20):
        title = f"{topic}怎么答？{len(p['core_views'])} 步思路＋逐字稿"
    if len(title) > 20:
        title = f"{topic} 每日一练"
    return title.replace('"', "")


NOTE_TEMPLATE = """---
title: "{title}"
type: 素材
业务线: 公考面试
板块: 01-Projects/自媒体内容库-持续项目/结构化
updated: {date}
tags:
  - 类型/素材
  - 业务线/公考结构化
---

# {type}·{topic} · 小红书图文笔记文案

> 配图：同目录 `{img_first}` 至 `{img_last}` 共 6 张（1080×1440，3:4）
> 视觉：答一道 VI（米色底 #fbf6ed · 枣红 #87110f · 金棕 #e3c79f），总分总 logo
> 口径：与 final 逐字稿一致；无「保过 / 直接背 / 万能」类表述

## 标题

1. **{title}**（配封面图）

## 正文

{break_angle}

1. {v0}
2. {v1}
3. {v2}

{closing}

{guide}

## 话题标签

`{tags}`
"""


def write_note(p, ctx, outdir):
    tags = " ".join(NOTE_TAGS + [f"#{re.sub(r'\\s+', '', ctx['type'])}"])
    views = list(p["core_views"]) + [""] * (3 - len(p["core_views"]))
    content = NOTE_TEMPLATE.format(
        title=make_note_title(p, ctx["topic"]),
        date=datetime.date.today().isoformat(),
        type=ctx["type"], topic=ctx["topic"],
        img_first=CARD_FILES[0], img_last=CARD_FILES[-1],
        break_angle=str(p["break_angle"]).strip(),
        v0=views[0].strip(), v1=views[1].strip(), v2=views[2].strip(),
        closing=str(p["closing"]).strip(),
        guide=NOTE_GUIDE, tags=tags,
    )
    (safe_path(outdir, "笔记文案.md")).write_text(content, encoding="utf-8")


# ------------------------------------------------------------ logo 校验
def check_logos(outdir):
    """--check：6 图存在 + logo 区域枣红占比 ≥50%（真图实测约 93%；封面/内页框不同）。"""
    ok = True
    for i, name in enumerate(CARD_FILES):
        try:
            path = safe_path(outdir, name)
        except ValueError as e:
            print(f"[FAIL] --check 路径越界: {e}")
            return False
        if not path.is_file():
            print(f"[FAIL] --check 缺文件: {name}")
            ok = False
            continue
        im = Image.open(path).convert("RGB")
        if im.size != (W, H):
            print(f"[FAIL] --check 尺寸不符: {name} {im.size}")
            ok = False
            continue
        box = LOGO_BOX if i == 0 else LOGO_BOX_INNER
        raw = im.crop(box).tobytes()  # RGB，3 字节/像素
        n = len(raw) // 3
        crim = 0
        for j in range(0, len(raw), 3):
            if (max(abs(raw[j] - CRIMSON[0]), abs(raw[j + 1] - CRIMSON[1]),
                    abs(raw[j + 2] - CRIMSON[2])) < 60):
                crim += 1
        verdict = crim / n >= 0.5
        status = "PASS" if verdict else "FAIL"
        if not verdict:
            ok = False
        print(f"[{status}] logo {name}: 枣红占比 {crim/n:.0%}（≥50%）")
    return ok


# ------------------------------------------------------------ 进度与目录
def read_done(img_root):
    """读 progress_answer.json 的 done 列表；无文件视为空。"""
    path = img_root / PROGRESS_NAME
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise SystemExit(f"[FAIL] 进度文件损坏: {path} —— {e}")
    done = data.get("done", [])
    return list(done) if isinstance(done, list) else []


def append_done(img_root, qid):
    """渲染+校验全部成功后才追加 done（已存在则不重复追加）。"""
    done = read_done(img_root)
    if qid in done:
        print(f"[NOTE] done 已含 {qid}，不重复追加")
        return
    done.append(qid)
    path = img_root / PROGRESS_NAME
    path.write_text(json.dumps({"done": done}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"[OK] 进度追加 {qid} → {path}")


def derive_qid(final_path):
    """从 final 文件名提取题 id：draft_yj-01_final.json → yj-01；不合式则用文件名。"""
    stem = Path(final_path).stem
    qid = stem
    if qid.endswith("_final"):
        qid = qid[: -len("_final")]
    if qid.startswith("draft_"):
        qid = qid[len("draft_"):]
    return qid or stem


def sanitize_name(s):
    return re.sub(r"[/\\:]", "／", str(s)).strip() or "未命名"


def derive_outdir(project_root, issue, type_, topic):
    """期目录名：第{期号}-{题型}-{主题}（缺省写在 <project-root>/图片输出/ 下）。"""
    img_root = Path(project_root) / IMG_DIR
    name = f"第{issue}期-{sanitize_name(type_)}-{sanitize_name(topic)}"
    return img_root / name


# ------------------------------------------------------------ 主流程
def validate_final(p):
    if not isinstance(p, dict):
        raise SystemExit("[FAIL] final JSON 顶层须为对象")
    for k in REQUIRED_FIELDS:
        if k not in p:
            raise SystemExit(f"[FAIL] final 缺字段: {k}")
    views = p.get("core_views")
    if (not isinstance(views, list) or len(views) != 3
            or not all(isinstance(v, str) and v.strip() for v in views)):
        raise SystemExit("[FAIL] core_views 须为恰 3 条非空字符串")


def build_ctx(args, p, issue):
    prefix = str(p.get("title_prefix") or "")
    source_badge = "历年考题" if "历年考题" in prefix else "每日一练"
    return {
        "issue": issue,
        "type": args.type,
        "topic": args.topic,
        "source_badge": source_badge,
        "script_badge": script_badge(p),
    }


def render_all(p, ctx):
    cards = [card1_cover, card2_question, card3_outline,
             card4_script_a, card5_script_b, card6_close]
    rendered = []
    for fn, name in zip(cards, CARD_FILES):
        im, d = new_card()
        try:
            fn(im, d, p, ctx)
        except CardOverflow as e:
            raise SystemExit(
                f"[FAIL] 卡{e.card} 内容超高：最低档仍放不下，不许截断——请人工精简")
        rendered.append((im, name))
    return rendered


def main():
    ap = argparse.ArgumentParser(
        description="结构化每日一练·答一道 6 卡渲染（答一道 VI 简洁风）")
    ap.add_argument("--project-root", required=True, help="vault 项目根目录")
    ap.add_argument("--final", help="final JSON（16 键，只读）")
    ap.add_argument("--type", help="题型，如 应急应变")
    ap.add_argument("--topic", help="题目主题，如 政务大厅断电")
    ap.add_argument("--outdir", default=None,
                    help="缺省写到 <project-root>/图片输出/第XXX期-题型-主题/")
    ap.add_argument("--check", action="store_true",
                    help="只复核已生成期目录的 logo 像素与 6 图存在，不渲染")
    args = ap.parse_args()

    root = Path(args.project_root)
    if not root.is_dir():
        print(f"[FAIL] 项目根不存在: {root}")
        sys.exit(1)
    img_root = (root / IMG_DIR).resolve()

    if args.check:
        if not args.outdir:
            ap.error("--check 需要 --outdir")
        outdir = Path(args.outdir).resolve()
        if not (outdir == img_root or outdir.is_relative_to(img_root)):
            print(f"[FAIL] outdir 不在 {img_root} 内: {outdir}")
            sys.exit(1)
        sys.exit(0 if check_logos(outdir) else 1)

    if not (args.final and args.type and args.topic):
        ap.error("渲染需要 --final / --type / --topic")

    # 资产先验：字体/logo 缺失即 STOP，不动磁盘
    ensure_assets()

    final_path = Path(args.final)
    if not final_path.is_file():
        print(f"[FAIL] final 不存在: {final_path}")
        sys.exit(1)
    try:
        p = json.loads(final_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[FAIL] final JSON 损坏: {e}")
        sys.exit(1)
    validate_final(p)

    done = read_done(img_root)
    issue = f"{len(done) + 1:03d}"
    qid = derive_qid(final_path)
    ctx = build_ctx(args, p, issue)

    if args.outdir:
        outdir = Path(args.outdir).resolve()
    else:
        outdir = derive_outdir(root, issue, args.type, args.topic).resolve()
    if not (outdir == img_root or outdir.is_relative_to(img_root)):
        print(f"[FAIL] outdir 不在 {img_root} 内: {outdir}")
        sys.exit(1)
    # 先全部渲染进内存再落盘：任何一张失败都不留半套图、不建期目录
    try:
        rendered = render_all(p, ctx)
    except SystemExit as e:
        print(e)
        sys.exit(1)
    if outdir.exists():
        print(f"[NOTE] 期目录已存在，将覆盖同名文件: {outdir.name}")
    outdir.mkdir(parents=True, exist_ok=True)
    for im, name in rendered:
        im.save(safe_path(outdir, name))
        print(f"[OK] 渲染 {name}")
    write_note(p, ctx, outdir)
    print("[OK] 渲染 笔记文案.md")

    if not check_logos(outdir):
        print("[FAIL] logo 像素校验未通过，进度不追加")
        sys.exit(1)

    append_done(img_root, qid)
    print(f"✅ 全部通过（6 图 + 笔记文案.md）→ {outdir}")


if __name__ == "__main__":
    main()

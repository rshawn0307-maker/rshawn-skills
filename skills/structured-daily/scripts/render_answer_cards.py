#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""结构化每日一练·答一道 小红书 6 卡渲染引擎（C 留白范式，PIL 直出）。

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

视觉契约见 wushi-daily references/card-layout.md（色值/字体/logo/wrap 同源）。

TR5 C 留白范式（用户选定方向，全部 6 卡）:
  - 底＝米白 #fff8ec；文字＝墨 #271e1b；点缀＝枣红 #87110f（标题/编号方块/印章）＋
    金 #e3c79f（tabline/细线）；无白色投影卡——文字直接排米白底，发丝线分隔；
  - 边距统一 84px；内页标题系统＝44px 枣红 Black＋金 tabline（72×5）；
  - 01 封面（TR5.1 起＝C2 居中大字版）：logo 印章 96px＋右上「第 N 期 · 题型」28px 灰
    ＋居中块「每日一练 · 答一道」30 枣红→主题 100 Black→金短线 120×6→slogan 30 灰
    （C1 竖排主题/竖排 slogan/封面方印退役；卡 06 方印保留）；
  - 02 题目：题干 40px 行距 1.7 居于上 1/3 区，来源枣红描边胶囊吸题干顶；
  - 03 思路：破题 38 枣红/理由 34 墨/核心观点 34 bold/导语 32 灰/观点 32 起排
    （降档下限 28，TR4.1 裁定口径），编号方块 26px；
  - 04/05 逐字稿：页签即标题系统；正文直接排米白底；分布/字号维持现行裁定
    （04=开场+第一/二步、05=第三步+收尾，均顶对齐；36/40）；步骤编号方块 40px；
    步间发丝线；卡 05 页脚上方字数小字 24px 灰；
  - 06 每题金句：金句（opening 末句规则不变）52px 墨色横排居中于版面中部（无卡无框），
    右下枣红方印「答一道」呼应封面；CTA 条保留贴页脚上方。
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
# —— VI 色板（成员不变；未使用者保留备查）——
BG = (255, 248, 236)        # fff8ec 米白画布底（C 留白范式）
INK = (39, 30, 27)          # 271e1b 墨色主文字
CRIMSON = (135, 17, 15)     # 87110f 枣红主色/编号方块/印章/标题
CREAM_W = (255, 248, 236)   # fff8ec 枣红底上的文字（与 BG 同值不同角色）
GOLD = (227, 199, 159)      # e3c79f 金棕 tabline/细线
GOLD_BG = (239, 224, 201)   # efe0c9 金棕胶囊底（历史徽章，备查）
BEIGE = (243, 233, 218)     # f3e9da 米杏（历史对照条底，备查）
GRAY = (117, 103, 95)       # 75675f 暖灰辅助文字
BORDER = (226, 215, 200)    # e2d7c8 发丝线/页脚线
CARD_W = (255, 255, 255)    # 白色（历史白卡，备查）
RED_BG = (247, 235, 233)    # f7ebe9 红系行底（备查）
RED_TXT = (170, 44, 40)     # aa2c28 红线文字（备查）
HERO_SUB = (236, 220, 196)  # ecdcc4 枣红 CTA 条上的浅金副字
SHADOW = (238, 227, 214)    # eee3d6 历史白卡投影（备查）

FONT_DIR = "/Users/shawn/Library/Fonts"
FONT_FILES = {
    "black": "HarmonyOS_Sans_SC_Black.ttf",
    "bold": "HarmonyOS_Sans_SC_Bold.ttf",
    "med": "HarmonyOS_Sans_SC_Medium.ttf",
    "reg": "HarmonyOS_Sans_SC_Regular.ttf",
}
LOGO_PATH = "/Users/shawn/Desktop/AI工作区/01-Projects/公考橙皮书/assets/logo-zfz.png"
SERIES_INTRO = "把考场真实答法，搬进你的答案"   # 眉标（TR4.x 封面眉标；TR5 封面弃用，备查）
BRAND_SLOGAN = "先答一道，把最影响得分的地方找出来"  # 封面竖排 slogan＝卡6 CTA 副行（开口练 hero 原话）
CTA_MAIN = "答一道 · 每日一练"                  # 卡6 CTA 主行
FOOTER_LEFT = "结构化每日一练 · 答一道"         # 页脚左上（统一）
NOTE_GUIDE = "想要完整逐字稿，评论区打「1」"    # 笔记文案固定引导
NOTE_TAGS = ["#结构化面试", "#公考面试", "#答题思路", "#每日一练", "#上岸"]
WORDMARK = "结构化每日一练"                     # 内页页眉字标
SPEECH_CPS = 3.5                                # 逐字稿口播速率（字/秒，≈210 字/分钟），字数小字估算用
IMG_DIR = "图片输出"
PROGRESS_NAME = "progress_answer.json"

# ---- C 留白版面（TR5）：边距 84；内页标题 44 枣红＋金 tabline；发丝线页脚 ----
MARGIN = 84
TX_X, TX_W = MARGIN, W - 2 * MARGIN     # 84 / 912 全卡统一
TITLE_Y, TITLE_SIZE = 150, 44           # 内页大标题/页签（枣红 Black）＋金 tabline
TABLINE = (MARGIN, 208, MARGIN + 72, 213)   # 金 72×5
ZONE_TOP, ZONE_BOT = 260, 1330          # 内容区（标题/tabline 之下～页脚线之上）
HEADER_LOGO_INNER = 56                  # 内页页眉 logo（56px 圆角）＋字标 28px 墨
HEADER_LOGO_XY = (MARGIN, 28)
HEADER_TEXT_X, HEADER_TEXT_Y = MARGIN + 56 + 16, 56
HEADER_WORDMARK_SIZE = 28
HEADER_LOGO_COVER = 96                  # 封面 logo 印章 96px 圆角
FOOTER_SIZE = 28                        # 页脚文字（发丝线＋28px 灰）
FOOTER_LINE_Y = 1330                    # 发丝线（BORDER 2px）
FOOTER_TEXT_Y = 1374
LOGO_BOX = (84, 72, 180, 168)           # 封面 logo 像素校验框（96px 贴图位）
LOGO_BOX_INNER = (84, 28, 140, 84)      # 内页 logo 像素校验框（56px 贴图位）

# ---- 卡2 题目：题干 40px 行距 1.7，居上 1/3 区；来源枣红描边胶囊吸题干顶 ----
QUESTION_TIERS = (40, 38, 36, 34, 32, 30)
QUESTION_ADVANCE = 68                   # 40×1.7
Q_CENTER_Y = 438                        # 标题下～页脚上之间的上 1/3 区中心
CAPSULE_TEXT_SIZE = 28                  # 来源描边胶囊（枣红描边，标签底线内）

# ---- 卡3 答题思路：观点正文 32 起排（降档下限 28，TR4.1 裁定口径）----
SQ_SIZE = 26                            # 观点编号方块（清单同构）
SQ_NUM_SIZE = 16
OUTLINE_TIERS = ((38, 34, 34, 32, 32), (36, 32, 32, 30, 30),
                 (34, 30, 30, 28, 28), (32, 28, 28, 28, 28))
#            (破题 Bold, 理由 Med, 观点题 Bold, 导语 Med, 观点正文 Med)

# ---- 卡4/5 逐字稿：满版直排，分布/字号维持现行裁定 ----
SCRIPT_X, SCRIPT_W = MARGIN, W - 2 * MARGIN
SCRIPT_ZONE_BOT = ZONE_BOT
SCRIPT_NOTE_Y = 1290              # 卡05 页脚线上方字数小字（24px 灰，辅助标注）
SCRIPT_LEAD_SIZE = 40             # lead 设计档
SCRIPT_BODY_SIZE = 36             # 正文设计档（huashu 底线）
SCRIPT_LEAD_GAP = 6               # 行距（现行裁定）
SCRIPT_LINE_GAP = 6
LEAD_BODY_GAP = 8
SCRIPT_GROUP_GAP = 28             # 组间距（发丝线居中：上下各 13 + 线 2，打磨 R1）
SCRIPT_ZONE_TOP = 248             # 打磨 R1：顶对齐末行不贴页脚线（距线 ~32px）
SCRIPT_TIERS = ((40, 36), (38, 34), (36, 32), (34, 30), (32, 28))  # 超高自动降档，仍超高 FAIL
SQ_STEP = 40                      # 步骤编号方块（TR5：40px）
SQ_STEP_NUM = 26                  # 方块内数字

# ---- 卡6 每题金句：金句横排居中（无卡无框）＋枣红方印＋CTA 条 ----
GOLDEN_TIERS = (52, 48, 44, 40, 36)  # 金句 52 起档可降
GOLDEN_LEAD_GAP = 20                 # 金句行距（TR4.3 打磨：背诵素材留白）
GOLDEN_MAX = 60                      # opening 末句超此字数回退 closing
CTA_H = 140                          # 枣红 CTA 条高（现行）
CTA_Y = 1150                         # CTA 贴页面下方页脚上方
SEAL_SIZE = 110                      # 枣红方印（呼应封面）

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
    """字体四档 + 品牌 logo 缺失/不可读即 STOP exit 非 0，不静默降级。"""
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
    if not Path(LOGO_PATH).is_file():
        raise SystemExit(f"[FAIL] 品牌 logo 缺失: {LOGO_PATH} —— STOP，不静默降级")


_probe_draw = None


def glyph_height(s, f):
    """textbbox 高度：字体缺该字形时为 0（渲染即空白）。通用工具，
    供日后复用特殊符号绘制前自检。"""
    global _probe_draw
    if _probe_draw is None:
        _probe_draw = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    b = _probe_draw.textbbox((0, 0), s, font=f)
    return b[3] - b[1]


def require_glyph(f, *chars):
    """绘制前字形断言（通用工具）：任一符号 bbox 高 ≤0 即 STOP exit 非 0，
    不静默画空白。HarmonyOS Sans SC 缺 U+2717/U+2713 字形——若日后复用
    对照条符号必须用有真实字形的 ×/√ 并先行断言（历史教训 I-1）。"""
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


NO_LINE_START = "、，。：；！？·）》」』%,.;:!?)]"
NO_LINE_END = "「『（《"
TAIL_PUNCT = "。，、；：！？"   # 句读尾：孤行借字判定用（TR4.2 打磨）


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
    # 末行孤字向上借字：末行仅 1 字，或「单字+句读」两字行（如「置。」）均视为孤行，
    # 从上一行借一字成 3 字行（TR4.2 打磨；huashu 体检项：末行孤字）
    if (len(lines) >= 2 and len(lines[-2]) > 3
            and (len(lines[-1]) == 1
                 or (len(lines[-1]) == 2 and lines[-1][1] in TAIL_PUNCT))):
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
    """封面页眉：logo 印章 96px 圆角（左上 84,72）；无字标/眉标（C 留白）。"""
    lg = rounded_logo(HEADER_LOGO_COVER)
    im.paste(lg, (MARGIN, 72), lg)


def logo_header_inner(im, d):
    """内页页眉（02-06）：logo 56px 圆角（84,28）+ 字标 28px 墨（垂直居中）。
    页眉区总高 ≤110px（logo 28–84）。"""
    lg = rounded_logo(HEADER_LOGO_INNER)
    im.paste(lg, HEADER_LOGO_XY, lg)
    d.text((HEADER_TEXT_X, HEADER_TEXT_Y), WORDMARK,
           font=F_BOLD(HEADER_WORDMARK_SIZE), fill=INK, anchor="lm")


def inner_title(d, text):
    """内页标题系统（TR5）：44px 枣红 Black 左对齐 + 金 tabline 72×5。"""
    d.text((MARGIN, TITLE_Y), text, font=F_BLACK(TITLE_SIZE),
           fill=CRIMSON, anchor="la")
    d.rectangle(TABLINE, fill=GOLD)


def footer_note(d, idx):
    """统一页脚：发丝线（BORDER 2px）+ 左系列名/右页码 28px 灰。"""
    d.line([MARGIN, FOOTER_LINE_Y, W - MARGIN, FOOTER_LINE_Y],
           fill=BORDER, width=2)
    d.text((MARGIN, FOOTER_TEXT_Y), FOOTER_LEFT, font=F_REG(FOOTER_SIZE),
           fill=GRAY, anchor="lm")
    d.text((W - MARGIN, FOOTER_TEXT_Y), f"{idx:02d}/06", font=F_REG(FOOTER_SIZE),
           fill=GRAY, anchor="rm")


def draw_centered_spaced(d, cx, y, text, f, fill, spacing):
    """居中加字距逐字绘制（letter-spacing 对应实现）：整串按 字宽+spacing 累计后
    以 cx 居中，逐字左起排布；只重排不增删字。"""
    text = str(text)
    widths = [tw(d, ch, f) + spacing for ch in text]
    x = cx - (sum(widths) - spacing) / 2
    for ch, w in zip(text, widths):
        d.text((x, y), ch, font=f, fill=fill, anchor="la")
        x += w


def script_badge(p):
    """字数小字（卡05 页脚线上方）：全文 N 字 · 约 M 秒（以字段实测字数为准，秒数十位取整）。"""
    total = sum(len(str(p[k])) for k in SCRIPT_KEYS)
    secs = int(round(total / SPEECH_CPS / 10.0) * 10)
    return f"全文 {total} 字 · 约 {secs} 秒"


def strip_done_mark(s):
    """金句取 closing 时去掉口播收尾标记「答题完毕」（只减不增，不篡改正文）。"""
    s = str(s).strip()
    stripped = re.sub(r"答题完毕[。.!！!~]?\s*$", "", s).strip()
    return stripped or s


def opening_golden(p):
    """金句换源（TR4.4）：取逐字稿 opening（定调段）末句——按句号切分定位最后一句，
    含句末标点、为 opening 原文逐字子串不改动；末句为空/仅剩句读或超 60 字时
    回退 closing（去「答题完毕」，TR4.1 既有逻辑）。"""
    text = str(p["opening"]).strip()
    end = text.rfind("。")
    tail = text[end + 1:].strip()
    if tail:
        # 句号后仍有内容（！？收尾或无标点收尾）：该尾巴即最后一句
        last = tail
    elif end != -1:
        start = text.rfind("。", 0, end) + 1  # 倒数第二个句号之后
        last = text[start:end + 1].strip()    # 末句连同句号，纯子串
    else:
        last = text  # 整段无句号，整段即末句
    if last.strip("。，、；：！？") and len(last) <= GOLDEN_MAX:
        return last
    return strip_done_mark(p["closing"])


# ------------------------------------------------------------ 卡1 封面
def card1_cover(im, d, p, ctx):
    """C2 居中大字封面（照 c2.html，TR5.1）：logo 印章 96px 左上＋右上
    「第 N 期 · 题型」28px 灰＋居中块（「每日一练 · 答一道」30 枣红→主题
    100px Black 墨→金短线 120×6→slogan 30 灰，均加宽字距居中）＋发丝线页脚。
    C1 竖排主题/竖排 slogan/方印退役（仅封面；卡 06 方印保留）。"""
    logo_header_cover(im, d)
    d.text((W - MARGIN, 96), f"第 {ctx['issue']} 期 · {ctx['type']}",
           font=F_MED(28), fill=GRAY, anchor="ra")
    # 居中块（c2.html .center top=460）：tag→主题→金短线→slogan
    tag_y = 464
    draw_centered_spaced(d, W // 2, tag_y, "每日一练 · 答一道",
                         F_MED(30), CRIMSON, 6)
    topic = str(ctx["topic"])
    size = 100
    while len(topic) * (size + 8) > W - 2 * MARGIN and size > 60:
        size -= 2  # 超宽主题逐档降（每档 -2px），只缩不截
    if len(topic) * (size + 8) > W - 2 * MARGIN:
        # 君上裁决 TR5.1：60px 下限档仍超宽（约 ≥14 字）→ 显式 FAIL，不静默裁字，
        # 与全产线「只折行永不截断、超高显式 FAIL」纪律一致
        raise SystemExit(
            f"[FAIL] 封面主题超长：{len(topic)} 字在 60px 下限档仍超可用宽 "
            f"{W - 2 * MARGIN}px（需字号 ≤{W // len(topic) - 8}px），"
            "不许截断——请精简主题")
    h1_y = tag_y + 36 + 44
    draw_centered_spaced(d, W // 2, h1_y, topic, F_BLACK(size), INK, 8)
    line_y = h1_y + size + 70
    d.rectangle([W // 2 - 60, line_y, W // 2 + 60, line_y + 6], fill=GOLD)
    draw_centered_spaced(d, W // 2, line_y + 6 + 64, BRAND_SLOGAN,
                         F_MED(30), GRAY, 3)
    footer_note(d, 1)


# ------------------------------------------------------------ 卡2 题目
def card2_question(im, d, p, ctx):
    """标题「题目」44 枣红＋金 tabline；题干 40px 行距 1.7 直接排米白底，
    垂直居中于上 1/3 区；来源枣红描边胶囊（28px）吸题干顶。无白卡。"""
    logo_header_inner(im, d)
    inner_title(d, "题目")
    q = str(p["question"])
    chosen = None
    for allow_long in (True, False):  # 先找 ≤6 行档，找不到再放宽行数
        for qf in QUESTION_TIERS:
            f_q = F_MED(qf)
            lines = wrap_text(d, q, f_q, TX_W)
            block_h = len(lines) * (qf + 28)
            if block_h <= ZONE_BOT - 260 and (allow_long and len(lines) <= 6
                                              or not allow_long):
                chosen = (qf, lines, block_h)
                break
        if chosen:
            break
    if chosen is None:
        raise CardOverflow("02-题目")
    qf, lines, block_h = chosen
    f_q = F_MED(qf)
    # 上 1/3 区（260..Q_CENTER_Y+178）垂直居中；胶囊吸题干顶（下限不越 tabline）
    q_top = max(Q_CENTER_Y - block_h // 2, 320)
    cap_h = CAPSULE_TEXT_SIZE + 2 * 8
    cap_y = max(264, q_top - cap_h - 20)
    if cap_y + cap_h > q_top - 12:  # 钳制后仍贴题干：题干块下让
        q_top = cap_y + cap_h + 16
    label = str(ctx["source_badge"])
    f_s = F_BOLD(CAPSULE_TEXT_SIZE)
    sw = tw(d, label, f_s)
    rounded(d, [MARGIN, cap_y, MARGIN + sw + 32, cap_y + cap_h], cap_h // 2,
            outline=CRIMSON, width=2)
    d.text((MARGIN + 16 + sw / 2, cap_y + cap_h / 2), label,
           font=f_s, fill=CRIMSON, anchor="mm")
    y = q_top
    for ln in lines:
        d.text((TX_X, y), ln, font=f_q, fill=INK, anchor="la")
        y += QUESTION_ADVANCE
    footer_note(d, 2)


# ------------------------------------------------------------ 卡3 答题思路
def card3_outline(im, d, p, ctx):
    """标题「答题思路」44 枣红＋金 tabline；破题 38 枣红 bold／理由 34 墨／
    核心观点 34 bold／导语 32 灰／三观点（26px 编号方块＋32px 正文，清单同构）。
    文字直接排米白底，整组垂直居中；文字一字不改。档位自动降（下限 28）。"""
    logo_header_inner(im, d)
    inner_title(d, "答题思路")
    zone = ZONE_BOT - ZONE_TOP
    chosen = None
    for af, rf, vf, inf, vw in OUTLINE_TIERS:
        la = n_lines(d, p["break_angle"], F_BOLD(af), TX_W)
        lr = n_lines(d, p["break_angle_reason"], F_MED(rf), TX_W)
        lv = n_lines(d, p["core_views_title"], F_BOLD(vf), TX_W)
        li = n_lines(d, p["core_views_intro"], F_MED(inf), TX_W)
        vs = [n_lines(d, v, F_MED(vw), TX_W - SQ_SIZE - 22)
              for v in p["core_views"]]
        h = (la * (af + 12) + 16 + lr * (rf + 20) + 36
             + lv * (vf + 14) + 8 + li * (inf + 10) + 16
             + sum(max(SQ_SIZE, n * (vw + 10)) + 20 for n in vs))
        if h <= zone:
            chosen = (af, rf, vf, inf, vw, la, lr, lv, li, vs, h)
            break
    if chosen is None:
        raise CardOverflow("03-答题思路")
    af, rf, vf, inf, vw, la, lr, lv, li, vs, h = chosen
    y = ZONE_TOP + (zone - h) // 2  # 内容组在留白区垂直居中
    y = draw_wrapped(d, (TX_X, y), p["break_angle"], F_BOLD(af), CRIMSON,
                     TX_W, line_gap=12) + 16
    y = draw_wrapped(d, (TX_X, y), p["break_angle_reason"], F_MED(rf), INK,
                     TX_W, line_gap=20) + 36
    y = draw_wrapped(d, (TX_X, y), p["core_views_title"], F_BOLD(vf), INK,
                     TX_W, line_gap=14) + 8
    y = draw_wrapped(d, (TX_X, y), p["core_views_intro"], F_MED(inf), GRAY,
                     TX_W, line_gap=10) + 16
    f_v = F_MED(vw)
    for i, (v, n) in enumerate(zip(p["core_views"], vs), start=1):
        rounded(d, [TX_X, y, TX_X + SQ_SIZE, y + SQ_SIZE], 6, fill=CRIMSON)
        d.text((TX_X + SQ_SIZE // 2, y + SQ_SIZE // 2), str(i),
               font=F_BOLD(SQ_NUM_SIZE), fill=CREAM_W, anchor="mm")
        draw_wrapped(d, (TX_X + SQ_SIZE + 22, y + 1), v, f_v, INK,
                     TX_W - SQ_SIZE - 22, line_gap=10)
        y += max(SQ_SIZE, n * (vw + 10)) + 20
    footer_note(d, 3)


# ------------------------------------------------- 卡4/5 逐字稿（上/下）
# TR5：无白卡，正文直接排米白底；页签即标题系统；分布/字号维持现行裁定
# （04=开场+第一/二步、05=第三步+收尾，均顶对齐；36/40）；步骤编号方块 40px；
# 步间发丝线；开场/收尾胶囊标签退役（C 留白单焦点，段落即结构）。
def _script_groups(p):
    return (
        (("para", p["opening"], INK),
         ("step", 0, p["point1_lead"], p["point1_body"]),
         ("step", 1, p["point2_lead"], p["point2_body"])),
        (("step", 2, p["point3_lead"], p["point3_body"]),
         ("para", p["closing"], INK)),
    )


def _step_head_w(d, idx):
    """步骤组首行头部宽：40px 编号方块 + 18px 间距（C：方块后直接 lead）。"""
    return SQ_STEP + 18


def _group_measure(d, g, lf, bf):
    if g[0] == "para":
        return n_lines(d, g[1], F_MED(bf), SCRIPT_W) * (bf + SCRIPT_LINE_GAP)
    _, idx, lead, body = g
    head_w = _step_head_w(d, idx)
    nl = len(wrap_text_widths(d, lead, F_BOLD(lf),
                              lambda i, _hw=head_w: SCRIPT_W - _hw if i == 0 else SCRIPT_W))
    nb = n_lines(d, body, F_MED(bf), SCRIPT_W)
    return nl * (lf + SCRIPT_LEAD_GAP) + LEAD_BODY_GAP + nb * (bf + SCRIPT_LINE_GAP)


def _draw_group(d, g, y, lf, bf):
    if g[0] == "para":
        draw_wrapped(d, (SCRIPT_X, y), g[1], F_MED(bf), INK, SCRIPT_W,
                     line_gap=SCRIPT_LINE_GAP)
        return
    _, idx, lead, body = g
    f_lead = F_BOLD(lf)
    head_w = _step_head_w(d, idx)
    lines = wrap_text_widths(d, lead, f_lead,
                             lambda i, _hw=head_w: SCRIPT_W - _hw if i == 0 else SCRIPT_W)
    # 40px 枣红编号方块与 lead 首行同构对齐
    rounded(d, [SCRIPT_X, y, SCRIPT_X + SQ_STEP, y + SQ_STEP], 8, fill=CRIMSON)
    d.text((SCRIPT_X + SQ_STEP // 2, y + SQ_STEP // 2), str(idx + 1),
           font=F_BOLD(SQ_STEP_NUM), fill=CREAM_W, anchor="mm")
    yy = y
    for i, ln in enumerate(lines):
        d.text((SCRIPT_X + head_w if i == 0 else SCRIPT_X, yy), ln,
               font=f_lead, fill=INK, anchor="la")
        yy += lf + SCRIPT_LEAD_GAP
    yy += LEAD_BODY_GAP
    draw_wrapped(d, (SCRIPT_X, yy), body, F_MED(bf), INK, SCRIPT_W,
                 line_gap=SCRIPT_LINE_GAP)


def _hairline(d, y):
    """组间发丝线（GOLD 2px 细金线；打磨 R1：1px 在米白底上几乎不可见）。"""
    d.line([SCRIPT_X, y, SCRIPT_X + SCRIPT_W, y], fill=GOLD, width=2)


def _render_script_page(im, d, p, page_no, groups):
    logo_header_inner(im, d)
    inner_title(d, "答题逐字稿")  # 两页页签相同，无上/下（TR4.2 起，TR5 沿用）
    page_name = "上" if page_no == 0 else "下"
    zone_bot = SCRIPT_ZONE_BOT if page_no == 0 else SCRIPT_NOTE_Y - 32
    content_top = ZONE_TOP
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
    # TR4.3 用户裁定：两页统一顶对齐（同节奏翻页）；卡 05 字数注记底部固定
    y = content_top
    for k, (g, h) in enumerate(zip(groups, hs)):
        if k:
            _hairline(d, y - SCRIPT_GROUP_GAP // 2 - 1)
        _draw_group(d, g, y, lf, bf)
        y += h + SCRIPT_GROUP_GAP
    if page_no == 1:
        d.text((W // 2, SCRIPT_NOTE_Y), script_badge(p), font=F_MED(24),
               fill=GRAY, anchor="mm")
    # 页脚（发丝线+系列名+页码，全卡保留）；卡 05 字数注记在其上方并存
    footer_note(d, 4 + page_no)
    print(f"[OK] 逐字稿（{page_name}）档位 lead/body = {lf}/{bf}")


def card4_script_a(im, d, p, ctx):
    """逐字稿（上）：页签「答题逐字稿」+ 开场段 + 第一/二步（顶对齐铺满）。"""
    _render_script_page(im, d, p, 0, _script_groups(p)[0])


def card5_script_b(im, d, p, ctx):
    """逐字稿（下）：页签「答题逐字稿」+ 第三步 + 收尾段（顶对齐）
    + 页脚线上方字数小字（全文 N 字 · 约 M 秒）。"""
    _render_script_page(im, d, p, 1, _script_groups(p)[1])


# ------------------------------------------------------------ 卡6 每题金句
def _balanced_lines(d, text, f, max_w):
    """金句两行均衡折行（TR4.4 打磨）：整体折行后若两行失衡（末行 < 首行-2 字），
    自半程向右找首个两行均合法（宽不超限、不犯避头尾）的断点重排；
    只重排不增删字（"".join(lines) == text），找不到/非两行时原样返回。"""
    lines = wrap_text(d, text, f, max_w)
    if len(lines) != 2 or len(lines[1]) >= len(lines[0]) - 2:
        return lines
    n = len(text)
    for cut in range((n + 1) // 2, n):
        a, b = text[:cut], text[cut:]
        if (a and b and tw(d, a, f) <= max_w and tw(d, b, f) <= max_w
                and a[-1] not in NO_LINE_END and b[0] not in NO_LINE_START
                and a + b == text):
            return [a, b]
    return lines


def card6_close(im, d, p, ctx):
    """标题「每题金句」44 枣红＋金 tabline；金句（opening 末句规则不变）52px 墨色
    横排居中于版面中部（无卡无框，两行失衡自动均衡）＋右下枣红方印「答一道」
    呼应封面＋枣红 CTA 条（贴页面下方页脚上方）。"""
    logo_header_inner(im, d)
    inner_title(d, "每题金句")
    golden = opening_golden(p)
    chosen = None
    for gf in GOLDEN_TIERS:
        f_g = F_BOLD(gf)
        ng = n_lines(d, golden, f_g, TX_W)
        h_g = ng * (gf + GOLDEN_LEAD_GAP)
        if h_g + SEAL_SIZE + 56 + CTA_H + 24 <= ZONE_BOT - ZONE_TOP:
            chosen = (gf, f_g, h_g)
            break
    if chosen is None:
        raise CardOverflow("06-每题金句")
    gf, f_g, h_g = chosen
    # 金句横排居中于「标题下～CTA 上」剩余区；方印右对齐随金句下缘
    rest_bot = CTA_Y - 24
    gy = ZONE_TOP + ((rest_bot - ZONE_TOP) - h_g) // 2
    yy = gy
    for ln in _balanced_lines(d, golden, f_g, TX_W):
        d.text((W // 2, yy), ln, font=f_g, fill=INK, anchor="ma")
        yy += gf + GOLDEN_LEAD_GAP
    seal_size = max(110, tw(d, "答一道", F_BOLD(36)) + 28)
    seal_x = W - MARGIN - seal_size
    seal_y = gy + h_g + 56
    d.rectangle([seal_x, seal_y, seal_x + seal_size, seal_y + seal_size],
                fill=CRIMSON)
    d.text((seal_x + seal_size // 2, seal_y + seal_size // 2), "答一道",
           font=F_BOLD(36), fill=CREAM_W, anchor="mm")
    # 枣红 CTA 条（贴页面下方页脚上方；主/副行光学居中）
    rounded(d, [MARGIN, CTA_Y, W - MARGIN, CTA_Y + CTA_H], 36, fill=CRIMSON)
    d.text((W // 2, CTA_Y + 48), CTA_MAIN, font=F_BOLD(44), fill=CREAM_W, anchor="mm")
    d.text((W // 2, CTA_Y + 100), BRAND_SLOGAN, font=F_MED(26), fill=HERO_SUB, anchor="mm")
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
> 视觉：答一道 VI（米白底 #fff8ec · 枣红 #87110f · 金棕 #e3c79f），总分总 logo，C 留白范式
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
    """--check：6 图存在 + logo 区域枣红占比 ≥50%（封面 96px/内页 56px 两套框）。"""
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
        description="结构化每日一练·答一道 6 卡渲染（C 留白范式）")
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

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
SERIES_INTRO = "把考场真实答法，搬进你的答案"   # 封面页眉眉标
COVER_HOOK_DEFAULT = "照这个顺序答，考官以为你干过这岗位"  # 封面价值句（final 无 cover_hook 时固定使用）
FAKE_DEMO = "一方面……另一方面，加强管理"        # 卡6 假大空对照条·固定示范句（不篡改正文）
REAL_DEMO = "先查人、后修电，三本账对得上"      # 卡6 具体做法对照·固定示范句
# 对照条符号：HarmonyOS Sans SC 缺 U+2717/U+2713 字形（textbbox 高 0，渲染为空白），
# 改用同字体有真实字形的 ×/√；渲染前有 require_glyph 断言防再犯。
MARK_NO = "×"
MARK_YES = "√"
CTA_MAIN = "答一道 · 每日一练"                  # 卡6 CTA 主行
CTA_SUB = "先答一道，把最影响得分的地方找出来"  # 卡6 CTA 副行（品牌 slogan）
FOOTER_LEFT = "结构化每日一练 · 答一道"         # 页脚左上（统一）
NOTE_GUIDE = "想要完整逐字稿，评论区打「1」"    # 笔记文案固定引导
NOTE_TAGS = ["#结构化面试", "#公考面试", "#答题思路", "#每日一练", "#上岸"]
WORDMARK = "结构化每日一练"                     # 页眉字标
SPEECH_CPS = 3.5                                # 逐字稿口播速率（字/秒，≈210 字/分钟），徽章估算用
IMG_DIR = "图片输出"
PROGRESS_NAME = "progress_answer.json"
LOGO_BOX = (70, 58, 182, 170)  # 与真图 logo 贴图位置一致（112px）

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

# 内页统一版面：大标 y=296（F_BLACK 72），内容区 380–1330，卡内文字宽 820
TITLE_Y, TITLE_SIZE = 296, 72
ZONE_TOP, ZONE_BOT = 380, 1330
TX_X, TX_W = 130, 820
CARD_PAD = 44  # 大卡内边距（上下）


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
    require_glyph(F_MED(26), MARK_NO)
    require_glyph(F_BOLD(30), MARK_YES)
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


def wrap_text(d, text, f, max_w):
    """按像素折行；每行像素 ≤ max_w；行首不带避头标点（标点连同前一字移入下行）、
    行尾不悬挂开引号括号；末行孤字向上借字。只折行、永不截断（"".join(lines) == 原文）。"""
    lines, cur = [], ""
    for ch in str(text):
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


def logo_header(im, d, badge_text, eyebrow):
    """每张卡顶部：总品牌 logo 图 + 「结构化每日一练」字标 + 眉标 + 右上金徽胶囊。"""
    lg = rounded_logo(112)
    im.paste(lg, (70, 58), lg)
    d.text((206, 74), WORDMARK, font=F_BOLD(52), fill=INK, anchor="la")
    d.text((208, 136), eyebrow, font=F_MED(26), fill=GRAY, anchor="la")
    f_b = F_MED(26)
    bw = tw(d, badge_text, f_b)
    x0, x1 = W - 56 - bw - 48, W - 56
    rounded(d, [x0, 84, x1, 144], 30, fill=GOLD_BG)
    d.text(((x0 + x1) // 2, 114), badge_text, font=f_b, fill=CRIMSON, anchor="mm")


def footer_note(d, idx):
    """统一页脚：左上系列名 + 右上页码 0N/06 + GOLD 细线；无装饰条幅。"""
    d.line([70, 1348, W - 70, 1348], fill=GOLD, width=2)
    d.text((70, 1384), FOOTER_LEFT, font=F_REG(26), fill=GRAY, anchor="lm")
    d.text((W - 70, 1384), f"{idx:02d}/06", font=F_REG(26), fill=GRAY, anchor="rm")


def inner_title(d, text):
    d.text((W // 2, TITLE_Y), text, font=F_BLACK(TITLE_SIZE), fill=INK, anchor="mm")


def script_badge(p):
    """脚本字数徽章：全文 N 字 · M 秒（以字段实测字数为准，秒数十位取整）。"""
    total = sum(len(str(p[k])) for k in SCRIPT_KEYS)
    secs = int(round(total / SPEECH_CPS / 10.0) * 10)
    return f"全文 {total} 字 · {secs} 秒"


def strip_done_mark(s):
    """金句卡取 closing 时去掉口播收尾标记「答题完毕」（只减不增，不篡改正文）。"""
    s = str(s).strip()
    stripped = re.sub(r"答题完毕[。.!！!~]?\s*$", "", s).strip()
    return stripped or s


# ------------------------------------------------------------ 卡1 封面
def card1_cover(im, d, p, ctx):
    """logo 头（眉标=SERIES_INTRO）+ 系列名 96 墨 + 主题大字 132 枣红（超宽缩）
    + 金短线 + 价值句 Bold 44 枣红 + 页脚。"""
    logo_header(im, d, f"第{ctx['issue']}期", eyebrow=SERIES_INTRO)
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
    hook = str(p.get("cover_hook") or "").strip() or COVER_HOOK_DEFAULT
    s_h = fit_title(d, hook, 44, 28, 900)
    d.text((W // 2, y_div + 112), hook, font=F_BOLD(s_h), fill=CRIMSON, anchor="mm")
    footer_note(d, 1)


# ------------------------------------------------------------ 卡2 题目
def card2_question(im, d, p, ctx):
    """大标「题目」+ 题干白卡（Medium 44→34 自适应、≤6 行倾向）+ 来源徽章（页眉）。"""
    logo_header(im, d, ctx["source_badge"], eyebrow=ctx["eyebrow"])
    inner_title(d, "题目")
    zone = ZONE_BOT - ZONE_TOP
    tiers = [44, 42, 40, 38, 36, 34, 32, 30]  # 34–44 为主档，32/30 为超高应急降档
    chosen = None
    for allow_long in (True, False):  # 先找 ≤6 行档，找不到再放宽行数
        for qf in tiers:
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
    y0 = ZONE_TOP + (zone - card_h) // 2
    shadow_card(im, d, [80, y0, 1000, y0 + card_h], 40)
    draw_wrapped(d, (TX_X, y0 + (card_h - content_h) // 2), p["question"],
                 f_q, INK, TX_W, line_gap=18)
    footer_note(d, 2)


# ------------------------------------------------------------ 卡3 答题思路
def card3_outline(im, d, p, ctx):
    """大标「答题思路」+ 破题角度（枣红 Bold）+ 切入理由 + 核心观点标题 + 导语
    + 3 条编号观点（枣红数字方块）。档位自动降，仍超高 FAIL。"""
    logo_header(im, d, f"第{ctx['issue']}期", eyebrow=ctx["eyebrow"])
    inner_title(d, "答题思路")
    zone = ZONE_BOT - ZONE_TOP
    tiers = [(36, 29, 34, 28, 28), (34, 27, 32, 26, 26), (32, 25, 30, 25, 25),
             (30, 23, 28, 24, 24), (28, 22, 26, 22, 22)]
    chosen = None
    for af, rf, vf, inf, vw in tiers:
        la = n_lines(d, p["break_angle"], F_BOLD(af), TX_W)
        lr = n_lines(d, p["break_angle_reason"], F_MED(rf), TX_W)
        lv = n_lines(d, p["core_views_title"], F_BOLD(vf), TX_W)
        li = n_lines(d, p["core_views_intro"], F_MED(inf), TX_W)
        sq = int(vw * 1.9)
        vs = [n_lines(d, v, F_MED(vw), TX_W - sq - 22) for v in p["core_views"]]
        h = (la * (af + 12) + 8 + lr * (rf + 9) + 34
             + lv * (vf + 14) + 8 + li * (inf + 8) + 14
             + sum(max(sq, n * (vw + 8)) + 20 for n in vs))
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
    sq = int(vw * 1.9)
    for i, (v, n) in enumerate(zip(p["core_views"], vs), start=1):
        rounded(d, [TX_X, y, TX_X + sq, y + sq], 14, fill=CRIMSON)
        d.text((TX_X + sq // 2, y + sq // 2), str(i), font=F_BOLD(int(sq * 0.58)),
               fill=CREAM_W, anchor="mm")
        draw_wrapped(d, (TX_X + sq + 22, y + 2), v, f_v, INK,
                     TX_W - sq - 22, line_gap=8)
        y += max(sq, n * (vw + 8)) + 20
    footer_note(d, 3)


# ------------------------------------------------- 卡4/5 逐字稿（上/下）
def _measure_script_card(d, lead, body, lf, bf):
    f_b = F_MED(bf)
    return (lf + 14 + n_lines(d, body, f_b, TX_W) * (bf + 9) + 76
            if lead is not None else
            n_lines(d, body, F_BOLD(lf), TX_W) * (lf + 10) + 64)


def _draw_script_card(im, d, y, h, lead, body, lf, bf, body_fill=GRAY):
    shadow_card(im, d, [80, y, 1000, y + h], 32)
    if lead is not None:
        d.text((TX_X, y + 38), lead, font=F_BOLD(lf), fill=INK, anchor="la")
        draw_wrapped(d, (TX_X, y + 38 + lf + 14), body, F_MED(bf), body_fill,
                     TX_W, line_gap=9)
    else:
        draw_wrapped(d, (TX_X, y + 32), body, F_BOLD(lf), INK, TX_W, line_gap=10)


def card4_script_a(im, d, p, ctx):
    """大标「答题逐字稿（上）」+ opening + point1（lead Bold / body 折行）
    + 页眉脚本字数徽章（全文 N 字 · M 秒，实测字数）。"""
    logo_header(im, d, ctx["script_badge"], eyebrow=ctx["eyebrow"])
    inner_title(d, "答题逐字稿（上）")
    zone = ZONE_BOT - ZONE_TOP
    tiers = [(34, 28), (32, 26), (30, 25), (28, 23), (26, 21)]
    chosen = None
    for lf, bf in tiers:
        h_o = _measure_script_card(d, None, p["opening"], bf, bf)
        h_p = _measure_script_card(d, p["point1_lead"], p["point1_body"], lf, bf)
        if h_o + h_p + 20 <= zone:
            chosen = (lf, bf, h_o, h_p)
            break
    if chosen is None:
        raise CardOverflow("04-逐字稿（上）")
    lf, bf, h_o, h_p = chosen
    y = ZONE_TOP + (zone - h_o - h_p - 20) // 2
    _draw_script_card(im, d, y, h_o, None, p["opening"], bf, bf, body_fill=INK)
    _draw_script_card(im, d, y + h_o + 20, h_p, p["point1_lead"],
                      p["point1_body"], lf, bf)
    footer_note(d, 4)


def card5_script_b(im, d, p, ctx):
    """大标「答题逐字稿（下）」+ point2 + point3 + closing（判据式/总结式都收）
    + 「答题完毕」页脚角标。"""
    logo_header(im, d, f"第{ctx['issue']}期", eyebrow=ctx["eyebrow"])
    inner_title(d, "答题逐字稿（下）")
    zone = ZONE_BOT - ZONE_TOP
    tiers = [(34, 28, 28), (32, 26, 27), (30, 25, 26), (28, 24, 25), (26, 22, 23)]
    chosen = None
    for lf, bf, cf in tiers:
        h2 = _measure_script_card(d, p["point2_lead"], p["point2_body"], lf, bf)
        h3 = _measure_script_card(d, p["point3_lead"], p["point3_body"], lf, bf)
        hc = _measure_script_card(d, None, p["closing"], cf, cf)  # lead=None 与绘制分支一致
        if h2 + h3 + hc + 2 * 18 <= zone:
            chosen = (lf, bf, cf, h2, h3, hc)
            break
    if chosen is None:
        raise CardOverflow("05-逐字稿（下）")
    lf, bf, cf, h2, h3, hc = chosen
    y = ZONE_TOP + (zone - h2 - h3 - hc - 2 * 18) // 2
    _draw_script_card(im, d, y, h2, p["point2_lead"], p["point2_body"], lf, bf)
    _draw_script_card(im, d, y + h2 + 18, h3, p["point3_lead"],
                      p["point3_body"], lf, bf)
    _draw_script_card(im, d, y + h2 + h3 + 2 * 18, hc, None, p["closing"], cf, cf)
    footer_note(d, 5)


# ------------------------------------------------------------ 卡6 收尾引流
def card6_close(im, d, p, ctx):
    """大标「背下来 · 开口就用」+ 金句卡（closing 或 dedicated 句）
    + 米杏假大空对照条（固定示范句）+ 枣红 CTA 条。"""
    logo_header(im, d, f"第{ctx['issue']}期", eyebrow=SERIES_INTRO)
    inner_title(d, "背下来 · 开口就用")
    zone = ZONE_BOT - ZONE_TOP
    golden = str(p.get("golden_line") or "").strip() or strip_done_mark(p["closing"])
    f_fake, f_real = F_MED(26), F_BOLD(30)
    require_glyph(f_fake, MARK_NO)
    require_glyph(f_real, MARK_YES)
    nf = n_lines(d, MARK_NO + " " + FAKE_DEMO, f_fake, 840)
    nr = n_lines(d, MARK_YES + " " + REAL_DEMO, f_real, 840)
    h_c = 26 + nf * 38 + 12 + nr * 42 + 26
    cta_h = 140
    chosen = None
    for gf in (44, 40, 36, 32, 28):
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
    d.text((W // 2, y + 106), CTA_SUB, font=F_MED(26), fill=HERO_SUB, anchor="mm")
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
    """--check：6 图存在 + logo 区域枣红占比 ≥50%（真图实测约 93%）。"""
    ok = True
    for name in CARD_FILES:
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
        raw = im.crop(LOGO_BOX).tobytes()  # RGB，3 字节/像素
        n = len(raw) // 3
        crim = 0
        for i in range(0, len(raw), 3):
            if (max(abs(raw[i] - CRIMSON[0]), abs(raw[i + 1] - CRIMSON[1]),
                    abs(raw[i + 2] - CRIMSON[2])) < 60):
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
        "eyebrow": f"{args.type} · {args.topic}",
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

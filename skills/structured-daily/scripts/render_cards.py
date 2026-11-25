#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_cards.py — 「总分总」双模式图片渲染引擎（v4.0，旧版 VI 复刻）

两种模式，共用同一套视觉资产：
  --mode tips    考官视角 / 展开说说：封面 → 万能展开法总述 → N 档递进 → 避坑 → 品牌页
  --mode answer  答一道 / 每日一练：封面 → 思维导图 → 逐字稿（自动分页）→ 收尾引流 → 品牌页

画布 1080×1440，PIL 直出。视觉契约以 references/DESIGN.md 为唯一事实源。
字体：Songti SC（宋体，Black/Bold/Regular）+ SourceHanSansSC-Bold（页脚）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------- 画布与色板 ----------------
W, H = 1080, 1440
MARGIN_L, MARGIN_R = 96, 96
CONTENT_TOP, CONTENT_BOTTOM = 196, 1290
FOOTER_H = 108
FOOTER_TOP = H - FOOTER_H

RED = (134, 18, 16)          # #861210 品牌红
CREAM = (227, 199, 158)      # #E3C79E 米金
INK = (26, 26, 26)           # 正文墨
NAVY = (11, 47, 64)          # #0B2F40 页脚/小标题
MUTED = (106, 100, 94)
WATERMARK = (246, 243, 238)
HAIRLINE = (214, 198, 174)
WHITE = (255, 255, 255)

BRANCH_COLORS = [
    (46, 111, 158),   # 蓝
    (62, 142, 90),    # 绿
    (208, 138, 44),   # 橙
    (176, 74, 62),    # 砖红
    (122, 90, 166),   # 紫
]

FONT_DIR = Path.home() / "Library/Fonts"
SONGTI_TTC = "/System/Library/Fonts/Supplemental/Songti.ttc"
SONG_INDEX = {"black": 0, "bold": 1, "regular": 6, "light": 3}
SANS_FILES = {
    "bold": FONT_DIR / "SourceHanSansSC-Bold.otf",
    "medium": FONT_DIR / "SourceHanSansSC-Medium.otf",
    "regular": FONT_DIR / "SourceHanSansSC-Regular.otf",
}
LOGO_CANDIDATES = [
    Path.home() / "Desktop/AI工作区/01-Projects/公考橙皮书/assets/logo-zfz.png",
]

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    """kind: black|bold|regular|light|sans_bold|sans_med|sans_reg"""
    key = (kind, size)
    if key in _font_cache:
        return _font_cache[key]
    if kind.startswith("sans"):
        alias = {"med": "medium", "reg": "regular"}.get(kind[5:], kind[5:])
        f = ImageFont.truetype(str(SANS_FILES[alias]), size)
    else:
        f = ImageFont.truetype(SONGTI_TTC, size, index=SONG_INDEX[kind])
    _font_cache[key] = f
    return f


def logo_image(size: int) -> Image.Image | None:
    """返回圆形裁切的品牌 logo；资产缺失返回 None（调用方画圆形替代）。"""
    for p in LOGO_CANDIDATES:
        if p.exists():
            src = Image.open(p).convert("RGBA").resize((size, size), Image.LANCZOS)
            mask = Image.new("L", (size * 4, size * 4), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
            mask = mask.resize((size, size), Image.LANCZOS)
            src.putalpha(mask)
            return src
    return None


# ---------------- 折行（中文避头尾 + ASCII 原子） ----------------
NO_LINE_START = set("，。！？；：、）》」』】…·%,.!?;:'\")]}")
NO_LINE_END = set("（《「『【([{")


def _tokens(text: str) -> list[str]:
    """CJK 逐字，ASCII 连续串（含数字/百分号/小数点/连字符）作为原子。"""
    out, buf = [], ""
    for ch in text:
        if ch.isascii() and (ch.isalnum() or ch in "._%+-/:@#&*'\"()[]{}<>="):
            buf += ch
        else:
            if buf:
                out.append(buf)
                buf = ""
            out.append(ch)
    if buf:
        out.append(buf)
    return out


# 折行（中文避头尾 + ASCII 原子）：见 wrap_text


def wrap_text(segments: list[tuple[str, str]], sizes: dict[str, int], max_w: int):
    """精确折行：按每段的实际字号测量。"""
    lines: list[list[tuple[str, str]]] = [[]]
    cur_w = 0
    for text, kind in segments:
        size = sizes[kind]
        f = font(kind, size)
        for tok in _tokens(text):
            w = f.getlength(tok)
            if lines[-1] and tok and tok[0] in NO_LINE_START:
                lines[-1].append((tok, kind))
                cur_w += w
                continue
            if cur_w + w > max_w and lines[-1]:
                if lines[-1][-1][0][-1] in NO_LINE_END:
                    moved = lines[-1].pop()
                    lines.append([moved])
                    cur_w = font(moved[1], sizes[moved[1]]).getlength(moved[0]) + w
                else:
                    lines.append([])
                    cur_w = 0
            lines[-1].append((tok, kind))
            cur_w += w
    return lines


def draw_lines(draw: ImageDraw.ImageDraw, xy, lines, sizes: dict[str, int],
               line_h: int, color, first_indent: int = 0, rest_indent: int = 0):
    x0, y = xy
    for i, line in enumerate(lines):
        x = x0 + (first_indent if i == 0 else rest_indent)
        for text, kind in line:
            draw.text((x, y), text, font=font(kind, sizes[kind]), fill=color, anchor="la")
            x += font(kind, sizes[kind]).getlength(text)
        y += line_h
    return y


def text_height(n_lines: int, line_h: int) -> int:
    return n_lines * line_h


# ---------------- 页面骨架 ----------------
class Page:
    def __init__(self, kind: str = "content"):
        self.img = Image.new("RGB", (W, H), WHITE if kind != "brand" else CREAM)
        self.d = ImageDraw.Draw(self.img)
        self.kind = kind
        if kind == "content":
            self._watermark()
            self._header()
            self._footer()

    def _watermark(self):
        f = font("black", 196)
        for i, ch in enumerate("总分总"):
            w = f.getlength(ch)
            self.d.text(((W - w) / 2 + 160, 260 + i * 220), ch, font=f,
                        fill=WATERMARK, anchor="la")

    def _header(self):
        logo = logo_image(64)
        if logo:
            self.img.paste(logo, (MARGIN_L - 8, 46), logo)
        else:
            self.d.ellipse((MARGIN_L, 52, MARGIN_L + 60, 112), fill=RED)
        self.d.text((MARGIN_L + 80, 78), "深耕结构化面试，善用总分总章法",
                    font=font("sans_bold", 22), fill=RED, anchor="lm")

    def _footer(self):
        self.d.rectangle((0, FOOTER_TOP, W, H), fill=CREAM)
        self.d.text((MARGIN_L, FOOTER_TOP + FOOTER_H / 2), "有逻辑 · 有观点 · 有表达",
                    font=font("sans_bold", 30), fill=NAVY, anchor="lm")
        # 右下角红方块 + 竖排 logo
        self.d.rectangle((W - 108, FOOTER_TOP, W, H), fill=RED)
        f = font("sans_bold", 20)
        y = FOOTER_TOP + 18
        for ch in "总分总":
            self.d.text((W - 54, y), ch, font=f, fill=WHITE, anchor="ma")
            y += 25


def cover(title_lines: list[str], kicker: str | None = None,
          footer_note: str = "深耕结构化面试，善用总分总章法",
          title_size: int = 84, start_y: int = 360, line_h: int | None = None,
          indent_first: bool = False, kicker_size: int = 54, indent_all: bool = False):
    img = Image.new("RGB", (W, H), RED)
    d = ImageDraw.Draw(img)
    if kicker:
        d.text((MARGIN_L, 104), kicker, font=font("bold", kicker_size), fill=CREAM, anchor="la")
    line_h = line_h or int(title_size * 1.4)
    y = start_y
    sizes = {"black": title_size}
    max_w = W - MARGIN_L - MARGIN_R
    for line in title_lines:
        if not str(line).strip():
            continue
        lines = wrap_text([(line, "black")], sizes, max_w - (FIRST_INDENT if indent_first else 0))
        y = draw_lines(d, (MARGIN_L, y), lines, sizes, line_h, CREAM,
                       first_indent=(BODY_SIZE * 2 if (indent_first or indent_all) else 0),
                       rest_indent=(BODY_SIZE * 2 if indent_all else 0))
        y += 10
    # 左滑提示（文字 + 下划线 + 小箭头）
    hint = "左滑开始进步"
    fh = font("regular", 34)
    tw = fh.getlength(hint)
    x0 = W - MARGIN_R - tw
    y0 = 1152
    d.text((x0, y0), hint, font=fh, fill=CREAM, anchor="la")
    ly = y0 + 48
    d.line((x0, ly, W - MARGIN_R - 12, ly), fill=CREAM, width=3)
    d.polygon([(W - MARGIN_R - 12, ly - 9), (W - MARGIN_R - 12, ly + 9),
               (W - MARGIN_R + 6, ly)], fill=CREAM)
    # 底部标语
    d.ellipse((MARGIN_L + 2, 1246, MARGIN_L + 20, 1264), fill=CREAM)
    d.text((MARGIN_L + 36, 1240), footer_note, font=font("regular", 28), fill=CREAM, anchor="lm")
    # 页脚带
    d.rectangle((0, FOOTER_TOP, W, H), fill=CREAM)
    d.text((MARGIN_L, FOOTER_TOP + FOOTER_H / 2), "有逻辑 · 有观点 · 有表达",
           font=font("sans_bold", 30), fill=NAVY, anchor="lm")
    d.rectangle((W - 108, FOOTER_TOP, W, H), fill=RED)
    f2 = font("sans_bold", 20)
    yy = FOOTER_TOP + 18
    for ch in "总分总":
        d.text((W - 54, yy), ch, font=f2, fill=WHITE, anchor="ma")
        yy += 25
    return img


def brand_page():
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    f = font("black", 120)
    y = 250
    for ch in "总分总":
        d.text((W / 2, y), ch, font=f, fill=RED, anchor="ma")
        y += 150
    d.text((W / 2, 720), "有逻辑 | 有观点 | 有表达", font=font("bold", 40), fill=RED, anchor="ma")
    slogans = ["深耕结构化面试", "善用总分总章法", "掌握方法多练习", "结构化面试不着急"]
    y = 790
    for s in slogans:
        d.text((W / 2, y), s, font=font("regular", 36), fill=RED, anchor="ma")
        y += 62
    d.rectangle((0, H - 80, W, H), fill=RED)
    f2 = font("sans_bold", 18)
    yy = H - 72
    for ch in "总分总":
        d.text((W / 2, yy), ch, font=f2, fill=WHITE, anchor="ma")
        yy += 24
    d.text((W - 40, H - 30), "找到我", font=font("sans_med", 14), fill=CREAM, anchor="ra")
    return img


# ---------------- 思维导图 ----------------
def _cubic(d, p1, p2, color, width=3, steps=26):
    """三次贝塞尔：控制点取水平中点，保证树线平滑。"""
    mx = (p1[0] + p2[0]) / 2
    c1, c2 = (mx, p1[1]), (mx, p2[1])
    pts = []
    for i in range(steps + 1):
        t = i / steps
        x = (1 - t) ** 3 * p1[0] + 3 * (1 - t) ** 2 * t * c1[0] + 3 * (1 - t) * t ** 2 * c2[0] + t ** 3 * p2[0]
        y = (1 - t) ** 3 * p1[1] + 3 * (1 - t) ** 2 * t * c1[1] + 3 * (1 - t) * t ** 2 * c2[1] + t ** 3 * p2[1]
        pts.append((x, y))
    d.line(pts, fill=color, width=width, joint="curve")


def mindmap_page(tree: dict) -> Image:
    page = Page("content")
    root = tree.get("root", "核心观点")
    branches = tree.get("branches", [])
    if not branches:
        raise ValueError("mindmap.branches 为空")

    X = [292, 592, 800]
    TW = [230, 280, 160]
    GAP_V, GAP_B = 6, 16
    sizes_h = {1: (24, 30), 2: (20, 24), 3: (20, 24)}  # depth → (字号, 行高)

    def own_h(node, depth):
        size, lh = sizes_h[min(depth, 3)]
        lines = wrap_text([(node["label"], "bold" if depth <= 1 else "regular")],
                          {"bold": size, "regular": size}, TW[min(depth - 1, 2)])
        return len(lines) * lh

    def calc_h(node, depth):
        kids = node.get("children", [])
        h_own = own_h(node, depth)
        kids_h = sum(calc_h(k, depth + 1) for k in kids) + GAP_V * (len(kids) - 1) if kids else 0
        node["_h"] = h_own + (GAP_B / 2 + kids_h if kids else 0)
        return node["_h"]

    total = sum(calc_h(b, 1) for b in branches) + GAP_B * (len(branches) - 1)
    avail = CONTENT_BOTTOM - CONTENT_TOP - 10
    if total > avail:
        raise ValueError(f"思维导图超出单页（{total}px > {avail}px），请减少分支层级/叶子")

    top = CONTENT_TOP + (avail - total) // 2
    d = page.d

    def draw_own(node, depth, y, color):
        size, lh = sizes_h[min(depth, 3)]
        kind = "bold" if depth <= 1 else "regular"
        lines = wrap_text([(node["label"], kind)], {kind: size}, TW[min(depth - 1, 2)])
        h = len(lines) * lh
        cx = X[min(depth - 1, 2)]
        draw_lines(d, (cx, y), lines, {kind: size}, lh, color)
        cy = y + h // 2
        d.ellipse((cx - 28, cy - 5, cx - 18, cy + 5), fill=color)
        return cy, cx, h

    def place(node, depth, y, color):
        cy, cx, h_own = draw_own(node, depth, y, color)
        kids = node.get("children", [])
        if kids:
            child_y = y + h_own + GAP_B / 2
            bus_x = cx - 24
            for k in kids:
                ccy, ccx, _ = place(k, depth + 1, child_y, color)
                _cubic(d, (bus_x, y + h_own + 6), (ccx - 24, ccy), color)
                child_y += k["_h"] + GAP_V
            # 标签圆点 → 子节点总线起点（走文字左侧）
            d.line((cx - 23, cy, bus_x, y + h_own + 6), fill=color, width=3)
        return cy, cx, h_own

    root_y = top + total // 2
    root_x0 = 120
    root_w = font("bold", 28).getlength(root)
    d.text((root_x0, root_y), root, font=font("bold", 28), fill=INK, anchor="lm")
    d.ellipse((root_x0 - 16, root_y - 7, root_x0 - 4, root_y + 7), fill=INK)
    y = top
    for i, b in enumerate(branches):
        color = BRANCH_COLORS[i % len(BRANCH_COLORS)]
        cy, cx, _ = place(b, 1, y, color)
        _cubic(d, (root_x0 + root_w + 12, root_y), (cx - 23, cy), color)
        y += b["_h"] + GAP_B
    return page.img


# ---------------- 内容排版（自动分页） ----------------
BODY_SIZE = 32
BODY_LINE = 54
FIRST_INDENT = BODY_SIZE * 2


class Flow:
    """顺序排版器：段落超高自动新页。"""

    def __init__(self):
        self.pages: list[Page] = []
        self.page = Page("content")
        self.y = CONTENT_TOP

    def new_page(self):
        self.pages.append(self.page)
        self.page = Page("content")
        self.y = CONTENT_TOP

    def ensure(self, h: int):
        if self.y + h > CONTENT_BOTTOM:
            self.new_page()

    def paragraph(self, segments, sizes=None, line_h=BODY_LINE, color=INK,
                  space_before=0, indent=True, align="left"):
        sizes = sizes or {"regular": BODY_SIZE}
        wrap_w = W - MARGIN_L - MARGIN_R - (FIRST_INDENT if indent else 0)
        lines = wrap_text(segments, sizes, wrap_w)
        if space_before:
            self.y += space_before
        i = 0
        while i < len(lines):
            fit = int((CONTENT_BOTTOM - self.y) // line_h)
            if fit <= 0:
                self.new_page()
                continue
            chunk = lines[i:i + fit]
            self.y = draw_lines(self.page.d, (MARGIN_L, self.y), chunk, sizes, line_h,
                                color, FIRST_INDENT if (indent and i == 0) else 0)
            i += fit
            if i < len(lines):
                self.new_page()
        return len(lines) * line_h

    def heading(self, text: str, size=44, color=RED, kind="black", space_before=0,
                space_after=16, line_h=None, keep_with_next=False):
        line_h = line_h or int(size * 1.45)
        sizes = {kind: size}
        lines = wrap_text([(text, kind)], sizes, W - MARGIN_L - MARGIN_R)
        h = len(lines) * line_h
        if space_before:
            self.y += space_before
        reserve = h + space_after + (BODY_LINE if keep_with_next else 0)
        if self.y + reserve > CONTENT_BOTTOM:
            self.new_page()
        draw_lines(self.page.d, (MARGIN_L, self.y), lines, sizes, line_h, color)
        self.y += h + space_after

    def numbered_point(self, idx: int, lead: str, body: str, space_before=22):
        lead_seg = [(f"{idx}. ", "bold"), (lead, "bold")]
        body_seg = [("：", "regular"), (body, "regular")] if body else []
        segments = lead_seg + body_seg
        sizes = {"bold": BODY_SIZE, "regular": BODY_SIZE}
        lines = wrap_text(segments, sizes, W - MARGIN_L - MARGIN_R - 62)
        self.y += space_before
        i = 0
        while i < len(lines):
            fit = int((CONTENT_BOTTOM - self.y) // BODY_LINE)
            if fit <= 0:
                self.new_page()
                continue
            for line in lines[i:i + fit]:
                xx = MARGIN_L if i == 0 else MARGIN_L + 62
                for text, kind in line:
                    self.page.d.text((xx, self.y), text, font=font(kind, BODY_SIZE),
                                     fill=INK, anchor="la")
                    xx += font(kind, BODY_SIZE).getlength(text)
                self.y += BODY_LINE
                i += 1
            if i < len(lines):
                self.new_page()
        return len(lines) * BODY_LINE

    def rule(self, space_before=34, space_after=26):
        self.y += space_before
        if self.y + 4 > CONTENT_BOTTOM:
            self.new_page()
        self.page.d.rectangle((MARGIN_L, self.y, W - MARGIN_R, self.y + 3), fill=HAIRLINE)
        self.y += space_after

    def finish(self) -> list[Image.Image]:
        self.pages.append(self.page)
        return [p.img for p in self.pages]


def quote_block(flow: Flow, text: str, size=30):
    """左侧竖线引用块（总述/导语）。"""
    sizes = {"regular": size}
    lines = wrap_text([(text, "regular")], sizes, W - MARGIN_L - MARGIN_R - 60)
    h = len(lines) * int(size * 1.6)
    flow.ensure(h + 34)
    y0 = flow.y + 8
    flow.page.d.rectangle((MARGIN_L, y0, MARGIN_L + 5, y0 + h - 6), fill=(198, 186, 170))
    draw_lines(flow.page.d, (MARGIN_L + 34, y0), lines, sizes, int(size * 1.6), (78, 74, 70))
    flow.y = y0 + h + 26


# ---------------- 数据校验 ----------------
ANSWER_REQUIRED = ["question", "break_angle", "break_angle_reason", "core_views_title",
                   "core_views_intro", "opening", "point1_lead", "point1_body",
                   "point2_lead", "point2_body", "point3_lead", "point3_body", "closing"]
TIPS_REQUIRED = ["cover_title", "overview_title", "overview_intro", "tiers"]


def validate(data: dict, mode: str) -> list[str]:
    errs = []
    if mode == "answer":
        for k in ANSWER_REQUIRED:
            if not str(data.get(k, "")).strip():
                errs.append(f"缺字段: {k}")
        cv = data.get("core_views")
        if not (isinstance(cv, list) and len(cv) == 3 and all(str(x).strip() for x in cv)):
            errs.append("core_views 必须是 3 条非空字符串")
        mm = data.get("mindmap")
        if mm is not None:
            if not isinstance(mm, dict) or not isinstance(mm.get("branches"), list) or not mm["branches"]:
                errs.append("mindmap 需为 {root, branches:[...]}")
        src = str(data.get("source", ""))
        prefix = str(data.get("title_prefix", "结构化每日一练："))
        if "真题" in src and "历年考题" not in prefix:
            errs.append("真题库来源必须使用 title_prefix「结构化历年考题：」")
    else:
        for k in TIPS_REQUIRED:
            if not data.get(k):
                errs.append(f"缺字段: {k}")
        tiers = data.get("tiers") or []
        if len(tiers) < 2:
            errs.append("tiers 至少 2 档")
        for i, t in enumerate(tiers):
            if not t.get("title") or not t.get("points"):
                errs.append(f"tiers[{i}] 缺 title/points")
            for j, pt in enumerate(t.get("points") or []):
                if not str(pt.get("lead", "")).strip():
                    errs.append(f"tiers[{i}].points[{j}] 缺 lead")
    return errs


# ---------------- 两种模式 ----------------
def render_tips(data: dict) -> list[Image.Image]:
    imgs = []
    imgs.append(cover([data["cover_title"], data.get("cover_line2", "")],
                      kicker=data.get("kicker"), title_size=84, start_y=360, line_h=118))
    flow = Flow()
    flow.heading(data["overview_title"], size=42, color=RED, kind="black", space_before=0, keep_with_next=True)
    quote_block(flow, data["overview_intro"], size=30)
    for tier in data["tiers"]:
        flow.heading(tier["title"], size=38, color=(23, 72, 92), kind="bold", space_before=22, space_after=12, keep_with_next=True)
        if tier.get("intro"):
            flow.paragraph([(tier["intro"], "regular")], space_before=6, indent=False)
            flow.y += 6
        for i, pt in enumerate(tier["points"], 1):
            flow.numbered_point(i, pt["lead"], pt.get("body", ""), space_before=20)
    if data.get("takeaway"):
        tk = data["takeaway"]
        flow.heading(tk.get("title", "避坑提醒"), size=36, color=RED, kind="bold", space_before=30, keep_with_next=True)
        flow.paragraph([(tk.get("body", ""), "regular")], space_before=4)
    if data.get("practice"):
        flow.heading(data.get("practice_title", "练习"), size=36, color=RED, kind="bold", space_before=30, keep_with_next=True)
        flow.paragraph([(data["practice"], "regular")], space_before=4)
    if data.get("cta"):
        flow.rule()
        sizes = {"bold": 28}
        lines = wrap_text([(data["cta"], "bold")], sizes, W - MARGIN_L - MARGIN_R)
        h = len(lines) * 44
        flow.ensure(h)
        draw_lines(flow.page.d, (MARGIN_L, flow.y), lines, sizes, 44, RED)
        flow.y += h
    imgs += flow.finish()
    imgs.append(brand_page())
    return imgs


def render_answer(data: dict) -> list[Image.Image]:
    first = cover([data["question"]], kicker=str(data.get("title_prefix", "结构化每日一练：")),
                  title_size=64, start_y=230, line_h=100, indent_first=True, indent_all=True)
    if data.get("cover_meta"):
        d = ImageDraw.Draw(first)
        d.text((MARGIN_L, 1210), str(data["cover_meta"]), font=font("regular", 26),
               fill=(238, 220, 192), anchor="la")
    imgs = [first]
    if data.get("mindmap"):
        imgs.append(mindmap_page(data["mindmap"]))
    else:
        # 无导图时退化为「核心观点」页
        flow = Flow()
        flow.heading(data.get("core_views_title", "核心观点"), size=44)
        flow.paragraph([(data.get("core_views_intro", ""), "regular")], space_before=6)
        for i, cv in enumerate(data.get("core_views", []), 1):
            flow.numbered_point(i, "", cv, space_before=22)
        imgs += flow.finish()

    flow = Flow()
    flow.paragraph([(data["opening"], "regular")], space_before=0)
    for i in (1, 2, 3):
        flow.paragraph([(data[f"point{i}_lead"], "regular")], space_before=26, indent=False)
        flow.paragraph([(data[f"point{i}_body"], "regular")], space_before=6, indent=False)
    flow.paragraph([(data["closing"], "regular")], space_before=26)
    if data.get("cta"):
        flow.rule()
        sizes = {"bold": 26}
        lines = wrap_text([(data["cta"], "bold")], sizes, W - MARGIN_L - MARGIN_R)
        draw_lines(flow.page.d, (MARGIN_L, flow.y), lines, sizes, 42, RED)
        flow.y += len(lines) * 42
    imgs += flow.finish()
    imgs.append(brand_page())
    return imgs


# ---------------- 版面自检 ----------------
def verify_layout(imgs: list[Image.Image]) -> list[str]:
    """内容页（排除封面/品牌页）墨迹必须落在 96/96 版心内，且不得压入页脚间隙。"""
    problems = []
    n = len(imgs)
    for idx, img in enumerate(imgs, 1):
        if idx == 1 or idx == n:
            continue
        gray = img.convert("L")
        mask = gray.crop((0, CONTENT_TOP, W, CONTENT_BOTTOM)).point(
            lambda v: 255 if v < 200 else 0)
        box = mask.getbbox()
        if box:
            left, right = box[0], box[2] - 1
            if left < MARGIN_L - 2:
                problems.append(f"第{idx}页左缘 {left} 越界（版心 {MARGIN_L}）")
            if right > W - MARGIN_R:
                problems.append(f"第{idx}页右缘 {right} 超版心 {W - MARGIN_R}")
        gap = gray.crop((0, CONTENT_BOTTOM + 2, W, FOOTER_TOP)).point(
            lambda v: 255 if v < 200 else 0)
        if gap.getbbox():
            problems.append(f"第{idx}页内容压入页脚间隙")
    return problems


# ---------------- CLI ----------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="总分总双模式出图（考官视角 / 答一道）")
    ap.add_argument("--mode", choices=["tips", "answer"], required=True)
    ap.add_argument("--final", required=True, help="final JSON")
    ap.add_argument("--outdir", required=True, help="输出目录")
    ap.add_argument("--project-root", help="项目根（提供时校验 outdir 位于 图片输出/ 内，并写期号进度）")
    ap.add_argument("--note", help="笔记文案.md 内容文件（可选）")
    ap.add_argument("--period-id", help="答一道期号 ID（渲染成功后追加到 progress_answer.json）")
    ap.add_argument("--check", action="store_true", help="只校验 JSON，不出图")
    args = ap.parse_args(argv)

    data = json.loads(Path(args.final).read_text(encoding="utf-8"))
    errs = validate(data, args.mode)
    if errs:
        for e in errs:
            print(f"[FAIL] {e}", file=sys.stderr)
        return 1
    if args.check:
        print("[OK] 校验通过")
        return 0

    outdir = Path(args.outdir)
    if args.project_root:
        root = Path(args.project_root)
        allowed = root / "图片输出"
        try:
            outdir.resolve().relative_to(allowed.resolve())
        except ValueError:
            print(f"[FAIL] outdir 不在 {allowed} 内：{outdir}", file=sys.stderr)
            return 1
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("*.png"):
        old.unlink()

    imgs = render_tips(data) if args.mode == "tips" else render_answer(data)
    problems = verify_layout(imgs)
    if problems:
        for p in problems:
            print(f"[FAIL] {p}", file=sys.stderr)
        return 1
    content_n = len(imgs) - 2
    names = ["01-封面"]
    first = "02-万能展开法" if args.mode == "tips" else (
        "02-思维导图" if data.get("mindmap") else "02-答题思路")
    names.append(first)
    tail = "内页" if args.mode == "tips" else "逐字稿"
    for idx in range(1, content_n):
        names.append(f"{idx + 2:02d}-{tail}")
    names.append(f"{len(imgs):02d}-品牌页")
    for i, img in enumerate(imgs, 1):
        path = outdir / f"{names[i-1]}.png"
        if img.size != (W, H):
            print(f"[FAIL] 第 {i} 张尺寸异常：{img.size}", file=sys.stderr)
            return 1
        img.save(path, "PNG")
    if args.note and Path(args.note).exists():
        (outdir / "笔记文案.md").write_text(Path(args.note).read_text(encoding="utf-8"), encoding="utf-8")
    if args.period_id and args.mode == "answer" and args.project_root:
        pf = Path(args.project_root) / "图片输出" / "progress_answer.json"
        data_p = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {"done": []}
        done = data_p.setdefault("done", [])
        if args.period_id not in done:
            done.append(args.period_id)
            pf.write_text(json.dumps(data_p, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] 已渲染 {len(imgs)} 张 → {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公务员务实·岗位业务小红书 6 卡渲染引擎（答一道 VI，简洁风）。

用法:
  python3 gen_wushi_cards.py --pending pending_wushi.json [--outdir <期目录>]
  python3 gen_wushi_cards.py --check --outdir <期目录>   # 复核已生成 6 图的 logo 区域像素

行为约定:
  - 渲染 6 张 1080×1440 PNG + 笔记文案.md；
  - 渲染完自动跑内置 logo 像素校验；
  - 全部成功才打印双 ✅ 并删除 pending；任何失败保留 pending、非零退出；
  - 正文只折行、永不截断；版面放不下按档位缩字号，仍放不下报错退出；
  - 输出路径用 pathlib 解析并限制在基准目录内，拒绝目录穿越；
  - 规范交付位置已硬编码为常量，缺省即写进规范位置，无需传 outdir。
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1440
BG = (251, 246, 237)        # fbf6ed 米色底
INK = (39, 30, 27)          # 271e1b 墨色
CRIMSON = (135, 17, 15)     # 87110f 枣红
CREAM_W = (255, 248, 236)   # fff8ec 米白
GOLD = (227, 199, 159)      # e3c79f 金棕
GOLD_BG = (239, 224, 201)   # efe0c9 金棕浅底
BEIGE = (243, 233, 218)     # f3e9da 米杏
GRAY = (117, 103, 95)       # 75675f 暖灰
BORDER = (226, 215, 200)    # e2d7c8 边框
CARD_W = (255, 255, 255)
HERO_SUB = (236, 220, 196)  # 枣红底上的浅金字
RED_BG = (247, 235, 233)    # 红线行底
RED_TXT = (170, 44, 40)     # 红线文字
SHADOW = (238, 227, 214)    # 软投影

F_DIR = "/Users/shawn/Library/Fonts"
LOGO_PATH = "/Users/shawn/Desktop/AI工作区/01-Projects/公考橙皮书/assets/logo-zfz.png"  # 总分总 总品牌 logo（枣红方块白字竖排）
SERIES_INTRO = "把基层真实工作流，搬进你的答案"  # 封面页眉系列简介；后几页保持逐卡眉标

# 规范交付位置（硬编码常量，缺省全部落在基准目录内）
BASE_DIR = Path(
    "/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/"
    "公务员务实"
)
DEFAULT_PENDING = BASE_DIR / "pending_wushi.json"

CARD_FILES = ["01-封面.png", "02-场景.png", "03-步骤上.png",
              "04-步骤下.png", "05-红线.png", "06-嵌入句.png"]
LOGO_BOX = (70, 58, 182, 170)  # 与真图 logo 贴图位置一致（112px）


def safe_path(base, name):
    """解析路径并限制在 base 内，拒绝目录穿越与子目录逃逸。"""
    base_res = Path(base).resolve()
    full = (base_res / str(name)).resolve()
    if not (full == base_res or full.is_relative_to(base_res)):
        raise ValueError(f"路径越界: {name!r}（base={base_res}）")
    return full


def font(name, size):
    return ImageFont.truetype(f"{F_DIR}/{name}", size)


def F_BLACK(s):
    return font("HarmonyOS_Sans_SC_Black.ttf", s)


def F_BOLD(s):
    return font("HarmonyOS_Sans_SC_Bold.ttf", s)


def F_MED(s):
    return font("HarmonyOS_Sans_SC_Medium.ttf", s)


def F_REG(s):
    return font("HarmonyOS_Sans_SC_Regular.ttf", s)


NO_LINE_START = "、，。：；！？·）》」』%,.;:!?)]"
NO_LINE_END = "「『（《"


def tw(d, s, f):
    b = d.textbbox((0, 0), s, font=f)
    return b[2] - b[0]


def rounded(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def shadow_card(im, d, box, r=36, fill=CARD_W):
    x0, y0, x1, y1 = box
    rounded(d, [x0 + 4, y0 + 10, x1 + 4, y1 + 10], r, fill=SHADOW)
    rounded(d, box, r, fill=fill, outline=BORDER, width=2)


def wrap_text(d, text, f, max_w):
    """按像素折行；行首不带避头标点、行尾不悬挂开引号括号；末行孤字向上借字。只折行、不截断。"""
    lines, cur = [], ""
    for ch in str(text):
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if tw(d, cur + ch, f) <= max_w or (ch in NO_LINE_START and cur):
            cur += ch
        elif cur and cur[-1] in NO_LINE_END:
            lines.append(cur[:-1])
            cur = cur[-1] + ch
        else:
            lines.append(cur)
            cur = ch
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


def new_card():
    im = Image.new("RGB", (W, H), BG)
    return im, ImageDraw.Draw(im)


_logo_cache = None


def rounded_logo(size):
    """总品牌真 logo（枣红方块白字竖排「总分总」）缩放 + 圆角，带缓存。

    同《公务员务实手册》物料的贴图方案；缺失时报错退出，不许静默降级为手绘。
    """
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


def logo_header(im, d, badge_text, eyebrow="岗位业务 · 逐期拆解"):
    """每张卡顶部：总品牌 logo 图 + 「结构化技巧」字标 + 眉标 + 右上金徽。"""
    lg = rounded_logo(112)
    im.paste(lg, (70, 58), lg)
    d.text((206, 74), "结构化技巧", font=F_BOLD(52), fill=INK, anchor="la")
    d.text((208, 136), eyebrow, font=F_MED(26), fill=GRAY, anchor="la")
    f_b = F_MED(26)
    bw = tw(d, badge_text, f_b)
    x0, x1 = W - 56 - bw - 48, W - 56
    rounded(d, [x0, 84, x1, 144], 30, fill=GOLD_BG)
    d.text(((x0 + x1) // 2, 114), badge_text, font=f_b, fill=CRIMSON, anchor="mm")


def footer_note(d, text="总分总进步 · 公务员务实系列 · 每期一个岗位业务"):
    d.text((W // 2, 1372), text, font=F_REG(28), fill=GRAY, anchor="mm")


def fit_title(d, text, base=96, min_size=40, max_w=940):
    s = base
    while s > min_size and tw(d, text, F_BLACK(s)) > max_w:
        s -= 2
    return s


# ---------------------------------------------------------------- 卡1 封面
def card1_cover(im, d, p):
    """对齐答一道 Word 模板首页：logo 头 + 岗位/业务超大标题 + 金线 + 一句价值句。
    唯一要传达的：这期讲哪个岗位哪个业务，照着说考官以为你干过。"""
    logo_header(im, d, f"第{p['issue']}期", eyebrow=SERIES_INTRO)
    t1 = f"{p['post']}岗"
    s1 = fit_title(d, t1, base=132, min_size=80)
    y1 = 560
    d.text((W // 2, y1), t1, font=F_BLACK(s1), fill=INK, anchor="mm")
    t2 = p["business"]
    s2 = fit_title(d, t2, base=104, min_size=44)
    y2 = y1 + int(s1 * 0.75) + 34
    d.text((W // 2, y2), t2, font=F_BLACK(s2), fill=CRIMSON, anchor="mm")
    y_div = y2 + int(s2 * 0.75) + 40
    d.line([W // 2 - 110, y_div, W // 2 + 110, y_div], fill=GOLD, width=6)
    s_h = fit_title(d, p["cover_hook"], base=44, min_size=32)
    d.text((W // 2, y_div + 110), p["cover_hook"], font=F_BOLD(s_h),
           fill=CRIMSON, anchor="mm")
    footer_note(d)


# ---------------------------------------------------------------- 卡2 场景
def card2_scene(im, d, p):
    logo_header(im, d, f"第{p['issue']}期")
    d.text((W // 2, 320), "题目场景", font=F_BLACK(88), fill=INK, anchor="mm")
    # 白卡高度随场景文字自适应，在剩余版面内垂直居中；字号 44→30，放不下硬失败
    f_s = F_MED(44)
    zone_top, zone_bot = 480, 1330
    card_h = 460
    lines, content_h = [], 0
    for _ in range(8):
        lines = wrap_text(d, p["scene"], f_s, 810)
        content_h = len(lines) * (f_s.size + 18)
        card_h = max(460, content_h + 170)
        if card_h <= zone_bot - zone_top:
            break
        f_s = F_MED(max(30, f_s.size - 2))
    else:
        raise SystemExit("[FAIL] 场景版面放不下，不许截断——场景过长请人工精简")
    card_y0 = zone_top + (zone_bot - zone_top - card_h) // 2
    shadow_card(im, d, [80, card_y0, 1000, card_y0 + card_h], 40)
    draw_wrapped(d, (140, card_y0 + (card_h - content_h) // 2), p["scene"],
                 f_s, INK, 810, line_gap=18)
    footer_note(d)


# ------------------------------------------------------------- 卡3/4 步骤
def _render_step_card(im, d, steps, start_no, badge):
    logo_header(im, d, badge)
    d.text((W // 2, 320), "实操步骤", font=F_BLACK(88), fill=INK, anchor="mm")
    y_top, y_bot = 460, 1330
    # 档位: (正文字号, 行距, 头高, 行卡内边距)
    hs = []
    for body_f, lgap, head_h, rpad in [(27, 12, 96, 26), (25, 10, 88, 22), (24, 8, 80, 18)]:
        f_b = F_MED(body_f)
        hs = [head_h + n_lines(d, st["body"], f_b, 690) * (body_f + lgap) + rpad
              for st in steps]
        if y_top + sum(hs) + (len(steps) - 1) * 20 <= y_bot:
            break
    else:
        raise SystemExit(f"[FAIL] 步骤版面放不下（{len(steps)} 步），不许截断——请人工拆分或精简")
    y = y_top
    for i, (st, h) in enumerate(zip(steps, hs)):
        shadow_card(im, d, [80, y, 1000, y + h], 32)
        rounded(d, [122, y + 34, 210, y + 122], 24, fill=CRIMSON)
        d.text((166, y + 78), str(start_no + i), font=F_BOLD(52), fill=CREAM_W, anchor="mm")
        tx = 250
        if st["lead"]:
            d.text((tx, y + 40), st["lead"], font=F_BOLD(38), fill=INK, anchor="la")
            draw_wrapped(d, (tx, y + 96), st["body"], f_b, GRAY, 690, line_gap=lgap)
        else:
            draw_wrapped(d, (tx, y + 40), st["body"], F_BOLD(34), INK, 690, line_gap=10)
        y += h + 20
    footer_note(d)


def card3_steps_a(im, d, p):
    k = (len(p["steps"]) + 1) // 2
    _render_step_card(im, d, p["steps"][:k], 1, f"步骤 1–{k}")


def card4_steps_b(im, d, p):
    k = (len(p["steps"]) + 1) // 2
    rest = p["steps"][k:]
    if not rest:  # 只有 1 步的业务：下卡复展示整段（罕见，防空卡）
        rest = p["steps"]
    _render_step_card(im, d, rest, k + 1, f"步骤 {k+1}–{k+len(rest)}")


# ---------------------------------------------------------------- 卡5 红线
def card5_redlines(im, d, p):
    logo_header(im, d, "红线")
    d.text((W // 2, 320), "红线禁区", font=F_BLACK(88), fill=INK, anchor="mm")
    zone_top, zone_bot = 460, 1330
    hs = []
    for rf, lgap, rpad in [(36, 12, 34), (32, 10, 28), (28, 8, 24)]:
        f_r = F_BOLD(rf)
        hs = [rpad * 2 + n_lines(d, r, f_r, 760) * (rf + lgap) for r in p["redlines"]]
        if sum(hs) + (len(p["redlines"]) - 1) * 18 <= zone_bot - zone_top:
            break
    else:
        raise SystemExit("[FAIL] 红线版面放不下，不许截断——请人工精简")
    y = zone_top + (zone_bot - zone_top - (sum(hs) + (len(p["redlines"]) - 1) * 18)) // 2
    for r, h in zip(p["redlines"], hs):
        rounded(d, [80, y, 1000, y + h], 30, fill=RED_BG)
        d.text((128, y + h // 2), "✗", font=F_BOLD(44), fill=CRIMSON, anchor="lm")
        draw_wrapped(d, (190, y + rpad), r, f_r, RED_TXT, 760, line_gap=lgap)
        y += h + 18
    footer_note(d)


# ------------------------------------------------------------- 卡6 嵌入句
def card6_embed(im, d, p):
    logo_header(im, d, "嵌入句")
    d.text((W // 2, 320), "答题嵌入句", font=F_BLACK(88), fill=INK, anchor="mm")
    # 嵌入句白卡（字号随长度自适应 44→32，只折行不截断；仍放不下硬失败）
    f_e = F_BOLD(44)
    for _ in range(4):
        elines = wrap_text(d, p["embed"], f_e, 820)
        if 540 + len(elines) * (f_e.size + 20) <= 950:
            break
        f_e = F_BOLD(max(32, f_e.size - 4))
    if 540 + len(wrap_text(d, p["embed"], f_e, 820)) * (f_e.size + 20) > 950:
        raise SystemExit("[FAIL] 嵌入句版面放不下，不许截断——请人工精简")
    shadow_card(im, d, [80, 470, 1000, 960], 40)
    draw_wrapped(d, (0, 540), p["embed"], f_e, INK, 820, line_gap=20, center_x=W // 2)
    # 假大空对照条（高度按行数自适应）
    fc = p["fake_compare"]
    f_f, f_r = F_MED(26), F_BOLD(30)
    fl = n_lines(d, "✗ " + fc["fake"], f_f, 850)
    rl = n_lines(d, "✓ " + fc["real"], f_r, 850)
    bar_h = 30 + fl * 38 + 12 + rl * 42 + 30
    bar_y0 = 990
    rounded(d, [80, bar_y0, 1000, bar_y0 + bar_h], 32, fill=BEIGE)
    yy = bar_y0 + 30
    yy = draw_wrapped(d, (120, yy), "✗ " + fc["fake"], f_f, GRAY, 850, line_gap=12)
    draw_wrapped(d, (120, yy + 12), "✓ " + fc["real"], f_r, CRIMSON, 850, line_gap=12)
    # CTA 条
    cta_y0 = min(1196, bar_y0 + bar_h + 20)
    rounded(d, [80, cta_y0, 1000, cta_y0 + 140], 36, fill=CRIMSON)
    d.text((W // 2, cta_y0 + 54), "16 岗务实手册 · 看主页", font=F_BOLD(44),
           fill=CREAM_W, anchor="mm")
    d.text((W // 2, cta_y0 + 106), "先答一道，把最影响得分的地方找出来",
           font=F_MED(26), fill=HERO_SUB, anchor="mm")
    footer_note(d)


# ------------------------------------------------------------- 笔记文案
NOTE_TEMPLATE = """---
title: "{title}"
type: 素材
业务线: 公考面试
板块: 01-Projects/自媒体内容库-持续项目/公务员务实
updated: {date}
tags:
  - 类型/素材
  - 业务线/公考结构化
---

# {post}岗·{business} · 小红书图文笔记文案

> 配图：同目录 `{img_first}` 至 `{img_last}` 共 6 张（1080×1440，3:4）
> 视觉：答一道 VI（米色底 #fbf6ed · 枣红 #87110f · 金棕 #e3c79f），总分总 logo
> 口径：与《公务员务实手册》{post}岗 md 源稿一致；无「保过 / 直接背 / 万能」类表述

## 标题（三选一，均 ≤20 字）

1. **{t0}**（主推，配封面图）
2. {t1}
3. {t2}

## 正文

{body}

## 话题标签

`{tags}`

## 发布小贴士

{pub_tips}
"""


def write_note(p, outdir):
    t = p["titles"]
    content = NOTE_TEMPLATE.format(
        title=str(t[0]).replace('"', ""),
        date=datetime.date.today().isoformat(),
        post=p["post"], business=p["business"],
        img_first=CARD_FILES[0], img_last=CARD_FILES[-1],
        t0=t[0], t1=t[1], t2=t[2],
        body=str(p["body_note"]).strip(),
        tags=" ".join(p["tags"]),
        pub_tips=str(p["pub_tips"]).strip(),
    )
    (safe_path(outdir, "笔记文案.md")).write_text(content, encoding="utf-8")


# ------------------------------------------------------------- logo 校验
def check_logos(outdir):
    """总品牌真图判定：区域内枣红占比 ≥50%。

    缺图/贴错色=不达标；白色字块与圆角不干扰（同源配色，无需按背景色区分）。
    """
    ok = True
    for name in CARD_FILES:
        path = safe_path(outdir, name)
        if not path.is_file():
            print(f"[FAIL] --check 缺文件: {name}")
            ok = False
            continue
        im = Image.open(path).convert("RGB")
        px = list(im.crop(LOGO_BOX).getdata())
        n = len(px)
        crim = sum(1 for r, g, b in px
                   if max(abs(r - CRIMSON[0]), abs(g - CRIMSON[1]), abs(b - CRIMSON[2])) < 60)
        verdict = crim / n >= 0.5
        status = "PASS" if verdict else "FAIL"
        if not verdict:
            ok = False
        print(f"[{status}] logo {name}: 枣红占比 {crim/n:.0%}（≥50%）")
    return ok


def derive_outdir(p):
    """期目录名：第{期号}-{岗位}-{业务名}；路径分隔符等文件系统非法字符替换为全角。"""
    business = re.sub(r"[/\\:]", "／", str(p["business"]))
    post = re.sub(r"[/\\:]", "／", str(p["post"]))
    return BASE_DIR / f"第{p['issue']}期-{post}-{business}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pending", default=str(DEFAULT_PENDING))
    ap.add_argument("--outdir", default=None,
                    help="缺省自动写到规范位置的 第XXX期-岗位-业务名/ 目录")
    ap.add_argument("--check", action="store_true",
                    help="只校验已生成 6 图的 logo 区域，不渲染")
    args = ap.parse_args()

    if args.check:
        if not args.outdir:
            ap.error("--check 需要 --outdir")
        sys.exit(0 if check_logos(Path(args.outdir)) else 1)

    pending_path = Path(args.pending).resolve()
    if not pending_path.is_file():
        print(f"[FAIL] pending 不存在: {pending_path}")
        sys.exit(1)
    marker = Path(str(pending_path) + ".passed")
    if not marker.is_file():
        print("[FAIL] 未过内容门禁：请先运行 check_wushi_content.py（成功会写 .passed 标记）")
        sys.exit(1)
    try:
        p = json.loads(pending_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[FAIL] pending JSON 损坏: {e}")
        sys.exit(1)
    if not re.fullmatch(r"\d{3}", str(p.get("issue", ""))):
        print(f"[FAIL] issue 须三位数字，实际: {p.get('issue')}")
        sys.exit(1)
    for k in ("issue", "post", "business", "scene", "steps", "redlines",
              "embed", "fake_compare", "cover_hook", "titles", "body_note",
              "tags", "pub_tips"):
        if k not in p:
            print(f"[FAIL] pending 缺字段: {k}")
            sys.exit(1)

    outdir = Path(args.outdir).resolve() if args.outdir else derive_outdir(p).resolve()
    if not (outdir == BASE_DIR.resolve() or outdir.is_relative_to(BASE_DIR.resolve())):
        print(f"[FAIL] outdir 不在规范基准目录内: {outdir}")
        sys.exit(1)
    if outdir.exists():
        print(f"[NOTE] 期目录已存在，将覆盖同名文件: {outdir.name}")
    outdir.mkdir(parents=True, exist_ok=True)

    # 先全部渲染进内存再统一落盘：任何一张失败都不留半套图
    cards = [card1_cover, card2_scene, card3_steps_a, card4_steps_b,
             card5_redlines, card6_embed]
    rendered = []
    for fn, name in zip(cards, CARD_FILES):
        im, d = new_card()
        try:
            fn(im, d, p)
        except SystemExit as e:
            print(f"[FAIL] {name}: {e}")
            sys.exit(1)
        rendered.append((im, name))
    for im, name in rendered:
        im.save(safe_path(outdir, name))
        print(f"[OK] 渲染 {name}")
    write_note(p, outdir)
    print("[OK] 渲染 笔记文案.md")

    if not check_logos(outdir):
        print("[FAIL] logo 像素校验未通过，pending 保留")
        sys.exit(1)

    print("✅ 全部通过（6 图 + 笔记文案.md）")
    try:
        pending_path.unlink(missing_ok=True)
        marker.unlink(missing_ok=True)
        print(f"✅ pending 已删除：{pending_path}")
    except OSError as e:
        print(f"[WARN] pending/标记删除失败（不阻塞交付）: {e}")


if __name__ == "__main__":
    main()

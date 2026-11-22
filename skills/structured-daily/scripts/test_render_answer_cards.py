#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_render_answer_cards —— render_answer_cards.py（答一道 v3 七卡产线）回归测试（沙箱）。

运行：python3 scripts/test_render_answer_cards.py [关键字 ...]
- 全 16 用例全过 exit 0；全量运行时用例数 < MIN_CASES(16) → exit 1（框架坏/被删 = 假绿，不许）。
- 带关键字时只跑命中的子集（用于定位），命中 0 条 → exit 1（筛不中即失败，不许假绿）。
- 沙箱纪律（references/shared-engine-safety.md）：全程只写系统临时目录；final 样本为
  TR2 draft_yj-01_final.json 的内嵌只读副本；不触碰真实 vault
  （真实 图片输出/progress 只由人工在首期实跑时写，永不进本测试）。

v3 契约（7 卡 1080×1440，见 references/DESIGN.md）：
  01-封面 02-题目 03-答题思路 04-逐字稿一 05-逐字稿二 06-逐字稿三 07-收尾引流
  米白底 #fff8ec · 墨 #271e1b · 枣红 #87110f 唯一强调色；页脚 NN/07，无装饰横线。

覆盖 16 用例：
  case_golden             7 图全契约（尺寸/命名/配色性质/页脚/各卡结构/--check）
  case_issue_increment    progress 已有 done → 期号顺延第002期
  case_long_question      题干 72 字仍可渲染（≤80 硬上限内不 FAIL）
  case_overflow_card2     题干 ×12 → 卡 2 超高 FAIL，不落盘不写进度（v3 新增闸门）
  case_overflow_card3     观点 ×400 字 → 卡 3 超高 FAIL，不落盘不写进度
  case_no_font            FONT_DIR 缺失 → STOP（不静默降级）
  case_no_logo            LOGO_PATH 缺失 → STOP
  case_check_paths        --check 通过 / logo 占比不足 / 缺文件 三路径
  case_wrap_text          wrap_text 只折行不截断 + 避头标点 + require_glyph
  case_outdir_escape      outdir 越出 图片输出/ 拒绝
  case_cover_topic_overflow 封面主题 32 字在 88px 下限档排不下 → 显式 FAIL
  case_real_exam_prefix   真题库来源必须标「历年考题」，否则 FAIL；模拟题库误标给 WARN
  case_layout_constants   v3 版式常量 + 已删常量哨兵 + 金句源/标题/徽标函数
  case_scale_ladder       六档字号梯与相邻比（1.25–1.6）+ 正文硬下限
  case_residue_cleanup    v1 残留 png 被清理，目录只剩 7 图
  case_outdir_reuse_issue --outdir 期号复用不推进 progress（幂等）+ 无 outdir 顺延
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
RENDER = os.path.join(HERE, "render_answer_cards.py")

# v3 实际用例数；全量运行低于此数说明框架被破坏（删用例凑绿）→ exit 1
MIN_CASES = 16

# 答一道 v3 色板（唯一事实源：render_answer_cards.py 顶部常量）
BG = (255, 248, 236)       # 米白 #fff8ec
INK = (39, 30, 27)         # 墨 #271e1b
INK2 = (74, 60, 54)        # 次级墨 #4a3c36
INK3 = (140, 127, 118)     # 三级墨（页脚/微标）
CRIMSON = (135, 17, 15)    # 枣红 #87110f，唯一强调色
CREAM_W = (255, 248, 236)  # 枣红块内米白字
HERO_SUB = (236, 220, 196) # CTA 副行
RULE = (226, 215, 200)     # 分隔线

# 版面分区（性质断言的取样框，不是「必须纯色」死框）
# 内页右上角：v3 内页（02/03/07）无徽章；04/05/06 有「逐字稿 i/3」微标
TOP_RIGHT = (620, 100, 1024, 180)
TOP_RIGHT_SCRIPT = (620, 42, 1024, 90)   # 逐字稿微标 y≈42–87
FOOTER_BAND = (60, 1330, 1020, 1420)     # 页脚文字带（左右两段 28px）
TITLE_BAND = (84, 150, 996, 240)         # 内页 L1 分节标题带
CONTENT_BAND = (84, 176, 996, 1290)      # 正文可用区
CTA_BOX = (84, 1150, 996, 1270)          # 卡 07 CTA 圆角条
SCRIPT_BADGE_BAND = (84, 1241, 996, 1295)  # 卡 06 底部 script_badge

CARD_FILES = ["01-封面.png", "02-题目.png", "03-答题思路.png",
              "04-逐字稿一.png", "05-逐字稿二.png", "06-逐字稿三.png",
              "07-收尾引流.png"]
TYPE = "应急应变"
TOPIC = "政务大厅断电"

# TR2 首期 final（draft_yj-01_final.json）内嵌只读副本；16 键内容不动
SAMPLE = {
    "question": "你是政务服务大厅负责人。大厅突然停电，系统中断，现场有上百名群众等候并出现抱怨。你怎么办？",
    "title_prefix": "结构化每日一练：",
    "source": "模拟题库",
    "break_angle": "这道题的破题点在处置顺序，先查人、后修电。",
    "break_angle_reason": "应急应变考的是慌中排序。多数人拿到这题会先讲启动预案、安抚群众，先查人这一步容易漏。这条顺序是安全底线，突发事件应对法对公共场所的疏散救援有明确要求。这个顺序也是这道题的评分关键，顺序一错整篇就虚。",
    "core_views_title": "核心观点",
    "core_views_intro": "按先查人、后修电排三步。第一步分三路排除人身风险并分流控场，第二步只发已核实信息、窗口四类分流处置并边处置边报告，第三步复电验证、补录对账、善后复盘。",
    "core_views": [
        "分三路查配电房、电梯和疏散通道，有困人或者火情立即报警疏散，同时把等候群众往空地分流，照顾好行动不便的人。",
        "广播和线上只发已确认的信息，给出下次通报时间；窗口按离线受理、材料预审、线上办理、预约分流四类处理，不越权收原件，边处置边向值班领导报告。",
        "复电后先验系统再开窗口，按原排队顺序补录对账；事后补齐应急电源、广播、离线受理和岗位分工，用三本账检验处置。",
    ],
    "opening": "断电之后，处置顺序必须是先查人、后修电，这个顺序不能反。大厅一黑，电梯可能困着人，配电房可能带着火，上百人堵在窗口还可能踩踏。业务停半天能补，人出了事补不回来。",
    "point1_lead": "我先让保安、后勤和消防控制室分三路查。",
    "point1_body": "一路守配电房，看有没有焦糊味、异响，门口拉警戒，非电工不准靠近。一路逐部确认电梯，轿厢里有没有人，有没有停在两层之间。一路走疏散通道，看应急照明亮不亮、安全出口能不能推开。查到困人或者起火，马上打119和120，按预案疏散，不等请示。大厅这边请导服把群众往门口和中间空地分流，孕妇、抱小孩的、腿脚不便的先找座位，通道拐角留人打手电。",
    "point2_lead": "人查清了、现场稳住了，我再用广播说明情况，只讲已经核实的内容。",
    "point2_body": "停电原因没查清就不猜，恢复时间没把握就不报，只告诉大家下一次通报在几点。入口、官网和政务新媒体同步发服务调整，劝还没出门的群众改天再来。窗口按四类处理，有离线受理规范的，登记排队顺序、核验材料、按规定出凭证。没有离线权限的，只做材料预审和一次性告知，不收原件。手机能办的引导线上办，短时恢复不了的协调邻近大厅分流或者按群众意愿预约。我一边处置一边向中心值班领导报告停电范围、已采取的措施和需要支援的事项，有进展就续报。",
    "point3_lead": "电来了先别开窗口。",
    "point3_body": "让技术人员查网络、服务器和终端，确认稳定再逐批开放。系统恢复后按承诺的渠道再发一次通知，写清恢复时间、补办安排和咨询电话。工作人员按停电前的排队顺序和离线登记逐件核对，补录一件勾掉一件，当天对不平的下班前集中处理。已经离开的群众按登记方式通知，答应当天回复的必须回。材料交接双人签字，避免忙中拿错、丢件。事后把应急照明、备用电源、广播、离线受理、材料保管逐项查一遍，缺什么补什么。预案里写清谁拉闸、谁报信、谁分流，岗位清单补齐，安排一次演练。当天的投诉和延误逐件复核，能当场改的当场改，改不了的定责任人和期限。",
    "closing": "断电处置到不到位，看当晚三本账。离线登记、系统补录、答应回访的投诉，三本对得上，事才落地。差一笔，就有人的事悬着。答题完毕。",
}


# --------------------------------------------------------------------------
# 像素工具：全部是「性质统计」，不做「某矩形必须纯色」的死断言
# --------------------------------------------------------------------------
def near(color, target, tol):
    return (abs(color[0] - target[0]) <= tol
            and abs(color[1] - target[1]) <= tol
            and abs(color[2] - target[2]) <= tol)


def count_near(im, box, target, tol):
    """box 内与 target 三通道差都 <= tol 的像素数。"""
    crop = im.crop(box).convert("RGB")
    data = crop.tobytes()
    t0, t1, t2 = target
    n = 0
    for i in range(0, len(data), 3):
        if (abs(data[i] - t0) <= tol and abs(data[i + 1] - t1) <= tol
                and abs(data[i + 2] - t2) <= tol):
            n += 1
    return n


def count_nonbg(im, box, tol=6):
    """box 内非米白底（含抗锯齿）的像素数。"""
    crop = im.crop(box).convert("RGB")
    data = crop.tobytes()
    b0, b1, b2 = BG
    n = 0
    for i in range(0, len(data), 3):
        if (abs(data[i] - b0) > tol or abs(data[i + 1] - b1) > tol
                or abs(data[i + 2] - b2) > tol):
            n += 1
    return n


def count_saturated(im, box, min_spread=60):
    """饱和彩色像素数（任一通道极差 >= min_spread），用于「纯米白留白」性质断言。"""
    crop = im.crop(box).convert("RGB")
    data = crop.tobytes()
    n = 0
    for i in range(0, len(data), 3):
        lo = min(data[i], data[i + 1], data[i + 2])
        hi = max(data[i], data[i + 1], data[i + 2])
        if hi - lo >= min_spread:
            n += 1
    return n


def row_profile(im, box, target, tol):
    """按行统计 box 内匹配色像素数 → [(y, n), ...]。"""
    x0, y0, x1, y1 = box
    px = im.load()
    out = []
    for y in range(y0, y1):
        n = 0
        for x in range(x0, x1):
            if near(px[x, y], target, tol):
                n += 1
        out.append((y, n))
    return out


def bands(profile, min_px):
    """把连续满足 n >= min_px 的行合成 (y_start, y_end) 区间。"""
    out, cur = [], None
    for y, n in profile:
        if n >= min_px:
            cur = (y, y) if cur is None else (cur[0], y)
        elif cur is not None:
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    return out


def wide_row_peak(im, box):
    """box 内单行非米白像素的最大值（用于判定「有没有整条横线」）。"""
    x0, y0, x1, y1 = box
    px = im.load()
    peak = 0
    for y in range(y0, y1):
        n = 0
        for x in range(x0, x1, 2):  # 隔点抽样，横线必然整行命中
            if not near(px[x, y], BG, 6):
                n += 1
        peak = max(peak, n * 2)
    return peak


def content_bottom(im):
    """正文区（x84–996）最后一条有内容的行，用于「不越过 ZONE_BOT」性质断言。"""
    px = im.load()
    last = None
    for y in range(CONTENT_BAND[1], CONTENT_BAND[3]):
        n = 0
        for x in range(CONTENT_BAND[0], CONTENT_BAND[2], 2):
            if not near(px[x, y], BG, 6):
                n += 1
                if n >= 3:
                    break
        if n >= 3:
            last = y
    return last


def square_bands(im, y0=300, y1=1250, need=0.55):
    """枣红编号方块：找出「左栏 40×40 盒子枣红占比 >= need」的互不相邻 y 带。

    方块是 40×40 圆角（RADIUS_SMALL=12），整盒占比峰值约 0.88，故用 0.55 兜住
    抗锯齿差异；相邻命中按 <=8px 合并成一条 y 带。
    """
    hits = []
    for y in range(y0, y1, 2):
        if y + 40 > 1400:
            break
        if count_near(im, (84, y, 124, y + 40), CRIMSON, 60) >= int(40 * 40 * need):
            hits.append(y)
    merged = []
    for y in hits:
        if merged and y - merged[-1][1] <= 8:
            merged[-1] = (merged[-1][0], y)
        else:
            merged.append((y, y))
    return merged


# --------------------------------------------------------------------------
# 沙箱与子进程
# --------------------------------------------------------------------------
def load_mod():
    """进程内加载渲染引擎模块（供 monkeypatch 常量与常量断言）。"""
    spec = importlib.util.spec_from_file_location("render_answer_cards", RENDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_sandbox(tmpdir, final=None, progress=None):
    """在 tmpdir/proj 下搭项目根沙箱；progress 非 None 时预置 progress_answer.json。"""
    root = Path(tmpdir) / "proj"
    (root / "scripts").mkdir(parents=True)
    final_path = root / "scripts" / "draft_yj-01_final.json"
    final_path.write_text(json.dumps(final or SAMPLE, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    if progress is not None:
        (root / "图片输出").mkdir()
        (root / "图片输出" / "progress_answer.json").write_text(
            json.dumps(progress, ensure_ascii=False), encoding="utf-8")
    return root, final_path


def run_render(root, final_path, extra=None):
    cmd = [sys.executable, RENDER, "--project-root", str(root),
           "--final", str(final_path), "--type", TYPE, "--topic", TOPIC]
    if extra:
        cmd += extra
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def run_check(root, outdir):
    cmd = [sys.executable, RENDER, "--project-root", str(root),
           "--check", "--outdir", str(outdir)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def issue_dir(root, issue):
    return Path(root) / "图片输出" / f"第{issue}期-{TYPE}-{TOPIC}"


def progress_path(root):
    return Path(root) / "图片输出" / "progress_answer.json"


CASES = []


def case(cid, title):
    def wrap(fn):
        CASES.append((cid, title, fn))
        return fn
    return wrap


# --------------------------------------------------------------------------
# 1. golden 全契约
# --------------------------------------------------------------------------
@case("case_golden", "golden 7 图全契约（尺寸/命名/配色性质/页脚/各卡结构/笔记/进度/--check）")
def case_golden(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        root, final_path = make_sandbox(tmpdir)
        rc, out = run_render(root, final_path)
        check(rc == 0, "exit=%s out=%s" % (rc, out[-500:]))
        check("✅ 全部通过（7 图 + 笔记文案.md）" in out,
              "无 v3 成功标记（7 图 + 笔记文案.md）: %s" % out[-300:])
        # 逐字稿三卡的档位回执：观点句 56 / 正文 44（v3 梯）
        check(out.count("[OK] 逐字稿") == 3,
              "逐字稿档位回执应为 3 条，实际 %s" % out.count("[OK] 逐字稿"))
        check("观点句 56px / 正文 44px" in out,
              "逐字稿未落在 v3 设计档 56/44: %s" % out[-300:])
        outdir = issue_dir(root, "001")
        check(outdir.is_dir(), "期目录未生成: %s" % outdir)
        check(sorted(p.name for p in outdir.glob("*.png")) == sorted(CARD_FILES),
              "目录 png 集合 ≠ 7 张 CARD_FILES: %s"
              % sorted(p.name for p in outdir.glob("*.png")))
        ims = {}
        for name in CARD_FILES:
            p = outdir / name
            check(p.is_file(), "缺图: %s" % name)
            if not p.is_file():
                continue
            im = Image.open(p).convert("RGB")
            ims[name] = im
            check(im.size == (1080, 1440), "%s 尺寸=%s" % (name, im.size))
            corners = [im.getpixel(xy) for xy in
                       ((12, 12), (1067, 12), (12, 1427), (1067, 1427))]
            check(all(c == BG for c in corners), "%s 四角非米白: %s" % (name, corners))
            # 页脚：v3 只有左右两段 28px 文字，没有装饰横线
            non_bg = count_nonbg(im, FOOTER_BAND)
            check(non_bg > 1000,
                  "%s 页脚带非米白像素 %s ≤1000（页脚缺失?）" % (name, non_bg))
            peak = wide_row_peak(im, (0, 1300, 1080, 1440))
            check(peak < 400,
                  "%s 页脚带出现整行非米白 %s px（v3 已删装饰横线?）" % (name, peak))
            # 正文不越过 ZONE_BOT=1290
            bottom = content_bottom(im)
            check(bottom is not None and bottom <= 1290,
                  "%s 正文底沿 %s 越过 ZONE_BOT=1290" % (name, bottom))
        if len(ims) != 7:
            return

        # ---- 卡 01 封面：枣红圆角块 + 块内米白主题 + 下方副标 + 大片留白
        c1 = ims["01-封面.png"]
        ratio = count_near(c1, (0, 0, 1080, 1440), CRIMSON, 60) / (1080 * 1440)
        check(0.08 <= ratio <= 0.12,
              "封面枣红总面积占比 %.4f 不在 8%%..12%%（主题块尺度漂移）" % ratio)
        prof = row_profile(c1, (0, 400, 1080, 1100), CRIMSON, 60)
        blk = bands(prof, 200)
        check(len(blk) == 1, "封面枣红块 y 带不唯一: %s" % (blk,))
        if blk:
            y0, y1 = blk[0]
            check(560 <= y0 <= 610, "封面主题块上沿 %s 不在 560..610" % y0)
            check(735 <= y1 <= 800, "封面主题块下沿 %s 不在 735..800" % y1)
            check(y1 - y0 >= 150, "封面主题块高 %s < 150（块尺度漂移）" % (y1 - y0))
            check(y0 >= 240 and y1 <= 1240,
                  "封面主题块 %s..%s 越出 COVER_ZONE(240,1240)" % (y0, y1))
            xs = [x for x in range(0, 1080)
                  if near(c1.getpixel((x, (y0 + y1) // 2)), CRIMSON, 60)]
            check(xs and min(xs) <= 100, "封面主题块未贴左边距 84: %s" % (min(xs) if xs else None))
            check(xs and max(xs) >= 900, "封面主题块右边 %s < 900（块宽异常）"
                  % (max(xs) if xs else None))
            cream = count_near(c1, (84, y0 + 30, 966, y1 - 30), CREAM_W, 12)
            check(cream > 20000, "封面主题米白字像素 %s ≤20000（主题缺失?）" % cream)
        # 副标在主题块下方，且其下 200px 内不许有饱和彩色（留白纪律）
        sub = count_near(c1, (84, 800, 996, 1000), INK, 60)
        check(sub > 800, "封面副标墨色像素 %s ≤800（COVER_SUB 缺失?）" % sub)
        below = count_saturated(c1, (0, 1000, 1080, 1200))
        check(below == 0, "封面副标下 200px 出现 %s 个饱和彩色像素（留白纪律破）" % below)
        # 封面右上「第 N 期 · 题型」标签
        check(count_nonbg(c1, (620, 84, 1024, 144)) > 150,
              "封面右上期号标签缺失（非米白 %s）"
              % count_nonbg(c1, (620, 84, 1024, 144)))

        # ---- 卡 02 题目：无 L1 标题（v3 内页无 TITLE_Y/TABLINE），微标+题干+短线+破题句+理由
        c2 = ims["02-题目.png"]
        check(count_nonbg(c2, TITLE_BAND) == 0,
              "卡 02 出现 L1 标题带内容 %s（v3 内页无标题范式）"
              % count_nonbg(c2, TITLE_BAND))
        check(count_nonbg(c2, TOP_RIGHT) == 0,
              "卡 02 右上出现非米白 %s（内页不应有角标）"
              % count_nonbg(c2, TOP_RIGHT))
        check(count_near(c2, (84, 290, 996, 390), CRIMSON, 60) > 100,
              "卡 02 来源微标缺失")
        check(count_near(c2, (84, 360, 996, 660), INK, 60) > 3000,
              "卡 02 题干墨色像素不足")
        # 96×3 枣红短线：整行满 96px 命中（x84..180），非满行不认
        rule = bands(row_profile(c2, (84, 600, 182, 780), CRIMSON, 60), 94)
        check(len(rule) == 1, "卡 02 96×3 枣红短线不唯一: %s" % (rule,))
        if rule:
            check(660 <= rule[0][0] <= 700,
                  "卡 02 短线 y=%s 不在 660..700" % (rule[0][0],))
            check(rule[0][1] - rule[0][0] <= 8, "卡 02 短线过粗: %s" % (rule,))
            mid = (rule[0][0] + rule[0][1]) // 2
            xs = [x for x in range(0, 480) if near(c2.getpixel((x, mid)), CRIMSON, 60)]
            check(xs and min(xs) == 84 and max(xs) == 180,
                  "卡 02 短线 x 范围 %s..%s ≠ 84..180（长度应为 96）"
                  % (min(xs) if xs else None, max(xs) if xs else None))
        check(count_near(c2, (84, 700, 996, 800), CRIMSON, 60) > 2000,
              "卡 02 破题句枣红像素不足")
        check(count_near(c2, (84, 800, 996, 1130), INK2, 30) > 3000,
              "卡 02 破题理由 INK2 像素不足")

        # ---- 卡 03 答题思路：L1 分节标题 + 三个 40px 枣红编号方块
        c3 = ims["03-答题思路.png"]
        check(count_near(c3, TITLE_BAND, INK, 60) > 5000,
              "卡 03 L1 分节标题墨色不足")
        check(count_nonbg(c3, TOP_RIGHT) == 0, "卡 03 右上出现角标")
        sq = square_bands(c3)
        check(len(sq) == 3, "卡 03 编号方块应 3 个，实测 %s 条 y 带: %s" % (len(sq), sq))
        for i in range(1, len(sq)):
            check(sq[i][0] - sq[i - 1][1] >= 150,
                  "卡 03 方块间距过小: %s" % (sq,))

        # ---- 卡 04/05/06 逐字稿：右上「逐字稿 i/3」微标 + 各 1 个编号方块
        for idx, name in ((3, "04-逐字稿一.png"), (4, "05-逐字稿二.png"),
                          (5, "06-逐字稿三.png")):
            im = ims[name]
            check(count_nonbg(im, TOP_RIGHT_SCRIPT) > 500,
                  "%s 缺「%s」微标" % (name, ["逐字稿 1/3", "逐字稿 2/3", "逐字稿 3/3"][idx - 3]))
            check(count_nonbg(im, TITLE_BAND) > 1000,
                  "%s 正文起点异常（标题带无内容）" % name)
            check(len(square_bands(im, 150, 1300)) == 1,
                  "%s 编号方块数目异常" % name)
        # 卡 06 底部 script_badge（只为卡 06 断言，卡 07 同区是 CTA）
        c6 = ims["06-逐字稿三.png"]
        badge = count_near(c6, SCRIPT_BADGE_BAND, INK3, 40)
        check(badge > 800, "卡 06 底部 script_badge INK3 像素 %s ≤800（字数时长徽标缺失?）" % badge)
        for name in ("04-逐字稿一.png", "05-逐字稿二.png"):
            check(count_near(ims[name], SCRIPT_BADGE_BAND, INK3, 40) < 200,
                  "%s 底部出现 badge 小字（应只在最后一页）" % name)

        # ---- 卡 07 收尾引流：金句 + 短线 + 收尾话 + 枣红 CTA
        c7 = ims["07-收尾引流.png"]
        check(count_nonbg(c7, TOP_RIGHT) == 0, "卡 07 右上出现角标")
        check(count_near(c7, (84, 480, 996, 620), INK, 60) > 5000,
              "卡 07 本期金句墨色不足")
        check(count_near(c7, (84, 650, 996, 820), INK2, 30) > 5000,
              "卡 07 收尾话 INK2 像素不足")
        gold_rule = bands(row_profile(c7, (84, 380, 182, 560), CRIMSON, 60), 94)
        check(len(gold_rule) == 1, "卡 07 96×3 枣红短线不唯一: %s" % (gold_rule,))
        check(gold_rule and gold_rule[0][1] - gold_rule[0][0] <= 8,
              "卡 07 短线过粗: %s" % (gold_rule,))
        cta = count_near(c7, CTA_BOX, CRIMSON, 40) / float(
            (CTA_BOX[2] - CTA_BOX[0]) * (CTA_BOX[3] - CTA_BOX[1]))
        check(cta >= 0.50, "卡 07 CTA 枣红占比 %.3f < 0.50" % cta)
        check(count_near(c7, CTA_BOX, CREAM_W, 12) > 2000,
              "卡 07 CTA 主行米白字缺失")
        check(count_near(c7, CTA_BOX, HERO_SUB, 24) > 1000,
              "卡 07 CTA 副行 HERO_SUB 缺失（BRAND_SLOGAN?）")

        # ---- 笔记文案（v3 模板）
        note = outdir / "笔记文案.md"
        check(note.is_file(), "缺 笔记文案.md")
        if note.is_file():
            txt = note.read_text(encoding="utf-8")
            check("#结构化面试" in txt, "缺固定标签 #结构化面试")
            check(f"#{TYPE}" in txt, "缺题型标签 #%s" % TYPE)
            check("评论区打「1」" in txt, "缺固定引导")
            check("## 本期金句" in txt, "v3 缺「## 本期金句」段")
            check("业务停半天能补，人出了事补不回来" in txt,
                  "本期金句与 opening 末句不一致")
            check("## 配图" in txt and "共 7 张" in txt, "v3 缺「## 配图（共 7 张）」段")
            check("07-收尾引流.png" in txt, "配图清单未写全 7 图")
            check("7 卡" in txt and "references/DESIGN.md" in txt,
                  "视觉说明句未提 7 卡 / DESIGN.md")
            check("米白底 #fff8ec" in txt and "#87110f" in txt,
                  "视觉说明句未写 v3 色板")
            check("政务大厅断电，先查人、后修电" in txt, "标题未从 break_angle 提炼")
        prog = progress_path(root)
        check(prog.is_file(), "progress_answer.json 未生成")
        if prog.is_file():
            data = json.loads(prog.read_text(encoding="utf-8"))
            check(data.get("done") == ["yj-01"], "done=%r" % data.get("done"))

        # ---- --check（7 图 logo 像素校验）
        rc2, out2 = run_check(root, outdir)
        check(rc2 == 0, "--check 未通过: exit=%s out=%s" % (rc2, out2[-300:]))
        check("7 图 logo 像素校验" in out2, "--check 未走 v3 七图口径: %s" % out2[-200:])
        check(out2.count("[PASS] logo") == 7,
              "--check 通过回执 %s 条 ≠ 7" % out2.count("[PASS] logo"))


# --------------------------------------------------------------------------
# 2. 期号递增
# --------------------------------------------------------------------------
@case("case_issue_increment", "期号递增（progress 已有 1 条 done → 第002期，done 追加）")
def case_issue_increment(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        root, final_path = make_sandbox(tmpdir, progress={"done": ["demo-009"]})
        rc, out = run_render(root, final_path)
        check(rc == 0, "exit=%s out=%s" % (rc, out[-300:]))
        check(issue_dir(root, "002").is_dir(), "第002期目录未生成")
        check(not issue_dir(root, "001").exists(), "不应同时生成第001期")
        data = json.loads(progress_path(root).read_text(encoding="utf-8"))
        check(data.get("done") == ["demo-009", "yj-01"], "done=%r" % data.get("done"))
        check(f"第002期" in out, "成功回执未带期号: %s" % out[-200:])


# --------------------------------------------------------------------------
# 3. 长题干仍可渲染
# --------------------------------------------------------------------------
@case("case_long_question", "题干 72 字（≤80 硬上限）仍渲染 7 图不截断")
def case_long_question(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        final = dict(SAMPLE)
        final["question"] = (SAMPLE["question"].rstrip("？")
                             + "现场群众情绪激动，有人拍摄发帖，话题开始发酵，你怎么办？")
        check(len(final["question"]) <= 80, "题干超 80 字上限: %s" % len(final["question"]))
        root, final_path = make_sandbox(tmpdir, final=final)
        rc, out = run_render(root, final_path)
        check(rc == 0, "退出码=%s 输出=%s" % (rc, out[-400:]))
        outdir = issue_dir(root, "001")
        for name in CARD_FILES:
            check((outdir / name).is_file(), "缺图: %s" % name)
        c2 = Image.open(outdir / CARD_FILES[1]).convert("RGB")
        check(count_near(c2, (84, 176, 996, 1290), INK, 60) > 5000,
              "长题干墨色像素不足（题干可能被吞）")


# --------------------------------------------------------------------------
# 4/5. 超高 FAIL（卡 2 / 卡 3 两处闸门）
# --------------------------------------------------------------------------
@case("case_overflow_card2", "卡 2 超高 FAIL（题干 ×12）→ exit≠0、不落盘、不写进度")
def case_overflow_card2(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        final = dict(SAMPLE)
        final["question"] = (SAMPLE["question"].rstrip("？") * 12) + "？"
        check(len(final["question"]) > 400, "构造题干过短: %s" % len(final["question"]))
        root, final_path = make_sandbox(tmpdir, final=final)
        rc, out = run_render(root, final_path)
        check(rc != 0, "卡 2 超高未 FAIL，exit=%s" % rc)
        check("卡2" in out and "超高" in out, "未指出卡 2 内容超高: %s" % out[-300:])
        check("不许截断" in out, "未重申「不许截断」铁律: %s" % out[-300:])
        check(not progress_path(root).is_file(), "失败却写了进度")
        check(not issue_dir(root, "001").exists(), "失败却留了期目录")


@case("case_overflow_card3", "卡 3 超高 FAIL（观点 ×400 字）→ exit≠0、不落盘、不写进度")
def case_overflow_card3(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        final = dict(SAMPLE)
        final["core_views"] = [SAMPLE["core_views"][0] * 8,
                               SAMPLE["core_views"][1] * 8,
                               SAMPLE["core_views"][2] * 8]
        root, final_path = make_sandbox(tmpdir, final=final)
        rc, out = run_render(root, final_path)
        check(rc != 0, "卡 3 超高未 FAIL，exit=%s" % rc)
        check("卡3" in out and "超高" in out, "未指出卡 3 内容超高: %s" % out[-300:])
        check(not progress_path(root).is_file(), "失败却写了进度")
        check(not issue_dir(root, "001").exists(), "失败却留了期目录")


# --------------------------------------------------------------------------
# 6/7. 资产缺失 STOP
# --------------------------------------------------------------------------
@case("case_no_font", "缺字体 monkeypatch FONT_DIR → STOP exit≠0，不建目录不写进度")
def case_no_font(check):
    mod = load_mod()
    real = mod.FONT_DIR
    mod.FONT_DIR = "/nonexistent_v3_fonts"
    try:
        with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
            root, final_path = make_sandbox(tmpdir)
            sys.argv = ["render_answer_cards.py", "--project-root", str(root),
                        "--final", str(final_path), "--type", TYPE, "--topic", TOPIC]
            try:
                mod.main()
                code, msg = 0, ""
            except SystemExit as e:
                code, msg = e.code, str(e)
            check(code not in (0, None), "exit=%r" % code)
            # v3 两条文案：目录不存在 / 缺文件——都只保证含「字体」与「STOP」
            check("字体" in msg, "未报字体问题: %s" % msg)
            check("STOP" in msg, "未按 STOP 纪律中止: %s" % msg)
            check(not (Path(root) / "图片输出").exists(),
                  "STOP 却创建了 图片输出/")
    finally:
        mod.FONT_DIR = real


@case("case_no_logo", "缺 logo monkeypatch LOGO_PATH → STOP exit≠0，不写进度")
def case_no_logo(check):
    mod = load_mod()
    real = mod.LOGO_PATH
    mod.LOGO_PATH = "/nonexistent_v3/logo-zfz.png"
    try:
        with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
            root, final_path = make_sandbox(tmpdir)
            sys.argv = ["render_answer_cards.py", "--project-root", str(root),
                        "--final", str(final_path), "--type", TYPE, "--topic", TOPIC]
            try:
                mod.main()
                code, msg = 0, ""
            except SystemExit as e:
                code, msg = e.code, str(e)
            check(code not in (0, None), "exit=%r" % code)
            check("logo" in msg, "未报 logo 缺失: %s" % msg)
            check("STOP" in msg, "未按 STOP 纪律中止: %s" % msg)
            check(not (Path(root) / "图片输出").exists(),
                  "STOP 却创建了 图片输出/")
    finally:
        mod.LOGO_PATH = real


# --------------------------------------------------------------------------
# 8. --check 三路径
# --------------------------------------------------------------------------
@case("case_check_paths", "--check 通过 / logo 占比不足 / 缺文件 三路径")
def case_check_paths(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        root, final_path = make_sandbox(tmpdir)
        rc, out = run_render(root, final_path)
        check(rc == 0, "前置渲染失败 exit=%s" % rc)
        outdir = issue_dir(root, "001")
        rc, out = run_check(root, outdir)
        check(rc == 0, "--check 应通过: exit=%s out=%s" % (rc, out[-300:]))
        # 失败路径一：封面 logo 区被清成米底 → 枣红占比不达标
        Image.new("RGB", (1080, 1440), BG).save(outdir / CARD_FILES[0])
        rc, out = run_check(root, outdir)
        check(rc != 0, "logo 被清空后 --check 仍通过")
        check("枣红占比" in out, "未报 logo 枣红占比: %s" % out[-300:])
        # 重渲染复原，再走失败路径二：缺图
        rc, out = run_render(root, final_path, extra=["--outdir", str(outdir)])
        check(rc == 0, "复原渲染失败 exit=%s out=%s" % (rc, out[-300:]))
        (outdir / CARD_FILES[6]).unlink()
        rc, out = run_check(root, outdir)
        check(rc != 0, "缺图后 --check 仍通过")
        check("缺文件" in out, "未报缺文件")
        check(CARD_FILES[6] in out, "未指出缺的是 %s: %s" % (CARD_FILES[6], out[-300:]))
        # --check 缺 --outdir 也要拒绝
        proc = subprocess.run([sys.executable, RENDER, "--project-root", str(root),
                               "--check"], capture_output=True, text=True)
        check(proc.returncode != 0, "--check 无 outdir 仍通过")
        check("--outdir" in (proc.stdout + proc.stderr), "--check 未提示需要 --outdir")


# --------------------------------------------------------------------------
# 9. wrap_text / require_glyph
# --------------------------------------------------------------------------
@case("case_wrap_text", "wrap_text 只折行不截断 + 避头标点 + require_glyph 拦截零高字形")
def case_wrap_text(check):
    from PIL import ImageDraw
    mod = load_mod()
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    f = mod.F_MED(28)
    max_w = 820
    text = "政务服务大厅突然停电系统中断，现场有上百名群众等候并出现抱怨，处置顺序不能反。" * 6
    lines = mod.wrap_text(d, text, f, max_w)
    check(len(lines) > 1, "未折行 lines=%s" % len(lines))
    check("".join(lines) == text, "折行丢字（截断）")
    for ln in lines:
        w = mod.tw(d, ln, f)
        check(w <= max_w, "行宽超限 %s > %s: %r" % (w, max_w, ln[:20]))
        check(not (ln and ln[0] in mod.NO_LINE_START), "行首避头标点违规: %r" % ln[:6])
        check(not (ln and ln[-1] in mod.NO_LINE_END), "行尾悬挂开引号: %r" % ln[-6:])
    # 英文/数字不被拆断（v3 _alnum_run_start 语义）
    en = "PIL 1080x1440 渲染 7 卡图片，ABCDEFGHIJKLMNOPQRSTUVWXYZ 与 0123456789"
    el = mod.wrap_text(d, en, f, 300)
    check("".join(el) == en, "英文折行丢字")
    check(all(mod.tw(d, ln, f) <= 300 for ln in el), "英文行宽超限")
    # require_glyph：缺字形符号（bbox 高 0）渲染即空白，必须拦截
    real_gh = mod.glyph_height
    mod.glyph_height = lambda s, f: 0
    try:
        try:
            mod.require_glyph(mod.F_MED(26), "字")
            raised = False
        except SystemExit:
            raised = True
        check(raised, "require_glyph 未拦截零高字形")
    finally:
        mod.glyph_height = real_gh


# --------------------------------------------------------------------------
# 10. outdir 越界
# --------------------------------------------------------------------------
@case("case_outdir_escape", "outdir 越界拒绝（须在 图片输出/ 内，且不创建目录）")
def case_outdir_escape(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        root, final_path = make_sandbox(tmpdir)
        outside = Path(tmpdir) / "outside"
        rc, out = run_render(root, final_path, extra=["--outdir", str(outside)])
        check(rc != 0, "越界 outdir 未拒绝 exit=%s" % rc)
        check("不在" in out, "未报越界: %s" % out[-300:])
        check(not outside.exists(), "越界目录被创建")
        check(not progress_path(root).is_file(), "失败却写了进度")


# --------------------------------------------------------------------------
# 11. 封面主题超长
# --------------------------------------------------------------------------
@case("case_cover_topic_overflow", "封面主题超长（32 字）→ 显式 FAIL 不出图，报错带字数")
def case_cover_topic_overflow(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        root, final_path = make_sandbox(tmpdir)
        long_topic = "政务" * 16  # 32 字：88px 下限档 × 2 行仍放不进 824px 内宽
        rc, out = run_render(root, final_path, extra=["--topic", long_topic])
        check(rc != 0, "超长主题未 FAIL exit=%s" % rc)
        check("封面主题超长" in out, "未报主题超长: %s" % out[-300:])
        check(str(len(long_topic)) in out, "报错未指明主题字数: %s" % out[-300:])
        check(not issue_dir(root, "001").exists(), "失败却留了期目录")
        check(not progress_path(root).is_file(), "失败却写了进度")


# --------------------------------------------------------------------------
# 11b. 封面前缀铁律（真题库来源必须标「历年考题」）
# --------------------------------------------------------------------------
@case("case_real_exam_prefix", "封面前缀铁律：真题库须含「历年考题」，否则 FAIL 不落盘")
def case_real_exam_prefix(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        root, final_path = make_sandbox(tmpdir)
        # ① 真题库来源 + 未标「历年考题」→ 必须 FAIL
        bad = dict(SAMPLE)
        bad["source"] = "真题库"
        bad["title_prefix"] = "结构化每日一练："
        final_path.write_text(json.dumps(bad, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        rc, out = run_render(root, final_path)
        check(rc != 0, "真题库漏标「历年考题」未 FAIL，exit=%s" % rc)
        check("真题库" in out and "历年考题" in out,
              "报错未点明真题库/历年考题: %s" % out[-300:])
        check(not progress_path(root).is_file(), "失败却写了进度")
        check(not issue_dir(root, "001").exists(), "失败却留了期目录")
        # ② 真题库来源 + 正确标「历年考题」→ 正常出 7 图
        good = dict(SAMPLE)
        good["source"] = "真题库"
        good["title_prefix"] = "结构化历年考题："
        final_path.write_text(json.dumps(good, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        rc, out = run_render(root, final_path)
        check(rc == 0, "真题库正确标注后仍失败 exit=%s: %s" % (rc, out[-300:]))
        outdir = issue_dir(root, "001")
        for name in CARD_FILES:
            check((outdir / name).is_file(), "真题库路径缺图: %s" % name)
        # ③ 模拟题库 + 误标「历年考题」→ 放行但给 WARN
        warn = dict(SAMPLE)
        warn["source"] = "模拟题库"
        warn["title_prefix"] = "结构化历年考题："
        final_path.write_text(json.dumps(warn, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        rc, out = run_render(root, final_path,
                             extra=["--outdir", str(issue_dir(root, "001"))])
        check(rc == 0, "模拟题库误标历年考题不应阻断 exit=%s: %s" % (rc, out[-300:]))
        check("WARN" in out and "历年考题" in out,
              "误标未给 WARN 提示: %s" % out[-300:])
        # ④ 真实 SAMPLE（source=模拟题库 + 每日一练前缀）不受新闸门影响，且不误报 WARN
        final_path.write_text(json.dumps(SAMPLE, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        rc, out = run_render(root, final_path,
                             extra=["--outdir", str(issue_dir(root, "001"))])
        check(rc == 0, "SAMPLE 基线被新闸门误伤 exit=%s: %s" % (rc, out[-300:]))
        check("WARN" not in out, "普通来源误报 WARN: %s" % out[-300:])


# --------------------------------------------------------------------------
# 12. v3 版式常量
# --------------------------------------------------------------------------
@case("case_layout_constants", "v3 版式常量 + 已删常量哨兵 + 金句源/标题/徽标函数")
def case_layout_constants(check):
    mod = load_mod()
    # --- 色板：v3 只有 8 个颜色，且金色/灰阶系全删
    check(mod.BG == (255, 248, 236), "底色 %s ≠ 米白 #fff8ec" % (mod.BG,))
    check(mod.INK == (39, 30, 27), "主墨 %s ≠ #271e1b" % (mod.INK,))
    check(mod.INK2 == (74, 60, 54), "次级墨 %s ≠ #4a3c36" % (mod.INK2,))
    check(mod.INK3 == (140, 127, 118), "三级墨 %s ≠ #8c7f76" % (mod.INK3,))
    check(mod.CRIMSON == (135, 17, 15), "强调色 %s ≠ 枣红 #87110f" % (mod.CRIMSON,))
    check(mod.CREAM_W == mod.BG, "枣红块内米白字 %s 应等于底色米白" % (mod.CREAM_W,))
    check(mod.HERO_SUB == (236, 220, 196), "CTA 副行色 %s 漂移" % (mod.HERO_SUB,))
    check(mod.RULE == (226, 215, 200), "分隔线色 %s 漂移" % (mod.RULE,))
    for gone in ("GOLD", "GOLD_BG", "BEIGE", "GRAY", "BORDER", "CARD_W",
                 "RED_BG", "RED_TXT", "SHADOW"):
        check(not hasattr(mod, gone),
              "v1 色板常量 %s 仍存在（应已删除，测试需同步）" % gone)
    # --- 版面骨架
    check(mod.MARGIN == 84 and mod.TX_X == 84 and mod.TX_W == 912,
          "边距口径不符: %s/%s/%s" % (mod.MARGIN, mod.TX_X, mod.TX_W))
    check(mod.TX_W + 2 * mod.MARGIN == 1080, "版心与边距不自洽: %s" % (mod.TX_W,))
    check(mod.SAFE == 64, "SAFE=%s ≠ 64" % mod.SAFE)
    check(mod.ZONE_BOT == 1290, "ZONE_BOT=%s ≠ 1290" % mod.ZONE_BOT)
    check(mod.FOOTER_TEXT_Y == 1372, "页脚基线 %s ≠ 1372" % mod.FOOTER_TEXT_Y)
    check(mod.FOOTER_TEXT_Y > mod.ZONE_BOT, "页脚应在正文区之下")
    check(mod.RADIUS_SMALL == 12 and mod.RADIUS_LARGE == 24,
          "圆角 %s/%s ≠ 12/24" % (mod.RADIUS_SMALL, mod.RADIUS_LARGE))
    check(mod.RULE_W == 3, "短线粗细 %s ≠ 3" % mod.RULE_W)
    # --- 已删的 v1 内页范式（TITLE_Y / TITLE_SIZE / TABLINE / STRUCT）
    for gone in ("TITLE_Y", "TITLE_SIZE", "TABLINE", "STRUCT"):
        check(not hasattr(mod, gone), "v1 内页常量 %s 仍存在" % gone)
    # --- 7 卡清单与卡函数名
    check(mod.CARD_FILES == CARD_FILES, "CARD_FILES 非 v3 七卡: %s" % (mod.CARD_FILES,))
    check(len(mod.CARDS) == 7, "CARDS 数目 %s ≠ 7" % len(mod.CARDS))
    check([n for n, _ in mod.CARDS] == [f[:-4] for f in CARD_FILES],
          "CARDS 名与 CARD_FILES 不同构: %s" % [n for n, _ in mod.CARDS])
    for fn_name in ("card1_cover", "card2_question", "card3_views", "card4_script1",
                    "card5_script2", "card6_script3", "card7_close"):
        check(callable(getattr(mod, fn_name, None)), "缺卡函数 %s" % fn_name)
    for fn_name in ("card8_extra", "card0_brand"):
        check(not hasattr(mod, fn_name), "出现第 8/第 0 张卡函数 %s（v3 恰好七卡）" % fn_name)
    card_fns = sorted(n for n in dir(mod) if n.startswith("card") and callable(
        getattr(mod, n)))
    check(card_fns == ["card1_cover", "card2_question", "card3_views", "card4_script1",
                       "card5_script2", "card6_script3", "card7_close"],
          "卡函数清单非 v3 七卡: %s" % (card_fns,))
    # --- 页脚 NN/07（无装饰横线：源码里 footer 不画 line）
    check(mod.FOOTER_SIZE == 28, "页脚字号 %s ≠ 28" % mod.FOOTER_SIZE)
    check(mod.HEADER_WORDMARK_SIZE == 28, "内页字标 %s ≠ 28" % mod.HEADER_WORDMARK_SIZE)
    # --- 卡 01 封面
    check(mod.COVER_ZONE == (240, 1240), "COVER_ZONE=%s ≠ (240,1240)" % (mod.COVER_ZONE,))
    check(mod.COVER_PAD_X == 44 and mod.COVER_PAD_Y == 20,
          "封面内边距 %s/%s ≠ 44/20" % (mod.COVER_PAD_X, mod.COVER_PAD_Y))
    check(mod.COVER_SUB_GAP == 76, "副标间距 %s ≠ 76" % mod.COVER_SUB_GAP)
    check(mod.COVER_SUB == "把最影响得分的地方找出来", "副标文案漂移: %s" % mod.COVER_SUB)
    # --- 卡 02 题目
    check(mod.Q_LABEL_Y == 300, "Q_LABEL_Y=%s ≠ 300" % mod.Q_LABEL_Y)
    # --- 卡 03 答题思路
    check(mod.SQ_SIZE == 40, "编号方块 %s ≠ 40" % mod.SQ_SIZE)
    check(mod.SQ_NUM_SIZE == 24, "方块内数字 %s ≠ 24" % mod.SQ_NUM_SIZE)
    check(mod.SQ_GAP == 20, "方块内边距 %s ≠ 20" % mod.SQ_GAP)
    check(mod.VIEW_GAP == 30, "观点间距 %s ≠ 30" % mod.VIEW_GAP)
    # --- 卡 04/05/06 逐字稿
    check(mod.SCRIPT_ZONE_TOP == 176, "正文顶 %s ≠ 176" % mod.SCRIPT_ZONE_TOP)
    check(mod.SCRIPT_LEAD_SIZE == mod.T_L2 == 56, "观点句 %s ≠ T_L2=56" % mod.SCRIPT_LEAD_SIZE)
    check(tuple(mod.SCRIPT_BODY_TIERS) == (44, 42),
          "正文降档表 %s ≠ (44,42)" % (mod.SCRIPT_BODY_TIERS,))
    check(mod.SCRIPT_LEAD_SIZE >= mod.SCRIPT_BODY_TIERS[0],
          "观点句 %s < 正文首档 %s" % (mod.SCRIPT_LEAD_SIZE, mod.SCRIPT_BODY_TIERS[0]))
    check(mod.LEAD_BODY_GAP == 26, "观点句-正文间距 %s ≠ 26" % mod.LEAD_BODY_GAP)
    check(mod.PARA_BODY_GAP == 34, "段间距 %s ≠ 34" % mod.PARA_BODY_GAP)
    check(mod.SCRIPT_NOTE_Y == 1252, "徽标 y=%s ≠ 1252" % mod.SCRIPT_NOTE_Y)
    check(mod.GROUP_GAP == 56, "观点组间距 %s ≠ 56" % mod.GROUP_GAP)
    check(list(mod.SCRIPT_PAGE_LABELS) == ["逐字稿 1/3", "逐字稿 2/3", "逐字稿 3/3"],
          "逐字稿页标漂移: %s" % (mod.SCRIPT_PAGE_LABELS,))
    for gone in ("SCRIPT_BODY_SIZE", "SCRIPT_TIERS", "OUTLINE_TIERS",
                 "QUESTION_TIERS", "CAPSULE_TEXT_SIZE", "SQ_STEP"):
        check(not hasattr(mod, gone), "v1 档位常量 %s 仍存在" % gone)
    # --- 卡 07 收尾引流
    check(mod.GOLDEN_MAX == 60, "金句字数上限 %s ≠ 60" % mod.GOLDEN_MAX)
    check(mod.GOLDEN_ZONE == (260, 1086), "GOLDEN_ZONE=%s ≠ (260,1086)" % (mod.GOLDEN_ZONE,))
    check(mod.GOLDEN_CLOSING_GAP == 56, "金句-收尾间距 %s ≠ 56" % mod.GOLDEN_CLOSING_GAP)
    check(mod.CTA_H == 120, "CTA 高 %s ≠ 120" % mod.CTA_H)
    check(mod.CTA_Y == 1150, "CTA 顶 %s ≠ 1150" % mod.CTA_Y)
    check(mod.CTA_Y + mod.CTA_H < mod.ZONE_BOT,
          "CTA 底 %s 越过 ZONE_BOT=%s" % (mod.CTA_Y + mod.CTA_H, mod.ZONE_BOT))
    for gone in ("GOLDEN_TIERS", "GOLDEN_CENTER_Y"):
        check(not hasattr(mod, gone), "v1 金句常量 %s 仍存在" % gone)
    check("答一道" in mod.CTA_MAIN and "每日一练" in mod.CTA_MAIN,
          "CTA 主行文案漂移: %s" % mod.CTA_MAIN)
    check("把最影响得分的地方找出来" in mod.BRAND_SLOGAN,
          "CTA 副行文案漂移: %s" % mod.BRAND_SLOGAN)
    # --- 笔记标签
    for tag in ("#结构化面试", "#公考面试", "#答题思路", "#每日一练", "#上岸"):
        check(tag in mod.NOTE_TAGS, "缺固定标签 %s" % tag)
    check(mod.NOTE_GUIDE == "想要完整逐字稿，评论区打「1」", "引导语漂移: %s" % mod.NOTE_GUIDE)
    # --- 金句源：opening 末句（逐字子串，v3 不带句号）
    g = mod.opening_golden(SAMPLE)
    check(g == "业务停半天能补，人出了事补不回来", "金句源不符: %r" % g)
    check(g in SAMPLE["opening"], "金句非 opening 逐字子串")
    check(not g.endswith("。"), "v3 金句不应带句号: %r" % g)
    check(mod.opening_golden({"opening": "", "closing": "答案落地。答题完毕。"})
          == "答案落地。", "空 opening 未回退 closing")
    at_max = "超" * mod.GOLDEN_MAX
    check(mod.opening_golden({"opening": "首句铺垫。" + at_max + "。",
                              "closing": "回退句。"}) == at_max,
          "恰好 GOLDEN_MAX(%s) 字的末句应被采用（边界值）" % mod.GOLDEN_MAX)
    check(mod.opening_golden({"opening": "首句铺垫。" + "超" * (mod.GOLDEN_MAX + 1) + "。",
                              "closing": "回退句。"}) == "回退句。",
          "超 GOLDEN_MAX 字的末句未回退 closing")
    check(mod.GOLDEN_MAX == 60, "GOLDEN_MAX=%s ≠ 60" % mod.GOLDEN_MAX)
    check(mod.opening_golden({"opening": "只有一句完整的话。", "closing": "回退句。"})
          == "只有一句完整的话", "单句 opening 末句取错")
    # --- 金句两行均衡重排：只重排不增删字、行宽不超限
    from PIL import ImageDraw
    d2 = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    q = "业务停半天能补，人出了事补不回来"
    bl = mod._balanced_lines(d2, q, mod.F_BOLD(52), 820)
    check("".join(bl) == q, "均衡重排丢字: %r" % (bl,))
    check(len(bl) == 2 and abs(len(bl[0]) - len(bl[1])) <= 2,
          "两行未均衡: %r" % (bl,))
    check(all(mod.tw(d2, ln, mod.F_BOLD(52)) <= 820 for ln in bl),
          "均衡行超宽: %r" % (bl,))
    check(mod._balanced_lines(d2, "一句话。", mod.F_BOLD(52), mod.TX_W)
          == ["一句话。"], "单行金句被重排")
    # --- 笔记标题从 break_angle 提炼
    title = mod.make_note_title(SAMPLE, TOPIC)
    check(title == "政务大厅断电，先查人、后修电", "笔记标题漂移: %r" % title)
    check(len(title) <= 20, "笔记标题 %s 字超 20: %r" % (len(title), title))
    # --- 卡 06 徽标文案（字数/时长）
    badge = mod.script_badge(SAMPLE)
    check(badge.startswith("全文 ") and "字" in badge and "秒" in badge,
          "script_badge 文案异常: %r" % badge)
    # --- 缺一不可：字体与 logo 资产声明
    check(Path(mod.FONT_DIR).is_dir(), "字体目录不存在: %s" % mod.FONT_DIR)
    check(Path(mod.LOGO_PATH).is_file(), "品牌 logo 不存在: %s" % mod.LOGO_PATH)


# --------------------------------------------------------------------------
# 13. 字号梯
# --------------------------------------------------------------------------
@case("case_scale_ladder", "字号梯：六档单调 + 相邻比 1.25–1.6 + 正文硬下限 42")
def case_scale_ladder(check):
    mod = load_mod()
    ladder = [("T_L0", mod.T_L0), ("T_L1", mod.T_L1), ("T_L2", mod.T_L2),
              ("T_L3", mod.T_L3), ("T_L4", mod.T_L4), ("T_L5", mod.T_L5)]
    values = [v for _, v in ladder]
    check(values == sorted(values, reverse=True),
          "字号梯非单调递减: %s" % (ladder,))
    check(len(set(values)) == len(values), "字号梯存在重复档: %s" % (values,))
    pairs = [("T_L0/T_L1", mod.T_L0, mod.T_L1), ("T_L1/T_L2", mod.T_L1, mod.T_L2),
             ("T_L2/T_L3", mod.T_L2, mod.T_L3), ("T_L3/T_L4", mod.T_L3, mod.T_L4),
             ("T_L4/T_L5", mod.T_L4, mod.T_L5)]
    for label, big, small in pairs:
        ratio = big / float(small)
        check(1.25 - 1e-6 <= ratio <= 1.6 + 1e-6,
              "%s 相邻比 %.4f 不在 [1.25, 1.6]（%s→%s）" % (label, ratio, big, small))
    check(mod.T_L3 >= 42, "正文档 T_L3=%s < 42 硬下限" % mod.T_L3)
    check(mod.T_L3_MIN >= 42, "正文最低档 T_L3_MIN=%s < 42 硬下限" % mod.T_L3_MIN)
    check(mod.T_L3_MIN <= mod.T_L3, "T_L3_MIN=%s 大于 T_L3=%s" % (mod.T_L3_MIN, mod.T_L3))
    check(mod.T_L0 >= 132, "封面主档 T_L0=%s < 132" % mod.T_L0)
    check(mod.T_L0_MIN >= 84, "封面下限档 T_L0_MIN=%s < 84（低于内页 L1）" % mod.T_L0_MIN)
    check(mod.T_L0_MIN <= mod.T_L0, "T_L0_MIN=%s 大于 T_L0=%s" % (mod.T_L0_MIN, mod.T_L0))
    check(76 <= mod.T_L1 <= 88, "分节标题 T_L1=%s 不在 76..88" % mod.T_L1)
    check(28 <= mod.T_L5 <= 30, "微标 T_L5=%s 不在 28..30（标签底线 28）" % mod.T_L5)
    check(mod.SCRIPT_BODY_TIERS[-1] >= 42,
          "逐字稿最低档 %s < 42 硬下限" % (mod.SCRIPT_BODY_TIERS[-1],))
    check(mod.SCRIPT_BODY_TIERS[0] <= mod.T_L3,
          "逐字稿首档 %s 超过 T_L3=%s（正文不得大于统一正文档）"
          % (mod.SCRIPT_BODY_TIERS[0], mod.T_L3))
    # 行高：封面/标题紧、正文松，且都为合理值
    for name, lh in (("LH_COVER", mod.LH_COVER), ("LH_TITLE", mod.LH_TITLE),
                     ("LH_QUOTE", mod.LH_QUOTE), ("LH_BODY", mod.LH_BODY),
                     ("LH_NOTE", mod.LH_NOTE), ("LH_MICRO", mod.LH_MICRO)):
        check(1.0 < lh <= 1.7, "%s=%s 越出 (1.0, 1.7]" % (name, lh))
    check(mod.LH_COVER < mod.LH_BODY and mod.LH_TITLE < mod.LH_BODY,
          "正文行高 %.2f 未大于封面/标题行高 %.2f/%.2f"
          % (mod.LH_BODY, mod.LH_COVER, mod.LH_TITLE))
    check(mod.LH_MICRO <= mod.LH_NOTE,
          "微标行高 %.2f 应不比注行高 %.2f 更松" % (mod.LH_MICRO, mod.LH_NOTE))


# --------------------------------------------------------------------------
# 14. 旧版残留清理
# --------------------------------------------------------------------------
@case("case_residue_cleanup", "旧版残留清理：v1 残留 png 被删，目录只剩 7 图")
def case_residue_cleanup(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        root, final_path = make_sandbox(tmpdir, progress={"done": ["demo-009"]})
        outdir = issue_dir(root, "002")
        outdir.mkdir(parents=True)
        # v1 六卡残留：04-逐字稿上 / 06-收尾引流（v3 已改名/移位）
        for stale in ("04-逐字稿上.png", "06-收尾引流.png"):
            Image.new("RGB", (1080, 1440), BG).save(outdir / stale)
        (outdir / "笔记文案.md").write_text("v1 旧文案", encoding="utf-8")
        rc, out = run_render(root, final_path, extra=["--outdir", str(outdir)])
        check(rc == 0, "exit=%s out=%s" % (rc, out[-400:]))
        check("清理旧版残留" in out, "未打印清理回执: %s" % out[-400:])
        check("04-逐字稿上.png" in out, "未指出 04-逐字稿上.png 残留")
        check("06-收尾引流.png" in out, "未指出 06-收尾引流.png 残留")
        check(not (outdir / "04-逐字稿上.png").exists(), "v1 残留 04-逐字稿上 未被删除")
        check(not (outdir / "06-收尾引流.png").exists(), "v1 残留 06-收尾引流 未被删除")
        pngs = sorted(p.name for p in outdir.glob("*.png"))
        check(pngs == sorted(CARD_FILES), "清理后 png 集合 %s ≠ 7 图" % (pngs,))
        check(len(pngs) == 7, "清理后仍有 %s 张 png" % len(pngs))
        check((outdir / "笔记文案.md").is_file(), "笔记文案.md 未生成")
        txt = (outdir / "笔记文案.md").read_text(encoding="utf-8")
        check("v1 旧文案" not in txt, "笔记文案.md 未被覆盖")
        check("共 7 张" in txt, "新笔记未按 v3 口径写 7 张")


# --------------------------------------------------------------------------
# 15. --outdir 期号复用 + 幂等
# --------------------------------------------------------------------------
@case("case_outdir_reuse_issue", "--outdir 期号复用不推进 progress（幂等）；无 outdir 才顺延")
def case_outdir_reuse_issue(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        root, final_path = make_sandbox(tmpdir, progress={"done": ["demo-009"]})
        outdir = issue_dir(root, "002")
        outdir.mkdir(parents=True)
        # 第一次：带 --outdir 指向 第002期 → 目录名沿用 002，progress 仍追加 qid
        rc, out = run_render(root, final_path, extra=["--outdir", str(outdir)])
        check(rc == 0, "exit=%s out=%s" % (rc, out[-400:]))
        check("第002期" in out, "回执期号不是 002: %s" % out[-200:])
        check(not issue_dir(root, "003").exists(), "带 outdir 时不应另建第003期")
        names = sorted(p.name for p in (Path(root) / "图片输出").iterdir())
        check(names == ["progress_answer.json", f"第002期-{TYPE}-{TOPIC}"],
              "图片输出/ 下出现了多余条目: %s" % (names,))
        data = json.loads(progress_path(root).read_text(encoding="utf-8"))
        check(data.get("done") == ["demo-009", "yj-01"],
              "首次渲染后 done=%r（应追加 yj-01）" % data.get("done"))
        # 第二次：同一 outdir 再渲染 → 幂等，qid 不重复追加
        rc, out = run_render(root, final_path, extra=["--outdir", str(outdir)])
        check(rc == 0, "二次渲染 exit=%s out=%s" % (rc, out[-300:]))
        check("不重复追加" in out, "二次渲染未提示幂等跳过: %s" % out[-300:])
        data2 = json.loads(progress_path(root).read_text(encoding="utf-8"))
        check(data2.get("done") == ["demo-009", "yj-01"],
              "二次渲染后 done=%r（应保持 2 条）" % data2.get("done"))
        # 第三次：不带 outdir → 期号顺延到 003，且 done 不重复
        rc, out = run_render(root, final_path)
        check(rc == 0, "无 outdir 渲染 exit=%s out=%s" % (rc, out[-300:]))
        check(issue_dir(root, "003").is_dir(), "无 outdir 时未顺延到第003期")
        data3 = json.loads(progress_path(root).read_text(encoding="utf-8"))
        check(data3.get("done") == ["demo-009", "yj-01"],
              "顺延渲染后 done=%r（qid 不应重复）" % data3.get("done"))


# --------------------------------------------------------------------------
def main() -> int:
    keys = sys.argv[1:]
    selected = [c for c in CASES
                if not keys or any(k in (c[0] + " " + c[1]) for k in keys)]
    if keys:
        if not selected:
            print("筛选 %r 未命中任何用例（禁止假绿）" % (keys,), file=sys.stderr)
            return 1
        print("[NOTE] 筛选运行：%s/%s 用例（子集，非全量）\n"
              % (len(selected), len(CASES)))
    elif len(CASES) < MIN_CASES:
        print("用例数 %s < 下限 %s（框架被破坏/用例被删，本套件须全量运行）"
              % (len(CASES), MIN_CASES), file=sys.stderr)
        return 1

    failures = []
    for cid, title, fn in selected:
        problems = []

        def check(ok, message, _problems=problems):
            if not ok:
                _problems.append(message)

        try:
            fn(check)
        except Exception as exc:  # 用例自身崩了也算 FAIL，不许静默跳过
            problems.append("用例异常: %s: %s" % (type(exc).__name__, exc))
        status = "PASS" if not problems else "FAIL"
        print(f"[{status}] {cid} — {title}")
        for problem in problems:
            print(f"  - {problem}")
        if problems:
            failures.append(cid)

    passed = len(selected) - len(failures)
    print(f"\n{passed}/{len(selected)} 用例通过")
    if failures:
        print("失败用例：%s" % "、".join(failures), file=sys.stderr)
        return 1
    if keys:
        print("✅ 筛选子集全部通过（%s 条）" % len(selected))
    else:
        print("✅ 全部 %s 用例通过（v3 七卡口径）" % passed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_render_answer_cards —— render_answer_cards.py（答一道 6 卡图片产线）回归测试（沙箱）。

运行：python3 scripts/test_render_answer_cards.py
- 全 11 用例全过 exit 0；任一失败或用例数 <11 → exit 1（不允许假绿，筛选不中即失败）。
- 沙箱纪律：全程只写系统临时目录；final 样本为 TR2 draft_yj-01_final.json 的内嵌只读副本；
  不触碰真实 vault（图片输出/progress 仅在首期实跑时由人工执行，不入本测试）。
- 覆盖 11 用例：黄金路径全契约（exit0 / 6 PNG 1080×1440 / 目录命名 / 笔记文案含标签 /
  progress done 追加 / TR4.1 右上角期数徽章已删（旧徽章区域纯米底）/ 页脚全卡存在
  （页脚带非米白像素>阈值，修复轮 1 C1 回归）/ 逐字稿 40/36 设计档 /
  删徽章后 --check 通过）/ 期号递增（已有 1 条 done → 第002期）/ 题干 80 字硬上限内仍可渲染 /
  超高 FAIL exit 非0 指出卡片且不写进度 / 缺字体 monkeypatch STOP / 缺 logo monkeypatch
  STOP / --check 通过与失败两路径 / wrap_text 只折行不截断+避头标点 / outdir 越界拒绝 /
  封面主题超长显式 FAIL（TR5.1 君上裁决）/
  TR4.1 版式常量断言（逐字稿正文≥36、标签≥28、编号方块≤26、档位表自洽）。
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

MIN_CASES = 11

C5_BG = (255, 248, 236)   # TR5 米白底 #fff8ec
# 内页右上角无徽章区（TR4.1 删徽章；TR5 封面右上为指定「第 N 期 · 题型」灰标签，豁免）：
# 卡 02-06 该区域必须为纯米白，一个杂色像素都不许有。
BADGE_REGION = (640, 84, 1024, 144)
# TR5.1 封面 C2 居中大字版三带：主题（h1_y=544 起 100px）、金短线（line_y=714，120×6）、
# slogan（784 起 30px）——坐标由 card1_cover 布局推导
H1_REGION = (100, 540, 980, 660)
GOLDLINE_REGION = (470, 705, 610, 730)
SLOGAN_REGION = (150, 775, 930, 830)
# TR5 卡 06 枣红 CTA 条（贴页脚上方）：CTA_Y=1150、高 140、宽 84–996
CTA_REGION = (84, 1150, 996, 1290)
# 页脚存在性断言区（C1 回归）：页脚带必须含发丝线＋系列名＋页码（非米白像素 >1000）。
FOOTER_REGION = (60, 1300, 1020, 1420)

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

CARD_FILES = ["01-封面.png", "02-题目.png", "03-答题思路.png",
              "04-逐字稿上.png", "05-逐字稿下.png", "06-收尾引流.png"]
TYPE = "应急应变"
TOPIC = "政务大厅断电"


def load_mod():
    """进程内加载渲染引擎模块（供 monkeypatch 常量用例）。"""
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


CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


@case("golden 黄金路径全契约（6 PNG/尺寸/命名/文案/进度/删徽章/40-36 档/--check）")
def case_golden(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        root, final_path = make_sandbox(tmpdir)
        rc, out = run_render(root, final_path)
        check(rc == 0, "exit=%s out=%s" % (rc, out[-400:]))
        check("✅" in out, "无成功标记")
        check("档位 lead/body = 40/36" in out, "逐字稿未落在 40/36 设计档: %s" % out[-300:])
        outdir = issue_dir(root, "001")
        check(outdir.is_dir(), "期目录未生成: %s" % outdir)
        for idx, name in enumerate(CARD_FILES):
            p = outdir / name
            check(p.is_file(), "缺图: %s" % name)
            if not p.is_file():
                continue
            im = Image.open(p).convert("RGB")
            check(im.size == (1080, 1440), "%s 尺寸=%s" % (name, im.size))
            # TR5 米白底：四角必须为米白
            corners = [im.getpixel(xy) for xy in
                       ((12, 12), (1067, 12), (12, 1427), (1067, 1427))]
            check(all(c == C5_BG for c in corners),
                  "%s 四角非米白: %s" % (name, corners))
            if idx == 0:
                # TR5 封面右上「第 N 期 · 题型」28px 灰标签须存在
                region = im.crop(BADGE_REGION)
                non = sum(c for c, col in region.getcolors(maxcolors=1_000_000)
                          if col != C5_BG)
                check(non > 150, "封面右上期数标签缺失: 非米白像素 %s" % non)
                # TR5.1 居中大字版三带断言：主题墨色/金短线/slogan 灰
                h1 = im.crop(H1_REGION)
                ink = sum(c for c, col in h1.getcolors(maxcolors=1_000_000)
                          if max(abs(col[0] - 39), abs(col[1] - 30),
                                 abs(col[2] - 27)) < 60)
                check(ink > 5000, "封面居中主标题缺失（墨色像素 %s）" % ink)
                gl = im.crop(GOLDLINE_REGION)
                gold = sum(c for c, col in gl.getcolors(maxcolors=1_000_000)
                           if max(abs(col[0] - 227), abs(col[1] - 199),
                                  abs(col[2] - 159)) < 30)
                check(gold > 400, "封面金短线缺失（金色像素 %s）" % gold)
                sl = im.crop(SLOGAN_REGION)
                graypx = sum(c for c, col in sl.getcolors(maxcolors=1_000_000)
                             if max(abs(col[0] - 117), abs(col[1] - 103),
                                    abs(col[2] - 95)) < 60)
                check(graypx > 500, "封面 slogan 缺失（灰像素 %s）" % graypx)
                # 主标题居中：墨色最左/最右像素近似对称于版心中线
                xs = [x for x in range(H1_REGION[0], H1_REGION[2])
                      for y in (590, 610)
                      if max(abs(im.getpixel((x, y))[0] - 39),
                             abs(im.getpixel((x, y))[1] - 30),
                             abs(im.getpixel((x, y))[2] - 27)) < 60]
                if xs:
                    mid = (min(xs) + max(xs)) / 2
                    check(abs(mid - 540) <= 40, "主标题未居中（墨色中心 %.0f ≠ 540）" % mid)
            else:
                # TR4.1 删徽章（内页沿用）：右上角区域纯米白
                region = im.crop(BADGE_REGION)
                colors = region.getcolors(maxcolors=1_000_000)
                check(colors == [(region.size[0] * region.size[1], C5_BG)],
                      "%s 右上角仍有非米白像素: %s" % (name, colors[:3]))
            # C1 回归：页脚带（发丝线+系列名+页码）全卡必须存在
            band = im.crop(FOOTER_REGION)
            non_bg = sum(c for c, col in band.getcolors(maxcolors=1_000_000)
                         if col != C5_BG)
            check(non_bg > 1000,
                  "%s 页脚带非米白像素 %s ≤1000（页脚缺失?）" % (name, non_bg))
        # TR5.2 卡 06：金句文字块垂直中心 ≈710（画布水平中线附近）；方印已删
        c6 = Image.open(outdir / CARD_FILES[5]).convert("RGB")
        ys = []
        for y in range(300, 1100, 2):
            strip = c6.crop((150, y, 930, y + 2))
            cnt = sum(c for c, col in strip.getcolors(maxcolors=1_000_000)
                      if max(abs(col[0] - 39), abs(col[1] - 30),
                             abs(col[2] - 27)) < 60)
            if cnt > 20:
                ys.append(y)
        check(ys, "卡 06 金句墨色缺失（标题下～CTA 上无正文墨色）")
        if ys:
            center = (ys[0] + ys[-1]) / 2 + 1
            check(700 <= center <= 726,
                  "金句垂直中心 %.0f 不在中线附近 700-720" % center)
        # 原方印区（右中，x≈886–1010 / y≈760–1000）必须纯米白（方印整块移除）
        seal_zone = c6.crop((900, 756, 1015, 1000))
        colors = seal_zone.getcolors(maxcolors=1_000_000)
        check(colors == [(seal_zone.size[0] * seal_zone.size[1], C5_BG)],
              "卡 06 右中方印区仍有非米白像素（方印未删净?）: %s" % colors[:3])
        # TR5 CTA 保留断言（卡 06 枣红 CTA 条贴页脚上方）
        cta = c6.crop(CTA_REGION)
        crim = sum(c for c, col in cta.getcolors(maxcolors=1_000_000)
                   if max(abs(col[0] - 135), abs(col[1] - 17), abs(col[2] - 15)) < 60)
        check(crim >= (CTA_REGION[2] - CTA_REGION[0]) * (CTA_REGION[3] - CTA_REGION[1]) * 0.5,
              "卡 06 CTA 条枣红像素不足: %s" % crim)
        note = outdir / "笔记文案.md"
        check(note.is_file(), "缺 笔记文案.md")
        if note.is_file():
            txt = note.read_text(encoding="utf-8")
            check("#结构化面试" in txt, "缺固定标签 #结构化面试")
            check(f"#{TYPE}" in txt, "缺题型标签 #%s" % TYPE)
            check("评论区打「1」" in txt, "缺固定引导")
            check("政务大厅断电，先查人、后修电" in txt, "标题未从 break_angle 提炼")
        prog = Path(root) / "图片输出" / "progress_answer.json"
        check(prog.is_file(), "progress_answer.json 未生成")
        if prog.is_file():
            data = json.loads(prog.read_text(encoding="utf-8"))
            check(data.get("done") == ["yj-01"], "done=%r" % data.get("done"))
        # TR4.1：删徽章后 --check 仍通过（封面/内页两套 logo 校验框）
        rc2, out2 = run_check(root, outdir)
        check(rc2 == 0, "删徽章后 --check 未通过: exit=%s out=%s" % (rc2, out2[-200:]))


@case("期号递增（progress 已有 1 条 done → 第002期）")
def case_issue_increment(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        root, final_path = make_sandbox(tmpdir, progress={"done": ["demo-009"]})
        rc, out = run_render(root, final_path)
        check(rc == 0, "exit=%s out=%s" % (rc, out[-300:]))
        check(issue_dir(root, "002").is_dir(), "第002期目录未生成")
        prog = Path(root) / "图片输出" / "progress_answer.json"
        data = json.loads(prog.read_text(encoding="utf-8"))
        check(data.get("done") == ["demo-009", "yj-01"], "done=%r" % data.get("done"))


@case("题干 80 字硬上限内仍可渲染（TR4.2 卡上移后不截断）")
def case_long_question(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        final = dict(SAMPLE)
        # SKILL.md 题干硬上限 80 字；TR4.2 卡 02 白卡下界收到 ~780，超长题干
        # 在中线上方放不下（引擎按只折行不截断契约 FAIL，见下一用例）
        final["question"] = (SAMPLE["question"].rstrip("？")
                             + "现场群众情绪激动，有人拍摄发帖，话题开始发酵，你怎么办？")
        check(len(final["question"]) <= 80, "题干超 80 字上限: %s" % len(final["question"]))
        root, final_path = make_sandbox(tmpdir, final=final)
        rc, out = run_render(root, final_path)
        check(rc == 0, "exit=%s out=%s" % (rc, out[-300:]))
        outdir = issue_dir(root, "001")
        for name in CARD_FILES:
            check((outdir / name).is_file(), "缺图: %s" % name)


@case("超高 FAIL exit 非0 指出卡片且不写进度")
def case_overflow_fail(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        final = dict(SAMPLE)
        final["question"] = SAMPLE["question"].rstrip("？") * 90 + "？"
        root, final_path = make_sandbox(tmpdir, final=final)
        rc, out = run_render(root, final_path)
        check(rc != 0, "超高未 FAIL，exit=%s" % rc)
        check("02-题目" in out, "未指出卡片: %s" % out[-200:])
        prog = Path(root) / "图片输出" / "progress_answer.json"
        check(not prog.is_file(), "失败却写了进度")
        check(not issue_dir(root, "001").exists(), "失败却留了期目录")


@case("缺字体 monkeypatch FONT_DIR → STOP exit 非0")
def case_no_font(check):
    mod = load_mod()
    real = mod.FONT_DIR
    mod.FONT_DIR = "/nonexistent_tr4_fonts"
    try:
        with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
            root, final_path = make_sandbox(tmpdir)
            sys.argv = ["render_answer_cards.py", "--project-root", str(root),
                        "--final", str(final_path), "--type", TYPE, "--topic", TOPIC]
            try:
                mod.main()
                code, msg = 0, ""
            except SystemExit as e:
                # SystemExit 带消息串 = 解释器以非零码退出并打印消息，同样算 STOP
                code, msg = e.code, str(e)
            check(code not in (0, None), "exit=%r" % code)
            check("字体缺失" in msg, "未报字体缺失: %s" % msg)
            check(not (Path(root) / "图片输出" / "progress_answer.json").exists(),
                  "STOP 却写了进度")
    finally:
        mod.FONT_DIR = real


@case("缺 logo monkeypatch LOGO_PATH → STOP exit 非0")
def case_no_logo(check):
    mod = load_mod()
    real = mod.LOGO_PATH
    mod.LOGO_PATH = "/nonexistent_tr4/logo-zfz.png"
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
            check("logo 缺失" in msg, "未报 logo 缺失: %s" % msg)
            check(not (Path(root) / "图片输出" / "progress_answer.json").exists(),
                  "STOP 却写了进度")
    finally:
        mod.LOGO_PATH = real


@case("--check 通过/失败两路径")
def case_check_paths(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        root, final_path = make_sandbox(tmpdir)
        rc, out = run_render(root, final_path)
        check(rc == 0, "前置渲染失败 exit=%s" % rc)
        outdir = issue_dir(root, "001")
        rc, out = run_check(root, outdir)
        check(rc == 0, "--check 应通过: exit=%s out=%s" % (rc, out[-200:]))
        # 失败路径一：logo 区域被清成米底 → 占比不达标
        Image.new("RGB", (1080, 1440), (251, 246, 237)).save(outdir / CARD_FILES[0])
        rc, out = run_check(root, outdir)
        check(rc != 0, "logo 被清空后 --check 仍通过")
        # 失败路径二：缺图
        (outdir / CARD_FILES[5]).unlink()
        rc, out = run_check(root, outdir)
        check(rc != 0, "缺图后 --check 仍通过")
        check("缺文件" in out, "未报缺文件")


@case("wrap_text 只折行不截断 + 避头标点 + require_glyph 机制")
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
    # require_glyph 机制回归（TR4.4 删对照条断言后保留工具层自检）：
    # 缺字形符号（bbox 高 0，如 ✗/✓ 或任何字体缺字字符）渲染即空白，必须拦截。
    real_gh = mod.glyph_height
    mod.glyph_height = lambda s, f: 0  # monkeypatch 模拟缺字形
    try:
        try:
            mod.require_glyph(mod.F_MED(26), "字")
            raised = False
        except SystemExit:
            raised = True
        check(raised, "require_glyph 未拦截零高字形")
    finally:
        mod.glyph_height = real_gh


@case("outdir 越界拒绝（须在 图片输出/ 内）")
def case_outdir_escape(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        root, final_path = make_sandbox(tmpdir)
        outside = Path(tmpdir) / "outside"
        rc, out = run_render(root, final_path, extra=["--outdir", str(outside)])
        check(rc != 0, "越界 outdir 未拒绝 exit=%s" % rc)
        check("不在" in out, "未报越界: %s" % out[-200:])
        check(not outside.exists(), "越界目录被创建")


@case("封面主题超长 → 显式 FAIL 不出图（TR5.1 君上裁决）")
def case_cover_topic_overflow(check):
    with tempfile.TemporaryDirectory(prefix="render_answer_test_") as tmpdir:
        root, final_path = make_sandbox(tmpdir)
        long_topic = "政务" * 9  # 18 字：60px 下限档（18×68=1224）远超可用宽 912
        rc, out = run_render(root, final_path, extra=["--topic", long_topic])
        check(rc != 0, "超长主题未 FAIL exit=%s" % rc)
        check("封面主题超长" in out, "未报主题超长: %s" % out[-300:])
        check(str(len(long_topic)) in out, "报错未指明主题字数: %s" % out[-300:])
        check(not issue_dir(root, "001").exists(), "失败却留了期目录")
        prog = Path(root) / "图片输出" / "progress_answer.json"
        check(not prog.is_file(), "失败却写了进度")


@case("TR4.1 版式常量断言（逐字稿正文≥36/标签≥28/方块≤26/档位自洽）")
def case_layout_constants(check):
    mod = load_mod()
    # 逐字稿卡：正文达 huashu 底线 36px，lead ≥ 正文
    check(mod.SCRIPT_BODY_SIZE >= 36, "SCRIPT_BODY_SIZE=%s < 36" % mod.SCRIPT_BODY_SIZE)
    check(mod.SCRIPT_LEAD_SIZE >= mod.SCRIPT_BODY_SIZE,
          "lead %s < body %s" % (mod.SCRIPT_LEAD_SIZE, mod.SCRIPT_BODY_SIZE))
    # 标签底线 28px：页眉字标（内页）/页脚/来源描边胶囊（TR5：封面眉标已随 C 范式退役）
    check(mod.HEADER_WORDMARK_SIZE >= 28, "内页字标 %s < 28" % mod.HEADER_WORDMARK_SIZE)
    check(mod.FOOTER_SIZE >= 28, "页脚 %s < 28" % mod.FOOTER_SIZE)
    check(mod.CAPSULE_TEXT_SIZE >= 28, "来源胶囊 %s < 28" % mod.CAPSULE_TEXT_SIZE)
    # 观点编号方块 26px（清单同构，TR4.1 起）
    check(mod.SQ_SIZE == 26, "观点编号方块 %s ≠ 26" % mod.SQ_SIZE)
    # 君上裁定（修复轮 1）：卡 03 观点正文 30px 长期口径＝清单条目按标签底线 ≥28px，
    # 降档表各档 vw 均不得下穿 28
    check(min(t[4] for t in mod.OUTLINE_TIERS) >= 28,
          "卡 03 观点正文降档下穿 28px 标签底线: %r" % (mod.OUTLINE_TIERS,))
    # 档位表自洽：首档=设计档且逐档递减（自动降档只降不升）
    check(mod.SCRIPT_TIERS[0] == (mod.SCRIPT_LEAD_SIZE, mod.SCRIPT_BODY_SIZE),
          "逐字稿首档 %r ≠ 设计档 (%s, %s)"
          % (mod.SCRIPT_TIERS[0], mod.SCRIPT_LEAD_SIZE, mod.SCRIPT_BODY_SIZE))
    leads = [t[0] for t in mod.SCRIPT_TIERS]
    bodies = [t[1] for t in mod.SCRIPT_TIERS]
    check(leads == sorted(leads, reverse=True) and bodies == sorted(bodies, reverse=True),
          "降档表非单调递减: %r" % (mod.SCRIPT_TIERS,))
    # 各卡设计档（TR5）：题干 40 / 观点正文 32 起排 / 金句 52 起排 / 内页标题 44 枣红
    check(mod.QUESTION_TIERS[0] == 40, "题干首档 %s ≠ 40" % mod.QUESTION_TIERS[0])
    check(mod.OUTLINE_TIERS[0][4] == 32, "观点正文首档 %s ≠ 32" % mod.OUTLINE_TIERS[0][4])
    check(mod.GOLDEN_TIERS[0] == 52, "金句首档 %s ≠ 52" % mod.GOLDEN_TIERS[0])
    check(mod.GOLDEN_CENTER_Y == 710, "金句垂直中心 %s ≠ 710（TR5.2 中线附近）"
          % mod.GOLDEN_CENTER_Y)
    check(mod.CTA_H == 140, "CTA 条高 %s ≠ 140" % mod.CTA_H)
    # TR4.4 金句换源：opening 末句（逐字子串），超长/空回退 closing（去「答题完毕」）
    g = mod.opening_golden(SAMPLE)
    check(g == "业务停半天能补，人出了事补不回来。", "金句源不符: %r" % g)
    check(g in SAMPLE["opening"], "金句非 opening 逐字子串")
    check(mod.opening_golden({"opening": "", "closing": "答案落地。答题完毕。"})
          == "答案落地。", "空 opening 未回退 closing/未去口播标记")
    long_open = "首句铺垫。" + "超" * 60 + "。"
    check(mod.opening_golden({"opening": long_open, "closing": "回退句。"})
          == "回退句。", "超 60 字末句未回退 closing")
    check(mod.opening_golden({"opening": "只有一句完整的话。", "closing": "回退句。"})
          == "只有一句完整的话。", "单句 opening 末句取错: %r"
          % mod.opening_golden({"opening": "只有一句完整的话。", "closing": "回退句。"}))
    # 打磨：金句两行均衡重排——只重排不增删字、行宽不超限
    #（TR5 边距 84 后本句 52px 在 912 宽下单行放得下，两行路径以 820 宽验证）
    from PIL import ImageDraw
    d2 = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    q = "业务停半天能补，人出了事补不回来。"
    bl = mod._balanced_lines(d2, q, mod.F_BOLD(52), 820)
    check("".join(bl) == q, "均衡重排丢字: %r" % (bl,))
    check(len(bl) == 2 and abs(len(bl[0]) - len(bl[1])) <= 2,
          "两行未均衡: %r" % (bl,))
    check(all(mod.tw(d2, ln, mod.F_BOLD(52)) <= 820 for ln in bl),
          "均衡行超宽: %r" % (bl,))
    check(mod._balanced_lines(d2, "一句话。", mod.F_BOLD(52), mod.TX_W)
          == ["一句话。"], "单行金句被重排")
    # TR5 C 留白版面：边距 84 全卡统一；内页标题 44 枣红；步骤方块 40px；米白底
    check(mod.TITLE_SIZE == 44, "内页标题 %s ≠ 44" % mod.TITLE_SIZE)
    check(mod.MARGIN == 84 and mod.TX_X == 84 and mod.TX_W == 912,
          "边距口径不符: %s/%s/%s" % (mod.MARGIN, mod.TX_X, mod.TX_W))
    check(mod.SQ_STEP == 40, "步骤编号方块 %s ≠ 40" % mod.SQ_STEP)
    check(mod.SQ_SIZE == 26, "观点编号方块 %s ≠ 26" % mod.SQ_SIZE)
    check(mod.BG == (255, 248, 236), "底色 %s ≠ 米白 #fff8ec" % (mod.BG,))


def main() -> int:
    selected = [entry for entry in CASES if not sys.argv[1:]
                or any(key in entry[0] for key in sys.argv[1:])]
    if len(selected) < MIN_CASES:
        print("用例数 %s < 下限 %s（筛选不中或框架坏，本套件须全量运行）"
              % (len(selected), MIN_CASES), file=sys.stderr)
        return 1

    failures = []
    for name, fn in selected:
        problems = []

        def check(ok, message, _problems=problems):
            if not ok:
                _problems.append(message)

        fn(check)
        status = "PASS" if not problems else "FAIL"
        print(f"[{status}] {name}")
        for problem in problems:
            print(f"  - {problem}")
        if problems:
            failures.append(name)

    passed = len(selected) - len(failures)
    print(f"\n{passed}/{len(selected)} 用例通过")
    if failures:
        print("失败用例：%s" % "、".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

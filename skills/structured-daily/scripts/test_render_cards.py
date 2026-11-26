#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_cards.py 回归测试：双模式、校验、导图、折行。

运行：python3 scripts/test_render_cards.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_cards as rc  # noqa: E402
from PIL import Image  # noqa: E402

MIN_CASES = 14

ANSWER = {
    "question": "科技产品展销会因下雨人少、商家不满，怎么做。",
    "title_prefix": "结构化历年考题：",
    "source": "真题库",
    "break_angle": "先安抚商家，会期内补救，会后给书面交代。",
    "break_angle_reason": "题干把人少和商家不满放在一起，只答引流等于答了一半。",
    "core_views_title": "核心观点",
    "core_views_intro": "按稳商家、拉人气、给交代排三步。",
    "core_views": ["先稳商家。", "线上线下一起引流。", "商家要的是实在交代。"],
    "opening": "雨一连下了两个小时，展位前的人流散了大半。",
    "point1_lead": "我和同事分头把展位走一遍。",
    "point1_body": "让商家把话说完，人流、销量、费用，一条条记下来。",
    "point2_lead": "接着线上线下一起引流。",
    "point2_body": "雨没停就主攻线上，雨一停线下马上加场。",
    "point3_lead": "商家要的是实实在在的交代。",
    "point3_body": "会期内加互动场次、延长开放时间，承诺的减免会后一周落成书面。",
    "closing": "这场雨暴露的问题，一半在天气，一半在筹备。",
}
MINDMAP = {"root": "核心观点", "branches": [
    {"label": "一、白纸被吹走：不是风太大，是太“空”", "children": [
        {"label": "缺少根基，盲从他人"},
        {"label": "内心无内容，外力来袭立不住"},
        {"label": "没有主见立场，随波逐流"}]},
    {"label": "二、蝴蝶吹不走：有生命，就有方向", "children": [
        {"label": "懂得感知：辨明风向与力度"},
        {"label": "拥有意志：明确目标、主动发力"},
        {"label": "善于行动：借风顺势，走出自己路线"},
        {"label": "有方向者：大风也吹不散"}]},
    {"label": "三、从白纸变蝴蝶：不是变强，是变“活”", "children": [
        {"label": "认知误区：一味追求变硬、变强"},
        {"label": "蜕变三要素", "children": [
            {"label": "独立思考：不盲从，深究底层逻辑"},
            {"label": "找准方向：明晰自身前行目标"},
            {"label": "学会借力：主动驾驭环境"}]}]},
    {"label": "总结升华", "children": [
        {"label": "世事风浪常在，不必等风停"},
        {"label": "唯有自我成长，长出内在翅膀"}]},
]}
TIPS = {
    "cover_title": "“畅通群众监督渠道”",
    "cover_line2": "具体怎么畅通？",
    "overview_title": "面试中“畅通群众监督渠道”万能展开法（分 3 档，直接套用）",
    "overview_intro": "不讲空话，讲清怎么提、谁来接、何时回、有保障的闭环。",
    "tiers": [
        {"title": "1.  AIR 版（3 个维度，时间紧张/追问时用）", "points": [
            {"lead": "多元渠道覆盖", "body": "线上新媒体＋线下传统渠道，让不同群体都有反映途径；"},
            {"lead": "限时闭环办理", "body": "明确受理和办结时限，件件有回音。"}]},
        {"title": "2.  Pro 版（4 个维度，逻辑最完整，推荐首选）", "points": [
            {"lead": "全域渠道无死角", "body": "线上开通一键举报，线下设置意见箱和领导接访日。"},
            {"lead": "快速响应不推诿", "body": "1 个工作日签收，3 个工作日反馈进度。"}]},
        {"title": "3.  Pro Max 版（加 1 个差异化动作，拉开差距）", "points": [
            {"lead": "群众监督员队伍", "body": "从人大代表、政协委员、社区代表中选聘监督员。"}]},
    ],
    "takeaway": {"title": "避坑提醒", "body": "只适用于怎么落实类题目。"},
    "cta": "关注我，后续分享更多面试实战技巧和考场避坑指南。",
}


def render(mode, data, outdir, check=False):
    """在进程内调用引擎（避免子进程；outdir 由 tempfile 生成）。"""
    tmp = Path(tempfile.mkdtemp())
    p = tmp / "final.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    argv = ["--mode", mode, "--final", str(p), "--outdir", str(outdir)]
    if check:
        argv.append("--check")
    return rc.main(argv)


class TestValidate(unittest.TestCase):
    def test_answer_missing_field(self):
        bad = {k: v for k, v in ANSWER.items() if k != "closing"}
        self.assertIn("缺字段: closing", rc.validate(bad, "answer"))

    def test_answer_core_views_count(self):
        bad = dict(ANSWER, core_views=["只有一条"])
        self.assertTrue(any("core_views" in e for e in rc.validate(bad, "answer")))

    def test_answer_real_exam_prefix(self):
        bad = dict(ANSWER, title_prefix="结构化每日一练：")
        self.assertTrue(any("历年考题" in e for e in rc.validate(bad, "answer")))
        self.assertEqual(rc.validate(dict(ANSWER, title_prefix="结构化历年考题："), "answer"), [])

    def test_tips_tiers_minimum(self):
        bad = dict(TIPS, tiers=TIPS["tiers"][:1])
        self.assertIn("tiers 至少 2 档", rc.validate(bad, "tips"))


class TestWrap(unittest.TestCase):
    def test_no_line_start_punctuation(self):
        lines = rc.wrap_text([("一二三四五六七八九十，十一十二。", "regular")],
                             {"regular": 32}, 300)
        for line in lines[1:]:
            self.assertNotIn(line[0][0][0], "，。！？；：、")

    def test_ascii_token_atomic(self):
        lines = rc.wrap_text([("马上打119和120", "regular")], {"regular": 32}, 200)
        joined = "".join(t for line in lines for t, _ in line)
        self.assertIn("119", joined)


class TestRender(unittest.TestCase):
    def test_tips_without_cover_line2(self):
        """cover_line2 是可选字段；缺省时封面只画主标题。"""
        with tempfile.TemporaryDirectory() as d:
            data = {k: v for k, v in TIPS.items() if k != "cover_line2"}
            self.assertEqual(render("tips", data, d), 0)
            self.assertTrue(list(Path(d).glob("01-封面.png")))

    def test_tips_render(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(render("tips", TIPS, d), 0)
            pngs = sorted(Path(d).glob("*.png"))
            self.assertGreaterEqual(len(pngs), 4)
            for p in pngs:
                with Image.open(p) as im:
                    self.assertEqual(im.size, (1080, 1440))
            with Image.open(pngs[-1]) as im:
                self.assertEqual(im.convert("RGB").getpixel((20, 20)), rc.CREAM)

    def test_answer_render_with_mindmap(self):
        with tempfile.TemporaryDirectory() as d:
            data = dict(ANSWER, mindmap=MINDMAP, cta="关注我。")
            self.assertEqual(render("answer", data, d), 0)
            pngs = sorted(Path(d).glob("*.png"))
            self.assertGreaterEqual(len(pngs), 4)
            self.assertTrue(pngs[1].name.startswith("02-思维导图"))

    def test_answer_without_mindmap(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(render("answer", ANSWER, d), 0)
            names = [p.name for p in sorted(Path(d).glob("*.png"))]
            self.assertTrue(names[1].startswith("02-答题思路"))

    def test_overflow_paginates(self):
        with tempfile.TemporaryDirectory() as d:
            long = dict(ANSWER, opening=ANSWER["opening"] * 90)
            self.assertEqual(render("answer", long, d), 0)
            self.assertGreaterEqual(len(list(Path(d).glob("*.png"))), 7)

    def test_check_only_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(render("answer", ANSWER, d, check=True), 0)
            self.assertEqual(list(Path(d).glob("*.png")), [])

    def test_mindmap_overflow_fails(self):
        huge = {"root": "核心观点", "branches": [
            {"label": f"分支{i}", "children": [{"label": f"叶子{j}"} for j in range(10)]}
            for i in range(6)]}
        with self.assertRaises(ValueError):
            render("answer", dict(ANSWER, mindmap=huge), tempfile.mkdtemp())

    def test_content_right_margin(self):
        """内容页墨迹不得越过版心右界 984（封面/品牌页满幅属设计例外）。"""
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(render("answer", dict(ANSWER, mindmap=MINDMAP), d), 0)
            for p in sorted(Path(d).glob("*.png")):
                if p.name in ("01-封面.png") or "品牌页" in p.name:
                    continue
                with Image.open(p) as im:
                    gray = im.convert("L")
                    px = gray.load()
                    w, h = gray.size
                    right = max((x for y in range(200, 1300, 4)
                                 for x in range(w) if px[x, y] < 220), default=0)
                self.assertLessEqual(right, 984, f"{p.name} 右缘 {right} 越界")

    def test_mindmap_lines_do_not_cross_labels(self):
        """导图连线不得穿过任何标签文字（DESIGN 5.6 硬规则；长 root 回归）。"""
        import copy
        tree = copy.deepcopy(MINDMAP)
        tree["root"] = "规矩不能让，路要指够"
        boxes, pts = [], []
        orig_dl, orig_cb = rc.draw_lines, rc._cubic

        def spy_dl(dr, pos, lines, sizes, lh, fill, **kw):
            widths = []
            for line in lines:          # 每行 = [(text, kind), ...]
                x = pos[0]
                for t, k in line:
                    x += rc.font(k, sizes[k]).getlength(t)
                widths.append(x - pos[0])
            w = max(widths) if widths else 0
            boxes.append((pos[0], pos[1], pos[0] + w, pos[1] + lh * len(lines)))

        def spy_cb(dr, p1, p2, color, width=3, steps=26):
            orig_cb(dr, p1, p2, color, width, steps)
            mx = (p1[0] + p2[0]) / 2
            c1, c2 = (mx, p1[1]), (mx, p2[1])
            for i in range(steps + 1):
                t = i / steps
                x = ((1 - t) ** 3 * p1[0] + 3 * (1 - t) ** 2 * t * c1[0]
                     + 3 * (1 - t) * t ** 2 * c2[0] + t ** 3 * p2[0])
                y = ((1 - t) ** 3 * p1[1] + 3 * (1 - t) ** 2 * t * c1[1]
                     + 3 * (1 - t) * t ** 2 * c2[1] + t ** 3 * p2[1])
                pts.append((x, y))

        rc.draw_lines, rc._cubic = spy_dl, spy_cb
        try:
            rc.mindmap_page(tree)
        finally:
            rc.draw_lines, rc._cubic = orig_dl, orig_cb
        bad = [pt for pt in pts for b in boxes
               if b[0] - 2 <= pt[0] <= b[2] + 2 and b[1] - 2 <= pt[1] <= b[3] + 2]
        self.assertEqual(bad, [])
        self.assertGreater(len(pts), 40)
        self.assertGreater(len(boxes), 6)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    if suite.countTestCases() < MIN_CASES:
        raise SystemExit(f"[FAIL] 用例数 {suite.countTestCases()} < {MIN_CASES}")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

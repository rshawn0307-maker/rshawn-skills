#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_voice.py 回归测试：结构门禁是否真的抓程序化，且不误伤合格稿。"""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_voice as cv  # noqa: E402

MIN_CASES = 8
DATA = Path(__file__).resolve().parent / "testdata"
GOOD = json.loads((DATA / "answer_ok.json").read_text(encoding="utf-8"))
TIPS = json.loads((DATA / "tips_ok.json").read_text(encoding="utf-8"))


class TestAnswer(unittest.TestCase):
    def test_good_fixture_passes(self):
        fails, _ = cv.check_answer(GOOD)
        self.assertEqual(fails, [])

    def test_no_mindmap_fails(self):
        d = {k: v for k, v in GOOD.items() if k != "mindmap"}
        fails, _ = cv.check_answer(d)
        self.assertTrue(any("R1 缺 mindmap" in f for f in fails))

    def test_thin_details_fail(self):
        d = copy.deepcopy(GOOD)
        for i in (1, 2, 3):
            d[f"point{i}_body"] = "做好相关工作，确保落实到位。"
        fails, _ = cv.check_answer(d)
        self.assertTrue(any("R4" in f for f in fails))

    def test_banned_slogan_fails(self):
        d = copy.deepcopy(GOOD)
        d["point2_body"] += "这体现了我们的担当。"
        fails, _ = cv.check_answer(d)
        self.assertTrue(any("注水标语" in f for f in fails))

    def test_repeated_wo_leads_fail(self):
        d = copy.deepcopy(GOOD)
        d["point1_lead"] = "我先去展位。"
        d["point2_lead"] = "我再开直播。"
        d["point3_lead"] = "我还要回访。"
        fails, _ = cv.check_answer(d)
        self.assertTrue(any("「我」开头" in f for f in fails))

    def test_step_labels_limit(self):
        d = copy.deepcopy(GOOD)
        d["point1_body"] = "第一步，先稳住。第二步，再补救。第三步，留档。"
        fails, _ = cv.check_answer(d)
        self.assertTrue(any("第X步" in f for f in fails))

    def test_no_boundary_is_warning_only(self):
        d = copy.deepcopy(GOOD)
        for k in ("opening", "point1_body", "point2_body", "point3_body", "closing"):
            d[k] = d[k].replace("如果", "").replace("遇到", "").replace("前提", "")
        fails, warns = cv.check_answer(d)
        self.assertEqual(fails, [])
        self.assertTrue(any("R7" in w for w in warns))


class TestTips(unittest.TestCase):
    def test_tips_fixture_passes(self):
        fails, _ = cv.check_tips(TIPS)
        self.assertEqual(fails, [])

    def test_air_without_any_detail_fails(self):
        d = copy.deepcopy(TIPS)
        for p in d["tiers"][0]["points"]:
            p["body"] = "做好相关工作，持续优化，确保落实到位。"
        fails, _ = cv.check_tips(d)
        self.assertTrue(any("AIR" in f for f in fails))

    def test_tips_banned_slogan_fails(self):
        d = copy.deepcopy(TIPS)
        d["tiers"][2]["points"][0]["body"] += "有效提升治理水平。"
        fails, _ = cv.check_tips(d)
        self.assertTrue(any("注水标语" in f for f in fails))


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    if suite.countTestCases() < MIN_CASES:
        raise SystemExit(f"[FAIL] 用例数 {suite.countTestCases()} < {MIN_CASES}")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

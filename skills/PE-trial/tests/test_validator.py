#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_artifacts.py 单测（任务2）：0 skip，坏 fixture 必须红。

覆盖任务书清单：运动技能/健康课、19/21 锚点虚报、时长求和、教材源冲突、
危险保护、解析失败串锚、缺伴随文件、零项目、重复ID、11列表格，
以及 A4 版式、中文字体、自评分、占位符、画像字段、红->绿循环。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(TESTS)
SCRIPTS = os.path.join(SKILL, "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, TESTS)

import make_docx_fixtures  # noqa: E402
import validate_artifacts as va  # noqa: E402

GOOD = os.path.join(TESTS, "fixtures", "good")
PROFILE_FULL = os.path.join(TESTS, "fixtures", "profile_tuhuan_full.json")
PROFILE_SEG = os.path.join(TESTS, "fixtures", "profile_health_segment.json")
TEXTBOOK = os.path.join(TESTS, "fixtures", "textbook_excerpt.md")
VALIDATOR = os.path.join(SCRIPTS, "validate_artifacts.py")

T07 = "07_田径_07-10_双手头上前掷实心球_试讲稿_v1.0.md"
T07_SC = "07_田径_07-10_双手头上前掷实心球_自检表_v1.0.md"
T07_FM = "07_田径_07-10_双手头上前掷实心球_队形图_v1.0.md"
T09 = "09_健康课程_09-04_沟通与合作_试讲稿_v1.0.md"


def run_cli(args):
    p = subprocess.run([sys.executable, VALIDATOR] + args,
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def codes(out):
    return set(l.split()[1] for l in out.splitlines()
               if l.startswith(("[error]", "[veto ", "[warn ]")))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        make_docx_fixtures.main()
        cls.tmp = tempfile.mkdtemp(prefix="pe-trial-test-")
        cls.suite = os.path.join(cls.tmp, "suite")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        # 每个测试从干净副本开始：任何测试中途失败也不污染后续测试
        if os.path.isdir(self.suite):
            shutil.rmtree(self.suite, ignore_errors=True)
        shutil.copytree(GOOD, self.suite)

    def path(self, name):
        return os.path.join(self.suite, name)

    def restore(self, name):
        shutil.copy2(os.path.join(GOOD, name), self.path(name))

    def edit(self, name, old, new, count=-1):
        with open(self.path(name), "r", encoding="utf-8") as f:
            t = f.read()
        assert old in t, "fixture 缺待改片段：%r" % old[:30]
        with open(self.path(name), "w", encoding="utf-8") as f:
            f.write(t.replace(old, new) if count < 0
                    else t.replace(old, new, count))

    def scrub(self, name, words):
        """删除文件中实际存在的词（不存在的跳过），用于清空保护词类测试。"""
        for w in words:
            with open(self.path(name), "r", encoding="utf-8") as f:
                t = f.read()
            if w in t:
                with open(self.path(name), "w", encoding="utf-8") as f:
                    f.write(t.replace(w, ""))


class GoodSuitesGreen(Base):
    """好套件必须全绿：运动技能课 + 健康课片段。"""

    def test_skills_full_lesson_passes(self):
        rc, out = run_cli(["--suite", self.path(T07),
                           "--profile", PROFILE_FULL, "--textbook", TEXTBOOK])
        self.assertEqual(rc, 0, out)
        self.assertIn("RESULT: PASS", out)
        self.assertIn("'lesson_kind': 'skills'", out.replace('"', "'"))

    def test_health_segment_passes(self):
        rc, out = run_cli(["--suite", self.path(T09), "--profile", PROFILE_SEG])
        self.assertEqual(rc, 0, out)
        self.assertIn("RESULT: PASS", out)

    def test_zero_project_green_when_real_dir_has_transcripts(self):
        # 单一画像只匹配 07-10 技能课；混合课型目录应按各自画像分套校验
        only07 = os.path.join(self.tmp, "only07")
        os.makedirs(only07, exist_ok=True)
        for fn in os.listdir(GOOD):
            if fn.startswith("07_"):
                shutil.copy2(os.path.join(GOOD, fn), only07)
        rc, out = run_cli(["--suite", only07, "--profile", PROFILE_FULL])
        self.assertEqual(rc, 0, out)
        self.assertIn("transcript_count", out)


class BadFixturesRed(Base):
    """任务书清单逐项：坏 fixture 必须红（exit 1 + 对应错误码）。"""

    def test_duration_sum_mismatch(self):  # 时长求和
        self.edit(T07, "## 基本部分（6分钟）", "## 基本部分（7分钟）")
        rc, out = run_cli(["--suite", self.path(T07), "--profile", PROFILE_FULL])
        self.assertEqual(rc, 1, out)
        self.assertIn("DURATION-SUM", out)
        self.restore(T07)

    def test_anchor_claim_19_of_21(self):  # 19/21 锚点虚报
        self.edit(T07_SC, "| F2 | 无生互动真实感 | 通过 | 试讲稿:9-10 |\n", "")
        self.edit(T07_SC, "| G1 | 结构可迁移 | 通过 | 备课提纲:13-18 |\n", "")
        rc, out = run_cli(["--suite", self.path(T07), "--profile", PROFILE_FULL])
        self.assertEqual(rc, 1, out)
        self.assertIn("ANCHOR-CLAIM-MISMATCH", out)
        self.assertIn("共21项 但实际锚点行 19", out)
        self.restore(T07_SC)

    def test_duplicate_id(self):  # 重复 ID
        self.edit(T07_SC, "| B1 | 环节结构完整 | 通过 | 备课提纲:13-18 |",
                  "| B1 | 环节结构完整 | 通过 | 备课提纲:13-18 |\n"
                  "| B1 | 环节结构完整 | 通过 | 备课提纲:13-18 |")
        rc, out = run_cli(["--suite", self.path(T07), "--profile", PROFILE_FULL])
        self.assertEqual(rc, 1, out)
        self.assertIn("DUPLICATE-ID", out)
        self.restore(T07_SC)

    def test_parse_bad_anchor_row(self):  # 解析失败串锚
        self.edit(T07_SC, "| A1 | 技术要领与教材一致 |", "| X99 | 技术要领与教材一致 |")
        rc, out = run_cli(["--suite", self.path(T07), "--profile", PROFILE_FULL])
        self.assertEqual(rc, 1, out)
        self.assertIn("PARSE-BAD-ANCHOR-ROW", out)
        self.assertIn("拒绝串锚", out)
        self.restore(T07_SC)

    def test_textbook_source_conflict(self):  # 教材源冲突
        self.edit(T07, "# 双手头上前掷实心球", "# 单手侧抛铅球")
        rc, out = run_cli(["--suite", self.path(T07),
                           "--profile", PROFILE_FULL, "--textbook", TEXTBOOK])
        self.assertEqual(rc, 1, out)
        self.assertIn("TEXTBOOK-SOURCE-CONFLICT", out)
        self.restore(T07)

    def test_veto_safety_no_protection(self):  # 危险保护
        self.scrub(T07, va.PROTECT_WORDS)
        self.scrub(T07_FM, va.PROTECT_WORDS)
        rc, out = run_cli(["--suite", self.path(T07), "--profile", PROFILE_FULL])
        self.assertEqual(rc, 1, out)
        self.assertIn("VETO-SAFETY", out)
        self.assertIn("保护帮助", out)

    def test_veto_safety_opposed_throw(self):  # 相向投掷
        self.edit(T07, "统一方向投掷，", "两人一组相向投掷，")
        rc, out = run_cli(["--suite", self.path(T07), "--profile", PROFILE_FULL])
        self.assertEqual(rc, 1, out)
        self.assertIn("VETO-SAFETY", out)
        self.assertIn("相向投掷", out)
        self.restore(T07)

    def test_missing_companion(self):  # 缺伴随文件
        os.remove(self.path(T07_FM))
        rc, out = run_cli(["--suite", self.path(T07), "--profile", PROFILE_FULL])
        self.assertEqual(rc, 1, out)
        self.assertIn("MISSING-COMPANION", out)
        self.assertIn("队形图", out)
        self.restore(T07_FM)

    def test_zero_project(self):  # 零项目
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty, exist_ok=True)
        rc, out = run_cli(["--suite", empty, "--profile", PROFILE_FULL])
        self.assertEqual(rc, 1, out)
        self.assertIn("ZERO-PROJECT", out)

    def test_skill_structure_missing_phase(self):  # 技能课缺环节
        self.edit(T07, "## 结束部分（1分钟）", "## 收尾环节（1分钟）")
        rc, out = run_cli(["--suite", self.path(T07), "--profile", PROFILE_FULL])
        self.assertEqual(rc, 1, out)
        self.assertIn("STRUCTURE", out)
        self.assertIn("结束部分", out)
        self.restore(T07)

    def test_health_structure_missing_core(self):  # 健康课缺核心环节
        self.edit(T09, "## 游戏探究（3分钟）", "## 集体游戏（3分钟）")
        rc, out = run_cli(["--suite", self.path(T09), "--profile", PROFILE_SEG])
        self.assertEqual(rc, 1, out)
        self.assertIn("STRUCTURE", out)
        self.assertIn("游戏探究", out)
        self.restore(T09)

    def test_self_score_in_selfcheck(self):  # 自评分
        self.edit(T07_SC, "| A1 | 技术要领与教材一致 | 通过 |",
                  "| A1 | 技术要领与教材一致 | 9分 |")
        rc, out = run_cli(["--suite", self.path(T07), "--profile", PROFILE_FULL])
        self.assertEqual(rc, 1, out)
        self.assertIn("SELF-SCORE", out)
        self.restore(T07_SC)

    def test_cleanliness_anchor_and_profile(self):  # 净稿纯净性
        self.edit(T07, "## 开始部分（1分钟）",
                  "> 评分锚点：B2 满弓示范到位\n\n## 开始部分（1分钟）")
        self.edit(T07, "今天我们一起学习",
                  "本稿共 1800 字。今天我们一起学习")
        self.edit(T07, "上肢力量和全身协调用力",
                  "上肢力量和全身协调用力（EXAM_PROFILE trial_minutes）")
        rc, out = run_cli(["--suite", self.path(T07), "--profile", PROFILE_FULL])
        self.assertEqual(rc, 1, out)
        c = codes(out)
        self.assertIn("CLEANLINESS", c)
        self.assertGreaterEqual(out.count("CLEANLINESS"), 3)
        self.assertIn("评分锚点", out)
        self.assertIn("EXAM_PROFILE", out)
        self.assertIn("自报统计", out)
        self.restore(T07)

    def test_placeholder(self):  # 占位符
        self.edit(T07, "下面开始我的试讲。", "下面开始我的试讲。TODO")
        rc, out = run_cli(["--suite", self.path(T07), "--profile", PROFILE_FULL])
        self.assertEqual(rc, 1, out)
        self.assertIn("CLEANLINESS", out)
        self.assertIn("TODO", out)
        self.restore(T07)


class ProfileRedGreen(Base):
    def _mutated_profile(self, key, value=None, drop=False):
        with open(PROFILE_FULL, encoding="utf-8") as f:
            bad = json.load(f)
        if drop:
            bad.pop(key, None)
        else:
            bad[key] = value
        return bad

    def _write(self, name, obj):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        return p

    def test_profile_missing_field(self):
        p = self._write("bad_profile.json", self._mutated_profile("trial_minutes", drop=True))
        rc, out = run_cli(["--profile", p])
        self.assertEqual(rc, 1, out)
        self.assertIn("PROFILE-MISSING-FIELD", out)
        self.assertIn("trial_minutes", out)

    def test_profile_bad_enum(self):
        p = self._write("bad_enum.json",
                        self._mutated_profile("deliverable_type", "whole_school_play"))
        rc, out = run_cli(["--profile", p])
        self.assertEqual(rc, 1, out)
        self.assertIn("PROFILE-BAD-ENUM", out)


class DocxChecks(Base):
    """DOCX 版式：11列表格/表宽/A4/边距/中文字体。"""

    def test_good_a4_docx_passes(self):
        rc, out = run_cli(["--docx",
                           os.path.join(TESTS, "fixtures", "docx", "good_a4.docx")])
        self.assertEqual(rc, 0, out)

    def test_bad_table11_fails(self):
        rc, out = run_cli(["--docx",
                           os.path.join(TESTS, "fixtures", "docx", "bad_table11.docx")])
        self.assertEqual(rc, 1, out)
        c = codes(out)
        self.assertIn("TABLE-TOO-MANY-COLS", c)
        self.assertIn("TABLE-TOO-WIDE", c)
        self.assertIn("PAGE-SETUP", c)
        self.assertIn("FONT-MISSING", c)


class RedGreenCycle(Base):
    """CLI 级红->绿循环：故意破坏临时 fixture 必须红，恢复后全绿。"""

    def test_break_then_restore(self):
        args = ["--suite", self.path(T07), "--profile", PROFILE_FULL,
                "--textbook", TEXTBOOK]
        rc, out = run_cli(args)
        self.assertEqual(rc, 0, out)  # 绿

        self.edit(T07, "## 准备部分（2分钟）", "## 准备部分（5分钟）")
        self.edit(T07, "身体后仰成满弓", "身体后仰成满弓（XXX 待补）")
        rc, out = run_cli(args)
        self.assertEqual(rc, 1, out)  # 红
        self.assertIn("DURATION-SUM", out)
        self.assertIn("CLEANLINESS", out)

        self.restore(T07)
        rc, out = run_cli(args)
        self.assertEqual(rc, 0, out)  # 恢复全绿
        self.assertIn("RESULT: PASS", out)


if __name__ == "__main__":
    unittest.main()

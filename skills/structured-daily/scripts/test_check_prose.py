#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_prose —— structured-daily check_prose.py 副本小型自测。

运行：python3 scripts/test_check_prose.py [关键字...]
- 全过 exit 0；任一用例失败 / 0 用例（筛选不中或框架坏）→ exit 1
  （不允许假绿）。
- 沙箱纪律：样本文件只写系统临时目录（tempfile），真实 vault 只读。

用例（Task6 简报指定 6 项）：
1. dash        破折号检出（exit 非 0，报「破折号」）
2. pivot       翻案腔检出（不是…而是；exit 非 0）
3. gongkao     公考高危词检出（体现；exit 非 0，报「公考高危词」）
4. prefix      冒号前缀豁免（「点评：」前缀+正文无其他冒号 → exit 0），
               附反例：非前缀提示性冒号仍拦
5. clean       干净文本放行（exit 0）
6. negation    否定式排比≤1（两处拒 exit 非 0；一处放行 exit 0）
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK_CLI = os.path.join(HERE, "check_prose.py")

MIN_CASES = 6  # 用例数下限，防框架坏后假绿


def run_cli(sample_text):
    with tempfile.TemporaryDirectory(prefix="check_prose_test_") as tmpdir:
        path = os.path.join(tmpdir, "sample.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(sample_text)
        proc = subprocess.run(
            [sys.executable, CHECK_CLI, path],
            capture_output=True, text=True,
        )
        return proc.returncode, proc.stdout + proc.stderr


CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


@case("dash 破折号检出")
def case_dash(check):
    rc, out = run_cli("他停了一下——然后补了一句关键的话。\n")
    check(rc != 0, "exit=%s" % rc)
    check("破折号" in out, "未报破折号")


@case("pivot 翻案腔检出（不是…而是）")
def case_pivot(check):
    rc, out = run_cli(
        "这不是技巧问题，而是判断问题。先立判断，再给理由，最后落到动作。\n"
    )
    check(rc != 0, "exit=%s" % rc)
    check("翻案句" in out, "未报禁用翻案句")


@case("gongkao 公考高危词检出（体现）")
def case_gongkao(check):
    rc, out = run_cli("这一做法体现了基层的执行力，也彰显了改革的决心。\n")
    check(rc != 0, "exit=%s" % rc)
    check("公考高危词" in out, "未报公考高危词")


@case("prefix 冒号前缀豁免（点评：放行；非前缀冒号仍拦）")
def case_prefix(check):
    rc, out = run_cli(
        "点评：普通答法先立一句总起，再分两层展开，最后收一个能落地的判断。\n"
    )
    check(rc == 0, "前缀冒号未豁免，exit=%s" % rc)
    check("模板前缀冒号豁免 1" in out, "豁免计数未体现")
    rc2, out2 = run_cli("一句话总结：先立骨。\n")
    check(rc2 != 0, "非前缀提示性冒号未拦，exit=%s" % rc2)
    check("中文冒号" in out2, "冒号失败项未报")


@case("clean 干净文本放行")
def case_clean(check):
    rc, out = run_cli(
        "他会先写一句总起，再把理由分成两层，最后收一个能落地的判断。"
        "理由从材料里来，判断从理由里来，整段只有一个重点。\n"
    )
    check(rc == 0, "exit=%s" % rc)
    check("需要修改" not in out, "干净文本出现失败项")


@case("negation 否定式排比≤1（两处拒/一处放行）")
def case_negation(check):
    rc, out = run_cli(
        "不是没努力，不是没方法，是没把方法落到题上。"
        "不是不会拆，不是不敢拆，是拆完不收判断。\n"
    )
    check(rc != 0, "两处否定式排比未拒，exit=%s" % rc)
    check("否定式排比 2 处" in out, "计数未报 2 处")
    rc1, _ = run_cli("不是没努力，不是没方法，是没把方法落到题上。\n")
    check(rc1 == 0, "一处否定式排比未放行（红线≤1），exit=%s" % rc1)


def main() -> int:
    selected = [entry for entry in CASES if not sys.argv[1:]
                or any(key in entry[0] for key in sys.argv[1:])]
    if not selected:
        print("0 用例命中（筛选不中或框架坏）", file=sys.stderr)
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

    print(f"\n{len(selected) - len(failures)}/{len(selected)} 用例通过")
    if failures:
        print("失败用例：%s" % "、".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

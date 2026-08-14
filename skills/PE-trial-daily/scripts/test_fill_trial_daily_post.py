# -*- coding: utf-8 -*-
"""test_fill_trial_daily_post.py v1.0

隔离测试：在临时工作区构建 pending_trial_daily.json，运行 fill_trial_daily_post.py，
验证生成 DOCX 的结构契约（封面、图例、环节拆解、易犯错误表格、试讲逐字稿、引流页）。

用法:
    python3 test_fill_trial_daily_post.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

SCRIPT_DIR = Path(__file__).resolve().parent
FILL_SCRIPT = SCRIPT_DIR / "fill_trial_daily_post.py"

CYAN_LEGACY = "关注我，每天一个体育试讲设计，帮你备考上岸"

# 生成一张测试用 PNG（覆盖图例插入路径）
def make_test_png(path):
    import struct, zlib
    w = h = 64
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    Path(path).write_bytes(png)


def build_pending(fig_path):
    return {
        "sport": "篮球",
        "chapter": "第三章 篮球运动教学内容 | 二、运球",
        "segment_name": "原地运球",
        "segment_type": "practice",
        "difficulty": "★★",
        "figure": "图3-2-7 原地低运球、图3-2-8 原地高运球",
        "figure_images": [fig_path],
        "method": "两腿微屈上体稍前倾，以肘为轴前臂屈伸，用手指和指根触球，球落点在同侧脚外侧前方。",
        "rules": "降低重心抬头观察，不低头看球，另一侧手臂护球。",
        "intent": "建立正确手指触球手型与按压节奏，体会高低运球差异。",
        "organization": "散点站位每人一球，间隔一臂距离，巡回指导统一口令。",
        "errors": [
            ["掌心按拍球", "体会手指和指根触球，掌心空出"],
            ["低头看球", "手势报数游戏引导抬头"]
        ],
        "lecture_script": "同学们好，我们先复习原地运球。每人拿一个球拉开距离，记住手指触球按拍有力控制落点。看我示范，两腿微屈上体前倾，以肘为轴用手指指根触球，掌心空出。跟我做，一二三四。低运球十下，高运球十下。我转一圈看，小王做得很稳。小李你掌心太紧了，空出来。抬头看我手势，报数几个就运几个。运球不是拍球，要有迎球缓冲。这节课把手感练出来，下节课学行进间运球。好收球做放松。",
        "cta": CYAN_LEGACY,
        "hashtags": "#教师编 #体育教师 #体育试讲 #试讲设计 #一次上岸",
    }


def run_test():
    tmp = Path(tempfile.mkdtemp(prefix="trial_test_"))
    try:
        ws = tmp / "workspace"
        (ws / "scripts").mkdir(parents=True)
        (ws / "desktop-attachments").mkdir(parents=True)
        fig = ws / "fig.png"
        make_test_png(fig)

        pending = build_pending(str(fig))
        (ws / "scripts" / "pending_trial_daily.json").write_text(
            json.dumps(pending, ensure_ascii=False), encoding="utf-8"
        )

        env = dict(os.environ)
        env["TRIAL_DAILY_WORKSPACE"] = str(ws)
        result = subprocess.run(
            [sys.executable, str(FILL_SCRIPT)],
            capture_output=True, text=True, env=env,
        )
        out = result.stdout + result.stderr
        passed = [
            "✅ 全部通过" in out,
            "✅ pending_trial_daily.json 已删除" in out,
        ]
        if result.returncode != 0 or not all(passed):
            print("======== 测试失败：脚本输出 ========")
            print(out)
            return False

        # 校验 DOCX 结构
        docx_path = ws / "desktop-attachments" / "2 体育试讲每日一练-帖子内容编辑模板.docx"
        if not docx_path.exists():
            print("FAIL: 输出 DOCX 不存在")
            return False
        doc = Document(str(docx_path))
        text = "\n".join(p.text or "" for p in doc.paragraphs)
        for t in doc.tables:
            for r in t.rows:
                for c in r.cells:
                    text += "\n" + (c.text or "")

        checks = {}
        checks["封面标题"] = "体育试讲设计每日一练" in text
        checks["项目标签"] = "【篮球】练习环节" in text
        checks["环节名"] = "原地运球" in text
        checks["活动方法"] = pending["method"] in text
        checks["规则"] = pending["rules"] in text
        checks["设计意图"] = pending["intent"] in text
        checks["组织形式"] = pending["organization"] in text
        checks["易犯错误表"] = "易犯错误" in text and "纠正方法" in text
        checks["试讲逐字稿"] = "试讲逐字稿" in text
        checks["引流段"] = CYAN_LEGACY in text
        checks["话题标签"] = pending["hashtags"] in text
        # 图例图片数
        img_count = sum(
            len(p._element.findall(".//" + qn("w:drawing"))) for p in doc.paragraphs
        )
        checks["图例图片"] = img_count == 1

        failed = [k for k, v in checks.items() if not v]
        for k, v in checks.items():
            print(f"  {'✅' if v else '❌'} {k}")
        if failed:
            print(f"FAIL: 未通过 {failed}")
            return False
        print("  ✅ 全部结构校验通过")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    ok = run_test()
    sys.exit(0 if ok else 1)
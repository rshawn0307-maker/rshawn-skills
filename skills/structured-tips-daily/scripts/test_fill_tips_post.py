# -*- coding: utf-8 -*-
"""test_fill_tips_post.py v1.0

隔离测试：在临时工作区构建 pending_tips.json + 模板副本，运行 fill_tips_post.py，
验证生成 DOCX 的结构契约（封面前缀、技巧字段、普通vs高分对照、段数、图片、引流段）。

用法:
    python3 test_fill_tips_post.py
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
# fill_tips_post.py 引擎位于结构化工作区（WORKSPACE = SCRIPT_DIR.parent）
REAL_WORKSPACE = Path("/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/结构化")
FILL_SCRIPT = REAL_WORKSPACE / "scripts" / "fill_tips_post.py"
REAL_TEMPLATE = REAL_WORKSPACE / "desktop-attachments" / "3 结构化答题技巧-帖子内容编辑模板.docx"

DRAIN_TEXT = "关注我，后续分享更多面试实战技巧和考场避坑"  # 实际引流段前缀，用于校验保留


def build_pending():
    return {
        "tip_title": "应急应变别再平均用力，先排序再出招",
        "question_type": "适用题型：应急应变题",
        "tip_intro": "破题角度：考官看的是轻重缓急的排序能力，不是面面俱到。",
        "step1": "第一步：先定优先级，把最紧急、最伤人的事排第一。",
        "step2": "第二步：止损优先，先把事态控制住，再谈调查和追责。",
        "step3": "第三步：处置+善后闭环，给结果也给交代。",
        "case_normal": "普通答法：遇到这种情况，我会先了解情况，再上报领导，然后安抚群众，最后总结经验。",
        "case_normal_note": "点评：平均用力，没有排序，考官看不到你的判断力。",
        "case_high": "高分答法：第一，先疏散人群、切断危险源；第二，立刻上报并同步联络消防医疗；第三，专人对接家属，事后复盘。",
        "case_high_note": "点评：有明确先后顺序，每个动作都有具体抓手。",
        "pitfalls_lead": "避坑提醒：",
        "pitfalls": "别一上来就'上报领导'当万能开头；别把'安抚'说得空泛。",
        "tip_takeaway": "说到底，应急应变衡量的不是话术，是你能不能分清轻重。",
        "hashtags": "#公考面试 #结构化面试 #应急应变 #答题技巧 #上岸",
    }


def run_test():
    tmp = Path(tempfile.mkdtemp(prefix="tips_test_"))
    try:
        ws = tmp / "workspace"
        (ws / "scripts").mkdir(parents=True)
        (ws / "desktop-attachments").mkdir(parents=True)

        # 复制引擎脚本 + 真实模板到临时工作区
        tmp_fill = ws / "scripts" / "fill_tips_post.py"
        shutil.copy(FILL_SCRIPT, tmp_fill)
        shutil.copy(REAL_TEMPLATE, ws / "desktop-attachments" / "3 结构化答题技巧-帖子内容编辑模板.docx")

        pending = build_pending()
        (ws / "scripts" / "pending_tips.json").write_text(
            json.dumps(pending, ensure_ascii=False), encoding="utf-8"
        )

        result = subprocess.run(
            [sys.executable, str(tmp_fill)],
            capture_output=True, text=True, env=dict(os.environ),
        )
        out = result.stdout + result.stderr
        passed = [
            "全部验证通过" in out,
            "pending_tips.json" in out,
            "答题技巧" in out,
        ]
        if result.returncode != 0 or not all(passed):
            print("======== 测试失败：脚本输出 ========")
            print(out)
            return False

        docx_path = ws / "desktop-attachments" / "3 结构化答题技巧-帖子内容编辑模板.docx"
        if not docx_path.exists():
            print("FAIL: 输出 DOCX 不存在")
            return False
        doc = Document(str(docx_path))
        text = "\n".join(p.text or "" for p in doc.paragraphs)

        checks = {}
        checks["段数=17"] = len(doc.paragraphs) == 17
        img_total = sum(len(p._element.findall('.//' + qn('w:drawing'))) for p in doc.paragraphs)
        checks["图片=5"] = img_total == 5
        # 封面文本框前缀"答题技巧："（2 镜像）
        prefixes = []
        tip_titles = []
        for tx in doc.paragraphs[0]._element.iter(qn('w:txbxContent')):
            ts = [t.text for t in tx.findall('.//' + qn('w:t'))]
            if len(ts) >= 2:
                prefixes.append(ts[0])
                tip_titles.append(ts[1])
        checks["封面前缀=答题技巧"] = prefixes == ["答题技巧：", "答题技巧："]
        checks["封面标题"] = all(t == pending["tip_title"] for t in tip_titles)
        # 正文字段全命中
        checks["适用题型"] = pending["question_type"] in text
        checks["破题角度"] = pending["tip_intro"] in text
        checks["步骤"] = pending["step1"] in text and pending["step3"] in text
        checks["普通vs高分"] = pending["case_normal"] in text and pending["case_high"] in text
        checks["避坑"] = pending["pitfalls"] in text
        checks["总结"] = pending["tip_takeaway"] in text
        checks["标签"] = pending["hashtags"] in text
        # 引流段保留（原模板固定段）
        checks["引流段保留"] = "关注我" in text
        # 引流段样式：段[15] 加粗 + #85120F + 居中
        p15 = doc.paragraphs[15]
        r15 = p15.runs[0]
        checks["引流段样式"] = (
            p15.alignment == 1 and r15.bold is True and str(r15.font.color.rgb) == "85120F"
        )
        # 段[7] pageBreakBefore
        p7_pPr = doc.paragraphs[7]._element.find(qn('w:pPr'))
        checks["段7分页"] = p7_pPr is not None and p7_pPr.find(qn('w:pageBreakBefore')) is not None

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
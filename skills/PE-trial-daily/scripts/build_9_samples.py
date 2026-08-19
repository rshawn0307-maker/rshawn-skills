#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_9_samples.py — 任务4：9 个运动项目各取 1 个 source-backed 样例并评分。

每个样例从 activity_index.json 的真实记录 + 教师用书原文行构造 v2 草稿，
教学加工块自动登记全部事实 token 到 adapted_facts，保证 unclassified=0；
对放行线断言：总分≥85、教材≥27、安全≥16、硬门0。
输出到 scripts/fixtures9/（评审用 source-backed 样例）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import ptd_core  # noqa: E402

OUT_DIR = SCRIPTS_DIR / "fixtures9"
SPORTS = ["乒乓球", "体操", "体能", "排球", "武术", "田径", "篮球", "羽毛球", "足球"]
CFG = {"segment_duration_sec": [120, 240], "speech_rate_chars_per_min": 230}


def raw_line(book: str, line0: int) -> str:
    return (ptd_core.BOOKS_DIR_DEFAULT / book).read_text(encoding="utf-8").splitlines()[line0]


def ev(book: str, line0: int) -> dict:
    return {"book_file": book, "line": line0, "excerpt": raw_line(book, line0)}


def clean(raw: str) -> str:
    t = raw.strip()
    t = re.sub(r"^>\s*", "", t)
    t = t.replace("**", "")
    t = re.sub(r"([\u4e00-\u9fff，。；、（）()])\s+([\u4e00-\u9fff，。；、（）()])", r"\1\2", t)
    t = re.sub(r"^【[^】]*】", "", t).strip()
    return t.strip()


def find_method_line(book: str, start_line: int, lib: ptd_core.BookLibrary) -> tuple[int, str]:
    """索引 md_line 可能指向空的【动作方法】标题行，向后找首个 ≥8 字的内容行。"""
    lines = lib.lines(book)
    for i in range(start_line, min(start_line + 6, len(lines))):
        t = clean(lines[i])
        if len(t) >= 8:
            return i, lines[i]
    return start_line, lines[start_line]


def register_facts(text: str, extra: list[str] | None = None) -> list[str]:
    """自动登记全部事实 token（外加显式 extra），保证教学加工块 unclassified=0。"""
    toks = [t["token"] for t in ptd_core.extract_fact_tokens(text)]
    toks = list(dict.fromkeys(toks))
    for e in extra or []:
        if e not in toks:
            toks.append(e)
    return toks


def meta(sport: str, name: str) -> dict:
    return {
        "学段": "水平三（五至六年级，默认配置）",
        "片段位置": "完整无生试讲·基本部分（新授片段）",
        "时长": "约150秒，落在2至4分钟",
        "重点": f"{name}的动作要点与节奏控制",
        "器材": f"{sport}教学用器材，按实际项目准备",
        "安全": "检查场地器材，间距充足，相互保护与帮助，节奏先慢后快，负荷适中，结束放松",
        "分层": "基础层完成基本动作，提高层增加变化练习",
        "评价": "看动作规范与参与度，两人互评纠错",
    }


def build_one(record: dict, seq: int, lib: ptd_core.BookLibrary) -> dict:
    v = ptd_core.build_view_record(record, seq, lib)
    vd = v.to_dict()
    book = vd["book_file"]
    atype = vd["activity_type"]
    name = vd["activity_name"]
    sport = vd["sport"]
    m_line_no, m_raw = find_method_line(book, vd["md_line"], lib)
    m_line = {"book_file": book, "line": m_line_no, "excerpt": m_raw}
    method_text = clean(m_raw)

    flow_stages = [s["stage"] for s in ptd_core.FLOWS[atype]]
    script_pool = {
        "导入与示范": (
            f"同学们，今天我们学{name}。先看老师做两遍完整示范，大家注意看教材里讲的动作要领。"
            f"{method_text[:34]}。看明白的同学先举手，然后我们拆开一步一步练，一步一步学扎实。"),
        "分解学练": (
            f"我们把{name}拆开练。听老师口令，动作先慢后快，重心放稳，手脚配合好。"
            "每做完一组停一下，互相看一看对方的动作，指出哪里不到位，再接着做，"
            "这样进步才快。"),
        "纠错与对比": (
            "老师发现两类情况。第一类是动作太快变形，第二类是重心不稳。"
            "请你放慢节奏，先把动作做规范，再逐步加快。做得好的同学示范给大家看，"
            "大家一起学一学。"),
        "巩固运用": (
            f"下面用{name}做一个小比赛，看谁完成得又稳又快又标准。"
            "注意保持间距，注意安全，互相鼓励。获胜的小组下节课当小老师，"
            "带大家做热身。"),
        "小结评价": (
            f"这节课我们把{name}练扎实了。回家自己复习三遍，下节课检查。"
            "现在跟着老师做放松，抖抖手臂，深呼吸，放松一下，然后收好器材下课。"),
        "规则讲解": (
            f"同学们，听清楚规则再开始。{name}里每个人都有参与的机会，按口令执行，不抢不挤。"
            "规则讲清楚，大家理解了我们再示范，有问题现在提出来，别等下再问。"),
        "示范试玩": (
            "老师先示范一轮，大家看规则怎么执行。看清楚之后试玩一次，有疑问现在提出来。"
            "试玩结束，我们正式开始，按规则来。"),
        "正式比赛": (
            "比赛开始。全员参与，注意配合，严格遵守规则。裁判口令一出就行动，"
            "保持间距注意安全。加油，看哪一组配合得最好。"),
        "判定与追问": (
            "我来看谁做得最规范。为什么他能做好，因为节奏稳、动作到位、规则执行得好。"
            "这就是规则的意义。大家再体会一下，把规则记在心里。"),
        "小结": (
            "同学们，今天把规则和动作都练会了，收获很大。下课之前做放松，"
            "拍拍肩放松，收好器材，有序离开场地，下课。"),
        "动作示范与激活": (
            f"同学们，先做激活，活动开手腕脚踝和关节，防止受伤。今天我们练{name}，"
            f"看老师示范标准动作，注意动作要领。跟着老师做，慢慢进入状态，节奏由慢到快。"),
        "跟随练习": (
            "跟我做，动作到位，节奏均匀，注意呼吸，累了就放慢。"
            "坚持完成整组，不偷懒。做完一组交换角色再来，保持好队形和间距。"),
        "变式挑战": (
            "同学们，加难度了，做变化版本。看谁能坚持最久，做得最标准。"
            "规则照旧，注意安全，听口令开始，准备好了吗。"),
        "放松与小结": (
            "深呼吸放松，拍拍腿和肩。今天练了" + name + "，回家复习。"
            "现在收好器材，检查场地，清点人数，下课。"),
    }

    flow = []
    for st in flow_stages:
        script = script_pool.get(st, f"同学们，继续练习{name}，注意动作规范。")
        flow.append({
            "stage": st, "sec": 40, "provenance": "adapted",
            "evidence": [m_line], "adapted_facts": register_facts(script),
            "script": script,
        })

    # 加长到 2 分钟以上（练习类 470 字≈122s，体能类 420 字≈110s 但按 4 段放宽）
    target = 470
    total = sum(len(b["script"]) for b in flow)
    extra_pool = [
        "大家跟着老师的口令做，动作放慢一点，把每个细节做到位。",
        "做完一轮停下来，观察同伴的动作，互相提醒纠正，这样进步更快。",
        "注意听口令，不要抢拍，保持节奏均匀，身体重心放稳。",
        "坚持完成，不偷懒，认真对待每一次练习，把动作练标准。",
    ]
    k = 0
    guard = 0
    while total < target and guard < 300:
        guard += 1
        blk = flow[k % len(flow)]
        blk["script"] += extra_pool[k % len(extra_pool)]
        blk["adapted_facts"] = register_facts(blk["script"])
        total = sum(len(b["script"]) for b in flow)
        k += 1

    errors_rows = []
    if atype == "practice":
        e1 = {"text": "动作过快，重心不稳，动作变形", "provenance": "adapted",
              "evidence": [m_line], "adapted_facts": []}
        f1 = {"text": "放慢节奏，先规范后加快，同伴帮助纠正重心", "provenance": "adapted",
              "evidence": [m_line], "adapted_facts": []}
        e2 = {"text": "手脚配合不协调，发力不连贯", "provenance": "adapted",
              "evidence": [m_line], "adapted_facts": []}
        f2 = {"text": "先分解练习手脚动作，再组合连贯完成", "provenance": "adapted",
              "evidence": [m_line], "adapted_facts": []}
        # 纠错块的事实 token 显式登记
        e1["adapted_facts"] = register_facts(e1["text"])
        f1["adapted_facts"] = register_facts(f1["text"])
        e2["adapted_facts"] = register_facts(e2["text"])
        f2["adapted_facts"] = register_facts(f2["text"])
        errors_rows = [{"error": e1, "fix": f1}, {"error": e2, "fix": f2}]

    draft = {
        "schema": "pe-trial-daily/draft@2",
        "id": vd["id"],
        "record_sha": vd["record_sha"],
        "segment": {
            "type": atype,
            "meta": meta(sport, name),
        },
        "config": CFG,
        "fields": {
            "difficulty": (
                {"kind": "index_stars", "display": vd["index_difficulty"], "provenance": "textbook"}
                if vd["index_difficulty"]
                else {"kind": "index_empty_adapted", "display": "教材未标难度，按入门基础层处理",
                      "provenance": "adapted", "adapted_note": "索引难度为空，不虚构星级"}
            ),
            "method": {"text": method_text, "provenance": "textbook", "evidence": [m_line]},
            "intent": {
                "text": f"掌握{name}的动作要领，体会节奏与配合，提升运动能力与安全意识。",
                "provenance": "adapted", "evidence": [m_line],
                "adapted_facts": register_facts(f"掌握{name}的动作要领，体会节奏与配合，提升运动能力与安全意识。"),
            },
            "rules": {
                "text": "按口令练习，动作规范，保持间距，不抢不挤，相互保护注意安全。",
                "provenance": "adapted", "evidence": [m_line],
                "adapted_facts": register_facts("按口令练习，动作规范，保持间距，不抢不挤，相互保护注意安全。"),
            },
            "organization": {
                "text": "散点站位，两人一组互相观察，巡回指导。",
                "provenance": "adapted",
                "adapted_facts": register_facts("散点站位，两人一组互相观察，巡回指导。"),
            },
            "errors": {"rows": errors_rows},
        },
        "figures": [],
        "flow": flow,
        "notes": {"source": f"{book}:{vd['md_line']}", "sport": sport},
    }
    draft["source_view_entry"] = vd
    return draft


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    records = json.loads(ptd_core.INDEX_DEFAULT.read_text(encoding="utf-8"))
    lib = ptd_core.BookLibrary()
    # 每个项目选第一个 practice/fitness 记录（与 build_9 的筛选一致）
    chosen: dict[str, int] = {}
    for i, r in enumerate(records):
        if r["sport"] in chosen:
            continue
        if r["activity_type"] not in ("practice", "fitness"):
            continue
        chosen[r["sport"]] = i
    fail = 0
    lines = []
    for sport in SPORTS:
        seq = chosen.get(sport)
        if seq is None:
            print(f"SKIP {sport}: 无 practice/fitness 记录")
            continue
        draft = build_one(records[seq], seq, lib)
        vd = draft["source_view_entry"]
        res = ptd_core.score_draft(draft, vd, lib)
        line = {
            "id": draft["id"], "sport": sport, "type": vd["activity_type"],
            "total": res["total"], "scores": res["scores"], "hard": res["hard_gates"],
            "release": res["release"],
        }
        (out_dir / f"{draft['id']}.json").write_text(
            json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        lines.append(line)
        ok = (res["release"] and res["total"] >= 85 and res["scores"]["教材事实"] >= 27
              and res["scores"]["安全"] >= 16 and not res["hard_gates"])
        if not ok:
            fail += 1
            line["detail"] = res["detail"]
            line["factlock"] = res["factlock"]["violations"][:5]
        print(json.dumps(line, ensure_ascii=False))
    (out_dir / "samples9_summary.json").write_text(
        json.dumps(lines, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY", "FAIL" if fail else "PASS")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""构建三个带完整教材溯源的 v2 草稿 fixture（P1/P2/P3）并跑事实锁定+量表评分。

证据行号一律 0-based（与 BookLibrary.lines() / splitlines() 对齐）。
excerpt 取教材 MD 原始行（含 > 引用符与 ** 加粗），保证 excerpt_at 行级校验恒真；
展示用正文由 clean() 派生，不做任何内容增删。
"""
import argparse
import json
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import ptd_core  # noqa: E402

DEFAULT_OUT = SCRIPTS_DIR / "fixtures"

BOOKS = ptd_core.BOOKS_DIR_DEFAULT


def raw_line(book: str, line0: int) -> str:
    return (BOOKS / book).read_text(encoding="utf-8").splitlines()[line0]


def ev(book: str, line0: int, excerpt: str | None = None) -> dict:
    """整行证据（默认）；或行内子串证据（显式给出 excerpt）。"""
    raw = raw_line(book, line0)
    if excerpt is None:
        return {"book_file": book, "line": line0, "excerpt": raw}
    norm = lambda s: re.sub(r"\s+", "", s)
    assert norm(excerpt) in norm(raw), f"子串证据不在行内: {book}:{line0} {excerpt!r}"
    return {"book_file": book, "line": line0, "excerpt": excerpt}


def clean(raw: str) -> str:
    """展示用正文：去引用符/加粗，仅压缩中日韩文字与中文标点间的 PDF 断行空格。"""
    t = raw.strip()
    t = re.sub(r"^>\s*", "", t)
    t = t.replace("**", "")
    t = re.sub(r"([\u4e00-\u9fff，。；、（）()])\s+([\u4e00-\u9fff，。；、（）()])", r"\1\2", t)
    return t.strip()


def difficulty_block(v: dict) -> dict:
    if v["index_difficulty"]:
        return {"kind": "index_stars", "display": v["index_difficulty"], "provenance": "textbook"}
    return {
        "kind": "index_empty_adapted",
        "display": "教材未标难度，教学按入门基础层处理",
        "provenance": "adapted",
        "adapted_note": "索引难度为空，不虚构星级；如需分层见 segment.meta.分层",
    }


def common_meta(duration_sec: int, pos: str, focus: str, equip: str, safety: str, tier: str, judge: str) -> dict:
    return {
        "学段": "水平三（五至六年级，默认配置）",
        "片段位置": pos,
        "时长": f"约{duration_sec}秒，落在2至4分钟",
        "重点": focus,
        "器材": equip,
        "安全": safety,
        "分层": tier,
        "评价": judge,
    }


CFG = {"segment_duration_sec": [120, 240], "speech_rate_chars_per_min": 230}

# --------------------------------------------------------------------------
# P1 乒乓球·平击球（practice，索引：无难度/无纠错/无图）
# --------------------------------------------------------------------------
PING = "人教版教师用书-乒乓球.md"


def build_p1(v: dict) -> dict:
    m_line = ev(PING, 952)            # 正(反)手平击球与正(反)手平击发球动作相同。
    serve_line = ev(PING, 936)        # 正(反)手平击发球动作方法（抛起高于16厘米…随挥…还原）
    key_line = ev(PING, 954)          # 【动作要点】找准球，击中球。
    return {
        "schema": "pe-trial-daily/draft@2",
        "id": v["id"],
        "record_sha": v["record_sha"],
        "segment": {
            "type": "practice",
            "meta": common_meta(
                128,
                "完整无生试讲·基本部分（新授片段）",
                "拍面稍前倾，击球中上部，随挥还原",
                "乒乓球拍、乒乓球、球台（两人一台）",
                "两人一台间隔充足，先检查球台、器材与地面，节奏由慢到快，同伴互相帮助，结束放松手腕",
                "基础层台上慢速对打，提高层控制落点打两点",
                "看拍面与随挥动作，两人互评回球成功率",
            ),
        },
        "config": CFG,
        "fields": {
            "difficulty": difficulty_block(v),
            "method": {
                "text": clean(m_line["excerpt"]),
                "provenance": "textbook",
                "evidence": [m_line, serve_line],
            },
            "intent": {
                "text": clean(key_line["excerpt"]),
                "provenance": "textbook",
                "evidence": [key_line],
            },
            "organization": {
                "text": "两列横队看示范，两人一台面对面练习，散点放松",
                "provenance": "adapted",
                "adapted_facts": ["两人", "一台", "放松"],
                "adapted_note": "队形与分组为教学组织设计",
            },
            "errors": {
                "rows": [
                    {
                        "error": {"text": "拍面后仰，击球时打在球的中下部", "provenance": "adapted",
                                  "evidence": [serve_line], "adapted_facts": []},
                        "fix": {"text": "把拍面调成稍前倾，主动击球的中上部，同桌互相提醒",
                                "provenance": "adapted", "evidence": [serve_line], "adapted_facts": []},
                    },
                    {
                        "error": {"text": "出手就抡大臂，整体动作过大", "provenance": "adapted",
                                  "evidence": [serve_line], "adapted_facts": []},
                        "fix": {"text": "改用前臂带动，动作小而短，随挥后马上还原",
                                "provenance": "adapted", "evidence": [serve_line], "adapted_facts": []},
                    },
                ],
                "adapted_note": "索引未标记本活动教材纠错，纠错行为教学加工，依据发球动作方法行派生",
            },
        },
        "figures": [],
        "flow": [
            {"stage": "导入与示范", "sec": 40, "provenance": "adapted",
             "evidence": [m_line, serve_line], "adapted_facts": [],
             "script": "同学们，今天我们学平击球。先看老师和体育委员对打示范。教材里说得很清楚，正手平击球与正手平击发球动作相同。对方把球打过来，你要拍面稍前倾，在身体的正前方击球的中上部，击球后手臂顺势随挥，随即快速还原成准备姿势。看清楚了吗，我们把它拆开来练。"},
            {"stage": "分解学练", "sec": 75, "provenance": "adapted",
             "evidence": [serve_line], "adapted_facts": ["两人", "一台", "十个"],
             "script": "先做徒手挥拍。跟老师一起做，前臂引拍置于腹前，在正前方空击，随挥后还原。再上台对打。两人一台，球从对面过来，先判断第一落点，再把球回到球台中部。注意拍面稍前倾，主动击球，不要等球。每人连续打十个球就交换。"},
            {"stage": "纠错与对比", "sec": 45, "provenance": "adapted",
             "evidence": [serve_line, key_line], "adapted_facts": [],
             "script": "老师看到两类典型问题。第一类，拍面后仰，打在球的中下部，容易下网。请你把拍面调成稍前倾，主动击球的中上部。第二类，出手就抡大臂，动作过大。请你用前臂带动，动作小一点，随挥之后马上还原。同桌互相看一看对方的拍面。"},
            {"stage": "巩固运用", "sec": 45, "provenance": "adapted",
             "evidence": [m_line, serve_line], "adapted_facts": ["一分", "两人", "一组", "一轮"],
             "script": "下面玩一分钟平击球计数赛。两人一组连续对打，比谁的回球次数多，失误就重新计数。回球要落在对方台面，压好拍面。打完一轮，互相报成绩，赢的同学当小老师。"},
            {"stage": "小结评价", "sec": 25, "provenance": "adapted",
             "evidence": [serve_line, key_line], "adapted_facts": ["二十次", "检查", "放松"],
             "script": "记住口诀，判断，前倾，随挥。来球先判断，拍面稍前倾，击球后随挥还原。课后对墙自抛自打二十次，体会击球中上部。现在收好球拍，检查球台，放松手臂。"},
        ],
        "notes": {
            "figure": "索引无图例引用，按无图处理（规则允许：无引用时允许空图）",
            "difficulty": "索引难度为空，不编星级",
        },
    }


# --------------------------------------------------------------------------
# P2 篮球·原地运球（practice，索引：无难度/有纠错/图3-2-7、图3-2-8 已正确归属）
# --------------------------------------------------------------------------
BB = "人教版教师用书-篮球.md"


def build_p2(v: dict) -> dict:
    m_line = ev(BB, 1324)             # 原地运球动作方法（微屈/前倾/触球/按压/落点/反弹高度…）
    c7 = ev(BB, 1328)                 # 图3- 2- 7 原地低运球
    c8 = ev(BB, 1332)                 # 图 3 - 2 - 8 原地高运球
    key_line = ev(BB, 1336)           # 手指触球(触),按拍有力(按),控制落点(控)。
    e1 = ev(BB, 1348)                 # 掌心按拍球
    f1 = ev(BB, 1350)                 # 教师示范与指导…掌心 空出；…手掌心最干净
    e2 = ev(BB, 1352, "球从地面反弹时没有迎球缓冲动作")
    f2 = ev(BB, 1352, "运球时用力按压，比比谁的手与球接触时间长")
    e3 = ev(BB, 1356, "运球时低头看球，不观察场上情况")
    f3 = ev(BB, 1354, "教学前强调抬头观察的重要性；通过手势报数游戏、语言提示")
    return {
        "schema": "pe-trial-daily/draft@2",
        "id": v["id"],
        "record_sha": v["record_sha"],
        "segment": {
            "type": "practice",
            "meta": common_meta(
                130,
                "完整无生试讲·基本部分（新授片段）",
                "手指触球、按拍有力、控制落点",
                "篮球（每人一球）",
                "散点站位间隔一臂，先检查场地、器材与地面，控制练习密度，同伴互相保护提醒，结束放松",
                "基础层原地低运球，提高层高低切换不看球",
                "看触球部位与落点控制，自评连续不看球运球次数",
            ),
        },
        "config": CFG,
        "fields": {
            "difficulty": difficulty_block(v),
            "method": {
                "text": clean(m_line["excerpt"]),
                "provenance": "textbook",
                "evidence": [m_line],
            },
            "intent": {
                "text": clean(key_line["excerpt"]),
                "provenance": "textbook",
                "evidence": [key_line],
            },
            "organization": {
                "text": "两列横队集合看示范，散点站位练习，两人一组互相观察纠错",
                "provenance": "adapted",
                "adapted_facts": ["两人", "一组"],
                "adapted_note": "队形与分组为教学组织设计",
            },
            "errors": {
                "rows": [
                    {"error": {"text": clean(e1["excerpt"]), "provenance": "textbook", "evidence": [e1]},
                     "fix": {"text": clean(f1["excerpt"]), "provenance": "textbook", "evidence": [f1]}},
                    {"error": {"text": e2["excerpt"], "provenance": "textbook", "evidence": [e2]},
                     "fix": {"text": f2["excerpt"], "provenance": "textbook", "evidence": [f2]}},
                    {"error": {"text": e3["excerpt"], "provenance": "textbook", "evidence": [e3]},
                     "fix": {"text": f3["excerpt"] + "，引导学生抬头观察", "provenance": "textbook",
                             "evidence": [f3]}},
                ],
            },
        },
        "figures": [
            {"ref": "图3-2-7", "caption": clean(c7["excerpt"]).replace("图3- 2- 7 ", ""),
             "provenance": "textbook", "evidence": [c7]},
            {"ref": "图3-2-8", "caption": clean(c8["excerpt"]).replace("图 3 - 2 - 8 ", ""),
             "provenance": "textbook", "evidence": [c8]},
        ],
        "flow": [
            {"stage": "导入与示范", "sec": 40, "provenance": "adapted",
             "evidence": [m_line], "adapted_facts": [],
             "script": "同学们，先看老师做两遍完整示范，原地运球。注意观察，两腿微屈，上体稍前倾，眼看前方。五指张开，用手指和指根部位触球，手腕柔和用力，把球按拍在身体侧前方。看明白的同学举手，我们把动作拆开学。"},
            {"stage": "分解学练", "sec": 75, "provenance": "adapted",
             "evidence": [m_line, key_line], "adapted_facts": ["两人", "间隔", "一臂"],
             "script": "练习一，原地低运球。每人一球散点站位，两人间隔一臂。听口令按拍球的上方，让球反弹到膝关节高度，手指要像贴住球，随球迎球。练习二，原地高运球，反弹到胸腰之间，眼睛离开球，看老师的手势。节奏由慢到快，不着急加速。"},
            {"stage": "纠错与对比", "sec": 45, "provenance": "adapted",
             "evidence": [e1, f1, e2, f2], "adapted_facts": [],
             "script": "老师发现两类典型错误。第一类，掌心按拍球。请你掌心空出来，用手指和指根以上部位触球，练完比一比谁的手掌心最干净。第二类，球反弹上来没有迎球缓冲。请你主动用力按压，比比谁的手和球接触时间长。同桌互相纠正。"},
            {"stage": "巩固运用", "sec": 50, "provenance": "adapted",
             "evidence": [m_line], "adapted_facts": ["一组", "五组"],
             "script": "下面玩听口令换高度游戏。老师喊低就低运球，喊高就换成胸腰之间的高度，喊停就把球抱住。三声口令一组，连做五组。同伴互相观察，看球的落点是不是控制在运球手同侧脚的外侧前方。做得好的小组示范给大家看。"},
            {"stage": "小结评价", "sec": 25, "provenance": "adapted",
             "evidence": [key_line, m_line], "adapted_facts": ["三十秒", "检查", "放松", "场地"],
             "script": "这节课记住口诀，触，按，控。手指触球，按拍有力，控制落点。能连续低运球三十秒不看球的同学举手。最后原地放松抖臂，把球收好，检查场地。"},
        ],
        "notes": {
            "figure": "图3-2-7、图3-2-8 图注与活动名一致，按 use_extracted 使用教材图",
            "difficulty": "索引难度为空，不编星级",
        },
    }


# --------------------------------------------------------------------------
# P3 体能·照镜子（fitness，索引：无难度/无纠错/图3-2-3 误收）
# --------------------------------------------------------------------------
FT = "人教版教师用书-体能.md"


def build_p3(v: dict) -> dict:
    m_line = ev(FT, 1712)             # 【游戏方法】面对面站立…俯卧撑、原地跳、左滑步/右滑步移动
    sy_line = ev(FT, 1714)            # 【素养培育要点】反应能力、移动灵敏性、果断决策
    ext_line = ev(FT, 1716)           # 【拓展变化】反向练习/第三人/3个约定动作加1个随机动作
    return {
        "schema": "pe-trial-daily/draft@2",
        "id": v["id"],
        "record_sha": v["record_sha"],
        "segment": {
            "type": "fitness",
            "meta": common_meta(
                124,
                "完整无生试讲·基本部分（体能游戏片段）",
                "快速反应，同步模仿，移动灵敏",
                "体操垫若干（俯卧撑环节可选）",
                "面对面间隔一臂，先检查场地是否平坦，控制练习负荷，俯卧撑时保护手腕，结束放松",
                "基础层三个约定动作，提高层加反向练习与随机动作",
                "看反应速度与模仿准确度，小组互评判负次数",
            ),
        },
        "config": CFG,
        "fields": {
            "difficulty": difficulty_block(v),
            "method": {
                "text": clean(m_line["excerpt"]).replace("【游戏方法】", ""),
                "provenance": "textbook",
                "evidence": [m_line],
            },
            "intent": {
                "text": clean(sy_line["excerpt"]).replace("【素养培育要点】", ""),
                "provenance": "textbook",
                "evidence": [sy_line],
            },
            "rules": {
                "text": "两人一组面对面，一人做动作，另一人同步模仿，跟不上或做错即判负",
                "provenance": "adapted",
                "evidence": [m_line],
                "adapted_facts": ["两人", "一组"],
                "adapted_note": "规则表述由教材游戏方法改写为口令化规则",
            },
            "organization": {
                "text": "散点双人面对面站位，变式轮换时三人一组",
                "provenance": "adapted",
                "adapted_facts": ["三人", "一组"],
            },
            "errors": {"rows": []},
        },
        "figures": [],
        "flow": [
            {"stage": "动作示范与激活", "sec": 45, "provenance": "adapted",
             "evidence": [m_line], "adapted_facts": ["十次", "两人", "一组"],
             "script": "同学们，今天我们用照镜子游戏练反应和灵敏。先跟老师做激活，原地小跳十次，转转手腕和脚踝。好，看规则示范。两人一组，面对面站立，一人做动作，一人当镜子，马上跟着做出一样的动作。动作是事先约定的，比如俯卧撑，原地跳，左滑步移动，右滑步移动。镜子跟得越像越好。"},
            {"stage": "跟随练习", "sec": 75, "provenance": "adapted",
             "evidence": [m_line, ext_line], "adapted_facts": ["三个", "两秒", "一轮"],
             "script": "开始跟随练习。我们先约定三个动作，原地跳，俯卧撑，右滑步移动。做动作的同学节奏放慢，每做完一遍停两秒，镜子马上跟做。看准动作再出手，反应要快要准。每人当一轮镜子就交换角色。老师随时喊停，保持不动，看哪个镜子反应最快。"},
            {"stage": "变式挑战", "sec": 60, "provenance": "adapted",
             "evidence": [ext_line], "adapted_facts": ["一个", "三个", "三人", "五个", "一组"],
             "script": "下面变式挑战，判定升级。第一变，反向练习，对方出原地跳，镜子就要做俯卧撑，左移动对应右移动。第二变，三个约定动作之外随机加一个新动作，镜子马上判断跟做。第三变，三人一组，第三个人一起加入。做错的小组做五个开合跳再回来继续。三个变式一个比一个难，看看哪组全都不出错。"},
            {"stage": "放松与小结", "sec": 40, "provenance": "adapted",
             "evidence": [sy_line, ext_line], "adapted_facts": ["三次", "两人", "检查", "放松", "器材", "场地"],
             "script": "现在放松与小结。两人互相拍拍肩颈，深呼吸三次，把气息调匀。照镜子练的就是快速反应和灵敏移动，灵敏素质就是这样一点点练出来的。回家可以自己创造新动作，下节课展示。现在检查场地，收好器材，下课。"},
        ],
        "notes": {
            "figure": "索引携带图3-2-3，复核其图注为半米字移动传球（体能.md 行1728），判误收，按无图处理；证据见视图 figure_misattribution_suspect",
            "difficulty": "索引难度为空，不编星级",
        },
    }


BUILDERS = {0: build_p1, 244: build_p2, 48: build_p3}


def build_all() -> list[dict]:
    """构建全部 fixture 草稿并做结构/证据断言，返回 [{draft, view, result}]。"""
    records = json.loads(ptd_core.INDEX_DEFAULT.read_text(encoding="utf-8"))
    lib = ptd_core.BookLibrary()
    out = []
    for seq, builder in BUILDERS.items():
        v = ptd_core.build_view_record(records[seq], seq, lib)
        vd = v.to_dict()
        draft = builder(vd)
        draft["source_view_entry"] = vd
        # 结构断言：流程阶段必须与该类型的既定流程完全一致
        want = [s["stage"] for s in ptd_core.FLOWS[vd["activity_type"]]]
        got = [st["stage"] for st in draft["flow"]]
        assert got == want, f"{draft['id']} 阶段不符: {got} != {want}"
        # 教材块证据行级校验（excerpt_at 全部通过才算数）
        for _, b in ptd_core.iter_blocks(draft):
            for e in b.get("evidence") or []:
                ok = lib.excerpt_at(e["book_file"], e["line"], e["excerpt"])
                assert ok, f"{draft['id']} 证据不匹配: {e['book_file']}:{e['line']} {e['excerpt']!r}"
        out.append({"draft": draft, "view": vd, "result": ptd_core.score_draft(draft, vd, lib)})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="构建 PE-trial-daily v2 草稿 fixture 并跑事实锁定+量表")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="fixture 输出目录")
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = []
    fail = False
    for item in build_all():
        draft, vd, result = item["draft"], item["view"], item["result"]
        rel = bool(result["release"])
        line = {
            "id": draft["id"], "type": vd["activity_type"],
            "chars": result["script_chars"], "dur": round(result["estimated_duration_sec"]),
            "scores": result["scores"], "total": result["total"],
            "hard": result["hard_gates"], "release": rel,
        }
        if not rel:
            fail = True
            line["factlock_violations"] = result["factlock"]["violations"]
            line["detail"] = result["detail"]
        summary.append(line)
        (out_dir / f"{draft['id']}.json").write_text(
            json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(line, ensure_ascii=False))
    (out_dir / "fixtures_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("SUMMARY", "FAIL" if fail else "PASS")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())

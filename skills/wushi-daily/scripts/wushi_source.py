#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《公务员务实手册》源稿解析共享模块。

check_wushi_content.py 与 gen_wushi_cards.py 都从这里取解析逻辑，
保证「门禁校验的源稿」和「渲染参考的结构」永不漂移。

源稿结构（16 岗全库统一）：
    ### 业务 N：业务名
    **场景**：一句话题面
    **编号步骤**：
    1. 四字动宾：展开句。
    **红线**：不许X；不许Y；…；不许Z。
    **答题嵌入句**：「……。」
    ## 五、假大空改写对照（表：| 假大空原句 | 务实改写 |）
"""
import os
import re
import unicodedata

DEFAULT_SOURCE_DIR = (
    "/Users/shawn/Desktop/AI工作区/02-Areas/公考面试结构化培训/"
    "03_热点与素材/公务员务实"
)

# 弯引号统一为直角引号，NBSP/全角空格剔除——normalize 后比较可容忍复制转换
QUOTE_TABLE = str.maketrans({
    "\u201c": "「", "\u201d": "」",
    "\u2018": "『", "\u2019": "』",
    "\u00a0": "", "\u3000": "",
})

BIZ_RE = re.compile(r"^###\s*业务\s*(\d+)\s*[：:]\s*(.+?)\s*$", re.M)
STEP_RE = re.compile(r"^\s*\d+[\.、]\s*(.+?)\s*$")


def normalize(s):
    """NFC + 弯引号归一 + 去全部空白。verbatim 比较的唯一口径。"""
    if s is None:
        return ""
    s = unicodedata.normalize("NFC", str(s)).translate(QUOTE_TABLE)
    return re.sub(r"\s+", "", s)


def strip_outer_quotes(s):
    s = (s or "").strip()
    if len(s) >= 2 and s[0] == "「" and s[-1] == "」":
        s = s[1:-1].strip()
    return s


def _field(section, name):
    """取 **字段名**：直到空行/段尾的内容。"""
    m = re.search(
        r"\*\*" + re.escape(name) + r"\*\*[：:]?\s*(.*?)(?=\n\s*\n|\Z)",
        section, re.S,
    )
    return m.group(1).strip() if m else ""


def _split_steps(block):
    steps = []
    for line in block.splitlines():
        sm = STEP_RE.match(line.strip())
        if not sm:
            continue
        txt = sm.group(1).strip()
        cm = re.match(r"^(.+?)[：:]\s*(.*)$", txt)
        if cm and cm.group(1).strip():
            steps.append({"lead": cm.group(1).strip(), "body": cm.group(2).strip()})
        else:
            steps.append({"lead": "", "body": txt})
    return steps


def _split_redlines(raw):
    raw = raw.replace("\n", "")
    items = [x.strip() for x in re.split(r"[；;]", raw)]
    return [re.sub(r"。$", "", x).strip() for x in items if normalize(x)]


def parse_businesses(md_text):
    """解析全部 `### 业务` 小节，返回列表（保序）。

    每项: {num, title, scene, steps:[{lead,body}], redlines:[...], embed}
    红线已按分号拆项并去尾句号；嵌入句已去外层「」。
    """
    heads = list(BIZ_RE.finditer(md_text))
    out = []
    for i, m in enumerate(heads):
        if i + 1 < len(heads):
            sec = md_text[m.end():heads[i + 1].start()]
        else:
            m2 = re.search(r"^## ", md_text[m.end():], re.M)
            sec = md_text[m.end():] if not m2 else md_text[m.end():m.end() + m2.start()]
        b = {
            "num": int(m.group(1)),
            "title": m.group(2).strip(),
            "scene": _field(sec, "场景").replace("\n", "").strip(),
            "steps": _split_steps(_field(sec, "编号步骤")),
            "redlines": _split_redlines(_field(sec, "红线")),
            "embed": strip_outer_quotes(_field(sec, "答题嵌入句").replace("\n", "")),
        }
        out.append(b)
    return out


def parse_fake_rows(md_text):
    """解析「假大空改写对照」表，返回 [{fake, real}]（保序）。无表返回 []。"""
    m = re.search(r"^#+.*假大空改写对照.*$", md_text, re.M)
    if not m:
        return []
    rows = []
    for line in md_text[m.end():].splitlines():
        if line.strip().startswith("#"):
            break
        if not line.strip().startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[0] or not cells[1]:
            continue
        if cells[0] == "假大空原句" or set(cells[0]) <= set("-—: "):
            continue
        rows.append({"fake": cells[0], "real": cells[1]})
    return rows


def source_path(source_dir, post):
    return os.path.join(source_dir, f"{post}岗-公务员务实.md")


def load_source(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return text, parse_businesses(text), parse_fake_rows(text)


def match_business(businesses, name):
    """按业务名精确匹配（normalize 口径），也接受 '业务N' 或纯数字 N。返回命中列表。"""
    key = normalize(name)
    if not key:
        return []
    hits = []
    for b in businesses:
        if normalize(b["title"]) == key:
            hits.append(b)
        elif normalize(f"业务{b['num']}") == key or key == str(b["num"]):
            hits.append(b)
    return hits

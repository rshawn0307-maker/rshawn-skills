#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建体育教师用书活动索引。

解析人教版各册教师用书 MD 文件，提取可用于「体育试讲每日一练」的教学环节
（热身游戏 / 体能游戏 / 练习环节），输出统一索引 activity_index.json。

标记约定：
- 【活动方法】→ game     （游戏/比赛活动，篮球、田径）
- 【游戏方法】→ fitness   （体能游戏，体能）
- 【动作方法】→ practice  （技术动作练习环节，仅当附近存在【易犯错误与纠正方法】时收录）
"""
import json
import os
import re
import sys

TEACHER_BOOK_DIR = "/Users/shawn/Desktop/AI工作区/03-Resources/各版本体育教材/人教版"
OUTPUT_PATH = "/Users/shawn/Desktop/AI工作区/01-Projects/自媒体内容库-持续项目/体育教师编/scripts/activity_index.json"

MATCH_MARKERS = ["【活动方法】", "【游戏方法】", "【动作方法】"]
# 武术书使用全角括号：〔动作方法〕，也收录为练习环节
ALT_MARKER_MAP = {"〔动作方法〕": "【动作方法】", "〔游戏方法〕": "【游戏方法】"}

# 章节标题识别（用于构建路径栈）
CHAPTER_HEAD_RE = re.compile(r'^\s*>?\s*\**\s*第[一二三四五六七八九十]+章')
SECTION_HEAD_RE = re.compile(r'^\s*>?\s*\**\s*(?:第[一二三四五六七八九十]+节|一、|二、|三、|四、|五、|六、|七、|八、|九、|十、)')
SUBHEAD_RE = re.compile(r'^\s*>?\s*\**\s*(?:[\(（][一二三四五六七八九十]+[\)）]\.?\s*|\d+[\.、)]\s*)')

# 活动标题识别：含难度标记（★★）或数字编号开头
DIFF_RE = re.compile(r'[（(★]?\s*(★{1,4})\s*[）)]?')
ACTIVITY_TITLE_RE = re.compile(r'^\s*>?\s*\**\s*(?:\(?\d+\s*[\.、)）])?\s*\**\s*([^（(★\d]+)')

MAX_BACKSCAN = 30       # 向上回溯标题的最大行数
ERROR_SCAN_AHEAD = 200  # 向下扫描易犯错误的最大行数
FIG_SCAN_AHEAD = 15     # 向下扫描图例引用的行数


def clean_text(line):
    """去除 md 标记、引用符号、空白，返回纯文本。"""
    t = line.strip()
    t = re.sub(r'^>\s*\|\s*', '|', t)          # 去掉表格行的引用前缀
    t = re.sub(r'^>\s*', '', t)
    t = t.replace('**', '')
    t = re.sub(r'\{\.underline\}', '', t)
    t = re.sub(r'\[|\]', '', t)
    return t.strip()


def extract_difficulty(line):
    m = DIFF_RE.search(line)
    if m:
        return m.group(1)
    return None


def extract_figure_refs(text):
    """从文本中提取图例引用，如 图3-2-7 / 图 3 - 2 - 7。"""
    # 归一化空格
    t = re.sub(r'\s+', '', text)
    refs = re.findall(r'图\d+-\d+-\d+', t)
    return list(dict.fromkeys(refs))


def build_section_stack(lines):
    """构建每个方法标记行对应的章节路径。

    返回 dict: line_index -> section_path (str)
    采用一次扫描维护栈。
    """
    stack = []
    path_map = {}
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        if CHAPTER_HEAD_RE.match(line):
            stack = [clean_text(line)]
        elif SECTION_HEAD_RE.match(line):
            # 替换同层或追加
            stack = stack[:1] + [clean_text(line)]
        elif SUBHEAD_RE.match(line):
            # 追加子标题
            stack = stack + [clean_text(line)]
        path_map[i] = " > ".join(s for s in stack if s)
    return path_map


def _sanitize_name(name):
    """清洗活动名称：去表格行、去编号前缀、去图例引用后缀。"""
    name = name.strip().strip('|').strip()
    if not name or name.startswith('|') or '|' in name:
        return None
    # 去掉转义的 (n) 前缀
    name = re.sub(r'^\\?[\(（]?\d+[\)）]?\s*\.?\s*', '', name).strip()
    # 去掉 (如图3-2-44、图3-2-45) 后缀
    name = re.sub(r'[\(（]如图[^）)]*[\)）]', '', name).strip()
    # 去掉残留的 \ 转义
    name = name.replace('\\>', '').replace('\\', '').strip()
    if not name or len(name) > 30:
        return None
    return name


def find_activity_title(lines, marker_idx):
    """从方法标记行向上回溯，返回 (activity_name, difficulty)。

    优先找含难度标记(★★)的标题；否则找最近的非章节编号标题。
    排除章节固定标题（如"动作方法与要点""练习方法"等）。
    """
    skip_phrases = ["方法与要点", "动作方法", "练习方法", "游戏方法", "学练赛活动",
                    "学练活动", "比赛活动", "素养培育", "教学建议", "水平与课时"]
    for j in range(marker_idx - 1, max(-1, marker_idx - MAX_BACKSCAN), -1):
        raw = lines[j]
        line = clean_text(raw)
        if not line:
            continue
        # 含难度标记优先
        diff = extract_difficulty(raw)
        if diff:
            name = re.sub(r'[（(]?★{1,4}[）)]?', '', line).strip()
            name = _sanitize_name(name)
            if name and not any(p in name for p in skip_phrases):
                return name, diff
        # 数字编号开头的强标题（技术练习等无难度标记）
        if re.match(r'^\(?\d+\s*[\.、)）]', line):
            name = _sanitize_name(line)
            if name and not any(p in name for p in skip_phrases):
                return name, None
    return None, None


def main():
    print("=== 构建体育教师用书活动索引 ===")
    if not os.path.isdir(TEACHER_BOOK_DIR):
        print(f"ERROR: 教师用书目录不存在: {TEACHER_BOOK_DIR}")
        sys.exit(1)

    entries = []
    md_files = sorted(
        f for f in os.listdir(TEACHER_BOOK_DIR)
        if f.startswith("人教版教师用书-") and f.endswith(".md")
    )
    if not md_files:
        print("ERROR: 未找到教师用书 MD 文件")
        sys.exit(1)

    for md_file in md_files:
        sport = md_file.replace("人教版教师用书-", "").replace(".md", "")
        path = os.path.join(TEACHER_BOOK_DIR, md_file)
        print(f"\n--- {md_file} ---")
        with open(path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        path_map = build_section_stack(all_lines)

        # 定位方法标记行
        marker_lines = []
        for i, raw in enumerate(all_lines):
            for marker in MATCH_MARKERS:
                if marker in raw:
                    marker_lines.append((i, marker))
                    break
            else:
                for alt_marker, std_marker in ALT_MARKER_MAP.items():
                    if alt_marker in raw:
                        marker_lines.append((i, std_marker))
                        break

        print(f"  方法标记数: {len(marker_lines)}")

        for i, marker in marker_lines:
            name, difficulty = find_activity_title(all_lines, i)
            if not name:
                continue

            # 图例引用（向下扫描）
            fig_refs = []
            for j in range(i, min(len(all_lines), i + FIG_SCAN_AHEAD)):
                refs = extract_figure_refs(all_lines[j])
                if refs:
                    fig_refs = refs
                    break

            # 类型判定
            if marker == "【活动方法】":
                atype = "game"
            elif marker == "【游戏方法】":
                atype = "fitness"
            else:
                atype = "practice"

            # 是否有易犯错误表格（向下扫描）
            has_errors = False
            if atype == "practice":
                for j in range(i + 1, min(len(all_lines), i + ERROR_SCAN_AHEAD)):
                    if "【易犯错误与纠正方法】" in all_lines[j]:
                        has_errors = True
                        break
                    if CHAPTER_HEAD_RE.match(all_lines[j].strip()):
                        break

            section_path = path_map.get(i, "")

            entries.append({
                "sport": sport,
                "book_file": md_file,
                "activity_name": name,
                "activity_type": atype,
                "difficulty": difficulty or "",
                "section_path": section_path,
                "has_figure": bool(fig_refs),
                "figure_refs": fig_refs,
                "has_errors": has_errors,
                "md_line": i,  # 0-based
                "marker": marker,
            })

    # 排序：运动 → 类型 → 章节 → 名称
    entries.sort(key=lambda e: (e["sport"], e["activity_type"], e["section_path"], e["activity_name"]))

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    # 统计
    by_type = {}
    for e in entries:
        by_type[e["activity_type"]] = by_type.get(e["activity_type"], 0) + 1
    by_sport = {}
    for e in entries:
        by_sport[e["sport"]] = by_sport.get(e["sport"], 0) + 1

    print(f"\n=== 索引完成 ===")
    print(f"总条目数: {len(entries)}")
    print(f"\n按类型: {json.dumps(by_type, ensure_ascii=False)}")
    print(f"按运动: {json.dumps(by_sport, ensure_ascii=False)}")
    print(f"含图例: {sum(1 for e in entries if e['has_figure'])}")
    print(f"输出: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
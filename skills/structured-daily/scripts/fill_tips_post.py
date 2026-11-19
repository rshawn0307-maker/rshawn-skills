#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fill_tips_post.py v3.0 -- 结构化答题技巧·每日一练 帖子生成引擎（structured-daily 技巧线）

用法:
    python3 fill_tips_post.py --project-root DIR
    项目根解析: --project-root > 环境变量 TIPS_PROJECT_ROOT > 报错 exit1 要求显式传
    （v3.0 取消旧版 parent.parent fallback：引擎收进 skill 内后 parent.parent 是 skill
      目录而非 vault，保留 fallback 会误写 skill 目录）

项目根内路径布局:
    desktop-attachments/3 结构化答题技巧-帖子内容编辑模板.docx  模板（成功时原子替换）
    scripts/pending_tips.json   待写入内容（成功后删除，任何失败保留）
    scripts/_snapshots_tips/    写入前快照（最多保留 10 个，超出删最旧）

pending JSON schema（硬性，恰好 15 个顶层 key，全部非空字符串 strip 后非空）:
    tip_title(≤20 字；封面"结构化答题技巧："前缀由引擎自动加，不计入 20 字) card_point
    fix_summary demo step1 step2 step3 case_normal contrast_note boundary_scope
    boundary_misuse boundary_evidence exercise self_check hashtags

模板契约（C2 段位，Task3 baseline 定稿 assets/tips-template-baseline.docx）:
    段数 23 / 图数 pic:pic==4（口径是 pic:pic 真实图片数；w:drawing==5 因含封面文本框
    形状，不作图数契约）/ 封面文本框双镜像 txbxContent==2（drawing + VML fallback）
    / 品牌蓝 003153 / 通用字体无内嵌 / 段 3 样式基准含 b+bCs（首行缩进 2 字符
    firstLineChars=200 + color 85120F + b + bCs）

退出码:
    0 成功
    1 环境错误（项目根未传 / pending 缺失 / 模板缺失或损坏 / 写入前预检失败:
       段数≠23、pic:pic≠4、txbxContent≠2、封面文本框结构异常）——模板未动
    2 pending JSON 无效（非 UTF-8 / 带 BOM / 语法错 / 顶层非对象 / 缺字段 / 多字段 /
       空字段 / tip_title 超长）——模板未动
    3 写入后验证失败（结构 / 15 字段命中 / 引流段原文与样式 / 样式指纹漂移）——
       模板字节不变，pending 保留排查
    4 模板已原子替换但 pending 清理失败 -> 模板已自动回滚为写入前字节，pending 保留

安全设计（references/shared-engine-safety.md 10 条契约）:
    1) schema 全量校验先于任何写盘
    2) 写入前段数 / 图数 / 文本框预检，失败模板未动
    3) 先写临时文件并验证（结构 + 内容 + 逐段样式指纹 pPr/rPr 零漂移，含封面文本框内
       段落），通过后 os.replace 原子替换
    4) 快照写入前生成（最多 10 个；快照失败仅告警降级，内存保留写入前字节用于本轮回滚）
    5) 正文替换只改文本：找第一个纯文本 run 写入，不预设 run[0] 是文本 run，图片 run 完全不动
    6) 封面段 0 双镜像同步：前缀"结构化答题技巧："与 tip_title 各写 2 处
    7) emoji 段首（段 5 👍 / 段 11 🙅‍♂️）由引擎自动加，JSON 不含
    8) 任何失败（exit1/2/3）模板字节不变；exit4 自动回滚为写入前字节
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

TEMPLATE_REL = Path("desktop-attachments") / "3 结构化答题技巧-帖子内容编辑模板.docx"
PENDING_REL = Path("scripts") / "pending_tips.json"
SNAPSHOTS_REL = Path("scripts") / "_snapshots_tips"
MAX_SNAPSHOTS = 10

SCHEMA_KEYS = [
    "tip_title", "card_point", "fix_summary", "demo",
    "step1", "step2", "step3",
    "case_normal", "contrast_note",
    "boundary_scope", "boundary_misuse", "boundary_evidence",
    "exercise", "self_check", "hashtags",
]
TITLE_MAX_CHARS = 20

COVER_PREFIX = "结构化答题技巧："  # 段[0] 封面前缀（txbxContent 双镜像 2 处同步）
DRAIN_COLOR = "85120F"             # 引流段颜色（段[21] 固定）
DRAIN_TEXT = "关注我，后续分享更多面试实战技巧和考场避坑指南，帮你少走弯路，一次上岸"

EXPECTED_PARAS = 23
EXPECTED_IMG_TOTAL = 4   # pic:pic 计数（非 w:drawing；w:drawing==5 含封面文本框形状）
EXPECTED_TXBX = 2        # 封面文本框双镜像（drawing txbxContent + VML fallback）

# 段位映射（Task3 C2 定稿；段[0]=tip_title 走封面文本框双镜像特殊处理）
REPLACE_MAP = [
    (0, "tip_title"),  # 封面文本框，前缀 + 标题各 2 镜像同步（fill_cover）
    (2, "card_point"),
    (3, "fix_summary"),
    (5, "demo"),
    (7, "step1"),
    (8, "step2"),
    (9, "step3"),
    (11, "case_normal"),
    (12, "contrast_note"),
    (14, "boundary_scope"),
    (15, "boundary_misuse"),
    (16, "boundary_evidence"),
    (18, "exercise"),
    (19, "self_check"),
    (20, "hashtags"),
]
BODY_REPLACE_MAP = [pair for pair in REPLACE_MAP if pair[0] != 0]
EMOJI_PREFIX = {5: "👍", 11: "🙅\u200d♂️"}  # 引擎自动加段首，JSON 不含

# 固定不动段: 1/4/6/10/13/17 蓝色标题 / 21 引流段原文+样式 / 22 末图
FIXED_HEADING_PARAS = [
    (1, "卡点诊断"), (4, "定调版示范"), (6, "改法拆解"),
    (10, "对照点评"), (13, "适用边界"), (17, "迁移练习"),
]
END_IMG_PARA = 21 + 1  # 段[22] 末图


def fail(code: int, *msgs) -> None:
    for m in msgs:
        print(m)
    sys.exit(code)


def resolve_project_root(cli_value: str) -> Path:
    """--project-root > 环境变量 TIPS_PROJECT_ROOT > 报错（v3.0 取消 parent.parent fallback）。"""
    if cli_value:
        root = Path(cli_value).expanduser()
    elif os.environ.get("TIPS_PROJECT_ROOT"):
        root = Path(os.environ["TIPS_PROJECT_ROOT"]).expanduser()
    else:
        fail(1, "[ERROR] 项目根未指定（v3.0 已取消 parent.parent fallback，防误写 skill 目录）",
             "        请用 --project-root <项目根> 或环境变量 TIPS_PROJECT_ROOT 显式传入")
        return None  # unreachable，fail 不返回
    if not root.is_dir():
        fail(1, f"[ERROR] 项目根不存在: {root}")
    return root


def load_pending(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except OSError as e:
        fail(1, f"[ERROR] pending 文件不可读: {path}", f"        {type(e).__name__}: {e}")
    if raw.startswith(b"\xef\xbb\xbf"):
        fail(2, "[ERROR] pending JSON 带 UTF-8 BOM，拒绝解析",
             "        请以 UTF-8 无 BOM 重新保存")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        fail(2, f"[ERROR] pending JSON 不是有效 UTF-8: {e}",
             "        请以 UTF-8 无 BOM 重新保存")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        fail(2, f"[ERROR] pending JSON 语法错误: {e}")
    if not isinstance(data, dict):
        fail(2, f"[ERROR] pending JSON 顶层必须是对象，实际: {type(data).__name__}")

    keys = set(data.keys())
    expected = set(SCHEMA_KEYS)
    missing, extra = sorted(expected - keys), sorted(keys - expected)
    if missing:
        fail(2, f"[ERROR] 缺少 {len(missing)} 个必填字段: {', '.join(missing)}",
             f"        恰好需要 {len(SCHEMA_KEYS)} 个顶层 key: {', '.join(SCHEMA_KEYS)}")
    if extra:
        fail(2, f"[ERROR] 发现 {len(extra)} 个多余字段: {', '.join(extra)}",
             f"        恰好需要 {len(SCHEMA_KEYS)} 个顶层 key，多余字段一律拒绝")
    for k in SCHEMA_KEYS:
        v = data[k]
        if not isinstance(v, str) or not v.strip():
            fail(2, f"[ERROR] 字段 {k} 必须为非空字符串（strip 后非空），实际: {v!r}")
    if len(data["tip_title"]) > TITLE_MAX_CHARS:
        fail(2, f"[ERROR] tip_title 超长: {len(data['tip_title'])} 字（上限 {TITLE_MAX_CHARS} 字，"
             f"封面'结构化答题技巧：'前缀由引擎自动加不计入）: {data['tip_title']!r}")
    return data


def take_snapshot(root: Path):
    """写入前快照模板到 _snapshots_tips/（最多 10 个，超出删最旧）。

    返回 (快照路径 | None, 告警 | None)；快照失败不阻断（内存中已保留写入前字节用于回滚）。
    """
    snap_dir = root / SNAPSHOTS_REL
    tpl = root / TEMPLATE_REL
    try:
        snap_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        snap = snap_dir / f"snapshot_{ts}.docx"
        shutil.copy(tpl, snap)
        for old in sorted(snap_dir.glob("snapshot_*.docx"),
                          key=lambda p: p.stat().st_mtime, reverse=True)[MAX_SNAPSHOTS:]:
            old.unlink()
        return snap, None
    except OSError as e:
        return None, (f"快照创建失败（降级继续，内存已保留写入前字节用于回滚）: "
                      f"{type(e).__name__}: {e}")


def precheck_template(doc: Document) -> list:
    """写入前预检（失败 exit1，模板未动）：段数 / pic:pic / txbxContent / 封面文本框结构。"""
    errors = []
    paras = doc.paragraphs
    if len(paras) != EXPECTED_PARAS:
        errors.append(f"段数预检失败: {len(paras)} (期望 {EXPECTED_PARAS})——模板与 Task3 "
                      f"baseline 不符，疑似漂移/错版，请先恢复 assets/tips-template-baseline.docx")
        return errors
    pic_total = sum(len(p._element.findall(".//" + qn("pic:pic"))) for p in paras)
    if pic_total != EXPECTED_IMG_TOTAL:
        errors.append(f"图片数预检失败: pic:pic={pic_total} (期望 {EXPECTED_IMG_TOTAL})"
                      f"；图数口径是 pic:pic（w:drawing==5 含封面文本框形状，不作数）")
    txbx_total = sum(len(p._element.findall(".//" + qn("w:txbxContent"))) for p in paras)
    if txbx_total != EXPECTED_TXBX:
        errors.append(f"封面文本框数预检失败: txbxContent={txbx_total} (期望 {EXPECTED_TXBX} 双镜像)")
    for i, txbx in enumerate(paras[0]._element.iter(qn("w:txbxContent"))):
        text_paras = [tp for tp in txbx.iter(qn("w:p")) if tp.findall(".//" + qn("w:t"))]
        if len(text_paras) != 2:
            errors.append(f"封面文本框[{i}] 结构异常: 含文本段落 {len(text_paras)} "
                          f"(期望 2: 前缀行 + 标题行)")
    return errors


def set_textline(p_el, text: str) -> None:
    """把文本段（txbxContent 内 w:p）的文本整体替换为 text：首个 w:t 写入，其余清空。

    只改 <w:t> 文本，run/rPr 结构原样保留（样式指纹零漂移的前提）。
    """
    ts = p_el.findall(".//" + qn("w:t"))
    if not ts:
        return
    ts[0].text = text
    for t in ts[1:]:
        t.text = ""


def fill_cover(paragraph, tip_title: str) -> int:
    """封面段 0 双镜像写入：前缀 + tip_title 各 2 处（drawing txbxContent + VML fallback）。

    返回写入镜像数（期望 2）。
    """
    mirrors = 0
    for txbx in paragraph._element.iter(qn("w:txbxContent")):
        text_paras = [tp for tp in txbx.iter(qn("w:p")) if tp.findall(".//" + qn("w:t"))]
        if len(text_paras) != 2:
            continue  # precheck 已拦截，此处防御跳过
        set_textline(text_paras[0], COVER_PREFIX)
        set_textline(text_paras[1], tip_title)
        mirrors += 1
    return mirrors


def replace_run_text_safely(paragraph, new_text: str) -> None:
    """找第一个纯文本 run（有 w:t 且无 drawing）写入，图片 run 完全不动，其余文本 run 清空。"""
    runs = paragraph.runs
    if not runs:
        paragraph.add_run(new_text)  # 模板异常路径：新增 run 无 rPr 会被样式指纹拦截 exit3
        return
    target = None
    for r in runs:
        has_t = bool(r._element.findall(".//" + qn("w:t")))
        has_d = bool(r._element.findall(".//" + qn("w:drawing")))
        if has_t and not has_d:
            target = r
            break
    if target is None:
        paragraph.add_run(new_text)
        return
    target.text = new_text
    for r in runs:
        if r is target:
            continue
        if not r._element.findall(".//" + qn("w:drawing")):
            r.text = ""


def fill_document(doc: Document, content: dict) -> int:
    """按段位映射写入全部 15 字段，返回封面双镜像写入数（期望 2）。"""
    mirrors = fill_cover(doc.paragraphs[0], content["tip_title"])
    for idx, key in BODY_REPLACE_MAP:
        text = content[key]
        if idx in EMOJI_PREFIX:
            text = EMOJI_PREFIX[idx] + text
        replace_run_text_safely(doc.paragraphs[idx], text)
    return mirrors


def capture_style_fingerprint(doc: Document) -> list:
    """逐段捕获样式指纹: 每段 (pPr XML, 各 run rPr XML 元组)，含封面文本框内段落。

    写入只允许改 <w:t> 文本；任何 pPr/rPr 变化（字体/字号/颜色/对齐/加粗/下划线等）
    都会造成指纹不一致，据此拦截"文本对了但样式坏了"的假绿输出。
    段 3 基准含 b+bCs（baseline 实际 pPr/rPr 为准，不手工指定）。
    """
    def para_fp(p_el) -> tuple:
        ppr = p_el.find(qn("w:pPr"))
        run_fps = []
        for r_el in p_el.findall(qn("w:r")):
            rpr = r_el.find(qn("w:rPr"))
            run_fps.append(rpr.xml if rpr is not None else "<none>")
        return (ppr.xml if ppr is not None else "<none>", tuple(run_fps))

    fp = []
    for p in doc.paragraphs:
        el = p._element
        fp.append(para_fp(el))
        for txbx in el.iter(qn("w:txbxContent")):
            for tp in txbx.iter(qn("w:p")):
                fp.append(para_fp(tp))
    return fp


def validate_doc(path: Path, content: dict, fp_before: list) -> list:
    """结构契约 + 15 字段命中 + 引流段 + 末图 + 样式指纹零漂移（对临时文件执行）。"""
    errors = []
    doc = Document(str(path))
    paras = doc.paragraphs

    if len(paras) != EXPECTED_PARAS:
        errors.append(f"段数异常: {len(paras)} (期望 {EXPECTED_PARAS})")
        return errors
    pic_total = sum(len(p._element.findall(".//" + qn("pic:pic"))) for p in paras)
    if pic_total != EXPECTED_IMG_TOTAL:
        errors.append(f"图片总数: pic:pic={pic_total} (期望 {EXPECTED_IMG_TOTAL})")
    txbx_total = sum(len(p._element.findall(".//" + qn("w:txbxContent"))) for p in paras)
    if txbx_total != EXPECTED_TXBX:
        errors.append(f"封面文本框数: txbxContent={txbx_total} (期望 {EXPECTED_TXBX})")

    # 段[0] 封面双镜像: 前缀与 tip_title 各 2 处
    prefix_hits = 0
    title_hits = 0
    for txbx in paras[0]._element.iter(qn("w:txbxContent")):
        for tp in txbx.iter(qn("w:p")):
            ts = tp.findall(".//" + qn("w:t"))
            if not ts:
                continue
            joined = "".join(t.text or "" for t in ts)
            if joined == COVER_PREFIX:
                prefix_hits += 1
            if joined == content["tip_title"]:
                title_hits += 1
    if prefix_hits != EXPECTED_TXBX:
        errors.append(f"段[0] 封面前缀'{COVER_PREFIX}'命中 {prefix_hits} 处 "
                      f"(期望 {EXPECTED_TXBX} 处双镜像同步)")
    if title_hits != EXPECTED_TXBX:
        errors.append(f"段[0] 封面标题未生效或镜像不同步: {title_hits} 处 "
                      f"(期望 {EXPECTED_TXBX} 处)")

    # 15 字段命中: tip_title 由封面镜像校验，此处 14 个正文段
    for idx, key in BODY_REPLACE_MAP:
        expect = EMOJI_PREFIX.get(idx, "") + content[key]
        if expect not in (paras[idx].text or ""):
            errors.append(f"字段未写入或被改动: {key} (段[{idx}])")

    # 固定段[21]: 引流段原文 + 样式（endnote text + jc center + b + color 85120F）
    p21 = paras[21]
    if (p21.text or "") != DRAIN_TEXT:
        errors.append(f"段[21] 引流段原文被改动: {(p21.text or '')!r}")
    if p21.style.name != "endnote text":
        errors.append(f"段[21] 样式名异常: {p21.style.name!r} (期望 'endnote text')")
    r21 = p21.runs[0] if p21.runs else None
    if r21 is None or not (p21.alignment == 1 and r21.bold is True
                           and str(r21.font.color.rgb) == DRAIN_COLOR):
        errors.append("段[21] 引流段样式丢失（须居中 + 加粗 + #85120F）")

    # 固定段: 蓝色标题原文不动（样式由指纹覆盖）
    for idx, expected_text in FIXED_HEADING_PARAS:
        if (paras[idx].text or "") != expected_text:
            errors.append(f"段[{idx}] 固定标题被改动: {(paras[idx].text or '')!r} "
                          f"(期望 {expected_text!r})")

    # 固定段[22]: 末图不动
    if len(paras[END_IMG_PARA]._element.findall(".//" + qn("pic:pic"))) != 1:
        errors.append(f"段[{END_IMG_PARA}] 末图丢失 (期望 1 张 pic:pic)")

    # 样式指纹: 填充前后逐段 pPr/rPr 必须零漂移（含封面文本框内段落；段 3 基准含 b+bCs）
    fp_after = capture_style_fingerprint(doc)
    if len(fp_after) != len(fp_before):
        errors.append(f"样式指纹条目数变化: {len(fp_after)} (期望 {len(fp_before)})")
    else:
        for i, (a, b) in enumerate(zip(fp_after, fp_before)):
            if a != b:
                errors.append(f"样式指纹漂移 @条目{i}: pPr 或 run rPr 与写入前不一致"
                              f"（字体/字号/颜色/对齐/加粗/下划线被改动）")
                break
    return errors


def rollback_template(tpl: Path, original_bytes: bytes) -> bool:
    """把模板字节回滚为写入前内容（临时文件 + os.replace 原子写回）。"""
    try:
        rb = tpl.with_name(tpl.name + ".rollback.tmp")
        rb.write_bytes(original_bytes)
        os.replace(rb, tpl)
        return True
    except OSError:
        return False


def main() -> None:
    ap = argparse.ArgumentParser(
        description="结构化答题技巧·每日一练 帖子生成引擎 v3.0（structured-daily 技巧线）")
    ap.add_argument("--project-root",
                    help="项目根目录（或环境变量 TIPS_PROJECT_ROOT；无目录 fallback）")
    args = ap.parse_args()

    root = resolve_project_root(args.project_root)
    tpl = root / TEMPLATE_REL
    pending = root / PENDING_REL

    if not pending.exists():
        fail(1, f"[ERROR] 待写入文件不存在: {pending}",
             "        请先把新技巧稿写到 pending_tips.json 再运行本脚本")
    if not tpl.exists():
        fail(1, f"[ERROR] 模板不存在: {tpl}")

    content = load_pending(pending)
    print(f"[1/6] schema 校验通过: 15 字段齐 / 标题 {len(content['tip_title'])} 字"
          f"（前缀'{COVER_PREFIX}'由引擎自动加）")

    original_bytes = tpl.read_bytes()  # 任何后续失败以此回滚
    try:
        doc = Document(str(tpl))
    except Exception as e:  # noqa: BLE001 模板损坏/非 docx 一律走环境错误
        fail(1, f"[ERROR] 模板无法解析（已损坏或不是 docx）: {tpl}",
             f"        {type(e).__name__}: {e}",
             "        模板未被改动；请从快照或 assets/tips-template-baseline.docx 恢复后重试")

    pre_errors = precheck_template(doc)
    if pre_errors:
        print(f"[FAIL] 写入前预检发现 {len(pre_errors)} 个问题:")
        for e in pre_errors:
            print(f"  - {e}")
        print(f"[KEEP] 模板未被改动（字节不变），pending 保留排查: {pending}")
        sys.exit(1)
    print(f"[2/6] 写入前预检通过: 段数 {EXPECTED_PARAS} / pic:pic {EXPECTED_IMG_TOTAL}"
          f" / txbxContent {EXPECTED_TXBX}")

    fp_before = capture_style_fingerprint(doc)
    snap, snap_warn = take_snapshot(root)
    if snap_warn:
        print(f"[WARN] {snap_warn}")
    print(f"[3/6] 快照备份: {snap.name if snap else '无（降级继续）'}")

    print("[4/6] 写入 15 字段（封面双镜像 + 14 正文段；段[5]👍/段[11]🙅‍♂️ 引擎自动加段首）")
    mirrors = fill_document(doc, content)

    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".docx", prefix=".fill_tips_tmp_",
                                        dir=str(tpl.parent))
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)
    try:
        doc.save(str(tmp_path))

        print("[5/6] 验证临时文件（结构 + 15 字段命中 + 引流段 + 样式指纹零漂移，未动模板）")
        errors = validate_doc(tmp_path, content, fp_before)
        if errors:
            print(f"[FAIL] 写入后验证发现 {len(errors)} 个问题:")
            for e in errors:
                print(f"  - {e}")
            print(f"[KEEP] 模板未被替换（字节不变），pending 保留排查: {pending}")
            sys.exit(3)
        if mirrors != EXPECTED_TXBX:
            # 预检与验证均已确认双镜像内容正确，此处仅理论兜底
            print(f"[WARN] 封面镜像写入计数 {mirrors}（期望 {EXPECTED_TXBX}），已验证内容正确，继续")

        os.replace(tmp_path, tpl)
        print("[6/6] 原子替换完成")
    finally:
        tmp_path.unlink(missing_ok=True)  # 成功时已被 os.replace 消费；失败路径清理残留

    try:
        pending.unlink()
    except OSError as e:
        print(f"[ERROR] pending 清理失败: {e}")
        if rollback_template(tpl, original_bytes):
            print("[ROLLBACK] 模板已回滚为写入前字节（本次写入作废，pending 保留可重试）")
            fail(4, "[EXIT-4] pending 清理失败，已回滚模板避免\"模板已变 + pending 残留\"中间态",
                 f"        排查 {pending.parent} 目录权限/占用后重跑即可；快照留档: {snap}")
        fail(4, f"[EXIT-4] pending 清理失败且回滚失败，请手工从快照恢复模板: {snap}",
             f"        当前 pending 保留: {pending}")

    print("[OK] 全部验证通过！")
    print(f"     ✅ 段数 {EXPECTED_PARAS} / pic:pic {EXPECTED_IMG_TOTAL} / "
          f"封面双镜像 txbxContent {EXPECTED_TXBX}")
    print("     ✅ 15 字段全部命中（tip_title 封面 2 镜像 + 14 正文段，含段[5]👍/段[11]🙅‍♂️）")
    print("     ✅ 引流段[21] 原文 + 样式不动 / 固定标题 6 段不动 / 末图[22] 不动 / 图片 run 不动")
    print("     ✅ 样式指纹零漂移（逐段 pPr/rPr 与 baseline 一致，含段 3 b+bCs）")
    print("[CLEAN] 已清理 pending_tips.json")
    print(f"快照: {snap}")
    print(f"\n{'=' * 50}\n模板已更新: {tpl}\n{'=' * 50}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
R1-R14 反例 + 结构兼容自查脚本（v1.7 实战升级版）
用法：python r1_self_check.py <dir>

v1.7 新增（2026-06-15）：
- R11: clean_md_content 兼容 4 种优化记录格式（无 > / 无 ** 都吃）
- R12: SKILL 模板"2. 回原文"步骤名误报白名单（人工 verify 后豁免）
- R13: patch 工具嵌套错位元教训——见自验 4 步法
- R14: execute_code 长度限制——本脚本不依赖 execute_code，全部走 terminal

v1.5/v1.6 旧功能保留：R1-R6 + 结构 + 10 红线
"""
import re
import sys
from pathlib import Path


def r1_check(text: str) -> dict:
    """R1-R14 反例严格自查。返回 7 项违规计数。"""
    # R1 四种变体前缀
    r1_v1 = text.count("讲义原话：")
    r1_v2 = text.count("讲义原文：")
    r1_v3 = text.count("原文：")
    r1_v4 = len(re.findall(r'教材\s*[:：]|讲义\s*[:：]', text))
    # R2 孤冒号
    r2 = len(re.findall(r'[。.]\s*[:：]\s*["""]', text))
    # R5 列举式（考点：模块X-Y）
    r5 = len(re.findall(r'[（(][^）)]*考点[：:]\s*模块', text))
    # R6 批量 re.sub 后的"X：" 孤冒号
    r6 = len(re.findall(r'[。.][：:]\s*["""]', text))
    # R12 误报候选：找"2. 回原文"步骤名（不扣分但提示人工 verify）
    r12_candidates = len(re.findall(r'^2\.\s*回原文：', text, re.MULTILINE))
    return {
        "R1_讲义原话:": r1_v1,
        "R1_讲义原文:": r1_v2,
        "R1_原文:": r1_v3,
        "R1_其他前缀:": r1_v4,
        "R2_孤冒号:": r2,
        "R5_列举式:": r5,
        "R6_批re.sub残:": r6,
        "R12_误报候选:": r12_candidates,  # 仅提示，不计入 TOTAL
        "TOTAL": r1_v1 + r1_v2 + r1_v3 + r1_v4 + r2 + r5 + r6,
    }


def r12_verify_white_list(text: str) -> list:
    """R12 误报白名单：返回"原文："出现位置+上下文——若在 ^2\. 回原文 行内，豁免。"""
    suspects = []
    for i, line in enumerate(text.split('\n'), 1):
        if re.match(r'^2\.\s*回原文：', line):
            # 此行是 SKILL 模板规定步骤名 → R12 误报候选
            suspects.append((i, '[R12 误报·已豁免]', line.strip()[:120]))
    return suspects


def struct_check(text: str) -> int:
    """8 大结构宽松正则（兼容'## 模块X'和'## 一、'两种风格）"""
    patterns = [
        r"^## *(?:一|模块一)[、.：:\s]",
        r"^## *(?:二|模块二)[、.：:\s]",
        r"^## *(?:三|模块三)[、.：:\s]",
        r"^## *(?:四|模块四)[、.：:\s]",
        r"^## *(?:五|模块五)[、.：:\s]",
        r"^## *(?:六|模块六)[、.：:\s]",
        r"^## *(?:七|模块七)?[、.：:\s]?记忆口诀",
        r"^##\s*学习导航",
    ]
    return sum(1 for p in patterns if re.search(p, text, re.MULTILINE))


def v36_check(text: str) -> dict:
    """v3.6 新增：修订说明存在性 / 正文授课提示 3-6 处 / 修订说明含 R1 触发词。"""
    parts = text.split("## 【修订说明】")
    body = parts[0]
    xiuding = len(parts) > 1
    mic = body.count("> 🎤 授课提示")
    triggers = 0
    if xiuding:
        for w in ["讲义原话：", "讲义原文：", "原文：", "讲义："]:
            triggers += parts[1].count(w)
    return {"修订说明": xiuding, "授课提示": mic, "修订说明R1": triggers}


def banned_check(text: str) -> list:
    """10 条学员稿红线"""
    banned = ["试试看", "做完再往下", "这一节我带你", "重点看思路", "别看答案",
              "做得对=掌握", "看我是怎么做的", "&nbsp;", "⬇️", "N+1", "M+1"]
    return [w for w in banned if w in text]


def main():
    if len(sys.argv) < 2:
        print("用法: python r1_self_check.py <dir>")
        sys.exit(1)

    target_dir = Path(sys.argv[1])
    if not target_dir.exists():
        print(f"❌ 目录不存在: {target_dir}")
        sys.exit(1)

    files = sorted(target_dir.glob("*.md"))
    if not files:
        print(f"⚠️ 目录无 .md 文件: {target_dir}")
        sys.exit(0)

    print("=" * 70)
    print(f"R1-R14 + 结构 + 10 红线 自查 v1.7（{target_dir}）")
    print("=" * 70)
    all_ok = 0
    total_r1 = 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        r = r1_check(text)
        struct = struct_check(text)
        bans = banned_check(text)
        v36 = v36_check(text)
        # R12 误报豁免：从 R1_原文 中减去 R12_误报候选
        r1_real = r["R1_原文:"] - r["R12_误报候选:"]
        ok = (r["TOTAL"] == 0 and not bans and struct >= 6 and r1_real == 0)
        if ok:
            all_ok += 1
        else:
            total_r1 += r["TOTAL"]
        print(f"  {'✅' if ok else '❌'} {f.name} ({len(text)}字) R1={r['TOTAL']} 结构={struct}/8 红线={len(bans)} 修订说明={'✅' if v36['修订说明'] else '—'} 授课提示={v36['授课提示']} 修订说明R1={v36['修订说明R1']}")
        if r["TOTAL"] > 0:
            for k, v in r.items():
                if v and k != "TOTAL" and k != "R12_误报候选:":
                    print(f"      └ {k}: {v}")
        # R12 误报提示
        if r["R12_误报候选:"] > 0:
            print(f"      └ R12_误报候选: {r['R12_误报候选:']}（已豁免·SKILL 模板合法步骤名）")
        if bans:
            for b in bans:
                print(f"      └ 红线 '{b}': 1")
    print(f"\n📊 合规: {all_ok}/{len(files)} | R1 总违规（真）: {total_r1} | R12 误报豁免: 见每行")
    sys.exit(0 if total_r1 == 0 else 1)


if __name__ == "__main__":
    main()

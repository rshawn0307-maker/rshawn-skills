#!/usr/bin/env python3
"""
公考面试结构化验证脚本（v2.2）：多模式验证

用法：
  # 题目验证（默认模式，向后兼容）
  python validate_question.py <md文件路径> [md文件路径...]
  python validate_question.py 综合分析_01_指尖形式主义.md
  python validate_question.py 综合分析_*.md   (批量)

  # 多模式验证
  python validate_question.py <file> --mode question      # 题目验证（默认）
  python validate_question.py <file> --mode methodology   # 方法论验证
  python validate_question.py <file> --mode framework     # 框架模板验证
  python validate_question.py <file> --mode material      # 素材验证
  python validate_question.py <file> --mode lecture       # 讲义整体验证
  python validate_question.py <file> --mode lecture --expected-chapters 5

输出：
  每个文件的验证结果（汉字数、AI痕迹、用语禁忌、结构完整性等）
  最终汇总：全部通过 / 存在需修正的文件

字数口径：
  逐字稿统计汉字数（不含标点），目标 700-800，硬边界 680-820。
  硬边界外报 error；边界内但不在目标区间报 warning。
"""

import sys
import re
import os
import glob
import argparse

# ============================================================
# 字数标准（v2.2：700-800 汉字，不含标点；硬边界 680-820）
# ============================================================
CHAR_MIN = 680
CHAR_MAX = 820
TARGET_MIN = 700
TARGET_MAX = 800
HAN_RE = re.compile(r"[\u4e00-\u9fff]")

# ============================================================
# AI痕迹关键词（6类）—— 对应 SKILL.md 的 AI 痕迹扫描清单
# ============================================================
AI_PATTERNS = {
    "AI标志性短语": [
        "标志着", "彰显了", "体现了", "不断演变", "至关重要", "不可或缺",
        "深远影响", "深刻变革", "不可磨灭", "深深植根", "关键转折点",
        "为…奠定基础", "为…做出贡献",
    ],
    "AI连接词/填充短语": [
        "此外", "然而", "值得注意的是", "综上所述", "总而言之",
        "更重要的是", "深入探讨", "为了实现这一目标",
        "在这个时间点",
    ],
    "模糊归因": [
        "专家认为", "业内人士表示", "观察者指出",
        "一些批评者认为", "行业报告显示",
    ],
    "否定式排比": [
        "不仅…而且", "这不仅仅是", "不仅…更是",
    ],
    "万能收束": [
        "总之", "综上", "总而言之", "未来可期", "任重道远",
        "前景光明", "追求卓越",
    ],
    "公考高危词": [
        "深入推进", "全面落实", "持续优化", "多措并举",
        "综合施策", "协同推进", "切实保障", "有效提升",
        "有力推动",
    ],
}

# ============================================================
# 用语禁忌关键词（4类）—— 对应 SKILL.md 的公考面试用语禁忌
# ============================================================
FORBIDDEN_WORDS = {
    "贬义比喻词": [
        "落水狗", "狼狈", "龟孙", "痛打", "狼狈为奸",
    ],
    "网络流行词": [
        "韭菜", "小白", "键盘侠", "内卷", "摆烂", "躺平",
        "yyds", "绝绝子",
    ],
    "情绪化表达": [
        "气死", "笑死", "巨坑", "血亏", "无语", "离谱",
    ],
    "政治风险词": [
        "上面不作为", "领导拍脑袋",
    ],
}

# ============================================================
# 素材类型字数标准
# ============================================================
MATERIAL_CHAR_RANGES = {
    "政策文件摘要": (200, 400),
    "典型案例故事": (250, 400),
    "高分金句语录": (50, 150),
    "热点数据统计": (100, 250),
}

MATERIAL_REQUIRED_FRONTMATTER = [
    "type", "素材类型", "题型", "主题", "来源", "updated", "tags"
]

MATERIAL_REQUIRED_SECTIONS = ["素材内容", "适用场景", "使用建议"]


# ============================================================
# 通用工具函数
# ============================================================

def read_file(filepath):
    """读取文件内容"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return None


def count_chars(text):
    """统计字符数（含中文标点，不含空格和换行）"""
    text = text.replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')
    return len(text)


def count_han_chars(text):
    """统计汉字数（不含标点、数字、字母、空格）"""
    return len(HAN_RE.findall(text))


def scan_ai_patterns(text):
    """扫描AI痕迹，返回 {类别: [命中词, ...]}"""
    hits = {}
    for category, patterns in AI_PATTERNS.items():
        matched = []
        for p in patterns:
            if '…' in p:
                parts = p.split('…')
                regex = re.escape(parts[0]) + '.*' + re.escape(parts[1])
                if re.search(regex, text):
                    matched.append(p)
            elif p in text:
                matched.append(p)
        if matched:
            hits[category] = matched
    return hits


def count_dashes(text):
    """统计破折号使用情况，返回含破折号的段落列表 [(段号, 数量)]"""
    paragraphs = [p for p in text.split('\n') if p.strip()]
    overuse = []
    for i, para in enumerate(paragraphs):
        count = para.count('——')
        if count > 0:
            overuse.append((i + 1, count))
    return overuse


def scan_forbidden_words(text):
    """扫描用语禁忌词，返回 {类别: [命中词, ...]}"""
    hits = {}
    for category, words in FORBIDDEN_WORDS.items():
        matched = [w for w in words if w in text]
        if matched:
            hits[category] = matched
    return hits


def detect_three_part_pattern(text):
    """检测机械三段式（第一/第二/第三 在相近位置连续出现）"""
    pattern = r'第一[，,].{0,200}第二[，,].{0,200}第三[，,]'
    if re.search(pattern, text, re.DOTALL):
        return True
    return False


def parse_frontmatter(content):
    """解析 frontmatter，返回 dict 或 None"""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return None
    fm_text = match.group(1)
    fm = {}
    for line in fm_text.split('\n'):
        if ':' in line:
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip()
            if value:
                fm[key] = value
    return fm


# ============================================================
# 模式：question（题目验证，原有功能）
# ============================================================

def extract_answer_text(content):
    """提取'## 答题逐字稿'之后、下一个二级标题或文末分隔线之前的内容。"""
    match = re.search(r'##\s*答题逐字稿\s*\n(.*?)(?=\n##\s|\n---\s*\n|\n---\s*$|\Z)', content, re.DOTALL)
    if not match:
        match = re.search(r'##\s*答题逐字稿\s*\n(.*)', content, re.DOTALL)
    if not match:
        return None
    text = match.group(1)
    lines = []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if stripped.startswith('---'):
            continue
        lines.append(line)
    text = '\n'.join(lines)
    return text


def validate_question(content):
    """验证单个题目 md 文件，返回结果字典"""
    text = extract_answer_text(content)
    if not text or not text.strip():
        return {"error": "未找到'## 答题逐字稿'部分"}

    char_count = count_han_chars(text)
    ai_hits = scan_ai_patterns(text)
    forbidden_hits = scan_forbidden_words(text)
    dash_info = count_dashes(text)
    three_part = detect_three_part_pattern(text)

    char_ok = CHAR_MIN <= char_count <= CHAR_MAX
    char_in_target = TARGET_MIN <= char_count <= TARGET_MAX
    all_clear = (
        char_ok
        and not ai_hits
        and not forbidden_hits
        and not dash_info
        and not three_part
    )

    return {
        "char_count": char_count,
        "char_ok": char_ok,
        "char_in_target": char_in_target,
        "ai_hits": ai_hits,
        "forbidden_hits": forbidden_hits,
        "dash_overuse": dash_info,
        "three_part_pattern": three_part,
        "all_clear": all_clear,
    }


# ============================================================
# 模式：methodology（方法论验证）
# ============================================================

def validate_methodology(content):
    """验证方法论段落，返回结果字典"""
    errors = []
    warnings = []

    # 检查必需段落
    required_sections = ["题型特征", "核心方法论要点", "常见误区与规避"]
    for section in required_sections:
        if section not in content:
            errors.append(f"缺少必需段落: {section}")

    # 提取方法论部分（## 一、答题方法论 到 ## 二、答题框架模板 之间）
    match = re.search(r'##\s*一、答题方法论\s*\n(.*?)(?:##\s*二、答题框架模板|\Z)', content, re.DOTALL)
    method_text = match.group(1) if match else content

    # 检查要点数量（#### 级标题）
    point_matches = re.findall(r'####\s+.+', method_text)
    point_count = len(point_matches)
    if point_count < 6:
        errors.append(f"核心方法论要点不足: {point_count}个 (需6-8个)")
    elif point_count > 8:
        warnings.append(f"核心方法论要点偏多: {point_count}个 (建议6-8个)")

    # 检查例句覆盖（每个要点至少2条 > 引用）
    points_with_quotes = re.findall(r'####\s+.+?\n(.*?)(?=####\s|\Z)', method_text, re.DOTALL)
    for i, point_text in enumerate(points_with_quotes):
        quote_count = len(re.findall(r'^>\s', point_text, re.MULTILINE))
        if quote_count < 2:
            warnings.append(f"要点{i+1}例句不足: {quote_count}条 (建议至少2条)")

    # 检查误区表格行数
    table_rows = re.findall(r'\|[^|]+\|[^|]+\|[^|]+\|', method_text)
    # 减去表头和分隔行
    actual_rows = max(0, len(table_rows) - 2)
    if actual_rows < 5:
        errors.append(f"误区表格行数不足: {actual_rows}行 (需至少5行)")

    # 字数检查
    char_count = count_chars(method_text)
    char_ok = 1500 <= char_count <= 4000
    if not char_ok:
        warnings.append(f"字数 {char_count} 不在 1500-4000 范围")

    # AI痕迹扫描
    ai_hits = scan_ai_patterns(method_text)

    all_clear = len(errors) == 0 and not ai_hits

    return {
        "char_count": char_count,
        "char_ok": char_ok,
        "point_count": point_count,
        "table_rows": actual_rows,
        "ai_hits": ai_hits,
        "errors": errors,
        "warnings": warnings,
        "all_clear": all_clear,
    }


# ============================================================
# 模式：framework（框架模板验证）
# ============================================================

def validate_framework(content):
    """验证框架模板段落，返回结果字典"""
    errors = []
    warnings = []

    # 检查必需段落
    required_sections = ["完整结构", "结构要点"]
    for section in required_sections:
        if section not in content:
            errors.append(f"缺少必需段落: {section}")

    # 提取框架部分（## 二、答题框架模板 到 ## 三、例题汇编 之间）
    match = re.search(r'##\s*二、答题框架模板\s*\n(.*?)(?:##\s*三、例题汇编|\Z)', content, re.DOTALL)
    framework_text = match.group(1) if match else content

    # 检查代码块
    code_blocks = re.findall(r'```\n(.*?)```', framework_text, re.DOTALL)
    if len(code_blocks) < 1:
        errors.append("完整结构下缺少代码块")
    else:
        # 检查占位符（至少3处 [占位说明] 或 {占位} 格式）
        full_code = '\n'.join(code_blocks)
        placeholders = re.findall(r'[\[{【][^}\]】]+[\]}】]', full_code)
        if len(placeholders) < 3:
            warnings.append(f"代码块内占位符不足: {len(placeholders)}处 (建议至少3处)")

        # 检查【破题】和【收尾】标记
        if '【破题】' not in full_code and '破题' not in full_code:
            errors.append("代码块缺少【破题】标记")
        if '【收尾】' not in full_code and '收尾' not in full_code:
            errors.append("代码块缺少【收尾】标记")

    # AI痕迹扫描
    ai_hits = scan_ai_patterns(framework_text)

    all_clear = len(errors) == 0 and not ai_hits

    return {
        "code_blocks": len(code_blocks),
        "ai_hits": ai_hits,
        "errors": errors,
        "warnings": warnings,
        "all_clear": all_clear,
    }


# ============================================================
# 模式：material（素材验证）
# ============================================================

def validate_material(content):
    """验证素材 md 文件，返回结果字典"""
    errors = []
    warnings = []

    # 检查 frontmatter
    fm = parse_frontmatter(content)
    if not fm:
        errors.append("缺少 frontmatter")
        fm = {}
    else:
        for field in MATERIAL_REQUIRED_FRONTMATTER:
            if field not in fm:
                errors.append(f"frontmatter 缺少字段: {field}")

    # 检查素材类型
    material_type = fm.get("素材类型", "")
    if material_type and material_type not in MATERIAL_CHAR_RANGES:
        errors.append(f"素材类型无效: {material_type} (需为4种之一)")

    # 检查必需段落
    for section in MATERIAL_REQUIRED_SECTIONS:
        if section not in content:
            errors.append(f"缺少必需段落: {section}")

    # 提取素材内容部分
    content_match = re.search(r'##\s*素材内容\s*\n(.*?)(?:##\s*适用场景|\Z)', content, re.DOTALL)
    material_text = content_match.group(1) if content_match else ""

    # 字数检查（按类型）
    char_count = count_chars(material_text)
    if material_type in MATERIAL_CHAR_RANGES:
        min_chars, max_chars = MATERIAL_CHAR_RANGES[material_type]
        char_ok = min_chars <= char_count <= max_chars
        if not char_ok:
            warnings.append(f"字数 {char_count} 不在 {min_chars}-{max_chars} 范围（{material_type}）")
    else:
        char_ok = True  # 无法确定类型时跳过字数检查

    # 来源标注检查
    source = fm.get("来源", "")
    if not source:
        errors.append("frontmatter 来源字段为空")

    # AI痕迹扫描（仅素材内容段落）
    ai_hits = scan_ai_patterns(material_text) if material_text else {}

    all_clear = len(errors) == 0 and not ai_hits

    return {
        "material_type": material_type,
        "char_count": char_count,
        "char_ok": char_ok,
        "ai_hits": ai_hits,
        "errors": errors,
        "warnings": warnings,
        "all_clear": all_clear,
    }


# ============================================================
# 模式：lecture（讲义整体验证）
# ============================================================

def extract_lecture_questions(content):
    """提取讲义中所有嵌入的答题逐字稿（#### 四级标题）"""
    pattern = r'####\s*答题逐字稿\s*\n(.*?)(?=\n####\s|\n###\s|\n##\s|\n#\s|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    return matches


def validate_lecture(content, expected_chapters=5):
    """验证讲义整体结构（兼容旧章结构与一本通篇结构），返回结果字典"""
    errors = []
    warnings = []
    question_results = []

    # 结构单位：优先识别“第X篇”（一本通），其次兼容旧“第X章”
    part_matches = re.findall(r'^#\s+第.+篇', content, re.MULTILINE)
    chapter_matches = re.findall(r'^#\s+第.+章', content, re.MULTILINE)
    if part_matches:
        section_matches = part_matches
        unit = "篇"
    else:
        section_matches = chapter_matches
        unit = "章"
    section_count = len(section_matches)

    if section_count != expected_chapters:
        errors.append(f"{unit}数量: {section_count} (期望 {expected_chapters})")

    # 编号连续性检查
    section_nums = []
    for match in section_matches:
        num_match = re.search(rf'第([一二三四五六七八九十]+){unit}', match)
        if num_match:
            num_str = num_match.group(1)
            num_map = {"一":1, "二":2, "三":3, "四":4, "五":5,
                       "六":6, "七":7, "八":8, "九":9, "十":10}
            if num_str in num_map:
                section_nums.append(num_map[num_str])

    for i, num in enumerate(section_nums):
        if num != i + 1:
            errors.append(f"{unit}编号不连续: 第{section_nums[i]}{unit}出现在位置{i+1}")
            break

    # 前言一致性检查（仅在前言区域搜索，避免误匹配正文）
    first_heading = f'# 第一{unit}'
    preface_section = content[:content.find(first_heading)] if first_heading in content else content[:5000]
    cn_num_map = {"一":1, "二":2, "三":3, "四":4, "五":5, "六":6, "七":7, "八":8, "九":9, "十":10}
    stated_sections = None
    if unit == "篇":
        preface_match = re.search(r'(?:全书|共)\s*分?\s*(\d+)\s*篇', preface_section)
        if preface_match:
            stated_sections = int(preface_match.group(1))
        else:
            cn_match = re.search(r'(?:全书|共)\s*分?\s*([一二三四五六七八九十]+)\s*篇', preface_section)
            if cn_match:
                stated_sections = cn_num_map.get(cn_match.group(1), 0)
    else:
        preface_match = re.search(r'共\s*(\d+)\s*章', preface_section)
        if preface_match:
            stated_sections = int(preface_match.group(1))
        else:
            cn_match = re.search(r'共\s*分?\s*([一二三四五六七八九十]+)\s*章', preface_section)
            if cn_match:
                stated_sections = cn_num_map.get(cn_match.group(1), 0)
    if stated_sections is not None and stated_sections != section_count:
        errors.append(f"前言描述{unit}数({stated_sections})与实际({section_count})不符")

    # 旧章结构的题型章结构检查（1-6章应含三节）；一篇结构不适用
    if unit == "章":
        type_chapters = section_nums[:6] if len(section_nums) >= 6 else section_nums
        for ch_num in type_chapters:
            num_map_rev = {1:"一", 2:"二", 3:"三", 4:"四", 5:"五", 6:"六"}
            ch_name = num_map_rev.get(ch_num, "")
            if ch_name:
                ch_pattern = f'# 第{ch_name}章.*?(?=# 第|$)'
                ch_match = re.search(ch_pattern, content, re.DOTALL)
                if ch_match:
                    ch_text = ch_match.group(0)
                    for section in ["答题方法论", "答题框架模板", "例题汇编"]:
                        if section not in ch_text:
                            warnings.append(f"第{ch_name}章缺少段落: {section}")
    else:
        if '# 附录' not in content and '附录' not in content:
            warnings.append("一篇结构未找到附录")

    # 嵌入题目验证
    questions = extract_lecture_questions(content)
    total_questions = len(questions)
    passed_questions = 0
    failed_questions = []
    off_target_questions = []

    for i, q_text in enumerate(questions):
        # 清理 markdown 标记
        lines = []
        for line in q_text.split('\n'):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if stripped.startswith('---'):
                continue
            lines.append(line)
        clean_text = '\n'.join(lines)

        char_count = count_han_chars(clean_text)
        char_ok = CHAR_MIN <= char_count <= CHAR_MAX
        char_in_target = TARGET_MIN <= char_count <= TARGET_MAX
        ai_hits = scan_ai_patterns(clean_text)

        if char_ok and not ai_hits:
            passed_questions += 1
            if not char_in_target:
                off_target_questions.append((i + 1, char_count))
        else:
            failed_questions.append({
                "index": i + 1,
                "char_count": char_count,
                "char_ok": char_ok,
                "ai_hits": ai_hits,
            })

    if off_target_questions:
        preview = '、'.join(f"第{idx}道({count})" for idx, count in off_target_questions[:8])
        more = f" 等{len(off_target_questions)}道" if len(off_target_questions) > 8 else ""
        warnings.append(f"逐字稿在硬边界内但未落在目标 {TARGET_MIN}-{TARGET_MAX}: {preview}{more}")

    # frontmatter updated 检查
    fm = parse_frontmatter(content)
    if fm and "updated" not in fm:
        warnings.append("frontmatter 缺少 updated 字段")

    all_clear = len(errors) == 0 and len(failed_questions) == 0

    return {
        "chapter_count": section_count,
        "unit": unit,
        "expected_chapters": expected_chapters,
        "total_questions": total_questions,
        "passed_questions": passed_questions,
        "failed_questions": failed_questions,
        "errors": errors,
        "warnings": warnings,
        "all_clear": all_clear,
    }


# ============================================================
# 报告打印
# ============================================================

def print_question_report(filename, result):
    """打印题目验证报告"""
    print(f"\n{'=' * 60}")

    if "error" in result:
        print(f"❌ {filename}: {result['error']}")
        return False

    print(f"📄 {filename}")
    print(f"{'=' * 60}")

    if not result['char_ok']:
        char_status = "❌"
    elif not result.get('char_in_target', True):
        char_status = "⚠️"
    else:
        char_status = "✅"
    print(f"{char_status} 汉字数: {result['char_count']} (目标 {TARGET_MIN}-{TARGET_MAX}，硬边界 {CHAR_MIN}-{CHAR_MAX})")
    if result['char_ok'] and not result.get('char_in_target', True):
        print(f"   ⚠️  在硬边界内但未落在目标 {TARGET_MIN}-{TARGET_MAX}，建议改回目标区间")

    if result['ai_hits']:
        print(f"❌ AI痕迹命中:")
        for cat, words in result['ai_hits'].items():
            print(f"   {cat}: {', '.join(words)}")
    else:
        print(f"✅ AI痕迹: 零命中")

    if result['forbidden_hits']:
        print(f"❌ 用语禁忌命中:")
        for cat, words in result['forbidden_hits'].items():
            print(f"   {cat}: {', '.join(words)}")
    else:
        print(f"✅ 用语禁忌: 零命中")

    if result['dash_overuse']:
        print(f"⚠️  破折号未清零:")
        for para_num, count in result['dash_overuse']:
            print(f"   第{para_num}段: {count}个破折号 (应清零)")
    else:
        print(f"✅ 破折号: 正常")

    if result['three_part_pattern']:
        print(f"⚠️  检测到机械三段式 (第一/第二/第三 连续)")
    else:
        print(f"✅ 三段式: 未检测到")

    if result['all_clear']:
        if not result.get('char_in_target', True):
            print(f"\n⚠️  硬边界内通过，建议改回目标 {TARGET_MIN}-{TARGET_MAX}")
        else:
            print(f"\n✅ 全部通过")
    else:
        print(f"\n❌ 存在问题，需修正")

    return result['all_clear']


def print_methodology_report(filename, result):
    """打印方法论验证报告"""
    print(f"\n{'=' * 60}")
    print(f"📋 {filename} [方法论验证]")
    print(f"{'=' * 60}")

    if "error" in result:
        print(f"❌ {result['error']}")
        return False

    print(f"字数: {result['char_count']} (目标 1500-4000) {'✅' if result['char_ok'] else '⚠️'}")
    print(f"要点数: {result['point_count']} (目标 6-8)")
    print(f"误区表格: {result['table_rows']}行 (目标 ≥5)")

    if result['ai_hits']:
        print(f"❌ AI痕迹命中:")
        for cat, words in result['ai_hits'].items():
            print(f"   {cat}: {', '.join(words)}")
    else:
        print(f"✅ AI痕迹: 零命中")

    for err in result['errors']:
        print(f"❌ {err}")
    for warn in result['warnings']:
        print(f"⚠️  {warn}")

    print(f"\n{'✅ 全部通过' if result['all_clear'] else '❌ 存在问题'}")
    return result['all_clear']


def print_framework_report(filename, result):
    """打印框架模板验证报告"""
    print(f"\n{'=' * 60}")
    print(f"🏗️  {filename} [框架模板验证]")
    print(f"{'=' * 60}")

    if "error" in result:
        print(f"❌ {result['error']}")
        return False

    print(f"代码块数: {result['code_blocks']}")

    if result['ai_hits']:
        print(f"❌ AI痕迹命中:")
        for cat, words in result['ai_hits'].items():
            print(f"   {cat}: {', '.join(words)}")
    else:
        print(f"✅ AI痕迹: 零命中")

    for err in result['errors']:
        print(f"❌ {err}")
    for warn in result['warnings']:
        print(f"⚠️  {warn}")

    print(f"\n{'✅ 全部通过' if result['all_clear'] else '❌ 存在问题'}")
    return result['all_clear']


def print_material_report(filename, result):
    """打印素材验证报告"""
    print(f"\n{'=' * 60}")
    print(f"📦 {filename} [素材验证]")
    print(f"{'=' * 60}")

    if "error" in result:
        print(f"❌ {result['error']}")
        return False

    print(f"素材类型: {result['material_type'] or '未指定'}")
    print(f"字数: {result['char_count']}")

    if result['ai_hits']:
        print(f"❌ AI痕迹命中:")
        for cat, words in result['ai_hits'].items():
            print(f"   {cat}: {', '.join(words)}")
    else:
        print(f"✅ AI痕迹: 零命中")

    for err in result['errors']:
        print(f"❌ {err}")
    for warn in result['warnings']:
        print(f"⚠️  {warn}")

    print(f"\n{'✅ 全部通过' if result['all_clear'] else '❌ 存在问题'}")
    return result['all_clear']


def print_lecture_report(filename, result):
    """打印讲义验证报告"""
    print(f"\n{'=' * 60}")
    print(f"📖 {filename} [讲义验证]")
    print(f"{'=' * 60}")

    if "error" in result:
        print(f"❌ {result['error']}")
        return False

    unit = result.get('unit', '章')
    print(f"{unit}数: {result['chapter_count']} (期望 {result['expected_chapters']})")
    print(f"嵌入题目: {result['total_questions']}道")
    print(f"  通过: {result['passed_questions']}道")
    print(f"  未通过: {len(result['failed_questions'])}道")

    if result['failed_questions']:
        print(f"\n未通过题目详情:")
        for fq in result['failed_questions'][:10]:  # 最多显示10条
            status = []
            if not fq['char_ok']:
                status.append(f"汉字数{fq['char_count']}超出{CHAR_MIN}-{CHAR_MAX}")
            if fq['ai_hits']:
                status.append(f"AI痕迹{sum(len(v) for v in fq['ai_hits'].values())}处")
            print(f"  第{fq['index']}道: {', '.join(status)}")
        if len(result['failed_questions']) > 10:
            print(f"  ...还有 {len(result['failed_questions']) - 10} 道未通过")

    for err in result['errors']:
        print(f"❌ {err}")
    for warn in result['warnings']:
        print(f"⚠️  {warn}")

    print(f"\n{'✅ 全部通过' if result['all_clear'] else '❌ 存在问题'}")
    return result['all_clear']


# ============================================================
# 主流程
# ============================================================

VALIDATE_MODES = {
    "question": (validate_question, print_question_report),
    "methodology": (validate_methodology, print_methodology_report),
    "framework": (validate_framework, print_framework_report),
    "material": (validate_material, print_material_report),
    "lecture": (validate_lecture, print_lecture_report),
}


def expand_wildcards(args):
    """展开通配符参数（Windows cmd 不自动展开 *.md）"""
    files = []
    for arg in args:
        if '*' in arg or '?' in arg:
            matched = sorted(glob.glob(arg))
            if matched:
                files.extend(matched)
            else:
                files.append(arg)
        else:
            files.append(arg)
    return files


def main():
    parser = argparse.ArgumentParser(
        description="公考面试结构化验证脚本 v2.2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python validate_question.py question_01.md                    # 题目验证（默认）
  python validate_question.py *.md --mode question              # 批量题目验证
  python validate_question.py methodology.md --mode methodology # 方法论验证
  python validate_question.py framework.md --mode framework     # 框架模板验证
  python validate_question.py material.md --mode material       # 素材验证
  python validate_question.py lecture.md --mode lecture         # 讲义验证
  python validate_question.py lecture.md --mode lecture --expected-chapters 5
        """
    )
    parser.add_argument("files", nargs="+", help="md文件路径（支持通配符）")
    parser.add_argument("--mode", default="question",
                        choices=["question", "methodology", "framework", "material", "lecture"],
                        help="验证模式（默认: question）")
    parser.add_argument("--expected-chapters", type=int, default=5,
                        help="讲义期望篇数（仅 --mode lecture 使用；一本通默认 5 篇，旧章结构可传章数）")

    args = parser.parse_args()

    mode = args.mode
    validate_func, print_func = VALIDATE_MODES[mode]

    files = expand_wildcards(args.files)
    all_clear = True
    total = 0
    passed = 0

    for filepath in files:
        if not os.path.exists(filepath):
            print(f"\n❌ 文件不存在: {filepath}")
            all_clear = False
            continue

        total += 1
        content = read_file(filepath)
        if content is None:
            print(f"\n❌ 读取失败: {filepath}")
            all_clear = False
            continue

        # 调用对应模式的验证函数
        if mode == "lecture":
            result = validate_func(content, args.expected_chapters)
        else:
            result = validate_func(content)

        result_with_error = result if "error" in result else result
        ok = print_func(os.path.basename(filepath), result_with_error)
        if ok:
            passed += 1
        else:
            all_clear = False

    print(f"\n{'=' * 60}")
    print(f"汇总 [{mode}模式]: {passed}/{total} 文件通过验证")
    if all_clear and total > 0:
        print(f"🎉 全部通过！")
    elif total == 0:
        print(f"⚠️  没有找到可验证的文件")
    else:
        print(f"⚠️  存在需修正的文件，请按报告修改后重跑。")
    print(f"{'=' * 60}")

    sys.exit(0 if (all_clear and total > 0) else 1)


if __name__ == "__main__":
    main()

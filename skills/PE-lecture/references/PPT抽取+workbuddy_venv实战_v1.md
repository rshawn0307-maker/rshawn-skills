# 实战 v1：PPT 抽取 + workbuddy venv 实战（2026-06-18）

> 来源：网球 PPT（14 篇）+ 运动生理 PPT（4 篇）双实战验证

## 1. 老板 PPT 附件真实位置

`<项目根>/02_Hermes_教师编体育学科教研/.hermes/desktop-attachments/`（**不是** 01_教师编... 下的 `.hermes/desktop-attachments/`——**老板 PPT 都堆在 02_Hermes**）。

**新工作区（01_教师编）下 `.hermes/desktop-attachments/` 只有历史备份的 SKILL.md + xlsx 模板**——**PPT 不会自动同步到 01_教师编**。

## 2. pptx 库 + Python 环境：workbuddy venv

**Hermes venv 的 docx 在某些 path 不可 import**（v1.0 实战）——改用 **workbuddy venv**（**稳定可用**）：

```bash
# 实际可用（2026-06-18 验证）：
<Python 环境>

# 验证命令（必跑）：
"<Python 环境>" -c "import docx, pptx; print('OK')"
```

**R1 自查脚本也用这个 python**（因为 R1 脚本本身不依赖 docx，但 workflow 必须用同一个 python）。

## 3. PPT 抽取 4 大坑

### 坑 1：`p.slides[:5]` 切片语法报错

```python
# ❌ 报错 AttributeError: 'list' object has no attribute 'rId'
for i, slide in enumerate(p.slides[:5]):

# ✅ 正确
slides = list(p.slides)
for i, slide in enumerate(slides[:5]):
```

### 坑 2：必须过滤水印段

老板 PPT 几乎每页都有 **"三有考编 / 世豪老师"** 等水印段——grep 必过滤掉：

```python
# ✅ 过滤水印
for i, p in enumerate(slides):
    text_parts = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                t = para.text.strip()
                # 过滤水印 + 空段
                if t and '世豪老师' not in t and '三有考编' not in t:
                    text_parts.append(t)
    if text_parts:
        print(f'Slide {i+1}: {" | ".join(text_parts)[:200]}')
```

### 坑 3：32 MB PPT 抽取超时

- 网球 PPT = 32.2 MB（28 slides）
- 运动生理 PPT = 25.6 MB（43 slides）

**建议**：用 workbuddy venv 跑（hermes venv 在大文件上经常超时）。

### 坑 4：R1/R12 误报精确区分

**R12 误报**已自动豁免"2. 回原文——"破折号 → 但 **R1_原文 仍是真违规**——写稿时钉钉"零前缀"是预防，**写完后仍要 patch 破折号**（不是"豁免后就完全不用管"）；R1_其他前缀（"讲义：""原文："）永远是真违规必须 patch。

```python
# 写稿后批量 patch 必跑
text = text.replace('2. 回原文：', '2. 回原文——')  # R12 已豁免
# R1_其他前缀需 patch 为 PPT 标记（避免 R1）
# 例："讲义：**" → "「PPT」**"
```

## 4. 4 篇拆点节奏（按实际章节量）

**默认节奏**：01 概述 + 02 基本技术上 + 03 基本技术下+战术 + 04 竞赛规程+裁判

**老板新规则（2026-06-18 游泳澄清）**：**严格按讲义/PPT 实际章节量决定篇数**——游泳讲义只有 2 章（概述+蛙爬），A 选"3 篇"而非默认 4 篇。

**实战策略**：clarify 时给老板 4 篇默认 + 短篇（如 3 篇/2 篇）选项，让老板按实际章节量拍板。

## 5. 输出文件命名（PPTX 内容）

写稿顶部元数据加 **"数据来源"** 行：

```markdown
> **数据来源**：基于 PPT「运动生理-3 骨骼肌机能；循环机能.pptx」（老板提供，讲义上无对应内容）
```

这样学员/审核能看到本稿来自 PPT（不是浙江教材）。

## 6. 35 篇总产出（2026-06-18 累计）

9 模块（田径+篮球+足球+排球+乒乓+羽毛+网球+游泳+运动生理）共 **35 篇讲稿** + 1 个下册 docx（104 KB）+ umbrella v1.5/v2.0。

老板可能继续推进 PPT 模式（运动生理 PPT 验证可复现）——下次接 PPT 类任务时**直接用本 reference 工作流**。
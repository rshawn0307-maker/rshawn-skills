# PPT 无讲义处理 SOP v1（2026-06-15 网球 4 篇实战验证）

> **适用场景**：用户给 PPT（如「网球.pptx」）作讲义底本，无独立 .docx 讲义时

## 1. PPT 抽取 5 步

### Step 1：装库验证

```bash
"<Python 环境>" -c "import pptx; print('pptx OK:', pptx.__file__)"
```

workbuddy venv 在 hermes-agent venv 不工作时是备份 Python 环境（docx/pptx 都有装）。

### Step 2：禁用切片陷阱

```python
# ❌ 错误（课件非标准 PPT 时报错 AttributeError: 'list' object has no attribute 'rId'）：
for i, slide in enumerate(p.slides[:5]):
    ...

# ✅ 正确（list() 后 enumerate）：
slides = list(p.slides)
for i in range(min(5, len(slides))):
    slide = slides[i]
```

### Step 3：抽章节大纲（先看小范围）

```python
from pptx import Presentation
p = Presentation(r'...')
slides = list(p.slides)
print(f'总 slide 数: {len(slides)}')
for i, slide in enumerate(slides):
    text_parts = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                t = para.text.strip()
                if t:
                    text_parts.append(t)
    full_text = ' | '.join(text_parts)
    print(f'Slide {i+1} ({len(text_parts)}段): {full_text[:200]}')
```

### Step 4：按大纲拆 4 篇（参考讲义 SOP）

- 4 篇拆点固定：01 概述起源 / 02 组织赛事 / 03 竞赛规则计分 / 04 场地赛制种类
- 边界处理：PPT 内容外的技术细节**不补**（如网球无技术内容就坦白）——按 SKILL v2.3 边界处理

### Step 5：写稿标识规范

- 每篇顶部元数据加：**数据来源：基于讲义 PPT「xxx.pptx」（老板提供，无独立讲义）**
- 讲义原话引用用 **`「PPT」`**（不带冒号，**不是**"讲义："前缀）——R1 违规规避

## 2. R1 反弹预防 4 钉钉（写稿时脑里）

1. **不加"讲义："前缀** → 改用「PPT」引出词
2. **不加"讲义原文：xxxx"** → 改用「PPT」xxx
3. **模块三"2. 回原文："步骤名** → 改破折号"2. 回原文——"
4. **不加"考点：模块X-Y XXX"尾巴** → 删 或 移到模块五

## 3. R12 误报豁免（v1.7 脚本升级）

- R12 检测"2. 回原文："字面字符串——但 v1.7 脚本已加白名单豁免 `^2\. 回原文` 行
- **真 R1_R原文 仍报**：破折号改了之后无真违规

## 4. 网球 4 篇实战结构

| # | PPT slide 范围 | 主题 | 字数 |
|---|---------------|------|------|
| 01 | 4-5 | 起源 4 阶段+1885 传入+1896 入奥 | 5202 |
| 02 | 6-10 | 3 大组织（ITF+ATP+WTA）+8 大赛事 | 6179 |
| 03 | 13-19 | 发球 7 规定+失分 7+计分（15/30/40+决胜局） | 8827 |
| 04 | 20-24 | 场地 23.77×8.23+赛制+4 大场地种类 | 7159 |

## 5. 已知坑

- `p.slides[:5]` 切片语法在某些 PPT 文件报错——**永远用 `list(p.slides)[i]`**
- pptx 库**只抽文字**，图片/表格内容丢失——PPT 教学图要单独 OCR 或让老板提供文字版
- 老板习惯**给 PPT 在 .hermes/desktop-attachments/**——永远 verify 路径再抽

## 6. 关联文件

- 主 SKILL umbrella：`jiaoyi-fansan-anli/SKILL.md`（触发分支 + 0 反弹曲线 + 写稿钉钉）
- 反例自查脚本：`scripts/r1_self_check.py`（v1.7 自动豁免 R12）
- 真路径速查：`references/老板项目真路径_v1.md`
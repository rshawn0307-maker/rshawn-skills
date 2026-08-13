# 大讲义抽章节 SOP（venv python + python-docx 行号切片）

> 来源：2026-06-10 5 大模块（3 体育游戏 226 行 / 4 运动解剖学 750 行 / 5 运动生理学 352 行）实战归纳。

## 为什么需要这个 SOP

- 教师编讲义 docx 通常 **2-3 MB**（含大量排版、表格、图）
- `grep` 全文会撞 **50K stdout cap**（execute_code 沙箱限制）
- `terminal` 跑 `python -c "import docx..."` 多行嵌 f-string/dict 易 SyntaxError
- 一次性 print 大量行到 stdout 易撞 sandbox timeout 拦截

## 3 步 SOP

### 步骤 1：找模块边界（find_mod*.py）

写 `<临时目录>/find_mod*.py`（git-bash 路径）：

```python
import docx
d = docx.Document(r"<讲义绝对路径>")
for i, p in enumerate(d.paragraphs):
    t = p.text.strip()
    if ("<模块关键词>" in t or "<下个模块关键词>" in t) and len(t) < 80:
        print("[" + str(i).zfill(4) + "]" + p.style.name[:8] + "|" + t)
```

**跑法**：
```bash
"<Python 环境>" \
  "<临时目录>\find_mod5.py" > \
  "<临时目录>\mod5.txt"
```

### 步骤 2：抽章节大纲（mod*_outline.py）

找到模块行号范围（如 1804-2155）后，抽标题行：

```python
import docx
d = docx.Document(r"<讲义路径>")
for i, p in enumerate(d.paragraphs):
    if <起始行> <= i <= <结束行>:
        t = p.text.strip()
        # 短行 + Normal 标题 / "一、二、三"开头 = 章节标题
        if t and (p.style.name == "Normal" or
                  (len(t) < 60 and (t.startswith("一、") or t.startswith("第")))):
            print("[" + str(i).zfill(4) + "]" + p.style.name[:8] + "|" + t)
```

**输出落临时 txt**，再 `read_file` 读 —— **不要在 execute_code 内 print 后回显**（撞 sandbox timeout）。

### 步骤 3：抽章节原料（mod*_p1.py 等）

按拆解篇数切成 N 段（如 02 原料 = 1985-2112 / 03 原料 = 2113-2155），分别写脚本：

```python
import docx
d = docx.Document(r"<讲义路径>")
print("========== XX 原料 (起始-结束) ==========")
for i, p in enumerate(d.paragraphs):
    if <起始> <= i <= <结束>:
        t = p.text.strip()
        if t:
            print("[" + str(i).zfill(4) + "]" + p.style.name[:8] + "|" + t)
```

同样 **落临时 txt** 再 read。

## 关键陷阱

1. **venv python 路径**：必须用 `<Python 环境>`，**不是** git-bash `python` alias（后者跑 Python312 找不到 docx）
2. **f-string 内嵌 dict**：`f"...{ {'k': 'v'} }..."` 会 SyntaxError；用 `"..." + str({...}) + "..."` 替代
3. **execute_code 沙箱 timeout**：大段 print 输出撞 sandbox 上限——**必须** write_file 落临时 txt 后 read_file 读
4. **大讲义范围**：≥750 行 = 4 运动解剖学规模；≤350 行 = 5 运动生理学规模；2-3 篇正合适
5. **行号 0 vs 1 索引**：python-docx `paragraphs` 是 0 索引，但显示时 `zfill(4)` 输出 4 位数便于阅读

## 已验证 5 大模块抽取行号

| 模块 | 行号范围 | 篇幅 | 拆篇数 |
|------|----------|------|--------|
| 第三模块·体育游戏 | 831-1056 | 226 行 | 3 篇 |
| 第四模块·运动解剖学 | 1057-1803 | **750 行**（最大） | 5 篇 |
| 第五模块·运动生理学 | 1804-2155 | 352 行 | 3 篇 |
| 第六模块·体育保健学 | 2156-? | 待抽 | 待定 |
| 第七模块·运动训练学 | ?-末 | 待抽 | 待定 |

## 关联文件

- `scripts/r1_self_check.py` —— 反例自查脚本（写完稿跑）
- 本地 SKILL v2.3 —— `01_教师编体育学科教研/01_笔试/05_学员稿/举一反三讲稿/SKILL_举一反三讲解稿_v2.3.md`

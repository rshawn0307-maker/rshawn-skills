# 下册 docx 同步工作流 v1（2026-06-13 实战验证）

> 触发：老板说"合并下册"/"同步下册 docx"/"把田径+篮球同步到 docx"。本文件是 SKILL.md "下册 docx 同步工作流"小节的详细展开版。

## 与现有 SOP 的分工

| 流程 | 触发 | 起点 | 工具 |
|------|------|------|------|
| 批量产出 SOP | 老板给新讲义写稿 | md 起点 | r1_self_check.py |
| 批量审核工作流 | 老板说"审核某模块" | 改既有 md | r1_self_check.py |
| **下册 docx 同步**（v1.4 新增）| 老板说"合并下册"/"同步 docx" | **md → docx 转换** | verify_v1_下 |

## 5 步成体系（详细版）

### 步骤 0：umbrella stale 风险预检（必做，不能跳）

**为什么必做**：umbrella 沉淀的"老板项目脚本位置"和"docx 输出位置"**可能落后于老板项目实际结构**（2026-06-14 老板改过目录结构没回填 umbrella）。直接 cp umbrella 写的路径 = **FileNotFoundError**。

**实地 verify 命令**（windows git-bash）：

```bash
# 1. 找老板项目里的真执行件
find "<项目根>/01_教师编体育学科教研" -maxdepth 5 -name "*脚本_合并md*" -type f 2>/dev/null

# 2. 找老板参考版 docx 真位置
find "<项目根>/01_教师编体育学科教研" -name "举一反三讲义*.docx" 2>/dev/null

# 3. 找上册自动版 docx 真位置
find "<项目根>/01_教师编体育学科教研" -name "*举一反三讲义（上）*.docx" 2>/dev/null
```

**真路径速查**（2026-06-14 路径迁移后，**这是当前唯一可信版本**）：

| 资源 | 真实位置 |
|------|---------|
| **老板项目根** | `01_教师编体育学科教研/` |
| **举一反三讲稿 md 库** | `01_教师编体育学科教研/01_笔试/05_学员稿/举一反三讲稿/` |
| **老板参考版 docx（309 KB）** | `01_教师编体育学科教研/01_笔试/05_学员稿/举一反三讲稿/体育教师招聘笔试 举一反三讲义（上册）.docx` |
| **上册自动版 docx（314 KB）** | `01_教师编体育学科教研/01_笔试/04_讲义库/体育教师招聘笔试 举一反三讲义 （上）.docx` |
| **下册 docx（v1.4 新增 104 KB）** | `01_教师编体育学科教研/01_笔试/04_讲义库/体育教师招聘笔试 举一反三讲义 （下）.docx` |
| **老板项目 merge 脚本（真执行件）** | `01_教师编体育学科教研/03_教研/03_脚本存档/12_脚本_合并md生成word版讲义_上_v1.py` |
| **下册版 merge 脚本（v1.4 新建）** | `01_教师编体育学科教研/03_教研/03_脚本存档/13_脚本_合并md生成word版讲义_下_v1.py` |
| **本地 SKILL 模板** | `01_教师编体育学科教研/01_笔试/05_学员稿/举一反三讲稿/SKILL_举一反三讲解稿_v2.3.1.md` |

**对比 umbrella v1.3 写错的（v1.4 已修正）**：

| umbrella v1.3 写的（错）| 真实（v1.4 修正） |
|------------------------|-----------------|
| `02_Hermes_.../05_教研产出/12_脚本_...` | `02_Hermes_.../03_教研/03_脚本存档/12_脚本_...` |
| `02_Hermes_.../03_课程讲义/01_笔试讲义/举一反三讲稿/...` | `02_Hermes_.../01_笔试/05_学员稿/举一反三讲稿/...` |
| `02_Hermes_.../03_课程讲义/01_笔试讲义/...` | `02_Hermes_.../01_笔试/04_讲义库/...` |

### 步骤 1：基于老板项目真执行件 cp 出下册版脚本

**为什么 cp 老板真执行件，不 cp umbrella 公共库**：
- 老板 12 号 = 737 行（**v1.3 升级版**，main 函数签名升级 = 多 `len(MODULES)` 参数）
- umbrella v1.2 = 688 行（**v1.2 老版**，main 函数签名旧）
- 老板 12 号**砍了 4 道校核**（umbrella 保留）—— 下册脚本需要校核，**得加回**

**cp 命令**：

```bash
cd "<项目根>/01_教师编体育学科教研"
cp "03_教研/03_脚本存档/12_脚本_合并md生成word版讲义_上_v1.py" "03_教研/03_脚本存档/13_脚本_合并md生成word版讲义_下_v1.py"
```

**下册脚本命名规则**（沿用老板项目编号习惯）：
- `12_` = 上册
- `13_` = 下册
- 未来 `14_` = 全册合并

### 步骤 2：5 处精准 patch（最小修改单位）

**patch 1 - docstring**（脚本顶部说明）：
```python
# 旧
"""
合并 7 模块 md 讲稿 → 单个 docx
|- 命名: 体育教师招聘笔试 举一反三讲义 （上册）
"""

# 新
"""
合并 2 模块 md 讲稿 → 单个 docx（下册）
|- 命名: 体育教师招聘笔试 举一反三讲义 （下）
"""
```

**patch 2 - OUTPUT 路径**：
```python
# 旧
OUTPUT = Path(r"<用户目录>\Desktop\AI-Workspace\Hermes\01_教师编体育学科教研\01_笔试\04_讲义库\体育教师招聘笔试 举一反三讲义 （上）.docx")

# 新
OUTPUT = Path(r"<用户目录>\Desktop\AI-Workspace\Hermes\01_教师编体育学科教研\01_笔试\04_讲义库\体育教师招聘笔试 举一反三讲义 （下）.docx")
```

**patch 3 - MODULES 列表**（7 模块 → 2 模块）：
```python
# 旧（上册 7 模块）
MODULES = [
    ("1学校体育学", "第一模块 学校体育学"),
    ("2体育心理学", "第二模块 体育心理学"),
    ("3体育游戏", "第三模块 体育游戏"),
    ("4运动解剖学", "第四模块 运动解剖学"),
    ("5运动生理学", "第五模块 运动生理学"),
    ("6体育保健学", "第六模块 体育保健学"),
    ("7运动训练学", "第七模块 运动训练学"),
]

# 新（下册 2 模块）
MODULES = [
    ("8田径", "第八模块 田径"),
    ("9篮球", "第九模块 篮球"),
]
```

**patch 4 - 封面主标题**（docstring 里 L 附近）：
```python
# 旧
r = p.add_run("举一反三讲义（上册）")

# 新
r = p.add_run("举一反三讲义（下）")
```

**patch 5 - 封面副标**：
```python
# 旧
r = p.add_run("上册 · 专业基础理论部分")

# 新
r = p.add_run("下册 · 运动技术理论与实践部分")
```

**5 处 patch 用 `patch` 工具**（不是 sed/awk），精准改 `old_string → new_string`。

**精准修改准则**（守住）：
- 改 5 处就停手，**不要顺手优化其他代码**
- 验证通过再考虑后续
- 任何 patch 前**先 read_file 看精确文本**——避免 patch 误匹配

### 步骤 3：加 4 道校核函数（下册专用期望值）+ 补 import

**为什么加校核**：12 号脚本砍了 4 道校核（umbrella v1.2 保留），下册脚本需要校核兜底。

**加 import sys**（**必做**，不然 `sys.exit(1)` 报 NameError）：
```python
# 文件开头，import re 后
import re
import sys
from pathlib import Path
from docx import Document
```

**加 verify_v1_下 函数**（在 main() 之后，if __name__ 之前）：
```python
def verify_v1_下(docx_path: str) -> bool:
    """v1 下册校核清单（下册专用期望值）：
    1) Heading 1 必须=N（下册 N 个模块章标题）
    2) 元信息行（• 知识点/所属模块/难度/考频/题型）每篇 5 行 × M 篇 = 5M
    3) 暗红色记忆提示 #8B0000 必须>0
    4) 真实 Word 表格必须>0
    5) 元数据残留（v1 优化记录）必须=0
    """
    from docx import Document
    doc = Document(docx_path)
    h1 = sum(1 for p in doc.paragraphs if p.style.name == "Heading 1")
    meta = sum(1 for p in doc.paragraphs
               if p.text.startswith("• ") and any(k in p.text[:10] for k in ["知识点", "所属模块", "难度", "考频", "题型"]))
    mnem = sum(1 for p in doc.paragraphs
               for r in p.runs
               if r.font.color and r.font.color.rgb
               and "8B0000" in str(r.font.color.rgb).upper())
    tables = len(doc.tables)
    meta_hits = sum(1 for p in doc.paragraphs
                    if "本讲稿 v" in p.text and "优化记录" in p.text)
    print("\n[下册 4 道校核]")
    print(f"  H1 章标题: {h1} (期望=N)")
    print(f"  元信息行: {meta} (期望>=5M)")
    print(f"  暗红记忆提示: {mnem} (期望>0)")
    print(f"  真实 Word 表格: {tables} (期望>0)")
    print(f"  元数据残留: {meta_hits} (期望=0)")
    ok = (h1 == N and meta >= 5*M and mnem > 0 and tables > 0 and meta_hits == 0)
    print(f"  总判定: {'✅ 合格' if ok else '❌ 不合格'}")
    return ok
```

**期望值算法**：
- H1 = N（模块数）
- meta ≥ 5M（篇数 × 5 元信息行）
- 暗红 / 表格 = >0（实测填）
- 元数据残留 = 0

**改 `if __name__` 块**（二段跑）：
```python
# 旧
if __name__ == "__main__":
    main()

# 新
if __name__ == "__main__":
    main()
    if verify_v1_下(OUTPUT):
        print("\n✅ 下册 docx 合并+校核全过")
    else:
        print("\n❌ 校核不通过，需检查")
        sys.exit(1)
```

### 步骤 4：clean 函数正则增强（R8 反例防御）

**为什么必做**：AI 实战稿常写 `本讲稿 v1.0 优化记录：...`（无 `>` + 无 `**`），原正则 `^>\s*\*\*本讲稿 v?\s*优化记录\*\*` 严格匹配漏删 → 校核"元数据残留"❌。

**patch**：
```python
# 旧
if re.match(r"^>\s*\*\*本讲稿 v\d+(\.\d+)?\s*优化记录\*\*", stripped):
    in_meta = True
    continue

# 新（兼容 4 种格式）
if re.match(r"^(?:>\s*)?(?:\*\*)?本讲稿\s*v\d+(\.\d+)?\s*优化记录", stripped):
    in_meta = True
    continue
```

**4 种格式覆盖**：
1. `> **本讲稿 v1 优化记录**`（SKILL 标准）
2. `**本讲稿 v1 优化记录**`（无 `>`）
3. `> 本讲稿 v1 优化记录`（无 `**`）
4. `本讲稿 v1.0 优化记录：...`（AI 实战常见——本次命中）

完整 R8 反例见 SKILL.md "6 大反例"小节。

### 步骤 5：跑脚本 + 4 道校核 + 二次验证

**跑命令**（**terminal 不用 execute_code**，踩 v1.1 沙箱超时坑）：
```bash
"<Python 环境>" \
  "<项目根>/01_教师编体育学科教研/03_教研/03_脚本存档/13_脚本_合并md生成word版讲义_下_v1.py" \
  2>&1 | tee "<临时目录>/merge_xia_result.txt"
```

**期望输出**：
```
[OK] 已生成: ...\体育教师招聘笔试 举一反三讲义 （下）.docx
     总篇数: 8
     总字符: 67,620 (66 KB)
     文件大小: 104 KB

[下册 4 道校核]
  H1 章标题: 2 (期望=2)
  元信息行: 40 (期望>=40)
  暗红记忆提示: 17 (期望>0)
  真实 Word 表格: 27 (期望>0)
  元数据残留: 0 (期望=0)
  总判定: ✅ 合格

✅ 下册 docx 合并+校核全过
```

**二次验证**（脚本绿 ≠ 内容对）：
- 若 H1 不达：MODULES 列表错
- 若 meta < 5M：md 元信息被 clean 函数误删
- 若元数据残留 > 0：R8 正则还没修对（**回步骤 4**）
- 若暗红 = 0：md 稿本身没暗红记忆提示（**稿子侧问题**）
- 若表格 = 0：md 稿里没表格或表格解析失败

## 实战案例（2026-06-13 同步田径+篮球下册）

| 阶段 | 输出 |
|------|------|
| 步骤 0 实地 verify | 老板 12 号在 `03_教研/03_脚本存档/`、BASE 在 `01_笔试/05_学员稿/举一反三讲稿/` |
| 步骤 1 cp 13 号 | 26374 bytes（= 12 号同样大小）|
| 步骤 2 5 处 patch | docstring/OUTPUT/MODULES/封面主标/封面副标 |
| 步骤 3 加校核 + import sys | verify_v1_下 期望值 H1=2/meta≥40 + 补 import |
| 步骤 4 第一次跑 | **5 项校核 4/5 通过**——元数据残留=2 ❌（R8 命中）|
| 步骤 4 增强 clean 正则 | 兼容 4 种格式 |
| 步骤 5 第二次跑 | **5 项校核 5/5 全 ✅**——104 KB docx |
| 报告产出物 | "下册 docx 同步完工报告"（5 处 patch + 1 处正则增强 + 1 处 import 补漏）|

**老板沟通模式**：
- 老板说"同步"先问 1 字母（多解 → A/B/C/D）
- 老板拍 A 后**直接执行 5 步 SOP**（v3.1 沟通风格：回 1 字母后继续执行 ABC）
- 完事**主动汇报副产物**（umbrella stale 坑），给老板 1 字母切路

## 副产物清单（每次下册同步可能踩的坑）

1. **umbrella stale 风险**（步骤 0 防御）
2. **R8 反例**（步骤 4 防御）
3. **import sys 漏导**（步骤 3 防御）
4. **patch 字符串匹配失败**（"精准修改准则"防御——patch 前 read_file 看精确文本）
5. **校核期望值算错**（H1 = 模块数、meta ≥ 5M 是硬算法）
6. **execute_code 50KB cap BLOCKED**（步骤 5 防御——terminal 跑）

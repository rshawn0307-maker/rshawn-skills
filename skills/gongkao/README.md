# gongkao

> Skill：公考面试结构化教研与产品题库工具

为公考面试结构化培训提供 **教研与产品题库支持**，覆盖从单题生成到完整讲义和程序可导入 JSON 的 7 个工作流。产品数据模式在原有题目内容上增加版本化评分维度、错因候选和复测约束，并使用独立校验器保证合同一致性。

---

## 功能亮点

- **7 个工作流全覆盖**：题目生成 / 方法论 / 框架模板 / 过渡句 / 素材库 / 讲义组装 / 产品题库 JSON
- **6 条内容铁律**：有观点、有逻辑、有表达、避套路、拒假大空、接地气可操作
- **Python 多模式验证**：`validate_question.py` 支持 5 种验证模式（题目/方法论/框架/素材/讲义）
- **human-writing 深度集成**：逐字稿经过去 AI 味儿处理，避免"标志着/彰显了/体现了"等套路表达
- **模块化架构**：工作流 B-G 的详细模板和产品合同放在 `references/`，SKILL.md 只保留调度与关键约束
- **批量生产策略**：先样例后铺量，每道必跑验证脚本，零命中才过关
- **Obsidian 兼容**：生成标准 md 文件，含 frontmatter 元信息和三级标签体系

---

## 目录结构

```
gongkao/
├── SKILL.md                          # skill 定义文件（核心：调度表 + 流程步骤 + 共享标准）
├── README.md                         # 本文件
├── references/                       # 工作流 B-F 详细输出模板
│   ├── workflow-b-methodology.md     # 方法论生成模板
│   ├── workflow-c-framework.md       # 框架模板生成模板
│   ├── workflow-d-transitions.md     # 过渡句生成模板
│   ├── workflow-e-materials.md       # 素材库生成模板（含4类素材规范）
│   ├── workflow-f-lecture.md         # 讲义组装/更新流程
│   ├── workflow-g-product-data.md    # 产品题库 JSON 输出流程
│   └── product/                      # Schema、量表、错因和复测合同
├── scripts/
│   ├── validate_question.py          # 教研内容验证脚本（5种模式）
│   └── validate_product_question.py  # 产品 JSON 结构与合同校验
└── test-prompts.json                 # 测试用例
```

---

## 安装方式

本 skill 已并入 [rshawn-skills](https://github.com/rshawn0307-maker/rshawn-skills) 合集仓库：

```bash
git clone https://github.com/rshawn0307-maker/rshawn-skills.git
# 将 skills/gongkao/ 目录复制到你的 skills 目录即可
```

旧仓库 `gongkao-interview-question` 保留仅供旧链接访问。

---

## 使用方式

### 工作流触发词

| 工作流 | 触发词 | 输出 |
|--------|--------|------|
| A. 题目生成 | 面试题库/出面试题/批量出题/题库填充 | 单题 md 文件 |
| B. 方法论生成 | 生成方法论/更新方法论/方法论提炼 | 方法论段落 md |
| C. 框架模板生成 | 生成框架/更新框架/框架模板 | 框架模板段落 md |
| D. 过渡句生成 | 生成过渡句/更新过渡句/过渡句库 | 过渡句段落 md |
| E. 素材库生成 | 生成素材/补充素材/素材库 | 素材 md 文件 |
| F. 讲义组装/更新 | 组装讲义/更新讲义/导出讲义 | 完整讲义 md |
| G. 产品题库输出 | 产品题库/JSON题库/程序导入/复测题数据 | 每题一个标准 JSON |

### 工作流 A 示意（题目生成）

```
用户说出触发词
    ↓
步骤1: AI 提出选题清单 → 用户确认
    ↓
步骤2: 按 6 条铁律撰写内容
    ↓
步骤3: 跑 validate_question.py 验证字数
    ↓
步骤4: 扫描 AI 痕迹 + 用语禁忌 → 改写至零命中
    ↓
步骤5: 写入知识库题库文件夹
    ↓
步骤6: 先 6 道样例 → 用户确认 → 批量生产
```

---

## 验证脚本

`scripts/validate_question.py` 提供 5 种验证模式：

```bash
# 题目验证（默认，向后兼容）
python scripts/validate_question.py 综合分析_01_指尖形式主义.md

# 批量验证
python scripts/validate_question.py 综合分析_*.md

# 方法论验证
python scripts/validate_question.py 方法论.md --mode methodology

# 框架模板验证
python scripts/validate_question.py 框架.md --mode framework

# 素材验证
python scripts/validate_question.py 素材.md --mode material

# 讲义整体验证
python scripts/validate_question.py 讲义.md --mode lecture --expected-chapters 9
```

检查项：
| 类别 | 内容 |
|------|------|
| 字数统计 | 逐字稿 800-1000 字（含标点） |
| AI 痕迹（6类） | 标志性短语、三段式列举、破折号（清零）、模糊归因、否定排比、万能收束 |
| 公考高危词 | "体现/彰显/凸显""深入推进/全面落实""多措并举/综合施策"等 |
| 用语禁忌（4类） | 贬义比喻、网络流行词、情绪化表达、政治风险表述 |
| 结构检查 | 机械三段式（第一/第二/第三连续） |
| 方法论模式 | 必需段落 + 要点数量 + 例句覆盖 + 误区表格 |
| 框架模式 | 完整结构 + 代码块 + 占位符 + 破题收尾标记 |
| 素材模式 | frontmatter + 素材类型 + 字数 + 来源标注 |
| 讲义模式 | 章节计数 + 编号连续 + 前言一致 + 嵌入题目验证 |

---

## 适用场景

- 公考面试结构化培训的题库建设
- 公务员/事业单位面试备考资料生成
- 面试培训机构的内容标准化
- 完整讲义产品的生成与维护
- 个人面试练习的题目来源

---

## 版本

- **当前版本**：v2.1.0
- **更新日期**：2026-08-27
- **变更摘要**：新增产品题库 JSON 工作流，内置题目 Schema、临时评分量表、错因标签、复测规则和零依赖校验器；原有六项教研工作流保持不变

---

## 许可

本 skill 为个人作品，供学习交流使用。

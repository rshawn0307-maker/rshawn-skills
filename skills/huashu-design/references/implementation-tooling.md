# 实现红线与 Starter Components

本文件由原 SKILL.md 无损拆出。需要落地 HTML、React、幻灯片、动画或设备框架时完整读取。

## 技术红线（必读 references/react-setup.md）

**React+Babel项目**必须用pinned版本（见`react-setup.md`）。三条不可违反：

1. **never** 写 `const styles = {...}`——多组件时命名冲突会炸。**必须**给唯一名字：`const terminalStyles = {...}`
2. **scope不共享**：多个`<script type="text/babel">`之间组件不通，必须用`Object.assign(window, {...})`导出
3. **never** 用 `scrollIntoView`——会搞坏容器滚动，用其他DOM scroll方法
4. **手写 Stage / Sprite**（不用 `assets/animations.jsx`）必须实现两件事：(a) tick 第一帧同步设 `window.__ready = true` (b) 检测 `window.__recording === true` 时强制 loop=false——否则录视频必出问题

**固定尺寸内容**（幻灯片/视频）必须自己实现JS缩放，用auto-scale + letterboxing。

**幻灯片架构选型（必先决定）**：
- 🔴 **默认且强烈推荐：多文件 + 概览墙**（几乎所有 PPT——培训/路演/科普/课件/汇报）→ 每页独立 HTML + `assets/deck_index.html` 拼接器。**这是 PPT 的默认交付形态**：自带**两种自适应 3D 概览**（网格 iframe / 无限画廊图片，按秒数 60/40 随机）+ 任意页数自适应（少页倾斜居中、多页舒适大卡滚动）+ 统一页码。**直接用，别重写概览**（倾斜/点击命中/裁切三个坑已内建解决，见 slide-decks.md）。
- **单文件**（仅 ≤5 页极简 pitch、且明确不需要概览墙、或需跨页共享 JS 状态）→ `assets/deck_stage.js`。
- 🛑 **不要默认选单文件而绕过概览墙**——北大 13 页 deck 实测踩坑：选了单文件 = 丢了概览墙，违背 PPT 默认交付形态。选单文件前先确认「这真的是 ≤5 页、且不需要概览墙」。

先读 `references/slide-decks.md` 的「🛑 先定架构」一节，错了会反复踩 CSS 特异性/作用域的坑。

## Starter Components（assets/下）

造好的起手组件，直接copy进项目使用：

| 文件 | 何时用 | 提供 |
|------|--------|------|
| `deck_index.html` | **幻灯片的默认基础产物** | **直接复制为 `index.html`、编辑 MANIFEST 即用，不要重写概览逻辑**（三个坑已内建解决）。自带两种自适应概览（网格 iframe 60% / 画廊 40%，画廊需 `thumb` 字段 + 先跑 `scripts/gen_deck_thumbs.mjs`）+ 键盘翻页 + scale + 计数器 + 打印合并。要改先读 `references/slide-decks.md` 三条硬约束 |
| `scripts/gen_deck_thumbs.mjs` | **给无限画廊概览生成缩略图**（网格 iframe 模式不需要）| playwright 截每页 + sharp 降采样 1600px JPEG：`npm i playwright sharp && node gen_deck_thumbs.mjs --slides slides --out thumbs`，再给 MANIFEST 每项加 `thumb`。分辨率别 <1000px 否则 hover 发虚 |
| `deck_stage.js` | 做幻灯片（单文件架构，仅 ≤5 页） | web component：auto-scale + 键盘导航 + slide counter + localStorage + speaker notes ⚠️ **script 必须放在 `</deck-stage>` 之后，section 的 `display: flex` 必须写到 `.active` 上**，详见 `references/slide-decks.md` 的两个硬约束 |
| `scripts/export_deck_pdf.mjs` | **HTML→PDF 导出（多文件架构）** · 每页独立 HTML 文件，playwright 逐个 `page.pdf()` → pdf-lib 合并。文字保留矢量可搜。依赖 `playwright pdf-lib` |
| `scripts/export_deck_stage_pdf.mjs` | **HTML→PDF 导出（单文件 deck-stage 架构专用）** · 2026-04-20 新增。处理 shadow DOM slot 导致的「只出 1 页」、absolute 子元素溢出等坑。详见 `references/slide-decks.md` 末节。依赖 `playwright` |
| `scripts/export_deck_pptx.mjs` | **HTML→可编辑 PPTX 导出** · 调 `html2pptx.js` 导出原生可编辑文本框，文字在 PPT 里双击可直接编辑。**HTML 必须符合 4 条硬约束**（见 `references/editable-pptx.md`），视觉自由度优先的场景请改走 PDF 路径。依赖 `playwright pptxgenjs sharp` |
| `scripts/html2pptx.js` | **HTML→PPTX 元素级翻译器** · 读 computedStyle 把 DOM 逐元素翻译成 PowerPoint 对象（text frame / shape / picture）。`export_deck_pptx.mjs` 内部调用。要求 HTML 严格满足 4 条硬约束 |
| `design_canvas.jsx` | 并排展示≥2个静态variations | 带label的网格布局 |
| `animations.jsx` | 任何动画HTML | Stage + Sprite + useTime + Easing + interpolate |
| `ios_frame.jsx` | iOS App mockup | iPhone bezel + 状态栏 + 圆角 |
| `android_frame.jsx` | Android App mockup | 设备bezel |
| `macos_window.jsx` | 桌面App mockup | 窗口chrome + 红绿灯 |
| `browser_window.jsx` | 网页在浏览器里的样子 | URL bar + tab bar |
| `cursor.jsx` | 产品UI演示里的光标操作叙事 | macOS光标4形状 + CursorSprite弧线轨迹（Catmull-Rom+收敛手抖）+ ClickRipple双圈解耦 + hover联动 + GSAP/Stage双驱动，帧确定性 |

用法：读取对应 assets 文件内容 → inline 进你的 HTML `<script>` 标签 → slot 进你的设计。

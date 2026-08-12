# App / iOS 原型速查规则

本文件由原 SKILL.md 无损拆出。App、iOS、Android 或移动端原型任务完整读取。

## App / iOS 原型专属守则（速查版）

做移动 app 原型时（触发：「app 原型」「iOS mockup」「移动应用」「做个 app」），以下硬规则**覆盖**通用 placeholder 原则——app 原型是 demo 现场，静态摆拍没有说服力。完整操作细节（架构选型表 / 取图渠道与代码 / AppPhone JSX 骨架 / ios_frame 三步用法 / 品位锚点全表）见 `references/app-prototype.md`：

1. **架构默认单文件 inline React**：`file://` 双击就能开，本地图片 base64 内嵌；仅 >1000 行难维护或多 agent 并行写不同屏才拆多文件（拆了必须附 `python3 -m http.server` 启动说明）
2. **先找真图再设计**：渠道同 Phase 3.5 取图表；取图前过**真图诚实性测试**——「去掉这张图信息是否有损？」无损 = 装饰 = slop，不加
3. **交付形态默认「平铺 4-6 主屏 + 每台可交互」**，不要问用户二选一；每台是独立迷你状态机（tab 可切 / 按钮可点 / 能弹 modal），仅用户明确说「只要静态」或「单流程 demo」才偏离
4. 🔴 **iOS 设备框必须用 `assets/ios_frame.jsx`**：禁止手写 Dynamic Island / status bar / home indicator / bezel——自己写 99% 撞位置 bug（岛是固定 124×36，两侧 status bar 空间极窄）
5. **信息密度分型**：默认克制型（少一层容器 / 少一个 border / 少一个装饰 icon）；产品卖点是 AI / 数据 / 上下文感知时走**高密度型**——每屏 ≥3 处**有内容的**差异化信息，装饰 icon 照样忌讳
6. **交付前 Playwright 跑 3 项点击测试**（进详情 / 关键标注点 / tab 切换），`pageerror` 为 0 再交付
7. **品位锚点**：衬线 display（Newsreader/Source Serif/EB Garamond）+ `-apple-system` body；一个有温度的底色 + 单 accent 贯穿；留一处「值得截图」的 120% 细节签名



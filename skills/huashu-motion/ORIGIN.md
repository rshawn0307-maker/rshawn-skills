# 出处 / Origin

本 skill 收录自 [alchaincyf/huashu-motion](https://github.com/alchaincyf/huashu-motion)（作者：花叔 alchaincyf），MIT 许可，保留原作者内容，感谢原作者。

- 2026-10-18 首次收录（0.1.0）；2026-10-24 同步至 0.3.1；2026-11-22 同步至 0.6.0
- - 2026-11-24 同步至 0.6.1（`om check --source` 正则修正：`om-` → `^om-`，避免 zoom-in/bottom-bar/custom-chart 等真实素材被误判为未使用素材）
上游默认分支：`main`

## 本副本的打包方式

上游是多端分发 monorepo，skill 本体在 `skills/huashu-motion/`，但 `bin/om` 需要调用仓库根的 CLI（`cli/`、`runtime/`、`templates/`、`fonts/`、`studio/`、`examples/`、`music/`），不能只拷 skill 子目录。本副本因此做了扁平化打包：

- `SKILL.md`、`references/`、`bin/` 取自上游 `skills/huashu-motion/`
- `cli/ runtime/ templates/ fonts/ studio/ examples/ music/ package.json LICENSE THIRD_PARTY.md README*` 取自上游仓库根
- 上游的 `docs/`、`site/`、`test/`、`scripts/` 未收录（运行时不需要）
- `bin/om` 的 CLI 查找路径由 `../../../cli/om.js` 改为 `../cli/om.js`，以适配扁平布局

## 运行时依赖

- Node ≥ 22
- Chrome / Chromium / Edge（截帧、检查、导出复用本机浏览器）
- FFmpeg + ffprobe（视频导出、配乐合成、qa）
- 可选：真乐器音色 `om samples build`（约 55MB）；口播 Kokoro（uv + Python 3.12）或本机录制；曲库 `om music build`（下载到 `~/.cache/huashu-motion/music`，可用 `OM_MUSIC` 覆盖路径）

安装后跑 `om doctor` 自检。

## 更新

在 rshawn-skills 仓库根目录运行：

```bash
bash scripts/sync-huashu-motion.sh
```

脚本会重新拉取上游并重建扁平布局、补回来源声明与本文件。

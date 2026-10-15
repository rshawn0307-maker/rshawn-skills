# ORIGIN

- **来源**：https://github.com/wheresryan22/anatomy （作者：wheresryan22）
- **收录日期**：2026-10-15
- **收录版本**：main 分支（2026-10-14 快照，最新 commit 2026-10-14T22:24Z）
- **许可证**：MIT（上游仓库根 LICENSE）
- **收录方式**：SKILL.md 位于上游仓库根目录，本副本取自仓库整体（SKILL.md + kit/ + references/ + scripts/ + tests/ + examples/ + evals/ + agents/），仅删除 .github/ 与仓库协作元文件（CODE_OF_CONDUCT/CONTRIBUTING/SECURITY/.gitignore/.gitattributes），并在 SKILL.md 首个 H1 后加来源声明；skill 本体内容未改动。
- **运行依赖**：Node.js 20.10+；校验步骤需 Chrome/Chromium（scripts/capture.mjs、drive.mjs、lines.mjs 走 headless Chrome）。WebGL shader 与 3D 模式为可选能力。
- **上游更新**：`git clone --depth 1 https://github.com/wheresryan22/anatomy` 后用仓库整体覆盖本目录（保留本 ORIGIN.md 与 SKILL.md 头部来源声明，重新删除 .github/ 等），再同步其余各端。

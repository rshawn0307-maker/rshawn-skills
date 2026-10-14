# ORIGIN

- **来源**：https://github.com/pbakaus/impeccable （作者：Paul Bakaus / pbakaus）
- **收录日期**：2026-10-14
- **收录版本**：v4.5.2（skill `version: 4.5.2`，scripts/VERSION 同步）
- **许可证**：Apache 2.0（上游仓库根 LICENSE）
- **收录方式**：上游仓库为多端分发 monorepo，本副本取自 `plugin/skills/impeccable/`（SKILL.md + reference/ + scripts/），未改动 skill 内容。
- **上游 NOTICE**：`reference/ios.md` 与 `reference/android.md` 蒸馏自 ehmo/platform-design-skills（MIT），详见上游仓库根 NOTICE.md。
- **引擎说明**：`scripts/impeccable` launcher 首次运行会下载自包含引擎二进制到 `~/.impeccable/bin/<version>/`，无需 Node。
- **上游更新**：`git clone --depth 1 https://github.com/pbakaus/impeccable` 后用 `plugin/skills/impeccable/` 覆盖本目录（保留本 ORIGIN.md 与 SKILL.md 头部来源声明），再同步其余各端。

# 出处 / Origin

本 skill 收录自 [alchaincyf/huashu-mac-use](https://github.com/alchaincyf/huashu-mac-use)（作者：花叔 alchaincyf），保留原作者内容，感谢原作者。

- 2026-09-07 首次收录（当时未建 ORIGIN.md，2026-10-19 补齐并升上游 v1.0.0）；2026-10-19 同步至五端
- 2026-10-24 复核上游：自 v1.0.0 后无内容变更
- 本副本 `scripts/mac` 是本机编译的 Swift 内核（约 296K），上游不含该产物；更新时保留，换机后跑 `scripts/build.sh` 重建
- 仓库副本不含该编译产物

上游更新后，在 rshawn-skills 仓库根目录手动同步（本 skill 未纳入 sync-huashu.sh，可按需加入其 SOURCES）：

```bash
git clone --depth 1 https://github.com/alchaincyf/huashu-mac-use.git /tmp/hm-up && \
rsync -a --delete --exclude='.git' --exclude='ORIGIN.md' --exclude='scripts/mac' /tmp/hm-up/ ~/.zcode/skills/huashu-mac-use/
```

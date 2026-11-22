# 出处 / Origin

本 skill 收录自 [alchaincyf/huashu-skills 内置](https://github.com/alchaincyf/huashu-skills)（作者：花叔 alchaincyf），保留原作者内容，感谢原作者。

- 上游目录快照：skills.json updated 2026-10-26；2026-10-30 首次收录
- 本地补丁（2026-11-22）：`scripts/check_updates.py` 保留「无 SKILL.md 版本标记 → unknown」分支——上游把它并进了 outdated 文案，但纯资产/无 version 字段的仓库会被误报为过期。`scripts/sync-huashu.sh` 已内置该补丁的重打步骤，每次同步后自动恢复

上游更新后，在 rshawn-skills 仓库根目录运行一条命令即可同步：

```bash
bash scripts/sync-huashu.sh
```

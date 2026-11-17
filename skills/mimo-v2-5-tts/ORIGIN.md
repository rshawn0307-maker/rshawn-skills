# 出处 / Origin

本 skill 收录自 [XiaomiMiMo/MiMo-Skills](https://github.com/XiaomiMiMo/MiMo-Skills)（作者：小米 XiaomiMiMo，MIT 许可），保留原作者内容，感谢原作者。

> **本地补丁**（2026-11-17）：三个 TTS 脚本支持 `MIMO_BASE_URL` 环境变量覆盖端点（默认仍为官方 `https://api.xiaomimimo.com/v1`），用于 Token Plan 套餐专属 Base URL。上游无此变量，同步时会被覆盖，需按本条重打。

- 上游版本：0.1.2（SKILL.md metadata），2026-11-17 首次收录（main 最新）
- 运行依赖：Python3 + `openai` 库（本机已装 3.52.0）+ `MIMO_API_KEY` 环境变量（MiMo 开放平台 platform.xiaomimimo.com 获取，由用户自行配置）；ffmpeg 仅拼接场景用；飞书发送另需 FEISHU_APP_ID/SECRET
- 上游更新后，在 rshawn-skills 仓库根目录运行一条命令即可同步：

```bash
bash scripts/sync-mimo.sh
```

#!/usr/bin/env bash
#
# 一键同步小米 MiMo 系 skill（XiaomiMiMo/MiMo-Skills）到本仓库。
# 上游是多 skill 仓库，当前收录 mimo-v2-5-tts；上游新增 skill 时在 SKILLS 数组里追加。
#
# 用法：
#   bash scripts/sync-mimo.sh            仅更新工作区文件并打印变更摘要
#   bash scripts/sync-mimo.sh --push     更新并自动 commit + push
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM="https://github.com/XiaomiMiMo/MiMo-Skills.git"
SKILLS=(mimo-v2-5-tts)

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "==> 拉取 $UPSTREAM" >&2
git -c http.version=HTTP/1.1 -c http.connectTimeout=30 -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=30 \
  clone --depth 1 "$UPSTREAM" "$TMP_DIR/up" >/dev/null 2>&1 || { echo "拉取失败：$UPSTREAM"; exit 1; }

for NAME in "${SKILLS[@]}"; do
  SRC="$TMP_DIR/up/skills/$NAME"
  DST="$REPO_ROOT/skills/$NAME"
  if [ ! -d "$SRC" ]; then
    echo "上游没有 skills/$NAME/（可能已改名或删除），跳过"
    continue
  fi
  mkdir -p "$DST"
  rsync -a --delete --exclude='.git' "$SRC/" "$DST/"
  # 本地补丁：Token Plan 套餐端点覆盖（上游无此变量，每次同步后自动重打）
  python3 - "$DST" <<'PY'
import pathlib, sys
d = pathlib.Path(sys.argv[1])
old = 'return OpenAI(api_key=api_key, base_url="https://api.xiaomimimo.com/v1")'
new = ('base_url = os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")   # 本地补丁：支持 Token Plan 套餐专属端点\n'
       '    return OpenAI(api_key=api_key, base_url=base_url)')
for name in ["mimo_tts.py", "mimo_tts_voicedesign.py", "mimo_tts_voiceclone.py"]:
    p = d / "scripts" / name
    if not p.exists():
        continue
    t = p.read_text(encoding="utf-8")
    if "MIMO_BASE_URL" in t:
        continue
    if old not in t or "import os" not in t:
        print(f"  ⚠️ {name}: 结构变化，补丁未打，请人工核对")
        continue
    t = t.replace(old, new, 1)
    p.write_text(t, encoding="utf-8")
    print(f"  补丁已重打: {name}")
PY
  cat > "$DST/ORIGIN.md" <<'EOF'
# 出处 / Origin

本 skill 收录自 [XiaomiMiMo/MiMo-Skills](https://github.com/XiaomiMiMo/MiMo-Skills)（作者：小米 XiaomiMiMo，MIT 许可），保留原作者内容，感谢原作者。

- 上游版本：0.1.2（SKILL.md metadata），2026-11-17 首次收录（main 最新）
- 运行依赖：Python3 + `openai` 库（本机已装 3.52.0）+ `MIMO_API_KEY` 环境变量（MiMo 开放平台 platform.xiaomimimo.com 获取，由用户自行配置）；ffmpeg 仅拼接场景用；飞书发送另需 FEISHU_APP_ID/SECRET
- 上游更新后，在 rshawn-skills 仓库根目录运行一条命令即可同步：

```bash
bash scripts/sync-mimo.sh
```
EOF
  # SKILL.md 来源声明：插在首个 H1 之后，已存在则跳过
  python3 - "$DST/SKILL.md" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
if "来源声明" in t:
    sys.exit(0)
note = "> **来源声明**：本 skill 收录自 [XiaomiMiMo/MiMo-Skills](https://github.com/XiaomiMiMo/MiMo-Skills)（作者：小米 XiaomiMiMo，MIT 许可），保留原作者内容，感谢原作者。同步与出处详见本目录 ORIGIN.md。"
lines = t.splitlines()
for i, l in enumerate(lines):
    if l.startswith("# "):
        lines[i+1:i+1] = ["", note]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        break
PY
  echo "OK: 已同步 $NAME"
done

echo
echo "==> 变更摘要："
PATHS=""
for NAME in "${SKILLS[@]}"; do PATHS="$PATHS skills/$NAME"; done
git -C "$REPO_ROOT" status --short -- $PATHS

if [ "${1:-}" = "--push" ]; then
  git -C "$REPO_ROOT" add $PATHS
  if git -C "$REPO_ROOT" diff --cached --quiet; then
    echo "(nothing to commit)"
  else
    git -C "$REPO_ROOT" commit -m "sync: MiMo-Skills 上游更新（XiaomiMiMo）"
    git -C "$REPO_ROOT" push
  fi
fi
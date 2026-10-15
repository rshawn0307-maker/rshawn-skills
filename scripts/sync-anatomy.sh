#!/usr/bin/env bash
#
# 一键同步源自 wheresryan22 的 anatomy skill 到本仓库。
#
# 用法：
#   bash scripts/sync-anatomy.sh            仅更新工作区文件并打印变更摘要
#   bash scripts/sync-anatomy.sh --push     更新并自动 commit + push
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NAME="anatomy"
UPSTREAM="https://github.com/wheresryan22/anatomy.git"

ORIGIN_MD="# ORIGIN

- **来源**：https://github.com/wheresryan22/anatomy （作者：wheresryan22）
- **许可证**：MIT（上游仓库根 LICENSE）
- **收录方式**：SKILL.md 位于上游仓库根目录，本副本取自仓库整体（SKILL.md + kit/ + references/ + scripts/ + tests/ + examples/ + evals/ + agents/），仅删除 .github/ 与仓库协作元文件（CODE_OF_CONDUCT/CONTRIBUTING/SECURITY/.gitignore/.gitattributes），并在 SKILL.md 首个 H1 后加来源声明；skill 本体内容未改动。
- **运行依赖**：Node.js 20.10+；校验步骤需 Chrome/Chromium（scripts/capture.mjs、drive.mjs、lines.mjs 走 headless Chrome）。WebGL shader 与 3D 模式为可选能力。
- **上游更新**：在 rshawn-skills 仓库根目录运行一条命令即可同步：

\`\`\`bash
bash scripts/sync-anatomy.sh
\`\`\`
"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

clone_repo() {
  local repo="$1"
  local key dir
  key="$(printf '%s' "$repo" | shasum | cut -c1-8)"
  dir="$TMP_DIR/repo_$key"
  if [ ! -d "$dir/.git" ]; then
    echo "==> 拉取 $repo" >&2
    if ! git -c http.version=HTTP/1.1 -c http.connectTimeout=30 -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=30 clone --depth 1 "$repo" "$dir" >/dev/null 2>&1; then
      echo "❌ 拉取失败：$repo（github.com 直连常失败，请挂代理后重试）"
      exit 1
    fi
  fi
  printf '%s' "$dir"
}

# SKILL.md 有 H1（`# Anatomy`），来源声明固定插在首个 H1 之后，与已收录
# 副本的现有位置一致。
ensure_attribution() {
  local f="$1"
  local note="$2"
  [ -f "$f" ] || return 0
  grep -q "来源声明" "$f" && return 0
  local line
  line="$(grep -n '^# ' "$f" | head -1 | cut -d: -f1)"
  [ -n "$line" ] || return 0
  awk -v n="$line" -v note="$note" 'NR==n { print; print ""; print note; next } { print }' "$f" > "$f.tmp"
  mv "$f.tmp" "$f"
}

sync_skill() {
  local repo_dir src dst
  repo_dir="$(clone_repo "$UPSTREAM")"
  src="$repo_dir"
  dst="$REPO_ROOT/skills/$NAME"
  attribution="> **来源声明**：本 skill 收录自 [wheresryan22/anatomy](https://github.com/wheresryan22/anatomy)（作者：wheresryan22），保留原作者内容，感谢原作者。MIT License。上游更新可用仓库根目录 \`scripts/sync-anatomy.sh\` 一键同步。"
  mkdir -p "$dst"
  # 上游 skill 本体即仓库根目录；剔除 .git 与仓库协作元文件，与已收录副本一致
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude='.git' --exclude='.github' --exclude='.gitignore' --exclude='.gitattributes' \
      --exclude='CODE_OF_CONDUCT.md' --exclude='CONTRIBUTING.md' --exclude='SECURITY.md' \
      "$src/" "$dst/"
  else
    cp -R "$src/." "$dst/"
    rm -rf "$dst/.git" "$dst/.github" "$dst/.gitignore" "$dst/.gitattributes" \
      "$dst/CODE_OF_CONDUCT.md" "$dst/CONTRIBUTING.md" "$dst/SECURITY.md"
  fi
  printf '%s' "$ORIGIN_MD" > "$dst/ORIGIN.md"
  ensure_attribution "$dst/SKILL.md" "$attribution"
  echo "✅ 已同步 $NAME"
}

sync_skill

echo
echo "==> 变更摘要："
git -C "$REPO_ROOT" status --short -- "skills/$NAME"

if [ "${1:-}" = "--push" ]; then
  git -C "$REPO_ROOT" add "skills/$NAME"
  if git -C "$REPO_ROOT" diff --cached --quiet; then
    echo "（无变更可提交）"
  else
    git -C "$REPO_ROOT" commit -m "sync: 同步 anatomy（wheresryan22）上游更新"
    git -C "$REPO_ROOT" push
  fi
fi

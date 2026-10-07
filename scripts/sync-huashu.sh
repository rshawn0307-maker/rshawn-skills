#!/usr/bin/env bash
#
# 一键同步源自花叔（alchaincyf）的 skill 到本仓库。
#
# 用法：
#   bash scripts/sync-huashu.sh            仅更新工作区文件并打印变更摘要
#   bash scripts/sync-huashu.sh --push     更新并自动 commit + push
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 每条记录：本地目录名|上游仓库|上游内子目录（. 表示仓库根目录）|出处链接|出处显示名
SOURCES=(
  "darwin-skill|https://github.com/alchaincyf/darwin-skill.git|.|https://github.com/alchaincyf/darwin-skill|alchaincyf/darwin-skill"
  "huashu-design|https://github.com/alchaincyf/huashu-design.git|.|https://github.com/alchaincyf/huashu-design|alchaincyf/huashu-design"
  "huashu-report|https://github.com/alchaincyf/huashu-report.git|.|https://github.com/alchaincyf/huashu-report|alchaincyf/huashu-report"
  "huashu-art-motion|https://github.com/alchaincyf/huashu-art-motion.git|.|https://github.com/alchaincyf/huashu-art-motion|alchaincyf/huashu-art-motion"
)

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
      echo "❌ 拉取失败：$repo"
      exit 1
    fi
  fi
  printf '%s' "$dir"
}

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
  local name="$1" repo="$2" sub="$3" origin_url="$4" origin_label="$5"
  local src dst attribution origin_md
  src="$(clone_repo "$repo")/$sub"
  dst="$REPO_ROOT/skills/$name"
  if [ ! -d "$src" ]; then
    echo "⚠️  上游没有 $sub/（可能已改名或删除），跳过 $name"
    return 0
  fi
  attribution="> **来源声明**：本 skill 收录自 [$origin_label]($origin_url)（作者：花叔 alchaincyf），保留原作者内容，感谢原作者。上游更新可用仓库根目录 \`scripts/sync-huashu.sh\` 一键同步。"
  origin_md="# 出处 / Origin

本 skill 收录自 [$origin_label]($origin_url)（作者：花叔 alchaincyf），保留原作者内容，感谢原作者。

上游更新后，在 rshawn-skills 仓库根目录运行一条命令即可同步：

\`\`\`bash
bash scripts/sync-huashu.sh
\`\`\`
"
  mkdir -p "$dst"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude='.git' "$src/" "$dst/"
  else
    cp -R "$src/." "$dst/"
    rm -rf "$dst/.git"
  fi
  printf '%s' "$origin_md" > "$dst/ORIGIN.md"
  ensure_attribution "$dst/SKILL.md" "$attribution"
  echo "✅ 已同步 $name"
}

for entry in "${SOURCES[@]}"; do
  IFS='|' read -r name repo sub origin_url origin_label <<< "$entry"
  sync_skill "$name" "$repo" "$sub" "$origin_url" "$origin_label"
done

echo
echo "==> 变更摘要："
git -C "$REPO_ROOT" status --short -- skills/darwin-skill skills/huashu-design skills/huashu-report skills/huashu-art-motion

if [ "${1:-}" = "--push" ]; then
  git -C "$REPO_ROOT" add skills/darwin-skill skills/huashu-design skills/huashu-report skills/huashu-art-motion
  if git -C "$REPO_ROOT" diff --cached --quiet; then
    echo "（无变更可提交）"
  else
    git -C "$REPO_ROOT" commit -m "sync: 同步花叔（alchaincyf）上游更新"
    git -C "$REPO_ROOT" push
  fi
fi

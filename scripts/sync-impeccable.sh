#!/usr/bin/env bash
#
# 一键同步源自 pbakaus 的 impeccable skill 到本仓库。
#
# 用法：
#   bash scripts/sync-impeccable.sh            仅更新工作区文件并打印变更摘要
#   bash scripts/sync-impeccable.sh --push     更新并自动 commit + push
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NAME="impeccable"
UPSTREAM="https://github.com/pbakaus/impeccable.git"
SUB_DIR="plugin/skills/impeccable"

ORIGIN_MD="# 出处 / Origin

本 skill 收录自 [pbakaus/impeccable](https://github.com/pbakaus/impeccable)（作者：Paul Bakaus），保留原作者内容，感谢原作者。上游采用 Apache 2.0 许可（见目录内 LICENSE），使用前请留意。

上游仓库为多端分发 monorepo，本副本取自 \`plugin/skills/impeccable/\`。skill 自带 launcher（\`scripts/impeccable\`），首次运行会下载自包含引擎二进制到 \`~/.impeccable/bin/<version>/\`，无需 Node；沙箱无外网时可设 \`IMPECCABLE_BIN\` 指向预装二进制。

上游更新后，在 rshawn-skills 仓库根目录运行一条命令即可同步：

\`\`\`bash
bash scripts/sync-impeccable.sh
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
      echo "❌ 拉取失败：$repo"
      exit 1
    fi
  fi
  printf '%s' "$dir"
}

# SKILL.md 无 H1（frontmatter 之后直接是正文），来源声明插在 frontmatter
# 结束的第二个 `---` 之后，与已收录副本的现有位置一致。
ensure_attribution() {
  local f="$1"
  local note="$2"
  [ -f "$f" ] || return 0
  grep -q "来源声明" "$f" && return 0
  local line
  line="$(awk '$0=="---" { c++; if (c==2) { print NR; exit } }' "$f")"
  [ -n "$line" ] || return 0
  awk -v n="$line" -v note="$note" 'NR==n { print; print ""; print note; next } { print }' "$f" > "$f.tmp"
  mv "$f.tmp" "$f"
}

sync_skill() {
  local repo_dir src dst
  repo_dir="$(clone_repo "$UPSTREAM")"
  src="$repo_dir/$SUB_DIR"
  dst="$REPO_ROOT/skills/$NAME"
  if [ ! -d "$src" ]; then
    echo "⚠️  上游没有 $SUB_DIR/（可能已改名或删除），跳过 $NAME"
    return 0
  fi
  attribution="> **来源声明**：本 skill 收录自 [pbakaus/impeccable](https://github.com/pbakaus/impeccable)（作者：Paul Bakaus），保留原作者内容，感谢原作者。上游采用 Apache 2.0 许可。上游更新可用仓库根目录 \`scripts/sync-impeccable.sh\` 一键同步。"
  mkdir -p "$dst"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude='.git' "$src/" "$dst/"
  else
    cp -R "$src/." "$dst/"
    rm -rf "$dst/.git"
  fi
  if [ -f "$repo_dir/LICENSE" ]; then
    cp "$repo_dir/LICENSE" "$dst/LICENSE"
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
    git -C "$REPO_ROOT" commit -m "sync: 同步 impeccable（pbakaus）上游更新"
    git -C "$REPO_ROOT" push
  fi
fi

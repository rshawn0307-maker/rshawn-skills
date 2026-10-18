#!/usr/bin/env bash
#
# 一键同步源自花叔（alchaincyf）的 huashu-motion skill 到本仓库。
#
# 上游是多端分发 monorepo：skill 本体在 skills/huashu-motion/，
# 但 bin/om 需要调用仓库根的 CLI 资源，不能只拷 skill 子目录。
# 本脚本把 skill 扁平化打包：SKILL.md/references/bin 提到根目录，
# cli/runtime/templates/fonts/studio/examples 同级部署，并适配 bin/om 的查找路径。
#
# 用法：
#   bash scripts/sync-huashu-motion.sh            仅更新工作区文件并打印变更摘要
#   bash scripts/sync-huashu-motion.sh --push     更新并自动 commit + push
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NAME="huashu-motion"
UPSTREAM="https://github.com/alchaincyf/huashu-motion.git"
SUB_DIR="skills/huashu-motion"

# 扁平化时要带到 skill 根目录的运行时目录/文件（上游仓库根）
RUNTIME_DIRS=(cli runtime templates fonts studio examples)
RUNTIME_FILES=(package.json LICENSE THIRD_PARTY.md README.md README.en.md)

ORIGIN_MD="# 出处 / Origin

本 skill 收录自 [alchaincyf/huashu-motion](https://github.com/alchaincyf/huashu-motion)（作者：花叔 alchaincyf），MIT 许可，保留原作者内容，感谢原作者。

- 上游版本：0.1.0（package.json），收录日期 2026-10-18
- 上游默认分支：\`main\`

## 本副本的打包方式

上游是多端分发 monorepo，skill 本体在 \`skills/huashu-motion/\`，但 \`bin/om\` 需要调用仓库根的 CLI（\`cli/\`、\`runtime/\`、\`templates/\`、\`fonts/\`、\`studio/\`、\`examples/\`），不能只拷 skill 子目录。本副本因此做了扁平化打包：

- \`SKILL.md\`、\`references/\`、\`bin/\` 取自上游 \`skills/huashu-motion/\`
- \`cli/ runtime/ templates/ fonts/ studio/ examples/ package.json LICENSE THIRD_PARTY.md README*\` 取自上游仓库根
- 上游的 \`docs/\`、\`site/\`、\`test/\` 未收录（运行时不需要，约 28MB）
- \`bin/om\` 的 CLI 查找路径由 \`../../../cli/om.js\` 改为 \`../cli/om.js\`，以适配扁平布局

## 运行时依赖

- Node ≥ 22
- Chrome / Chromium / Edge（截帧、检查、导出复用本机浏览器）
- FFmpeg + ffprobe（视频导出、配乐合成、qa）
- 可选：真乐器音色 \`om samples build\`（约 55MB）；口播 Kokoro（uv + Python 3.12）或本机录制

安装后跑 \`om doctor\` 自检。

## 更新

在 rshawn-skills 仓库根目录运行：

\`\`\`bash
bash scripts/sync-huashu-motion.sh
\`\`\`

脚本会重新拉取上游并重建扁平布局、补回来源声明与本文件。
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
  local repo_dir src dst stage d f
  repo_dir="$(clone_repo "$UPSTREAM")"
  src="$repo_dir/$SUB_DIR"
  dst="$REPO_ROOT/skills/$NAME"
  stage="$TMP_DIR/stage"
  if [ ! -d "$src" ]; then
    echo "⚠️  上游没有 $SUB_DIR/（可能已改名或删除），跳过 $NAME"
    return 0
  fi

  mkdir -p "$stage"
  rsync -a --exclude='.git' "$src/" "$stage/"
  for d in "${RUNTIME_DIRS[@]}"; do
    [ -d "$repo_dir/$d" ] || { echo "⚠️  上游缺少 $d/，中止"; exit 1; }
    rsync -a --exclude='.git' "$repo_dir/$d" "$stage/"
  done
  for f in "${RUNTIME_FILES[@]}"; do
    [ -f "$repo_dir/$f" ] && cp "$repo_dir/$f" "$stage/"
  done

  # 适配扁平布局：bin/om 从仓库根找到 skill 根（直接生成 launcher，避免依赖 perl -i 的写入行为）
  cat > "$stage/bin/om" <<'LAUNCHER'
#!/bin/sh
# Runs the huashu-motion CLI shipped inside this skill; falls back to the npm package.
DIR="$(cd "$(dirname "$0")" && pwd -P)"
if [ -f "$DIR/../cli/om.js" ]; then exec node "$DIR/../cli/om.js" "$@"; fi
exec npx --yes huashu-motion "$@"
LAUNCHER
  chmod +x "$stage/bin/om"

  printf '%s' "$ORIGIN_MD" > "$stage/ORIGIN.md"
  attribution="> **来源声明**：本 skill 收录自 [alchaincyf/huashu-motion](https://github.com/alchaincyf/huashu-motion)（作者：花叔 alchaincyf），保留原作者内容，感谢原作者。上游更新可用仓库根目录 \`scripts/sync-huashu-motion.sh\` 一键同步。本副本为扁平化打包：\`SKILL.md\` 与 \`references/\` 提到根目录，CLI 资源（\`cli/ runtime/ templates/ fonts/ studio/ examples/\`）同级部署，\`bin/om\` 的查找路径已相应适配；运行时依赖 Node ≥22、Chrome、FFmpeg。"
  ensure_attribution "$stage/SKILL.md" "$attribution"

  mkdir -p "$dst"
  rsync -a --delete "$stage/" "$dst/"
  chmod +x "$dst/bin/om" 2>/dev/null || true
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
    git -C "$REPO_ROOT" commit -m "sync: 同步 huashu-motion（alchaincyf）上游更新"
    git -C "$REPO_ROOT" push
  fi
fi

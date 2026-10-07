#!/usr/bin/env bash
#
# 一键同步源自 Khazix 的 skill 到本仓库。
#
# 用法：
#   bash scripts/sync-khazix.sh            仅更新工作区文件并打印变更摘要
#   bash scripts/sync-khazix.sh --push     更新并自动 commit + push
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 每条记录：本地目录名|上游仓库|上游内子目录|出处链接|出处显示名
SOURCES=(
  "neat-freak|https://github.com/KKKKhazix/khazix-skills.git|neat-freak|https://github.com/KKKKhazix/khazix-skills|khazix-skills"
  "storage-analyzer|https://github.com/KKKKhazix/khazix-skills.git|storage-analyzer|https://github.com/KKKKhazix/khazix-skills|khazix-skills"
  "leader|https://github.com/KKKKhazix/khazix-skills.git|leader|https://github.com/KKKKhazix/khazix-skills|khazix-skills"
  "khazix-writer|https://github.com/KKKKhazix/khazix-skills.git|khazix-writer|https://github.com/KKKKhazix/khazix-skills|khazix-skills"
  "human-writing|https://github.com/KKKKhazix/human-writing.git|human-writing|https://github.com/KKKKhazix/human-writing|KKKKhazix/human-writing"
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
  attribution="> **来源声明**：本 skill 收录自 [$origin_label]($origin_url)（作者：KKKKhazix），保留原作者内容，感谢原作者。上游更新可用仓库根目录 \`scripts/sync-khazix.sh\` 一键同步。"
  origin_md="# 出处 / Origin

本 skill 收录自 [$origin_label]($origin_url)（作者：KKKKhazix），保留原作者内容，感谢原作者。

上游更新后，在 rshawn-skills 仓库根目录运行一条命令即可同步：

\`\`\`bash
bash scripts/sync-khazix.sh
\`\`\`
"
  mkdir -p "$dst"
  cp -R "$src/." "$dst/"
  printf '%s' "$origin_md" > "$dst/ORIGIN.md"
  ensure_attribution "$dst/SKILL.md" "$attribution"
  echo "✅ 已同步 $name"
}

for entry in "${SOURCES[@]}"; do
  IFS='|' read -r name repo sub origin_url origin_label <<< "$entry"
  sync_skill "$name" "$repo" "$sub" "$origin_url" "$origin_label"
done

echo
echo "==> 校验依赖 human-writing 的 skill："
HUMAN_WRITING_VERSION="$(cat "$REPO_ROOT/skills/human-writing/VERSION" 2>/dev/null || echo '?')"
DEPENDENTS=(gongkao structured-post zhankai)
for s in "${DEPENDENTS[@]}"; do
  f="$REPO_ROOT/skills/$s/SKILL.md"
  missing=""
  grep -q "human-writing" "$f" || missing="$missing human-writing引用"
  grep -q "破折号" "$f" || missing="$missing 破折号规则"
  grep -q "冒号" "$f" || missing="$missing 冒号规则"
  grep -q "翻案" "$f" || missing="$missing 翻案腔规则"
  if [ -z "$missing" ]; then
    echo "✅ $s 已对齐 human-writing $HUMAN_WRITING_VERSION（引用与硬禁令要点齐全）"
  else
    echo "⚠️  $s 缺少：$missing（human-writing 当前版本 $HUMAN_WRITING_VERSION，请人工检查）"
  fi
done

echo
echo "==> 变更摘要："
git -C "$REPO_ROOT" status --short -- skills/neat-freak skills/storage-analyzer skills/leader skills/khazix-writer skills/human-writing skills/gongkao skills/structured-post skills/zhankai

if [ "${1:-}" = "--push" ]; then
  git -C "$REPO_ROOT" add skills/neat-freak skills/storage-analyzer skills/leader skills/khazix-writer skills/human-writing skills/gongkao skills/structured-post skills/zhankai
  if git -C "$REPO_ROOT" diff --cached --quiet; then
    echo "（无变更可提交）"
  else
    git -C "$REPO_ROOT" commit -m "sync: 同步 Khazix 上游更新"
    git -C "$REPO_ROOT" push
  fi
fi

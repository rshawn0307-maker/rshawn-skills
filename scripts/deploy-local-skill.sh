#!/usr/bin/env bash
#
# 把本机某个自研 skill 从权威源同步到「本仓库 + 各端 agent 工具」。
#
# 为什么需要它：自研 skill 的权威源只有一个（默认 DSH 的 ~/.dsh/skills/<name>），
# 但 Codex / Trae / ZCode / WorkBuddy 各自维护一份独立副本。手工 rsync 五处极易漏，
# 且旧副本里的 __pycache__ 会残留（rsync --exclude 不会删已存在的被排除文件）。
# 本脚本负责：源校验 → 逐目标 rsync --delete → 清 __pycache__ → 哈希一致性终检。
#
# 用法：
#   bash scripts/deploy-local-skill.sh structured-daily          预演（不写任何文件）
#   bash scripts/deploy-local-skill.sh structured-daily --apply  真正写入
#   bash scripts/deploy-local-skill.sh structured-daily --apply --push  写入并 commit + push
#
# 选项：
#   --src <dir>   自定义权威源目录（默认 ~/.dsh/skills/<name>）
#   --apply       真正执行（缺省为预演）
#   --push        写入后 git commit + push（隐含 --apply）
#   --no-agents   只同步到本仓库，不碰各端 agent 工具
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 各端 agent 工具的 skill 根目录。不存在的会跳过（未安装该工具）。
# 只列实际在用的四端。若以后也用 Claude Code / .agents，取消下面注释即可纳入。
AGENT_ROOTS=(
  "$HOME/.codex/skills"
  "$HOME/.trae/skills"
  "$HOME/.zcode/skills"
  "$HOME/.workbuddy/skills"
  # "$HOME/.claude/skills"
  # "$HOME/.agents/skills"
)

NAME=""; SRC=""; APPLY=0; PUSH=0; NO_AGENTS=0
while [ $# -gt 0 ]; do
  case "$1" in
    --src)      SRC="${2:?--src 需要参数}"; shift 2 ;;
    --apply)    APPLY=1; shift ;;
    --push)     APPLY=1; PUSH=1; shift ;;
    --no-agents) NO_AGENTS=1; shift ;;
    -h|--help)  sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)         echo "未知选项: $1" >&2; exit 2 ;;
    *)          NAME="$1"; shift ;;
  esac
done

[ -n "$NAME" ] || { echo "用法: bash scripts/deploy-local-skill.sh <skill 名> [--apply] [--push]" >&2; exit 2; }
[ -n "$SRC" ] || SRC="$HOME/.dsh/skills/$NAME"

# ---- 源校验：必须是含 SKILL.md 的目录 ----
[ -d "$SRC" ] || { echo "[FAIL] 源目录不存在: $SRC" >&2; exit 1; }
[ -f "$SRC/SKILL.md" ] || { echo "[FAIL] 源目录缺 SKILL.md: $SRC" >&2; exit 1; }
SRC="$(cd "$SRC" && pwd -P)"

VERSION="$(grep -m1 '^version:' "$SRC/SKILL.md" | sed 's/^version: *//' || true)"
[ -n "$VERSION" ] || VERSION="(SKILL.md 无 version 行)"

echo "==> skill: $NAME"
echo "    源  : $SRC"
echo "    版本: $VERSION"
echo

# ---- 目标清单 ----
TARGETS=("$REPO_ROOT/skills/$NAME")
if [ "$NO_AGENTS" -eq 0 ]; then
  for R in "${AGENT_ROOTS[@]}"; do
    [ -d "$R" ] && TARGETS+=("$R/$NAME")
  done
fi

# ---- 逐个同步 ----
for DST in "${TARGETS[@]}"; do
  LABEL="$(echo "$DST" | sed "s|$HOME/||; s|$REPO_ROOT/|repo/|")"
  if [ "$APPLY" -eq 1 ]; then
    mkdir -p "$DST"
    rsync -a --delete \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' \
      "$SRC/" "$DST/"
    # rsync 的 --exclude 不会删除目标端已存在的被排除项，需显式清理
    rm -rf "$DST/scripts/__pycache__" "$DST/__pycache__"
    echo "    [SYNC] $LABEL"
  elif [ ! -e "$DST" ]; then
    echo "    [DRY ] $LABEL  →  将新建"
  else
    # grep 无匹配时返回 1，pipefail 下会中断，故容错
    N="$( { diff -rq "$SRC" "$DST" 2>/dev/null || true; } | { grep -v __pycache__ || true; } | wc -l | tr -d ' ')"
    [ "$N" -eq 0 ] && echo "    [DRY ] $LABEL  →  无差异" \
                   || echo "    [DRY ] $LABEL  →  $N 处差异"
  fi
done

[ "$APPLY" -eq 1 ] || { echo; echo "（预演结束，加 --apply 才真正写入）"; exit 0; }

# ---- 终检：所有目标与源的文件集合哈希必须一致 ----
echo
echo "==> 一致性终检"
FAIL=0
BASE_HASH=""
for DST in "$SRC" "${TARGETS[@]}"; do
  H="$(cd "$DST" && find . -type f ! -name '*.pyc' ! -path '*__pycache__*' | sort \
        | xargs md5 -q 2>/dev/null | md5 -q)"
  LABEL="$(echo "$DST" | sed "s|$HOME/||; s|$REPO_ROOT/|repo/|")"
  printf "    %-52s %s\n" "$LABEL" "$H"
  if [ -z "$BASE_HASH" ]; then BASE_HASH="$H"; elif [ "$H" != "$BASE_HASH" ]; then FAIL=1; fi
done
[ "$FAIL" -eq 0 ] || { echo; echo "[FAIL] 存在内容不一致的副本，未提交" >&2; exit 1; }
echo "    [PASS] 全部一致"

# ---- 提交推送 ----
if [ "$PUSH" -eq 1 ]; then
  cd "$REPO_ROOT"
  if git diff --quiet HEAD -- "skills/$NAME" 2>/dev/null && [ -z "$(git status --porcelain "skills/$NAME")" ]; then
    echo
    echo "[NOTE] skills/$NAME 无变更，跳过 commit"
  else
    git add "skills/$NAME"
    git commit -q -m "chore($NAME): 同步本地版本 $VERSION"
    git push origin "$(git rev-parse --abbrev-ref HEAD)"
    echo
    echo "    [PUSH] $(git log --oneline -1)"
  fi
fi

echo
echo "✅ 完成：$NAME $VERSION → ${#TARGETS[@]} 个目标"
echo "   提醒：WorkBuddy / Trae 等 GUI 工具有 skill 列表缓存，需重启应用后才会加载新版本。"

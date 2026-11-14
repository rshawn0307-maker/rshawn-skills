#!/usr/bin/env bash
#
# 一键同步 doc-format skill（da-damu/doc-format-skill）到本仓库。
#
# 用法：
#   bash scripts/sync-doc-format.sh            仅更新工作区文件并打印变更摘要
#   bash scripts/sync-doc-format.sh --push     更新并自动 commit + push
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="doc-format"
UPSTREAM="https://github.com/da-damu/doc-format-skill.git"
ORIGIN_URL="https://github.com/da-damu/doc-format-skill"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "==> 拉取 $UPSTREAM" >&2
git -c http.version=HTTP/1.1 -c http.connectTimeout=30 -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=30 \
  clone --depth 1 "$UPSTREAM" "$TMP_DIR/up" >/dev/null 2>&1 || { echo "拉取失败：$UPSTREAM"; exit 1; }

DST="$REPO_ROOT/skills/$NAME"
mkdir -p "$DST"
rsync -a --delete --exclude='.git' "$TMP_DIR/up/" "$DST/"

# 出处声明（每端一致）
cat > "$DST/ORIGIN.md" <<'EOF'
# 出处 / Origin

本 skill 收录自 [da-damu/doc-format-skill](https://github.com/da-damu/doc-format-skill)（作者：da-damu），保留原作者内容，感谢原作者。

- 2026-11-14 首次收录（上游未打版本标签，收录时为 main 最新）
- 运行依赖：Python ≥3.9 + `python-docx`、`PyYAML`、`PyMuPDF`；出 PDF 另需 LibreOffice（本机已装，`soffice` 在 PATH）
- 上游更新后，在 rshawn-skills 仓库根目录运行一条命令即可同步：

```bash
bash scripts/sync-doc-format.sh
```
EOF

# SKILL.md 来源声明：插在首个 H1 之后，已存在则跳过
python3 - "$DST/SKILL.md" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
if "来源声明" in t:
    sys.exit(0)
note = "> **来源声明**：本 skill 收录自 [da-damu/doc-format-skill](https://github.com/da-damu/doc-format-skill)（作者：da-damu），保留原作者内容，感谢原作者。同步与出处详见本目录 ORIGIN.md。"
lines = t.splitlines()
for i, l in enumerate(lines):
    if l.startswith("# "):
        lines[i+1:i+1] = ["", note]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        break
PY

echo "OK: 已同步 $NAME"
echo
echo "==> 变更摘要："
git -C "$REPO_ROOT" status --short -- "skills/$NAME"

if [ "${1:-}" = "--push" ]; then
  git -C "$REPO_ROOT" add "skills/$NAME"
  if git -C "$REPO_ROOT" diff --cached --quiet; then
    echo "(nothing to commit)"
  else
    git -C "$REPO_ROOT" commit -m "sync: doc-format 上游更新（da-damu/doc-format-skill）"
    git -C "$REPO_ROOT" push
  fi
fi
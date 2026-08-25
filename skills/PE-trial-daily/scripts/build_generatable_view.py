#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成可生成视图 + dry-run 迁移表（任务1）。

只读源数据（activity_index.json / progress_trial.json / 教师用书 MD/PDF），
输出到 --out 指定目录（默认 /tmp，避免污染只读工作区）。

用法：
  python3 build_generatable_view.py --out /tmp/ptd_view [--stats-only]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ptd_core as core


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/ptd_view", help="输出目录")
    ap.add_argument("--index", default=str(core.INDEX_DEFAULT))
    ap.add_argument("--books-dir", default=str(core.BOOKS_DIR_DEFAULT))
    ap.add_argument("--progress", default=str(core.PROGRESS_DEFAULT))
    ap.add_argument("--stats-only", action="store_true")
    args = ap.parse_args()

    view = core.build_generatable_view(
        index_path=Path(args.index),
        books_dir=Path(args.books_dir),
        progress_path=Path(args.progress),
    )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    view_path = out_dir / "generatable_view.json"
    view_path.write_text(json.dumps(view, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "migration_dryrun.json").write_text(
        json.dumps(view["migration_dryrun"], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(view["stats"], ensure_ascii=False))
    print("view ->", view_path)
    if args.stats_only:
        return
    # 误收样例打印（前5条）
    suspects = [
        e for e in view["entries"] if "figure_misattribution_suspect" in e["flags"]
    ]
    print(f"figure_misattribution_suspect 例（{len(suspects)} 条，前5）:")
    for e in suspects[:5]:
        for f in e["figures"]:
            if f.get("match") == "suspect":
                print(f"  {e['id']} ref={f['ref']} caption={f.get('caption','')!r} caption_line={f.get('caption_line')}")


if __name__ == "__main__":
    main()

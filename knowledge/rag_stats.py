#!/usr/bin/env python3
"""rag_stats — print RAG index size, freshness, top files."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

RAG_DIR = Path(os.path.expanduser("~/.local/share/lisa-rag"))
DB_PATH = RAG_DIR / "index.db"
META_PATH = RAG_DIR / "meta.json"


def main() -> int:
    if not DB_PATH.exists():
        print("index does not exist yet — run scripts/rag_index.py")
        return 2

    db_size = DB_PATH.stat().st_size
    print(f"index db: {DB_PATH} ({db_size / 1024 / 1024:.2f} MB)")

    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text())
        print(f"\nlast run: {meta.get('last_run_at')} ({meta.get('last_run_seconds')}s)")
        print(f"  files indexed:        {meta.get('indexed')}")
        print(f"  files skipped:        {meta.get('skipped_unchanged')}")
        print(f"  orphans removed:      {meta.get('orphans_removed')}")
        print(f"  chunks total in db:   {meta.get('chunks_total_in_db')}")
        print(f"  embedding model:      {meta.get('embedding_model')}")

    conn = sqlite3.connect(DB_PATH)
    print(f"\ntop 10 files by chunks count:")
    rows = conn.execute(
        "SELECT path, chunks_count, indexed_at FROM files ORDER BY chunks_count DESC LIMIT 10"
    ).fetchall()
    for path, cnt, ts in rows:
        print(f"  {cnt:5d}  {path}")

    print(f"\ntotals:")
    f_cnt = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    c_cnt = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"  files: {f_cnt}  chunks: {c_cnt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

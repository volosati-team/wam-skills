#!/usr/bin/env python3
"""
rag_search — semantic search over the RAG index.

Returns top-K chunks with source path, line range, score, and preview.

Usage:
  python3 scripts/rag_search.py "ag_gateway tunnel"
  python3 scripts/rag_search.py "натальная карта" --k 10
  python3 scripts/rag_search.py "deepseek провайдер" --jsonl
  python3 scripts/rag_search.py "что я знаю про reminder daemon" --min-score 0.3
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
RAG_DIR = Path(os.path.expanduser("~/.local/share/lisa-rag"))
DB_PATH = RAG_DIR / "index.db"

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_K = 5
DEFAULT_MIN_SCORE = 0.0  # 0..1 cosine similarity (vec0 distance is L2 by default; we sort and trust ranking)

_embedder_cache = None


def _get_embedder():
    global _embedder_cache
    if _embedder_cache is None:
        from fastembed import TextEmbedding
        _embedder_cache = TextEmbedding(model_name=EMBED_MODEL)
    return _embedder_cache


def _embed_query(text: str) -> list[float]:
    """Returns L2-normalized embedding (matches rag_index.py)."""
    import math
    embedder = _get_embedder()
    vec = [float(x) for x in next(iter(embedder.embed([text])))]
    n = math.sqrt(sum(x * x for x in vec))
    return [x / n for x in vec] if n else vec


def _open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(f"index not found at {DB_PATH} — run scripts/rag_index.py first", file=sys.stderr)
        sys.exit(2)
    conn = sqlite3.connect(DB_PATH)
    conn.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _preview(text: str, max_chars: int = 240) -> str:
    text = text.strip().replace("\n", " ")
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + "…"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", type=str)
    ap.add_argument("--k", type=int, default=DEFAULT_K)
    ap.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE,
                    help="Minimum similarity (0..1). Lower = more permissive.")
    ap.add_argument("--jsonl", action="store_true", help="Output as JSON Lines")
    args = ap.parse_args()

    conn = _open_db()
    qvec = _embed_query(args.query)

    rows = conn.execute(
        f"""
        SELECT
            v.distance,
            c.path, c.line_start, c.line_end, c.text
        FROM vec_chunks v
        JOIN chunks c ON c.id = v.rowid
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (json.dumps(qvec), args.k * 2)  # over-fetch, filter below
    ).fetchall()

    # Both index and query vectors are L2-normalized (unit length).
    # For unit vectors: L2_dist² = 2 - 2*cosine, so cosine = 1 - L2²/2.
    # Cosine ranges [-1, 1]; rescale to [0, 1] for intuitive 0..1 similarity.
    results = []
    for distance, path, ls, le, text in rows:
        d = float(distance)
        cosine = 1.0 - (d * d) / 2.0  # in [-1, 1]
        similarity = max(0.0, min(1.0, (cosine + 1.0) / 2.0))  # rescale to [0, 1]
        if similarity < args.min_score:
            continue
        results.append({
            "score": round(similarity, 4),
            "path": path,
            "line_start": ls,
            "line_end": le,
            "preview": _preview(text),
        })
    results = results[:args.k]

    if not results:
        print(f"no matches for: {args.query}", file=sys.stderr)
        return 1

    if args.jsonl:
        for r in results:
            print(json.dumps(r, ensure_ascii=False))
    else:
        for r in results:
            print(f"\n[{r['score']:.3f}] {r['path']}:{r['line_start']}-{r['line_end']}")
            print(f"  {r['preview']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

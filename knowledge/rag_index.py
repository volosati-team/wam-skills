#!/usr/bin/env python3
"""
rag_index — build / update the RAG index over projects/**/*.md.

Storage: ~/.local/share/lisa-rag/index.db (sqlite-vec).
Embeddings: fastembed paraphrase-multilingual-MiniLM-L12-v2 (384-dim, Ru+En).

Usage:
  python3 scripts/rag_index.py --rebuild        # full rebuild from scratch
  python3 scripts/rag_index.py                  # incremental (default)
  python3 scripts/rag_index.py --file <path>    # one file only (for hooks)
  python3 scripts/rag_index.py --dry-run        # report scope, don't write
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
PROJECTS_ROOT = WORKSPACE / "projects"
RAG_DIR = Path(os.path.expanduser("~/.local/share/lisa-rag"))
DB_PATH = RAG_DIR / "index.db"
META_PATH = RAG_DIR / "meta.json"

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBED_DIM = 384
BATCH_SIZE = 32

EXCLUDE_PATTERNS = (
    "/.git/", "/node_modules/", "/archive/", "/archives/",
    "/.bak", ".bak.", "/_archive/",
)
EXCLUDE_BASENAMES = {"override.md", "dashboards.json"}


def _glob_md_files() -> list[Path]:
    out = []
    for p in PROJECTS_ROOT.rglob("*.md"):
        s = str(p)
        if any(pat in s for pat in EXCLUDE_PATTERNS):
            continue
        if p.name in EXCLUDE_BASENAMES:
            continue
        if p.is_symlink():
            continue
        out.append(p)
    return out


def _file_hash(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


_PARA_SPLIT_RE = re.compile(r"\n{2,}")


def _chunk_md(text: str) -> list[tuple[str, int, int]]:
    """Split markdown into paragraph-based chunks with 1-paragraph overlap.

    Returns list of (chunk_text, line_start, line_end) tuples (1-based, inclusive).
    Falls back to fixed-width chunks if no paragraph structure (one huge blob).
    """
    if not text.strip():
        return []

    # Build line index for paragraphs
    paragraphs: list[tuple[str, int, int]] = []
    cur_para: list[str] = []
    cur_start = 1
    for i, line in enumerate(text.splitlines(), start=1):
        if line.strip() == "":
            if cur_para:
                paragraphs.append(("\n".join(cur_para), cur_start, i - 1))
                cur_para = []
            continue
        if not cur_para:
            cur_start = i
        cur_para.append(line)
    if cur_para:
        paragraphs.append(("\n".join(cur_para), cur_start, len(text.splitlines())))

    if not paragraphs:
        return []

    # Fallback: if document is one huge paragraph, do fixed split
    if len(paragraphs) == 1 and len(paragraphs[0][0]) > 800:
        only_text, ls, le = paragraphs[0]
        chunks = []
        for i in range(0, len(only_text), 500):
            chunks.append((only_text[i:i + 600], ls, le))  # naive — line range collapses
        return chunks

    # Build chunks with 1-para overlap. Target ~500-1000 chars per chunk.
    chunks: list[tuple[str, int, int]] = []
    i = 0
    while i < len(paragraphs):
        bucket: list[tuple[str, int, int]] = [paragraphs[i]]
        size = len(paragraphs[i][0])
        j = i + 1
        while j < len(paragraphs) and size < 800:
            bucket.append(paragraphs[j])
            size += len(paragraphs[j][0])
            j += 1
        text_chunk = "\n\n".join(b[0] for b in bucket)
        line_start = bucket[0][1]
        line_end = bucket[-1][2]
        chunks.append((text_chunk, line_start, line_end))
        # Overlap: step by (j-i-1) so next chunk starts at the LAST paragraph of this bucket
        i = max(i + 1, j - 1)
    return chunks


_embedder_cache = None


def _get_embedder():
    global _embedder_cache
    if _embedder_cache is None:
        from fastembed import TextEmbedding
        _embedder_cache = TextEmbedding(model_name=EMBED_MODEL)
    return _embedder_cache


def _normalize(vec: list[float]) -> list[float]:
    """L2-normalize to unit length so vec0 L2 distance equals sqrt(2 - 2*cosine)."""
    import math
    n = math.sqrt(sum(x * x for x in vec))
    if n == 0:
        return vec
    return [x / n for x in vec]


def _embed_batch(texts: list[str]) -> list[list[float]]:
    embedder = _get_embedder()
    return [_normalize(list(map(float, vec))) for vec in embedder.embed(texts)]


def _open_db() -> sqlite3.Connection:
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            md5 TEXT NOT NULL,
            chunks_count INTEGER NOT NULL,
            indexed_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            chunk_idx INTEGER NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            text TEXT NOT NULL,
            UNIQUE(path, chunk_idx),
            FOREIGN KEY(path) REFERENCES files(path) ON DELETE CASCADE
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
            embedding float[{EMBED_DIM}]
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
    """)
    conn.commit()


def _index_one(conn: sqlite3.Connection, path: Path, force: bool = False) -> tuple[int, str]:
    """Index one file. Returns (chunks_added, status). status: indexed|skipped|removed."""
    rel_path = str(path.relative_to(WORKSPACE))
    if not path.exists():
        # Cleanup orphaned entry
        conn.execute("DELETE FROM chunks WHERE path = ?", (rel_path,))
        conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))
        conn.commit()
        return (0, "removed")

    new_md5 = _file_hash(path)
    if not force:
        cur = conn.execute("SELECT md5 FROM files WHERE path = ?", (rel_path,))
        row = cur.fetchone()
        if row and row[0] == new_md5:
            return (0, "skipped")

    text = path.read_text(encoding="utf-8", errors="replace")
    chunks = _chunk_md(text)
    if not chunks:
        return (0, "skipped")

    embeddings = _embed_batch([c[0] for c in chunks])

    # Replace existing chunks for this file
    conn.execute("BEGIN")
    try:
        # Delete old chunks + their vec rows
        old_ids = [r[0] for r in conn.execute(
            "SELECT id FROM chunks WHERE path = ?", (rel_path,)
        ).fetchall()]
        if old_ids:
            placeholders = ",".join("?" for _ in old_ids)
            conn.execute(f"DELETE FROM vec_chunks WHERE rowid IN ({placeholders})", old_ids)
            conn.execute(f"DELETE FROM chunks WHERE id IN ({placeholders})", old_ids)

        # Insert new
        for idx, ((chunk_text, line_start, line_end), emb) in enumerate(zip(chunks, embeddings)):
            cur = conn.execute(
                "INSERT INTO chunks(path, chunk_idx, line_start, line_end, text) VALUES (?, ?, ?, ?, ?)",
                (rel_path, idx, line_start, line_end, chunk_text)
            )
            chunk_id = cur.lastrowid
            conn.execute(
                "INSERT INTO vec_chunks(rowid, embedding) VALUES (?, ?)",
                (chunk_id, json.dumps(emb))
            )

        # Update file record
        conn.execute(
            "INSERT OR REPLACE INTO files(path, md5, chunks_count, indexed_at) VALUES (?, ?, ?, ?)",
            (rel_path, new_md5, len(chunks), time.time())
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return (len(chunks), "indexed")


def _cleanup_orphans(conn: sqlite3.Connection, current_files: set[str]) -> int:
    """Remove DB records for files no longer on disk."""
    db_files = {r[0] for r in conn.execute("SELECT path FROM files").fetchall()}
    orphans = db_files - current_files
    for rel_path in orphans:
        old_ids = [r[0] for r in conn.execute(
            "SELECT id FROM chunks WHERE path = ?", (rel_path,)
        ).fetchall()]
        if old_ids:
            placeholders = ",".join("?" for _ in old_ids)
            conn.execute(f"DELETE FROM vec_chunks WHERE rowid IN ({placeholders})", old_ids)
            conn.execute(f"DELETE FROM chunks WHERE id IN ({placeholders})", old_ids)
        conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))
    conn.commit()
    return len(orphans)


def _save_meta(stats: dict) -> None:
    META_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="Drop everything, full rebuild")
    ap.add_argument("--file", type=str, default=None, help="Index a single file (path relative to workspace)")
    ap.add_argument("--dry-run", action="store_true", help="Report scope, don't write")
    args = ap.parse_args()

    t0 = time.time()
    conn = _open_db()

    if args.rebuild:
        conn.executescript("DROP TABLE IF EXISTS chunks; DROP TABLE IF EXISTS vec_chunks; DROP TABLE IF EXISTS files;")
        conn.commit()
    _ensure_schema(conn)

    if args.file:
        target = (WORKSPACE / args.file).resolve()
        if not str(target).startswith(str(WORKSPACE)):
            print("file outside workspace, refusing", file=sys.stderr)
            return 1
        if args.dry_run:
            print(f"[dry-run] would index: {target.relative_to(WORKSPACE)}")
            return 0
        added, status = _index_one(conn, target, force=False)
        print(f"{status}: {target.relative_to(WORKSPACE)} ({added} chunks)")
        return 0

    files = _glob_md_files()
    if args.dry_run:
        print(f"[dry-run] would scan {len(files)} files")
        for f in files[:10]:
            print(f"  {f.relative_to(WORKSPACE)}")
        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more")
        return 0

    indexed = skipped = 0
    chunks_total = 0
    current_paths = set()
    for p in files:
        current_paths.add(str(p.relative_to(WORKSPACE)))
        try:
            added, status = _index_one(conn, p, force=args.rebuild)
        except Exception as e:
            print(f"  err {p.relative_to(WORKSPACE)}: {e}", file=sys.stderr)
            continue
        chunks_total += added
        if status == "indexed":
            indexed += 1
        elif status == "skipped":
            skipped += 1
        if (indexed + skipped) % 25 == 0:
            print(f"  progress: indexed={indexed} skipped={skipped} chunks={chunks_total}")

    orphans = _cleanup_orphans(conn, current_paths)
    elapsed = time.time() - t0

    stats = {
        "files_total": len(files),
        "indexed": indexed,
        "skipped_unchanged": skipped,
        "orphans_removed": orphans,
        "chunks_total_in_db": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
        "embedding_model": EMBED_MODEL,
        "embedding_dim": EMBED_DIM,
        "last_run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "last_run_seconds": round(elapsed, 2),
    }
    _save_meta(stats)
    print(f"\ndone in {elapsed:.1f}s — indexed={indexed} skipped={skipped} orphans={orphans} "
          f"chunks_in_db={stats['chunks_total_in_db']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

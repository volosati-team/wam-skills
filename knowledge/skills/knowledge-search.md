---
name: knowledge-search
description: Semantic search over your own accumulated notes and project docs (RAG over projects/**/*.md). Trigger when the user asks "what do I know about X", "did I write about Y before", "find in my notes/projects about Z", or when you need context from previously saved reviews, ideas, or teardowns before starting new work. Use this BEFORE grep when the question is conceptual/topical rather than an exact-text lookup.
---

# Knowledge search (RAG)

Semantic search via `knowledge/rag_search.py` — a sqlite-vec index over your
own `projects/**/*.md` notes. Finds topically related content even when the
exact words don't match, which plain `Grep` can't do.

## When to use

- "What do I know about X", "did I ever write about Y", "find my notes on Z"
- You need context from previously saved reviews, ideas, concepts, teardowns
- The question is conceptual/topical, not an exact-text lookup (use `Grep` for that)
- Before starting new work — check whether prior notes already cover the topic
- The user references something they "wrote down once" / "we discussed before"

## When NOT to use

- Exact-text search (a filename, a code snippet) — `Grep` is faster and exact
- File-pattern search (`*.json`, `**/foo`) — use `Glob`
- Searching logs or large JSON/data files — the index only covers `.md` files

## Setup (one-time)

Requires two Python packages and a local sqlite-vec index:

```sh
pip install --user fastembed sqlite-vec
python3 knowledge/rag_index.py --rebuild
```

The index lives at `~/.local/share/lisa-rag/index.db`. First rebuild
downloads the embedding model (~100MB) and processes every `.md` file
under `projects/` — expect a few minutes on a large notes tree.

## Usage

```sh
# top-5 results by default
python3 knowledge/rag_search.py "tunnel connection issue"

# more results
python3 knowledge/rag_search.py "natal chart project" --k 10

# JSON Lines output for parsing
python3 knowledge/rag_search.py "deepseek provider" --jsonl

# raise the relevance floor (0..1, higher = stricter)
python3 knowledge/rag_search.py "what do I know about reminders" --min-score 0.4
```

## Output format

```
[score] path:line_start-line_end
  preview (240 chars max)
```

`score` is normalized similarity (0..1, higher = more relevant). Rough
guide: >0.3 potentially useful, >0.5 clearly on-topic.

## What to do with results

1. Read the top 1-3 chunks in full via your file-read tool, using
   `line_start`/`line_end` to grab full context (the preview is truncated).
2. If nothing useful comes back — reformulate the query (switch language,
   swap a vague theme for concrete terms).
3. If the index is empty or stale (`python3 knowledge/rag_stats.py`) —
   run `python3 knowledge/rag_index.py` (incremental) or `--rebuild`.

## Keeping the index fresh

Two ways to keep it current:

- **Manual**: run `python3 knowledge/rag_index.py` (incremental, only
  re-embeds changed files) whenever you remember to.
- **Automatic**: wire a `PostToolUse` hook on `Write`/`Edit` that calls
  `python3 knowledge/rag_index.py --file <path>` for `.md` files under
  `projects/`. See `agent-behavior/claude-skills.md` in this repo for how
  Claude Code hooks are configured in `.claude/settings.json`.

## Limits

- Indexes only `.md` files under `projects/` (or wherever you point
  `rag_index.py` — check the script's `--help` for scope flags).
- Embedding model: `paraphrase-multilingual-MiniLM-L12-v2` (384-dim,
  multilingual — works across languages in the same index).
- Recall isn't 100% — RAG finds **topically close** content, it doesn't
  guarantee it surfaces everything relevant.

## On error

Run `python3 knowledge/rag_stats.py` first — it reports index size, file
count, and last-indexed timestamp, which covers most "why is this empty/
stale" questions. If `rag_index.py --rebuild` fails on the embedding
download, check network access to the model host (HuggingFace) — fastembed
caches locally after the first successful run.

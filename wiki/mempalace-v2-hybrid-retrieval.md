---
type: Core Architecture
title: MemPalace v2 — SQLite Hybrid Retrieval Memory
description: Full-Python hybrid retrieval engine (SQLite + FTS5 BM25 + fastembed dense + RRF) replacing legacy DuckDB stores.
resource: file:///D:/Work/mempalace/src/mempalace/
tags: [memory, retrieval, sqlite, fts5, embeddings, hybrid, mempalace, typer]
status: active
generated:
  actor: agent:antigravity/1.0
  timestamp: 2026-09-05T22:05:00Z
sources:
  - id: adr-009
    resource: file:///D:/Work/mempalace/docs/decisions/ADR-009-sqlite-hybrid-retrieval-for-mempalace.md
    title: ADR-009 SQLite Hybrid Retrieval for MemPalace
    author: maintainers
    usage_count: 1
    last_modified: 2026-09-03
verified:
  by: agent:antigravity/1.0
  at: 2026-09-05T22:05:00Z
  method: test
---

# MemPalace v2 — SQLite Hybrid Retrieval Memory

## Overview
MemPalace v2 is a full-Python, embedded memory and retrieval engine providing coding agents with durable, searchable, semantic recall across sessions. It supersedes the earlier DuckDB substring search (ADR-002) with a resilient three-layer hybrid retrieval architecture (ADR-009).

## Architecture Layers

- **L1 Lexical**: SQLite FTS5 with porter tokenizer, BM25 scoring, and injection-safe phrase matching with ranked-OR recall fallback.
- **L2 Dense**: Local embeddings generated via `fastembed` (`BAAI/bge-small-en-v1.5`), utilizing numpy cosine similarity or `sqlite-vec` KNN acceleration.
- **L3 Fusion**: Reciprocal Rank Fusion (RRF, with default $k=60$) combining lexical and dense rank lists.

## Source of Truth & Data Model
- Essence markdown files (`MemPalace/essences/*.md`) and Architectural Decision Records (`docs/decisions/*.md`) are the **single source of truth**.
- The SQLite database (`MemPalace/memory.sqlite`) is purely a derived, rebuildable index generated via `mempalace ingest`.
- `mempalace reconcile` monitors drift in both directions between markdown source files and database index rows.

## CLI Subcommands
```bash
uv run python -m mempalace init          # Initialize SQLite schema
uv run python -m mempalace ingest        # Derive DB and search index from essence/ADR files
uv run python -m mempalace embed         # Compute embeddings for dense/hybrid search
uv run python -m mempalace search --mode hybrid --limit 5 "query"
uv run python -m mempalace reconcile     # Report drift between files and database
uv run python -m mempalace register-decisions # Upsert ADR files into index
```


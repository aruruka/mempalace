# MemPalace v2 - hybrid retrieval memory for coding agents

A full-Python, embedded memory + retrieval engine that gives coding agents durable, searchable,
semantic recall across sessions. Essence (lesson) files are the **single source of truth**; the
SQLite database is a derived, rebuildable index.

Three retrieval layers:

- **L1 lexical** - SQLite FTS5 (porter tokenizer), BM25 ranking, AND semantics with a ranked-OR
  recall fallback, injection-safe quoted phrases.
- **L2 dense** - local embeddings via fastembed (`BAAI/bge-small-en-v1.5`), numpy brute-force
  cosine **or** [sqlite-vec](https://github.com/asg017/sqlite-vec) KNN (optional `vec` extra),
  with automatic fallback.
- **L3 fusion** - Reciprocal Rank Fusion (k=60) over the BM25 + dense rankings.

Design decisions live in `docs/decisions/` (ADR-009 supersedes the original DuckDB approach in
ADR-002). The golden-recall benchmark measured 1.000 macro recall@5 (hybrid) on its corpus.

## Setup

Requires Python >= 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                   # base install (BM25 + numpy dense)
uv sync --extra vec       # + sqlite-vec KNN path
uv sync --extra legacy    # + duckdb (only needed for migrating a v1 DuckDB store)
```

Optional extras: `vec` (sqlite-vec), `legacy` (duckdb).

## Usage

```bash
uv run mempalace --help
uv run python -m mempalace init          # create schema (idempotent)
uv run python -m mempalace ingest        # derive DB + search index from essence/ADR files
uv run python -m mempalace embed         # compute embeddings (offline after the first run)
uv run python -m mempalace search --mode hybrid --limit 5 "file lock hermes"
uv run python -m mempalace reconcile     # drift report between files and DB
uv run python -m mempalace sync --id <session_id> --summary "..." --tags a,b
```

### CLI subcommands

`init`, `ingest`, `sync`, `search` (JSON out; `--mode bm25|dense|hybrid`), `reconcile`, `embed`,
`register-tools`, `register-decisions`.

`search` never embeds automatically: without stored vectors it returns BM25 with a note; run
`mempalace embed` first for dense/hybrid (`--no-embed` forces BM25).

## Layout

```
src/mempalace/            package (models/config/storage/ingest/reconcile/embeddings/retrieval/cli)
tests/                    BDD contract + in-memory + black-box tests
tests/benchmark/          golden recall benchmark harness (requires a workspace corpus)
docs/decisions/           ADR-002 (superseded), ADR-009 (current SQLite hybrid decision)
```

## Testing

```bash
uv run pytest             # full suite (BDD, in-memory, black-box)
uv run ruff check . && uv run ruff format --check .
uv run pyright            # src strict; relaxations are per-file directives (see pyrightconfig.json)
```

## Data model & policy

- Essence files (`MemPalace/essences/*.md`) and ADR files are the source of truth; the DB
  (`MemPalace/memory.sqlite`) is derived by `ingest`.
- `reconcile` reports drift in both directions (files vs rows) plus legacy gaps.
- English-only content policy; multilingual embeddings are out of scope.

## License

MIT - see [LICENSE](LICENSE).

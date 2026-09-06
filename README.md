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

## 🚀 Quickstart: Import MemPalace into Your Workspace in 60 Seconds

You can import MemPalace into any existing project using an interactive wizard:

```bash
# Option 1: Zero-install one-liner via uvx
uvx --from git+https://github.com/aruruka/mempalace.git mempalace init-workspace

# Option 2: Install as a standalone CLI tool in your environment (Recommended)
uv tool install git+https://github.com/aruruka/mempalace.git
mempalace init-workspace

# Option 3: Install as a dev dependency in your project
uv add --dev "mempalace @ git+https://github.com/aruruka/mempalace.git"
uv run mempalace init-workspace
```

The initializer wizard guides you interactively through:
1. **Scaffolding**: Creates `MemPalace/essences/` and seeds a starter lesson.
2. **Database Initialization**: Creates the local SQLite database and pre-indexes starter documents.
3. **Agent Configuration**: Tailors rules for your coding agent (**OpenCode**, **Hermes**, **Antigravity / Gemini**, **Claude Code**, or **Cursor**) and installs the proposal-first `memory-sync` skill.
4. **Automated Setup Scripts**: Generates `scripts/setup-mempalace.ps1` (Windows PowerShell) and `scripts/setup-mempalace.sh` (POSIX/Bash) to easily bootstrap `uv` and `mempalace` in any developer or agent environment.
5. **Kick-off Prompt Generation**: Generates a ready-to-use kick-off prompt (`MEMPALACE_KICKOFF.md`) with self-healing instructions and displays it in the terminal.

> **Next step:** Copy the generated Kick-off Prompt and send it to your coding agent. The agent will run `mempalace doctor` to verify memory access and adopt the memory retention protocol!

## Setup (Contributing to Upstream MemPalace)

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
uv run python -m mempalace doctor         # environment & database health diagnostics
uv run python -m mempalace init-workspace # interactive workspace onboarding wizard (alias: setup)
uv run python -m mempalace list           # list all essences, categories, ADRs & vector coverage (alias: ls)
uv run python -m mempalace init           # create schema (idempotent)
uv run python -m mempalace ingest         # derive DB + search index from essence/ADR files
uv run python -m mempalace embed          # compute embeddings (offline after the first run)
uv run python -m mempalace search file lock hermes # multi-token positional search (auto-syncs fresh essences)
uv run python -m mempalace reconcile      # drift report between files and DB
uv run python -m mempalace sync --id <session_id> --summary "..." --tags a,b
```

### CLI subcommands

`doctor`, `init-workspace` (alias `setup`), `list` (alias `ls`), `init`, `ingest`, `sync`, `search` (JSON out;
`--mode bm25|dense|hybrid`, multi-word unquoted args supported), `reconcile`, `embed`, `register-tools`, `register-decisions`.

`init-workspace` auto-indexes dense vectors upon setup, ensuring hybrid search works immediately. `search` lazily detects
and reconciles newly added essence files on disk before executing queries.

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

## Contribution boundary (consumer workspaces)

mempalace is designed to be **consumed as a dependency** (uv path or git dependency), never edited
from inside a consumer checkout. If using mempalace in another repository surfaces a bug or a
missing feature:

1. File an issue at https://github.com/aruruka/mempalace/issues with a repro.
2. Fixes are developed in this repository and released as tags (e.g. `v0.2.0`).
3. Consumers update by refreshing their dependency (e.g. `uv sync --reinstall-package mempalace`
   for a path dependency, or bumping the git tag).

Do **not** patch mempalace code or documentation from the consuming workspace.

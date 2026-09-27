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

---

## 🚀 Setting Up MemPalace in a New Project

Import MemPalace into any existing or new project repository in 60 seconds using the automated onboarding wizard:

### 1. Installation & Scaffolding

```bash
# Option 1: Zero-install one-liner via uvx (Fastest)
uvx --from git+https://github.com/aruruka/mempalace.git mempalace init-workspace

# Option 2: Install as a standalone CLI tool in your environment (Recommended)
uv tool install git+https://github.com/aruruka/mempalace.git
mempalace init-workspace

# Option 3: Install as a project dev dependency (for UV projects)
uv add --dev "mempalace @ git+https://github.com/aruruka/mempalace.git"
uv run mempalace init-workspace
```

*(Note: `mempalace setup` is an alias for `mempalace init-workspace`)*

### 2. What gets generated

The initializer scaffolds:
- `MemPalace/essences/`: Storage directory for markdown lesson files and `template.md`.
- `MemPalace/memory.sqlite`: Derived local index pre-loaded with starter vectors.
- `scripts/setup-mempalace.ps1` & `.sh`: Cross-platform bootstrap scripts for team members & CI runners.
- `.agents/skills/memory-sync/SKILL.md`: Proposal-first memory retention skill for coding agents.
- `MEMPALACE_KICKOFF.md`: Agent activation prompt tailored to your selected agent flavor (**OpenCode**, **Hermes**, **Antigravity / Gemini**, **Claude Code**, or **Cursor**).

### 3. Agent Kick-off & Health Check

1. Copy the generated prompt in `MEMPALACE_KICKOFF.md` and send it to your coding agent.
2. Run `mempalace doctor` at any time to verify system requirements, database integrity, and embedding coverage:
   ```bash
   mempalace doctor
   ```

For detailed architecture, configuration flags, and CI workflows, see the [Workspace Setup & Onboarding Guide](wiki/workspace-setup-and-onboarding.md).

---

## 🛠️ Usage in Consumer Projects

```bash
# Daily operations
mempalace list                             # Catalog all essences, categories, ADRs & vector coverage (alias: ls)
mempalace search file lock hermes          # Multi-word semantic & lexical search (auto-syncs fresh essences)
mempalace doctor                           # Run system & workspace health diagnostics
mempalace ingest                           # Re-index all markdown files into SQLite
mempalace embed                            # Compute embeddings for dense hybrid search
mempalace reconcile                        # Check for drift between disk files and database
mempalace sync --id <id> --summary "..."   # Propose and persist a new memory essence
```

---

## 💻 Setup (Contributing to Upstream MemPalace)

If you are developing or contributing to MemPalace itself:

Requires Python >= 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                   # base install (BM25 + numpy dense)
uv sync --extra vec       # + sqlite-vec KNN path
uv sync --extra legacy    # + duckdb (only needed for migrating a v1 DuckDB store)
```

Optional extras: `vec` (sqlite-vec), `legacy` (duckdb).

### Testing & Verification

```bash
uv run pytest             # full suite (BDD contract, in-memory, black-box)
uv run ruff check . && uv run ruff format --check .
uv run pyright            # src strict; relaxations are per-file directives (see pyrightconfig.json)
```

## Layout

```
src/mempalace/            package (models/config/storage/ingest/reconcile/embeddings/retrieval/cli)
tests/                    BDD contract + in-memory + black-box tests
tests/benchmark/          golden recall benchmark harness (requires a workspace corpus)
docs/decisions/           ADR-002 (superseded), ADR-009 (SQLite hybrid), ADR-010 (workspace initializer)
wiki/                     OKF v0.2 persistent knowledge base
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

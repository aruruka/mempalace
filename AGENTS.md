# AGENTS.md — MemPalace Knowledge Schema & Agent Operating Rules

> Governs agent interactions, execution workflows, and knowledge base conventions for **MemPalace**.
> Synthesizes **Karpathy's LLM Wiki Pattern**, **Google Cloud Open Knowledge Format (OKF v0.2)**, and **Agent2Agent (A2A) Protocol**.

---

## 1. Workspace 3-Layer Architecture

1. **`sources/` (Layer 1 - Immutable Raw Sources)**:
   - Raw benchmark outputs, external protocol references, API logs, and original schema dumps.
   - **Agents MUST NEVER edit files in `sources/`**. Treat as immutable ground truth.

2. **`wiki/` (Layer 2 - Persistent OKF Knowledge Bundle)**:
   - LLM-owned persistent knowledge base.
   - All markdown files MUST include valid OKF v0.2 YAML frontmatter.
   - Incremental synthesis: Ingesting new sources or benchmarks updates concept pages, architecture entities, and cross-references.

3. **`AGENTS.md` (Layer 3 - Knowledge Schema & Agent Operating Rules)**:
   - This document. Governs agent operational rules, frontmatter schemas, workspace constraints, and A2A collaboration.

---

## 2. OKF v0.2 Frontmatter Rules

Every concept document in `wiki/` MUST begin with YAML frontmatter:

```yaml
---
type: <Type Name>                  # REQUIRED (e.g. Architecture, Core Engine, Retrieval Layer, ADR)
title: <Display Title>             # REQUIRED
description: <One-line summary>   # REQUIRED
resource: <Canonical URI/File>     # RECOMMENDED (e.g. src/mempalace/...)
tags: [<tag1>, <tag2>]             # RECOMMENDED
status: active | deprecated        # REQUIRED
generated:
  actor: agent:antigravity/1.0     # REQUIRED
  timestamp: <ISO-8601>            # REQUIRED
sources:                           # RECOMMENDED (Provenance & Credibility Signals)
  - id: <source-id>
    resource: <URI/Path>
    title: <Title>
    author: <actor>
    usage_count: <int>
    last_modified: <YYYY-MM-DD>
verified:                          # RECOMMENDED (Trust Tiering)
  by: human:<id> | agent:<id>
  at: <ISO-8601>
  method: inspection | test
---
```

---

## 3. Reserved Filenames & Navigation

- **`wiki/index.md`**: Content-oriented catalog of all wiki pages grouped by category, with display titles, links, and tags.
- **`wiki/log.md`**: Append-only chronological audit log of all ingests, schema updates, queries, and lint passes (prefixed with `## [YYYY-MM-DD] <action> | <title>`).
- **`llms.txt`**: Standardized AI navigation entrypoint indexing repository guides, architecture, and playbooks.

---

## 4. A2A Agent Card & Capabilities

```yaml
agentCard:
  id: agent:mempalace/core
  role: MemPalace Core Engine Maintainer & Architect
  environment:
    os: Windows 11
    python: ">=3.13"
    packageManager: uv
    tools: [uv, pytest, ruff, pyright, sqlite3, git]
  modalities:
    supported:
      - text/markdown
      - application/json
      - text/x-python
      - text/x-gherkin
  protocols:
    - a2a-protocol: "1.0"
    - okf: "0.2"
    - karpathy-llm-wiki: "1.0"
  rules:
    - "Strict Pyright type-checking (src strict; see pyrightconfig.json)"
    - "Ruff lint and format check required before PR / commit"
    - "Full pytest suite (including BDD contract in tests/features/) must pass"
    - "English-only content policy for memory essences and wiki"
```

---

## 5. Environment & Tooling Rules (Upstream Repository)

- **Workspace Identity**: This repository is the **upstream origin** of `mempalace`. It develops, tests, and publishes the library.
- **Python Toolchain**: Use `uv` exclusively (`uv run`, `uv sync`, `uv lock`, `uv add`). Never use global `pip`.
- **Quality Gates & Verification**:
  - Run `uv run ruff check . && uv run ruff format --check .`
  - Run `uv run pyright` (strict checking for `src/mempalace/`)
  - Run `uv run pytest` (BDD contract, in-memory, black-box CLI tests)
- **Unified 4-Entity Memory Model & Policy**:
  1. **Semantic Memory (`MemPalace/essences/*.md` -> `wisdom`)**:
     - Single source of truth for pitfalls, preferences, and thinking styles (`English-only`).
     - **Deterministic Qualification Gate**: Propose candidates only when Tooling Invisibility $I \ge 2$, Blast Radius $B \ge 2$, and Composite Score $S = 0.35B + 0.30R + 0.20P + 0.15I \ge 3.2$.
  2. **Architectural Memory (`docs/decisions/ADR-NNN-*.md` -> `decisions`)**:
     - Use `docs/decisions/template.md` for Type 1 irreversible architectural decisions.
     - Valid statuses: `draft`, `proposed`, `active`, `accepted`, `rejected`, `deprecated`, `superseded`.
     - **ADR-002 Governance & Supersession Rules**:
       - Supersede old decisions bidirectionally without rewriting history (e.g. ADR-002 DuckDB is marked `superseded` with `Superseded-by: ADR-009`, while ADR-009 has `Supersedes: ADR-002`).
       - Bidirectional consistency and schema validity are enforced via `uv run python scripts/validate_governance.py`.
       - Superseded records (such as ADR-002) are excluded from default retrieval but remain discoverable with `--include-archived`.
     - Register decisions with `uv run python -m mempalace register-decisions` or `uv run mempalace ingest`.
  3. **Episodic Memory (`MemPalace/sessions.jsonl` -> `sessions`)**:
     - At task/session closure, record a condensed session summary via `uv run python -m mempalace sync --id "<session-id>" --summary "<summary>" --tags "<tags>"`.
     - Appends/updates `MemPalace/sessions.jsonl` so episodic history survives `memory.sqlite` rebuilds.
  4. **Procedural Memory (`tools/<subdir>/`, `scripts/*` -> `tool_registry`)**:
     - Before writing a new utility script, search registered tools: `uv run python -m mempalace search --source tool "<capability>"`.
     - Register cohesive tool directories (`tools/<subdir>/`) and standalone scripts (`scripts/*.{py,ps1,sh}`) with `uv run python -m mempalace register-tools` or `uv run mempalace ingest`.
  - **Derived Index, Doctor & Hygiene Sweeps**:
     - `MemPalace/memory.sqlite` is rebuilt from source files via `uv run python -m mempalace ingest`.
     - Run `uv run mempalace doctor --human` (or `mempalace doctor`) to inspect vector synchronization, schema integrity, and stale entry counts.
     - Default `mempalace search` returns only active records (`active`/`accepted`); pass `--include-archived` for historical/superseded items.
     - When `mempalace doctor` warns that non-active records reached the threshold ($\ge 20$), run `uv run python -m mempalace sweep` to evict stale vectors and optimize FTS5.
- **Harness & A2A Collaboration**:
  - Follow A2A Task Object conventions in `docs/harness-playbook/`.
  - Reversible, scoped improvements with explicit acceptance checklists.




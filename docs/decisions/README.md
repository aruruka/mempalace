# Architectural Decision Records (ADRs)

This directory maintains Architecture Decision Records for the MemPalace workspace.
Decisions follow the format defined in [template.md](template.md).

## Index of Decisions

| ADR | Date | Status | Title | Tags |
| --- | --- | --- | --- | --- |
| [ADR-002](ADR-002-duckdb-for-mempalace.md) | 2026-04-16 | `superseded` | DuckDB for MemPalace Storage | memory, storage, duckdb |
| [ADR-009](ADR-009-sqlite-hybrid-retrieval-for-mempalace.md) | 2026-09-03 | `active` | SQLite Hybrid Retrieval for MemPalace v2 | memory, retrieval, sqlite, fts5, embeddings, hybrid |
| [ADR-010](ADR-010-workspace-initializer.md) | 2026-09-06 | `active` | Workspace Initializer and Agent Onboarding Protocol | onboarding, cli, initializer, scaffolding, agent-card, bdd |

---

## Status Definitions
- `draft`: Initial work-in-progress draft.
- `proposed`: Under discussion or prototyping.
- `active` / `accepted`: In effect and binding for current architecture (indexed in default search).
- `superseded`: Replaced by a subsequent decision (requires bidirectional `Supersedes:` / `Superseded-by:` headers; excluded from default search).
- `deprecated`: No longer applicable (excluded from default search).
- `rejected`: Evaluated but not adopted (excluded from default search).



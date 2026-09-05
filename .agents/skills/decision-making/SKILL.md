---
name: decision-making
description: Record, review, supersede, and register architecture decisions as ADRs using workspace best practices and MemPalace integration.
tags:
  - adr
  - architecture
  - governance
  - best-practices
---

# SKILL: Decision Making and ADR Registration

## Description
This skill defines how to record architecture-level decisions in MemPalace so they are durable, reviewable, and searchable in memory.
It combines ADR best practices with repository-specific governance and tooling.

## When to Use
- Major architecture or process decisions (retrieval algorithms, embedding models, storage engine, API design).
- Decisions with meaningful trade-offs that future maintainers will need to understand.
- Cases where a prior decision is being replaced (e.g. ADR-009 superseding ADR-002).

## When Not to Use
- Routine bug fixes.
- Minor version bumps without architectural impact.
- Local implementation details that do not change system architecture.

## ADR Lifecycle
Use one status per ADR:
- `proposed`: Under discussion.
- `active`: Accepted and in force.
- `rejected`: Considered but not adopted.
- `deprecated`: No longer relevant.
- `superseded`: Replaced by another ADR.

## Execution Rules
1. **Before deciding**:
   - Query existing memory first: `uv run python -m mempalace search --mode hybrid "<keywords>"`
   - Check `docs/decisions/` for related ADRs.
2. **ADR format**:
   - Path: `docs/decisions/ADR-NNN-short-slug.md`
   - Use `docs/decisions/template.md`.
   - Metadata: Date, Status, Tags, Deciders.
   - Required sections: Context, Decision Drivers, Options Considered, Decision, Rationale, Consequences, Related Decisions, Supersession.
3. **Status policy**:
   - Use `active` for current decisions.
   - If replaced, create a new ADR and mark old ADR as `superseded`.
   - Do not rewrite history in old ADRs except status and supersession link updates.
4. **MemPalace registration**:
   - Register decisions into SQLite memory store:
     ```bash
     uv run python -m mempalace register-decisions
     ```
   - Update `docs/decisions/README.md` index.


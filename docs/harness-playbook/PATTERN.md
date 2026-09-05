# Harness Engineering Pattern (A2A Protocol Compliant)

## Purpose
Provide a repeatable, standardized pattern for **Agent2Agent (A2A)** Client-Remote collaboration in the MemPalace codebase.

## Protocol Roles
- **A2A Client Agent (Architect)**: Discovers target capabilities, formulates Task Objects, enforces quality gates, and synthesizes returned artifacts.
- **A2A Remote Agent (Implementor)**: Executes scoped tasks, reports lifecycle states (`submitted` -> `working` -> `completed`), and returns deliverable artifacts.

## Core Principles
1. **Capability Discovery First**: Inspect workspace Agent Card in `AGENTS.md` prior to task dispatch.
2. **Atomic Scope**: Scope exactly one meaningful, reversible change per rehearsal.
3. **Structured Task Objects**: Handoffs use multi-part messages (Scope, Acceptance Criteria, Report Template).
4. **Evidence-Based Deliverables**: Validate execution with concrete CLI outputs (`uv run pytest`, `uv run ruff check .`, `uv run pyright`).
5. **OKF Knowledge Compounding**: Implementor outputs write back OKF v0.2 concepts into `wiki/` and append entries to `wiki/log.md`.

## Standard Flow
1. Architect inspects workspace Agent Card and diagnoses environment constraints.
2. Architect formulates an A2A Task Object with explicit workspace-relative paths.
3. Implementor transitions task to `working`, executes changes end-to-end, and generates deliverable artifacts.
4. Implementor transitions task to `completed` and returns structured multi-part report.
5. Architect verifies evidence against acceptance criteria and updates `wiki/` concepts and `wiki/log.md`.

## Quality Gates
1. File-level changes are explicit and non-destructive.
2. Execution evidence (`pytest`, `ruff`, `pyright`) is attached.
3. OKF v0.2 YAML frontmatter is validated for new/updated wiki concepts.


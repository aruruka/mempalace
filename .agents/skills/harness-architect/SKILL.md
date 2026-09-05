---
name: harness-architect
description: Diagnose workspace capabilities, perform A2A Agent Card discovery, and issue A2A Task Objects for implementor agents.
tags:
  - harness
  - architect
  - handoff
  - playbook
  - a2a-protocol
  - okf-v0.2
---

# SKILL: Harness Architect Execution Workflow (A2A Protocol Optimized)

## Description
This skill transforms harness-engineering intent into an **Agent2Agent (A2A) Protocol** compliant task dispatch package. It structures architect-to-implementor collaboration using A2A Agent Cards, Task Objects, multi-part messages, and OKF v0.2 knowledge writebacks.

## Protocol Roles
- **Architect (A2A Client Agent)**: Discovers capabilities, formulates tasks, enforces quality gates, and synthesizes returned artifacts into the workspace knowledge base.
- **Implementor (A2A Remote Agent)**: Receives Task Objects, executes scoped changes, reports state updates (`submitted` -> `working` -> `completed` / `requires_input`), and returns deliverable artifacts.

## When To Use
1. Transforming or initializing a workspace using structured A2A Client/Remote agent collaboration.
2. Generating A2A-compliant task packages with multi-part message contexts and explicit acceptance criteria.
3. Conducting repeatable, state-tracked engineering rehearsals.

## Inputs
1. Target workspace Agent Card (`AGENTS.md` capabilities block).
2. One scoped task focus (atomic, reversible improvement).
3. Available materials under `docs/` and `sources/`.

## Outputs
1. **A2A Agent Card**: Capability & constraint discovery descriptor for the target workspace.
2. **A2A Task Object**: Formatted handoff package containing:
   - `taskId` & initial state (`submitted`).
   - Part 1: Scope & Context (`text/markdown`).
   - Part 2: Acceptance Checklist (`text/markdown`).
   - Part 3: Report-Back Template (`text/markdown`).
3. **OKF v0.2 Knowledge Concepts**: Synthesized deliverable writebacks stored in `wiki/`.
4. **Audit Log Entry**: Chronological update appended to `wiki/log.md`.

## Required References
1. `docs/harness-playbook/PATTERN.md`
2. `docs/harness-playbook/architect-checklist.md`
3. `docs/harness-playbook/implementor-handoff-template.md`
4. `AGENTS.md` in the active workspace

## Execution Rules

1. **A2A Capability Discovery (Agent Card)**:
   - Inspect workspace `AGENTS.md` to verify supported modalities and tools (`uv`, `pytest`, `ruff`, `pyright`, `sqlite3`) before dispatch.

2. **Diagnose & Scope Control**:
   - Identify exactly ONE small, meaningful, and reversible task per rehearsal.
   - Clearly demarcate in-scope vs. out-of-scope boundaries.

3. **Formulate A2A Task Object**:
   - Construct a multi-part message with explicit workspace-relative paths.
   - Define testable acceptance criteria and multi-file report structures.

4. **Quality Gate Before Send**:
   - Verify no destructive commands are implied.
   - Confirm requirements are objectively verifiable via `uv run pytest`, `uv run ruff`, or `uv run pyright`.

5. **Process A2A Remote Agent Deliverables**:
   - Inspect returned A2A Artifacts against the acceptance checklist.
   - Extract actionable feedback and template improvements.

6. **OKF v0.2 Synthesis & Memory Sync**:
   - Write back new or modified concept pages to `wiki/` with valid OKF v0.2 YAML frontmatter.
   - Append an entry to `wiki/log.md` (`## [YYYY-MM-DD] <action> | <title>`).
   - Propose memory essences to user if candidate events occurred.

## Definition Of Done
1. Implementor (Remote Agent) executes task autonomously to completion (`state: completed`).
2. Return message includes structured file diffs, test evidence, and A2A artifact deliverables.
3. Workspace knowledge base (`wiki/`) is updated with OKF v0.2 frontmatter concepts and audited in `wiki/log.md`.


# Architect Checklist (A2A Protocol Compliant)

Use this checklist before issuing an A2A Task Object to an implementor remote agent.

## A) Capability Discovery (Agent Card)
1. Confirm workspace `AGENTS.md` specifies environment capabilities (`uv`, `pytest`, `ruff`, `pyright`, `sqlite3`).
2. Verify workspace supports required modalities (`text/markdown`, `application/json`, `text/x-python`, `text/x-gherkin`).

## B) Task Scope & Safety
1. Scope exactly one small, meaningful, and reversible task.
2. Prohibit destructive file operations and unneeded global installations.
3. State explicit in-scope and out-of-scope boundaries.

## C) A2A Task Object Construction
1. Generate unique `taskId` and set initial state to `submitted`.
2. Attach Part 1 (Scope & Context with explicit workspace-relative paths).
3. Attach Part 2 (Acceptance Checklist with testable criteria).
4. Attach Part 3 (Report-Back Template for multi-file results).

## D) Review of Implementor Artifacts
1. Confirm task state transition to `completed`.
2. Validate changed files against requested scope.
3. Verify test/execution evidence is present and passing (`pytest`, `ruff`, `pyright`).

## E) OKF Synthesis & Post-Run Operations
1. Write back new or modified concept pages to `wiki/` with OKF v0.2 YAML frontmatter.
2. Append chronological entry to `wiki/log.md`.
3. Check for candidate lessons and sync memory if confirmed.


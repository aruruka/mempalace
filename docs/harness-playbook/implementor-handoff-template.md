# Implementor Handoff Template (A2A Protocol Task Object)

Paste and adapt this multi-part message block into the implementor thread.

---

## A2A Task Object

```yaml
taskId: task-<YYYYMMDD>-<slug>
state: submitted
protocolVersion: "1.0"
clientAgent: agent:antigravity/architect
remoteAgent: agent:antigravity/implementor
```

### Part 1: Context & Scope (`text/markdown`)
You are acting as an **A2A Remote Agent** for the MemPalace workspace.

**Goal**:
Execute one scoped improvement end-to-end using the attached materials, then return structured A2A Deliverable Artifacts.

**Priority**:
1. Select exactly one task from `<context_material_path>`.
2. Implement with minimal, reversible edits using project tools (`uv`, `pytest`, `ruff`, `pyright`).
3. Validate using project test suite (`uv run pytest`, `uv run ruff check .`, `uv run pyright`).
4. Return completed report using `<report_template_path>`.

**Required Behavior**:
- Read project operating rules in `AGENTS.md` before editing.
- Log assumptions and potential risks.
- Avoid destructive commands and unrelated edits.

---

### Part 2: Acceptance Checklist (`text/markdown`)
- [ ] Requirements specified in `<acceptance_checklist_path>` are satisfied.
- [ ] No extraneous file changes outside requested task scope.
- [ ] Validation commands executed and clean output attached as evidence.
- [ ] Strict type checking passes (`uv run pyright`).
- [ ] Lint and formatting pass (`uv run ruff check .` and `uv run ruff format --check .`).

---

### Part 3: Report-Back Template (`text/markdown`)
Return a final message with task state set to `completed` containing:
1. **Task State & ID**: `taskId` and completion status.
2. **Changed Files**: Explicit list of modified/created files.
3. **Validation Evidence**: Command outputs proving correctness (`pytest`, `ruff`, `pyright`).
4. **Risks & Logged Assumptions**: Impact assessment.
5. **Knowledge Base Deliverables**: Any created OKF v0.2 concept files for `wiki/`.


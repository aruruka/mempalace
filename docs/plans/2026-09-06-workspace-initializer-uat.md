# Workspace Initializer UAT Implementation Plan

> **For Agent:** REQUIRED SUB-SKILL: Use executing-plans or subagent-driven execution to carry out this plan step-by-step.

**Goal:** Conduct end-to-end User Acceptance Testing (UAT) of the MemPalace Workspace Initializer on an external workspace (`D:/Work/mempalace-uat-workspace`), validating human onboarding, agent kick-off prompt execution, and proposal-first memory synchronization.

**Architecture:** Create an isolated sample project workspace at `D:/Work/mempalace-uat-workspace`, execute human-facing `mempalace init-workspace` scaffolding, inspect the generated scaffolding (`MemPalace/essences/`, `docs/decisions/`, `AGENTS.md`, `.agents/skills/memory-sync/`, `MEMPALACE_KICKOFF.md`), simulate the coding agent executing the kick-off prompt, and test the full proposal-first memory ingestion cycle.

**Tech Stack:** Python 3.13, MemPalace v2 (SQLite + FTS5 + Embeddings), Typer CLI, pytest-bdd.

---

### Task 1: Prepare External Sample Workspace

**Files:**
- Create: `D:/Work/mempalace-uat-workspace/README.md`
- Create: `D:/Work/mempalace-uat-workspace/pyproject.toml`
- Create: `D:/Work/mempalace-uat-workspace/src/sample_app/main.py`
- Create: `D:/Work/mempalace-uat-workspace/AGENTS.md` (initial baseline to test non-destructive appending)

**Step 1: Create target directory and sample project files**
- Scaffold `D:/Work/mempalace-uat-workspace` with a minimal Python web service.
- Add an existing `AGENTS.md` to verify that `init-workspace` appends without clobbering existing instructions.

**Step 2: Verify workspace isolation**
- Confirm directory structure exists and contains no prior `MemPalace/` files.

---

### Task 2: Execute Human-Facing Workspace Initialization

**Files:**
- Output generated in: `D:/Work/mempalace-uat-workspace/`

**Step 1: Execute `mempalace init-workspace` CLI command**
- Run `uv run python -m mempalace init-workspace --workspace D:/Work/mempalace-uat-workspace --agent-flavor antigravity`
- Inspect CLI console output, ASCII banners, and generated summary report.

**Step 2: Inspect Scaffolding Outputs**
- Verify `MemPalace/essences/README.md` and starter essence `YYYY-MM-DD-welcome-to-mempalace.md`.
- Verify `docs/decisions/README.md` and `docs/decisions/template.md`.
- Verify `AGENTS.md` contains `<!-- BEGIN MEMPALACE INTEGRATION -->` block.
- Verify `.agents/skills/memory-sync/SKILL.md` is installed.
- Verify `MemPalace/memory.sqlite` was created with indexed starter essence.
- Verify `MEMPALACE_KICKOFF.md` contains tailored Antigravity instructions and verification command.

---

### Task 3: Agent Onboarding & Kick-Off Prompt Execution

**Files:**
- Read: `D:/Work/mempalace-uat-workspace/MEMPALACE_KICKOFF.md`

**Step 1: Ingest & Execute Kick-Off Prompt**
- Extract the verification command from `MEMPALACE_KICKOFF.md`:
  `uv run python -m mempalace search --workspace D:/Work/mempalace-uat-workspace --mode bm25 "welcome"`
- Verify search returns the starter essence with score and metadata.

**Step 2: Verify Hybrid Retrieval in External Workspace**
- Run:
  `uv run python -m mempalace search --workspace D:/Work/mempalace-uat-workspace --mode hybrid "starter rules"`
- Confirm hybrid ranking and JSON formatting.

---

### Task 4: Validate Proposal-First Memory Sync Workflow

**Files:**
- Create: `D:/Work/mempalace-uat-workspace/MemPalace/essences/2026-09-06-sample-preference.md`

**Step 1: Agent Proposal Simulation**
- Simulate coding agent proposing a new preference essence according to `memory-sync` protocol.

**Step 2: Write approved essence and trigger ingest**
- Write `MemPalace/essences/2026-09-06-sample-preference.md`.
- Run:
  `uv run python -m mempalace ingest --workspace D:/Work/mempalace-uat-workspace`
- Verify database updates (`docs_indexed` count increments).

**Step 3: Query newly ingested essence**
- Search for the newly added preference to confirm end-to-end recall.

---

### Task 5: Verify Idempotency & Summary

**Step 1: Re-run `init-workspace` on the same workspace**
- Ensure existing essences and custom agent instructions are preserved without duplicate markers or corruption.

**Step 2: Document UAT Results**
- Summarize verification outputs and confirmation.

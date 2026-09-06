# Environment Prerequisites & Automated Setup Implementation Plan

> **For Agent:** REQUIRED SUB-SKILL: Use executing-plans or subagent-driven execution to carry out this plan task-by-task.

**Goal:** Enhance the MemPalace Workspace Initializer with automated environment setup scripts (`setup-mempalace.ps1`/`.sh`), a system diagnostic command (`mempalace doctor`), and self-healing environment bootstrap guidance in agent kick-off prompts.

**Architecture:** 
1. Build `src/mempalace/doctor.py` to inspect runtime environment (Python >= 3.13, `uv`, SQLite FTS5, embeddings, and workspace SQLite DB) with dual human/agent output.
2. Extend `src/mempalace/initializer.py` to scaffold cross-platform setup scripts (`scripts/setup-mempalace.ps1` and `scripts/setup-mempalace.sh`) that automatically detect/install `uv` and install the `mempalace` CLI tool.
3. Update `generate_kickoff_prompt` and `generate_agent_rules` in `src/mempalace/initializer.py` to provide coding agents with immediate fallback and self-healing commands if `mempalace` is not in PATH.
4. Add comprehensive BDD/pytest tests and update ADR-010 / README.

**Tech Stack:** Python 3.13, Typer CLI, SQLite FTS5, FastEmbed, PowerShell, POSIX Shell, pytest-bdd.

---

### Task 1: Implement `mempalace doctor` Diagnostic Module

**Files:**
- Create: `src/mempalace/doctor.py`
- Modify: `src/mempalace/cli.py`
- Test: `tests/test_doctor.py`

**Step 1: Write the failing tests in `tests/test_doctor.py`**
- Test `diagnose_environment(workspace)` returns structured `DoctorReport`.
- Test `mempalace doctor` CLI command outputs JSON with `--agent` flag.
- Test `mempalace doctor` CLI command outputs human checklist.

**Step 2: Run tests to verify they fail**
Run: `uv run pytest tests/test_doctor.py`
Expected: FAIL (module not found)

**Step 3: Implement `src/mempalace/doctor.py` and register in `src/mempalace/cli.py`**
- Check Python version (`sys.version_info >= (3, 13)`).
- Check `uv` binary availability (`shutil.which("uv")`).
- Check SQLite FTS5 extension support.
- Check fastembed importability.
- Check workspace DB integrity and document count.
- Expose `@app.command(name="doctor")` in `cli.py`.

**Step 4: Run tests to verify they pass**
Run: `uv run pytest tests/test_doctor.py`
Expected: PASS

---

### Task 2: Implement Cross-Platform Setup Scripts Generator

**Files:**
- Modify: `src/mempalace/initializer.py`
- Test: `tests/test_workspace_initializer.py`

**Step 1: Write failing tests for script scaffolding**
- Test that `initialize_workspace` generates `scripts/setup-mempalace.ps1` and `scripts/setup-mempalace.sh`.
- Test that scripts contain automated `uv` detection and `uv tool install` routines.

**Step 2: Run tests to verify they fail**
Run: `uv run pytest tests/test_workspace_initializer.py -k test_scripts`
Expected: FAIL

**Step 3: Implement setup script templates in `src/mempalace/initializer.py`**
- Add `_SETUP_PS1_TEMPLATE` (PowerShell: checks for `uv`, installs if missing, runs `uv tool install`, runs `mempalace ingest`).
- Add `_SETUP_SH_TEMPLATE` (Bash: checks for `uv`, installs via curl if missing, runs `uv tool install`, runs `mempalace ingest`).
- Add `setup_scripts: bool = True` to `WorkspaceInitializerConfig`.
- Write scripts to `ws / "scripts"` in `initialize_workspace`.

**Step 4: Run tests to verify they pass**
Run: `uv run pytest tests/test_workspace_initializer.py`
Expected: PASS

---

### Task 3: Enhance Agent Kick-Off Prompts with Self-Healing Guidance

**Files:**
- Modify: `src/mempalace/initializer.py`
- Modify: `tests/test_workspace_initializer.py`

**Step 1: Update `generate_kickoff_prompt` and `generate_agent_rules`**
- Include "Environment Prerequisite & Self-Healing" section in `MEMPALACE_KICKOFF.md`:
  - Self-check: `mempalace doctor`
  - If command not found: run `.\scripts\setup-mempalace.ps1` (or `./scripts/setup-mempalace.sh`) or `uv tool install mempalace` / `uvx mempalace`.
- Include guidance in `AGENTS.md` and `.agents/skills/memory-sync/SKILL.md`.

**Step 2: Update unit test assertions**
- Verify kickoff prompt contains `mempalace doctor` and fallback instructions.

**Step 3: Run pytest to verify**
Run: `uv run pytest tests/test_workspace_initializer.py`
Expected: PASS

---

### Task 4: Update Documentation & Quality Gates

**Files:**
- Modify: `README.md`
- Modify: `docs/decisions/ADR-010-workspace-initializer.md`
- Modify: `tests/features/workspace_initializer.feature`

**Step 1: Document `mempalace doctor` and setup scripts in `README.md`**
**Step 2: Add BDD scenario for environment diagnostics and setup scripts**
**Step 3: Run full verification suite**
Run: `uv run pytest && uv run ruff check . && uv run pyright`
Expected: All 100% PASS with 0 warnings/errors.

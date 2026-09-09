# CLI Robustness, Auto-Embedding & Memory Discovery Implementation Plan

> **For Agent:** REQUIRED SUB-SKILL: Use executing-plans or subagent-driven development to execute this plan task-by-task.

**Goal:** Implement 4 core improvements identified during UAT: multi-word search argument parsing, auto-embedding during workspace initialization, lazy auto-ingest on search, and a new `mempalace list` memory catalog command.

**Architecture:**
1. **Multi-Word Search**: Update `search` command in `src/mempalace/cli.py` to accept `list[str]` for `keywords`, safely joining tokens into a single query string.
2. **Auto-Embedding Initializer**: Extend `src/mempalace/initializer.py` with `embed: bool = True` to prime dense vector embeddings during `init-workspace`, updating setup scripts accordingly.
3. **Lazy Auto-Ingest**: Add a fast freshness check in `src/mempalace/retrieval.py` / `cli.py` that syncs unindexed or modified essences before executing search queries.
4. **Memory Discovery (`mempalace list`)**: Add `@app.command(name="list")` in `cli.py` to display structured catalogs of wisdom essences and ADR decisions for humans and AI agents.

**Tech Stack:** Python 3.13, Typer, SQLite FTS5, FastEmbed, pytest, pytest-bdd.

---

### Task 1: Multi-Word Search Argument Parsing

**Files:**
- Modify: `src/mempalace/cli.py`
- Test: `tests/test_cli_blackbox.py`

**Step 1: Write failing black-box test for multi-word search without quotes**
```python
def test_blackbox_search_multi_word_unquoted_args(cli_runner: CliRunner, workspace: Path) -> None:
    # Passing separate arguments: "search", "hermes", "file", "locking"
    result = cli_runner.invoke(
        app, ["search", "hermes", "file", "locking", "--workspace", str(workspace)]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data["hits"]) >= 1
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/test_cli_blackbox.py -k test_blackbox_search_multi_word_unquoted_args`
Expected: FAIL (`Got unexpected extra argument(s)`)

**Step 3: Implement `keywords: Annotated[list[str], typer.Argument(...)]` in `src/mempalace/cli.py`**
- Join arguments: `query_str = " ".join(keywords).strip()`.
- Validate that `query_str` is not empty.

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/test_cli_blackbox.py -k test_blackbox_search_multi_word_unquoted_args`
Expected: PASS

---

### Task 2: Auto-Embedding during Workspace Initialization

**Files:**
- Modify: `src/mempalace/initializer.py`
- Modify: `src/mempalace/cli.py`
- Test: `tests/test_workspace_initializer.py`

**Step 1: Write failing test for auto-embedding during initialization**
```python
def test_initialize_workspace_with_embeddings(tmp_path: Path) -> None:
    cfg = WorkspaceInitializerConfig(
        workspace=tmp_path,
        seed_essences=True,
        embed=True,
    )
    report = initialize_workspace(cfg)
    assert report.vectors_indexed >= 1
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/test_workspace_initializer.py -k test_initialize_workspace_with_embeddings`
Expected: FAIL (`report has no attribute vectors_indexed`)

**Step 3: Implement embedding generation in `initialize_workspace`**
- Add `embed: bool = True` to `WorkspaceInitializerConfig`.
- Add `vectors_indexed: int = 0` to `WorkspaceInitializerReport`.
- In `initialize_workspace`, compute embeddings if `cfg.embed` is True and fastembed is available.
- Add `--embed / --no-embed` to `init-workspace` CLI command.
- Add `mempalace embed` to `_SETUP_PS1_TEMPLATE` and `_SETUP_SH_TEMPLATE`.

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/test_workspace_initializer.py`
Expected: PASS

---

### Task 3: Lazy Auto-Ingest on Search (Freshness Guarantee)

**Files:**
- Modify: `src/mempalace/ingest.py`
- Modify: `src/mempalace/cli.py`
- Test: `tests/test_retrieval.py`

**Step 1: Write failing test for search discovering newly added essence without manual ingest**
```python
def test_search_auto_syncs_new_essence(tmp_path: Path, cli_runner: CliRunner) -> None:
    # 1. Initialize workspace
    cfg = WorkspaceInitializerConfig(workspace=tmp_path)
    initialize_workspace(cfg)
    # 2. Add new essence directly to disk without running mempalace ingest
    new_essence = tmp_path / "MemPalace" / "essences" / "2026-09-06-dynamic-rule.md"
    new_essence.write_text(
        "# Dynamic Rule\nCategory: preference\nAlways use strict linting.\n", encoding="utf-8"
    )
    # 3. Search should automatically detect and return the new essence
    result = cli_runner.invoke(app, ["search", "dynamic", "rule", "--workspace", str(tmp_path)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert any(h["source_ref"] == "2026-09-06-dynamic-rule" for h in data["hits"])
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/test_retrieval.py -k test_search_auto_syncs_new_essence`
Expected: FAIL

**Step 3: Implement auto-reconciliation before search in `cli.py`**
- Check if any `.md` file in `essence_dir` or `decisions_dir` is missing from `search_docs` or modified.
- Ingest changes seamlessly before querying.

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/test_retrieval.py -k test_search_auto_syncs_new_essence`
Expected: PASS

---

### Task 4: Memory Catalog Discovery Command (`mempalace list`)

**Files:**
- Modify: `src/mempalace/cli.py`
- Test: `tests/test_cli_blackbox.py`

**Step 1: Write failing test for `mempalace list` command**
```python
def test_cli_list_memories_agent_json(tmp_path: Path, cli_runner: CliRunner) -> None:
    cfg = WorkspaceInitializerConfig(workspace=tmp_path)
    initialize_workspace(cfg)
    result = cli_runner.invoke(app, ["list", "--workspace", str(tmp_path), "--agent"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "essences" in data
    assert "decisions" in data
    assert len(data["essences"]) >= 1
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/test_cli_blackbox.py -k test_cli_list_memories`
Expected: FAIL (`No such command 'list'`)

**Step 3: Implement `@app.command(name="list")` in `src/mempalace/cli.py`**
- Fetch all wisdom rows, decision rows, and vector status from SQLite.
- Emit structured JSON in `--agent` mode.
- Render styled summary table in `--human` / interactive mode.

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/test_cli_blackbox.py -k test_cli_list_memories`
Expected: PASS

---

### Task 5: Full QA Verification, Documentation & Git Sync

**Files:**
- Update: `README.md`
- Update: `docs/decisions/ADR-010-workspace-initializer.md`
- Update: `wiki/log.md`

**Step 1: Run full test suite & linters**
- `uv run pytest`
- `uv run ruff check .`
- `uv run pyright`
**Step 2: Re-install tool locally and verify against `../mempalace-uat-workspace-human`**
**Step 3: Commit and push changes to `origin/main`**

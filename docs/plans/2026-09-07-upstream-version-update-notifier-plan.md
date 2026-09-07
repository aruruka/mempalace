# Upstream Version Update Notifier Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a lightweight, non-intrusive runtime update notifier in MemPalace that checks upstream GitHub releases with a 24-hour workspace TTL and prints an agent-actionable update banner to `stderr`.

**Architecture:**
1. Zero-dependency notifier module `src/mempalace/notifier.py` with standard library `urllib.request`, 1.5s socket timeout, and silent failure on network/rate-limit errors.
2. Workspace-scoped JSON cache `MemPalace/.cache.json` storing `last_checked_at` and `latest_version` with an 86400-second TTL.
3. Non-intrusive `stderr` banner rendering with clean stdout preservation and `MEMPALACE_NO_UPDATE_CHECK=1` opt-out support.
4. BDD contract tests in `tests/features/update_notifier.feature` and pytest-bdd step definitions in `tests/test_bdd_contract.py`.

**Tech Stack:** Python 3.13, Typer, pytest, pytest-bdd, urllib.request, json, sys.stderr.

---

### Task 1: Core Notifier Logic & Cache Management

**Files:**
- Create: `src/mempalace/notifier.py`
- Create: `tests/test_notifier.py`

**Step 1: Write failing unit tests for `UpdateCache`, `SemverComparator`, and `NoticeRenderer`**
- In `tests/test_notifier.py`:
  - Test semver comparison (`parse_semver("0.3.0") > parse_semver("0.2.1")`).
  - Test `UpdateCache` reads/writes `MemPalace/.cache.json` and evaluates TTL expiry correctly.
  - Test `NoticeRenderer.render(...)` produces the expected box banner text.

**Step 2: Run test to verify it fails**
- Run: `uv run pytest tests/test_notifier.py -v`
- Expected: FAIL with `ModuleNotFoundError: No module named 'mempalace.notifier'`

**Step 3: Implement minimal notifier classes in `src/mempalace/notifier.py`**
- Implement `parse_semver(version: str) -> tuple[int, ...]`.
- Implement `UpdateCache`:
  - `read(workspace: Path) -> dict[str, Any] | None`
  - `write(workspace: Path, latest_version: str, timestamp: float | None = None) -> None`
  - `is_expired(cache: dict[str, Any] | None, ttl_seconds: int = 86400) -> bool`
- Implement `GitHubVersionChecker`:
  - `fetch_latest_version(current_version: str, timeout: float = 1.5) -> str | None` (catches all exceptions, returns `None` on failure).
- Implement `NoticeRenderer`:
  - `render_banner(current_version: str, latest_version: str) -> str`
- Implement `check_and_notify(workspace: Path, current_version: str) -> str | None`.

**Step 4: Run test to verify it passes**
- Run: `uv run pytest tests/test_notifier.py -v`
- Expected: PASS

**Step 5: Commit**
```bash
git add src/mempalace/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): add core version check, cache, and banner rendering"
```

---

### Task 2: Executable BDD Contract Specification & Step Bindings

**Files:**
- Create: `tests/features/update_notifier.feature`
- Modify: `tests/test_bdd_contract.py`

**Step 1: Create `tests/features/update_notifier.feature`**
- Define 4 scenarios:
  1. Cache hit with a newer version displays notice without network call.
  2. Expired cache performs network check and caches latest release.
  3. Network failure or timeout fails silently.
  4. Update check is disabled via environment variable `MEMPALACE_NO_UPDATE_CHECK=1`.

**Step 2: Bind scenario steps in `tests/test_bdd_contract.py`**
- Add `_NOTIFIER_FEATURE = Path(__file__).with_name("features") / "update_notifier.feature"` and `scenarios(str(_NOTIFIER_FEATURE))`.
- Add step definitions for:
  - `@given(parsers.parse('a workspace with cached version "{cached_version}" checked {hours:d} hour ago'))`
  - `@given(parsers.parse('upstream GitHub reports latest release "{latest_version}"'))`
  - `@given('upstream GitHub is unreachable or times out')`
  - `@given(parsers.parse('the environment variable "{var_name}" is set to "{val}"'))`
  - `@then(parsers.parse('stderr displays an update banner suggesting "{expected_version}"'))`
  - `@then(parsers.parse('"{cache_rel_path}" is updated with "{expected_version}"'))`
  - `@then('no update check or banner is emitted to stderr')`

**Step 3: Run BDD test to verify failure or missing steps**
- Run: `uv run pytest tests/test_bdd_contract.py -k "update_notifier" -v`
- Expected: FAIL / StepDefinitionNotFoundError (until step logic is hooked)

**Step 4: Implement mocked step logic in `tests/test_bdd_contract.py`**
- Wire test fixtures with `monkeypatch` to simulate network and check stderr outputs.

**Step 5: Run test to verify it passes**
- Run: `uv run pytest tests/test_bdd_contract.py -k "update_notifier" -v`
- Expected: PASS

**Step 6: Commit**
```bash
git add tests/features/update_notifier.feature tests/test_bdd_contract.py
git commit -m "test(bdd): add executable acceptance criteria for update notifier"
```

---

### Task 3: CLI Integration Hooking

**Files:**
- Modify: `src/mempalace/cli.py`
- Test: `tests/test_cli_blackbox.py`

**Step 1: Write failing black-box test in `tests/test_cli_blackbox.py`**
- Test that executing a CLI command (e.g. `mempalace search` or `mempalace doctor`) with an update available prints the banner to `stderr` and preserves valid JSON on `stdout`.

**Step 2: Run test to verify it fails**
- Run: `uv run pytest tests/test_cli_blackbox.py -k "test_update_notifier" -v`
- Expected: FAIL

**Step 3: Hook `check_and_notify` in `src/mempalace/cli.py`**
- Add `_maybe_notify_update(workspace: Path)` helper in `cli.py`.
- Call `_maybe_notify_update` in `_open_db` and lifecycle commands (`doctor`, `init_workspace`).
- Ensure `sys.stderr.write(banner + "\n")` is used, leaving `_emit()` / `stdout` untouched.

**Step 4: Run test to verify it passes**
- Run: `uv run pytest tests/test_cli_blackbox.py -k "test_update_notifier" -v`
- Expected: PASS

**Step 5: Commit**
```bash
git add src/mempalace/cli.py tests/test_cli_blackbox.py
git commit -m "feat(cli): hook update notifier into CLI execution lifecycle"
```

---

### Task 4: Full Verification & Quality Gates

**Files:**
- Check: All modified and new files

**Step 1: Run Ruff linter and formatter**
- Run: `uv run ruff check . && uv run ruff format --check .`
- Expected: All checks pass with 0 errors.

**Step 2: Run Pyright strict type checking**
- Run: `uv run pyright`
- Expected: 0 errors, 0 warnings.

**Step 3: Run entire pytest test suite**
- Run: `uv run pytest`
- Expected: All tests (including new BDD scenarios) pass.

**Step 4: Commit and finalize**
```bash
git add .
git commit -m "chore: format and lint update notifier implementation"
```

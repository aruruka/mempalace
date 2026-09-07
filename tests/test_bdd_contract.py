# pyright: basic
"""BDD contract tests: Gherkin scenarios executed via pytest-bdd."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from typer.testing import CliRunner

from mempalace import notifier, storage
from mempalace.cli import app

_FEATURE = Path(__file__).with_name("features") / "mempalace.feature"
scenarios(str(_FEATURE))

_WS_INIT_FEATURE = Path(__file__).with_name("features") / "workspace_initializer.feature"
scenarios(str(_WS_INIT_FEATURE))

_NOTIFIER_FEATURE = Path(__file__).with_name("features") / "update_notifier.feature"
scenarios(str(_NOTIFIER_FEATURE))


@pytest.fixture
def search_out() -> dict[str, object]:
    """Mutable holder carrying the last search JSON across steps."""
    return {}


@given("a fresh workspace database is initialized")
def _given_init(app_cmd: Any) -> None:
    result = app_cmd(["init"])
    assert result.exit_code == 0  # type: ignore[union-attr]


@then("the database contains the v1-mirror tables and an FTS index")
def _then_tables(db_path: Path) -> None:
    conn = storage.connect(db_path)
    try:
        tables = storage.table_names(conn)
    finally:
        conn.close()
    for expected in ("wisdom", "sessions", "tool_registry", "decisions"):
        assert expected in tables
    assert any("fts" in name for name in tables)


@given("a workspace with essence files and an ADR file")
def _given_workspace(workspace: Path) -> None:
    assert (workspace / "MemPalace" / "essences").exists()
    assert (workspace / "docs" / "decisions").exists()


@when("the CLI ingests the workspace")
def _when_ingest(app_cmd: Any) -> None:
    result = app_cmd(["ingest"])
    assert result.exit_code == 0  # type: ignore[union-attr]


@then("the database has one wisdom row per essence file")
def _then_wisdom_rows(db_path: Path) -> None:
    conn = storage.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM wisdom").fetchone()[0]
    finally:
        conn.close()
    assert int(count) == 3


@then("the database has one decision row per ADR file")
def _then_decision_rows(db_path: Path) -> None:
    conn = storage.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    finally:
        conn.close()
    assert int(count) == 1


@then("the search index is populated")
def _then_index_populated(db_path: Path) -> None:
    conn = storage.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM search_docs").fetchone()[0]
    finally:
        conn.close()
    assert int(count) > 0


@given("a workspace ingested into the database")
def _given_ingested(ingested: Path) -> None:
    assert ingested.exists()


@when(parsers.re('I search in bm25 mode for "(?P<query>[^"]+)"'))
def _when_search_bm25(app_cmd: Any, search_out: dict[str, object], query: str) -> None:
    result = app_cmd(["search", query, "--mode", "bm25", "--limit", "5"])
    assert result.exit_code == 0  # type: ignore[union-attr]
    search_out["json"] = json.loads(result.output)  # type: ignore[union-attr]


@then("the top hit references the hermes file-locking essence")
def _then_top_hit_hermes(search_out: dict[str, object]) -> None:
    payload = search_out["json"]
    assert isinstance(payload, dict)
    hits = payload["hits"]
    assert isinstance(hits, list) and hits
    first = hits[0]
    assert isinstance(first, dict)
    assert first["source_ref"] == "2026-08-20-hermes-file-locking"


@then("every hit references the uv cache rename essence")
def _then_all_hits_uv(search_out: dict[str, object]) -> None:
    payload = search_out["json"]
    assert isinstance(payload, dict)
    hits = payload["hits"]
    assert isinstance(hits, list) and hits
    for hit in hits:
        assert isinstance(hit, dict)
        assert hit["source_ref"] == "2026-07-17-uv-cache-rename"


@then("the hit count is one")
def _then_hit_count_one(search_out: dict[str, object]) -> None:
    payload = search_out["json"]
    assert isinstance(payload, dict)
    assert payload["count"] == 1


@then("the command prints valid JSON with a hits array")
def _then_valid_json(search_out: dict[str, object]) -> None:
    payload = search_out["json"]
    assert isinstance(payload, dict)
    assert isinstance(payload["hits"], list)


@when("I run reconcile")
def _when_reconcile(app_cmd: Any) -> None:
    result = app_cmd(["reconcile"])
    assert result.exit_code == 0  # type: ignore[union-attr]


@then("the drift report lists no files without rows and no rows without files")
def _then_no_drift(db_path: Path, workspace: Path) -> None:
    conn = storage.connect(db_path)
    try:
        from mempalace import reconcile

        report = reconcile.reconcile(conn, workspace)
    finally:
        conn.close()
    assert report.files_without_row == []
    assert report.rows_without_file == []
    assert report.decision_files_without_row == []
    assert report.decision_rows_without_file == []


@when("the CLI ingests the workspace again")
def _when_ingest_again(app_cmd: Any) -> None:
    result = app_cmd(["ingest"])
    assert result.exit_code == 0  # type: ignore[union-attr]


@then("the wisdom and decision counts are unchanged")
def _then_counts_unchanged(db_path: Path) -> None:
    conn = storage.connect(db_path)
    try:
        wisdom = conn.execute("SELECT COUNT(*) FROM wisdom").fetchone()[0]
        decisions = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    finally:
        conn.close()
    assert int(wisdom) == 3
    assert int(decisions) == 1


@pytest.fixture
def target_ws(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("target_ws")


@given("a clean target workspace directory")
def _given_clean_ws(target_ws: Path) -> None:
    assert target_ws.exists()


@when(parsers.parse('the CLI initializes the workspace for "{agent}"'))
def _when_init_ws(cli_runner: Any, target_ws: Path, agent: str) -> None:
    result = cli_runner.invoke(
        app,
        ["init-workspace", "--workspace", str(target_ws), "--agent", "--agent-flavor", agent],
    )
    assert result.exit_code == 0, result.output


@when(parsers.parse('the CLI initializes the workspace for "{agent}" again'))
def _when_init_ws_again(cli_runner: Any, target_ws: Path, agent: str) -> None:
    result = cli_runner.invoke(
        app,
        ["init-workspace", "--workspace", str(target_ws), "--agent", "--agent-flavor", agent],
    )
    assert result.exit_code == 0, result.output


@then("the workspace has a MemPalace essences directory")
def _then_essences_dir(target_ws: Path) -> None:
    assert (target_ws / "MemPalace" / "essences").is_dir()


@then("the workspace has a starter essence file")
def _then_starter_essence(target_ws: Path) -> None:
    essences = list((target_ws / "MemPalace" / "essences").glob("*-welcome-to-mempalace.md"))
    assert len(essences) == 1


@then("the workspace has a memory SQLite database")
def _then_ws_db(target_ws: Path) -> None:
    db_file = target_ws / "MemPalace" / "memory.sqlite"
    assert db_file.exists()


@then("the workspace has an AGENTS.md file")
def _then_agents_md(target_ws: Path) -> None:
    assert (target_ws / "AGENTS.md").exists()


@then("the workspace has a CLAUDE.md file")
def _then_claude_md(target_ws: Path) -> None:
    assert (target_ws / "CLAUDE.md").exists()


@then("the workspace has a memory-sync skill file")
def _then_skill_file(target_ws: Path) -> None:
    assert (target_ws / ".agents" / "skills" / "memory-sync" / "SKILL.md").exists()


@then("the workspace has automated setup scripts")
def _then_setup_scripts(target_ws: Path) -> None:
    assert (target_ws / "scripts" / "setup-mempalace.ps1").exists()
    assert (target_ws / "scripts" / "setup-mempalace.sh").exists()


@then("the workspace has a kickoff prompt file")
def _then_kickoff_file(target_ws: Path) -> None:
    assert (target_ws / "MEMPALACE_KICKOFF.md").exists()


@then(parsers.parse('the kickoff prompt references "{needle}"'))
def _then_kickoff_references(target_ws: Path, needle: str) -> None:
    content = (target_ws / "MEMPALACE_KICKOFF.md").read_text(encoding="utf-8")
    assert needle in content


@then("the kickoff prompt file still exists")
def _then_kickoff_still_exists(target_ws: Path) -> None:
    assert (target_ws / "MEMPALACE_KICKOFF.md").exists()


# ── Upstream Version Update Notifier BDD Steps ─────────────────────────────


@pytest.fixture
def notifier_run() -> dict[str, Any]:
    """State holder for update notifier BDD scenario runs."""
    return {}


@given(parsers.parse('a workspace with cached version "{cached_version}" checked {hours:d} hour ago'))
def _given_cached_version(workspace: Path, cached_version: str, hours: int) -> None:
    cache = notifier.UpdateCache(workspace)
    cache.write(cached_version, timestamp=time.time() - (hours * 3600))


@given("a workspace with no cache or an expired cache")
@given("a workspace with an expired cache")
def _given_no_or_expired_cache(workspace: Path) -> None:
    cache_file = workspace / "MemPalace" / ".cache.json"
    if cache_file.exists():
        cache_file.unlink()


@given(parsers.parse('upstream GitHub reports latest release "{latest_version}"'))
def _given_upstream_release(monkeypatch: pytest.MonkeyPatch, latest_version: str) -> None:
    monkeypatch.setattr(
        notifier.GitHubVersionChecker,
        "fetch_latest_version",
        lambda self, current_version="0.2.1", timeout=1.5: latest_version,
    )


@given("upstream GitHub is unreachable or times out")
def _given_upstream_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        notifier.GitHubVersionChecker,
        "fetch_latest_version",
        lambda self, current_version="0.2.1", timeout=1.5: None,
    )


@given(parsers.parse('the environment variable "{var_name}" is set to "{val}"'))
def _given_env_var(monkeypatch: pytest.MonkeyPatch, var_name: str, val: str) -> None:
    monkeypatch.setenv(var_name, val)


@when("I run a mempalace CLI command")
def _when_run_cli_cmd(
    cli_runner: CliRunner, workspace: Path, notifier_run: dict[str, Any]
) -> None:
    result = cli_runner.invoke(app, ["list", "--agent", "--workspace", str(workspace)])
    notifier_run["result"] = result


@then(parsers.parse('stderr displays an update banner suggesting "{expected_version}"'))
def _then_stderr_banner(notifier_run: dict[str, Any], expected_version: str) -> None:
    res = notifier_run["result"]
    assert "mempalace update available" in res.stderr
    assert expected_version in res.stderr


@then("stdout remains clean and uncorrupted")
def _then_stdout_clean(notifier_run: dict[str, Any]) -> None:
    res = notifier_run["result"]
    data = json.loads(res.stdout)
    assert "essences" in data or "workspace" in data


@then(parsers.parse('"{cache_rel_path}" is updated with "{expected_version}"'))
def _then_cache_updated(workspace: Path, cache_rel_path: str, expected_version: str) -> None:
    cache_file = workspace / cache_rel_path
    assert cache_file.exists()
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    assert data["latest_version"] == expected_version.lstrip("v")


@then("the command succeeds with exit code 0")
def _then_cmd_succeeds(notifier_run: dict[str, Any]) -> None:
    res = notifier_run["result"]
    assert res.exit_code == 0


@then("no error or trace is shown to the user")
def _then_no_error(notifier_run: dict[str, Any]) -> None:
    res = notifier_run["result"]
    assert "Traceback" not in res.stdout
    assert "Traceback" not in res.stderr


@then("the check backs off without blocking the operation")
def _then_backs_off(notifier_run: dict[str, Any]) -> None:
    res = notifier_run["result"]
    assert res.exit_code == 0


@then("no update check or banner is emitted to stderr")
def _then_no_banner(notifier_run: dict[str, Any]) -> None:
    res = notifier_run["result"]
    assert "mempalace update available" not in res.stderr


# pyright: basic
"""BDD contract tests: Gherkin scenarios executed via pytest-bdd."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from mempalace import storage

_FEATURE = Path(__file__).with_name("features") / "mempalace.feature"
scenarios(str(_FEATURE))


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

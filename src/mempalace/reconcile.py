"""Consistency reporting between source files and the derived DB.

v2 removes the v1 dual-write flaw by construction (wisdom/decisions are file
derived), so post-ingest drift is zero; the report still surfaces the *historical*
v1 gap (essence files vs legacy DuckDB wisdom rows) as ``legacy_gap_files`` so the
migration evidence is not lost.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from mempalace.config import decisions_dir, essence_dir, legacy_duckdb_path
from mempalace.ingest import ADR_FILE_RE
from mempalace.models import DriftReport


def _count_or_none(legacy: Any, table: str) -> int | None:
    """Return COUNT(*) for a legacy table, tolerating missing/None rows."""
    row = legacy.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    if row is None:
        return None
    return int(row[0])


def _legacy_counts_and_gap(
    workspace: Path, essence_files: list[Path]
) -> tuple[int | None, int | None, int | None, list[str]]:
    """Read legacy DuckDB row counts and estimate files lacking a legacy row."""
    duckdb_path = legacy_duckdb_path(workspace)
    if not duckdb_path.exists():
        return None, None, None, []
    try:
        import duckdb

        with duckdb.connect(str(duckdb_path), read_only=True) as legacy:
            table_rows = legacy.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
            tables = {str(row[0]) for row in table_rows}
            wisdom_rows: int | None = None
            session_rows: int | None = None
            tool_rows: int | None = None
            if "wisdom" in tables:
                wisdom_rows = _count_or_none(legacy, "wisdom")
            if "sessions" in tables:
                session_rows = _count_or_none(legacy, "sessions")
            if "tool_registry" in tables:
                tool_rows = _count_or_none(legacy, "tool_registry")
            legacy_texts: list[str] = []
            if "wisdom" in tables:
                for row in legacy.execute("SELECT content, source_session FROM wisdom").fetchall():
                    legacy_texts.append(f"{row[0] or ''} {row[1] or ''}")
    except Exception:
        return None, None, None, []
    blob = " ".join(legacy_texts).lower()
    gap = [file_path.name for file_path in essence_files if file_path.stem.lower() not in blob]
    return wisdom_rows, session_rows, tool_rows, gap


def reconcile(conn: sqlite3.Connection, workspace: Path) -> DriftReport:
    """Compare essence/ADR files against DB rows and legacy DuckDB state."""
    essence_files = [
        file_path
        for file_path in sorted(essence_dir(workspace).glob("*.md"))
        if file_path.name.lower() != "template.md"
    ]
    file_stems = {file_path.stem for file_path in essence_files}

    wisdom_rows = conn.execute("SELECT slug, source_path FROM wisdom").fetchall()
    canonical_slugs = {
        str(row["slug"])
        for row in wisdom_rows
        if row["source_path"] is not None and str(row["source_path"]) != ""
    }
    files_without_row = [
        file_path.name for file_path in essence_files if file_path.stem not in canonical_slugs
    ]
    rows_without_file = [
        str(row["slug"])
        for row in wisdom_rows
        if row["source_path"] is None
        or str(row["source_path"]) == ""
        or str(row["slug"]) not in file_stems
    ]

    decision_files = [
        file_path
        for file_path in sorted(decisions_dir(workspace).glob("ADR-*.md"))
        if ADR_FILE_RE.match(file_path.name)
    ]
    decision_ids_on_disk: set[str] = set()
    for file_path in decision_files:
        match = ADR_FILE_RE.match(file_path.name)
        if match is not None:
            decision_ids_on_disk.add(match.group(1))
    decision_rows = conn.execute("SELECT id FROM decisions").fetchall()
    decision_ids_in_db = {str(row["id"]) for row in decision_rows}
    decision_files_without_row = sorted(decision_ids_on_disk - decision_ids_in_db)
    decision_rows_without_file = sorted(decision_ids_in_db - decision_ids_on_disk)

    session_count = int(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
    tool_count = int(conn.execute("SELECT COUNT(*) FROM tool_registry").fetchone()[0])

    legacy_wisdom, legacy_sessions, legacy_tools, legacy_gap = _legacy_counts_and_gap(
        workspace, essence_files
    )

    return DriftReport(
        essence_files=len(essence_files),
        wisdom_rows=len(wisdom_rows),
        files_without_row=sorted(files_without_row),
        rows_without_file=sorted(rows_without_file),
        decision_files=len(decision_files),
        decision_rows=len(decision_rows),
        decision_files_without_row=decision_files_without_row,
        decision_rows_without_file=decision_rows_without_file,
        session_count=session_count,
        tool_count=tool_count,
        legacy_wisdom_rows=legacy_wisdom,
        legacy_session_rows=legacy_sessions,
        legacy_tool_rows=legacy_tools,
        legacy_gap_files=legacy_gap,
    )

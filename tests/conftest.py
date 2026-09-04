"""Shared pytest fixtures for MemPalace v2 (standalone repo).

The package is imported through the uv editable install; no sys.path
manipulation is needed here.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mempalace import ingest, storage
from mempalace.cli import app

HERMES_ESSENCE = """# Hermes Agent Update File Locking (WinError 32)

**Category**: pitfall

Running `hermes update` on Windows fails because pip cannot replace the
executing hermes.exe (WinError 32, file locked by another process).
Fix: stop lingering electron/python workers, then update via
`python -m pip install -e .` in the agent venv.
"""

UV_ESSENCE = """# uv cache rename failure on Windows

**Category**: pitfall

`uv add yt-dlp` fails with os error 1 during a cache-file rename when the
default cache location is C:\\.uv_cache. Set UV_CACHE_DIR to a writable
workspace-local directory to fix.
"""

DUCKDB_ESSENCE = """# DuckDB CLI and Memory Rules

**Category**: preference

Use the native duckdb CLI for ad hoc DuckDB inspection instead of
python -c snippets; do not persist dynamic MCP servers.
"""

ADR_TEXT = """# ADR-001: Sample Decision

Date: 2026-09-01
Status: active
Tags: sample, test

## Context
Example decision used only by tests.
"""


@pytest.fixture
def cli_runner() -> CliRunner:
    """Return a Typer/Click CLI runner for in-process command tests."""
    return CliRunner()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Build a hermetic workspace: essences dir + ADR dir (no DuckDB)."""
    essence_path = tmp_path / "MemPalace" / "essences"
    essence_path.mkdir(parents=True)
    (essence_path / "2026-08-20-hermes-file-locking.md").write_text(
        HERMES_ESSENCE, encoding="utf-8"
    )
    (essence_path / "2026-07-17-uv-cache-rename.md").write_text(UV_ESSENCE, encoding="utf-8")
    (essence_path / "2026-04-17-duckdb-cli-rules.md").write_text(DUCKDB_ESSENCE, encoding="utf-8")
    decisions_path = tmp_path / "docs" / "decisions"
    decisions_path.mkdir(parents=True)
    (decisions_path / "ADR-001-sample.md").write_text(ADR_TEXT, encoding="utf-8")
    return tmp_path


@pytest.fixture
def db_path(workspace: Path, tmp_path: Path) -> Path:
    """Return the SQLite DB path inside the hermetic workspace."""
    return tmp_path / "memory.sqlite"


def ingest_workspace(workspace: Path, db_path: Path) -> None:
    """Run the ingest pipeline over a workspace into db_path."""
    conn = storage.connect(db_path)
    try:
        storage.init_db(conn)
        ingest.ingest_all(conn, workspace)
    finally:
        conn.close()


@pytest.fixture
def ingested(workspace: Path, db_path: Path) -> Path:
    """A workspace whose essence/ADR files have been ingested into the DB."""
    ingest_workspace(workspace, db_path)
    return db_path


@pytest.fixture
def app_cmd(
    cli_runner: CliRunner, db_path: Path, workspace: Path
) -> Callable[[list[str], dict[str, str] | None], Any]:
    """Factory running a CLI command list against the fixture DB/workspace."""

    def run(args: list[str], extra_env: dict[str, str] | None = None) -> Any:
        return cli_runner.invoke(
            app,
            [*args, "--db", str(db_path), "--workspace", str(workspace)],
            env=extra_env,
        )

    return run

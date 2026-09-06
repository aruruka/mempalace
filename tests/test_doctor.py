# pyright: basic
"""Unit and functional tests for the mempalace doctor diagnostic module."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mempalace.cli import app
from mempalace.doctor import DoctorReport, diagnose_environment
from mempalace.initializer import WorkspaceInitializerConfig, initialize_workspace


def test_diagnose_environment_clean_workspace(tmp_path: Path) -> None:
    report = diagnose_environment(tmp_path)
    assert isinstance(report, DoctorReport)
    assert report.python_ok is True
    assert report.sqlite_fts5_ok is True
    assert report.fastembed_ok is True
    assert report.db_exists is False
    assert report.docs_indexed == 0
    assert report.all_ok is False
    assert any("database not found" in issue.lower() for issue in report.issues)


def test_diagnose_environment_initialized_workspace(tmp_path: Path) -> None:
    cfg = WorkspaceInitializerConfig(workspace=tmp_path)
    initialize_workspace(cfg)

    report = diagnose_environment(tmp_path)
    assert report.python_ok is True
    assert report.db_exists is True
    assert report.docs_indexed >= 1
    assert report.essences_count >= 1
    assert report.all_ok is True
    assert len(report.issues) == 0


def test_cli_doctor_agent_json_output(tmp_path: Path, cli_runner: CliRunner) -> None:
    cfg = WorkspaceInitializerConfig(workspace=tmp_path)
    initialize_workspace(cfg)

    result = cli_runner.invoke(
        app,
        ["doctor", "--workspace", str(tmp_path), "--agent"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["python_ok"] is True
    assert data["db_exists"] is True
    assert data["all_ok"] is True


def test_cli_doctor_human_output(tmp_path: Path, cli_runner: CliRunner) -> None:
    cfg = WorkspaceInitializerConfig(workspace=tmp_path)
    initialize_workspace(cfg)

    result = cli_runner.invoke(
        app,
        ["doctor", "--workspace", str(tmp_path), "--human"],
    )
    assert result.exit_code == 0, result.output
    assert "MemPalace Environment Diagnostics" in result.output
    assert "Python Version" in result.output
    assert "SQLite FTS5" in result.output

"""Black-box CLI tests: real subprocess invocations of ``python -m mempalace``.

These mirror Go ``testscript`` semantics for Python: the packaged CLI runs as a
subprocess against a hermetic temp workspace; assertions cover stdout JSON,
exit codes, and stderr notes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERMES_SLUG = "2026-08-20-hermes-file-locking"


def _run(db_path: Path, workspace: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mempalace",
            *args,
            "--db",
            str(db_path),
            "--workspace",
            str(workspace),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
        timeout=120,
    )


def test_blackbox_ingest_and_search_roundtrip(workspace: Path, db_path: Path) -> None:
    result = _run(db_path, workspace, ["ingest"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["wisdom_upserted"] == 3
    assert payload["decision_upserted"] == 1

    search = _run(
        db_path, workspace, ["search", "file lock hermes update", "--mode", "bm25", "--limit", "3"]
    )
    assert search.returncode == 0, search.stderr
    data = json.loads(search.stdout)
    assert data["mode"] == "bm25"
    assert data["hits"]
    assert data["hits"][0]["source_ref"] == HERMES_SLUG


def test_blackbox_invalid_mode_exits_nonzero(workspace: Path, db_path: Path) -> None:
    _run(db_path, workspace, ["ingest"])
    result = _run(db_path, workspace, ["search", "anything", "--mode", "banana"])
    assert result.returncode != 0


def test_blackbox_search_multi_word_unquoted_args(workspace: Path, db_path: Path) -> None:
    _run(db_path, workspace, ["ingest"])
    # Multiple positional arguments passed without wrapping quotes:
    # `mempalace search file lock hermes --mode bm25`
    result = _run(
        db_path,
        workspace,
        ["search", "file", "lock", "hermes", "--mode", "bm25", "--limit", "3"],
    )
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    data = json.loads(result.stdout)
    assert len(data["hits"]) >= 1
    assert data["hits"][0]["source_ref"] == HERMES_SLUG


def test_blackbox_sync_then_find_session(workspace: Path, db_path: Path) -> None:
    _run(db_path, workspace, ["ingest"])
    sync = _run(
        db_path,
        workspace,
        [
            "sync",
            "--id",
            "demo-session-2026",
            "--summary",
            "probe cache token",
            "--tags",
            "demo,probe",
        ],
    )
    assert sync.returncode == 0, sync.stderr

    search = _run(
        db_path, workspace, ["search", "probe cache token", "--mode", "bm25", "--limit", "3"]
    )
    assert search.returncode == 0, search.stderr
    data = json.loads(search.stdout)
    refs = [hit["source_ref"] for hit in data["hits"]]
    assert "demo-session-2026" in refs


def test_blackbox_reconcile_reports_zero_drift(workspace: Path, db_path: Path) -> None:
    _run(db_path, workspace, ["ingest"])
    result = _run(db_path, workspace, ["reconcile"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["files_without_row"] == []
    assert payload["rows_without_file"] == []


def test_blackbox_init_workspace_subprocess(tmp_path: Path) -> None:
    target = tmp_path / "consumer"
    target.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "mempalace",
            "init-workspace",
            "--workspace",
            str(target),
            "--agent",
            "--agent-flavor",
            "antigravity",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["agent_flavor"] == "antigravity"
    assert payload["vectors_indexed"] >= 1
    assert (target / "MEMPALACE_KICKOFF.md").exists()


def test_blackbox_list_memories_agent(workspace: Path, db_path: Path) -> None:
    _run(db_path, workspace, ["ingest"])
    result = _run(db_path, workspace, ["list", "--agent"])
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "essences" in data
    assert "decisions" in data
    assert len(data["essences"]) >= 3
    assert len(data["decisions"]) >= 1
    assert any(e["slug"] == HERMES_SLUG for e in data["essences"])


def test_blackbox_list_memories_human(workspace: Path, db_path: Path) -> None:
    _run(db_path, workspace, ["ingest"])
    result = _run(db_path, workspace, ["list", "--human"])
    assert result.returncode == 0, result.stderr
    assert "MemPalace Memory Catalog" in result.stdout or "Essences" in result.stdout


def test_blackbox_update_notifier_stderr_banner(workspace: Path, db_path: Path) -> None:
    cache_file = workspace / "MemPalace" / ".cache.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps({"last_checked_at": time.time(), "latest_version": "9.9.9"}),
        encoding="utf-8",
    )
    result = _run(db_path, workspace, ["ingest"])
    assert result.returncode == 0, result.stderr
    assert "mempalace update available: v" in result.stderr
    assert "v9.9.9" in result.stderr
    data = json.loads(result.stdout)
    assert data["wisdom_upserted"] == 3


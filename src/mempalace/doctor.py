"""System and workspace health diagnostics for MemPalace v2.

Checks Python version, uv availability, SQLite FTS5 extension,
embedding support, and workspace database readiness.
"""

from __future__ import annotations

import importlib.util
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from mempalace import config, storage


def _empty_str_list() -> list[str]:
    """Return an empty list of strings for dataclass defaults."""
    return []


@dataclass
class DoctorReport:
    """Diagnostic health report for MemPalace runtime and workspace."""

    workspace: str
    python_version: str
    python_ok: bool
    uv_installed: bool
    uv_path: str | None
    sqlite_version: str
    sqlite_fts5_ok: bool
    fastembed_ok: bool
    db_path: str
    db_exists: bool
    docs_indexed: int = 0
    vectors_indexed: int = 0
    essences_count: int = 0
    decisions_count: int = 0
    all_ok: bool = True
    issues: list[str] = field(default_factory=_empty_str_list)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON output."""
        return asdict(self)


def check_sqlite_fts5() -> bool:
    """Verify that SQLite FTS5 virtual table extension is supported."""
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE _fts_check USING fts5(col);")
        conn.close()
        return True
    except Exception:
        return False


def check_fastembed() -> bool:
    """Verify that fastembed is importable."""
    return importlib.util.find_spec("fastembed") is not None


def diagnose_environment(workspace: Path | None = None) -> DoctorReport:
    """Run full diagnostic checks on the runtime environment and target workspace.

    Args:
        workspace: Path to the target workspace (default: current working directory).

    Returns:
        DoctorReport containing status of all checks.
    """
    ws = config.resolve_workspace(str(workspace) if workspace else None)
    issues: list[str] = []

    # 1. Python version check (>= 3.13)
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 13)
    if not py_ok:
        issues.append(f"Python version {py_ver} is unsupported. MemPalace requires >= 3.13.")

    # 2. uv tool availability
    uv_bin = shutil.which("uv")
    uv_ok = uv_bin is not None
    if not uv_ok:
        issues.append("`uv` was not found in PATH. Install uv from https://docs.astral.sh/uv/.")

    # 3. SQLite FTS5 check
    fts5_ok = check_sqlite_fts5()
    if not fts5_ok:
        issues.append("SQLite FTS5 extension is not available in the current Python SQLite build.")

    # 4. FastEmbed check
    fe_ok = check_fastembed()
    if not fe_ok:
        issues.append("`fastembed` package is not installed or importable.")

    # 5. Workspace DB & essences inspection
    db_file = config.resolve_db(ws, None)
    db_exists = db_file.exists()
    docs_indexed = 0
    vectors_indexed = 0

    if db_exists:
        try:
            conn = storage.connect(db_file)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM search_docs")
            row = cur.fetchone()
            docs_indexed = int(row[0]) if row else 0

            cur.execute("SELECT COUNT(*) FROM doc_vectors")
            vrow = cur.fetchone()
            vectors_indexed = int(vrow[0]) if vrow else 0
            conn.close()
        except Exception as exc:
            issues.append(f"Database at {db_file} could not be read: {exc}")
    else:
        issues.append(f"MemPalace database not found at {db_file}. Run 'mempalace init-workspace'.")

    # Essences count on disk
    essence_dir = config.essence_dir(ws)
    essences_count = 0
    if essence_dir.exists():
        essences_count = len(list(essence_dir.glob("*.md")))

    # Decisions count on disk
    dec_dir = config.decisions_dir(ws)
    decisions_count = 0
    if dec_dir.exists():
        decisions_count = len(list(dec_dir.glob("*.md")))

    all_ok = py_ok and fts5_ok and fe_ok and db_exists and len(issues) == 0

    return DoctorReport(
        workspace=str(ws),
        python_version=py_ver,
        python_ok=py_ok,
        uv_installed=uv_ok,
        uv_path=uv_bin,
        sqlite_version=sqlite3.sqlite_version,
        sqlite_fts5_ok=fts5_ok,
        fastembed_ok=fe_ok,
        db_path=str(db_file),
        db_exists=db_exists,
        docs_indexed=docs_indexed,
        vectors_indexed=vectors_indexed,
        essences_count=essences_count,
        decisions_count=decisions_count,
        all_ok=all_ok,
        issues=issues,
    )

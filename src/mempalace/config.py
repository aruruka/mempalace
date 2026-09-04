"""Path and runtime configuration for MemPalace v2."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
RRF_K = 60


def resolve_workspace(workspace_arg: str | None) -> Path:
    """Resolve the workspace root.

    Priority: CLI argument > ``MEM_PALACE_WORKSPACE`` env var > current working
    directory (the package may be installed anywhere, so a source-tree-derived
    default is not reliable - agents run from the workspace root).
    """
    if workspace_arg:
        return Path(workspace_arg).resolve()
    env_workspace = os.environ.get("MEM_PALACE_WORKSPACE")
    if env_workspace:
        return Path(env_workspace).resolve()
    return Path.cwd()


def resolve_db(workspace: Path, db_arg: str | None) -> Path:
    """Resolve the SQLite DB path.

    Priority: CLI argument > ``MEM_PALACE_DB`` env var > ``<workspace>/MemPalace/memory.sqlite``.
    """
    if db_arg:
        return Path(db_arg).resolve()
    env_db = os.environ.get("MEM_PALACE_DB")
    if env_db:
        return Path(env_db).resolve()
    return workspace / "MemPalace" / "memory.sqlite"


def essence_dir(workspace: Path) -> Path:
    """Return the essences directory for a workspace."""
    return workspace / "MemPalace" / "essences"


def decisions_dir(workspace: Path) -> Path:
    """Return the ADR decisions directory for a workspace."""
    return workspace / "docs" / "decisions"


def legacy_duckdb_path(workspace: Path) -> Path:
    """Return the legacy MemPalace DuckDB path for a workspace."""
    return workspace / "MemPalace" / "memory.duckdb"


def embed_cache_dir() -> Path:
    """Return the fastembed model cache directory (overridable via env var)."""
    env_cache = os.environ.get("MEM_PALACE_MODEL_CACHE")
    if env_cache:
        return Path(env_cache)
    return Path.home() / ".cache" / "fastembed"

"""Typer CLI for MemPalace v2.

Subcommands: init, ingest, sync, search, reconcile, embed, register-tools,
register-decisions. ``search`` emits JSON; the rest emit short summaries.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Annotated, Any, cast

import typer

from mempalace import config, retrieval, storage
from mempalace import ingest as ingest_mod
from mempalace import reconcile as reconcile_mod
from mempalace.embeddings import Embedder
from mempalace.models import tags_to_json

app = typer.Typer(
    help="MemPalace v2 — hybrid retrieval memory (SQLite + FTS5 + local embeddings).",
    no_args_is_help=True,
)


def _emit(payload: object) -> None:
    """Print a JSON payload to stdout (agents consume this)."""
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _open_db(db_arg: str | None, workspace_arg: str | None) -> tuple[Path, sqlite3.Connection]:
    """Resolve workspace/db and open a connection with the schema ensured."""
    workspace = config.resolve_workspace(workspace_arg)
    db_path = config.resolve_db(workspace, db_arg)
    conn = storage.connect(db_path)
    storage.init_db(conn)
    return db_path, conn


@app.command()
def init(
    db: Annotated[
        str | None,
        typer.Option(help="SQLite DB path (default: <workspace>/MemPalace/memory.sqlite)"),
    ] = None,
    workspace: Annotated[str | None, typer.Option(help="Workspace root")] = None,
) -> None:
    """Create the SQLite schema (idempotent)."""
    db_path, conn = _open_db(db, workspace)
    conn.close()
    typer.echo(f"Initialized MemPalace v2 database at {db_path}")


@app.command()
def ingest(
    workspace: Annotated[str | None, typer.Option(help="Workspace root")] = None,
    db: Annotated[str | None, typer.Option(help="SQLite DB path")] = None,
    no_migrate: Annotated[bool, typer.Option(help="Skip legacy DuckDB migration")] = False,
) -> None:
    """Ingest essences + ADR files; migrate sessions/tools from legacy DuckDB."""
    ws = config.resolve_workspace(workspace)
    _, conn = _open_db(db, workspace)
    try:
        report = ingest_mod.ingest_all(conn, ws, migrate=not no_migrate)
    finally:
        conn.close()
    _emit(report.to_dict())


@app.command()
def sync(
    session_id: Annotated[str, typer.Option("--id", help="Session identifier")],
    summary: Annotated[str, typer.Option(help="Session summary text")],
    tags: Annotated[str, typer.Option(help="Comma-separated tags")] = "",
    workspace: Annotated[str | None, typer.Option(help="Workspace root")] = None,
    db: Annotated[str | None, typer.Option(help="SQLite DB path")] = None,
) -> None:
    """Upsert a session record (AGENTS.md parity) and refresh the search index."""
    _, conn = _open_db(db, workspace)
    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
    try:
        conn.execute(
            "INSERT INTO sessions (session_id, summary, tags) VALUES (?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET "
            "summary = excluded.summary, tags = excluded.tags",
            (session_id, summary, tags_to_json(tag_list)),
        )
        conn.commit()
        indexed = storage.sync_search_index(conn)
    finally:
        conn.close()
    _emit({"session_id": session_id, "docs_indexed": indexed})


@app.command()
def search(
    keywords: Annotated[str, typer.Argument(help="Search terms (space-separated, AND semantics)")],
    mode: Annotated[
        str, typer.Option("--mode", help=f"One of: {', '.join(retrieval.VALID_MODES)}")
    ] = retrieval.MODE_HYBRID,
    limit: Annotated[int, typer.Option(help="Max results")] = 5,
    source: Annotated[
        str | None, typer.Option(help="Filter by source kind (wisdom/session/tool/decision)")
    ] = None,
    category: Annotated[
        str | None, typer.Option(help="Filter by category (pitfall/preference/thinking_style)")
    ] = None,
    model: Annotated[str, typer.Option(help="fastembed model name")] = config.DEFAULT_MODEL,
    no_embed: Annotated[bool, typer.Option(help="Never attempt embeddings (bm25 only)")] = False,
    workspace: Annotated[str | None, typer.Option(help="Workspace root")] = None,
    db: Annotated[str | None, typer.Option(help="SQLite DB path")] = None,
) -> None:
    """Ranked hybrid search over the memory store; emits JSON."""
    _, conn = _open_db(db, workspace)
    try:
        result = retrieval.search(
            conn,
            keywords,
            mode=mode,
            limit=limit,
            source_kind=source,
            category=category,
            embedder=None if no_embed else Embedder(model_name=model),
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    finally:
        conn.close()
    if result.note:
        typer.echo(f"# note: {result.note}", err=True)
    _emit(result.to_dict())


@app.command()
def reconcile(
    workspace: Annotated[str | None, typer.Option(help="Workspace root")] = None,
    db: Annotated[str | None, typer.Option(help="SQLite DB path")] = None,
) -> None:
    """Report drift between source files and the DB, plus the legacy v1 gap."""
    ws = config.resolve_workspace(workspace)
    _, conn = _open_db(db, workspace)
    try:
        report = reconcile_mod.reconcile(conn, ws)
    finally:
        conn.close()
    _emit(report.to_dict())


@app.command()
def embed(
    model: Annotated[str, typer.Option(help="fastembed model name")] = config.DEFAULT_MODEL,
    workspace: Annotated[str | None, typer.Option(help="Workspace root")] = None,
    db: Annotated[str | None, typer.Option(help="SQLite DB path")] = None,
) -> None:
    """Embed all search documents lacking vectors (local, offline after first run)."""
    _, conn = _open_db(db, workspace)
    try:
        added = retrieval.ensure_vectors(conn, Embedder(model_name=model))
    except Exception as exc:
        conn.close()
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    conn.close()
    _emit({"model": model, "vectors_added": added})


@app.command()
def register_tools(
    workspace: Annotated[str | None, typer.Option(help="Workspace root")] = None,
    db: Annotated[str | None, typer.Option(help="SQLite DB path")] = None,
) -> None:
    """Discover workspace scripts/tools and insert any not already registered."""
    ws = config.resolve_workspace(workspace)
    _, conn = _open_db(db, workspace)
    found = ingest_mod.scan_workspace_tools(ws)
    existing = {str(row[0]) for row in conn.execute("SELECT name FROM tool_registry").fetchall()}
    added = 0
    try:
        for name, path, description in found:
            if name in existing:
                continue
            conn.execute(
                "INSERT INTO tool_registry (name, path, description) VALUES (?, ?, ?)",
                (name, path, description),
            )
            added += 1
        conn.commit()
        indexed = storage.sync_search_index(conn)
    finally:
        conn.close()
    _emit({"discovered": len(found), "inserted": added, "docs_indexed": indexed})


@app.command()
def register_decisions(
    workspace: Annotated[str | None, typer.Option(help="Workspace root")] = None,
    db: Annotated[str | None, typer.Option(help="SQLite DB path")] = None,
) -> None:
    """Upsert decision rows from ADR files and refresh the search index."""
    ws = config.resolve_workspace(workspace)
    _, conn = _open_db(db, workspace)
    try:
        count = ingest_mod.ingest_decisions(conn, config.decisions_dir(ws))
        indexed = storage.sync_search_index(conn)
    finally:
        conn.close()
    _emit({"decisions_upserted": count, "docs_indexed": indexed})


def _force_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 (Windows consoles default to cp932/cp1252)."""
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            cast(Any, stream).reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main() -> None:
    """Console-script entry point."""
    _force_utf8_stdio()
    app()

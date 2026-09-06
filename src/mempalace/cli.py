"""Typer CLI for MemPalace v2.

Subcommands: init, init-workspace, setup, ingest, sync, search, reconcile,
embed, register-tools, register-decisions. ``search`` and ``init-workspace --agent``
emit JSON; the rest emit short summaries.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Annotated, Any, cast

import typer

from mempalace import config, retrieval, storage
from mempalace import doctor as doctor_mod
from mempalace import ingest as ingest_mod
from mempalace import initializer as initializer_mod
from mempalace import reconcile as reconcile_mod
from mempalace.embeddings import Embedder
from mempalace.initializer import WorkspaceInitializerConfig, parse_agent_flavor
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


def _run_init_workspace(
    workspace: str | None,
    agent: str,
    seed: bool,
    skills: bool,
    decisions: bool,
    scripts: bool,
    kickoff_file: str,
    interactive: bool | None,
    agent_mode: bool,
    human: bool,
    dry_run: bool,
) -> None:
    """Core dispatcher for workspace initialization (shared by init-workspace and setup)."""
    if agent_mode:
        is_interactive = False
    elif human:
        is_interactive = True
    elif interactive is not None:
        is_interactive = interactive
    else:
        is_interactive = sys.stdin.isatty() and not agent_mode

    if is_interactive:
        typer.secho("\n🏰 MemPalace v2 — Workspace Initializer\n", fg=typer.colors.CYAN, bold=True)
        default_ws = str(config.resolve_workspace(workspace))
        chosen_ws = typer.prompt("Target workspace path", default=default_ws)
        ws_path = Path(chosen_ws).resolve()

        if not agent:
            typer.echo("\nSelect your target coding agent:")
            typer.echo("  1. Antigravity / Gemini CLI")
            typer.echo("  2. OpenCode")
            typer.echo("  3. Hermes")
            typer.echo("  4. Claude Code")
            typer.echo("  5. Cursor")
            typer.echo("  6. Generic / Universal")
            choice = typer.prompt("Choose an agent", default="1")
            choice_map = {
                "1": "antigravity",
                "2": "opencode",
                "3": "hermes",
                "4": "claude",
                "5": "cursor",
                "6": "generic",
            }
            agent_str = choice_map.get(choice.strip(), choice.strip())
        else:
            agent_str = agent

        try:
            flavor = parse_agent_flavor(agent_str)
        except ValueError as exc:
            typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2) from exc

        seed_choice = typer.confirm("Seed a starter essence file?", default=seed)
        skills_choice = typer.confirm("Install memory-sync skill for agent?", default=skills)
        decisions_choice = typer.confirm("Scaffold docs/decisions for ADRs?", default=decisions)
        scripts_choice = typer.confirm("Generate setup-mempalace scripts?", default=scripts)

        cfg = WorkspaceInitializerConfig(
            workspace=ws_path,
            agent_flavor=flavor,
            seed_essences=seed_choice,
            install_skills=skills_choice,
            setup_decisions=decisions_choice,
            setup_scripts=scripts_choice,
            kickoff_file=kickoff_file,
            dry_run=dry_run,
        )
        report = initializer_mod.initialize_workspace(cfg)

        typer.secho("\n✨ Workspace initialized successfully!", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"  Workspace: {report.workspace}")
        typer.echo(f"  Agent:     {report.agent_flavor}")
        if report.created_paths:
            typer.echo("  Created:")
            for p in report.created_paths:
                typer.echo(f"    + {p}")
        if report.existing_paths:
            typer.echo("  Existing (preserved):")
            for p in report.existing_paths:
                typer.echo(f"    = {p}")
        typer.echo(f"  Database:  Initialized ({report.docs_indexed} docs indexed)")
        if report.kickoff_prompt_path:
            typer.echo(f"  Kickoff:   Saved to {report.kickoff_prompt_path}")

        border = "=" * 80
        typer.secho(f"\n{border}", fg=typer.colors.YELLOW)
        typer.secho("📋 MEMPALACE KICK-OFF PROMPT", fg=typer.colors.YELLOW, bold=True)
        typer.secho(
            "Copy & paste this prompt into your coding agent to activate memory:",
            fg=typer.colors.WHITE,
        )
        typer.secho(border, fg=typer.colors.YELLOW)
        typer.echo(report.kickoff_prompt_content)
        typer.secho(border, fg=typer.colors.YELLOW)
    else:
        ws_path = config.resolve_workspace(workspace)
        try:
            flavor = parse_agent_flavor(agent)
        except ValueError as exc:
            typer.echo(
                json.dumps({"error": True, "code": "INVALID_AGENT", "message": str(exc)}),
                err=True,
            )
            raise typer.Exit(code=2) from exc

        cfg = WorkspaceInitializerConfig(
            workspace=ws_path,
            agent_flavor=flavor,
            seed_essences=seed,
            install_skills=skills,
            setup_decisions=decisions,
            setup_scripts=scripts,
            kickoff_file=kickoff_file,
            dry_run=dry_run,
        )
        report = initializer_mod.initialize_workspace(cfg)
        _emit(report.to_dict())


@app.command(name="init-workspace")
def init_workspace(
    workspace: Annotated[
        str | None,
        typer.Option(help="Target workspace root (default: current directory)"),
    ] = None,
    agent: Annotated[
        str,
        typer.Option(
            "--agent-flavor",
            "-a",
            help="Target agent: opencode, hermes, antigravity, claude, cursor, generic",
        ),
    ] = "",
    seed: Annotated[bool, typer.Option(help="Seed starter essence file")] = True,
    skills: Annotated[bool, typer.Option(help="Install memory-sync skill")] = True,
    decisions: Annotated[bool, typer.Option(help="Scaffold docs/decisions")] = True,
    scripts: Annotated[bool, typer.Option(help="Generate setup-mempalace scripts")] = True,
    kickoff_file: Annotated[
        str, typer.Option(help="File path to save kickoff prompt")
    ] = "MEMPALACE_KICKOFF.md",
    interactive: Annotated[
        bool | None, typer.Option(help="Force interactive or non-interactive mode")
    ] = None,
    agent_mode: Annotated[
        bool, typer.Option("--agent", help="Emit JSON output for AI agents (ai-native-cli)")
    ] = False,
    human: Annotated[
        bool, typer.Option("--human", help="Force human-friendly interactive output")
    ] = False,
    dry_run: Annotated[bool, typer.Option(help="Preview actions without writing to disk")] = False,
) -> None:
    """Interactive & AI-native wizard to initialize a workspace for MemPalace."""
    _run_init_workspace(
        workspace=workspace,
        agent=agent,
        seed=seed,
        skills=skills,
        decisions=decisions,
        scripts=scripts,
        kickoff_file=kickoff_file,
        interactive=interactive,
        agent_mode=agent_mode,
        human=human,
        dry_run=dry_run,
    )


@app.command(name="setup")
def setup(
    workspace: Annotated[
        str | None,
        typer.Option(help="Target workspace root (default: current directory)"),
    ] = None,
    agent: Annotated[
        str,
        typer.Option(
            "--agent-flavor",
            "-a",
            help="Target agent: opencode, hermes, antigravity, claude, cursor, generic",
        ),
    ] = "",
    seed: Annotated[bool, typer.Option(help="Seed starter essence file")] = True,
    skills: Annotated[bool, typer.Option(help="Install memory-sync skill")] = True,
    decisions: Annotated[bool, typer.Option(help="Scaffold docs/decisions")] = True,
    scripts: Annotated[bool, typer.Option(help="Generate setup-mempalace scripts")] = True,
    kickoff_file: Annotated[
        str, typer.Option(help="File path to save kickoff prompt")
    ] = "MEMPALACE_KICKOFF.md",
    interactive: Annotated[
        bool | None, typer.Option(help="Force interactive or non-interactive mode")
    ] = None,
    agent_mode: Annotated[
        bool, typer.Option("--agent", help="Emit JSON output for AI agents (ai-native-cli)")
    ] = False,
    human: Annotated[
        bool, typer.Option("--human", help="Force human-friendly interactive output")
    ] = False,
    dry_run: Annotated[bool, typer.Option(help="Preview actions without writing to disk")] = False,
) -> None:
    """Alias for init-workspace."""
    _run_init_workspace(
        workspace=workspace,
        agent=agent,
        seed=seed,
        skills=skills,
        decisions=decisions,
        scripts=scripts,
        kickoff_file=kickoff_file,
        interactive=interactive,
        agent_mode=agent_mode,
        human=human,
        dry_run=dry_run,
    )


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


@app.command()
def doctor(
    workspace: Annotated[
        str | None,
        typer.Option(help="Target workspace root (default: current directory)"),
    ] = None,
    agent: Annotated[
        bool,
        typer.Option(help="Emit JSON output for AI agents (ai-native-cli)"),
    ] = False,
    human: Annotated[
        bool,
        typer.Option(help="Force human-friendly checklist output"),
    ] = False,
) -> None:
    """Run environment and workspace health diagnostics."""
    ws = config.resolve_workspace(workspace)
    report = doctor_mod.diagnose_environment(ws)
    emit_json = agent or (not human and not sys.stdin.isatty())
    if emit_json:
        _emit(report.to_dict())
        if not report.all_ok:
            raise typer.Exit(code=1)
        return

    typer.secho("\n🩺 MemPalace Environment Diagnostics\n", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  Workspace:       {report.workspace}")

    py_icon = "✅" if report.python_ok else "❌"
    typer.echo(f"  {py_icon} Python Version:  {report.python_version} (required >= 3.13)")

    uv_icon = "✅" if report.uv_installed else "❌"
    uv_desc = report.uv_path if report.uv_installed else "Not found in PATH"
    typer.echo(f"  {uv_icon} uv Tool:        {uv_desc}")

    fts5_icon = "✅" if report.sqlite_fts5_ok else "❌"
    typer.echo(
        f"  {fts5_icon} SQLite FTS5:     v{report.sqlite_version} "
        f"(FTS5 enabled: {report.sqlite_fts5_ok})"
    )

    fe_icon = "✅" if report.fastembed_ok else "❌"
    typer.echo(f"  {fe_icon} FastEmbed:       {'Available' if report.fastembed_ok else 'Missing'}")

    db_icon = "✅" if report.db_exists else "❌"
    status_label = "Found" if report.db_exists else "Missing"
    typer.echo(f"  {db_icon} Database:        {report.db_path} ({status_label})")
    if report.db_exists:
        doc_stats = (
            f"Indexed Docs:  {report.docs_indexed} "
            f"(Essences: {report.essences_count}, ADRs: {report.decisions_count})"
        )
        typer.echo(f"     {doc_stats}")
        typer.echo(f"     Dense Vectors: {report.vectors_indexed}")

    if report.issues:
        typer.secho("\n⚠️  Issues Detected:", fg=typer.colors.YELLOW, bold=True)
        for issue in report.issues:
            typer.secho(f"  - {issue}", fg=typer.colors.RED)
        typer.secho("\n💡 Quick Fix:", fg=typer.colors.YELLOW)
        typer.echo("  Run setup script or 'mempalace init-workspace' to configure the workspace.\n")
        raise typer.Exit(code=1)
    else:
        typer.secho(
            "\n✨ All environment and workspace checks passed!\n", fg=typer.colors.GREEN, bold=True
        )


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

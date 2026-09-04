"""Ingestion: essence files + ADR files -> SQLite; legacy DuckDB migration.

Design principle (fixes the v1 dual-write flaw): **files are the single source of
truth** for wisdom and decisions. The DB is a derived, rebuildable index. Sessions
and the tool registry have no file representation and are migrated once from the
legacy DuckDB store (only when the sessions table is empty).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from mempalace.config import decisions_dir, essence_dir, legacy_duckdb_path
from mempalace.models import CATEGORY_VALUES, Essence, IngestReport
from mempalace.storage import sync_search_index

ADR_FILE_RE = re.compile(r"^(ADR-\d{3})-(.+)\.md$")
_CATEGORY_LINE_RE = re.compile(
    r"(?im)^\s*\*{0,2}category\*{0,2}\s*[:：]\s*([a-zA-Z_ -]+)\s*$"  # noqa: RUF001 - fullwidth colon intentional (CN essence text)
)

_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def _now() -> str:
    """Return the current UTC timestamp as an ISO-like string."""
    return datetime.now(UTC).strftime(_TS_FORMAT)


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split YAML-ish frontmatter (when present) from the body.

    Returns ``(metadata, body)``; metadata keys are lowercased.
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    if len(lines) < 3:
        return {}, text
    end = next((i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if end is None:
        return {}, text
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip()
    return meta, "\n".join(lines[end + 1 :])


def _detect_category(text: str, meta: dict[str, str]) -> str | None:
    """Infer a wisdom category from frontmatter, explicit markers, or sections."""
    candidate = (meta.get("category") or meta.get("type") or "").strip().lower()
    if candidate in CATEGORY_VALUES:
        return candidate
    line_match = _CATEGORY_LINE_RE.search(text)
    if line_match:
        candidate = line_match.group(1).strip().lower().replace(" ", "_")
        if candidate in CATEGORY_VALUES:
            return candidate
    if "## Pitfall" in text and "## Preference" not in text:
        return "pitfall"
    if "## Preference" in text and "## Pitfall" not in text:
        return "preference"
    return None


def parse_essence(path: Path) -> Essence:
    """Parse one essence Markdown file into an :class:`Essence`."""
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, _ = _split_frontmatter(text)
    slug = path.stem
    category = _detect_category(text, meta)
    return Essence(slug=slug, path=path, category=category, content=text)


def ingest_wisdom(conn: sqlite3.Connection, essences_path: Path) -> int:
    """Full-sync wisdom rows from essence files; returns the file count."""
    if not essences_path.exists():
        return 0
    files = [f for f in sorted(essences_path.glob("*.md")) if f.name.lower() != "template.md"]
    current_paths = {str(f.resolve()) for f in files}

    rows = conn.execute("SELECT id, source_path FROM wisdom").fetchall()
    for row in rows:
        source_path = row["source_path"]
        if source_path is not None and str(source_path) not in current_paths:
            conn.execute("DELETE FROM wisdom WHERE id = ?", (row["id"],))

    now = _now()
    for file_path in files:
        essence = parse_essence(file_path)
        conn.execute(
            """
            INSERT INTO wisdom (slug, category, content, timestamp, source_path, source_session)
            VALUES (?, ?, ?, ?, ?, NULL)
            ON CONFLICT(slug) DO UPDATE SET
                category = excluded.category,
                content = excluded.content,
                timestamp = excluded.timestamp,
                source_path = excluded.source_path
            """,
            (essence.slug, essence.category, essence.content, now, str(file_path.resolve())),
        )
    conn.commit()
    return len(files)


def _extract_title(lines: list[str], fallback: str) -> str:
    """Extract the ADR title from its heading line."""
    for line in lines:
        if line.startswith("# "):
            header = line[2:].strip()
            if ":" in header:
                return header.split(":", 1)[1].strip()
            return header
    return fallback.replace("-", " ").title()


def _extract_metadata(lines: list[str]) -> tuple[str | None, str, list[str]]:
    """Extract date/status/tags from ADR header lines."""
    decision_date: str | None = None
    status = "active"
    tags: list[str] = []
    for raw in lines:
        line = raw.strip()
        lowered = line.lower()
        if lowered.startswith("date:"):
            value = line.split(":", 1)[1].strip()
            decision_date = value or None
        elif lowered.startswith("status:"):
            value = line.split(":", 1)[1].strip().lower()
            if value:
                status = value
        elif lowered.startswith("tags:"):
            value = line.split(":", 1)[1].strip()
            tags = [tag.strip() for tag in value.split(",") if tag.strip()]
    return decision_date, status, tags


def ingest_decisions(conn: sqlite3.Connection, decisions_path: Path) -> int:
    """Upsert decision rows from ADR files; returns the file count."""
    if not decisions_path.exists():
        return 0
    entries: list[tuple[str, str, str, str, str | None, str]] = []
    for file_path in sorted(decisions_path.glob("ADR-*.md")):
        match = ADR_FILE_RE.match(file_path.name)
        if not match:
            continue
        decision_id = match.group(1)
        slug = match.group(2)
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        title = _extract_title(lines, slug)
        decision_date, status, tags = _extract_metadata(lines)
        from mempalace.models import tags_to_json

        entries.append(
            (
                decision_id,
                title,
                str(file_path.resolve()),
                status,
                decision_date,
                tags_to_json(tags),
            )
        )
    for entry in entries:
        conn.execute(
            """
            INSERT INTO decisions (id, title, path, status, date, tags)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                path = excluded.path,
                status = excluded.status,
                date = excluded.date,
                tags = excluded.tags
            """,
            entry,
        )
    conn.commit()
    return len(entries)


def migrate_sessions_tools(conn: sqlite3.Connection, duckdb_path: Path) -> tuple[int, int]:
    """Migrate sessions + tool_registry from the legacy DuckDB store (idempotent).

    Returns ``(session_count, tool_count)`` migrated. Skipped when the DuckDB
    file is absent. Requires the ``duckdb`` package (a project dependency).
    """
    if not duckdb_path.exists():
        return 0, 0
    import duckdb

    session_count = 0
    tool_count = 0
    with duckdb.connect(str(duckdb_path), read_only=True) as legacy:
        table_rows = legacy.execute("SELECT table_name FROM information_schema.tables").fetchall()
        names = {str(row[0]) for row in table_rows}

        if "sessions" in names:
            rows = legacy.execute(
                "SELECT session_id, CAST(timestamp AS VARCHAR), summary, CAST(tags AS VARCHAR) "
                "FROM sessions"
            ).fetchall()
            for session_id, timestamp, summary, tags in rows:
                tags_text = str(tags) if tags is not None else None
                conn.execute(
                    "INSERT OR REPLACE INTO sessions (session_id, timestamp, summary, tags) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        str(session_id),
                        str(timestamp) if timestamp is not None else None,
                        summary,
                        tags_text,
                    ),
                )
                session_count += 1

        if "tool_registry" in names:
            rows = legacy.execute("SELECT name, path, description FROM tool_registry").fetchall()
            for name, path, description in rows:
                conn.execute(
                    "INSERT INTO tool_registry (name, path, description) VALUES (?, ?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET path = excluded.path, "
                    "description = excluded.description",
                    (str(name), path, description),
                )
                tool_count += 1
    conn.commit()
    return session_count, tool_count


def ingest_all(conn: sqlite3.Connection, workspace: Path, migrate: bool = True) -> IngestReport:
    """Run the full ingest pipeline over a workspace.

    Steps: wisdom from essences, decisions from ADR files, one-time session/tool
    migration from the legacy DuckDB, then a diff-based search-index resync.
    """
    wisdom_count = ingest_wisdom(conn, essence_dir(workspace))
    decision_count = ingest_decisions(conn, decisions_dir(workspace))

    session_count = 0
    tool_count = 0
    duckdb_path = legacy_duckdb_path(workspace)
    if migrate and duckdb_path.exists():
        existing_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
        if existing_sessions is not None and int(existing_sessions[0]) == 0:
            session_count, tool_count = migrate_sessions_tools(conn, duckdb_path)

    indexed = sync_search_index(conn)
    return IngestReport(
        wisdom_upserted=wisdom_count,
        decision_upserted=decision_count,
        sessions_migrated=session_count,
        tools_upserted=tool_count,
        docs_indexed=indexed,
    )


def _docstring_first_line(text: str) -> str:
    """Return the first non-empty line of a module docstring, if any."""
    match = re.search(r"(?s)^(?:'''|\"\"\")(.*?)(?:'''|\"\"\")", text)
    if match is None:
        return ""
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:200]
    return ""


def scan_workspace_tools(workspace: Path) -> list[tuple[str, str, str]]:
    """Data-driven discovery of workspace Python tools (fixes F3 hardcoding).

    Returns sorted ``(name, workspace-relative path, description)`` tuples for
    ``scripts/*.py`` and ``tools/*/*.py``; descriptions come from the first line
    of each module docstring. Registration is insert-only so migrated v1
    descriptions are never clobbered.
    """
    candidates: list[Path] = []
    scripts_dir = workspace / "scripts"
    tools_dir = workspace / "tools"
    if scripts_dir.exists():
        candidates.extend(sorted(scripts_dir.glob("*.py")))
    if tools_dir.exists():
        for sub in sorted(tools_dir.iterdir()):
            if sub.is_dir():
                candidates.extend(sorted(sub.glob("*.py")))

    seen: set[str] = set()
    result: list[tuple[str, str, str]] = []
    for file_path in candidates:
        name = file_path.stem
        if name in seen:
            continue
        seen.add(name)
        relative = str(file_path.relative_to(workspace)).replace("\\", "/")
        try:
            description = _docstring_first_line(
                file_path.read_text(encoding="utf-8", errors="replace")
            )
        except OSError:
            description = ""
        result.append((name, relative, description))
    return result

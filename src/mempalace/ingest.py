"""Ingestion: essence files + ADR files + sessions.jsonl + tools -> SQLite.

Design principle (fixes the v1 dual-write flaw): **files are the single source of
truth** for wisdom, decisions, sessions (``MemPalace/sessions.jsonl``), and tools
(``scripts/`` and ``tools/``). The DB is a derived, rebuildable index.
"""

from __future__ import annotations

import json
import re
import sqlite3
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from mempalace import storage
from mempalace.config import (
    decisions_dir,
    essence_dir,
    legacy_duckdb_path,
    sessions_jsonl_path,
)
from mempalace.models import (
    CATEGORY_VALUES,
    VALID_STATUSES,
    Essence,
    IngestReport,
    coerce_tags,
    tags_to_json,
)
from mempalace.storage import sync_search_index

ADR_FILE_RE = re.compile(r"^(ADR-\d{3})-(.+)\.md$")
_CATEGORY_LINE_RE = re.compile(
    r"(?im)^\s*\*{0,2}category\*{0,2}\s*[:：]\s*([a-zA-Z_ -]+)\s*$"  # noqa: RUF001 - fullwidth colon intentional (CN essence text)
)
_STATUS_LINE_RE = re.compile(
    r"(?im)^\s*\*{0,2}status\*{0,2}\s*[:：]\s*([a-zA-Z_-]+)\s*$"  # noqa: RUF001
)
_PEP723_RE = re.compile(
    r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)\s*\n(?P<content>(?:^#(?: .*)?\n)+)^# ///$"
)
_PS_SYNOPSIS_RE = re.compile(
    r"(?is)<#.*?\.SYNOPSIS\s*\r?\n(?P<synopsis>.*?)(?=\r?\n\s*\.[A-Z]+|\r?\n\s*#>)"
)
_SH_DESC_RE = re.compile(r"(?im)^#\s*@description:\s*(.+)$")

_SCRIPT_EXTS = (".py", ".ps1", ".sh", ".bash")
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def _now() -> str:
    """Return the current UTC timestamp as an ISO-like string."""
    return datetime.now(UTC).strftime(_TS_FORMAT)


def _strip_quotes(val: str) -> str:
    """Strip surrounding single or double quotes from a scalar string."""
    v = val.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        return v[1:-1].strip()
    return v


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
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = _strip_quotes(value)
    return meta, "\n".join(lines[end + 1 :])


def _detect_category(text: str, meta: dict[str, str]) -> str | None:
    """Infer a wisdom category from frontmatter, explicit markers, or sections."""
    candidate = _strip_quotes(meta.get("category") or meta.get("type") or "").lower()
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


def _detect_status(text: str, meta: dict[str, str]) -> str:
    """Infer document lifecycle status from frontmatter or body headers."""
    candidate = _strip_quotes(meta.get("status") or "").lower()
    if candidate in VALID_STATUSES:
        return candidate
    line_match = _STATUS_LINE_RE.search(text)
    if line_match:
        candidate = line_match.group(1).strip().lower()
        if candidate in VALID_STATUSES:
            return candidate
    return "active"


def parse_essence(path: Path) -> Essence:
    """Parse one essence Markdown file into an :class:`Essence`."""
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, _ = _split_frontmatter(text)
    slug = path.stem
    category = _detect_category(text, meta)
    status = _detect_status(text, meta)
    return Essence(slug=slug, path=path, category=category, content=text, status=status)


def ingest_wisdom(conn: sqlite3.Connection, essences_path: Path) -> int:
    """Full-sync wisdom rows from essence files; returns the file count."""
    storage.ensure_status_columns(conn)
    if not essences_path.exists():
        return 0
    files = [
        f
        for f in sorted(essences_path.glob("*.md"))
        if f.name.lower() not in ("template.md", "readme.md")
    ]
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
            INSERT INTO wisdom (
                slug, category, content, timestamp, source_path, source_session, status
            )
            VALUES (?, ?, ?, ?, ?, NULL, ?)
            ON CONFLICT(slug) DO UPDATE SET
                category = excluded.category,
                content = excluded.content,
                timestamp = excluded.timestamp,
                source_path = excluded.source_path,
                status = excluded.status
            """,
            (
                essence.slug,
                essence.category,
                essence.content,
                now,
                str(file_path.resolve()),
                essence.status,
            ),
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
    """Extract date/status/tags from ADR frontmatter or header lines."""
    decision_date: str | None = None
    status = "active"
    tags: list[str] = []
    in_tags_list = False
    for raw in lines:
        line = raw.strip()
        lowered = line.lower()
        if in_tags_list:
            if line.startswith("- "):
                item = _strip_quotes(line[2:].strip())
                if item and item not in tags:
                    tags.append(item)
                continue
            in_tags_list = False
        if lowered.startswith("date:"):
            value = _strip_quotes(line.split(":", 1)[1].strip())
            decision_date = value or None
        elif lowered.startswith("status:"):
            value = _strip_quotes(line.split(":", 1)[1].strip()).lower()
            if value:
                status = value
        elif lowered.startswith("tags:"):
            value = line.split(":", 1)[1].strip()
            if not value:
                in_tags_list = True
            else:
                cleaned = value.strip("[]")
                parsed = [_strip_quotes(tag.strip()) for tag in cleaned.split(",") if tag.strip()]
                for t in parsed:
                    if t and t not in tags:
                        tags.append(t)
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


def append_or_update_session_jsonl(
    workspace: Path,
    session_id: str,
    timestamp: str,
    summary: str,
    tags: list[str],
    status: str = "active",
) -> None:
    """Persist a session record to ``MemPalace/sessions.jsonl`` (idempotent upsert)."""
    jsonl_file = sessions_jsonl_path(workspace)
    jsonl_file.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    found = False
    if jsonl_file.exists():
        for raw_line in jsonl_file.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                loaded = json.loads(stripped)
            except ValueError:
                continue
            if isinstance(loaded, dict):
                item = cast(dict[str, object], loaded)
                if str(item.get("session_id", "")) == session_id:
                    item["timestamp"] = timestamp
                    item["summary"] = summary
                    item["tags"] = tags
                    item["status"] = status
                    found = True
                records.append(item)
    if not found:
        records.append(
            {
                "session_id": session_id,
                "timestamp": timestamp,
                "summary": summary,
                "tags": tags,
                "status": status,
            }
        )
    content = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
    jsonl_file.write_text(content, encoding="utf-8")


def ingest_sessions_jsonl(conn: sqlite3.Connection, jsonl_path: Path) -> int:
    """Upsert session rows from ``MemPalace/sessions.jsonl``; returns count upserted."""
    storage.ensure_status_columns(conn)
    if not jsonl_path.exists():
        return 0
    count = 0
    now = _now()
    for raw_line in jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            loaded = json.loads(stripped)
        except ValueError:
            continue
        if not isinstance(loaded, dict):
            continue
        item = cast(dict[str, object], loaded)
        session_id = str(item.get("session_id") or "").strip()
        if not session_id:
            continue
        timestamp = str(item.get("timestamp") or now).strip() or now
        summary = str(item.get("summary") or "").strip()
        tags_list = coerce_tags(item.get("tags"))
        status = str(item.get("status") or "active").strip().lower() or "active"
        conn.execute(
            """
            INSERT INTO sessions (session_id, timestamp, summary, tags, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                timestamp = excluded.timestamp,
                summary = excluded.summary,
                tags = excluded.tags,
                status = excluded.status
            """,
            (session_id, timestamp, summary, tags_to_json(tags_list), status),
        )
        count += 1
    conn.commit()
    return count


def migrate_sessions_tools(conn: sqlite3.Connection, duckdb_path: Path) -> tuple[int, int]:
    """Migrate sessions + tool_registry from the legacy DuckDB store (idempotent).

    Returns ``(session_count, tool_count)`` migrated. Skipped when the DuckDB
    file is absent. Requires the ``duckdb`` package (a project dependency).
    """
    if not duckdb_path.exists():
        return 0, 0
    import duckdb

    storage.ensure_status_columns(conn)
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
                    "INSERT OR REPLACE INTO sessions "
                    "(session_id, timestamp, summary, tags, status) "
                    "VALUES (?, ?, ?, ?, 'active')",
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
                    "INSERT INTO tool_registry (name, path, description, status) "
                    "VALUES (?, ?, ?, 'active') "
                    "ON CONFLICT(name) DO UPDATE SET path = excluded.path, "
                    "description = excluded.description",
                    (str(name), path, description),
                )
                tool_count += 1
    conn.commit()
    return session_count, tool_count


def _docstring_first_line(text: str) -> str:
    """Return the first non-empty line of a module docstring, if any."""
    match = re.search(r"(?s)^\s*(?:#[^\n]*\n\s*)*(?:'''|\"\"\")(.*?)(?:'''|\"\"\")", text)
    if match is None:
        return ""
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:200]
    return ""


def _extract_tool_description(file_path: Path) -> str:
    """Extract a concise description from a Python, PowerShell, Shell, or Markdown file."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    ext = file_path.suffix.lower()

    if ext == ".py":
        pep_match = _PEP723_RE.search(text)
        if pep_match and pep_match.group("type") == "script":
            raw_toml = "\n".join(
                line[2:] if line.startswith("# ") else line[1:]
                for line in pep_match.group("content").splitlines()
            )
            try:
                parsed_toml = tomllib.loads(raw_toml)
                tool_sec = cast(dict[str, object], parsed_toml.get("tool") or {})
                mp_sec = cast(dict[str, object], tool_sec.get("mempalace") or {})
                desc = str(
                    mp_sec.get("description") or parsed_toml.get("description") or ""
                ).strip()
                if desc:
                    return desc[:200]
            except Exception:
                pass
        return _docstring_first_line(text)

    if ext == ".ps1":
        ps_match = _PS_SYNOPSIS_RE.search(text)
        if ps_match:
            syn = " ".join(ps_match.group("synopsis").strip().splitlines()).strip()
            if syn:
                return syn[:200]
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("#") and not s.startswith("#!"):
                comment = s.lstrip("#").strip()
                if comment:
                    return comment[:200]
        return ""

    if ext in (".sh", ".bash"):
        sh_match = _SH_DESC_RE.search(text)
        if sh_match:
            return sh_match.group(1).strip()[:200]
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("#") and not s.startswith("#!"):
                comment = s.lstrip("#").strip()
                if comment:
                    return comment[:200]
        return ""

    if ext == ".md":
        meta, body = _split_frontmatter(text)
        if meta.get("description"):
            return meta["description"][:200]
        for line in body.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                return s[:200]
        return ""

    return ""


def _extract_dir_tool_description(tool_dir: Path) -> str:
    """Extract a cohesive description for a directory-based tool in ``tools/<name>/``."""
    for doc_name in ("SKILL.md", "README.md"):
        doc_file = tool_dir / doc_name
        if doc_file.is_file():
            desc = _extract_tool_description(doc_file)
            if desc:
                return desc

    pyproject = tool_dir / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
            proj = cast(dict[str, object], data.get("project") or {})
            desc = str(proj.get("description") or "").strip()
            if desc:
                return desc[:200]
        except Exception:
            pass

    for entry_name in ("__init__.py", "main.py", "cli.py"):
        entry_file = tool_dir / entry_name
        if entry_file.is_file():
            desc = _extract_tool_description(entry_file)
            if desc:
                return desc

    for ext in _SCRIPT_EXTS:
        for script_file in sorted(tool_dir.glob(f"*{ext}")):
            if not script_file.name.startswith("_"):
                desc = _extract_tool_description(script_file)
                if desc:
                    return desc
    return ""


def _dir_has_tool_files(tool_dir: Path) -> bool:
    """Return True if a tool subdirectory contains scripts or tool metadata."""
    for marker in ("SKILL.md", "pyproject.toml", "__init__.py", "main.py", "cli.py"):
        if (tool_dir / marker).is_file():
            return True
    return any(
        f.is_file() and f.suffix.lower() in _SCRIPT_EXTS and not f.name.startswith("_")
        for f in tool_dir.iterdir()
    )


def scan_workspace_tools(workspace: Path) -> list[tuple[str, str, str]]:
    """Data-driven discovery of workspace tools across ``scripts/`` and ``tools/``.

    - ``scripts/*.{py,ps1,sh,bash}`` (excluding ``_*``) are registered as single-file tools.
    - ``tools/<subdir>/`` are registered as a single cohesive directory tool named ``<subdir>``,
      preventing ``__init__.py`` pollution and ``main.py`` stem collisions across subdirectories.
    - ``tools/*.{py,ps1,sh,bash}`` standalone files are registered by stem.
    """
    seen: set[str] = set()
    result: list[tuple[str, str, str]] = []

    scripts_dir = workspace / "scripts"
    if scripts_dir.exists():
        for file_path in sorted(scripts_dir.iterdir()):
            if (
                not file_path.is_file()
                or file_path.name.startswith("_")
                or file_path.suffix.lower() not in _SCRIPT_EXTS
            ):
                continue
            name = file_path.stem
            if name in seen:
                continue
            seen.add(name)
            relative = str(file_path.relative_to(workspace)).replace("\\", "/")
            description = _extract_tool_description(file_path)
            result.append((name, relative, description))

    tools_dir = workspace / "tools"
    if tools_dir.exists():
        for sub in sorted(tools_dir.iterdir()):
            if sub.name.startswith(("_", ".")):
                continue
            if sub.is_dir():
                if not _dir_has_tool_files(sub):
                    continue
                name = sub.name
                if name in seen:
                    continue
                seen.add(name)
                relative = str(sub.relative_to(workspace)).replace("\\", "/")
                description = _extract_dir_tool_description(sub)
                result.append((name, relative, description))
            elif sub.is_file() and sub.suffix.lower() in _SCRIPT_EXTS:
                name = sub.stem
                if name in seen:
                    continue
                seen.add(name)
                relative = str(sub.relative_to(workspace)).replace("\\", "/")
                description = _extract_tool_description(sub)
                result.append((name, relative, description))

    return result


def reconcile_workspace_tools(conn: sqlite3.Connection, workspace: Path) -> tuple[int, int, int]:
    """Full CRUD reconciliation of workspace tools into ``tool_registry``.

    Inserts new tools, updates changed paths/descriptions (preserving non-empty
    migrated descriptions when the on-disk description is empty), and tombstones
    (``status = 'removed'``) file-backed workspace tools whose paths no longer
    exist on disk.

    Returns ``(discovered_count, upserted_count, tombstoned_count)``.
    """
    storage.ensure_status_columns(conn)
    found = scan_workspace_tools(workspace)
    found_map = {name: (rel_path, desc) for name, rel_path, desc in found}

    existing_rows = conn.execute(
        "SELECT name, path, description, COALESCE(status, 'active') AS status FROM tool_registry"
    ).fetchall()
    existing = {
        str(r["name"]): (
            "" if r["path"] is None else str(r["path"]),
            "" if r["description"] is None else str(r["description"]),
            str(r["status"]),
        )
        for r in existing_rows
    }

    upserted = 0
    for name, (rel_path, desc) in found_map.items():
        if name not in existing:
            conn.execute(
                "INSERT INTO tool_registry (name, path, description, status) "
                "VALUES (?, ?, ?, 'active')",
                (name, rel_path, desc),
            )
            upserted += 1
        else:
            old_path, old_desc, old_status = existing[name]
            effective_desc = desc if desc else old_desc
            if (old_path, old_desc, old_status) != (rel_path, effective_desc, "active"):
                conn.execute(
                    "UPDATE tool_registry SET path = ?, description = ?, status = 'active' "
                    "WHERE name = ?",
                    (rel_path, effective_desc, name),
                )
                upserted += 1

    tombstoned = 0
    for name, (old_path, _, old_status) in existing.items():
        if name in found_map or old_status == "removed":
            continue
        if old_path and not (workspace / old_path).exists():
            conn.execute(
                "UPDATE tool_registry SET status = 'removed' WHERE name = ?",
                (name,),
            )
            tombstoned += 1

    conn.commit()
    return len(found), upserted, tombstoned


def ingest_all(conn: sqlite3.Connection, workspace: Path, migrate: bool = True) -> IngestReport:
    """Run the full ingest pipeline over a workspace.

    Steps: wisdom from essences, decisions from ADR files, sessions from
    ``MemPalace/sessions.jsonl`` (plus one-time legacy DuckDB migration), and
    then a diff-based search-index resync.
    """
    wisdom_count = ingest_wisdom(conn, essence_dir(workspace))
    decision_count = ingest_decisions(conn, decisions_dir(workspace))

    session_count = ingest_sessions_jsonl(conn, sessions_jsonl_path(workspace))
    tool_count = 0
    duckdb_path = legacy_duckdb_path(workspace)
    if migrate and duckdb_path.exists():
        existing_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
        if existing_sessions is not None and int(existing_sessions[0]) == 0:
            mig_sessions, mig_tools = migrate_sessions_tools(conn, duckdb_path)
            session_count += mig_sessions
            tool_count += mig_tools

    indexed = sync_search_index(conn)
    return IngestReport(
        wisdom_upserted=wisdom_count,
        decision_upserted=decision_count,
        sessions_migrated=session_count,
        tools_upserted=tool_count,
        docs_indexed=indexed,
    )


def is_stale(conn: sqlite3.Connection, workspace: Path) -> bool:
    """Check if on-disk essences, ADRs, or sessions.jsonl differ from SQLite."""
    edir = essence_dir(workspace)
    ddir = decisions_dir(workspace)
    sfile = sessions_jsonl_path(workspace)
    if not edir.exists() and not ddir.exists() and not sfile.exists():
        return False

    essence_files = (
        [f for f in sorted(edir.glob("*.md")) if f.name.lower() not in ("template.md", "readme.md")]
        if edir.exists()
        else []
    )
    file_stems = {f.stem for f in essence_files}
    wisdom_rows = conn.execute("SELECT slug FROM wisdom WHERE source_path IS NOT NULL").fetchall()
    wisdom_slugs = {str(row["slug"]) for row in wisdom_rows}
    if file_stems != wisdom_slugs:
        return True

    decision_files = (
        [f for f in sorted(ddir.glob("ADR-*.md")) if ADR_FILE_RE.match(f.name)]
        if ddir.exists()
        else []
    )
    decision_ids_on_disk: set[str] = set()
    for f in decision_files:
        m = ADR_FILE_RE.match(f.name)
        if m:
            decision_ids_on_disk.add(m.group(1))
    decision_rows = conn.execute("SELECT id FROM decisions").fetchall()
    decision_ids = {str(row["id"]) for row in decision_rows}
    if decision_ids_on_disk != decision_ids:
        return True

    if sfile.exists():
        disk_sessions: set[str] = set()
        for raw_line in sfile.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                loaded = json.loads(stripped)
                if isinstance(loaded, dict):
                    sid = str(cast(dict[str, object], loaded).get("session_id") or "").strip()
                    if sid:
                        disk_sessions.add(sid)
            except ValueError:
                continue
        db_sessions = {
            str(r["session_id"]) for r in conn.execute("SELECT session_id FROM sessions").fetchall()
        }
        if not disk_sessions.issubset(db_sessions):
            return True

    return False


def ensure_fresh_index(conn: sqlite3.Connection, workspace: Path) -> IngestReport | None:
    """Reconcile on-disk essences, decisions, and sessions into the DB if drift is detected."""
    if is_stale(conn, workspace):
        return ingest_all(conn, workspace, migrate=False)
    return None

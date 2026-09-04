"""SQLite storage layer: schema, connection helper, search-index sync.

The DB is a *derived* index: wisdom and decision rows come from source files
(MemPalace essences and ADR files), sessions and the tool registry are migrated
from the legacy DuckDB store. ``search_docs`` holds the canonical text of every
searchable document and ``search_docs_fts`` is its FTS5 mirror (sharing rowids,
porter-tokenized) -- together they form the unified, BM25-rankable search
surface consumed by the retrieval layer. :func:`sync_search_index` reconciles
that surface from the four source tables as a per-document *diff*, so unchanged
documents keep their ``doc_id`` and stored embeddings.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from mempalace.models import KIND_DECISION, KIND_SESSION, KIND_TOOL, KIND_WISDOM

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    timestamp TEXT,
    summary TEXT,
    tags TEXT
);

CREATE TABLE IF NOT EXISTS wisdom (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE,
    category TEXT,
    content TEXT NOT NULL,
    timestamp TEXT,
    source_path TEXT,
    source_session TEXT
);

CREATE TABLE IF NOT EXISTS tool_registry (
    name TEXT PRIMARY KEY,
    path TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    title TEXT,
    path TEXT,
    status TEXT,
    date TEXT,
    tags TEXT
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open (creating parent dirs if needed) a SQLite connection for MemPalace v2."""
    text_path = str(db_path)
    if text_path != ":memory:":
        Path(text_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(text_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    if text_path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all MemPalace v2 tables and the FTS5 index if missing (idempotent)."""
    conn.executescript(_SCHEMA)
    # search_docs and its FTS5 twin are separate tables that share rowids
    # (doc_id). True external-content FTS5 with content= + triggers is overkill
    # at this scale; sync_search_index reconciles the pair per document instead.
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS search_docs (
            doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_kind TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            category TEXT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS search_docs_fts
            USING fts5(title, body, tokenize='porter');
        CREATE TABLE IF NOT EXISTS doc_vectors (
            doc_id INTEGER PRIMARY KEY REFERENCES search_docs(doc_id) ON DELETE CASCADE,
            model TEXT NOT NULL,
            vector BLOB NOT NULL
        );
        """
    )
    conn.commit()
    # Optional sqlite-vec acceleration (L2 upgrade path): created only when the
    # loadable extension is available; numpy brute-force remains the fallback.
    init_vec_index(conn)


def init_vec_index(conn: sqlite3.Connection) -> bool:
    """Load the sqlite-vec extension and create the vec0 mirror table.

    Returns True when the vec0 table is usable on this connection. Failures
    (extension missing, version mismatch, dimension mismatch) are silent: the
    retrieval layer falls back to numpy brute-force cosine.
    """
    if not try_load_vec(conn):
        return False
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_documents "
            "USING vec0(doc_id INTEGER PRIMARY KEY, embedding float[384] distance_metric=cosine)"
        )
        conn.commit()
        return True
    except sqlite3.Error:
        return False


def try_load_vec(conn: sqlite3.Connection) -> bool:
    """Return True if the sqlite-vec loadable extension is active on the connection."""
    try:
        import sqlite_vec  # type: ignore[import-untyped]
    except ImportError:
        return False
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        return True
    except (AttributeError, sqlite3.Error, OSError):
        return False


VEC_DIM = 384


def table_names(conn: sqlite3.Connection) -> list[str]:
    """Return the names of all tables in the database (diagnostics/tests)."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name"
    ).fetchall()
    return [str(row[0]) for row in rows]


def _delete_vec_row(conn: sqlite3.Connection, doc_id: int) -> None:
    """Delete a vec0 mirror row when the table exists; no-op otherwise."""
    try:
        conn.execute("DELETE FROM vec_documents WHERE doc_id = ?", (doc_id,))
    except sqlite3.Error:
        return


def sync_search_index(conn: sqlite3.Connection) -> int:
    """Synchronize the unified search index with the four source tables.

    This is a per-document *diff*, not a wholesale rebuild: documents are keyed
    by stable identity ``(source_kind, source_ref)``, unchanged documents keep
    their ``doc_id`` (so their embeddings survive), changed documents are
    updated in place and their vectors invalidated, new documents are inserted,
    and stale documents (with their vectors) are removed.

    Returns the number of documents present after the sync.
    """
    existing_rows = conn.execute(
        "SELECT doc_id, source_kind, source_ref, title, body, category FROM search_docs"
    ).fetchall()
    existing: dict[tuple[str, str], tuple[int, str, str, str | None]] = {}
    for row in existing_rows:
        existing[(str(row["source_kind"]), str(row["source_ref"]))] = (
            int(row["doc_id"]),
            str(row["title"]),
            str(row["body"]),
            None if row["category"] is None else str(row["category"]),
        )

    rows: list[tuple[str, str, str, str, str | None]] = []

    for row in conn.execute("SELECT slug, category, content FROM wisdom ORDER BY id"):
        slug = str(row["slug"])
        content = str(row["content"])
        category = None if row["category"] is None else str(row["category"])
        rows.append((KIND_WISDOM, slug, slug, content, category))

    for row in conn.execute("SELECT session_id, summary, tags FROM sessions ORDER BY session_id"):
        session_id = str(row["session_id"])
        summary = "" if row["summary"] is None else str(row["summary"])
        tags = _join_tags(row["tags"])
        body = f"{summary} {tags} {session_id}".strip()
        rows.append((KIND_SESSION, session_id, session_id, body, None))

    for row in conn.execute("SELECT name, path, description FROM tool_registry ORDER BY name"):
        name = str(row["name"])
        path = "" if row["path"] is None else str(row["path"])
        description = "" if row["description"] is None else str(row["description"])
        body = f"{name} {path} {description}".strip()
        rows.append((KIND_TOOL, name, name, body, None))

    for row in conn.execute(
        "SELECT id, title, path, status, date, tags FROM decisions ORDER BY id"
    ):
        decision_id = str(row["id"])
        title = "" if row["title"] is None else str(row["title"])
        path = "" if row["path"] is None else str(row["path"])
        status = "" if row["status"] is None else str(row["status"])
        date = "" if row["date"] is None else str(row["date"])
        tags = _join_tags(row["tags"])
        body = f"{title} {path} {status} {date} {tags}".strip()
        rows.append((KIND_DECISION, decision_id, f"{decision_id} {title}".strip(), body, None))

    desired_keys: set[tuple[str, str]] = set()
    for kind, ref, title, body, category in rows:
        key = (kind, ref)
        desired_keys.add(key)
        prior = existing.get(key)
        if prior is None:
            cursor = conn.execute(
                "INSERT INTO search_docs (source_kind, source_ref, title, body, category) "
                "VALUES (?, ?, ?, ?, ?)",
                (kind, ref, title, body, category),
            )
            conn.execute(
                "INSERT INTO search_docs_fts (rowid, title, body) VALUES (?, ?, ?)",
                (cursor.lastrowid, title, body),
            )
        else:
            doc_id, old_title, old_body, old_category = prior
            if (old_title, old_body, old_category) != (title, body, category):
                conn.execute(
                    "UPDATE search_docs SET title = ?, body = ?, category = ? WHERE doc_id = ?",
                    (title, body, category, doc_id),
                )
                conn.execute("DELETE FROM search_docs_fts WHERE rowid = ?", (doc_id,))
                conn.execute(
                    "INSERT INTO search_docs_fts (rowid, title, body) VALUES (?, ?, ?)",
                    (doc_id, title, body),
                )
                # Content changed: invalidate embeddings so `embed` recomputes them.
                conn.execute("DELETE FROM doc_vectors WHERE doc_id = ?", (doc_id,))
                _delete_vec_row(conn, doc_id)

    for key in list(existing):
        if key in desired_keys:
            continue
        doc_id = existing[key][0]
        conn.execute("DELETE FROM search_docs_fts WHERE rowid = ?", (doc_id,))
        conn.execute("DELETE FROM search_docs WHERE doc_id = ?", (doc_id,))
        _delete_vec_row(conn, doc_id)

    conn.commit()
    return len(rows)


def _join_tags(raw: object) -> str:
    """Render stored tags (JSON or list literal) as a plain space-joined string."""
    from mempalace.models import coerce_tags

    return " ".join(coerce_tags(raw))

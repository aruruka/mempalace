"""Core dataclasses and value types for MemPalace v2."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

# Source kinds stored in the unified search index.
KIND_WISDOM = "wisdom"
KIND_SESSION = "session"
KIND_TOOL = "tool"
KIND_DECISION = "decision"

CATEGORY_VALUES = ("preference", "pitfall", "thinking_style")


def _empty_hits() -> list[SearchHit]:
    """Return an empty hits list (typed default for dataclass fields)."""
    return []


def _empty_strings() -> list[str]:
    """Return an empty string list (typed default for dataclass fields)."""
    return []


@dataclass(frozen=True)
class Essence:
    """Parsed representation of one MemPalace essence Markdown file."""

    slug: str
    path: Path
    category: str | None
    content: str


@dataclass(frozen=True)
class SearchHit:
    """One ranked retrieval hit."""

    rank: int
    score: float
    source_kind: str
    source_ref: str
    title: str
    body: str
    category: str | None = None
    doc_id: int = -1

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly mapping (internal doc_id omitted)."""
        return {
            "rank": self.rank,
            "score": round(self.score, 6),
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "title": self.title,
            "category": self.category,
            "body": self.body,
        }


@dataclass(frozen=True)
class SearchResult:
    """Ranked result set for one query."""

    query: str
    mode: str
    hits: list[SearchHit] = field(default_factory=_empty_hits)
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly mapping."""
        return {
            "query": self.query,
            "mode": self.mode,
            "count": len(self.hits),
            "note": self.note,
            "hits": [hit.to_dict() for hit in self.hits],
        }


@dataclass(frozen=True)
class DriftReport:
    """Consistency report between source files and the derived DB."""

    essence_files: int
    wisdom_rows: int
    files_without_row: list[str]
    rows_without_file: list[str]
    decision_files: int
    decision_rows: int
    decision_files_without_row: list[str]
    decision_rows_without_file: list[str]
    session_count: int
    tool_count: int
    legacy_wisdom_rows: int | None = None
    legacy_session_rows: int | None = None
    legacy_tool_rows: int | None = None
    legacy_gap_files: list[str] = field(default_factory=_empty_strings)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly mapping."""
        return {
            "essence_files": self.essence_files,
            "wisdom_rows": self.wisdom_rows,
            "files_without_row": self.files_without_row,
            "rows_without_file": self.rows_without_file,
            "decision_files": self.decision_files,
            "decision_rows": self.decision_rows,
            "decision_files_without_row": self.decision_files_without_row,
            "decision_rows_without_file": self.decision_rows_without_file,
            "session_count": self.session_count,
            "tool_count": self.tool_count,
            "legacy_wisdom_rows": self.legacy_wisdom_rows,
            "legacy_session_rows": self.legacy_session_rows,
            "legacy_tool_rows": self.legacy_tool_rows,
            "legacy_gap_files": self.legacy_gap_files,
        }


@dataclass(frozen=True)
class IngestReport:
    """Counts produced by one ingest run."""

    wisdom_upserted: int
    decision_upserted: int
    sessions_migrated: int
    tools_upserted: int
    docs_indexed: int

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly mapping."""
        return {
            "wisdom_upserted": self.wisdom_upserted,
            "decision_upserted": self.decision_upserted,
            "sessions_migrated": self.sessions_migrated,
            "tools_upserted": self.tools_upserted,
            "docs_indexed": self.docs_indexed,
        }


def tags_to_json(tags: list[str]) -> str:
    """Encode a tag list as a JSON string for TEXT columns."""
    return json.dumps(tags, ensure_ascii=False)


def coerce_tags(raw: object) -> list[str]:
    """Coerce a stored tag representation (JSON or Python-list literal) to a list."""
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    parsed: object = None
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        pass
    if isinstance(parsed, list):
        return [str(item) for item in cast(list[object], parsed)]
    try:
        import ast

        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        pass
    if isinstance(parsed, list):
        return [str(item) for item in cast(list[object], parsed)]
    return []

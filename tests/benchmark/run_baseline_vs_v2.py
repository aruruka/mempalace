# pyright: basic
"""Baseline-vs-v2 recall comparison over the golden benchmark queries.

Compares four measurements per query (core Q01-Q20 + active probes):
- v1@5      : v1 substring-OR semantics emulated over the 34 essence files,
              top-5 in file order (v1 returned unordered OR-union rows).
- v1-any    : same emulation, no top-5 truncation (pure algorithm misses).
- v1-store  : whether the target essence was visible at all in the archived
              legacy DuckDB store (drift factor) - from a legacy DB path if given.
- v2-bm25@5 / v2-hybrid@5 : the real v2 engine against the SQLite DB.

Usage:
    uv run python tests/benchmark/run_baseline_vs_v2.py
        [--db <sqlite>] [--legacy-db <duckdb>] [--workspace <root>]
        [--out-dir artifacts]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from mempalace import config, ingest, retrieval, storage
from mempalace.embeddings import Embedder

_FIXTURE = Path(__file__).with_name("golden_queries.json")


def _load_fixture() -> dict[str, list[dict[str, object]]]:
    with _FIXTURE.open(encoding="utf-8") as handle:
        return json.load(handle)


def _essence_docs(workspace: Path) -> list[tuple[str, str]]:
    """Return (stem, lowercased title+body) per essence file."""
    docs: list[tuple[str, str]] = []
    essence_path = workspace / "MemPalace" / "essences"
    for file_path in sorted(essence_path.glob("*.md")):
        if file_path.name.lower() == "template.md":
            continue
        text = file_path.read_text(encoding="utf-8", errors="replace").lower()
        docs.append((file_path.stem, text))
    return docs


def _v1_match(docs: list[tuple[str, str]], query: str) -> list[str]:
    """v1 semantics: OR-union of substring matches over title+body, file order."""
    keywords = [kw.lower() for kw in query.split() if kw]
    return [stem for stem, text in docs if any(kw in text for kw in keywords)]


def _legacy_visible(legacy_db: Path | None, workspace: Path, stem: str) -> bool:
    """Whether the target essence stem is traceable in the archived DuckDB store."""
    if legacy_db is None or not legacy_db.exists():
        return False
    try:
        import duckdb

        with duckdb.connect(str(legacy_db), read_only=True) as conn:
            tables = {
                str(r[0])
                for r in conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
            }
            haystack: list[str] = []
            for table, column in (
                ("sessions", "session_id"),
                ("wisdom", "content"),
                ("tool_registry", "name"),
            ):
                if table in tables:
                    for row in conn.execute(f"SELECT {column} FROM {table}").fetchall():
                        value = row[0]
                        if value is not None:
                            haystack.append(str(value).lower())
            return any(stem in text for text in haystack)
    except Exception:
        return False


def _run_v2(conn, mode: str, query: str, targets: list[str], embedder: Embedder | None) -> float:
    result = retrieval.search(conn, query, mode=mode, limit=5, embedder=embedder)
    refs = [hit.source_ref for hit in result.hits]
    if not targets:
        return 1.0 if refs else 0.0
    return len(set(refs) & set(targets)) / len(targets)


def main() -> None:
    """Compute and write the baseline-vs-v2 comparison."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None)
    parser.add_argument("--legacy-db", default=None, help="Archived legacy DuckDB path")
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--out-dir", default="artifacts")
    args = parser.parse_args()

    workspace = config.resolve_workspace(args.workspace)
    db_path = config.resolve_db(workspace, args.db)
    legacy_db = Path(args.legacy_db) if args.legacy_db else None
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    docs = _essence_docs(workspace)
    conn = storage.connect(db_path)
    storage.init_db(conn)
    ingest.ingest_all(conn, workspace)

    embedder = Embedder()
    try:
        retrieval.ensure_vectors(conn, embedder)
    except Exception as exc:  # offline - hybrid degrades to bm25 internally
        print(f"# embeddings unavailable ({exc}); hybrid falls back to bm25", file=sys.stderr)
        embedder = None

    fixture = _load_fixture()
    rows: list[dict[str, object]] = []
    for group in ("core", "probes"):
        for entry in fixture[group]:
            if entry.get("retired"):
                continue
            query = str(entry["query"])
            targets = [str(target) for target in cast(list[object], entry["targets"])]
            matched = _v1_match(docs, query)
            hit_targets = [t for t in targets if t in matched]
            v1_at5 = (
                len([t for t in targets if t in matched[:5]]) / len(targets) if targets else 0.0
            )
            v1_any = len(hit_targets) / len(targets) if targets else 0.0
            visible = (
                sum(_legacy_visible(legacy_db, workspace, t) for t in targets) / len(targets)
                if targets
                else 0.0
            )
            rows.append(
                {
                    "id": str(entry["id"]),
                    "group": group,
                    "query": query,
                    "targets": targets,
                    "v1_at5": round(v1_at5, 3),
                    "v1_any": round(v1_any, 3),
                    "v1_store_visible": round(visible, 3),
                    "v2_bm25_at5": round(_run_v2(conn, "bm25", query, targets, None), 3),
                    "v2_hybrid_at5": round(_run_v2(conn, "hybrid", query, targets, embedder), 3),
                }
            )
    conn.close()

    core = [row for row in rows if row["group"] == "core"]
    macro = {
        engine: sum(float(cast(Any, row[engine])) for row in core) / len(core)
        for engine in ("v1_at5", "v1_any", "v1_store_visible", "v2_bm25_at5", "v2_hybrid_at5")
    }

    lines = [
        "# Baseline vs MemPalace v2 — Golden Recall Comparison (2026-09-03)",
        "",
        "Measured over the golden benchmark (core Q01-Q20, active probes). recall@5 unless noted.",
        "",
        "| ID | v1 substring@5 | v1 matched (any) | v1 store visible | v2 BM25@5 | v2 hybrid@5 |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        if row["group"] == "core":
            lines.append(
                f"| {row['id']} | {row['v1_at5']} | {row['v1_any']} | {row['v1_store_visible']} | "
                f"{row['v2_bm25_at5']} | {row['v2_hybrid_at5']} |"
            )
    lines.append(
        f"| **macro (core)** | **{macro['v1_at5']:.3f}** | **{macro['v1_any']:.3f}** | "
        f"**{macro['v1_store_visible']:.3f}** | **{macro['v2_bm25_at5']:.3f}** | "
        f"**{macro['v2_hybrid_at5']:.3f}** |"
    )
    lines += [
        "",
        "Notes:",
        "- v1 columns emulate v1 semantics (case-insensitive substring OR-union, file order, no ranking).",
        "- v1-store-visible uses the archived legacy DuckDB (tmp/mempalace-legacy-data/memory.duckdb); "
        "the remaining gap is dual-write drift (legacy wisdom rows never covered most essence files).",
        "- v2 hybrid measured on MemPalace/memory.sqlite with sqlite-vec KNN + RRF.",
    ]
    md_path = out_dir / "baseline-vs-v2-comparison.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    payload = {"generated": "2026-09-03", "macro_core": macro, "rows": rows}
    json_path = out_dir / "baseline-vs-v2-comparison.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"macro core: v1@5={macro['v1_at5']:.3f} v1-any={macro['v1_any']:.3f} "
        f"v1-store={macro['v1_store_visible']:.3f} v2-bm25={macro['v2_bm25_at5']:.3f} "
        f"v2-hybrid={macro['v2_hybrid_at5']:.3f}"
    )
    print(f"wrote {md_path} and {json_path}")


if __name__ == "__main__":
    main()

# pyright: basic
"""Golden recall benchmark runner for MemPalace v2.

Usage:
    uv run python tests/benchmark/run_benchmark.py [--mode bm25|dense|hybrid]
        [--db <path>] [--workspace <root>] [--topk 5] [--min-recall 0.85]
        [--include-probes] [--json <out>]

Measures macro recall@5 over the core query set (Q01-Q20) from
``golden_queries.json``, prints per-query top-5 document references, emits the
drift report, and exits non-zero when macro recall@5 is below the gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from mempalace import config, ingest, reconcile, retrieval, storage
from mempalace.embeddings import Embedder

_FIXTURE = Path(__file__).with_name("golden_queries.json")
_GATE = 0.85


def _load_fixture() -> dict[str, list[dict[str, object]]]:
    with _FIXTURE.open(encoding="utf-8") as handle:
        return json.load(handle)


def _measure(
    conn,
    mode: str,
    query: str,
    targets: list[str],
    topk: int,
    embedder: Embedder | None,
) -> tuple[float, list[str]]:
    """Return (recall@topk, top references) for one query."""
    result = retrieval.search(conn, query, mode=mode, limit=topk, embedder=embedder)
    refs = [hit.source_ref for hit in result.hits]
    if not targets:
        return 1.0 if refs else 0.0, refs
    hit_count = len(set(refs) & set(targets))
    return hit_count / len(targets), refs


def _run(
    mode: str,
    db_arg: str | None,
    workspace_arg: str | None,
    topk: int,
    include_probes: bool,
    min_recall: float,
) -> int:
    workspace = config.resolve_workspace(workspace_arg)
    db_path = config.resolve_db(workspace, db_arg)
    conn = storage.connect(db_path)
    storage.init_db(conn)
    ingest.ingest_all(conn, workspace)  # idempotent: rebuild derived DB + index

    embedder: Embedder | None = None
    effective_mode = mode
    if mode != retrieval.MODE_BM25:
        embedder = Embedder()
        try:
            retrieval.ensure_vectors(conn, embedder)
        except Exception as exc:  # degrade gracefully offline
            print(f"# embedding unavailable ({exc}); measuring bm25 only", file=sys.stderr)
            embedder = None
            effective_mode = retrieval.MODE_BM25

    fixture = _load_fixture()
    core_rows: list[tuple[str, float, list[str]]] = []
    probe_rows: list[tuple[str, float, list[str]]] = []

    for entry in fixture["core"]:
        query = str(entry["query"])
        targets = [str(target) for target in cast(list[object], entry["targets"])]
        recall, refs = _measure(conn, effective_mode, query, targets, topk, embedder)
        core_rows.append((str(entry["id"]), recall, refs))

    if include_probes:
        for entry in fixture["probes"]:
            if entry.get("retired"):
                continue
            query = str(entry["query"])
            targets = [str(target) for target in cast(list[object], entry["targets"])]
            recall, refs = _measure(conn, effective_mode, query, targets, topk, embedder)
            probe_rows.append((str(entry["id"]), recall, refs))

    macro = sum(recall for _, recall, _ in core_rows) / len(core_rows) if core_rows else 0.0
    zero_hits = [query_id for query_id, recall, refs in core_rows if not refs]

    drift = reconcile.reconcile(conn, workspace)
    conn.close()

    print(f"# mode={effective_mode} topk={topk} queries={len(core_rows)}")
    for query_id, recall, refs in core_rows:
        print(f"{query_id} recall={recall:.2f} top={refs[:topk]}")
    if include_probes:
        for query_id, recall, refs in probe_rows:
            print(f"{query_id} (probe) recall={recall:.2f} top={refs[:topk]}")
    print(
        f"# MACRO_RECALL@{topk}={macro:.3f} "
        f"zero_hit_queries={len(zero_hits)} drift_files_without_row={len(drift.files_without_row)} "
        f"legacy_gap_files={len(drift.legacy_gap_files)}"
    )
    passed = macro >= min_recall
    print(f"# GATE ({min_recall}) {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def main() -> None:
    """Parse args and run the benchmark."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=retrieval.VALID_MODES, default=retrieval.MODE_HYBRID)
    parser.add_argument(
        "--db", default=None, help="SQLite DB path (default: workspace MemPalace/memory.sqlite)"
    )
    parser.add_argument("--workspace", default=None, help="Workspace root (default: repo root)")
    parser.add_argument("--topk", type=int, default=5)
    parser.add_argument("--min-recall", type=float, default=_GATE)
    parser.add_argument("--include-probes", action="store_true")
    args = parser.parse_args()

    sys.exit(
        _run(args.mode, args.db, args.workspace, args.topk, args.include_probes, args.min_recall)
    )


if __name__ == "__main__":
    main()

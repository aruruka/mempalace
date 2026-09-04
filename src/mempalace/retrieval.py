"""Retrieval layers: L1 lexical (FTS5/BM25), L2 dense (numpy cosine), L3 hybrid (RRF).

Semantics fixes over MemPalace v1 (flaw F1):
- ranked BM25 (not substring ILIKE),
- AND semantics across query terms (with stopword removal),
- porter stemming at index+query time (``locking`` matches ``lock``),
- LIKE-wildcard hazards gone (terms are quoted FTS5 phrases),
- ``limit`` bounds output.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

import numpy as np

from mempalace import storage
from mempalace.config import RRF_K
from mempalace.embeddings import Embedder, EmbeddingError
from mempalace.models import SearchHit, SearchResult

_STOPWORDS = frozenset(
    """a an and are as at be but by for from how in is it its of on or that the this
    to was were when which with you your do does did not we our can could should
    will would what why who whom about into over under between""".split()
)
_WHITESPACE_RE = re.compile(r"\s+")

MODE_BM25 = "bm25"
MODE_DENSE = "dense"
MODE_HYBRID = "hybrid"
VALID_MODES = (MODE_BM25, MODE_DENSE, MODE_HYBRID)


@dataclass(frozen=True)
class _Doc:
    """Internal search-document row."""

    doc_id: int
    source_kind: str
    source_ref: str
    title: str
    body: str
    category: str | None


def _query_tokens(query: str) -> list[str]:
    """Tokenize + stopword-filter free-text query terms (fallback: raw tokens)."""
    tokens = [token for token in _WHITESPACE_RE.split(query.strip()) if token]
    kept = [token for token in tokens if len(token) >= 2 and token.lower() not in _STOPWORDS]
    return kept or tokens


def fts_query(query: str) -> str:
    """Build an AND-combined, quoted FTS5 query from free text.

    Stopwords are dropped and each remaining term is wrapped in a phrase so FTS5
    operators cannot be injected. Returns '' when nothing usable remains.
    """
    tokens = _query_tokens(query)
    if not tokens:
        return ""
    phrases = [f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens]
    return " AND ".join(phrases)


def _or_query(query: str) -> str:
    """Build an OR-combined, quoted FTS5 query (relaxed recall fallback)."""
    tokens = _query_tokens(query)
    if not tokens:
        return ""
    phrases = [f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens]
    return " OR ".join(phrases)


def _fetch_docs(
    conn: sqlite3.Connection,
    source_kind: str | None = None,
    category: str | None = None,
) -> list[_Doc]:
    """Fetch search documents, optionally filtered by kind/category."""
    sql = (
        "SELECT doc_id, source_kind, source_ref, title, body, category FROM search_docs WHERE 1 = 1"
    )
    params: list[object] = []
    if source_kind:
        sql += " AND source_kind = ?"
        params.append(source_kind)
    if category:
        sql += " AND category = ?"
        params.append(category)
    rows = conn.execute(sql + " ORDER BY doc_id", params).fetchall()
    docs: list[_Doc] = []
    for row in rows:
        docs.append(
            _Doc(
                doc_id=int(row["doc_id"]),
                source_kind=str(row["source_kind"]),
                source_ref=str(row["source_ref"]),
                title=str(row["title"]),
                body=str(row["body"]),
                category=None if row["category"] is None else str(row["category"]),
            )
        )
    return docs


def _to_hits(docs: list[_Doc], scores: list[float], limit: int) -> list[SearchHit]:
    """Zip docs+scores into ranked SearchHit objects, truncated to limit."""
    hits: list[SearchHit] = []
    for rank, (doc, score) in enumerate(zip(docs, scores, strict=False), start=1):
        if rank > limit:
            break
        hits.append(
            SearchHit(
                rank=rank,
                score=float(score),
                source_kind=doc.source_kind,
                source_ref=doc.source_ref,
                title=doc.title,
                body=doc.body,
                category=doc.category,
                doc_id=doc.doc_id,
            )
        )
    return hits


def _bm25_search(
    conn: sqlite3.Connection,
    fts_expr: str,
    limit: int,
    source_kind: str | None,
    category: str | None,
) -> list[SearchHit]:
    """Run one BM25 FTS query (AND or OR expression) with optional filters."""
    sql = (
        "SELECT d.doc_id, d.source_kind, d.source_ref, d.title, d.body, d.category, "
        "-bm25(search_docs_fts) AS score "
        "FROM search_docs_fts "
        "JOIN search_docs d ON d.doc_id = search_docs_fts.rowid "
        "WHERE search_docs_fts MATCH ?"
    )
    params: list[object] = [fts_expr]
    if source_kind:
        sql += " AND d.source_kind = ?"
        params.append(source_kind)
    if category:
        sql += " AND d.category = ?"
        params.append(category)
    sql += " ORDER BY score DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    hits: list[SearchHit] = []
    for rank, row in enumerate(rows, start=1):
        hits.append(
            SearchHit(
                rank=rank,
                score=float(row["score"]),
                source_kind=str(row["source_kind"]),
                source_ref=str(row["source_ref"]),
                title=str(row["title"]),
                body=str(row["body"]),
                category=None if row["category"] is None else str(row["category"]),
                doc_id=int(row["doc_id"]),
            )
        )
    return hits


def search_bm25(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    source_kind: str | None = None,
    category: str | None = None,
) -> list[SearchHit]:
    """L1: BM25-ranked FTS5 search with AND semantics.

    Natural-language queries often contain tokens that no document has; when
    the strict AND query returns nothing we retry with a ranked OR query
    (BM25 ranking keeps results relevant, unlike v1's unranked substring OR).
    """
    and_expr = fts_query(query)
    if not and_expr:
        return []
    and_hits = _bm25_search(conn, and_expr, limit, source_kind, category)
    if and_hits:
        return and_hits
    or_expr = _or_query(query)
    if or_expr == and_expr:
        return []
    return _bm25_search(conn, or_expr, limit, source_kind, category)


def _vector_arrays(conn: sqlite3.Connection) -> tuple[list[int], np.ndarray]:
    """Load (doc_id list, stacked float32 matrix) from doc_vectors."""
    rows = conn.execute("SELECT doc_id, vector FROM doc_vectors").fetchall()
    doc_ids = [int(row["doc_id"]) for row in rows]
    arrays = [np.frombuffer(bytes(row["vector"]), dtype=np.float32) for row in rows]
    if not doc_ids:
        return [], np.empty((0, 0), dtype=np.float32)
    return doc_ids, np.stack(arrays)


def _vector_count(conn: sqlite3.Connection) -> int:
    """Return the number of stored embeddings."""
    row = conn.execute("SELECT COUNT(*) FROM doc_vectors").fetchone()
    return int(row[0]) if row is not None else 0


def _doc_count(conn: sqlite3.Connection) -> int:
    """Return the number of search documents."""
    row = conn.execute("SELECT COUNT(*) FROM search_docs").fetchone()
    return int(row[0]) if row is not None else 0


def ensure_vectors(conn: sqlite3.Connection, embedder: Embedder) -> int:
    """Embed and persist vectors for documents that have none; returns count added."""
    existing = {int(row[0]) for row in conn.execute("SELECT doc_id FROM doc_vectors").fetchall()}
    docs = [doc for doc in _fetch_docs(conn) if doc.doc_id not in existing]
    if not docs:
        return 0
    texts = [f"{doc.title} {doc.body}" for doc in docs]
    matrix = embedder.embed_texts(texts)
    for doc, vector in zip(docs, matrix, strict=False):
        conn.execute(
            "INSERT INTO doc_vectors (doc_id, model, vector) VALUES (?, ?, ?) "
            "ON CONFLICT(doc_id) DO UPDATE SET model = excluded.model, vector = excluded.vector",
            (doc.doc_id, embedder.model_name, vector.astype(np.float32).tobytes()),
        )
    conn.commit()
    _sync_vec_mirror(conn)
    return len(docs)


def _sync_vec_mirror(conn: sqlite3.Connection) -> None:
    """Copy BLOB vectors into the vec0 mirror table when available and same-dim."""
    try:
        if not storage.try_load_vec(conn):
            return
        rows = conn.execute(
            "SELECT doc_id, vector FROM doc_vectors "
            "WHERE doc_id NOT IN (SELECT doc_id FROM vec_documents)"
        ).fetchall()
        for row in rows:
            vector = bytes(row["vector"])
            if len(vector) // 4 != storage.VEC_DIM:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO vec_documents (doc_id, embedding) VALUES (?, ?)",
                (int(row["doc_id"]), vector),
            )
        conn.commit()
    except (sqlite3.Error, ValueError):
        return


def _knn_scores(conn: sqlite3.Connection, query_blob: bytes) -> dict[int, float] | None:
    """sqlite-vec KNN over the vec0 mirror; None when unavailable/empty/failed.

    ``MEM_PALACE_VEC=0`` disables the sqlite-vec path (numpy brute-force is used).
    """
    import os

    if os.environ.get("MEM_PALACE_VEC", "1") == "0":
        return None
    try:
        if not storage.try_load_vec(conn):
            return None
        count_row = conn.execute("SELECT COUNT(*) FROM vec_documents").fetchone()
        if count_row is None or int(count_row[0]) == 0:
            return None
        rows = conn.execute(
            "SELECT doc_id, distance FROM vec_documents "
            "WHERE embedding MATCH ? ORDER BY distance LIMIT 2000",
            (query_blob,),
        ).fetchall()
        if not rows:
            return None
        return {int(row["doc_id"]): float(1.0 - float(row["distance"])) for row in rows}
    except (sqlite3.Error, ValueError):
        return None


def _dense_scores(conn: sqlite3.Connection, embedder: Embedder, query: str) -> dict[int, float]:
    """Return {doc_id: cosine similarity} for the query vs stored vectors.

    Prefers the sqlite-vec KNN path (vec0 mirror) when the extension is loaded;
    falls back to numpy brute-force cosine over the BLOB vectors otherwise.
    """
    query_vector = embedder.embed_texts([query])[0].astype(np.float32)
    _sync_vec_mirror(conn)
    knn = _knn_scores(conn, query_vector.tobytes())
    if knn:
        return knn

    doc_ids, matrix = _vector_arrays(conn)
    if not doc_ids:
        raise EmbeddingError("no stored vectors; run 'mempalace embed'")
    query_norm = query_vector / (np.linalg.norm(query_vector) + 1e-9)
    row_norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    similarities = (matrix / row_norms) @ query_norm
    return dict(zip(doc_ids, (float(value) for value in similarities), strict=False))


def search_dense(
    conn: sqlite3.Connection,
    embedder: Embedder,
    query: str,
    limit: int,
    source_kind: str | None = None,
    category: str | None = None,
) -> list[SearchHit]:
    """L2: cosine search over persisted embeddings (never auto-embeds)."""
    if _vector_count(conn) == 0:
        raise EmbeddingError("no stored vectors; run 'uv run python -m mempalace embed' first")
    docs = _fetch_docs(conn, source_kind, category)
    if not docs:
        return []
    scores = _dense_scores(conn, embedder, query)
    scored = [(scores[doc.doc_id], doc) for doc in docs if doc.doc_id in scores]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    docs_sorted = [doc for _, doc in scored]
    doc_scores = [score for score, _ in scored]
    return _to_hits(docs_sorted, doc_scores, limit)


def _rrf_fuse(
    bm25_hits: list[SearchHit], dense_hits: list[SearchHit], limit: int
) -> list[SearchHit]:
    """Reciprocal Rank Fusion (k=RRF_K) over BM25 + dense rankings."""
    fused: dict[int, float] = {}
    order: list[int] = []
    for hits in (bm25_hits, dense_hits):
        for rank, hit in enumerate(hits, start=1):
            doc_id = hit.doc_id
            if doc_id not in fused:
                fused[doc_id] = 0.0
                order.append(doc_id)
            fused[doc_id] += 1.0 / (RRF_K + rank)
    ranked_ids = sorted(order, key=lambda doc_id: fused[doc_id], reverse=True)[:limit]
    by_id = {hit.doc_id: hit for hit in (*bm25_hits, *dense_hits)}
    hits: list[SearchHit] = []
    for rank, doc_id in enumerate(ranked_ids, start=1):
        source = by_id[doc_id]
        hits.append(
            SearchHit(
                rank=rank,
                score=fused[doc_id],
                source_kind=source.source_kind,
                source_ref=source.source_ref,
                title=source.title,
                body=source.body,
                category=source.category,
                doc_id=doc_id,
            )
        )
    return hits


def search(
    conn: sqlite3.Connection,
    query: str,
    mode: str = MODE_HYBRID,
    limit: int = 5,
    source_kind: str | None = None,
    category: str | None = None,
    embedder: Embedder | None = None,
) -> SearchResult:
    """Top-level retrieval entry point with graceful embedding fallback.

    Search never embeds documents inline. Dense/hybrid modes use only the
    embeddings already persisted by ``mempalace embed``; when none exist (or the
    model cannot load) the result degrades to BM25 with an explanatory note.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {VALID_MODES}")
    pool = max(limit * 4, limit)
    bm25_hits = search_bm25(conn, query, pool, source_kind, category)
    note: str | None = None

    if mode == MODE_BM25 or embedder is None:
        return SearchResult(query=query, mode=MODE_BM25, hits=bm25_hits[:limit])

    try:
        dense_hits = search_dense(conn, embedder, query, pool, source_kind, category)
    except EmbeddingError as exc:
        note = f"dense unavailable ({exc}); fell back to bm25"
        return SearchResult(query=query, mode=MODE_BM25, hits=bm25_hits[:limit], note=note)

    if mode == MODE_DENSE:
        return SearchResult(query=query, mode=MODE_DENSE, hits=dense_hits[:limit])

    missing = _doc_count(conn) - _vector_count(conn)
    if missing > 0:
        note = f"{missing} document(s) not embedded yet; run 'uv run python -m mempalace embed'"
    return SearchResult(
        query=query,
        mode=MODE_HYBRID,
        hits=_rrf_fuse(bm25_hits, dense_hits, limit),
        note=note,
    )

# pyright: basic
"""In-memory (code-level) tests for retrieval layers and ingest helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from mempalace import ingest, retrieval, storage
from mempalace.embeddings import Embedder, EmbeddingError
from mempalace.ingest import parse_essence
from mempalace.models import SearchHit

HERMES_SLUG = "2026-08-20-hermes-file-locking"
UV_SLUG = "2026-07-17-uv-cache-rename"
QUERY_FILE_LOCK = "file lock when updating hermes agent on windows"
QUERY_UV = "uv cache rename"


class FakeEmbedder(Embedder):
    """Deterministic embedder for plumbing tests (no network, no model)."""

    def __init__(self) -> None:
        super().__init__("fake")
        self._features = ("cache", "hermes", "duckdb", "uv")

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        rows = [[1.0 if feature in text else 0.0 for feature in self._features] for text in texts]
        return np.asarray(rows, dtype=np.float32)


class BrokenEmbedder(Embedder):
    """Embedder that always fails, for fallback-path tests."""

    def __init__(self) -> None:
        super().__init__("broken")

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        raise EmbeddingError("model download failed (offline)")


def _connect(db_path: Path):
    conn = storage.connect(db_path)
    storage.init_db(conn)
    return conn


def test_bm25_ranks_hermes_for_natural_language(ingested: Path) -> None:
    conn = _connect(ingested)
    try:
        hits = retrieval.search_bm25(conn, QUERY_FILE_LOCK, limit=3)
    finally:
        conn.close()
    assert hits
    assert hits[0].source_ref == HERMES_SLUG


def test_and_semantics_narrows_results(ingested: Path) -> None:
    conn = _connect(ingested)
    try:
        hits = retrieval.search_bm25(conn, QUERY_UV, limit=10)
    finally:
        conn.close()
    assert hits
    assert all(hit.source_ref == UV_SLUG for hit in hits)
    assert len(hits) == 1


def test_fts_query_quotes_operators() -> None:
    assert '"100%"' == retrieval.fts_query("100% OR *")
    assert retrieval.fts_query("   ") == ""


def test_injection_query_is_safe(ingested: Path) -> None:
    conn = _connect(ingested)
    try:
        hits = retrieval.search_bm25(conn, "100% OR *", limit=5)
    finally:
        conn.close()
    assert isinstance(hits, list)


def test_parse_essence_category_detection(workspace: Path) -> None:
    file_path = workspace / "MemPalace" / "essences" / f"{HERMES_SLUG}.md"
    essence = parse_essence(Path(file_path))
    assert essence.category == "pitfall"
    assert essence.slug == HERMES_SLUG


def test_dense_and_hybrid_with_fake_vectors(ingested: Path) -> None:
    conn = _connect(ingested)
    fake = FakeEmbedder()
    try:
        added = retrieval.ensure_vectors(conn, fake)
        assert added == 4  # 3 wisdom docs + 1 decision doc
        dense = retrieval.search_dense(conn, fake, "hermes cache", limit=3)
        hybrid = retrieval.search(
            conn, "hermes cache", mode=retrieval.MODE_HYBRID, limit=3, embedder=fake
        )
    finally:
        conn.close()
    assert dense and dense[0].source_ref in (HERMES_SLUG, UV_SLUG)
    assert hybrid.mode == retrieval.MODE_HYBRID
    assert hybrid.hits


def test_hybrid_falls_back_to_bm25_on_embedding_failure(ingested: Path) -> None:
    conn = _connect(ingested)
    broken = BrokenEmbedder()
    try:
        result = retrieval.search(
            conn, QUERY_FILE_LOCK, mode=retrieval.MODE_HYBRID, limit=3, embedder=broken
        )
    finally:
        conn.close()
    assert result.mode == retrieval.MODE_BM25
    assert result.note is not None
    assert result.hits and result.hits[0].source_ref == HERMES_SLUG


def test_rrf_fuses_both_rankings() -> None:
    def hit(doc_id: int) -> SearchHit:
        return SearchHit(
            rank=1,
            score=0.0,
            source_kind="wisdom",
            source_ref=str(doc_id),
            title="",
            body="",
            doc_id=doc_id,
        )

    bm25 = [hit(1), hit(2), hit(3)]
    dense = [hit(2), hit(1), hit(4)]
    fused = retrieval._rrf_fuse(bm25, dense, limit=3)
    assert [h.doc_id for h in fused] == [1, 2, 3]


def test_search_rejects_unknown_mode(ingested: Path) -> None:
    conn = _connect(ingested)
    try:
        with pytest.raises(ValueError):
            retrieval.search(conn, "anything", mode="bogus")
    finally:
        conn.close()


def test_vec_mirror_table_and_dim_guard(ingested: Path) -> None:
    """vec0 exists iff sqlite-vec loads; non-384-dim vectors are not mirrored."""
    conn = _connect(ingested)
    try:
        vec_available = storage.try_load_vec(conn)
        tables = storage.table_names(conn)
        assert ("vec_documents" in tables) is vec_available
        retrieval.ensure_vectors(conn, FakeEmbedder())  # 4-dim fake vectors
        if vec_available:
            count = conn.execute("SELECT COUNT(*) FROM vec_documents").fetchone()
            assert count is not None and int(count[0]) == 0  # dim guard skipped them
    finally:
        conn.close()


def test_reingest_keeps_doc_ids_and_vectors(ingested: Path, workspace: Path) -> None:
    """Unchanged content across ingest keeps doc_ids and stored vectors stable."""
    conn = _connect(ingested)
    try:
        retrieval.ensure_vectors(conn, FakeEmbedder())
        before_docs = conn.execute(
            "SELECT doc_id, source_kind, source_ref FROM search_docs ORDER BY doc_id"
        ).fetchall()
        before_vec = {
            int(row[0]) for row in conn.execute("SELECT doc_id FROM doc_vectors").fetchall()
        }
        assert len(before_vec) == 4

        ingest.ingest_all(conn, workspace)

        after_docs = conn.execute(
            "SELECT doc_id, source_kind, source_ref FROM search_docs ORDER BY doc_id"
        ).fetchall()
        after_vec = {
            int(row[0]) for row in conn.execute("SELECT doc_id FROM doc_vectors").fetchall()
        }
        assert [(r[0], r[1], r[2]) for r in after_docs] == [(r[0], r[1], r[2]) for r in before_docs]
        assert after_vec == before_vec  # no re-embedding triggered
    finally:
        conn.close()


def test_content_change_invalidates_only_changed_vector(
    ingested: Path,
    workspace: Path,
) -> None:
    """Editing one essence invalidates exactly that document's vector."""
    from mempalace import ingest

    conn = _connect(ingested)
    try:
        retrieval.ensure_vectors(conn, FakeEmbedder())
        hermes = conn.execute(
            "SELECT doc_id FROM search_docs "
            "WHERE source_kind = 'wisdom' AND source_ref = '2026-08-20-hermes-file-locking'"
        ).fetchone()
        assert hermes is not None
        hermes_id = int(hermes[0])

        file_path = workspace / "MemPalace" / "essences" / "2026-08-20-hermes-file-locking.md"
        file_path.write_text(
            file_path.read_text(encoding="utf-8") + "\n\nAdded: a brand new pitfall sentence.\n",
            encoding="utf-8",
        )
        ingest.ingest_all(conn, workspace)

        changed_id = conn.execute(
            "SELECT doc_id FROM search_docs "
            "WHERE source_kind = 'wisdom' AND source_ref = '2026-08-20-hermes-file-locking'"
        ).fetchone()
        assert changed_id is not None and int(changed_id[0]) == hermes_id
        gone = conn.execute(
            "SELECT COUNT(*) FROM doc_vectors WHERE doc_id = ?", (hermes_id,)
        ).fetchone()
        assert gone is not None and int(gone[0]) == 0
        remaining = conn.execute("SELECT COUNT(*) FROM doc_vectors").fetchone()
        assert remaining is not None and int(remaining[0]) == 3
    finally:
        conn.close()


def test_search_without_vectors_falls_back_to_bm25(ingested: Path) -> None:
    """Dense/hybrid search with no vectors fails fast to BM25 with a note."""
    conn = _connect(ingested)
    try:
        result = retrieval.search(
            conn, QUERY_FILE_LOCK, mode=retrieval.MODE_HYBRID, limit=3, embedder=FakeEmbedder()
        )
        assert result.mode == retrieval.MODE_BM25
        assert result.note is not None and "embed" in result.note
        assert result.hits and result.hits[0].source_ref == HERMES_SLUG
    finally:
        conn.close()


def test_offline_policy_env(tmp_path: Path, monkeypatch) -> None:
    """HF_HUB_OFFLINE is set only when an ONNX model is already cached."""
    import os

    from mempalace.embeddings import _apply_offline_policy

    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    _apply_offline_policy(tmp_path)  # empty cache -> stays online
    assert os.environ.get("HF_HUB_OFFLINE") is None
    (tmp_path / "model.onnx").write_bytes(b"onnx")
    _apply_offline_policy(tmp_path)  # cached model -> offline enforced
    assert os.environ.get("HF_HUB_OFFLINE") == "1"


def test_vec_knn_parity_with_numpy(tmp_path: Path) -> None:
    """sqlite-vec KNN ordering/scores match numpy cosine on the same vectors."""
    db = tmp_path / "vec-parity.sqlite"
    conn = storage.connect(db)
    storage.init_db(conn)
    try:
        if not storage.try_load_vec(conn):
            pytest.skip("sqlite-vec extension unavailable")
        dim = storage.VEC_DIM
        rng = np.random.default_rng(0)
        query = rng.normal(size=dim).astype(np.float32)
        near = (query * 0.9 + 0.1 * rng.normal(size=dim)).astype(np.float32)
        far = rng.normal(size=dim).astype(np.float32)

        for doc_id, vector in ((1, near), (2, far)):
            conn.execute(
                "INSERT INTO search_docs (doc_id, source_kind, source_ref, title, body) "
                "VALUES (?, 'wisdom', ?, 't', 'b')",
                (doc_id, f"d{doc_id}"),
            )
            conn.execute(
                "INSERT INTO doc_vectors (doc_id, model, vector) VALUES (?, 'fake', ?)",
                (doc_id, vector.tobytes()),
            )
            conn.execute(
                "INSERT INTO vec_documents (doc_id, embedding) VALUES (?, ?)",
                (doc_id, vector.tobytes()),
            )
        conn.commit()

        knn = retrieval._knn_scores(conn, query.tobytes())
        assert knn is not None
        assert set(knn) == {1, 2}
        assert knn[1] > knn[2]  # near vector ranks above far

        def _cos(a: np.ndarray, b: np.ndarray) -> float:
            return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

        assert abs(knn[1] - _cos(query, near)) < 0.02
        assert abs(knn[2] - _cos(query, far)) < 0.02
    finally:
        conn.close()


def test_search_auto_syncs_new_essence(tmp_path: Path) -> None:
    import json

    from typer.testing import CliRunner

    from mempalace.cli import app
    from mempalace.initializer import WorkspaceInitializerConfig, initialize_workspace

    runner = CliRunner()
    # 1. Initialize workspace
    cfg = WorkspaceInitializerConfig(workspace=tmp_path, embed=False)
    initialize_workspace(cfg)

    # 2. Add new essence directly to disk without running mempalace ingest
    new_essence = tmp_path / "MemPalace" / "essences" / "2026-09-06-dynamic-rule.md"
    new_essence.write_text(
        "# Dynamic Rule\nCategory: preference\nAlways use strict linting and verification.\n",
        encoding="utf-8",
    )

    # 3. Search should automatically detect and return the new essence
    result = runner.invoke(
        app, ["search", "dynamic", "rule", "--workspace", str(tmp_path), "--mode", "bm25"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert any(h["source_ref"] == "2026-09-06-dynamic-rule" for h in data["hits"])

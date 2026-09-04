"""L3 local embeddings via fastembed (ONNX; offline after first model download)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from mempalace.config import DEFAULT_MODEL, embed_cache_dir

_BATCH_SIZE = 64


class EmbeddingError(RuntimeError):
    """Raised when embeddings cannot be produced (fastembed missing or offline)."""


def _has_local_model(cache_dir: Path) -> bool:
    """Return True when an ONNX model is already present in the cache dir."""
    if not cache_dir.exists():
        return False
    return any(cache_dir.rglob("*.onnx"))


def _apply_offline_policy(cache_dir: Path) -> None:
    """Force offline model loading when the model is already cached locally.

    This prevents a network metadata round-trip from stalling model load; the
    first download (empty cache) is left online and is performed by the explicit
    ``mempalace embed`` command.
    """
    import os

    if _has_local_model(cache_dir):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")


class Embedder:
    """Lazy fastembed wrapper producing float32 embedding matrices.

    The fastembed import and the model download both happen on first use, so a
    plain ``search --mode bm25`` never touches this module's heavy machinery.
    Model loading is cache-first: when the ONNX model is already cached locally
    we force offline mode (``HF_HUB_OFFLINE=1``) so no network round-trip can
    stall a load; a missing cache means a genuine download, which only the
    explicit ``mempalace embed`` command performs.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        """Create an embedder for ``model_name`` (the model loads lazily)."""
        self._model_name = model_name
        self._backend: Any | None = None

    @property
    def model_name(self) -> str:
        """Return the configured fastembed model name."""
        return self._model_name

    def _backend_or_raise(self) -> Any:
        """Import fastembed and load the model, or raise EmbeddingError."""
        cache_dir = embed_cache_dir()
        _apply_offline_policy(cache_dir)
        if self._backend is None:
            try:
                from fastembed import TextEmbedding  # type: ignore[import-untyped]
            except ImportError as exc:  # pragma: no cover - defensive
                raise EmbeddingError(
                    f"fastembed is not installed ({exc}); run: uv add fastembed"
                ) from exc
            try:
                self._backend = TextEmbedding(model_name=self._model_name, cache_dir=str(cache_dir))
            except Exception as exc:  # surface any model-load failure
                raise EmbeddingError(
                    f"could not load embedding model {self._model_name!r} "
                    f"(offline? cache_dir={cache_dir}): {exc}"
                ) from exc
        return self._backend

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts into a single float32 matrix (rows = texts)."""
        backend = self._backend_or_raise()
        vectors = [
            np.asarray(vector, dtype=np.float32)
            for vector in backend.embed(texts, batch_size=_BATCH_SIZE)
        ]
        if not vectors:
            raise EmbeddingError("embedding produced no vectors")
        return np.stack(vectors)

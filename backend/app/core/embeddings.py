"""SentenceTransformers wrapper.

The model is a process-level singleton: loading weights costs seconds, so it is
loaded once at FastAPI startup and reused for every request.
"""
from __future__ import annotations

import logging
import os
import threading

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

_model = None
_lock = threading.Lock()


def _load_model():
    from sentence_transformers import SentenceTransformer

    os.environ.setdefault("HF_HOME", settings.hf_home)
    logger.info("Loading embedding model %s", settings.embedding_model)
    model = SentenceTransformer(settings.embedding_model)
    logger.info("Embedding model ready (dim=%s)", model.get_sentence_embedding_dimension())
    return model


def get_model():
    """Return the shared model, loading it on first use (thread-safe)."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = _load_model()
    return _model


def warmup() -> None:
    """Called at startup so the first real request is not the one paying for load."""
    get_model().encode(["warmup"], normalize_embeddings=True)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts into L2-normalised vectors.

    Normalising at write time means cosine similarity reduces to a dot product,
    which is what pgvector's `<=>` operator gives us cheaply.
    """
    if not texts:
        return []
    vectors = get_model().encode(
        texts,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return [v.astype(np.float32).tolist() for v in vectors]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]; safe against zero vectors."""
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0.0:
        return 0.0
    return float(np.dot(va, vb) / denom)

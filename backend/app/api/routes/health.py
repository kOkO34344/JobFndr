"""Liveness and readiness."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False

    from app.core import embeddings

    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "embedding_model": settings.embedding_model,
        "embedding_loaded": embeddings._model is not None,
    }

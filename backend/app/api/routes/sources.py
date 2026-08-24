"""Job source management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories import jobs_repo, sources_repo
from app.schemas.models import SourceOut, SourceToggle
from app.services import job_fetch_service
from app.services.sources.registry import attributions

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)) -> list[SourceOut]:
    job_fetch_service.ensure_sources_registered(db)
    counts = dict(jobs_repo.source_counts(db))
    return [
        SourceOut(**{
            **{k: getattr(source, k) for k in
               ("id", "name", "display_name", "type", "base_url", "rate_limit_info",
                "enabled", "last_fetched_at", "last_status")},
            "job_count": counts.get(source.display_name, 0),
        })
        for source in sources_repo.list_all(db)
    ]


@router.put("/{name}", response_model=SourceOut)
def toggle_source(name: str, payload: SourceToggle, db: Session = Depends(get_db)) -> SourceOut:
    source = sources_repo.set_enabled(db, name, payload.enabled)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Source '{name}' not found")
    db.commit()
    return SourceOut(**{
        **{k: getattr(source, k) for k in
           ("id", "name", "display_name", "type", "base_url", "rate_limit_info",
            "enabled", "last_fetched_at", "last_status")},
        "job_count": 0,
    })


@router.get("/attributions", response_model=list[str])
def source_attributions() -> list[str]:
    return attributions()

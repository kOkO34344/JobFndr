"""Job scanning, listing and labelling endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.serializers import job_detail, job_summary
from app.repositories import jobs_repo, matches_repo
from app.repositories.jobs_repo import JobFilters
from app.schemas.models import (
    JobDetail,
    JobListResponse,
    LabelRequest,
    ScanRequest,
    ScanResponse,
)
from app.services import job_fetch_service
from app.services.taxonomy import ALL_CATEGORIES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/scan", response_model=ScanResponse)
async def scan_jobs(
    payload: ScanRequest | None = None, db: Session = Depends(get_db)
) -> ScanResponse:
    """Fetch, normalize, embed and rank jobs from every enabled source.

    Synchronous by design: a scan is explicitly user-triggered and the UI shows
    a real result rather than a job id to poll.
    """
    sources = payload.sources if payload else None
    try:
        result = await job_fetch_service.scan(db, sources)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scan failed")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Scan failed: {type(exc).__name__}: {exc}"
        ) from exc
    return ScanResponse(**result)


@router.get("", response_model=JobListResponse)
def list_jobs(
    db: Session = Depends(get_db),
    category: list[str] | None = Query(default=None),
    source: list[str] | None = Query(default=None),
    seniority: list[str] | None = Query(default=None),
    job_format: list[str] | None = Query(default=None, alias="format"),
    job_status: list[str] | None = Query(default=None, alias="status"),
    min_score: float = Query(default=0.0, ge=0.0, le=1.0),
    remote_only: bool = Query(default=False),
    passed_filters_only: bool = Query(default=False),
    search: str | None = Query(default=None, max_length=200),
    sort: str = Query(default="score", pattern="^(score|date|title)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JobListResponse:
    filters = JobFilters(
        category=category,
        source=source,
        seniority=seniority,
        format=job_format,
        status=job_status,
        min_score=min_score,
        remote_only=remote_only,
        passed_filters_only=passed_filters_only,
        search=search,
        sort=sort,
    )
    rows, total = jobs_repo.list_jobs(db, filters, limit=limit, offset=offset)
    return JobListResponse(
        items=[job_summary(posting, match, label, src) for posting, match, label, src in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/categories", response_model=list[str])
def list_categories() -> list[str]:
    return list(ALL_CATEGORIES)


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobDetail:
    posting = jobs_repo.get(db, job_id)
    if posting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Job {job_id} not found")
    return job_detail(posting)


@router.post("/{job_id}/label", response_model=JobDetail)
def label_job(job_id: int, payload: LabelRequest, db: Session = Depends(get_db)) -> JobDetail:
    if jobs_repo.get(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Job {job_id} not found")
    matches_repo.set_label(db, job_id, payload.status, payload.notes)
    db.commit()
    return job_detail(jobs_repo.get(db, job_id))


@router.delete("/{job_id}/label", response_model=JobDetail)
def clear_job_label(job_id: int, db: Session = Depends(get_db)) -> JobDetail:
    if jobs_repo.get(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Job {job_id} not found")
    matches_repo.clear_label(db, job_id)
    db.commit()
    return job_detail(jobs_repo.get(db, job_id))


@router.post("/rerank", response_model=dict)
def rerank(db: Session = Depends(get_db)) -> dict:
    """Re-score stored jobs without re-fetching (after tweaking preferences)."""
    return {"ranked": job_fetch_service.rank_all(db)}

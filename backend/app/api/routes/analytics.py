"""Analytics endpoints for the dashboard summary view."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories import jobs_repo, matches_repo, scans_repo
from app.schemas.models import AnalyticsResponse
from app.services.llm import client as llm

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=AnalyticsResponse)
def analytics(db: Session = Depends(get_db)) -> AnalyticsResponse:
    last = scans_repo.latest(db)
    return AnalyticsResponse(
        total_jobs=jobs_repo.total_count(db),
        category_counts=dict(jobs_repo.category_counts(db)),
        high_match_by_category=dict(matches_repo.category_score_breakdown(db, min_score=0.5)),
        label_counts=matches_repo.label_counts(db),
        score_buckets=matches_repo.score_buckets(db),
        source_counts=dict(jobs_repo.source_counts(db)),
        last_scan=(
            {
                "id": last.id,
                "started_at": last.started_at.isoformat() if last.started_at else None,
                "finished_at": last.finished_at.isoformat() if last.finished_at else None,
                "status": last.status,
                "jobs_fetched": last.jobs_fetched,
                "jobs_new": last.jobs_new,
                "jobs_ranked": last.jobs_ranked,
                "errors": last.errors,
            }
            if last
            else None
        ),
        llm=llm.provider_status(),
    )

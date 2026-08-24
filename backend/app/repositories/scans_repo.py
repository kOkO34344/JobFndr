"""Data access for scan runs (the on-demand fetch audit trail)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScanRun


def start(db: Session, source_names: list[str]) -> ScanRun:
    run = ScanRun(sources_run=source_names, status="running")
    db.add(run)
    db.flush()
    return run


def finish(db: Session, run: ScanRun, stats: dict, errors: list[dict], status: str) -> ScanRun:
    run.finished_at = datetime.now(timezone.utc)
    run.jobs_fetched = stats.get("fetched", 0)
    run.jobs_new = stats.get("new", 0)
    run.jobs_updated = stats.get("updated", 0)
    run.jobs_embedded = stats.get("embedded", 0)
    run.jobs_ranked = stats.get("ranked", 0)
    run.errors = errors
    run.status = status
    db.flush()
    return run


def latest(db: Session) -> ScanRun | None:
    return db.execute(
        select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1)
    ).scalar_one_or_none()


def recent(db: Session, limit: int = 10) -> list[ScanRun]:
    return list(
        db.execute(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(limit)).scalars()
    )

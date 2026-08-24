"""Data access for job sources."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JobSource


def list_all(db: Session, enabled_only: bool = False) -> list[JobSource]:
    stmt = select(JobSource).order_by(JobSource.name)
    if enabled_only:
        stmt = stmt.where(JobSource.enabled.is_(True))
    return list(db.execute(stmt).scalars())


def get_by_name(db: Session, name: str) -> JobSource | None:
    return db.execute(select(JobSource).where(JobSource.name == name)).scalar_one_or_none()


def upsert(db: Session, row: dict) -> JobSource:
    """Register an adapter, preserving any user edits to config/enabled."""
    source = get_by_name(db, row["name"])
    if source is None:
        source = JobSource(**row)
        db.add(source)
    else:
        # Only refresh adapter-owned metadata; config and enabled are the user's.
        for key in ("display_name", "type", "base_url", "api_endpoint", "rate_limit_info"):
            if key in row:
                setattr(source, key, row[key])
    db.flush()
    return source


def set_enabled(db: Session, name: str, enabled: bool) -> JobSource | None:
    source = get_by_name(db, name)
    if source:
        source.enabled = enabled
        db.flush()
    return source


def mark_fetched(db: Session, source: JobSource, status: str) -> None:
    source.last_fetched_at = datetime.now(timezone.utc)
    source.last_status = status[:500]
    db.flush()

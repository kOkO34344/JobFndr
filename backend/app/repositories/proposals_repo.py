"""Data access for generated proposals."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Proposal

USER_ID = 1


def create(db: Session, job_id: int, content: str, tone: str,
           model_used: str | None, generated_by: str) -> Proposal:
    proposal = Proposal(
        job_id=job_id, user_id=USER_ID, tone=tone, content=content,
        model_used=model_used, generated_by=generated_by,
    )
    db.add(proposal)
    db.flush()
    return proposal


def latest_for_job(db: Session, job_id: int) -> Proposal | None:
    return db.execute(
        select(Proposal)
        .where(Proposal.job_id == job_id)
        .order_by(Proposal.created_at.desc(), Proposal.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def history_for_job(db: Session, job_id: int, limit: int = 10) -> list[Proposal]:
    return list(
        db.execute(
            select(Proposal)
            .where(Proposal.job_id == job_id)
            .order_by(Proposal.created_at.desc(), Proposal.id.desc())
            .limit(limit)
        ).scalars()
    )

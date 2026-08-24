"""Data access for match scores and triage labels."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import JobLabel, JobMatch, JobPosting
from app.services.ranking_service import MatchResult

USER_ID = 1


def to_vector_literal(vector) -> str:
    """Format a vector for pgvector's text input: "[0.1,0.2,...]".

    pgvector hands embeddings back as numpy arrays, and str() on one of those
    yields numpy's repr (newlines, no commas), which Postgres rejects.
    """
    return "[" + ",".join(f"{float(v):.8f}" for v in vector) + "]"


def cosine_scores(db: Session, cv_embedding) -> dict[int, float]:
    """Cosine similarity of every stored job against the CV, computed in Postgres.

    pgvector's `<=>` is cosine *distance*, so similarity is 1 - distance. Doing
    this in the DB avoids pulling every 384-dim vector into Python.
    """
    if cv_embedding is None or len(cv_embedding) == 0:
        return {}
    rows = db.execute(
        text(
            "SELECT job_id, 1 - (embedding_vector <=> CAST(:cv AS vector)) AS similarity "
            "FROM job_embedding"
        ),
        {"cv": to_vector_literal(cv_embedding)},
    ).all()
    return {job_id: float(similarity) for job_id, similarity in rows}


def upsert_match(db: Session, job_id: int, result: MatchResult) -> JobMatch:
    existing = db.execute(
        select(JobMatch).where(JobMatch.job_id == job_id, JobMatch.user_id == USER_ID)
    ).scalar_one_or_none()

    fields = dict(
        rule_score=result.rule_score,
        semantic_score=result.semantic_score,
        final_score=result.final_score,
        passed_filters=result.passed_filters,
        explanation=result.explanation,
        scored_at=datetime.now(timezone.utc),
    )

    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
        db.flush()
        return existing

    match = JobMatch(job_id=job_id, user_id=USER_ID, **fields)
    db.add(match)
    db.flush()
    return match


def top_matches(db: Session, limit: int = 20) -> list[tuple[JobPosting, JobMatch]]:
    return list(
        db.execute(
            select(JobPosting, JobMatch)
            .join(JobMatch, JobMatch.job_id == JobPosting.id)
            .where(JobMatch.user_id == USER_ID)
            .order_by(JobMatch.final_score.desc())
            .limit(limit)
        ).all()
    )


def set_label(db: Session, job_id: int, status: str, notes: str | None) -> JobLabel:
    existing = db.execute(
        select(JobLabel).where(JobLabel.job_id == job_id, JobLabel.user_id == USER_ID)
    ).scalar_one_or_none()

    if existing:
        existing.status = status
        if notes is not None:
            existing.notes = notes
        db.flush()
        return existing

    label = JobLabel(job_id=job_id, user_id=USER_ID, status=status, notes=notes)
    db.add(label)
    db.flush()
    return label


def clear_label(db: Session, job_id: int) -> bool:
    label = db.execute(
        select(JobLabel).where(JobLabel.job_id == job_id, JobLabel.user_id == USER_ID)
    ).scalar_one_or_none()
    if label:
        db.delete(label)
        db.flush()
        return True
    return False


def label_counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(JobLabel.status, func.count(JobLabel.id)).group_by(JobLabel.status)
    ).all()
    return {status: count for status, count in rows}


def score_buckets(db: Session) -> dict[str, int]:
    """Distribution of match quality, for the analytics view."""
    rows = db.execute(
        select(
            func.count(JobMatch.id).filter(JobMatch.final_score >= 0.7),
            func.count(JobMatch.id).filter(
                JobMatch.final_score >= 0.5, JobMatch.final_score < 0.7
            ),
            func.count(JobMatch.id).filter(
                JobMatch.final_score >= 0.3, JobMatch.final_score < 0.5
            ),
            func.count(JobMatch.id).filter(JobMatch.final_score < 0.3),
        )
    ).one()
    return {"strong": rows[0], "good": rows[1], "weak": rows[2], "poor": rows[3]}


def category_score_breakdown(db: Session, min_score: float = 0.5) -> list[tuple[str, int]]:
    """High-match counts per category — the 'internships vs freelance' chart."""
    return list(
        db.execute(
            select(JobPosting.category, func.count(JobPosting.id))
            .join(JobMatch, JobMatch.job_id == JobPosting.id)
            .where(JobMatch.final_score >= min_score, JobMatch.passed_filters.is_(True))
            .group_by(JobPosting.category)
            .order_by(func.count(JobPosting.id).desc())
        ).all()
    )

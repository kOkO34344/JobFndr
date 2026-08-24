"""Data access for job postings and their embeddings."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import JobEmbedding, JobLabel, JobMatch, JobPosting, JobSource
from app.services.normalizer import NormalizedJob


@dataclass
class JobFilters:
    category: list[str] | None = None
    source: list[str] | None = None
    seniority: list[str] | None = None
    format: list[str] | None = None
    status: list[str] | None = None
    min_score: float = 0.0
    remote_only: bool = False
    passed_filters_only: bool = False
    search: str | None = None
    sort: str = "score"  # score | date | title


def upsert_posting(db: Session, source_id: int, job: NormalizedJob) -> tuple[JobPosting, bool]:
    """Insert or refresh a posting. Returns (posting, was_created)."""
    existing = db.execute(
        select(JobPosting).where(
            JobPosting.source_id == source_id,
            JobPosting.external_id == job.external_id,
        )
    ).scalar_one_or_none()

    fields = dict(
        title=job.title,
        company=job.company,
        location=job.location,
        remote_flag=job.remote_flag,
        raw_description=job.raw_description,
        url=job.url,
        seniority=job.seniority,
        format=job.format,
        category=job.category,
        tags=job.tags,
        salary_text=job.salary_text,
        posted_at=job.posted_at,
        fetched_at=datetime.now(timezone.utc),
    )

    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
        db.flush()
        return existing, False

    posting = JobPosting(source_id=source_id, external_id=job.external_id, **fields)
    db.add(posting)
    db.flush()
    return posting, True


def get(db: Session, job_id: int) -> JobPosting | None:
    return db.execute(
        select(JobPosting)
        .options(joinedload(JobPosting.source), joinedload(JobPosting.match),
                 joinedload(JobPosting.label))
        .where(JobPosting.id == job_id)
    ).scalar_one_or_none()


def existing_hashes(db: Session, job_ids: list[int]) -> dict[int, str]:
    """content_hash of every job that already has an embedding, so a re-scan
    only re-embeds postings whose text actually changed."""
    if not job_ids:
        return {}
    rows = db.execute(
        select(JobEmbedding.job_id, JobEmbedding.content_hash).where(
            JobEmbedding.job_id.in_(job_ids)
        )
    ).all()
    return {job_id: content_hash for job_id, content_hash in rows}


def upsert_embedding(
    db: Session, job_id: int, vector: list[float], model_name: str, content_hash: str
) -> None:
    existing = db.get(JobEmbedding, job_id)
    if existing:
        existing.embedding_vector = vector
        existing.model_name = model_name
        existing.content_hash = content_hash
    else:
        db.add(
            JobEmbedding(
                job_id=job_id,
                embedding_vector=vector,
                model_name=model_name,
                content_hash=content_hash,
            )
        )
    db.flush()


def all_job_ids(db: Session) -> list[int]:
    return list(db.execute(select(JobPosting.id)).scalars())


def _apply_filters(stmt: Select, filters: JobFilters) -> Select:
    if filters.category:
        stmt = stmt.where(JobPosting.category.in_(filters.category))
    if filters.source:
        stmt = stmt.where(JobSource.name.in_(filters.source))
    if filters.seniority:
        stmt = stmt.where(JobPosting.seniority.in_(filters.seniority))
    if filters.format:
        stmt = stmt.where(JobPosting.format.in_(filters.format))
    if filters.remote_only:
        stmt = stmt.where(JobPosting.remote_flag.is_(True))
    if filters.min_score > 0:
        stmt = stmt.where(JobMatch.final_score >= filters.min_score)
    if filters.passed_filters_only:
        stmt = stmt.where(JobMatch.passed_filters.is_(True))
    if filters.status:
        if "unlabeled" in filters.status:
            others = [s for s in filters.status if s != "unlabeled"]
            condition = JobLabel.status.is_(None)
            if others:
                condition = or_(condition, JobLabel.status.in_(others))
            stmt = stmt.where(condition)
        else:
            stmt = stmt.where(JobLabel.status.in_(filters.status))
    if filters.search:
        pattern = f"%{filters.search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(JobPosting.title).like(pattern),
                func.lower(JobPosting.company).like(pattern),
                func.lower(JobPosting.raw_description).like(pattern),
            )
        )
    return stmt


def _base_query() -> Select:
    return (
        select(JobPosting, JobMatch, JobLabel, JobSource)
        .join(JobSource, JobPosting.source_id == JobSource.id)
        .outerjoin(JobMatch, JobMatch.job_id == JobPosting.id)
        .outerjoin(JobLabel, JobLabel.job_id == JobPosting.id)
    )


def list_jobs(
    db: Session, filters: JobFilters, limit: int = 50, offset: int = 0
) -> tuple[list[tuple], int]:
    """Return (rows, total_count) where each row is (posting, match, label, source)."""
    stmt = _apply_filters(_base_query(), filters)

    count_stmt = _apply_filters(
        select(func.count(func.distinct(JobPosting.id)))
        .select_from(JobPosting)
        .join(JobSource, JobPosting.source_id == JobSource.id)
        .outerjoin(JobMatch, JobMatch.job_id == JobPosting.id)
        .outerjoin(JobLabel, JobLabel.job_id == JobPosting.id),
        filters,
    )
    total = db.execute(count_stmt).scalar_one()

    if filters.sort == "date":
        stmt = stmt.order_by(JobPosting.posted_at.desc().nullslast(), JobPosting.id.desc())
    elif filters.sort == "title":
        stmt = stmt.order_by(JobPosting.title.asc())
    else:
        stmt = stmt.order_by(JobMatch.final_score.desc().nullslast(), JobPosting.id.desc())

    rows = db.execute(stmt.limit(limit).offset(offset)).all()
    return rows, total


def category_counts(db: Session, min_score: float = 0.0) -> list[tuple[str, int]]:
    stmt = (
        select(JobPosting.category, func.count(JobPosting.id))
        .outerjoin(JobMatch, JobMatch.job_id == JobPosting.id)
        .group_by(JobPosting.category)
        .order_by(func.count(JobPosting.id).desc())
    )
    if min_score > 0:
        stmt = stmt.where(JobMatch.final_score >= min_score)
    return list(db.execute(stmt).all())


def source_counts(db: Session) -> list[tuple[str, int]]:
    return list(
        db.execute(
            select(JobSource.display_name, func.count(JobPosting.id))
            .join(JobPosting, JobPosting.source_id == JobSource.id)
            .group_by(JobSource.display_name)
            .order_by(func.count(JobPosting.id).desc())
        ).all()
    )


def total_count(db: Session) -> int:
    return db.execute(select(func.count(JobPosting.id))).scalar_one()

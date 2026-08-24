"""On-demand job scanning: fetch -> normalize -> store -> embed -> rank.

There is no scheduler by design; this runs only when POST /jobs/scan is called.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.embeddings import embed_texts
from app.models import JobPosting, UserProfile
from app.repositories import jobs_repo, matches_repo, profile_repo, scans_repo, sources_repo
from app.services import profile_service
from app.services.normalizer import NormalizedJob, normalize
from app.services.ranking_service import JobView, rank_job
from app.services.sources.base import SourceError, build_client
from app.services.sources.registry import ADAPTERS, get_adapter

logger = logging.getLogger(__name__)


def ensure_sources_registered(db: Session) -> None:
    """Make sure every adapter in the registry has a job_source row."""
    for adapter in ADAPTERS:
        sources_repo.upsert(db, adapter.to_source_row())
    db.commit()


async def scan(db: Session, source_names: list[str] | None = None) -> dict:
    """Run one full scan. Never raises for a single failing source."""
    ensure_sources_registered(db)
    profile = profile_service.bootstrap(db)

    sources = sources_repo.list_all(db, enabled_only=True)
    if source_names:
        wanted = set(source_names)
        sources = [s for s in sources if s.name in wanted]
    if not sources:
        return {"status": "no_sources", "message": "No enabled sources to scan.",
                "stats": {}, "errors": [], "top_jobs": []}

    run = scans_repo.start(db, [s.name for s in sources])
    db.commit()

    stats = {"fetched": 0, "new": 0, "updated": 0, "embedded": 0, "ranked": 0}
    errors: list[dict] = []
    per_source: list[dict] = []

    async with build_client() as client:
        for source in sources:
            adapter = get_adapter(source.name)
            if adapter is None:
                errors.append({"source": source.name, "error": "No adapter registered"})
                continue

            try:
                raw_jobs = await adapter.fetch(client, source.config or {})
            except SourceError as exc:
                logger.warning("scan: %s failed: %s", source.name, exc)
                errors.append({"source": source.name, "error": str(exc)})
                sources_repo.mark_fetched(db, source, f"error: {exc}")
                per_source.append({"source": source.display_name, "fetched": 0,
                                   "new": 0, "error": str(exc)})
                db.commit()
                continue
            except Exception as exc:  # noqa: BLE001 - one bad source must not stop the scan
                logger.exception("scan: unexpected failure in %s", source.name)
                errors.append({"source": source.name, "error": f"{type(exc).__name__}: {exc}"})
                sources_repo.mark_fetched(db, source, f"error: {exc}")
                per_source.append({"source": source.display_name, "fetched": 0,
                                   "new": 0, "error": str(exc)})
                db.commit()
                continue

            created, updated = _store_jobs(db, source.id, raw_jobs)
            stats["fetched"] += len(raw_jobs)
            stats["new"] += created
            stats["updated"] += updated
            sources_repo.mark_fetched(db, source, f"ok: {len(raw_jobs)} jobs")
            per_source.append({
                "source": source.display_name,
                "fetched": len(raw_jobs),
                "new": created,
                "error": None,
            })
            db.commit()

    stats["embedded"] = await asyncio.to_thread(_embed_pending_jobs, db)
    stats["ranked"] = rank_all(db, profile)
    db.commit()

    status = "completed" if not errors or stats["fetched"] else "failed"
    scans_repo.finish(db, run, stats, errors, status)
    db.commit()

    top_rows = matches_repo.top_matches(db, limit=20)
    return {
        "status": status,
        "scan_id": run.id,
        "stats": stats,
        "errors": errors,
        "per_source": per_source,
        "top_jobs": [_top_job_summary(posting, match) for posting, match in top_rows],
    }


def _store_jobs(db: Session, source_id: int, raw_jobs: list) -> tuple[int, int]:
    created = updated = 0
    seen: set[str] = set()

    for raw in raw_jobs:
        try:
            job: NormalizedJob = normalize(raw)
        except Exception:  # noqa: BLE001 - skip an individual malformed posting
            logger.exception("normalize failed for %r", getattr(raw, "external_id", "?"))
            continue

        if not job.title or not job.url or not job.external_id:
            continue
        # A source can return the same posting twice across pages.
        if job.external_id in seen:
            continue
        seen.add(job.external_id)

        _, was_created = jobs_repo.upsert_posting(db, source_id, job)
        created += was_created
        updated += not was_created

    return created, updated


def _embed_pending_jobs(db: Session, batch_size: int = 64) -> int:
    """Embed postings whose text has no embedding, or whose text has changed."""
    from sqlalchemy import select

    postings = list(db.execute(select(JobPosting)).scalars())
    if not postings:
        return 0

    known = jobs_repo.existing_hashes(db, [p.id for p in postings])
    pending: list[tuple[JobPosting, str, str]] = []

    for posting in postings:
        job = _posting_to_normalized(posting)
        content_hash = job.content_hash()
        if known.get(posting.id) == content_hash:
            continue
        pending.append((posting, job.embedding_text(), content_hash))

    if not pending:
        return 0

    logger.info("Embedding %d job postings", len(pending))
    embedded = 0
    for start in range(0, len(pending), batch_size):
        chunk = pending[start : start + batch_size]
        vectors = embed_texts([text for _, text, _ in chunk])
        for (posting, _, content_hash), vector in zip(chunk, vectors, strict=True):
            jobs_repo.upsert_embedding(
                db, posting.id, vector, settings.embedding_model, content_hash
            )
            embedded += 1
        db.commit()

    return embedded


def _posting_to_normalized(posting: JobPosting) -> NormalizedJob:
    """Rebuild the normalized view from a stored row (for hashing/embedding)."""
    return NormalizedJob(
        external_id=posting.external_id,
        title=posting.title,
        url=posting.url,
        company=posting.company,
        location=posting.location,
        raw_description=posting.raw_description,
        tags=list(posting.tags or []),
        salary_text=posting.salary_text,
        posted_at=posting.posted_at,
        remote_flag=posting.remote_flag,
        seniority=posting.seniority,
        format=posting.format,
        category=posting.category,
        domains=[],
    )


def rank_all(db: Session, profile: UserProfile | None = None) -> int:
    """Score every stored job against the profile. Safe to re-run any time."""
    from sqlalchemy import select

    profile = profile or profile_repo.get(db)
    if profile is None:
        return 0

    view = profile_service.build_profile_view(profile)
    similarities = matches_repo.cosine_scores(db, profile.cv_embedding)

    postings = list(db.execute(select(JobPosting)).scalars())
    ranked = 0

    for posting in postings:
        job_view = JobView(
            title=posting.title,
            description=posting.raw_description,
            tags=list(posting.tags or []),
            seniority=posting.seniority,
            format=posting.format,
            remote_flag=posting.remote_flag,
            company=posting.company,
            location=posting.location,
        )
        result = rank_job(
            job_view,
            view,
            cosine_similarity=similarities.get(posting.id, 0.0),
            rule_weight=settings.rule_weight,
            semantic_weight=settings.semantic_weight,
        )
        matches_repo.upsert_match(db, posting.id, result)
        ranked += 1

    db.commit()
    return ranked


def _top_job_summary(posting: JobPosting, match) -> dict:
    return {
        "id": posting.id,
        "title": posting.title,
        "company": posting.company,
        "category": posting.category,
        "seniority": posting.seniority,
        "format": posting.format,
        "url": posting.url,
        "final_score": match.final_score,
        "summary": (match.explanation or {}).get("summary"),
    }

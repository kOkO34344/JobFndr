"""Turn ORM rows into API models. Keeps routers free of shaping logic."""
from __future__ import annotations

from app.models import JobLabel, JobMatch, JobPosting, JobSource, UserProfile
from app.schemas.models import JobDetail, JobSummary, LabelOut, MatchOut, ProfileOut
from app.services.sources.registry import get_adapter


def job_summary(posting: JobPosting, match: JobMatch | None,
                label: JobLabel | None, source: JobSource) -> JobSummary:
    return JobSummary(
        id=posting.id,
        title=posting.title,
        company=posting.company,
        location=posting.location,
        remote_flag=posting.remote_flag,
        url=posting.url,
        seniority=posting.seniority,
        format=posting.format,
        category=posting.category,
        tags=list(posting.tags or []),
        salary_text=posting.salary_text,
        posted_at=posting.posted_at,
        fetched_at=posting.fetched_at,
        source=source.display_name,
        final_score=match.final_score if match else None,
        passed_filters=match.passed_filters if match else None,
        match_summary=(match.explanation or {}).get("summary") if match else None,
        status=label.status if label else None,
    )


def job_detail(posting: JobPosting) -> JobDetail:
    match, label, source = posting.match, posting.label, posting.source
    adapter = get_adapter(source.name)
    base = job_summary(posting, match, label, source)
    return JobDetail(
        **base.model_dump(),
        raw_description=posting.raw_description,
        match=MatchOut(
            rule_score=match.rule_score,
            semantic_score=match.semantic_score,
            final_score=match.final_score,
            passed_filters=match.passed_filters,
            explanation=match.explanation or {},
            scored_at=match.scored_at,
        ) if match else None,
        label=LabelOut(
            status=label.status, notes=label.notes, updated_at=label.updated_at
        ) if label else None,
        source_display_name=source.display_name,
        source_attribution=adapter.attribution if adapter else None,
    )


def profile_out(profile: UserProfile) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        name=profile.name,
        email=profile.email,
        location=profile.location,
        headline=profile.headline,
        cv_original_path=profile.cv_original_path,
        has_cv=bool(profile.cv_text),
        has_embedding=profile.cv_embedding is not None,
        skills=list(profile.skills or []),
        languages=list(profile.languages or []),
        education=list(profile.education or []),
        experience=list(profile.experience or []),
        domains=list(profile.domains or []),
        preferred_roles=list(profile.preferred_roles or []),
        preferred_formats=list(profile.preferred_formats or []),
        preferred_seniority=list(profile.preferred_seniority or []),
        remote_only=profile.remote_only,
        updated_at=profile.updated_at,
    )

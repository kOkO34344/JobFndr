"""Pydantic request/response models for the API layer."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SeniorityLiteral = Literal["internship", "junior", "mid-level", "senior", "other"]
FormatLiteral = Literal["freelance", "part-time", "full-time", "unknown"]
StatusLiteral = Literal["shortlisted", "maybe", "rejected", "applied"]


# --- Profile ---------------------------------------------------------------
class LanguageOut(BaseModel):
    name: str
    proficiency: str | None = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str | None = None
    location: str | None = None
    headline: str | None = None
    cv_original_path: str | None = None
    has_cv: bool = False
    has_embedding: bool = False
    skills: list[str] = []
    languages: list[dict] = []
    education: list[dict] = []
    experience: list[dict] = []
    domains: list[dict] = []
    preferred_roles: list[str] = []
    preferred_formats: list[str] = []
    preferred_seniority: list[str] = []
    remote_only: bool = True
    updated_at: datetime | None = None


class ProfileUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    location: str | None = None
    headline: str | None = None
    skills: list[str] | None = None
    languages: list[dict] | None = None
    education: list[dict] | None = None
    experience: list[dict] | None = None
    domains: list[dict] | None = None
    preferred_roles: list[str] | None = None
    preferred_formats: list[FormatLiteral] | None = None
    preferred_seniority: list[SeniorityLiteral] | None = None
    remote_only: bool | None = None
    reembed: bool = Field(
        default=True,
        description="Re-embed the profile and re-rank all jobs after saving.",
    )


class CvUploadResult(BaseModel):
    profile: ProfileOut
    parsed: dict
    warnings: list[str] = []


# --- Jobs ------------------------------------------------------------------
class MatchOut(BaseModel):
    rule_score: float
    semantic_score: float
    final_score: float
    passed_filters: bool
    explanation: dict[str, Any] = {}
    scored_at: datetime | None = None


class LabelOut(BaseModel):
    status: StatusLiteral
    notes: str | None = None
    updated_at: datetime | None = None


class JobSummary(BaseModel):
    id: int
    title: str
    company: str | None = None
    location: str | None = None
    remote_flag: bool
    url: str
    seniority: SeniorityLiteral
    format: FormatLiteral
    category: str
    tags: list[str] = []
    salary_text: str | None = None
    posted_at: datetime | None = None
    fetched_at: datetime | None = None
    source: str
    final_score: float | None = None
    passed_filters: bool | None = None
    match_summary: str | None = None
    status: StatusLiteral | None = None


class JobDetail(JobSummary):
    raw_description: str
    match: MatchOut | None = None
    label: LabelOut | None = None
    source_display_name: str | None = None
    source_attribution: str | None = None


class JobListResponse(BaseModel):
    items: list[JobSummary]
    total: int
    limit: int
    offset: int


class LabelRequest(BaseModel):
    status: StatusLiteral
    notes: str | None = None


# --- Scanning --------------------------------------------------------------
class ScanRequest(BaseModel):
    sources: list[str] | None = Field(
        default=None, description="Source names to scan; omit for all enabled sources."
    )


class ScanSourceResult(BaseModel):
    source: str
    fetched: int
    new: int
    error: str | None = None


class ScanResponse(BaseModel):
    status: str
    scan_id: int | None = None
    stats: dict[str, int] = {}
    errors: list[dict] = []
    per_source: list[ScanSourceResult] = []
    top_jobs: list[dict] = []


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_name: str
    type: str
    base_url: str
    rate_limit_info: str | None = None
    enabled: bool
    last_fetched_at: datetime | None = None
    last_status: str | None = None
    job_count: int = 0


class SourceToggle(BaseModel):
    enabled: bool


# --- Proposals -------------------------------------------------------------
class ProposalRequest(BaseModel):
    tone: Literal["professional", "warm", "direct", "enthusiastic"] = "professional"
    extra_instructions: str | None = None


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    tone: str
    content: str
    model_used: str | None = None
    generated_by: str
    created_at: datetime


class ProposalResponse(BaseModel):
    proposal: ProposalOut
    meta: dict


# --- Analytics -------------------------------------------------------------
class AnalyticsResponse(BaseModel):
    total_jobs: int
    category_counts: dict[str, int]
    high_match_by_category: dict[str, int]
    label_counts: dict[str, int]
    score_buckets: dict[str, int]
    source_counts: dict[str, int]
    last_scan: dict | None = None
    llm: dict

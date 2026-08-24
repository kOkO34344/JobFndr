"""SQLAlchemy models mirroring backend/sql/schema.sql."""
from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.models.base import Base, TimestampMixin

DIM = settings.embedding_dim

SENIORITY_VALUES = ("internship", "junior", "mid-level", "senior", "other")
FORMAT_VALUES = ("freelance", "part-time", "full-time", "unknown")
LABEL_VALUES = ("shortlisted", "maybe", "rejected", "applied")


class UserProfile(Base):
    """The single user. id is pinned to 1 by a CHECK constraint."""

    __tablename__ = "user_profile"
    __table_args__ = (CheckConstraint("id = 1", name="ck_single_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    headline: Mapped[str | None] = mapped_column(Text)
    cv_original_path: Mapped[str | None] = mapped_column(Text)
    cv_text: Mapped[str | None] = mapped_column(Text)
    cv_embedding: Mapped[list[float] | None] = mapped_column(Vector(DIM))
    skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    languages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    education: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    experience: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    domains: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    preferred_roles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    preferred_formats: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    preferred_seniority: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    remote_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class JobSource(Base):
    __tablename__ = "job_source"
    __table_args__ = (
        CheckConstraint("type IN ('api','ats','rss','scraping')", name="ck_source_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_endpoint: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    rate_limit_info: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    postings: Mapped[list[JobPosting]] = relationship(back_populates="source")


class JobPosting(Base):
    __tablename__ = "job_posting"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_job_source_external"),
        CheckConstraint(
            "seniority IN ('internship','junior','mid-level','senior','other')",
            name="ck_seniority",
        ),
        CheckConstraint(
            "format IN ('freelance','part-time','full-time','unknown')", name="ck_format"
        ),
        Index("ix_job_posting_category", "category"),
        Index("ix_job_posting_seniority", "seniority"),
        Index("ix_job_posting_format", "format"),
        Index("ix_job_posting_posted_at", "posted_at"),
        Index("ix_job_posting_remote", "remote_flag"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("job_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    remote_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[str] = mapped_column(Text, nullable=False)
    seniority: Mapped[str] = mapped_column(String(16), nullable=False, default="other")
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    category: Mapped[str] = mapped_column(String(48), nullable=False, default="Other")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    salary_text: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source: Mapped[JobSource] = relationship(back_populates="postings")
    embedding: Mapped[JobEmbedding | None] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    match: Mapped[JobMatch | None] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    label: Mapped[JobLabel | None] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )


class JobEmbedding(Base):
    __tablename__ = "job_embedding"

    job_id: Mapped[int] = mapped_column(
        ForeignKey("job_posting.id", ondelete="CASCADE"), primary_key=True
    )
    embedding_vector: Mapped[list[float]] = mapped_column(Vector(DIM), nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped[JobPosting] = relationship(back_populates="embedding")


class JobMatch(Base):
    __tablename__ = "job_match"
    __table_args__ = (
        UniqueConstraint("job_id", "user_id", name="uq_job_match_job_user"),
        Index("ix_job_match_final_score", "final_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("job_posting.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_profile.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    semantic_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    passed_filters: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    explanation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped[JobPosting] = relationship(back_populates="match")


class JobLabel(Base):
    __tablename__ = "job_label"
    __table_args__ = (
        UniqueConstraint("job_id", "user_id", name="uq_job_label_job_user"),
        CheckConstraint(
            "status IN ('shortlisted','maybe','rejected','applied')", name="ck_label_status"
        ),
        Index("ix_job_label_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("job_posting.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_profile.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    job: Mapped[JobPosting] = relationship(back_populates="label")


class Proposal(Base, TimestampMixin):
    __tablename__ = "proposal"
    __table_args__ = (
        CheckConstraint("generated_by IN ('llm','template')", name="ck_generated_by"),
        Index("ix_proposal_job", "job_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("job_posting.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_profile.id", ondelete="CASCADE"), nullable=False
    )
    tone: Mapped[str] = mapped_column(String(32), nullable=False, default="professional")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[str] = mapped_column(String(16), nullable=False, default="llm")


class ScanRun(Base):
    __tablename__ = "scan_run"
    __table_args__ = (
        CheckConstraint("status IN ('running','completed','failed')", name="ck_scan_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sources_run: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    jobs_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_embedded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_ranked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")

-- JobFndr schema (PostgreSQL 16 + pgvector)
-- Applied automatically at backend startup via SQLAlchemy metadata; kept here
-- as the canonical readable reference and for `psql -f` bootstrapping.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Single-user profile. Exactly one row (id = 1), enforced by the check below.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_profile (
    id               INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    name             TEXT        NOT NULL,
    email            TEXT,
    location         TEXT,
    headline         TEXT,
    cv_original_path TEXT,
    cv_text          TEXT,
    cv_embedding     vector(384),
    skills           JSONB       NOT NULL DEFAULT '[]'::jsonb,
    languages        JSONB       NOT NULL DEFAULT '[]'::jsonb,
    education        JSONB       NOT NULL DEFAULT '[]'::jsonb,
    experience       JSONB       NOT NULL DEFAULT '[]'::jsonb,
    domains          JSONB       NOT NULL DEFAULT '[]'::jsonb,
    preferred_roles  JSONB       NOT NULL DEFAULT '[]'::jsonb,
    preferred_formats JSONB      NOT NULL DEFAULT '[]'::jsonb,
    preferred_seniority JSONB    NOT NULL DEFAULT '[]'::jsonb,
    remote_only      BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Job sources: public APIs, ATS boards, RSS or polite scrapers.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_source (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN ('api', 'ats', 'rss', 'scraping')),
    base_url        TEXT NOT NULL,
    api_endpoint    TEXT,
    -- Adapter-specific config, e.g. {"boards": ["anthropic", "figma"]}
    config          JSONB NOT NULL DEFAULT '{}'::jsonb,
    rate_limit_info TEXT,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    last_fetched_at TIMESTAMPTZ,
    last_status     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Normalised job postings.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_posting (
    id              SERIAL PRIMARY KEY,
    source_id       INTEGER NOT NULL REFERENCES job_source(id) ON DELETE CASCADE,
    external_id     TEXT NOT NULL,
    title           TEXT NOT NULL,
    company         TEXT,
    location        TEXT,
    remote_flag     BOOLEAN NOT NULL DEFAULT FALSE,
    raw_description TEXT NOT NULL DEFAULT '',
    url             TEXT NOT NULL,
    seniority       TEXT NOT NULL DEFAULT 'other'
                    CHECK (seniority IN ('internship','junior','mid-level','senior','other')),
    format          TEXT NOT NULL DEFAULT 'unknown'
                    CHECK (format IN ('freelance','part-time','full-time','unknown')),
    category        TEXT NOT NULL DEFAULT 'Other',
    tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    salary_text     TEXT,
    posted_at       TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Same posting re-seen on a later scan must update, not duplicate.
    CONSTRAINT uq_job_source_external UNIQUE (source_id, external_id)
);

CREATE INDEX IF NOT EXISTS ix_job_posting_category   ON job_posting (category);
CREATE INDEX IF NOT EXISTS ix_job_posting_seniority  ON job_posting (seniority);
CREATE INDEX IF NOT EXISTS ix_job_posting_format     ON job_posting (format);
CREATE INDEX IF NOT EXISTS ix_job_posting_posted_at  ON job_posting (posted_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_job_posting_source     ON job_posting (source_id);
CREATE INDEX IF NOT EXISTS ix_job_posting_remote     ON job_posting (remote_flag);

-- ---------------------------------------------------------------------------
-- Job embeddings (1:1 with job_posting).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_embedding (
    job_id           INTEGER PRIMARY KEY REFERENCES job_posting(id) ON DELETE CASCADE,
    embedding_vector vector(384) NOT NULL,
    model_name       TEXT NOT NULL,
    -- Hash of the embedded text, so a re-scan only re-embeds changed postings.
    content_hash     TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Cosine-distance ANN index. IVFFlat needs rows before it helps; harmless empty.
CREATE INDEX IF NOT EXISTS ix_job_embedding_cosine
    ON job_embedding USING ivfflat (embedding_vector vector_cosine_ops) WITH (lists = 100);

-- ---------------------------------------------------------------------------
-- Hybrid ranking results.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_match (
    id             SERIAL PRIMARY KEY,
    job_id         INTEGER NOT NULL REFERENCES job_posting(id) ON DELETE CASCADE,
    user_id        INTEGER NOT NULL REFERENCES user_profile(id) ON DELETE CASCADE,
    rule_score     DOUBLE PRECISION NOT NULL CHECK (rule_score BETWEEN 0 AND 1),
    semantic_score DOUBLE PRECISION NOT NULL CHECK (semantic_score BETWEEN 0 AND 1),
    final_score    DOUBLE PRECISION NOT NULL CHECK (final_score BETWEEN 0 AND 1),
    passed_filters BOOLEAN NOT NULL DEFAULT TRUE,
    explanation    JSONB NOT NULL DEFAULT '{}'::jsonb,
    scored_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_job_match_job_user UNIQUE (job_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_job_match_final_score ON job_match (final_score DESC);
CREATE INDEX IF NOT EXISTS ix_job_match_user        ON job_match (user_id);

-- ---------------------------------------------------------------------------
-- My triage decisions.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_label (
    id         SERIAL PRIMARY KEY,
    job_id     INTEGER NOT NULL REFERENCES job_posting(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES user_profile(id) ON DELETE CASCADE,
    status     TEXT NOT NULL CHECK (status IN ('shortlisted','maybe','rejected','applied')),
    notes      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_job_label_job_user UNIQUE (job_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_job_label_status ON job_label (status);

-- ---------------------------------------------------------------------------
-- Generated proposal drafts (history kept; latest wins in the UI).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS proposal (
    id            SERIAL PRIMARY KEY,
    job_id        INTEGER NOT NULL REFERENCES job_posting(id) ON DELETE CASCADE,
    user_id       INTEGER NOT NULL REFERENCES user_profile(id) ON DELETE CASCADE,
    tone          TEXT NOT NULL DEFAULT 'professional',
    content       TEXT NOT NULL,
    model_used    TEXT,
    generated_by  TEXT NOT NULL DEFAULT 'llm' CHECK (generated_by IN ('llm','template')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_proposal_job ON proposal (job_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Scan audit trail (what each on-demand scan actually did).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scan_run (
    id             SERIAL PRIMARY KEY,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    sources_run    JSONB NOT NULL DEFAULT '[]'::jsonb,
    jobs_fetched   INTEGER NOT NULL DEFAULT 0,
    jobs_new       INTEGER NOT NULL DEFAULT 0,
    jobs_updated   INTEGER NOT NULL DEFAULT 0,
    jobs_embedded  INTEGER NOT NULL DEFAULT 0,
    jobs_ranked    INTEGER NOT NULL DEFAULT 0,
    errors         JSONB NOT NULL DEFAULT '[]'::jsonb,
    status         TEXT NOT NULL DEFAULT 'running'
                   CHECK (status IN ('running','completed','failed'))
);

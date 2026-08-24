"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import SessionLocal, engine, init_extensions
from app.models import Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("jobfndr")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # pgvector must exist before create_all builds tables with Vector columns.
    init_extensions()
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        from app.services import job_fetch_service, profile_service

        profile_service.bootstrap(db)
        job_fetch_service.ensure_sources_registered(db)

    # Load the embedding model once, at startup, rather than on first request.
    try:
        from app.core.embeddings import warmup

        warmup()
    except Exception:  # noqa: BLE001 - the API is still useful without it
        logger.exception("Embedding model failed to load; semantic scoring disabled")

    logger.info("JobFndr backend ready")
    yield


app = FastAPI(
    title="JobFndr API",
    version="1.0.0",
    description=(
        "Single-user job finding assistant: on-demand scanning of free public "
        "job APIs, hybrid rule + semantic ranking against a CV, and LLM-drafted "
        "application messages."
    ),
    lifespan=lifespan,
)

# In Docker the frontend is same-origin (nginx proxies /api), so CORS matters
# only for `vite dev` running on the host.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.routes import analytics, health, jobs, profile, proposals, sources  # noqa: E402

API_PREFIX = "/api"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(profile.router, prefix=API_PREFIX)
app.include_router(jobs.router, prefix=API_PREFIX)
app.include_router(proposals.router, prefix=API_PREFIX)
app.include_router(sources.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)


@app.get("/")
def root() -> dict:
    return {"name": "JobFndr API", "docs": "/docs", "health": "/api/health"}

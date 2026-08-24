"""Profile and CV endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.serializers import profile_out
from app.repositories import profile_repo
from app.schemas.models import CvUploadResult, ProfileOut, ProfileUpdate
from app.services import job_fetch_service, profile_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profile", tags=["profile"])

MAX_CV_BYTES = 10 * 1024 * 1024


@router.get("", response_model=ProfileOut)
def read_profile(db: Session = Depends(get_db)) -> ProfileOut:
    return profile_out(profile_service.bootstrap(db))


@router.put("", response_model=ProfileOut)
def update_profile(payload: ProfileUpdate, db: Session = Depends(get_db)) -> ProfileOut:
    profile_service.bootstrap(db)
    fields = payload.model_dump(exclude_none=True, exclude={"reembed"})
    profile = profile_repo.update(db, fields)

    # Preferences feed the ranker, so a change invalidates every stored score.
    if payload.reembed:
        profile_service.refresh_embedding(db, profile)
        db.commit()
        job_fetch_service.rank_all(db, profile)

    db.commit()
    db.refresh(profile)
    return profile_out(profile)


@router.post("/cv", response_model=CvUploadResult, status_code=status.HTTP_201_CREATED)
async def upload_cv(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> CvUploadResult:
    filename = file.filename or "cv.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDF CVs are supported")

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")
    if len(data) > MAX_CV_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "CV exceeds 10 MB")

    try:
        profile, parsed = profile_service.ingest_cv(db, filename, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    warnings: list[str] = []
    if not parsed.skills:
        warnings.append("No skills were recognised — add them manually below.")
    if not parsed.experience:
        warnings.append("No work experience was parsed — add entries manually below.")
    if not parsed.languages:
        warnings.append("No languages were parsed.")

    # A new CV changes what 'me' means, so every existing job must be re-scored.
    job_fetch_service.rank_all(db, profile)

    return CvUploadResult(
        profile=profile_out(profile), parsed=parsed.to_dict(), warnings=warnings
    )

"""Proposal drafting endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories import proposals_repo
from app.schemas.models import ProposalOut, ProposalRequest, ProposalResponse
from app.services import proposal_service
from app.services.llm import client as llm

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proposals"])


@router.post("/jobs/{job_id}/proposal", response_model=ProposalResponse)
async def create_proposal(
    job_id: int, payload: ProposalRequest, db: Session = Depends(get_db)
) -> ProposalResponse:
    try:
        proposal, meta = await proposal_service.generate(
            db, job_id, payload.tone, payload.extra_instructions
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    return ProposalResponse(proposal=ProposalOut.model_validate(proposal), meta=meta)


@router.get("/jobs/{job_id}/proposal", response_model=ProposalOut | None)
def latest_proposal(job_id: int, db: Session = Depends(get_db)) -> ProposalOut | None:
    proposal = proposals_repo.latest_for_job(db, job_id)
    return ProposalOut.model_validate(proposal) if proposal else None


@router.get("/jobs/{job_id}/proposals", response_model=list[ProposalOut])
def proposal_history(job_id: int, db: Session = Depends(get_db)) -> list[ProposalOut]:
    return [
        ProposalOut.model_validate(p) for p in proposals_repo.history_for_job(db, job_id)
    ]


@router.get("/llm/status", response_model=dict)
def llm_status() -> dict:
    return llm.provider_status()

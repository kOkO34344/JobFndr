"""ATS job-board API adapters.

Greenhouse, Lever and Ashby all expose the *public* job board of a company as
JSON with no key. Each adapter takes a list of board tokens from its source
config, so following a new company is a one-line config change.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.config import settings
from app.services.normalizer import RawJob
from app.services.sources.base import JobSourceAdapter, SourceError, parse_timestamp

logger = logging.getLogger(__name__)

# Companies that plausibly hire for AI annotation / evaluation / trust & safety
# and publish an open board. Edit these lists (or the DB row) to follow others.
DEFAULT_GREENHOUSE_BOARDS = ["anthropic", "scaleai", "labelbox", "discord", "duolingo"]
DEFAULT_LEVER_BOARDS = ["appen", "spotify", "palantir"]
DEFAULT_ASHBY_BOARDS = ["openai", "mercor", "replit", "handshake"]


class _MultiBoardAdapter(JobSourceAdapter):
    """Shared fan-out logic: one HTTP call per board, failures isolated."""

    config_key = "boards"
    default_boards: list[str] = []

    def board_url(self, board: str) -> str:
        raise NotImplementedError

    def parse_board(self, board: str, payload) -> list[RawJob]:
        raise NotImplementedError

    async def fetch(self, client: httpx.AsyncClient, config: dict) -> list[RawJob]:
        boards = config.get(self.config_key) or self.default_boards
        if not boards:
            return []

        async def one(board: str) -> list[RawJob]:
            try:
                payload = await self._get_json(client, self.board_url(board))
                return self.parse_board(board, payload)
            except SourceError as exc:
                # A renamed or private board must not fail the other boards.
                logger.info("%s: skipping board '%s': %s", self.name, board, exc)
                return []

        results = await asyncio.gather(*(one(b) for b in boards))
        jobs = _interleave(results)
        if not jobs and boards:
            raise SourceError(
                f"{self.name}: no jobs returned from any of {len(boards)} boards"
            )
        return jobs[: settings.max_jobs_per_source]


class GreenhouseSource(_MultiBoardAdapter):
    name = "greenhouse"
    display_name = "Greenhouse boards"
    type = "ats"
    base_url = "https://boards-api.greenhouse.io"
    api_endpoint = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    rate_limit_info = "Public board API, no key. One request per configured board."
    default_boards = DEFAULT_GREENHOUSE_BOARDS

    def board_url(self, board: str) -> str:
        return f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"

    def parse_board(self, board: str, payload) -> list[RawJob]:
        jobs: list[RawJob] = []
        for item in payload.get("jobs") or []:
            location = (item.get("location") or {}).get("name")
            jobs.append(
                RawJob(
                    external_id=f"{board}:{item.get('id')}",
                    title=(item.get("title") or "").strip(),
                    url=item.get("absolute_url", ""),
                    company=board.replace("-", " ").title(),
                    location=location,
                    description=item.get("content", ""),
                    tags=[d.get("name", "") for d in (item.get("departments") or [])],
                    posted_at=parse_timestamp(item.get("updated_at") or item.get("created_at")),
                )
            )
        return jobs


class LeverSource(_MultiBoardAdapter):
    name = "lever"
    display_name = "Lever boards"
    type = "ats"
    base_url = "https://api.lever.co"
    api_endpoint = "https://api.lever.co/v0/postings/{board}?mode=json"
    rate_limit_info = "Public postings API, no key. One request per configured board."
    default_boards = DEFAULT_LEVER_BOARDS

    def board_url(self, board: str) -> str:
        return f"https://api.lever.co/v0/postings/{board}?mode=json"

    def parse_board(self, board: str, payload) -> list[RawJob]:
        if not isinstance(payload, list):
            return []
        jobs: list[RawJob] = []
        for item in payload:
            categories = item.get("categories") or {}
            commitment = categories.get("commitment") or ""
            jobs.append(
                RawJob(
                    external_id=f"{board}:{item.get('id')}",
                    title=(item.get("text") or "").strip(),
                    url=item.get("hostedUrl") or item.get("applyUrl", ""),
                    company=board.replace("-", " ").title(),
                    location=categories.get("location"),
                    description=item.get("descriptionPlain") or item.get("description", ""),
                    tags=[v for v in (categories.get("team"), categories.get("department"),
                                      commitment) if v],
                    posted_at=parse_timestamp(item.get("createdAt")),
                    format_hint=_commitment_to_format(commitment),
                )
            )
        return jobs


class AshbySource(_MultiBoardAdapter):
    name = "ashby"
    display_name = "Ashby boards"
    type = "ats"
    base_url = "https://api.ashbyhq.com"
    api_endpoint = "https://api.ashbyhq.com/posting-api/job-board/{board}"
    rate_limit_info = "Public posting API, no key. One request per configured board."
    default_boards = DEFAULT_ASHBY_BOARDS

    def board_url(self, board: str) -> str:
        return f"https://api.ashbyhq.com/posting-api/job-board/{board}"

    def parse_board(self, board: str, payload) -> list[RawJob]:
        jobs: list[RawJob] = []
        for item in payload.get("jobs") or []:
            employment = item.get("employmentType") or ""
            jobs.append(
                RawJob(
                    external_id=f"{board}:{item.get('id')}",
                    title=(item.get("title") or "").strip(),
                    url=item.get("jobUrl") or item.get("applyUrl", ""),
                    company=payload.get("name") or board.title(),
                    location=item.get("location"),
                    description=item.get("descriptionHtml") or item.get("descriptionPlain", ""),
                    tags=[v for v in (item.get("department"), item.get("team"), employment) if v],
                    posted_at=parse_timestamp(item.get("publishedAt")),
                    remote_hint=item.get("isRemote"),
                    format_hint=_commitment_to_format(employment),
                )
            )
        return jobs


def _interleave(groups: list[list[RawJob]]) -> list[RawJob]:
    """Round-robin the boards together.

    Concatenating instead would let one large board (Anthropic alone posts 500+)
    consume the whole per-source cap and starve every board after it.
    """
    merged: list[RawJob] = []
    for index in range(max((len(g) for g in groups), default=0)):
        for group in groups:
            if index < len(group):
                merged.append(group[index])
    return merged


def _commitment_to_format(value: str) -> str | None:
    text = (value or "").lower().replace("_", " ")
    if not text:
        return None
    if any(k in text for k in ("contract", "freelance", "temporary")):
        return "freelance"
    if "part" in text:
        return "part-time"
    if "full" in text:
        return "full-time"
    return None

"""Public job-board API adapters (no key required)."""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.services.normalizer import RawJob
from app.services.sources.base import JobSourceAdapter, SourceError, parse_timestamp


class ArbeitnowSource(JobSourceAdapter):
    """Arbeitnow's open job-board API. Free, documented, no key, paginated."""

    name = "arbeitnow"
    display_name = "Arbeitnow"
    type = "api"
    base_url = "https://www.arbeitnow.com"
    api_endpoint = "https://www.arbeitnow.com/api/job-board-api"
    rate_limit_info = "Public API, no key. Fetched only on demand; max 5 pages per scan."

    async def fetch(self, client: httpx.AsyncClient, config: dict) -> list[RawJob]:
        jobs: list[RawJob] = []
        max_pages = int(config.get("max_pages", 5))

        for page in range(1, max_pages + 1):
            payload = await self._get_json(
                client, self.api_endpoint, params={"page": page}
            )
            entries = payload.get("data") or []
            if not entries:
                break

            for item in entries:
                job_types = item.get("job_types") or []
                jobs.append(
                    RawJob(
                        external_id=item.get("slug") or item.get("url", ""),
                        title=item.get("title", "").strip(),
                        url=item.get("url", ""),
                        company=item.get("company_name"),
                        location=item.get("location"),
                        description=item.get("description", ""),
                        tags=list(item.get("tags") or []) + list(job_types),
                        posted_at=parse_timestamp(item.get("created_at")),
                        remote_hint=bool(item.get("remote")),
                        format_hint=_format_from_types(job_types),
                    )
                )
            if len(jobs) >= settings.max_jobs_per_source:
                break

        return jobs[: settings.max_jobs_per_source]


class RemotiveSource(JobSourceAdapter):
    """Remotive's public remote-jobs API. Everything here is remote by definition."""

    name = "remotive"
    display_name = "Remotive"
    type = "api"
    base_url = "https://remotive.com"
    api_endpoint = "https://remotive.com/api/remote-jobs"
    rate_limit_info = (
        "Remotive asks integrators to cache results and avoid frequent polling. "
        "Only called on an explicit scan."
    )
    attribution = "Job data from Remotive (remotive.com)"

    async def fetch(self, client: httpx.AsyncClient, config: dict) -> list[RawJob]:
        params: dict = {"limit": min(int(config.get("limit", 150)), settings.max_jobs_per_source)}
        if category := config.get("category"):
            params["category"] = category
        if search := config.get("search"):
            params["search"] = search

        payload = await self._get_json(client, self.api_endpoint, params=params)
        jobs: list[RawJob] = []

        for item in payload.get("jobs") or []:
            jobs.append(
                RawJob(
                    external_id=str(item.get("id")),
                    title=(item.get("title") or "").strip(),
                    url=item.get("url", ""),
                    company=item.get("company_name"),
                    location=item.get("candidate_required_location") or "Remote",
                    description=item.get("description", ""),
                    tags=list(item.get("tags") or []) + [item.get("category") or ""],
                    salary_text=item.get("salary") or None,
                    posted_at=parse_timestamp(item.get("publication_date")),
                    remote_hint=True,
                    format_hint=_format_from_types([item.get("job_type") or ""]),
                )
            )
        return jobs


class RemoteOkSource(JobSourceAdapter):
    """RemoteOK's public JSON feed.

    Their terms require attribution and a link back to the original posting;
    `attribution` is surfaced in the UI and every job keeps its source URL.
    """

    name = "remoteok"
    display_name = "RemoteOK"
    type = "api"
    base_url = "https://remoteok.com"
    api_endpoint = "https://remoteok.com/api"
    rate_limit_info = "Public feed. RemoteOK asks for attribution and a link back."
    attribution = "Job data from RemoteOK (remoteok.com)"

    async def fetch(self, client: httpx.AsyncClient, config: dict) -> list[RawJob]:
        payload = await self._get_json(client, self.api_endpoint)
        if not isinstance(payload, list):
            raise SourceError("remoteok: expected a JSON array")

        jobs: list[RawJob] = []
        for item in payload:
            # The feed's first element is a legal/attribution notice, not a job.
            if not isinstance(item, dict) or not item.get("id") or item.get("legal"):
                continue
            jobs.append(
                RawJob(
                    external_id=str(item.get("id")),
                    title=(item.get("position") or item.get("title") or "").strip(),
                    url=item.get("url") or item.get("apply_url", ""),
                    company=item.get("company"),
                    location=item.get("location") or "Remote",
                    description=item.get("description", ""),
                    tags=list(item.get("tags") or []),
                    salary_text=_salary_text(item),
                    posted_at=parse_timestamp(item.get("epoch") or item.get("date")),
                    remote_hint=True,
                )
            )
        return jobs[: settings.max_jobs_per_source]


class HimalayasSource(JobSourceAdapter):
    """Himalayas' public remote-jobs API."""

    name = "himalayas"
    display_name = "Himalayas"
    type = "api"
    base_url = "https://himalayas.app"
    api_endpoint = "https://himalayas.app/jobs/api"
    rate_limit_info = "Public API, no key. On-demand only."
    attribution = "Job data from Himalayas (himalayas.app)"

    async def fetch(self, client: httpx.AsyncClient, config: dict) -> list[RawJob]:
        limit = min(int(config.get("limit", 100)), settings.max_jobs_per_source)
        payload = await self._get_json(client, self.api_endpoint, params={"limit": limit})
        jobs: list[RawJob] = []

        for item in payload.get("jobs") or []:
            locations = item.get("locationRestrictions") or []
            jobs.append(
                RawJob(
                    external_id=str(item.get("guid") or item.get("id") or item.get("applicationLink")),
                    title=(item.get("title") or "").strip(),
                    url=item.get("applicationLink") or item.get("url", ""),
                    company=item.get("companyName"),
                    location=", ".join(locations) if locations else "Remote",
                    description=item.get("description") or item.get("excerpt", ""),
                    tags=list(item.get("categories") or []) + list(item.get("seniority") or []),
                    posted_at=parse_timestamp(item.get("pubDate")),
                    remote_hint=True,
                )
            )
        return jobs


def _format_from_types(job_types: list[str]) -> str | None:
    """Map a source's own contract-type labels onto our four formats."""
    joined = " ".join(t.lower().replace("_", " ") for t in job_types if t)
    if not joined:
        return None
    if any(k in joined for k in ("freelance", "contract", "temporary")):
        return "freelance"
    if "part" in joined:
        return "part-time"
    if any(k in joined for k in ("full time", "full-time", "permanent")):
        return "full-time"
    if "intern" in joined:
        return "full-time"
    return None


def _salary_text(item: dict) -> str | None:
    low, high = item.get("salary_min"), item.get("salary_max")
    if low and high:
        return f"${int(low):,} - ${int(high):,}"
    return item.get("salary") or None

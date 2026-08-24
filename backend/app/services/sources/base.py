"""Adapter contract for job sources."""
from __future__ import annotations

import abc
import logging
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.services.normalizer import RawJob
from app.services.sources import robots

logger = logging.getLogger(__name__)


class SourceError(RuntimeError):
    """Raised when a source cannot be fetched. Never aborts a whole scan."""


class JobSourceAdapter(abc.ABC):
    """One job board / ATS / feed.

    Adding a source means subclassing this and registering it — the fetch
    service, normalizer and ranker need no changes.
    """

    name: str = "base"
    display_name: str = "Base"
    type: str = "api"
    base_url: str = ""
    api_endpoint: str | None = None
    rate_limit_info: str = "Unspecified; requests are issued sparingly on demand."
    # Terms that must be shown to the user when results are displayed.
    attribution: str | None = None
    # Whether this adapter hits HTML pages (and therefore must pass robots.txt).
    needs_robots_check: bool = False

    @abc.abstractmethod
    async def fetch(self, client: httpx.AsyncClient, config: dict) -> list[RawJob]:
        """Return raw jobs. Raise SourceError on unrecoverable failure."""

    async def _get_json(self, client: httpx.AsyncClient, url: str, **kwargs):
        if self.needs_robots_check and not await robots.is_allowed(url, client):
            raise SourceError(f"robots.txt disallows fetching {url}")
        try:
            response = await client.get(url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise SourceError(
                f"{self.name}: HTTP {exc.response.status_code} for {url}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SourceError(f"{self.name}: request failed for {url}: {exc}") from exc
        except ValueError as exc:
            raise SourceError(f"{self.name}: response was not valid JSON: {exc}") from exc

    async def _get_text(self, client: httpx.AsyncClient, url: str, **kwargs) -> str:
        if self.needs_robots_check and not await robots.is_allowed(url, client):
            raise SourceError(f"robots.txt disallows fetching {url}")
        try:
            response = await client.get(url, **kwargs)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as exc:
            raise SourceError(
                f"{self.name}: HTTP {exc.response.status_code} for {url}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SourceError(f"{self.name}: request failed for {url}: {exc}") from exc

    def to_source_row(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "type": self.type,
            "base_url": self.base_url,
            "api_endpoint": self.api_endpoint,
            "rate_limit_info": self.rate_limit_info,
        }


def parse_timestamp(value) -> datetime | None:
    """Best-effort timestamp parsing across the formats sources actually use."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return parse_timestamp(int(text))
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z"):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def build_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
        headers={
            "User-Agent": settings.http_user_agent,
            "Accept": "application/json, text/html;q=0.8",
        },
    )

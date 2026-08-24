"""robots.txt gate shared by every HTTP fetch.

Politeness here is a hard requirement, not a nicety: the app is only allowed to
use free public APIs and scraping that the target site permits. Every adapter
routes through `is_allowed` before issuing a request.
"""
from __future__ import annotations

import logging
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# origin -> (parser | None, fetched_at). None means robots.txt was unreachable.
_CACHE: dict[str, tuple[RobotFileParser | None, float]] = {}
_TTL_SECONDS = 3600.0


def _origin(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}"


async def _load_robots(origin: str, client: httpx.AsyncClient) -> RobotFileParser | None:
    cached = _CACHE.get(origin)
    if cached and (time.monotonic() - cached[1]) < _TTL_SECONDS:
        return cached[0]

    parser: RobotFileParser | None = None
    try:
        response = await client.get(f"{origin}/robots.txt", timeout=10.0)
        if response.status_code == 200:
            parser = RobotFileParser()
            parser.parse(response.text.splitlines())
        elif response.status_code in (401, 403):
            # An access-controlled robots.txt means "stay out".
            parser = RobotFileParser()
            parser.disallow_all = True
        # 404 -> no robots.txt -> nothing is disallowed; leave parser as None.
    except Exception as exc:  # noqa: BLE001 - network failure is not fatal
        logger.warning("robots.txt fetch failed for %s: %s", origin, exc)

    _CACHE[origin] = (parser, time.monotonic())
    return parser


async def is_allowed(url: str, client: httpx.AsyncClient) -> bool:
    """True if our user agent may fetch `url`."""
    if not settings.respect_robots:
        return True
    parser = await _load_robots(_origin(url), client)
    if parser is None:
        return True
    return parser.can_fetch(settings.http_user_agent, url)


async def crawl_delay(url: str, client: httpx.AsyncClient) -> float:
    """Site-requested delay between requests, defaulting to a polite 1s."""
    if not settings.respect_robots:
        return 0.0
    parser = await _load_robots(_origin(url), client)
    if parser is None:
        return 1.0
    delay = parser.crawl_delay(settings.http_user_agent)
    return float(delay) if delay else 1.0


def clear_cache() -> None:
    _CACHE.clear()

"""RSS and polite-HTML adapters.

Both are generic and driven entirely by the source's DB config, so a new feed
or a new (permitted) page is a config row rather than new code. Both check
robots.txt and honour any declared crawl-delay.
"""
from __future__ import annotations

import asyncio
import logging
from xml.etree import ElementTree

import httpx

from app.core.config import settings
from app.services.normalizer import RawJob
from app.services.sources import robots
from app.services.sources.base import JobSourceAdapter, SourceError, parse_timestamp

logger = logging.getLogger(__name__)

# Publicly syndicated job feeds. RSS exists to be consumed, so this is the
# most clearly permitted form of "scraping" available.
DEFAULT_FEEDS = [
    {"url": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
     "company_from_title": True},
    {"url": "https://weworkremotely.com/categories/remote-customer-support-jobs.rss",
     "company_from_title": True},
]

_ATOM = "{http://www.w3.org/2005/Atom}"


class RssSource(JobSourceAdapter):
    """Generic RSS/Atom reader."""

    name = "rss"
    display_name = "RSS feeds"
    type = "rss"
    base_url = "https://weworkremotely.com"
    rate_limit_info = "Public RSS feeds, fetched once per scan with a crawl delay."
    needs_robots_check = True
    attribution = "Includes listings syndicated via public RSS feeds."

    async def fetch(self, client: httpx.AsyncClient, config: dict) -> list[RawJob]:
        feeds = config.get("feeds") or DEFAULT_FEEDS
        jobs: list[RawJob] = []
        errors: list[str] = []

        for index, feed in enumerate(feeds):
            url = feed.get("url") if isinstance(feed, dict) else str(feed)
            if not url:
                continue
            if index:
                await asyncio.sleep(await robots.crawl_delay(url, client))
            try:
                xml = await self._get_text(client, url)
                jobs.extend(self._parse_feed(xml, feed if isinstance(feed, dict) else {}))
            except (SourceError, ElementTree.ParseError) as exc:
                errors.append(f"{url}: {exc}")
                logger.info("rss: skipping %s: %s", url, exc)

        if not jobs and errors:
            raise SourceError("; ".join(errors[:3]))
        return jobs[: settings.max_jobs_per_source]

    def _parse_feed(self, xml: str, feed_config: dict) -> list[RawJob]:
        root = ElementTree.fromstring(xml)
        items = root.findall(".//item") or root.findall(f".//{_ATOM}entry")
        jobs: list[RawJob] = []

        for item in items:
            title = _text(item, "title") or _text(item, f"{_ATOM}title") or ""
            link = _text(item, "link") or _link_from_atom(item) or ""
            if not title or not link:
                continue

            company = None
            # WeWorkRemotely-style feeds use "Company: Role" in the title.
            if feed_config.get("company_from_title", True) and ":" in title:
                company, _, remainder = title.partition(":")
                company, title = company.strip(), remainder.strip() or title

            jobs.append(
                RawJob(
                    external_id=_text(item, "guid") or link,
                    title=title,
                    url=link,
                    company=company,
                    location=_text(item, "region") or feed_config.get("location") or "Remote",
                    description=(
                        _text(item, "description")
                        or _text(item, f"{_ATOM}summary")
                        or _text(item, f"{_ATOM}content")
                        or ""
                    ),
                    tags=[c.text.strip() for c in item.findall("category") if c.text],
                    posted_at=parse_timestamp(
                        _text(item, "pubDate") or _text(item, f"{_ATOM}published")
                    ),
                    remote_hint=feed_config.get("remote", True),
                )
            )
        return jobs


class PoliteHtmlSource(JobSourceAdapter):
    """CSS-selector scraper for pages that permit it.

    Ships disabled (no targets configured). Add entries to the source's config
    to enable, e.g.:
        {"targets": [{"url": "...", "item": ".job", "title": ".t", "link": "a"}]}
    Every request is gated on robots.txt and spaced by the declared crawl-delay.
    """

    name = "html"
    display_name = "HTML (robots-checked)"
    type = "scraping"
    base_url = ""
    rate_limit_info = "robots.txt enforced; crawl-delay honoured; on-demand only."
    needs_robots_check = True

    async def fetch(self, client: httpx.AsyncClient, config: dict) -> list[RawJob]:
        targets = config.get("targets") or []
        if not targets:
            return []

        from bs4 import BeautifulSoup

        jobs: list[RawJob] = []
        for index, target in enumerate(targets):
            url = target.get("url")
            if not url:
                continue
            if index:
                await asyncio.sleep(await robots.crawl_delay(url, client))

            try:
                html = await self._get_text(client, url)
            except SourceError as exc:
                logger.info("html: skipping %s: %s", url, exc)
                continue

            soup = BeautifulSoup(html, "html.parser")
            for node in soup.select(target.get("item", "article"))[:100]:
                title_node = node.select_one(target["title"]) if target.get("title") else node
                link_node = node.select_one(target.get("link", "a"))
                href = link_node.get("href") if link_node else None
                if not title_node or not href:
                    continue
                if href.startswith("/"):
                    href = url.split("/", 3)[0] + "//" + url.split("/")[2] + href

                company_node = (
                    node.select_one(target["company"]) if target.get("company") else None
                )
                jobs.append(
                    RawJob(
                        external_id=href,
                        title=title_node.get_text(strip=True),
                        url=href,
                        company=company_node.get_text(strip=True) if company_node else
                        target.get("company_name"),
                        location=target.get("location"),
                        description=node.get_text(" ", strip=True),
                        remote_hint=target.get("remote"),
                    )
                )
        return jobs[: settings.max_jobs_per_source]


def _text(item, tag: str) -> str | None:
    node = item.find(tag)
    return node.text.strip() if node is not None and node.text else None


def _link_from_atom(item) -> str | None:
    node = item.find(f"{_ATOM}link")
    return node.get("href") if node is not None else None

"""Registry of every available job source adapter."""
from __future__ import annotations

from app.services.sources.ats import AshbySource, GreenhouseSource, LeverSource
from app.services.sources.base import JobSourceAdapter
from app.services.sources.boards import (
    ArbeitnowSource,
    HimalayasSource,
    RemoteOkSource,
    RemotiveSource,
)
from app.services.sources.feeds import PoliteHtmlSource, RssSource

ADAPTERS: tuple[JobSourceAdapter, ...] = (
    ArbeitnowSource(),
    RemotiveSource(),
    RemoteOkSource(),
    HimalayasSource(),
    GreenhouseSource(),
    LeverSource(),
    AshbySource(),
    RssSource(),
    PoliteHtmlSource(),
)

ADAPTER_BY_NAME: dict[str, JobSourceAdapter] = {a.name: a for a in ADAPTERS}


def get_adapter(name: str) -> JobSourceAdapter | None:
    return ADAPTER_BY_NAME.get(name)


def attributions() -> list[str]:
    return [a.attribution for a in ADAPTERS if a.attribution]

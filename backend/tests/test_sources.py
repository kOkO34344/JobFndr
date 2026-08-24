"""Source adapter unit tests. No network: adapters are fed recorded payloads."""
import pytest

from app.services.normalizer import normalize
from app.services.sources.ats import _interleave
from app.services.sources.base import parse_timestamp
from app.services.sources.boards import (
    ArbeitnowSource,
    RemoteOkSource,
    RemotiveSource,
    _format_from_types,
)
from app.services.sources.registry import ADAPTER_BY_NAME, ADAPTERS


class FakeAdapter:
    """Stands in for the HTTP layer by returning a canned payload."""

    def __init__(self, adapter, payload):
        self.adapter = adapter
        self.payload = payload

    async def _get_json(self, client, url, **kwargs):
        return self.payload


def bind(adapter, payload):
    adapter._get_json = FakeAdapter(adapter, payload)._get_json
    return adapter


class TestRegistry:
    def test_every_adapter_has_a_unique_name(self):
        names = [a.name for a in ADAPTERS]
        assert len(names) == len(set(names))

    def test_lookup_by_name(self):
        assert ADAPTER_BY_NAME["arbeitnow"].display_name == "Arbeitnow"
        assert ADAPTER_BY_NAME.get("nope") is None

    def test_scraping_adapters_check_robots(self):
        for adapter in ADAPTERS:
            if adapter.type in ("scraping", "rss"):
                assert adapter.needs_robots_check, f"{adapter.name} must respect robots.txt"

    def test_source_row_is_complete(self):
        for adapter in ADAPTERS:
            row = adapter.to_source_row()
            assert row["name"] and row["display_name"] and row["type"]


class TestTimestamps:
    def test_iso_with_z(self):
        assert parse_timestamp("2026-08-01T12:00:00Z").year == 2026

    def test_unix_epoch(self):
        assert parse_timestamp(1754006400).year == 2025

    def test_rfc_822(self):
        assert parse_timestamp("Fri, 01 Aug 2026 09:00:00 +0000").month == 8

    def test_garbage_returns_none(self):
        assert parse_timestamp("not a date") is None
        assert parse_timestamp(None) is None
        assert parse_timestamp("") is None


class TestFormatMapping:
    @pytest.mark.parametrize(
        "types,expected",
        [
            (["contract"], "freelance"),
            (["FULL_TIME"], "full-time"),
            (["part_time"], "part-time"),
            (["freelance"], "freelance"),
            ([], None),
            (["something odd"], None),
        ],
    )
    def test_mapping(self, types, expected):
        assert _format_from_types(types) == expected


class TestInterleave:
    def test_round_robins_boards(self):
        assert _interleave([["a1", "a2", "a3"], ["b1"], ["c1", "c2"]]) == [
            "a1", "b1", "c1", "a2", "c2", "a3",
        ]

    def test_large_board_cannot_starve_the_others(self):
        big = [f"big{i}" for i in range(500)]
        small = ["small1", "small2"]
        merged = _interleave([big, small])[:10]
        assert "small1" in merged and "small2" in merged

    def test_handles_empty_input(self):
        assert _interleave([]) == []
        assert _interleave([[], []]) == []


@pytest.mark.asyncio
class TestParsing:
    async def test_arbeitnow(self):
        adapter = bind(ArbeitnowSource(), {
            "data": [{
                "slug": "ai-annotator-123",
                "title": "AI Data Annotator",
                "company_name": "Acme",
                "location": "Remote",
                "description": "<p>Label data for <b>LLM</b> training.</p>",
                "url": "https://arbeitnow.com/view/ai-annotator-123",
                "remote": True,
                "tags": ["ai"],
                "job_types": ["contract"],
                "created_at": 1754006400,
            }]
        })
        jobs = await adapter.fetch(None, {"max_pages": 1})
        assert len(jobs) == 1
        job = normalize(jobs[0])
        assert job.remote_flag is True
        assert job.format == "freelance"
        assert "<b>" not in job.raw_description

    async def test_remotive(self):
        adapter = bind(RemotiveSource(), {
            "jobs": [{
                "id": 42,
                "title": "Content Moderator",
                "company_name": "Acme",
                "url": "https://remotive.com/x/42",
                "candidate_required_location": "Europe",
                "description": "Moderate content.",
                "tags": ["support"],
                "category": "Customer Service",
                "job_type": "part_time",
                "publication_date": "2026-08-01T09:00:00",
            }]
        })
        jobs = await adapter.fetch(None, {})
        assert jobs[0].external_id == "42"
        assert jobs[0].remote_hint is True
        assert jobs[0].format_hint == "part-time"

    async def test_remoteok_skips_the_legal_notice(self):
        adapter = bind(RemoteOkSource(), [
            {"legal": "See remoteok.com/api for terms"},
            {
                "id": "99",
                "position": "Junior Python Developer",
                "company": "Acme",
                "url": "https://remoteok.com/l/99",
                "description": "Build APIs.",
                "tags": ["python"],
                "epoch": 1754006400,
            },
        ])
        jobs = await adapter.fetch(None, {})
        assert len(jobs) == 1
        assert jobs[0].title == "Junior Python Developer"

    async def test_missing_fields_do_not_crash(self):
        adapter = bind(ArbeitnowSource(), {"data": [{"slug": "x", "title": "", "url": ""}]})
        jobs = await adapter.fetch(None, {"max_pages": 1})
        assert len(jobs) == 1  # emitted; the store step drops it for lacking a title

    async def test_empty_payload(self):
        adapter = bind(ArbeitnowSource(), {"data": []})
        assert await adapter.fetch(None, {"max_pages": 1}) == []

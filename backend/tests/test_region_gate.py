"""Region restriction gate. Every location string below came from a live scan."""
import pytest

from app.services.normalizer import detect_region_restriction
from app.services.ranking_service import JobView, ProfileView, apply_hard_filters

EU_BASED = ProfileView(
    domain_weights={"ai": 1.0},
    languages=["bulgarian", "english", "german"],
)


class TestDetection:
    @pytest.mark.parametrize(
        "location,expected",
        [
            ("Remote (USA)", "USA"),
            ("US - Remote", "USA"),
            ("Remote - Japan", "Japan"),
            ("Remote, India", "India"),
            ("Remote - LatAm", "LatAm"),
        ],
    )
    def test_restriction_is_read(self, location, expected):
        assert expected in detect_region_restriction(location)

    @pytest.mark.parametrize(
        "location",
        ["Anywhere in the World", "Worldwide", "Remote", "", None, "Global"],
    )
    def test_open_locations_are_unrestricted(self, location):
        assert detect_region_restriction(location) == set()

    def test_european_restriction_is_still_a_restriction(self):
        assert detect_region_restriction("Germany - Remote") == {"Germany"}


class TestGate:
    def _job(self, location):
        return JobView(
            title="AI Data Annotator",
            description="Annotate data.",
            seniority="junior",
            format="full-time",
            remote_flag=True,
            location=location,
        )

    @pytest.mark.parametrize("location", ["Remote (USA)", "US - Remote", "Remote - Japan"])
    def test_unreachable_regions_are_filtered(self, location):
        result = apply_hard_filters(self._job(location), EU_BASED)
        assert result.passed is False
        assert "restricted to" in result.reasons[0]

    @pytest.mark.parametrize(
        "location",
        ["Anywhere in the World", "Europe", "Germany - Remote", "Remote", "EMEA", "Remote - UK"],
    )
    def test_reachable_locations_pass(self, location):
        assert apply_hard_filters(self._job(location), EU_BASED).passed is True

    def test_gate_is_disabled_by_an_empty_allowlist(self):
        anywhere = ProfileView(domain_weights={"ai": 1.0}, allowed_regions=[])
        assert apply_hard_filters(self._job("Remote (USA)"), anywhere).passed is True

    def test_multi_region_posting_passes_if_one_is_reachable(self):
        job = self._job("Remote - USA, Europe")
        assert apply_hard_filters(job, EU_BASED).passed is True

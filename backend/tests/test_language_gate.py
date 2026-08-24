"""The language gate.

Localisation and voice-data vendors publish one role templated across dozens of
languages. The titles below are real ones that dominated the first live scan.
"""
import pytest

from app.services.normalizer import detect_required_languages
from app.services.ranking_service import (
    JobView,
    ProfileView,
    apply_hard_filters,
    compute_rule_score,
    rank_job,
)

KALOYAN = ProfileView(
    skills=["data annotation", "model evaluation"],
    domain_weights={"ai": 1.0, "trust_safety": 0.54, "policy": 0.6, "languages": 0.25},
    languages=["bulgarian", "english", "german"],
)


class TestDetection:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("[Russian-US] - Voice Recording Specialist", "russian"),
            ("[Croatian] - Voice Recording Specialist", "croatian"),
            ("[Russian - Georgia] - Voice Recording Specialist", "russian"),
            ("Translation Evaluator – Russian/English (Remote)", "russian"),
            ("Native Polish speaker for AI data collection", "polish"),
            ("Content Moderator - fluent in Turkish", "turkish"),
        ],
    )
    def test_requirement_is_detected(self, title, expected):
        assert expected in detect_required_languages(title, "")

    def test_passing_mention_is_not_a_requirement(self):
        # A language named deep in a perks list must not gate the job out.
        text = "Great role. " + ("filler. " * 300) + "We also offer Spanish classes."
        assert detect_required_languages("Data Annotator", text) == set()

    def test_no_language_mentioned(self):
        assert detect_required_languages("Junior Python Developer", "Write APIs.") == set()


class TestGate:
    def test_unspoken_language_is_filtered_out(self):
        job = JobView(
            title="[Croatian] - Voice Recording Specialist",
            description="Record voice samples in your native language.",
            seniority="other",
            format="freelance",
            remote_flag=True,
        )
        result = apply_hard_filters(job, KALOYAN)
        assert result.passed is False
        assert "Croatian" in result.reasons[0]

    def test_spoken_language_passes(self):
        job = JobView(
            title="[Bulgarian] - Voice Recording Specialist",
            description="Record voice samples in your native language.",
            seniority="other",
            format="freelance",
            remote_flag=True,
        )
        assert apply_hard_filters(job, KALOYAN).passed is True

    def test_translation_pair_requires_the_non_english_half(self):
        """"Russian/English" needs Russian; English is the pivot, not an option.
        This posting topped the first live scan despite being unreachable."""
        job = JobView(
            title="Translation Evaluator – Russian/English (Remote)",
            description="Evaluate translation quality.",
            seniority="other",
            format="freelance",
            remote_flag=True,
        )
        result = apply_hard_filters(job, KALOYAN)
        assert result.passed is False
        assert "Russian" in result.reasons[0]

    def test_multi_language_posting_passes_if_one_is_spoken(self):
        job = JobView(
            title="Translation Evaluator – Bulgarian/English",
            description="Evaluate translations.",
            seniority="other",
            format="freelance",
            remote_flag=True,
        )
        assert apply_hard_filters(job, KALOYAN).passed is True

    def test_gate_is_inert_without_a_profile_language_list(self):
        blank = ProfileView(domain_weights={"ai": 1.0})
        job = JobView(
            title="[Croatian] - Voice Recording Specialist",
            seniority="other",
            format="freelance",
            remote_flag=True,
        )
        assert apply_hard_filters(job, blank).passed is True


class TestBonus:
    def test_bulgarian_requirement_is_surfaced(self):
        job = JobView(
            title="Content Moderator - Native Bulgarian",
            description="Review Bulgarian-language content.",
            seniority="junior",
            format="full-time",
            remote_flag=True,
        )
        _, detail = compute_rule_score(job, KALOYAN)
        assert detail["language_bonus"] == "Bulgarian"

    def test_english_alone_is_not_a_bonus(self):
        job = JobView(
            title="Fluent English Data Annotator",
            description="Annotate English text.",
            seniority="junior",
            format="full-time",
            remote_flag=True,
        )
        _, detail = compute_rule_score(job, KALOYAN)
        assert detail["language_bonus"] is None


class TestRankingImpact:
    """The deck-flooding case, end to end."""

    def test_bulgarian_variant_outranks_every_unspoken_variant(self):
        def variant(language):
            return JobView(
                title=f"[{language}] - Voice Recording Specialist",
                description="Record voice samples in your native language. Freelance, remote.",
                seniority="other",
                format="freelance",
                remote_flag=True,
            )

        mine = rank_job(variant("Bulgarian"), KALOYAN, 0.42)
        others = [
            rank_job(variant(lang), KALOYAN, 0.42)
            for lang in ("Russian", "Croatian", "Danish", "Finnish", "Czech", "Polish", "Greek")
        ]

        assert mine.passed_filters is True
        assert all(o.passed_filters is False for o in others)
        assert mine.final_score > max(o.final_score for o in others) * 2


class TestRoleTypePatterns:
    """A leading language on a localisation-style role is a requirement."""

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Remote Work From Home: Lao Voice Recording Project", "lao"),
            ("German Content Moderator", "german"),
            ("Bulgarian Transcription Specialist", "bulgarian"),
            ("Japanese Search Quality Rater", "japanese"),
        ],
    )
    def test_language_plus_role_type(self, title, expected):
        assert expected in detect_required_languages(title, "")

    @pytest.mark.parametrize(
        "title",
        ["Senior Python Developer", "Content Designer", "Trust & Safety Analyst"],
    )
    def test_ordinary_titles_are_untouched(self, title):
        assert detect_required_languages(title, "") == set()

    def test_lao_project_is_gated_out(self):
        job = JobView(
            title="Remote Work From Home: Lao Voice Recording Project",
            description="Record Lao speech samples.",
            seniority="other",
            format="freelance",
            remote_flag=True,
        )
        assert apply_hard_filters(job, KALOYAN).passed is False

    def test_german_project_passes(self):
        job = JobView(
            title="German Voice Recording Project",
            description="Record German speech samples.",
            seniority="other",
            format="freelance",
            remote_flag=True,
        )
        assert apply_hard_filters(job, KALOYAN).passed is True

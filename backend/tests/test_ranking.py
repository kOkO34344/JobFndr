import pytest

from app.services.ranking_service import (
    COMPONENT_WEIGHTS,
    JobView,
    ProfileView,
    apply_hard_filters,
    compute_rule_score,
    normalize_semantic,
    rank_job,
    score_seniority,
    score_skills,
)

KALOYAN = ProfileView(
    skills=[
        "prompt engineering", "data annotation", "model evaluation", "python",
        "content moderation", "policy analysis", "github",
    ],
    domain_weights={
        "ai": 1.0, "trust_safety": 0.95, "policy": 0.85,
        "tech": 0.8, "markets": 0.6, "admin": 0.4, "languages": 0.5,
    },
    preferred_seniority=["internship", "junior", "mid-level"],
    preferred_formats=["freelance", "part-time", "full-time"],
    remote_only=True,
)


def make_job(**kw) -> JobView:
    base = dict(
        title="Data Annotator",
        description="Annotate data.",
        tags=[],
        seniority="junior",
        format="full-time",
        remote_flag=True,
    )
    base.update(kw)
    return JobView(**base)


class TestComponentWeights:
    def test_weights_sum_to_one(self):
        assert sum(COMPONENT_WEIGHTS.values()) == pytest.approx(1.0)


class TestHardFilters:
    def test_remote_job_passes(self):
        assert apply_hard_filters(make_job(), KALOYAN).passed is True

    def test_onsite_job_rejected(self):
        result = apply_hard_filters(make_job(remote_flag=False), KALOYAN)
        assert result.passed is False
        assert "Not remote-friendly" in result.reasons

    def test_senior_role_rejected(self):
        result = apply_hard_filters(make_job(seniority="senior"), KALOYAN)
        assert result.passed is False
        assert any("senior" in r for r in result.reasons)

    def test_unknown_seniority_allowed_by_default(self):
        assert apply_hard_filters(make_job(seniority="other"), KALOYAN).passed is True

    def test_unknown_seniority_rejected_when_strict(self):
        strict = ProfileView(**{**KALOYAN.__dict__, "allow_unknown_seniority": False})
        assert apply_hard_filters(make_job(seniority="other"), strict).passed is False

    def test_multiple_failures_all_reported(self):
        result = apply_hard_filters(make_job(remote_flag=False, seniority="senior"), KALOYAN)
        assert len(result.reasons) == 2

    def test_non_remote_ok_when_not_remote_only(self):
        flexible = ProfileView(**{**KALOYAN.__dict__, "remote_only": False})
        assert apply_hard_filters(make_job(remote_flag=False), flexible).passed is True


class TestSeniorityScore:
    def test_preferred_first_choice_scores_highest(self):
        intern, _ = score_seniority(make_job(seniority="internship"), KALOYAN)
        mid, _ = score_seniority(make_job(seniority="mid-level"), KALOYAN)
        assert intern > mid

    def test_senior_scores_zero(self):
        score, _ = score_seniority(make_job(seniority="senior"), KALOYAN)
        assert score == 0.0

    def test_unstated_is_neutral(self):
        score, _ = score_seniority(make_job(seniority="other"), KALOYAN)
        assert score == 0.5


class TestSkillScore:
    def test_matches_are_found_case_insensitively(self):
        score, matched = score_skills(
            make_job(description="You will do Prompt Engineering and Data Annotation."),
            KALOYAN,
        )
        assert set(matched) == {"prompt engineering", "data annotation"}
        assert score == pytest.approx(0.4)

    def test_saturates_at_five(self):
        desc = "python prompt engineering data annotation model evaluation github policy analysis"
        score, matched = score_skills(make_job(description=desc), KALOYAN)
        assert len(matched) >= 5
        assert score == 1.0

    def test_no_skills_no_score(self):
        score, matched = score_skills(make_job(description="Drive a forklift."), KALOYAN)
        assert score == 0.0 and matched == []


class TestSemanticNormalisation:
    def test_floor_maps_to_zero(self):
        assert normalize_semantic(0.05) == 0.0

    def test_ceiling_maps_to_one(self):
        assert normalize_semantic(0.60) == 1.0

    def test_is_monotonic(self):
        assert normalize_semantic(0.2) < normalize_semantic(0.4)

    def test_clamps_out_of_band_values(self):
        assert normalize_semantic(-0.9) == 0.0
        assert normalize_semantic(0.99) == 1.0


class TestRuleScore:
    def test_ideal_job_scores_high(self):
        job = make_job(
            title="Freelance AI Data Annotation Specialist",
            description=(
                "Remote contract work on prompt engineering, data annotation and "
                "model evaluation for LLM training. Python experience welcome."
            ),
            seniority="junior",
            format="freelance",
        )
        score, detail = compute_rule_score(job, KALOYAN)
        assert score > 0.8
        assert detail["matched_domains"][0]["key"] == "ai"

    def test_irrelevant_job_scores_low(self):
        job = make_job(
            title="Remote Forklift Dispatch Coordinator",
            description="Coordinate forklift schedules in our depot network.",
        )
        score, _ = compute_rule_score(job, KALOYAN)
        assert score < 0.5

    def test_best_domain_dominates_over_many_weak_ones(self):
        focused = make_job(
            title="Trust & Safety Content Moderation Specialist",
            description="Policy enforcement and content moderation.",
        )
        scattered = make_job(
            title="Generalist Assistant",
            description="Some finance, some communication, some scheduling.",
        )
        focused_score, _ = compute_rule_score(focused, KALOYAN)
        scattered_score, _ = compute_rule_score(scattered, KALOYAN)
        assert focused_score > scattered_score


class TestRankJob:
    def test_scores_are_all_in_range(self):
        result = rank_job(make_job(), KALOYAN, cosine_similarity=0.3)
        for value in (result.rule_score, result.semantic_score, result.final_score):
            assert 0.0 <= value <= 1.0

    def test_weighting_is_respected(self):
        semantic_heavy = rank_job(make_job(), KALOYAN, 0.6, rule_weight=0.0, semantic_weight=1.0)
        assert semantic_heavy.final_score == pytest.approx(1.0)

    def test_filtered_job_is_demoted_not_dropped(self):
        good = make_job(
            title="Junior AI Data Annotator",
            description="Prompt engineering and data annotation, remote.",
        )
        same_but_onsite = make_job(
            title="Junior AI Data Annotator",
            description="Prompt engineering and data annotation, remote.",
            remote_flag=False,
        )
        passed = rank_job(good, KALOYAN, 0.4)
        failed = rank_job(same_but_onsite, KALOYAN, 0.4)
        assert failed.passed_filters is False
        assert failed.final_score < passed.final_score * 0.5
        assert failed.final_score > 0  # still stored and inspectable

    def test_explanation_is_complete(self):
        result = rank_job(
            make_job(title="Trust & Safety Analyst", description="Content moderation, remote."),
            KALOYAN,
            0.35,
        )
        exp = result.explanation
        for key in (
            "matched_domains", "matched_skills", "seniority", "format", "remote",
            "components", "rule_score", "semantic_score", "final_score",
            "weights", "filters", "summary",
        ):
            assert key in exp, f"missing {key}"
        assert isinstance(exp["summary"], str) and exp["summary"]

    def test_filtered_summary_states_the_reason(self):
        result = rank_job(make_job(remote_flag=False), KALOYAN, 0.3)
        assert "Filtered out" in result.explanation["summary"]

    def test_zero_weights_rejected(self):
        with pytest.raises(ValueError):
            rank_job(make_job(), KALOYAN, 0.3, rule_weight=0.0, semantic_weight=0.0)


class TestRankingOrder:
    """End-to-end demonstration: a realistic sample must sort sensibly."""

    SAMPLE = [
        ("AI Research Intern (Remote)",
         "Evaluate LLM outputs, annotate datasets, model evaluation. Internship.",
         "internship", "full-time", True, 0.52),
        ("Freelance Content Moderator - Bulgarian",
         "Trust and safety content moderation, policy enforcement. Native Bulgarian required.",
         "other", "freelance", True, 0.44),
        ("Junior EU Policy Analyst (Remote)",
         "Research European Union institutions and public policy for our think tank.",
         "junior", "full-time", True, 0.38),
        ("Part-time Crypto Market Analyst",
         "Analyse crypto and forex markets, write daily notes.",
         "junior", "part-time", True, 0.30),
        ("Senior Machine Learning Engineer",
         "Lead our ML platform team. 8+ years experience.",
         "senior", "full-time", True, 0.41),
        ("On-site Warehouse Supervisor",
         "Supervise depot staff in Plovdiv.",
         "other", "full-time", False, 0.06),
    ]

    def _ranked(self):
        scored = []
        for title, desc, sen, fmt, remote, cos in self.SAMPLE:
            job = JobView(title=title, description=desc, seniority=sen,
                          format=fmt, remote_flag=remote)
            scored.append((title, rank_job(job, KALOYAN, cos)))
        scored.sort(key=lambda x: x[1].final_score, reverse=True)
        return scored

    def test_ai_internship_ranks_first(self):
        assert "AI Research Intern" in self._ranked()[0][0]

    def test_filtered_jobs_sink_to_the_bottom(self):
        bottom_two = {t for t, _ in self._ranked()[-2:]}
        assert "Senior Machine Learning Engineer" in bottom_two
        assert "On-site Warehouse Supervisor" in bottom_two

    def test_every_relevant_job_beats_every_filtered_job(self):
        ranked = self._ranked()
        passed = [r.final_score for _, r in ranked if r.passed_filters]
        failed = [r.final_score for _, r in ranked if not r.passed_filters]
        assert min(passed) > max(failed)

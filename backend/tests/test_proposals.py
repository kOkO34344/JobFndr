"""Template proposal drafting (the no-API-key path)."""
from types import SimpleNamespace

import pytest

from app.services.proposal_service import (
    TONES,
    _join_list,
    _relevant_experience,
    build_prompt,
    build_template_proposal,
)


def make_profile(**kw):
    base = dict(
        name="Kaloyan Ivanov",
        location="Sofia, Bulgaria",
        headline="Political science student working in AI research.",
        languages=[
            {"name": "Bulgarian", "proficiency": "Native"},
            {"name": "English", "proficiency": "C1"},
            {"name": "German", "proficiency": "Basic"},
        ],
        education=[{"degree": "BA Political Science", "institution": "New Bulgarian University"}],
        experience=[
            {"role": "AI Research Intern", "company": "Sensika Technologies",
             "description": "Annotated datasets and evaluated LLM outputs.", "source": "cv"},
            {"role": "Receptionist", "company": "Griffin Hotels",
             "description": "Guest communication and reservations.", "source": "cv"},
            {"role": "Trust & Safety Specialist", "company": "Telus Digital",
             "description": "Content moderation and policy enforcement.", "source": "manual"},
        ],
        skills=["data annotation", "prompt engineering", "model evaluation"],
        preferred_roles=["AI data annotation"],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def make_job(**kw):
    base = dict(
        title="AI Data Annotation Specialist",
        company="Acme AI",
        location="Anywhere in the World",
        remote_flag=True,
        seniority="junior",
        format="freelance",
        category="AI & Coding",
        salary_text=None,
        tags=["ai"],
        raw_description="Annotate datasets and evaluate LLM outputs. Prompt engineering welcome.",
        match=SimpleNamespace(explanation={
            "summary": "Strong match.",
            "matched_domains": [{"key": "ai", "label": "AI & ML"}],
            "matched_skills": ["data annotation", "prompt engineering"],
        }),
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestJoinList:
    def test_single(self):
        assert _join_list(["a"]) == "a"

    def test_pair(self):
        assert _join_list(["a", "b"]) == "a and b"

    def test_three(self):
        assert _join_list(["a", "b", "c"]) == "a, b and c"


class TestRelevantExperience:
    def test_ai_job_picks_ai_roles_not_the_hotel_desk(self):
        picked = _relevant_experience(make_profile(), make_job())
        roles = [e["role"] for e in picked]
        assert "AI Research Intern" in roles
        assert "Receptionist" not in roles

    def test_support_job_picks_the_hospitality_role(self):
        job = make_job(
            title="Customer Support Agent",
            raw_description="Handle guest reservations, client support and scheduling.",
            tags=[],
        )
        roles = [e["role"] for e in _relevant_experience(make_profile(), job)]
        assert "Receptionist" in roles

    def test_trust_and_safety_job_picks_the_telus_role(self):
        job = make_job(
            title="Content Moderator",
            raw_description="Trust and safety content moderation and policy enforcement.",
            tags=[],
        )
        roles = [e["role"] for e in _relevant_experience(make_profile(), job)]
        assert "Trust & Safety Specialist" in roles

    def test_empty_experience(self):
        assert _relevant_experience(make_profile(experience=[]), make_job()) == []


class TestTemplateDraft:
    def test_contains_the_essentials(self):
        text = build_template_proposal(make_profile(), make_job(), "professional")
        assert "Acme AI" in text
        assert "AI Data Annotation Specialist" in text
        assert text.rstrip().endswith("Kaloyan Ivanov")

    def test_company_casing_is_preserved(self):
        text = build_template_proposal(make_profile(), make_job(), "professional")
        assert "Sensika Technologies" in text
        assert "sensika technologies" not in text

    def test_single_skill_grammar(self):
        job = make_job(match=SimpleNamespace(explanation={"matched_skills": ["data annotation"]}))
        text = build_template_proposal(make_profile(), job, "professional")
        assert "which I work with directly" in text
        assert "all of which" not in text

    def test_multiple_skill_grammar(self):
        text = build_template_proposal(make_profile(), make_job(), "professional")
        assert "all of which I work with directly" in text

    def test_direct_tone_uses_a_short_greeting(self):
        assert build_template_proposal(make_profile(), make_job(), "direct").startswith("Hello,")

    def test_no_match_data_still_produces_a_draft(self):
        job = make_job(match=None)
        text = build_template_proposal(make_profile(), job, "professional")
        assert len(text.split()) > 30

    def test_never_invents_a_placeholder_name(self):
        text = build_template_proposal(make_profile(), make_job(), "warm")
        assert "[Your Name]" not in text


class TestPrompt:
    def test_prompt_carries_profile_job_and_match(self):
        prompt = build_prompt(make_profile(), make_job(), "professional", None)
        assert "CANDIDATE PROFILE" in prompt
        assert "JOB POSTING" in prompt
        assert "WHY THIS WAS MATCHED" in prompt
        assert "Telus Digital" in prompt  # manual experience reaches the LLM
        assert TONES["professional"] in prompt

    def test_extra_instructions_are_included(self):
        prompt = build_prompt(make_profile(), make_job(), "warm", "Mention EU hours.")
        assert "Mention EU hours." in prompt

    def test_description_is_bounded(self):
        job = make_job(raw_description="x" * 20000)
        assert len(build_prompt(make_profile(), job, "direct", None)) < 12000

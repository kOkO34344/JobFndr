from datetime import datetime, timezone

from app.services.normalizer import (
    RawJob,
    detect_domains,
    detect_format,
    detect_remote,
    detect_seniority,
    normalize,
    strip_html,
)


class TestStripHtml:
    def test_removes_tags_and_entities(self):
        html = "<p>Hello <b>world</b>&nbsp;&amp; friends</p><script>evil()</script>"
        out = strip_html(html)
        assert "evil" not in out
        assert "Hello world & friends" in out

    def test_list_items_become_bullets(self):
        assert "•" in strip_html("<ul><li>One</li><li>Two</li></ul>")

    def test_empty_input(self):
        assert strip_html("") == ""


class TestSeniority:
    def test_internship_from_title(self):
        assert detect_seniority("AI Research Intern", "") == "internship"

    def test_working_student_is_internship(self):
        assert detect_seniority("Working Student Data Annotation", "") == "internship"

    def test_junior_from_title(self):
        assert detect_seniority("Junior Python Developer", "") == "junior"

    def test_senior_from_title(self):
        assert detect_seniority("Senior Backend Engineer", "") == "senior"

    def test_title_beats_body(self):
        # A junior posting that merely mentions senior colleagues stays junior.
        assert detect_seniority(
            "Junior Analyst", "You will report to a senior director of policy."
        ) == "junior"

    def test_falls_back_to_body(self):
        assert detect_seniority("Data Annotator", "This is an entry level role.") == "junior"

    def test_unstated_is_other(self):
        assert detect_seniority("Data Annotator", "Join our team.") == "other"


class TestFormat:
    def test_freelance(self):
        assert detect_format("Freelance Content Reviewer", "") == "freelance"

    def test_part_time(self):
        assert detect_format("Content Moderator", "Part-time, 20 hours per week") == "part-time"

    def test_full_time(self):
        assert detect_format("Analyst", "This is a full-time permanent role") == "full-time"

    def test_hint_wins(self):
        assert detect_format("Analyst", "full-time", hint="freelance") == "freelance"

    def test_unknown(self):
        assert detect_format("Analyst", "Join us") == "unknown"


class TestRemote:
    """Evidence precedence: location and title beat a source flag, which beats
    body text. All three of the live regressions below came from a real scan."""

    def test_remote_in_location(self):
        assert detect_remote("Analyst", "Remote", "") is True

    def test_remote_in_title(self):
        assert detect_remote("Analyst (Remote)", "", "") is True

    def test_hybrid_is_not_remote(self):
        assert detect_remote("Analyst", "Remote / Hybrid Berlin", "") is False

    def test_named_location_overrides_source_flag(self):
        # Ashby sets isRemote on roles that are only remote within a country;
        # "Applied AI Engineer — Seoul, South Korea" was ranking as remote.
        assert detect_remote("Applied AI Engineer", "Seoul, South Korea", "", hint=True) is False

    def test_named_location_overrides_body_mention(self):
        # "Account Associate - Singapore" matched on a stray body mention.
        body = "OpenAI has a remote-friendly culture and offers remote onboarding."
        assert detect_remote("Account Associate - Singapore", "Singapore", body) is False

    def test_hint_applies_when_location_is_generic(self):
        assert detect_remote("Analyst", "Any", "", hint=True) is True
        assert detect_remote("Analyst", "", "", hint=True) is True

    def test_hint_false_is_respected(self):
        assert detect_remote("Analyst", "", "", hint=False) is False

    def test_body_only_evidence_with_no_location(self):
        assert detect_remote("Analyst", "", "This is a fully remote position.") is True

    def test_onsite(self):
        assert detect_remote("Analyst", "Sofia, Bulgaria", "Office based") is False


class TestDomains:
    def test_trust_and_safety_detected(self):
        scores = detect_domains("Trust & Safety Specialist", "Content moderation and policy enforcement", [])
        assert scores["trust_safety"] >= 0.8

    def test_ai_domain(self):
        scores = detect_domains("Data Annotation Specialist", "Label datasets for LLM training", [])
        assert scores["ai"] >= 0.8

    def test_policy_domain(self):
        scores = detect_domains("EU Policy Research Intern", "Research on European Union institutions", [])
        assert scores["policy"] >= 0.8

    def test_title_weighted_above_body(self):
        in_title = detect_domains("Content Moderation Lead", "", [])
        in_body = detect_domains("Operations Lead", "Some content moderation may be involved", [])
        assert in_title["trust_safety"] > in_body["trust_safety"]

    def test_word_boundary_prevents_false_positive(self):
        # 'ai' must not match inside 'chair' / 'sql' not inside 'mysqld'
        scores = detect_domains("Chairperson of the Board", "We use mysqld internally", [])
        assert scores.get("ai", 0) == 0

    def test_unrelated_job_has_no_strong_domain(self):
        scores = detect_domains("Warehouse Forklift Operator", "Lift boxes in our depot", [])
        assert all(v < 0.5 for v in scores.values())


class TestNormalize:
    def test_full_pipeline(self):
        raw = RawJob(
            external_id="abc-1",
            title="Freelance AI Data Annotator (Remote)",
            url="https://example.com/j/1",
            company="Acme AI",
            location="Remote, Europe",
            description="<p>Label <b>datasets</b> for LLM training. Contract work.</p>",
            tags=["ai", "annotation"],
            posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        job = normalize(raw)
        assert job.remote_flag is True
        assert job.format == "freelance"
        assert job.category == "AI & Coding"
        assert "ai" in job.domains
        assert "<b>" not in job.raw_description

    def test_internship_category_wins_over_topic(self):
        raw = RawJob(
            external_id="i-1",
            title="AI Research Intern",
            url="https://example.com/j/2",
            description="Work on LLM evaluation. Remote.",
        )
        assert normalize(raw).category == "Internships"

    def test_content_hash_is_stable_and_content_sensitive(self):
        base = RawJob(external_id="1", title="Analyst", url="u", description="Same text")
        other = RawJob(external_id="1", title="Analyst", url="u", description="Different text")
        assert normalize(base).content_hash() == normalize(base).content_hash()
        assert normalize(base).content_hash() != normalize(other).content_hash()

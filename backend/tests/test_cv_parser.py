"""Parser tests. The real CV is used as the primary fixture when present."""
import pathlib

import pytest

from app.services.cv_parser import (
    display_skill,
    parse_cv,
    parse_education,
    parse_experience,
    parse_languages,
    parse_location,
    parse_name,
    parse_skills,
    split_sections,
)

CV_PATH = pathlib.Path(__file__).resolve().parents[2] / "cv2.3.pdf"

SYNTHETIC = """Jane Marie Doe Berlin, Germany | jane@example.com | +49 170 1234567
Languages: German (Native), English (C2), Spanish (Basic)
Profile Analyst with an interest in public policy and trust and safety work.
Education Free University — Berlin, Germany Master's Degree in Public Policy | 2021 - 2023
Professional Experience Trust & Safety Analyst — Example Corp, Berlin, Germany | June 2023 - Present
- Reviewed harmful content and enforced platform policy.
Junior Data Annotator — Data Ltd, Remote | January 2022 - May 2023
Technical & Professional Skills
- Content moderation, data annotation, prompt engineering, Python
"""


class TestHeadingDetection:
    def test_prose_mention_does_not_start_a_section(self):
        text = "Profile I have practical experience in research.\nProfessional Experience Analyst — X, Y | 2020 - 2021"
        sections = split_sections(text)
        assert "Professional Experience" in sections["experience"]

    def test_all_sections_found_in_synthetic_cv(self):
        sections = split_sections(SYNTHETIC)
        assert {"profile", "education", "experience", "skills", "languages"} <= set(sections)


class TestFieldParsing:
    def test_name_excludes_run_on_city(self):
        assert parse_name("Jane Marie Doe Berlin, Germany | jane@example.com") == "Jane Marie Doe"

    def test_name_with_clean_separator(self):
        assert parse_name("Jane Doe | jane@example.com") == "Jane Doe"

    def test_location_excludes_name(self):
        line = "Jane Marie Doe Berlin, Germany | jane@example.com"
        assert parse_location(line, name="Jane Marie Doe") == "Berlin, Germany"

    def test_languages_with_proficiency(self):
        langs = {l["name"]: l["proficiency"] for l in parse_languages(SYNTHETIC)}
        assert langs["German"] == "Native"
        assert langs["English"] == "C2"

    def test_skills_detected(self):
        skills = {s.lower() for s in parse_skills(SYNTHETIC)}
        assert "content moderation" in skills
        assert "prompt engineering" in skills

    def test_acronyms_keep_their_casing(self):
        assert display_skill("llm") == "LLM"
        assert display_skill("model evaluation") == "Model Evaluation"
        assert display_skill("github") == "GitHub"

    def test_experience_entries(self):
        entries = parse_experience(split_sections(SYNTHETIC)["experience"])
        roles = [e["role"] for e in entries]
        assert "Trust & Safety Analyst" in roles
        assert "Junior Data Annotator" in roles
        assert entries[0]["company"] == "Example Corp"

    def test_role_does_not_absorb_previous_sentence(self):
        text = "Did policy work online. Receptionist — Hotel Co, Varna | April 2025 - August 2025"
        assert parse_experience(text)[0]["role"] == "Receptionist"

    def test_education_strips_absorbed_heading(self):
        entries = parse_education("Education Free University — Berlin Master's Degree | 2021 - 2023")
        assert entries[0]["institution"] == "Free University"


class TestExtractText:
    def test_rejects_non_pdf_bytes(self):
        from app.services.cv_parser import extract_text

        with pytest.raises(ValueError):
            extract_text(b"this is not a pdf")


@pytest.mark.skipif(not CV_PATH.exists(), reason="cv2.3.pdf not present")
class TestRealCV:
    @pytest.fixture(scope="class")
    def parsed(self):
        return parse_cv(CV_PATH.read_bytes())

    def test_identity(self, parsed):
        assert parsed.name == "Kaloyan Ivanov"
        assert parsed.email == "koko06ivanov@gmail.com"
        assert parsed.location == "Sofia, Bulgaria"

    def test_languages(self, parsed):
        langs = {l["name"]: l["proficiency"] for l in parsed.languages}
        assert langs == {"Bulgarian": "Native", "English": "C1", "German": "Basic"}

    def test_education(self, parsed):
        assert parsed.education[0]["institution"] == "New Bulgarian University"
        assert "2025" in parsed.education[0]["dates"]

    def test_both_cv_roles_extracted(self, parsed):
        roles = {e["role"] for e in parsed.experience}
        assert "AI Research Intern" in roles
        assert "Receptionist" in roles
        assert {e["company"] for e in parsed.experience} == {"Sensika Technologies", "Griffin Hotels"}

    def test_core_skills_present(self, parsed):
        skills = {s.lower() for s in parsed.skills}
        for expected in ("prompt engineering", "model evaluation", "policy analysis", "forex"):
            assert expected in skills, f"missing skill: {expected}"

    def test_domain_weights_are_relative_not_saturated(self, parsed):
        """Weights must discriminate: AI leads, incidental domains trail.

        The CV mentions several domains strongly, so a saturating scheme would
        return 1.0 for all of them and the ranker could no longer prefer an AI
        role over an admin one.
        """
        weights = {d["key"]: d["weight"] for d in parsed.domains}
        assert weights["ai"] == 1.0, "AI is the CV's strongest domain"
        assert weights["policy"] > weights["admin"]
        assert weights["policy"] > weights["tech"]
        assert len({round(w, 2) for w in weights.values()}) > 2, "weights collapsed"

    def test_trust_safety_absent_from_pdf_alone(self, parsed):
        """The Telus Digital role is not in the PDF; it is merged in as manual
        experience by the profile service, which is what lifts this domain."""
        assert "trust_safety" not in {d["key"] for d in parsed.domains}

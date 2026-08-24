"""Extract structured profile data from a CV PDF.

Deliberately heuristic rather than LLM-backed: parsing runs on every CV upload
and must work offline, with no API key configured. Anything it gets wrong is
editable through PUT /profile.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.services import taxonomy as tx

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
URL_RE = re.compile(r"https?://\S+")
YEAR_RANGE_RE = re.compile(
    r"((?:19|20)\d{2})\s*[–—-]\s*((?:19|20)\d{2}|Present|present|Current|current)"
)

# Section headings, most specific first. A generic word like "experience"
# also appears in prose ("practical experience in AI research"), so the
# specific heading is always tried before the bare one.
SECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "profile": (r"\bprofile\b", r"\bpersonal statement\b", r"\bsummary\b", r"\babout me\b"),
    "education": (r"\beducation\b", r"\bacademic background\b", r"\bqualifications\b"),
    "experience": (
        r"\bprofessional experience\b",
        r"\bwork experience\b",
        r"\bemployment history\b",
        r"\bexperience\b",
    ),
    "skills": (
        r"\btechnical & professional skills\b",
        r"\btechnical skills\b",
        r"\bskills\b",
        r"\bcompetencies\b",
    ),
    "languages": (r"\blanguages?\b",),
}

# A real heading is followed by a colon, a bullet, a line break, or a
# capitalised word — never by a lowercase continuation of a sentence.
_HEADING_TAIL_RE = re.compile(r"\s*(?:[:•\n]|[A-Z0-9])")

LANGUAGE_NAMES = (
    "bulgarian", "english", "german", "french", "spanish", "italian", "russian",
    "romanian", "greek", "turkish", "dutch", "polish", "portuguese", "serbian",
    "croatian", "macedonian", "ukrainian", "czech", "hungarian",
)
PROFICIENCY_RE = re.compile(
    r"\b(native|fluent|proficient|advanced|intermediate|basic|beginner|"
    r"mother tongue|[abc][12])\b",
    re.IGNORECASE,
)

# Skills worth recognising by name. Built from the domain taxonomy's strong
# terms plus a few multi-word skills that are not domain markers on their own.
EXTRA_SKILL_TERMS = (
    "version control", "github", "git", "data entry", "research",
    "critical thinking", "analytical thinking", "time management",
    "teamwork", "adaptability", "project management", "public speaking",
    "report writing", "content classification", "quality assurance",
    "customer service", "excel", "powerpoint", "notion", "jira",
)


def _known_skill_terms() -> list[str]:
    terms: set[str] = set(EXTRA_SKILL_TERMS)
    for domain in tx.DOMAINS:
        terms.update(domain.strong)
    return sorted(terms, key=len, reverse=True)


KNOWN_SKILLS = _known_skill_terms()


@dataclass
class ParsedCV:
    raw_text: str = ""
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    skills: list[str] = field(default_factory=list)
    languages: list[dict] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)
    experience: list[dict] = field(default_factory=list)
    domains: list[dict] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "location": self.location,
            "headline": self.headline,
            "skills": self.skills,
            "languages": self.languages,
            "education": self.education,
            "experience": self.experience,
            "domains": self.domains,
        }


def extract_text(pdf_bytes: bytes) -> str:
    """Pull text out of a PDF. Raises ValueError if the file is unreadable."""
    from io import BytesIO

    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 - surfaced to the API caller
        raise ValueError(f"Could not read PDF: {exc}") from exc

    text = "\n".join(pages)
    if not text.strip():
        raise ValueError(
            "No text found in PDF — it may be a scanned image. "
            "Export a text-based PDF or fill the profile in manually."
        )
    return re.sub(r"[ \t]+", " ", text)


def split_sections(text: str) -> dict[str, str]:
    """Locate section headings and slice the text between them.

    CV exports frequently collapse a whole CV onto few lines, so headings are
    matched anywhere in the text rather than only at line starts.
    """
    hits: list[tuple[int, str]] = []
    for key, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            position = _find_heading(text, pattern)
            if position is not None:
                hits.append((position, key))
                break  # first (most specific) pattern that matches wins

    if not hits:
        return {"full": text}

    hits.sort()
    sections: dict[str, str] = {}
    for idx, (pos, key) in enumerate(hits):
        end = hits[idx + 1][0] if idx + 1 < len(hits) else len(text)
        sections[key] = text[pos:end].strip()
    return sections


def _find_heading(text: str, pattern: str) -> int | None:
    """Position of the first occurrence of `pattern` that looks like a heading."""
    for m in re.finditer(pattern, text, re.IGNORECASE):
        if _HEADING_TAIL_RE.match(text, m.end()):
            return m.start()
    return None


def parse_name(text: str) -> str | None:
    """The name is conventionally the first non-empty line of a CV."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        candidate = re.split(r"[|,•]", line)[0].strip()
        words = candidate.split()
        # Exports often run the name straight into the location with no
        # separator ("Kaloyan Ivanov Sofia, Bulgaria"). If a comma follows on
        # the same line, the word just before it is the city, not a surname.
        if "," in line and len(words) > 2:
            words = words[:-1]
        if 1 < len(words) <= 4 and all(w[:1].isupper() for w in words if w):
            return " ".join(words)
        break
    return None


def parse_location(text: str, name: str | None = None) -> str | None:
    head = "\n".join(text.splitlines()[:5])
    if name:
        head = head.replace(name, " ")
    m = re.search(
        r"\b([A-Z][a-zA-Zà-ÿ.\-]+(?: [A-Z][a-zA-Zà-ÿ.\-]+)?,"
        r"\s*[A-Z][a-zA-Zà-ÿ.\-]+(?: [A-Z][a-zA-Zà-ÿ.\-]+)?)",
        head,
    )
    if m:
        candidate = m.group(1).strip()
        if "@" not in candidate and len(candidate) < 60:
            return candidate
    return None


def parse_languages(text: str) -> list[dict]:
    found: list[dict] = []
    lowered = text.lower()
    for name in LANGUAGE_NAMES:
        for m in re.finditer(rf"\b{name}\b", lowered):
            # Proficiency is normally parenthesised right after the language.
            window = text[m.end() : m.end() + 30]
            prof = PROFICIENCY_RE.search(window)
            if prof or "(" in window[:3]:
                found.append({
                    "name": name.capitalize(),
                    "proficiency": prof.group(1).title() if prof else None,
                })
                break
    # Dedupe, first mention wins.
    seen: set[str] = set()
    return [l for l in found if not (l["name"] in seen or seen.add(l["name"]))]


# Terms whose conventional casing title() would mangle ("Llm", "Nlp").
ACRONYMS = {
    "llm": "LLM", "nlp": "NLP", "ai": "AI", "sql": "SQL", "api": "API",
    "rlhf": "RLHF", "github": "GitHub", "eu": "EU", "b2b": "B2B",
    "seo": "SEO", "crm": "CRM", "kyc": "KYC", "ml": "ML",
}


def display_skill(term: str) -> str:
    """Title-case a skill while preserving acronyms word by word."""
    return " ".join(ACRONYMS.get(w.lower(), w.title()) for w in term.split())


def parse_skills(text: str) -> list[str]:
    lowered = text.lower()
    matched: list[str] = []
    for term in KNOWN_SKILLS:
        if tx.contains_term(lowered, term):
            # Skip terms already covered by a longer matched skill, so
            # "annotation" does not appear beside "data annotation".
            if any(term in longer for longer in matched):
                continue
            matched.append(term)
    return sorted({display_skill(m) for m in matched})


_ROLE_HEADING_RE = re.compile(
    r"^(professional experience|work experience|employment history|experience)\s+",
    re.IGNORECASE,
)


def _clean_role(role: str) -> str:
    """Trim a captured role back to the job title itself.

    The regex reaches backwards from the dash and can pick up the tail of the
    previous bullet ("...information online. Receptionist") or an absorbed
    section heading ("Professional Experience AI Research Intern").
    """
    for boundary in (".", "•", "\n"):
        if boundary in role:
            role = role.rsplit(boundary, 1)[-1]
    role = _ROLE_HEADING_RE.sub("", role.strip())
    words = role.split()
    return " ".join(words[-6:]).strip(" ,-") if words else ""


def parse_experience(text: str) -> list[dict]:
    """Find 'Role — Company, Location | Dates' style entries."""
    entries: list[dict] = []
    # PDF text wraps anywhere, including between "March" and "2026", so match
    # against a single-line view of the section.
    text = re.sub(r"\s+", " ", text)
    pattern = re.compile(
        r"([A-Z][A-Za-z&/ .\-]{2,60}?)\s*[—–-]\s*"          # role
        r"([A-Z][A-Za-z0-9&.,' \-]{2,80}?)\s*\|\s*"          # company (+ location)
        r"([A-Za-z]* ?(?:19|20)\d{2}\s*[–—-]\s*"             # start
        r"(?:[A-Za-z]* ?(?:19|20)\d{2}|Present|Current))",   # end
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        role, company_part, dates = (g.strip(" ,|") for g in m.groups())
        role = _clean_role(role)
        if not role:
            continue
        company, _, location = company_part.partition(",")
        entries.append({
            "role": role.strip(),
            "company": company.strip(),
            "location": location.strip() or None,
            "dates": dates.strip(),
            "source": "cv",
        })
    return entries


def parse_education(text: str) -> list[dict]:
    entries: list[dict] = []
    for m in re.finditer(
        r"([A-Z][A-Za-z' ]*(?:University|College|School|Institute|Academy)[A-Za-z' ]*)",
        text,
    ):
        window = text[m.start() : m.start() + 260]
        degree = re.search(
            r"(Bachelor[’'s]*\s*Degree[^|.\n]*|Master[’'s]*[^|.\n]*|BA|BSc|MA|MSc|PhD)[^|.\n]*",
            window,
        )
        years = YEAR_RANGE_RE.search(window)
        institution = re.sub(
            r"^(Education|Academic Background|Qualifications)\s+", "",
            m.group(1).strip(), flags=re.IGNORECASE,
        ).strip()
        entries.append({
            "institution": institution,
            "degree": degree.group(0).strip() if degree else None,
            "dates": f"{years.group(1)} – {years.group(2)}" if years else None,
        })
    seen: set[str] = set()
    return [e for e in entries if not (e["institution"] in seen or seen.add(e["institution"]))]


def infer_domains(text: str, skills: list[str]) -> list[dict]:
    """Rank the CV's own domains, which become the ranker's interest weights."""
    from app.services.normalizer import detect_domain_points, normalize_domain_weights

    return normalize_domain_weights(detect_domain_points("", text, skills))


def parse_cv(pdf_bytes: bytes) -> ParsedCV:
    text = extract_text(pdf_bytes)
    sections = split_sections(text)

    skills = parse_skills(sections.get("skills", text))
    languages = parse_languages(sections.get("languages", text[:800]))
    experience = parse_experience(sections.get("experience", text))
    education = parse_education(sections.get("education", text))

    headline = None
    if profile_section := sections.get("profile"):
        body = re.sub(r"^\s*profile\s*", "", profile_section, flags=re.IGNORECASE).strip()
        headline = body.split(".")[0].strip()[:240] or None

    email_match = EMAIL_RE.search(text)
    phone_match = PHONE_RE.search(text)

    name = parse_name(text)
    return ParsedCV(
        raw_text=text,
        name=name,
        email=email_match.group(0) if email_match else None,
        phone=phone_match.group(0).strip() if phone_match else None,
        location=parse_location(text, name),
        headline=headline,
        skills=skills,
        languages=languages,
        education=education,
        experience=experience,
        domains=infer_domains(text, skills),
        sections=sections,
    )

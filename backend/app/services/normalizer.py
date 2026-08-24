"""Turn heterogeneous source payloads into consistent job_posting fields.

Every adapter emits a `RawJob`; this module is the single place that decides
seniority, format, remote-ness and category, so all sources are classified by
identical rules.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

from app.services import taxonomy as tx

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n{3,}")


@dataclass
class RawJob:
    """Source-agnostic job payload produced by an adapter."""

    external_id: str
    title: str
    url: str
    company: str | None = None
    location: str | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    salary_text: str | None = None
    posted_at: datetime | None = None
    remote_hint: bool | None = None
    format_hint: str | None = None


@dataclass
class NormalizedJob:
    external_id: str
    title: str
    url: str
    company: str | None
    location: str | None
    raw_description: str
    tags: list[str]
    salary_text: str | None
    posted_at: datetime | None
    remote_flag: bool
    seniority: str
    format: str
    category: str
    domains: list[str]

    def embedding_text(self) -> str:
        """The text actually embedded. Title and company are repeated up front
        because they carry far more signal per token than the boilerplate that
        dominates most descriptions."""
        parts = [
            self.title,
            f"Company: {self.company}" if self.company else "",
            f"Location: {self.location}" if self.location else "",
            f"Type: {self.format}, level: {self.seniority}",
            " ".join(self.tags),
            self.raw_description[:4000],
        ]
        return "\n".join(p for p in parts if p)

    def content_hash(self) -> str:
        return hashlib.sha256(self.embedding_text().encode("utf-8")).hexdigest()


def strip_html(text: str) -> str:
    """Cheap HTML-to-text. Sources hand us anything from plain text to full
    markup; we only need readable prose for embedding and display."""
    if not text:
        return ""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "• ", text)
    text = _TAG_RE.sub(" ", text)
    for entity, char in (
        ("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&quot;", '"'), ("&#39;", "'"), ("&rsquo;", "'"), ("&ndash;", "-"),
        ("&mdash;", "—"),
    ):
        text = text.replace(entity, char)
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def detect_seniority(title: str, text: str) -> str:
    """Title evidence outranks body evidence: a description mentioning
    'you'll work with senior engineers' must not make the role senior."""
    t, full = title.lower(), text.lower()

    if tx.find_terms(t, tx.INTERNSHIP_TERMS):
        return "internship"
    if tx.find_terms(t, tx.SENIOR_TERMS):
        return "senior"
    if tx.find_terms(t, tx.JUNIOR_TERMS):
        return "junior"
    if tx.find_terms(t, tx.MID_TERMS):
        return "mid-level"

    if tx.find_terms(full, tx.INTERNSHIP_TERMS):
        return "internship"
    if tx.find_terms(full, tx.SENIOR_TERMS):
        return "senior"
    if tx.find_terms(full, tx.JUNIOR_TERMS):
        return "junior"
    if tx.find_terms(full, tx.MID_TERMS):
        return "mid-level"
    return "other"


def detect_format(title: str, text: str, hint: str | None = None) -> str:
    if hint in ("freelance", "part-time", "full-time"):
        return hint
    combined = f"{title}\n{text}".lower()
    if tx.find_terms(combined, tx.FREELANCE_TERMS):
        return "freelance"
    if tx.find_terms(combined, tx.PART_TIME_TERMS):
        return "part-time"
    if tx.find_terms(combined, tx.FULL_TIME_TERMS):
        return "full-time"
    return "unknown"


def detect_remote(title: str, location: str | None, text: str,
                  hint: bool | None = None) -> bool:
    """Decide whether a posting is genuinely remote.

    Precedence matters here. Scanning the description for the word "remote"
    finds it in nearly every modern posting ("we have a remote-friendly
    culture", "remote onboarding"), which marked Seoul- and Singapore-based
    roles as remote in a live scan. So body text is treated as the weakest
    evidence and only counts when the posting names no specific location.
    """
    title_l = (title or "").lower()
    location_l = (location or "").strip().lower()

    # An explicit on-site or hybrid statement settles it, whatever else says.
    if tx.find_terms(f"{title_l} {location_l}", tx.ONSITE_TERMS):
        return False

    if location_l and tx.find_terms(location_l, tx.REMOTE_TERMS):
        return True
    if tx.find_terms(title_l, tx.REMOTE_TERMS):
        return True

    # A location naming an actual place contradicts a remote claim, including
    # the source's own flag: ATS boards set isRemote on roles that are only
    # remote *within* a country.
    named_place = bool(location_l) and not _is_generic_location(location_l)
    if named_place:
        return False

    if hint is not None:
        return bool(hint)

    # No location given: fall back to the body, but only the opening, where a
    # real requirement would be stated.
    return bool(tx.find_terms(text.lower()[:600], tx.REMOTE_TERMS))


# Placeholders sources use when a posting has no real location.
_GENERIC_LOCATIONS = {
    "any", "anywhere", "n/a", "na", "none", "worldwide", "global",
    "international", "multiple locations", "various", "unspecified", "-", "",
}


def _is_generic_location(location: str) -> bool:
    cleaned = location.strip().strip(".,-").lower()
    return cleaned in _GENERIC_LOCATIONS


def detect_domain_points(title: str, text: str, tags: list[str]) -> dict[str, float]:
    """Raw, unsaturated keyword evidence per domain.

    Job scoring wants the saturated view (`detect_domains`) — past a clear
    match, more mentions do not make a job *more* about a domain. Profile
    weighting wants this one, because a CV mentions several domains strongly
    and only the raw totals reveal which one it actually leans on.
    """
    title_l = title.lower()
    tags_l = " ".join(tags).lower()
    body_l = text.lower()[:8000]
    scores: dict[str, float] = {}

    for domain in tx.DOMAINS:
        points = 0.0
        for term in domain.strong:
            if tx.contains_term(title_l, term) or tx.contains_term(tags_l, term):
                points += 2.0
            elif tx.contains_term(body_l, term):
                points += 1.0
        for term in domain.weak:
            if tx.contains_term(title_l, term) or tx.contains_term(tags_l, term):
                points += 0.8
            elif tx.contains_term(body_l, term):
                points += 0.35
        if points > 0:
            scores[domain.key] = round(points, 4)
    return scores


def detect_domains(title: str, text: str, tags: list[str]) -> dict[str, float]:
    """Score each domain in [0, 1] from keyword evidence.

    Title and tag hits are weighted 2x body hits: a posting titled 'Content
    Moderator' is about trust & safety in a way that one merely mentioning
    moderation in a benefits list is not.
    """
    # 4 points ~= a clear, unambiguous domain match.
    return {
        key: round(min(1.0, points / 4.0), 4)
        for key, points in detect_domain_points(title, text, tags).items()
    }


def detect_required_languages(title: str, text: str) -> set[str]:
    """Languages a posting plainly requires.

    Scoped to the title and the opening of the description: that is where a
    hard requirement is stated. A language listed further down among "nice to
    haves" is not a gate, and treating it as one would discard good jobs.
    """
    haystack = f"{title}\n{text[:1200]}".lower()
    found: set[str] = set()
    for pattern in tx.LANGUAGE_REQUIREMENT_PATTERNS:
        for match in re.finditer(pattern, haystack, re.IGNORECASE):
            for group in match.groups():
                if group:
                    found.add(group.lower())

    # In a pair like "Russian/English" the English half is the pivot language,
    # not a second option — the role needs Russian. Keeping English in the set
    # would let every such posting through for any English speaker.
    if len(found) > 1 and "english" in found:
        found.discard("english")
    return found


def detect_region_restriction(location: str | None) -> set[str]:
    """Regions a remote posting is limited to, read from its location string.

    Returns an empty set when the posting is open ("Anywhere in the World") or
    names no region at all, so the caller can tell "unrestricted" apart from
    "restricted to somewhere I cannot work".
    """
    if not location:
        return set()

    text = location.lower()
    if any(token in text for token in tx.UNRESTRICTED_TOKENS) and not any(
        tx.contains_term(text, token) for token in tx.REGION_TOKENS
    ):
        return set()

    found = {
        canonical
        for token, canonical in tx.REGION_TOKENS.items()
        if tx.contains_term(text, token)
    }
    return found


def choose_category(seniority: str, fmt: str, remote: bool,
                    domain_scores: dict[str, float]) -> str:
    """Internships are a category of their own regardless of topic — that is how
    you actually triage them. Otherwise a confident topical domain wins, and
    employment format is the fallback."""
    if seniority == "internship":
        return tx.CATEGORY_INTERNSHIP

    if domain_scores:
        top_key, top_score = max(domain_scores.items(), key=lambda kv: kv[1])
        if top_score >= 0.5:
            return tx.DOMAIN_CATEGORY.get(top_key, tx.CATEGORY_OTHER)

    if fmt == "freelance":
        return tx.CATEGORY_FREELANCE
    if fmt == "part-time":
        return tx.CATEGORY_PART_TIME
    if fmt == "full-time" and remote:
        return tx.CATEGORY_FULL_TIME
    return tx.CATEGORY_OTHER


def normalize(raw: RawJob) -> NormalizedJob:
    description = strip_html(raw.description)
    tags = [t.strip() for t in raw.tags if t and t.strip()][:25]

    seniority = detect_seniority(raw.title, description)
    fmt = detect_format(raw.title, description, raw.format_hint)
    remote = detect_remote(raw.title, raw.location, description, raw.remote_hint)
    domain_scores = detect_domains(raw.title, description, tags)
    category = choose_category(seniority, fmt, remote, domain_scores)

    return NormalizedJob(
        external_id=str(raw.external_id),
        title=raw.title.strip()[:500],
        url=raw.url,
        company=(raw.company or "").strip()[:300] or None,
        location=(raw.location or "").strip()[:300] or None,
        raw_description=description,
        tags=tags,
        salary_text=raw.salary_text,
        posted_at=raw.posted_at,
        remote_flag=remote,
        seniority=seniority,
        format=fmt,
        category=category,
        domains=sorted(domain_scores, key=lambda k: domain_scores[k], reverse=True),
    )


def normalize_domain_weights(points: dict[str, float]) -> list[dict]:
    """Scale raw domain evidence so the strongest domain is 1.0.

    Saturating each domain at 1.0 first would flatten a multi-domain CV into
    "everything matters equally", and the domain component of the rule score
    would stop discriminating between an AI role and an admin one. The 0.25
    floor keeps a weakly evidenced domain in play rather than dropping it.
    """
    if not points:
        return []

    strongest = max(points.values())
    if strongest <= 0:
        return []

    weighted = [
        {
            "key": key,
            "label": tx.DOMAIN_BY_KEY[key].label,
            "weight": round(max(0.25, value / strongest), 3),
        }
        for key, value in points.items()
        if key in tx.DOMAIN_BY_KEY and value / strongest >= 0.12
    ]
    weighted.sort(key=lambda d: d["weight"], reverse=True)
    return weighted

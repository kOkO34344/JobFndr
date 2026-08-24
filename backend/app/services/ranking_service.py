"""Hybrid job ranking: hard filters + rule score + semantic score.

Everything here is a pure function over plain dataclasses. No DB session, no
embedding model, no network — the caller supplies an already-computed cosine
similarity. That is what makes the ranker unit-testable and cheap to retune.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services import taxonomy as tx
from app.services.normalizer import (
    detect_domains,
    detect_region_restriction,
    detect_required_languages,
)

# Weights of the five rule-score components. Must sum to 1.0.
COMPONENT_WEIGHTS = {
    "domain": 0.40,
    "seniority": 0.25,
    "format": 0.15,
    "remote": 0.10,
    "skills": 0.10,
}

# Raw cosine similarity between a CV and a job description rarely exceeds ~0.6
# even for an excellent match, and hovers near 0.05 for unrelated postings.
# Mapping the [FLOOR, CEIL] band onto [0, 1] keeps the score readable instead of
# squashing every job into the 0.5-0.7 range that (cos + 1) / 2 would produce.
SEMANTIC_FLOOR = 0.05
SEMANTIC_CEIL = 0.60


@dataclass
class ProfileView:
    """The slice of the user profile the ranker needs."""

    skills: list[str] = field(default_factory=list)
    # domain key -> interest weight in [0, 1]
    domain_weights: dict[str, float] = field(default_factory=dict)
    preferred_seniority: list[str] = field(default_factory=lambda: ["internship", "junior", "mid-level"])
    preferred_formats: list[str] = field(default_factory=lambda: ["freelance", "part-time", "full-time"])
    # Lower-cased languages the candidate can actually work in.
    languages: list[str] = field(default_factory=list)
    # Regions the candidate can legally/practically work from. Empty disables
    # the region check entirely.
    allowed_regions: list[str] = field(default_factory=lambda: list(tx.DEFAULT_ALLOWED_REGIONS))
    remote_only: bool = True
    allow_unknown_seniority: bool = True
    allow_unknown_format: bool = True


@dataclass
class JobView:
    """The slice of a job posting the ranker needs."""

    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    seniority: str = "other"
    format: str = "unknown"
    remote_flag: bool = False
    company: str | None = None
    location: str | None = None


@dataclass
class FilterResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class MatchResult:
    rule_score: float
    semantic_score: float
    final_score: float
    passed_filters: bool
    explanation: dict


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


# --------------------------------------------------------------------------
# Hard filters
# --------------------------------------------------------------------------
def apply_hard_filters(job: JobView, profile: ProfileView) -> FilterResult:
    """Reject postings that are structurally wrong for me, whatever they say.

    'unknown'/'other' values are allowed through by default: a large share of
    postings simply never state a level or contract type, and excluding them
    silently would cost far more good matches than it saves bad ones.
    """
    reasons: list[str] = []

    if profile.remote_only and not job.remote_flag:
        reasons.append("Not remote-friendly")

    if job.seniority not in profile.preferred_seniority:
        if job.seniority == "other" and profile.allow_unknown_seniority:
            pass
        else:
            reasons.append(f"Seniority '{job.seniority}' outside target levels")

    if job.format not in profile.preferred_formats:
        if job.format == "unknown" and profile.allow_unknown_format:
            pass
        else:
            reasons.append(f"Format '{job.format}' outside target formats")

    # "Remote (USA)" is remote and still unreachable from Sofia.
    if profile.allowed_regions:
        restricted_to = detect_region_restriction(job.location)
        if restricted_to and not (restricted_to & set(profile.allowed_regions)):
            listed = ", ".join(sorted(restricted_to))
            reasons.append(f"Remote but restricted to {listed}")

    # Localisation and voice-data roles are one posting templated across dozens
    # of languages. Without this gate they flood the top of the deck with jobs
    # that cannot be applied for at all.
    required = detect_required_languages(job.title, job.description)
    if required and profile.languages:
        spoken = {lang.lower() for lang in profile.languages}
        if not (required & spoken):
            listed = ", ".join(sorted(r.title() for r in required))
            reasons.append(f"Requires {listed}, which you do not speak")

    return FilterResult(passed=not reasons, reasons=reasons)


# --------------------------------------------------------------------------
# Rule score components
# --------------------------------------------------------------------------
def score_domains(job: JobView, profile: ProfileView) -> tuple[float, list[dict]]:
    """Weighted overlap between what the job is about and what I care about."""
    job_domains = detect_domains(job.title, job.description, job.tags)
    if not job_domains or not profile.domain_weights:
        return 0.0, []

    matched: list[dict] = []
    for key, job_score in job_domains.items():
        weight = profile.domain_weights.get(key, 0.0)
        if weight <= 0 or job_score <= 0:
            continue
        matched.append({
            "key": key,
            "label": tx.DOMAIN_BY_KEY[key].label if key in tx.DOMAIN_BY_KEY else key,
            "job_score": round(job_score, 3),
            "profile_weight": round(weight, 3),
            "contribution": round(job_score * weight, 4),
        })

    if not matched:
        return 0.0, []

    matched.sort(key=lambda d: d["contribution"], reverse=True)
    # Best domain dominates; the runner-up adds at most a third. A job that is
    # squarely in one of my domains should beat one that grazes three.
    best = matched[0]["contribution"]
    second = matched[1]["contribution"] if len(matched) > 1 else 0.0
    return _clamp(best + 0.33 * second), matched


def score_seniority(job: JobView, profile: ProfileView) -> tuple[float, dict]:
    preferred = profile.preferred_seniority
    if job.seniority in preferred:
        # Prefer the levels I am actually targeting, best-first.
        rank = preferred.index(job.seniority)
        score = 1.0 - (rank * 0.1 if rank < 3 else 0.3)
    elif job.seniority == "other":
        score = 0.5  # unstated level: neither rewarded nor punished
    elif job.seniority == "senior":
        score = 0.0
    else:
        score = 0.2
    return _clamp(score), {
        "job": job.seniority,
        "preferred": preferred,
        "match": job.seniority in preferred,
        "score": round(score, 3),
    }


def score_format(job: JobView, profile: ProfileView) -> tuple[float, dict]:
    if job.format in profile.preferred_formats:
        score = 1.0
    elif job.format == "unknown":
        score = 0.5
    else:
        score = 0.1
    return _clamp(score), {
        "job": job.format,
        "preferred": profile.preferred_formats,
        "match": job.format in profile.preferred_formats,
        "score": round(score, 3),
    }


def score_remote(job: JobView, profile: ProfileView) -> tuple[float, dict]:
    score = 1.0 if job.remote_flag else (0.0 if profile.remote_only else 0.5)
    return score, {
        "job": job.remote_flag,
        "required": profile.remote_only,
        "match": job.remote_flag or not profile.remote_only,
    }


def score_skills(job: JobView, profile: ProfileView) -> tuple[float, list[str]]:
    """Literal overlap between my listed skills and the posting text."""
    if not profile.skills:
        return 0.0, []
    haystack = f"{job.title}\n{' '.join(job.tags)}\n{job.description}".lower()[:12000]
    matched = [s for s in profile.skills if tx.contains_term(haystack, s.lower())]
    # Five explicit skill hits is already a strong signal; saturate there.
    return _clamp(len(matched) / 5.0), matched


def score_languages(job: JobView, profile: ProfileView) -> str | None:
    """A posting that asks for a language you have is a genuine edge.

    Bulgarian in particular narrows the applicant pool sharply, so surfacing it
    in the explanation is worth more than a fractional score tweak.
    """
    if not profile.languages:
        return None
    required = detect_required_languages(job.title, job.description)
    spoken = {lang.lower() for lang in profile.languages}
    # English is table stakes on remote boards and carries no signal.
    distinctive = (required & spoken) - {"english"}
    return ", ".join(sorted(lang.title() for lang in distinctive)) or None


def compute_rule_score(job: JobView, profile: ProfileView) -> tuple[float, dict]:
    domain_score, matched_domains = score_domains(job, profile)
    seniority_score, seniority_detail = score_seniority(job, profile)
    format_score, format_detail = score_format(job, profile)
    remote_score, remote_detail = score_remote(job, profile)
    skills_score, matched_skills = score_skills(job, profile)

    components = {
        "domain": domain_score,
        "seniority": seniority_score,
        "format": format_score,
        "remote": remote_score,
        "skills": skills_score,
    }
    rule_score = sum(components[k] * COMPONENT_WEIGHTS[k] for k in components)

    detail = {
        "matched_domains": matched_domains,
        "matched_skills": matched_skills,
        "language_bonus": score_languages(job, profile),
        "seniority": seniority_detail,
        "format": format_detail,
        "remote": remote_detail,
        "components": {k: round(v, 4) for k, v in components.items()},
        "component_weights": COMPONENT_WEIGHTS,
    }
    return _clamp(rule_score), detail


# --------------------------------------------------------------------------
# Semantic + combination
# --------------------------------------------------------------------------
def normalize_semantic(cosine: float) -> float:
    """Map raw cosine similarity onto a calibrated [0, 1] score."""
    return _clamp((cosine - SEMANTIC_FLOOR) / (SEMANTIC_CEIL - SEMANTIC_FLOOR))


def build_summary(rule_detail: dict, final_score: float, filters: FilterResult) -> str:
    if not filters.passed:
        return "Filtered out: " + "; ".join(filters.reasons)

    bits: list[str] = []
    domains = rule_detail.get("matched_domains") or []
    if domains:
        names = ", ".join(d["label"] for d in domains[:2])
        bits.append(f"Overlaps your {names} background")
    skills = rule_detail.get("matched_skills") or []
    if skills:
        bits.append(f"mentions {len(skills)} of your skills ({', '.join(skills[:3])})")
    if bonus := rule_detail.get("language_bonus"):
        bits.append(f"wants {bonus}, which you speak")
    sen = rule_detail.get("seniority", {})
    if sen.get("match"):
        bits.append(f"{sen.get('job')} level matches your targets")
    fmt = rule_detail.get("format", {})
    if fmt.get("match"):
        bits.append(f"{fmt.get('job')} format")

    if not bits:
        return f"Weak match ({final_score:.0%}) — no clear domain or skill overlap."
    return f"{final_score:.0%} match. " + "; ".join(bits) + "."


def rank_job(
    job: JobView,
    profile: ProfileView,
    cosine_similarity: float,
    rule_weight: float = 0.4,
    semantic_weight: float = 0.6,
) -> MatchResult:
    """Score one job. `cosine_similarity` is the raw CV-vs-job cosine."""
    filters = apply_hard_filters(job, profile)
    rule_score, rule_detail = compute_rule_score(job, profile)
    semantic_score = normalize_semantic(cosine_similarity)

    total_weight = rule_weight + semantic_weight
    if total_weight <= 0:
        raise ValueError("rule_weight + semantic_weight must be > 0")
    final_score = (rule_score * rule_weight + semantic_score * semantic_weight) / total_weight

    # A job that fails a hard filter is kept (so it stays inspectable and the
    # UI can show why) but pushed down hard rather than deleted.
    if not filters.passed:
        final_score *= 0.25

    explanation = {
        **rule_detail,
        "rule_score": round(rule_score, 4),
        "semantic_score": round(semantic_score, 4),
        "raw_cosine": round(cosine_similarity, 4),
        "final_score": round(final_score, 4),
        "weights": {"rule": rule_weight, "semantic": semantic_weight},
        "filters": {"passed": filters.passed, "reasons": filters.reasons},
    }
    explanation["summary"] = build_summary(rule_detail, final_score, filters)

    return MatchResult(
        rule_score=round(rule_score, 4),
        semantic_score=round(semantic_score, 4),
        final_score=round(_clamp(final_score), 4),
        passed_filters=filters.passed,
        explanation=explanation,
    )

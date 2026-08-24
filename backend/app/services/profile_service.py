"""Profile bootstrap, CV ingestion and the profile view used by the ranker."""
from __future__ import annotations

import json
import logging
import os
import pathlib
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.embeddings import embed_text
from app.models import UserProfile
from app.repositories import profile_repo
from app.services import taxonomy as tx
from app.services.cv_parser import ParsedCV, parse_cv
from app.services.ranking_service import ProfileView

logger = logging.getLogger(__name__)

DEFAULT_PREFERRED_SENIORITY = ["internship", "junior", "mid-level"]
DEFAULT_PREFERRED_FORMATS = ["freelance", "part-time", "full-time"]
DEFAULT_PREFERRED_ROLES = [
    "AI data annotation",
    "AI model evaluation",
    "Trust & Safety / content moderation",
    "Prompt engineering",
    "Policy research assistant",
    "EU affairs intern",
    "Market research analyst",
    "Junior backend / Python developer",
]

# Experience a CV PDF does not contain, seeded from data/manual_experience.json
# if present. Kept as manual entries so a CV re-upload never wipes them, and
# included in the embedded profile text so they influence semantic matching as
# much as parsed roles do. Loaded from a file rather than hard-coded so the
# repository carries no one's employment history.
MANUAL_EXPERIENCE_FILE = pathlib.Path(
    os.getenv("MANUAL_EXPERIENCE_FILE", "/config/manual_experience.json")
)


def _load_manual_experience() -> list[dict]:
    if not MANUAL_EXPERIENCE_FILE.exists():
        return []
    try:
        entries = json.loads(MANUAL_EXPERIENCE_FILE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s", MANUAL_EXPERIENCE_FILE, exc)
        return []
    if not isinstance(entries, list):
        logger.warning("%s must contain a JSON list", MANUAL_EXPERIENCE_FILE)
        return []
    return [{**entry, "source": "manual"} for entry in entries if entry.get("role")]


MANUAL_EXPERIENCE = _load_manual_experience()


def default_profile_fields() -> dict:
    return {
        "name": settings.operator_name,
        "email": settings.operator_email or None,
        "location": settings.operator_location or None,
        "skills": [],
        "languages": [],
        "education": [],
        "experience": list(MANUAL_EXPERIENCE),
        "domains": [],
        "preferred_roles": DEFAULT_PREFERRED_ROLES,
        "preferred_formats": DEFAULT_PREFERRED_FORMATS,
        "preferred_seniority": DEFAULT_PREFERRED_SENIORITY,
        "remote_only": True,
    }


def bootstrap(db: Session) -> UserProfile:
    """Guarantee the single profile row exists."""
    profile = profile_repo.get(db)
    if profile is None:
        logger.info("Seeding single-user profile row")
        profile = profile_repo.get_or_create(db, default_profile_fields())
        db.commit()
    return profile


# ---------------------------------------------------------------------------
# CV ingestion
# ---------------------------------------------------------------------------
def _merge_experience(existing: list, parsed: list[dict]) -> list[dict]:
    """CV-parsed roles replace previous CV-parsed roles; manual ones survive.

    Without this, uploading a new CV would silently delete roles added by hand
    (such as the Telus Digital position, which is not in the PDF).
    """
    manual = [e for e in (existing or []) if e.get("source") != "cv"]
    if not manual:
        manual = list(MANUAL_EXPERIENCE)

    parsed_keys = {(e.get("role", "").lower(), e.get("company", "").lower()) for e in parsed}
    manual = [
        e for e in manual
        if (e.get("role", "").lower(), e.get("company", "").lower()) not in parsed_keys
    ]
    return parsed + manual


def _store_cv_file(filename: str, data: bytes) -> str:
    directory = pathlib.Path(settings.cv_storage_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", pathlib.Path(filename).name) or "cv.pdf"
    path = directory / f"{stamp}-{safe}"
    path.write_bytes(data)
    return str(path)


def profile_text_for_embedding(profile: UserProfile) -> str:
    """The text embedded as 'me'.

    Manually added experience is appended to the CV text so that roles absent
    from the PDF still shape the semantic score.
    """
    parts = [profile.cv_text or ""]

    manual = [e for e in (profile.experience or []) if e.get("source") != "cv"]
    if manual:
        parts.append("Additional experience:")
        for entry in manual:
            line = " ".join(
                str(v) for v in (
                    entry.get("role"), entry.get("company"),
                    entry.get("dates"), entry.get("description"),
                ) if v
            )
            parts.append(line)

    if profile.skills:
        parts.append("Skills: " + ", ".join(profile.skills))
    if profile.preferred_roles:
        parts.append("Roles sought: " + ", ".join(profile.preferred_roles))

    return "\n".join(p for p in parts if p.strip()).strip()


def refresh_embedding(db: Session, profile: UserProfile) -> bool:
    """Re-embed the profile. Returns False when there is nothing to embed."""
    text = profile_text_for_embedding(profile)
    if not text:
        return False
    profile.cv_embedding = embed_text(text)
    db.flush()
    return True


def ingest_cv(db: Session, filename: str, data: bytes) -> tuple[UserProfile, ParsedCV]:
    """Parse an uploaded CV, merge it into the profile and re-embed."""
    parsed = parse_cv(data)
    profile = profile_repo.get_or_create(db, default_profile_fields())

    stored_path = _store_cv_file(filename, data)
    profile.cv_original_path = stored_path
    profile.cv_text = parsed.raw_text

    if parsed.name:
        profile.name = parsed.name
    if parsed.email:
        profile.email = parsed.email
    if parsed.location:
        profile.location = parsed.location
    if parsed.headline:
        profile.headline = parsed.headline
    if parsed.skills:
        profile.skills = parsed.skills
    if parsed.languages:
        profile.languages = parsed.languages
    if parsed.education:
        profile.education = parsed.education

    profile.experience = _merge_experience(profile.experience, parsed.experience)
    profile.domains = _recompute_domains(profile, parsed)

    refresh_embedding(db, profile)
    db.commit()
    db.refresh(profile)
    return profile, parsed


def _recompute_domains(profile: UserProfile, parsed: ParsedCV) -> list[dict]:
    """Domain weights from the CV *plus* manual experience.

    Trust & Safety only scores highly because the Telus Digital role is folded
    in here — the PDF alone would leave that domain near zero.
    """
    from app.services.normalizer import detect_domain_points, normalize_domain_weights

    manual_text = " ".join(
        str(v)
        for entry in (profile.experience or [])
        if entry.get("source") != "cv"
        for v in (entry.get("role"), entry.get("company"), entry.get("description"))
        if v
    )
    combined = f"{parsed.raw_text}\n{manual_text}"
    return normalize_domain_weights(detect_domain_points("", combined, parsed.skills))


# ---------------------------------------------------------------------------
# Profile view for the ranker
# ---------------------------------------------------------------------------
def build_profile_view(profile: UserProfile) -> ProfileView:
    domain_weights = {
        d["key"]: float(d.get("weight", 0.5))
        for d in (profile.domains or [])
        if d.get("key")
    }
    if not domain_weights:
        # A profile with no CV yet still ranks sensibly against my stated interests.
        domain_weights = {"ai": 1.0, "trust_safety": 0.9, "policy": 0.8,
                          "tech": 0.7, "markets": 0.6, "admin": 0.4, "languages": 0.5}

    return ProfileView(
        skills=[s for s in (profile.skills or []) if isinstance(s, str)],
        domain_weights=domain_weights,
        preferred_seniority=list(profile.preferred_seniority or DEFAULT_PREFERRED_SENIORITY),
        preferred_formats=list(profile.preferred_formats or DEFAULT_PREFERRED_FORMATS),
        languages=[
            str(entry.get("name", "")).lower()
            for entry in (profile.languages or [])
            if entry.get("name")
        ],
        remote_only=bool(profile.remote_only),
    )

"""Draft tailored application messages for a shortlisted job.

Two paths, same output shape:
  * an LLM draft when an API key is configured;
  * otherwise a locally composed draft built from the real match explanation.

The fallback is not a stub — it produces a genuinely sendable message using the
overlapping skills and domains the ranker already identified.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.llm import client as llm

if TYPE_CHECKING:  # keeps the drafting functions importable without the ORM
    from sqlalchemy.orm import Session

    from app.models import JobPosting, Proposal, UserProfile

logger = logging.getLogger(__name__)

TONES = {
    "professional": "Professional and concise, in plain business English.",
    "warm": "Warm and personable, still professional. First-person and human.",
    "direct": "Very direct and brief. No pleasantries beyond a short greeting.",
    "enthusiastic": "Genuinely enthusiastic without hype or exaggeration.",
}

SYSTEM_PROMPT = """You write short, tailored job application messages on behalf \
of a specific candidate. You are given the candidate's real background and a real \
job posting.

Hard rules:
- Never invent experience, employers, tools, degrees, or years of experience. \
Use only what the candidate profile states.
- If the candidate lacks something the posting asks for, do not claim it. You may \
frame adjacent real experience, or simply leave it out.
- Write in first person as the candidate.
- 150-220 words. No subject line unless asked. No markdown headings, no bullet \
lists unless the posting is a freelance brief where a short list genuinely helps.
- End with a brief, low-pressure call to action.
- Output only the message body. No preamble, no commentary, no placeholders \
like [Your Name] other than signing off with the candidate's actual name."""


def _profile_block(profile: "UserProfile") -> str:
    lines = [f"Name: {profile.name}"]
    if profile.location:
        lines.append(f"Location: {profile.location}")
    if profile.headline:
        lines.append(f"Summary: {profile.headline}")
    if profile.languages:
        langs = ", ".join(
            f"{l.get('name')}" + (f" ({l.get('proficiency')})" if l.get("proficiency") else "")
            for l in profile.languages
        )
        lines.append(f"Languages: {langs}")
    if profile.education:
        lines.append(
            "Education: "
            + "; ".join(
                " ".join(str(v) for v in (e.get("degree"), e.get("institution"), e.get("dates")) if v)
                for e in profile.education
            )
        )
    if profile.experience:
        lines.append("Experience:")
        for entry in profile.experience:
            parts = [entry.get("role"), entry.get("company"), entry.get("dates")]
            line = " — ".join(str(p) for p in parts if p)
            if entry.get("description"):
                line += f": {entry['description']}"
            lines.append(f"  - {line}")
    if profile.skills:
        lines.append("Skills: " + ", ".join(profile.skills))
    return "\n".join(lines)


def _job_block(job: "JobPosting") -> str:
    header = [
        f"Title: {job.title}",
        f"Company: {job.company or 'Unknown'}",
        f"Location: {job.location or 'Unspecified'} (remote: {job.remote_flag})",
        f"Level: {job.seniority} | Type: {job.format} | Category: {job.category}",
    ]
    if job.salary_text:
        header.append(f"Compensation: {job.salary_text}")
    body = (job.raw_description or "")[:6000]
    return "\n".join(header) + "\n\nPosting:\n" + body


def _match_block(job: "JobPosting") -> str:
    explanation = (job.match.explanation if job.match else None) or {}
    lines = []
    if summary := explanation.get("summary"):
        lines.append(f"Match summary: {summary}")
    if domains := explanation.get("matched_domains"):
        lines.append("Overlapping domains: " + ", ".join(d["label"] for d in domains[:4]))
    if skills := explanation.get("matched_skills"):
        lines.append("Skills the posting explicitly mentions: " + ", ".join(skills))
    return "\n".join(lines)


def build_prompt(profile: "UserProfile", job: "JobPosting", tone: str,
                 extra_instructions: str | None) -> str:
    sections = [
        "CANDIDATE PROFILE\n" + _profile_block(profile),
        "JOB POSTING\n" + _job_block(job),
    ]
    if match := _match_block(job):
        sections.append("WHY THIS WAS MATCHED\n" + match)
    sections.append(
        "TONE\n" + TONES.get(tone, TONES["professional"])
    )
    if extra_instructions:
        sections.append("ADDITIONAL INSTRUCTIONS FROM THE CANDIDATE\n" + extra_instructions.strip())
    sections.append("Write the application message now.")
    return "\n\n---\n\n".join(sections)


def _relevant_experience(profile: "UserProfile", job: "JobPosting") -> list[dict]:
    """Order experience by how well it fits *this* job.

    Listing roles in CV order surfaces whichever came first, which is how a
    hotel receptionist role ended up cited in a draft for an AI legal
    specialist. Scoring each entry against the job's domains keeps the draft
    honest and relevant.
    """
    from app.services.normalizer import detect_domains

    entries = [e for e in (profile.experience or []) if e.get("role")]
    if not entries:
        return []

    job_domains = detect_domains(job.title, job.raw_description or "", list(job.tags or []))
    if not job_domains:
        return entries[:2]

    def relevance(entry: dict) -> float:
        text = " ".join(
            str(v) for v in (entry.get("role"), entry.get("company"), entry.get("description"))
            if v
        )
        entry_domains = detect_domains("", text, [])
        return sum(
            score * job_domains.get(key, 0.0) for key, score in entry_domains.items()
        )

    ranked = sorted(entries, key=relevance, reverse=True)
    # Drop entries with no overlap at all rather than padding the draft.
    return [e for e in ranked if relevance(e) > 0][:2] or ranked[:1]


def _join_list(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def build_template_proposal(profile: "UserProfile", job: "JobPosting", tone: str) -> str:
    """Deterministic draft assembled from the actual match explanation."""
    explanation = (job.match.explanation if job.match else None) or {}
    domains = [d["label"] for d in (explanation.get("matched_domains") or [])[:2]]
    skills = (explanation.get("matched_skills") or [])[:4]

    company = job.company or "your team"
    greeting = "Hello," if tone == "direct" else f"Dear {company} team,"

    opening = (
        f"I'm writing about the {job.title} role"
        + (f" at {company}" if job.company else "")
        + ". "
    )
    if job.seniority in ("internship", "junior"):
        opening += (
            "I'm an early-career candidate looking for exactly this kind of "
            "remote position, and the scope of the role lines up closely with "
            "what I already do."
        )
    else:
        opening += "The role lines up closely with the work I've been doing."

    relevant = _relevant_experience(profile, job)
    experience_line = ""
    if relevant:
        first = relevant[0]
        experience_line = (
            f"As {first['role']} at {first.get('company', 'my current employer')}, "
            "I worked on the kind of tasks this posting describes"
        )
        if len(relevant) > 1:
            second = relevant[1]
            experience_line += (
                f", and before that I worked as {second['role']}"
                + (f" at {second['company']}" if second.get("company") else "")
            )
        experience_line += "."

    overlap_line = ""
    if skills:
        verb = "which I work with directly" if len(skills) == 1 else "all of which I work with directly"
        overlap_line = f"The posting mentions {_join_list(skills)} — {verb}."
    elif domains:
        overlap_line = f"My background sits squarely in {_join_list(domains)}."

    language_line = ""
    languages = [l.get("name") for l in (profile.languages or []) if l.get("name")]
    if len(languages) > 1:
        language_line = f"I work in {_join_list(languages)}."

    closing = (
        "I'd be glad to share more detail or walk through relevant examples if "
        "that's useful. Thank you for your time."
    )

    body = " ".join(p for p in (opening, experience_line, overlap_line, language_line) if p)
    return f"{greeting}\n\n{body}\n\n{closing}\n\n{profile.name}"


async def generate(
    db: "Session",
    job_id: int,
    tone: str = "professional",
    extra_instructions: str | None = None,
) -> tuple["Proposal", dict]:
    """Generate and persist a proposal. Returns (proposal, meta)."""
    from app.repositories import jobs_repo, profile_repo, proposals_repo

    job = jobs_repo.get(db, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    profile = profile_repo.get(db)
    if profile is None:
        raise ValueError("No profile yet — upload your CV first")

    meta: dict = {"fallback_reason": None, **llm.provider_status()}

    if llm.is_configured():
        prompt = build_prompt(profile, job, tone, extra_instructions)
        try:
            response = await llm.complete(SYSTEM_PROMPT, prompt)
            proposal = proposals_repo.create(
                db, job_id, response.text, tone, response.model, "llm"
            )
            db.commit()
            db.refresh(proposal)
            return proposal, meta
        except (llm.LLMError, llm.LLMUnavailable) as exc:
            logger.warning("LLM proposal failed for job %s: %s", job_id, exc)
            meta["fallback_reason"] = str(exc)
    else:
        meta["fallback_reason"] = "No LLM API key configured"

    content = build_template_proposal(profile, job, tone)
    proposal = proposals_repo.create(db, job_id, content, tone, None, "template")
    db.commit()
    db.refresh(proposal)
    return proposal, meta

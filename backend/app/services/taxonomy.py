"""Domain vocabulary derived from the CV.

Each domain carries weighted keywords: `strong` terms are near-conclusive
evidence the posting sits in that domain, `weak` terms are supporting signal.
Keeping this as data (not code branches) means retuning the ranker is an edit
here, and the ranking tests can assert against it directly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Domain:
    key: str
    label: str
    strong: tuple[str, ...] = field(default_factory=tuple)
    weak: tuple[str, ...] = field(default_factory=tuple)


DOMAINS: tuple[Domain, ...] = (
    Domain(
        key="ai",
        label="AI & ML",
        strong=(
            "llm", "large language model", "prompt engineering", "nlp",
            "natural language processing", "data annotation", "data labeling",
            "data labelling", "model evaluation", "rlhf", "fine-tuning",
            "machine learning", "generative ai", "ai training", "ai trainer",
            "annotation", "labeling", "labelling", "red teaming", "ai research",
        ),
        weak=("ai", "artificial intelligence", "dataset", "training data",
              "classification", "chatgpt", "openai", "anthropic", "claude", "gpt"),
    ),
    Domain(
        key="tech",
        label="Software & Coding",
        strong=("python", "fastapi", "backend", "react", "web scraping",
                "javascript", "typescript", "api development", "sql", "docker"),
        weak=("git", "github", "version control", "software", "developer",
              "engineer", "coding", "programming", "frontend", "full-stack",
              "automation", "scripting", "database", "rest api"),
    ),
    Domain(
        key="trust_safety",
        label="Trust & Safety",
        strong=(
            "trust and safety", "trust & safety", "content moderation",
            "content moderator", "policy enforcement", "community operations",
            "abuse prevention", "platform integrity", "safety operations",
            "misinformation", "disinformation", "fact-checking", "fact checking",
        ),
        weak=("moderation", "escalation", "policy violation", "harmful content",
              "user reports", "integrity", "risk review", "compliance review",
              "content review", "community guidelines"),
    ),
    Domain(
        key="policy",
        label="Politics & Policy",
        strong=("political science", "eu institutions", "european union",
                "public policy", "policy analysis", "policy research",
                "government affairs", "public affairs", "geopolitics",
                "european commission", "european parliament"),
        weak=("politics", "policy", "regulation", "governance", "democracy",
              "civic", "advocacy", "think tank", "ngo", "legislation",
              "international relations", "brussels"),
    ),
    Domain(
        key="markets",
        label="Financial Markets",
        strong=("forex", "financial markets", "equity research", "trading desk",
                "crypto", "cryptocurrency", "commodities", "futures",
                "market analysis", "quantitative"),
        weak=("stocks", "markets", "trading", "finance", "financial", "fintech",
              "investment", "portfolio", "blockchain", "web3", "economics"),
    ),
    Domain(
        key="admin",
        label="Admin & Communication",
        strong=("customer support", "virtual assistant", "administrative assistant",
                "reservations", "front desk", "intercultural communication"),
        weak=("administration", "coordination", "scheduling", "communication",
              "hospitality", "guest", "client support", "back office",
              "operations assistant", "data entry"),
    ),
    Domain(
        key="languages",
        label="Languages",
        strong=("bulgarian", "native bulgarian", "english c1", "localization",
                "localisation", "translation", "transcription"),
        weak=("english", "german", "multilingual", "bilingual", "linguist",
              "proofreading", "language"),
    ),
)

DOMAIN_BY_KEY: dict[str, Domain] = {d.key: d for d in DOMAINS}

# --- Seniority ------------------------------------------------------------
INTERNSHIP_TERMS = ("intern", "internship", "trainee", "traineeship", "stagiaire",
                    "praktikum", "working student", "werkstudent", "apprentice",
                    "co-op", "student assistant")
JUNIOR_TERMS = ("junior", "entry level", "entry-level", "graduate", "grad role",
                "associate", "jr.", "jr ", "early career", "no experience required",
                "0-2 years", "beginner")
MID_TERMS = ("mid-level", "mid level", "midlevel", "intermediate", "2-4 years",
             "3+ years", "specialist", "analyst ii")
SENIOR_TERMS = ("senior", "staff engineer", "principal", "lead ", "team lead",
                "head of", "director", "vp of", "vice president", "manager,",
                "architect", "sr.", "sr ", "5+ years", "7+ years", "10+ years",
                "expert", "chief")

# --- Format ---------------------------------------------------------------
FREELANCE_TERMS = ("freelance", "freelancer", "contract", "contractor", "gig",
                   "project-based", "project based", "consultant", "b2b",
                   "independent contractor", "per project", "hourly rate")
PART_TIME_TERMS = ("part-time", "part time", "parttime", "flexible hours",
                   "20 hours", "25 hours", "hours per week", "side project",
                   "evenings", "weekend")
FULL_TIME_TERMS = ("full-time", "full time", "fulltime", "permanent", "40 hours")

# --- Remote ---------------------------------------------------------------
REMOTE_TERMS = ("remote", "work from home", "wfh", "distributed team",
                "anywhere", "home office", "telecommute", "fully remote",
                "remote-first", "remote first")
ONSITE_TERMS = ("on-site", "on site", "onsite", "in-office", "in office",
                "hybrid", "must be located in", "relocation required")

# --- Language requirements ------------------------------------------------
# Many annotation and localisation postings are one role templated across
# dozens of languages. Without this, they flood the deck with jobs that are
# unreachable because they demand a language the candidate does not speak.
KNOWN_LANGUAGES = (
    "arabic", "bulgarian", "catalan", "croatian", "czech", "danish", "dutch",
    "english", "estonian", "farsi", "filipino", "finnish", "french", "german",
    "greek", "hebrew", "hindi", "hungarian", "indonesian", "italian",
    "japanese", "korean", "latvian", "lithuanian", "malay", "mandarin",
    "norwegian", "persian", "polish", "portuguese", "romanian", "russian",
    "serbian", "slovak", "slovenian", "spanish", "swedish", "tagalog", "thai",
    "turkish", "ukrainian", "urdu", "vietnamese", "chinese", "cantonese",
    "macedonian", "albanian", "bosnian", "icelandic", "irish", "welsh",
    "swahili", "bengali", "tamil", "telugu", "punjabi", "marathi",
    "lao", "khmer", "burmese", "nepali", "sinhala", "amharic", "somali",
    "pashto", "kurdish", "azerbaijani", "kazakh", "uzbek", "georgian",
    "armenian", "mongolian", "maltese", "basque", "galician", "flemish",
    "afrikaans", "zulu", "yoruba", "igbo", "hausa", "javanese", "sundanese",
)

_LANG_ALT = "|".join(sorted(KNOWN_LANGUAGES, key=len, reverse=True))

# A language is only treated as *required* when the posting says so plainly.
# A passing mention in a benefits list must not gate the job out.
LANGUAGE_REQUIREMENT_PATTERNS = (
    # "[Russian - Poland] - Voice Recording Specialist"
    rf"\[\s*({_LANG_ALT})\b",
    # "Translation Evaluator - Russian/English"
    rf"\b({_LANG_ALT})\s*[/&]\s*(?:{_LANG_ALT})\b",
    rf"\b(?:{_LANG_ALT})\s*[/&]\s*({_LANG_ALT})\b",
    # "native Russian", "fluent in Polish", "Greek speaker"
    rf"\b(?:native|fluent|proficient|professional)\s+(?:in\s+)?({_LANG_ALT})\b",
    rf"\b({_LANG_ALT})\s+(?:speaker|native|fluency|proficiency)\b",
    rf"\b(?:must speak|fluency in|proficiency in|speak)\s+({_LANG_ALT})\b",
    # "Russian (Native)" as it appears in localisation postings
    rf"\b({_LANG_ALT})\s*\(\s*(?:native|c2|c1)\b",
    # "Lao Voice Recording Project", "German Content Moderator" — for these
    # role types a leading language name is the requirement by definition.
    rf"\b({_LANG_ALT})\s+(?:voice|speech|audio|transcription|transcriber|"
    rf"translation|translator|localization|localisation|linguist|annotator|"
    rf"reviewer|moderator|evaluator|copywriter|data collection|content|"
    rf"language|market|search|ads?)\b",
)


# --- Region restrictions --------------------------------------------------
# "Remote (USA)" is remote and still unreachable from Sofia. Boards encode the
# restriction in the location string, so it is cheap to read and expensive to
# ignore — these roles otherwise sit near the top of the deck permanently.
REGION_TOKENS = {
    "usa": "USA", "u.s.": "USA", "u.s.a.": "USA", "us": "USA",
    "united states": "USA", "america": "USA", "americas": "Americas",
    "canada": "Canada", "latam": "LatAm", "latin america": "LatAm",
    "brazil": "Brazil", "mexico": "Mexico", "argentina": "Argentina",
    "india": "India", "japan": "Japan", "china": "China", "korea": "Korea",
    "singapore": "Singapore", "apac": "APAC", "australia": "Australia",
    "new zealand": "New Zealand", "philippines": "Philippines",
    "africa": "Africa", "nigeria": "Nigeria", "kenya": "Kenya",
    "uk": "UK", "united kingdom": "UK", "ireland": "Ireland",
    "germany": "Germany", "france": "France", "spain": "Spain",
    "portugal": "Portugal", "poland": "Poland", "netherlands": "Netherlands",
    "bulgaria": "Bulgaria", "romania": "Romania", "europe": "Europe",
    "eu": "Europe", "emea": "EMEA", "cet": "Europe", "cest": "Europe",
}

# Locations that place no restriction at all.
UNRESTRICTED_TOKENS = (
    "worldwide", "anywhere", "global", "international", "any", "remote",
    "work from home", "fully remote", "remote-first", "distributed",
)

# Regions a Europe-based candidate can realistically work from.
DEFAULT_ALLOWED_REGIONS = (
    "Europe", "EMEA", "UK", "Ireland", "Germany", "France", "Spain",
    "Portugal", "Poland", "Netherlands", "Bulgaria", "Romania",
)


# --- Category -------------------------------------------------------------
CATEGORY_INTERNSHIP = "Internships"
CATEGORY_FREELANCE = "Freelance gigs"
CATEGORY_PART_TIME = "Part-time remote"
CATEGORY_FULL_TIME = "Full-time remote"
CATEGORY_AI = "AI & Coding"
CATEGORY_TRUST_SAFETY = "Trust & Safety"
CATEGORY_POLICY = "Political/Policy"
CATEGORY_MARKETS = "Markets"
CATEGORY_ADMIN = "Admin/Support"
CATEGORY_OTHER = "Other"

ALL_CATEGORIES = (
    CATEGORY_INTERNSHIP, CATEGORY_FREELANCE, CATEGORY_PART_TIME,
    CATEGORY_FULL_TIME, CATEGORY_AI, CATEGORY_TRUST_SAFETY,
    CATEGORY_POLICY, CATEGORY_MARKETS, CATEGORY_ADMIN, CATEGORY_OTHER,
)

# Domain -> topical category, used when a posting is better described by what
# it is about than by its employment format.
DOMAIN_CATEGORY = {
    "ai": CATEGORY_AI,
    "tech": CATEGORY_AI,
    "trust_safety": CATEGORY_TRUST_SAFETY,
    "policy": CATEGORY_POLICY,
    "markets": CATEGORY_MARKETS,
    "admin": CATEGORY_ADMIN,
    "languages": CATEGORY_ADMIN,
}


def contains_term(haystack: str, term: str) -> bool:
    """Whole-word-ish containment.

    Multi-word terms and terms with punctuation are matched as substrings;
    single alphanumeric words use word boundaries so that 'ai' does not fire
    inside 'chair' and 'sql' does not fire inside 'mysqld'.
    """
    if " " in term or not term.isalnum():
        return term in haystack
    return re.search(rf"\b{re.escape(term)}\b", haystack) is not None


def find_terms(haystack: str, terms: tuple[str, ...]) -> list[str]:
    return [t for t in terms if contains_term(haystack, t)]

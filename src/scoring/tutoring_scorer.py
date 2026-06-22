"""Heuristic scorer for the private-tutoring branch.

Pure-rule scorer (no LLM calls). The LLM is only used to *parse* the raw
parent message; numeric scoring follows the rubric in
``docs/dual-pathway.md`` §5 exactly.

Why deterministic? Three reasons:

1. Re-runs are reproducible. We can diff scores after the parser improves
   and know whether it was the rubric or the LLM that changed.
2. Lead triage is high-volume-and-low-stakes (one Telegram DM per minute
   worst case). Per-lead LLM calls would double-fire on the same provider
   budgets the school pipeline already uses.
3. Auditable. The user wants to know *why* a lead scored 62, not 58 — a
   rule table lets us show the breakdown in the proposal notify.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

from src.config import settings

log = logging.getLogger("scoring.tutoring")


# ---------------------------------------------------------------------------
# Taxonomies
# ---------------------------------------------------------------------------

Curriculum = Literal[
    "IGCSE_Edexcel", "IGCSE_CIE",
    "A-Level_Edexcel", "A-Level_CIE",
    "IB", "AP", "American",
    "GCSE_Combined",
    "Other",
]

IN_SCOPE: frozenset[Curriculum] = frozenset({
    "IGCSE_Edexcel", "IGCSE_CIE",
    "A-Level_Edexcel", "A-Level_CIE",
})

OUT_OF_SCOPE: frozenset[Curriculum] = frozenset({
    "IB", "AP", "American",
    "GCSE_Combined",
    "Other",
})


# ---------------------------------------------------------------------------
# Heuristic helpers
# ---------------------------------------------------------------------------

_CURRICULUM_PATTERNS: list[tuple[Curriculum, re.Pattern[str]]] = [
    ("IGCSE_Edexcel",   re.compile(r"\b(igcse|gcse).{0,40}(edexcel|pearson)\b", re.I)),
    ("IGCSE_CIE",       re.compile(r"\b(igcse|gcse).{0,40}(cie|cambridge)\b", re.I)),
    ("A-Level_Edexcel", re.compile(r"\b(a[- ]?level|a level).{0,40}(edexcel|pearson)\b", re.I)),
    ("A-Level_CIE",     re.compile(r"\b(a[- ]?level|a level).{0,40}(cie|cambridge)\b", re.I)),
    ("IB",              re.compile(r"\b(ib\b|international baccalaureate)\b", re.I)),
    ("AP",              re.compile(r"\bap\b.{0,30}(physics|calculus)", re.I)),
    ("American",        re.compile(r"\b(sat|act|us high school|american curriculum|american school)\b", re.I)),
    ("GCSE_Combined",   re.compile(r"\bcombined (science|trilogy)\b", re.I)),
    ("IGCSE_Edexcel",   re.compile(r"\b(igcse|gcse)\b", re.I)),
    ("A-Level_Edexcel", re.compile(r"\b(a[- ]?level|a level|as[- ]?level|a2)\b", re.I)),
]


def _classify_curriculum(text: str) -> Curriculum:
    """Return the most specific curriculum mentioned, else ``Other``."""
    for label, pat in _CURRICULUM_PATTERNS:
        if pat.search(text):
            return label
    return "Other"


_SUBJECT_KEYWORDS: dict[str, re.Pattern[str]] = {
    "physics": re.compile(r"\bphysics\b", re.I),
    "maths":   re.compile(r"\b(math|maths|mathematics)\b", re.I),
    "combined": re.compile(r"\bcombined (science|trilogy)\b", re.I),
    "general_science": re.compile(r"\b(general science|science (subject|class))\b", re.I),
}


def _classify_subject(text: str) -> str:
    has_physics = bool(_SUBJECT_KEYWORDS["physics"].search(text))
    has_maths = bool(_SUBJECT_KEYWORDS["maths"].search(text))
    has_combined = bool(_SUBJECT_KEYWORDS["combined"].search(text))
    has_general = bool(_SUBJECT_KEYWORDS["general_science"].search(text))

    if has_combined:
        return "combined_science"
    if has_general and not has_physics:
        return "general_science"
    if has_physics and has_maths:
        return "physics_plus_maths"
    if has_physics:
        return "pure_physics"
    if has_maths:
        return "pure_maths"
    return "other"


_URGENCY_KEYWORDS: dict[str, re.Pattern[str]] = {
    "high":   re.compile(r"\b(urgent|asap|immediately|this week|next week|exam\s+is?\s+in\s+\d{1,2}\s*weeks?|exam\s+in\s+\d{1,2}\s*weeks?|retake|resit|missed|panick(?:ing|ed))\b", re.I),
    "medium": re.compile(r"\b(soon|next month|in a (?:couple|few) (?:of )?(?:months|weeks)|preparing for|mock exam|term exam|end of term)\b", re.I),
    "low":    re.compile(r"\b(next year|long term|general improvement|ahead of|advanced|extracurricular|optional)\b", re.I),
}


def _classify_urgency(text: str) -> str:
    for level, pat in (("high", _URGENCY_KEYWORDS["high"]),
                       ("medium", _URGENCY_KEYWORDS["medium"]),
                       ("low", _URGENCY_KEYWORDS["low"])):
        if pat.search(text):
            return level
    return "unknown"


_WEEKS_RE = re.compile(
    r"(?:exam|test|assessment|retake|resit|final|board)\b[^.\n]{0,40}?\b(\d{1,2})\s*(weeks?|months?)\b",
    re.I,
)


def _weeks_to_exam(text: str) -> int | None:
    """Best-effort estimate of weeks until exam. ``None`` if unmentioned."""
    m = _WEEKS_RE.search(text)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    return n if unit.startswith("week") else n * 4


_BUDGET_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    # Currency-prefixed highest-priority; fall back to bare numbers.
    # Use (?<![A-Za-z0-9]) instead of \b because the `£` character is a
    # "word" char under Python's default Unicode-aware \b, so `\b£` never
    # matches in practice.
    (re.compile(r"(?<![A-Za-z0-9])(?:usd|\$)\s*(\d{2,3})\b", re.I), 1.0),
    (re.compile(r"(?<![A-Za-z0-9])(?:gbp|£)\s*(\d{2,3})\b", re.I), 1.27),  # GBP -> USD
    (re.compile(r"(?<![A-Za-z0-9])(?:aed|د\.إ)\s*(\d{2,4})\b", re.I), 0.27), # AED -> USD
    (re.compile(r"(?<![A-Za-z0-9])(?:qar|ر\.ق)\s*(\d{2,4})\b", re.I), 0.27), # QAR -> USD
    (re.compile(r"(?<![A-Za-z0-9])(?:sar|ر\.س)\s*(\d{2,4})\b", re.I), 0.27), # SAR -> USD
    (re.compile(r"(?<![A-Za-z0-9])(?:hkd|hk\$)\s*(\d{2,4})\b", re.I), 0.13), # HKD -> USD
    (re.compile(r"(?<![A-Za-z0-9])(?:sgd|s\$)\s*(\d{2,4})\b", re.I), 0.74),  # SGD -> USD
    # Bare number patterns look weaker; only match after "per hour" / "hr"
    (re.compile(r"\b(\d{2,3})\s*(?:usd|dollars?)[\s/]*(?:per\s*)?(?:hour|hr|h)\b", re.I), 1.0),
    (re.compile(r"\b(\d{2,3})\s*(?:gbp|pounds?)[\s/]*(?:per\s*)?(?:hour|hr|h)\b", re.I), 1.27),
]


def _extract_budget_usd(text: str) -> float | None:
    for pat, fx in _BUDGET_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return round(float(m.group(1)) * fx, 2)
            except ValueError:
                continue
    return None


_TIMEZONE_OFFSETS: dict[str, float] = {
    # Gulf
    "uae": 4.0, "dubai": 4.0, "abudhabi": 4.0, "abu dhabi": 4.0, "sharjah": 4.0,
    "qatar": 3.0, "doha": 3.0,
    "saudi": 3.0, "saudi arabia": 3.0, "riyadh": 3.0, "jeddah": 3.0,
    "kuwait": 3.0, "bahrain": 3.0, "oman": 4.0, "muscat": 4.0,
    # UK / Europe
    "uk": 0.0, "united kingdom": 0.0, "london": 0.0, "manchester": 0.0, "birmingham": 0.0,
    "england": 0.0, "scotland": 0.0, "wales": 0.0, "northern ireland": 0.0,
    "ireland": 0.0, "dublin": 0.0,
    # East Asia
    "hong kong": 8.0, "hk": 8.0,
    "singapore": 8.0,
    "china": 8.0, "mainland china": 8.0, "beijing": 8.0, "shanghai": 8.0, "shenzhen": 8.0,
    "taiwan": 8.0, "taipei": 8.0,
    "malaysia": 8.0, "kuala lumpur": 8.0,
    # Other (rough)
    "egypt": 2.0, "cairo": 2.0,
    "turkey": 3.0, "istanbul": 3.0,
    "jordan": 3.0, "amman": 3.0,
    "lebanon": 2.0, "beirut": 2.0,
}


def _extract_timezone_hours(text: str) -> float | None:
    for keyword, offset in _TIMEZONE_OFFSETS.items():
        if re.search(rf"\b{re.escape(keyword)}\b", text, re.I):
            return offset
    return None


# ---------------------------------------------------------------------------
# Rubric (docs/dual-pathway.md §5)
# ---------------------------------------------------------------------------

def _score_curriculum(curriculum: Curriculum) -> int:
    return 30 if curriculum in IN_SCOPE else 0  # out_of_scope override below


def _score_subject(subject: str) -> int:
    return {
        "pure_physics": 25,
        "physics_plus_maths": 25,
        "combined_science": 15,
        "general_science": 15,
        "pure_maths": 12,
        "other": 5,
    }.get(subject, 5)


def _score_timezone(offset_h: float | None) -> int:
    if offset_h is None:
        return 8  # unknown -> neutral mid-band
    abs_off = abs(offset_h - 2.0)  # Tripoli is UTC+2
    if abs_off <= 2.5:        # Gulf (UAE/Qatar/Saudi 1-3h from Tripoli) + same-zone (Libya+/-)
        return 20
    if abs_off <= 3.5:        # wider Tier 1 fallback
        return 18
    if abs_off <= 6.0:        # SG/HK/CN (6h)
        return 14
    if abs_off <= 7.0:        # CN (7h)
        return 12
    return 8                  # far


_URGENCY_WEEKS_BANDS = [(8, 10), (16, 7), (None, 4)]  # ≤8w : 10 ; ≤16w : 7 ; rest : 4


def _score_urgency(weeks: int | None, urgency_label: str) -> int:
    if weeks is not None:
        for threshold, score in _URGENCY_WEEKS_BANDS:
            if threshold is None or weeks <= threshold:
                return score
    # Fall back on the keyword label
    return {"high": 7, "medium": 5, "low": 3, "unknown": 2}[urgency_label]


_BUDGET_TIERS = [(50.0, 15), (35.0, 12), (32.0, 8)]  # ≥$50:15 ; ≥$35:12 ; ≥$32:8


def _score_budget(budget_usd: float | None) -> tuple[int, bool]:
    """Return (score, is_below_floor). Below floor -> auto low_budget_hold."""
    if budget_usd is None:
        return 0, False  # don't penalise unknown budget as a hold
    if budget_usd < settings.tutoring_min_rate_usd:
        return 0, True
    for floor, score in _BUDGET_TIERS:
        if budget_usd >= floor:
            return score, False
    return 0, True


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass
class TutoringScore:
    curriculum: Curriculum
    subject: str
    weeks_to_exam: int | None
    urgency: str
    timezone_offset_hours: float | None
    budget_per_hour_usd: float | None
    match_score: int
    score_breakdown: dict[str, int]
    status: Literal["new", "low_budget_hold", "out_of_scope_hold"]
    proposed_rate_usd: float

    @property
    def is_in_scope(self) -> bool:
        return self.curriculum in IN_SCOPE


# ---------------------------------------------------------------------------
# Top-level scoring entry
# ---------------------------------------------------------------------------

def score_tutoring_lead(text: str) -> TutoringScore:
    """Score a raw parent/student message and return a typed result.

    Pure function. Same input -> same output. Safe to call often.
    """
    curriculum = _classify_curriculum(text)  # type: ignore[assignment]
    subject = _classify_subject(text)
    weeks = _weeks_to_exam(text)
    urgency_label = _classify_urgency(text)
    tz_h = _extract_timezone_hours(text)
    budget_usd = _extract_budget_usd(text)

    # Compose
    out_of_scope = curriculum in OUT_OF_SCOPE
    budget_score, below_floor = _score_budget(budget_usd)

    if out_of_scope and settings.tutoring_out_of_scope_hold:
        status = "out_of_scope_hold"
    elif below_floor:
        status = "low_budget_hold"
    else:
        status = "new"

    breakdown = {
        "curriculum": _score_curriculum(curriculum),
        "subject":    _score_subject(subject),
        "timezone":   _score_timezone(tz_h),
        "budget":     budget_score,
        "urgency":    _score_urgency(weeks, urgency_label),
    }
    if out_of_scope:
        # Force curriculum to 0 when out of scope, regardless of base score.
        breakdown["curriculum"] = 0

    match_score = max(0, min(100, sum(breakdown.values())))

    # Proposed rate: midpoint of the configured band; if budget known and
    # higher, anchor slightly above the band but cap at 2x.
    band = settings.tutoring_rate_band_default_usd
    proposed = band
    if budget_usd is not None and budget_usd > band:
        proposed = min(budget_usd, band * 2)

    return TutoringScore(
        curriculum=curriculum,
        subject=subject,
        weeks_to_exam=weeks,
        urgency=urgency_label,
        timezone_offset_hours=tz_h,
        budget_per_hour_usd=budget_usd,
        match_score=match_score,
        score_breakdown=breakdown,
        status=status,
        proposed_rate_usd=proposed,
    )

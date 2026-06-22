"""Tutoring proposal generator.

Drafts a 200-300 word parent-facing reply anchored in the TutoringBrief
and the parent-facing profile blurb. Designed to write in British English,
warm-but-direct, end on a free-intro-session offer.

Two modes:

- **template**: deterministic, no LLM call, sub-50ms. Default for v1.
  Files tagged ``__fallback`` in the cover_letters directory.
- **llm**:     routes through the same provider pool the school pipeline
  uses (re-using ``src.scoring.llm_scorer.LLMScorer``'s single-fn shape).
  Files tagged ``__LLM``. Wired but *not enabled* until the v1 parser is
  in place to populate ``TutoringBrief``.

The split mirrors the cover-letter generator: template is always safe;
LLM is opt-in via ``USE_LLM=True`` once we're confident.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agents.models import TutoringBrief
from src.scoring.tutoring_scorer import TutoringScore

log = logging.getLogger("job-hunter")


OUTPUT_DIR = Path("data/cover_letters")


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------

def _load_profile() -> dict[str, Any]:
    try:
        with open("data/profile_tutoring.json", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        log.warning("data/profile_tutoring.json missing; using stub profile")
        return {
            "headline": "Online IGCSE & A-Level Physics tutor based in Tripoli",
            "qualifications_summary": (
                "B.Sc. Mechanical Engineering, PGCEi candidate (LJMU). "
                "Four years of IGCSE/A-Level Physics teaching experience."
            ),
            "intro_session_minutes": 30,
            "intro_session_promise": "Free, no-obligation 30-minute session.",
            "rate_band_usd_per_hour": "35-60",
            "response_sla_hours": 24,
            "preferred_contact_channels": ["WhatsApp", "Telegram", "Email"],
            "subjects": ["Physics", "Maths"],
            "languages": ["English (fluent)", "Arabic (native)"],
        }


# ---------------------------------------------------------------------------
# Voice / register scaling
# ---------------------------------------------------------------------------

def _voice_register(level: int) -> str:
    """Map 1-5 warmth target to a tone directive for the template."""
    return {
        1: "formal and academic",
        2: "polite and professional",
        3: "warm and direct — recommended default",
        4: "warm, conversational, with a personal note",
        5: "parental and reassuring — like writing to a fellow parent",
    }.get(level, "warm and direct — recommended default")


# ---------------------------------------------------------------------------
# Template fallback
# ---------------------------------------------------------------------------

_CURRICULUM_HUMAN = {
    "IGCSE_Edexcel":   "IGCSE (Pearson Edexcel)",
    "IGCSE_CIE":       "IGCSE (Cambridge CIE)",
    "A-Level_Edexcel": "A-Level (Pearson Edexcel)",
    "A-Level_CIE":     "A-Level (Cambridge CIE)",
    "IB":              "IB",
    "AP":              "AP",
    "American":        "the American curriculum",
    "GCSE_Combined":   "GCSE Combined Science",
    "Other":           "your syllabus",
}


_SUBJECT_HUMAN = {
    "pure_physics":         "physics",
    "physics_plus_maths":   "physics and maths",
    "pure_maths":           "maths",
    "combined_science":     "combined science",
    "general_science":      "general science",
    "other":                "your subject",
}


def _render_template(
    brief: TutoringBrief,
    score: TutoringScore,
    profile: dict[str, Any],
) -> str:
    pains = "; ".join(brief.student_pain_points[:2]) if brief.student_pain_points else "the topics you mentioned"
    curriculum_human = _CURRICULUM_HUMAN.get(score.curriculum, "your syllabus")
    subject_human = _SUBJECT_HUMAN.get(score.subject, "your subject")
    intro_minutes = int(profile.get("intro_session_minutes", 30))
    intro_promise = profile.get(
        "intro_session_promise",
        f"Free, no-obligation {intro_minutes}-minute session.",
    )
    rate_band = profile.get("rate_band_usd_per_hour", "35-60")
    sla = int(profile.get("response_sla_hours", 24))
    channels = profile.get("preferred_contact_channels", ["WhatsApp"])
    preferred = ", ".join(channels[:2]) if channels else "your preferred channel"

    voice_note = _voice_register(brief.voice_warmth_target)
    red_flags = brief.red_flags or []
    red_flag_block = ""
    if red_flags:
        red_flag_block = (
            "\n\nA note before we go further: I can't help with "
            + ", ".join(red_flags[:2])
            + " — that's outside what I offer. Everything else is fair game.\n"
        )

    return (
        f"Hi — I'm Mahmoud. Thanks for getting in touch about {subject_human}.{red_flag_block}\n\n"
        f"From what you've shared, the core issue is {pains}. "
        f"My specialism is {curriculum_human}, and I'd start the "
        f"{intro_minutes}-minute intro session by mapping that exact topic to the syllabus, "
        f"identifying the highest-leverage gaps, and agreeing where we'd begin.\n\n"
        f"Sessions are online, run in 60-minute blocks, and are paced to your exam timeline. "
        f"My usual rate is USD {rate_band} per hour, with the first {intro_minutes} minutes free — "
        f"no charge, no obligation — so we can both see whether I'm a good fit before you commit.\n\n"
        f"If you'd like to go ahead, send me two or three time windows and I'll send a calendar "
        f"link back within {sla} hours. I usually work over {preferred}.\n\n"
        f"Speak soon,\nMahmoud\n"
    )


# ---------------------------------------------------------------------------
# Optional LLM path (wired, not enabled by default)
# ---------------------------------------------------------------------------

PROPOSAL_PROMPT = """You are a tutor writing a first reply to a parent who got in touch about lessons.

PARENT MESSAGE (excerpt):
{raw_excerpt}

PARSED STRUCTURED BRIEF (JSON):
{brief}

SCORER OUTPUT (matching, currency, urgency, proposed rate band):
{scorer}

PARENT-FACING PROFILE BLURB:
{profile}

VOICE TARGET: {voice_note}

WRITE A 200-300 WORD REPLY THAT:
1. Acknowledges the parent's pain point by phrase (cite exactly one item from student_pain_points).
2. Names the curriculum + grade context briefly.
3. One sentence on what we'd cover in the free 30-minute intro (cite recommended_first_session_focus).
4. Mentions the free intro session, "no charge, no obligation" — repeated twice.
5. Plain rate band (USD 35-60) without invented testimonials.
6. CTA: pick a time via WhatsApp or preferred channel, mention 24-hour response SLA.

RULES:
- British English throughout.
- No markdown, no bullet points — flowing paragraphs.
- No specific grade guarantees. No fake testimonial claims.
- If red_flags are non-empty, mention them honestly in a sentence.
- Address: "Hi — I'm Mahmoud." (no "Dear Parent"). Sign off "Speak soon, Mahmoud".

Output only the reply body."""


@dataclass
class ProposalResult:
    text: str
    mode: str   # "template" | "llm"
    path: Path  # file written


def _save(text: str, lead_id: str, mode: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = "LLM" if mode == "llm" else "fallback"
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    path = OUTPUT_DIR / f"tutoring_{lead_id}_{tag}_{timestamp}.txt"
    path.write_text(text, encoding="utf-8")
    return path


def _strip_wrappers(text: str) -> str:
    """Strip ``` fences and leading prose before ``Hi —`` if the LLM drifted."""
    text = text.strip()
    text = re.sub(r"^```(?:text|markdown)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Capture from the first greeting onward
    m = re.search(r"Hi\b", text)
    if m:
        text = text[m.start():]
    return text.strip()


def generate_proposal(
    lead_row: dict[str, Any],
    brief: TutoringBrief,
    score: TutoringScore,
    use_llm: bool = False,
    llm_call: Any = None,
) -> ProposalResult:
    """Generate a parent-facing reply.

    Args:
        lead_row: full ``tutoring_leads`` row (id, raw_message at minimum).
        brief:    parsed ``TutoringBrief`` (parser is the *next* stage; for
                  now callers may pass :meth:`TutoringBrief.fallback`).
        score:    output of ``score_tutoring_lead``.
        use_llm:  if False, template mode. If True, must also pass
                  ``llm_call`` (callable ``(prompt: str) -> str | None``).
                  Kept off by default until the v1 LLM parser is in place.

    Returns:
        :class:`ProposalResult` with the body text, mode tag, and the file
        path written under ``data/cover_letters/``.
    """
    profile = _load_profile()
    lead_id = lead_row.get("id") or "unknown"

    # ---- Template path (always available) ----
    template_text = _render_template(brief, score, profile)
    if not use_llm:
        path = _save(template_text, lead_id, "template")
        return ProposalResult(text=template_text, mode="template", path=path)

    # ---- LLM path (opt-in) ----
    if llm_call is None:
        log.warning("use_llm=True but no llm_call provided; falling back to template")
        path = _save(template_text, lead_id, "template")
        return ProposalResult(text=template_text, mode="template", path=path)

    raw_excerpt = (lead_row.get("raw_message") or "")[:1500]
    scorer_summary = json.dumps({
        "curriculum": score.curriculum,
        "subject": score.subject,
        "weeks_to_exam": score.weeks_to_exam,
        "urgency": score.urgency,
        "match_score": score.match_score,
        "score_breakdown": score.score_breakdown,
        "proposed_rate_usd": score.proposed_rate_usd,
    }, indent=2)

    prompt = PROPOSAL_PROMPT.format(
        raw_excerpt=raw_excerpt,
        brief=brief.model_dump_json(indent=2),
        scorer=scorer_summary,
        profile=json.dumps(profile, indent=2),
        voice_note=_voice_register(brief.voice_warmth_target),
    )

    try:
        raw = llm_call(prompt)
    except Exception as e:
        log.warning("LLM proposal call failed (%s); using template", e)
        raw = None

    if raw:
        text = _strip_wrappers(raw)
        if 50 <= len(text) <= 2000:
            path = _save(text, lead_id, "llm")
            return ProposalResult(text=text, mode="llm", path=path)
        log.warning("LLM output out of range (%d chars); using template", len(text))

    path = _save(template_text, lead_id, "template")
    return ProposalResult(text=template_text, mode="template", path=path)

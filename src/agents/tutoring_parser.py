"""Tutoring Parser — extracts a :class:`TutoringBrief` from raw parent text.

Distinct from :mod:`src.agents.research_agent`: this is a single-shot
interpretation call, no tool-calling, no web search. The job is to read a
(parent) message and produce a structured brief that the proposal generator
can anchor to.

Design choices:

- **Single provider per call.** The school pipeline uses a weighted cascade
  because it batches 5+ jobs per call and pays the cost in rate-limit fees.
  Tutoring leads trickle in (1-3 per hour worst case), so a single provider
  is enough. If it fails, the next provider in cascade order is tried.
- **60-second deadline** (matches ``settings.tutoring_parse_timeout_s``).
  On any failure we return ``TutoringBrief.fallback(raw_message)`` so the
  pipeline never blocks.
- **No re-try inside the lead.** A failed parse marks the lead as having
  ``tutoring_brief_json`` not-yet-null but the parser isn't re-invoked on
  this row in v1; it just gets the fallback. (Future: replace with a retry
  counter column.)
- **British English output.** Spelling enforced in the prompt.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

import httpx

from src.agents.models import TutoringBrief
from src.config import settings

log = logging.getLogger("tutoring.parser")


# ---------------------------------------------------------------------------
#  Prompt
# ---------------------------------------------------------------------------

PARSE_PROMPT = """You are extracting structured information from a parent (or student) message asking for a tutor. Your output drives a proposal that will be sent back to them. Be precise; do not invent details.

RAW PARENT MESSAGE (may include English, Arabic, Arabizi, or mixed; please read for meaning, not for spelling):
\"\"\"{raw}\"\"\"

PARTICIPANT BACKGROUND (for context, do not echo anywhere):
- Tutor: Mahmoud Alsini (Tripoli, Libya). IGCSE + A-Level Physics and Maths via Pearson Edexcel and Cambridge CIE.
- Voice can be anything between formal and warm-parental; pick the right level for this parent.

EXTRACT:

1. **student_pain_points** (1-4 items): What is the student actually struggling with? Pick from concrete things mentioned (topic name, exam timing, last result, behavioural). If they're vague, paraphrase them faithfully — do NOT invent topics.

2. **parent_signals** (0-4 items): Urgency cues, budget hints ("I can pay 200 dirhams", "we can afford it"), prior tutors tried, language of address ("I'm worried", "he's falling behind"). Skip if the message is silent on these.

3. **subject_alignment**: One paragraph naming the curricular bucket (e.g. "IGCSE Edexcel Physics Unit 4 — Electricity"; "A-Level Edexcel Mechanics"; "Year 10 Combined Science"). Be specific even if the parent was vague.

4. **recommended_first_session_focus**: 1-2 sentences on what the FREE 30-MINUTE intro session should cover for this specific case (assessment of current level, paper-style diagnostic, syllabus-mapping, etc.).

5. **voice_warmth_target**: an integer 1-5.
   1 = formal / academic / "Dear Sir"
   2 = polite and professional
   3 = warm and direct (recommended default)
   4 = warm, conversational, with a personal note ("as a teacher who teaches daily in this syllabus, I see this exact gap often")
   5 = parental, reassuring — like a fellow parent writing to a working parent

   Pick based on: how the parent wrote (warmth vs clipped), and what the situation looks like (panic vs planned).

6. **red_flags** (0-4 items): Concerns to surface in the proposal reply. Examples, not all may apply: "homework-completion request" (the parent wants someone to do the homework rather than teach), "grade guarantee", "exam in less than 2 weeks for major content gap", "asking for free trial lesson".

OUTPUT FORMAT (read carefully):
- Respond with EXACTLY one JSON object. No prose, no markdown, no code fences.
- The first character of your response must be {{ and the last must be }}.
- All string fields use British English. No American spellings (color→colour, organize→organise, program→programme).

SCHEMA:
{{
  "student_pain_points": ["<string>", ...],
  "parent_signals": ["<string>", ...] or [],
  "subject_alignment": "<string>",
  "recommended_first_session_focus": "<string>",
  "voice_warmth_target": <int 1-5>,
  "red_flags": ["<string>", ...] or []
}}"""


# ---------------------------------------------------------------------------
#  JSON extraction — mirror of the LLMScorer helpers, deliberately duplicated
#  so this module is self-contained and importable independently.
# ---------------------------------------------------------------------------

def _strip_wrappers(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    return text.removesuffix("```").strip()


def _balanced_extract(text: str, start: int, open_ch: str, close_ch: str) -> str | None:
    """Bracket-walk from *start* until balanced, returning the substring."""
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return None


def _fix_json_quirks(text: str) -> str:
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def _extract_json_object(text: str) -> str | None:
    if not text:
        return None
    text = _strip_wrappers(text)
    start = text.find("{")
    if start == -1:
        return None
    candidate = _balanced_extract(text, start, "{", "}")
    if candidate is None:
        return None
    return _fix_json_quirks(candidate)


# ---------------------------------------------------------------------------
#  Provider calls — single-shot, no cascade retry inside this call. Caller
#  is responsible for choosing a provider and rotating if it fails.
#  Mirrors the request shape of LLMScorer's per-provider methods but does
#  NOT depend on LLMScorer: kept small and independent so we can pass any
#  provider implementation in.
# ---------------------------------------------------------------------------

def _call_groq(prompt: str, model: str) -> str | None:
    if not settings.groq_api_key:
        return None
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 700,
            },
            timeout=settings.tutoring_parse_timeout_s,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.warning("groq parser call failed: %s", e)
        return None


def _call_nvidia(prompt: str, model: str) -> str | None:
    if not settings.nvidia_api_key:
        return None
    try:
        r = httpx.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.nvidia_api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 700,
            },
            timeout=settings.tutoring_parse_timeout_s,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.warning("nvidia parser call failed: %s", e)
        return None


def _call_openrouter(prompt: str, model: str) -> str | None:
    if not settings.openrouter_api_key:
        return None
    try:
        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 700,
            },
            timeout=settings.tutoring_parse_timeout_s,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.warning("openrouter parser call failed: %s", e)
        return None


def _call_opencode_zen(prompt: str, model: str = "mimo-v2.5-free") -> str | None:
    """OpenCode Zen single-shot parser call.

    Primary model ``mimo-v2.5-free`` (2026-08-30); falls back to
    ``deepseek-v4-flash-free`` if it errors. Reasoning headroom:
    max_tokens=4096 so reasoning-mode models finish and emit content.
    """
    if not settings.opencode_zen_api_key:
        return None
    for m in ("mimo-v2.5-free", "deepseek-v4-flash-free"):
        try:
            r = httpx.post(
                "https://opencode.ai/zen/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.opencode_zen_api_key}"},
                json={
                    "model": m,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 4096,
                },
                timeout=settings.tutoring_parse_timeout_s,
            )
            if r.status_code in (401, 404):
                log.warning("opencode_zen model %s rejected (HTTP %s) — trying fallback", m, r.status_code)
                continue
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.warning("opencode_zen model %s failed: %s", m, e)
            continue
    return None


def _call_gemini(prompt: str, model: str = "gemini-2.5-flash") -> str | None:
    if not settings.gemini_api_key:
        return None
    try:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": settings.gemini_api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=settings.tutoring_parse_timeout_s,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        log.warning("gemini parser call failed: %s", e)
        return None


def _provider_call(prompt: str) -> str | None:
    """Try providers in priority order until one returns content.

    Priority mirrors ``PROVIDER_WEIGHTS`` from llm_scorer.py but the order
    is biased toward fast/cheap for short single-shot parses.
    Cascade priority matches the project-wide LLM weights (re-ordered
    2026-06-29): opencode_zen → nvidia → groq → openrouter → gemini.
    """
    candidates: list[tuple[str, Callable[[str], str | None]]] = []

    if settings.opencode_zen_api_key:
        candidates.append(("opencode_zen:mimo-v2.5-free",
                           _call_opencode_zen))
    if settings.nvidia_api_key and settings.nvidia_backup_model:
        candidates.append((f"nvidia:{settings.nvidia_backup_model}",
                           lambda p, m=settings.nvidia_backup_model: _call_nvidia(p, m)))
    if settings.groq_api_key and settings.groq_model:
        candidates.append((f"groq:{settings.groq_model}",
                           lambda p, m=settings.groq_model: _call_groq(p, m)))
    if settings.openrouter_api_key and settings.openrouter_model:
        candidates.append((f"openrouter:{settings.openrouter_model}",
                           lambda p, m=settings.openrouter_model: _call_openrouter(p, m)))
    if settings.gemini_api_key:
        candidates.append(("gemini:gemini-2.5-flash", _call_gemini))

    for label, fn in candidates:
        log.info("tutoring_parser trying %s", label)
        content = fn(prompt)
        if content:
            return content
    return None


# ---------------------------------------------------------------------------
#  Public entry
# ---------------------------------------------------------------------------

def parse_tutoring_lead(raw_message: str) -> TutoringBrief:
    """Return a parsed :class:`TutoringBrief` for *raw_message*.

    On any failure (no API key, all providers fail, JSON parse error) we
    return :meth:`TutoringBrief.fallback` so the orchestrator can continue.

    Never raises.
    """
    if not raw_message or not raw_message.strip():
        return TutoringBrief.fallback("")

    # Truncate very long messages to keep prompt under control.
    if len(raw_message) > 8000:
        raw_message = raw_message[:8000]

    prompt = PARSE_PROMPT.format(raw=raw_message)

    try:
        content = _provider_call(prompt)
    except Exception as e:
        log.warning("provider cascade crashed (non-fatal): %s", e)
        content = None

    if not content:
        return TutoringBrief.fallback(raw_message)

    json_str = _extract_json_object(content)
    if not json_str:
        log.warning("could not extract JSON from parser output; using fallback")
        return TutoringBrief.fallback(raw_message)

    try:
        payload = json.loads(json_str)
        brief = TutoringBrief.model_validate(payload)
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("parser JSON invalid (%s); using fallback", e)
        return TutoringBrief.fallback(raw_message)

    return brief


def parse_to_dict(raw_message: str) -> tuple[TutoringBrief, dict[str, Any]]:
    """Like :func:`parse_tutoring_lead` but returns the brief plus a
    JSON-serialisable dict for direct database storage.

    The dict layout matches the ``tutoring_brief_json`` column shape:
      {"schema_version": 1, "brief": {...}}
    """
    brief = parse_tutoring_lead(raw_message)
    return brief, {
        "schema_version": 1,
        "brief": brief.model_dump(mode="json"),
    }

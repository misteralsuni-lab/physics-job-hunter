import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import httpx

from src.config import settings

log = logging.getLogger("job-hunter")

_SENTINEL = object()

COVER_LETTER_PROMPT = """You are a professional educational copywriter drafting a highly targeted cover letter. Write in British English.

JOB DETAILS:
{job}

RESEARCH BRIEF:
{research_brief}

APPLICANT PROFILE:
{profile}

CANDIDATE: Mahmoud altaher Alsini — B.Sc. Engineering Science, University of Tripoli (2021), completing PGCEi at Liverpool John Moores University, 4+ years teaching Physics and Mathematics internationally, expertise in Pearson Edexcel IGCSE (4PH1) and A-Level curricula, pedagogical focus on Cognitive Load Theory and Assessment for Learning.

FORMAT:
- Address: "Dear Hiring Manager"
- Closing: "Yours faithfully," followed by "Mahmoud altaher Alsini"

CRITICAL CONSTRAINTS:
1. LENGTH CEILING: Maximum 300 words.
2. NO CLICHES: Strictly ban generic filler phrases (e.g. "In today's fast-paced educational landscape", "I am thrilled to apply", "I believe I am the perfect fit").
3. ANCHORING: Use the 2-3 institution facts from the research brief. If the brief is empty or generic, extract exactly 2 unique facts from the job description. Explicitly mention them to prove this is not a template.
4. OPENING HOOK: Follow the recommended_angle in the research brief for the opening paragraph.
5. Weave qualifications naturally — do not list them mechanically.
6. NO DATES: Strictly exclude specific accreditation dates or timelines. Focus on your active PGCEi pedagogical alignment, mechanical engineering background, and the institution facts — do not mention year of graduation unless the job explicitly requires it.

Output the letter text directly. No preamble, no commentary, no markdown."""


SPECULATIVE_EMAIL_PROMPT = """You are a professional educational copywriter drafting a highly targeted, SPECULATIVE outreach email for a proactive campaign. Write in British English.

SCHOOL / PROSPECT:
{job}

RESEARCH BRIEF:
{research_brief}

APPLICANT PROFILE:
{profile}

CANDIDATE: Mahmoud Alsini — B.Sc. Engineering Science, University of Tripoli (2020), completing PGCEi at Liverpool John Moores University, 4+ years teaching Physics and Mathematics internationally, expertise in Pearson Edexcel IGCSE (4PH1) and A-Level curricula, pedagogical focus on Cognitive Load Theory and Assessment for Learning.

CONTEXT — SPECULATIVE OUTREACH (no live vacancy):
Mahmoud is building an entry pathway into the Central European international-school market. He has a relative in Dresden and will be visiting Dresden and the nearby city next month. This email is NOT an application for a posted vacancy.

FORMAT:
- Subject line: short, professional.
- Greeting: "Dear Admissions / HR Team" or "Dear Head of Science".
- Closing: "Yours faithfully," followed by "Mahmoud Alsini".

CRITICAL CONSTRAINTS:
1. LENGTH CEILING: Maximum 300 words.
2. NO CLICHES: strictly ban generic filler phrases.
3. ANCHORING: Reference 2-3 specific, unique facts about the school from the RESEARCH BRIEF (e.g. its Edexcel/Physics offering, campus, recent news). If the brief is empty, anchor on the school's stated curriculum from the prospect details.
4. SPECULATIVE FRAMING (mandatory):
   - Introduce Mahmoud's Pearson Edexcel IGCSE/A-Level Physics & Maths specialism.
   - State he will be visiting Dresden and the nearby city next month (he has a relative there).
   - Propose a brief meeting, informal interview, or demo lesson in case a Physics/Maths position opens in the near future.
   - Note his CV is attached (CV_Mahmoud_Alsini.html).
   - Do NOT say "I am applying for the vacancy of X" or imply a posted job exists.
5. Weave qualifications naturally.

Output the email text directly. No preamble, no commentary, no markdown."""


def _generate_fallback_letter(job: dict[str, Any], profile: dict[str, Any]) -> str:
    """Generate a structured cover letter from a template when no LLM is available."""
    title = job.get("title", "the advertised position")
    school = job.get("school", "your school")

    return f"""Dear Hiring Manager,

I am writing to express my strong interest in the {title} position at {school}. With over four years of experience teaching Physics and Mathematics across international curricula, I am confident that my background and pedagogical approach align closely with the requirements of this role.

I hold a B.Sc. in Engineering Science from the University of Tripoli (2021) and am currently completing my PGCEi at Liverpool John Moores University. This combination of subject-specific depth and professional teaching qualification enables me to bridge theoretical physics with evidence-informed classroom practice — an approach I refer to as "Applied Mastery."

Throughout my teaching career, I have developed deep expertise in the Pearson Edexcel IGCSE (4PH1 linear specification) and A-Level curricula. I am skilled at preparing students for external examinations while fostering genuine scientific curiosity and critical thinking.

My classroom practice is grounded in Cognitive Load Theory and Assessment for Learning. I design instruction that respects the architecture of working memory, uses targeted formative assessment to identify gaps, and adapts my teaching in real time to ensure every student progresses. These strategies have proven particularly effective in helping students master complex topics in Physics.

I would welcome the opportunity to discuss how my experience and educational philosophy can contribute to the continued success of your Science department.

        Yours faithfully,
        Mahmoud altaher Alsini
        """


def _generate_fallback_speculative_email(prospect: dict[str, Any], profile: dict[str, Any]) -> str:
    """Template speculative outreach email when no LLM is available."""
    school = prospect.get("school_name", "your school")
    location = prospect.get("location", "your region")
    offerings = ", ".join(prospect.get("pearson_offerings", []) or ["Edexcel Physics and Mathematics"])
    return f"""Dear Admissions / HR Team,

I am writing to introduce myself as a Pearson Edexcel Physics and Mathematics specialist, in case a teaching position opens at {school} in the near future. I hold a B.Sc. in Engineering Science from the University of Tripoli (2020) and am currently completing my PGCEi at Liverpool John Moores University, with over four years of international experience across the Pearson Edexcel IGCSE (4PH1) and A-Level curricula.

I understand {school} offers {offerings}, and I would welcome the chance to contribute to your Science department's continued success. My classroom practice is grounded in Cognitive Load Theory and Assessment for Learning, and I design instruction that respects the architecture of working memory while fostering genuine scientific curiosity.

I will be visiting Dresden and the nearby city next month, as I have a relative there, and would be glad to arrange a brief meeting, informal interview, or demo lesson at your convenience. My CV is attached for your reference (CV_Mahmoud_Alsini.html).

Yours faithfully,
Mahmoud Alsini
"""


class CoverLetterGenerator:
    """Generates bespoke cover letters using the configured LLM provider.

    Reuses the same provider resolution pattern as LLMScorer, trying the
    configured primary provider first, then the fallback. Generated letters
    are saved to ``data/cover_letters/`` as Markdown files.
    """

    def __init__(self) -> None:
        self.profile = self._load_profile()
        self._llm_provider: tuple[str | None, Callable[[str], str | None] | object] | object = _SENTINEL

    # ------------------------------------------------------------------
    # Profile loading
    # ------------------------------------------------------------------

    def _load_profile(self) -> dict[str, Any]:
        try:
            with open("data/profile.json", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            log.warning("data/profile.json not found — using empty profile")
            return {}
        except json.JSONDecodeError:
            log.error("data/profile.json is invalid JSON — using empty profile")
            return {}

    # ------------------------------------------------------------------
    # LLM provider resolution (mirrors LLMScorer pattern)
    # ------------------------------------------------------------------

    # Provider short codes — first two letters of the canonical provider
    # name, used only in cover-letter filenames so operator can tell which
    # cascade step succeeded:
    #   oc = opencode_zen
    #   nv = nvidia
    #   gr = groq
    #   or = openrouter
    #   gm = gemini
    # The two-letter codes survive any filename-length display (on Discord,
    # Telegram, file managers) and pair with the existing "__LLM" tag.
    PROVIDER_SHORT_CODE: dict[str, str] = {
        "opencode_zen": "oc",
        "nvidia": "nv",
        "groq": "gr",
        "openrouter": "or",
        "gemini": "gm",
    }

    def _resolve_provider(self) -> tuple[str | None, Callable[[str], str | None]] | tuple[None, None]:
        """Probe all providers in priority order; return first healthy one.

        Returns a tuple (name, fn) so the caller can stash which
        provider answered — needed for the filename tag at save time.
        ``(None, None)`` indicates every provider failed validation
        during the probe (caller should fall through to the
        template-letter path).

        Provider cascade priority (updated 2026-09-23 to match
        PROVIDER_WEIGHTS): gemini → nvidia → groq → openrouter →
        opencode_zen (key expired).
        """
        name_fn = self._provider_cascade()

        for name, fn in name_fn.items():
            try:
                result = fn("Reply with just the word OK.")
                if result is not None and result.strip():
                    log.info("Cover letter provider resolved: %s", name)
                    return name, fn
            except Exception as exc:
                log.warning("Cover letter probe %s failed: %s", name, exc)

        log.warning(
            "Cover letter probe exhausted all LLM providers — using "
            "template fallback.  Likely cause: every provider's API key "
            "is missing or the cascade is rate-limited."
        )
        return None, None

    def _provider_cascade(self) -> dict[str, Callable[[str], str | None]]:
        """The provider cascade, in priority order."""
        return {
            "gemini": self._call_gemini,
            "nvidia": self._call_nvidia,
            "groq": self._call_groq,
            "openrouter": self._call_openrouter,
            "opencode_zen": self._call_opencode_zen,
        }

    def _demote_provider(self, failed_name: str | None) -> tuple[str | None, Callable[[str], str | None]] | tuple[None, None]:
        """Return the first provider *after* ``failed_name`` that answers a probe.

        Called when the pinned provider returns ``None`` mid-run — almost
        always a 429 rather than a bad key.  Previously any empty response
        dropped straight to the template, so a single provider getting
        rate-limited turned every remaining letter in the batch into a
        generic template.  This walks the rest of the cascade instead.
        """
        if failed_name is None:
            return self._resolve_provider()

        cascade = self._provider_cascade()
        names = list(cascade)
        try:
            idx = names.index(failed_name) + 1
        except ValueError:
            return self._resolve_provider()

        for name in names[idx:]:
            fn = cascade[name]
            try:
                result = fn("Reply with just the word OK.")
                if result is not None and result.strip():
                    log.info("Cover letter demoted %s → %s after an empty response",
                             failed_name, name)
                    return name, fn
            except Exception as exc:
                log.warning("Cover letter probe %s failed: %s", name, exc)

        log.warning(
            "Cover letter cascade exhausted after %s — no healthy provider "
            "left, subsequent letters will use the template.", failed_name
        )
        return None, None

    def _call_opencode_zen(self, prompt: str) -> str | None:
        # Primary: ``mimo-v2.5-free`` (OpenCode Zen, 2026-08-30); falls back to
        # ``deepseek-v4-flash-free`` if it errors.  The paid-model pair
        # ``deepseek-v4-flash`` and ``deepseek-v4-pro`` both return HTTP 401
        # because the workspace ``wrk_01KRNSES9FY5ACEMK78BKAC1QY`` is empty
        # of credit, so the loop above caused the cover-letter cascade to
        # silently fall through to NVIDIA every job (noticeable as
        # ``__LLM_nv.md`` filenames in ``data/cover_letters/``).  Realigned
        # 2026-07-03 to match ``LLMScorer._call_opencode_zen`` which has
        # been on the free tier since 2026-06-29.
        #
        # Reasoning-mode headroom: ``deepseek-v4-flash-free`` burns most of
        # its completion budget on ``reasoning_content`` chain-of-thought.
        # The scorer gets away with ``max_tokens=4096`` because its prompt
        # is short and reasoning stays small — but the cover-letter prompt
        # (~3.6k chars) triggers far longer reasoning (~4k tokens), and at
        # 4096 the whole budget is consumed before any visible ``content``
        # is emitted (observed: finish_reason="length", content_len=0).
        # ``max_tokens=8192`` leaves headroom for the model to finish
        # reasoning AND emit the letter (verified: finish_reason="stop",
        # ~1.3k-char letter).  ``timeout=120`` matches the scorer; the
        # request takes ~40s.
        #
        # ``temperature=0.3`` matches the research-agent tier and the
        # scorer's reasoning budget — cover letters should be precise
        # and grounded rather than creative.
        for model in ("mimo-v2.5-free", "deepseek-v4-flash-free"):
            try:
                resp = httpx.post(
                    "https://opencode.ai/zen/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.opencode_zen_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 8192,
                    },
                    timeout=120,
                )
                if resp.status_code in (401, 404):
                    log.warning("OpenCode model %r failed (HTTP %s) — opencode_zen is being removed from cascade", model, resp.status_code)
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as exc:
                log.debug("OpenCode Zen %s failed: %s", model, exc)
                continue
        return None

    def _call_groq(self, prompt: str) -> str | None:
        try:
            resp = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.groq_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 1200,
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            log.debug("Groq call failed: %s", exc)
            return None

    def _call_gemini(self, prompt: str) -> str | None:
        try:
            resp = httpx.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                params={"key": settings.gemini_api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:
            log.debug("Gemini call failed: %s", exc)
            return None

    def _call_nvidia(self, prompt: str) -> str | None:
        for model in (settings.nvidia_model, settings.nvidia_backup_model):
            try:
                resp = httpx.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.nvidia_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.8,
                        "max_tokens": 4096,
                    },
                    timeout=120,
                )
                if resp.status_code in (401, 404):
                    log.warning("NVIDIA model %r failed (HTTP %s) — trying backup", model, resp.status_code)
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as exc:
                log.debug("NVIDIA %s failed: %s", model, exc)
                continue
        return None

    def _call_openrouter(self, prompt: str) -> str | None:
        try:
            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openrouter_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 1200,
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            log.debug("OpenRouter call failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Diversity evaluation loop
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_diversity(letters: list[str]) -> float:
        """Compute average structural similarity across generated letters.

        Uses sentence-level overlap ratio between all pairs. Returns a score
        between 0.0 (completely unique) and 1.0 (identical). If > 0.40 the
        prompt needs iteration.
        """
        import itertools
        import re

        def _sentence_set(text: str) -> set[str]:
            sentences = re.split(r'(?<=[.!?])\s+', text.lower().strip())
            return {s.strip() for s in sentences if len(s.strip()) > 20}

        pairs = 0
        total_overlap = 0.0
        for a, b in itertools.combinations(letters, 2):
            sa, sb = _sentence_set(a), _sentence_set(b)
            if not sa or not sb:
                continue
            union = sa | sb
            if not union:
                continue
            overlap = len(sa & sb) / len(union)
            total_overlap += overlap
            pairs += 1

        if pairs == 0:
            return 0.0
        return total_overlap / pairs

    @staticmethod
    def _run_evaluation_loop(prompt_template: str, profile: dict, provider: Callable[[str], str | None]) -> str:
        """Generate 3 sample letters and iterate the prompt until diversity < 40%.

        Returns the final prompt template that passed the diversity gate.
        """
        sample_jobs = [
            {
                "title": "Head of Physics",
                "school": "Wellington College, Shanghai",
                "curriculum": "IGCSE, A-Level, IB",
                "country": "China",
                "salary_range": "£45,000 – £55,000",
                "description": "Leading the Physics department at a prestigious British international school in Shanghai. Seeking an experienced educator to mentor staff, develop curriculum, and teach IGCSE, A-Level, and IB Physics to high-achieving students in a state-of-the-art science facility.",
            },
            {
                "title": "STEM Coordinator & Physics Teacher",
                "school": "Green Valley School, Nairobi",
                "curriculum": "Cambridge IGCSE, A-Level",
                "country": "Kenya",
                "salary_range": "£28,000 – £38,000",
                "description": "Join a growing international school in Nairobi to coordinate the STEM programme and teach Physics. The school emphasises project-based learning, community engagement, and preparing students for Cambridge examinations. Candidates with experience in robotics or environmental science encouraged.",
            },
            {
                "title": "Physics Teacher (MYP/DP)",
                "school": "International School of Kuala Lumpur",
                "curriculum": "IB MYP, IB DP",
                "country": "Malaysia",
                "salary_range": "£40,000 – £52,000",
                "description": "The International School of Kuala Lumpur seeks an IB Physics specialist for MYP and Diploma Programmes. The role includes supervising Extended Essays in the Sciences, leading a CAS activity, and contributing to the school's sustainability initiatives. Collaborative, inquiry-based teaching approach expected.",
            },
        ]

        prompt = prompt_template
        for iteration in range(5):
            letters: list[str] = []
            for job in sample_jobs:
                filled = prompt.format(
                    job=json.dumps(job, indent=2, default=str),
                    profile=json.dumps(profile, indent=2, default=str),
                )
                result = provider(filled)
                letters.append(result.strip() if result else "")
                time.sleep(5)

            letters = [l for l in letters if l]
            if len(letters) < 2:
                log.warning("Evaluation loop: too few successful generations, retrying...")
                continue

            similarity = CoverLetterGenerator._evaluate_diversity(letters)
            log.info("Evaluation loop iteration %d: similarity=%.2f", iteration + 1, similarity)

            if similarity <= 0.40:
                log.info("Diversity gate passed (%.2f ≤ 0.40)", similarity)
                return prompt

            prompt = prompt.replace(
                "Vary the structure: open with a different angle",
                "Vary the structure drastically: open with a unique angle for each job "
                "(e.g. school philosophy, location advantages, specific programme highlights). "
                "Avoid reusing the same paragraph structure or opening sentence across letters. "
                "Write each letter as if it is the only job you are applying for.",
            )

        log.warning("Evaluation loop exhausted 5 iterations — using last prompt")
        return prompt

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        job: dict[str, Any],
        campaign: dict | None = None,
        speculative: bool = False,
        out_dir: str | None = None,
    ) -> str | None:
        """Generate a cover letter (or speculative outreach email) and save it.

        For the reactive job pipeline, *speculative* is ``False`` and the
        letter is saved under ``data/cover_letters``. For the proactive
        campaign, *speculative* is ``True``: the email uses the
        Dresden-visit framing (no "application for vacancy" language) and is
        saved under the campaign's ``emails`` directory when *out_dir* is
        supplied.

        Returns the absolute file path of the saved letter, or ``None``
        if generation fails.
        """
        letter: str | None = None
        source = "fallback"
        provider_name: str | None = None

        if self._llm_provider is _SENTINEL:
            self._llm_provider = self._resolve_provider()
        # Stash the resolved provider name (or None when probe failed).
        provider_name, fn = self._llm_provider  # type: ignore[misc]

        if fn is not None:
            if speculative:
                prompt = SPECULATIVE_EMAIL_PROMPT.format(
                    job=json.dumps(self._prospect_text(job), indent=2, default=str),
                    research_brief=json.dumps(job.get("research_brief") or {}, indent=2, default=str),
                    profile=json.dumps(self.profile, indent=2, default=str),
                )
            else:
                prompt = COVER_LETTER_PROMPT.format(
                    job=json.dumps(job, indent=2, default=str),
                    research_brief=json.dumps(job.get("research_brief") or {}, indent=2, default=str),
                    profile=json.dumps(self.profile, indent=2, default=str),
                )
                if campaign is not None:
                    lane = job.get("lane", "")
                    if lane == "edexcel_only":
                        directive = (
                            "\n\nCAMPAIGN DIRECTIVE: This is the Pearson Edexcel Central Europe "
                            "campaign and this role is in the edexcel_only lane — lean fully into "
                            "Mahmoud's Pearson Edexcel 4PH1 IGCSE and A-Level Physics/Maths authority."
                        )
                    else:
                        directive = (
                            "\n\nCAMPAIGN DIRECTIVE: This is the Pearson Edexcel Central Europe "
                            "campaign and this role is in the curriculum_adjacent lane — bridge the "
                            "school's Cambridge/IB Physics-Maths to Mahmoud's Edexcel expertise via the "
                            "~90% content-overlap framing, pulling from the research brief's "
                            "institution_facts, school_profile, candidate_match and contact_strategy."
                        )
                    prompt += directive
            letter = fn(prompt)
            if letter is not None:
                letter = letter.strip()

            if letter:
                short = self.PROVIDER_SHORT_CODE.get(provider_name or "", "?")
                source = f"LLM_{short}"
                log.info(
                    "LLM %s generated for %s via %s → tag %s",
                    "speculative email" if speculative else "cover letter",
                    job.get("school_name", job.get("title", "?")),
                    provider_name, source,
                )
            else:
                log.warning(
                    "LLM (%s) returned empty for %s — trying next provider",
                    provider_name, job.get("school_name", job.get("title", "?")),
                )
                # A rate limit (429) on the pinned provider must not send every
                # remaining letter in the batch to the template.  Demote to
                # the next healthy provider and retry this same letter.
                provider_name, fn = self._demote_provider(provider_name)
                self._llm_provider = (provider_name, fn)
                if fn is not None:
                    letter = fn(prompt)
                    if letter is not None:
                        letter = letter.strip()
                    if letter:
                        short = self.PROVIDER_SHORT_CODE.get(provider_name or "", "?")
                        source = f"LLM_{short}"
                        log.info(
                            "LLM %s generated for %s via %s (after demotion) → tag %s",
                            "speculative email" if speculative else "cover letter",
                            job.get("school_name", job.get("title", "?")),
                            provider_name, source,
                        )

        if not letter:
            if speculative:
                log.info("Using speculative template fallback for %s", job.get("school_name", "?"))
                letter = _generate_fallback_speculative_email(job, self.profile)
            else:
                log.info("Using template fallback for %s at %s", job.get("title", "?"), job.get("school", "?"))
                letter = _generate_fallback_letter(job, self.profile)

        return self._save_letter(job, letter, source, out_dir=out_dir)

    @staticmethod
    def _prospect_text(prospect: dict[str, Any]) -> dict[str, Any]:
        """Flatten a campaign prospect into job-like text for the prompt."""
        return {
            "school_name": prospect.get("school_name", ""),
            "location": prospect.get("location", ""),
            "tier": prospect.get("tier", ""),
            "campaign_score": prospect.get("campaign_score", ""),
            "pearson_offerings": prospect.get("pearson_offerings", []),
            "distance_km": prospect.get("distance_km", ""),
            "category_f": prospect.get("category_f", False),
        }

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitise_filename(text: str, max_length: int = 60) -> str:
        """Strip special characters and truncate for safe filenames."""
        safe = "".join(c.lower() for c in text if c.isalnum() or c in " -_").strip()
        safe = safe.replace(" ", "_")
        return safe[:max_length].rstrip("_")

    def _save_letter(
        self,
        job: dict[str, Any],
        letter: str,
        source: str = "fallback",
        out_dir: str | None = None,
    ) -> str:
        base = Path(out_dir) if out_dir else Path("data/cover_letters")
        base.mkdir(parents=True, exist_ok=True)

        school = self._sanitise_filename(job.get("school_name") or job.get("school", "unknown_school"))
        title = self._sanitise_filename(job.get("title") or job.get("school_name", "unknown_role"))
        filename = f"{school}__{title}__{source}.md"
        filepath = base / filename

        header_lines = [
            f"# Outreach Email — {job.get('school_name', job.get('title', 'Unknown'))}\n",
            "",
            f"- **School:** {job.get('school_name', job.get('school', 'Unknown'))}",
        ]
        if job.get("location"):
            header_lines.append(f"- **Location:** {job['location']}")
        if job.get("tier"):
            header_lines.append(f"- **Tier:** {job['tier']}")
        if job.get("campaign_score") is not None:
            header_lines.append(f"- **Campaign Score:** {job['campaign_score']}/100")
        if job.get("score") is not None:
            header_lines.append(f"- **Score:** {job['score']}/100")
        if job.get("confidence"):
            header_lines.append(f"- **Confidence:** {job['confidence']}")
        if job.get("distance_km") is not None:
            header_lines.append(f"- **Distance from Dresden:** {job['distance_km']} km")
        if job.get("category_f"):
            header_lines.append(f"- **Category F (live vacancy detected):** Yes")
        reasoning = job.get("scoring_reasoning") or job.get("reasoning") or ""
        if reasoning:
            header_lines.append(f"- **Why this score:** {reasoning}")
        if job.get("evidence_urls"):
            urls = ", ".join(job["evidence_urls"])
            header_lines.append(f"- **Evidence:** {urls}")
        header_lines.append(f"- **Date:** {datetime.now().strftime('%Y-%m-%d')}")
        if job.get("url"):
            header_lines.append(f"- **Job URL:** {job['url']}")
        header_lines.append("")
        header_lines.append("---")
        header_lines.append("")
        header = "\n".join(header_lines)

        filepath.write_text(header + letter, encoding="utf-8")
        log.info("Outreach email saved → %s", filepath.resolve())
        return str(filepath.resolve())

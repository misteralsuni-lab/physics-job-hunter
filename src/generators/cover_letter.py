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

        Provider cascade priority (re-ordered 2026-06-29 to match the
        project-wide LLM weights: opencode_zen → nvidia → groq →
        openrouter → gemini).  OpenCode Zen is primary because the
        ``deepseek-v4-flash-free`` free-tier model has zero cost while
        still emitting enough reasoning budget for the cover-letter
        JSON schema (max_tokens=4096 — already wired in LLMScorer).
        NVIDIA is the high-quality 200K-context fallback and groq is the
        fastest paid fallback once healthy.
        ``openrouter`` and ``gemini`` stay as last-ditch paths.
        """
        name_fn: dict[str, Callable[[str], str | None]] = {
            "opencode_zen": self._call_opencode_zen,
            "nvidia": self._call_nvidia,
            "groq": self._call_groq,
            "openrouter": self._call_openrouter,
            "gemini": self._call_gemini,
        }

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

    def _call_opencode_zen(self, prompt: str) -> str | None:
        # Primary: ``hy3-free`` (OpenCode Zen, 2026-07-12); falls back to
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
        for model in ("hy3-free", "deepseek-v4-flash-free"):
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

    def generate(self, job: dict[str, Any]) -> str | None:
        """Generate a cover letter for *job* and save it to disk.

        Tries the configured LLM provider first; if no provider is available
        it falls back to a template-based letter so the user always has a
        draft to review.

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
            prompt = COVER_LETTER_PROMPT.format(
                job=json.dumps(job, indent=2, default=str),
                research_brief=json.dumps(job.get("research_brief") or {}, indent=2, default=str),
                profile=json.dumps(self.profile, indent=2, default=str),
            )
            letter = fn(prompt)
            if letter is not None:
                letter = letter.strip()

            if letter:
                # Compose the filename tag with the provider's 2-letter
                # short code (e.g. "LLM_oc" for opencode_zen) so the
                # operator can identify which cascade step produced this
                # letter when reviewing Telegram attachments or browser
                # listings — useful in case a future bug silently routes
                # through a different provider than the configured lead.
                short = self.PROVIDER_SHORT_CODE.get(provider_name or "", "?")
                source = f"LLM_{short}"
                log.info(
                    "LLM cover letter generated for %s at %s via %s → tag %s",
                    job.get("title", "?"), job.get("school", "?"),
                    provider_name, source,
                )
            else:
                log.warning(
                    "LLM (%s) returned empty for %s — using template fallback",
                    provider_name, job.get("title", "?"),
                )

        if not letter:
            log.info("Using template fallback for %s at %s", job.get("title", "?"), job.get("school", "?"))
            letter = _generate_fallback_letter(job, self.profile)

        return self._save_letter(job, letter, source)

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitise_filename(text: str, max_length: int = 60) -> str:
        """Strip special characters and truncate for safe filenames."""
        safe = "".join(c.lower() for c in text if c.isalnum() or c in " -_").strip()
        safe = safe.replace(" ", "_")
        return safe[:max_length].rstrip("_")

    def _save_letter(self, job: dict[str, Any], letter: str, source: str = "fallback") -> str:
        out_dir = Path("data/cover_letters")
        out_dir.mkdir(parents=True, exist_ok=True)

        school = self._sanitise_filename(job.get("school", "unknown_school"))
        title = self._sanitise_filename(job.get("title", "unknown_role"))
        filename = f"{school}__{title}__{source}.md"
        filepath = out_dir / filename

        score = job.get("score")
        reasoning = job.get("scoring_reasoning") or job.get("reasoning") or ""
        score_line = f"- **Score:** {score}/100\n" if score is not None else ""
        reasoning_line = f"- **Why this score:** {reasoning}\n" if reasoning else ""
        header = (
            f"# Cover Letter — {job.get('title', 'Unknown')}\n"
            f"\n"
            f"- **School:** {job.get('school', 'Unknown')}\n"
            f"{score_line}"
            f"{reasoning_line}"
            f"- **Date:** {datetime.now().strftime('%Y-%m-%d')}\n"
            f"- **Job URL:** {job.get('url', '#')}\n"
            f"\n"
            f"---\n\n"
        )

        filepath.write_text(header + letter, encoding="utf-8")
        log.info("Cover letter saved → %s", filepath.resolve())
        return str(filepath.resolve())

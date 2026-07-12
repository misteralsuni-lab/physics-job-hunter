import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from src.config import settings
from src.agents.models import StrategicBrief
from src.agents.tools import web_search, deep_scrape

log = logging.getLogger("job-hunter")


# ---------------------------------------------------------------------------
#  Agent action model — used for structured LLM output
# ---------------------------------------------------------------------------

class AgentAction(BaseModel):
    """A single action chosen by the Research Agent at each step."""
    action: Literal["web_search", "deep_scrape", "finalise"]
    reasoning: str = Field(..., min_length=5)
    arguments: dict[str, Any] = Field(default_factory=dict)
    brief: StrategicBrief | None = None


# ---------------------------------------------------------------------------
#  Research context — conversation history for the agent
# ---------------------------------------------------------------------------

@dataclass
class ResearchContext:
    school_name: str
    location: str
    job_description: str
    profile: dict[str, Any]
    observations: list[str] = field(default_factory=list)

    def add_observation(self, tool: str, input_args: dict, result: dict) -> None:
        summary = json.dumps(result, indent=2, default=str)[:1200]
        self.observations.append(f"Tool: {tool}\nInput: {input_args}\nOutput: {summary}")

    def observations_text(self) -> str:
        return "\n\n---\n\n".join(self.observations) if self.observations else "No observations yet."

    def to_prompt(self) -> str:
        obs = "\n\n---\n\n".join(self.observations) if self.observations else "No observations yet."
        return AGENT_PROMPT_TEMPLATE.format(
            school_name=self.school_name,
            location=self.location,
            job_description=self.job_description,
            profile=json.dumps(self.profile, indent=2),
            observations=obs,
        )


# ---------------------------------------------------------------------------
#  Prompts (British English spelling throughout)
# ---------------------------------------------------------------------------

AGENT_PROMPT_TEMPLATE = """You are a strategic research analyst for an international teaching job application. Your task is to actively research the hiring institution and produce a concise, evidence-based strategic brief that aligns the school's specific goals with the candidate's profile.

You must use British English spelling and terminology throughout (e.g. standardise, programme, enrol, organisation, centre, behaviour).

CANDIDATE PROFILE (Mahmoud):
{profile}

JOB TO RESEARCH:
- School name: {school_name}
- Location: {location}
- Role description: {job_description}

AVAILABLE TOOLS:
1. web_search(query): Search DuckDuckGo for the school's official website, recent news, campus branches, or curriculum pages.
2. deep_scrape(url): Extract clean markdown from a webpage such as the school's "About Us", "Curriculum", "Headteacher's Welcome", or "Vacancies" pages.

You may take up to 5 steps. At each step, return exactly one JSON object with this shape:

For a tool call:
{{
  "action": "web_search" or "deep_scrape",
  "reasoning": "Why you are choosing this tool and what you hope to learn",
  "arguments": {{"query": "your search query"}} or {{"url": "https://..."}},
  "brief": null
}}

For the final answer:
{{
  "action": "finalise",
  "reasoning": "Why these facts and this angle were chosen",
  "arguments": {{}},
  "brief": {{
    "institution_facts": ["2-3 highly specific, unique facts about the school"],
    "strategic_alignment": "Short paragraph deciding which part of Mahmoud's expertise (engineering background, PGCEi, tech/AI integration, bilingual STEM delivery) best matches the school's current goals.",
    "recommended_angle": "Directive for the cover letter opening hook."
  }}
}}

RULES:
- You should normally perform at least one web_search and one deep_scrape before finalising, unless the tools return no usable data.
- institution_facts must be 2-3 items, highly specific and unique to this institution. Avoid generic statements.
- strategic_alignment should explicitly reference Mahmoud's credentials and the school's goals.
- recommended_angle should be a direct, actionable opening-hook instruction for the cover letter writer.
- If you cannot find specific data, use what is available and avoid fabricating facts. Return a finalise action with the best brief you can honestly construct.
- Always return a valid finalise action before the step limit, even if data is limited.

OBSERVATIONS SO FAR:
{observations}

What is your next step? Return only the JSON object."""


SYNTHESIS_PROMPT = """You are a strategic research analyst. Based on the observations gathered below, synthesise a final strategic brief in the exact JSON schema.

Use British English spelling and terminology.

CANDIDATE PROFILE:
{profile}

SCHOOL:
{school_name}

OBSERVATIONS:
{observations}

Return ONLY a JSON object matching this schema:
{{
  "institution_facts": ["2-3 highly specific, unique facts"],
  "strategic_alignment": "Short paragraph deciding which part of Mahmoud's expertise best matches the school's goals.",
  "recommended_angle": "Directive for the cover letter opening hook."
}}

If the observations are sparse, still produce the best brief you can without fabricating facts."""


# ---------------------------------------------------------------------------
#  Lightweight LLM client — cascades through available providers
# ---------------------------------------------------------------------------

class LLMClient:
    """Minimal LLM caller that tries every configured provider in priority order.

    Mirrors the same provider endpoints used elsewhere in the project but
    keeps the research agent self-contained.
    """

    def __init__(self) -> None:
        self._nvidia_models = [m for m in (settings.nvidia_model, settings.nvidia_backup_model) if m]

    # --------------------------------------------------------------
    #  Public API
    # --------------------------------------------------------------

    def complete(self, prompt: str, max_tokens: int = 1200, temperature: float = 0.3) -> str | None:
        """Try every configured provider; return the first non-empty response."""
        for name, fn in self._providers():
            try:
                text = fn(prompt, max_tokens, temperature)
                if text and text.strip():
                    log.info("Research Agent LLM response from %s", name)
                    return text.strip()
            except Exception as exc:
                log.warning("Research Agent LLM provider %s failed: %s", name, exc)
        log.error("All LLM providers exhausted for research agent")
        return None

    # --------------------------------------------------------------
    #  Provider list (highest weight first)
    # --------------------------------------------------------------

    def _providers(self) -> list[tuple[str, Callable]]:
        # Provider cascade priority (re-ordered 2026-06-29 to match the
        # project-wide LLM weights: opencode_zen → nvidia → groq →
        # openrouter → gemini).
        p: list[tuple[str, Callable]] = []
        if settings.opencode_zen_api_key:
            p.append(("opencode_zen", self._call_opencode_zen))
        if settings.nvidia_api_key and settings.nvidia_api_key != "nvapi-":
            p.append(("nvidia", self._call_nvidia))
        if settings.groq_api_key:
            p.append(("groq", self._call_groq))
        if settings.openrouter_api_key:
            p.append(("openrouter", self._call_openrouter))
        if settings.gemini_api_key:
            p.append(("gemini", self._call_gemini))
        return p

    # --------------------------------------------------------------
    #  OpenAI-compatible helper
    # --------------------------------------------------------------

    def _openai_post(
        self,
        url: str,
        api_key: str,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        timeout: int = 60,
        extra_body: dict | None = None,
    ) -> str | None:
        body: dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if extra_body:
            body["extra_body"] = extra_body

        resp = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=timeout,
        )
        if resp.status_code in (401, 404):
            return None
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    # --------------------------------------------------------------
    #  Provider implementations
    # --------------------------------------------------------------

    def _call_groq(self, prompt: str, max_tokens: int, temperature: float) -> str | None:
        return self._openai_post(
            "https://api.groq.com/openai/v1/chat/completions",
            settings.groq_api_key,
            settings.groq_model,
            prompt,
            max_tokens,
            temperature,
        )

    def _call_nvidia(self, prompt: str, max_tokens: int, temperature: float) -> str | None:
        for model in self._nvidia_models:
            try:
                result = self._openai_post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    settings.nvidia_api_key,
                    model,
                    prompt,
                    max_tokens,
                    temperature,
                    timeout=120,
                )
                if result is not None:
                    return result
            except Exception as exc:
                log.debug("NVIDIA model %s failed: %s", model, exc)
                continue
        return None

    def _call_openrouter(self, prompt: str, max_tokens: int, temperature: float) -> str | None:
        return self._openai_post(
            "https://openrouter.ai/api/v1/chat/completions",
            settings.openrouter_api_key,
            settings.openrouter_model,
            prompt,
            max_tokens,
            temperature,
        )

    def _call_gemini(self, prompt: str, max_tokens: int, temperature: float) -> str | None:
        try:
            resp = httpx.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                params={"key": settings.gemini_api_key},
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "response_mime_type": "application/json",
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens,
                    },
                },
                timeout=45,
            )
            if resp.status_code != 200:
                return None
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            log.debug("Gemini research call failed: %s", exc)
            return None

    def _call_opencode_zen(self, prompt: str, max_tokens: int, temperature: float) -> str | None:
        # Primary: hy3-free (OpenCode Zen). deepseek-v4-flash-free is the
        # fallback if hy3-free is unavailable / errors (2026-07-12). The
        # paid ``deepseek-v4-pro`` / ``deepseek-v4-flash`` fallbacks were
        # dropped on 2026-06-28 — both return 401 CreditsError for the
        # workspace ``wrk_01KRNSES9FY5ACEMK78BKAC1QY`` (no payment method).
        #
        # Reasoning-mode headroom:  deepseek-v4-flash-free burns most of
        # its output budget on ``reasoning_content`` chain-of-thought,
        # so a plain ``max_tokens=800`` returns ``content=""``.  Empirically
        # verified on 2026-06-28 that ``max_tokens=4096`` is enough for
        # the model to finish reasoning and emit the visible answer
        # (e.g. ``content: '80'`` for the IGCSE-Physics scoring prompt).
        # Endpoint: https://opencode.ai/zen/v1/chat/completions
        for model in ("hy3-free", "deepseek-v4-flash-free"):
            from src.config import settings as _s
            try:
                # Use at least 4096 tokens to leave reasoning headroom,
                # unless the caller already specified a higher budget.
                budget = max(max_tokens, 4096) if max_tokens else 4096
                result = self._openai_post(
                    "https://opencode.ai/zen/v1/chat/completions",
                    _s.opencode_zen_api_key,
                    model,
                    prompt,
                    max_tokens=budget,
                    temperature=temperature,
                )
                if result is not None:
                    return result
            except Exception as exc:
                log.debug("OpenCode Zen model %s failed: %s", model, exc)
                continue
        return None


# ---------------------------------------------------------------------------
#  Research Agent — main orchestrator
# ---------------------------------------------------------------------------

TOOL_MAP: dict[str, Callable] = {
    "web_search": web_search,
    "deep_scrape": deep_scrape,
}


class ResearchAgent:
    """Tool-calling agent that researches a hiring institution and returns a
    :class:`StrategicBrief`.

    Uses a ReAct-style loop: the agent decides at each step whether to call
    a tool or finalise with a brief. Falls back gracefully on any failure.
    """

    MAX_STEPS = 5

    def __init__(self) -> None:
        self.profile = self._load_profile()
        self.llm = LLMClient()

    # --------------------------------------------------------------
    #  Public API
    # --------------------------------------------------------------

    def research(self, school_name: str, location: str, job_description: str) -> StrategicBrief:
        """Research the institution and produce a strategic brief.

        Args:
            school_name: The name of the hiring school.
            location: The geographic location (city / country).
            job_description: The full job description text.

        Returns:
            A :class:`StrategicBrief` populated with research findings.
        """
        context = ResearchContext(
            school_name=school_name,
            location=location,
            job_description=job_description,
            profile=self.profile,
        )

        for step in range(1, self.MAX_STEPS + 1):
            prompt = context.to_prompt()
            raw = self.llm.complete(prompt, max_tokens=1800, temperature=0.3)
            if raw is None:
                log.error("Research Agent: no LLM response at step %d — returning fallback", step)
                return StrategicBrief.fallback(school_name)

            action = self._parse_action(raw)
            if action is None:
                log.warning(
                    "Research Agent: unparseable response at step %d: %.200r",
                    step, raw,
                )
                # Try one more time; if not, fallback
                continue

            log.info(
                "Research Agent step %d/%d: action=%s reasoning=%.80s",
                step, self.MAX_STEPS, action.action, action.reasoning,
            )

            if action.action == "finalise":
                if action.brief is not None:
                    return action.brief
                log.warning("Research Agent: finalise with no brief at step %d — continuing", step)
                continue

            # Execute tool
            tool_fn = TOOL_MAP.get(action.action)
            if tool_fn is None:
                log.warning("Research Agent: unknown tool %r at step %d", action.action, step)
                continue

            try:
                result = tool_fn(**action.arguments)
            except Exception as exc:
                log.warning("Research Agent: tool %s failed at step %d: %s", action.action, step, exc)
                result = {"error": str(exc)}

            context.add_observation(action.action, action.arguments, result)

            # If web_search is circuit-broken, skip remaining steps — go straight to synthesis
            if action.action == "web_search" and result.get("error") in ("circuit_breaker_active",):
                log.info("Research Agent: web_search circuit-broken — skipping to synthesis")
                break

        log.info("Research Agent: step limit (%d) reached — synthesising from observations", self.MAX_STEPS)
        return self._synthesise(context, school_name)

    # --------------------------------------------------------------
    #  Internal helpers
    # --------------------------------------------------------------

    def _parse_action(self, raw: str) -> AgentAction | None:
        """Extract and validate an ``AgentAction`` from the LLM response."""
        json_str = self._extract_json(raw)
        if json_str is None:
            return None
        try:
            return AgentAction.model_validate_json(json_str)
        except ValidationError as exc:
            log.warning("AgentAction validation error: %s", exc)
            return None

    def _synthesise(self, context: ResearchContext, school_name: str) -> StrategicBrief:
        """Last-ditch synthesis from gathered observations when the step limit
        is reached before the agent calls finalise."""
        prompt = SYNTHESIS_PROMPT.format(
            observations=context.observations_text(),
            profile=json.dumps(self.profile, indent=2),
            school_name=school_name,
        )
        raw = self.llm.complete(prompt, max_tokens=1200, temperature=0.3)
        if raw is None:
            return StrategicBrief.fallback(school_name)

        json_str = self._extract_json(raw)
        if json_str is None:
            return StrategicBrief.fallback(school_name)
        try:
            return StrategicBrief.model_validate_json(json_str)
        except ValidationError:
            return StrategicBrief.fallback(school_name)

    @staticmethod
    def _extract_json(text: str) -> str | None:
        """Extract a valid JSON object from *text*, handling markdown fences
        and possible extra output."""
        # Reuse LLMScorer's robust JSON extractor if available
        try:
            from src.scoring.llm_scorer import LLMScorer
            return LLMScorer._extract_json(text)
        except Exception:
            pass
        # Fallback: simple bracket walker
        try:
            import re
            text = re.sub(r"^```(?:json)?\s*", "", text.strip())
            text = text.removesuffix("```").strip()
            start = text.index("{")
            depth = 0
            in_str = False
            for i in range(start, len(text)):
                ch = text[i]
                if ch == "\\" and in_str:
                    continue
                if ch == '"':
                    in_str = not in_str
                elif not in_str:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = text[start:i + 1]
                            json.loads(candidate)
                            return candidate
            return None
        except (ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _load_profile() -> dict[str, Any]:
        try:
            with open("data/profile.json", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            log.warning("Could not load data/profile.json — using default profile")
            return {
                "target_subjects": ["Physics", "Science"],
                "target_curricula": ["IGCSE", "A-Level"],
            }

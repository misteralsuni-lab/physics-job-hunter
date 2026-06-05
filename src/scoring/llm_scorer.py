import json
from typing import Any
from tenacity import retry, stop_after_attempt, wait_exponential

import httpx

from src.config import settings


JOB_SCORING_PROMPT = """You are an expert recruiter specializing in international Physics teaching positions. Score this job listing against the candidate's profile.

Candidate Profile:
{profile}

Job Listing:
{job}

Return a JSON object with:
{{
  "score": <integer 0-100>,
  "reasoning": "<brief explanation>",
  "visa_sponsorship": true/false/null,
  "housing_allowance": true/false/null,
  "curriculum_match": "<IGCSE|A-Level|IB|Other>"
}}
Score based on: curriculum match, salary, location, visa sponsorship, housing, school reputation, and alignment with candidate's background. Output ONLY valid JSON."""


class LLMScorer:
    def __init__(self):
        self.profile = self._load_profile()

    def _load_profile(self) -> dict:
        try:
            with open("data/profile.json") as f:
                return json.load(f) | {"cv_summary": ""}
        except FileNotFoundError:
            return {"target_subjects": ["Physics"], "target_curricula": ["IGCSE", "A-Level", "IB"], "cv_summary": ""}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def score(self, job: dict[str, Any]) -> dict[str, Any]:
        prompt = JOB_SCORING_PROMPT.format(profile=json.dumps(self.profile, indent=2), job=json.dumps(job, indent=2))

        provider = settings.scorer_provider
        result = None

        if provider == "opencode_zen":
            result = self._score_via_opencode_zen(prompt)
        elif provider == "gemini":
            result = self._score_via_gemini(prompt)
        elif provider == "nvidia":
            result = self._score_via_nvidia(prompt)

        if result is None and settings.scorer_fallback:
            fallback = settings.scorer_fallback
            if fallback == "opencode_zen":
                result = self._score_via_opencode_zen(prompt)
            elif fallback == "gemini":
                result = self._score_via_gemini(prompt)
            elif fallback == "nvidia":
                result = self._score_via_nvidia(prompt)

        return result or {"score": 0, "reasoning": "All scoring providers failed", "visa_sponsorship": None, "housing_allowance": None, "curriculum_match": None}

    def _score_via_opencode_zen(self, prompt: str) -> dict | None:
        try:
            resp = httpx.post(
                "https://api.opencode.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.opencode_zen_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-v4-flash-free",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content.strip().removeprefix("```json").removesuffix("```").strip())
        except Exception:
            return None

    def _score_via_gemini(self, prompt: str) -> dict | None:
        try:
            resp = httpx.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                params={"key": settings.gemini_api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(content.strip().removeprefix("```json").removesuffix("```").strip())
        except Exception:
            return None

    def _score_via_nvidia(self, prompt: str) -> dict | None:
        try:
            resp = httpx.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.nvidia_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.nvidia_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content.strip().removeprefix("```json").removesuffix("```").strip())
        except Exception:
            return None

import json
from typing import Any, Callable

import httpx

from src.config import settings


_SENTINEL = object()


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
        self._llm_provider: Callable[[str], dict | None] | object = _SENTINEL

    def _load_profile(self) -> dict:
        try:
            with open("data/profile.json") as f:
                return json.load(f) | {"cv_summary": ""}
        except FileNotFoundError:
            return {"target_subjects": ["Physics"], "target_curricula": ["IGCSE", "A-Level", "IB"], "cv_summary": ""}

    def _resolve_provider(self) -> Callable[[str], dict | None] | None:
        name_fn = {
            "opencode_zen": self._score_via_opencode_zen,
            "gemini": self._score_via_gemini,
            "nvidia": self._score_via_nvidia,
        }
        tried = set()
        for name in (settings.scorer_provider, settings.scorer_fallback):
            fn = name_fn.get(name)
            if fn is None or name in tried:
                continue
            tried.add(name)
            try:
                result = fn("Reply with just the word OK.")
                if result is not None:
                    return fn
            except Exception:
                continue
        return None

    def score(self, job: dict[str, Any]) -> dict[str, Any]:
        if self._llm_provider is _SENTINEL:
            self._llm_provider = self._resolve_provider()

        if self._llm_provider is not None:
            prompt = JOB_SCORING_PROMPT.format(profile=json.dumps(self.profile, indent=2), job=json.dumps(job, indent=2))
            result = self._llm_provider(prompt)
            if result is not None:
                return result

        return self._score_via_rules(job)

    def _score_via_opencode_zen(self, prompt: str) -> dict | None:
        try:
            resp = httpx.post(
                "https://opencode.ai/zen/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.opencode_zen_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-v4-flash",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
                timeout=5,
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
                timeout=5,
            )
            resp.raise_for_status()
            content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(content.strip().removeprefix("```json").removesuffix("```").strip())
        except Exception:
            return None

    def _score_via_rules(self, job: dict) -> dict:
        title = (job.get("title") or "").lower()
        combined = f"{title} {(job.get('school') or '')} {(job.get('subject') or '')} {(job.get('curriculum') or '')}".lower()
        reason = []
        score = 30

        target_subjects = self.profile.get("target_subjects", ["Physics"])
        if any(s.lower() in title for s in target_subjects):
            score += 25
            reason.append("subject match")

        target_curricula = self.profile.get("target_curricula", [])
        for curr in target_curricula:
            if curr.lower() in combined:
                score += 15
                reason.append(f"{curr}")
                break

        country = (job.get("country") or "").lower()
        target_countries = self.profile.get("target_countries", [])
        if target_countries and country in [c.lower() for c in target_countries]:
            score += 10
            reason.append("country match")

        salary = job.get("salary_range", "")
        if salary:
            score += 10
            reason.append("salary listed")

        score = min(score, 100)
        return {
            "score": score,
            "reasoning": "; ".join(reason) if reason else "rule-based fallback",
            "visa_sponsorship": None,
            "housing_allowance": None,
            "curriculum_match": next((c for c in target_curricula if c.lower() in combined), "Other"),
        }

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
                timeout=5,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content.strip().removeprefix("```json").removesuffix("```").strip())
        except Exception:
            return None

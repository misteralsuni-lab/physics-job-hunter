import json
import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any, Callable

import httpx
from tenacity import Retrying, wait_random_exponential, stop_after_attempt

from src.config import settings
from src.storage.dedup_store import DB_PATH

log = logging.getLogger("scoring")

_SENTINEL = object()

# Leaky-bucket pacing constants
MAX_PER_CHUNK = 5          # max jobs per provider call
CHUNK_DELAY = 20           # seconds between chunks to let rate-limit buckets replenish

# Score modifiers
EASY_APPLY_BONUS = 10
DEADLINE_WITHIN_7_DAYS = 15
DEADLINE_WITHIN_14_DAYS = 10
DEADLINE_WITHIN_30_DAYS = 5

# Provider RPM weights (higher = more capacity share).
# Re-ordered 2026-06-29 so OpenCode Zen (free tier deepseek-v4-flash-free)
# Provider weight registry — higher weight = tried first during cascade.
# Gemini is PRIMARY (most reliable free tier), NVIDIA Nemotron-3-Super is
# SECONDARY (high-quality 200K-context), Groq is TERTIARY (fastest paid
# fallback).  OpenRouter often rate-limited; OpenCode Zen key expired.
PROVIDER_WEIGHTS: dict[str, int] = {
    "gemini": 40,
    "nvidia": 30,
    "groq": 20,
    "openrouter": 15,
    "opencode_zen": 5,
}

JOB_SCORING_PROMPT = """\
You are a strict, objective pedagogical evaluator. Score this teaching job listing against the candidate profile below.

CANDIDATE PROFILE:
{profile}

JOB LISTING:
{job}

SCORING RUBRIC (additive, max 100):
- Curriculum match (IGCSE/A-Level): 0-35
- Subject match (Physics, Maths, Science): 0-30
- Location/country desirability: 0-25
- Housing/benefits: 0-10

CRITICAL INSTRUCTIONS:
- Output ONLY a valid JSON object — no introductory text, no conversational filler, no markdown, no code fences.
- Your entire response must start with {{ and end with }}.

EXACT SCHEMA:
{{"score": <int 0-100>, "reasoning": "<1-2 sentences, max 200 chars>", "housing_allowance": <true|false|null>, "curriculum_match": "<IGCSE|A-Level|IB|Other>"}}

- If information is missing, use null for booleans and "Other" for curriculum_match."""

BATCH_SCORING_PROMPT = """\
You are a strict, objective pedagogical evaluator. Score {n} jobs against one candidate profile.

CANDIDATE PROFILE:
{profile}

JOB LISTINGS (score each independently):
{serialized_jobs}

Return a JSON array of exactly {n} objects, one per job, in input order.

EACH OBJECT SCHEMA:
{{"score": <int 0-100>, "reasoning": "<1-2 sentences, max 200 chars>", "housing_allowance": <true|false|null>, "curriculum_match": "<IGCSE|A-Level|IB|Other>"}}

SCORING RUBRIC (additive, max 100):
- Curriculum match: 0-35 | Subject match: 0-30 | Location: 0-25 | Housing: 0-10

  CRITICAL INSTRUCTIONS:
- Output ONLY a raw JSON array: [{{...}}, {{...}}, ...]
- No markdown, no code fences, no text outside the array.
- No trailing commas. No extra fields. No commentary.
- Array length MUST equal {n}."""


CAMPAIGN_CONTEXT_BLOCK = """\n\nCAMPAIGN CONTEXT (override where relevant): This is the Pearson Edexcel Central Europe campaign. Prioritise Pearson Edexcel curriculum (full credit) and Central-European geography (Dresden > Germany > Czechia > other Central Europe). Treat verified Cambridge/IB Physics-Maths as curriculum-adjacent at 0.6x credit per the campaign rule set. Keep the total max 100."""


# ---------------------------------------------------------------------------
#  Weighted Provider Registry — Health State Machine
# ---------------------------------------------------------------------------

@dataclass
class ProviderConfig:
    """Metadata for a single LLM provider endpoint."""
    name: str
    rpm: int                           # nominal requests-per-minute capacity
    single_fn: Callable[[str], dict | None]   # fn(prompt) -> dict|None
    batch_fn: Callable[[str, int], list[dict] | None] | None = None  # fn(prompt, expected) -> list|None
    key_configured: bool = True        # False when API key is empty / missing
    weight: int = 10


class ProviderHealth:
    """Persistent record of per-provider probe verdicts.

    Without this, every pipeline run re-probed all five providers from
    scratch.  Two of them (OpenCode Zen with an expired key, OpenRouter
    persistently rate-limited) answered 403/429 on every single run, costing
    ~3s of doomed HTTP per run, 9 runs a day, plus a misleading
    ``[CONFIG_INVALID]`` line in the log that implied a config bug rather
    than a transient limit.

    Verdicts older than ``VALIDITY_SECS`` are ignored so a provider that was
    rate-limited overnight gets re-probed later rather than being written
    off for good.  Stored in the same SQLite file as the dedup store so it
    needs no extra infrastructure.
    """

    VALIDITY_SECS = 24 * 60 * 60  # re-probe a dead verdict after 24h

    def __init__(self, db_path: str | Path = DB_PATH):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS provider_health (
                provider    TEXT PRIMARY KEY,
                verdict     TEXT NOT NULL,
                http_status INTEGER,
                checked_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._conn.commit()

    def cached_verdict(self, name: str) -> str | None:
        """Return the recorded verdict if it is still fresh, else None."""
        row = self._conn.execute(
            "SELECT verdict, checked_at FROM provider_health WHERE provider = ?", (name,)
        ).fetchone()
        if not row:
            return None
        verdict, checked_at = row
        try:
            age = datetime.now() - datetime.fromisoformat(checked_at)
        except (TypeError, ValueError):
            return None
        if age.total_seconds() > self.VALIDITY_SECS:
            return None  # stale — force a fresh probe
        return verdict

    def record(self, name: str, verdict: str, http_status: int | None = None) -> None:
        self._conn.execute(
            """INSERT INTO provider_health (provider, verdict, http_status, checked_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(provider) DO UPDATE SET
                 verdict = excluded.verdict,
                 http_status = excluded.http_status,
                 checked_at = excluded.checked_at""",
            (name, verdict, http_status),
        )
        self._conn.commit()

    def known_dead(self) -> list[tuple[str, str | None, str]]:
        """Diagnostics: (provider, verdict, checked_at) for every row."""
        return self._conn.execute(
            "SELECT provider, http_status, checked_at FROM provider_health"
        ).fetchall()

    def clear(self, name: str | None = None) -> None:
        if name:
            self._conn.execute("DELETE FROM provider_health WHERE provider = ?", (name,))
        else:
            self._conn.execute("DELETE FROM provider_health")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


_provider_health = ProviderHealth()


class ProviderRegistry:
    """In-memory health state machine for all LLM providers.

    States:
      ACTIVE        — ready to receive traffic
      COOLING_DOWN  — hit an error; will be probed with a canary after ``cooldown_secs``
      DEAD          — permanently removed (only if 3 consecutive cooldown cycles fail)
    """

    COOLDOWN_SECS = 300  # 5 minutes
    MAX_CONSECUTIVE_FAILURES = 3

    def __init__(self, configs: list[ProviderConfig]):
        self._configs: dict[str, ProviderConfig] = {c.name: c for c in configs}
        self._state: dict[str, str] = {}           # name -> ACTIVE|COOLING_DOWN|DEAD
        self._failures: dict[str, int] = {}         # consecutive failure count
        self._cooldown_until: dict[str, float] = {}  # monotonic timestamp

        for c in configs:
            self._state[c.name] = "ACTIVE" if c.key_configured else "DEAD"
            self._failures[c.name] = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def active_providers(self, weights: dict[str, int] | None = None) -> list[ProviderConfig]:
        """Return providers in ACTIVE state, sorted by weight (highest first)."""
        now = time.monotonic()
        candidates = []
        wmap = weights or {}

        for name, cfg in self._configs.items():
            state = self._state.get(name, "ACTIVE")
            # Check if cooldown has expired → auto-restore via canary
            if state == "COOLING_DOWN":
                cooldown_end = self._cooldown_until.get(name, 0)
                if now >= cooldown_end:
                    # Attempt canary
                    if self._canary(cfg):
                        self._restore(name)
                        state = "ACTIVE"
                    else:
                        self._failures[name] = self._failures.get(name, 0) + 1
                        if self._failures[name] >= self.MAX_CONSECUTIVE_FAILURES:
                            self._state[name] = "DEAD"
                            log.warning("Provider %s: %d consecutive failures — marked DEAD", name, self._failures[name])
                        else:
                            self._cooldown_until[name] = now + self.COOLDOWN_SECS
                        continue
                else:
                    continue

            if state != "ACTIVE":
                continue

            candidates.append((wmap.get(name, cfg.weight), cfg))

        candidates.sort(key=lambda x: -x[0])  # highest weight first
        return [c for _, c in candidates]

    def record_failure(self, name: str):
        """Transition *name* to COOLING_DOWN state."""
        now = time.monotonic()
        self._state[name] = "COOLING_DOWN"
        self._cooldown_until[name] = now + self.COOLDOWN_SECS
        self._failures[name] = self._failures.get(name, 0) + 1
        log.info("Provider %s → COOLING_DOWN for %ds (failures=%d)", name, self.COOLDOWN_SECS, self._failures[name])

    def record_success(self, name: str):
        """Reset failure count for *name*."""
        self._failures[name] = 0

    def record_dead(self, name: str):
        """Permanently remove *name* from rotation for this session.

        Used when validation proves the key/endpoint is wrong (config_invalid)
        rather than merely rate-limited.  A permanently-dead provider can never
        pass a canary, so parking it in COOLING_DOWN would invite pointless
        probes every cooldown window.
        """
        self._state[name] = "DEAD"
        self._failures[name] = 0
        log.info("Provider %s → DEAD (removed from rotation)", name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _canary(self, cfg: ProviderConfig) -> bool:
        """Try a minimal probe to see if a COOLING_DOWN provider is healthy again."""
        try:
            result = cfg.single_fn('Return a JSON object with {"status": "ok"}')
            return result is not None
        except Exception:
            return False

    def _restore(self, name: str):
        self._state[name] = "ACTIVE"
        self._failures[name] = 0
        log.info("Provider %s → ACTIVE (canary passed)", name)

    def state_summary(self) -> str:
        return ", ".join(f"{n}={s}" for n, s in sorted(self._state.items()))


# ---------------------------------------------------------------------------
#  Context Compressor — strips non-essential data before sending to LLM
# ---------------------------------------------------------------------------

def compress_job(job: dict[str, Any]) -> dict[str, Any]:
    """Return a minimal copy of *job* with only the fields the LLM needs."""
    compressed = {}
    for k in ("title", "school", "subject", "curriculum", "country",
              "location", "description", "closing_date",
              "job_type", "easy_apply"):
        v = job.get(k)
        if v:
            compressed[k] = v
    # Aggressively strip whitespace and truncate long strings
    for k, v in compressed.items():
        if isinstance(v, str):
            compressed[k] = " ".join(v.split())[:500]
    return compressed


# ---------------------------------------------------------------------------
#  LLMScorer — Weighted Load Balancer with Cascading Failover
# ---------------------------------------------------------------------------

class LLMScorer:
    def __init__(self, campaign: dict | None = None):
        self.profile = self._load_profile()
        self.campaign = campaign

        # Populate model rotation lists from settings
        if settings.groq_model:
            self.GROQ_MODELS = [settings.groq_model]
        self.NVIDIA_MODELS = [
            m for m in (settings.nvidia_model, settings.nvidia_backup_model) if m
        ]

        # Build provider list in weight order.  Each entry is a tuple:
        #   (name, single_fn, batch_fn_or_None)
        self._providers: list[tuple[str, Callable, Callable | None]] = []

        # NVIDIA
        if settings.nvidia_api_key and settings.nvidia_api_key != "nvapi-":
            self._providers.append(("nvidia", self._score_via_nvidia, None))

        # Groq
        if settings.groq_api_key:
            self._providers.append(("groq", self._score_via_groq, self._batch_score_via_groq))

        # OpenRouter
        if settings.openrouter_api_key:
            self._providers.append(("openrouter", self._score_via_openrouter,
                                    self._batch_score_via_openrouter))

        # OpenCode Zen
        if settings.opencode_zen_api_key:
            self._providers.append(("opencode_zen", self._score_via_opencode_zen, self._batch_score_via_opencode_zen))

        # Gemini
        if settings.gemini_api_key:
            self._providers.append(("gemini", self._score_via_gemini,
                                    self._batch_score_via_gemini))

        # Build ProviderRegistry
        configs = []
        for name, single_fn, batch_fn in self._providers:
            configs.append(ProviderConfig(
                name=name,
                rpm=PROVIDER_WEIGHTS.get(name, 10),
                single_fn=single_fn,
                batch_fn=batch_fn,
                key_configured=True,
                weight=PROVIDER_WEIGHTS.get(name, 10),
            ))
        self._registry = ProviderRegistry(configs)

        # Validate every provider at startup (No-Dead-End rule)
        self.validate_provider_configs()

        # Sort providers by weight (highest first) so score()/batch iterate correctly
        self._providers.sort(
            key=lambda t: PROVIDER_WEIGHTS.get(t[0], 0),
            reverse=True,
        )

        log.info("LLMScorer initialised — providers: %s", self._registry.state_summary())

    # ------------------------------------------------------------------
    #  validate_provider_configs() — No-Dead-End Rule
    #  Probes each provider once. On 404/401, the provider's own method
    #  handles backup models (e.g., NVIDIA tries nemotron-3-super-120b-a12b,
    #  OpenCode Zen tries deepseek-v4-pro). If all models for a provider fail,
    #  the provider is removed from rotation for this session.
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    #  Probe map — one-shot calls for validation (no tenacity retries)
    # ------------------------------------------------------------------

    # HTTP statuses that mean "this key/endpoint is wrong, stop asking".
    # 403 is included because every provider endpoint here is key-scoped:
    # OpenCode Zen and OpenRouter both answer 403 for an invalid key.
    # 410 Gone and 451 Unavailable For Legal Reasons are permanent removals
    # (no forwarding address) — retrying them is pointless, so they are
    # config-invalid rather than transient.  OpenCode Zen's endpoint answers
    # 410 once its free tier is withdrawn.
    _CONFIG_INVALID_STATUS = frozenset({401, 403, 404, 410, 451})

    def _probe_once(self, name: str, prompt: str) -> dict | None:
        """Single-shot probe without retries, for ``validate_provider_configs``."""
        model: str | None = None
        if name == "groq" and self.GROQ_MODELS:
            model = self.GROQ_MODELS[0]
            return self._call_groq(model, prompt)
        if name == "nvidia" and self.NVIDIA_MODELS:
            model = self.NVIDIA_MODELS[0]
            return self._call_nvidia(model, prompt)
        if name == "openrouter":
            model = settings.openrouter_model
            return self._call_openrouter(model, prompt)
        if name == "opencode_zen":
            for m in self.OPENCODE_MODELS:
                result = self._call_opencode_zen(m, prompt)
                if result is not None:
                    return result
            return None
        if name == "gemini":
            return self._call_gemini("gemini-2.5-flash", prompt)
        return None

    def _probe_verdict(self, name: str, prompt: str) -> tuple[str, int | None]:
        """Probe *name* and classify the outcome.

        Returns ``(verdict, http_status)`` where verdict is one of:

        ``"ok"``
            Provider answered with a parseable score.
        ``"config_invalid"``
            The key or endpoint is wrong (401/403/404).  Retrying within the
            run is pointless, so the provider is dropped from rotation.
        ``"transient"``
            Rate limit, 5xx, timeout, connection error, or an unparseable
            body.  The provider is probably fine and must stay in rotation.

        This distinction is load-bearing.  ``_call_gemini`` *raises* on 429
        while returning ``None`` for an empty/unparseable body, and every
        other ``_call_*`` uses ``raise_for_status``.  The previous
        implementation caught all of these with a bare ``except Exception``
        and collapsed them to a single ``[CONFIG_INVALID]`` outcome — which
        meant a provider being momentarily rate-limited was thrown out of
        rotation for the rest of the run.  Gemini, which successfully
        batch-scored jobs hours earlier, was discarded this way.
        """
        try:
            result = self._probe_once(name, prompt)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in self._CONFIG_INVALID_STATUS:
                return "config_invalid", status
            # 429 / 5xx — rate limited or upstream trouble.
            return "transient", status
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            log.warning("  ! %s probe transport error: %s", name, exc)
            return "transient", None
        except Exception as exc:
            # A crash in parsing/prompting says nothing about the key.
            log.warning("  ! %s probe raised %s: %s", name, type(exc).__name__, exc)
            return "transient", None

        if result is not None and result.get("score") is not None:
            return "ok", None
        # Answered, but with nothing usable — a body we could not parse.
        return "transient", None

    def validate_provider_configs(self) -> None:
        """Probe every registered provider once.

        Permanently-dead providers (bad key / wrong endpoint) are removed
        from rotation and their verdict persisted so the next run does not
        re-probe them.  Providers that merely rate-limited or hiccuped stay
        registered but start in COOLING_DOWN.
        """
        deadline = time.monotonic() + 120  # total 2-minute budget across all providers
        still_alive: list[tuple[str, Callable, Callable | None]] = []

        for name, single_fn, batch_fn in self._providers:
            if time.monotonic() >= deadline:
                log.warning("Validation deadline exceeded — keeping %s as-is", name)
                still_alive.append((name, single_fn, batch_fn))
                continue

            cached = _provider_health.cached_verdict(name)
            if cached == "config_invalid":
                log.info("  ✗ %s known CONFIG_INVALID (cached) — skipping probe", name)
                # Mark it in the registry too, otherwise the startup summary
                # reports a dropped provider as ACTIVE.
                self._registry.record_dead(name)
                continue

            log.info("Validating provider %s ...", name)

            # Build a proper scoring-style probe so the provider can parse it
            probe_job = {'title': 'Physics Teacher', 'school': 'Probe School',
                         'country': 'UK', 'subject': ['Physics'], 'curriculum': ['IGCSE']}
            compressed = compress_job(probe_job)
            probe_prompt = JOB_SCORING_PROMPT.format(
                profile=json.dumps(self.profile, indent=2),
                job=json.dumps(compressed, indent=2),
            )

            verdict, status = self._probe_verdict(name, probe_prompt)
            _provider_health.record(name, verdict, status)

            if verdict == "ok":
                self._registry.record_success(name)
                still_alive.append((name, single_fn, batch_fn))
            elif verdict == "config_invalid":
                log.warning("  ✗ %s failed validation — removing from rotation [CONFIG_INVALID, HTTP %s]",
                            name, status)
                self._registry.record_dead(name)
            else:
                # Keep it. A rate-limited provider is a working provider.
                log.warning("  ! %s probe failed transiently — keeping in rotation on cooldown", name)
                self._registry.record_failure(name)
                still_alive.append((name, single_fn, batch_fn))

        self._providers = still_alive

    def _load_profile(self) -> dict:
        try:
            with open("data/profile.json") as f:
                # Preserve the real cv_summary from the profile file. The earlier
                # `| {"cv_summary": ""}` merge overwrote it with an empty string
                # because dict `|` keeps the right operand, sending every scoring
                # prompt out with a blank CV summary.
                return json.load(f)
        except FileNotFoundError:
            return {
                "target_subjects": ["Physics"],
                "target_curricula": ["IGCSE", "A-Level", "IB"],
                "cv_summary": "",
            }

    # ------------------------------------------------------------------
    #  Score modifiers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_modifiers(score: int, job: dict) -> tuple[int, list[str]]:
        """Apply Easy-Apply bonus and deadline urgency modifiers."""
        modifiers: list[str] = []

        easy = job.get("easy_apply", False)
        if easy:
            score += EASY_APPLY_BONUS
            modifiers.append(f"easy-apply +{EASY_APPLY_BONUS}")

        closing = job.get("closing_date")
        if closing:
            try:
                if isinstance(closing, str):
                    closing_dt = datetime.strptime(closing, "%Y-%m-%d").date()
                elif isinstance(closing, datetime):
                    closing_dt = closing.date()
                else:
                    closing_dt = closing
                today = date.today()
                days_left = (closing_dt - today).days
                if days_left < 0:
                    modifiers.append(f"deadline passed ({-days_left}d ago)")
                elif days_left <= 7:
                    score += DEADLINE_WITHIN_7_DAYS
                    modifiers.append(f"closing soon ({days_left}d) +{DEADLINE_WITHIN_7_DAYS}")
                elif days_left <= 14:
                    score += DEADLINE_WITHIN_14_DAYS
                    modifiers.append(f"closing ({days_left}d) +{DEADLINE_WITHIN_14_DAYS}")
                elif days_left <= 30:
                    score += DEADLINE_WITHIN_30_DAYS
                    modifiers.append(f"closing ({days_left}d) +{DEADLINE_WITHIN_30_DAYS}")
            except (ValueError, TypeError):
                pass

        return min(score, 100), modifiers

    # ------------------------------------------------------------------
    #  Model rotation helper — tries models in order with tenacity retry
    # ------------------------------------------------------------------

    def _try_models(self, provider_name: str, prompt: str,
                    models: list[str],
                    call_fn: Callable[[str, str], dict | None],
                    model_configs: dict[str, dict] | None = None) -> dict | None:
        """Try each *model* in *models* through *call_fn(model, prompt)*.

        For each model, uses tenacity exponential backoff (3 attempts).
        Logs every attempt in [PIPELINE] format.
        Returns the first successful dict, or None if all models fail.
        """
        for model in models:
            retryer = Retrying(
                wait=wait_random_exponential(multiplier=1, max=60),
                stop=stop_after_attempt(3),
                reraise=False,
            )
            model_exhausted = True

            for attempt in retryer:
                attempt_n = attempt.retry_state.attempt_number
                with attempt:
                    try:
                        result = call_fn(model, prompt)
                        if result is not None:
                            log.info(
                                "[PIPELINE] Provider: %s | Model: %s | Result: Success | Attempt: %d",
                                provider_name, model, attempt_n,
                            )
                            return result
                        # None means the provider rejected the model (401/404)
                        # or couldn't extract JSON — don't retry, try next model
                        model_exhausted = False
                        break
                    except Exception as e:
                        status = ""
                        if isinstance(e, httpx.HTTPStatusError):
                            status = f" HTTP {e.response.status_code}"
                            # Non-retryable HTTP errors — move to next model
                            if e.response.status_code in (401, 404):
                                log.warning(
                                    "[PIPELINE] Provider: %s | Model: %s | Result: Fail (%s%s) | Attempt: %d — not retrying",
                                    provider_name, model, e.__class__.__name__, status,
                                    attempt_n,
                                )
                                model_exhausted = False
                                break
                        elif isinstance(e, httpx.TimeoutException):
                            status = " (timeout)"
                        log.warning(
                            "[PIPELINE] Provider: %s | Model: %s | Result: Fail (%s%s) | Attempt: %d",
                            provider_name, model, e.__class__.__name__, status,
                            attempt_n,
                        )
                        raise  # triggers tenacity retry

            if model_exhausted:
                log.warning(
                    "[PIPELINE] Provider: %s | Model: %s | Retries exhausted — rotating to next model",
                    provider_name, model,
                )

        log.warning("[PIPELINE] Provider: %s | All models failed — returning None", provider_name)
        return None

    # ------------------------------------------------------------------
    #  Cascading failover — ``score()``
    # ------------------------------------------------------------------

    def score(self, job: dict[str, Any]) -> dict[str, Any]:
        """Score *job* using the first available provider; cascade on any error."""
        compressed = compress_job(job)
        prompt = JOB_SCORING_PROMPT.format(
            profile=json.dumps(self.profile, indent=2),
            job=json.dumps(compressed, indent=2),
        )
        if self.campaign is not None:
            prompt += CAMPAIGN_CONTEXT_BLOCK

        # Consult the registry so COOLING_DOWN / DEAD providers are skipped
        # instead of being retried on every job. record_success/record_failure
        # below drive the state transitions.
        for cfg in self._registry.active_providers(PROVIDER_WEIGHTS):
            try:
                result = cfg.single_fn(prompt)
                if result is not None:
                    self._registry.record_success(cfg.name)
                    score, mods = self._apply_modifiers(result.get("score", 0), job)
                    result["score"] = score
                    if mods:
                        existing = result.get("reasoning", "")
                        result["reasoning"] = (f"{existing} | {'; '.join(mods)}"
                                               if existing else "; ".join(mods))
                    return result
            except Exception as e:
                log.warning("%s score failed: %s — cascading to next provider", cfg.name, e)
                self._registry.record_failure(cfg.name)

        # Ultimate fallback — rule-based
        result = self._score_via_rules(job)
        score, mods = self._apply_modifiers(result["score"], job)
        result["score"] = score
        if mods:
            existing = result.get("reasoning", "")
            result["reasoning"] = (f"{existing} | {'; '.join(mods)}"
                                   if existing else "; ".join(mods))
        return result

    # ------------------------------------------------------------------
    #  Leaky-bucket paced ``batch_score()``
    # ------------------------------------------------------------------

    def batch_score(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Score *jobs* with leaky-bucket pacing (max 5 per chunk, 20 s delay)."""
        results: list[dict[str, Any]] = []
        chunk_count = 0

        for start in range(0, len(jobs), MAX_PER_CHUNK):
            chunk = jobs[start: start + MAX_PER_CHUNK]
            chunk_count += 1

            scored = self._try_batch(chunk)
            if scored is None:
                scored = [self.score(j) for j in chunk]
            elif len(scored) != len(chunk):
                # Defence in depth: no provider may shorten the list, even
                # one that returns an array of the *wrong* length rather than
                # a bare object.  Backfill the missing tail individually so a
                # short response can never leave a job permanently unscored
                # (that bug stranded jobs at score=null forever, because the
                # caller zipped the results against the chunk).
                log.warning(
                    "Batch returned %d result(s) for a chunk of %d — backfilling %d individually",
                    len(scored), len(chunk), len(chunk) - len(scored),
                )
                for i in range(len(scored), len(chunk)):
                    scored.append(self.score(chunk[i]))

            results.extend(scored)

            # Leaky-bucket delay between chunks (skip delay on last chunk)
            remaining = len(jobs) - (start + MAX_PER_CHUNK)
            if remaining > 0:
                log.info("Leaky-bucket delay: sleeping %ds before next chunk...", CHUNK_DELAY)
                time.sleep(CHUNK_DELAY)
            else:
                log.info("All %d chunks processed — no delay needed", chunk_count)

        return results

    def _try_batch(self, chunk: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        """Try batch-scoring *chunk* through active providers in weight order."""
        compressed = [compress_job(j) for j in chunk]
        serialized = json.dumps([{
            k: v for k, v in j.items()
            if k in ("title", "school", "subject", "curriculum", "country",
                     "location", "description")
        } for j in compressed], indent=2)
        prompt = BATCH_SCORING_PROMPT.format(
            n=len(chunk),
            profile=json.dumps(self.profile, indent=2),
            serialized_jobs=serialized,
        )
        if self.campaign is not None:
            prompt += CAMPAIGN_CONTEXT_BLOCK

        for cfg in self._registry.active_providers(PROVIDER_WEIGHTS):
            if cfg.batch_fn is None:
                continue
            try:
                result = cfg.batch_fn(prompt, len(chunk))
                if result is not None:
                    self._registry.record_success(cfg.name)
                    log.info("Batch scored %d jobs via %s", len(result), cfg.name)
                    return result
            except Exception as e:
                log.warning("%s batch failed: %s — cascading", cfg.name, e)
                self._registry.record_failure(cfg.name)

        return None  # caller will fall back to individual cascade

    # ------------------------------------------------------------------
    #  Model rotation lists (primary → fallback chain, per provider)
    #  Populated from settings at instance creation.
    # ------------------------------------------------------------------

    GROQ_MODELS: list[str] = []
    NVIDIA_MODELS: list[str] = []
    # Primary: mimo-v2.5-free (OpenCode Zen). deepseek-v4-flash-free is the fallback
    # if mimo-v2.5-free is unavailable / errors (2026-08-30).
    OPENCODE_MODELS: list[str] = ["mimo-v2.5-free", "deepseek-v4-flash-free"]

    # ------------------------------------------------------------------
    #  _call_base — shared HTTP POST to any OpenAI-compatible endpoint
    # ------------------------------------------------------------------

    def _call_base(self, url: str, api_key: str, model: str, prompt: str,
                   max_tokens: int = 800, timeout: int = 60,
                   extra_body: dict | None = None) -> dict | None:
        """Single HTTP POST to an OpenAI-compatible chat completions endpoint.

        Returns parsed JSON dict on success, or None on hard error (401/404)
        or JSON extraction failure.  Raises on retryable errors (429, 5xx,
        timeouts) so ``_try_models`` can retry.
        """
        body: dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
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

        # Hard errors — no retry
        if resp.status_code in (401, 404):
            log.warning("[CONFIG_INVALID] Model %r at %s rejected (HTTP %s)",
                        model, url, resp.status_code)
            return None

        # Retryable errors — raise to trigger tenacity
        resp.raise_for_status()

        # Parse content
        content = resp.json()["choices"][0]["message"]["content"].strip()
        json_str = self._extract_json(content)
        if json_str is None:
            cleaned = content.removeprefix("```json").removesuffix("```").strip()
            json_str = self._extract_json(cleaned)
        if json_str is None:
            log.warning("Could not extract JSON from %s response: %r", model, content[:200])
            return None
        return json.loads(json_str)

    # ------------------------------------------------------------------
    #  Provider: Groq
    # ------------------------------------------------------------------

    def _call_groq(self, model: str, prompt: str) -> dict | None:
        return self._call_base(
            "https://api.groq.com/openai/v1/chat/completions",
            settings.groq_api_key, model, prompt,
        )

    def _score_via_groq(self, prompt: str) -> dict | None:
        return self._try_models("groq", prompt, self.GROQ_MODELS, self._call_groq)

    def _batch_score_via_groq(self, prompt: str, expected: int) -> list[dict] | None:
        """Batch scoring via Groq (single call, multi-job response)."""
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
                    "temperature": 0.1,
                    "max_tokens": 2000,
                },
                timeout=60,
            )
            if resp.status_code in (401, 404):
                log.warning("[CONFIG_INVALID] Groq batch rejected (HTTP %s)", resp.status_code)
                return None
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            json_str = self._extract_json_array(content)
            if json_str is None:
                # A bare object instead of an array is not a usable batch
                # result.  Wrapping it as [obj] silently shortens the list,
                # and the caller zips it against the chunk — so every job
                # after the first is left permanently unscored.  Cascade
                # instead so the per-job path scores them.
                log.warning("Groq batch: expected a JSON array of %d, got a bare object — cascading", expected)
                return None
            scores = json.loads(json_str)
            if isinstance(scores, dict):
                scores = [scores]
            if len(scores) != expected:
                log.warning("Groq batch: expected %d scores, got %d", expected, len(scores))
            return scores[:expected]
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 500, 502, 503):
                raise  # retryable
            log.warning("Groq batch failed: %s", e)
            return None
        except Exception as e:
            log.debug("Groq batch failed: %s", e)
            return None

    # ------------------------------------------------------------------
    #  Provider: NVIDIA NIM
    # ------------------------------------------------------------------

    def _call_nvidia(self, model: str, prompt: str) -> dict | None:
        """Call NVIDIA with *model*.

        Reasoning-mode headroom: both NVIDIA chain members
        ([nvidia/nemotron-3-super-120b-a12b, openai/gpt-oss-20b])
        emit a response that puts a meaningful fraction of the
        completion budget into ``reasoning_content`` chain-of-thought,
        so the default ``max_tokens=800`` returns ``content=""`` or a
        truncated JSON fragment and ``_extract_json()`` silently fails
        for the real scoring prompt.  Empirical verification on
        2026-06-29 (real IGCSE-Physics probe prompt) confirmed
        ``max_tokens=4096`` is enough for *both* NVIDIA models to finish
        reasoning, hit ``finish_reason=stop``, and emit a parseable
        JSON answer (``{"score":...}``).  Without this headroom the
        NVIDIA chain cascades wastefully to ``openrouter`` /
        ``gemini`` on every job.

        Combined NVIDIA call cost at 4096 tokens for a typical scoring
        prompt: ~750 total completion tokens (650 reasoning + 100
        answer) per job.  That maps to <1 cent per job on the free
        NVIDIA catalogue tier.
        """
        return self._call_base(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            settings.nvidia_api_key, model, prompt,
            max_tokens=4096, timeout=120,
        )

    def _score_via_nvidia(self, prompt: str) -> dict | None:
        return self._try_models("nvidia", prompt, self.NVIDIA_MODELS, self._call_nvidia)

    # ------------------------------------------------------------------
    #  Provider: OpenRouter
    # ------------------------------------------------------------------

    def _call_openrouter(self, model: str, prompt: str) -> dict | None:
        return self._call_base(
            "https://openrouter.ai/api/v1/chat/completions",
            settings.openrouter_api_key, model, prompt,
        )

    def _score_via_openrouter(self, prompt: str) -> dict | None:
        return self._try_models(
            "openrouter", prompt, [settings.openrouter_model], self._call_openrouter,
        )

    def _batch_score_via_openrouter(self, prompt: str, expected: int) -> list[dict] | None:
        """Batch scoring via OpenRouter (single call, multi-job response)."""
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
                    "temperature": 0.1,
                    "max_tokens": 1500,
                },
                timeout=30,
            )
            if resp.status_code in (401, 404):
                log.warning("[CONFIG_INVALID] OpenRouter batch rejected (HTTP %s)", resp.status_code)
                return None
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            json_str = self._extract_json_array(content)
            if json_str is None:
                # A bare object instead of an array is not a usable batch
                # result.  Wrapping it as [obj] silently shortens the list,
                # and the caller zips it against the chunk — so every job
                # after the first is left permanently unscored.  Cascade
                # instead so the per-job path scores them.
                log.warning("OpenRouter batch: expected a JSON array of %d, got a bare object — cascading", expected)
                return None
            scores = json.loads(json_str)
            if isinstance(scores, dict):
                scores = [scores]
            if len(scores) != expected:
                log.warning("OpenRouter batch: expected %d scores, got %d", expected, len(scores))
            return scores[:expected]
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 500, 502, 503):
                raise  # retryable
            log.warning("OpenRouter batch failed: %s", e)
            return None
        except Exception as e:
            log.debug("OpenRouter batch failed: %s", e)
            return None

    # ------------------------------------------------------------------
    #  Provider: Gemini
    # ------------------------------------------------------------------

    def _call_gemini(self, model: str, prompt: str) -> dict | None:
        """Single Gemini API call.  Returns parsed dict or None."""
        resp = httpx.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            params={"key": settings.gemini_api_key},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": 0.1,
                    "maxOutputTokens": 2000,
                },
            },
            timeout=30,
        )
        if resp.status_code == 429:
            raise httpx.HTTPStatusError("Gemini 429", request=resp.request, response=resp)
        if resp.status_code != 200:
            log.warning("Gemini %s — body: %s", resp.status_code, resp.text[:300])
            return None
        data = resp.json()
        try:
            candidate = data["candidates"][0]
            content = candidate["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            log.warning("Gemini: unexpected response shape: %s", data)
            return None
        content = content.strip()
        json_str = self._extract_json(content)
        if json_str is None:
            log.warning("Gemini: could not extract JSON from content: %r", content[:300])
            return None
        return json.loads(json_str)

    def _score_via_gemini(self, prompt: str) -> dict | None:
        return self._try_models(
            "gemini", prompt, ["gemini-2.5-flash"], self._call_gemini,
        )

    def _batch_score_via_gemini(self, prompt: str, expected: int) -> list[dict] | None:
        """Batch scoring via Gemini (single call, multi-job response)."""
        try:
            resp = httpx.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                params={"key": settings.gemini_api_key},
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "response_mime_type": "application/json",
                        "temperature": 0.1,
                        "maxOutputTokens": 3000,
                    },
                },
                timeout=45,
            )
            if resp.status_code == 429:
                raise httpx.HTTPStatusError("Gemini batch 429", request=resp.request, response=resp)
            if resp.status_code != 200:
                log.warning("Gemini batch %s — body: %s", resp.status_code, resp.text[:300])
                return None
            data = resp.json()
            candidate = data["candidates"][0]
            content = candidate["content"]["parts"][0]["text"]
            json_str = self._extract_json_array(content)
            if json_str is None:
                # A bare object instead of an array is not a usable batch
                # result.  Wrapping it as [obj] silently shortens the list,
                # and the caller zips it against the chunk — so every job
                # after the first is left permanently unscored.  Cascade
                # instead so the per-job path scores them.
                log.warning("Gemini batch: expected a JSON array of %d, got a bare object — cascading", expected)
                return None
            scores = json.loads(json_str)
            if isinstance(scores, dict):
                scores = [scores]
            if len(scores) != expected:
                log.warning("Gemini batch: expected %d scores, got %d", expected, len(scores))
            return scores[:expected]
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 500, 502, 503):
                raise  # retryable
            log.warning("Gemini batch failed: %s", e)
            return None
        except Exception as e:
            log.debug("Gemini batch failed: %s", e)
            return None

    # ------------------------------------------------------------------
    #  Provider: OpenCode Zen
    # ------------------------------------------------------------------

    def _call_opencode_zen(self, model: str, prompt: str) -> dict | None:
        # Reasoning-mode headroom: deepseek-v4-flash-free burns most of
        # its output budget on ``reasoning_content`` chain-of-thought, so
        # a plain ``max_tokens=800`` returns ``content=""``.  Empirical
        # verification on 2026-06-28 confirmed ``max_tokens=4096`` is
        # enough for the model to finish reasoning and emit the visible
        # answer (``JSON {"score":..}``) for the real probe prompt.
        return self._call_base(
            "https://opencode.ai/zen/v1/chat/completions",
            settings.opencode_zen_api_key, model, prompt,
            max_tokens=4096, timeout=120,
        )

    def _score_via_opencode_zen(self, prompt: str) -> dict | None:
        return self._try_models("opencode_zen", prompt, self.OPENCODE_MODELS, self._call_opencode_zen)

    def _batch_score_via_opencode_zen(self, prompt: str, expected: int) -> list[dict] | None:
        """Batch scoring via OpenCode Zen (single call, multi-job response).

        Uses the first model in OPENCODE_MODELS (mimo-v2.5-free, with
        deepseek-v4-flash-free as fallback) — see _try_models rotation.
        Reasoning-mode headroom: max_tokens=4096 so the model can finish
        its reasoning_content chain-of-thought and emit the visible JSON
        array answer (same fix as the single-score path, 2026-06-28).
        temperature=0.3 matches the single-score path (not 0.1 like Groq)
        because reasoning-mode models benefit from a slightly warmer
        setting to avoid the chain-of-thought collapsing onto itself.
        """
        last_err: Exception | None = None
        for model in self.OPENCODE_MODELS:
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
                        "max_tokens": 4096,
                    },
                    timeout=120,
                )
                if resp.status_code in (401, 404):
                    log.warning("[CONFIG_INVALID] OpenCode Zen batch model %r rejected (HTTP %s) — trying next",
                                model, resp.status_code)
                    last_err = RuntimeError(f"HTTP {resp.status_code}")
                    continue
                resp.raise_for_status()
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 500, 502, 503):
                    raise  # retryable — tenacity handles
                log.warning("OpenCode Zen batch model %r failed: %s — trying next", model, e)
                last_err = e
                continue
            except Exception as e:
                log.debug("OpenCode Zen batch model %r failed: %s", model, e)
                last_err = e
                continue
        else:
            log.warning("OpenCode Zen batch: all models failed (last: %s)", last_err)
            return None

        try:
            content = resp.json()["choices"][0]["message"]["content"]
            json_str = self._extract_json_array(content)
            if json_str is None:
                # A bare object instead of an array is not a usable batch
                # result.  Wrapping it as [obj] silently shortens the list,
                # and the caller zips it against the chunk — so every job
                # after the first is left permanently unscored.  Cascade
                # instead so the per-job path scores them.
                log.warning("OpenCode Zen batch: expected a JSON array of %d, got a bare object — cascading", expected)
                return None
            scores = json.loads(json_str)
            if isinstance(scores, dict):
                scores = [scores]
            if len(scores) != expected:
                log.warning("OpenCode Zen batch: expected %d scores, got %d", expected, len(scores))
            return scores[:expected]
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 500, 502, 503):
                raise  # retryable — tenacity handles
            log.warning("OpenCode Zen batch failed: %s", e)
            return None
        except Exception as e:
            log.debug("OpenCode Zen batch failed: %s", e)
            return None

    # ------------------------------------------------------------------
    #  Rule-based ultimate fallback
    # ------------------------------------------------------------------

    def _score_via_rules(self, job: dict) -> dict:
        # Campaign-aware: if a deterministic campaign_score was already
        # computed upstream, surface it so the rule fallback stays aligned
        # with the campaign's 5-axis rubric instead of the generic profile.
        if job.get("campaign_score") is not None:
            return {
                "score": int(job["campaign_score"]),
                "reasoning": "campaign deterministic score",
                "housing_allowance": job.get("housing_allowance"),
                "curriculum_match": job.get("curriculum", "Other"),
            }

        # Aligned with the LLM rubric (Curriculum 0-35, Subject 0-30,
        # Location 0-25, Housing 0-10) so that the ultimate fallback — only
        # reached when every provider is dead — ranks jobs on a comparable
        # scale rather than capping at 80 and silently gating good jobs below
        # the notify threshold. Slightly conservative on each axis to avoid
        # over-ranking in the absence of the LLM's nuance.
        title = (job.get("title") or "").lower()
        combined = f"{title} {(job.get('school') or '')} {(job.get('subject') or '')} {(job.get('curriculum') or '')}".lower()
        reason = []
        score = 0

        # Subject match (LLM rubric: 0-30)
        target_subjects = self.profile.get("target_subjects", ["Physics"])
        if any(s.lower() in title for s in target_subjects):
            score += 30
            reason.append("subject match")

        # Curriculum match (LLM rubric: 0-35)
        target_curricula = self.profile.get("target_curricula", [])
        if target_curricula and any(c.lower() in combined for c in target_curricula):
            score += 30  # conservative — full rubric weight is 35
            matched_curr = next((c for c in target_curricula if c.lower() in combined), "Other")
            reason.append(matched_curr)
        else:
            matched_curr = "Other"

        # Location match (LLM rubric: 0-25)
        country = (job.get("country") or "").lower()
        target_countries = self.profile.get("target_countries", [])
        if target_countries and country in [c.lower() for c in target_countries]:
            score += 25
            reason.append("country match")

        # Housing/benefits (LLM rubric: 0-10)
        housing = job.get("housing_allowance")
        if housing:
            score += 10
            reason.append("housing listed")

        score = min(score, 100)
        return {
            "score": score,
            "reasoning": "; ".join(reason) if reason else "rule-based fallback",
            "housing_allowance": housing,
            "curriculum_match": matched_curr,
        }

    # ------------------------------------------------------------------
    #  JSON extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _balanced_extract(text: str, start: int, open_ch: str, close_ch: str) -> str | None:
        """String-aware bracket walker. Skips characters inside JSON string literals."""
        depth = 0
        in_string = False
        i = start
        n = len(text)
        while i < n:
            ch = text[i]
            if ch == "\\" and in_string:
                i += 2  # skip escaped char entirely
                continue
            if ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1]
            i += 1
        return None

    @staticmethod
    def _strip_llm_wrappers(text: str) -> str:
        """Remove markdown fences and NVIDIA thinking tags."""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        return text.removesuffix("```").strip()

    @classmethod
    def _extract_json(cls, text: str) -> str | None:
        if not text:
            return None
        text = cls._strip_llm_wrappers(text)
        start = text.find("{")
        if start == -1:
            return None
        candidate = cls._balanced_extract(text, start, "{", "}")
        if candidate is None:
            return None
        # Fix trailing commas before } or ]
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            return None

    @classmethod
    def _extract_json_array(cls, text: str) -> str | None:
        if not text:
            return None
        text = cls._strip_llm_wrappers(text)
        start = text.find("[")
        if start == -1:
            return None
        candidate = cls._balanced_extract(text, start, "[", "]")
        if candidate is None:
            return None
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            return None

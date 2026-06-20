# Physics Job Hunter — Agent Guide

## Entrypoints

- **CLI**: `physics-job-hunter` (needs `pip install -e .`) or `python3 -m src.main`
- **Scheduler (systemd user service)**: `systemctl --user start physics-job-hunter.service` (APScheduler via systemd, survives reboot via `loginctl enable-linger $USER`)
- **Stop**: `systemctl --user stop physics-job-hunter.service`
- **Status**: `systemctl --user status physics-job-hunter.service`
- **Live logs**: `journalctl --user -u physics-job-hunter.service -f`
- **Disable auto-start**: `systemctl --user disable physics-job-hunter.service`
- No web server or API — fully script-based pipeline.
- Legacy nohup command (if systemd unavailable): `nohup python3 -c "from src.scheduler.daily_run import start; start()" > /tmp/scheduler.log 2>&1 &`

## Pipeline (`src/main.py:run_pipeline()`)

1. **Scrape** — `TESScraper` (works) + `LibyanJobsScraper` (works) + `LinkedInScraper` + `SearchAssociatesScraper` + `SchroleScraper` (last 3 are placeholders, return `[]`)
2. **Heuristic pre-filter** — `filter_relevant_jobs()` drops jobs whose title/subject don't match physics/maths/science/IGCSE/A-Level keywords
3. **Deduplicate** — skip URLs already in Supabase (falls back to `DedupStore` SQLite at `data/dedup.db`)
4. **Upsert** — `SupabaseClient.upsert_jobs()` into `job_listings` table; coerces empty `closing_date=""` → `None`
5. **Score** — `LLMScorer` with Weighted Provider Registry: validates providers at startup via `validate_provider_configs()`, removes dead ones, queries survivors in weight order. Active providers: **Groq** (weight 40) → **NVIDIA** (30) → **OpenRouter** (20) → **Gemini** (15). OpenCode Zen (weight 20) is always dead (401). `SCORER_PROVIDER`/`SCORER_FALLBACK` env vars are **not consumed** — provider selection = API key presence + `PROVIDER_WEIGHTS`. If all LLM providers fail, falls back to rule-based scoring (base 30). LLM rubric: Curriculum 0-30, Subject 0-25, Location 0-20, Salary 0-15, Housing 0-10 (max 100). `visa_sponsorship` and `deadline_urgency` removed.
6. **Notify** — Telegram (`src/notify/telegram.py`) + Email (`src/notify/email_sender.py`, Resend or SMTP) for jobs scored ≥ `settings.notify_score_threshold` (default 50, configurable via `NOTIFY_SCORE_THRESHOLD` in `.env`)

## Important gotchas

- **Python >= 3.12** required
- **`.env` has live API keys** — do not modify or commit changes
- **`tests/test_gemini_smoke.py`** — smoke test for LLM scorer; run via `python3 tests/test_gemini_smoke.py`
- **`scripts/test_gemini.py`** — standalone Gemini key validation
- **No lint, typecheck, formatter, or pre-commit config** — nothing to run
- **`src/extractors/` is empty** — planned but not implemented
- **`TeacherHorizonsScraper` bypassed** — detail pages require activated account
- **`scripts/setup_supabase.sql`** — schema for `job_listings` table; must be applied manually to Supabase before first run (schema wiped on project pause/resume)
- **`health_check()` on `SupabaseClient`** — probes with `SELECT id LIMIT 1` at startup; if it fails, raises `httpx.HTTPError` immediately so the pipeline falls through to in-memory scoring with local SQLite
- **`update_score()` and `mark_notified()` filter by `url` column** — NOT by `id`. Callers pass `_job_key(job)` which returns `job["id"]` (UUID) or falls back to `job["url"]`. `update_score` was broken (filtered `id=url`, silent no-op)
- **`import re` must be in `src/scoring/llm_scorer.py`** — `_strip_llm_wrappers()` uses `re.sub`. If the import is missing, every provider validation fails silently (caught by `except Exception`). All providers return HTTP 200 but JSON extraction crashes with `NameError`
- **`upsert_jobs()` coerces empty `closing_date=""` → `None`** — PostgreSQL refuses `""` for `date` type
- **`get_recent()` ignores its `days` parameter** — always queries `>= date.today()`. Minor bug, but affects any code expecting a sliding window
- **Provider validation** — `validate_provider_configs()` has a 2-minute deadline; probes with a real scoring prompt. On 401/404 logs `[CONFIG_INVALID]` and removes provider. On any other failure (including extraction crash) logs `[CONFIG_INVALID]`
- **Health state machine** — `ProviderRegistry` tracks ACTIVE → COOLING_DOWN (300s canary) → DEAD (3 consecutive cooldown failures). Dead providers stay removed for the session
- **Intra-provider model rotation** — Groq: 1 model (`settings.groq_model`). NVIDIA: `nemotron-3-super-120b-a12b` (thinking + 90s timeout) → `nemotron-3-nano-30b-a3b`. OpenCode Zen: 2 models (both 401). OpenRouter/Gemini: 1 model each
- **Tenacity retry** — `tenacity.Retrying` with `wait_random_exponential(multiplier=1, max=60)`, 3 attempts per model before rotating or moving to next provider. Format: log every attempt as `[PIPELINE] Provider: groq | Model: ... | Result: Success/Fail | Attempt: N`
- **Leaky-bucket pacing** — `batch_score()` splits into chunks of `MAX_PER_CHUNK=5` with `CHUNK_DELAY=20s`. Total pipeline ~2.5min for 20 jobs
- **Cover letter `_resolve_provider()`** — probes Groq → NVIDIA → OpenRouter → OpenCode Zen → Gemini; `time.sleep(5)` between calls in evaluation loop to avoid 429s. Files tagged `__LLM` (AI) or `__fallback` (template)
- **TES scraper** — extracts from `__NEXT_DATA__` JSON (catches `AttributeError` for null fields); falls back to HTML parsing. Relative `canonicalUrl` → absolute via `https://www.tes.com` prepend at `src/scrapers/tes.py:108`
- **LibyanJobs scraper** — WordPress theme; each job is `<article.loadmore-item.noo_job>`. Up to 30 jobs across 3 pages
- **`_extract_json()` bracket walk** — used instead of brittle `json.loads()` + `removeprefix`; handles NVIDIA thinking mode interleaving reasoning text before JSON. `_extract_json_array()` for batch responses
- Supabase DNS may be unreachable — all `SupabaseClient` methods fall through to `DedupStore` on `httpx.HTTPError`
- Virtual environment at `.venv/` but deps installed globally; `pip install -e .` not required

## Configuration

- All settings via `.env`, loaded by `pydantic-settings` (`src/config.py:Settings`)
- Candidate profile: `data/profile.json`
- `SCHEDULE_TIME` format: comma-separated 24h, e.g. `08:00,17:00,22:00,22:30,23:00`
- `NOTIFY_SCORE_THRESHOLD` — minimum score for notifications (default 50, set in `.env`)

## Key files

- `src/scoring/llm_scorer.py` — Weighted Load Balancer, 5 providers, model rotation, tenacity, health state machine, leaky bucket, `_extract_json`/`_extract_json_array`
- `src/storage/supabase_client.py` — Supabase CRUD; every method falls through to `DedupStore` on `httpx.HTTPError`
- `src/storage/dedup_store.py` — SQLite tables `seen_urls` and `job_cache`; persisted across runs
- `src/generators/cover_letter.py` — 5-provider cascade, `__LLM`/`__fallback` filename tagging
- `src/notify/telegram.py` — `scoring_reasoning` in alerts, cover letter attachment
- `src/notify/email_sender.py` — Resend or SMTP with STARTTLS; must rename was `email.py` (stdlib conflict)
- `scripts/setup_supabase.sql` — schema migration; apply manually via Supabase SQL Editor

# Physics Job Hunter — Agent Guide

## Entrypoints

- **CLI**: `physics-job-hunter` (needs `pip install -e .` first) or `python3 -m src.main` (works without install)
- **Scheduler**: `python -c "from src.scheduler.daily_run import start; start()"` (APScheduler, not OS cron; accepts comma-separated times in `SCHEDULE_TIME`, e.g. `08:00,17:00,23:00`)
- No web server or API — fully script-based pipeline.

## Pipeline (in order)

`src/main.py:run_pipeline()`:
1. **Scrape** — `TESScraper` (works) + `LinkedInScraper` (placeholder, always returns `[]`)
2. **Deduplicate** — skip URLs already in Supabase
3. **Upsert** — `SupabaseClient.upsert_jobs()` into `job_listings` table
4. **Score** — `LLMScorer` via configured LLM provider, with fallback; scores only `score IS NULL` rows
5. **Notify** — Telegram (`src/notify/telegram.py`, runnable directly) + Email (`src/notify/email_sender.py`, Resend or SMTP) for jobs scored ≥ 80 that haven't been notified

## Important gotchas

- **Python >= 3.12** required
- **`.env` is committed with real API keys** — do NOT modify or commit changes to `.env`; it contains live Supabase and LLM provider credentials
- **`tests/` directory is empty** — no test suite exists
- **`src/extractors/` is empty** — planned but not implemented
- **`LinkedInScraper` is a placeholder** — `scrape()` returns `[]`; implemented as `async def` but never awaited
- **`TESScraper._extract_from_json`** catches `AttributeError` in addition to `JSONDecodeError, KeyError, TypeError` — the `__NEXT_DATA__` JSON can have null-valued fields
- **`scripts/setup_supabase.sql`** — required schema for the `job_listings` table; must be applied manually to Supabase before first run
- Virtual environment at `.venv/` but dependencies are installed globally via home dir pip; `pip install -e .` not required
- `src/notify/email_sender.py` was renamed from `email.py` to avoid shadowing stdlib `email` package
- No lint, typecheck, formatter, or pre-commit config

## Configuration

- All settings via `.env` file, loaded by `pydantic-settings` (see `src/config.py:Settings`)
- Scoring providers: `opencode_zen`, `gemini`, `nvidia` — set via `SCORER_PROVIDER` + `SCORER_FALLBACK`
- Candidate profile: `data/profile.json` — edit to tune job matching

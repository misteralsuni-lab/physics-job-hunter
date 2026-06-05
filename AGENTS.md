# Physics Job Hunter — Agent Guide

## Entrypoints

- **CLI**: `physics-job-hunter` (needs `pip install -e .` first) or `python3 -m src.main` (works without install)
- **Scheduler**: `nohup python3 -c "from src.scheduler.daily_run import start; start()" > /tmp/scheduler.log 2>&1 &` (APScheduler, not OS cron; accepts comma-separated times in `SCHEDULE_TIME`, e.g. `08:00,17:00,22:00,22:30,23:00`)
- **Stop scheduler**: `kill <PID>` (find PID via `ps aux | grep daily_run` or the `echo $!` from the nohup command)
- **Check scheduler logs**: `cat /tmp/scheduler.log`
- No web server or API — fully script-based pipeline.

## Pipeline (in order)

`src/main.py:run_pipeline()`:
1. **Scrape** — `TESScraper` (works) + `LinkedInScraper` (placeholder) + `SearchAssociatesScraper` (placeholder) + `SchroleScraper` (placeholder)
2. **Deduplicate** — skip URLs already in Supabase (falls back to in-memory if Supabase down)
3. **Upsert** — `SupabaseClient.upsert_jobs()` into `job_listings` table
4. **Score** — `LLMScorer` probes primary + fallback LLM provider once at startup; if all fail, falls back to rule-based scoring (keyword matching on title, curriculum, country, salary)
5. **Notify** — Telegram (`src/notify/telegram.py`, runnable directly) + Email (`src/notify/email_sender.py`, Resend or SMTP) for jobs scored ≥ 80

## Important gotchas

- **Python >= 3.12** required
- **`.env` is committed with real API keys** — do NOT modify or commit changes to `.env`; it contains live Supabase and LLM provider credentials
- **`tests/` directory is empty** — no test suite exists
- **`src/extractors/` is empty** — planned but not implemented
- **`LinkedInScraper` is a placeholder** — `scrape()` is `async def` but never awaited; always returns `[]`
- **`TeacherHorizonsScraper` is bypassed** — removed from `main.py` scrapers list because job detail pages require an activated teacher account; list-view data lacked school name and salary
- **`TESScraper._extract_from_json`** catches `AttributeError` in addition to `JSONDecodeError, KeyError, TypeError` — the `__NEXT_DATA__` JSON can have null-valued fields
- **TESScraper URLs** come from `canonicalUrl` in Next.js JSON, which is a relative path; `src/scrapers/tes.py:108` prepends `https://www.tes.com` to make absolute URLs for Telegram links
- **`scripts/setup_supabase.sql`** — required schema for the `job_listings` table; must be applied manually to Supabase before first run
- Virtual environment at `.venv/` but dependencies are installed globally via home dir pip; `pip install -e .` not required
- `src/notify/email_sender.py` was renamed from `email.py` to avoid shadowing stdlib `email` package
- No lint, typecheck, formatter, or pre-commit config

## Configuration

- All settings via `.env` file, loaded by `pydantic-settings` (see `src/config.py:Settings`)
- Scoring providers: `opencode_zen`, `gemini`, `nvidia` — set via `SCORER_PROVIDER` + `SCORER_FALLBACK`
  - If all LLM providers fail, `LLMScorer._score_via_rules` does keyword matching (subject, curriculum, country, salary) with base score 30
- Candidate profile: `data/profile.json` — edit to tune job matching
- `SCHEDULE_TIME` format: comma-separated 24h times, e.g. `08:00,17:00,22:00,22:30,23:00`

## Relevant files

- `src/scoring/llm_scorer.py` — probes working LLM once, caches result; `_score_via_rules` fallback at line 103
- `src/scrapers/tes.py` — `_parse_job` at line 107 converts relative `canonicalUrl` to absolute
- `src/main.py` — `run_pipeline()` handles Supabase failure gracefully, scores in-memory as fallback

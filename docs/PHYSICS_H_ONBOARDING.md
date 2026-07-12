# Physics Job Hunter — Onboarding Guide

> **New team member? Start here.**
> This guide walks you through the project architecture, key concepts, and the recommended learning path.
>
> *Generated from the project knowledge graph at commit `3cc9d723`.*

---

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture Layers](#architecture-layers)
- [Key Concepts](#key-concepts)
- [Guided Tour (10 Steps)](#guided-tour)
- [File Map](#file-map)
- [Complexity Hotspots](#complexity-hotspots)

---

## Project Overview

| | |
|---|---|
| **Name** | physics-job-hunter |
| **Description** | Automated job search pipeline for international Physics teaching roles |
| **Languages** | Python, TOML, JSON, SQL, env, markdown |
| **Frameworks** | httpx, beautifulsoup4, playwright, apscheduler, supabase, pydantic |
| **Entry Point** | `src/main.py:main()` |
| **CLI** | `physics-job-hunter` (after `pip install -e .`) |
| **Scheduler** | `nohup python3 -c "from src.scheduler.daily_run import start; start()"` |

### What It Does

The pipeline runs in 5 stages, orchestrated by `src/main.py`:

1. **Scrape** — Fetch job listings from TES.com (working) and 3 placeholder scrapers (LinkedIn, Schrole, Search Associates). Teacher Horizons is bypassed.
2. **Deduplicate** — Skip URLs already stored in Supabase (falls back to in-memory if DB is down).
3. **Upsert** — Insert or update jobs in the Supabase `job_listings` table.
4. **Score** — LLM-powered scoring against your candidate profile, with a keyword-based fallback when all LLM providers fail.
5. **Notify** — Send Telegram + email alerts for jobs scored ≥ `notify_score_threshold` (default 50, configurable via `NOTIFY_SCORE_THRESHOLD` in `.env`).

---

## Architecture Layers

The project is organized into **9 logical layers**. Every file belongs to exactly one layer.

### 1. Configuration *(5 files)*
> _Environment variables, Pydantic settings, and project metadata — consumed by every downstream module._

| File | Purpose |
|---|---|
| `.env` | API keys (Supabase, LLM providers, Telegram, email) and runtime settings |
| `.gitignore` | Excludes venv, cache, and build artifacts |
| `pyproject.toml` | Dependencies, CLI entry point, build metadata |
| `src/config.py` | **Pydantic `BaseSettings`** — loads `.env` into typed Python objects |
| `src/__init__.py` | Package marker |

**Why it matters:** `src/config.py` has the highest **fan-in** in the project (8 incoming edges). Every module imports it for settings. Change `.env` and nothing else, and the whole pipeline adapts.

---

### 2. Pipeline Orchestration *(3 files)*
> _The conductor. Highest fan-out (10 edges to scrapers, storage, scoring, notify)._

| File | Purpose |
|---|---|
| `src/main.py` | **Orchestrator** — `run_pipeline()` chains scrape → dedup → score → notify |
| `src/scheduler/daily_run.py` | **APScheduler** — runs `run_pipeline()` at configurable times (e.g. `08:00,17:00,22:00`) |
| `src/scheduler/__init__.py` | Package marker |

**Key insight:** `main.py` is the only file that knows the full pipeline. Every other module is a black-box stage.

---

### 3. Data Collection (Scrapers) *(7 files)*
> _820 lines of scraping logic. The most active development area._

| File | Status | Purpose |
|---|---|---|
| `src/scrapers/base.py` | **Abstract** | HTTP client, BS4 parsing, URL utilities |
| `src/scrapers/tes.py` | **Working** | Primary scraper — Next.js JSON + HTML fallback |
| `src/scrapers/teacher_horizons.py` | **Bypassed** | Playwright-based SPA scraper (needs activated account) |
| `src/scrapers/linkedin.py` | Placeholder | Requires logged-in session |
| `src/scrapers/schrole.py` | Placeholder | Requires login credentials |
| `src/scrapers/search_associates.py` | Placeholder | Requires login credentials |
| `src/scrapers/__init__.py` | — | Package marker |

**Design pattern:** All scrapers inherit from `BaseScraper` (ABC). The orchestrator treats them polymorphically — call `scrape()` and get a list of job dicts.

---

### 4. Scoring Engine *(2 files)*
> _LLM-powered or rule-based fallback. The brain of the pipeline._

| File | Purpose |
|---|---|
| `src/scoring/llm_scorer.py` | Probes 3 LLM providers at startup, caches the winner, scores against `profile.json` |
| `src/scoring/__init__.py` | Package marker |

**Fallback logic:** If all LLM providers fail (Zen: no payment, Gemini: invalid key, NVIDIA: 403), `_score_via_rules()` does keyword matching on title, curriculum, country, salary — base 30 + up to 50 bonus points.

---

### 5. Notification *(3 files)*
> _Telegram bot + email digests. Only fires for jobs scored ≥ threshold (default 50)._

| File | Purpose |
|---|---|
| `src/notify/telegram.py` | Telegram Bot API alerts with clickable "Apply" links |
| `src/notify/email_sender.py` | HTML email via **Resend API** or direct **SMTP** with STARTTLS |
| `src/notify/__init__.py` | Package marker |

**Note:** `email_sender.py` was renamed from `email.py` to avoid shadowing the stdlib `email` package.

---

### 6. Storage *(2 files)*
> _Supabase client for persistent job storage._

| File | Purpose |
|---|---|
| `src/storage/supabase_client.py` | CRUD on `job_listings` table, deduplication by URL |
| `src/storage/__init__.py` | Package marker |

**Fallback:** If Supabase DNS is unreachable, the pipeline falls back to in-memory deduplication and continues scoring/notification.

---

### 7. Data Schema *(7 nodes)*
> _Database definition + candidate profile._

| File/Table | Purpose |
|---|---|
| `data/profile.json` | Candidate profile — subject, curriculum, countries, salary, CV summary |
| `scripts/setup_supabase.sql` | **Migration** — creates `job_listings` table + 4 indexes |
| `table:job_listings` | Main table storing scraped jobs |
| `table:idx_job_listings_score` | Index on `score` for fast filtering |
| `table:idx_job_listings_notified` | Index on `notified` for finding unnotified jobs |
| `table:idx_job_listings_source` | Index on `source` for filtering by scraper |
| `table:idx_job_listings_created` | Index on `created_at` for time-based queries |

**Important:** Run `scripts/setup_supabase.sql` manually in Supabase before the first pipeline run.

---

### 8. Documentation *(1 file)*
> _The single best onboarding resource._

| File | Purpose |
|---|---|
| `AGENTS.md` | Pipeline flow, entrypoints, gotchas, config reference, troubleshooting |

**Start here** if you need a quick-reference during development.

---

### 9. Extractors *(1 file)* — Placeholder
> _Empty stub. Future: structured extraction from scraped listings._

| File | Purpose |
|---|---|
| `src/extractors/__init__.py` | Package marker (no logic yet) |

---

## Key Concepts

### 1. Pipeline Orchestration Pattern
A single `run_pipeline()` function sequences all stages linearly. Each stage is isolated in its own function. This keeps the top-level flow readable while deferring implementation to dedicated modules.

### 2. Multi-Provider LLM Fallback
The `LLMScorer` probes providers (`opencode_zen`, `gemini`, `nvidia`) once at startup, caches the first that responds, and uses it for all jobs. If all fail, a **rule-based fallback** kicks in (keyword matching). The system *always* produces a score — it never blocks on external API failure.

### 3. Polymorphic Scraper Inheritance
All scrapers inherit from `BaseScraper` (ABC) and implement `scrape()`. The orchestrator calls them uniformly — it doesn't care which scraper produced which job.

### 4. Graceful Degradation
The pipeline is designed to survive failures:
- **Supabase down** → in-memory deduplication + scoring
- **All LLMs down** → rule-based scoring
- **Single scraper fails** → other scrapers continue; pipeline skips that source
- **Telegram down** → email still sends (and vice versa)

### 5. Pydantic Settings Management
`src/config.py` uses `pydantic.BaseSettings` to load `.env` into typed, validated Python objects. Changing a setting is as simple as editing `.env` — no code changes needed.

---

## Guided Tour

Follow these 10 steps in order to understand the codebase from the ground up.

### Step 1 — Project Overview
📄 **`AGENTS.md`**

Start with the agent onboarding guide. It documents the full pipeline, entrypoints, gotchas, and configuration. Bookmark it — you will come back to it.

### Step 2 — Pipeline Entry Point & Orchestration
📄 **`src/main.py`**

The heart of the system. Read `run_pipeline()` to see how scrape → dedup → score → notify is wired together. Then read `main()` for the CLI entry point.

> **Language lesson:** Pipeline orchestration — a single function sequences stages linearly, with each stage isolated in its own function. This keeps the top-level readable.

### Step 3 — Configuration Foundation
📄 **`src/config.py`** + `.env` + `pyproject.toml`

`config.py` is the highest fan-in module (8 incoming edges). Every downstream module imports it. The `Settings` class reads `.env` via Pydantic `BaseSettings`.

> **Language lesson:** `pydantic.BaseSettings` automatically reads environment variables and `.env` files, providing type validation and defaults.

### Step 4 — Scraper Foundation & Abstract Base
📄 **`src/scrapers/base.py`**

`BaseScraper` is the second-highest fan-in class (7 inheriting classes). It provides shared HTTP client setup, BS4 parsing, and URL utilities.

> **Language lesson:** Abstract base classes (ABC) in Python define an interface contract. Subclasses must implement `scrape()` while inheriting shared utilities.

### Step 5 — Working Scraper: TES
📄 **`src/scrapers/tes.py`**

The primary working scraper. Note how `TESScraper` extracts data from `__NEXT_DATA__` JSON, falling back to HTML. Also note the relative `canonicalUrl` → absolute URL fix.

### Step 6 — Additional Scrapers
📄 **`src/scrapers/teacher_horizons.py`** + `linkedin.py` + `schrole.py` + `search_associates.py`

- **Teacher Horizons:** Playwright handles Angular SPA, but requires an activated account. Understand why it was bypassed.
- **Placeholders:** Each logs a warning and returns `[]`. They exist so the pipeline doesn't break when credentials are unavailable.

### Step 7 — Scoring Engine
📄 **`src/scoring/llm_scorer.py`** + `data/profile.json`

The most complex file in the project. Understand:
1. How providers are probed at startup
2. How the cache avoids re-probing per job
3. The rule-based fallback (`_score_via_rules`) and why it exists

> **Language lesson:** Multi-provider fallback — probe on startup, cache the winner, fall back to deterministic logic if all fail. Ensures the system runs even when external APIs are down.

### Step 8 — Notifications
📄 **`src/notify/telegram.py`** + `email_sender.py`

Both consume config and are invoked by the orchestrator for jobs ≥ `notify_score_threshold`. Note the dual-transport email (Resend API + SMTP fallback).

### Step 9 — Database Storage & Schema
📄 **`src/storage/supabase_client.py`** + `scripts/setup_supabase.sql`

`SupabaseClient` handles deduplication and upsert. The SQL migration must be applied before first run. Check the 4 indexes — they support the main query patterns.

### Step 10 — Automated Scheduling
📄 **`src/scheduler/daily_run.py`**

APScheduler triggers `run_pipeline()` at configurable times. The scheduler runs as a background Python process, not as an OS cron job.

---

## File Map

### By Layer

| Layer | Key Files |
|---|---|
| **Configuration** | `.env`, `pyproject.toml`, `src/config.py` |
| **Pipeline** | `src/main.py`, `src/scheduler/daily_run.py` |
| **Scrapers** | `src/scrapers/base.py`, `tes.py`, `teacher_horizons.py` (+ placeholders) |
| **Scoring** | `src/scoring/llm_scorer.py`, `data/profile.json` |
| **Notify** | `src/notify/telegram.py`, `email_sender.py` |
| **Storage** | `src/storage/supabase_client.py`, `scripts/setup_supabase.sql` |
| **Docs** | `AGENTS.md` |

### Quick Reference — What Each File Does

| File | Lines | Complexity | Role |
|---|---|---|---|
| `src/main.py` | 137 | **moderate** | Pipeline orchestrator — scrape, dedup, score, notify |
| `src/config.py` | 35 | simple | Pydantic settings from `.env` |
| `src/scrapers/tes.py` | 139 | **complex** | Working scraper — Next.js JSON + HTML fallback |
| `src/scrapers/teacher_horizons.py` | 170 | **complex** | Playwright SPA scraper (bypassed) |
| `src/scrapers/base.py` | 60 | **moderate** | Abstract base scraper with HTTP + BS4 |
| `src/scoring/llm_scorer.py` | 169 | **complex** | LLM scorer with multi-provider fallback |
| `src/notify/email_sender.py` | 92 | **moderate** | Email via Resend or SMTP |
| `src/notify/telegram.py` | 65 | simple | Telegram Bot API alerts |
| `src/storage/supabase_client.py` | 66 | **moderate** | Supabase CRUD + dedup logic |
| `src/scheduler/daily_run.py` | 30 | simple | APScheduler cron setup |
| `src/scrapers/linkedin.py` | 15 | simple | Placeholder — returns `[]` |
| `src/scrapers/schrole.py` | 17 | simple | Placeholder — returns `[]` |
| `src/scrapers/search_associates.py` | 17 | simple | Placeholder — returns `[]` |
| `src/scrapers/linkedin.py` | 15 | simple | Placeholder — returns `[]` |
| `.env` | 33 | simple | API keys and runtime settings |
| `data/profile.json` | 10 | simple | Candidate matching profile |
| `scripts/setup_supabase.sql` | 25 | simple | DB migration — `job_listings` + indexes |
| `AGENTS.md` | 47 | simple | Agent onboarding guide |

---

## Complexity Hotspots

These files require the most careful attention. Approach them with extra time and context.

### 🔴 `src/scoring/llm_scorer.py` (_COMPLEX_)
- **Why complex:** Multi-provider LLM probing, provider caching, and fallback to rule-based scoring.
- **Key gotchas:**
  - Providers are probed **once** at startup — if credentials change after startup, they take effect on next restart.
  - `_score_via_rules` is the safety net when all LLMs fail. It scores 30 + bonuses for subject (25), curriculum (15), country (10), and salary (10).
- **How to extend:** Add a new provider by implementing the probe + score methods, then register it in the provider list.

### 🔴 `src/scrapers/tes.py` (_COMPLEX_)
- **Why complex:** Two extraction paths (Next.js JSON + HTML fallback), curriculum inference, and relative-to-absolute URL conversion.
- **Key gotcha:** `canonicalUrl` is a relative path (`/jobs/vacancy/...`) — it's prepended with `https://www.tes.com` before being stored.
- **Fragility:** Relies on TES's Next.js page structure. If TES redesigns, `_extract_from_json` may need a rewrite.

### 🔴 `src/scrapers/teacher_horizons.py` (_COMPLEX_)
- **Why complex:** Playwright SPA scraping with Angular dynamic content.
- **Status:** **Bypassed** — detail pages require an activated teacher account. The list view experiment confirmed this limitation.
- **Learning value:** Read it to understand Playwright async patterns (page.goto, wait_for_selector, querySelectorAll) even though it's not used in production.

### 🟡 `src/main.py` (MODERATE)
- **Why moderate:** Orchestrates 4 pipeline stages and handles graceful degradation (Supabase down → in-memory fallback).
- **Key pattern:** `run_pipeline()` chains stages but each stage is isolated and can fail independently without crashing the pipeline.

### 🟡 `src/scrapers/base.py` (MODERATE)
- **Why moderate:** Abstract base with shared HTTP session, BeautifulSoup setup, and URL utilities.
- **Key pattern:** Subclasses must implement `scrape()` (enforced by `@abstractmethod`). Shared utilities like `extract_text()` and `fetch()` reduce boilerplate.

### 🟡 `src/notify/email_sender.py` (MODERATE)
- **Why moderate:** Dual-transport email (Resend API + SMTP) with HTML digest generation.

---

## Next Steps

1. **Set up your environment:**
   ```bash
   pip install -e .
   # Edit .env with your credentials
   ```

2. **Run the pipeline end-to-end:**
   ```bash
   python3 -m src.main
   ```

3. **Apply the database migration:**
   ```bash
   # Run scripts/setup_supabase.sql manually in your Supabase console
   ```

4. **Tweak your profile:**
   ```bash
   # Edit data/profile.json to match your target roles
   ```

5. **Start the scheduler:**
   ```bash
   nohup python3 -c "from src.scheduler.daily_run import start; start()" > /tmp/scheduler.log 2>&1 &
   ```

6. **Commit this guide for your team:**
   ```bash
   git add docs/PHYSICS_H_ONBOARDING.md
   git commit -m "Add onboarding guide from knowledge graph"
   ```

---

*Guide generated from the project knowledge graph (52 nodes, 84 edges, 9 layers, 10 tour steps).*

# Physics Job Hunter — Onboarding Guide

Generated from the project knowledge graph (2026-06-29).

---

## Project Overview

**Name:** physics-job-hunter  
**Description:** Automated job search pipeline for international Physics teaching roles  
**Languages:** Python, TypeScript, JavaScript, SQL, Shell, CSS  
**Frameworks:** Next.js 14, Playwright, Supabase, Pydantic, APScheduler, Tailwind CSS  

This system scrapes 10 international teaching job boards, scores listings against a candidate profile using multiple LLM providers, deep-researches high-scoring roles, and sends notifications via Telegram and Email. A parallel tutoring pathway handles inbound leads from Telegram.

---

## Architecture Layers

### 1. Configuration & Foundation
Base configuration and shared data models. All environment variables flow through `src/config.py` (Pydantic Settings loaded from `.env`). Candidate profile data lives in `data/profile.json` (teaching) and `data/profile_tutoring.json` (tutoring). Pydantic models for research briefs and agent outputs are in `src/agents/models.py`.

Key files: `src/config.py`, `src/agents/models.py`, `data/profile.json`, `data/profile_tutoring.json`, `pyproject.toml`, `package.json`

### 2. Data Storage & Persistence
Supabase-hosted PostgreSQL for production data with a SQLite fallback (`DedupStore`) for offline resilience. The `SupabaseClient` performs health checks at startup, upserts jobs into `job_listings`, and manages the `tutoring_leads` table. Database schemas are defined as SQL migration scripts.

Key files: `src/storage/supabase_client.py`, `src/storage/dedup_store.py`, `src/storage/tutoring_leads.py`, `scripts/setup_supabase.sql`

### 3. Web Scraping
A 10-scraper fleet on two base classes: `BaseScraper` (HTTP/curl_cffi) and `StealthBrowserScraper` (Playwright + Camoufox Firefox for anti-bot evasion). Active scrapers target TES (Next.js JSON), LinkedIn (curl_cffi Chrome 120 fingerprint), LibyanJobs (WordPress), Basis, Dipont, GulfTalent, TopTutorJob (Camoufox Turnstile bypass), SearchAssociates (cookie auth), and TeacherHorizons (SPA + cookie resume). A stealth verification harness (`stealth_browser.py`) validates 11/11 anti-fingerprinting tests before every session.

Key files: `src/scrapers/base.py`, `src/scrapers/browser_base.py`, `stealth_browser.py`, all scraper modules in `src/scrapers/`

### 4. AI & Scoring Engine
Multi-provider LLM scorer with a weighted registry (Groq, NVIDIA, OpenRouter, OpenCode Zen, Gemini), health state machine (ACTIVE/COOLING_DOWN/DEAD), tenacity retry, and leaky-bucket chunk pacing. A ReAct-style research agent produces StrategicBriefs for high-scoring jobs using DuckDuckGo search and Firecrawl deep scraping. A separate tutoring scorer uses heuristic rules (no LLM cost) for the tutoring pathway.

Key files: `src/scoring/llm_scorer.py`, `src/scoring/tutoring_scorer.py`, `src/agents/research_agent.py`, `src/agents/tools.py`

### 5. Notification Services
Telegram bot for job alerts (with scoring reasoning and cover letter attachments) and email via Resend API or SMTP STARTTLS. A separate inbound Telegram handler receives tutoring leads.

Key files: `src/notify/telegram.py`, `src/notify/email_sender.py`, `src/notify/telegram_inbound.py`

### 6. Pipeline Orchestration & CLI
`src/main.py` chains the full job-search pipeline: scrape → pre-filter → deduplicate → upsert → score → research → notify. APScheduler runs this periodically via `daily_run.py`. The tutoring pathway has its own scheduler (`tutoring_run.py`). Shell scripts wrap these for systemd user services.

Key files: `src/main.py`, `src/scheduler/daily_run.py`, `src/scheduler/tutoring_run.py`, `scripts/run_scheduler.py`, `scripts/run_telegram_bot.py`

### 7. Web API & Server (Next.js App Router)
Server-side API routes for jobs (paginated/filtered), pipeline control (systemd start/stop/run/status/logs), settings (thresholds and schedule), and tutoring leads CRUD. Auth guards protect mutating endpoints via admin token or localhost.

Key files: All route handlers in `web/app/api/*/route.ts`, `web/lib/api/guards.ts`, `web/lib/supabase/server.ts`

### 8. Web UI (Next.js Dashboard)
Four reactive client pages: Dashboard (`/` — job table with filters/sort/pagination/detail drawer), Pipeline Control (`/pipeline` — systemd status + logs + actions), Settings (`/settings` — threshold slider + schedule editor), and Leads (`/leads` — manual entry, status tiles, inline status-flip, expandable briefs). Zustand stores manage state; a design-system component library provides touch-friendly UI primitives.

Key files: All page components in `web/app/*/page.tsx`, UI components in `web/app/components/`, Zustand stores in `web/lib/store/`

---

## Key Concepts

- **Dual Pathway:** The system runs two independent pipelines — Pathway 1 (job search: scrape → score → research → notify) and Pathway 2 (tutoring: inbound leads → parse → score → propose → notify).
- **Stealth Browser:** Scrapers behind Cloudflare Turnstile use Camoufox, a hardened Firefox build with anti-fingerprint measures. Enabled via `CAMOUFOX_ENABLED=1` in `.env`. All 11 Intoli/Sannysoft tests must PASS before scraping (verified by `stealth_browser.py`).
- **Weighted LLM Provider Registry:** Five LLM providers compete to score jobs. Each has a weight, health state, and model rotation. Failures cascade to the next provider; all-fail falls back to rule-based scoring (base 30).
- **Heuristic Pre-filter:** `filter_relevant_jobs()` drops jobs whose title/subject don't match physics/maths/science/IGCSE/A-Level keywords before any LLM cost is incurred.
- **SQLite Fallback:** Every Supabase operation falls through to `DedupStore` (SQLite) on HTTP errors — the pipeline never crashes on storage failures.
- **Camoufox Kill-Switch:** The browser binary is never auto-fetched mid-pipeline. `CAMOUFOX_ENABLED` defaults to `False`; operator explicitly opts in after provisioning the binary.
- **pydantic-settings for Config:** All `.env` values are loaded into `src.config.settings` via pydantic-settings. Scrapers reference `settings.camoufox_enabled` (not `os.getenv`) — ensuring consistent config access.
- **Cover Letters:** Generated for every job scored ≥ threshold, using strategic briefs from the research agent for institution-aware writing.

---

## Guided Tour

### 1. Project Overview & Dual-Pathway Architecture
Start with `readme.md` to understand the project purpose. Read `docs/dual-pathway.md` to learn how the job-search pipeline (Pathway 1) and tutoring lead system (Pathway 2) work in parallel. `AGENTS.md` is the operational reference.

### 2. Configuration Foundation & Candidate Profiles
All configuration flows from `src/config.py` (Pydantic Settings loaded from `.env`). Candidate profile data in `data/profile.json` and `data/profile_tutoring.json` drives scoring relevance and proposal personalization.

### 3. Pipeline Orchestrator (Pathway 1 Entry Point)
`src/main.py` runs the full sequence: scrape all job boards → heuristic pre-filter → deduplicate → upsert to Supabase → LLM-score → deep-research high-scoring jobs → notify via Telegram and Email.

### 4. Web Scraping Fleet
10 scrapers on two base classes: `BaseScraper` (HTTP) and `StealthBrowserScraper` (Playwright/Camoufox). Active scrapers include TES (Next.js JSON), LinkedIn (curl_cffi), LibyanJobs (WordPress), Basis, Dipont, GulfTalent, and stealth-browser scrapers for TopTutorJob, SearchAssociates, and TeacherHorizons.

### 5. Stealth Browser Verification Harness
`stealth_browser.py` validates Camoufox fingerprint against bot.sannysoft.com using zstd route-injection. All 11/11 tests must PASS before scraping is safe.

### 6. Data Storage & Deduplication
Jobs upserted into Supabase (`job_listings` table) via `SupabaseClient`, with SQLite `DedupStore` as fallback. Schema defined in `scripts/setup_supabase.sql`.

### 7. LLM Scoring Engine
Multi-provider `LLMScorer` with weighted provider registry, model rotation, health state machine, and rule-based fallback. Rubric: Curriculum 0-30, Subject 0-25, Location 0-20, Salary 0-15, Housing 0-10.

### 8. Deep Research Agent
ReAct-style agent produces `StrategicBrief` (institution_facts, strategic_alignment, recommended_angle) for jobs scored ≥ 60, using DuckDuckGo search and Firecrawl deep scraping.

### 9. Notification Services (Pathway 1 Output)
Jobs ≥ threshold notified via Telegram (with scoring reasoning + cover letter) and Email (Resend API or SMTP).

### 10. Tutoring Lead Pathway (Pathway 2)
Independent pathway: inbound Telegram messages → parse via LLM → score heuristically → generate proposal → notify back.

### 11. CLI & Scheduler Entry Points
Three entry points: `scripts/run_scheduler.py` (APScheduler), `scripts/run_telegram_bot.py` (inbound polling), and `python3 -m src.main` (single run).

### 12. Web Dashboard & Front-End
Next.js 14 dashboard with four pages: Dashboard (jobs table), Pipeline Control (systemd controls), Settings (thresholds/schedule), and Leads (tutoring CRM). Zustand state management, Tailwind CSS design system.

---

## File Map (by Layer)

### Configuration & Foundation
| File | Purpose |
|------|---------|
| `src/config.py` | Pydantic Settings loaded from `.env` — API keys, thresholds, feature flags |
| `src/agents/models.py` | Pydantic models for TutoringBrief and StrategicBrief |
| `data/profile.json` | Candidate profile — subjects, curricula, target countries |
| `data/profile_tutoring.json` | Tutoring-specific candidate profile |
| `pyproject.toml` | Python project metadata and dependencies |

### Data Storage
| File | Purpose |
|------|---------|
| `src/storage/supabase_client.py` | Supabase CRUD for `job_listings` table with health checks |
| `src/storage/dedup_store.py` | SQLite deduplication store (fallback on HTTP errors) |
| `src/storage/tutoring_leads.py` | Supabase CRUD for `tutoring_leads` table |
| `scripts/setup_supabase.sql` | Database schema migration for job_listings |

### Scraping
| File | Purpose |
|------|---------|
| `src/scrapers/base.py` | `BaseScraper` abstract base class (HTTP) |
| `src/scrapers/browser_base.py` | `StealthBrowserScraper` with Playwright/Camoufox automation |
| `src/scrapers/tes.py` | TES.com scraper (Next.js JSON + HTML fallback) |
| `src/scrapers/linkedin.py` | LinkedIn scraper (curl_cffi Chrome 120 fingerprint) |
| `src/scrapers/libyan_jobs.py` | LibyanJobs WordPress scraper |
| `src/scrapers/basis.py` | Basis International Schools scraper |
| `src/scrapers/dipont.py` | Dipont Education scraper |
| `src/scrapers/gulftalent.py` | GulfTalent corporate job board |
| `src/scrapers/toptutorjob.py` | TopTutorJob (Camoufox Turnstile bypass) |
| `src/scrapers/search_associates.py` | Search Associates (Camoufox + cookie auth) |
| `src/scrapers/teacher_horizons.py` | Teacher Horizons (Camoufox SPA + cookie resume) |
| `stealth_browser.py` | Pre-flight fingerprint verification harness |

### AI & Scoring
| File | Purpose |
|------|---------|
| `src/scoring/llm_scorer.py` | Multi-provider LLM scorer with weighted registry, retry, health states |
| `src/scoring/tutoring_scorer.py` | Heuristic tutoring lead scorer (no LLM) |
| `src/agents/research_agent.py` | ReAct-style research agent with web_search/deep_scrape tools |
| `src/agents/tools.py` | DuckDuckGo search and Firecrawl/HTTP scrape implementations |
| `src/agents/tutoring_parser.py` | LLM-powered tutoring lead parser |
| `src/generators/tutoring_proposal.py` | Tutoring proposal generator (template + optional LLM) |

### Notification
| File | Purpose |
|------|---------|
| `src/notify/telegram.py` | Telegram bot alert sender |
| `src/notify/telegram_inbound.py` | Inbound Telegram message handler for tutoring leads |
| `src/notify/email_sender.py` | Email via Resend API or SMTP STARTTLS |

### Pipeline Orchestration
| File | Purpose |
|------|---------|
| `src/main.py` | Pipeline orchestrator — chains scrape, dedup, score, notify |
| `src/scheduler/daily_run.py` | APScheduler for periodic job pipeline execution |
| `src/scheduler/tutoring_run.py` | APScheduler for periodic tutoring pipeline tick |
| `scripts/run_scheduler.py` | CLI entry point for APScheduler |
| `scripts/run_telegram_bot.py` | CLI entry point for Telegram bot polling |

### Web API
| File | Purpose |
|------|---------|
| `web/app/api/jobs/route.ts` | Paginated, filtered jobs from Supabase |
| `web/app/api/jobs/options/route.ts` | Distinct sources & countries for filter dropdowns |
| `web/app/api/pipeline/status/route.ts` | systemd service state probe |
| `web/app/api/pipeline/start|stop|run/route.ts` | Mutating pipeline actions |
| `web/app/api/pipeline/logs/route.ts` | Recent journalctl log lines |
| `web/app/api/settings/route.ts` | Advisory settings read/write |
| `web/app/api/leads/*/route.ts` | Tutoring leads CRUD |
| `web/lib/api/guards.ts` | Auth guard (admin token or localhost) |
| `web/lib/supabase/server.ts` | Server-only Supabase client |

### Web UI
| File | Purpose |
|------|---------|
| `web/app/page.tsx` | Dashboard — job table with filters, skeletons, pagination |
| `web/app/pipeline/page.tsx` | Pipeline control — status, actions, logs viewer |
| `web/app/settings/page.tsx` | Settings — threshold slider, schedule editor |
| `web/app/leads/page.tsx` | Leads management — entry form, status tiles, table |
| `web/app/components/jobs/JobTable.tsx` | Sortable job table with detail drawer |
| `web/app/components/layout/Sidebar.tsx` | Responsive nav (desktop sidebar / mobile tab bar) |
| `web/lib/store/jobs.ts` | Zustand store for dashboard jobs state |

---

## Complexity Hotspots

These areas have the highest complexity in the codebase — approach with care:

| Component | Complexity | Description |
|-----------|-----------|-------------|
| `JobTable.tsx` | **complex** | Sortable table with row selection, loading/error/empty states, pagination, lazy-loaded detail drawer |
| `LeadsPage` (`web/app/leads/page.tsx`) | **complex** | Status tiles, manual entry form, filtered table, inline status-flip, expandable brief rows |
| `PipelinePage` (`web/app/pipeline/page.tsx`) | **complex** | Status polling, start/stop/run actions, admin token input, live journalctl log viewer |

These three UI components handle multiple concurrent concerns (state management, async data fetching, user interaction, accessibility). The rest of the codebase is moderate complexity — individual scrapers, storage layers, and API routes follow consistent patterns.

---

## Getting Started

1. Clone the repo and install dependencies (`pip install -e .` for Python, `pnpm install` for web)
2. Copy `.env.example` to `.env` and populate API keys
3. Run `python -m camoufox fetch` to provision the stealth browser binary
4. Run `python3 stealth_browser.py` to verify all 11/11 fingerprint tests PASS
5. Run `python3 -m src.main` to execute the full pipeline once
6. Set `CAMOUFOX_ENABLED=1` in `.env` to activate stealth scrapers
7. For production: enable systemd services (`systemctl --user enable physics-job-hunter.service`)

See `AGENTS.md` for the complete operational reference.

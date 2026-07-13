# physics-job-hunter — Onboarding Guide

*Generated from the project knowledge graph (.understand-anything/knowledge-graph.json, snapshot 2026-06-29). For the newer campaign feature (added 2026-07-13) see `AGENTS.md` → "Campaign Mode".*

## Project Overview

| | |
|---|---|
| **Name** | physics-job-hunter |
| **Description** | Automated job search pipeline for international Physics teaching roles |
| **Languages** | Python, TypeScript, JavaScript, SQL, Shell, CSS, JSON, Markdown, TOML, YAML |
| **Frameworks** | Next.js, Playwright, Supabase, Pydantic, APScheduler, Tailwind CSS |

The system runs as a **dual-pathway** product:
- **Pathway 1 — Job Search**: scrape international teaching job boards → heuristic pre-filter → LLM score → deep research → notify via Telegram/Email.
- **Pathway 2 — Tutoring Leads**: inbound Telegram messages → parse/score via LLM → generate proposals → notify back.

## Architecture Layers

1. **Configuration & Foundation** — Pydantic settings (`src/config.py`), shared models (`src/agents/models.py`), profile data, and all build configs (pyproject.toml, package.json, tsconfig, etc.).
2. **Data Storage & Persistence** — Supabase CRUD clients, SQLite `DedupStore` fallback, table definitions, and SQL migrations.
3. **Web Scraping** — 10-scraper fleet on `BaseScraper`/`StealthBrowserScraper` (Playwright/Camoufox) + the stealth-browser verification harness.
4. **AI & Scoring Engine** — multi-provider `LLMScorer`, tutoring heuristic scorer, ReAct `ResearchAgent` with tools, tutoring parser, proposal generator.
5. **Notification Services** — Telegram alert sender, inbound Telegram handler, email sender (Resend/SMTP).
6. **Pipeline Orchestration & CLI** — `src/main.py` orchestrator, APScheduler runs, CLI/systemd scripts.
7. **Web API & Server** — Next.js App Router route handlers (jobs, leads, pipeline control, settings), server-only Supabase client, auth guards.
8. **Web UI** — Next.js pages, UI component library, Zustand stores, types, CSS.
9. **Tests** — smoke tests for tutoring pipeline and Gemini scorer.
10. **Documentation & Meta** — AGENTS.md, README, dual-pathway docs, interview Q&A.

## Key Concepts

- **Dual-pathway design** — job-search and tutoring pipelines run independently but share storage, scoring, and notification primitives.
- **Heuristic pre-filter with hard guard** — `filter_relevant_jobs()` drops non-physics/non-teacher listings; the hard `"physics" in combined` check is the non-negotiable safety rail.
- **Multi-provider LLM scorer** — weighted provider registry (OpenCode Zen/NVIDIA/Groq/OpenRouter/Gemini per `AGENTS.md`) with model rotation, tenacity retry, a health state machine (ACTIVE→COOLING_DOWN→DEAD), leaky-bucket chunk pacing, and a rule-based fallback (base 30) when all LLMs fail.
- **Stealth scraping + pre-flight** — Camoufox fingerprinting for anti-bot evasion; `stealth_browser.py` must pass 11 Intoli/Sannysoft tests before any scrape session.
- **ReAct research agent** — high-scoring jobs get deep research (DuckDuckGo + Firecrawl/HTTP) producing a `StrategicBrief` that feeds cover letters; degrades gracefully via `fallback()`.
- **Storage resilience** — every `SupabaseClient` call falls through to `DedupStore` (SQLite) on `httpx.HTTPError`.
- **Campaign mode (added 2026-07-13)** — `CAMPAIGN=pe_central_europe` re-targets the pipeline via `data/campaign_<id>.json` using a two-lane model (Edexcel-only primary + Cambridge/IB `curriculum_adjacent` at 0.6× boost). Documented in `AGENTS.md`.

## Guided Tour (recommended learning path)

1. **Overview & dual-pathway** — read `README.md`, `docs/dual-pathway.md`, `AGENTS.md`.
2. **Config foundation** — `src/config.py` (Pydantic `.env` settings), `data/profile.json` / `data/profile_tutoring.json`, `pyproject.toml`.
3. **Pipeline orchestrator** — `src/main.py` + `src/scheduler/daily_run.py` (the heart of Pathway 1).
4. **Scraping fleet** — `BaseScraper`, `StealthBrowserScraper`, TES, LinkedIn, LibyanJobs, Basis, Dipont, GulfTalent.
5. **Stealth harness** — `stealth_browser.py` + the Camoufox scrapers (TopTutorJob, SearchAssociates, Teacher Horizons).
6. **Storage & dedup** — `SupabaseClient`, `DedupStore`, `scripts/setup_supabase.sql`.
7. **LLM scoring** — `src/scoring/llm_scorer.py` (rubric, provider registry, health machine).
8. **Research agent** — `research_agent.py`, `models.py`, `tools.py`.
9. **Notifications** — `telegram.py`, `email_sender.py`.
10. **Tutoring pathway** — `telegram_inbound.py`, `tutoring_run.py`, `tutoring_parser.py`, `tutoring_scorer.py`, `tutoring_proposal.py`, `tutoring_leads.py`.
11. **CLI & scheduler** — `run_scheduler.py`, `run_telegram_bot.py`, `.sh` wrappers for systemd.
12. **Web dashboard** — Next.js pages (`/`, `/pipeline`, `/settings`, `/leads`), Zustand stores, API routes.

## File Map

**Configuration & Foundation**
- `src/config.py` — Pydantic Settings loaded from `.env` (incl. `CAMPAIGN`, `CAMOUFOX_ENABLED`, thresholds).
- `src/agents/models.py` — Pydantic models: `StrategicBrief` and `TutoringBrief`.
- `data/profile.json` / `data/profile_tutoring.json` — candidate profiles driving relevance and proposal personalization.

**Data Storage & Persistence**
- `src/storage/supabase_client.py` — Supabase CRUD for `job_listings`; falls through to `DedupStore` on HTTP error.
- `src/storage/dedup_store.py` — SQLite deduplication store.
- `src/storage/tutoring_leads.py` — Supabase CRUD for `tutoring_leads`.
- `scripts/setup_supabase.sql` — `job_listings` schema (apply manually).

**Web Scraping**
- `src/scrapers/base.py` — `BaseScraper` ABC.
- `src/scrapers/browser_base.py` — `StealthBrowserScraper` (Playwright/Camoufox automation).
- `src/scrapers/tes.py` — TES.com (Next.js JSON + HTML fallback).
- `src/scrapers/linkedin.py` — LinkedIn (curl_cffi Chrome 120 fingerprint).
- `src/scrapers/libyan_jobs.py`, `basis.py`, `dipont.py`, `gulftalent.py` — additional board scrapers.
- `stealth_browser.py` — pre-flight Camoufox fingerprint verification (11 Sannysoft tests).

**AI & Scoring Engine**
- `src/scoring/llm_scorer.py` — multi-provider LLM scorer; weighted registry, health state machine, rule fallback. *(core, high-importance)*
- `src/agents/research_agent.py` — ReAct research agent with `web_search`/`deep_scrape`.
- `src/agents/tools.py` — DuckDuckGo web search + Firecrawl/HTTP deep scrape.
- `src/scoring/tutoring_scorer.py` — heuristic tutoring lead scorer (no LLM).
- `src/agents/tutoring_parser.py` — LLM tutoring lead parser.
- `src/generators/tutoring_proposal.py` — tutoring proposal generator.
- `src/generators/cover_letter.py` — *(added 2026-07-13; not in graph snapshot)* campaign-aware cover letters.

**Notification Services**
- `src/notify/telegram.py` — Telegram alert sender (with scoring reasoning + cover-letter attachments).
- `src/notify/email_sender.py` — Email via Resend/SMTP.
- `src/notify/telegram_inbound.py` — inbound Telegram handler for tutoring leads.

**Pipeline Orchestration & CLI**
- `src/main.py` — orchestrator: scrape → pre-filter → dedup → upsert → score → research → notify. *(core, high-importance)*
- `src/scheduler/daily_run.py` — APScheduler for daily job pipeline.
- `src/scheduler/tutoring_run.py` — APScheduler for tutoring tick.
- `scripts/run_scheduler.py`, `run_telegram_bot.py`, `.sh` wrappers — entry points / systemd units.

**Web API & Server**
- `web/app/api/jobs/route.ts`, `leads/*`, `pipeline/*`, `settings/route.ts` — route handlers.
- `web/lib/supabase/server.ts` — server-only Supabase client.
- `web/lib/api/guards.ts` — auth guard for mutating pipeline routes.

**Web UI**
- `web/app/page.tsx` (dashboard), `pipeline/page.tsx` (control), `settings/page.tsx`, `leads/page.tsx`.
- `web/app/components/jobs/*` — `JobTable`, `JobDetailDrawer`, filters, pagination, `ScoreBadge`.
- `web/app/components/ui/*` — `Button`, `Card`, `Slider`, `Toggle`, `StatusBadge`, `Toast`, etc. (44px tap targets).
- `web/lib/store/jobs.ts` — Zustand store for dashboard state.

## Complexity Hotspots

The graph rates most file-level nodes **moderate**; only **3 are `complex`**, all on the Web UI:

| File | Why it's hot |
|---|---|
| `web/app/components/jobs/JobTable.tsx` | Responsive sortable table with row selection, loading/error/empty states, pagination, lazy detail drawer. |
| `web/app/leads/page.tsx` | Tutoring leads mgmt: status tiles, manual entry form, filter bar, paginated table, inline status-flip, expandable brief. |
| `web/app/pipeline/page.tsx` | systemd status polling, start/stop/run actions, admin-token input, live journalctl log viewer. |

**Backend caution (rated moderate but high-blast-radius):**
- `src/scoring/llm_scorer.py` — provider registry, model rotation, tenacity, health machine; a regression here silently degrades every score.
- `src/main.py` — the orchestrator; the pre-filter (`_is_relevant`) hard `physics` guard must never be weakened.
- `src/storage/supabase_client.py` — every method must preserve the `DedupStore` fallback path.

**Snapshot gap:** the graph predates `src/campaign.py`, `data/campaign_pe_central_europe.json`, and the `tag_campaign()` addition to `src/main.py`. Those are `moderate`-complexity but central to the new campaign feature — read `AGENTS.md` "Campaign Mode" for them.

---

**Note:** This guide reflects the 2026-06-29 knowledge-graph snapshot and does not include the 2026-07-13 campaign changes (covered in `AGENTS.md`).

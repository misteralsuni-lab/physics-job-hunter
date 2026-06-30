# Physics Job Hunter — Agent Guide

## Entrypoints

- **CLI**: `physics-job-hunter` (needs `pip install -e .`) or `python3 -m src.main`
- **Scheduler (systemd user service)**: `systemctl --user start physics-job-hunter.service` (APScheduler via systemd, survives reboot via `loginctl enable-linger $USER`)
- **Stop**: `systemctl --user stop physics-job-hunter.service`
- **Status**: `systemctl --user status physics-job-hunter.service`
- **Live logs**: `journalctl --user -u physics-job-hunter.service -f`
- **Disable auto-start**: `systemctl --user disable physics-job-hunter.service`
- **Tutoring Telegram bot (inbound)**: `systemctl --user start physics-job-hunter-bot.service`. Long-polls in a separate process; independent lifecycle from the scheduler.
- **Bot logs**: `journalctl --user -u physics-job-hunter-bot.service -f`
- **Front-end dashboard** at `web/` (Next.js 14 App Router, TypeScript, Tailwind, Zustand) — see Front End section below.
- Legacy nohup command (if systemd unavailable): `nohup python3 -c "from src.scheduler.daily_run import start; start()" > /tmp/scheduler.log 2>&1 &`

## Pipeline (`src/main.py:run_pipeline()`)

1. **Scrape** — 10-scraper fleet registered in `src/main.py:run_scrapers()`:
   - `TESScraper` (works)
   - `LibyanJobsScraper` (works)
   - `LinkedInScraper` (`curl_cffi` Chrome 120 fingerprint + hard `physics` pre-filter)
   - `BasisScraper` (HTML selector probing)
   - `DipontScraper` (`/careers/independent-schools-jobs/`)
   - `TopTutorJobScraper` (Camoufox — Cloudflare Turnstile bypass; dormant unless `CAMOUFOX_ENABLED=1`)
   - `SearchAssociatesScraper` (Camoufox + cookie-resume auth — dormant unless `SA_USERNAME/SA_PASSWORD` set)
   - `TeacherHorizonsScraper` (Camoufox + cookie-resume auth — dormant unless `TH_EMAIL/TH_PASSWORD` set)
   - `GulfTalentScraper` (BaseScraper, no auth — corporate Gulf board; near-zero IGCSE/A-Level yield by design)
   - `SchroleScraper` (browser lane — awaiting credentials)
0. **Pre-flight (stealth verification)** — Before every scrape session, run `python3 stealth_browser.py`. It tests the Camoufox fingerprint against bot.sannysoft.com (the Intoli test suite). **If > 0 tests show FAIL, do not scrape** — investigate and fix the regression first. Any single failure means the fingerprint is compromised and scraping will likely hit CAPTCHAs/403s. See Stealth Browser Harness section below for details.
1. **Heuristic pre-filter** — `filter_relevant_jobs()` drops jobs whose title/subject don't match physics/maths/science/IGCSE/A-Level keywords. The hard `physics in (title | subject | curriculum)` is the primary guard. Substring matchers block non-teacher roles (2026-06-29 expansion): technicians ("technician", "lab technician", "science technician", "stem technician"), management ("director of", "head of department", "head of physics", "manager", "coordinator", "administrator"), higher-ed ("lecturer", "university", "researcher", "postdoc", "professor"), lab roles ("physics lab", "physics laboratory"). Blocked jobs never reach the LLM scorer and never trigger Telegram notifications.
3. **Deduplicate** — skip URLs already in Supabase (falls back to `DedupStore` SQLite at `data/dedup.db`)
4. **Upsert** — `SupabaseClient.upsert_jobs()` into `job_listings` table; coerces empty `closing_date=""` → `None`
5. **Score** — `LLMScorer` with Weighted Provider Registry: validates providers at startup via `validate_provider_configs()`, removes dead ones, queries survivors in weight order. Active providers (compare matrix, 2026-06-29 rerun): **OpenCode Zen** (weight 40, primary — `deepseek-v4-flash-free` free-tier via OpenCode Zen catalogue) → **NVIDIA** (30, primary model `openai/gpt-oss-120b` clean JSON, backup `nvidia/nemotron-3-super-120b-a12b` thinking-mode; 2026-06-30 swap puts GPT-OSS-120B first because Nemotron burned most of *its* completion budget on `reasoning_content` chain-of-thought — see NVIDIA reasoning-headroom fix below) → **Groq** (20, fastest when ACTIVE — `meta-llama/llama-4-scout-17b-16e-instruct` per `.env`) → **OpenRouter** (15, often cool-down rate-limited) → **Gemini** (10). `SCORER_PROVIDER`/`SCORER_FALLBACK` env vars are **not consumed** — provider selection = API key presence + `PROVIDER_WEIGHTS`. If all LLM providers fail, falls back to rule-based scoring (base 30). LLM rubric: Curriculum 0-30, Subject 0-25, Location 0-20, Salary 0-15, Housing 0-10 (max 100). `visa_sponsorship` and `deadline_urgency` removed. **Five-way comparison pass** (2026-06-29 live test against a canonical IGCSE-Physics job): PASS-1 OpenCode-primary → 90/18s, PASS-2 NVIDIA-primary → 95/23s, PASS-3 Gemini-primary → 90/16s, PASS-4 NVIDIA+OpenCode dual → 90/21s, PASS-5 ORIGINAL groq-primary (pre-ship) → 90/12.9s. Recommendation: **stay with PASS-1 OpenCode-primary** for steady-state — only 7s slower than Groq-primary when Groq is hot, but doesn't burn credits.
6. **Research** — `ResearchAgent` produces a `StrategicBrief` for every job scored ≥ `RESEARCH_SCORE_THRESHOLD` (default 60). Uses a ReAct-style LLM loop with two tools: `web_search` (DuckDuckGo) and `deep_scrape` (Firecrawl or HTTP fallback). The brief feeds `institution_facts`, `strategic_alignment`, and `recommended_angle` into the cover letter generator. Falls back to `StrategicBrief.fallback()` if research fails.
7. **Notify** — Telegram (`src/notify/telegram.py`) + Email (`src/notify/email_sender.py`, Resend or SMTP) for jobs scored ≥ `settings.notify_score_threshold` (default 50, configurable via `NOTIFY_SCORE_THRESHOLD` in `.env`)

## Important gotchas

- **Python >= 3.12** required
- **`.env` has live API keys** — do not modify or commit changes
- **`tests/test_gemini_smoke.py`** — smoke test for LLM scorer; run via `python3 tests/test_gemini_smoke.py`
- **`scripts/test_gemini.py`** — standalone Gemini key validation
- **No lint, typecheck, formatter, or pre-commit config** for Python — nothing to run
- **Web front-end** has `npm run typecheck` (tsc --noEmit) and `npm run lint` (next lint). Always run both before committing web changes. Use `pnpm` (v11.4.0) — `pnpm install`; if building fails with `ERR_PNPM_IGNORED_BUILDS`, create `.pnpm-approve-builds.json` with `{"unrs-resolver": true}` or run `pnpm approve-builds`
- **`src/extractors/` is empty** — planned but not implemented
- **`scripts/setup_supabase.sql`** — schema for `job_listings` table; must be applied manually to Supabase before first run (schema wiped on project pause/resume)
- **Frontend audit (2026-06-27)** — three bugs found and fixed during QA:
  - `web/app/components/ui/Toast.tsx`: `id: nextId++` inside the Zustand `set` updater — React strict-mode double-invocation produced out-of-sequence IDs. Increment moved out of the updater.
  - `web/app/settings/page.tsx`: regex `^\d{2}:\d{2}$` accepted impossible clocks (`25:99`). Added `isValidClockTime()` helper (0-23 hours, 0-59 minutes).
  - `web/app/pipeline/page.tsx`: deferred `setTimeout(..., 500)` `setStatus` could call setState on unmounted component. Added `mountedRef` flag flipped at unmount.
- **Stealth browser kill-switch** — `CAMOUFOX_ENABLED` in `.env` controls the browser fleet.  Read via `src/config.py:Settings.camoufox_enabled` (pydantic-settings `bool`, default `False`).  All scraper checks use `settings.camoufox_enabled` — NOT `os.getenv()` — so `.env` must be loaded via pydantic-settings (which happens automatically at `from src.config import settings`).  Default `False` keeps the Camoufox Firefox binary (1.3 GB unpacked, version 135.0.1-beta.24) **never auto-fetched** mid-pipeline.  Operator opts in with `CAMOUFOX_ENABLED=1` once `python -m camoufox fetch` has been run manually.
- **Stealth browser verification harness** — `stealth_browser.py` at project root. Run before every scrape session. Validates 11 Intoli/Sannysoft tests via route-intercepted HTML injection (zstd decompression → `<script>` injection → fulfill). All 11 tests must show PASS (CSS class `passed` on DOM elements) or the scrape session is unsafe. See Stealth Browser Harness section below.
- **Stealth browser route-injection pattern** — `bot.sannysoft.com` serves HTML with `Content-Encoding: zstd`. Camoufox's `add_init_script()` runs too late for inline page scripts. The harness uses `page.route()` interception: `route.fetch()`, `zstandard.ZstdDecompressor().stream_reader()`, inject a `<script>` before the first page `<script>`, `route.fulfill()`. Only the `window.chrome` mock + `navigator.permissions.query` override are injected — `navigator.webdriver`, `navigator.plugins`, and `navigator.languages` are already handled natively by Camoufox and must NOT be re-patched (defining them as own properties makes `_.has()` detect them).
- **Stealth browser Camoufox cleanup** — Camoufox's background fingerprinting monitor periodically resets spoofed properties. After page load completes, `window.chrome` is deleted. This is normal and does not affect test results (the test evaluates before cleanup). When debugging, check the DOM element's CSS class (`passed`/`failed`), not `!!window.chrome` at eval time.
- **Playwright Node.js driver patch** — the `.venv` Playwright driver (`coreBundle.js`) has been patched at two locations to handle `pageError.location` being `undefined` (Firefox crash on sannysoft page errors). The patch is permanent in the `.venv` but will be lost on `pip install --upgrade playwright`. If Camoufox crashes with a Firefox content-process error, re-apply the patch.
- **zstandard dependency** — `zstandard` (python package) is required for stealth browser route interception (decompressing zstd-encoded HTML). Installed in `.venv` via `pip install zstandard`.
- **`TeacherHorizonsScraper` (Phase 2)** — formerly a Playwright stub; now rebuilt on `StealthBrowserScraper` with cookie resume after recon confirmed no anonymous path exists (`/jobs` = Angular shell, `/th/api/jobs` = 401).  Read `docs/ONBOARDING.md` for the full recon table.
- **`TopTutorJobScraper` selector budget (2026-06-29)** — passing a fixed CSS selector to Playwright's `wait_for_selector` traps the pipeline when the site reorganises its DOM. A previous `article.job` sentinel burned 45 seconds/page × 3 pages = 2+ minutes of pipeline wall-clock returning zero rows. Now: the wait sentinel is `_JOB_CONTAINER_SELECTORS[0]` with `timeout_ms=8000` hard-cap, and the downstream `_extract_jobs` walks the candidate-list top-to-bottom. To fix DOM drift in future, open `https://www.toptutorjob.com/physics-jobs/` in a normal browser and copy the new card selector into `_JOB_CONTAINER_SELECTORS` (line ~43).
- **`StealthBrowserScraper` Screen type fix (2026-06-29)** — `_pick_screen()` returned a `tuple[int,int]` but `browserforge` expects a `Screen` dataclass (with `is_set()` method).  This caused `AttributeError: 'tuple' object has no attribute 'is_set'` on stealth launch.  Also, using `Screen(min_width=w, max_width=w, ...)` was too restrictive for the header generator — fixed by removing the `screen` param entirely from `_browser_session()` and the standalone `Camoufox(...)` calls in `teacher_horizons.py` and `search_associates.py`, letting Camoufox use its own default screen fingerprinting.
- **GeoIP database** — `geoip=True` (default) triggers a 66MB GeoIP download on first Camoufox launch.  Cached at `~/.cache/camoufox/` for subsequent runs.  First run after clearing cache will be slow.  Set `geoip=False` (via `CAMOUFOX_GEOIP` env) to skip if geolocation anchoring isn't needed.
- **`GulfTalentScraper` (2026-06-28)** — corporate Gulf employment board (`/api/jobs/search`, no auth).  After a second probe (GCC `country` mask `10111111000000` + combined subject + curriculum phrase), the search DOES return real teaching gigs in UAE/Saudi/Qatar/Bahrain/Oman/Kuwait — however, the keyword matcher is loose full-text and primary/homeroom dominates.  Scraper now defaults to `search_keyword=physics teacher IGCSE` and similar combined phrases + the GCC bitmask.  Expected IGCSE secondary match rate is **sparse but real**; corporate-Gulf pollution reduced vs. the unfiltered global search.  Overridable via `GT_COUNTRY_MASK` env var (set to empty string for unfiltered global search).
- **`health_check()` on `SupabaseClient`** — probes with `SELECT id LIMIT 1` at startup; if it fails, raises `httpx.HTTPError` immediately so the pipeline falls through to in-memory scoring with local SQLite
- **`update_score()` and `mark_notified()` filter by `url` column** — NOT by `id`. Callers pass `_job_key(job)` which returns `job["id"]` (UUID) or falls back to `job["url"]`. `update_score` was broken (filtered `id=url`, silent no-op)
- **`import re` must be in `src/scoring/llm_scorer.py`** — `_strip_llm_wrappers()` uses `re.sub`. If the import is missing, every provider validation fails silently (caught by `except Exception`). All providers return HTTP 200 but JSON extraction crashes with `NameError`
- **`upsert_jobs()` coerces empty `closing_date=""` → `None`** — PostgreSQL refuses `""` for `date` type
- **`get_recent()` ignores its `days` parameter** — always queries `>= date.today()`. Minor bug, but affects any code expecting a sliding window
- **Provider validation** — `validate_provider_configs()` has a 2-minute deadline; probes with a real scoring prompt. On 401/404 logs `[CONFIG_INVALID]` and removes provider. On any other failure (including extraction crash) logs `[CONFIG_INVALID]`
- **Health state machine** — `ProviderRegistry` tracks ACTIVE → COOLING_DOWN (300s canary) → DEAD (3 consecutive cooldown failures). Dead providers stay removed for the session
- **Intra-provider model rotation** — Groq: 1 model (`settings.groq_model`). NVIDIA: `openai/gpt-oss-120b` (primary clean JSON, ~10s on real scoring prompt) → `nvidia/nemotron-3-super-120b-a12b` (backup, thinking-mode + 90s timeout — operator swap dated **2026-06-30**; previously Llama-3.1 70B/8B then Nemotron-3-Super primary). OpenCode Zen: **`["deepseek-v4-flash-free"]`** — the free tier via OpenCode Zen catalogue (added 2026-06-28 after the paid `deepseek-v4-flash` was blocked by 401 CreditsError; the scorer calls this with `max_tokens=4096` instead of the default 800 because reasoning-mode burns most of the budget on chain-of-thought, leaving 0 tokens for the visible answer at 800). OpenRouter/Gemini: 1 model each
- **NVIDIA reasoning-headroom fix (2026-06-29)** — both NVIDIA chain members (`nvidia/nemotron-3-super-120b-a12b` and `openai/gpt-oss-120b`) put a meaningful fraction of the completion budget into `reasoning_content` chain-of-thought. The default `max_tokens=800` returns truncated (or empty) `content` for both, which is why the previous prompt failed _extract_json. The fix shipped 2026-06-29: `_call_nvidia` in `src/scoring/llm_scorer.py:699` now passes `max_tokens=4096`. Verified the same fix works for both models in `tutorials/test_nvidia_fix.py` — both models now hit `finish_reason=stop`, emit valid JSON, and parse cleanly via `_extract_json`. Cost: ~750 completion tokens per job (650 reasoning + 100 answer), <1 cent per job on the free NVIDIA catalogue tier. The pre-existing `NVIDIA_Nemotron-3-Super_hidden-reasoning issue` gotcha (older comment in the gotcha log) is no longer applicable once this fix lands.
- **Tenacity retry** — `tenacity.Retrying` with `wait_random_exponential(multiplier=1, max=60)`, 3 attempts per model before rotating or moving to next provider. Format: log every attempt as `[PIPELINE] Provider: groq | Model: ... | Result: Success/Fail | Attempt: N`
- **Leaky-bucket pacing** — `batch_score()` splits into chunks of `MAX_PER_CHUNK=5` with `CHUNK_DELAY=20s`. Total pipeline ~2.5min for 20 jobs
- **Cover letter `_resolve_provider()`** — probes OpenCode Zen → NVIDIA → Groq → OpenRouter → Gemini (**2026-06-29 reorder**: was previously Groq-primary; OpenCode Zen is the primary cascade-wide so the free deepseek-v4-flash-free is the default across scorer, research, and cover letters, with NVIDIA as the high-quality 200K-context fallback, Groq as the fastest paid fallback once healthy). `time.sleep(5)` between calls in evaluation loop to avoid 429s. Files tagged `__LLM` (AI) or `__fallback` (template). Cover letters consume ``research_brief`` dict from the job for institution-aware writing.
- **Research Agent cascade** — same priority (OpenCode Zen → NVIDIA → Groq → OpenRouter → Gemini), enforced at the `ResearchAgent._providers()` level. The agent fires the cascade through the same lookup. OpenCode Zen is `[deepseek-v4-flash-free]` and benefits from the same `max_tokens=4096` reasoning-headroom already wired into `LLMScorer._call_opencode_zen`. The research-agent loop has no separate validator — it relies on whichever provider surfaces a non-empty string first.
- **TES scraper** — extracts from `__NEXT_DATA__` JSON (catches `AttributeError` for null fields); falls back to HTML parsing. Relative `canonicalUrl` → absolute via `https://www.tes.com` prepend at `src/scrapers/tes.py:108`. **Pre-tag fix (2026-06-29):** removed hardcoded `subject: ["Physics"]` on every listing (was in two places: HTML-fallback path line ~88 and JSON path line ~111). Now `subject` is set only when the title literally contains the word "physics" — same pattern as `linkedin.py`, `toptutorjob.py`, `search_associates.py`, `gulftalent.py`. Previously a "Lead Teacher of Biology" listing at RG8 0PJ (The Oratory School) was mis-stamped as Physics to satisfy the heuristic filter, scored 60/100 by the LLM, and triggered a bogus Telegram notification. Same fix applied to `dipont.py` (also had hardcoded `subject: ["Physics"]` AND `curriculum_board: "Edexcel"` — the latter now derives from "edexcel" in title) and `libyan_jobs.py` (was tagging any "teacher" / "academic" title with `["Physics", "Science"]`; now reserves subject tagging for literal-word matches).

- **LibyanJobs scraper** — WordPress theme; each job is `<article.loadmore-item.noo_job>`. Up to 30 jobs across 3 pages
- **`_extract_json()` bracket walk** — used instead of brittle `json.loads()` + `removeprefix`; handles NVIDIA thinking mode interleaving reasoning text before JSON. `_extract_json_array()` for batch responses
- Supabase DNS may be unreachable — all `SupabaseClient` methods fall through to `DedupStore` on `httpx.HTTPError`
- Research Agent `web_search` uses DuckDuckGo HTML endpoint — may be rate-limited; `deep_scrape` falls back to HTTP if Firecrawl is unconfigured
- `StrategicBrief.fallback()` is called when research data cannot be gathered — this does NOT crash the pipeline
- Virtual environment at `.venv/` but deps installed globally; `pip install -e .` not required

## Stealth Browser Harness (`stealth_browser.py`)

Pre-flight verification script at project root. Tests the Camoufox fingerprint against `bot.sannysoft.com` (the Intoli/Sannysoft bot detection suite — the public gold standard). **Must be run before every scrape session.** If any test shows FAIL, scraping is unsafe.

### Verified test suite (11 tests, all PASS as of 2026-06-29)

| # | Test | Expected | Mechanism |
|---|------|----------|-----------|
| 1 | User Agent (Old) | PASS (Firefox UA shown) | Camoufox native |
| 2 | WebDriver (New) | PASS (`missing (passed)`) | Camoufox native — `navigator.webdriver` is `false` on prototype, NOT an own property |
| 3 | WebDriver Advanced | PASS | Camoufox native — no Selenium/WebDriver artefacts on `window`/`document` |
| 4 | Chrome (New) | PASS (`present (passed)`) | Route-injected `window.chrome` mock (runtime, loadTimes, csi, app) |
| 5 | Permissions (New) | PASS | Route-injected `navigator.permissions.query` override |
| 6 | Plugins Length (Old) | PASS (`5`) | Camoufox native PluginArray |
| 7 | Plugins is PluginArray | PASS | Camoufox native |
| 8 | Languages (Old) | PASS (`en-US,en`) | Camoufox native |
| 9 | WebGL Vendor | PASS (`Google Inc. …`) | Camoufox native (ANGLE renderer) |
| 10 | WebGL Renderer | PASS (ANGLE string) | Camoufox native |
| 11 | Broken Image Dimensions | PASS (`24x24`) | Camoufox native |

### Architecture

```
stealth_browser.py
  ├── page.route("https://bot.sannysoft.com/", inject_into_html)
  │     ├── route.fetch() → zstd decompress via zstandard.ZstdDecompressor().stream_reader()
  │     └── body.replace(b"<script", INJECT_SCRIPT + b"<script", 1) → route.fulfill()
  ├── AsyncCamoufox(headless=False, humanize=True, os="windows", locale="en-US")
  ├── .venv/lib/python3.14/site-packages/playwright/driver/package/lib/coreBundle.js  (patched)
  └── ~/.cache/camoufox/  (Firefox 135.0.1-beta.24 custom build)
```

### Injected script (before any page `<script>`)

```javascript
window.chrome = {
  runtime: {},
  loadTimes: function() {},
  csi: function() {},
  app: {isInstalled: false}
};
navigator.permissions.query = function(p) {
  return p.name === 'notifications'
    ? Promise.resolve({state: Notification.permission})
    : _origQuery(p);
};
```

### Known behavioural notes

- **Camoufox background monitor** deletes `window.chrome` after page load. Do NOT check `!!window.chrome` via `page.evaluate()` after the page settles — it will be `false`. Always check the DOM element's CSS class (`passed` vs `failed`) to determine actual test verdicts.
- **Do NOT redefine `navigator.webdriver`** — Camoufox already has it as `false` on the prototype chain (not an own property). Using `Object.defineProperty()` creates an own property, which triggers `_.has(navigator, "webdriver")` → `true` → FAIL.
- **Do NOT redefine `navigator.plugins` or `navigator.languages`** — same reason. Camoufox handles PluginArray and language enumeration natively.
- **The `os="windows"` fingerprint** means the browser reports Windows NT 10.0. Some sites may cross-check this against TLS fingerprint or font enumeration. If a site-specific issue arises, test with different `os` values.
- **`zstandard` python package** is a hard dependency for the route-injection path. It's installed in `.venv`. The main page HTML from bot.sannysoft.com is served with `Content-Encoding: zstd` via Cloudflare.

### Manual verification checklist

```bash
# 1. Verify Camoufox binary is installed
cat ~/.cache/camoufox/version.json  # should show 135.0.1-beta.24

# 2. Verify zstandard is available
.venv/bin/python3 -c "import zstandard; print('OK')"

# 3. Run the harness
.venv/bin/python3 stealth_browser.py

# 4. Check output — all 11 tests must show ✅
# If any show ❌ or CSS class "failed" — DO NOT SCRAPE
```

## Configuration

- All settings via `.env`, loaded by `pydantic-settings` (`src/config.py:Settings`)
- `CAMOUFOX_ENABLED` — set to `1` to activate stealth Camoufox browsers (default `0`/False)
- Candidate profile: `data/profile.json`
- `SCHEDULE_TIME` format: comma-separated 24h, e.g. `08:00,17:00,22:00,22:30,23:00`
- `NOTIFY_SCORE_THRESHOLD` — minimum score for notifications (default 50, set in `.env`)
- `RESEARCH_SCORE_THRESHOLD` — minimum score for deep research (default 60, set in `.env`)

## Key files

- `src/scoring/llm_scorer.py` — Weighted Load Balancer, 5 providers, model rotation, tenacity, health state machine, leaky bucket, `_extract_json`/`_extract_json_array`
- `src/storage/supabase_client.py` — Supabase CRUD; every method falls through to `DedupStore` on `httpx.HTTPError`
- `src/storage/dedup_store.py` — SQLite tables `seen_urls` and `job_cache`; persisted across runs
- `src/generators/cover_letter.py` — 5-provider cascade, `__LLM`/`__fallback` filename tagging; now consumes `research_brief` dict from job for institution-aware writing
- `src/agents/models.py` — `StrategicBrief` Pydantic model (institution_facts, strategic_alignment, recommended_angle); includes `fallback()` classmethod for graceful degradation
- `src/agents/tools.py` — `web_search` (DuckDuckGo HTML) and `deep_scrape` (Firecrawl or HTTP fallback) tool implementations
- `src/agents/research_agent.py` — ReAct-style tool-calling agent with 5-provider LLM cascade, MAX_STEPS=5, `_extract_json` bracket walker, synthesis fallback on exhaustion
- `src/notify/telegram.py` — `scoring_reasoning` in alerts, cover letter attachment
- `src/notify/email_sender.py` — Resend or SMTP with STARTTLS; must rename was `email.py` (stdlib conflict)
- `scripts/setup_supabase.sql` — schema migration; apply manually via Supabase SQL Editor

## Front End (`web/`)

A Next.js 14 App Router dashboard providing a reactive, touch-friendly control panel for the pipeline.

### Entrypoints
- **Dev**: `cd web && pnpm dev` (starts on `http://localhost:3000`). Slow first compile (~100-120s on 3.8Gi RAM systems). Pages compile on demand thereafter.
- **Build**: `cd web && pnpm build`. May require `NODE_OPTIONS="--max-old-space-size=2048"` on low-memory systems. Full build takes ~3-5min.
- **Production**: `cd web && pnpm start`. Requires ~400MB RSS; may get OOM-killed on systems with <2Gi available RAM.
- **Lightweight static preview**: `node /tmp/serve-static.mjs` after build. Serves pre-rendered HTML + static chunks with stub API responses. Uses ~40MB RSS; stays alive on low-memory systems. API routes return stubs (no real Supabase queries).
- **Typecheck**: `cd web && pnpm typecheck` (tsc --noEmit) — must pass before committing
- **Lint**: `cd web && pnpm lint` (next lint)

### Routes
| Route | Purpose |
|-------|---------|
| `/` | Dashboard — scored jobs with filters, sort, pagination, detail drawer. |
| `/pipeline` | Pipeline Control — systemd status, Start/Stop/Run, live journalctl logs. |
| `/settings` | Advisory threshold (0–100) and schedule-times editor. |
| `/leads` | Tutoring leads — manual-entry form, status tile row, paginated table filtered by status, inline status-flip menu, expandable row showing parsed brief + proposal. |

### API Routes (server-only)
| Path | Method | Auth | Notes |
|------|--------|------|-------|
| `/api/jobs` | GET | — | Paginated, filtered jobs from Supabase. |
| `/api/jobs/options` | GET | — | Distinct sources & countries for filter dropdowns. |
| `/api/settings` | GET/POST | — | Advisory settings mirrored in `web/config.json`. |
| `/api/pipeline/status` | GET | — | systemd `is-active` + `show` state. |
| `/api/pipeline/start\|stop\|run` | POST | `x-admin-token` or localhost | Mutating scheduler actions. |
| `/api/pipeline/logs` | GET | — | Recent journalctl lines (default 200). |
| `/api/leads` | GET | — | Paginated, status-filtered list of tutoring leads. |
| `/api/leads/counts` | GET | — | Current-calendar-month tile counts (new, proposal_sent, reply_received, paid_first_session, lost). |
| `/api/leads/manual` | POST | `x-admin-token` or localhost | Insert a tutoring lead from the dashboard manual-entry form. |
| `/api/leads/<id>/status` | POST | `x-admin-token` or localhost | Flip lead status to one of the seven lifecycle states. |
| `/api/leads/<id>/status` | GET | `x-admin-token` or localhost | Download rendered proposal as plain text (Content-Disposition: attachment). |

### Environment (`web/.env.local`)
| Key | Required | Description |
|-----|----------|-------------|
| `SUPABASE_URL` | Yes | Project URL, e.g. `https://<ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Service-role key — **server-only**, never sent to browser. |
| `SUPABASE_ANON_KEY` | No | Currently unused; all reads via server route handlers. |
| `PIPELINE_CWD` | No | Python project root (default `/mnt/d/physics-job-hunter`). |
| `SYSTEMD_UNIT` | No | systemd unit name (default `physics-job-hunter.service`). |
| `ADMIN_TOKEN` | No | Shared secret for mutating pipeline endpoints; if unset, localhost-only. |
| `NOTIFY_SCORE_THRESHOLD` | No | Advisory threshold mirror (default 50). |
| `SCHEDULE_TIME` | No | Advisory schedule mirror (default `08:00,17:00,22:00,22:30,23:00`). |

### Key Files
- `web/app/page.tsx` — Dashboard client component (fetches `/api/jobs`, wires `JobTable`).
- `web/app/pipeline/page.tsx` — Pipeline Control client (status/logs polling, actions).
- `web/app/settings/page.tsx` — Settings form (POST `/api/settings`).
- `web/app/leads/page.tsx` — Tutoring leads: manual-entry form, status tiles, paginated table, inline status-flip menu, expandable row showing parsed brief + proposal.
- `web/app/api/*/route.ts` — Server route handlers (Supabase, systemctl, settings store).
- `web/lib/supabase/server.ts` — Server-only Supabase client (service role, cached).
- `web/lib/api/guards.ts` — Auth guard for mutating pipeline routes.
- `web/lib/api/settings-store.ts` — `web/config.json` read/write.
- `web/lib/store/jobs.ts` — Zustand store (jobs list, filters, sort, pagination).
- `web/lib/store/settings.ts` — Zustand store (advisory settings).
- `web/app/components/ui/*.tsx` — Touch-friendly primitives (Button, Card, Slider, Toggle, StatusBadge, Toast, etc.).
- `web/app/components/jobs/*.tsx` — Job table, filters, detail drawer, skeleton, score badge.
- `web/tailwind.config.ts` — Semantic tokens (surface/ink/brand/status/score), 44px tap targets.
- `web/globals.css` — CSS variables for tokens, base styles, accessibility.
- `web/README.md` `.gitignore` — ignores `node_modules`, `.next`, `config.json`, `.env.local`.

### Security
- Service-role key is **server-side only** — imported via `import "server-only"` in `lib/supabase/server.ts`.
- Mutating pipeline endpoints (`start`, `stop`, `run`) require either:
  - `x-admin-token` header matching `ADMIN_TOKEN` env var, **or**
  - Request originates from `127.0.0.1` / `::1` (localhost fallback).
- All `systemctl` and `python3` spawns use argument arrays (no shell).

### Accessibility & UX
- British English spelling throughout (standardise, programme, labelling, colour, etc.).
- Minimum 44×44 px tap targets on all interactive elements.
- Focus rings, ARIA labels/roles, keyboard navigation.
- `prefers-reduced-motion` respected (animations disabled).
- Dark mode via `prefers-color-scheme`.
- Toast notifications for async actions.

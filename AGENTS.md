# Physics Job Hunter — Agent Guide

## Security & personal data (HARD RULE)

**Never commit cover letters, CVs, profiles, applications, or any document
containing personal information — the operator's or anyone else's.**

- `data/cover_letters/`, `CV_*.html`, `cv_redesign*.py`, `apllications/`,
  `data/profile.json`, `data/profile_tutoring.json`, personal interview/relocation
  docs, `_pdfscan/`, `opencode export*.json`, and personal `.docx`/`.pptx` files
  were untracked on 2026-10-16 (commit `e261522`) and are listed in `.gitignore`.
- These files **remain on disk** — the pipeline reads and writes them locally.
  Never `git add -f` them, never re-add them, and never paste their contents into
  commits, code, docs, or logs.
- Git history before 2026-10-16 still contains some of these files (already pushed
  to GitHub). The cleanup was deliberately forward-only — do not rewrite history
  unless the operator explicitly asks for it.
- The pipeline writes new cover letters to `data/cover_letters/` at runtime; that
  directory is ignored, so no commit should ever include it.

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

1. **Scrape** — 12-scraper fleet registered in `src/main.py:run_scrapers()`:
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
   - `BSOTeachersScraper` (BaseScraper, no auth — Firefish/ASP.NET board for British International Schools; near-zero physics yield, coverage play; added 2026-08-14)
   - `SeekTeachersScraper` (BaseScraper, no auth — agency board, `jobs.asp?keyword=physics` country-discovery + per-country crawl intersected with `profile.json` `target_countries`; `SEEK_COUNTRIES=all` bypass; added 2026-08-14)
0. **Pre-flight (stealth verification)** — Before every scrape session, run `python3 stealth_browser.py`. It tests the Camoufox fingerprint against bot.sannysoft.com (the Intoli test suite). **If > 0 tests show FAIL, do not scrape** — investigate and fix the regression first. Any single failure means the fingerprint is compromised and scraping will likely hit CAPTCHAs/403s. See Stealth Browser Harness section below for details.
1. **Heuristic pre-filter** — `filter_relevant_jobs()` drops jobs whose title/subject don't match physics/maths/science/IGCSE/A-Level keywords. The hard `physics in (title | subject | curriculum)` is the primary guard. Substring matchers block non-teacher roles (2026-06-29 expansion): technicians ("technician", "lab technician", "science technician", "stem technician"), management ("director of", "head of department", "head of physics", "manager", "coordinator", "administrator"), higher-ed ("lecturer", "university", "researcher", "postdoc", "professor"), lab roles ("physics lab", "physics laboratory"). Blocked jobs never reach the LLM scorer and never trigger Telegram notifications.
3. **Deduplicate** — skip URLs already in Supabase (falls back to `DedupStore` SQLite at `data/dedup.db`)
4. **Upsert** — `SupabaseClient.upsert_jobs()` into `job_listings` table; coerces empty `closing_date=""` → `None`
5. **Score** — `LLMScorer` with Weighted Provider Registry: validates providers at startup via `validate_provider_configs()`, removes dead ones, queries survivors in weight order. Active providers: **Gemini** (weight 40, primary — `gemini-2.5-flash` free tier) → **NVIDIA** (30, primary `nvidia/nemotron-3-super-120b-a12b`, backup `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` — swapped 2026-10-16 after the previous backup `openai/gpt-oss-20b` was found hanging even on trivial prompts) → **Groq** (20, `openai/gpt-oss-120b` production model) → **OpenRouter** (15, often cool-down rate-limited) → **OpenCode Zen** (5, key expired — skipped). `SCORER_PROVIDER`/`SCORER_FALLBACK` env vars are **not consumed** — provider selection = API key presence + `PROVIDER_WEIGHTS`. If all LLM providers fail, falls back to rule-based scoring (base 30). LLM rubric: Curriculum 0-30, Subject 0-25, Location 0-20, Salary 0-15, Housing 0-10 (max 100). `visa_sponsorship` and `deadline_urgency` removed.
6. **Research** — `ResearchAgent` produces a `StrategicBrief` for every job scored ≥ `RESEARCH_SCORE_THRESHOLD` (default 60). Uses a ReAct-style LLM loop with two tools: `web_search` (DuckDuckGo) and `deep_scrape` (Firecrawl or HTTP fallback). The brief feeds `institution_facts`, `strategic_alignment`, and `recommended_angle` into the cover letter generator. Falls back to `StrategicBrief.fallback()` if research fails.
7. **Notify** — Telegram (`src/notify/telegram.py`) + Email (`src/notify/email_sender.py`, Resend or SMTP) for jobs scored ≥ `settings.notify_score_threshold` (default 50, configurable via `NOTIFY_SCORE_THRESHOLD` in `.env`)

## Campaign Mode (targeted acquisition)

The pipeline can be re-targeted to a specific acquisition campaign via the `CAMPAIGN`
env var, **without** touching the shared `profile.json` or any other branch.

- **Activate**: `CAMPAIGN=pe_central_europe python3 -m src.main`
- **Loader**: `src/campaign.py:load_campaign()` returns `None` when `CAMPAIGN` is empty
  (legacy behaviour, zero change) or the dict from `data/campaign_<name>.json`.
- **Two-lane model** — the campaign JSON defines an `edexcel_only` primary lane and a
  `curriculum_adjacent` secondary lane (Cambridge/IB Physics-Maths) at a `0.6×`
  `adjacency_boost`. The pre-filter's `_EXCLUDED_EXAM_BOARDS` (Cambridge/IB/AQA/IB…) is
  lifted **only when a campaign is active**, so adjacent-board schools can pass the
  filter; in legacy mode the exclusion stays in force.
- **Tagging**: `tag_campaign()` (`src/main.py`) derives `curriculum`, `region`, `lane`,
  and a deterministic `campaign_score` (0–100) from each surviving job's
  title/school/location/description text — deliberately NOT the sparse `curriculum`
  field (only TES/LinkedIn populate it). `curriculum_adjacent` jobs are dropped when
  `secondary_lane_enabled=false`.
- **Scoring/Research/Cover-letter**: `LLMScorer`, `ResearchAgent`, and
  `CoverLetterGenerator` all accept a `campaign` arg that injects campaign context
  into their prompts (Edexcel > adjacent; Dresden > Germany > Czechia weighting) without
  altering the 0–100 rubric or the notify/research gates.
- **Config**: `data/campaign_pe_central_europe.json` — the live campaign for a Pearson
  Edexcel Physics+Maths teacher targeting Central Europe (Dresden family base). Implements
  the decision in `docs/research/pe-architecture.md`; the two-lane scoring schema lives in
  `docs/research/pe-synthesis.md` §4.
- **Safety rail**: the hard `physics in combined` guard in `_is_relevant()` is always
  enforced, in both legacy and campaign modes.

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
- **`BSOTeachersScraper` (2026-08-14)** — Firefish Recruitment Software, ASP.NET WebForms, no auth. Bare GET of `/jobs.aspx` (no consent cookie, no session) returns the full board — verified, content is NOT gated behind the `__doPostBack` cookie banner. No RSS (`/jobs/rss.aspx` 301s back to `/jobs.aspx`); `sitemap.xml` lists all 43 job URLs in one request (unused optimization). Selectors: `div.job-result-item` cards, `a.card__title` (title+URL), `li.results-job-location` (raw "Europe, Poland" / "Middle East, Doha, Qatar"), `li.results-posted-at` (relative, not parsed). Listing-only — no detail fetches (no closing dates, no curriculum). Country = last comma segment, with `startswith("UAE")` special-case for "UAE - Abu Dhabi". Subject tagging = conservative literal-word rule (verbatim from `libyan_jobs.py`) plus whole-token `mathematics`/`maths` (the libyan `"math" in title.split()` trap misses "Mathematics Teacher"). WARNING log when a page yields 0 cards (Firefish commercial-DOM drift sentinel). Expected physics yield ~0 — coverage play for BSO-accredited British international schools.
- **`health_check()` on `SupabaseClient`** — probes with `SELECT id LIMIT 1` at startup; if it fails, raises `httpx.HTTPError` immediately so the pipeline falls through to in-memory scoring with local SQLite
- **`update_score()` and `mark_notified()` filter by `url` column** — NOT by `id`. Callers pass `_job_key(job)` which returns `job["id"]` (UUID) or falls back to `job["url"]`. `update_score` was broken (filtered `id=url`, silent no-op)
- **`import re` must be in `src/scoring/llm_scorer.py`** — `_strip_llm_wrappers()` uses `re.sub`. If the import is missing, every provider validation fails silently (caught by `except Exception`). All providers return HTTP 200 but JSON extraction crashes with `NameError`
- **`upsert_jobs()` coerces empty `closing_date=""` → `None`** — PostgreSQL refuses `""` for `date` type
- **`get_recent()` ignores its `days` parameter** — always queries `>= date.today()`. Minor bug, but affects any code expecting a sliding window
- **`target_countries` + Europe (2026-08-14)** — `data/profile.json` `target_countries` extended with `"Spain", "Poland", "Romania", "Germany"` (additive only; existing targets untouched) so BSOteachers.com's Europe cluster earns the `llm_scorer.py:1023` country-match bonus. Side effect: country bonus now applies to those countries for every scraper, not just BSO.
- **`send_telegram_alert` early-return bug (2026-08-14)** — `return sent` was indented inside the `for job in jobs:` loop in `src/notify/telegram.py`, so only the FIRST top-scoring job ever received an alert message (subsequent jobs were silently dropped). Symptom: "Telegram: N alerts sent" where N=1 despite multiple jobs ≥ `notify_score_threshold` with generated cover letters. Fixed by dedenting to function level. Caught live on the first BSOteachers run (Doha 90/100 alerted, UAE-Abu-Dhabi 55/100 dropped).
- **`SeekTeachersScraper` (2026-08-14; crawl depth + round-robin 2026-10-01)** — e-IT Solutions classic ASP agency board, robots `Allow: /`, no auth. `jobs.asp?keyword=physics` returns a country picker (`a[href*="keyword=physics&country_id="]`). The keyword matcher is LOOSE (a Humanities listing appears in a physics search), so the heuristic pre-filter remains the real guard. Country names canonicalised via `COUNTRY_ALIASES` and intersected with `profile.json` `target_countries`; `SEEK_COUNTRIES=all` sweeps all discovered countries.
- **SeekTeachers crawl depth (2026-10-01)** — the old `MAX_PAGES_PER_COUNTRY = 10` / `MAX_PAGES_TOTAL = 60` pair truncated every country short of its tail (measured: country 17 exhausts at page 5, UAE at page 14, and the largest board was still returning 20 fresh listings per page at page 30). Worse, the **sequential** loop let the first country in discovery order consume the entire global budget, starving every later country — and discovery puts the largest board first. Crawl is now **round-robin** across countries (`cursors`/`active`/`stopped_at`), so each progresses in step and countries that exhaust early hand their budget back. Caps raised to 20/country and 120 total. Measured: **552 → 831 listings, 10 → 14 surviving the pre-filter, +4 new physics jobs, 0 regressions**, for ~85s vs ~60s. Note: an "empty page" past page 1 is normal exhaustion, not DOM drift — only page 1 being empty warns.

- **Fleet-wide signature dedup (2026-08-14; window retuned 2026-09-30)** — `job_signature()` in `src/storage/dedup_store.py` = md5 of normalized `school|title|country`; stored in SQLite table `notified_signatures(signature, first_notified, first_url)`. **It is a notification gate, not a storage drop**: `send_notifications()` skips Telegram/email/cover-letter for jobs whose signature was recorded within the re-post TTL; jobs are still upserted/scored and appear on the dashboard. **The window is now `SIGNATURE_REPOST_TTL_DAYS = 30`, not 180.** The 180-day version suppressed a school+title for half a year and created a permanent deadlock: suppression keyed on signature alone, so a row the `notified` flag still reported as False could never alert again even after a failed `mark_notified` — 12 top-scoring vacancies (incl. a 100/100 Subject Leader of Physics, Dubai) were muted indefinitely. The `notified` column is the same-URL guard; this table exists solely to collapse the same vacancy advertised under several URLs. First deploy backfills from Supabase `notified=true` rows (via `SupabaseClient.get_notified_jobs()`); backfill only runs when `signature_count() == 0`.
- **`--resend-notified` (2026-09-30)** — releases jobs muted by a signature block. Selects `notified=false AND score >= NOTIFY_SCORE_THRESHOLD`, deletes their signatures via `DedupStore.forget_signature()`, then calls `send_notifications(..., ignore_signatures=True)`. `--resend-min-score N` overrides the threshold. Use after a deliberate config change (e.g. shortening the TTL) to re-surface jobs that the old window silenced.
- **`--force-notify` now actually forces (2026-09-30)** — `send_notifications()` takes `ignore_signatures: bool`; `--force-notify` passes `True`. Previously the flag bypassed the `notified` column but NOT the signature gate, so it could not re-alert a signature-suppressed job despite its help text. The signature backfill is also skipped when `ignore_signatures=True`.
- **Provider validation (2026-09-30: typed verdicts)** — `validate_provider_configs()` has a 2-minute deadline; probes with a real scoring prompt. `_probe_verdict()` returns `(verdict, http_status)` where verdict is `ok` / `config_invalid` / `transient`. `config_invalid` = 401/403/404/410/451 (`_CONFIG_INVALID_STATUS`) → logged `[CONFIG_INVALID, HTTP nnn]` and recorded as DEAD (out of rotation). `transient` = 429/5xx/timeout/transport error/**unparseable body** → logged `probe failed transiently — keeping in rotation on cooldown`. **The previous bare `except Exception` collapsed both classes to `[CONFIG_INVALID]`, which meant a provider being momentarily rate-limited was thrown out of rotation for the whole run** — Gemini, which had batch-scored jobs hours earlier, was discarded this way on a 429. A crash in parsing says nothing about the key, so it is transient, not config.
- **Health state machine** — `ProviderRegistry` tracks ACTIVE → COOLING_DOWN (300s canary) → DEAD (3 consecutive cooldown failures). A `config_invalid` verdict is recorded directly as DEAD via `record_dead()` — a permanently-dead endpoint can never pass a canary, so parking it in COOLING_DOWN would invite pointless probes. Dead providers stay removed for the session
- **Persisted provider health (2026-09-30)** — `ProviderHealth` (`src/scoring/llm_scorer.py`, `data/dedup.db` table `provider_health(provider, verdict, http_status, checked_at)`) caches probe verdicts. A provider cached as `config_invalid` is skipped with **no HTTP request** (log: `known CONFIG_INVALID (cached) — skipping probe`); it also calls `record_dead()` so the startup summary reports the dropped provider as DEAD rather than ACTIVE or COOLING_DOWN. Verdicts older than `VALIDITY_SECS = 24h` are ignored so a provider rate-limited overnight is re-probed rather than written off. Previously every run re-probed all five providers, costing ~3s/run of doomed requests 9×/day. Clear with `ProviderHealth().clear()`.
- **Intra-provider model rotation** — Groq: 1 model (`settings.groq_model`, default `openai/gpt-oss-120b`). NVIDIA: `nvidia/nemotron-3-super-120b-a12b` (primary, ~12–13s on the real scoring prompt) → `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (backup, ~17–25s). OpenCode Zen: `["mimo-v2.5-free", "deepseek-v4-flash-free"]` (key expired — skipped). OpenRouter/Gemini: 1 model each
- **NVIDIA endpoint health varies wildly (2026-10-16 probe)** — the catalogue lists 81 models but most are either 404 on `/chat/completions` (`nvidia/nemotron-nano-3-30b-a3b`, `mistralai/mistral-large-2-instruct`, `moonshotai/kimi-k2.6`, `nvidia/llama-3.1-nemotron-*`, `nvidia/nemotron-4-340b-instruct`, `writer/palmyra-creative-122b`, `ibm/granite-3.0-8b-instruct`, `google/gemma-3-12b-it`, …) or hang indefinitely even on a one-word prompt (`openai/gpt-oss-20b`, `nvidia/nemotron-3.5-lightning-30b-a3b`, `nvidia/nemotron-3-ultra-550b-a55b`, `deepseek-ai/deepseek-v4.1-flash`, `z-ai/glm-5.3`, `z-ai/glm-5.3-flash`, `google/gemma-4-31b-it`, `meta/muse-glimmer-30b`). A hang costs the full `_call_nvidia` timeout (120s) before `_try_models` rotates, so a dead backup model silently taxes every cascade that reaches it. Verified healthy on the real scoring prompt (valid JSON, 100/100 on a Romania Edexcel listing): `nvidia/nemotron-3-super-120b-a12b` 12–13s, `nvidia/nemotron-3.5-super-vl-120b-a12b` 32–82s (high variance), `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` 17–25s, `stepfun-ai/step-5-preview` 39s. Re-probe before changing `NVIDIA_MODEL`/`NVIDIA_BACKUP_MODEL` — trivial-prompt latency is a fast screen: >15s or a timeout means the endpoint is unhealthy.
- **NVIDIA reasoning-headroom fix (2026-06-29)** — both NVIDIA chain members (`nvidia/nemotron-3-super-120b-a12b` and its backup, since 2026-10-16 `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`; previously `openai/gpt-oss-20b`) put a meaningful fraction of the completion budget into `reasoning_content` chain-of-thought. The default `max_tokens=800` returns truncated (or empty) `content` for both. The fix: `_call_nvidia` in `src/scoring/llm_scorer.py` passes `max_tokens=4096`. Cost: ~750 completion tokens per job, <1 cent per job on the free NVIDIA catalogue tier.
- **Tenacity retry** — `tenacity.Retrying` with `wait_random_exponential(multiplier=1, max=60)`, 3 attempts per model before rotating or moving to next provider. Format: log every attempt as `[PIPELINE] Provider: groq | Model: ... | Result: Success/Fail | Attempt: N`
- **Leaky-bucket pacing** — `batch_score()` splits into chunks of `MAX_PER_CHUNK=5` with `CHUNK_DELAY=20s`. Total pipeline ~2.5min for 20 jobs
- **Cover letter `_resolve_provider()`** — probes OpenCode Zen → NVIDIA → Groq → OpenRouter → Gemini (**2026-06-29 reorder**: was previously Groq-primary; OpenCode Zen is the primary cascade-wide so the free deepseek-v4-flash-free is the default across scorer, research, and cover letters, with NVIDIA as the high-quality 200K-context fallback, Groq as the fastest paid fallback once healthy). `time.sleep(5)` between calls in evaluation loop to avoid 429s. Files tagged `__LLM` (AI) or `__fallback` (template). Cover letters consume ``research_brief`` dict from the job for institution-aware writing.
- **Cover-letter `_call_opencode_zen` realign (2026-07-03)** — the cover-letter generator's OpenCode Zen call at `src/generators/cover_letter.py:159` was looping the **paid** model pair `("deepseek-v4-flash", "deepseek-v4-pro")`. Both return HTTP 401 from the OpenCode Zen catalogue (workspace `wrk_01KRNSES9FY5ACEMK78BKAC1QY` has no credits), which is why cover letters were silently falling through to NVIDIA on every job and producing `__LLM_nv.md` filenames. Realigned to `("deepseek-v4-flash-free",)` to match `LLMScorer._call_opencode_zen` and `ResearchAgent._call_opencode_zen`. Also bumped `max_tokens=1200 → 4096` (reasoning-mode headroom) and `temperature=0.8 → 0.3` (match research-agent tier). Verified live: a realistic cover letter prompt returns `finish_reason=stop`, 2074 chars of `content` (proper cover letter), 8714 chars of internal reasoning, 2122 total completion tokens — so the free tier is correct and reachable in the cover-letter path too.
- **Research Agent cascade** — same priority (OpenCode Zen → NVIDIA → Groq → OpenRouter → Gemini), enforced at the `ResearchAgent._providers()` level. The agent fires the cascade through the same lookup. OpenCode Zen is `[deepseek-v4-flash-free]` and benefits from the same `max_tokens=4096` reasoning-headroom already wired into `LLMScorer._call_opencode_zen`. The research-agent loop has no separate validator — it relies on whichever provider surfaces a non-empty string first.
- **Batch scoring bypassed OpenCode Zen (2026-07-03)** — `LLMScorer._try_batch()` iterates `self._registry.active_providers(PROVIDER_WEIGHTS)` and skips any provider whose `cfg.batch_fn is None`. OpenCode Zen (weight 40, primary) and NVIDIA (weight 30, secondary) were both registered with `batch_fn=None`, so batch scoring silently fell through to Groq (weight 20) on every run — `Batch scored 1 jobs via groq` in the logs was the symptom. Fix: added `_batch_score_via_opencode_zen()` (`max_tokens=4096`, `temperature=0.3`, `timeout=120`) mirroring the Groq batch pattern, and wired it into the provider registration at `self._providers.append(("opencode_zen", ..., self._batch_score_via_opencode_zen))`. NVIDIA still has `batch_fn=None` (its thinking-mode models are too slow for batch — single-score path only). Verified live: a synthetic 1-job batch now resolves to `opencode_zen` first (29s, score=85, finish_reason=stop).
- **Profile alignment from CV HTML (2026-06-30)** — `data/profile.json` (school-job pipeline) updated to reflect the 2026-06-27 leadership-positioning CV HTML (`CV_Mahmoud_Alsini_VersionB_Leadership.html`): `leadership_opportunities` flipped `false`→`true`; new `leadership_role_preference` key `[Head of Physics, Subject Lead, STEM Coordinator, STEM Lead]`; `target_countries` lost the spurious Vietnam entry; `cv_summary` reflects the correct three-year window (Sept 2023 → present) with PGCEi 2025–2026, B.Sc. Mechanical Engineering 2020 (was wrongly listed 2021), and STEM-enrichment / leadership emphasis. No Maths in CV — earlier mention of Science+Maths in `cv_summary` was incorrect and is removed. **Same alignment applied to `data/profile_tutoring.json`** (separate file for tutoring leads): dropped "Maths" subject and "Cambridge CIE" exam-board references, fixed the B.Sc. graduation year (2020 not 2021), corrected experience tenure (three years), and gated off the false "four years … Maths" claim. Bilingual tutoring profile now pure-Physics, Pearson-Edexcel only, matching the school-job profile.
- **TES scraper** — extracts from `__NEXT_DATA__` JSON (catches `AttributeError` for null fields); falls back to HTML parsing. Relative `canonicalUrl` → absolute via `https://www.tes.com` prepend at `src/scrapers/tes.py:108`. **Pre-tag fix (2026-06-29):** removed hardcoded `subject: ["Physics"]` on every listing (was in two places: HTML-fallback path line ~88 and JSON path line ~111). Now `subject` is set only when the title literally contains the word "physics" — same pattern as `linkedin.py`, `toptutorjob.py`, `search_associates.py`, `gulftalent.py`. Previously a "Lead Teacher of Biology" listing at RG8 0PJ (The Oratory School) was mis-stamped as Physics to satisfy the heuristic filter, scored 60/100 by the LLM, and triggered a bogus Telegram notification. Same fix applied to `dipont.py` (also had hardcoded `subject: ["Physics"]` AND `curriculum_board: "Edexcel"` — the latter now derives from "edexcel" in title) and `libyan_jobs.py` (was tagging any "teacher" / "academic" title with `["Physics", "Science"]`; now reserves subject tagging for literal-word matches).


- **LibyanJobs scraper** — WordPress theme; each job is `<article.loadmore-item.noo_job>`. Up to 30 jobs across 3 pages
- **`_extract_json()` bracket walk** — used instead of brittle `json.loads()` + `removeprefix`; handles NVIDIA thinking mode interleaving reasoning text before JSON. `_extract_json_array()` for batch responses
- Supabase DNS may be unreachable — all `SupabaseClient` methods fall through to `DedupStore` on `httpx.HTTPError`
- Research Agent `web_search` uses DuckDuckGo HTML endpoint — may be rate-limited; `deep_scrape` falls back to HTTP if Firecrawl is unconfigured
- `StrategicBrief.fallback()` is called when research data cannot be gathered — this does NOT crash the pipeline
- Virtual environment at `.venv/` but deps installed globally; `pip install -e .` not required

## Board availability audit (2026-10-01)

Every non-contributing scraper was re-reconed against the live sites. Only
**one was actually broken**; the rest are structurally or credential-gated.

| Scraper | Real cause | Outcome |
|---|---|---|
| `gulftalent` | **Genuinely broken** — two bugs. See below. | Header bug fixed; board gated off by default |
| `dipont` | **Not a job board.** `/careers/independent-schools-jobs/` is a Divi (`et_pb_*`) marketing page: zero job cards, all four original selectors match 0. Vacancies live on 5 partner schools — 3 are dead (`huaercollegiate.com` does not resolve, `rkcshz.cn` times out, `dipont-hc.com` returns 0 bytes) and the 2 that respond publish none either (`kcschengdu` links only to a login portal, `nkcswx.cn` only to `mailto:`). | Log now states the finding; nothing extractable exists |
| `schrole` | **Credential-gated.** Correct listing roots are `/jobs-for-teachers/<region>/` (not `/en/job-search`, which 404s). Those pages serve only *school* cards; every public path on `app.schrole.com` is either `/api/files/<uuid>` or `/Identity/Account/Login`. | Log states it is credential-gated, not "unimplemented"; `REGION_PATHS` kept for a future credentialed build |
| `toptutorjob` | Camoufox binary never fetched — `~/.cache/camoufox/` is empty | Needs `python -m camoufox fetch` (~1.3 GB) then `CAMOUFOX_ENABLED=1` |
| `search_associates` | No `SA_USERNAME`/`SA_PASSWORD` in `.env` | Needs credentials |
| `teacher_horizons` | No `TH_EMAIL`/`TH_PASSWORD` in `.env` | Needs credentials |

**GulfTalent, the one real bug.** Two defects:
1. **Cloudflare 403.** Probed header combinations against the live endpoint;
   only the full XHR set succeeds — `BaseScraper.HEADERS` (403) → `+
   Accept: application/json` (403) → `+ Referer/Origin` (403) → `+
   X-Requested-With: XMLHttpRequest` (**200**, real JSON). Scoped to this
   scraper as `API_HEADERS`, not added to `BaseScraper` — the other ten
   scrapers must keep presenting as ordinary browser page loads.
2. **`KEYWORDS` was dead code.** `BaseScraper.run()` injects a generic
   default list whenever `search_terms` is None, so the board's targeted
   subject+curriculum phrases never fired. `run()` is now overridden.

Even fixed, the board is not worth running: Cloudflare still challenges
roughly **1 request in 3** (with `POLITE_DELAY` and a retry on challenge),
and the queries that get through returned **0 teaching roles** — it is a
corporate Gulf employment list where "physics" hits medical physicists and
engineers. Keywords trimmed 6 → 2 and the board is now **opt-in via
`GT_ENABLED=1`** (`gt_enabled` in `src/config.py`), saving ~80s per run.

### The two action items, resolved (2026-10-01)

**`last_seen` migration — no longer needed.** It cannot be applied
programmatically: `supabase-py` has no raw-DDL method, the project exposes no
DDL RPC (`exec_sql`/`execute_sql`/`exec`/`query` all return `PGRST202`), and
`SUPABASE_DB_URL` in `.env` has a **literally masked password**
(`postgres://…:***@…`), so a direct connection is impossible. Rather than leave
a manual step, `SupabaseClient` now **probes once and caches the answer**
(`_supports_last_seen`). The first batch pays one rejected request; every
batch after it omits the column silently. Adding the column later upgrades it
automatically with no code change — the probe succeeds and the flag flips.

Nothing else depended on `last_seen`: it was always diagnostic, and the 45-day
freshness gate reads `created_at`.

**Email — now honest, still needs credentials.** `email_status()` in
`src/notify/email_sender.py` reports whether email can *actually* be sent and,
if not, exactly which value is missing. The previous `send_email_digest()`
returned `False` silently, so a config claiming `EMAIL_PROVIDER=resend` logged
a benign-looking `Email digest: skipped` forever.

Critically, it now also treats **placeholder addresses as missing**: `.env`
shipped `EMAIL_FROM=job-hunter@yourdomain.com` and `EMAIL_TO=you@email.com`, so
merely adding a Resend key would still have delivered nowhere. The warning is
logged **once per process** rather than once per job.

To enable, set in `.env` (the guide forbids editing `.env` from tooling, so
this one is manual):

```
EMAIL_PROVIDER=resend          # or "smtp", or "" to disable cleanly
RESEND_API_KEY=re_...          # from https://resend.com/api-keys
EMAIL_FROM=alerts@yourdomain.com   # a domain VERIFIED in Resend
EMAIL_TO=you@gmail.com
```

`.env.example` documents all of the above. Telegram remains the primary alert
channel and is unaffected either way.

### Regressions found and fixed while doing this

- **SeekTeachers could zero out the whole board.** The deeper round-robin
  crawl issues more requests and started hitting read timeouts; a single
  failed page propagated out of `scrape()`, so `run_scrapers()` logged
  `✗ seekteachers failed` and returned **0 jobs** — losing ~831 listings to
  one bad page. Added `BaseScraper.fetch_with_retry()` (3 attempts,
  backoff; transport errors only, so a 404 still fails fast) and made a
  persistently failing page skip-and-continue per country instead of
  aborting.
- **The upsert reported success when it had written nothing.**
  `upsert_jobs()` returned `len(rows)` even when the request failed and jobs
  were diverted to the local SQLite cache, so the pipeline logged
  `Stored 43 new jobs in Supabase` for a write that never happened. It now
  returns `None` on fallback and `run_pipeline` logs
  `Upsert did not reach Supabase` and reports `0 new`.
- **`get_seen_urls()` silently degraded dedup.** One read timeout sent the
  pipeline to the local `seen_urls` table, which holds ~53 URLs against
  ~400 in Supabase — so nearly every scraped job was misclassified as "new".
  Now retries twice and logs the degradation at ERROR.

## Job freshness & stale-listing suppression (2026-09-30)

Added because the pipeline kept re-surfacing a fixed, saturating pool of
**already-closed** vacancies. TES and LinkedIn are genuinely exhausted
(~20–40 and ~28 unique listings), so every run re-read the same postings and
re-alerted on them. There is no reliable expiry signal to filter on:

- **96% of `job_listings` rows have `closing_date IS NULL`** (11 of 358).
- **TES's `__NEXT_DATA__` payload carries no date field at all** — no posted
  date, no closing date. Probing every field for `dat|post|expir|clos|dead`
  returns nothing.
- Only **BSOTeachers** exposes a usable signal (`li.results-posted-at`,
  "Posted 6 days ago"), and it is relative text that is not yet parsed.

So freshness is derived from **`created_at`** — when the posting first entered
our pool — rather than from any field the boards supply.

- **`max_job_age_days` (default 45, `src/config.py`)** — `get_scored_unnotified()`
  takes `max_age_days` and filters on `created_at`. Set to `0` to disable.
  On the live dataset this suppressed 112 of 137 un-notified rows.
- **Deliberately NOT gated on `last_seen`** — TES re-serves the identical URL
  indefinitely, so a `last_seen` gate refreshes forever and suppresses
  nothing. `created_at` is the only field that distinguishes a zombie listing
  from a live one. This is why the freshness gate works at all.
- **Tradeoff** — a vacancy genuinely open 45+ days (a long maternity cover,
  say) is suppressed. Unavoidable without a date on the payload.
- **`last_seen` column (2026-09-30)** — records when a posting was last present
  on its board, distinguishing "still listed" from "vanished". Diagnostic
  only; nothing gates on it yet. **Requires the manual migration** in
  `scripts/setup_supabase.sql`:
  ```sql
  alter table job_listings add column if not exists last_seen timestamptz default now();
  create index if not exists idx_job_listings_last_seen on job_listings(last_seen);
  ```
  Until that is applied, `SupabaseClient.upsert_jobs()` catches the resulting
  `APIError`, logs `job_listings.last_seen is missing`, and **retries without
  the column** — the pipeline is fully functional either way, `last_seen` is
  simply inert. Note the supabase-py client has no raw-DDL method
  (`client.query` does not exist) and this repo has no `psycopg`, so the DDL
  must be pasted into the Supabase SQL Editor.
- **Upsert-all change** — `run_pipeline()` now upserts *every* scraped job, not
  only unseen ones, so re-upserting refreshes `last_seen` without disturbing
  `created_at` / `score` / `notified`. The reported "new" count is still
  computed from the unseen set.

## Scoring & generation fixes (2026-09-30)

- **Batch scoring silently lost jobs (P0)** — all four
  `_batch_score_via_*` providers shared a branch that answered a bare JSON
  object with `return [json.loads(json_str)]`. `_try_batch` treats non-`None`
  as success, `batch_score` extends the results, and `score_jobs_from_db`
  paired them with `zip(unscored, results)` — so **every job after the first
  in a chunk was left permanently at `score=null`** and re-attempted every run
  (observed: "Scoring 3 jobs" → "→ 1 jobs scored"). Three fixes: the branch now
  returns `None` so `_try_batch` cascades to the per-job path;
  `batch_score()` backfills any short chunk individually; both callers in
  `src/main.py` use index-checked assignment instead of `zip` and log a
  warning if anything is still unscored. Gemini is the provider that actually
  trips this — it honours `response_mime_type: application/json` and answers
  with an object rather than an array.
- **TES `country` was garbage** — `location.split(",")[-1].strip()` produced
  `"Surrey"`, `"Byfleet"`, `"BN27 3QH"` (a postcode). That one field fed
  `job_signature` dedup, the LLM's Location 0–25 rubric, and the country-match
  bonus at `llm_scorer.py:_apply_modifiers`. Because `profile.json`
  `target_countries` uses the short form `"UAE"` while TES emits
  `"United Arab Emirates"`, **the country bonus never fired for a single UAE
  posting**. Replaced with `_resolve_country()`: alias map (mirroring
  `seekteachers.COUNTRY_ALIASES`) → target-country match → UK region → UK
  postcode → trailing segment. Known residual gap: a UK posting naming only a
  town/district ("Bromsgrove, Sunbrae") still resolves to that town; closing
  it needs a gazetteer, and it is no worse than the previous behaviour.
- **TES phantom pagination (wasted ~24s/run)** — `range(1, 6)` never stopped
  early because the old guard was `len(jobs) < 20` and TES serves exactly 20
  listings per page. Probing pages 1–15 showed **every page returns the
  identical 20 listings** — TES ignores `page` entirely beyond the first. The
  loop now breaks on "page yielded no new URLs" (plus a diminishing-returns
  guard), matching how `seekteachers.py` already paginates. Verified: same 41
  unique jobs from 6 requests instead of 15.
- **Cover letters silently degraded to templates** — `CoverLetterGenerator`
  resolves one provider on first use, caches it on the instance, and reuses it
  for every letter, with no retry or cascade. A single 429 (Groq, exhausted by
  the preceding research-agent loop) therefore turned *every remaining letter
  in the batch* into a `__fallback.md` template — 12/12 on one run.
  `_demote_provider()` now walks the rest of the cascade on an empty response
  and re-resolves the pinned provider, so a rate limit costs one letter rather
  than the batch.

## Known coverage ceiling (measured 2026-09-30, not yet addressed)

For anyone wondering why the pipeline reports `0 new`:

| Board | State | Yield available |
|---|---|---|
| TES | exhausted — pagination is a no-op, ~20–40 unique total | none |
| LinkedIn | saturated at 28 | none |
| seekteachers | **30–50% never crawled** (10-page cap; country 5 still returned 20/page at page 30) | ~6 physics jobs/country |
| gulftalent | 403 on every query; also its 6 targeted `KEYWORDS` are **dead code** because `BaseScraper.run()` injects a default 3-term list | offline |
| dipont | stale selectors, matches nothing | offline |
| schrole | 14-line `return []` stub, still registered in the fleet | offline |
| toptutorjob / search_associates / teacher_horizons | dormant — no creds, `CAMOUFOX_ENABLED=0` | offline |

Also dead: **email**. `.env` sets `EMAIL_PROVIDER=resend` with an empty
`RESEND_API_KEY`, so `Email digest: skipped` every run while the config
implies email is wired.

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
- `CAMPAIGN` — campaign id to re-target the pipeline (e.g. `pe_central_europe`); empty = legacy behaviour. Loads `data/campaign_<id>.json` via `src/campaign.py:load_campaign()`.

## Key files

- `src/scoring/llm_scorer.py` — Weighted Load Balancer, 5 providers, model rotation, tenacity, health state machine, leaky bucket, `_extract_json`/`_extract_json_array`
- `src/campaign.py` — campaign config loader (`load_campaign()`); returns `None` when no campaign active so legacy behaviour is unchanged
- `data/campaign_pe_central_europe.json` — live "Pearson Edexcel Central Europe" campaign rule set (two-lane scoring, geography weights, school whitelist)
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

# Handoff Prompt — Campaign Mode (proactive discovery)

You are continuing work on the **Physics Job Hunter** proactive campaign pipeline
(`/mnt/d/physics-job-hunter`). The reactive job-scraping pipeline is separate and
already working; this is the *proactive* "Pearson Edexcel Central Europe" campaign
that discovers real target schools, researches the top 10, and drafts speculative
outreach emails.

## Current state (as of 2026-07-13)

**Step 8 (orchestrator + entry point) is DONE and verified.** All 8 blueprint steps
are now complete. See `docs/campaign_handoff.md` for the per-piece status map.

Implemented this session:
- `src/campaign_runner.py` — `run_campaign(campaign_id=None, force=False)` wiring:
  DiscoveryAgent → ProspectsStore → ResearchAgent (top 10) → CoverLetterGenerator
  (speculative) → CampaignReporter → Telegram digest. Also a `python3 -m
  src.campaign_runner` entry point that reads `CAMPAIGN` env, `--campaign-id`, and
  `--force`/`FORCE=1`.
- `src/main.py` — added `--campaign-run` (and `--campaign-id`) argparse flag. The
  reactive pipeline is unchanged; the two modes are mutually exclusive.

Two latent bugs fixed this session:
1. `src/storage/prospects_store.py` — the SQLite fallback table had **no unique
   key**, so re-runs *appended* duplicate rows instead of upserting. Added
   `PRIMARY KEY (campaign_id, normalized_key)` to mirror Supabase's
   `on_conflict=(campaign_id, normalized_key)`.
2. `src/generators/campaign_reporter.py` — numeric fields return as **strings**
   from the SQLite fallback, crashing `>=` comparisons in the Visa Analysis
   section. Coerced `visa` to `int(...)`.

Added `.gitignore` excluding `data/campaign_pe_central_europe/`,
`data/campaign_pe_central_europe_cambridge/`, `data/prospects.db`, `data/dedup.db`,
`data/job_cache/`, `data/local_job_db.json` (source `data/*.json` profiles stay tracked).

## How to run

```bash
CAMPAIGN=pe_central_europe python3 -m src.campaign_runner          # normal
CAMPAIGN=pe_central_europe FORCE=1 python3 -m src.campaign_runner  # re-discover
CAMPAIGN=pe_central_europe_cambridge python3 -m src.campaign_runner  # fallback only if Edexcel yields nothing
```
Or via the CLI flag: `python3 -m src.main --campaign-run` (requires `CAMPAIGN` env).

Expected artifacts under `data/campaign_pe_central_europe/`: `prospects/*.md` (~40),
`emails/*.md` (10), `STRATEGY_REPORT.md`, plus a top-10 Telegram digest.

## How to verify (fast, no network)

The real run hits DuckDuckGo + LLM providers and is slow (~minutes per school).
For a fast structural check, stub `DiscoveryAgent`, `ResearchAgent`, and
`CoverLetterGenerator` in `src.campaign_runner` and assert:
- `python3 -c "import src.campaign_runner; import src.main"` resolves.
- `ProspectsStore.get_top` returns Category-F first, then `campaign_score` desc.
- A second `run_campaign(force=False)` yields the same distinct row count (dedup works).
- `render_strategy_report` contains 10 `## ` sections.
- `send_campaign_digest` loops only the top 10 (guard already in place).

## Key gotchas (from AGENTS.md + this build)

- Python ≥ 3.12. `.env` has LIVE API keys — never modify or commit.
- Read settings via `src/config.py:Settings`, never `os.getenv` for real settings.
  `FORCE`/`CAMPAIGN_RUN` are run-mode flags, so `os.getenv` in `main.py` is acceptable.
- Discovery uses `web_search` (DuckDuckGo) only — Camoufox stays dormant (no
  `CAMOUFOX_ENABLED` needed). `web_search` has a 300s circuit breaker after a 202;
  the agent paces with `time.sleep(1)`. Do NOT remove the sleeps.
- The Supabase `campaign_prospects` table does **not** exist yet in the live project
  (apply `scripts/setup_supabase.sql` manually via the Supabase SQL Editor). Until
  then every run falls through to the SQLite fallback (`data/prospects.db`) — this is
  expected and verified working.
- `campaign_prospects` columns `pearson_offerings` / `evidence_urls` are `text[]` —
  always assign lists, never scalar strings (crashed an earlier run with
  `malformed array literal: "Other"`). `ProspectsStore` already coerces via `_as_json_list`.
- LLM cascade: OpenCode Zen (`hy3-free` → `deepseek-v4-flash-free`) → NVIDIA → Groq →
  OpenRouter → Gemini. NVIDIA/OpenCode Zen need `max_tokens=4096` (reasoning headroom).
- `career`/`competition` axes in `DiscoveryAgent._score` are heuristic at discovery
  time; treat `campaign_score` as a triage ranker, not a precise fit metric.
- Naming nuance: the candidate is "Mahmoud Alsini" in the speculative prompt but
  "Mahmoud altaher Alsini" inside `models.py` `strategic_alignment`. Harmless but
  note it for CV consistency.

## Likely next tasks for the new session

- Apply `scripts/setup_supabase.sql` to Supabase so the primary store (not just the
  SQLite fallback) is used; then run a real `FORCE=1` campaign and eyeball the
  discovered schools / emails / strategy report.
- Tune `DiscoveryAgent` ring queries / `cap` / `classification_thresholds` if
  discovery yields too few or too many schools.
- If the Telegram digest is empty, check `settings.telegram_bot_token` / `telegram_chat_id`.
- Decide whether to commit the uncommitted campaign work (many `data/*.json`,
  `docs/*.md`, `src/agents/discovery_agent.py`, `src/generators/campaign_reporter.py`,
  `src/storage/prospects_store.py`, `src/campaign_runner.py` are currently untracked/
  modified). Not committed because the user did not ask.

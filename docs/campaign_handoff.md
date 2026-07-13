# Campaign Mode — Execution Handoff (Status)

> Companion to `docs/campaign_blueprint.md`. That document is the *locked plan*;
> this one records *what has actually been built* so the next session can finish
> Step 8 (orchestrator + entry point) and run the pipeline. Update as work lands.

---

## 0. Status Map

| Blueprint Step | Status | Artifact |
|---|---|---|
| 1 — rewrite `campaign_pe_central_europe.json` | ✅ DONE | `data/campaign_pe_central_europe.json` |
| 2 — Cambridge fallback JSON | ✅ DONE | `data/campaign_pe_central_europe_cambridge.json` |
| 3 — `campaign_prospects` table + `ProspectsStore` | ✅ DONE | `scripts/setup_supabase.sql`, `src/storage/prospects_store.py` |
| 4 — `DiscoveryAgent` (radial, web_search, scoring) | ✅ DONE | `src/agents/discovery_agent.py` |
| 5 — Tier wiring + Category-F detection | ✅ DONE (inside Step 4) | `src/agents/discovery_agent.py` |
| 6 — Speculative cover letter + ResearchAgent top-10 | ✅ DONE | `src/generators/cover_letter.py` (ResearchAgent already PART-8 capable) |
| 7 — `CampaignReporter` + Telegram digest | ✅ DONE | `src/generators/campaign_reporter.py`, `src/notify/telegram.py` |
| 8 — `campaign_runner` orchestrator + `main.py` entry | ✅ DONE | `src/campaign_runner.py`, `src/main.py` (`--campaign-run` flag) |

---

## 1. What Each Built Piece Does

### `data/campaign_pe_central_europe.json` (Step 1)
Edexcel-primary proactive-discovery config. Key new blocks vs. the old reactive file:
- `mode: "proactive_discovery"`, `required_curriculum: "Edexcel"`.
- `discovery`: `center` (Dresden 51.0504,13.7373), `max_radius_km: 300`,
  `ring_step_km: 50`, `cap: 40`, `region_queries` keyed by ring radius (0…300).
- `classification_thresholds: {apply_immediately: 66, network_first: 45}`
  (now **consumed** by the DiscoveryAgent — previously dead).
- `output`: `base_dir`, `prospects_dir`, `emails_dir`, `strategy_report`.
- `research_agent_prompt` retained (PART-8 brief, no outreach email).

### `data/campaign_pe_central_europe_cambridge.json` (Step 2)
Cambridge-only fallback. Same shape; `required_curriculum: "Cambridge"`,
`lane.adjacency_boost: 1.0`, `fallback_for: "pe_central_europe"`, separate
`output.base_dir`. Run **manually only** if Edexcel yields nothing.

### `scripts/setup_supabase.sql` (Step 3)
Appended `campaign_prospects` table (`text[]` for `pearson_offerings` /
`evidence_urls` — do NOT assign scalar strings; that crashed the old run with
`malformed array literal: "Other"`). Unique key `(campaign_id, normalized_key)`.
Apply manually to Supabase before first run.

### `src/storage/prospects_store.py` (Step 3)
`ProspectsStore` — Supabase primary, `data/prospects.db` SQLite fallback
(`_ProspectsSQLite`, mirrors `DedupStore`). Methods:
`upsert_prospects()`, `get_all(campaign_id)`, `get_top(campaign_id, n=10)`
(orders Category-F first, then score desc), `mark_email_written()`,
`close()`. All Supabase calls fall through to SQLite on `httpx.HTTPError`.

### `src/agents/discovery_agent.py` (Steps 4–5)
`DiscoveryAgent(campaign)`:
- `discover(force=False)` walks rings inner→outer, `web_search` per ring,
  extracts candidate school names, verifies each with a second `web_search`
  (Edexcel/Cambridge + Physics at IGCSE/A-Level → `evidence_url`; unverified
  dropped = hallucination guard), geo-locates via `CITY_COORDS` +
  Nominatim fallback (`geocode()`), computes `distance_km`/`ring`, drops
  beyond `max_radius`, stops at `cap` (40).
- `_check_category_f()` searches careers/vacancies for a live Physics post.
- `_score()` — deterministic 5-axis (curriculum 0–30, visa 0–20, location
  0–15, career 0–20, competition 0–15), clamped to 100. Career/competition
  are **rule-based heuristics** (location attractiveness + snippet signals)
  pending deep research on the top 10.
- Tiering consumes `classification_thresholds`: `F` > `apply_immediately`
  (≥66) > `network_first` (45–65) > `low_priority`. `confidence`
  (high/medium/low) from evidence quality.
- Pacing: `time.sleep(1)` between searches; respects `web_search` circuit breaker.

### `src/generators/cover_letter.py` (Step 6)
- New `SPECULATIVE_EMAIL_PROMPT` (Dresden-visit framing, CV attached, no
  "application for vacancy" language).
- `generate(job, campaign=None, speculative=False, out_dir=None)` — speculative
  mode uses the new prompt and writes into `out_dir` (campaign `emails/` dir).
- `_generate_fallback_speculative_email()` template fallback.
- `_save_letter()` now renders a prospect-aware header and honours `out_dir`.

### `src/generators/campaign_reporter.py` (Step 7)
`CampaignReporter(campaign)`:
- `write_prospect_briefs(prospects)` → `prospects/<slug>.md` for all ~40.
- `render_strategy_report(all, top10)` → 10-part `STRATEGY_REPORT.md` (§6).
- `send_digest(top10, email_paths)` → Telegram (top 10 only).

### `src/notify/telegram.py` (Step 7)
Added `send_campaign_digest(prospects, email_paths)` — summary message +
per-school email document attachments.

---

## 2. Step 8 — What Still Needs Building

Wire the pieces into a runnable orchestrator. Suggested shape:

**`src/campaign_runner.py`**
```python
from src.campaign import load_campaign
from src.agents.discovery_agent import DiscoveryAgent
from src.storage.prospects_store import ProspectsStore
from src.agents.research_agent import ResearchAgent
from src.generators.cover_letter import CoverLetterGenerator
from src.generators.campaign_reporter import CampaignReporter

def run_campaign(campaign_id: str | None = None, force: bool = False) -> dict:
    campaign = load_campaign() or (load by campaign_id)
    agent = DiscoveryAgent(campaign)
    prospects = agent.discover(force=force)
    store = ProspectsStore()
    store.upsert_prospects(prospects)
    top10 = store.get_top(campaign["id"], n=10)
    # deep-research top 10
    researcher = ResearchAgent(campaign=campaign)
    generator = CoverLetterGenerator()
    out_dir = campaign["output"]["base_dir"] + "/emails"
    email_paths = {}
    for p in top10:
        desc = f"Offerings: {p.get('pearson_offerings')}; Location: {p.get('location')}; Evidence: {p.get('evidence_urls')}"
        try:
            brief = researcher.research(p["school_name"], p.get("location",""), desc, campaign=campaign)
            p["research_brief"] = brief.model_dump()
        except Exception:
            p["research_brief"] = StrategicBrief.fallback(p["school_name"]).model_dump()
        path = generator.generate(p, speculative=True, out_dir=out_dir)
        if path:
            p["outreach_email_path"] = path
            email_paths[p["normalized_key"]] = path
    store.upsert_prospects(top10)  # persist brief + email path
    reporter = CampaignReporter(campaign)
    reporter.write_prospect_briefs(prospects)
    reporter.render_strategy_report(prospects, top10)
    reporter.send_digest(top10, email_paths)
    return {"discovered": len(prospects), "top10": len(top10)}
```

**`src/main.py`** — add a `--campaign-run` argparse flag (or env `CAMPAIGN_RUN`)
that calls `run_campaign()` instead of the reactive `run_pipeline()`. Keep the
reactive pipeline intact; the two modes are mutually exclusive.

---

## 3. Gotchas for the Next Session (from `AGENTS.md` + this build)

- Python ≥ 3.12. `.env` has LIVE API keys — never modify or commit.
- Read settings via `src/config.py:Settings` (`settings.camoufox_enabled`, etc.),
  never `os.getenv`. Discovery uses `web_search` (DuckDuckGo) — Camoufox stays
  dormant (no `CAMOUFOX_ENABLED` needed).
- `web_search` has a 300s circuit breaker after a 202; the agent paces with
  `time.sleep(1)` between calls. A 40-school run = many searches — expect
  rate-limit cooldowns; do not remove the sleeps.
- Supabase methods must fall through to SQLite on `httpx.HTTPError` (already
  done in `ProspectsStore`).
- LLM cascade: OpenCode Zen (`deepseek-v4-flash-free` / `hy3-free`) → NVIDIA →
  Groq → OpenRouter → Gemini. NVIDIA/OpenCode Zen need `max_tokens=4096`.
  Research/cover-letter calls already honour this.
- `import re` must stay in `llm_scorer.py`.
- Career/competition axes in `DiscoveryAgent._score` are heuristic at discovery
  time (no deep research yet). They are intentionally conservative; the top-10
  `ResearchAgent` brief can later refine them. Do NOT treat `campaign_score`
  as a precise fit metric — it is a triage ranker.
- `strategic_alignment` text in `models.py` references "Mahmoud altaher Alsini"
  (double surname) while the speculative prompt uses "Mahmoud Alsini". Align if
  it matters for CV consistency.
- The campaign `output.base_dir` (`data/campaign_pe_central_europe`) is git-
  ignored? Verify `data/` is in `.gitignore` so discovered prospects/emails are
  not committed.

---

## 4. How to Run (once Step 8 lands)

```bash
# Primary Edexcel campaign
CAMPAIGN=pe_central_europe python3 -m src.campaign_runner

# Force re-discovery (ignores dedup by normalized_key)
CAMPAIGN=pe_central_europe FORCE=1 python3 -m src.campaign_runner

# Cambridge fallback (only if Edexcel yields nothing)
CAMPAIGN=pe_central_europe_cambridge python3 -m src.campaign_runner
```

Expected artifacts under `data/campaign_pe_central_europe/`:
`prospects/*.md` (~40), `emails/*.md` (10), `STRATEGY_REPORT.md`. Top-10
Telegram digest sent (if bot token configured).

---

## 5. Verification Checklist Before Declaring Done

- [ ] `python3 -c "import src.campaign_runner"` (syntax + imports resolve).
- [ ] `CAMPAIGN=pe_central_europe FORCE=1 python3 -m src.campaign_runner` runs a
      short smoke (cap lowered to ~3) without crashing; prints discovered count.
- [ ] `ProspectsStore.get_top` returns Cat-F-first ordering.
- [ ] `CampaignReporter.render_strategy_report` produces a 10-part markdown.
- [ ] `send_campaign_digest` sends only the top 10 (guard: do not loop all ~40).
- [ ] No scalar string assigned to `text[]` columns (prospects store uses lists).
- [ ] `data/` not committed to git.

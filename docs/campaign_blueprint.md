# Campaign Mode — Architecture Blueprint (Execution Handoff)

> This document is the *complete, finalized plan* for re-architecting the campaign
> feature of the Physics Job Hunter pipeline. It was produced in a planning-only
> session (grilling). The next session should **execute** it. Do not re-litigate
> the design — every decision below is locked unless explicitly marked OPEN.

---

## 0. Goal / Pivot

The campaign feature is being **repurposed** from *reactive vacancy scraping*
(pull live jobs from TES/LinkedIn → score → notify) to **proactive target-school
prospecting**:

- Enumerate ~40 real Pearson Edexcel international schools in Central Europe,
  ranked by proximity to **Dresden, Germany** (candidate has family there).
- Research each speculatively (no live vacancy required).
- Generate a **master strategy report** + **10 personalized outreach emails**
  for the top 10 schools (top 5 = "Apply Immediately" tier).
- A **Cambridge-only fallback campaign** exists for if Edexcel outreach yields nothing.
- Everything is keyed to the candidate, not to live job posts.

### Candidate context (fixed facts)
- Name: **Mahmoud Alsini** (from `CV_Mahmoud_Alsini.html`).
- Specialism: **Pearson Edexcel International GCSE + A-Level Physics & Mathematics**.
- Has a **relative in Dresden**; plans to **visit Dresden and the nearby city next month**.
- CV attachment path: `d:/physics-job-hunter/CV_Mahmoud_Alsini.html`
- Not mandatory to start this academic year — building an entry pathway is the goal.

---

## 1. Locked Decisions (Q1–Q16)

| # | Topic | Decision |
|---|-------|----------|
| 1 | School source | **B — agent-driven discovery** (pipeline discovers & verifies schools via web search, not a static list). |
| 2 | Storage | Delegated → dedicated, **separate** from `job_listings`, mirroring its workflow (see §3). |
| 3 | Cambridge | **Sequential fallback only** — NOT a parallel blended lane. Separate campaign file, triggered manually if Edexcel yields nothing. |
| 4 | Scoring | Keep the deterministic campaign score (Curriculum 30 / Visa 20 / Location 15 / Career 20 / Competition 15). Deliverable = top schools. |
| 5 | Deliverables | **(A)** 10 separate outreach emails + **(B)** one master strategy doc. |
| 6 | Location model | **Radial / concentric rings** from Dresden (Dresden > Saxony/Leipzig/Berlin > Prague > rest of DE/CZ), Dresden-family-base weighted. |
| 7 | Hallucination guard | Radial discovery: find nearest Edexcel school, then expand outward in rings; each found school must be **real + geo-anchored + Edexcel-verified with an evidence URL**. |
| 8 | Cost | **Tiered**: cheap discovery (web_search only, rule-based score) for all ~40; full `ResearchAgent` deep-research + email generation for **top 10 only**. Expand later if affordable. |
| 9 | Fallback mechanism | **Option (i)**: separate file `campaign_pe_central_europe_cambridge.json`, run manually only if Edexcel produces no positive replies. |
| 10 | Storage detail | Dedicated `campaign_prospects` table (Supabase) + local **SQLite fallback** (`data/prospects.db`, mirrors `DedupStore`) when Supabase unreachable. Do NOT overload `job_listings`. |
| 11 | Radial params | Center = Dresden; **max radius = 300 km**; **ring step = 50 km**; stop at max radius **or** ~40 candidates collected. |
| 12 | Dedup / re-run | Unique key = **`school_name + normalized location`**. Re-runs skip existing prospects unless `FORCE=1`. |
| 13 | Notifications | **Top 10 → Telegram digest** (scores + paths to the 10 email files). Remaining ~30 → **disk only** (prospects store + master doc), no Telegram. |
| 14 | Tiering | Add **Category F** (live Edexcel vacancy found during discovery) = highest priority, above Apply-Immediate. Tiers: F > Apply Immediately (≥66) > Network First (45–65) > Low Priority (<45). |
| 15 | Output paths | `data/campaign_pe_central_europe/prospects/<slug>.md` (PART-8 brief); `data/campaign_pe_central_europe/emails/<slug>.md` (10 emails); `data/campaign_pe_central_europe/STRATEGY_REPORT.md` (master 10-part doc). |
| 16 | Outreach email | **Speculative mode** (no "application for vacancy X" framing). Modification: email states candidate is **visiting Dresden + nearby city next month** (relative there), proposes a **meeting/interview/demo lesson in case a position opens soon**, and **attaches CV** `d:/physics-job-hunter/CV_Mahmoud_Alsini.html`. |

### Decoded glossary (transcription corrections from planning session)
- "Christine" → Dresden · "Dixon/Dizon" → Edexcel · "radio search" → radial/concentric ·
  "restaurant" → tiered · "K superbase didn't talk" → in case Supabase is down ·
  "Turkey" (Q13) → question thirteen.

---

## 2. Data Model — `campaign_prospects` (new table)

Mirror the `job_listings` workflow but vacancy-independent. Columns (Supabase `text[]`
for list types — do NOT assign scalar strings to array columns, this crashed the old
campaign run with `malformed array literal: "Other"`):

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid / PK | |
| `campaign_id` | text | e.g. `pe_central_europe` |
| `school_name` | text | |
| `location` | text | city, country |
| `normalized_key` | text | `school_name + location` lowercased — dedup key |
| `latitude` / `longitude` | float | for ring assignment |
| `distance_km` | float | from Dresden |
| `ring` | int | which 50 km ring |
| `pearson_offerings` | text[] | e.g. `["IGCSE Physics","A-Level Maths"]` |
| `lane` | text | `edexcel` (primary) or `cambridge` (fallback run) |
| `visa` | int | 0–20 |
| `career` | int | 0–20 |
| `competition` | int | 0–15 |
| `location_score` | int | 0–15 |
| `curriculum_score` | int | 0–30 |
| `campaign_score` | int | 0–100 total |
| `tier` | text | `F` / `apply_immediately` / `network_first` / `low_priority` |
| `category_f` | bool | true if live vacancy detected |
| `evidence_urls` | text[] | source URLs confirming Edexcel + (if F) the vacancy |
| `confidence` | text | high/medium/low per evidence rules |
| `contact_strategy` | text | from ResearchAgent brief |
| `outreach_email_path` | text | path to generated email file |
| `research_brief` | jsonb | PART-8 brief |
| `created_at` | timestamptz | |

SQLite fallback (`data/prospects.db`) mirrors this for offline operation.

---

## 3. Discovery Algorithm (radial, the core new piece)

`DiscoveryAgent` (new component) loop:

1. Define rings: center = Dresden (51.0504, 13.7373), radii = [0, 50, 100, 150, 200, 250, 300] km.
2. For each ring (inner → outer):
   - Build a web-search query: `"Pearson Edexcel International GCSE A-Level Physics Mathematics school near <region for this ring>"` (region = Dresden, then Leipzig, Berlin, Prague, Czech border, etc.).
   - Collect candidate school names + websites.
3. For each candidate: verify it **actually offers Pearson Edexcel Physics and/or Maths** at IGCSE/A-Level. Require an **evidence URL** (school curriculum page / official posting). Drop candidates with no evidence (hallucination guard).
4. Geo-locate the school; compute `distance_km` from Dresden; assign `ring`.
5. **Category F check**: during verification, also check the school's careers page / TES for a *current* Edexcel Physics/Maths vacancy. If found → `category_f = true`.
6. Stop when `distance_km > 300` OR ~40 verified candidates collected.
7. Rule-based score each (see §4); rank.

Cost control: discovery uses **web_search only** (no LLM deep-research, no `deep_scrape`
per school at this stage). Deep-research + email generation is reserved for top 10.

---

## 4. Scoring Model (deterministic, kept from original)

```
curriculum_score (0–30):
  Edexcel A-Level Physics: +15
  Edexcel A-Level Maths:   +10
  Edexcel IGCSE Physics:   +10
  Edexcel IGCSE Maths:     +10
  Strong STEM dept:        +5   (normalize total to 30)

visa (0–20):        explicit sponsorship +20 / intl hiring history +10 / unknown 0–5
location (0–15):    ring-based, Dresden-family-base weighted (inner ring highest)
career (0–20):      reputation / salary / PD / mobility
competition (0–15): applicant pool / location attractiveness / popularity

campaign_score = min(100, round(sum))
```

Note: Primary campaign is **Edexcel-only** — no Cambridge/IB adjacency boost in the
primary run (that was the old design; now Cambridge is a separate fallback file). So
`_derive_curriculum` for the primary run returns `Edexcel` or the school is dropped;
the old `"Other"` scalar-into-array crash cannot occur here because prospects use the
separate `campaign_prospects` table.

Tiers (wire the currently-DEAD `classification_thresholds` from the JSON — they are
not referenced anywhere in `src/` today):
- `F` (category_f = true) → highest, urgent notify.
- `apply_immediately` : score ≥ 66  → top 5.
- `network_first`     : 45–65       → next 5 (completes top 10).
- `low_priority`      : < 45        → rest, disk only, listed in master doc.

---

## 5. Deliverables & Pipeline Flow

```
DiscoveryAgent (radial, web_search only)
   ↓  ~40 verified Edexcel schools, scored + tiered
ProspectsStore.upsert (Supabase + SQLite fallback, dedup by key)
   ↓
Rank; select top 10 (F first, then apply_immediate, then network_first)
   ↓
For each of top 10:
   ResearchAgent.research(school_name, location, discovered_profile)  → PART-8 brief
   CoverLetterGenerator.generate(job-like prospect, campaign, speculative=True) → email
   ↓
CampaignReporter:
   - emails/<slug>.md                (10 files)
   - prospects/<slug>.md             (PART-8 briefs, all ~40)
   - STRATEGY_REPORT.md              (master 10-part doc, see §6)
   ↓
Telegram digest for top 10 (paths + scores). Rest → disk only.
```

### Speculative email content (Q16 modification)
The `speculative=True` email must:
- Introduce Mahmoud Alsini + Pearson Edexcel IGCSE/A-Level Physics & Maths specialism.
- Reference something specific from the research brief (e.g. "I see you offer Edexcel IGCSE Physics").
- State he is **visiting Dresden and the nearby city next month** (relative in Dresden).
- Propose a **meeting / interview / demo lesson** in case a position opens in the near future.
- Note **CV is attached** (`d:/physics-job-hunter/CV_Mahmoud_Alsini.html`).
- NO "application for vacancy X" framing.

---

## 6. Master Strategy Report (STRATEGY_REPORT.md) — 10 parts

Assemble from the ~40 prospects + top-10 briefs:
1. Geographic ranking (Dresden > Leipzig > Berlin > Prague…).
2. Pearson Edexcel school ranking (top 40, scored).
3. Recruitment probability scores (per school).
4. Visa analysis.
5. Contact strategy.
6. Visit strategy (Dresden-centered; reference next-month trip).
7. CV positioning.
8. Automation design (this pipeline).
9. 8-week action plan (human execution; pipeline only produces artifacts).
10. Category F live-vacancy callouts (if any).

---

## 7. Build Order (execution steps)

1. **Rewrite `data/campaign_pe_central_europe.json`** — Edexcel-primary; add `discovery`
   block (center Dresden, max_radius 300, ring_step 50, cap 40); scoring weights;
   `classification_thresholds` (apply_immediately 66, network_first 45); output paths;
   keep `research_agent_prompt` (PART-8 brief, no outreach email — generator owns that).
2. **New `data/campaign_pe_central_europe_cambridge.json`** — fallback, Cambridge-only,
   full credit (no 0.6 blend), same discovery/scoring shape; triggered manually.
3. **`campaign_prospects` table + `scripts/setup_supabase.sql` migration + `data/prospects.db`
   SQLite fallback** (mirror `src/storage/dedup_store.py`).
4. **`DiscoveryAgent`** (`src/agents/discovery_agent.py`) — radial loop per §3, using
   existing `web_search` tool (`src/agents/tools.py`). Output → ProspectsStore.
5. **Tier wiring** — replace dead `classification_thresholds` consumption; assign
   `F / apply_immediately / network_first / low_priority`; Category F detection in discovery.
6. **`ResearchAgent` deep-research top 10** (already exists; pass discovered profile as
   description) + **`CoverLetterGenerator.speculative=True`** mode (edit `src/generators/cover_letter.py`).
7. **`CampaignReporter`** (`src/generators/campaign_reporter.py`) — renders STRATEGY_REPORT.md
   + writes email/brief files; **Telegram digest for top 10 only**.

---

## 8. Key Gotchas (from AGENTS.md — do NOT skip)

- Python ≥ 3.12. `.env` has LIVE API keys — never modify or commit.
- All settings via pydantic-settings `src/config.py:Settings`; read `settings.camoufox_enabled`
  etc., never `os.getenv`.
- `CAMOUFOX_ENABLED` default False — discovery uses `web_search` (DuckDuckGo), not Camoufox,
  so dormant browsers are fine.
- Supabase methods must fall through to SQLite on `httpx.HTTPError` (mirror `DedupStore`).
- `upsert_jobs` coerces `closing_date=""` → None; prospects table avoids this by not having
  a vacancy date.
- LLM provider cascade: OpenCode Zen (primary, `deepseek-v4-flash-free`) → NVIDIA → Groq →
  OpenRouter → Gemini. NVIDIA/OpenCode Zen need `max_tokens=4096` (reasoning headroom).
- Provider validation has a 2-min deadline; providers flap (NVIDIA failed validation in the
  test run) — design discovery to degrade gracefully.
- `import re` must stay in `llm_scorer.py`.

---

## 9. Open Risks (acknowledged, not blocking)

- Web search cannot literally geo-query "within 50 km"; rings are applied **post-hoc**
  (search → verify location → assign ring → drop beyond 300 km). Acceptable.
- Discovery may under/over-collect near borders; the ~40 cap + max-radius bound handles it.
- Category F detection depends on school careers pages being scrapeable; if not, F stays
  dormant and the speculative tiers govern.
- `web_search` (DuckDuckGo) may rate-limit during 40-school discovery — pace the loop.

---

## 10. Execution Start Point

Begin at **Step 1** (rewrite `campaign_pe_central_europe.json`). Read `src/campaign.py`
(`load_campaign`), `src/main.py` (`tag_campaign`, `filter_relevant_jobs`, `send_notifications`),
`src/scoring/llm_scorer.py` (`CAMPAIGN_CONTEXT_BLOCK`, campaign_score override ~line 988),
`src/agents/research_agent.py`, `src/generators/cover_letter.py` first to match conventions.
Do NOT run the full pipeline until Steps 3–4 (storage + discovery) exist, or it will crash
as the original campaign run did (`malformed array literal: "Other"`).

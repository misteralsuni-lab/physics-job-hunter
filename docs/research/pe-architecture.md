# Pearson Edexcel Central Europe — Reconfiguration Architecture

**Author:** Software Architect agent
**Date:** 12 July 2026
**Campaign id:** `pe_central_europe`
**Grounded in:** `docs/research/pe-synthesis.md` (feedback synthesis, Part 4 JSON filtering rules) and a full read of the live pipeline source.

This document is design-only. No implementation code. Every cited location was read from the current tree.

---

## 1. Current-state map (where things happen today)

### 1.1 Heuristic pre-filter — `src/main.py`
- `CORE_KEYWORDS` (main.py:30) and `_EXCLUDED_EXAM_BOARDS` (main.py:34-41) define the keyword universe. **Critical:** `_EXCLUDED_EXAM_BOARDS` hard-rejects `cambridge`, `cie`, `aqa`, `ib`, `international baccalaureate`, `ocr` (main.py:35-36). This means the entire **curriculum_adject lane (Cambridge/IB)** from the synthesis is currently *silently dropped before it can ever be scored*.
- `_EXCLUSION_PHRASES` (main.py:45-54) and `_NON_TEACHER_ROLES` (main.py:66-90) drop gender-locked and non-teacher roles.
- `_is_relevant(job)` (main.py:93-122) is the gate. Order: exam-board exclusion → phrase exclusion → non-teacher exclusion → **hard `"physics" in combined` guard (main.py:119)**. The hard physics guard is the project's safety net and must be preserved.
- `filter_relevant_jobs()` (main.py:125-131) applies `_is_relevant` and logs drop counts. It does **no** curriculum/region tagging and no scoring.
- `run_scrapers()` (main.py:134-149) enumerates 9 scrapers. **Schrole (line 138) and Search Associates (line 137) are dormant unless credentials are set** (see config.py:40-47) — a coverage gap for Edexcel international schools.

### 1.2 Scoring — `src/scoring/llm_scorer.py`
- Rubric lives in `JOB_SCORING_PROMPT` (llm_scorer.py:42-64) and `BATCH_SCORING_PROMPT` (llm_scorer.py:66-87). Current additive rubric: Curriculum (IGCSE/A-Level) 0-35, Subject 0-30, Location 0-25, Housing 0-10. **No notion of Edexcel vs Cambridge vs IB, and no Central-Europe geography weighting** — "Location" is a generic 0-25 desirability bucket.
- `compress_job()` (llm_scorer.py:203-216) is what the LLM actually sees: passes `curriculum` and `country`/`location` fields through.
- Provider registry / cascade / health machine (llm_scorer.py:105-196) — unaffected by this campaign; reuse as-is.
- Rule-based fallback `_score_via_rules()` (llm_scorer.py:976-1022) reads `target_curricula` and `target_countries` from the **profile**, not a campaign. It currently uses `profile["target_curricula"]` (llm_scorer.py:995-998) and `profile["target_countries"]` (llm_scorer.py:1005-1008). **The live `data/profile.json` (profile.json:3-4) lists `target_curricula: ["IGCSE","A-Level"]` and `target_countries` as Gulf/Asia — NOT Germany/Czechia.** So the campaign must not rely on the profile alone.
- Profile loaded by `LLMScorer._load_profile()` (llm_scorer.py:355-368) and `ResearchAgent._load_profile()` (research_agent.py:497-507) and `CoverLetterGenerator._load_profile()` (cover_letter.py:82-91) — **three separate loaders** of `data/profile.json`. A campaign config is a parallel, separate file (ADR-1) precisely to avoid mutating the shared profile and breaking the tutoring/school branches.

### 1.3 Research agent — `src/agents/research_agent.py`
- Prompt template `AGENT_PROMPT_TEMPLATE` (research_agent.py:64-113) and `SYNTHESIS_PROMPT` (research_agent.py:116-136) define the brief shape. Both produce a `StrategicBrief` with **only** `institution_facts`, `strategic_alignment`, `recommended_angle` (models.py:90-107). **There is no School Profile / Recruitment Analysis / Candidate Match / Contact Strategy / Outreach Email structure** — the synthesis PART 8 schema does not yet exist in code.
- Invocation is in `send_notifications()` (main.py:209-225): `agent.research(school_name=…, location=…, job_description=…)`. It triggers for jobs `score >= settings.research_score_threshold` (default 60, config.py:50).

### 1.4 Cover letter generator — `src/generators/cover_letter.py`
- `COVER_LETTER_PROMPT` (cover_letter.py:16-41) already hard-codes Edexcel positioning (line 27: *"expertise in Pearson Edexcel IGCSE (4PH1) and A-Level curricula"*) and consumes `job["research_brief"]` (cover_letter.py:425). It already aligns with the campaign; it just needs the richer PART-8 brief (ADR-5).

### 1.5 Scraper-level curriculum tagging — `src/scrapers/`
- `curriculum` is populated **only** by TES (`tes.py:144`, `_infer_curriculum` at tes.py:147-159 → IGCSE/A-Level/IB/GCSE) and LinkedIn (`linkedin.py:98`, `_infer_curriculum` at linkedin.py:138). All other scrapers emit `"curriculum": []` (dipont.py:85, libyan_jobs.py:78, gulftalent.py:248, search_associates.py:255, toptutorjob.py:168). **Implication:** a campaign filter keyed purely on the `curriculum` field would miss most scrapers. ADR-2 must derive curriculum from `title`+`school`+`description` text, not trust the field.

---

## 2. Architecture Decision Records

### ADR-1 — Campaign config file `data/campaign_pe_central_europe.json`
- **Status:** Proposed
- **Context:** The synthesis (pe-synthesis.md §4) defines a machine-readable rule set: two lanes (primary `edexcel_only`, secondary `curriculum_adjacent`), a 5-axis scoring schema (curriculum_match/visa/location/career/competition with explicit point components), a `0.6×` adjacency boost, geography weights, a target-school whitelist, confidence routing, and classification thresholds. This must be loadable and swappable without touching code. Env `CAMPAIGN=pe_central_europe` should select it.
- **Decision:** Add `data/campaign_pe_central_europe.json` mirroring the synthesis §4 schema verbatim (lanes, scoring.weights, curriculum_match.components, location.components with Dresden+20/Germany+15/Czechia+10/CentralEurope+5, lane.adjacency_boost, confidence.routing, classification_thresholds, example_record). Add a `campaign: str = ""` field to `Settings` (config.py, near line 65 `camoufox_enabled`) loaded from env `CAMPAIGN`. Add a loader `src/campaign.py` (new, tiny, reversible) exposing `load_campaign() -> dict | None` that returns `None` when `settings.campaign` is empty — so `None` means "legacy behaviour, no campaign". Pipelines consume `campaign = load_campaign()` and branch only when non-`None`.
- **Consequences:** +1 static JSON (no code path change when absent). Reversible: unset `CAMPAIGN` → `load_campaign()` returns `None` → zero behavioural change. Trade-off: a second config surface to keep in sync with the profile; mitigate by documenting in AGENTS.md.

### ADR-2 — Extend the heuristic pre-filter to tag curriculum / region / lane / campaign_score
- **Status:** Proposed
- **Context:** Today `_is_relevant` (main.py:93-122) only accepts/rejects. The two-lane model requires each surviving job to carry `curriculum`, `region`, `lane`, and a `campaign_score` so downstream scoring, notification and the front-end can route and rank. Also the adjacent lane (Cambridge/IB) is currently **blocked** by `_EXCLUDED_EXAM_BOARDS` (main.py:35-36).
- **Decision:**
  1. When `campaign is None`, behaviour is **unchanged** (guard rail).
  2. When `campaign` is loaded, move the Cambridge/IB/adjacent boards out of `_EXCLUDED_EXAM_BOARDS` *for campaign mode only* — i.e. gate the exclusion list behind `if campaign is None` so the adjacent lane can pass the pre-filter. Keep the hard `"physics" in combined` guard (main.py:119) intact for both modes (physics-only specialist rule is non-negotiable).
  3. In `filter_relevant_jobs()` (main.py:125) add a post-pass `tag_campaign(job, campaign)` that derives, from `title`+`school`+`country`+`location`+`description` text (not trusting the sparse `curriculum` field — see §1.5):
     - `curriculum` ∈ {Edexcel, Cambridge, IB, Other} via keyword match (`edexcel`/`pearson`→Edexcel; `cambridge`/`cie`→Cambridge; `\bib\b`/`international baccalaureate`→IB).
     - `region` ∈ {Dresden, Germany, Czechia, CentralEurope, Other} via the campaign's location.components map applied to `country`/`location`.
     - `lane`: `edexcel_only` if `curriculum == Edexcel`; otherwise `curriculum_adjacent` (only emitted when `campaign.secondary_lane_enabled == true`).
     - `campaign_score`: a deterministic, transparent computation straight from the JSON rule set (sum of matched component points, capped), with the `0.6×` adjacency boost applied to non-Edexcel curricula. Stored on the job dict for reuse.
  4. If `lane == curriculum_adjacent` and `secondary_lane_enabled == false`, **drop** the job (matching synthesis policy "Only surface curriculum_adjacent rows when secondary_lane_enabled=true").
- **Consequences:** Minimal, additive, fully gated by `campaign is None`. The biggest risk is overlapping keyword collisions (e.g. a school mentioning both Edexcel and Cambridge) — resolve by explicit precedence (Edexcel > Cambridge > IB > Other) and document it. Trade-off: pre-filter now mutates job dicts it previously only filtered; keep the mutation pure/purely-additive (new keys only).

### ADR-3 — Adjust scoring for Edexcel + Central-Europe fit
- **Status:** Proposed
- **Context:** The LLM rubric (llm_scorer.py:42-87) weights Curriculum 0-35, Subject 0-30, Location 0-25, Housing 0-10 with no Edexcel/region distinction. We need Edexcel + Central-Europe to rank above generic IGCSE/abroad matches for this campaign.
- **Decision:** **Prefer the low-risk option — pass campaign context into the prompt, do NOT change rubric weights.** Concretely:
  - Add an optional `campaign` param threaded into `LLMScorer.score()` / `batch_score()` / `_try_batch()` (llm_scorer.py:483, 524, 549). When non-`None`, wrap `JOB_SCORING_PROMPT`/`BATCH_SCORING_PROMPT` with an extra instruction block: *"This is the Pearson Edexcel Central Europe campaign. Prioritise Pearson Edexcel curriculum (full credit) and Central-European geography (Dresden > Germany > Czechia > other Central Europe). Treat verified Cambridge/IB Physics-Maths as curriculum-adjacent at 0.6× credit per the campaign rule set."* Embed the campaign's `scoring.weights` and `curriculum_match.components` so the LLM scores consistently.
  - Keep the existing rubric totals (max 100) so the `notify_score_threshold` (config.py:49) and `research_score_threshold` (config.py:50) semantics are unchanged — we bias *within* the existing 0-100 scale rather than rescaling.
  - Also seed the deterministic `campaign_score` (from ADR-2) onto the job so the **rule-based fallback** `_score_via_rules()` (llm_scorer.py:976) and the front-end can use it as a tie-breaker / explainability field even when the LLM is unavailable.
- **Rejected alternative:** hard-overriding `PROVIDER_WEIGHTS` or re-weighting the rubric numbers. That would distort every non-campaign run and is irreversible-by-default. Prompt-injection of campaign context is localised and reversible.
- **Consequences:** Slightly longer prompts (more tokens, ~marginal cost). Trade-off: LLM may not perfectly obey the 0.6× boost — mitigate by persisting `campaign_score` as the authoritative campaign number and using `score` only for the notify gate.

### ADR-4 — Research-agent PART-8 prompt template
- **Status:** Proposed
- **Context:** The synthesis PART 8 requires, per shortlisted school: School Profile / Recruitment Analysis / Candidate Match / Contact Strategy / Customized Outreach Email. Current `StrategicBrief` (models.py:90-107) has only 3 fields and the prompts (research_agent.py:64-136) emit only those. The PART-8 email overlaps the cover-letter generator (ADR-5) — avoid duplication: the research agent owns analysis; the cover-letter generator owns the final letter.
- **Decision:**
  1. Extend `StrategicBrief` (models.py:82-107) with **optional** new fields (kept backward-compatible; the existing 3 stay required): `school_profile: str`, `recruitment_analysis: str`, `candidate_match: str`, `contact_strategy: str`. Do NOT add an email field — the cover letter generator produces the email (ADR-5). `fallback()` (models.py:117-137) gets sensible defaults for the new fields.
  2. Add a campaign-aware prompt variant `AGENT_PROMPT_TEMPLATE_CAMPAIGN` (research_agent.py, alongside the existing template) that instructs the ReAct loop to gather and emit the four new sections, and a matching `SYNTHESIS_PROMPT_CAMPAIGN`. Switch templates when `campaign` is loaded (pass `campaign` into `ResearchAgent.research()` via `send_notifications()` main.py:213-220 — add `campaign=campaign` arg).
  3. The agent still triggers only for `score >= research_score_threshold` (main.py:210); for the campaign, additionally require the job to be `lane == edexcel_only` OR (`lane == curriculum_adjacent` AND `secondary_lane_enabled`).
  4. Store the brief on `job["research_brief"]` exactly as today (main.py:221) — front-end and cover-letter generator already read it.
- **Consequences:** `StrategicBrief` gains optional fields (no breakage of existing `model_validate`). Trade-off: longer research prompts / more tokens per high-score job; acceptable since research only runs on a small shortlist.

### ADR-5 — Cover-letter consumption of research brief + campaign profile
- **Status:** Proposed
- **Context:** `COVER_LETTER_PROMPT` (cover_letter.py:16-41) already anchors on Edexcel and reads `job["research_brief"]` (cover_letter.py:425). The campaign's value-add is (a) feeding the four new PART-8 brief sections and (b) pinning Pearson-Edexcel positioning when the school is `edexcel_only` vs a differentiated Edexcel/STEM/engineering positioning for `curriculum_adjacent`.
- **Decision:**
  1. Keep the existing Edexcel hard-copy in `COVER_LETTER_PROMPT` (cover_letter.py:27) — it already matches the candidate's genuine Edexcel authorship (profile.json:10).
  2. When `campaign` is set, append a campaign directive block to `COVER_LETTER_PROMPT` (same pattern as ADR-3) instructing: if `lane == edexcel_only`, lean fully into Pearson Edexcel 4PH1/A-Level authority; if `lane == curriculum_adjacent`, explicitly bridge Cambridge/IB Physics-Maths to the candidate's Edexcel expertise using the ~90% content-overlap positioning (drawn from the synthesis insight #1/#6), and pull `institution_facts`, `school_profile`, `candidate_match`, `contact_strategy` from `research_brief`.
  3. No change to the provider cascade or filename tagging (`__LLM_<code>`, cover_letter.py:439) — already correct.
- **Consequences:** Zero structural change; only prompt augmentation gated by campaign. Trade-off: adjacent-lane letters must be careful not to over-claim Edexcel — the ~90%-overlap framing is the safe narrative.

---

## 3. Concrete change list (ordered, minimal, reversible)

1. **`src/config.py`** — add `campaign: str = ""` (after line 65). No other change.
2. **`src/campaign.py`** (NEW, ~30 lines) — `load_campaign() -> dict | None`: if `settings.campaign` empty → `None`; else read `data/campaign_pe_central_europe.json` (path keyed by `settings.campaign`). Pure loader, no side effects.
3. **`data/campaign_pe_central_europe.json`** (NEW) — verbatim §4 schema from pe-synthesis.md (lanes, scoring.weights, curriculum_match.components, location.components, lane.adjacency_boost, confidence.routing, classification_thresholds, target-school whitelist).
4. **`src/main.py`** —
   - `run_pipeline()` / both score paths: `campaign = load_campaign()` once; pass into scorer + notifications.
   - `_is_relevant(job, campaign=None)` (main.py:93): when `campaign is not None`, skip the Cambridge/IB exclusion (gate `_EXCLUDED_EXAM_BOARDS` behind `campaign is None`).
   - `filter_relevant_jobs(jobs, campaign=None)` (main.py:125): after filtering, call new `tag_campaign(job, campaign)` (same file) to set `curriculum`/`region`/`lane`/`campaign_score`; drop `curriculum_adjacent` when `secondary_lane_enabled == false`.
   - `send_notifications(jobs, db, campaign=None)` (main.py:203): pass `campaign` into `ResearchAgent.research(...)` and gate research to the campaign's allowed lanes.
5. **`src/scoring/llm_scorer.py`** —
   - `LLMScorer.__init__(self, campaign=None)`: store `self.campaign`.
   - `score(job, campaign=None)` (line 483) and `batch_score`/`_try_batch` (524/549): when campaign set, augment `JOB_SCORING_PROMPT`/`BATCH_SCORING_PROMPT` with the campaign context block (ADR-3).
   - `_score_via_rules()` (line 976): if `job.get("campaign_score")` present, surface it (already computed deterministically) so fallback ranking is campaign-aware.
6. **`src/agents/models.py`** — add optional fields `school_profile`, `recruitment_analysis`, `candidate_match`, `contact_strategy` to `StrategicBrief` (lines 90-107) + defaults in `fallback()` (line 117).
7. **`src/agents/research_agent.py`** — add `AGENT_PROMPT_TEMPLATE_CAMPAIGN` + `SYNTHESIS_PROMPT_CAMPAIGN` (near lines 64/116); `ResearchAgent.__init__(self, campaign=None)` and `research(..., campaign=None)` (line 358) select template when campaign set.
8. **`src/generators/cover_letter.py`** — `generate(job, campaign=None)` (line 403): when campaign set, append campaign directive block to `COVER_LETTER_PROMPT` (line 16) using `job["lane"]` and `job["research_brief"]`.

No changes to scrapers (they already emit enough title/school text; ADR-2 derives curriculum from text). No SQL/schema change (new fields ride on the existing `job_listings` JSON columns already used for `research_brief`/`scoring_reasoning`).

---

## 4. Out of scope / risks

- **Cambridge/IB currently blocked (highest-impact finding).** `_EXCLUDED_EXAM_BOARDS` (main.py:35-36) kills the entire adjacent lane before scoring. ADR-2 fixes this *only in campaign mode*; legacy mode is untouched. If the adjacent lane is expected to work outside the campaign, that is a separate decision.
- **Scraper coverage gaps.** The genuine Edexcel international boards (Search Associates, Schrole, Teacher Horizons) are **dormant** unless credentials are set (config.py:40-47; AGENTS.md "Schrole/Search Associates dormant"). Leonardo V. Academy / IS OWL / Akademeia are most likely found via TES + LinkedIn (the two scrapers that populate `curriculum`) plus direct school-website monitoring — which the pipeline does not yet do. Expect *few* `edexcel_only` matches; the adjacent lane is the volume play.
- **`curriculum` field sparsity.** Only TES (tes.py:144) and LinkedIn (linkedin.py:98) populate `curriculum`; the other 7 scrapers emit `[]`. ADR-2 therefore derives curriculum from title/school/description text, not the field.
- **Edexcel scarcity.** Synthesis risk #1: ~1 genuine Edexcel school in the corridor. The campaign will surface a small `edexcel_only` set and rely on `curriculum_adjacent` (0.6× boost) for volume. The `classification_thresholds` (apply_immediately ≥66 AND lane=edexcel_only AND confidence=high) will rarely fire on abundant data — by design.
- **Geo/visa fields absent from scraped jobs.** The synthesis scores `visa`/`career`/`competition` per school, but scrapers do not emit those (only `country`/`location`/`description`). These axes must be enriched from the campaign's target-school whitelist (static JSON), not from live scrape — so `campaign_score` is partly a lookup, not a pure scrape-derived number. Document this hybrid.
- **Confidence gating needs candidate inputs.** Synthesis §5 notes candidate nationality + German level are required before final ranking; those are not in `data/profile.json` today. Add as optional profile/campaign fields if Tier-1 gating is to be enforced.
- **No lint/typecheck/test harness for Python** (AGENTS.md): changes are validated manually / via `python3 -m src.main` smoke runs.

---

*End of architecture document.*

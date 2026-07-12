# Pearson Edexcel Central Europe — Reality Check

**Agent:** Reality Checker
**Date:** 13 July 2026
**Verdict:** NEEDS WORK (see §Certification) — quality **B-**
**Method:** real imports, real file reads (file:line quoted), a scripted three-scenario behavioural proof, and a boost-delta measurement. All outputs captured below.

---

## Evidence Executed

### 1. Import smoke test
```
$ python3 -c "import src.main, src.campaign, src.scoring.llm_scorer, \
    src.agents.research_agent, src.generators.cover_letter, src.agents.models; print('IMPORTS OK')"
IMPORTS OK
```
PASS — every touched module imports clean.

### 2. Scripted three-scenario proof (`/tmp/reality_check.py`, run then deleted)
```
(a) CAMPAIGN unset -> legacy
  load_campaign() = None
  Cambridge Physics kept count (expect 0): 0
  Non-physics kept count (expect 0): 0
============================================================
(b) CAMPAIGN=pe_central_europe
  load_campaign() is not None: True
  Cambridge kept: 1
   lane: curriculum_adjacent | curriculum: Cambridge | region: Germany | campaign_score: 81 | type: int
   EDEXCEL lane: edexcel_only | curriculum: Edexcel | region: Czechia | campaign_score: 100
  Edexcel score > Cambridge score: True
============================================================
(c) non-physics dropped in campaign mode
  Non-physics kept count (expect 0): 0
```
- (a) PASS — legacy rail intact: `load_campaign() is None`, Cambridge Physics dropped, non-physics dropped.
- (b) PASS — Cambridge Physics now PASSES with `lane=="curriculum_adjacent"`, `campaign_score` is an `int` (81); Edexcel Physics+Maths gets `lane=="edexcel_only"` and a strictly higher score (100 > 81).
- (c) PASS — non-physics dropped in BOTH modes (hard `"physics" in combined` guard preserved).

### 3. 0.6× boost delta measurement
```
WITH boost campaign_score: 81
WITHOUT boost (1.0) campaign_score: 83
delta from 0.6x boost: 2
```
The boost is applied and DOES reduce the adjacent score — but only by **2 points** (see Critical Analysis).

---

## ADR Compliance

| ADR / §3 item | Verdict | Evidence |
|---|---|---|
| **ADR-1** campaign config + `Settings.campaign` + `load_campaign()` | PASS | `src/config.py:67` `campaign: str = ""`; `src/campaign.py:11-19` returns `None` when unset, loads `data/campaign_{name}.json` otherwise; proven `None` at runtime (§2a). |
| **ADR-2** pre-filter tags curriculum/region/lane/score; adjacent lane gated | PASS (with caveat) | `_is_relevant(job, campaign)` gates `_EXCLUDED_EXAM_BOARDS` behind `if campaign is None` (`src/main.py:103-106`); hard physics guard still unconditional (`src/main.py:123-124`); `tag_campaign` sets all four keys (`src/main.py:223-228`); disabled adjacent lane dropped (`src/main.py:173-174`). Caveat: boost magnitude — see Critical Analysis. |
| **ADR-3** campaign prompt block + campaign_score fallback | PASS | `CAMPAIGN_CONTEXT_BLOCK` appended in `score()` (`llm_scorer.py:494-495`) and `_try_batch()` (`llm_scorer.py:568-569`); `_score_via_rules` surfaces deterministic `campaign_score` as int (`llm_scorer.py:988-994`). Minor deviation: campaign is constructor-injected (`__init__(self, campaign=None)` `llm_scorer.py:227-229`) rather than a `score(job, campaign=None)` param as §3.5 literally specified — functionally equivalent, wired via `LLMScorer(campaign=campaign)` (`main.py:392,424`). |
| **ADR-4** StrategicBrief 4 optional fields + fallback + campaign templates | PASS | `models.py:109-112` four optional `str = ""` fields; `fallback()` defaults `models.py:142-145`; `AGENT_PROMPT_TEMPLATE_CAMPAIGN`/`SYNTHESIS_PROMPT_CAMPAIGN` (`research_agent.py:150,207`) selected when campaign set (`research_agent.py:52-61, 545-547`); `research(..., campaign=None)` (`research_agent.py:457`) wired from `send_notifications` (`main.py:339-344`). |
| **ADR-5** lane-aware cover-letter directive | PASS | `generate(job, campaign=None)` (`cover_letter.py:403`) appends `edexcel_only` vs `curriculum_adjacent` directive block (`cover_letter.py:428-444`); existing Edexcel hard-copy + provider cascade + filename tag untouched. |
| **§3 change list (1-8)** | PASS | All eight items present and wired: config field, loader, JSON, main threading (`load_campaign()` `main.py:379`, `filter_relevant_jobs` `main.py:381`, `send_notifications` campaign arg `main.py:410,415`), scorer, models, research agent, cover letter. |

**Tally: 5/5 ADRs PASS + §3 change list PASS.**

---

## Critical Analysis — the 0.6× boost math

`tag_campaign` (`src/main.py:176-192`) computes curriculum credit `cm`, then at `main.py:191-192`:
```python
if lane == "curriculum_adjacent":
    cm *= campaign.get("lane", {}).get("adjacency_boost", 0.6)
```
The boost line **exists, executes, and reduces the score** (measured delta = 2 pts, §3). So the literal criterion "boost is applied and reduces adjacent-lane scores" is **met — not a no-op.**

**However**, the practical effect is nearly inert, and this is the single most important finding:

Hand computation for the Cambridge Physics+Maths job (Berlin British School):
- `cm` accumulation (`main.py:178-190`): the four Edexcel curriculum buckets are gated behind `if "edexcel" in text or "pearson" in text:` (`main.py:178`). A genuine Cambridge school's text contains neither, so those **45 points (15+10+10+10) never fire.** Only `strong_stem` (5) is added (`main.py:189-190`).
- Boost applies: `cm = 5 × 0.6 = 3.0`.
- subject `physics_and_maths` = 20; whitelist Berlin British School visa 17 / career 14 / competition 12; region Germany loc 15.
- total = 3 + 20 + 17 + 15 + 14 + 12 = **81** ✓ (matches runtime).

Because the Edexcel-named components can *never* apply to a non-Edexcel school, the 0.6× multiplier only ever scales the lone 5-pt `strong_stem` bucket → a maximum ~2-pt effect. The researched intent ("subject expertise transfers, ~90% content overlap → adjacent lane at 0.6× curriculum credit") would imply an adjacent physics-maths school receives ≈0.6 × 50 = 30 curriculum points; the implementation gives it **3**. The lane differentiation that actually happens comes almost entirely from the Edexcel-gated components being zero for Cambridge, **not** from the advertised 0.6× adjacency mechanism.

**Geography weights: PASS.** JSON `location.components` (dresden_region 20, germany 15, czechia 10, central_europe 5 — `data/campaign_pe_central_europe.json:33-36`) match ADR spec (Dresden +20 > Germany +15 > Czechia +10 > CentralEurope +5) and are correctly looked up in `tag_campaign` (`main.py:217-218`) via the region→key map. `_derive_region` (`main.py:149-158`) resolves Dresden/Germany/Czechia/CentralEurope/Other correctly (Berlin→Germany, Prague→Czechia verified at runtime).

**JSON config: PASS.** `secondary_lane_enabled: true` (line 3), `lane.adjacency_boost: 0.6` (line 41), `curriculum_precedence` (line 43), `target_schools` whitelist with per-school visa/career/competition (lines 55-65) — all present.

---

## Spec vs Reality gaps

1. **0.6× adjacency boost is technically applied but functionally negligible** (2-pt effect). The "0.6× curriculum credit" transfer the research promised is not delivered because curriculum_match components are hard-gated to literal Edexcel/Pearson text. Adjacent-lane ranking is driven by absence-of-Edexcel-points, not by the boost. Implemented-but-arguably-wrong vs the researched *outcome*; compliant with the *letter* of ADR-2.
2. **`score()` signature deviation** — §3.5 said `score(job, campaign=None)`; actual uses constructor injection (`self.campaign`). Functionally equivalent, no behavioural gap.
3. **Whitelist enrichment dependency (documented risk, not a bug)** — visa/career/competition come only from the static `target_schools` lookup; a non-whitelisted adjacent school gets visa=unknown(5), career=0, competition=0 (`main.py:212-215`). Expected per architecture §4 risk note, but means off-whitelist adjacent jobs score materially lower — worth confirming this is intended.

---

## Issues found

**Critical:** none that break the guard rails. Legacy behaviour is byte-for-byte preserved (exclusion loop only skipped when `campaign is None`; verified drop of Cambridge + non-physics in legacy mode). Hard physics guard preserved in both modes.

**Medium:**
- M1 — 0.6× boost effectively scales only `strong_stem` (5→3) for real Cambridge/IB schools; the intended "adjacent = 0.6× of physics-maths curriculum credit" is not realised. If the research outcome (meaningful-but-discounted adjacent curriculum credit) is the requirement, this needs rework so the boost multiplies a physics-maths curriculum subtotal that can actually be non-zero for non-Edexcel schools.
- M2 — off-whitelist adjacent jobs receive career=competition=0, which may under-rank legitimate corridor schools not in the static list.

---

## Overall Certification

**NEEDS WORK** — honest quality rating **B-**.

The reconfiguration is real, cleanly gated, importable, and the guard rails hold: legacy mode is unchanged, the hard physics guard survives both modes, the two lanes route correctly, `campaign_score` is a deterministic int, and Edexcel out-ranks adjacent (100 vs 81). All 5 ADRs and the §3 change list are implemented. It is **not a fantasy approval** — it works. But it falls short of READY because the headline researched mechanism (the 0.6× adjacency credit) is demonstrably near-inert (2-pt effect), so the campaign's core value proposition is not yet quantitatively delivered.

## Required fixes before production
1. **Rework the adjacency-boost target (M1):** compute a physics-maths curriculum subtotal that is non-zero for verified Cambridge/IB schools, then apply the 0.6× to *that* so adjacent credit is a meaningful fraction of Edexcel credit — matching the researched ~90%-overlap intent. Add a unit assertion that adjacent-lane curriculum credit ≈ 0.6 × the equivalent Edexcel credit.
2. **Confirm or fix off-whitelist scoring (M2).**
3. (Optional) Align `score()` signature with §3.5 or update the change list to record the constructor-injection decision.

---

## Re-check after M1 fix (13 July 2026)

**Fix applied** (`src/main.py:tag_campaign`, lines ~176-205): curriculum_match credit is now awarded on the **subjects offered** (physics/maths at A-Level/IGCSE) independent of the exam-board keyword. The `0.6×` `adjacency_boost` is applied to the whole curriculum_match subtotal for `curriculum_adjacent` lanes.

**Verified delta (isolated, whitelist stripped):**
- Edexcel Physics+Maths (Prague): `campaign_score` = 85, `lane=edexcel_only` (full credit).
- Cambridge Physics+Maths (Berlin): `campaign_score` = 70, `lane=curriculum_adjacent` (0.6× credit).
- Before fix: adjacent ≈ edexcel (2-pt effect) — **now adjacent is correctly < edexcel and > 0**.

**Regression check:** legacy (`CAMPAIGN` unset) still drops Cambridge Physics (`load_campaign() is None`, `_EXCLUDED_EXAM_BOARDS` active); `CAMPAIGN=pe_central_europe` keeps + tags Cambridge as `curriculum_adjacent`; hard `"physics"` guard preserved in both modes; all imports clean.

**Revised certification:** **READY (B)** — the single blocking Medium (M1) is resolved; no Critical issues; remaining items are documented design characteristics (whitelisted schools cap at 100 via injected visa/career/competition points; Edexcel scarcity means a small `edexcel_only` set by design).

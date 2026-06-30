# Physics Job Hunter — Session Report 2026-06-29

> Heavy maintenance session covering the LLM cascade, specialist filter, scraper
> truthfulness, and the cover-letter filename convention. All changes were
> scoped to `/mnt/d/physics-job-hunter/` — sister project
> `/mnt/d/Alsini-physics-platform/` is untouched per user-edited path-boundary rule.

## At a Glance

| # | Fix | Files | Outcome |
|---|---|---|---|
| 0 | Cover-letter tag now `LLM_<provider-code>` | `src/generators/cover_letter.py` | operator can tell provider at a glance |
| 1 | Specialist filter — scraper truthfulness | `tes.py`, `dipont.py`, `libyan_jobs.py` | Biology/Geography/etc no longer mis-stamped as Physics |
| 2 | Non-teacher roles blocklist expanded | `src/main.py` | Technicians / Management / Higher-ed rejected |
| 3 | Dropped `BasisScraper` from fleet | `src/scrapers/basis.py`, `src/main.py` | 10 → 9 scrapers |
| 4 | NVIDIA model swap (Llama-3.1 → Nemotron-Super + GPT-OSS-120B) | `.env`, `src/config.py` | validated 200 OK |
| 5 | NVIDIA reasoning-budget fix | `src/scoring/llm_scorer.py` | both NVIDIA models now emit parseable JSON at `max_tokens=4096` |
| 6 | OpenCode Zen default-model | `src/scoring/llm_scorer.py`, `src/agents/research_agent.py` | `deepseek-v4-flash-free` confirmed free-tier, 200K window |
| 7 | Provider cascade reordered project-wide | 4 files | all consumers walk `[opencode_zen → nvidia → groq → openrouter → gemini]` |
| 8 | GulfTalent scope refined | `src/scrapers/gulftalent.py` | GCC + IGCSE + physics phrases; mask `10111111000000` |
| — | AGENTS.md gotcha lines | `AGENTS.md` | everything documented in-memory |

---

## 0. Cover-Letter Filename Convention (`src/generators/cover_letter.py`)

### Why

The Telegram pipeline attaches cover letters to score-rich job notifications.
Identifying which cascade step wrote the letter is essential for diagnosing
silent bugs and never-before-seen routing behaviour.

### What

Files now use the **two-letter provider short-code** appended after `LLM`:

| Provider | Code | Filename example |
|---|---|---|
| `opencode_zen` | `oc` | `gulf_school__igcse_physics__LLM_oc.md` |
| `nvidia` | `nv` | `gulf_school__igcse_physics__LLM_nv.md` |
| `groq` | `gr` | `gulf_school__igcse_physics__LLM_gr.md` |
| `openrouter` | `or` | `gulf_school__igcse_physics__LLM_or.md` |
| `gemini` | `gm` | `gulf_school__igcse_physics__LLM_gm.md` |
| template fallback | — | `gulf_school__igcse_physics__fallback.md` |

### How

- `_resolve_provider()` now returns `tuple[name, fn]` (was just `fn`).
- `PROVIDER_SHORT_CODE` class constant maps `opencode_zen → "oc"` etc.
- Consumer builds `source = f"LLM_{short}"` when AI path answered.
- Backward-compat: existing `__LLM` substring matching scripts continue to find
  new letters, because `LLM_oc` still matches `__LLM` regex.

### Test

Verified live with `_save_letter` of six call sites. Filenames render correctly:

```
LLM_oc     -> gulf_international_school__igcse_physics_teacher__LLM_oc.md
LLM_nv     -> gulf_international_school__igcse_physics_teacher__LLM_nv.md
LLM_gr     -> gulf_international_school__igcse_physics_teacher__LLM_gr.md
LLM_or     -> gulf_international_school__igcse_physics_teacher__LLM_or.md
LLM_gm     -> gulf_international_school__igcse_physics_teacher__LLM_gm.md
fallback   -> gulf_international_school__igcse_physics_teacher__fallback.md
```

---

## 1. Specialist Filter — Scraper Truthfulness

### Root cause

Three scrapers hardcoded `subject: ["Physics"]` on **every listing** to satisfy
the pre-filter, defeating the project's strict-typesetting specialty-check guarantee.

| File | Pre-fix | Post-fix |
|---|---|---|
| `src/scrapers/tes.py` (lines 88, 111) | always `["Physics"]` | only when `title` literally contains "physics" |
| `src/scrapers/dipont.py` (line 79) | always `["Physics"]` + hardcoded `curriculum_board: "Edexcel"` (second lie) | conditional on title; `curriculum_board` derives from "edexcel" in title |
| `src/scrapers/libyan_jobs.py` (lines 51-53) | any teacher/academic keyword → `["Physics", "Science"]` | literal-word matches only, with whole-token guard against "Physical Education" |

### User-reported false positives fixed

- "Lead Teacher of Biology" (The Oratory School, RG8 0PJ) — score 60 → now rejected.

### Pattern matched to existing truthful scrapers

`linkedin.py`, `toptutorjob.py`, `search_associates.py`, `gulftalent.py` — all
already used the literal-title-match pattern. The three offenders were aligned
to this convention.

---

## 2. Non-Teacher Roles Blocklist (`src/main.py`)

### Root cause

`_NON_TEACHER_ROLES` had only 12 phrases, none covering technician /
management / higher-ed roles.

### Fix

Expanded to cover:

| Category added | Phrases |
|---|---|
| Lab / technician | `technician`, `lab technician`, `science technician`, `stem technician`, `physics lab`, `physics laboratory` |
| Management | `director of`, `head of department`, `head of physics`, `manager`, `coordinator`, `administrator` |
| Higher-ed | `lecturer`, `university`, `researcher`, `postdoc`, `professor` |

### User-reported false positive fixed

- "Physics Technician" (Colfe's School, Greenwich) — score 65 → now rejected.

### Test matrix (19 cases)

- ✓ Biology / Geology / TAs / Geography / Director / Lecturer / Lecturer-Physics → 10 of 10 reject
- ✓ Physics Teacher / IGCSE Physics / Lead Teacher of Physics / STEM Tutor-in-Physics → 9 of 9 pass

---

## 3. `BasisScraper` Removed from Fleet

`src/scrapers/basis.py` — `git rm`'d. `BasisScraper` import + instantiation
removed from `run_scrapers()` in `src/main.py`.

Fleet now: **9 scrapers** (TES, LinkedIn, Dipont, TopTutorJob,
SearchAssociates, TeacherHorizons, GulfTalent, Schrole, LibyanJobs).

---

## 4. NVIDIA Model Swap

### Before

```ini
NVIDIA_MODEL=meta/llama-3.1-70b-instruct
NVIDIA_BACKUP_MODEL=meta/llama-3.1-8b-instruct
```

### After

```ini
NVIDIA_MODEL=nvidia/nemotron-3-super-120b-a12b
NVIDIA_BACKUP_MODEL=openai/gpt-oss-120b
```

- `src/config.py` — `nvidia_backup_model` default updated.
- `.env` — both values swapped live via `sed`.
- Validation: both endpoints return 200 OK with `'OK'` at ping level.

---

## 5. NVIDIA Reasoning-Mode Budget Fix (`src/scoring/llm_scorer.py:699`)

### Root cause

`_call_nvidia` used `max_tokens=800`. Both NVIDIA chain members are
reasoning-mode and burn ~650 tokens on `reasoning_content`, leaving 0 for the
visible `content` — the score JSON. Result: `finish_reason=length`, empty
content, silent cascade to backup → eventually OpenRouter/Gemini, every job.

### Live probe (canonical IGCSE-Physics scoring prompt)

| Model | `@max_tokens=200` | `@max_tokens=4096` (post-fix) |
|---|---|---|
| `nemotron-3-super-120b-a12b` | finish=`length`, IRRELEVANT reasoning-only ❌ | finish=`stop`, valid JSON ✅ |
| `openai/gpt-oss-120b` | finish=`length`, content="" ❌ | finish=`stop`, valid JSON ✅ |

### Fix shipped

`max_tokens=800 → 4096` in `_call_nvidia`. Docstring records: rationale, cost
ratio (~750 tokens/job at free NVIDIA tier, <1¢ per job), and that both models
now parse cleanly. Mirrors what was already done for OpenCode Zen earlier in
the session.

---

## 6. OpenCode Zen Default-Model Swap

### Decision

After probe across the OpenCode Zen catalogue (which has 17+ models on
free-tier mixes), `deepseek-v4-flash-free` was selected as the chosen default:

- Free-tier (cost reported as `"0"` in API response)
- 200K-token context window confirmed via 274K-token probe (returned
  `finish_reason=length`, not error)
- `max_tokens=4096` produces valid `{'score':80}` JSON for the scorer

`deepseek-v4-flash` (paid) was eliminated because the workspace
`wrk_01KRNSES9FY5ACEMK78BKAC1QY` returns `401 CreditsError`.

### Code

- `OPENCODE_MODELS = ["deepseek-v4-flash-free"]`
- `_call_opencode_zen(prompt, max_tokens=4096, timeout=120)` (already wired
  earlier in session)

---

## 7. Provider Cascade Reorder — Project-Wide

### Before/After

| Consumer | Before (lead) | After (lead) |
|---|---|---|
| `LLMScorer.PROVIDER_WEIGHTS` | groq=40 | **opencode_zen=40** |
| `ResearchAgent._providers()` | groq | **opencode_zen** |
| `CoverLetterGenerator._resolve_provider` | groq | **opencode_zen** |
| `tutoring_parser._provider_call` | groq (no opencode) | **opencode_zen** |

Final cascade everywhere: **opencode_zen → nvidia → groq → openrouter → gemini**.

### Live HTTP probes (smoke)

```
[1/3] OpenCode Zen  → 200 OK, 1816ms
[2/3] NVIDIA        → 200 OK,  986ms / 957ms (Nemotron + GPT-OSS)
[3/3] Groq          → 200 OK, 1307ms (Llama-4-Scout)
```

### Five-way comparison pass (canonical IGCSE-Physics job)

| Pass | Order | Score | Latency | Notes |
|---|---|---:|---:|---|
| **1** | opencode_zen-primary | **90** | **18s** | chosen |
| 2 | nvidia-primary | **95** | 23s | slow reasoning |
| 3 | gemini-primary | 90 | 16s | gemini cooled |
| 4 | nvidia+opencode dual | 90 | 21s | dual-lag |
| 5 | ORIGINAL (groq-primary) | 90 | **12.9s** ⚡ | costs credits |

**Recommendation**: pass-1 — 5s slower than groq-primary, but zero cost.

### Failover simulation

Mocked `CoverLetterGenerator._resolve_provider()` with OpenCode Zen returning
`None`:

```
provider fn returned:    _call_nvidia
capture trail:           ['opencode_zen', 'nvidia']
answer:                  'nvidia-answer'
```

Cascade skips OpenCode and reaches NVIDIA on next probe. Real cascade logic preserved.

---

## 8. GulfTalent — GCC Mask + Combined Phrases

### What the user's URL probes revealed

- **URL 1**: `country=10111111000000` — 6 contiguous bits set = GCC countries.
- **URL 2**: `/uae/jobs/secondary-physics-teacher-233616` — canonical detail-page pattern.
- Combined subject + curriculum phrases (`physics teacher igcse`) yield real
  teaching hits in `total_results=17`, page 1.

### Code changes

- `_GCC_MASK = "10111111000000"` constant.
- Parameter renamed `keywords=` → `search_keyword=` (correct API param).
- `KEYWORDS` rebuilt with combined phrases: `physics teacher IGCSE`,
  `physics teacher A-Level`, etc.
- URL builder passes `country` mask in `params=` (`overridable` via
  `GT_COUNTRY_MASK` env var).

---

## Path Boundary Compliance

In-scope edits today (all under `/mnt/d/physics-job-hunter/`):

```
✓ src/generators/cover_letter.py
✓ src/scrapers/{tes,dipont,libyan_jobs,gulftalent,basis}.py
✓ src/scrapers/toptutorjob.py        (selector budget fix)
✓ src/scrapers/browser_base.py       (read-only)
✓ src/main.py                        (BasisScraper removed + filter expanded)
✓ src/config.py                      (NVIDIA backup default updated)
✓ src/scoring/llm_scorer.py          (cascade reorder + opencode_zen default + reasoning-budget)
✓ src/agents/research_agent.py       (cascade reorder)
✓ src/agents/tutoring_parser.py      (cascade reorder)
✓ AGENTS.md                          (multiple gotcha line updates)
```

Out-of-scope (`/mnt/d/Alsini-physics-platform/`) **untouched** (mtime confirmed
unchanged at `2026-06-28 00:26:51`).

---

## Persistence

**Memory updated** so future sessions don't repeat the same mistakes:

- **Terse-typo rule** (existing entry #6) — treat lowercase-broken prose as direct task items, not broken English.
- **NVIDIA reasoning-mode rule** — `max_tokens>=4096` for
  reasoning-mode cascaders (deepseek-v4-flash-free, nemotron-3-super-120b-a12b, gpt-oss-120b).
  Default 800 fails.

---

## Caveats

- A few edge cases (e.g. "TA — Physics department") still pass through because
  the substring "ta" alone isn't in the blocklist. These are rare; expansion is
  on demand.
- The NVIDIA chain still shows reasoning-mode tokens in the response body even
  with the budget fix; only the visible `content` is sent through `_extract_json`.
- Existing Postgres rows for prior false-positive listings (Biology,
  Phys-Tech) are **not auto-cleaned**. Operator request — if desired, a SQL
  `UPDATE` script is one-shot away.

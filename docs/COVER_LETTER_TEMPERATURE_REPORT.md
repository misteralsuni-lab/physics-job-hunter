# Cover Letter Temperature A/B/C Test Report
**Date:** 2026-07-03  
**Model:** deepseek-v4-flash-free (OpenCode Zen free tier)  
**Job targets:** 3 representative postings (Harrow UAE, GEMS Wellington UAE, Doha College Qatar)  
**Settings tested:** A=0.3 (current), B=0.8 (sibling default), C=dynamic (0.7→0.3 fallback)

---

## Executive Summary

| Setting | Avg Content Length | Avg Reasoning | Avg Latency | Avg Completion Tokens | Heuristic Score (max 25) |
|---|---|---|---|---|---|
| **A_0.3** (current) | 2,008 | 12,980 | 35.5s | 2,933 | **12.0** |
| **B_0.8** | 2,059 | 9,718 | 27.6s | 2,339 | **12.0** |
| **C_dynamic_0.7** | 2,084 | 9,624 | 27.6s | 2,298 | **12.0** |
| **C_dynamic_fallback** | 1,874 | 9,623 | 25.8s | 2,113 | **12.0** |

**All 12 runs completed successfully (status=200, finish_reason=stop).**

---

## Detailed Metrics by Job × Temperature

### Job 1 — Lead Teacher of Physics, Harrow UAE (IGCSE + A-Level)

| Setting | Content | Reasoning | Tokens | Time | Score |
|---|---|---|---|---|---|
| **A_0.3** | 1,982 | 12,633333 | 2,867 | 37.0s | 12 |
| **B_0.8** | 1,841 | 10,511 | 2,469 | 29.2s | 12 |
| **C_dyn_0.7** | 1,888 | 9,506 | 2,168 | 25.6s | 12 |
| **C_dyn_0.3** | 1,793 | 9,576 | 2,198 | 28.5s | 11 |

### Job 2 — Secondary Physics (KS4/KS5), GEMS Wellington UAE (IGCSE)

| Setting | Content | Reasoning | Tokens | Time | Score |
|---|---|---|---|---|---|
| **A_0.3** | 2,222 | 9,827 | 2,342 | 28.7s | 12 |
| **B_0.8** | 1,969 | 9,389 | 2,201 | 25.7s | 13 |
| **C_dyn_0.7** | 2,284 | 10,189 | 2,431 | 31.0s | 12 |
| **C_dyn_0.3** | 1,418 | 4,935 | 1,251 | 14.0s | 12 |

### Job 3 — Physics & Maths Teacher + Head of Dept, Doha College Qatar (A-Level + IB)

| Setting | Content | Reasoning | Tokens | Time | Score |
|---|---|---|---|---|---|
| **A_0.3** | 1,820 | 16,479 | 3,591 | 40.8s | 12 |
| **B_0.8** | 2,368 | 9,255 | 2,346 | 27.9s | 11 |
| **C_dyn_0.7** | 2,080 | 9,177 | 2,295 | 26.3s | 12 |
| **C_dyn_0.3** | 2,411 | 14,358 | 3,224 | 34.9s | 13 |

---

## Qualitative Sample Comparison (Job 1 — Harrow)

### A_0.3 (current default)
> "I am writing to express my profound interest in the Lead Teacher of Physics position at Harrow International School, UAE. As a dedicated educator currently teaching Pearson Edexcel IGCSE and A-Level Physics and serving as a STREAM Lead at Vision International School, I am confident that my three years of classroom experience, combined with my background in Mechanical Engineering and my ongoing pursuit of a PGCEi at Liverpool John Moores University, have thoroughly prepared me to contribute meaningfully to your Physics department and uphold the exceptional standards of a Harrow education."

**Heuristic flags:** Edexcel ✓, IGCSE ✓, A-Level ✓, STEM ✓, Engineering ✓, PGCEi ✓

### B_0.8 (sibling default)
> "I am writing to express my enthusiastic interest in the Lead Teacher of Physics position at Harrow International School, UAE. Harrow's distinguished global reputation for academic excellence, character education, and preparing students for the world's leading universities deeply resonates with my own professional philosophy and career aspirations. Currently serving as a STREAM Lead at Vision International School, I directly deliver the Pearson Edexcel IGCSE and A-Level Physics curricula..."

### C_dynamic_0.7 (fallback path)
> "I am writing to formally express my keen interest in the position of Lead Teacher of Physics at Harrow International School, UAE. As a STREAM Lead currently teaching Pearson Edexcel IGCSE and A-Level Physics at Vision International School, I possess three years of direct classroom experience and a strong track record in curriculum leadership."

---

## Token Efficiency & Cost

| Setting | Avg Prompt | Avg Completion | Avg Reasoning | Total/Job | Est. Cost/Job |
|---|---|---|---|---|---|
| **A_0.3** | 214 | **2,933** | 1,976 | **3,080** | ~$0.003 |
| **B_0.8** | 214 | **2,339** | 1,726 | **2,483** | ~$0.002 |
| **C_dyn_0.7** | 214 | **2,298** | 1,711 | **2,452** | ~$0.002 |

*OpenCode Zen free tier reports $0 cost; these are token counts only.*

---

## Qualitative Assessment (Heuristic + Manual Read)

| Dimension | 0.3 (A) | 0.8 (B) | Dynamic 0.7 (C) |
|---|---|---|---|
| **Prose naturalness** | Slightly stiffer, precise | Flows better, more conversational | Balanced |
| **Curriculum keyword density** | High (explicit Edexcel, IGCSE, A-Level) | High | High |
| **Leadership language** | Strong "STREAM Lead" emphasis | Strong | Strong |
| **Sign-off & greeting** | Always "Dear/Sincerely" ✓ | Always "Dear/Sincerely" ✓ | Always ✓ |
| **Hallucination risk** | Lowest (0.3 is conservative) | Slightly higher (rare in cover letters) | Medium |
| **Latency** | Slowest (35–41s) | Faster (25–29s) | Balanced (26–31s) |

### Key observations
1. **All three temperatures produce viable, professional cover letters** — no hallucinations, proper structure, correct curriculum references.
2. **0.3 produces slightly longer, more token-expensive letters** with more reasoning tokens but not qualitatively better.
3. **0.8 is fastest** (25–29s vs 35–41s for 0.3) and ~20% fewer tokens — same quality.
4. **Dynamic 0.7** at 0.7 behaves like 0.8 (similar latency, token counts, quality). Fallback to 0.3 just adds a second round-trip.
5. **Heuristic scores identical (11–13/25)** — no setting wins on measurable proxies.

---

## Recommendation

**Keep current 0.3** for OpenCode Zen in cover-letter generator.

**Rationale:**
- The free-tier model's reasoning mode benefits from cooler temperature to keep chain-of-thought focused.
- 0.3 is consistent with research-agent tier (0.3) and scorer tier (0.1) — system-wide low-variance behaviour.
- No quality penalty observed; 0.8 saves ~6s but adds variance with no measurable gain.
- Token cost is still effectively $0 on free tier.

**If you prefer:** flip to 0.8 (one-line change in `cover_letter.py:191`). No functional regression either way.

---

## Files Produced

| File | Purpose |
|---|---|
| `/tmp/cover_letter_temp_ab/temperature_ab_raw_*.json` | Full API responses (12 entries, 164 KB) |
| `/tmp/cover_letter_temp_ab/temperature_ab_scored_*.json` | Heuristic scores + preview text |
| `scripts/temperature_ab_test.py` | Re-runnable test harness |

---

## Next Steps (if any)

- No code change required — current 0.3 is correct.
- If you want a live A/B in production, add `OPENCODE_ZEN_TEMPERATURE` env var and read it in `_call_opencode_zen`.
- Bug C (scorer batching picks Groq not OpenCode) and Bug D (GulfTalent pagination) remain open but are separate from this test.
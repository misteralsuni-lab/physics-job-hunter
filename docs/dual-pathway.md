# Dual-Pathway Sourcing — v1 Specification

**Status:** Draft v0.1 — initial commit
**Owner:** Mahmoud (decisions), Hermes agent (implementation)
**Goal:** Add a private-tutoring sourcing branch alongside the existing institutional-school pipeline, without breaking the latter.

---

## 1. Scope

Two pathways share infra but diverge at scoring, generation, and notify copy:

| | **Institutional (existing)** | **Private Tutoring (new)** |
|---|---|---|
| **Lead source** | TES + LibyanJobs (school scrapers) | Telegram bot forward + dashboard manual paste |
| **Storage table** | `job_listings` | `tutoring_leads` |
| **Brief schema** | `StrategicBrief` (institution_facts / strategic_alignment / recommended_angle) | `TutoringBrief` (student_pain_points / parent_signals / subject_alignment / recommended_first_session_focus / voice_warmth_target / red_flags) |
| **Scoring rubric** | Curriculum 30, Subject 25, Location 20, Salary 15, Housing 10 | Curriculum match 30, Subject 25, Timezone 20, Budget 15, Urgency 10 |
| **Generator** | `cover_letter.py` | `tutoring_proposal.py` (new) |
| **Notify threshold** | `NOTIFY_SCORE_THRESHOLD` (default 50) | Tutoring threshold 60 |
| **Notify content** | job alert + cover letter attachment | brief summary + draft proposal text |
| **Status tracking** | none (one-shot) | `new → proposal_sent → reply_received → paid_first_session → lost` |

Institutional pipeline is **untouched** in v1. No schema migration on `job_listings`. No changes to cover-letter provider cascade.

---

## 2. Lead Sources — v1

| Source | Mechanism | Notes |
|---|---|---|
| **Telegram paste-bot** | User forwards or copies a parent message into a dedicated Telegram bot. Bot DMs the bot, message lands in queue. | Fastest path from phone WeChat/WhatsApp screenshots into the system. |
| **Dashboard manual entry form** | `/manual-lead` page with a paste box + optional fields. Single button, lands in queue. | Backup to Telegram; better for longer messages. |

**Out of scope for v1** (deferred to v2+):

- Preply / Spires / TutorChase inbox polling (rate-limit + auth-gated)
- Xiaohongshu / Reddit / WeChat-OA scraping (ToS exposure + VPN unreliability)
- Automated outbound messaging (WhatsApp ToS risk in particular)

---

## 3. Schema — `tutoring_leads`

Migration `scripts/setup_tutoring_leads.sql`, applied manually to Supabase via SQL Editor (matching the existing `setup_supabase.sql` pattern).

```sql
create table public.tutoring_leads (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source in ('telegram', 'manual', 'other')),
  raw_message text not null,
  parent_contact_handle text,
  student_year_group text,
  curriculum text check (curriculum in (
    'IGCSE_Edexcel','IGCSE_CIE','A-Level_Edexcel','A-Level_CIE',
    'IB','AP','American','GCSE_Combined','Other'
  )),
  target_grade text,
  budget_per_hour_usd numeric,
  timezone_offset_hours numeric,
  urgency text check (urgency in ('low','medium','high')),
  tutoring_brief_json jsonb,
  match_score integer check (match_score between 0 and 100),
  proposed_rate_usd numeric,
  proposal_text text,
  status text not null default 'new' check (status in (
    'new','low_budget_hold','out_of_scope_hold','proposal_sent',
    'reply_received','paid_first_session','lost'
  )),
  created_at timestamptz not null default now(),
  status_changed_at timestamptz not null default now()
);

create index on public.tutoring_leads (status);
create index on public.tutoring_leads (match_score desc);
create index on public.tutoring_leads (created_at desc);
```

`low_budget_hold` is set when `budget_per_hour_usd < 25` (see §6). `out_of_scope_hold` is set when curriculum is IB/AP/American/GCSE_Combined/Other. Both are visible on the dashboard and notify-only.

---

## 4. `TutoringBrief` Schema

New Pydantic model in `src/agents/models.py`. **Distinct** from `StrategicBrief` — do not unify.

```python
class TutoringBrief(BaseModel):
    student_pain_points: list[str]       # what they're struggling with
    parent_signals: list[str]            # urgency, budget language, prior tutor experience
    subject_alignment: str               # which of your topics/concepts they map to
    recommended_first_session_focus: str # what to do in the 30-min intro
    voice_warmth_target: int             # 1 (formal/academic) to 5 (warm/parental)
    red_flags: list[str]                 # e.g. "asks for DIY assignment completion"
```

LLM extraction via the existing provider cascade (`LLMScorer` providers) with the same `weight_registry` ordering. **Time-bounded**: 60-second parse deadline; on timeout the row stays `raw_message` populated with `tutoring_brief_json = null`, status `new`, score `null`, and gets retried on the next scheduler tick. No data loss.

---

## 5. Scoring Rubric (Tutoring)

Max 100, threshold 60 for auto-proposal.

| Component | Max | Logic |
|---|---|---|
| **Curriculum match** | 30 | IGCSE_Edexcel/IGCSE_CIE/A-Level_Edexcel/A-Level_CIE = 30. IB/AP/American/GCSE_Combined = 0 (out-of-scope override below the score). Other = 10. |
| **Subject match** | 25 | Pure Physics = 25. Physics + Maths = 25 (still in your wheelhouse). Pure Maths context but no Physics = 12. "Combined science", "general science" = 15. |
| **Timezone fit** | 20 | Gulf (UTC+2/+3, ±2 from Tripoli UTC+2) = 20. UK (UTC+0/+1) = 18. Singapore/HK (UTC+8) = 14. Mainland China (UTC+8) = 12. Other = 8. |
| **Budget** | 15 | £50+/hr ($63+) = 15. £35-50/hr ($45-63) = 12. £25-35/hr ($32-45) = 8. Below £25/hr = auto-`low_budget_hold`, score 0 on this axis. |
| **Urgency** | 10 | Exam within 8 weeks = 10. 8-16 weeks = 7. 16+ weeks = 4. Unknown = 2. |

**Gate rule:** IF curriculum in (IB, AP, American, GCSE_Combined, Other) THEN set `status = out_of_scope_hold` regardless of total score. Visible on dashboard, but no auto-proposal.

**Conversion:** All budget thresholds use USD; stored as `budget_per_hour_usd` from ingestion. Proposal copy uses local currency (£ for UK, AED for UAE, etc. — derived from country if present in raw message, otherwise leave as USD).

---

## 6. Proposal Generator — `src/generators/tutoring_proposal.py`

New file. Mirrors `cover_letter.py` provider cascade and `__LLM` / `__fallback` filename tagging.

**Persona source:** `data/profile_tutoring.json` (new file).

**Voice target scaling:** prompt tunes register by `voice_warmth_target`:

- 1-2: formal, "Dear Parent / Student"
- 3: standard warm-professional, this is the default
- 4-5: noticeably warmer, mentions PGCEi work with adolescents

**Structure (200-300 words):**
1. Acknowledge parent's pain point by phrasing (cite one `student_pain_points` item)
2. Name the curriculum + grade context briefly
3. One sentence on what you'd cover in the free 30-min intro (from `recommended_first_session_focus`)
4. Mention free intro session, "no charge, no obligation" — repeated twice (Gulf-parent trust)
5. One concrete past-style result framing (not invented testimonials — *indicative* outcomes, e.g. "in my classroom, students with this exact topic typically move from a C to a B+ over 6-8 weeks")
6. CTA: pick a time via WhatsApp/preferred channel, mention response time (24h)

**Fallback** (when all LLM providers fail): template generated by string-formatting the brief fields, no LLM call. Files tagged `__LLM` for LLM-generated, `__fallback` for template.

**Notification:** if `match_score >= 60` and curriculum is in-scope, write proposal, save file to `data/cover_letters/tutoring_<id>_<LLM|fallback>.txt`, set status `proposal_sent`, Telegram-notify with proposal text inline (not as attachment — Telegram bots can't attach .txt reliably and copy-paste is faster on mobile).

---

## 7. parent-facing Blurb — `data/profile_tutoring.json`

```json
{
  "headline": "Online IGCSE & A-Level Physics tutor based in Tripoli",
  "blurb": "Hi — I'm Mahmoud. I teach IGCSE and A-Level Physics to international school students, with a focus on Pearson Edexcel. I'm currently completing my PGCEi (international PGCE) through Liverpool John Moores University while teaching full-time at a registered British examination centre in Tripoli. My lessons are structured around your exam board, with model-led problem solving and required-practical drill where it actually moves grades. The first 30 minutes are always free — no charge, no obligation — so we can both see whether I'm a good fit before you commit.",
  "languages": ["English", "Arabic"],
  "subjects": ["Physics"],
  "curricula": ["IGCSE", "A-Level"],
  "exam_boards": ["Pearson Edexcel"],
  "intro_session_minutes": 30,
  "intro_session_free": true,
  "rate_band_usd_per_hour": "35-60",
  "response_sla_hours": 24,
  "preferred_contact": "WhatsApp / Telegram"
}
```

Note: school-job profile (`data/profile.json`, pure-Physics positioning
with leadership preference) is **separate** from this tutoring profile.
See AGENTS.md §5 for the scorer wiring; AGENTS.md also notes the
discrepancy was resolved 2026-06-30.

Editable without code changes; generator reads at startup.

---

## 8. Workflow

```
Parent message
    ↓
[Telegram bot OR /manual-lead form]
    ↓
INSERT tutoring_leads (status='new', raw_message=...)
    ↓
[APScheduler job every 15 min]
    ↓
SELECT * WHERE status='new'
    ↓
For each: parse with LLM (60s deadline) → tutoring_brief_json, fields, score
    ↓ IF score >= 60 AND in_scope
    ↓ generate proposal → write file → status='proposal_sent', proposal_text stored
    ↓ Telegram-notify you with summary + proposal text inline
    ↓ IF not in_scope OR score < 60 OR budget < 25
    ↓ status = out_of_scope_hold / low_budget_hold (score still stored, visible)
    ↓
You copy-paste proposal into WhatsApp / email
    ↓
You flip status manually via:
    - Telegram bot reply: `/status <lead_id> reply_received` or `paid_first_session` or `lost`
    - Or dashboard row action menu
    ↓
Status updates persist; status_changed_at refreshes
```

Scheduler runs as a sibling to the existing `daily_run` pipeline. Same systemd unit, additional `cron`-like APScheduler trigger every 15 minutes on the new job. Budget ~3-5s per lead parse, so 15-min cadence is safe.

---

## 9. Status Update Endpoint

`POST /api/leads/<id>/status` — mutating.

Auth: same `x-admin-token` OR localhost pattern as existing pipeline mutators (no new auth surface).

Body: `{ "status": "reply_received" | "paid_first_session" | "lost" }`.

Server validates, updates row, returns updated row.

**Telegram bot command wire-up:** long-polling bot (no webhook — local-only) reads `/status` reply on the configured permitted chat ID, parses lead_id from message (latest N messages, or quoted reply), hits the endpoint over localhost.

---

## 10. What is **OUT** of v1

| Feature | Reason | Earliest revisit |
|---|---|---|
| Xiaohongshu / WeChat-OA / Reddit scanning | ToS + VPN reliability | v2 |
| Preply / Spires / TutorChase inbox polling | Auth-gated, rate-limited, fragile | v2 |
| Automated outbound | WhatsApp ToS risk | never (or v3 with explicit user opt-in) |
| Multi-currency conversion in proposal copy | Nice-to-have, hand-derive from country | v1.5 (cosmetic) |
| Recurring-session tracking post-paid | Revenue model unclear until you have 1 paid student | post-first-paid |
| Profile blurb A/B testing | Premature | post-5-clients |
| Curriculum expansion (IB, AP, American) | Different exam technique, wrong-proposal cost | v2 (post-5-IGCSE/A-Level closes) |

---

## 11. Success Metric

**Primary:** count where `status = 'paid_first_session'` per calendar month.
**Leading indicator:** `status = 'proposal_sent'` per week (with weekly `status='reply_received'` count as a 3-day lag indicator).
**Guardrails:** `out_of_scope_hold` rate < 40% of all leads (else intake form fields need fixing); `low_budget_hold` rate < 25% (else wrong market).

Dashboard `/` page adds a tile row at top showing: `New | Proposal sent | Reply received | Paid first session | Lost` (current month count).

---

## 12. British English Audit

Final review pass checks: standardise, programme, labelling, colour, maths, behaviour, organised, optimised, organisation, optimisation, sceptical, catalogue. Enforced by:

- Code comments + log messages
- Dashboard copy (header, button labels, modal body)
- Telegram notify copy
- Proposal generator output
- Profile blurb already in British English ("syllabus", "programme-quality")

---

## 13. Open Questions / Defaults Locked

| | Default I chose | Override path |
|---|---|---|
| Budget threshold | £25/hr floor (≈ $32 USD) | edit `TUTORING_MIN_RATE_USD` in `.env` |
| Intro session length | 30 min | edit `data/profile_tutoring.json` |
| In-scope curricula | IGCSE + A-Level (Edexcel + CIE) | edit `TUTORING_IN_SCOPE_CURRICULA` in `.env` |
| Auto-proposal threshold | score ≥ 60 | edit `TUTORING_PROPOSAL_SCORE_THRESHOLD` in `.env` |
| Scheduler cadence | 15 min | edit `TUTORING_PARSE_INTERVAL_MIN` in `.env` |
| LLM parse deadline | 60 s | edit `TUTORING_PARSE_TIMEOUT_S` in `.env` |

All five settings land in `.env` with sane defaults; user-readable values, no code change to tune.

---

**Next step:** migrate schema; build `TutoringBrief` + scorer + generator; wire Telegram bot; build dashboard table + manual-entry form. Each chunk ships independently and the institutional pipeline stays untouched until the user explicitly tests the new branch.

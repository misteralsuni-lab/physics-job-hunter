-- ============================================================================
-- Tutoring Leads table (Dual-Pathway v1)
-- Apply manually via Supabase SQL Editor, matching setup_supabase.sql pattern.
-- Schema is wiped on Supabase project pause/resume; rerun if needed.
-- ============================================================================

create table if not exists public.tutoring_leads (
  id uuid default gen_random_uuid() primary key,

  -- Source / intake
  source text not null default 'manual'
    check (source in ('telegram', 'manual', 'other')),
  raw_message text not null,

  -- LLM-extracted fields (nullable until parsed)
  parent_contact_handle text,
  student_year_group text,
  curriculum text
    check (curriculum in (
      'IGCSE_Edexcel','IGCSE_CIE',
      'A-Level_Edexcel','A-Level_CIE',
      'IB','AP','American','GCSE_Combined','Other'
    )),
  target_grade text,
  budget_per_hour_usd numeric,
  timezone_offset_hours numeric,
  urgency text check (urgency in ('low','medium','high')),
  tutoring_brief_json jsonb,

  -- Scoring + proposal
  match_score integer check (match_score between 0 and 100),
  proposed_rate_usd numeric,
  proposal_text text,

  -- Lifecycle: see docs/dual-pathway.md §6
  status text not null default 'new'
    check (status in (
      'new',
      'low_budget_hold',
      'out_of_scope_hold',
      'proposal_sent',
      'reply_received',
      'paid_first_session',
      'lost'
    )),

  created_at timestamptz not null default now(),
  status_changed_at timestamptz not null default now()
);

create index if not exists idx_tutoring_leads_status on public.tutoring_leads(status);
create index if not exists idx_tutoring_leads_score  on public.tutoring_leads(match_score desc);
create index if not exists idx_tutoring_leads_created on public.tutoring_leads(created_at desc);

-- ----------------------------------------------------------------------------
-- Auto-refresh status_changed_at on UPDATE
-- ----------------------------------------------------------------------------
create or replace function public.tutoring_leads_touch_status_changed_at()
returns trigger
language plpgsql
as $$
begin
  if new.status is distinct from old.status then
    new.status_changed_at := now();
  end if;
  return new;
end;
$$;

drop trigger if exists trg_tutoring_leads_status_changed_at on public.tutoring_leads;
create trigger trg_tutoring_leads_status_changed_at
  before update on public.tutoring_leads
  for each row execute function public.tutoring_leads_touch_status_changed_at();

-- ----------------------------------------------------------------------------
-- Row-Level Security (RLS)
-- Service-role key bypasses RLS by design; this guard exists so a leaked
-- anon key doesn't expose parent contact handles.
-- ----------------------------------------------------------------------------
alter table public.tutoring_leads enable row level security;

-- No policies = anon/authenticated cannot read or write.
-- Service-role (used by the Python pipeline and the Next.js server route
-- handlers via SUPABASE_SERVICE_ROLE_KEY) bypasses RLS.

-- ----------------------------------------------------------------------------
-- Optional: view combining both pathways for the dashboard top-tile counts.
-- Created conditionally so apply-twice is safe.
-- ----------------------------------------------------------------------------
create or replace view public.pathway_counts_current_month as
select
  'institutional'           as pathway,
  count(*) filter (where score is not null)        as scored_total,
  count(*) filter (where notified = true)          as notified_total,
  count(*) filter (where created_at >= date_trunc('month', now())) as new_this_month
from public.job_listings
union all
select
  'tutoring'                as pathway,
  count(*) filter (where match_score is not null)  as scored_total,
  count(*) filter (where status in ('proposal_sent','reply_received','paid_first_session')) as notified_total,
  count(*) filter (where created_at >= date_trunc('month', now())) as new_this_month
from public.tutoring_leads;

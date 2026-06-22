-- ============================================================================
-- Tutoring Leads table — core only (no cross-pathway view)
-- Apply via Supabase SQL Editor. Idempotent. RLS enabled.
--
-- NOTE — Original `setup_tutoring_leads.sql` also defines an optional view
-- `pathway_counts_current_month` over both `public.job_listings` and
-- `public.tutoring_leads`. That view is intentionally dropped here: if the
-- institutional pipeline's columns differ or the view creation fails,
-- the entire transaction reverts and the table itself never commits.
-- Once the core migration succeeds, the view can be re-attempted in a
-- separate SQL Editor run after both underlying tables are confirmed to
-- exist with the documented columns (score, notified, created_at).
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

  -- Lifecycle: see docs/dual-pathway.md
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

alter table public.tutoring_leads enable row level security;

-- If the previous full version of this script partially committed and left
-- an orphaned trigger/function name, the drop+create above fully replaces it.
-- Confirm with: SELECT to_regclass('public.tutoring_leads');

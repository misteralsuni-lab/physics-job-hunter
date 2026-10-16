create table if not exists job_listings (
  id uuid default gen_random_uuid() primary key,
  url text unique not null,
  title text not null,
  school text,
  country text,
  city text,
  curriculum text[] default '{}',
  subject text[] default '{}',
  salary_range text,
  visa_sponsorship boolean,
  housing_allowance boolean,
  closing_date date,
  source text,
  raw_json jsonb,
  score integer,
  score_reasoning text,
  notified boolean default false,
  created_at timestamptz default now()
);

create index if not exists idx_job_listings_score on job_listings(score);
create index if not exists idx_job_listings_notified on job_listings(notified);
create index if not exists idx_job_listings_source on job_listings(source);
create index if not exists idx_job_listings_created on job_listings(created_at);

-- ---------------------------------------------------------------------------
-- last_seen: when the posting was last present on its source board.
--
-- Distinct from created_at (first time we ever saw it).  A posting can sit on
-- TES for months with the same URL; last_seen is what lets us tell "still
-- listed" from "vanished from the board", which is the only real proxy for
-- "applications closed" available — 96% of rows have closing_date IS NULL and
-- TES's payload carries no date field at all.
--
-- Safe to re-run.  src/storage/supabase_client.py:upsert_jobs() retries
-- without this column if it is absent, so the pipeline keeps working either
-- way.
-- ---------------------------------------------------------------------------
alter table job_listings add column if not exists last_seen timestamptz default now();
create index if not exists idx_job_listings_last_seen on job_listings(last_seen);

-- ===========================================================================
-- Campaign prospecting store (proactive target-school discovery)
-- Mirrors the job_listings workflow but is vacancy-independent. Schools are
-- discovered via radial web search, verified, scored and tiered. List-type
-- columns use text[] (do NOT assign a scalar string — that crashed the old
-- campaign run with `malformed array literal: "Other"`).
-- ===========================================================================
create table if not exists campaign_prospects (
  id uuid default gen_random_uuid() primary key,
  campaign_id text not null,
  school_name text not null,
  location text,
  normalized_key text not null,
  latitude double precision,
  longitude double precision,
  distance_km double precision,
  ring integer,
  pearson_offerings text[] default '{}',
  lane text,
  visa integer default 0,
  career integer default 0,
  competition integer default 0,
  location_score integer default 0,
  curriculum_score integer default 0,
  campaign_score integer default 0,
  tier text,
  category_f boolean default false,
  evidence_urls text[] default '{}',
  confidence text default 'low',
  contact_strategy text,
  outreach_email_path text,
  research_brief jsonb,
  created_at timestamptz default now(),
  unique (campaign_id, normalized_key)
);

create index if not exists idx_campaign_prospects_campaign on campaign_prospects(campaign_id);
create index if not exists idx_campaign_prospects_score on campaign_prospects(campaign_score);
create index if not exists idx_campaign_prospects_tier on campaign_prospects(tier);
create index if not exists idx_campaign_prospects_key on campaign_prospects(campaign_id, normalized_key);

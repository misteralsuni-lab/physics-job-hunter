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

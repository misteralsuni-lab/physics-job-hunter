#!/usr/bin/env python3
"""
scripts/migrate_tutoring_leads.py
------------------------------------------------------------------------
Idempotent, safe schema migration for `public.tutoring_leads`.
Connects directly to PostgreSQL via the DATABASE_URL env var.
Wraps everything in safe syntax (CREATE … IF NOT EXISTS / DO $$ EXCEPTION …)
so the script can be rerun without causing errors.

After successful execution it issues:
    NOTIFY pgrst, 'reload schema';
to clear the PostgREST schema cache.
------------------------------------------------------------------------
"""
from __future__ import annotations

import os
import sys
import logging

import psycopg2
from psycopg2 import sql as psql

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("migrate_tutoring_leads")

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS public.tutoring_leads (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    source text NOT NULL DEFAULT 'manual'
        CHECK (source IN ('telegram', 'manual', 'other')),
    raw_message text NOT NULL,
    parent_contact_handle text,
    student_year_group text,
    curriculum text
        CHECK (curriculum IN (
            'IGCSE_Edexcel','IGCSE_CIE',
            'A-Level_Edexcel','A-Level_CIE',
            'IB','AP','American','GCSE_Combined','Other'
        )),
    target_grade text,
    budget_per_hour_usd numeric,
    timezone_offset_hours numeric,
    urgency text CHECK (urgency IN ('low','medium','high')),
    tutoring_brief_json jsonb,
    match_score integer CHECK (match_score BETWEEN 0 AND 100),
    proposed_rate_usd numeric,
    proposal_text text,
    status text NOT NULL DEFAULT 'new'
        CHECK (status IN (
            'new',
            'low_budget_hold',
            'out_of_scope_hold',
            'proposal_sent',
            'reply_received',
            'paid_first_session',
            'lost'
        )),
    created_at timestamptz NOT NULL DEFAULT now(),
    status_changed_at timestamptz NOT NULL DEFAULT now()
);

-- Idempotent indexes via DO $$ … EXCEPTION WHEN duplicate_object …
DO $$ BEGIN
    CREATE INDEX idx_tutoring_leads_status ON public.tutoring_leads(status);
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Index idx_tutoring_leads_status already exists, skipping.';
END $$;

DO $$ BEGIN
    CREATE INDEX idx_tutoring_leads_score ON public.tutoring_leads(match_score DESC);
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Index idx_tutoring_leads_score already exists, skipping.';
END $$;

DO $$ BEGIN
    CREATE INDEX idx_tutoring_leads_created ON public.tutoring_leads(created_at DESC);
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Index idx_tutoring_leads_created already exists, skipping.';
END $$;

-- Touch trigger for status_changed_at
CREATE OR REPLACE FUNCTION public.tutoring_leads_touch_status_changed_at()
RETURNS trigger
LANGUAGE plpgsql
AS $func$
BEGIN
    IF new.status IS DISTINCT FROM old.status THEN
        new.status_changed_at := now();
    END IF;
    RETURN new;
END;
$func$;

DO $$ BEGIN
    CREATE TRIGGER trg_tutoring_leads_status_changed_at
        BEFORE UPDATE ON public.tutoring_leads
        FOR EACH ROW
        EXECUTE FUNCTION public.tutoring_leads_touch_status_changed_at();
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Trigger trg_tutoring_leads_status_changed_at already exists, skipping.';
END $$;

-- Row-Level Security (RLS)
ALTER TABLE public.tutoring_leads ENABLE ROW LEVEL SECURITY;

-- Clear PostgREST schema cache
NOTIFY pgrst, 'reload schema';
""".strip()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        log.error("Environment variable %s is not set.", name)
        sys.exit(1)
    return value


def run_migration(dsn: str) -> None:
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        log.info("Executing tutoring_leads migration …")
        cur.execute(MIGRATION_SQL)
        log.info("Migration complete — notified 'pgrst, reload schema'.")
    finally:
        cur.close()
        conn.close()


def main() -> None:
    dsn = require_env("DATABASE_URL")
    log.info("Connecting to database …")
    run_migration(dsn)
    log.info("Done.")


if __name__ == "__main__":
    main()

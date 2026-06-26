// Shared TypeScript types for the Physics Job Hunter front end.
//
// These mirror the `job_listings` Supabase table defined in
// /scripts/setup_supabase.sql at the repo root. They are deliberately
// permissive about nullability because the scrapers do not populate every
// column for every job.

export interface Job {
  id: string;
  url: string;
  title: string;
  school: string | null;
  country: string | null;
  city: string | null;
  curriculum: string[];
  curriculum_board: string | null;
  subject: string[];
  salary_range: string | null;
  visa_sponsorship: boolean | null;
  housing_allowance: boolean | null;
  closing_date: string | null; // ISO date (YYYY-MM-DD) or null
  source: string | null;
  score: number | null;
  score_reasoning: string | null;
  notified: boolean | null;
  created_at: string; // ISO timestamp
}

/** Shape returned by the jobs list route handler (Phase 3). */
export interface JobListResponse {
  jobs: Job[];
  total: number;
  page: number;
  pageSize: number;
  /** Present when Supabase is unreachable; the UI degrades gracefully. */
  error: string | null;
}

/** Distinct filter values used to populate the jobs table dropdowns. */
export interface JobFilterOptions {
  sources: string[];
  countries: string[];
  curriculum_boards: string[];
  error: string | null;
}

/** Score band derived from the 0-100 LLM rubric. */
export type ScoreBand = "high" | "mid" | "low" | "none";

/** Map a numeric score to a semantic band for colour coding. */
export function scoreBand(score: number | null): ScoreBand {
  if (score === null || score === undefined) return "none";
  if (score >= 70) return "high";
  if (score >= 40) return "mid";
  return "low";
}

/** Sorting keys supported by the jobs table. */
export type JobSortKey =
  | "score"
  | "created_at"
  | "closing_date"
  | "title"
  | "school"
  | "country";

export type SortDirection = "asc" | "desc";

// The curriculum_board field is stored inside the JSONB raw_json column.
// We select it via a Supabase JSONB path query (->> in PostgREST).

export interface JobFilters {
  source: string | null;
  country: string | null;
  curriculum_board: string | null;
  scoreMin: number | null;
  scoreMax: number | null;
  notified: boolean | null;
  search: string;
}

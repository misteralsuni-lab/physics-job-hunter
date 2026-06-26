// GET /api/jobs — paginated, filtered list of scored job listings.
//
// Queries the Supabase `job_listings` table using the server-only client. The
// service-role key never leaves the server; the response is plain JSON.
// Mirrors the Python back end's graceful-degradation philosophy: if Supabase
// is unreachable we return HTTP 200 with an empty page and an `error` field so
// the UI can render a friendly message instead of crashing.
import { NextRequest, NextResponse } from "next/server";
import { getSupabaseServer, isSupabaseConfigured } from "@/lib/supabase/server";
import type { Job, JobListResponse } from "@/lib/types/job";
import type { JobSortKey } from "@/lib/types/job";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const SORT_KEYS = new Set<JobSortKey>([
  "score",
  "created_at",
  "closing_date",
  "title",
  "school",
  "country",
]);

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;

  const page = clampInt(params.get("page") ?? "1", 1, 1, 1000);
  const pageSize = clampInt(params.get("pageSize") ?? "25", 25, 1, 100);
  const source = params.get("source") || null;
  const country = params.get("country") || null;
  const curriculumBoard = params.get("curriculum_board") || null;
  const minScore = parseIntRange(params.get("minScore"), 0, 100);
  const maxScore = parseIntRange(params.get("maxScore"), 0, 100);
  const notified = params.get("notified");
  const q = (params.get("q") || "").trim();
  const sortKey = parseSortKey(params.get("sort"));
  const sortDir = params.get("dir") === "asc" ? "asc" : "desc";

  const empty: JobListResponse = {
    jobs: [],
    total: 0,
    page,
    pageSize,
    error: null,
  };

  if (!isSupabaseConfigured()) {
    return NextResponse.json<JobListResponse>({
      ...empty,
      error: "Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.",
    });
  }

  try {
    const supabase = getSupabaseServer();

    // Build the count query (filters applied, no range).
    let countQuery = supabase.from("job_listings").select("*", { count: "exact", head: true });
    countQuery = applyFilters(countQuery, { source, country, curriculum_board: curriculumBoard, minScore, maxScore, notified, q });

    const { count, error: countError } = await countQuery;
    if (countError) throw countError;
    const total = count ?? 0;

    // Build the data query with sorting + pagination. Unscored rows sort last
    // when ordering by score so the dashboard leads with strong matches.
    const ascending = sortDir === "asc";
    let dataQuery = supabase
      .from("job_listings")
      .select("*")
      .order(sortKey, { ascending, nullsFirst: false });
    dataQuery = applyFilters(dataQuery, { source, country, curriculum_board: curriculumBoard, minScore, maxScore, notified, q });
    dataQuery = dataQuery.range((page - 1) * pageSize, page * pageSize - 1);

    const { data, error: dataError } = await dataQuery;
    if (dataError) throw dataError;

    // Extract curriculum_board from raw_json JSONB for each row.
    const rows = (data ?? []) as (Record<string, unknown> & { raw_json?: Record<string, unknown> })[];
    const jobs = rows.map((row) => {
      const raw = row.raw_json ?? {};
      const curriculumBoard = typeof raw.curriculum_board === "string" ? raw.curriculum_board : null;
      return { ...row, curriculum_board: curriculumBoard } as unknown as Job;
    });

    return NextResponse.json<JobListResponse>({
      jobs,
      total,
      page,
      pageSize,
      error: null,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error contacting Supabase.";
    return NextResponse.json<JobListResponse>({
      ...empty,
      error: `Could not reach Supabase: ${message}`,
    });
  }
}

interface FilterArgs {
  source: string | null;
  country: string | null;
  curriculum_board: string | null;
  minScore: number | null;
  maxScore: number | null;
  notified: string | null;
  q: string;
}

// Apply the shared filter set to either a count (head) or data query builder.
// The PostgREST filter methods are chainable so this works for both shapes.
function applyFilters<T>(builder: T, args: FilterArgs): T {
  let b = builder as unknown as {
    eq?: (col: string, val: unknown) => typeof b;
    gte?: (col: string, val: number) => typeof b;
    lte?: (col: string, val: number) => typeof b;
    or?: (filt: string) => typeof b;
    ilike?: (col: string, pat: string) => typeof b;
  };
  if (args.source) b = b.eq!("source", args.source);
  if (args.country) b = b.eq!("country", args.country);
  if (args.curriculum_board) b = b.eq!("raw_json->>curriculum_board", args.curriculum_board);
  if (args.minScore !== null) b = b.gte!("score", args.minScore);
  if (args.maxScore !== null) b = b.lte!("score", args.maxScore);
  if (args.notified === "true") b = b.eq!("notified", true);
  if (args.notified === "false") b = b.eq!("notified", false);
  if (args.q) {
    const term = args.q.replace(/[%_]/g, (m) => `\\${m}`);
    b = b.or!(
      `title.ilike.%${term}%,school.ilike.%${term}%,country.ilike.%${term}%,city.ilike.%${term}%`,
    );
  }
  return b as unknown as T;
}

function clampInt(
  raw: string | null,
  fallback: number,
  min: number,
  max: number,
): number {
  if (raw === null || raw === "") return fallback;
  const n = Number.parseInt(raw, 10);
  if (Number.isNaN(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

function parseIntRange(
  raw: string | null,
  min: number,
  max: number,
): number | null {
  if (raw === null || raw === "") return null;
  const n = Number.parseInt(raw, 10);
  if (Number.isNaN(n)) return null;
  return Math.min(max, Math.max(min, n));
}

function parseSortKey(raw: string | null): JobSortKey {
  if (raw && SORT_KEYS.has(raw as JobSortKey)) return raw as JobSortKey;
  return "score";
}

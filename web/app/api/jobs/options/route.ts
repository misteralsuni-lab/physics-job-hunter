// GET /api/jobs/options — distinct filter values for the dashboard dropdowns.
//
// Returns the unique sources and countries present in the `job_listings` table.
// If Supabase is unreachable an error field is returned alongside empty arrays
// so the dashboard can degrade gracefully.
import { NextResponse } from "next/server";
import { getSupabaseServer, isSupabaseConfigured } from "@/lib/supabase/server";
import type { JobFilterOptions } from "@/lib/types/job";

export const dynamic = "force-dynamic";

export async function GET() {
  const empty: JobFilterOptions = { sources: [], countries: [], curriculum_boards: [], error: null };

  if (!isSupabaseConfigured()) {
    return NextResponse.json<JobFilterOptions>({
      ...empty,
      error: "Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.",
    });
  }

  try {
    const supabase = getSupabaseServer();

    const [sourceResult, countryResult, boardResult] = await Promise.all([
      supabase.from("job_listings").select("source").order("source").neq("source", null),
      supabase.from("job_listings").select("country").order("country").neq("country", null),
      supabase.from("job_listings").select("raw_json->>curriculum_board").not("raw_json->>curriculum_board", "is", null),
    ]);

    if (sourceResult.error) throw sourceResult.error;
    if (countryResult.error) throw countryResult.error;
    if (boardResult.error) throw boardResult.error;

    const sources = [
      ...new Set((sourceResult.data ?? []).map((row) => row.source).filter(Boolean)),
    ].sort((a, b) => a.localeCompare(b)) as string[];
    const countries = [
      ...new Set((countryResult.data ?? []).map((row) => row.country).filter(Boolean)),
    ].sort((a, b) => a.localeCompare(b)) as string[];
    const curriculumBoards = [
      ...new Set(
        (boardResult.data ?? [] as Record<string, unknown>[])
          .map((row) => Object.values(row)[0] as string)
          .filter(Boolean),
      ),
    ].sort((a: string, b: string) => a.localeCompare(b)) as string[];

    return NextResponse.json<JobFilterOptions>({ sources, countries, curriculum_boards: curriculumBoards, error: null });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error contacting Supabase.";
    return NextResponse.json<JobFilterOptions>({
      ...empty,
      error: `Could not reach Supabase: ${message}`,
    });
  }
}

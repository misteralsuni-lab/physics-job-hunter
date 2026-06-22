// GET /api/leads — paginated, filtered list of tutoring leads.
// Mirror of /api/jobs but for the `tutoring_leads` table.
//
// Filters (query params):
//   ?status=proposal_sent,paid_first_session   (comma-separated)
//   ?limit=100 (default)
//   ?offset=0
//
// Response:
//   { "rows": [...], "total": <approx count> }
import { NextRequest, NextResponse } from "next/server";
import { getSupabaseServer } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

const DEFAULT_LIMIT = 100;
const MAX_LIMIT = 500;

export async function GET(request: NextRequest) {
  try {
    const supabase = getSupabaseServer();
    const { searchParams } = new URL(request.url);
    const statusParam = searchParams.get("status");
    const limit = Math.min(
      MAX_LIMIT,
      Math.max(1, parseInt(searchParams.get("limit") ?? String(DEFAULT_LIMIT), 10) || DEFAULT_LIMIT),
    );
    const offset = Math.max(0, parseInt(searchParams.get("offset") ?? "0", 10) || 0);

    let query = supabase
      .from("tutoring_leads")
      .select("*", { count: "estimated" })
      .order("created_at", { ascending: false })
      .range(offset, offset + limit - 1);

    if (statusParam) {
      const statuses = statusParam
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      if (statuses.length === 1) {
        query = query.eq("status", statuses[0]);
      } else if (statuses.length > 1) {
        query = query.in("status", statuses);
      }
    }

    const { data, count, error } = await query;
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 502 });
    }
    return NextResponse.json({ rows: data ?? [], total: count ?? 0 });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Unknown error" },
      { status: 500 },
    );
  }
}

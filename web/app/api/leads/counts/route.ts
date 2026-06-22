// GET /api/leads/counts — top-tile counts for the dashboard.
// Returns: { new, proposal_sent, reply_received, paid_first_session, lost }
// All counts are current-calendar-month (per docs/dual-pathway.md §11).
import { NextResponse } from "next/server";
import { getSupabaseServer } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

const BUCKETS: ReadonlyArray<string> = [
  "new",
  "proposal_sent",
  "reply_received",
  "paid_first_session",
  "lost",
];

const BUCKET_SET = new Set<string>(BUCKETS);

export async function GET() {
  try {
    const supabase = getSupabaseServer();
    const monthStart = new Date();
    monthStart.setUTCDate(1);
    monthStart.setUTCHours(0, 0, 0, 0);
    const monthStartIso = monthStart.toISOString();

    const { data, error } = await supabase
      .from("tutoring_leads")
      .select("status")
      .gte("created_at", monthStartIso);
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 502 });
    }

    const counts: Record<string, number> = {};
    for (const b of BUCKETS) counts[b] = 0;
    for (const row of data ?? []) {
      const s = (row as { status: string }).status;
      if (BUCKET_SET.has(s)) {
        counts[s] = (counts[s] ?? 0) + 1;
      }
    }
    return NextResponse.json(counts);
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Unknown error" },
      { status: 500 },
    );
  }
}

// Lead status mutation endpoints.
//   POST /api/leads/<id>/status            — flip status
//   GET  /api/leads/<id>/proposal.txt      — download proposal as plain text
//
// Both gated by the same admin-token / localhost guard as the pipeline mutators.
import { NextRequest, NextResponse } from "next/server";
import { authorise } from "@/lib/api/guards";
import { getSupabaseServer } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

const VALID_STATUSES: ReadonlySet<string> = new Set([
  "new",
  "low_budget_hold",
  "out_of_scope_hold",
  "proposal_sent",
  "reply_received",
  "paid_first_session",
  "lost",
]);

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
) {
  const auth = authorise(request);
  if (!auth.ok) return auth.response;

  let payload: { status?: string };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: "Body must be JSON." }, { status: 400 });
  }
  const next = (payload.status ?? "").trim();
  if (!VALID_STATUSES.has(next)) {
    return NextResponse.json(
      {
        error: `Invalid status. Must be one of: ${Array.from(VALID_STATUSES).join(", ")}`,
      },
      { status: 400 },
    );
  }

  try {
    const supabase = getSupabaseServer();
    const { data, error } = await supabase
      .from("tutoring_leads")
      .update({ status: next })
      .eq("id", params.id)
      .select()
      .single();
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 502 });
    }
    if (!data) {
      return NextResponse.json({ error: "Lead not found." }, { status: 404 });
    }
    return NextResponse.json({ ok: true, lead: data });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Unknown error" },
      { status: 500 },
    );
  }
}

export async function GET(
  _request: NextRequest,
  { params }: { params: { id: string } },
) {
  const auth = authorise(_request);
  if (!auth.ok) return auth.response;

  try {
    const supabase = getSupabaseServer();
    const { data, error } = await supabase
      .from("tutoring_leads")
      .select("proposal_text, status")
      .eq("id", params.id)
      .single();
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 502 });
    }
    if (!data) {
      return NextResponse.json({ error: "Lead not found." }, { status: 404 });
    }
    if (!data.proposal_text) {
      return NextResponse.json(
        { error: "No proposal generated yet for this lead." },
        { status: 404 },
      );
    }
    return new NextResponse(data.proposal_text, {
      status: 200,
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Disposition": `attachment; filename="proposal_${params.id}.txt"`,
      },
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Unknown error" },
      { status: 500 },
    );
  }
}

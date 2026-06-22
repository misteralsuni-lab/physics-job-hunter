// POST /api/leads — manual intake endpoint for the dashboard "Manual Lead Entry"
// form. Inserts a row into tutoring_leads. The systemd-driven parser picks it
// up on the next tutoring tick.
//
// Mutating: gated by the same admin-token / localhost guard as the pipeline
// mutators. Accepts JSON body: { "raw_message": "...", "parent_contact_handle":
// "...optional..." }
import { NextRequest, NextResponse } from "next/server";
import { authorise } from "@/lib/api/guards";
import { getSupabaseServer } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const auth = authorise(request);
  if (!auth.ok) return auth.response;

  let payload: { raw_message?: string; parent_contact_handle?: string };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: "Body must be JSON." }, { status: 400 });
  }

  const raw = (payload.raw_message ?? "").trim();
  if (!raw) {
    return NextResponse.json(
      { error: "raw_message is required and cannot be empty." },
      { status: 400 },
    );
  }
  if (raw.length > 8000) {
    return NextResponse.json(
      { error: "raw_message exceeds 8000-character limit; please truncate." },
      { status: 413 },
    );
  }

  try {
    const supabase = getSupabaseServer();
    const insert = {
      source: "manual",
      raw_message: raw,
      parent_contact_handle: payload.parent_contact_handle?.trim() || null,
      status: "new",
    };
    const { data, error } = await supabase
      .from("tutoring_leads")
      .insert(insert)
      .select()
      .single();
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 502 });
    }
    return NextResponse.json({ ok: true, lead: data });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Unknown error" },
      { status: 500 },
    );
  }
}

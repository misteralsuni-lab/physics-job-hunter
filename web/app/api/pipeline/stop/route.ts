// POST /api/pipeline/stop — stop the scheduler's systemd user service. Mutating
// endpoint: gated by the admin token / localhost guard.
import { NextRequest, NextResponse } from "next/server";
import { authorise, runSystemctl } from "@/lib/api/guards";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const auth = authorise(request);
  if (!auth.ok) return auth.response;

  const result = await runSystemctl("stop");
  if (!result.ok) {
    return NextResponse.json(
      { error: `Could not stop service: ${result.stderr.trim() || "unknown error"}` },
      { status: 502 },
    );
  }
  return NextResponse.json({ ok: true, message: "Service stopped." });
}

// POST /api/pipeline/start — arm the scheduler by starting the systemd user
// service. Mutating endpoint: gated by the admin token / localhost guard.
import { NextRequest, NextResponse } from "next/server";
import { authorise, runSystemctl } from "@/lib/api/guards";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const auth = authorise(request);
  if (!auth.ok) return auth.response;

  const result = await runSystemctl("start");
  if (!result.ok) {
    return NextResponse.json(
      { error: `Could not start service: ${result.stderr.trim() || "unknown error"}` },
      { status: 502 },
    );
  }
  return NextResponse.json({ ok: true, message: "Service started." });
}

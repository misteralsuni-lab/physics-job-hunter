// Settings API.
// GET  /api/settings — returns the current advisory settings.
// POST /api/settings — validates and persists updated advisory settings to
//                      web/config.json. This is an advisory store only; applying
//                      changes to the running scheduler requires updating the
//                      root `.env` and restarting the systemd service.
import { NextRequest, NextResponse } from "next/server";
import { readSettings, writeSettings } from "@/lib/api/settings-store";
import { authorise } from "@/lib/api/guards";

export const dynamic = "force-dynamic";

export async function GET() {
  const settings = await readSettings();
  return NextResponse.json(settings);
}

export async function POST(request: NextRequest) {
  // POST mutates advisory settings — gate behind the same auth as other
  // mutating endpoints (pipeline start/stop, manual leads, etc.).
  const auth = authorise(request);
  if (!auth.ok) return auth.response;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: "Request body must be valid JSON." },
      { status: 400 },
    );
  }

  const result = await writeSettings(body);
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: 400 });
  }

  return NextResponse.json(result.settings);
}

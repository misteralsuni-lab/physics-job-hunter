// GET /api/pipeline/logs — tail the systemd journal for the
// physics-job-hunter service. Returns the most recent N lines (default 200).
// Uses an argument array; the line count is clamped to a safe maximum.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const unit = process.env.SYSTEMD_UNIT ?? "physics-job-hunter.service";
  const requested = Number.parseInt(request.nextUrl.searchParams.get("lines") ?? "200", 10);
  const lines = Number.isNaN(requested) ? 200 : Math.min(1000, Math.max(10, requested));

  try {
    const { spawn } = await import("node:child_process");
    const stdout = await new Promise<string>((resolve, reject) => {
      const child = spawn(
        "journalctl",
        ["--user", "-u", unit, "--no-pager", "-n", String(lines)],
        { cwd: process.env.PIPELINE_CWD },
      );
      let out = "";
      let err = "";
      child.stdout.on("data", (d) => (out += d.toString()));
      child.stderr.on("data", (d) => (err += d.toString()));
      child.on("error", reject);
      child.on("close", (code) => {
        if (code === 0) resolve(out);
        else reject(new Error(err || `journalctl exited ${code}`));
      });
    });

    const lineArray = stdout.split("\n").filter((l) => l.length > 0);
    return NextResponse.json({ lines: lineArray });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Could not read journal.";
    return NextResponse.json(
      { lines: [], error: `Journal unavailable: ${message}` },
      { status: 200 },
    );
  }
}

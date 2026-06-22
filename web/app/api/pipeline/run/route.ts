// POST /api/pipeline/run — trigger an immediate, one-off pipeline run by
// spawning `python3 -m src.main` detached in the project root. Returns 202
// immediately with a run id; the pipeline takes roughly 2.5 minutes for 20 jobs
// so the caller should not block. Mutating endpoint: gated by the admin token /
// localhost guard.
//
// SECURITY: the working directory is taken from the PIPELINE_CWD env var and the
// command uses an argument array (never shell=true) so there is no injection
// surface. Output is appended to /tmp/physics-job-hunter-run.log.
import { NextRequest, NextResponse } from "next/server";
import { authorise } from "@/lib/api/guards";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const auth = authorise(request);
  if (!auth.ok) return auth.response;

  const cwd = process.env.PIPELINE_CWD ?? "/mnt/d/physics-job-hunter";
  const runId = `run_${Date.now()}`;

  try {
    const { spawn } = await import("node:child_process");
    const fs = await import("node:fs");
    const fd = await new Promise<number>((resolve, reject) => {
      fs.open("/tmp/physics-job-hunter-run.log", "a", (err, fileDescriptor) => {
        if (err) reject(err);
        else resolve(fileDescriptor);
      });
    });

    const child = spawn("python3", ["-m", "src.main"], {
      cwd,
      stdio: ["ignore", fd, fd],
      detached: true,
    });
    child.unref();
    // The child inherits its own copy of fd via stdio; close the parent's
    // copy to prevent a leak on every manual run.
    try { fs.close(fd); } catch { /* already closed or invalid — ignore */ }

    return NextResponse.json(
      { ok: true, runId, message: "Pipeline run started. Inspect logs on the Pipeline Control page." },
      { status: 202 },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "Could not spawn pipeline process.";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

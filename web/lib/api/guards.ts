// Server-only guards shared by mutating pipeline route handlers.
//
// SECURITY MODEL
// All POST endpoints that touch the scheduler or spawn the Python pipeline are
// sensitive. Access is gated by EITHER:
//   1. A shared secret: the request sends `x-admin-token` matching the
//      `ADMIN_TOKEN` environment variable, OR
//   2. Localhost fallback: if `ADMIN_TOKEN` is unset, only requests originating
//      from the loopback address (127.0.0.1 / ::1) are permitted.
//
// If neither condition holds the request is rejected with 403. This keeps the
// dashboard safe on a single-user host while still allowing a token to be
// configured for LAN access.
import { NextRequest, NextResponse } from "next/server";

/** Outcome of an authorisation check. */
export type AuthResult =
  | { ok: true }
  | { ok: false; response: NextResponse };

const LOOPBACK = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"]);

/** Authorise a mutating request. Call at the top of each POST handler. */
export function authorise(request: NextRequest): AuthResult {
  const configuredToken = process.env.ADMIN_TOKEN;

  if (configuredToken) {
    const supplied = request.headers.get("x-admin-token");
    if (supplied && supplied === configuredToken) return { ok: true };
    return {
      ok: false,
      response: NextResponse.json(
        { error: "Forbidden: a valid x-admin-token header is required." },
        { status: 403 },
      ),
    };
  }

  // No token configured — fall back to localhost-only access.
  const ip = getClientIp(request);
  if (LOOPBACK.has(ip)) return { ok: true };
  return {
    ok: false,
    response: NextResponse.json(
      {
        error:
          "Forbidden: set ADMIN_TOKEN to allow remote access, or run this request from localhost.",
      },
      { status: 403 },
    ),
  };
}

/** Extract the originating client IP, honouring the standard forwarded header. */
function getClientIp(request: NextRequest): string {
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0];
    if (first) return first.trim();
  }
  return request.ip ?? "127.0.0.1";
}

/**
 * Run a systemctl --user command safely. Uses an argument array (never a shell
 * string) so there is no injection surface. Returns a normalised result so the
 * route handlers can format JSON consistently.
 */
export async function runSystemctl(
  ...args: string[]
): Promise<{ ok: boolean; stdout: string; stderr: string; code: number | null }> {
  const unit = process.env.SYSTEMD_UNIT ?? "physics-job-hunter.service";
  const { spawn } = await import("node:child_process");
  return new Promise((resolve) => {
    const child = spawn("systemctl", ["--user", ...args, unit], {
      cwd: process.env.PIPELINE_CWD,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d.toString()));
    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.on("error", () =>
      resolve({ ok: false, stdout, stderr: stderr || "spawn error", code: null }),
    );
    child.on("close", (code) =>
      resolve({ ok: code === 0, stdout, stderr, code }),
    );
  });
}

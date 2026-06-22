// GET /api/pipeline/status — current state of the physics-job-hunter systemd
// user service. Probes `systemctl --user is-active` and `systemctl --user show`
// for the active/sub state and last start timestamp. Falls back gracefully to
// an "unknown" state when systemd is unavailable (e.g. on non-Linux hosts or
// when the user bus is not reachable).
import { NextResponse } from "next/server";
import { runSystemctl } from "@/lib/api/guards";
import type { BadgeStatus } from "@/app/components/ui/StatusBadge";

export const dynamic = "force-dynamic";

export interface PipelineStatus {
  active: boolean;
  sub: string;
  status: BadgeStatus;
  lastStart: string | null;
  error: string | null;
}

export async function GET(): Promise<NextResponse<PipelineStatus>> {
  const isActive = await runSystemctl("is-active");
  if (!isActive.ok && isActive.code !== null && isActive.code !== 0) {
    // is-active returns non-zero when the unit is inactive — that is normal.
  }

  const show = await runSystemctl("show", "-p", "ActiveState", "-p", "SubState", "-p", "ExecMainStartTimestamp");

  const props = parseShow(show.stdout || isActive.stdout);
  const activeState = (props.get("activestate") ?? "").toLowerCase();
  const subState = (props.get("substate") ?? "").toLowerCase();
  const lastStart = props.get("execmainstarttimestamp") ?? null;

  // Map systemd states onto the dashboard badge vocabulary.
  let status: BadgeStatus;
  if (activeState === "active" && subState === "running") {
    status = "running";
  } else if (activeState === "active") {
    status = "active";
  } else if (activeState === "inactive" || activeState === "failed") {
    status = activeState === "failed" ? "error" : "sleeping";
  } else {
    status = "error";
  }

  const error = !show.ok && show.stderr && activeState === ""
    ? `systemctl unavailable: ${show.stderr.trim()}`
    : null;

  return NextResponse.json<PipelineStatus>({
    active: activeState === "active",
    sub: subState || activeState || "unknown",
    status,
    lastStart,
    error,
  });
}

function parseShow(stdout: string): Map<string, string> {
  const map = new Map<string, string>();
  for (const line of stdout.split("\n")) {
    const idx = line.indexOf("=");
    if (idx > 0) {
      const key = line.slice(0, idx).toLowerCase();
      const val = line.slice(idx + 1).trim();
      map.set(key, val);
    }
  }
  return map;
}

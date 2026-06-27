"use client";

// Pipeline Control — systemd service status, manual run trigger and journal
// viewer. Polls the /api/pipeline/* route handlers for live status and logs.
// All mutating requests carry the optional x-admin-token header; when no token
// is set, the server-side guard falls back to localhost-only access.
import { useEffect, useRef, useState } from "react";
import { Workflow, Play, Square, RotateCw, Shield, FileText } from "lucide-react";
import { Button } from "@/app/components/ui/Button";
import { Card, CardHeader } from "@/app/components/ui/Card";
import { StatusBadge } from "@/app/components/ui/StatusBadge";
import { Spinner } from "@/app/components/ui/Spinner";
import { toast } from "@/app/components/ui/Toast";
import type { PipelineStatus } from "@/app/api/pipeline/status/route";

export default function PipelinePage() {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [actionLoading, setActionLoading] = useState<"start" | "stop" | "run" | null>(null);
  const [adminToken, setAdminToken] = useState("");
  const logsRef = useRef<HTMLDivElement>(null);
  // Mounted-flag guards post-unmount setStatus calls in deferred status
  // refreshes below; cleared on unmount via the cleanup closure.
  const mountedRef = useRef(true);

  // Status poll.
  useEffect(() => {
    let cancelled = false;
    async function fetchStatus() {
      try {
        const res = await fetch("/api/pipeline/status");
        const payload = (await res.json()) as PipelineStatus;
        if (!cancelled) setStatus(payload);
      } catch (err) {
        if (!cancelled) {
          setStatus({
            active: false,
            sub: "unknown",
            status: "error",
            lastStart: null,
            error: err instanceof Error ? err.message : "Could not reach pipeline API.",
          });
        }
      }
    }
    fetchStatus();
    const interval = setInterval(fetchStatus, 8000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  // Logs poll.
  useEffect(() => {
    let cancelled = false;
    async function fetchLogs() {
      try {
        const res = await fetch("/api/pipeline/logs?lines=200");
        const payload = (await res.json()) as { lines: string[]; error?: string };
        if (!cancelled) setLogs(payload.lines);
      } catch {
        if (!cancelled) setLogs([]);
      }
    }
    fetchLogs();
    const interval = setInterval(fetchLogs, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  // Auto-scroll logs to the bottom when new lines arrive.
  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [logs]);

  // Unmount: flip the mounted flag so the deferred fetch in performAction
  // becomes a no-op.  Must be the last effect to run so all other useEffect
  // cleanup closures still see ``mountedRef.current === true``.
  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  async function performAction(
    action: "start" | "stop" | "run",
    confirmMessage?: string,
  ) {
    if (confirmMessage && !window.confirm(confirmMessage)) return;
    setActionLoading(action);
    try {
      const res = await fetch(`/api/pipeline/${action}`, {
        method: "POST",
        headers: adminToken ? { "x-admin-token": adminToken } : undefined,
      });
      const payload = (await res.json()) as { ok?: boolean; message?: string; error?: string };
      if (!res.ok || payload.error) {
        toast.error(payload.error || `Failed to ${action} service.`);
      } else {
        toast.success(payload.message || `${capitalize(action)} request sent.`);
      }
      // Refresh status quickly after an action.  Guard with ``mountedRef``
      // so an unmount mid-500ms doesn't trigger React's "setState on
      // unmounted component" dev-only warning.
      setTimeout(() => {
        if (!mountedRef.current) return;
        fetch("/api/pipeline/status")
          .then((r) => r.json())
          .then(setStatus)
          .catch(() => undefined);
      }, 500);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Network error";
      toast.error(`Could not ${action}: ${message}`);
    } finally {
      setActionLoading(null);
    }
  }

  return (
    <div className="animate-fade-in space-y-6">
      <header className="flex items-center gap-3">
        <Workflow className="h-7 w-7 text-brand" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold tracking-tight md:text-2xl">
            Pipeline Control
          </h1>
          <p className="text-sm text-ink-muted">
            Monitor the scheduler, run the pipeline manually and inspect logs.
          </p>
        </div>
      </header>

      <Card>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
              Service status
            </h2>
            <div className="flex items-center gap-3">
              {status ? (
                <>
                  <StatusBadge status={status.status} />
                  <span className="text-sm text-ink-muted">
                    {status.active ? status.sub : "Stopped"}
                  </span>
                </>
              ) : (
                <Spinner label="Loading status" />
              )}
            </div>
            {status?.lastStart && (
              <p className="text-xs text-ink-faint">
                Last start: {status.lastStart}
              </p>
            )}
            {status?.error && (
              <p className="text-sm text-status-error" role="alert">
                {status.error}
              </p>
            )}
          </div>

          <div className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
              Actions
            </h2>
            <div className="flex flex-wrap gap-2">
              <Button
                icon={Play}
                loading={actionLoading === "start"}
                onClick={() => performAction("start")}
              >
                Start
              </Button>
              <Button
                variant="danger"
                icon={Square}
                loading={actionLoading === "stop"}
                onClick={() =>
                  performAction("stop", "Stop the physics-job-hunter scheduler?")
                }
              >
                Stop
              </Button>
              <Button
                variant="secondary"
                icon={RotateCw}
                loading={actionLoading === "run"}
                onClick={() =>
                  performAction("run", "Run the pipeline now? This takes around 2–3 minutes.")
                }
              >
                Run pipeline now
              </Button>
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Security token"
          description="Required for mutating endpoints when accessing remotely. Leave blank on localhost."
          icon={Shield}
        />
        <div className="flex items-center gap-2">
          <input
            type="password"
            value={adminToken}
            onChange={(e) => setAdminToken(e.target.value)}
            placeholder="ADMIN_TOKEN"
            aria-label="Admin token"
            className="min-h-tap flex-1 rounded-lg border border-line bg-surface px-3 text-sm text-ink placeholder:text-ink-faint"
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Live logs"
          description="Recent output from journalctl for the scheduler."
          icon={FileText}
        />
        <div
          ref={logsRef}
          className="h-80 overflow-y-auto rounded-lg bg-slate-950 p-3 font-mono text-xs leading-relaxed text-slate-200"
        >
          {logs.length === 0 ? (
            <p className="text-slate-500">No log entries available.</p>
          ) : (
            logs.map((line, i) => (
              <p key={i} className="break-words">
                {line}
              </p>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

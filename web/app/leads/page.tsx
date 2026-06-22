"use client";

// Tutoring Leads dashboard.
//
// Layout
// ──────────────────────────────────────────────────────────────
//   1. Top tile row: current-calendar-month counts per status
//      (per docs/dual-pathway.md §11).
//   2. Filter bar: status multi-select + free-text search across raw message.
//   3. Manual Lead Entry card: paste-box + submit. Lands as a `new` row; the
//      systemd-driven tutoring tick picks it up on the next 15-minute interval.
//   4. Lead table: paginated, with status pills and an inline status-flip
//      menu (proposal_sent → reply_received → paid_first_session → lost).
//
// British English throughout.
import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, CardHeader } from "@/app/components/ui/Card";
import { Button } from "@/app/components/ui/Button";
import { cn } from "@/lib/utils/cn";

// ---------------------------------------------------------------------------
// Types — kept aligned with the SQL schema in scripts/setup_tutoring_leads.sql
// ---------------------------------------------------------------------------

type LeadStatus =
  | "new"
  | "low_budget_hold"
  | "out_of_scope_hold"
  | "proposal_sent"
  | "reply_received"
  | "paid_first_session"
  | "lost";

interface TutoringBriefJson {
  schema_version?: number;
  brief?: {
    student_pain_points?: string[];
    parent_signals?: string[];
    subject_alignment?: string;
    recommended_first_session_focus?: string;
    voice_warmth_target?: number;
    red_flags?: string[];
  };
}

interface Lead {
  id: string;
  source: string;
  raw_message: string;
  parent_contact_handle: string | null;
  curriculum: string | null;
  timezone_offset_hours: number | null;
  budget_per_hour_usd: number | null;
  urgency: string | null;
  match_score: number | null;
  proposed_rate_usd: number | null;
  proposal_text: string | null;
  tutoring_brief_json: TutoringBriefJson | null;
  status: LeadStatus;
  created_at: string;
  status_changed_at: string;
}

interface Counts {
  new: number;
  proposal_sent: number;
  reply_received: number;
  paid_first_session: number;
  lost: number;
}

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

const STATUS_LABEL: Record<LeadStatus, string> = {
  new: "New",
  low_budget_hold: "Below budget",
  out_of_scope_hold: "Out of scope",
  proposal_sent: "Proposal sent",
  reply_received: "Reply received",
  paid_first_session: "Paid first session",
  lost: "Lost",
};

const STATUS_TONE: Record<LeadStatus, string> = {
  new:                   "bg-brand/10 text-brand",
  low_budget_hold:       "bg-status-error/10 text-status-error",
  out_of_scope_hold:     "bg-status-sleeping/10 text-status-sleeping",
  proposal_sent:         "bg-status-running/10 text-status-running",
  reply_received:        "bg-status-running/15 text-status-running",
  paid_first_session:    "bg-status-active/15 text-status-active",
  lost:                  "bg-surface-muted text-ink-muted",
};

const NEXT_STATUS: Partial<Record<LeadStatus, LeadStatus>> = {
  new: "proposal_sent",
  proposal_sent: "reply_received",
  reply_received: "paid_first_session",
  paid_first_session: "lost",
};

function fmtBudget(n: number | null) {
  return n === null ? "—" : `$${n.toFixed(0)}/hr`;
}

function fmtTz(h: number | null) {
  return h === null ? "—" : `${h >= 0 ? "+" : ""}${h}h`;
}

function excerpt(s: string, n = 140) {
  return s.length <= n ? s : s.slice(0, n - 1).trimEnd() + "…";
}

// ---------------------------------------------------------------------------
// Tile row
// ---------------------------------------------------------------------------

function CountTile({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <Card padded={false} className="flex flex-col justify-between p-4">
      <span className="text-xs font-medium uppercase tracking-wide text-ink-muted">
        {label}
      </span>
      <div className="mt-2 flex items-baseline gap-2">
        <span className={cn("text-3xl font-semibold tabular-nums", tone)}>
          {value}
        </span>
        <span className="text-xs text-ink-muted">this month</span>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Manual entry form
// ---------------------------------------------------------------------------

function ManualEntryCard({ onSubmitted }: { onSubmitted: () => void }) {
  const [open, setOpen] = useState(false);
  const [raw, setRaw] = useState("");
  const [handle, setHandle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  const reset = () => {
    setRaw("");
    setHandle("");
    setFeedback(null);
  };

  const submit = async () => {
    if (!raw.trim()) {
      setFeedback({ kind: "err", msg: "Message cannot be empty." });
      return;
    }
    setSubmitting(true);
    setFeedback(null);
    try {
      const r = await fetch("/api/leads/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_message: raw, parent_contact_handle: handle || undefined }),
      });
      const body = await r.json();
      if (!r.ok) {
        setFeedback({ kind: "err", msg: body.error ?? `HTTP ${r.status}` });
      } else {
        setFeedback({ kind: "ok", msg: "Lead queued — parsed within 15 minutes." });
        reset();
        onSubmitted();
      }
    } catch (e) {
      setFeedback({
        kind: "err",
        msg: e instanceof Error ? e.message : "Network error",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader
        title="Manual lead entry"
        description="Paste a parent message from WhatsApp / WeChat / email. The tutoring tick will parse it within the next 15 minutes."
      />
      <div className="mt-4 space-y-3">
        <button
          onClick={() => setOpen((v) => !v)}
          className="text-sm font-medium text-brand hover:underline"
          type="button"
        >
          {open ? "Hide form" : "Open form"}
        </button>
        {open && (
          <>
            <label className="block">
              <span className="block text-sm font-medium text-ink">Parent message (paste here)</span>
              <textarea
                value={raw}
                onChange={(e) => setRaw(e.target.value)}
                rows={6}
                maxLength={8000}
                placeholder="Paste the raw parent message. Mixed English / Arabic / Arabizi is fine — the parser handles it."
                className="mt-1 w-full rounded-lg border border-line bg-surface-raised p-3 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-brand"
              />
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-ink">Contact handle (optional)</span>
              <input
                value={handle}
                onChange={(e) => setHandle(e.target.value)}
                placeholder="WhatsApp number, Telegram handle, or email"
                className="mt-1 w-full rounded-lg border border-line bg-surface-raised p-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-brand"
              />
            </label>
            {feedback && (
              <p
                className={cn(
                  "text-sm",
                  feedback.kind === "ok" ? "text-status-active" : "text-status-error",
                )}
              >
                {feedback.msg}
              </p>
            )}
            <div className="flex gap-2 pt-1">
              <Button onClick={submit} disabled={submitting} loading={submitting}>
                Submit lead
              </Button>
              <Button variant="secondary" onClick={reset} disabled={submitting}>
                Clear
              </Button>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Lead table row
// ---------------------------------------------------------------------------

function LeadRow({ lead, onUpdated }: { lead: Lead; onUpdated: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [updating, setUpdating] = useState<LeadStatus | null>(null);
  const next = NEXT_STATUS[lead.status];

  const flipTo = async (target: LeadStatus) => {
    setUpdating(target);
    try {
      const r = await fetch(`/api/leads/${lead.id}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: target }),
      });
      if (r.ok) onUpdated();
    } finally {
      setUpdating(null);
    }
  };

  return (
    <>
      <tr className="border-b border-line last:border-b-0">
        <td className="p-3 align-top">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-left text-sm text-ink-muted hover:text-ink"
          >
            {excerpt(lead.raw_message, 110)}
          </button>
        </td>
        <td className="p-3 align-top text-sm text-ink">
          {lead.curriculum ?? "—"}
        </td>
        <td className="p-3 align-top text-sm tabular-nums text-ink">
          {lead.match_score ?? "—"}
        </td>
        <td className="p-3 align-top text-sm tabular-nums text-ink">
          {fmtBudget(lead.budget_per_hour_usd)}
        </td>
        <td className="p-3 align-top text-sm tabular-nums text-ink">
          {fmtTz(lead.timezone_offset_hours)}
        </td>
        <td className="p-3 align-top">
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
              STATUS_TONE[lead.status],
            )}
          >
            {STATUS_LABEL[lead.status]}
          </span>
        </td>
        <td className="p-3 align-top">
          {next ? (
            <Button
              variant="secondary"
              loading={updating === next}
              onClick={() => flipTo(next)}
              className="px-3 py-1 text-xs"
            >
              Mark {STATUS_LABEL[next]}
            </Button>
          ) : (
            <span className="text-xs text-ink-muted">—</span>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-line bg-surface-muted/40">
          <td colSpan={7} className="p-4">
            <div className="space-y-3 text-sm text-ink">
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  Raw message
                </h4>
                <pre className="whitespace-pre-wrap break-words rounded-lg border border-line bg-surface-raised p-3 text-sm">
                  {lead.raw_message}
                </pre>
              </div>
              {lead.tutoring_brief_json?.brief && (
                <div>
                  <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                    Parsed brief
                  </h4>
                  <dl className="space-y-2 rounded-lg border border-line bg-surface-raised p-3">
                    {lead.tutoring_brief_json.brief.student_pain_points && (
                      <div>
                        <dt className="font-medium">Pain points</dt>
                        <dd className="text-ink-muted">
                          {lead.tutoring_brief_json.brief.student_pain_points.join("; ")}
                        </dd>
                      </div>
                    )}
                    {lead.tutoring_brief_json.brief.subject_alignment && (
                      <div>
                        <dt className="font-medium">Subject alignment</dt>
                        <dd className="text-ink-muted">
                          {lead.tutoring_brief_json.brief.subject_alignment}
                        </dd>
                      </div>
                    )}
                    {lead.tutoring_brief_json.brief.recommended_first_session_focus && (
                      <div>
                        <dt className="font-medium">Intro session plan</dt>
                        <dd className="text-ink-muted">
                          {lead.tutoring_brief_json.brief.recommended_first_session_focus}
                        </dd>
                      </div>
                    )}
                    {lead.tutoring_brief_json.brief.red_flags &&
                      lead.tutoring_brief_json.brief.red_flags.length > 0 && (
                        <div>
                          <dt className="font-medium text-status-error">Red flags</dt>
                          <dd className="text-status-error">
                            {lead.tutoring_brief_json.brief.red_flags.join("; ")}
                          </dd>
                        </div>
                      )}
                  </dl>
                </div>
              )}
              {lead.proposal_text && (
                <div>
                  <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                    Proposal (sent)
                  </h4>
                  <pre className="whitespace-pre-wrap break-words rounded-lg border border-line bg-surface-raised p-3 text-sm">
                    {lead.proposal_text}
                  </pre>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function LeadsPage() {
  const [counts, setCounts] = useState<Counts | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [filter, setFilter] = useState<LeadStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filter !== "all") params.set("status", filter);
      params.set("limit", "200");

      const [tilesRes, listRes] = await Promise.all([
        fetch("/api/leads/counts", { cache: "no-store" }),
        fetch(`/api/leads?${params.toString()}`, { cache: "no-store" }),
      ]);
      if (!tilesRes.ok) throw new Error(`counts: HTTP ${tilesRes.status}`);
      if (!listRes.ok) throw new Error(`list: HTTP ${listRes.status}`);
      const [tiles, list] = await Promise.all([tilesRes.json(), listRes.json()]);
      setCounts(tiles);
      setLeads(list.rows ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load leads");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const filtered = useMemo(() => {
    if (!search.trim()) return leads;
    const needle = search.toLowerCase();
    return leads.filter(
      (l) =>
        l.raw_message.toLowerCase().includes(needle) ||
        (l.curriculum ?? "").toLowerCase().includes(needle),
    );
  }, [leads, search]);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-ink">Tutoring leads</h1>
        <p className="text-sm text-ink-muted">
          Inbound inquiry desk for the private-tutoring pathway. Counts reflect the
          current calendar month.
        </p>
      </header>

      {/* Tile row */}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {counts ? (
          <>
            <CountTile label="New" value={counts.new} tone="text-brand" />
            <CountTile label="Proposal sent" value={counts.proposal_sent} tone="text-status-running" />
            <CountTile label="Reply received" value={counts.reply_received} tone="text-status-running" />
            <CountTile label="Paid first session" value={counts.paid_first_session} tone="text-status-active" />
            <CountTile label="Lost" value={counts.lost} tone="text-status-sleeping" />
          </>
        ) : (
          Array.from({ length: 5 }).map((_, i) => (
            <Card key={i} padded={false} className="h-24 animate-pulse p-4" />
          ))
        )}
      </section>

      {/* Manual intake */}
      <ManualEntryCard onSubmitted={loadAll} />

      {/* Filters + table */}
      <Card padded={false} className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-line p-4 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap gap-2">
            {(
              [
                "all",
                "new",
                "proposal_sent",
                "reply_received",
                "paid_first_session",
                "low_budget_hold",
                "out_of_scope_hold",
                "lost",
              ] as const
            ).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setFilter(s)}
                className={cn(
                  "rounded-full px-3 py-1 text-sm font-medium",
                  filter === s
                    ? "bg-brand text-brand-fg"
                    : "bg-surface-muted text-ink-muted hover:bg-surface-raised",
                )}
              >
                {s === "all" ? "All" : STATUS_LABEL[s]}
              </button>
            ))}
          </div>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search raw message or curriculum"
            className="w-full rounded-lg border border-line bg-surface-raised p-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-brand md:w-72"
          />
        </div>

        {error && (
          <p className="border-b border-line bg-status-error/10 p-3 text-sm text-status-error">
            {error}
          </p>
        )}

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-surface-muted/40 text-left text-xs uppercase tracking-wide text-ink-muted">
              <tr>
                <th className="p-3">Message</th>
                <th className="p-3">Curriculum</th>
                <th className="p-3">Score</th>
                <th className="p-3">Budget</th>
                <th className="p-3">TZ</th>
                <th className="p-3">Status</th>
                <th className="p-3">Action</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-sm text-ink-muted">
                    Loading…
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-sm text-ink-muted">
                    No leads matching the current filter.
                  </td>
                </tr>
              ) : (
                filtered.map((l) => (
                  <LeadRow key={l.id} lead={l} onUpdated={loadAll} />
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

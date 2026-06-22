"use client";

// Slide-over drawer showing the full record for a selected job, including the
// LLM scoring reasoning and a link to the original posting. Traps focus and
// closes on Escape / backdrop click. Renders nothing when no job is selected.
import { useEffect, useRef } from "react";
import { X, ExternalLink, MapPin, Building2, GraduationCap, Banknote, Calendar, Bell, type LucideIcon } from "lucide-react";
import { Button } from "@/app/components/ui/Button";
import { ScoreBadge } from "./ScoreBadge";
import { Chips } from "./Chips";
import { formatBritishDate, formatBritishDateTime } from "@/lib/utils/cn";
import type { Job } from "@/lib/types/job";
import { cn } from "@/lib/utils/cn";

export interface JobDetailDrawerProps {
  job: Job | null;
  onClose: () => void;
}

export function JobDetailDrawer({ job, onClose }: JobDetailDrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!job) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [job, onClose]);

  if (!job) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Job details">
      <button
        type="button"
        aria-label="Close job details"
        onClick={onClose}
        className="absolute inset-0 bg-slate-950/40 backdrop-blur-sm"
      />
      <div
        ref={panelRef}
        tabIndex={-1}
        className={cn(
          "relative flex h-full w-full max-w-md flex-col bg-surface-raised shadow-raised",
          "animate-slide-up focus:outline-none",
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-line p-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <ScoreBadge score={job.score} />
              {job.source && (
                <span className="rounded-md bg-surface-muted px-1.5 py-0.5 text-xs font-medium text-ink-muted">
                  {job.source}
                </span>
              )}
            </div>
            <h2 className="mt-2 text-lg font-semibold leading-tight text-ink">
              {job.title}
            </h2>
            {job.school && (
              <p className="mt-0.5 text-sm text-ink-muted">{job.school}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="tap-target -mr-1 -mt-1 rounded text-ink-faint hover:bg-surface-muted"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-4">
          <Field icon={MapPin} label="Location">
            {[job.city, job.country].filter(Boolean).join(", ") || "—"}
          </Field>
          <Field icon={Building2} label="School">
            {job.school || "—"}
          </Field>
          <Field icon={GraduationCap} label="Curriculum">
            <Chips items={job.curriculum} />
          </Field>
          <Field icon={GraduationCap} label="Subject">
            <Chips items={job.subject} />
          </Field>
          <Field icon={Banknote} label="Salary range">
            {job.salary_range || "—"}
          </Field>
          <Field icon={Calendar} label="Closing date">
            {formatBritishDate(job.closing_date)}
          </Field>
          <Field icon={Bell} label="Notification status">
            {job.notified ? "Notified via Telegram and email" : "Not yet notified"}
          </Field>

          <div className="space-y-1.5">
            <h3 className="text-sm font-semibold text-ink">Scoring reasoning</h3>
            {job.score_reasoning ? (
              <p className="whitespace-pre-wrap rounded-lg bg-surface-inset p-3 text-sm leading-relaxed text-ink-muted">
                {job.score_reasoning}
              </p>
            ) : (
              <p className="text-sm text-ink-faint">
                This job has not yet been scored by the LLM rubric.
              </p>
            )}
          </div>
        </div>

        <div className="border-t border-line p-4">
          <a href={job.url} target="_blank" rel="noopener noreferrer">
            <Button variant="secondary" icon={ExternalLink} className="w-full">
              View original posting
            </Button>
          </a>
          <p className="mt-2 text-center text-xs text-ink-faint">
            Added {formatBritishDateTime(job.created_at)}
          </p>
        </div>
      </div>
    </div>
  );
}

function Field({
  icon: Icon,
  label,
  children,
}: {
  icon: LucideIcon;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-ink-faint" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <dt className="text-xs font-medium uppercase tracking-wide text-ink-faint">
          {label}
        </dt>
        <dd className="mt-0.5 text-sm text-ink">{children}</dd>
      </div>
    </div>
  );
}

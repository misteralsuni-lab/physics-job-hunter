"use client";

// Responsive job data table. On wide screens it renders a sortable grid; on
// narrow screens each row collapses into a card so all fields stay legible
// without horizontal scrolling. Clicking any row opens the detail drawer.
import { useState } from "react";
import dynamic from "next/dynamic";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Inbox,
  Bell,
  MapPin,
} from "lucide-react";
import { ScoreBadge } from "./ScoreBadge";
import { Chips } from "./Chips";
import { JobTableSkeleton } from "./JobTableSkeleton";
import { Pagination } from "./Pagination";
import { EmptyState } from "@/app/components/ui/EmptyState";
import type { Job, JobSortKey, SortDirection } from "@/lib/types/job";
import { formatBritishDate } from "@/lib/utils/cn";
import { cn } from "@/lib/utils/cn";

// Code-split the drawer (8 lucide icons + focus-trap logic) into its own
// chunk — it only renders when a user clicks a row, so there's no need
// to pay the parse cost on initial page load.
const JobDetailDrawer = dynamic(
  () => import("./JobDetailDrawer").then((m) => ({ default: m.JobDetailDrawer })),
  { ssr: false, loading: () => null },
);

export interface JobTableProps {
  jobs: Job[];
  total: number;
  loading: boolean;
  error: string | null;
  page: number;
  pageSize: number;
  sortKey: JobSortKey;
  sortDir: SortDirection;
  onSort: (key: JobSortKey) => void;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
  onRetry?: () => void;
}

const COLUMNS: { key: JobSortKey; label: string; sortable: boolean }[] = [
  { key: "title", label: "Role", sortable: true },
  { key: "school", label: "School", sortable: true },
  { key: "country", label: "Location", sortable: true },
  { key: "score", label: "Score", sortable: true },
  { key: "closing_date", label: "Closing date", sortable: true },
];

export function JobTable({
  jobs,
  total,
  loading,
  error,
  page,
  pageSize,
  sortKey,
  sortDir,
  onSort,
  onPage,
  onPageSize,
  onRetry,
}: JobTableProps) {
  const [selected, setSelected] = useState<Job | null>(null);

  // Show the skeleton only for the initial load (no data yet). On a background
  // refresh we keep the existing rows visible and let the page's spinner
  // indicate activity — swapping to a skeleton mid-refresh would flicker the
  // data the user is already reading.
  if (loading && jobs.length === 0) return <JobTableSkeleton />;

  if (error) {
    return (
      <div className="rounded-2xl border border-status-error/30 bg-surface-raised p-6 shadow-card">
        <EmptyState
          title="Could not load jobs"
          description={error}
          icon={Inbox}
        />
      </div>
    );
  }

  return (
    <>
      <div className="overflow-hidden rounded-2xl border border-line bg-surface-raised shadow-card">
        {/* Desktop grid header */}
        <div className="hidden grid-cols-[2fr_1.5fr_1fr_0.75fr_1fr] gap-4 border-b border-line bg-surface-muted px-4 py-2.5 md:grid">
          {COLUMNS.map((col) => (
            <SortableHeader
              key={col.key}
              label={col.label}
              active={sortKey === col.key}
              dir={sortDir}
              onClick={() => onSort(col.key)}
            />
          ))}
        </div>

        {jobs.length === 0 ? (
          <EmptyState
            title="No jobs found"
            description="Try adjusting your filters, or run the pipeline to fetch new listings."
            icon={Inbox}
          />
        ) : (
          <ul className="divide-y divide-line">
            {jobs.map((job) => (
              <li key={job.id}>
                <button
                  type="button"
                  onClick={() => setSelected(job)}
                  className={cn(
                    "grid w-full grid-cols-2 gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-muted",
                    "focus-visible:outline-none focus-visible:bg-surface-muted focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand",
                    "md:grid-cols-[2fr_1.5fr_1fr_0.75fr_1fr] md:gap-4",
                  )}
                  aria-label={`View details for ${job.title}`}
                >
                  {/* Role + school (mobile merges these) */}
                  <div className="min-w-0 space-y-0.5">
                    <p className="truncate text-sm font-medium text-ink">
                      {job.title}
                    </p>
                    <p className="truncate text-xs text-ink-muted">
                      {job.school || "Unknown school"}
                    </p>
                    {job.curriculum_board && (
                      <span className="mt-0.5 inline-flex items-center rounded-md bg-brand/10 px-1.5 py-0.5 text-xs font-medium text-brand">
                        {job.curriculum_board}
                      </span>
                    )}
                    {/* Mobile-only score + date */}
                    <div className="flex items-center gap-2 pt-1 md:hidden">
                      <ScoreBadge score={job.score} />
                      <span className="text-xs text-ink-faint">
                        {formatBritishDate(job.closing_date)}
                      </span>
                    </div>
                  </div>

                  {/* School (desktop) */}
                  <div className="hidden min-w-0 md:block">
                    <p className="truncate text-sm text-ink-muted">
                      {job.school || "—"}
                    </p>
                  </div>

                  {/* Location */}
                  <div className="flex min-w-0 items-center gap-1.5">
                    <MapPin className="hidden h-3.5 w-3.5 shrink-0 text-ink-faint md:block" aria-hidden="true" />
                    <span className="truncate text-sm text-ink-muted">
                      {[job.city, job.country].filter(Boolean).join(", ") || "—"}
                    </span>
                  </div>

                  {/* Score */}
                  <div className="flex items-center">
                    <ScoreBadge score={job.score} />
                  </div>

                  {/* Closing date + notified (desktop) */}
                  <div className="hidden items-center justify-between gap-2 md:flex">
                    <span className="text-sm text-ink-muted">
                      {formatBritishDate(job.closing_date)}
                    </span>
                    {job.notified && (
                      <Bell className="h-3.5 w-3.5 text-brand" aria-label="Notified" />
                    )}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {jobs.length > 0 && (
        <Pagination
          className="mt-4"
          page={page}
          pageSize={pageSize}
          total={total}
          onPage={onPage}
          onPageSize={onPageSize}
        />
      )}

      <JobDetailDrawer job={selected} onClose={() => setSelected(null)} />
    </>
  );
}

function SortableHeader({
  label,
  active,
  dir,
  onClick,
}: {
  label: string;
  active: boolean;
  dir: SortDirection;
  onClick: () => void;
}) {
  const Icon = active ? (dir === "desc" ? ArrowDown : ArrowUp) : ArrowUpDown;
  return (
    <div
      role="columnheader"
      aria-sort={active ? (dir === "desc" ? "descending" : "ascending") : undefined}
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); } }}
      className={cn(
        "flex cursor-pointer items-center gap-1 text-xs font-semibold uppercase tracking-wide transition-colors",
        active ? "text-ink" : "text-ink-faint hover:text-ink-muted",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
      )}
    >
      {label}
      <Icon className="h-3 w-3" aria-hidden="true" />
    </div>
  );
}

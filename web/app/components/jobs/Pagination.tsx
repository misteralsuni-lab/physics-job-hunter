"use client";

// Pagination control for the jobs table. Shows current range, total count and
// prev/next buttons plus a page-size selector. All buttons are 44px tap
// targets and disabled at the table edges.
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils/cn";

export interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
  className?: string;
}

const PAGE_SIZES = [10, 25, 50];

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
  className,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  const prevDisabled = page <= 1;
  const nextDisabled = page >= totalPages;

  return (
    <div
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
    >
      <div className="flex items-center gap-3">
        <span className="text-sm text-ink-muted">
          {total === 0
            ? "No jobs"
            : `Showing ${from}–${to} of ${total}`}
        </span>
        <label className="flex items-center gap-1.5 text-sm text-ink-muted">
          <span className="sr-only">Rows per page</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSize(Number(e.target.value))}
            aria-label="Rows per page"
            className={cn(
              "min-h-tap rounded-lg border border-line bg-surface px-2 text-sm text-ink",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
            )}
          >
            {PAGE_SIZES.map((s) => (
              <option key={s} value={s}>
                {s} per page
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onPage(page - 1)}
          disabled={prevDisabled}
          aria-label="Previous page"
          className={cn(
            "tap-target rounded-lg border border-line bg-surface-raised px-3 text-ink-muted hover:bg-surface-muted",
            "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </button>
        <span className="min-w-[5rem] text-center text-sm tabular-nums text-ink-muted">
          Page {page} of {totalPages}
        </span>
        <button
          type="button"
          onClick={() => onPage(page + 1)}
          disabled={nextDisabled}
          aria-label="Next page"
          className={cn(
            "tap-target rounded-lg border border-line bg-surface-raised px-3 text-ink-muted hover:bg-surface-muted",
            "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

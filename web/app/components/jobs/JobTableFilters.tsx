"use client";

// Reactive filter bar for the jobs table. Combines a search box, source and
// country selects, a score-range slider and a notified toggle. Every control
// is a 44px tap target and updates the shared Zustand store immediately.
import { Search, X } from "lucide-react";
import { Toggle } from "@/app/components/ui/Toggle";
import { Button } from "@/app/components/ui/Button";
import { useJobsStore } from "@/lib/store/jobs";
import { cn } from "@/lib/utils/cn";

export interface JobTableFiltersProps {
  sources: string[];
  countries: string[];
  className?: string;
}

export function JobTableFilters({
  sources,
  countries,
  className,
}: JobTableFiltersProps) {
  const filters = useJobsStore((s) => s.filters);
  const setFilters = useJobsStore((s) => s.setFilters);
  const resetFilters = useJobsStore((s) => s.resetFilters);

  const hasActive =
    filters.source !== null ||
    filters.country !== null ||
    filters.scoreMin !== null ||
    filters.scoreMax !== null ||
    filters.notified !== null ||
    filters.search.trim() !== "";

  return (
    <div
      className={cn(
        "space-y-4 rounded-2xl border border-line bg-surface-raised p-4 shadow-card",
        className,
      )}
    >
      {/* Search row */}
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint"
          aria-hidden="true"
        />
        <input
          type="search"
          inputMode="search"
          value={filters.search}
          onChange={(e) => setFilters({ search: e.target.value })}
          placeholder="Search title, school or location…"
          aria-label="Search jobs"
          className={cn(
            "min-h-tap w-full rounded-lg border border-line bg-surface pl-10 pr-3 text-sm text-ink placeholder:text-ink-faint",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
          )}
        />
      </div>

      {/* Selects + slider */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <FilterSelect
          id="filter-source"
          label="Source"
          value={filters.source ?? ""}
          onChange={(v) => setFilters({ source: v || null })}
          options={sources}
          allLabel="All sources"
        />
        <FilterSelect
          id="filter-country"
          label="Country"
          value={filters.country ?? ""}
          onChange={(v) => setFilters({ country: v || null })}
          options={countries}
          allLabel="All countries"
        />

        <div className="space-y-2">
          <div className="flex items-baseline justify-between">
            <span className="text-sm font-medium text-ink">
              Minimum score
            </span>
            <span className="text-xs text-ink-muted">
              {filters.scoreMin ?? 0}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={filters.scoreMin ?? 0}
            onChange={(e) =>
              setFilters({ scoreMin: Number(e.target.value) || null })
            }
            aria-label="Minimum score"
            className="h-11 w-full cursor-pointer appearance-none rounded-lg"
            style={{
              background: `linear-gradient(to right, rgb(var(--brand)) 0%, rgb(var(--brand)) ${filters.scoreMin ?? 0}%, rgb(var(--surface-muted)) ${filters.scoreMin ?? 0}%, rgb(var(--surface-muted)) 100%)`,
            }}
          />
        </div>

        <Toggle
          id="filter-notified"
          checked={filters.notified === true}
          onChange={(v) => setFilters({ notified: v || null })}
          label="Notified only"
          description="Show jobs already sent to Telegram and email"
        />
      </div>

      {hasActive && (
        <div className="flex justify-end">
          <Button variant="ghost" icon={X} onClick={resetFilters}>
            Clear filters
          </Button>
        </div>
      )}
    </div>
  );
}

interface FilterSelectProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  allLabel: string;
}

function FilterSelect({
  id,
  label,
  value,
  onChange,
  options,
  allLabel,
}: FilterSelectProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-ink">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "min-h-tap w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
        )}
      >
        <option value="">{allLabel}</option>
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </div>
  );
}

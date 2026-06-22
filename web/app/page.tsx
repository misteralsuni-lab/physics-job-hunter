"use client";

// Dashboard — scored job listings from Supabase.
//
// Fetches the current page of jobs and the distinct filter options on mount,
// then re-fetches whenever the user changes filters, sorting or pagination. The
// Zustand store holds the reactive filter/sort/page state, while the API route
// (server-only) talks to Supabase.
import { useEffect, useState } from "react";
import { LayoutDashboard } from "lucide-react";
import { JobTable } from "@/app/components/jobs/JobTable";
import { JobTableFilters } from "@/app/components/jobs/JobTableFilters";
import { JobTableSkeleton } from "@/app/components/jobs/JobTableSkeleton";
import { Spinner } from "@/app/components/ui/Spinner";
import { useJobsStore } from "@/lib/store/jobs";
import { toast } from "@/app/components/ui/Toast";
import type { JobListResponse, JobFilterOptions } from "@/lib/types/job";

export default function DashboardPage() {
  const jobs = useJobsStore((s) => s.jobs);
  const total = useJobsStore((s) => s.total);
  const loading = useJobsStore((s) => s.loading);
  const error = useJobsStore((s) => s.error);
  const page = useJobsStore((s) => s.page);
  const pageSize = useJobsStore((s) => s.pageSize);
  const filters = useJobsStore((s) => s.filters);
  const sortKey = useJobsStore((s) => s.sortKey);
  const sortDir = useJobsStore((s) => s.sortDir);

  const setJobs = useJobsStore((s) => s.setJobs);
  const setLoading = useJobsStore((s) => s.setLoading);
  const setError = useJobsStore((s) => s.setError);
  const setPage = useJobsStore((s) => s.setPage);
  const setPageSize = useJobsStore((s) => s.setPageSize);
  const toggleSort = useJobsStore((s) => s.toggleSort);

  const [options, setOptions] = useState<JobFilterOptions>({
    sources: [],
    countries: [],
    error: null,
  });

  // Fetch jobs when query parameters change.
  useEffect(() => {
    let cancelled = false;
    async function fetchJobs() {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        params.set("page", String(page));
        params.set("pageSize", String(pageSize));
        params.set("sort", sortKey);
        params.set("dir", sortDir);
        if (filters.source) params.set("source", filters.source);
        if (filters.country) params.set("country", filters.country);
        if (filters.scoreMin !== null) params.set("minScore", String(filters.scoreMin));
        if (filters.scoreMax !== null) params.set("maxScore", String(filters.scoreMax));
        if (filters.notified === true) params.set("notified", "true");
        if (filters.search.trim()) params.set("q", filters.search.trim());

        const res = await fetch(`/api/jobs?${params.toString()}`);
        const payload = (await res.json()) as JobListResponse;
        if (!cancelled) {
          if (payload.error) {
            setError(payload.error);
          } else {
            setJobs(payload.jobs, payload.total);
          }
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Network error";
          setError(message);
          toast.error("Could not load jobs: " + message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchJobs();
    return () => {
      cancelled = true;
    };
  }, [page, pageSize, sortKey, sortDir, filters, setJobs, setLoading, setError]);

  // Fetch distinct filter options once on mount.
  useEffect(() => {
    let cancelled = false;
    async function fetchOptions() {
      try {
        const res = await fetch("/api/jobs/options");
        const payload = (await res.json()) as JobFilterOptions;
        if (!cancelled) setOptions(payload);
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Network error";
          setOptions({ sources: [], countries: [], error: message });
        }
      }
    }
    fetchOptions();
    return () => {
      cancelled = true;
    };
  }, [setOptions]);

  return (
    <div className="animate-fade-in space-y-6">
      <header className="flex items-center gap-3">
        <LayoutDashboard className="h-7 w-7 text-brand" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold tracking-tight md:text-2xl">
            Dashboard
          </h1>
          <p className="text-sm text-ink-muted">
            Scored teaching jobs from the latest pipeline run.
          </p>
        </div>
      </header>

      {options.error && (
        <p className="text-sm text-status-error" role="alert">
          {options.error}
        </p>
      )}

      <JobTableFilters
        sources={options.sources}
        countries={options.countries}
      />

      {loading && jobs.length === 0 ? (
        <JobTableSkeleton />
      ) : (
        <JobTable
          jobs={jobs}
          total={total}
          loading={loading}
          error={error}
          page={page}
          pageSize={pageSize}
          sortKey={sortKey}
          sortDir={sortDir}
          onSort={toggleSort}
          onPage={setPage}
          onPageSize={setPageSize}
        />
      )}

      {loading && jobs.length > 0 && (
        <div className="flex items-center justify-center py-2">
          <Spinner label="Updating jobs" />
        </div>
      )}
    </div>
  );
}

// Zustand store for the dashboard jobs view: list state, filters, sorting and
// pagination. Data wiring happens in Phase 3; the store exposes the reactive
// shape the UI will bind to.
import { create } from "zustand";
import type {
  Job,
  JobFilters,
  JobSortKey,
  SortDirection,
} from "@/lib/types/job";

export interface JobsState {
  jobs: Job[];
  total: number;
  loading: boolean;
  /** Non-null when the last fetch failed (e.g. Supabase unreachable). */
  error: string | null;

  page: number;
  pageSize: number;

  filters: JobFilters;
  sortKey: JobSortKey;
  sortDir: SortDirection;

  // Actions
  setJobs: (jobs: Job[], total: number) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  setFilters: (patch: Partial<JobFilters>) => void;
  resetFilters: () => void;
  setSort: (key: JobSortKey, dir: SortDirection) => void;
  toggleSort: (key: JobSortKey) => void;
}

const defaultFilters: JobFilters = {
  source: null,
  country: null,
  curriculum_board: null,
  scoreMin: null,
  scoreMax: null,
  notified: null,
  search: "",
};

export const useJobsStore = create<JobsState>((set) => ({
  jobs: [],
  total: 0,
  loading: false,
  error: null,
  page: 1,
  pageSize: 25,
  filters: defaultFilters,
  sortKey: "score",
  sortDir: "desc",

  setJobs: (jobs, total) => set({ jobs, total, error: null }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  setPage: (page) => set({ page }),
  setPageSize: (size) => set({ pageSize: size, page: 1 }),
  setFilters: (patch) =>
    set((s) => ({ filters: { ...s.filters, ...patch }, page: 1 })),
  resetFilters: () => set({ filters: defaultFilters, page: 1 }),
  setSort: (sortKey, sortDir) => set({ sortKey, sortDir }),
  toggleSort: (key) =>
    set((s) => ({
      sortKey: key,
      sortDir: s.sortKey === key && s.sortDir === "desc" ? "asc" : "desc",
    })),
}));

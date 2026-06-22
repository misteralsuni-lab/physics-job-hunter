// Zustand store for advisory settings mirrored from the Python pipeline's
// `.env`. The Python scheduler remains the source of truth; this store holds
// the values shown in the Settings page and any optimistic local edits.
import { create } from "zustand";

export interface SettingsState {
  notifyScoreThreshold: number;
  /** Comma-separated 24h schedule times, e.g. "08:00,17:00,22:00". */
  scheduleTimes: string;
  loading: boolean;
  error: string | null;
  saved: boolean;

  setNotifyScoreThreshold: (value: number) => void;
  setScheduleTimes: (value: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setSaved: (saved: boolean) => void;
  hydrate: (data: Partial<SettingsState>) => void;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  notifyScoreThreshold: 50,
  scheduleTimes: "08:00,17:00,22:00,22:30,23:00",
  loading: false,
  error: null,
  saved: false,

  setNotifyScoreThreshold: (notifyScoreThreshold) =>
    set({ notifyScoreThreshold, saved: false }),
  setScheduleTimes: (scheduleTimes) => set({ scheduleTimes, saved: false }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  setSaved: (saved) => set({ saved }),
  hydrate: (data) =>
    set({
      notifyScoreThreshold: data.notifyScoreThreshold ?? 50,
      scheduleTimes: data.scheduleTimes ?? "08:00,17:00,22:00,22:30,23:00",
      error: null,
      saved: false,
    }),
}));

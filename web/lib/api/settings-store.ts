// Server-side persistence for advisory settings. The Python scheduler's `.env`
// is the source of truth; this module mirrors a small set of advisory values
// (notification threshold and schedule times) into a local JSON file so the
// Settings page can read and update them without touching the root `.env`.
//
// File location: web/config.json (gitignored). If the file is absent, values
// fall back to the matching environment variables or sensible defaults.
import "server-only";
import { promises as fs } from "node:fs";
import path from "node:path";

export interface AdvisorySettings {
  notifyScoreThreshold: number;
  scheduleTimes: string[];
}

const CONFIG_PATH = path.join(process.cwd(), "config.json");

const DEFAULTS: AdvisorySettings = {
  notifyScoreThreshold: Number(process.env.NOTIFY_SCORE_THRESHOLD) || 50,
  scheduleTimes:
    process.env.SCHEDULE_TIME?.split(",").map((t) => t.trim()).filter(Boolean) ??
    ["08:00", "17:00", "22:00", "22:30", "23:00"],
};

/** Read advisory settings, merging stored values over environment defaults. */
export async function readSettings(): Promise<AdvisorySettings> {
  try {
    const raw = await fs.readFile(CONFIG_PATH, "utf8");
    const parsed = JSON.parse(raw) as Partial<AdvisorySettings>;
    return {
      notifyScoreThreshold:
        typeof parsed.notifyScoreThreshold === "number"
          ? parsed.notifyScoreThreshold
          : DEFAULTS.notifyScoreThreshold,
      scheduleTimes:
        Array.isArray(parsed.scheduleTimes) && parsed.scheduleTimes.length > 0
          ? parsed.scheduleTimes
          : DEFAULTS.scheduleTimes,
    };
  } catch {
    // File missing or invalid — return environment defaults.
    return { ...DEFAULTS };
  }
}

/** Validate and persist advisory settings to the local config file. */
export async function writeSettings(
  input: unknown,
): Promise<{ ok: true; settings: AdvisorySettings } | { ok: false; error: string }> {
  if (!isObject(input)) return { ok: false, error: "Request body must be an object." };

  const threshold = input.notifyScoreThreshold;
  if (typeof threshold !== "number" || !Number.isFinite(threshold)) {
    return { ok: false, error: "notifyScoreThreshold must be a number." };
  }
  if (threshold < 0 || threshold > 100) {
    return { ok: false, error: "notifyScoreThreshold must be between 0 and 100." };
  }

  const times = input.scheduleTimes;
  if (!Array.isArray(times) || times.length === 0) {
    return { ok: false, error: "scheduleTimes must be a non-empty array." };
  }
  for (const t of times) {
    if (typeof t !== "string" || !/^\d{2}:\d{2}$/.test(t)) {
      return { ok: false, error: `Invalid schedule time: "${t}". Expected HH:MM.` };
    }
    const [hh, mm] = t.split(":");
    if (Number(hh) > 23 || Number(mm) > 59) {
      return { ok: false, error: `Schedule time out of range: "${t}".` };
    }
  }

  const settings: AdvisorySettings = {
    notifyScoreThreshold: threshold,
    scheduleTimes: times,
  };

  try {
    await fs.writeFile(CONFIG_PATH, JSON.stringify(settings, null, 2), "utf8");
    return { ok: true, settings };
  } catch (err) {
    const message = err instanceof Error ? err.message : "Could not write config file.";
    return { ok: false, error: message };
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

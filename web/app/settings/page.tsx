"use client";

// Settings — advisory notification threshold and schedule times.
//
// Values are mirrored from the Python pipeline's `.env` and stored locally in
// web/config.json. The running scheduler remains the source of truth; to apply
// changes you must also update the root `.env` and restart the service.
import { useEffect, useState } from "react";
import { Settings as SettingsIcon, Save } from "lucide-react";
import { Card } from "@/app/components/ui/Card";
import { Button } from "@/app/components/ui/Button";
import { Slider } from "@/app/components/ui/Slider";
import { NumberInput } from "@/app/components/ui/NumberInput";
import { Spinner } from "@/app/components/ui/Spinner";
import { toast } from "@/app/components/ui/Toast";

interface SettingsPayload {
  notifyScoreThreshold: number;
  scheduleTimes: string[];
}

export default function SettingsPage() {
  const [threshold, setThreshold] = useState(50);
  const [timesText, setTimesText] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function fetchSettings() {
      setLoading(true);
      try {
        const res = await fetch("/api/settings");
        const payload = (await res.json()) as SettingsPayload;
        if (!cancelled) {
          setThreshold(payload.notifyScoreThreshold);
          setTimesText(payload.scheduleTimes.join(", "));
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Could not load settings";
          toast.error(message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchSettings();
    return () => {
      cancelled = true;
    };
  }, []);

  async function saveSettings() {
    setSaving(true);
    try {
      const times = timesText
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notifyScoreThreshold: threshold, scheduleTimes: times }),
      });
      const payload = (await res.json()) as SettingsPayload | { error: string };
      if (!res.ok || "error" in payload) {
        toast.error("error" in payload ? payload.error : "Failed to save settings.");
      } else {
        setThreshold(payload.notifyScoreThreshold);
        setTimesText(payload.scheduleTimes.join(", "));
        toast.success("Settings saved. Remember to update the root `.env` and restart the scheduler to apply them.");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Network error";
      toast.error(`Could not save settings: ${message}`);
    } finally {
      setSaving(false);
    }
  }

  const timesValid = timesText
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean)
    .every((t) => /^\d{2}:\d{2}$/.test(t));

  return (
    <div className="animate-fade-in space-y-6">
      <header className="flex items-center gap-3">
        <SettingsIcon className="h-7 w-7 text-brand" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold tracking-tight md:text-2xl">
            Settings
          </h1>
          <p className="text-sm text-ink-muted">
            Advisory notification threshold and schedule times.
          </p>
        </div>
      </header>

      {loading ? (
        <Card className="flex items-center justify-center py-12">
          <Spinner label="Loading settings" />
        </Card>
      ) : (
        <Card className="space-y-6">
          <div className="space-y-1.5">
            <h2 className="text-base font-semibold text-ink">
              Notification threshold
            </h2>
            <p className="text-sm text-ink-muted">
              Jobs scored at or above this value trigger Telegram and email notifications.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-[1fr_auto]">
            <Slider
              id="threshold-slider"
              label="Minimum score"
              value={threshold}
              min={0}
              max={100}
              step={1}
              onChange={setThreshold}
              valueSuffix=" / 100"
            />
            <NumberInput
              id="threshold-number"
              label="Value"
              value={threshold}
              min={0}
              max={100}
              step={1}
              onChange={setThreshold}
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="schedule-times" className="block text-base font-semibold text-ink">
              Schedule times
            </label>
            <p className="text-sm text-ink-muted">
              Comma-separated 24-hour times when the scheduler arms the pipeline, e.g. 08:00, 17:00, 22:00.
            </p>
            <input
              id="schedule-times"
              type="text"
              value={timesText}
              onChange={(e) => setTimesText(e.target.value)}
              className="min-h-tap w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink placeholder:text-ink-faint"
              aria-invalid={!timesValid}
              aria-describedby="schedule-help"
            />
            <p id="schedule-help" className="text-xs text-ink-faint">
              Each entry must be in HH:MM format.
            </p>
          </div>

          {!timesValid && (
            <p className="text-sm text-status-error" role="alert">
              One or more schedule times are invalid.
            </p>
          )}

          <div className="flex flex-col items-start justify-between gap-4 border-t border-line pt-4 sm:flex-row sm:items-center">
            <p className="text-xs text-ink-faint">
              These values are advisory until applied to the root <code>.env</code> and the scheduler restarted.
            </p>
            <Button
              icon={Save}
              loading={saving}
              onClick={saveSettings}
              disabled={!timesValid}
            >
              Save settings
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}

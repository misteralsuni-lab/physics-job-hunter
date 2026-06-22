"use client";

// Global error boundary. Any uncaught error in a route segment surfaces here.
// The reset() helper lets the user retry rendering without a full reload.
import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // In production this would forward to a telemetry sink.
    console.error("[front-end] route error:", error);
  }, [error]);

  return (
    <div
      className="flex min-h-[40vh] flex-col items-center justify-center gap-4 text-center"
      role="alert"
    >
      <AlertTriangle
        className="h-10 w-10 text-status-error"
        aria-hidden="true"
      />
      <div>
        <h1 className="text-lg font-semibold">Something went wrong</h1>
        <p className="mt-1 text-sm text-ink-muted">
          The view could not be displayed. You can try again.
        </p>
      </div>
      <button
        type="button"
        onClick={reset}
        className="tap-target rounded-lg bg-brand px-4 text-sm font-medium text-brand-fg hover:opacity-90"
      >
        Try again
      </button>
    </div>
  );
}

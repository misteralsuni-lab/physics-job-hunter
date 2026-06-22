// Global route-level loading boundary. Shown while a route segment is
// streaming. Kept intentionally simple; per-view skeletons live with the
// views themselves.
import { Loader2 } from "lucide-react";

export default function Loading() {
  return (
    <div
      className="flex min-h-[40vh] items-center justify-center"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="h-6 w-6 animate-spin text-brand" aria-hidden="true" />
      <span className="sr-only">Loading…</span>
    </div>
  );
}

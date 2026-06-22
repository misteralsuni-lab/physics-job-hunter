// Status pill used to convey pipeline health. Colour coding maps directly onto
// the `status-*` Tailwind tokens. The dot pulses while a service is running so
// users get immediate, glanceable feedback.
import { cn } from "@/lib/utils/cn";

export type BadgeStatus = "active" | "sleeping" | "error" | "running";

export interface StatusBadgeProps {
  status: BadgeStatus;
  className?: string;
}

const STATUS_LABEL: Record<BadgeStatus, string> = {
  active: "Active",
  sleeping: "Sleeping",
  error: "Error",
  running: "Running",
};

const STATUS_CLASSES: Record<BadgeStatus, string> = {
  active: "bg-status-active/15 text-status-active",
  sleeping: "bg-status-sleeping/15 text-status-sleeping",
  error: "bg-status-error/15 text-status-error",
  running: "bg-status-running/15 text-status-running",
};

const DOT_CLASSES: Record<BadgeStatus, string> = {
  active: "bg-status-active",
  sleeping: "bg-status-sleeping",
  error: "bg-status-error",
  running: "bg-status-running",
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        STATUS_CLASSES[status],
        className,
      )}
      role="status"
    >
      <span className="relative flex h-2 w-2">
        {status === "running" && (
          <span
            className={cn(
              "absolute inline-flex h-full w-full animate-ping rounded-full opacity-75",
              DOT_CLASSES[status],
            )}
            aria-hidden="true"
          />
        )}
        <span
          className={cn(
            "relative inline-flex h-2 w-2 rounded-full",
            DOT_CLASSES[status],
          )}
          aria-hidden="true"
        />
      </span>
      {STATUS_LABEL[status]}
    </span>
  );
}

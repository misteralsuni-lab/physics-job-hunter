"use client";

// Accessible toggle switch. Implements the WAI-ARIA switch pattern: role
// "switch", aria-checked, keyboard activation via Space/Enter, and a visible
// focus ring. The whole control is a 44px tap target.
import { forwardRef } from "react";
import { cn } from "@/lib/utils/cn";

export interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
  id?: string;
  className?: string;
}

export const Toggle = forwardRef<HTMLButtonElement, ToggleProps>(
  function Toggle(
    { checked, onChange, label, description, disabled, id, className },
    ref,
  ) {
    return (
      <div className={cn("flex items-center justify-between gap-4", className)}>
        <div className="min-w-0">
          <label
            htmlFor={id}
            className="block text-sm font-medium text-ink"
          >
            {label}
          </label>
          {description && (
            <p className="mt-0.5 text-xs text-ink-muted">{description}</p>
          )}
        </div>
        <button
          ref={ref}
          id={id}
          type="button"
          role="switch"
          aria-checked={checked}
          aria-label={label}
          disabled={disabled}
          onClick={() => onChange(!checked)}
          className={cn(
            "tap-target relative h-6 w-11 shrink-0 rounded-full transition-colors",
            "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
            checked ? "bg-brand" : "bg-surface-muted",
            disabled && "cursor-not-allowed opacity-50",
          )}
        >
          <span
            className={cn(
              "absolute top-1 h-4 w-4 rounded-full bg-white shadow transition-transform",
              checked ? "translate-x-6" : "translate-x-1",
            )}
            aria-hidden="true"
          />
        </button>
      </div>
    );
  },
);

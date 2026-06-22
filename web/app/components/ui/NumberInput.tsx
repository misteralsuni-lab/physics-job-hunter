"use client";

// Number input with large +/− steppers. The steppers are themselves 44px tap
// targets, making fine-grained threshold adjustments comfortable on a tablet.
// Clamping keeps the value within [min, max].
import { forwardRef } from "react";
import { Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils/cn";

export interface NumberInputProps {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
  label: string;
  id?: string;
  disabled?: boolean;
  className?: string;
}

export const NumberInput = forwardRef<HTMLInputElement, NumberInputProps>(
  function NumberInput(
    { value, min = 0, max = 100, step = 1, onChange, label, id, disabled, className },
    ref,
  ) {
    const clamp = (v: number) => Math.min(max, Math.max(min, v));
    const stepBy = (dir: 1 | -1) => onChange(clamp(value + dir * step));

    return (
      <div className={cn("space-y-2", className)}>
        <label htmlFor={id} className="block text-sm font-medium text-ink">
          {label}
        </label>
        <div className="flex items-stretch">
          <button
            type="button"
            onClick={() => stepBy(-1)}
            disabled={disabled || value <= min}
            aria-label={`Decrease ${label}`}
            className={cn(
              "tap-target rounded-l-lg border border-r-0 border-line bg-surface-raised px-3 text-ink-muted hover:bg-surface-muted",
              "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            <Minus className="h-4 w-4" aria-hidden="true" />
          </button>
          <input
            ref={ref}
            id={id}
            type="number"
            inputMode="numeric"
            min={min}
            max={max}
            step={step}
            value={value}
            disabled={disabled}
            onChange={(e) => {
              const n = Number(e.target.value);
              if (!Number.isNaN(n)) onChange(clamp(n));
            }}
            aria-label={label}
            className={cn(
              "min-h-tap w-16 border border-line bg-surface-raised text-center text-sm tabular-nums text-ink",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
          />
          <button
            type="button"
            onClick={() => stepBy(1)}
            disabled={disabled || value >= max}
            aria-label={`Increase ${label}`}
            className={cn(
              "tap-target rounded-r-lg border border-l-0 border-line bg-surface-raised px-3 text-ink-muted hover:bg-surface-muted",
              "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    );
  },
);

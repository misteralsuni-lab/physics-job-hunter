"use client";

// Reactive range slider with a labelled value readout. The native range input
// is styled to meet the 44px touch height — the visible track is slim but the
// hit area is padded. The current value is announced via aria-valuetext so
// screen-reader users hear "50 out of 100" rather than a bare number.
import { cn } from "@/lib/utils/cn";

export interface SliderProps {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
  label: string;
  /** Suffix shown next to the numeric readout, e.g. "/ 100". */
  valueSuffix?: string;
  id?: string;
  disabled?: boolean;
  className?: string;
}

export function Slider({
  value,
  min = 0,
  max = 100,
  step = 1,
  onChange,
  label,
  valueSuffix,
  id,
  disabled,
  className,
}: SliderProps) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="text-sm font-medium text-ink">
          {label}
        </label>
        <span className="text-sm tabular-nums text-ink-muted">
          {value}
          {valueSuffix}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={label}
        aria-valuetext={`${value} out of ${max}`}
        className={cn(
          "h-11 w-full cursor-pointer appearance-none rounded-lg bg-transparent",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
          disabled && "cursor-not-allowed opacity-50",
        )}
        style={{
          background: `linear-gradient(to right, rgb(var(--brand)) 0%, rgb(var(--brand)) ${pct}%, rgb(var(--surface-muted)) ${pct}%, rgb(var(--surface-muted)) 100%)`,
        }}
      />
    </div>
  );
}

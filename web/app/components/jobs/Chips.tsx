// Reusable text chip used for array columns (curriculum, subject). Chips wrap
// onto multiple lines and scroll horizontally on narrow screens.
import { cn } from "@/lib/utils/cn";

export interface ChipsProps {
  items: string[];
  className?: string;
  emptyLabel?: string;
}

export function Chips({ items, className, emptyLabel = "—" }: ChipsProps) {
  if (!items || items.length === 0) {
    return <span className="text-sm text-ink-faint">{emptyLabel}</span>;
  }
  return (
    <div className={cn("flex flex-wrap gap-1", className)}>
      {items.map((item, i) => (
        <span
          key={`${item}-${i}`}
          className="inline-flex items-center rounded-md bg-surface-muted px-1.5 py-0.5 text-xs font-medium text-ink-muted"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

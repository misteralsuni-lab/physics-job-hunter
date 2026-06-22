// Surface container with a soft border and shadow. Used to group related
// content such as the jobs table wrapper, status panels and settings sections.
import { cn } from "@/lib/utils/cn";
import type { LucideIcon } from "lucide-react";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Adds interior padding (default true). */
  padded?: boolean;
}

export function Card({ padded = true, className, children, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-line bg-surface-raised shadow-card",
        padded && "p-4 md:p-6",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  action,
  icon: Icon,
  className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: LucideIcon;
  className?: string;
}) {
  return (
    <div className={cn("mb-4 flex items-start justify-between gap-3", className)}>
      <div className="min-w-0 flex items-start gap-2">
        {Icon && (
          <Icon className="mt-0.5 h-4 w-4 text-ink-faint" aria-hidden="true" />
        )}
        <div>
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          {description && (
            <p className="mt-0.5 text-sm text-ink-muted">{description}</p>
          )}
        </div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

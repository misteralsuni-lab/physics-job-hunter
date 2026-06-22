"use client";

// Touch-friendly button with loading and disabled states. The minimum tap
// target is 44px (WCAG 2.5.5). Variants map onto the semantic token palette
// defined in tailwind.config.ts.
import { forwardRef } from "react";
import { Loader2, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils/cn";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "danger"
  | "ghost";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
  /** Optional icon rendered before the label. */
  icon?: LucideIcon;
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "bg-brand text-brand-fg hover:opacity-90 active:opacity-100 shadow-card",
  secondary:
    "bg-surface-raised text-ink border border-line hover:bg-surface-muted",
  danger:
    "bg-status-error text-white hover:opacity-90 active:opacity-100 shadow-card",
  ghost: "bg-transparent text-ink-muted hover:bg-surface-muted hover:text-ink",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "primary",
      loading = false,
      icon: Icon,
      disabled,
      className,
      children,
      type = "button",
      ...rest
    },
    ref,
  ) {
    const isDisabled = disabled || loading;
    return (
      <button
        ref={ref}
        type={type}
        disabled={isDisabled}
        aria-busy={loading || undefined}
        className={cn(
          "tap-target rounded-lg px-4 text-sm font-medium transition-colors",
          "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
          VARIANT_CLASSES[variant],
          isDisabled && "cursor-not-allowed opacity-50",
          className,
        )}
        {...rest}
      >
        {loading ? (
          <Loader2
            className="h-4 w-4 animate-spin"
            aria-hidden="true"
          />
        ) : (
          Icon && <Icon className="h-4 w-4" aria-hidden="true" />
        )}
        {children && <span className={cn(Icon || loading ? "ml-2" : "")}>{children}</span>}
      </button>
    );
  },
);

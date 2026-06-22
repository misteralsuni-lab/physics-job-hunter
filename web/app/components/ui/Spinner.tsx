// Inline spinner for busy states. Paired with an sr-only label so assistive
// technology announces "Loading" rather than silence.
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils/cn";

export interface SpinnerProps {
  label?: string;
  className?: string;
  size?: "sm" | "md" | "lg";
}

const SIZE = { sm: "h-4 w-4", md: "h-6 w-6", lg: "h-8 w-8" };

export function Spinner({
  label = "Loading",
  className,
  size = "md",
}: SpinnerProps) {
  return (
    <span
      role="status"
      aria-live="polite"
      className={cn("inline-flex items-center gap-2", className)}
    >
      <Loader2
        className={cn("animate-spin text-brand", SIZE[size])}
        aria-hidden="true"
      />
      <span className="sr-only">{label}</span>
    </span>
  );
}

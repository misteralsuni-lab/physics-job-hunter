// Shimmering placeholder block. Combines the `.skeleton` base class from
// globals.css with rounded corners so it visually matches the element it
// stands in for during loading.
import { cn } from "@/lib/utils/cn";

export interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return <div className={cn("skeleton rounded-md", className)} aria-hidden="true" />;
}

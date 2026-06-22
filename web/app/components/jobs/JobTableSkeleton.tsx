import { Skeleton } from "@/app/components/ui/Skeleton";

// Loading placeholder mirroring the JobTable layout. Shown while the Supabase
// query is in flight so the layout never jumps when data arrives.
export function JobTableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface-raised shadow-card">
      <div className="hidden grid-cols-[2fr_1.5fr_1fr_0.75fr_1fr] gap-4 border-b border-line bg-surface-muted px-4 py-3 text-xs font-semibold uppercase tracking-wide text-ink-muted md:grid">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-4 w-12" />
        <Skeleton className="h-4 w-24" />
      </div>
      <ul className="divide-y divide-line">
        {Array.from({ length: rows }).map((_, i) => (
          <li
            key={i}
            className="grid grid-cols-2 gap-3 px-4 py-3 md:grid-cols-[2fr_1.5fr_1fr_0.75fr_1fr] md:gap-4"
          >
            <div className="space-y-1.5">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
            <Skeleton className="hidden h-4 w-full md:block" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-6 w-10 rounded-md" />
            <Skeleton className="hidden h-4 w-24 md:block" />
          </li>
        ))}
      </ul>
    </div>
  );
}

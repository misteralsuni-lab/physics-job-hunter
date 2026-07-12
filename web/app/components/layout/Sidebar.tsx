"use client";

// Responsive navigation rail. On large screens it renders as a fixed left
// sidebar; on small screens it collapses into a bottom tab bar so thumb
// reach stays comfortable — both patterns use the 44px minimum tap target.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Workflow, Settings, Atom, Users } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { ThemeToggle, ThemeCycleButton } from "@/app/components/ui/ThemeToggle";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/pipeline", label: "Pipeline Control", icon: Workflow },
  { href: "/leads", label: "Tutoring Leads", icon: Users },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <>
      {/* Left rail — large screens only */}
      <aside
        className="hidden md:flex md:w-60 md:flex-col md:shrink-0 md:border-r md:border-line md:bg-surface-raised"
        aria-label="Primary navigation"
      >
        <div className="flex h-16 items-center gap-2 border-b border-line px-5">
          <Atom className="h-6 w-6 text-brand" aria-hidden="true" />
          <span className="text-control font-semibold">Physics Job Hunter</span>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3">
          {NAV_ITEMS.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "tap-target rounded-lg px-3 text-sm font-medium transition-colors",
                  "text-ink-muted hover:bg-surface-muted hover:text-ink",
                  active && "bg-brand-soft text-brand",
                )}
              >
                <Icon className="h-5 w-5" aria-hidden="true" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="space-y-3 border-t border-line p-4">
          <p className="text-xs text-ink-faint">
            Reactive dashboard for the job-scraping pipeline.
          </p>
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs font-medium text-ink-muted">Theme</span>
            <ThemeToggle />
          </div>
        </div>
      </aside>

      {/* Bottom tab bar — small screens */}
      <nav
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-surface-raised md:hidden"
        aria-label="Primary navigation"
      >
        {NAV_ITEMS.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              aria-label={item.label}
              className={cn(
                "tap-target flex flex-1 flex-col items-center justify-center gap-1 py-2 text-[0.6875rem] font-medium transition-colors",
                "text-ink-muted",
                active ? "text-brand" : "hover:text-ink",
              )}
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
              <span className="leading-none">{item.label}</span>
            </Link>
          );
        })}
        <ThemeCycleButton />
      </nav>
    </>
  );
}

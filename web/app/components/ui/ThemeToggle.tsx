"use client";

// Light / dark / system theme controls.
//
// `ThemeToggle` renders a 3-segment segmented control suitable for the desktop
// sidebar footer. `ThemeCycleButton` is a compact single-icon button (cycling
// light → dark → system) for the mobile bottom navigation. Both consume the
// shared ThemeProvider context.
import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils/cn";

const OPTIONS: { value: Theme; label: string; Icon: typeof Sun }[] = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "system", label: "System", Icon: Monitor },
  { value: "dark", label: "Dark", Icon: Moon },
];

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className={cn(
        "inline-flex items-center rounded-lg border border-line bg-surface-muted p-0.5",
        className,
      )}
    >
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setTheme(value)}
            className={cn(
              "tap-target inline-flex h-9 w-9 items-center justify-center rounded-md transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
              active
                ? "bg-surface-raised text-brand shadow-card"
                : "text-ink-muted hover:text-ink",
            )}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}

const CYCLE: Theme[] = ["light", "dark", "system"];

export function ThemeCycleButton({ className }: { className?: string }) {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const Icon = theme === "system" ? Monitor : resolvedTheme === "dark" ? Moon : Sun;
  const label =
    theme === "system"
      ? `Theme: system (${resolvedTheme}). Tap to change.`
      : `Theme: ${theme}. Tap to change.`;
  return (
    <button
      type="button"
      onClick={() => {
        const idx = CYCLE.indexOf(theme);
        setTheme(CYCLE[(idx + 1) % CYCLE.length] as Theme);
      }}
      aria-label={label}
      title="Change theme"
      className={cn(
        "tap-target flex flex-1 flex-col items-center justify-center gap-1 py-2 text-[0.6875rem] font-medium text-ink-muted transition-colors hover:text-ink",
        className,
      )}
    >
      <Icon className="h-5 w-5" aria-hidden="true" />
      <span className="leading-none">{theme === "system" ? "Auto" : theme}</span>
    </button>
  );
}

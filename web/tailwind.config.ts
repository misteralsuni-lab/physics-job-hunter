// Tailwind CSS configuration for the Physics Job Hunter front end.
//
// Design tokens below define a semantic palette layered on top of Tailwind's
// default scale. UI copy and comments use British English throughout; token
// identifiers follow the framework's own naming (`colors`) so utility classes
// stay familiar and the build remains valid.
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // NOTE: the key is `colors` — this is a Tailwind API identifier, not
      // user-facing prose, so the British spelling is not used here on
      // purpose. All comments and UI strings elsewhere use British English.
      colors: {
        // Surface tokens
        surface: {
          DEFAULT: "rgb(var(--surface) / <alpha-value>)",
          muted: "rgb(var(--surface-muted) / <alpha-value>)",
          raised: "rgb(var(--surface-raised) / <alpha-value>)",
          inset: "rgb(var(--surface-inset) / <alpha-value>)",
        },
        ink: {
          DEFAULT: "rgb(var(--ink) / <alpha-value>)",
          muted: "rgb(var(--ink-muted) / <alpha-value>)",
          faint: "rgb(var(--ink-faint) / <alpha-value>)",
        },
        line: {
          DEFAULT: "rgb(var(--line) / <alpha-value>)",
          strong: "rgb(var(--line-strong) / <alpha-value>)",
        },
        brand: {
          DEFAULT: "rgb(var(--brand) / <alpha-value>)",
          fg: "rgb(var(--brand-fg) / <alpha-value>)",
          soft: "rgb(var(--brand-soft) / <alpha-value>)",
        },
        // Semantic status colours (used by StatusBadge)
        status: {
          active: "rgb(var(--status-active) / <alpha-value>)",
          sleeping: "rgb(var(--status-sleeping) / <alpha-value>)",
          running: "rgb(var(--status-running) / <alpha-value>)",
          error: "rgb(var(--status-error) / <alpha-value>)",
        },
        // LLM score band colours
        score: {
          high: "rgb(var(--score-high) / <alpha-value>)",
          mid: "rgb(var(--score-mid) / <alpha-value>)",
          low: "rgb(var(--score-low) / <alpha-value>)",
          none: "rgb(var(--score-none) / <alpha-value>)",
        },
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.25rem",
      },
      boxShadow: {
        card: "0 1px 2px rgb(15 23 42 / 0.06), 0 1px 3px rgb(15 23 42 / 0.04)",
        raised:
          "0 4px 12px -2px rgb(15 23 42 / 0.10), 0 2px 6px -2px rgb(15 23 42 / 0.06)",
      },
      fontSize: {
        // Touch-friendly defaults; refined further via component utilities.
        control: ["0.9375rem", { lineHeight: "1.4", fontWeight: "500" }],
      },
      minHeight: {
        // WCAG 2.5.5-aligned minimum tap target.
        tap: "2.75rem", // 44px
      },
      minWidth: {
        tap: "2.75rem", // 44px
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(0.5rem)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.2s ease-out",
        "slide-up": "slide-up 0.25s ease-out",
      },
    },
  },
  plugins: [],
};

export default config;

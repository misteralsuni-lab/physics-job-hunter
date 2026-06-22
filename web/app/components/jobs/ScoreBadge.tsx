// Colour-coded LLM score chip. Maps the numeric 0-100 rubric onto the four
// semantic score bands (high / mid / low / none) so a glance at the table
// conveys match quality. The numeric value is always shown for precision.
import { scoreBand } from "@/lib/types/job";
import { cn } from "@/lib/utils/cn";

const BAND_CLASS = {
  high: "bg-score-high/15 text-score-high",
  mid: "bg-score-mid/15 text-score-mid",
  low: "bg-score-low/15 text-score-low",
  none: "bg-score-none/15 text-score-none",
} as const;

export interface ScoreBadgeProps {
  score: number | null;
  className?: string;
}

export function ScoreBadge({ score, className }: ScoreBadgeProps) {
  const band = scoreBand(score);
  return (
    <span
      className={cn(
        "inline-flex min-w-[2.75rem] items-center justify-center rounded-md px-2 py-0.5 text-sm font-semibold tabular-nums",
        BAND_CLASS[band],
        className,
      )}
      title={score === null ? "Not yet scored" : `Score: ${score} / 100`}
    >
      {score === null ? "—" : score}
    </span>
  );
}

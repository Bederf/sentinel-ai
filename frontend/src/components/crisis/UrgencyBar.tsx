import { ProgressBar } from "@tremor/react";

interface UrgencyBarProps {
  score: number;
}

export function UrgencyBar({ score }: UrgencyBarProps) {
  const color = score >= 0.8 ? "rose" : score >= 0.6 ? "amber" : "blue";
  const percentage = Math.round(score * 100);

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Urgency
        </span>
        <span
          className="text-sm font-semibold tabular-nums"
          style={{
            color:
              score >= 0.8
                ? "var(--color-sentinel-red)"
                : score >= 0.6
                  ? "var(--color-sentinel-amber)"
                  : "var(--color-sentinel-blue)",
          }}
        >
          {percentage}%
        </span>
      </div>
      <ProgressBar value={percentage} color={color} />
    </div>
  );
}

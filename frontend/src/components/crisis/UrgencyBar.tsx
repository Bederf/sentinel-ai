

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
      <div className="w-full rounded-full h-2" style={{ background: 'var(--color-sentinel-bg-secondary)' }}>
        <div className="h-2 w-full origin-left rounded-full transition-transform will-change-transform" style={{ transform: `scaleX(${percentage / 100})`, background: score >= 0.8 ? 'var(--color-sentinel-red)' : score >= 0.6 ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-blue)' }} />
      </div>
    </div>
  );
}

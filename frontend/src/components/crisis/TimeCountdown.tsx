interface TimeCountdownProps {
  minutes: number | null;
  confidence: string;
}

export function TimeCountdown({ minutes, confidence }: TimeCountdownProps) {
  return (
    <div className="flex flex-col gap-1">
      <span
        className="text-2xl font-bold tabular-nums"
        style={{ color: "var(--color-sentinel-text-primary)" }}
      >
        {minutes !== null ? `~${minutes} min` : "Time unknown"}
      </span>
      {confidence && (
        <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          ({confidence})
        </span>
      )}
    </div>
  );
}

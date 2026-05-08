/**
 * ScoreRing — circular progress indicator with center score.
 */

interface ScoreRingProps {
  score: number;       // 0–100
  size?: number;        // px, default 80
  strokeWidth?: number;  // px, default 7
  color?: string;       // CSS color, default amber
  label?: string;       // displayed below score, default "Score"
}

export function ScoreRing({
  score,
  size = 80,
  strokeWidth = 7,
  color = "var(--color-sentinel-amber)",
  label = "Score",
}: ScoreRingProps) {
  const r = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * r;
  const clampedScore = Math.min(100, Math.max(0, score));
  const dashOffset = circumference * (1 - clampedScore / 100);

  return (
    <div style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size} style={{ display: "block" }}>
          {/* Track */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--color-sentinel-border)"
            strokeWidth={strokeWidth}
          />
          {/* Progress arc */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        </svg>
        {/* Center score */}
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            fontSize: size * 0.22,
            fontWeight: 700,
            color: "var(--color-sentinel-text-primary)",
            fontVariantNumeric: "tabular-nums",
            lineHeight: 1,
          }}
        >
          {clampedScore}
        </div>
      </div>
      <span
        style={{
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: "0.1em",
          color: "var(--color-sentinel-text-secondary)",
          textTransform: "uppercase",
        }}
      >
        {label}
      </span>
    </div>
  );
}

export default ScoreRing;

/**
 * PageLoading — canonical full-page loading state.
 *
 * Used on every page that is fetching its primary data. One visual
 * language across all views: 48px ring, amber arc, centered.
 *
 * Usage:
 *   if (loading) return <PageLoading message="Loading AEGIS console…" />;
 *
 * For inline / in-panel loading use compact variant:
 *   <PageLoading compact message="Fetching scenarios…" />
 */

interface PageLoadingProps {
  message?: string;
  compact?: boolean;
}

export function PageLoading({ message = "Loading…", compact = false }: PageLoadingProps) {
  const size = compact ? 32 : 48;
  const r = (size - 6) / 2;
  const circumference = 2 * Math.PI * r;
  const dashOffset = circumference * 0.72; // ~28% arc visible

  return (
    <div
      className="flex flex-col items-center justify-center gap-4 p-6"
      style={{
        minHeight: "100dvh",
        background: "var(--color-sentinel-bg-canvas)",
      }}
    >
      <div style={{ position: "relative", width: size, height: size }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          style={{ animation: "sentinel-loader-rotate 1.2s linear infinite", display: "block" }}
        >
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--color-sentinel-border)"
            strokeWidth="3"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--color-sentinel-amber)"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        </svg>
        {!compact && (
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: "var(--color-sentinel-amber)",
              animation: "sentinel-loader-pulse 1.4s ease-in-out infinite",
            }}
          />
        )}
      </div>

      <div
        style={{
          fontSize: compact ? 12 : 13,
          fontWeight: 500,
          color: "var(--color-sentinel-text-primary)",
        }}
      >
        {message}
      </div>

      {!compact && (
        <div
          style={{
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: "0.14em",
            color: "var(--color-sentinel-text-disabled)",
            textTransform: "uppercase",
          }}
        >
          SENTINEL
        </div>
      )}

      {/* Inject keyframes once, scoped to this component. */}
      <style>{`
        @keyframes sentinel-loader-rotate { to { transform: rotate(360deg); } }
        @keyframes sentinel-loader-pulse {
          0%, 100% { opacity: 1; }
          50%      { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}

export default PageLoading;

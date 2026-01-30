interface LoadingCardProps {
  height?: string;
}

export function LoadingCard({ height = "h-24" }: LoadingCardProps) {
  return (
    <div
      className={`${height} animate-pulse rounded-lg p-4`}
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      <div className="space-y-3">
        <div
          className="h-4 rounded w-3/4"
          style={{ background: "var(--color-sentinel-bg-secondary)" }}
        />
        <div
          className="h-3 rounded w-1/2"
          style={{ background: "var(--color-sentinel-bg-secondary)" }}
        />
      </div>
    </div>
  );
}

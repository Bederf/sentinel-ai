interface LoadingCardProps {
  height?: string;
}

export function LoadingCard({ height = "h-24" }: LoadingCardProps) {
  return (
    <div
      className={`${height} animate-pulse glass-subtle p-4`}
    >
      <div className="space-y-3">
        <div
          className="h-4 rounded w-3/4"
          style={{ background: "rgba(255, 255, 255, 0.06)" }}
        />
        <div
          className="h-3 rounded w-1/2"
          style={{ background: "rgba(255, 255, 255, 0.04)" }}
        />
      </div>
    </div>
  );
}

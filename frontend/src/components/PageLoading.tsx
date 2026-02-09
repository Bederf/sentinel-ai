import { Activity } from "lucide-react";

interface PageLoadingProps {
  message?: string;
}

export function PageLoading({ message = "Loading..." }: PageLoadingProps) {
  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6 flex items-center justify-center"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      <div className="flex items-center gap-3">
        <Activity
          className="h-6 w-6 animate-spin"
          style={{ color: "var(--color-sentinel-blue)" }}
        />
        <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {message}
        </span>
      </div>
    </div>
  );
}

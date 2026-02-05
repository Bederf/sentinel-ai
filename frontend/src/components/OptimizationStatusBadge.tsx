/**
 * OptimizationStatusBadge Component - AI optimization status indicator
 *
 * Displays optimization status for a building with lightbulb icons:
 * - Automatic mode: Green lightbulb (AI is managing the building)
 * - Supervised mode + recommendation pending: Amber lightbulb, pulsing
 * - Error: Red X icon
 * - Supervised mode + no recommendation: No badge shown
 *
 * Supports size variants and shows optional timestamp.
 */

import { Lightbulb, XCircle } from "lucide-react";
import { useMemo } from "react";

export type OptimizationStatus = "optimized" | "recommendation_pending" | "warning" | "error" | "unknown";
export type OptimizationMode = "automatic" | "supervised";

interface OptimizationStatusBadgeProps {
  status: OptimizationStatus;
  mode?: OptimizationMode;
  size?: "sm" | "md";
  lastOptimization?: string | null | undefined;
  className?: string;
  hasRecommendation?: boolean;
}

/**
 * Format timestamp as relative time (e.g., "12 min ago")
 */
function formatRelativeTime(timestamp: string | null | undefined): string | null {
  if (!timestamp) return null;

  const now = new Date();
  const time = new Date(timestamp);
  const diffMs = now.getTime() - time.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins} min ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export function OptimizationStatusBadge({
  status,
  mode = "supervised",
  size = "md",
  lastOptimization,
  className = "",
  hasRecommendation = false,
}: OptimizationStatusBadgeProps) {
  const relativeTime = useMemo(() => formatRelativeTime(lastOptimization), [lastOptimization]);

  const sizeClasses = {
    sm: "text-xs px-1.5 py-0.5 gap-1",
    md: "text-sm px-2 py-1 gap-1.5",
  };

  const iconSizes = {
    sm: "h-3.5 w-3.5",
    md: "h-4 w-4",
  };

  // Determine what to show based on mode and recommendation
  const getBadgeConfig = () => {
    // Error state - always show error icon
    if (status === "error") {
      return {
        show: true,
        icon: XCircle,
        color: "var(--color-sentinel-red)",
        bg: "rgba(220, 38, 38, 0.15)",
        pulse: false,
        showTime: false,
        tooltip: "Optimization error",
      };
    }

    // Automatic mode - always show green lightbulb (AI is managing)
    if (mode === "automatic") {
      return {
        show: true,
        icon: Lightbulb,
        color: "var(--color-sentinel-green)",
        bg: "rgba(16, 185, 129, 0.15)",
        pulse: false,
        showTime: true,
        tooltip: "Auto-optimization enabled",
      };
    }

    // Supervised mode + has recommendation - amber lightbulb, pulsing
    if (mode === "supervised" && hasRecommendation) {
      return {
        show: true,
        icon: Lightbulb,
        color: "var(--color-sentinel-amber)",
        bg: "rgba(245, 158, 11, 0.15)",
        pulse: true,
        showTime: false,
        tooltip: "Recommendation pending approval",
      };
    }

    // Supervised mode without recommendation - don't show badge
    return {
      show: false,
      icon: Lightbulb,
      color: "",
      bg: "",
      pulse: false,
      showTime: false,
      tooltip: "",
    };
  };

  const config = getBadgeConfig();

  // Don't render if nothing to show
  if (!config.show) {
    return null;
  }

  const Icon = config.icon;

  return (
    <div className={`flex flex-col ${className}`}>
      <div
        className={`inline-flex items-center font-medium rounded ${sizeClasses[size]} ${
          config.pulse ? "animate-pulse" : ""
        }`}
        style={{
          background: config.bg,
          color: config.color,
        }}
      >
        <Icon className={iconSizes[size]} />
      </div>

      {config.showTime && relativeTime && (
        <span
          className={`text-xs mt-1 ${size === "sm" ? "text-[10px]" : ""}`}
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        >
          {relativeTime}
        </span>
      )}
    </div>
  );
}

export default OptimizationStatusBadge;

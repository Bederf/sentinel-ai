/**
 * OptimizationStatusBadge Component - AI optimization status indicator
 *
 * Displays optimization status for a building with lightbulb icons:
 * - Optimized (accepted): Green lightbulb, no pulse
 * - Recommendation Pending: Amber lightbulb, pulsing
 * - Rejected/Warning: Amber lightbulb, no pulse
 * - Error: Red X icon
 * - No recommendation: No badge shown
 *
 * Supports size variants and shows optional timestamp.
 */

import { Lightbulb, XCircle } from "lucide-react";
import { useMemo } from "react";

export type OptimizationStatus = "optimized" | "recommendation_pending" | "warning" | "error" | "unknown";

interface OptimizationStatusBadgeProps {
  status: OptimizationStatus;
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

  // Determine what to show based on status and recommendation
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
      };
    }

    // Optimized (accepted) - green lightbulb, no pulse
    if (status === "optimized") {
      return {
        show: true,
        icon: Lightbulb,
        color: "var(--color-sentinel-green)",
        bg: "rgba(16, 185, 129, 0.15)",
        pulse: false,
        showTime: true,
      };
    }

    // Has recommendation pending - amber lightbulb, pulsing
    if (hasRecommendation && status === "recommendation_pending") {
      return {
        show: true,
        icon: Lightbulb,
        color: "var(--color-sentinel-amber)",
        bg: "rgba(245, 158, 11, 0.15)",
        pulse: true,
        showTime: false,
      };
    }

    // Has recommendation but warning/rejected - amber lightbulb, no pulse
    if (hasRecommendation && (status === "warning" || status === "unknown")) {
      return {
        show: true,
        icon: Lightbulb,
        color: "var(--color-sentinel-amber)",
        bg: "rgba(245, 158, 11, 0.15)",
        pulse: false,
        showTime: false,
      };
    }

    // No recommendation and not optimized - don't show badge
    return {
      show: false,
      icon: Lightbulb,
      color: "",
      bg: "",
      pulse: false,
      showTime: false,
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

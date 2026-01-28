/**
 * OptimizationStatusBadge Component - AI optimization status indicator
 *
 * Displays optimization status for a building with color-coded badges:
 * - Optimized: Green with checkmark
 * - Recommendation Pending: Amber with lightbulb icon (pulsing)
 * - Warning: Orange with alert triangle
 * - Error: Red with X icon
 * - Unknown: Gray with question mark
 *
 * Supports size variants and shows optional timestamp.
 */

import { CheckCircle2, Lightbulb, AlertTriangle, XCircle, HelpCircle } from "lucide-react";
import { useMemo } from "react";

export type OptimizationStatus = "optimized" | "recommendation_pending" | "warning" | "error" | "unknown";

interface OptimizationStatusBadgeProps {
  status: OptimizationStatus;
  size?: "sm" | "md";
  lastOptimization?: string | null | undefined;
  className?: string;
}

/**
 * Get status configuration for SENTINEL theme
 */
function getStatusConfig(status: OptimizationStatus): {
  color: string;
  bg: string;
  icon: typeof CheckCircle2;
  label: string;
  pulse: boolean;
} {
  switch (status) {
    case "optimized":
      return {
        color: "var(--color-sentinel-green)",
        bg: "rgba(16, 185, 129, 0.15)",
        icon: CheckCircle2,
        label: "OPTIMIZED",
        pulse: false,
      };
    case "recommendation_pending":
      return {
        color: "var(--color-sentinel-amber)",
        bg: "rgba(245, 158, 11, 0.15)",
        icon: Lightbulb,
        label: "ACTION NEEDED",
        pulse: true,
      };
    case "warning":
      return {
        color: "var(--color-sentinel-orange)",
        bg: "rgba(249, 115, 22, 0.15)",
        icon: AlertTriangle,
        label: "WARNING",
        pulse: false,
      };
    case "error":
      return {
        color: "var(--color-sentinel-red)",
        bg: "rgba(220, 38, 38, 0.15)",
        icon: XCircle,
        label: "ERROR",
        pulse: false,
      };
    default:
      // Default to INFO instead of UNKNOWN for better UX
      return {
        color: "var(--color-sentinel-blue)",
        bg: "rgba(59, 130, 246, 0.15)",
        icon: HelpCircle,
        label: "INFO",
        pulse: false,
      };
  }
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
}: OptimizationStatusBadgeProps) {
  const config = useMemo(() => getStatusConfig(status), [status]);
  const Icon = config.icon;
  const relativeTime = useMemo(() => formatRelativeTime(lastOptimization), [lastOptimization]);

  const sizeClasses = {
    sm: "text-xs px-1.5 py-0.5 gap-1",
    md: "text-sm px-2 py-1 gap-1.5",
  };

  const iconSizes = {
    sm: "h-3.5 w-3.5",
    md: "h-4 w-4",
  };

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
        {status !== "recommendation_pending" && <span>{config.label}</span>}
      </div>

      {relativeTime && status === "optimized" && (
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

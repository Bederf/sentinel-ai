/**
 * KPICard Component - Grafana-inspired stat panel
 *
 * Displays:
 * - Large metric value with tabular numbers
 * - Title in uppercase with muted color
 * - Optional trend indicator with delta
 * - Icon with accent coloring
 * - Status-based accent bar at top
 *
 * Follows Grafana stat panel design patterns.
 */

import type { ReactNode } from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

export interface KPICardProps {
  /** Card title */
  title: string;
  /** Main metric value */
  value: string | number;
  /** Optional icon to display */
  icon?: ReactNode;
  /** Delta/trend percentage (e.g., 12.5 for +12.5%) */
  delta?: number;
  /** Custom delta text (e.g., "vs last week") */
  deltaText?: string;
  /** Whether the trend is inverted (decrease is good, increase is bad) */
  isInverseTrend?: boolean;
  /** Optional subtitle or description */
  subtitle?: string;
  /** Optional tooltip text */
  tooltip?: string;
  /** Optional click handler */
  onClick?: () => void;
  /** Accent color for the card */
  accentColor?: "green" | "orange" | "red" | "blue" | "purple" | "cyan";
}

export function KPICard({
  title,
  value,
  icon,
  delta,
  deltaText,
  isInverseTrend = false,
  subtitle,
  onClick,
  accentColor = "blue",
}: KPICardProps) {
  // Determine if trend is positive based on delta and inverse setting
  const isPositive = delta !== undefined && delta > 0;
  const isNegative = delta !== undefined && delta < 0;

  // Calculate actual good/bad based on inverse
  const isGood = isInverseTrend ? isNegative : isPositive;
  const isBad = isInverseTrend ? isPositive : isNegative;

  // Color mapping for accents
  const accentColors: Record<string, string> = {
    green: "var(--color-status-success)",
    orange: "var(--color-status-warning)",
    red: "var(--color-status-error)",
    blue: "var(--color-grafana-blue)",
    purple: "var(--color-grafana-purple)",
    cyan: "var(--color-grafana-cyan)",
  };

  // Format delta value
  const formatDelta = (d: number): string => {
    const sign = d >= 0 ? "+" : "";
    return `${sign}${d.toFixed(1)}%`;
  };

  return (
    <div
      className={`relative overflow-hidden rounded ${onClick ? "cursor-pointer" : ""}`}
      style={{
        background: "var(--color-grafana-bg-panel)",
        border: "1px solid var(--color-grafana-border)",
      }}
      onClick={onClick}
    >
      {/* Top accent bar */}
      <div
        className="absolute top-0 left-0 right-0 h-1"
        style={{ background: accentColors[accentColor] }}
      />

      <div className="p-4 pt-5">
        {/* Header row with icon */}
        <div className="flex items-start justify-between mb-3">
          <span
            className="text-xs font-medium uppercase tracking-wider"
            style={{ color: "var(--color-grafana-text-secondary)" }}
          >
            {title}
          </span>
          {icon && (
            <div
              className="p-2 rounded"
              style={{
                background: `${accentColors[accentColor]}20`,
                color: accentColors[accentColor],
              }}
            >
              {icon}
            </div>
          )}
        </div>

        {/* Main metric value */}
        <div
          className="text-3xl font-medium mb-2"
          style={{
            color: "var(--color-grafana-text-primary)",
            fontVariantNumeric: "tabular-nums",
            letterSpacing: "-0.02em",
          }}
        >
          {typeof value === "number" ? value.toLocaleString() : value}
        </div>

        {/* Delta indicator */}
        {delta !== undefined && (
          <div className="flex items-center gap-2">
            <div
              className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium"
              style={{
                background: isGood
                  ? "rgba(115, 191, 105, 0.15)"
                  : isBad
                    ? "rgba(242, 73, 92, 0.15)"
                    : "rgba(142, 142, 142, 0.15)",
                color: isGood
                  ? "var(--color-status-success)"
                  : isBad
                    ? "var(--color-status-error)"
                    : "var(--color-grafana-text-secondary)",
              }}
            >
              {isPositive ? (
                <TrendingUp className="h-3 w-3" />
              ) : isNegative ? (
                <TrendingDown className="h-3 w-3" />
              ) : (
                <Minus className="h-3 w-3" />
              )}
              {formatDelta(delta)}
            </div>
            {deltaText && (
              <span
                className="text-xs"
                style={{ color: "var(--color-grafana-text-disabled)" }}
              >
                {deltaText}
              </span>
            )}
          </div>
        )}

        {/* Subtitle (alternative to delta) */}
        {subtitle && delta === undefined && (
          <span
            className="text-xs"
            style={{ color: "var(--color-grafana-text-secondary)" }}
          >
            {subtitle}
          </span>
        )}
      </div>
    </div>
  );
}

export default KPICard;

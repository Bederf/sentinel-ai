/**
 * KPICard Component - SENTINEL stat panel
 *
 * Displays:
 * - Large metric value with tabular numbers
 * - Title in uppercase with muted color
 * - Optional trend indicator with delta
 * - Icon with accent coloring
 * - Status-based accent bar at top
 *
 * Follows SENTINEL dark theme design patterns.
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
  /** Visual style variant — flat (default) or glass (opt-in) */
  variant?: "flat" | "glass";
  /** Unit suffix displayed after the value (e.g. "kW", "%") */
  unit?: string;
  /** Optional progress bar (0–100), renders below the value */
  progress?: number;
  /** Left-border accent override (takes priority over accentColor for the border) */
  accent?: "green" | "orange" | "red" | "blue" | "purple" | "cyan";
  /** Density variant — compact reduces padding and height for dense layouts */
  density?: "default" | "compact";
}

export function KPICard({
  title,
  value,
  icon,
  delta,
  deltaText,
  isInverseTrend = false,
  subtitle,
  tooltip,
  onClick,
  accentColor = "blue",
  unit,
  progress,
  accent,
  density = "default",
  variant = "flat",
}: KPICardProps) {
  const isCompact = density === "compact";
  const isPositive = delta !== undefined && delta > 0;
  const isNegative = delta !== undefined && delta < 0;

  // Calculate actual good/bad based on inverse
  const isGood = isInverseTrend ? isNegative : isPositive;
  const isBad = isInverseTrend ? isPositive : isNegative;

  // Color mapping for SENTINEL accents — all design token references
  const accentColors: Record<string, string> = {
    green:  "var(--color-sentinel-green)",
    orange: "var(--color-sentinel-amber)",
    red:    "var(--color-sentinel-red)",
    blue:   "var(--color-sentinel-blue)",
    purple: "var(--color-sentinel-purple)",
    cyan:   "var(--color-sentinel-cyan)",
  };

  // Format delta value
  const formatDelta = (d: number): string => {
    const sign = d >= 0 ? "+" : "";
    return `${sign}${d.toFixed(1)}%`;
  };

  return (
    <div
      className={`relative overflow-hidden ${variant === "glass" ? "glass-card glass-highlight" : "border rounded-lg"} ${onClick ? "cursor-pointer hover:brightness-110" : ""}`}
      style={variant === "flat" ? {
        minHeight: isCompact ? "6.25rem" : "8.75rem",
        maxHeight: isCompact ? "8.125rem" : "11.25rem",
        background: "var(--color-sentinel-bg-panel)",
        borderColor: "var(--color-sentinel-border)",
      } : {
        minHeight: isCompact ? "6.25rem" : "8.75rem",
        maxHeight: isCompact ? "8.125rem" : "11.25rem",
      }}
      onClick={onClick}
      title={tooltip}
    >
      {/* Top accent bar */}
      <div
        className="absolute top-0 left-0 right-0 h-1"
        style={{ background: accentColors[accent ?? accentColor] }}
      />

      <div className={`${isCompact ? "p-3 pt-4" : "p-4 pt-5"} flex flex-col justify-between h-full`}>
        {/* Header row with icon */}
        <div className="flex items-start justify-between mb-3 flex-shrink-0">
          <span
            className="text-xs font-medium uppercase tracking-wider"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            {title}
          </span>
          {icon && (
            <div
              className="p-1.5 rounded flex-shrink-0"
              style={{
                background: `${accentColors[accent ?? accentColor]}20`,
                color: accentColors[accent ?? accentColor],
              }}
            >
              {icon}
            </div>
          )}
        </div>

        {/* Main metric value */}
        <div
          className="text-2xl font-medium mb-auto flex-shrink-0"
          style={{
            color: "var(--color-sentinel-text-primary)",
            fontVariantNumeric: "tabular-nums",
            letterSpacing: "-0.02em",
          }}
        >
          {typeof value === "number" ? value.toLocaleString() : value}
          {unit && (
            <span className="text-sm font-normal" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {unit}
            </span>
          )}
        </div>

        {/* Progress bar */}
        {progress !== undefined && (
          <div className="mt-2 flex-shrink-0">
            <div
              className="h-1 w-full rounded-full overflow-hidden"
              style={{ background: "var(--color-sentinel-border)" }}
            >
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.min(100, Math.max(0, progress))}%`,
                  background: accentColors[accent ?? accentColor],
                }}
              />
            </div>
          </div>
        )}

        {/* Delta indicator - only show if delta is defined and not zero */}
        {delta !== undefined && delta !== 0 && (
          <div className="flex items-center gap-2 flex-shrink-0">
            <div
              className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium"
              style={{
                background: isGood
                  ? "color-mix(in oklch, var(--color-sentinel-green) 15%, transparent)"
                  : isBad
                    ? "color-mix(in oklch, var(--color-sentinel-red) 15%, transparent)"
                    : "color-mix(in oklch, var(--color-sentinel-text-disabled) 15%, transparent)",
                color: isGood
                  ? "var(--color-sentinel-green)"
                  : isBad
                    ? "var(--color-sentinel-red)"
                    : "var(--color-sentinel-text-secondary)",
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
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                {deltaText}
              </span>
            )}
          </div>
        )}

        {/* Subtitle (alternative to delta) */}
        {subtitle && delta === undefined && (
          <span
            className="text-xs flex-shrink-0"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            {subtitle}
          </span>
        )}
      </div>
    </div>
  );
}

export default KPICard;

/**
 * KPICard Component - Key Performance Indicator card
 *
 * Displays:
 * - Title (e.g., "Total Sites", "Active Alerts")
 * - Value (large number)
 * - Trend indicator (up/down with %)
 * - Color based on trend (green good, red bad)
 *
 * Uses Tremor Metric and BadgeDelta components.
 *
 * Requirement: DASH-04 - KPI cards with trend indicators
 */

import { Card, Metric, Text, Flex, BadgeDelta, Tooltip } from "@tremor/react";
import type { DeltaType } from "@tremor/react";
import type { ReactNode } from "react";

export interface KPICardProps {
  /** Card title */
  title: string;
  /** Main metric value */
  value: string | number;
  /** Optional icon to display */
  icon?: ReactNode;
  /** Delta/trend percentage (e.g., 12.5 for +12.5%) */
  delta?: number;
  /** Delta type for coloring: "increase" = green, "decrease" = red, etc. */
  deltaType?: DeltaType;
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
}

/**
 * Determine delta type based on value and inversion
 */
function getDeltaType(delta: number, isInverse: boolean): DeltaType {
  if (delta === 0) return "unchanged";

  const isPositive = delta > 0;

  // If inverted, positive is bad (e.g., alerts increasing)
  if (isInverse) {
    return isPositive ? "increase" : "decrease";
  }

  // Normal: positive is good (e.g., uptime increasing)
  return isPositive ? "increase" : "decrease";
}

/**
 * Format delta value as percentage string
 */
function formatDelta(delta: number): string {
  const sign = delta >= 0 ? "+" : "";
  return `${sign}${delta.toFixed(1)}%`;
}

export function KPICard({
  title,
  value,
  icon,
  delta,
  deltaType,
  deltaText,
  isInverseTrend = false,
  subtitle,
  tooltip,
  onClick,
}: KPICardProps) {
  // Calculate delta type if not explicitly provided
  const computedDeltaType = deltaType ?? (delta !== undefined ? getDeltaType(delta, isInverseTrend) : "unchanged");

  // Determine color class based on delta type and inverse setting
  const decorationColor =
    computedDeltaType === "increase"
      ? (isInverseTrend ? "red" : "green")
      : computedDeltaType === "decrease"
        ? (isInverseTrend ? "green" : "red")
        : "gray";

  return (
    <Card
      className={`p-4 transition-all duration-200 ${
        onClick ? "cursor-pointer hover:shadow-lg hover:border-bidvest-blue-300" : ""
      }`}
      decoration="top"
      decorationColor={decorationColor}
      onClick={onClick}
    >
      <Tooltip content={tooltip}>
        <Flex justifyContent="start" className="gap-4">
          {/* Icon */}
          {icon && (
            <div className="p-3 bg-bidvest-blue-50 rounded-lg shrink-0">
              {icon}
            </div>
          )}

          {/* Content */}
          <div className="flex-1 min-w-0">
            {/* Title */}
            <Text className="text-gray-500 truncate">{title}</Text>

            {/* Value */}
            <Metric className="text-2xl font-bold text-gray-900 mt-1">
              {typeof value === "number" ? value.toLocaleString() : value}
            </Metric>

            {/* Trend indicator */}
            {delta !== undefined && (
              <Flex justifyContent="start" className="gap-2 mt-2">
                <BadgeDelta
                  deltaType={computedDeltaType}
                  size="sm"
                  isIncreasePositive={!isInverseTrend}
                >
                  {formatDelta(delta)}
                </BadgeDelta>
                {deltaText && (
                  <Text className="text-xs text-gray-400">{deltaText}</Text>
                )}
              </Flex>
            )}

            {/* Subtitle (alternative to trend) */}
            {subtitle && !delta && (
              <Text className="text-sm text-gray-500 mt-1">{subtitle}</Text>
            )}
          </div>
        </Flex>
      </Tooltip>
    </Card>
  );
}

export default KPICard;

/**
 * EnergyChart Component - Grafana-inspired chart visualization
 *
 * Uses Tremor AreaChart with dark theme styling.
 *
 * Features:
 * - Stacked area chart (HVAC, Lighting, Other)
 * - Grafana-style color palette
 * - Dark theme grid and axes
 * - Category breakdown with colored indicators
 */

import { AreaChart } from "@tremor/react";
import { Zap, TrendingUp } from "lucide-react";
import type { EnergyDataPoint } from "../lib/api";

interface EnergyChartProps {
  data: EnergyDataPoint[];
  loading?: boolean;
  selectedSiteId: string | null;
  days: number;
}

// Format date for chart display
function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-ZA", {
    month: "short",
    day: "numeric",
  });
}

// Aggregate data by date
function aggregateByDate(
  data: EnergyDataPoint[],
  selectedSiteId: string | null
): Array<{
  date: string;
  HVAC: number;
  Lighting: number;
  Other: number;
}> {
  const byDate: Record<
    string,
    { hvac: number; lighting: number; other: number }
  > = {};

  for (const point of data) {
    if (selectedSiteId && point.site_id !== selectedSiteId) {
      continue;
    }

    const dateKey = point.date;
    if (!byDate[dateKey]) {
      byDate[dateKey] = { hvac: 0, lighting: 0, other: 0 };
    }
    byDate[dateKey].hvac += point.hvac_kwh;
    byDate[dateKey].lighting += point.lighting_kwh;
    byDate[dateKey].other += point.other_kwh;
  }

  return Object.entries(byDate)
    .map(([date, values]) => ({
      date: formatDate(date),
      HVAC: Math.round(values.hvac),
      Lighting: Math.round(values.lighting),
      Other: Math.round(values.other),
    }))
    .sort((a, b) => {
      const dateA = new Date(a.date);
      const dateB = new Date(b.date);
      return dateA.getTime() - dateB.getTime();
    });
}

export function EnergyChart({
  data,
  loading = false,
  selectedSiteId,
  days,
}: EnergyChartProps) {
  const chartData = aggregateByDate(data, selectedSiteId);

  // Calculate totals for summary
  const totals = chartData.reduce(
    (acc, point) => ({
      hvac: acc.hvac + point.HVAC,
      lighting: acc.lighting + point.Lighting,
      other: acc.other + point.Other,
    }),
    { hvac: 0, lighting: 0, other: 0 }
  );
  const grandTotal = totals.hvac + totals.lighting + totals.other;

  // Loading skeleton
  if (loading) {
    return (
      <div
        className="rounded p-4"
        style={{
          background: "var(--color-grafana-bg-panel)",
          border: "1px solid var(--color-grafana-border)",
        }}
      >
        <div className="flex items-center gap-2 mb-4">
          <Zap className="h-5 w-5" style={{ color: "var(--color-grafana-yellow)" }} />
          <span
            className="font-medium"
            style={{ color: "var(--color-grafana-text-primary)" }}
          >
            Energy Consumption
          </span>
        </div>
        <div className="h-72 flex flex-col justify-end space-y-2">
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              className="skeleton"
              style={{ height: `${Math.random() * 60 + 20}px` }}
            />
          ))}
        </div>
      </div>
    );
  }

  // Empty state
  if (chartData.length === 0) {
    return (
      <div
        className="rounded p-4"
        style={{
          background: "var(--color-grafana-bg-panel)",
          border: "1px solid var(--color-grafana-border)",
        }}
      >
        <div className="flex items-center gap-2 mb-4">
          <Zap className="h-5 w-5" style={{ color: "var(--color-grafana-yellow)" }} />
          <span
            className="font-medium"
            style={{ color: "var(--color-grafana-text-primary)" }}
          >
            Energy Consumption
          </span>
        </div>
        <div className="h-72 flex items-center justify-center">
          <span style={{ color: "var(--color-grafana-text-disabled)" }}>
            No energy data available
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className="rounded overflow-hidden"
      style={{
        background: "var(--color-grafana-bg-panel)",
        border: "1px solid var(--color-grafana-border)",
      }}
    >
      {/* Header */}
      <div
        className="p-4 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--color-grafana-border)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: "rgba(242, 204, 12, 0.15)" }}
          >
            <Zap className="h-5 w-5" style={{ color: "var(--color-grafana-yellow)" }} />
          </div>
          <div>
            <h3
              className="font-medium text-sm"
              style={{ color: "var(--color-grafana-text-primary)" }}
            >
              Energy Consumption
            </h3>
            <span
              className="text-xs"
              style={{ color: "var(--color-grafana-text-secondary)" }}
            >
              Last {days} days
              {selectedSiteId
                ? ` • ${data.find((d) => d.site_id === selectedSiteId)?.site_name || selectedSiteId}`
                : " • All Sites"}
            </span>
          </div>
        </div>

        {/* Total metric */}
        <div className="text-right">
          <div className="flex items-center gap-1">
            <TrendingUp
              className="h-4 w-4"
              style={{ color: "var(--color-grafana-green)" }}
            />
            <span
              className="text-xl font-medium"
              style={{
                color: "var(--color-grafana-text-primary)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {grandTotal.toLocaleString()}
            </span>
            <span
              className="text-sm"
              style={{ color: "var(--color-grafana-text-secondary)" }}
            >
              kWh
            </span>
          </div>
          <span
            className="text-xs"
            style={{ color: "var(--color-grafana-text-disabled)" }}
          >
            Total consumption
          </span>
        </div>
      </div>

      {/* Chart */}
      <div className="p-4">
        <AreaChart
          className="h-64"
          data={chartData}
          index="date"
          categories={["HVAC", "Lighting", "Other"]}
          colors={["cyan", "amber", "slate"]}
          valueFormatter={(value) => `${value.toLocaleString()} kWh`}
          showLegend={false}
          showGridLines={true}
          showAnimation={true}
          stack={true}
          curveType="monotone"
        />
      </div>

      {/* Category breakdown */}
      <div
        className="px-4 py-3 flex justify-center gap-8"
        style={{ borderTop: "1px solid var(--color-grafana-border)" }}
      >
        {/* HVAC */}
        <div className="text-center">
          <div className="flex items-center gap-2 justify-center mb-1">
            <div
              className="w-3 h-3 rounded"
              style={{ background: "var(--color-grafana-cyan)" }}
            />
            <span
              className="text-xs uppercase tracking-wide"
              style={{ color: "var(--color-grafana-text-secondary)" }}
            >
              HVAC
            </span>
          </div>
          <div
            className="text-lg font-medium"
            style={{
              color: "var(--color-grafana-cyan)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {totals.hvac.toLocaleString()}
          </div>
          <span
            className="text-xs"
            style={{ color: "var(--color-grafana-text-disabled)" }}
          >
            kWh
          </span>
        </div>

        {/* Lighting */}
        <div className="text-center">
          <div className="flex items-center gap-2 justify-center mb-1">
            <div
              className="w-3 h-3 rounded"
              style={{ background: "var(--color-grafana-yellow)" }}
            />
            <span
              className="text-xs uppercase tracking-wide"
              style={{ color: "var(--color-grafana-text-secondary)" }}
            >
              Lighting
            </span>
          </div>
          <div
            className="text-lg font-medium"
            style={{
              color: "var(--color-grafana-yellow)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {totals.lighting.toLocaleString()}
          </div>
          <span
            className="text-xs"
            style={{ color: "var(--color-grafana-text-disabled)" }}
          >
            kWh
          </span>
        </div>

        {/* Other */}
        <div className="text-center">
          <div className="flex items-center gap-2 justify-center mb-1">
            <div
              className="w-3 h-3 rounded"
              style={{ background: "#64748b" }}
            />
            <span
              className="text-xs uppercase tracking-wide"
              style={{ color: "var(--color-grafana-text-secondary)" }}
            >
              Other
            </span>
          </div>
          <div
            className="text-lg font-medium"
            style={{
              color: "var(--color-grafana-text-primary)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {totals.other.toLocaleString()}
          </div>
          <span
            className="text-xs"
            style={{ color: "var(--color-grafana-text-disabled)" }}
          >
            kWh
          </span>
        </div>
      </div>
    </div>
  );
}

export default EnergyChart;

/**
 * EnergyChart Component - Energy consumption visualization
 *
 * Uses Tremor AreaChart to display stacked energy consumption by category.
 *
 * Features:
 * - Stacked area chart (HVAC, Lighting, Other)
 * - Legend with category colors
 * - Tooltip with exact kWh values
 * - Y-axis: kWh, X-axis: dates
 *
 * Props:
 * - data: Energy data points from API
 * - loading: Show loading state
 */

import { Card, Title, AreaChart, Text, Flex } from "@tremor/react";
import { Zap } from "lucide-react";
import type { EnergyDataPoint } from "../lib/api";
import { LoadingCard } from "./LoadingCard";

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

// Aggregate data by date (sum across sites if "All Sites" selected)
function aggregateByDate(
  data: EnergyDataPoint[],
  selectedSiteId: string | null
): Array<{
  date: string;
  HVAC: number;
  Lighting: number;
  Other: number;
}> {
  // Group by date
  const byDate: Record<
    string,
    { hvac: number; lighting: number; other: number }
  > = {};

  for (const point of data) {
    // Filter by site if specified
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

  // Convert to chart format and sort by date
  return Object.entries(byDate)
    .map(([date, values]) => ({
      date: formatDate(date),
      HVAC: Math.round(values.hvac),
      Lighting: Math.round(values.lighting),
      Other: Math.round(values.other),
    }))
    .sort((a, b) => {
      // Parse dates back for sorting
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

  if (loading) {
    return (
      <Card>
        <Flex justifyContent="start" alignItems="center" className="gap-2 mb-4">
          <Zap className="h-5 w-5 text-yellow-500" />
          <Title>Energy Consumption</Title>
        </Flex>
        <div className="h-72">
          <div className="animate-pulse flex flex-col h-full justify-end space-y-2 p-4">
            <div className="h-2 bg-gray-200 rounded w-full"></div>
            <div className="h-8 bg-gray-200 rounded w-full"></div>
            <div className="h-16 bg-gray-200 rounded w-full"></div>
            <div className="h-24 bg-gray-200 rounded w-full"></div>
            <div className="h-12 bg-gray-200 rounded w-full"></div>
            <div className="h-6 bg-gray-200 rounded w-full"></div>
          </div>
        </div>
      </Card>
    );
  }

  if (chartData.length === 0) {
    return (
      <Card>
        <Flex justifyContent="start" alignItems="center" className="gap-2 mb-4">
          <Zap className="h-5 w-5 text-yellow-500" />
          <Title>Energy Consumption</Title>
        </Flex>
        <div className="h-80 flex items-center justify-center">
          <Text className="text-gray-500">No energy data available</Text>
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <Flex justifyContent="between" alignItems="start" className="mb-4">
        <div>
          <Flex justifyContent="start" alignItems="center" className="gap-2">
            <Zap className="h-5 w-5 text-yellow-500" />
            <Title>Energy Consumption</Title>
          </Flex>
          <Text className="text-gray-500">
            Last {days} days{" "}
            {selectedSiteId
              ? `- ${data.find((d) => d.site_id === selectedSiteId)?.site_name || selectedSiteId}`
              : "- All Sites"}
          </Text>
        </div>
        <div className="text-right">
          <Text className="font-medium text-gray-900">
            {grandTotal.toLocaleString()} kWh
          </Text>
          <Text className="text-xs text-gray-500">Total consumption</Text>
        </div>
      </Flex>

      <AreaChart
        className="h-72"
        data={chartData}
        index="date"
        categories={["HVAC", "Lighting", "Other"]}
        colors={["blue", "amber", "slate"]}
        valueFormatter={(value) => `${value.toLocaleString()} kWh`}
        showLegend={true}
        showGridLines={true}
        showAnimation={true}
        stack={true}
        curveType="monotone"
      />

      {/* Category breakdown summary */}
      <Flex justifyContent="center" className="gap-6 mt-4 pt-4 border-t border-gray-100">
        <div className="text-center">
          <div className="flex items-center gap-1 justify-center">
            <div className="w-3 h-3 rounded bg-blue-500" />
            <Text className="text-xs text-gray-500">HVAC</Text>
          </div>
          <Text className="font-medium">{totals.hvac.toLocaleString()} kWh</Text>
        </div>
        <div className="text-center">
          <div className="flex items-center gap-1 justify-center">
            <div className="w-3 h-3 rounded bg-amber-500" />
            <Text className="text-xs text-gray-500">Lighting</Text>
          </div>
          <Text className="font-medium">{totals.lighting.toLocaleString()} kWh</Text>
        </div>
        <div className="text-center">
          <div className="flex items-center gap-1 justify-center">
            <div className="w-3 h-3 rounded bg-slate-500" />
            <Text className="text-xs text-gray-500">Other</Text>
          </div>
          <Text className="font-medium">{totals.other.toLocaleString()} kWh</Text>
        </div>
      </Flex>
    </Card>
  );
}

export default EnergyChart;

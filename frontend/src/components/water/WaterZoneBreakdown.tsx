/**
 * WaterZoneBreakdown - Zone-based water consumption breakdown with cost attribution
 *
 * Displays:
 * - Table with zones ranked by consumption/cost
 * - Color-coded status indicators (normal/elevated/critical)
 * - Trend indicators (up/down/stable)
 * - Cost attribution per zone
 * - Drill-down capability
 */

import { useState } from "react";
import {
  Text,
  BarChart,
  Table,
  TableHead,
  TableRow,
  TableHeaderCell,
  TableBody,
  TableCell,
  Badge,
  Flex,
} from "@tremor/react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

interface ZoneBreakdown {
  zone_id: string;
  zone_name: string;
  consumption_liters: number;
  consumption_percent: number;
  total_cost: number;
  cost_per_liter: number;
  rank: number;
  status: "normal" | "elevated" | "critical";
  trend: "up" | "down" | "stable";
}

interface WaterZoneBreakdownProps {
  siteId: string;
  days?: number;
}

export const WaterZoneBreakdown: React.FC<WaterZoneBreakdownProps> = ({
  siteId,
  days = 30,
}) => {
  const [sortBy, setSortBy] = useState<"consumption" | "cost">("consumption");

  // Mock data generation since backend doesn't yet have zone breakdown endpoint
  const { data: zones, isLoading } = useQuery({
    queryKey: ["water", "zones", "breakdown", siteId, days],
    queryFn: async () => {
      // Fallback: Generate demo zones until backend implements endpoint
      const mockZones: ZoneBreakdown[] = [
        {
          zone_id: "zone-001",
          zone_name: "Restrooms Level 1",
          consumption_liters: 4500,
          consumption_percent: 22,
          total_cost: 450,
          cost_per_liter: 0.1,
          rank: 1,
          status: "elevated",
          trend: "up",
        },
        {
          zone_id: "zone-002",
          zone_name: "Kitchens Level 1-2",
          consumption_liters: 3200,
          consumption_percent: 15.6,
          total_cost: 320,
          cost_per_liter: 0.1,
          rank: 2,
          status: "normal",
          trend: "stable",
        },
        {
          zone_id: "zone-003",
          zone_name: "Irrigation - Courtyard",
          consumption_liters: 6800,
          consumption_percent: 33.1,
          total_cost: 510,
          cost_per_liter: 0.075,
          rank: 3,
          status: "critical",
          trend: "up",
        },
        {
          zone_id: "zone-004",
          zone_name: "Cooling Towers B1",
          consumption_liters: 3500,
          consumption_percent: 17,
          total_cost: 350,
          cost_per_liter: 0.1,
          rank: 4,
          status: "normal",
          trend: "down",
        },
        {
          zone_id: "zone-005",
          zone_name: "Laundry Service",
          consumption_liters: 2400,
          consumption_percent: 11.7,
          total_cost: 240,
          cost_per_liter: 0.1,
          rank: 5,
          status: "normal",
          trend: "stable",
        },
      ];
      return mockZones;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  if (isLoading || !zones) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-center h-64">
          <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Loading zone data...
          </Text>
        </div>
      </div>
    );
  }

  const sorted = [...zones].sort((a, b) =>
    sortBy === "consumption"
      ? b.consumption_liters - a.consumption_liters
      : b.total_cost - a.total_cost
  );

  const statusColors: Record<string, "green" | "yellow" | "red"> = {
    normal: "green",
    elevated: "yellow",
    critical: "red",
  };

  const chartData = sorted.map((z) => ({
    name: z.zone_name.substring(0, 15),
    "Consumption (L)": z.consumption_liters,
  }));

  const highestCost = sorted[0];

  return (
    <div className="space-y-6">
      {/* Highest Cost Zone Card */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <Flex justifyContent="between" alignItems="center">
          <div>
            <Text
              style={{ color: "var(--color-sentinel-text-secondary)" }}
              className="text-xs"
            >
              Highest Cost Zone
            </Text>
            <h4 className="text-xl font-medium mt-1" style={{ color: "var(--color-sentinel-text-primary)" }}>{highestCost.zone_name}</h4>
            <Flex justifyContent="start" alignItems="center" className="gap-4 mt-2">
              <div>
                <Text
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Volume
                </Text>
                <Text className="font-semibold">
                  {(highestCost.consumption_liters / 1000).toFixed(1)}k L
                </Text>
              </div>
              <div>
                <Text
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Cost
                </Text>
                <Text className="font-semibold">
                  R{highestCost.total_cost.toLocaleString()}
                </Text>
              </div>
              <div>
                <Text
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  % of Total
                </Text>
                <Text className="font-semibold">
                  {highestCost.consumption_percent.toFixed(1)}%
                </Text>
              </div>
            </Flex>
          </div>
          <Badge color={statusColors[highestCost.status]}>
            {highestCost.status.toUpperCase()}
          </Badge>
        </Flex>
      </div>

      {/* Consumption Chart */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <Flex justifyContent="between" alignItems="center" className="mb-4">
          <h4 className="font-medium text-base" style={{ color: "var(--color-sentinel-text-primary)" }}>Consumption by Zone</h4>
          <div className="flex gap-2">
            <button
              onClick={() => setSortBy("consumption")}
              className="text-xs px-2 py-1 rounded"
              style={{
                background:
                  sortBy === "consumption"
                    ? "var(--color-sentinel-blue)"
                    : "var(--color-sentinel-bg-secondary)",
                color:
                  sortBy === "consumption"
                    ? "white"
                    : "var(--color-sentinel-text-secondary)",
              }}
            >
              By Volume
            </button>
            <button
              onClick={() => setSortBy("cost")}
              className="text-xs px-2 py-1 rounded"
              style={{
                background:
                  sortBy === "cost"
                    ? "var(--color-sentinel-blue)"
                    : "var(--color-sentinel-bg-secondary)",
                color:
                  sortBy === "cost"
                    ? "white"
                    : "var(--color-sentinel-text-secondary)",
              }}
            >
              By Cost
            </button>
          </div>
        </Flex>
        <BarChart data={chartData} index="name" categories={["Consumption (L)"]} />
      </div>

      {/* Zones Table */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h4 className="font-medium text-base mb-4" style={{ color: "var(--color-sentinel-text-primary)" }}>Zone Details</h4>
        <div className="overflow-x-auto">
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Zone</TableHeaderCell>
                <TableHeaderCell>Consumption</TableHeaderCell>
                <TableHeaderCell>Cost</TableHeaderCell>
                <TableHeaderCell>% of Total</TableHeaderCell>
                <TableHeaderCell>Cost/Liter</TableHeaderCell>
                <TableHeaderCell>Trend</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sorted.map((zone) => (
                <TableRow key={zone.zone_id}>
                  <TableCell>
                    <Text className="font-medium text-sm">
                      {zone.zone_name}
                    </Text>
                  </TableCell>
                  <TableCell>
                    <Text className="text-sm">
                      {(zone.consumption_liters / 1000).toFixed(1)}k L
                    </Text>
                  </TableCell>
                  <TableCell>
                    <Text className="text-sm font-semibold">
                      R{zone.total_cost.toLocaleString()}
                    </Text>
                  </TableCell>
                  <TableCell>
                    <Text className="text-sm">
                      {zone.consumption_percent.toFixed(1)}%
                    </Text>
                  </TableCell>
                  <TableCell>
                    <Text className="text-sm">
                      R{zone.cost_per_liter.toFixed(3)}/L
                    </Text>
                  </TableCell>
                  <TableCell>
                    <Flex justifyContent="start" alignItems="center" className="gap-1">
                      {zone.trend === "up" && (
                        <>
                          <TrendingUp className="h-4 w-4 text-red-500" />
                          <Text className="text-xs text-red-500">Up</Text>
                        </>
                      )}
                      {zone.trend === "down" && (
                        <>
                          <TrendingDown className="h-4 w-4 text-green-500" />
                          <Text className="text-xs text-green-500">Down</Text>
                        </>
                      )}
                      {zone.trend === "stable" && (
                        <>
                          <Minus className="h-4 w-4" style={{color: "var(--color-sentinel-text-secondary)"}} />
                          <Text className="text-xs" style={{color: "var(--color-sentinel-text-secondary)"}}>Stable</Text>
                        </>
                      )}
                    </Flex>
                  </TableCell>
                  <TableCell>
                    <Badge color={statusColors[zone.status]}>
                      {zone.status.substring(0, 3).toUpperCase()}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
};

import { useState } from "react";
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

function badgeStyle(status: string): React.CSSProperties {
  switch (status) {
    case "critical": return { background: "rgba(239, 68, 68, 0.15)", color: "#ef4444" };
    case "elevated": return { background: "rgba(234, 179, 8, 0.15)", color: "#eab308" };
    default: return { background: "rgba(34, 197, 94, 0.15)", color: "#22c55e" };
  }
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
      // Fallback: Generate seeded zones until backend implements endpoint
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
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Loading zone data...
          </span>
        </div>
      </div>
    );
  }

  const sorted = [...zones].sort((a, b) =>
    sortBy === "consumption"
      ? b.consumption_liters - a.consumption_liters
      : b.total_cost - a.total_cost
  );

  const chartData = sorted.map((z) => ({
    name: z.zone_name.substring(0, 15),
    "Consumption (L)": z.consumption_liters,
  }));

  const highestCost = sorted[0];
  const maxConsumption = Math.max(...chartData.map((d) => d["Consumption (L)"]));

  return (
    <div className="space-y-6">
      {/* Highest Cost Zone Card */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between">
          <div>
            <span
              style={{ color: "var(--color-sentinel-text-secondary)" }}
              className="text-xs"
            >
              Highest Cost Zone
            </span>
            <h4 className="text-xl font-medium mt-1" style={{ color: "var(--color-sentinel-text-primary)" }}>{highestCost.zone_name}</h4>
            <div className="flex items-center gap-4 mt-2">
              <div>
                <span
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Volume
                </span>
                <p className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {(highestCost.consumption_liters / 1000).toFixed(1)}k L
                </p>
              </div>
              <div>
                <span
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Cost
                </span>
                <p className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  R{highestCost.total_cost.toLocaleString()}
                </p>
              </div>
              <div>
                <span
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  % of Total
                </span>
                <p className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {highestCost.consumption_percent.toFixed(1)}%
                </p>
              </div>
            </div>
          </div>
          <span
            className="text-xs px-2 py-0.5 rounded font-medium"
            style={badgeStyle(highestCost.status)}
          >
            {highestCost.status.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Consumption Chart */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between mb-4">
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
        </div>
        <div className="space-y-2">
          {chartData.map((item) => {
            const pct = maxConsumption > 0 ? (item["Consumption (L)"] / maxConsumption) * 100 : 0;
            return (
              <div key={item.name} className="flex items-center gap-3">
                <span className="text-xs w-24 shrink-0 truncate" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {item.name}
                </span>
                <div className="flex-grow h-5 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                  <div
                    className="h-full rounded transition-all"
                    style={{
                      width: `${pct}%`,
                      background: "var(--color-sentinel-blue)",
                    }}
                  />
                </div>
                <span className="text-xs font-medium w-16 text-right" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {(item["Consumption (L)"] / 1000).toFixed(1)}k L
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Zones Table */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h4 className="font-medium text-base mb-4" style={{ color: "var(--color-sentinel-text-primary)" }}>Zone Details</h4>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                <th className="text-left py-2 px-2 font-semibold" style={{ color: "var(--color-sentinel-text-secondary)" }}>Zone</th>
                <th className="text-left py-2 px-2 font-semibold" style={{ color: "var(--color-sentinel-text-secondary)" }}>Consumption</th>
                <th className="text-left py-2 px-2 font-semibold" style={{ color: "var(--color-sentinel-text-secondary)" }}>Cost</th>
                <th className="text-left py-2 px-2 font-semibold" style={{ color: "var(--color-sentinel-text-secondary)" }}>% of Total</th>
                <th className="text-left py-2 px-2 font-semibold" style={{ color: "var(--color-sentinel-text-secondary)" }}>Cost/Liter</th>
                <th className="text-left py-2 px-2 font-semibold" style={{ color: "var(--color-sentinel-text-secondary)" }}>Trend</th>
                <th className="text-left py-2 px-2 font-semibold" style={{ color: "var(--color-sentinel-text-secondary)" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((zone) => (
                <tr key={zone.zone_id} style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                  <td className="py-3 px-2">
                    <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {zone.zone_name}
                    </span>
                  </td>
                  <td className="py-3 px-2">
                    <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {(zone.consumption_liters / 1000).toFixed(1)}k L
                    </span>
                  </td>
                  <td className="py-3 px-2">
                    <span className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      R{zone.total_cost.toLocaleString()}
                    </span>
                  </td>
                  <td className="py-3 px-2">
                    <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {zone.consumption_percent.toFixed(1)}%
                    </span>
                  </td>
                  <td className="py-3 px-2">
                    <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      R{zone.cost_per_liter.toFixed(3)}/L
                    </span>
                  </td>
                  <td className="py-3 px-2">
                    <div className="flex items-center gap-1">
                      {zone.trend === "up" && (
                        <>
                          <TrendingUp className="h-4 w-4 text-red-500" />
                          <span className="text-xs text-red-500">Up</span>
                        </>
                      )}
                      {zone.trend === "down" && (
                        <>
                          <TrendingDown className="h-4 w-4 text-green-500" />
                          <span className="text-xs text-green-500">Down</span>
                        </>
                      )}
                      {zone.trend === "stable" && (
                        <>
                          <Minus className="h-4 w-4" style={{color: "var(--color-sentinel-text-secondary)"}} />
                          <span className="text-xs" style={{color: "var(--color-sentinel-text-secondary)"}}>Stable</span>
                        </>
                      )}
                    </div>
                  </td>
                  <td className="py-3 px-2">
                    <span
                      className="text-xs px-2 py-0.5 rounded font-medium"
                      style={badgeStyle(zone.status)}
                    >
                      {zone.status.substring(0, 3).toUpperCase()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

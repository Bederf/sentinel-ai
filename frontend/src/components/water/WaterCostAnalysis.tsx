import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

interface CostAnalysis {
  period: string;
  total_cost: number;
  avg_daily_cost: number;
  tier1_cost: number;
  tier2_cost: number;
  tier3_cost: number;
  fixed_charge: number;
  top_zone_name?: string;
  top_zone_cost?: number;
}

interface ForecastData {
  date: string;
  projected_cost: number;
  confidence_low: number;
  confidence_high: number;
}

interface TariffTier {
  tier: number;
  min_liters: number;
  max_liters: number;
  rate_per_liter: number;
  current_cost: number;
}

interface WaterCostAnalysisProps {
  siteId: string;
}

export const WaterCostAnalysis: React.FC<WaterCostAnalysisProps> = ({
  siteId,
}) => {
  const [activeTabIndex, setActiveTabIndex] = useState<number>(0);
  const [scenarioReduction, setScenarioReduction] = useState(0);

  // Mock cost data
  const { data: costData, isLoading: costLoading } = useQuery({
    queryKey: ["water", "costs", siteId],
    queryFn: async () => {
      const mockData: CostAnalysis = {
        period: "February 2026",
        total_cost: 2480,
        avg_daily_cost: 124,
        tier1_cost: 800,
        tier2_cost: 1200,
        tier3_cost: 380,
        fixed_charge: 100,
        top_zone_name: "Irrigation - Courtyard",
        top_zone_cost: 510,
      };
      return mockData;
    },
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  // Mock forecast data
  const { data: forecast, isLoading: forecastLoading } = useQuery({
    queryKey: ["water", "forecast", siteId],
    queryFn: async () => {
      const mockForecast: ForecastData[] = [];
      const today = new Date();
      for (let i = 0; i < 30; i++) {
        const date = new Date(today);
        date.setDate(date.getDate() + i);
        mockForecast.push({
          date: date.toISOString().split("T")[0],
          projected_cost: 110 + Math.random() * 40,
          confidence_low: 100 + Math.random() * 20,
          confidence_high: 130 + Math.random() * 30,
        });
      }
      return mockForecast;
    },
    staleTime: 60 * 60 * 1000, // 1 hour
  });

  // Mock tariff data
  const tariffTiers: TariffTier[] = [
    {
      tier: 1,
      min_liters: 0,
      max_liters: 5000,
      rate_per_liter: 16.0,
      current_cost: 800,
    },
    {
      tier: 2,
      min_liters: 5001,
      max_liters: 15000,
      rate_per_liter: 24.0,
      current_cost: 1200,
    },
    {
      tier: 3,
      min_liters: 15001,
      max_liters: 999999,
      rate_per_liter: 38.0,
      current_cost: 380,
    },
  ];

  const isLoading = costLoading || forecastLoading;

  if (isLoading || !costData) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-center h-64">
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Loading cost analysis...
          </span>
        </div>
      </div>
    );
  }

  // Calculate projections
  const dailyAvg = costData.avg_daily_cost;
  const monthlyProjection = dailyAvg * 30;
  const annualProjection = monthlyProjection * 12;

  // Calculate scenario savings
  const reductionFactor = 1 - scenarioReduction / 100;
  const scenarioMonthly = monthlyProjection * reductionFactor;
  const scenarioSavings = monthlyProjection - scenarioMonthly;

  // Chart data for forecast
  const forecastChartData =
    forecast?.map((d) => ({
      date: new Date(d.date).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      }),
      "Projected Cost": Math.round(d.projected_cost),
    })) || [];

  const costBreakdownData = [
    {
      name: "Tier 1",
      "Cost (R)": costData.tier1_cost,
    },
    {
      name: "Tier 2",
      "Cost (R)": costData.tier2_cost,
    },
    {
      name: "Tier 3",
      "Cost (R)": costData.tier3_cost,
    },
    {
      name: "Fixed",
      "Cost (R)": costData.fixed_charge,
    },
  ];

  const TABS = ["Current", "Forecast", "Tariff"];
  const maxCostBreakdown = Math.max(...costBreakdownData.map(d => d["Cost (R)"]));
  const maxForecast = forecastChartData.length > 0 ? Math.max(...forecastChartData.map(d => d["Projected Cost"])) : 0;

  return (
    <div>
      <div className="flex gap-1 mb-6 overflow-x-auto border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        {TABS.map((tab, i) => (
          <button
            key={tab}
            onClick={() => setActiveTabIndex(i)}
            className="px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors rounded-t"
            style={{
              color: activeTabIndex === i ? "var(--color-sentinel-text-primary)" : "var(--color-sentinel-text-secondary)",
              borderBottom: activeTabIndex === i ? "2px solid var(--color-sentinel-blue)" : "2px solid transparent",
              background: activeTabIndex === i ? "var(--color-sentinel-bg-panel)" : "transparent",
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      <div>
        {/* Current Period Tab */}
        {activeTabIndex === 0 && (
          <div className="space-y-6">
            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                <span
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Current Period Total
                </span>
                <p className="text-xl font-semibold mt-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  R{costData.total_cost.toLocaleString()}
                </p>
                <span className="text-xs mt-1 block" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  February 2026
                </span>
              </div>

              <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                <span
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Average Daily Cost
                </span>
                <p className="text-xl font-semibold mt-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  R{costData.avg_daily_cost.toLocaleString()}
                </p>
                <span className="text-xs mt-1 block" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Last 7 days
                </span>
              </div>

              <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                <span
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Top Zone by Cost
                </span>
                <p className="text-xl font-semibold mt-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  R{(costData.top_zone_cost || 0).toLocaleString()}
                </p>
                <span className="text-xs mt-1 block" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {costData.top_zone_name}
                </span>
              </div>
            </div>

            {/* Cost Breakdown Chart */}
            <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <h4 className="font-medium text-base mb-4" style={{ color: "var(--color-sentinel-text-primary)" }}>Cost Breakdown by Tier</h4>
              <div className="space-y-3">
                {costBreakdownData.map((item) => {
                  const pct = maxCostBreakdown > 0 ? (item["Cost (R)"] / maxCostBreakdown) * 100 : 0;
                  return (
                    <div key={item.name} className="flex items-center gap-3">
                      <span className="text-xs w-16 shrink-0" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {item.name}
                      </span>
                      <div className="flex-grow h-6 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                        <div
                          className="h-full rounded transition-all"
                          style={{
                            width: `${pct}%`,
                            background: "var(--color-sentinel-emerald)",
                          }}
                        />
                      </div>
                      <span className="text-xs font-medium w-20 text-right" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        R{item["Cost (R)"].toLocaleString()}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Monthly & Annual Projections */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                <span
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Monthly Projection
                </span>
                <p className="text-xl font-semibold mt-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  R{Math.round(monthlyProjection).toLocaleString()}
                </p>
                <span className="text-xs mt-1 block" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Based on current usage pattern
                </span>
              </div>

              <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                <span
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Annual Projection
                </span>
                <p className="text-xl font-semibold mt-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  R{Math.round(annualProjection).toLocaleString()}
                </p>
                <span className="text-xs mt-1 block" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Annualized run rate
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Forecast Tab */}
        {activeTabIndex === 1 && (
          <div className="space-y-6">
            {/* Forecast Chart */}
            <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <h4 className="font-medium text-base" style={{ color: "var(--color-sentinel-text-primary)" }}>30-Day Cost Forecast</h4>
              <span className="text-xs mb-4 block" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Projected daily costs with confidence band
              </span>
              {forecastChartData.length > 0 ? (
                <div className="space-y-1 mt-4">
                  {forecastChartData.slice(0, 30).map((item) => {
                    const pct = maxForecast > 0 ? (item["Projected Cost"] / maxForecast) * 100 : 0;
                    return (
                      <div key={item.date} className="flex items-center gap-2">
                        <span className="text-xs w-16 shrink-0 text-right" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          {item.date}
                        </span>
                        <div className="flex-grow h-4 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                          <div
                            className="h-full rounded transition-all"
                            style={{
                              width: `${pct}%`,
                              background: "var(--color-sentinel-blue)",
                            }}
                          />
                        </div>
                        <span className="text-xs w-14 text-right" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          R{item["Projected Cost"]}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="h-64 flex items-center justify-center">
                  <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    No forecast data available
                  </span>
                </div>
              )}
            </div>

            {/* Scenario Analysis */}
            <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <h4 className="font-medium text-base mb-4" style={{ color: "var(--color-sentinel-text-primary)" }}>Scenario Analysis: Consumption Reduction</h4>

              <div className="space-y-4">
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Reduction Target
                    </span>
                    <span className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>{scenarioReduction}%</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={scenarioReduction}
                    onChange={(e) => setScenarioReduction(Number(e.target.value))}
                    className="w-full h-2 rounded appearance-none cursor-pointer"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                    }}
                  />
                </div>

                <div className="grid grid-cols-3 gap-3 pt-4 border-t" style={{ borderColor: "var(--color-sentinel-border)" }}>
                  <div>
                    <span
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                      className="text-xs"
                    >
                      Baseline Monthly
                    </span>
                    <p className="text-lg font-semibold mt-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      R{Math.round(monthlyProjection).toLocaleString()}
                    </p>
                  </div>

                  <div>
                    <span
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                      className="text-xs"
                    >
                      With {scenarioReduction}% Reduction
                    </span>
                    <p className="text-lg font-semibold mt-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      R{Math.round(scenarioMonthly).toLocaleString()}
                    </p>
                  </div>

                  <div>
                    <span
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                      className="text-xs"
                    >
                      Monthly Savings
                    </span>
                    <p className="text-lg font-semibold mt-1 text-green-500">
                      R{Math.round(scenarioSavings).toLocaleString()}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tariff Tab */}
        {activeTabIndex === 2 && (
          <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <h4 className="font-medium text-base mb-4" style={{ color: "var(--color-sentinel-text-primary)" }}>Current Tariff Structure</h4>

            <div className="mb-6 p-4 rounded" style={{ border: "1px solid var(--color-sentinel-border)" }}>
              <span
                style={{ color: "var(--color-sentinel-text-secondary)" }}
                className="text-xs"
              >
                Tariff Name & Period
              </span>
              <p className="font-semibold mt-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                City Water Schedule 2026 (Effective 2026-01-01)
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid var(--color-sentinel-border)",
                    }}
                  >
                    <th
                      className="text-left py-2 px-2 font-semibold"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Tier
                    </th>
                    <th
                      className="text-left py-2 px-2 font-semibold"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Usage Range
                    </th>
                    <th
                      className="text-left py-2 px-2 font-semibold"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Rate
                    </th>
                    <th
                      className="text-left py-2 px-2 font-semibold"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Your Cost
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {tariffTiers.map((tier) => (
                    <tr
                      key={tier.tier}
                      style={{
                        borderBottom: "1px solid var(--color-sentinel-border)",
                      }}
                    >
                      <td className="py-3 px-2">
                        <span className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Tier {tier.tier}</span>
                      </td>
                      <td className="py-3 px-2">
                        <span className="text-xs" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {tier.min_liters.toLocaleString()} -{" "}
                          {tier.max_liters === 999999
                            ? "∞"
                            : tier.max_liters.toLocaleString()}{" "}
                          L
                        </span>
                      </td>
                      <td className="py-3 px-2">
                        <span className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          R{tier.rate_per_liter.toFixed(2)}/L
                        </span>
                      </td>
                      <td className="py-3 px-2">
                        <span className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          R{tier.current_cost.toLocaleString()}
                        </span>
                      </td>
                    </tr>
                  ))}
                  <tr style={{ fontWeight: "bold" }}>
                    <td colSpan={3} className="py-3 px-2">
                      <span style={{ color: "var(--color-sentinel-text-primary)" }}>Fixed Charge</span>
                    </td>
                    <td className="py-3 px-2">
                      <span className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        R{costData.fixed_charge.toLocaleString()}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * WaterCostAnalysis - Water cost tracking and forecasting dashboard
 *
 * Displays:
 * - Current period costs and KPIs
 * - 30-day cost forecast with confidence band
 * - Monthly/annual projections
 * - Scenario analysis (what-if reduction)
 * - Tariff breakdown by tier
 */

import { useState } from "react";
import {
  Card,
  Title,
  Text,
  Metric,
  Flex,
  LineChart,
  BarChart,
  Tab,
  TabGroup,
  TabList,
  TabPanels,
  TabPanel,
} from "@tremor/react";
import { useQuery } from "@tanstack/react-query";
import { waterApi } from "../../lib/waterApi";

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
  buildingId: string;
}

export const WaterCostAnalysis: React.FC<WaterCostAnalysisProps> = ({
  buildingId,
}) => {
  const [activeTabIndex, setActiveTabIndex] = useState<number>(0);
  const [scenarioReduction, setScenarioReduction] = useState(0);

  // Mock cost data
  const { data: costData, isLoading: costLoading } = useQuery({
    queryKey: ["water", "costs", buildingId],
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
    queryKey: ["water", "forecast", buildingId],
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
      <Card>
        <div className="flex items-center justify-center h-64">
          <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Loading cost analysis...
          </Text>
        </div>
      </Card>
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

  return (
    <TabGroup index={activeTabIndex} onIndexChange={setActiveTabIndex}>
      <TabList className="mb-6">
        <Tab>Current Period</Tab>
        <Tab>Forecast</Tab>
        <Tab>Tariff</Tab>
      </TabList>

      <TabPanels>
        {/* Current Period Tab */}
        <TabPanel>
          <div className="space-y-6">
            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card>
                <Text
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Current Period Total
                </Text>
                <Metric className="mt-2">
                  R{costData.total_cost.toLocaleString()}
                </Metric>
                <Text className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  February 2026
                </Text>
              </Card>

              <Card>
                <Text
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Average Daily Cost
                </Text>
                <Metric className="mt-2">
                  R{costData.avg_daily_cost.toLocaleString()}
                </Metric>
                <Text className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Last 7 days
                </Text>
              </Card>

              <Card>
                <Text
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Top Zone by Cost
                </Text>
                <Metric className="mt-2">
                  R{(costData.top_zone_cost || 0).toLocaleString()}
                </Metric>
                <Text className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {costData.top_zone_name}
                </Text>
              </Card>
            </div>

            {/* Cost Breakdown Chart */}
            <Card>
              <Title>Cost Breakdown by Tier</Title>
              <BarChart
                data={costBreakdownData}
                index="name"
                categories={["Cost (R)"]}
                colors={["emerald"]}
              />
            </Card>

            {/* Monthly & Annual Projections */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card>
                <Text
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Monthly Projection
                </Text>
                <Metric className="mt-2">
                  R{Math.round(monthlyProjection).toLocaleString()}
                </Metric>
                <Text className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Based on current usage pattern
                </Text>
              </Card>

              <Card>
                <Text
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  className="text-xs"
                >
                  Annual Projection
                </Text>
                <Metric className="mt-2">
                  R{Math.round(annualProjection).toLocaleString()}
                </Metric>
                <Text className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Annualized run rate
                </Text>
              </Card>
            </div>
          </div>
        </TabPanel>

        {/* Forecast Tab */}
        <TabPanel>
          <div className="space-y-6">
            {/* Forecast Chart */}
            <Card>
              <Title>30-Day Cost Forecast</Title>
              <Text className="text-xs mb-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Projected daily costs with confidence band
              </Text>
              {forecastChartData.length > 0 && (
                <LineChart
                  data={forecastChartData}
                  index="date"
                  categories={["Projected Cost"]}
                />
              )}
            </Card>

            {/* Scenario Analysis */}
            <Card>
              <Title className="mb-4">Scenario Analysis: Consumption Reduction</Title>

              <div className="space-y-4">
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <Text
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Reduction Target
                    </Text>
                    <Text className="font-semibold">{scenarioReduction}%</Text>
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

                <div className="grid grid-cols-3 gap-3 pt-4 border-t border-gray-200 dark:border-gray-800">
                  <div>
                    <Text
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                      className="text-xs"
                    >
                      Baseline Monthly
                    </Text>
                    <Metric className="mt-1 text-lg">
                      R{Math.round(monthlyProjection).toLocaleString()}
                    </Metric>
                  </div>

                  <div>
                    <Text
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                      className="text-xs"
                    >
                      With {scenarioReduction}% Reduction
                    </Text>
                    <Metric className="mt-1 text-lg">
                      R{Math.round(scenarioMonthly).toLocaleString()}
                    </Metric>
                  </div>

                  <div>
                    <Text
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                      className="text-xs"
                    >
                      Monthly Savings
                    </Text>
                    <Metric className="mt-1 text-lg text-green-500">
                      R{Math.round(scenarioSavings).toLocaleString()}
                    </Metric>
                  </div>
                </div>
              </div>
            </Card>
          </div>
        </TabPanel>

        {/* Tariff Tab */}
        <TabPanel>
          <Card>
            <Title className="mb-4">Current Tariff Structure</Title>

            <div className="mb-6 p-4 rounded border border-gray-200 dark:border-gray-800">
              <Text
                style={{ color: "var(--color-sentinel-text-secondary)" }}
                className="text-xs"
              >
                Tariff Name & Period
              </Text>
              <Text className="font-semibold mt-1">
                City Water Schedule 2026 (Effective 2026-01-01)
              </Text>
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
                        <Text className="font-semibold">Tier {tier.tier}</Text>
                      </td>
                      <td className="py-3 px-2">
                        <Text className="text-xs">
                          {tier.min_liters.toLocaleString()} -{" "}
                          {tier.max_liters === 999999
                            ? "∞"
                            : tier.max_liters.toLocaleString()}{" "}
                          L
                        </Text>
                      </td>
                      <td className="py-3 px-2">
                        <Text className="font-semibold">
                          R{tier.rate_per_liter.toFixed(2)}/L
                        </Text>
                      </td>
                      <td className="py-3 px-2">
                        <Text className="font-semibold">
                          R{tier.current_cost.toLocaleString()}
                        </Text>
                      </td>
                    </tr>
                  ))}
                  <tr style={{ fontWeight: "bold" }}>
                    <td colSpan={3} className="py-3 px-2">
                      Fixed Charge
                    </td>
                    <td className="py-3 px-2">
                      <Text className="font-semibold">
                        R{costData.fixed_charge.toLocaleString()}
                      </Text>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Card>
        </TabPanel>
      </TabPanels>
    </TabGroup>
  );
};

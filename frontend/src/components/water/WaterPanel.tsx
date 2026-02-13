/**
 * WaterPanel - Water Consumption Dashboard
 *
 * Integrated water monitoring with:
 * - Quick stats: Current flow, today's volume, monthly cost, efficiency
 * - 4 main tabs:
 *   - Overview: Anomaly chart + real-time alerts
 *   - Zones: Zone breakdown by consumption/cost
 *   - Costs: Cost tracking, forecasting, scenario analysis
 *   - Alerts: Real-time alert feed with work order integration
 * - Site selector for multi-site support
 */

import { useState, useEffect } from "react";
import {
  Card,
  Title,
  Text,
  Metric,
  Flex,
  Button,
  Badge,
  Tab,
  TabGroup,
  TabList,
  TabPanels,
  TabPanel,
} from "@tremor/react";
import { Droplets, Building2, ChevronDown, AlertTriangle, CheckCircle } from "lucide-react";
import { waterApi } from "../../lib/waterApi";
import type {
  WaterAlert,
  WaterConsumption,
  WaterTrending,
  CurrentFlowResponse,
} from "../../lib/waterApi";
import { WaterZoneBreakdown } from "./WaterZoneBreakdown";
import { WaterCostAnalysis } from "./WaterCostAnalysis";
import { WaterAnomalyChart } from "./WaterAnomalyChart";
import { WaterAlertPanel } from "./WaterAlertPanel";

interface WaterPanelProps {
  siteId?: string;
}

export function WaterPanel({ siteId: propSiteId }: WaterPanelProps) {
  const [selectedSiteId, setSelectedSiteId] = useState<string>(propSiteId || "site-002");
  const [activeTabIndex, setActiveTabIndex] = useState<number>(0);
  const [currentFlow, setCurrentFlow] = useState<CurrentFlowResponse | null>(null);
  const [consumptionData, setConsumptionData] = useState<WaterConsumption[]>([]);
  const [alerts, setAlerts] = useState<WaterAlert[]>([]);
  const [trending, setTrending] = useState<WaterTrending | null>(null);

  // Fetch current flow rate (poll every 30 seconds)
  useEffect(() => {
    const fetchFlow = async () => {
      try {
        const flow = await waterApi.getCurrentFlow(selectedSiteId);
        setCurrentFlow(flow);
      } catch (err) {
        console.error("Failed to fetch current flow:", err);
        // Fallback for demo mode
        setCurrentFlow({
          site: selectedSiteId,
          flow_rate_lpm: 12.5,
          timestamp: new Date().toISOString(),
          meter_id: "meter-001",
        });
      }
    };

    fetchFlow();
    const interval = setInterval(fetchFlow, 30000); // 30 seconds
    return () => clearInterval(interval);
  }, [selectedSiteId]);

  // Fetch consumption data (last 7 days)
  useEffect(() => {
    const fetchConsumption = async () => {
      try {
        await new Promise((resolve) => setTimeout(resolve, 400));
        const endDate = new Date();
        const startDate = new Date();
        startDate.setDate(startDate.getDate() - 7);

        const data = await waterApi.getConsumption(
          selectedSiteId,
          startDate.toISOString().split("T")[0],
          endDate.toISOString().split("T")[0]
        );
        setConsumptionData(data);
      } catch (err) {
        console.error("Failed to fetch consumption:", err);
        // Fallback for demo mode
        const demoData: WaterConsumption[] = [];
        for (let i = 6; i >= 0; i--) {
          const date = new Date();
          date.setDate(date.getDate() - i);
          demoData.push({
            timestamp: date.toISOString(),
            volume_liters: 2000 + Math.random() * 1000,
            meter_id: "meter-001",
          });
        }
        setConsumptionData(demoData);
      }
    };

    fetchConsumption();
  }, [selectedSiteId]);

  // Fetch alerts
  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        await new Promise((resolve) => setTimeout(resolve, 500));
        const alertData = await waterApi.getActiveAlerts(selectedSiteId);
        setAlerts(alertData);
      } catch (err) {
        console.error("Failed to fetch alerts:", err);
        // Fallback for demo mode
        setAlerts([
          {
            alert_id: "alert-001",
            site: selectedSiteId,
            alert_type: "continuous_flow",
            severity: "critical",
            timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
            status: "active",
            details: {
              flow_rate_lpm: 45,
              duration_minutes: 120,
              location: "Basement Restrooms",
            },
          },
          {
            alert_id: "alert-002",
            site: selectedSiteId,
            alert_type: "unusual_pattern",
            severity: "medium",
            timestamp: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
            status: "active",
            details: {
              flow_rate_lpm: 22.5,
              percent_above_baseline: 180,
            },
          },
        ]);
      }
    };

    fetchAlerts();
  }, [selectedSiteId]);

  // Fetch trending data
  useEffect(() => {
    const fetchTrending = async () => {
      try {
        await new Promise((resolve) => setTimeout(resolve, 600));
        const trendData = await waterApi.getTrending(selectedSiteId, "week");
        setTrending(trendData);
      } catch (err) {
        console.error("Failed to fetch trending:", err);
        // Fallback for demo mode
        setTrending({
          site: selectedSiteId,
          period: "week",
          start_date: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
          end_date: new Date().toISOString(),
          total_volume_liters: 45000,
          average_flow_rate_lpm: 12.5,
          peak_flow_rate_lpm: 22.0,
          baseline_comparison_percent: 7.1,
          trend_direction: "up",
          record_count: 7,
        });
      }
    };

    fetchTrending();
  }, [selectedSiteId]);

  // Calculate KPIs
  const todayVolume = consumptionData
    .filter((d) => {
      const date = new Date(d.timestamp);
      const today = new Date();
      return date.toDateString() === today.toDateString();
    })
    .reduce((sum, d) => sum + d.volume_liters, 0);

  const monthlyVolume = consumptionData.reduce((sum, d) => sum + d.volume_liters, 0);

  // Handle alert resolution
  const handleResolveAlert = async (alertId: string) => {
    try {
      await waterApi.resolveAlert(alertId, {
        notes: "Resolved via dashboard",
        resolved_by: "admin",
      });
      // Refresh alerts
      const updatedAlerts = await waterApi.getActiveAlerts(selectedSiteId);
      setAlerts(updatedAlerts);
    } catch (err) {
      console.error("Failed to resolve alert:", err);
      alert("Failed to resolve alert. Please try again.");
    }
  };

  // Format chart data
  const consumptionChartData = consumptionData.map((d) => ({
    date: new Date(d.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    volume: d.volume_liters,
  }));

  const severityColors: Record<string, "red" | "yellow" | "blue" | "green"> = {
    critical: "red",
    high: "red",
    medium: "yellow",
    low: "blue",
  };

  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: "rgba(59, 130, 246, 0.15)" }}
          >
            <Droplets className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
          </div>
          <div>
            <h2
              className="text-lg font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Water Consumption
            </h2>
            <p
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Real-time monitoring, leak detection, and consumption trending
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Site Selector */}
          <div className="relative">
            <Building2
              className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            />
            <ChevronDown
              className="absolute right-2 top-1/2 transform -translate-y-1/2 h-3 w-3 pointer-events-none"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            />
            <select
              value={selectedSiteId}
              onChange={(e) => setSelectedSiteId(e.target.value)}
              className="pl-9 pr-7 py-1.5 text-sm rounded appearance-none cursor-pointer"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
                outline: "none",
                minWidth: "200px",
              }}
            >
              <option value="site-002">Sandton City Office Tower</option>
              <option value="site-003">Rosebank Mini Mall</option>
              <option value="site-005">Cape Town Harbour</option>
            </select>
          </div>
        </div>
      </div>

      {/* Quick Stats KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <Flex justifyContent="between" alignItems="center">
            <Text style={{ color: "var(--color-sentinel-text-secondary)" }} className="text-xs">
              Today's Consumption
            </Text>
            <Droplets className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
          </Flex>
          <Metric className="text-xl">{todayVolume.toLocaleString()}</Metric>
          <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Liters
          </Text>
        </Card>

        <Card>
          <Flex justifyContent="between" alignItems="center">
            <Text style={{ color: "var(--color-sentinel-text-secondary)" }} className="text-xs">
              Monthly Cost
            </Text>
            <Droplets className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
          </Flex>
          <Metric className="text-xl">R2,480</Metric>
          <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Feb estimate
          </Text>
        </Card>

        <Card>
          <Flex justifyContent="between" alignItems="center">
            <Text style={{ color: "var(--color-sentinel-text-secondary)" }} className="text-xs">
              Active Alerts
            </Text>
            <AlertTriangle className="h-4 w-4" style={{ color: "var(--color-sentinel-red)" }} />
          </Flex>
          <Metric className="text-xl">{alerts.length}</Metric>
          <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {alerts.some((a) => a.severity === "critical" || a.severity === "high")
              ? "Critical"
              : "Check required"}
          </Text>
        </Card>

        <Card>
          <Flex justifyContent="between" alignItems="center">
            <Text style={{ color: "var(--color-sentinel-text-secondary)" }} className="text-xs">
              Efficiency
            </Text>
            <Droplets className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
          </Flex>
          <Metric className="text-xl">
            {trending ? `${Math.abs(trending.baseline_comparison_percent).toFixed(1)}%` : "---"}
          </Metric>
          <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {trending && trending.baseline_comparison_percent > 0 ? "Above" : "Below"} baseline
          </Text>
        </Card>
      </div>

      {/* Tab Navigation and Content */}
      <TabGroup index={activeTabIndex} onIndexChange={setActiveTabIndex}>
        <TabList className="mb-6">
          <Tab>Overview</Tab>
          <Tab>Zones</Tab>
          <Tab>Costs & Forecast</Tab>
          <Tab>Alerts & Work Orders</Tab>
        </TabList>

        <TabPanels>
          <TabPanel>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <WaterAnomalyChart zoneId={selectedSiteId} days={7} />
              <WaterAlertPanel buildingId={selectedSiteId} />
            </div>
          </TabPanel>

          <TabPanel>
            <WaterZoneBreakdown buildingId={selectedSiteId} days={30} />
          </TabPanel>

          <TabPanel>
            <WaterCostAnalysis buildingId={selectedSiteId} />
          </TabPanel>

          <TabPanel>
            <WaterAlertPanel buildingId={selectedSiteId} />
          </TabPanel>
        </TabPanels>
      </TabGroup>
    </div>
  );
}

// Placeholder for LineChart (would import from @tremor/react in production)
function LineChartPlaceholder({ data }: { data: Array<{ date: string; volume: number }> }) {
  const maxValue = Math.max(...data.map((d) => d.volume));

  return (
    <div className="w-full h-full flex flex-col justify-end">
      <div className="flex items-end justify-between gap-1 h-48">
        {data.map((d, i) => (
          <div key={i} className="flex-1 flex flex-col items-center">
            <div
              className="w-full rounded-t transition-all"
              style={{
                height: `${(d.volume / maxValue) * 100}%`,
                background: "var(--color-sentinel-blue)",
                minHeight: "4px",
              }}
            />
            <Text className="text-xs mt-1" style={{ fontSize: "9px" }}>
              {d.date}
            </Text>
          </div>
        ))}
      </div>
    </div>
  );
}

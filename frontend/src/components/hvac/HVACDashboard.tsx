/**
 * HVACDashboard - Main HVAC Module Dashboard
 *
 * Orchestrates all HVAC module components with 5 tabs:
 * 1. Overview - Zone summary + compact equipment/comfort panels
 * 2. Zones - Full ZoneOverviewPanel
 * 3. Equipment - EquipmentStatusPanel (AHUs, FCUs, Chillers) + health
 * 4. Optimization - ThermalRunwayChart + PrecoolingSchedule
 * 5. Health Config - HealthConfigEditor (engineer-only)
 */

import { useState, useEffect, useRef } from "react";
import {
  Card,
  Title,
  Text,
  Badge,
  Flex,
  Grid,
  Tab,
  TabGroup,
  TabList,
  TabPanel,
  TabPanels,
} from "@tremor/react";
import {
  Thermometer,
  Wind,
  Activity,
  Settings,
  AlertTriangle,
  CheckCircle,
} from "lucide-react";
import { hvacApi, type HVACOverview } from "../../lib/hvacApi";
import { fetchEnergyComparisonSummary, calculateCarbonOffset } from "../../lib/api/energy";
import { SentinelValueCard } from "../SentinelValueCard";
import type { ComparisonSummary } from "../../lib/api/energy";
import ZoneOverviewPanel from "./ZoneOverviewPanel";
import EquipmentStatusPanel from "./EquipmentStatusPanel";
import ChillerControlPanel from "./ChillerControlPanel";
import { ThermalOptimizationPanelGated } from "./ThermalOptimizationPanelGated";
import ComfortAssistant from "./ComfortAssistant";
import HealthConfigEditor from "./HealthConfigEditor";

interface HVACDashboardProps {
  siteId: string;
  onAIRecommendation?: (recommendation: AIRecommendation) => void;
  enabledModules?: string[];
}

interface AIRecommendation {
  id: string;
  type: "hvac" | "energy" | "cross_system";
  priority: "low" | "medium" | "high" | "critical";
  title: string;
  description: string;
  source_module: string;
  related_modules?: string[];
  action?: {
    type: string;
    target: string;
    value: unknown;
  };
  timestamp: string;
}

// Generate AI recommendations from HVAC alerts
function generateRecommendations(data: HVACOverview, modules: string[]): AIRecommendation[] {
  const recs: AIRecommendation[] = [];
  const now = new Date().toISOString();

  // Convert HVAC alerts to recommendations
  data.alerts.forEach((alert) => {
    if (alert.type === "zone_fault") {
      recs.push({
        id: `hvac-fault-${Date.now()}-${alert.zone_id}`,
        type: "hvac",
        priority: "high",
        title: alert.title,
        description: alert.description,
        source_module: "hvac",
        timestamp: now,
      });
    }

    if (alert.type === "temp_deviation" && alert.priority === "high") {
      recs.push({
        id: `hvac-temp-${Date.now()}-${alert.zone_id}`,
        type: "hvac",
        priority: "medium",
        title: alert.title,
        description: alert.description,
        source_module: "hvac",
        timestamp: now,
      });
    }

    if (alert.type === "equipment_health") {
      recs.push({
        id: `hvac-health-${Date.now()}-${alert.equipment_id}`,
        type: "hvac",
        priority: alert.priority,
        title: alert.title,
        description: alert.description,
        source_module: "hvac",
        timestamp: now,
      });
    }
  });

  // Cross-system recommendation if Energy module is active
  if (modules.includes("energy") && data.overall_health < 80) {
    recs.push({
      id: `cross-energy-${Date.now()}`,
      type: "cross_system",
      priority: "medium",
      title: "HVAC Health Impact on Energy",
      description: `HVAC system health at ${data.overall_health.toFixed(0)}%. Poor equipment health may increase energy consumption.`,
      source_module: "hvac",
      related_modules: ["energy"],
      timestamp: now,
    });
  }

  return recs;
}

export function HVACDashboard({
  siteId,
  onAIRecommendation,
  enabledModules = ["hvac"],
}: HVACDashboardProps) {
  const [overview, setOverview] = useState<HVACOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState(0);
  const [comparison, setComparison] = useState<ComparisonSummary | null>(null);

  // Use ref to track if component is mounted
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    async function loadOverview() {
      try {
        const data = await hvacApi.getOverview(siteId);
        if (!mountedRef.current) return;

        setOverview(data);

        // Generate AI recommendations based on alerts
        const recommendations = generateRecommendations(data, enabledModules);
        recommendations.forEach((rec) => onAIRecommendation?.(rec));

        setLoading(false);
      } catch {
        if (mountedRef.current) {
          setLoading(false);
        }
      }
    }

    loadOverview();
    const interval = setInterval(loadOverview, 15000);

    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [siteId, enabledModules, onAIRecommendation]);

  // Fetch energy comparison for HVAC value card
  useEffect(() => {
    fetchEnergyComparisonSummary(siteId)
      .then((data) => { if (mountedRef.current) setComparison(data); })
      .catch(() => {});
  }, [siteId]);

  if (loading) {
    return (
      <div className="h-full p-4 md:p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)" }}>
            <Wind className="h-6 w-6" style={{ color: "#3B82F6" }} />
          </div>
          <div>
            <h1 className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>HVAC Control</h1>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Climate Control & Thermal Management</p>
          </div>
        </div>
        <div className="animate-pulse h-96 bg-gray-100 dark:bg-gray-800 rounded" />
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="h-full p-4 md:p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)" }}>
            <Wind className="h-6 w-6" style={{ color: "#3B82F6" }} />
          </div>
          <div>
            <h1 className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>HVAC Control</h1>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Climate Control & Thermal Management</p>
          </div>
        </div>
        <Text className="text-red-500">Failed to load HVAC data</Text>
      </div>
    );
  }

  // Build tab arrays to avoid Tremor typing issues
  const tabs = [
    <Tab key="overview">
      <Flex alignItems="center" className="gap-2">
        Overview
        {overview.alerts.length > 0 && (
          <Badge
            color={overview.alerts.some((a) => a.priority === "critical") ? "red" : "amber"}
            size="xs"
          >
            {overview.alerts.length}
          </Badge>
        )}
      </Flex>
    </Tab>,
    <Tab key="zones">
      <Flex alignItems="center" className="gap-2">
        Zones
        <Badge
          color={overview.zones.fault > 0 ? "red" : "green"}
          size="xs"
        >
          {overview.zones.total}
        </Badge>
      </Flex>
    </Tab>,
    <Tab key="equipment">Equipment</Tab>,
    <Tab key="optimization">Optimize</Tab>,
    <Tab key="health-config">
      <Flex alignItems="center" className="gap-1">
        <Settings className="w-4 h-4" />
        Health
      </Flex>
    </Tab>,
  ];

  const panels = [
    // Overview Tab
    <TabPanel key="overview">
      <div className="space-y-4">
        {/* SENTINEL Value Card */}
        {comparison ? (
          <SentinelValueCard
            title="HVAC Optimization Impact"
            icon={Wind}
            baseline={{
              label: "Without SENTINEL",
              value: Math.round(comparison.actual.hvac_kwh),
              unit: "kWh",
              costZar: Math.round(comparison.actual.hvac_kwh * 5),
            }}
            sentinel={{
              label: "With SENTINEL AI",
              value: Math.round(comparison.sentinel.hvac_kwh),
              unit: "kWh",
              costZar: Math.round(comparison.sentinel.hvac_kwh * 5),
            }}
            savingsPercent={
              comparison.actual.hvac_kwh > 0
                ? ((comparison.actual.hvac_kwh - comparison.sentinel.hvac_kwh) / comparison.actual.hvac_kwh) * 100
                : 0
            }
            carbonSavedKg={calculateCarbonOffset(comparison.actual.hvac_kwh - comparison.sentinel.hvac_kwh)}
            period="Monthly"
          />
        ) : (
          <SentinelValueCard
            title="HVAC Optimization Impact"
            icon={Wind}
            baseline={{ label: "", value: 0, unit: "kWh" }}
            sentinel={{ label: "", value: 0, unit: "kWh" }}
            savingsPercent={0}
            period="Monthly"
            collecting
          />
        )}

        {/* Status Cards */}
        <Grid className="grid grid-cols-4 gap-4">
          <Card decoration="top" decorationColor="green">
            <Flex alignItems="center" className="gap-2 mb-2">
              <Thermometer className="w-5 h-5 text-blue-400" />
              <Text className="font-medium">Zones</Text>
            </Flex>
            <div className="text-3xl font-bold">{overview.zones.total}</div>
            <Text className="text-xs text-gray-400">
              {overview.zones.normal} running, {overview.zones.fault} fault
            </Text>
          </Card>

          <Card decoration="top" decorationColor="cyan">
            <Flex alignItems="center" className="gap-2 mb-2">
              <Activity className="w-5 h-5 text-cyan-400" />
              <Text className="font-medium">Chillers</Text>
            </Flex>
            <div className="text-3xl font-bold">
              {overview.chillers_running}/{overview.equipment.chiller?.count || 0}
            </div>
            <Text className="text-xs text-gray-400">Running</Text>
          </Card>

          <Card
            decoration="top"
            decorationColor={overview.health_status === "healthy" ? "green" : overview.health_status === "attention" ? "amber" : "red"}
          >
            <Flex alignItems="center" className="gap-2 mb-2">
              {overview.health_status === "healthy" ? (
                <CheckCircle className="w-5 h-5 text-green-400" />
              ) : (
                <AlertTriangle className="w-5 h-5 text-amber-400" />
              )}
              <Text className="font-medium">Health</Text>
            </Flex>
            <div className="text-3xl font-bold">{overview.overall_health.toFixed(0)}%</div>
            <Text className="text-xs text-gray-400 capitalize">
              {overview.health_status}
            </Text>
          </Card>

          <Card decoration="top" decorationColor="amber">
            <Flex alignItems="center" className="gap-2 mb-2">
              <AlertTriangle className="w-5 h-5 text-amber-400" />
              <Text className="font-medium">Alerts</Text>
            </Flex>
            <div className="text-3xl font-bold">{overview.alerts.length}</div>
            <Text className="text-xs text-gray-400">
              {overview.alerts.filter((a) => a.priority === "high" || a.priority === "critical").length} high priority
            </Text>
          </Card>
        </Grid>

        {/* Alerts */}
        {overview.alerts.length > 0 && (
          <Card>
            <Title className="text-sm">Active Alerts</Title>
            <div className="space-y-2 mt-3">
              {overview.alerts.slice(0, 5).map((alert, idx) => (
                <div
                  key={idx}
                  className={`p-3 rounded-lg ${
                    alert.priority === "critical"
                      ? "bg-red-900/20 border border-red-500/30"
                      : alert.priority === "high"
                      ? "bg-amber-900/20 border border-amber-500/30"
                      : "bg-blue-900/20 border border-blue-500/30"
                  }`}
                >
                  <Flex justifyContent="between">
                    <Text className="font-medium">{alert.title}</Text>
                    <Badge
                      color={
                        alert.priority === "critical"
                          ? "red"
                          : alert.priority === "high"
                          ? "amber"
                          : "blue"
                      }
                      size="xs"
                    >
                      {alert.priority}
                    </Badge>
                  </Flex>
                  <Text className="text-xs text-gray-400 mt-1">
                    {alert.description}
                  </Text>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* Compact Panels */}
        <Grid className="grid grid-cols-2 gap-4">
          <div className="space-y-4">
            <ZoneOverviewPanel siteId={siteId} compact />
          </div>
          <div className="space-y-4">
            <ChillerControlPanel siteId={siteId} compact />
            <ThermalOptimizationPanelGated siteId={siteId} compact />
            <ComfortAssistant compact />
          </div>
        </Grid>
      </div>
    </TabPanel>,

    // Zones Tab
    <TabPanel key="zones">
      <ZoneOverviewPanel siteId={siteId} />
    </TabPanel>,

    // Equipment Tab
    <TabPanel key="equipment">
      <div className="space-y-6">
        <EquipmentStatusPanel siteId={siteId} />
        <ChillerControlPanel siteId={siteId} />
      </div>
    </TabPanel>,

    // Optimization Tab
    <TabPanel key="optimization">
      <ThermalOptimizationPanelGated siteId={siteId} />
    </TabPanel>,

    // Health Config Tab
    <TabPanel key="health-config">
      <HealthConfigEditor />
    </TabPanel>,
  ];

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6">
      {/* Page Header — matches Lighting tab pattern */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)" }}>
              <Wind className="h-6 w-6" style={{ color: "#3B82F6" }} />
            </div>
            <div>
              <h1 className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                HVAC Control
              </h1>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Climate Control & Thermal Management
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Tabbed Views */}
      <TabGroup index={activeTab} onIndexChange={setActiveTab}>
        <TabList className="mb-4 overflow-x-auto">{tabs as unknown as React.ReactElement}</TabList>
        <TabPanels>{panels as unknown as React.ReactElement}</TabPanels>
      </TabGroup>
    </div>
  );
}

export default HVACDashboard;

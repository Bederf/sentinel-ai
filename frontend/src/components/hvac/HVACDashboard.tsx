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
  AlertTriangle,
  CheckCircle,
  Brain,
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
  const [comparisonLoading, setComparisonLoading] = useState(true);

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

  // Fetch energy comparison for HVAC value card (re-polls with overview)
  useEffect(() => {
    let cancelled = false;
    setComparisonLoading(true);
    fetchEnergyComparisonSummary(siteId)
      .then((data) => { if (mountedRef.current && !cancelled) setComparison(data); })
      .catch(() => {})
      .finally(() => { if (mountedRef.current && !cancelled) setComparisonLoading(false); });
    return () => { cancelled = true; };
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
        <div
          className="animate-pulse h-96 rounded-lg"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        />
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
        <span className="text-sm" style={{ color: "var(--color-sentinel-red)" }}>Failed to load HVAC data</span>
      </div>
    );
  }

  // Build tab arrays — clean labels matching Lighting tab style
  const tabs = [
    <Tab key="overview">Overview</Tab>,
    <Tab key="zones">Zones</Tab>,
    <Tab key="equipment">Equipment</Tab>,
    <Tab key="optimization">Optimize</Tab>,
    <Tab key="health-config">Health</Tab>,
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
            baseline={{ label: "Without SENTINEL", value: 0, unit: "kWh" }}
            sentinel={{ label: "With SENTINEL AI", value: 0, unit: "kWh" }}
            savingsPercent={0}
            period="Monthly"
            collecting={comparisonLoading}
          />
        )}

        {/* Status Cards — Grafana style (matching Lighting) */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <Thermometer className="w-5 h-5" style={{ color: "#3B82F6" }} />
              <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>Zones</span>
            </div>
            <div className="text-3xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>{overview.zones.total}</div>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {overview.zones.normal} running, {overview.zones.fault} fault
            </span>
          </div>

          <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <Activity className="w-5 h-5" style={{ color: "#06B6D4" }} />
              <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>Chillers</span>
            </div>
            <div className="text-3xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              {overview.chillers_running}/{overview.equipment.chiller?.count || 0}
            </div>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>Running</span>
          </div>

          <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <div className="flex items-center gap-2 mb-2">
              {overview.health_status === "healthy" ? (
                <CheckCircle className="w-5 h-5" style={{ color: "#22C55E" }} />
              ) : (
                <AlertTriangle className="w-5 h-5" style={{ color: "#F59E0B" }} />
              )}
              <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>Health</span>
            </div>
            <div className="text-3xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>{overview.overall_health.toFixed(0)}%</div>
            <span className="text-xs capitalize" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {overview.health_status}
            </span>
          </div>

          <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-5 h-5" style={{ color: "#F59E0B" }} />
              <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>Alerts</span>
            </div>
            <div className="text-3xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>{overview.alerts.length}</div>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {overview.alerts.filter((a) => a.priority === "high" || a.priority === "critical").length} high priority
            </span>
          </div>
        </div>

        {/* SENTINEL Intelligence Summary */}
        {overview.sentinel_intelligence && (
          <div
            className="rounded-lg p-4"
            style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
          >
            <div className="flex items-center gap-2 mb-2">
              <Brain className="w-5 h-5" style={{ color: "#8B5CF6" }} />
              <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                SENTINEL HVAC Intelligence
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
              <div>
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Posture: </span>
                <span className="capitalize" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {overview.sentinel_intelligence.building_posture}
                </span>
              </div>
              <div>
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Guidance: </span>
                <span className="capitalize" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {overview.sentinel_intelligence.operator_guidance.mode.replace("_", " ")}
                </span>
              </div>
              <div>
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Primary Voice: </span>
                <span className="capitalize" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {(overview.sentinel_intelligence.primary_narrative?.voice || "none").replace("_", " ")}
                </span>
              </div>
            </div>
            <div className="mt-2 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {overview.sentinel_intelligence.operator_guidance.headline}
            </div>
            {overview.sentinel_intelligence.primary_narrative?.message && (
              <div className="mt-1 text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {overview.sentinel_intelligence.primary_narrative.message}
              </div>
            )}
          </div>
        )}

        {/* Raw Bridge Telemetry Summary */}
        {overview.raw_telemetry && (
          <div
            className="rounded-lg p-4"
            style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
          >
            <div className="flex items-center gap-2 mb-2">
              <Activity className="w-5 h-5" style={{ color: "#06B6D4" }} />
              <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Raw Bridge Telemetry
              </span>
              <span
                className="text-xs px-2 py-0.5 rounded capitalize"
                style={{
                  background: overview.raw_telemetry.status === "live" ? "rgba(16,185,129,0.15)" : "rgba(245,158,11,0.15)",
                  color: overview.raw_telemetry.status === "live" ? "var(--color-sentinel-green)" : "var(--color-sentinel-amber)",
                }}
              >
                {overview.raw_telemetry.status}
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
              <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Zones:{" "}
                <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {overview.raw_telemetry.zones_with_readings ?? 0}/{overview.raw_telemetry.zone_count ?? 0}
                </span>
              </div>
              <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                HVAC Power:{" "}
                <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {overview.raw_telemetry.power?.hvac_kw?.toFixed(2) ?? "0.00"} kW
                </span>
              </div>
              <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Equipment:{" "}
                <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {overview.raw_telemetry.equipment_summary?.online ?? 0}/{overview.raw_telemetry.equipment_summary?.total ?? 0} online
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Alerts */}
        {overview.alerts.length > 0 && (
          <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <h3 className="text-sm font-medium mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>Active Alerts</h3>
            <div className="space-y-2">
              {overview.alerts.slice(0, 5).map((alert, idx) => {
                const alertColor = alert.priority === "critical" ? "#EF4444" : alert.priority === "high" ? "#F59E0B" : "#3B82F6";
                return (
                <div
                  key={idx}
                  className="p-3 rounded-lg"
                  style={{ background: `${alertColor}15`, border: `1px solid ${alertColor}30` }}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{alert.title}</span>
                    <span
                      className="text-xs px-2 py-0.5 rounded capitalize"
                      style={{ background: `${alertColor}20`, color: alertColor }}
                    >
                      {alert.priority}
                    </span>
                  </div>
                  <span className="text-xs mt-1 block" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {alert.description}
                  </span>
                </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Compact Panels */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-4">
            <ZoneOverviewPanel siteId={siteId} compact />
          </div>
          <div className="space-y-4">
            <ChillerControlPanel siteId={siteId} compact />
            <ThermalOptimizationPanelGated siteId={siteId} compact />
            <ComfortAssistant compact />
          </div>
        </div>
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
        <TabList
          className="mb-4 overflow-x-auto [&>*]:whitespace-nowrap rounded-lg"
          style={{
            border: "1px solid var(--color-sentinel-border)",
            background: "var(--color-sentinel-bg-panel)",
          }}
        >
          {tabs as unknown as React.ReactElement}
        </TabList>
        <TabPanels>{panels as unknown as React.ReactElement}</TabPanels>
      </TabGroup>
    </div>
  );
}

export default HVACDashboard;

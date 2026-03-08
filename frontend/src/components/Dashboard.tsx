/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * Dashboard Component - SENTINEL Risk Dashboard
 *
 * Features:
 * - Top row: 5 KPI stat panels (draggable)
 * - Site protection overview grid (click to drill into site detail)
 * - Energy consumption chart with site filter + time period tabs
 *
 * Site-specific intelligence panels (lighting, solar, BESS, energy comparison,
 * risk predictions, comfort, occupancy, validation) live in SiteDetail.tsx.
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect, useMemo } from "react";
import { useServerEvents } from "@/hooks/useServerEvents";
import { useSimulation } from "@/contexts/SimulationContext";
import {
  Building2,
  AlertTriangle,
  Cpu,
  Shield,
  Bell,
  DollarSign,
  RefreshCw,
} from "lucide-react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  horizontalListSortingStrategy,
  arrayMove,
} from '@dnd-kit/sortable';
import api from '@/lib/api';
import type { DashboardStats, Site, Prediction, EnergyDataPoint } from '@/lib/api';
import { useBuildingsList } from "@/hooks/useBuildingsList";
import { SortableKPICard } from "./SortableKPICard";
import { DashboardSection } from "./DashboardSection";
import { SiteCard } from "./SiteCard";
import { SiteDetail } from "./SiteDetail";
import { EnergyChart } from "./EnergyChart";
import { type View } from "./Sidebar";
import { useModules } from "@/contexts/ModuleHooks";

// Time period options for energy chart
const TIME_PERIODS = [7, 30, 90] as const;
type TimePeriod = (typeof TIME_PERIODS)[number];

type KPICardId =
  | 'kpi-protected-sites'
  | 'kpi-monitored-assets'
  | 'kpi-active-risks'
  | 'kpi-potential-savings'
  | 'kpi-risk-predictions';

interface DashboardProps {
  onViewChange: (view: View) => void;
}

export function Dashboard({ onViewChange }: DashboardProps) {
  // React Query hooks — filter to primary site only
  const { data: allSites = [] } = useBuildingsList();
  const buildingsList = allSites;

  // Module gating
  const { isModuleActive, activeModules } = useModules();

  // Real-time event updates from backend SSE
  useServerEvents();

  // Simulation context for live sim data
  const { running: isSimulationRunning, _occupancyPercent, _hvacLoadPercent, _ambientTemp, totalEnergyKwh, currentHourPowerKw } = useSimulation();

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Site detail view state
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);

  // Energy chart state
  const [energyData, setEnergyData] = useState<EnergyDataPoint[]>([]);
  const [energyLoading, setEnergyLoading] = useState(false);
  const [energyFilterSiteId, setEnergyFilterSiteId] = useState<string | null>(null);
  const [selectedDays, setSelectedDays] = useState<TimePeriod>(30);

  // KPI card order (draggable)
  const [kpiOrder, setKpiOrder] = useState<KPICardId[]>([
    'kpi-protected-sites',
    'kpi-monitored-assets',
    'kpi-active-risks',
    'kpi-potential-savings',
    'kpi-risk-predictions',
  ]);

  // DnD sensors
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor)
  );

  // Scroll to top on dashboard load
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  useEffect(() => {
    const loadDashboardData = async () => {
      try {
        setLoading(true);
        const statsData = await api.getStats();
        // Stagger subsequent request by 250ms to avoid 429 rate limiting
        await new Promise((resolve) => setTimeout(resolve, 250));
        const predictionsData = await api.getPredictions();
        setStats(statsData);
        // Filter predictions to show only critical and warning severity (from health thresholds)
        setPredictions(predictionsData.predictions.filter(p => p.severity === 'critical' || p.severity === 'warning'));
        setError(null);
      } catch (err) {
        console.error("Failed to load dashboard data:", err);
        setError("Failed to load dashboard data");
      } finally {
        setLoading(false);
      }
    };

    loadDashboardData();
  }, []);

  // Load energy data when filters change + auto-refresh every 30s
  useEffect(() => {
    const loadEnergyData = async () => {
      try {
        setEnergyLoading(true);
        const response = await api.getEnergy(energyFilterSiteId, selectedDays);
        setEnergyData(response.data);
      } catch (err) {
        console.error("Failed to load energy data:", err);
        setEnergyData([]);
      } finally {
        setEnergyLoading(false);
      }
    };

    loadEnergyData();
    const interval = setInterval(loadEnergyData, 30_000);
    return () => clearInterval(interval);
  }, [energyFilterSiteId, selectedDays]);

  // Calculate site status counts for KPI
  // eslint-disable-next-line @typescript-eslint/ban-ts-comment
  // @ts-ignore - Site type mismatch from legacy api.ts
  const _normalSites = buildingsList.filter((s: Site) => s.status === "normal").length;
  // eslint-disable-next-line @typescript-eslint/ban-ts-comment
  // @ts-ignore - Site type mismatch from legacy api.ts
  const warningSites = buildingsList.filter((s: Site) => s.status === "warning").length;

  // Filter predictions to only show critical/warning severity (from health thresholds)
  const criticalPredictions = predictions.filter(p =>
    p.severity === 'critical' || p.severity === 'warning'
  );

  // Calculate total potential savings from filtered predictions only
  const totalPotentialSavings = criticalPredictions.reduce((sum, prediction) => {
    if (prediction.financial_impact) {
      return sum + prediction.financial_impact.potential_loss_zar;
    }
    return sum;
  }, 0);

  // Format currency for display
  const formatZAR = (amount: number) =>
    new Intl.NumberFormat("en-ZA", {
      style: "currency",
      currency: "ZAR",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);

  // Handle site card click - navigate to site detail view
  const handleSiteClick = (site: Site) => {
    setSelectedSiteId(site.id);
    window.scrollTo(0, 0);
  };

  // Handle back from site detail view - navigate to dashboard
  const handleSiteDetailBack = () => {
    // First ensure we're on the dashboard view
    onViewChange("dashboard");
    // Then clear the selected site to show dashboard content
    setSelectedSiteId(null);
  };

  // Handle equipment control navigation from SiteCard risk list
  const handleEquipmentControlNavigate = (equipmentId: string, siteId: string) => {
    // Store selection in sessionStorage for ControlDashboard to pick up
    sessionStorage.setItem("sentinel_selected_equipment", equipmentId);
    sessionStorage.setItem("sentinel_selected_site", siteId);
    onViewChange("control");
  };

  // Handle KPI card drag end
  const handleKPIDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      setKpiOrder((items) => {
        const oldIndex = items.indexOf(active.id as KPICardId);
        const newIndex = items.indexOf(over.id as KPICardId);
        return arrayMove(items, oldIndex, newIndex);
      });
    }
  };

  // KPI card definitions - MUST be before early returns (Rules of Hooks)
  const kpiCards = useMemo(() => {
    if (!stats) return {};

    // When simulation running, show live metrics
    const _displayTotalEnergy = isSimulationRunning ? totalEnergyKwh : null;
    const _displayCurrentPower = isSimulationRunning ? currentHourPowerKw : null;

    return {
      'kpi-protected-sites': {
        title: "Protected Sites",
        value: buildingsList.length,
        icon: <Building2 className="h-5 w-5" />,
        subtitle: `${warningSites} elevated`,
        accentColor: "blue" as const,
        tooltip: "Total buildings under SENTINEL monitoring. Elevated = sites with warning/critical equipment state.",
      },
      'kpi-monitored-assets': {
        title: "Monitored Assets",
        value: stats.total_equipment,
        icon: <Cpu className="h-5 w-5" />,
        // Only show delta if uptime_percent exists and is not null/undefined
        delta: stats.uptime_percent !== undefined && stats.uptime_percent !== null
          ? stats.uptime_percent - 95
          : undefined,
        deltaText: stats.uptime_percent !== undefined && stats.uptime_percent !== null
          ? "vs 95% target"
          : undefined,
        accentColor: "cyan" as const,
        tooltip: "Equipment tracked across all sites — chillers, AHUs, generators, meters, UPS, and more. Delta shows uptime vs 95% SLA target.",
      },
      'kpi-active-risks': {
        title: "Active Risks",
        value: stats.active_alerts || 0,
        icon: <Bell className="h-5 w-5" />,
        // Show critical count if any
        delta: stats.critical_alerts > 0
          ? -(stats.critical_alerts * 10)
          : undefined,
        isInverseTrend: true,
        deltaText: stats.critical_alerts > 0
          ? `${stats.critical_alerts} critical`
          : undefined,
        accentColor: "orange" as const,
        tooltip: "AI-detected risks requiring attention. Critical risks need immediate action; warnings are monitored.",
      },
      'kpi-potential-savings': {
        title: "Potential Savings",
        value: formatZAR(totalPotentialSavings),
        icon: <DollarSign className="h-5 w-5" />,
        subtitle: "If all preventive actions taken",
        accentColor: "green" as const,
        tooltip: "Estimated savings if all AI-recommended preventive maintenance actions are completed.",
      },
      'kpi-risk-predictions': {
        title: "Risk Predictions",
        value: predictions.length,
        icon: <Shield className="h-5 w-5" />,
        subtitle: "AI-detected risk events",
        accentColor: "purple" as const,
        tooltip: "ML-predicted equipment failures and anomalies. Based on LSTM forecasting, autoencoder anomaly detection, and fault classification.",
      },
    };
  }, [stats, warningSites, totalPotentialSavings, predictions.length, isSimulationRunning, totalEnergyKwh, currentHourPowerKw, buildingsList.length]);

  // Loading state
  if (loading) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <div className="text-center">
          <RefreshCw
            className="h-8 w-8 animate-spin mx-auto mb-4"
            style={{ color: "var(--color-sentinel-amber)" }}
          />
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Initializing SENTINEL protection...
          </span>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <div className="p-8 rounded-md text-center glass-panel">
          <AlertTriangle
            className="h-12 w-12 mx-auto mb-4"
            style={{ color: "var(--color-sentinel-red)" }}
          />
          <h2
            className="text-lg font-medium mb-2"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Error Loading Dashboard
          </h2>
          <p style={{ color: "var(--color-sentinel-text-secondary)" }}>{error}</p>
        </div>
      </div>
    );
  }

  // Show site detail view if a site is selected
  if (selectedSiteId) {
    return (
      <div className="h-full">
        <SiteDetail siteId={selectedSiteId} onBack={handleSiteDetailBack} />
      </div>
    );
  }

  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* KPI Row */}
      <DashboardSection id="kpi-row">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleKPIDragEnd}
        >
          <SortableContext items={kpiOrder} strategy={horizontalListSortingStrategy}>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
              {kpiOrder.map((kpiId) => {
                const cardProps = kpiCards[kpiId];
                if (!cardProps) return null;
                return (
                  <SortableKPICard
                    key={kpiId}
                    id={kpiId}
                    {...cardProps}
                  />
                );
              })}
            </div>
          </SortableContext>
        </DndContext>
      </DashboardSection>

      {/* Site Protection */}
      <DashboardSection id="site-protection">
        <div className="lg:col-span-3">
          <div
            className="rounded-md overflow-hidden glass-panel"
          >
          {/* Panel Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--glass-border)" }}
          >
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded"
                style={{ background: "rgba(59, 130, 246, 0.15)" }}
              >
                <Building2
                  className="h-5 w-5"
                  style={{ color: "var(--color-sentinel-blue)" }}
                />
              </div>
              <div>
                <h3
                  className="font-medium text-sm"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                  title="Overview of all buildings under SENTINEL monitoring. Click any site card to drill into equipment details."
                >
                  Site Protection Status
                </h3>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  {buildingsList.length} sites monitored
                </span>
              </div>
            </div>
            <span
              className="text-xs px-2 py-1 rounded"
              style={{
                background:
                  warningSites > 0 ? "rgba(245, 158, 11, 0.15)" : "rgba(148, 163, 184, 0.15)",
                color:
                  warningSites > 0 ? "var(--color-sentinel-amber)" : "var(--color-sentinel-text-secondary)",
              }}
            >
              {warningSites} elevated
            </span>
          </div>

          {/* Sites Grid */}
          <div className="p-4">
            {buildingsList.length === 0 ? (
              <div className="text-center py-8">
                <Building2
                  className="h-12 w-12 mx-auto mb-2"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                />
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  No sites available
                </span>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {/* eslint-disable-next-line @typescript-eslint/ban-ts-comment */}
                {/* @ts-ignore - JSX.Element vs Element type mismatch */}
                {buildingsList.map((site: Site, _index: number) => {
                  return (
                    <SiteCard
                      key={site.id}
                      site={site}
                      onClick={handleSiteClick}
                      showOptimizationStatus={true}
                      onEquipmentControlNavigate={handleEquipmentControlNavigate}
                    />
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardSection>

      {/* Energy Analytics */}
      {(activeModules.length === 0 || isModuleActive('energy')) && (
        <DashboardSection id="energy-analytics">
          <div className="mt-6">
            <div
              className="rounded-md overflow-hidden glass-panel"
            >
            {/* Panel Header with Filters */}
            <div
              className="p-4 flex flex-wrap items-center justify-between gap-4"
              style={{ borderBottom: "1px solid var(--glass-border)" }}
            >
              <h3
                className="font-medium text-sm"
                style={{ color: "var(--color-sentinel-text-primary)" }}
                title="Energy consumption trends across all sites. Filter by site or adjust the time window."
              >
                Energy Analytics
              </h3>

              <div className="flex items-center gap-4">
                {/* Site Filter */}
                <select
                  value={energyFilterSiteId || ""}
                  onChange={(e) => setEnergyFilterSiteId(e.target.value || null)}
                  className="text-sm rounded px-3 py-1.5"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    border: "1px solid var(--color-sentinel-border)",
                    color: "var(--color-sentinel-text-primary)",
                  }}
                >
                  <option value="">All Sites</option>
                  {/* eslint-disable-next-line @typescript-eslint/ban-ts-comment */}
                  {/* @ts-ignore - JSX.Element vs Element type mismatch */}
                  {buildingsList.map((site: Site, _index: number) => (
                    <option key={site.id} value={site.id}>
                      {site.name}
                    </option>
                  ))}
                </select>

                {/* Time Period Tabs */}
                <div
                  className="flex rounded overflow-hidden"
                  style={{ border: "1px solid var(--color-sentinel-border)" }}
                >
                  {TIME_PERIODS.map((period) => (
                    <button
                      key={period}
                      onClick={() => setSelectedDays(period)}
                      className="px-3 py-1.5 text-xs font-medium transition-colors"
                      style={{
                        background:
                          selectedDays === period
                            ? "var(--color-sentinel-amber)"
                            : "var(--color-sentinel-bg-secondary)",
                        color:
                          selectedDays === period
                            ? "white"
                            : "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      {period}d
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Chart Container */}
            <div className="p-4">
              <EnergyChart
                data={energyData}
                loading={energyLoading}
                selectedSiteId={energyFilterSiteId}
                days={selectedDays}
              />
            </div>
          </div>
        </div>
      </DashboardSection>
      )}
    </div>
  );
}

export default Dashboard;

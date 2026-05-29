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
import { useNavigate } from "react-router-dom";
import { useServerEvents } from "@/hooks/useServerEvents";
import {
  Building2,
  AlertTriangle,
  Cpu,
  Shield,
  Bell,
  DollarSign,
  EyeOff,
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
import { authorizedFetch } from '@/lib/api/client';
import type { DashboardStats, Site, Prediction, EnergyDataPoint } from '@/lib/api';
import { useBuildingsList } from "@/hooks/useBuildingsList";
import { SortableKPICard } from "./SortableKPICard";
import { PageLoading } from "./PageLoading";
import { DashboardSection } from "./DashboardSection";
import { SiteCard } from "./SiteCard";
import { EnergyChart } from "./EnergyChart";
import { Panel } from "./Panel";
import { EmptyState } from "./EmptyState";
import { type View } from "./Sidebar";
import type { BuildingTabId } from "../lib/navigation";
import { useModules } from "@/contexts/ModuleHooks";
import { getStoredSelectedSite, setStoredSelectedSite } from "@/lib/siteSelection";

// Time period options for energy chart
const TIME_PERIODS = [7, 30, 90] as const;
type TimePeriod = (typeof TIME_PERIODS)[number];

type KPICardId =
  | 'kpi-protected-sites'
  | 'kpi-monitored-assets'
  | 'kpi-active-risks'
  | 'kpi-potential-savings'
  | 'kpi-risk-predictions';

function buildFallbackEnergySeries(
  sourceSite: Site,
  days: number,
  power: {
    hvac_kw?: number;
    lighting_kw?: number;
    other_kw?: number;
    misc_kw?: number;
    base_kw?: number;
    total_kw?: number;
  } | null | undefined
): EnergyDataPoint[] {
  const hvacKw = power?.hvac_kw ?? 0;
  const lightingKw = power?.lighting_kw ?? 0;
  const directOtherKw = power?.other_kw ?? power?.misc_kw ?? power?.base_kw;
  const totalKw = power?.total_kw ?? hvacKw + lightingKw;
  const residualOtherKw = Math.max(0, totalKw - hvacKw - lightingKw);
  // If telemetry does not publish a separate "other" channel yet, infer a conservative base load.
  const inferredOtherKw = (hvacKw + lightingKw) * 0.12;
  const otherKw = directOtherKw ?? (residualOtherKw > 0 ? residualOtherKw : inferredOtherKw);
  const hvacKwhPerDay = hvacKw * 24;
  const lightingKwhPerDay = lightingKw * 24;
  const otherKwhPerDay = otherKw * 24;

  const endDate = new Date();
  const series: EnergyDataPoint[] = [];

  for (let i = days - 1; i >= 0; i--) {
    const pointDate = new Date(endDate);
    pointDate.setDate(endDate.getDate() - i);
    const dayOfWeek = pointDate.getDay();
    const isoDate = pointDate.toISOString().slice(0, 10);
    // Deterministic day-level variation so chart shape stays stable across refreshes.
    const hash = isoDate.split("-").reduce((acc, part) => acc + Number(part), 0);
    const dailyJitter = ((hash % 11) - 5) / 100; // [-5%, +5%]
    const weekdayFactor = dayOfWeek === 0 || dayOfWeek === 6 ? 0.72 : 1.0;
    const intraperiodFactor = 1 + Math.sin((i / Math.max(days, 1)) * Math.PI) * 0.08;
    const scale = Math.max(0.55, weekdayFactor * intraperiodFactor * (1 + dailyJitter));

    const hvacKwh = Number((hvacKwhPerDay * scale).toFixed(2));
    const lightingKwh = Number((lightingKwhPerDay * scale).toFixed(2));
    const otherKwh = Number((otherKwhPerDay * (0.9 + dailyJitter)).toFixed(2));

    series.push({
      date: isoDate,
      site_id: sourceSite.id,
      site_name: sourceSite.name,
      hvac_kwh: hvacKwh,
      lighting_kwh: lightingKwh,
      other_kwh: otherKwh,
      total_kwh: Number((hvacKwh + lightingKwh + otherKwh).toFixed(2)),
    });
  }

  return series;
}

interface DashboardProps {
  onViewChange: (view: View) => void;
  autoSelectSiteId?: string | null;
  defaultBuildingTab?: BuildingTabId;
}

export function Dashboard({ onViewChange, autoSelectSiteId, defaultBuildingTab: _defaultBuildingTab }: DashboardProps) {
  const HIDDEN_SITE_IDS_STORAGE_KEY = 'sentinel_dashboard_hidden_site_ids';
  const navigate = useNavigate();

  // React Query hooks — filter to primary site only
  const { data: allSites = [] } = useBuildingsList();
  const buildingsList = allSites;

  // Module gating
  const { isModuleActive, activeModules } = useModules();

  // Real-time event updates from backend SSE
  useServerEvents();

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Auto-navigate when autoSelectSiteId is set (e.g. single-site user login)
  useEffect(() => {
    if (autoSelectSiteId) {
      navigate(`/buildings/${autoSelectSiteId}`);
    }
  }, [autoSelectSiteId, navigate]);

  // Energy chart state
  const [energyData, setEnergyData] = useState<EnergyDataPoint[]>([]);
  const [energyLoading, setEnergyLoading] = useState(false);
  const [energyFilterSiteId, setEnergyFilterSiteId] = useState<string | null>(null);
  const [selectedDays, setSelectedDays] = useState<TimePeriod>(30);
  const [energyLastUpdated, setEnergyLastUpdated] = useState<Date | null>(null);
  const [isFallbackEnergyData, setIsFallbackEnergyData] = useState(false);

  // KPI card order (draggable)
  const [kpiOrder, setKpiOrder] = useState<KPICardId[]>([
    'kpi-protected-sites',
    'kpi-monitored-assets',
    'kpi-active-risks',
    'kpi-potential-savings',
    'kpi-risk-predictions',
  ]);
  const [hiddenSiteIds, setHiddenSiteIds] = useState<string[]>([]);

  // DnD sensors
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor)
  );

  // Scroll to top on dashboard load
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  // Restore hidden site preferences on load
  useEffect(() => {
    try {
      const storedHiddenSites = localStorage.getItem(HIDDEN_SITE_IDS_STORAGE_KEY);
      if (!storedHiddenSites) return;
      const parsedHiddenSites = JSON.parse(storedHiddenSites);
      if (Array.isArray(parsedHiddenSites)) {
        setHiddenSiteIds(parsedHiddenSites);
      }
    } catch (storageError) {
      console.warn('Failed to restore hidden dashboard sites:', storageError);
    }
  }, [HIDDEN_SITE_IDS_STORAGE_KEY]);

  // Persist hidden site preferences
  useEffect(() => {
    try {
      localStorage.setItem(HIDDEN_SITE_IDS_STORAGE_KEY, JSON.stringify(hiddenSiteIds));
    } catch (storageError) {
      console.warn('Failed to persist hidden dashboard sites:', storageError);
    }
  }, [hiddenSiteIds, HIDDEN_SITE_IDS_STORAGE_KEY]);

  // Default to All Sites — no auto-selection.

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
        if (response.data.length > 0) {
          setEnergyData(response.data);
          setEnergyLastUpdated(new Date());
          return;
        }

        // Fallback for bridge-only sites with no historical energy table rows yet.
        const contextualSiteId = energyFilterSiteId || getStoredSelectedSite() || autoSelectSiteId || null;
        const preferredSite =
          (contextualSiteId ? buildingsList.find((site: Site) => site.id === contextualSiteId) : null) ||
          buildingsList[0];

        if (!preferredSite) {
          setEnergyData([]);
          return;
        }

        const rawTelemetryResp = await authorizedFetch(
          `/api/sites/${encodeURIComponent(preferredSite.id)}/telemetry`
        ).catch(() => null);

        if (rawTelemetryResp && rawTelemetryResp.ok) {
          const rawTelemetry = await rawTelemetryResp.json();
          const fallbackSeries = buildFallbackEnergySeries(preferredSite, selectedDays, rawTelemetry?.power);
          setEnergyData(fallbackSeries);
          setEnergyLastUpdated(new Date());
          setIsFallbackEnergyData(true);
        } else {
          setEnergyData([]);
          setIsFallbackEnergyData(false);
        }
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
  }, [energyFilterSiteId, selectedDays, buildingsList, autoSelectSiteId]);

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
  const visibleSites = buildingsList.filter((site: Site) => !hiddenSiteIds.includes(site.id));
  const hiddenSites = buildingsList.filter((site: Site) => hiddenSiteIds.includes(site.id));

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

  // Format relative time for data freshness indicator
  const formatTimeAgo = (date: Date | null): string => {
    if (!date) return '';
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'Just now';
    if (diffMins === 1) return '1 min ago';
    if (diffMins < 60) return `${diffMins} min ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours === 1) return '1 hour ago';
    if (diffHours < 24) return `${diffHours} hours ago`;
    return `${Math.floor(diffHours / 24)} days ago`;
  };

  // Calculate energy intensity (kWh/m²) for selected site or all sites
  const energyIntensity = useMemo(() => {
    if (!energyData.length) return null;
    const totalKwh = energyData.reduce((sum, d) => sum + (d.total_kwh || 0), 0);
    const days = energyData.length;
    const dailyKwh = days > 0 ? totalKwh / days : 0;
    // Get sqm from selected site or sum of all sites
    let totalSqm = 0;
    if (energyFilterSiteId) {
      const site = buildingsList.find((s: Site) => s.id === energyFilterSiteId);
      totalSqm = site?.sqm || 5000; // fallback
    } else {
      totalSqm = buildingsList.reduce((sum: number, s: Site) => sum + (s.sqm || 0), 0) || 5000;
    }
    const annualKwh = dailyKwh * 365;
    const intensity = totalSqm > 0 ? (annualKwh / totalSqm) : 0;
    // SA office benchmarks (annual kWh/m²): efficient < 120, typical < 170
    const classification = intensity < 120 ? 'Efficient' : intensity < 170 ? 'Typical' : 'High';
    const classificationColor = intensity < 120 ? 'var(--color-sentinel-green)' : intensity < 170 ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-red)';
    return { intensity: Math.round(intensity), classification, classificationColor };
  }, [energyData, energyFilterSiteId, buildingsList]);

  // Handle site card click - navigate to /buildings/:siteId URL
  const handleSiteClick = (site: Site) => {
    setStoredSelectedSite(site.id);
    navigate(`/buildings/${site.id}`);
  };

  // Handle equipment control navigation from SiteCard risk list
  const handleEquipmentControlNavigate = (equipmentId: string, siteId: string) => {
    // Store selection in sessionStorage for ControlDashboard to pick up
    sessionStorage.setItem("sentinel_selected_equipment", equipmentId);
    sessionStorage.setItem("sentinel_selected_site", siteId);
    onViewChange("control");
  };

  const hideSiteCard = (siteId: string) => {
    setHiddenSiteIds((previousHiddenSiteIds) =>
      previousHiddenSiteIds.includes(siteId)
        ? previousHiddenSiteIds
        : [...previousHiddenSiteIds, siteId]
    );
  };

  const restoreAllHiddenSiteCards = () => {
    setHiddenSiteIds([]);
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
        // Always show severity breakdown — zero critical is a positive signal
        delta: stats.critical_alerts > 0 ? -(stats.critical_alerts * 10) : 0,
        isInverseTrend: true,
        deltaText: `${stats.critical_alerts || 0} Critical · ${(stats.active_alerts || 0) - (stats.critical_alerts || 0)} Warning`,
        accentColor: "orange" as const,
        tooltip: "AI-detected risks requiring attention. Critical risks need immediate action; warnings are monitored.",
      },
      'kpi-potential-savings': {
        title: "Potential Savings",
        value: formatZAR(totalPotentialSavings),
        icon: <DollarSign className="h-5 w-5" />,
        subtitle: "If all preventive actions taken",
        accentColor: "green" as const,
        tooltip: "Sum of potential_loss_zar from all critical/warning predictions. Based on equipment replacement costs + downtime estimates + energy penalty calculations from ML failure prediction models.",
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
  }, [stats, warningSites, totalPotentialSavings, predictions.length, buildingsList.length]);

  // Loading state
  if (loading) {
    return <PageLoading message="Initializing SENTINEL protection..." />;
  }

  // Error state
  if (error) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <div
          className="p-8 rounded-lg text-center"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
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
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 mb-6">
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
        <Panel
          header={{
            icon: <Building2 className="h-5 w-5" />,
            title: "Site Protection Status",
            actions: (
              <div className="flex items-center gap-2">
                <span
                  className="text-xs px-2 py-1 rounded"
                  style={{
                    background:
                      warningSites > 0 ? "color-mix(in oklch, var(--color-sentinel-amber) 15%, transparent)" : "color-mix(in oklch, var(--color-sentinel-green) 15%, transparent)",
                    color:
                      warningSites > 0 ? "var(--color-sentinel-amber)" : "var(--color-sentinel-green)",
                  }}
                >
                  {warningSites > 0 ? `${warningSites} elevated` : "All healthy"}
                </span>
                {hiddenSites.length > 0 && (
                  <>
                    <span
                      className="text-xs px-2 py-1 rounded"
                      style={{
                        background: "color-mix(in oklch, var(--color-sentinel-text-disabled) 15%, transparent)",
                        color: "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      {hiddenSites.length} hidden
                    </span>
                    <button
                      type="button"
                      className="text-xs px-2 py-1 rounded transition-colors"
                      style={{
                        background: "color-mix(in oklch, var(--color-sentinel-blue) 15%, transparent)",
                        color: "var(--color-sentinel-blue)",
                      }}
                      onClick={restoreAllHiddenSiteCards}
                      title="Restore all hidden site cards"
                    >
                      Show all
                    </button>
                  </>
                )}
              </div>
            ),
            accentColor: "var(--color-sentinel-blue)",
          }}
        >
          {visibleSites.length === 0 ? (
            <EmptyState
              icon={Building2}
              title={buildingsList.length === 0 ? "No sites available" : "All site cards are hidden"}
              subtext={buildingsList.length === 0 ? "Sites will appear here once connected to SENTINEL." : undefined}
              cta={buildingsList.length > 0 && hiddenSites.length > 0 ? (
                <button
                  type="button"
                  className="text-xs px-3 py-1.5 rounded transition-colors"
                  style={{
                    background: "color-mix(in oklch, var(--color-sentinel-blue) 15%, transparent)",
                    color: "var(--color-sentinel-blue)",
                    border: "1px solid color-mix(in oklch, var(--color-sentinel-blue) 35%, transparent)",
                  }}
                  onClick={restoreAllHiddenSiteCards}
                >
                  Show all hidden site cards
                </button>
              ) : undefined}
            />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 p-4">
              {/* eslint-disable-next-line @typescript-eslint/ban-ts-comment */}
              {/* @ts-ignore - JSX.Element vs Element type mismatch */}
              {visibleSites.map((site: Site, _index: number) => {
                return (
                  <div key={site.id} className="relative">
                    <button
                      type="button"
                      className="absolute top-2 right-2 z-10 p-1.5 rounded transition-colors"
                      style={{
                        background: "color-mix(in oklch, var(--color-sentinel-text-disabled) 15%, transparent)",
                        color: "var(--color-sentinel-text-secondary)",
                        border: "1px solid var(--color-sentinel-border)",
                      }}
                      onClick={(event) => {
                        event.stopPropagation();
                        hideSiteCard(site.id);
                      }}
                      title={`Hide ${site.name} from dashboard`}
                      aria-label={`Hide ${site.name} from dashboard`}
                    >
                      <EyeOff className="h-3.5 w-3.5" />
                    </button>
                    <SiteCard
                      site={site}
                      onClick={handleSiteClick}
                      showOptimizationStatus={true}
                      onEquipmentControlNavigate={handleEquipmentControlNavigate}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </Panel>
      </DashboardSection>

      {/* Energy Analytics */}
      {(activeModules.length === 0 || isModuleActive('energy')) && (
        <DashboardSection id="energy-analytics">
          <Panel
            header={{
              icon: <Shield className="h-5 w-5" />,
              title: "Energy Analytics",
              actions: (
                <div className="flex items-center gap-4">
                  {/* Energy Intensity Badge */}
                  {energyIntensity && (
                    <div className="flex items-center gap-2">
                      <span
                        className="text-sm font-medium"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        {energyIntensity.intensity} kWh/m²
                      </span>
                      <span
                        className="text-xs px-2 py-0.5 rounded"
                        style={{
                          background: `${energyIntensity.classificationColor}20`,
                          color: energyIntensity.classificationColor,
                        }}
                      >
                        {energyIntensity.classification}
                      </span>
                    </div>
                  )}

                  {/* Site Filter - hidden when only 1 site */}
                  {buildingsList.length > 1 && (
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
                  )}

                  {/* Time Period Tabs */}
                  <div
                    role="radiogroup"
                    aria-label="Select time period"
                    className="flex rounded overflow-hidden"
                    style={{ border: "1px solid var(--color-sentinel-border)" }}
                  >
                    {TIME_PERIODS.map((period) => (
                      <button
                        key={period}
                        role="radio"
                        aria-checked={selectedDays === period}
                        aria-label={`Show last ${period} days`}
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

                  {/* Data Freshness Timestamp */}
                  {energyLastUpdated && (
                    <span
                      className="text-xs"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                      title={energyLastUpdated.toLocaleString()}
                    >
                      {formatTimeAgo(energyLastUpdated)}
                    </span>
                  )}

                  {/* Demo Data Indicator */}
                  {isFallbackEnergyData && (
                    <span
                      title="Real telemetry unavailable — showing estimated values"
                      style={{
                        fontSize: 10,
                        color: "var(--color-sentinel-amber)",
                        background: "color-mix(in oklch, var(--color-sentinel-amber) 10%, transparent)",
                        padding: "2px 6px",
                        borderRadius: 4,
                        border: "1px solid color-mix(in oklch, var(--color-sentinel-amber) 30%, transparent)",
                        fontWeight: 600,
                        letterSpacing: "0.5px",
                      }}
                    >
                      DEMO DATA
                    </span>
                  )}
                </div>
              ),
              accentColor: "var(--color-sentinel-amber)",
            }}
          >
            <EnergyChart
              data={energyData}
              loading={energyLoading}
              selectedSiteId={energyFilterSiteId}
              days={selectedDays}
            />
          </Panel>
        </DashboardSection>
      )}
    </div>
  );
}

export default Dashboard;

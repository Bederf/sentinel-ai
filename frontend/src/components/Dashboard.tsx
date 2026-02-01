/**
 * Dashboard Component - SENTINEL Risk Dashboard
 *
 * Features:
 * - Top row: 5 KPI stat panels
 * - Left column: Site protection overview grid
 * - Right column: Risk alert feed
 * - Middle: Energy consumption chart with filters
 * - Bottom: AI Risk Predictions
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect, useMemo } from "react";
import {
  Building2,
  AlertTriangle,
  AlertCircle,
  Cpu,
  Shield,
  Bell,
  DollarSign,
  RefreshCw,
  LayoutGrid,
  XCircle,
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
  verticalListSortingStrategy,
  arrayMove,
} from '@dnd-kit/sortable';
import api from "../lib/api";
import type { DashboardStats, Site, Prediction, EnergyDataPoint, BuildingEquipmentItem } from "../lib/api";
import { SortableKPICard } from "./SortableKPICard";
import { DashboardSection } from "./DashboardSection";
import { SiteCard } from "./SiteCard";
import { SiteDetail } from "./SiteDetail";
// import { AlertFeed } from "./AlertFeed"; // Moved to header bell button
import { EnergyChart } from "./EnergyChart";
import { PredictionCard } from "./PredictionCard";
import { PredictionDetail } from "./PredictionDetail";
import { ROISummaryCard } from "./ROISummaryCard";
import { OccupancyPanel } from "./OccupancyPanel";
import ComfortComplaintPanel from "./ComfortComplaintPanel";
import { type View } from "./Sidebar";
import CardLibrary from "./CardLibrary";
import { DEFAULT_KPI_CARDS, DEFAULT_SECTIONS } from "../lib/cardDefinitions";

// Time period options for energy chart
const TIME_PERIODS = [7, 30, 90] as const;
type TimePeriod = (typeof TIME_PERIODS)[number];

// Dashboard section and KPI card types
type DashboardSectionId =
  | 'kpi-row'
  | 'site-protection'
  | 'energy-analytics'
  | 'risk-predictions'
  | 'comfort-assistant'
  | 'occupancy-dashboard';

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
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [sites, setSites] = useState<Site[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Site detail view state
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);

  // Prediction detail modal state
  const [selectedPrediction, setSelectedPrediction] = useState<Prediction | null>(null);
  const [isPredictionDetailOpen, setIsPredictionDetailOpen] = useState(false);

  // Energy chart state
  const [energyData, setEnergyData] = useState<EnergyDataPoint[]>([]);
  const [energyLoading, setEnergyLoading] = useState(false);
  const [energyFilterSiteId, setEnergyFilterSiteId] = useState<string | null>(null);
  const [selectedDays, setSelectedDays] = useState<TimePeriod>(30);

  // At-risk equipment state (warning/critical status)
  const [atRiskEquipment, setAtRiskEquipment] = useState<BuildingEquipmentItem[]>([]);

  // Drag and drop state
  const [sectionOrder, setSectionOrder] = useState<DashboardSectionId[]>([
    'kpi-row',
    'site-protection',
    'energy-analytics',
    'risk-predictions',
    'comfort-assistant',
    'occupancy-dashboard',
  ]);

  const [kpiOrder, setKpiOrder] = useState<KPICardId[]>([
    'kpi-protected-sites',
    'kpi-monitored-assets',
    'kpi-active-risks',
    'kpi-potential-savings',
    'kpi-risk-predictions',
  ]);

  // Card visibility state
  const [visibleKpiCards, setVisibleKpiCards] = useState<string[]>(DEFAULT_KPI_CARDS);
  const [visibleSections, setVisibleSections] = useState<string[]>(DEFAULT_SECTIONS);
  const [isCardLibraryOpen, setIsCardLibraryOpen] = useState(false);
  const [isSavingPreferences, setIsSavingPreferences] = useState(false);

  // DnD sensors
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor)
  );

  useEffect(() => {
    const loadDashboardData = async () => {
      try {
        setLoading(true);
        const [statsData, sitesData, predictionsData] = await Promise.all([
          api.getStats(),
          api.getSites(),
          api.getPredictions(),
        ]);
        setStats(statsData);
        setSites(sitesData);
        setPredictions(predictionsData.predictions);
        setError(null);

        // Load at-risk equipment from Sandton (site-002)
        try {
          const equipmentData = await api.getBuildingEquipment("sandton");
          // Filter for warning and critical status only
          const riskEquipment = equipmentData.equipment.filter(
            (e) => e.status === "warning" || e.status === "critical"
          );
          setAtRiskEquipment(riskEquipment);
        } catch (eqErr) {
          console.error("Failed to load at-risk equipment:", eqErr);
          setAtRiskEquipment([]);
        }
      } catch (err) {
        console.error("Failed to load dashboard data:", err);
        setError("Failed to load dashboard data");
      } finally {
        setLoading(false);
      }
    };

    loadDashboardData();
  }, []);

  // Load dashboard preferences on mount
  useEffect(() => {
    const loadPreferences = async () => {
      try {
        const response = await api.getDashboardPreferences();
        if (response.preferences) {
          setVisibleKpiCards(response.preferences.visible_kpi_cards);
          setVisibleSections(response.preferences.visible_sections);
          setKpiOrder(response.preferences.kpi_card_order as KPICardId[]);
          setSectionOrder(response.preferences.section_order as DashboardSectionId[]);
          if (response.preferences.default_energy_period) {
            setSelectedDays(response.preferences.default_energy_period as TimePeriod);
          }
        }
      } catch (err) {
        console.error("Failed to load dashboard preferences:", err);
        // Use defaults on error
      }
    };

    loadPreferences();
  }, []);

  // Load energy data when filters change
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
  }, [energyFilterSiteId, selectedDays]);

  // Calculate site status counts for KPI - computed values used in render functions
  const normalSites = sites.filter((s) => s.status === "normal").length;
  const warningSites = sites.filter((s) => s.status === "warning").length;

  // Calculate total potential savings from all predictions
  const totalPotentialSavings = predictions.reduce((sum, prediction) => {
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

  // Handle prediction card click
  const handlePredictionClick = (prediction: Prediction) => {
    setSelectedPrediction(prediction);
    setIsPredictionDetailOpen(true);
  };

  // Close prediction detail modal
  const closePredictionDetail = () => {
    setIsPredictionDetailOpen(false);
    setSelectedPrediction(null);
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

  // Handle section drag end
  const handleSectionDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      setSectionOrder((items) => {
        const oldIndex = items.indexOf(active.id as DashboardSectionId);
        const newIndex = items.indexOf(over.id as DashboardSectionId);

        // Only reorder if indices are valid
        if (oldIndex !== -1 && newIndex !== -1) {
          return arrayMove(items, oldIndex, newIndex);
        }
        return items;
      });
    }
  };

  // Save preferences helper
  const savePreferences = async (updates: Partial<{
    visible_kpi_cards: string[];
    visible_sections: string[];
    kpi_card_order: string[];
    section_order: string[];
  }>) => {
    setIsSavingPreferences(true);
    try {
      await api.updateDashboardPreferences({
        visible_kpi_cards: updates.visible_kpi_cards ?? visibleKpiCards,
        visible_sections: updates.visible_sections ?? visibleSections,
        kpi_card_order: updates.kpi_card_order ?? kpiOrder,
        section_order: updates.section_order ?? sectionOrder,
        default_energy_period: selectedDays,
        default_energy_site_id: energyFilterSiteId,
      });
    } catch (err) {
      console.error("Failed to save preferences:", err);
    } finally {
      setIsSavingPreferences(false);
    }
  };

  // Handle KPI card visibility change
  const handleKpiVisibilityChange = (cardId: string, visible: boolean) => {
    const newVisible = visible
      ? [...visibleKpiCards, cardId]
      : visibleKpiCards.filter(id => id !== cardId);
    setVisibleKpiCards(newVisible);
    savePreferences({ visible_kpi_cards: newVisible });
  };

  // Handle section visibility change
  const handleSectionVisibilityChange = (sectionId: string, visible: boolean) => {
    const newVisible = visible
      ? [...visibleSections, sectionId]
      : visibleSections.filter(id => id !== sectionId);
    setVisibleSections(newVisible);
    savePreferences({ visible_sections: newVisible });
  };

  // Reset preferences to defaults
  const handleResetToDefaults = async () => {
    setVisibleKpiCards(DEFAULT_KPI_CARDS);
    setVisibleSections(DEFAULT_SECTIONS);
    setKpiOrder(DEFAULT_KPI_CARDS as KPICardId[]);
    setSectionOrder(DEFAULT_SECTIONS as DashboardSectionId[]);

    try {
      await api.resetDashboardPreferences();
    } catch (err) {
      console.error("Failed to reset preferences:", err);
    }
  };

  // KPI card definitions - MUST be before early returns (Rules of Hooks)
  const kpiCards = useMemo(() => {
    if (!stats) return {};
    
    return {
      'kpi-protected-sites': {
        title: "Protected Sites",
        value: stats.total_sites,
        icon: <Building2 className="h-5 w-5" />,
        subtitle: `${normalSites} protected, ${warningSites} elevated`,
        accentColor: "blue" as const,
      },
      'kpi-monitored-assets': {
        title: "Monitored Assets",
        value: stats.total_equipment,
        icon: <Cpu className="h-5 w-5" />,
        // Only show delta if uptime_percent exists and is not null/undefined
        delta: (stats as any).uptime_percent !== undefined && (stats as any).uptime_percent !== null 
          ? (stats as any).uptime_percent - 95 
          : undefined,
        deltaText: (stats as any).uptime_percent !== undefined && (stats as any).uptime_percent !== null 
          ? "vs 95% target" 
          : undefined,
        accentColor: "cyan" as const,
      },
      'kpi-active-risks': {
        title: "Active Risks",
        value: stats.active_alerts || 0,
        icon: <Bell className="h-5 w-5" />,
        // Only show delta if critical_alerts exists and is greater than 0
        delta: (stats as any).critical_alerts !== undefined && (stats as any).critical_alerts !== null && (stats as any).critical_alerts > 0 
          ? -((stats as any).critical_alerts * 10) 
          : undefined,
        isInverseTrend: true,
        deltaText: (stats as any).critical_alerts !== undefined && (stats as any).critical_alerts !== null && (stats as any).critical_alerts > 0 
          ? `${(stats as any).critical_alerts} critical` 
          : undefined,
        accentColor: "orange" as const,
      },
      'kpi-potential-savings': {
        title: "Potential Savings",
        value: formatZAR(totalPotentialSavings),
        icon: <DollarSign className="h-5 w-5" />,
        subtitle: "If all preventive actions taken",
        accentColor: "green" as const,
      },
      'kpi-risk-predictions': {
        title: "Risk Predictions",
        value: predictions.length,
        icon: <Shield className="h-5 w-5" />,
        subtitle: "AI-detected risk events",
        accentColor: "purple" as const,
      },
    };
  }, [stats, normalSites, warningSites, totalPotentialSavings, predictions.length]);

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
        <div
          className="p-8 rounded-md text-center"
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

  // Show site detail view if a site is selected
  if (selectedSiteId) {
    return (
      <div className="h-full overflow-hidden">
        <SiteDetail siteId={selectedSiteId} onBack={handleSiteDetailBack} />
      </div>
    );
  }

  // Render KPI Row section
  const renderKPIRow = () => {
    // Filter to only visible KPI cards
    const visibleKpiOrder = kpiOrder.filter(id => visibleKpiCards.includes(id));
    if (visibleKpiOrder.length === 0) return null;

    // Calculate grid columns based on visible card count
    const gridCols = visibleKpiOrder.length <= 3
      ? `lg:grid-cols-${visibleKpiOrder.length}`
      : visibleKpiOrder.length === 4
      ? 'lg:grid-cols-4'
      : 'lg:grid-cols-5';

    return (
      <DashboardSection id="kpi-row">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleKPIDragEnd}
        >
          <SortableContext items={visibleKpiOrder} strategy={horizontalListSortingStrategy}>
            <div className={`grid grid-cols-1 sm:grid-cols-2 ${gridCols} gap-4 mb-6`}>
              {visibleKpiOrder.map((kpiId) => {
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
    );
  };

  // Render Site Protection section
  const renderSiteProtection = () => {

    return (
      <DashboardSection id="site-protection">
        <div className="lg:col-span-3">
          <div
            className="rounded-md overflow-hidden"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
          {/* Panel Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
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
                >
                  Site Protection Status
                </h3>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  {sites.length} sites under protection
                </span>
              </div>
            </div>
            <span
              className="text-xs px-2 py-1 rounded"
              style={{
                background: "rgba(16, 185, 129, 0.15)",
                color: "var(--color-sentinel-green)",
              }}
            >
              {normalSites} protected
            </span>
          </div>

          {/* Sites Grid */}
          <div className="p-4">
            {sites.length === 0 ? (
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
                {sites.map((site) => (
                  <SiteCard
                    key={site.id}
                    site={site}
                    onClick={handleSiteClick}
                    showOptimizationStatus={true}
                    onEquipmentControlNavigate={handleEquipmentControlNavigate}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardSection>
    );
  };


  // Render Energy Analytics section
  const renderEnergyAnalytics = () => (
    <DashboardSection id="energy-analytics">
      <div className="mt-6">
        <div
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {/* Panel Header with Filters */}
          <div
            className="p-4 flex flex-wrap items-center justify-between gap-4"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
          >
            <h3
              className="font-medium text-sm"
              style={{ color: "var(--color-sentinel-text-primary)" }}
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
                {sites.map((site) => (
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
              selectedSiteId={selectedSiteId}
              days={selectedDays}
            />
          </div>
        </div>
      </div>
    </DashboardSection>
  );

  // Render Risk Predictions section
  const renderRiskPredictions = () => (
    <DashboardSection id="risk-predictions">
      <div className="mt-6 space-y-6">
        {/* ROI Summary Card */}
        {predictions.length > 0 && <ROISummaryCard predictions={predictions} />}

        {/* Hero Risk Card - Highest Risk Equipment */}
        {atRiskEquipment.length > 0 && (() => {
          // Find highest risk: critical first, then warning, sorted by lowest health
          const sortedRisk = [...atRiskEquipment].sort((a, b) => {
            // Critical comes before warning
            if (a.status === "critical" && b.status !== "critical") return -1;
            if (b.status === "critical" && a.status !== "critical") return 1;
            // Then sort by health (lower = higher risk)
            return a.health - b.health;
          });
          const highestRisk = sortedRisk[0];
          const riskProbability = highestRisk.status === "critical"
            ? Math.max(80, 100 - highestRisk.health)
            : Math.max(60, 100 - highestRisk.health);

          return (
            <div
              className="rounded-md overflow-hidden cursor-pointer hover:brightness-105 transition-all"
              style={{
                background: highestRisk.status === "critical"
                  ? "linear-gradient(135deg, rgba(220, 38, 38, 0.2) 0%, rgba(220, 38, 38, 0.1) 100%)"
                  : "linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(245, 158, 11, 0.1) 100%)",
                border: `1px solid ${highestRisk.status === "critical" ? "rgba(220, 38, 38, 0.4)" : "rgba(245, 158, 11, 0.4)"}`,
              }}
              onClick={() => setSelectedSiteId("site-002")}
            >
              <div className="p-5">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className="text-xs px-2 py-0.5 rounded font-medium uppercase"
                        style={{
                          background: highestRisk.status === "critical" ? "rgba(220, 38, 38, 0.3)" : "rgba(245, 158, 11, 0.3)",
                          color: highestRisk.status === "critical" ? "var(--color-sentinel-red)" : "var(--color-sentinel-amber)",
                        }}
                      >
                        Highest Risk - Immediate Attention Required
                      </span>
                    </div>
                    <h3
                      className="text-lg font-semibold"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {highestRisk.name}
                    </h3>
                    <p
                      className="text-sm"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      {highestRisk.category} • {highestRisk.type} • {highestRisk.location}
                    </p>
                    <p
                      className="text-xs"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      {highestRisk.building_name} • {highestRisk.building_id}
                    </p>
                  </div>
                  <div className="text-right">
                    <div
                      className="text-3xl font-bold"
                      style={{
                        color: highestRisk.status === "critical" ? "var(--color-sentinel-red)" : "var(--color-sentinel-amber)",
                      }}
                    >
                      {highestRisk.health}%
                    </div>
                    <div
                      className="text-xs uppercase font-medium"
                      style={{
                        color: highestRisk.status === "critical" ? "var(--color-sentinel-red)" : "var(--color-sentinel-amber)",
                      }}
                    >
                      Health Score
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <div
                    className="p-3 rounded"
                    style={{ background: "rgba(0, 0, 0, 0.2)" }}
                  >
                    <div
                      className="text-xs mb-1"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Risk Level
                    </div>
                    <div
                      className="text-lg font-semibold"
                      style={{
                        color: highestRisk.status === "critical" ? "var(--color-sentinel-red)" : "var(--color-sentinel-amber)",
                      }}
                    >
                      {riskProbability}%
                    </div>
                  </div>
                  <div
                    className="p-3 rounded"
                    style={{ background: "rgba(0, 0, 0, 0.2)" }}
                  >
                    <div
                      className="text-xs mb-1"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Status
                    </div>
                    <div
                      className="text-lg font-semibold uppercase"
                      style={{
                        color: highestRisk.status === "critical" ? "var(--color-sentinel-red)" : "var(--color-sentinel-amber)",
                      }}
                    >
                      {highestRisk.status}
                    </div>
                  </div>
                  <div
                    className="p-3 rounded"
                    style={{ background: "rgba(0, 0, 0, 0.2)" }}
                  >
                    <div
                      className="text-xs mb-1"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Action Required
                    </div>
                    <div
                      className="text-sm font-medium"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {highestRisk.status === "critical" ? "Immediate" : "Schedule"}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })()}

        {/* Predictions Panel */}
        <div
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {/* Panel Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
          >
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded"
                style={{ background: "rgba(245, 158, 11, 0.15)" }}
              >
                <Shield
                  className="h-5 w-5"
                  style={{ color: "var(--color-sentinel-amber)" }}
                />
              </div>
              <div>
                <h3
                  className="font-medium text-sm"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Risk Intelligence
                </h3>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  AI-powered predictive insights
                </span>
              </div>
            </div>
            {(atRiskEquipment.length > 0 || predictions.length > 0) && (
              <div className="flex items-center gap-2">
                {atRiskEquipment.filter(e => e.status === "warning").length > 0 && (
                  <span
                    className="text-xs px-2 py-1 rounded"
                    style={{
                      background: "rgba(245, 158, 11, 0.15)",
                      color: "var(--color-sentinel-amber)",
                    }}
                  >
                    {atRiskEquipment.filter(e => e.status === "warning").length} Warning
                  </span>
                )}
                {atRiskEquipment.filter(e => e.status === "critical").length > 0 && (
                  <span
                    className="text-xs px-2 py-1 rounded"
                    style={{
                      background: "rgba(220, 38, 38, 0.15)",
                      color: "var(--color-sentinel-red)",
                    }}
                  >
                    {atRiskEquipment.filter(e => e.status === "critical").length} Critical
                  </span>
                )}
                {predictions.length > 0 && (
                  <span
                    className="text-xs px-2 py-1 rounded"
                    style={{
                      background: "rgba(16, 185, 129, 0.15)",
                      color: "var(--color-sentinel-green)",
                    }}
                  >
                    {formatZAR(totalPotentialSavings)} saveable
                  </span>
                )}
              </div>
            )}
          </div>

          {/* At-Risk Equipment Section */}
          {atRiskEquipment.length > 0 && (
            <div
              className="p-4"
              style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
            >
              <h4
                className="text-sm font-medium mb-3"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Equipment Requiring Attention
              </h4>
              <div className="space-y-2">
                {atRiskEquipment.map((equip) => (
                  <div
                    key={equip.id}
                    className="flex items-center justify-between p-3 rounded cursor-pointer hover:brightness-110 transition-all"
                    style={{
                      background: equip.status === "critical"
                        ? "rgba(220, 38, 38, 0.1)"
                        : "rgba(245, 158, 11, 0.1)",
                      border: `1px solid ${equip.status === "critical"
                        ? "rgba(220, 38, 38, 0.3)"
                        : "rgba(245, 158, 11, 0.3)"}`,
                    }}
                    onClick={() => {
                      // Navigate to site detail for this equipment
                      setSelectedSiteId("site-002");
                    }}
                  >
                    <div className="flex items-center gap-3">
                      {equip.status === "critical" ? (
                        <XCircle className="h-5 w-5" style={{ color: "var(--color-sentinel-red)" }} />
                      ) : (
                        <AlertCircle className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
                      )}
                      <div>
                        <div
                          className="font-medium text-sm"
                          style={{ color: "var(--color-sentinel-text-primary)" }}
                        >
                          {equip.name}
                        </div>
                        <div
                          className="text-xs"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          {equip.category} • {equip.location}
                        </div>
                        <div
                          className="text-xs"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          {equip.building_name} • {equip.building_id}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div
                        className="text-right"
                      >
                        <div
                          className="text-sm font-medium"
                          style={{
                            color: equip.status === "critical"
                              ? "var(--color-sentinel-red)"
                              : "var(--color-sentinel-amber)",
                          }}
                        >
                          {equip.health}%
                        </div>
                        <div
                          className="text-xs uppercase"
                          style={{
                            color: equip.status === "critical"
                              ? "var(--color-sentinel-red)"
                              : "var(--color-sentinel-amber)",
                          }}
                        >
                          {equip.status}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Predictions Grid */}
          <div className="p-4">
            {predictions.length === 0 && atRiskEquipment.length === 0 ? (
              <div className="text-center py-8">
                <Shield
                  className="h-12 w-12 mx-auto mb-2"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                />
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  No risk predictions detected
                </span>
              </div>
            ) : predictions.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {predictions.map((prediction) => (
                  <PredictionCard
                    key={prediction.id}
                    prediction={prediction}
                    onClick={() => handlePredictionClick(prediction)}
                  />
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </DashboardSection>
  );

  // Render Comfort Assistant section
  const renderComfortAssistant = () => (
    <DashboardSection id="comfort-assistant">
      <div className="mt-6">
        <ComfortComplaintPanel compact={true} />
      </div>
    </DashboardSection>
  );

  // Render Occupancy Dashboard section
  const renderOccupancyDashboard = () => (
    <DashboardSection id="occupancy-dashboard">
      <div className="mt-6">
        <OccupancyPanel
          compact={true}
          onViewDetails={() => onViewChange("occupancy")}
        />
      </div>
    </DashboardSection>
  );

  // Section renderer map
  const sectionRenderers: Record<DashboardSectionId, () => JSX.Element | null> = {
    'kpi-row': renderKPIRow,
    'site-protection': renderSiteProtection,
    'energy-analytics': renderEnergyAnalytics,
    'risk-predictions': renderRiskPredictions,
    'comfort-assistant': renderComfortAssistant,
    'occupancy-dashboard': renderOccupancyDashboard,
  };

  // Filter to only visible sections
  const visibleSectionOrder = sectionOrder.filter(id => visibleSections.includes(id));

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={handleSectionDragEnd}
    >
      <div
        className="h-full overflow-y-auto p-4 md:p-6"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        {/* Customize Dashboard Button */}
        <div className="flex justify-end mb-4">
          <button
            onClick={() => setIsCardLibraryOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors hover:opacity-80"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-secondary)",
            }}
          >
            <LayoutGrid className="w-4 h-4" />
            Customize
          </button>
        </div>

        <SortableContext items={visibleSectionOrder} strategy={verticalListSortingStrategy}>
          {visibleSectionOrder.map((sectionId) => {
            const renderer = sectionRenderers[sectionId];
            if (!renderer) return null;

            const content = renderer();
            if (!content) return null;

            return <div key={sectionId}>{content}</div>;
          })}
        </SortableContext>

        {/* Prediction Detail Modal */}
        {selectedPrediction && (
          <PredictionDetail
            prediction={selectedPrediction}
            isOpen={isPredictionDetailOpen}
            onClose={closePredictionDetail}
          />
        )}

        {/* Card Library Panel */}
        <CardLibrary
          isOpen={isCardLibraryOpen}
          onClose={() => setIsCardLibraryOpen(false)}
          visibleKpiCards={visibleKpiCards}
          visibleSections={visibleSections}
          onKpiVisibilityChange={handleKpiVisibilityChange}
          onSectionVisibilityChange={handleSectionVisibilityChange}
          onResetToDefaults={handleResetToDefaults}
          isSaving={isSavingPreferences}
        />
      </div>
    </DndContext>
  );
}

export default Dashboard;

// @ts-nocheck
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
import { useServerEvents } from "@/hooks/useServerEvents";
import {
  Building2,
  AlertTriangle,
  Cpu,
  Shield,
  Bell,
  DollarSign,
  RefreshCw,
  LayoutGrid,
  Sun,
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
import api, { createWorkOrder } from '@/lib/api';
import type { DashboardStats, Site, Prediction, EnergyDataPoint, BuildingEquipmentItem } from '@/lib/api';
import { toast } from "sonner";
import { useBuildingsList } from "@/hooks/useBuildingsList";
import { SortableKPICard } from "./SortableKPICard";
import { DashboardSection } from "./DashboardSection";
import { SiteCard } from "./SiteCard";
import { SiteDetail } from "./SiteDetail";
// import { AlertFeed } from "./AlertFeed"; // Moved to header bell button
import { EnergyChart } from "./EnergyChart";
import { PredictionCard } from "./PredictionCard";
import { PageLoading } from "./PageLoading";
import { PredictionDetail } from "./PredictionDetail";
import { RiskDetailModal } from "./RiskDetailModal";
import { ROISummaryCard } from "./ROISummaryCard";
import { OccupancyPanel } from "./OccupancyPanel";
import ComfortComplaintPanel from "./ComfortComplaintPanel";
import { EnergyComparisonPanel } from "./EnergyComparisonPanel";
import { ActualVsSentinelEnergyCard } from "./ActualVsSentinelEnergyCard";
import { SolarOverviewPanel } from "./solar/SolarOverviewPanel";
import { BESSStatusPanel } from "./solar/BESSStatusPanel";
import { InverterStatusMatrix } from "./solar/InverterStatusMatrix";
import { EnergyFlowDiagram } from "./solar/EnergyFlowDiagram";
import { SolarAnnualCard } from "./solar/SolarAnnualCard";
import { LightingIntelligencePanel } from "./LightingIntelligencePanel";
import { type View } from "./Sidebar";
import CardLibrary from "./CardLibrary";
import { DEFAULT_KPI_CARDS, DEFAULT_SECTIONS } from "../lib/cardDefinitions";
import { useModules } from "@/contexts/ModuleHooks";

// Time period options for energy chart
const TIME_PERIODS = [7, 30, 90] as const;
type TimePeriod = (typeof TIME_PERIODS)[number];

// Dashboard section and KPI card types
type DashboardSectionId =
  | 'kpi-row'
  | 'site-protection'
  | 'lighting-intelligence'
  | 'energy-analytics'
  | 'risk-predictions'
  | 'comfort-assistant'
  | 'occupancy-dashboard'
  | 'energy-comparison'
  | 'energy-comparison-actual-vs-sentinel'
  | 'solar-bess'
  | 'solar-annual';

type KPICardId =
  | 'kpi-protected-sites'
  | 'kpi-monitored-assets'
  | 'kpi-active-risks'
  | 'kpi-potential-savings'
  | 'kpi-risk-predictions';

interface DashboardProps {
  onViewChange: (view: View) => void;
  openCardLibrary?: boolean;
  onCardLibraryClose?: () => void;
}

export function Dashboard({ onViewChange, openCardLibrary, onCardLibraryClose }: DashboardProps) {
  // React Query hooks - replaces old manual API calls (stale-while-revalidate approach via React Query)
  const { data: buildingsList = [] } = useBuildingsList();

  // Module gating - called once at top level (hooks cannot be called inside render functions/map callbacks)
  const { isModuleActive, activeModules } = useModules();

  // Real-time event updates from backend SSE
  useServerEvents();

  const [stats, setStats] = useState<DashboardStats | null>(null);
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


  // Risk detail modal state
  const [selectedRiskEquipment, setSelectedRiskEquipment] = useState<BuildingEquipmentItem | null>(null);
  const [showRiskModal, setShowRiskModal] = useState(false);

  // Drag and drop state
  const [sectionOrder, setSectionOrder] = useState<DashboardSectionId[]>([
    'kpi-row',
    'site-protection',
    'lighting-intelligence',
    'solar-bess',
    'solar-annual',
    'energy-analytics',
    'energy-comparison',
    'energy-comparison-actual-vs-sentinel',
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

  // Load dashboard preferences on mount
  useEffect(() => {
    const loadPreferences = async () => {
      try {
        const response = await api.getDashboardPreferences();
        if (response.preferences) {
          // Merge saved KPI cards with defaults to include any new cards
          const savedKpiCards = response.preferences.visible_kpi_cards || [];
          const mergedKpiCards = Array.from(new Set([...DEFAULT_KPI_CARDS, ...savedKpiCards]));
          setVisibleKpiCards(mergedKpiCards);

          // Merge saved sections with defaults to include any new sections
          const savedSections = response.preferences.visible_sections || [];
          const mergedSections = Array.from(new Set([...DEFAULT_SECTIONS, ...savedSections]));
          setVisibleSections(mergedSections);

          // Merge saved section order with defaults to include any new sections
          const savedOrder = response.preferences.section_order as DashboardSectionId[] || [];
          const newSections = DEFAULT_SECTIONS.filter((s) => !savedOrder.includes(s as DashboardSectionId));
          const mergedOrder = [...savedOrder, ...newSections] as DashboardSectionId[];
          setSectionOrder(mergedOrder);

          if (response.preferences.kpi_card_order) {
            setKpiOrder(response.preferences.kpi_card_order as KPICardId[]);
          }
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

  // Handle card library open state from Sidebar
  useEffect(() => {
    if (openCardLibrary) {
      setIsCardLibraryOpen(true);
    }
  }, [openCardLibrary]);

  // Handle card library close
  const handleCardLibraryClose = () => {
    setIsCardLibraryOpen(false);
    onCardLibraryClose?.();
  };

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
  // @ts-ignore - Site type mismatch from legacy api.ts
  const normalSites = buildingsList.filter((s: Site) => s.status === "normal").length;
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

  // Create work order from prediction detail modal
  const handleCreateWorkOrderFromPrediction = async (equipmentId: string, equipmentName: string) => {
    const prediction = selectedPrediction;
    if (!prediction) return;

    try {
      const priority = prediction.severity === "critical" ? "critical" as const : "high" as const;
      await createWorkOrder({
        site_id: prediction.site_id || "",
        equipment_id: equipmentId,
        fault_description: `${equipmentName} - ${prediction.prediction_type.replace(/_/g, " ")}. ${prediction.probability_percent}% failure probability within ${prediction.timeframe_days} days.`,
        priority,
      });
      toast.success(`Work order created for ${equipmentName}`);
    } catch (err) {
      console.error("Failed to create work order:", err);
      toast.error("Failed to create work order");
    }
  };

  // Close risk detail modal
  const closeRiskModal = () => {
    setShowRiskModal(false);
    setSelectedRiskEquipment(null);
  };

  // Navigate to site from risk modal
  const handleNavigateToSiteFromModal = (siteId: string) => {
    closeRiskModal();
    setSelectedSiteId(siteId);
  };

  // Navigate to control from risk modal
  const handleControlFromRiskModal = (equipmentId: string) => {
    const siteId = selectedRiskEquipment?.site_id || "";
    closeRiskModal();
    handleEquipmentControlNavigate(equipmentId, siteId);
  };

  // Create work order from risk modal
  const handleCreateWorkOrder = async (equipmentId: string) => {
    const equipment = selectedRiskEquipment;
    if (!equipment) return;

    try {
      const priority = equipment.status === "critical" ? "critical" as const : "high" as const;
      await createWorkOrder({
        site_id: equipment.site_id,
        equipment_id: equipmentId,
        fault_description: `${equipment.name} - Health score ${equipment.health}% (${equipment.status}). Scheduled maintenance required.`,
        priority,
      });
      toast.success(`Work order created for ${equipment.name}`);
    } catch (err) {
      console.error("Failed to create work order:", err);
      toast.error("Failed to create work order");
    }
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
        value: buildingsList.length,
        icon: <Building2 className="h-5 w-5" />,
        subtitle: `${normalSites} protected, ${warningSites} elevated`,
        accentColor: "blue" as const,
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

  // Card Library panel - open when sidebar "Customize Dashboard Cards" is clicked (openCardLibrary) or in-dashboard Customize
  const cardLibraryPanel = (
    <CardLibrary
      isOpen={isCardLibraryOpen || !!openCardLibrary}
      onClose={handleCardLibraryClose}
      visibleKpiCards={visibleKpiCards}
      visibleSections={visibleSections}
      onKpiVisibilityChange={handleKpiVisibilityChange}
      onSectionVisibilityChange={handleSectionVisibilityChange}
      onResetToDefaults={handleResetToDefaults}
      isSaving={isSavingPreferences}
    />
  );

  // Loading state (still show Card Library when opened from sidebar)
  if (loading) {
    return (
      <>
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
        {cardLibraryPanel}
      </>
    );
  }

  // Error state (still show Card Library when opened from sidebar)
  if (error) {
    return (
      <>
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
        {cardLibraryPanel}
      </>
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
                >
                  Site Protection Status
                </h3>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  {buildingsList.length} sites under protection
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
    );
  };


  // Render Energy Analytics section
  const renderEnergyAnalytics = () => {
    // Only skip if modules loaded successfully AND energy module is not active
    if (activeModules.length > 0 && !isModuleActive('energy')) {
      return null;
    }
    return (
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
              selectedSiteId={selectedSiteId}
              days={selectedDays}
            />
          </div>
        </div>
      </div>
    </DashboardSection>
  );
  };

  // Render Risk Predictions section
  const renderRiskPredictions = () => {
    // Only skip if modules loaded successfully AND ml module is not active
    if (activeModules.length > 0 && !isModuleActive('ml')) {
      return null;
    }
    // Find highest risk prediction (critical first, then by probability)
    const sortedPredictions = [...predictions].sort((a, b) => {
      // Critical comes before warning
      if (a.severity === "critical" && b.severity !== "critical") return -1;
      if (b.severity === "critical" && a.severity !== "critical") return 1;
      // Then sort by probability (higher = higher risk)
      return b.probability_percent - a.probability_percent;
    });
    const highestRiskPrediction = sortedPredictions[0];

    return (
    <DashboardSection id="risk-predictions">
      <div className="mt-6 space-y-6">
        {/* ROI Summary Card */}
        {predictions.length > 0 && <ROISummaryCard predictions={predictions} />}

        {/* Hero Card - Highest Risk Prediction */}
        {highestRiskPrediction && (
          <div
            className="rounded-md overflow-hidden cursor-pointer hover:brightness-105 transition-all"
            style={{
              background: highestRiskPrediction.severity === "critical"
                ? "linear-gradient(135deg, rgba(220, 38, 38, 0.2) 0%, rgba(220, 38, 38, 0.1) 100%)"
                : "linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(245, 158, 11, 0.1) 100%)",
              border: `1px solid ${highestRiskPrediction.severity === "critical" ? "rgba(220, 38, 38, 0.4)" : "rgba(245, 158, 11, 0.4)"}`,
            }}
            onClick={() => handlePredictionClick(highestRiskPrediction)}
          >
            <div className="p-5">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className="text-xs px-2 py-0.5 rounded font-medium uppercase"
                      style={{
                        background: highestRiskPrediction.severity === "critical" ? "rgba(220, 38, 38, 0.3)" : "rgba(245, 158, 11, 0.3)",
                        color: highestRiskPrediction.severity === "critical" ? "var(--color-sentinel-red)" : "var(--color-sentinel-amber)",
                      }}
                    >
                      Highest Risk - Immediate Attention Required
                    </span>
                  </div>
                  <h3
                    className="text-lg font-semibold"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    {highestRiskPrediction.equipment_name}
                  </h3>
                  <p
                    className="text-sm"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    {highestRiskPrediction.equipment_type} • {highestRiskPrediction.prediction_type.replace(/_/g, " ")}
                  </p>
                  <p
                    className="text-xs"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    {highestRiskPrediction.site_name} • Site ID: {highestRiskPrediction.site_id}
                  </p>
                </div>
                <div className="text-right">
                  <div
                    className="text-3xl font-bold"
                    style={{
                      color: highestRiskPrediction.severity === "critical" ? "var(--color-sentinel-red)" : "var(--color-sentinel-amber)",
                    }}
                  >
                    {highestRiskPrediction.probability_percent}%
                  </div>
                  <div
                    className="text-xs uppercase font-medium"
                    style={{
                      color: highestRiskPrediction.severity === "critical" ? "var(--color-sentinel-red)" : "var(--color-sentinel-amber)",
                    }}
                  >
                    Failure Probability
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
                    Timeframe
                  </div>
                  <div
                    className="text-lg font-semibold"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    {highestRiskPrediction.timeframe_days} days
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
                    Confidence
                  </div>
                  <div
                    className="text-lg font-semibold uppercase"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    {highestRiskPrediction.confidence}
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
                    Potential Loss
                  </div>
                  <div
                    className="text-lg font-semibold"
                    style={{ color: "var(--color-sentinel-red)" }}
                  >
                    {formatZAR(highestRiskPrediction.financial_impact?.potential_loss_zar || 0)}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Risk Intelligence Panel */}
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
            {predictions.length > 0 && (
              <div className="flex items-center gap-2">
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

          {/* Predictions Grid */}
          <div className="p-4">
            {predictions.length === 0 ? (
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
  };

  // Render Comfort Assistant section
  const renderComfortAssistant = () => {
    // Only skip if modules loaded successfully AND hvac module is not active
    if (activeModules.length > 0 && !isModuleActive('hvac')) {
      return null;
    }
    return (
      <DashboardSection id="comfort-assistant">
        <div className="mt-6">
          <ComfortComplaintPanel compact={true} />
        </div>
      </DashboardSection>
    );
  };

  // Render Occupancy Dashboard section
  const renderOccupancyDashboard = () => {
    // Only skip if modules loaded successfully AND lighting module is not active
    if (activeModules.length > 0 && !isModuleActive('lighting')) {
      return null;
    }
    return (
      <DashboardSection id="occupancy-dashboard">
        <div className="mt-6">
          <OccupancyPanel
            compact={true}
            onViewDetails={() => onViewChange("occupancy")}
          />
        </div>
      </DashboardSection>
    );
  };

  // Render Energy Comparison section
  const renderEnergyComparison = () => {
    // Only skip if modules loaded successfully AND energy module is not active
    if (activeModules.length > 0 && !isModuleActive('energy')) {
      return null;
    }
    return (
      <DashboardSection id="energy-comparison">
        <div className="mt-6">
          <EnergyComparisonPanel siteId="site-002" />
        </div>
      </DashboardSection>
    );
  };

  // Render Actual vs SENTINEL Energy Comparison section
  const renderEnergyComparisonActualVsSentinel = () => {
    // Only skip if modules loaded successfully AND energy module is not active
    if (activeModules.length > 0 && !isModuleActive('energy')) {
      return null;
    }
    return (
      <DashboardSection id="energy-comparison-actual-vs-sentinel">
        <div className="mt-6">
          <div className="glass-panel rounded-md overflow-hidden">
            <ActualVsSentinelEnergyCard siteId={selectedSiteId || 'site-002'} />
          </div>
        </div>
      </DashboardSection>
    );
  };

  // Render Lighting Intelligence section
  const renderLightingIntelligence = () => {
    // Only skip if modules loaded successfully AND lighting module is not active
    if (activeModules.length > 0 && !isModuleActive('lighting')) {
      return null;
    }
    return (
      <DashboardSection id="lighting-intelligence">
        <div className="mt-6">
          <LightingIntelligencePanel siteId="site-002" />
        </div>
      </DashboardSection>
    );
  };

  // Render Solar & BESS section (conditionally shown when solar module active)
  const renderSolarBess = () => {
    // Only show if solar module is active (or modules still loading)
    if (activeModules.length > 0 && !isModuleActive('solar')) {
      return null;
    }
    const solarSiteId = "site-002";

    return (
      <DashboardSection id="solar-bess">
        <div className="mt-6 space-y-4">
          {/* Section Header */}
          <div className="flex items-center gap-3 mb-2">
            <div
              className="p-2 rounded"
              style={{ background: "rgba(250, 204, 21, 0.15)" }}
            >
              <Sun
                className="h-5 w-5"
                style={{ color: "#FACC15" }}
              />
            </div>
            <div>
              <h3
                className="font-medium text-sm"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Solar & BESS
              </h3>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Site-002 Solar &mdash; 3.875 MWp PV | 5,015 kWh BESS
              </span>
            </div>
          </div>

          {/* Top: Solar Overview */}
          <SolarOverviewPanel siteId={solarSiteId} />

          {/* Middle: Energy Flow Diagram */}
          <EnergyFlowDiagram siteId={solarSiteId} />

          {/* Bottom: BESS + Inverter Matrix side by side */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <BESSStatusPanel siteId={solarSiteId} />
            <InverterStatusMatrix siteId={solarSiteId} />
          </div>
        </div>
      </DashboardSection>
    );
  };

  const renderSolarAnnual = () => {
    // Only skip if modules loaded successfully AND solar module is not active
    if (activeModules.length > 0 && !isModuleActive('solar')) {
      return null;
    }
    const solarSiteId = 'site-002';
    return (
      <DashboardSection id="solar-annual">
        <div className="mt-6 space-y-4">
          {/* Section Header */}
          <div className="flex items-center gap-3 mb-2">
            <div
              className="p-2 rounded"
              style={{ background: "rgba(250, 204, 21, 0.15)" }}
            >
              <Sun
                className="h-5 w-5"
                style={{ color: "#FACC15" }}
              />
            </div>
            <div>
              <h3
                className="font-medium text-sm"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Solar Annual Summary
              </h3>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                365-day simulation with AI savings progression
              </span>
            </div>
          </div>

          {/* Solar Annual Card */}
          <SolarAnnualCard siteId={solarSiteId} />
        </div>
      </DashboardSection>
    );
  };

  // Section renderer map
  const sectionRenderers: Record<DashboardSectionId, () => JSX.Element | null> = {
    'kpi-row': renderKPIRow,
    'site-protection': renderSiteProtection,
    'lighting-intelligence': renderLightingIntelligence,
    'energy-analytics': renderEnergyAnalytics,
    'risk-predictions': renderRiskPredictions,
    'comfort-assistant': renderComfortAssistant,
    'occupancy-dashboard': renderOccupancyDashboard,
    'energy-comparison': renderEnergyComparison,
    'energy-comparison-actual-vs-sentinel': renderEnergyComparisonActualVsSentinel,
    'solar-bess': renderSolarBess,
    'solar-annual': renderSolarAnnual,
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
        <div className="flex justify-end mb-4">
          <button
            onClick={() => setIsCardLibraryOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors hover:opacity-80 glass-subtle"
            style={{
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

        {selectedPrediction && (
          <PredictionDetail
            prediction={selectedPrediction}
            isOpen={isPredictionDetailOpen}
            onClose={closePredictionDetail}
            onCreateWorkOrder={handleCreateWorkOrderFromPrediction}
          />
        )}

        {showRiskModal && selectedRiskEquipment && (
          <RiskDetailModal
            isOpen={showRiskModal}
            onClose={closeRiskModal}
            equipment={selectedRiskEquipment}
            onNavigateToControl={handleControlFromRiskModal}
            onCreateWorkOrder={handleCreateWorkOrder}
            onNavigateToSite={handleNavigateToSiteFromModal}
          />
        )}

        {cardLibraryPanel}
      </div>
    </DndContext>
  );
}

export default Dashboard;

/**
 * Site Detail Component - Detailed view of a single site
 * SENTINEL dark theme styling
 *
 * Features:
 * - Site information header with key metrics
 * - Equipment list with health indicators
 * - Site-specific alerts
 * - Energy consumption for this site
 * - AI predictions for this site
 */

import { useState, useEffect, useRef, lazy, Suspense } from "react";
import {
  ArrowLeft,
  Building2,
  MapPin,
  Phone,
  Mail,
  Clock,
  Cpu,
  AlertTriangle,
  Zap,
  Calendar,
  TrendingUp,
  CheckCircle,
  XCircle,
  AlertCircle,
  Activity,
  FileText,
  RefreshCw,
  Save,
  Edit3,
  Info,
  Wifi,
  Server,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import api from '@/lib/api';
import type {
  Alert,
  Prediction,
  EnergyDataPoint,
  Device,
  BuildingEquipmentItem,
  CategoryStatus,
  EquipmentMetadata,
} from '@/lib/api';
import { formatDateTime, getTimezoneAbbreviation, isDifferentTimezone } from "../lib/timeFormat";
import { KPICard } from "./KPICard";
import { EnergyChart } from "./EnergyChart";
import { PredictionCard } from "./PredictionCard";
import { PredictionDetail } from "./PredictionDetail";
import { OptimizationInfoCard } from "./OptimizationInfoCard";
import { ControlPanel } from "./ControlPanel";
import { useHealthThresholds } from "../hooks/useHealthThresholds";
import { useModules } from "@/contexts/ModuleHooks";
import { LightingIntelligencePanel } from "./LightingIntelligencePanel";
import { OccupancyPanel } from "./OccupancyPanel";
import { HVACIntelligenceCard } from "./intelligence/HVACIntelligenceCard";
import { EnergyIntelligenceCard } from "./intelligence/EnergyIntelligenceCard";
import { SolarIntelligenceCard } from "./intelligence/SolarIntelligenceCard";
import { WaterIntelligenceCard } from "./intelligence/WaterIntelligenceCard";
import { FireIntelligenceCard } from "./intelligence/FireIntelligenceCard";
import { SecurityIntelligenceCard } from "./intelligence/SecurityIntelligenceCard";
import CardLibrary from "./CardLibrary";
import { DEFAULT_KPI_CARDS, DEFAULT_SECTIONS } from "../lib/cardDefinitions";
import { BUILDING_TAB_ITEMS } from "../lib/navigation";
import type { BuildingTabId } from "../lib/navigation";

// ─── Lazy-loaded tab components ─────────────────────────────────────
// HVAC
const HVACDashboard = lazy(() => import("./hvac/HVACDashboard"));
// Controls (all-device control panel)
const ControlDashboard = lazy(() => import("./ControlDashboard").then(m => ({ default: m.ControlDashboard })));
// Energy
const OptimizationPage = lazy(() => import("../pages/OptimizationPage").then(m => ({ default: m.OptimizationPage })));
// Lighting
const LightingPage = lazy(() => import("./lighting/LightingPage").then(m => ({ default: m.LightingPage })));
const OccupancyFullPanel = lazy(() => import("./OccupancyPanel").then(m => ({ default: m.OccupancyPanel })));
const OccupancyAnalyticsPage = lazy(() => import("../pages/OccupancyAnalyticsPage").then(m => ({ default: m.OccupancyAnalyticsPage })));
const OccupancyEnergyCorrelationPage = lazy(() => import("../pages/OccupancyEnergyCorrelationPage").then(m => ({ default: m.OccupancyEnergyCorrelationPage })));
// Solar & BESS
const SolarDashboard = lazy(() => import("./solar/SolarDashboard").then(m => ({ default: m.SolarDashboard })));
const AegisConsolePage = lazy(() => import("../pages/AegisConsolePage").then(m => ({ default: m.AegisConsolePage })));
// Water
const WaterPanel = lazy(() => import("./water").then(m => ({ default: m.WaterPanel })));
// Fire
const FireSafetyPage = lazy(() => import("./fire/FireSafetyPage").then(m => ({ default: m.FireSafetyPage })));
// Security
const SecurityDashboard = lazy(() => import("./security").then(m => ({ default: m.SecurityDashboard })));
// Digital Twin
const DigitalTwin = lazy(() => import("./digital-twin").then(m => ({ default: m.DigitalTwin })));
// Simulation
const SimulationDashboard = lazy(() => import("./SimulationDashboard").then(m => ({ default: m.SimulationDashboard  })));

// ─── Sub-tab types for discipline tabs ────────────────────────────
type LightingSub = "Lighting" | "Occupancy" | "Analytics" | "Correlation";
type SolarBessSub = "Dashboard" | "AEGIS";

/** Loading spinner shown while lazy tabs load */
function TabLoading() {
  return (
    <div className="flex items-center justify-center py-20">
      <div
        className="animate-spin h-8 w-8 border-4 rounded-full"
        style={{
          borderColor: "var(--color-sentinel-blue)",
          borderTopColor: "transparent",
        }}
      />
    </div>
  );
}

interface SiteDetailProps {
  siteId: string;
  onBack: () => void;
}

interface SiteDetailData {
  id: string;
  name: string;
  address: string;
  location?: string;
  region: string;
  type: string;
  sqm?: number;
  floors?: number;
  year_built?: number;
  operating_hours?: { start: string; end: string };
  timezone?: string; // IANA timezone (e.g., "Africa/Johannesburg")
  occupancy_pattern?: string;
  contact_email?: string;
  contact_phone?: string;
  equipment_count: number;
  active_alerts: number;
  alert_count?: number;
  status?: "normal" | "warning" | "critical";
  optimization_enabled?: boolean;
  sentinel_processing_enabled?: boolean;
}

// Extended equipment interface for local state (combines API response with local fields)
interface Equipment extends BuildingEquipmentItem {
  health_score: number;  // Alias for health (for backwards compat)
  last_maintenance?: string;
}

type TabType = "equipment" | "alerts" | "energy" | "predictions";

export function SiteDetail({ siteId, onBack }: SiteDetailProps) {
  const [site, setSite] = useState<SiteDetailData | null>(null);
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [equipmentCategories, setEquipmentCategories] = useState<Record<string, CategoryStatus>>({});
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [energyData, setEnergyData] = useState<EnergyDataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>("equipment");
  const [activeMainTab, setActiveMainTab] = useState<BuildingTabId>("overview");
  const [lightingSub, setLightingSub] = useState<LightingSub>("Lighting");
  const [solarBessSub, setSolarBessSub] = useState<SolarBessSub>("Dashboard");
  const [equipmentExpanded, setEquipmentExpanded] = useState(false);

  // Equipment control
  const [selectedEquipment, setSelectedEquipment] = useState<Equipment | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [showEquipmentControl, setShowEquipmentControl] = useState(false);
  const [loadingDevice, setLoadingDevice] = useState(false);

  // Equipment metadata
  const [equipmentMetadata, setEquipmentMetadata] = useState<EquipmentMetadata | null>(null);
  const [loadingMetadata, setLoadingMetadata] = useState(false);
  const [editingNotes, setEditingNotes] = useState(false);
  const [notesValue, setNotesValue] = useState("");
  const [savingNotes, setSavingNotes] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [metadataTab, setMetadataTab] = useState<"info" | "network" | "device" | "operating" | "notes">("info");

  // Prediction detail modal
  const [selectedPrediction, setSelectedPrediction] = useState<Prediction | null>(null);
  const [isPredictionDetailOpen, setIsPredictionDetailOpen] = useState(false);

  // Card visibility (CardLibrary toggle)
  const [visibleKpiCards, setVisibleKpiCards] = useState<string[]>(DEFAULT_KPI_CARDS);
  const [visibleSections, setVisibleSections] = useState<string[]>(DEFAULT_SECTIONS);

  // Scroll container ref — reset to top on mount
  const containerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    containerRef.current?.scrollTo(0, 0);
  }, [siteId]);

  // Health thresholds
  const { thresholds } = useHealthThresholds();

  // Module gating for site-specific intelligence panels
  const { isModuleActive, activeModules } = useModules();

  // SENTINEL processing state — gates all intelligence panels
  const sentinelEnabled = site?.sentinel_processing_enabled !== false;

  useEffect(() => {
    const loadSiteData = async () => {
      try {
        setLoading(true);

        // Fetch site details using API client (always — need sentinel_processing_enabled)
        const siteData = await api.getSite(siteId);
        // Map the response to SiteDetailData format
        setSite({
          ...siteData,
          address: siteData.address || siteData.location || "",
          location: siteData.location,
        } as SiteDetailData);

        // When SENTINEL is off, don't pull any BMS data
        if (siteData.sentinel_processing_enabled === false) {
          setEquipment([]);
          setEquipmentCategories({});
          setAlerts([]);
          setPredictions([]);
          setEnergyData([]);
          setError(null);
          return;
        }

        // Use site ID directly as building ID (no hardcoded mappings)
        const buildingId = siteId;

        // Fetch equipment for this building using new building equipment endpoint
        try {
          const buildingEquipment = await api.getBuildingEquipment(buildingId);
          // API returns Equipment[] with health_score field
          setEquipment(buildingEquipment.equipment as any);
          setEquipmentCategories(buildingEquipment.categories);
        } catch (eqErr) {
          console.warn("Building equipment endpoint failed, falling back to legacy:", eqErr);
          // Fallback to legacy equipment endpoint
          const equipmentData = await api.getEquipment(siteId);
          setEquipment(equipmentData.map((eq: any) => ({
            ...eq,
            health_score: 80,
            health: 80,
            category: "Other",
            controllable: false,
            details: {},
          })) as Equipment[]);
        }

        // Fetch alerts for this site
        const allAlerts = await api.getAlerts();
        setAlerts(allAlerts.filter((a) => a.site_id === siteId));

        // Fetch predictions for this site
        const predictionsData = await api.getPredictions(siteId);
        setPredictions(predictionsData.predictions || []);

        // Fetch energy data for this site
        const energyResponse = await api.getEnergy(siteId, 30);
        setEnergyData(energyResponse.data || []);

        setError(null);
      } catch (err) {
        console.error("Failed to load site data:", err);
        setError("Failed to load site details");
      } finally {
        setLoading(false);
      }
    };

    loadSiteData();
  }, [siteId]);

  const handlePredictionClick = (prediction: Prediction) => {
    setSelectedPrediction(prediction);
    setIsPredictionDetailOpen(true);
  };

  // Handle click on equipment status badge (warning/critical) to open prediction detail
  const handleEquipmentRiskClick = (equip: Equipment, e: React.MouseEvent) => {
    e.stopPropagation(); // Don't trigger row click
    // Find prediction for this equipment by matching equipment_id or name
    const prediction = predictions.find(
      (p) => p.equipment_id === equip.id || p.equipment_name === equip.name
    );
    if (prediction) {
      setSelectedPrediction(prediction);
      setIsPredictionDetailOpen(true);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "online":
      case "normal":
        return "var(--color-sentinel-green)";
      case "warning":
        return "var(--color-sentinel-amber)";
      case "offline":
      case "critical":
        return "var(--color-sentinel-red)";
      default:
        return "var(--color-sentinel-text-secondary)";
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case "online":
      case "normal":
        return <CheckCircle className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />;
      case "warning":
        return <AlertCircle className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />;
      case "offline":
      case "critical":
        return <XCircle className="h-4 w-4" style={{ color: "var(--color-sentinel-red)" }} />;
      default:
        return <Cpu className="h-4 w-4" style={{ color: "var(--color-sentinel-text-disabled)" }} />;
    }
  };

  const getSeverityConfig = (severity: string) => {
    switch (severity.toLowerCase()) {
      case "critical":
        return {
          color: "var(--color-sentinel-red)",
          bg: "rgba(220, 38, 38, 0.15)",
          border: "rgba(220, 38, 38, 0.3)",
        };
      case "high":
        return {
          color: "var(--color-sentinel-amber)",
          bg: "rgba(245, 158, 11, 0.15)",
          border: "rgba(245, 158, 11, 0.3)",
        };
      case "medium":
        return {
          color: "#FBBF24",
          bg: "rgba(251, 191, 36, 0.15)",
          border: "rgba(251, 191, 36, 0.3)",
        };
      default:
        return {
          color: "var(--color-sentinel-blue)",
          bg: "rgba(59, 130, 246, 0.15)",
          border: "rgba(59, 130, 246, 0.3)",
        };
    }
  };

  // Reserved for future use:
  // const getHealthColor = (score: number) => {
  //   if (score >= thresholds.healthy) return "var(--color-sentinel-green)";
  //   if (score >= thresholds.warning) return "var(--color-sentinel-amber)";
  //   return "var(--color-sentinel-red)";
  // };

  const handleEquipmentClick = async (equip: Equipment) => {
    try {
      setSelectedEquipment(equip);
      setShowEquipmentControl(true);
      setLoadingDevice(true);
      setLoadingMetadata(true);
      setEquipmentMetadata(null);
      setMetadataTab("info");
      setEditingNotes(false);

      // Fetch equipment controls and metadata in parallel
      const [deviceResult, metadataResult] = await Promise.allSettled([
        api.getEquipmentControls(equip.id),
        api.getEquipmentMetadata(equip.id),
      ]);

      if (deviceResult.status === "fulfilled") {
        setSelectedDevice(deviceResult.value);
      } else {
        console.warn("Could not load equipment controls:", deviceResult.reason);
        setSelectedDevice(null);
      }

      if (metadataResult.status === "fulfilled") {
        setEquipmentMetadata(metadataResult.value.equipment);
        setNotesValue(metadataResult.value.equipment.notes || "");
      } else {
        console.warn("Could not load equipment metadata:", metadataResult.reason);
      }
    } catch (error) {
      console.error("Failed to load equipment details:", error);
    } finally {
      setLoadingDevice(false);
      setLoadingMetadata(false);
    }
  };

  const handleSaveNotes = async () => {
    if (!selectedEquipment) return;

    setSavingNotes(true);
    try {
      const userEmail = localStorage.getItem("sentinel_user_email") || "unknown";
      await api.updateEquipmentNotes(selectedEquipment.id, notesValue, userEmail);
      setEquipmentMetadata((prev) => prev ? { ...prev, notes: notesValue } : null);
      setEditingNotes(false);
    } catch (error) {
      console.error("Failed to save notes:", error);
    } finally {
      setSavingNotes(false);
    }
  };

  const handleDiscoverEquipment = async () => {
    if (!selectedEquipment) return;

    setDiscovering(true);
    try {
      const result = await api.discoverEquipment(selectedEquipment.id, true);
      if (result.saved) {
        // Refresh metadata
        const metadataResult = await api.getEquipmentMetadata(selectedEquipment.id);
        setEquipmentMetadata(metadataResult.equipment);
        setNotesValue(metadataResult.equipment.notes || "");
      }
    } catch (error) {
      console.error("Discovery failed:", error);
    } finally {
      setDiscovering(false);
    }
  };

  const handleEquipmentControl = async (deviceId: string, point: string, value: number | boolean) => {
    try {
      // Use equipment control endpoint for Supabase equipment
      await api.controlEquipment(deviceId, point, value);
      // Refresh equipment list after control action
      const buildingId = siteId;
      try {
        const buildingEquipment = await api.getBuildingEquipment(buildingId);
        setEquipment(buildingEquipment.equipment.map((eq: any) => ({
          ...eq,
          health_score: eq.health || eq.health_score,
        })) as any);
        setEquipmentCategories(buildingEquipment.categories);
      } catch {
        // Fallback
        const equipmentData = await api.getEquipment(siteId);
        setEquipment(equipmentData.map((eq: any) => ({
          ...eq,
          health_score: 80,
          health: 80,
          category: "Other",
          controllable: false,
          details: {},
        })) as Equipment[]);
      }
    } catch (error) {
      console.error("Equipment control failed:", error);
      throw error;
    }
  };

  if (loading) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <div className="text-center">
          <div
            className="animate-spin h-8 w-8 border-4 rounded-full mx-auto mb-4"
            style={{
              borderColor: "var(--color-sentinel-blue)",
              borderTopColor: "transparent",
            }}
          />
          <p style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading site details...</p>
        </div>
      </div>
    );
  }

  if (error || !site) {
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
            Error Loading Site
          </h2>
          <p style={{ color: "var(--color-sentinel-text-secondary)" }} className="mb-4">
            {error}
          </p>
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onBack();
            }}
            className="px-4 py-2 rounded transition-colors cursor-pointer"
            style={{
              background: "var(--color-sentinel-blue)",
              color: "white",
            }}
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  // Calculate summary stats based on status field (matches what's shown in table)
  const healthyEquipment = equipment.filter((e) => e.status === "normal" || (e.status as string) === "online").length;
  const warningEquipment = equipment.filter((e) => e.status === "warning").length;
  const criticalEquipment = equipment.filter((e) => e.status === "critical" || (e.status as string) === "offline" || (e.status as string) === "maintenance").length;
  const avgHealth = equipment.length > 0
    ? Math.round(equipment.reduce((sum, e) => sum + (e.health_score || (e as any).health || 0), 0) / equipment.length)
    : 0;

  const statusConfig = site.status
    ? {
        normal: {
          color: "var(--color-sentinel-green)",
          bg: "rgba(16, 185, 129, 0.15)",
          label: "Protected",
        },
        warning: {
          color: "var(--color-sentinel-amber)",
          bg: "rgba(245, 158, 11, 0.15)",
          label: "Elevated",
        },
        critical: {
          color: "var(--color-sentinel-red)",
          bg: "rgba(220, 38, 38, 0.15)",
          label: "Critical",
        },
      }[site.status]
    : null;

  return (
    <div
      ref={containerRef}
      className="overflow-y-auto p-4 md:p-6"
      style={{ background: "var(--color-sentinel-bg-canvas)", height: 'calc(100vh - 3.5rem)' }}
    >
      {/* Back Button */}
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onBack();
        }}
        className="flex items-center gap-2 mb-6 transition-colors cursor-pointer hover:brightness-110"
        style={{ color: "var(--color-sentinel-text-secondary)" }}
      >
        <ArrowLeft className="h-5 w-5" />
        <span>Back to Dashboard</span>
      </button>

      {/* Site Header Banner */}
      <div
        className="rounded-md overflow-hidden mb-6"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="p-4 md:p-6">
          <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-3">
                <Building2
                  className="h-8 w-8"
                  style={{ color: "var(--color-sentinel-blue)" }}
                />
                <h1
                  className="text-2xl font-semibold flex-1"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  {site.name}
                </h1>
                {/* Site Code */}
                <span
                  className="text-sm font-mono px-2 py-1 rounded"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    color: "var(--color-sentinel-text-secondary)",
                    border: "1px solid var(--color-sentinel-border)",
                  }}
                >
                  {site.id.slice(0, 8).toUpperCase()}
                </span>
                {statusConfig && (
                  <div
                    className="flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium"
                    style={{
                      background: statusConfig.bg,
                      color: statusConfig.color,
                    }}
                  >
                    <div
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ background: statusConfig.color }}
                    />
                    {statusConfig.label}
                  </div>
                )}
                <div
                  className="px-2 py-1 rounded text-xs font-medium"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    color: "var(--color-sentinel-text-secondary)",
                  }}
                >
                  {site.type.replace("_", " ")}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                <div className="flex items-center gap-1.5">
                  <MapPin className="h-4 w-4" />
                  <span className="text-sm">{site.address}</span>
                </div>
                {site.operating_hours && (
                  <div className="flex items-center gap-1.5">
                    <Clock className="h-4 w-4" />
                    <span className="text-sm">
                      {site.operating_hours.start || "N/A"} - {site.operating_hours.end || "N/A"}
                      {isDifferentTimezone(site.timezone) && site.timezone && (
                        <span
                          className="ml-1.5 px-1.5 py-0.5 rounded text-xs font-medium"
                          style={{
                            background: "rgba(59, 130, 246, 0.15)",
                            color: "var(--color-sentinel-blue)",
                          }}
                          title={`Building timezone: ${site.timezone}`}
                        >
                          {getTimezoneAbbreviation(site.timezone)}
                        </span>
                      )}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* AI Optimization Info Card */}
      {visibleSections.includes('ai-optimization') && (
        <OptimizationInfoCard
          siteId={siteId}
          optimizationEnabled={site.optimization_enabled || false}
        />
      )}

      {/* KPI Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {visibleKpiCards.includes('kpi-equipment') && (
          <KPICard
            title="Equipment"
            value={sentinelEnabled ? site.equipment_count : "—"}
            icon={<Cpu className="h-5 w-5" />}
            accentColor="blue"
          />
        )}
        {visibleKpiCards.includes('kpi-alerts') && (
          <KPICard
            title="Active Alerts"
            value={sentinelEnabled ? alerts.length : "—"}
            icon={<AlertTriangle className="h-5 w-5" />}
            accentColor="orange"
          />
        )}
        {visibleKpiCards.includes('kpi-health') && (
          <KPICard
            title="Avg Health"
            value={sentinelEnabled ? `${avgHealth}%` : "—"}
            icon={<TrendingUp className="h-5 w-5" />}
            accentColor={sentinelEnabled && avgHealth >= thresholds.healthy ? "green" : sentinelEnabled && avgHealth >= thresholds.warning ? "orange" : sentinelEnabled ? "red" : "blue"}
          />
        )}
        {visibleKpiCards.includes('kpi-predictions') && (
          <KPICard
            title="Predictions"
            value={sentinelEnabled ? predictions.length : "—"}
            icon={<TrendingUp className="h-5 w-5" />}
            accentColor="purple"
          />
        )}
      </div>

      {/* Site Info Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div
          className="rounded-md p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{
                background: "rgba(59, 130, 246, 0.15)",
                color: "var(--color-sentinel-blue)",
              }}
            >
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Building Size
              </p>
              <p className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {(site.sqm || 0).toLocaleString()} sqm
              </p>
            </div>
          </div>
        </div>

        <div
          className="rounded-md p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{
                background: "rgba(168, 85, 247, 0.15)",
                color: "#a78bfa",
              }}
            >
              <Calendar className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Year Built
              </p>
              <p className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {site.year_built || "N/A"}
              </p>
            </div>
          </div>
        </div>

        <div
          className="rounded-md p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{
                background: "rgba(16, 185, 129, 0.15)",
                color: "var(--color-sentinel-green)",
              }}
            >
              <Phone className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Contact
              </p>
              <p className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {site.contact_phone || "N/A"}
              </p>
            </div>
          </div>
        </div>

        <div
          className="rounded-md p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{
                background: "rgba(245, 158, 11, 0.15)",
                color: "var(--color-sentinel-amber)",
              }}
            >
              <Mail className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Email
              </p>
              <p className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {site.contact_email || "N/A"}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════
          Main Tab Bar — 10 discipline tabs (SIMBIOT-data-driven)
          ═══════════════════════════════════════════════════════════ */}
      <div
        className="mb-6 rounded-md"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div
          className="flex overflow-x-auto border-b scrollbar-hide"
          style={{ borderColor: "var(--color-sentinel-border)" }}
        >
          {BUILDING_TAB_ITEMS
            .filter((tab) => {
              // Hide tabs that require a module add-on (e.g., simulation)
              if (tab.requiredModule && !isModuleActive(tab.requiredModule)) return false;
              // Controls tab: only show if ANY control add-on is active
              if (tab.id === "controls") {
                const CONTROL_MODULES = [
                  'hvac_control', 'energy_control', 'lighting_control',
                  'solar_control', 'water_control', 'security_control',
                  'digital_twin_control',
                ] as const;
                return CONTROL_MODULES.some(mod => isModuleActive(mod));
              }
              return true;
            })
            .map((tab) => {
              const Icon = tab.icon;
              const isActive = activeMainTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveMainTab(tab.id)}
                  className="flex-shrink-0 flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors relative whitespace-nowrap"
                  style={{
                    color: isActive
                      ? "var(--color-sentinel-amber)"
                      : "var(--color-sentinel-text-secondary)",
                    borderBottom: isActive
                      ? "2px solid var(--color-sentinel-amber)"
                      : "2px solid transparent",
                    background: isActive
                      ? "rgba(245, 158, 11, 0.08)"
                      : "transparent",
                  }}
                >
                  <Icon className="h-4 w-4" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════
          Tab Content
          ═══════════════════════════════════════════════════════════ */}

      {activeMainTab === "overview" ? (
      <>
      {/* Overview Tab — original Equipment/Alerts/Energy/Predictions tabs + summary panels */}
      <div
        className="rounded-md overflow-hidden mb-6"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        {/* Sub-Tab Navigation (Equipment/Alerts/Energy/Predictions) */}
        <div
          className="flex overflow-x-auto border-b scrollbar-hide"
          style={{ borderColor: "var(--color-sentinel-border)" }}
        >
          {[
            { id: "equipment" as TabType, label: "Equipment", icon: Cpu, count: equipment.length },
            { id: "alerts" as TabType, label: "Alerts", icon: AlertTriangle, count: alerts.length },
            { id: "energy" as TabType, label: "Energy", icon: Zap },
            { id: "predictions" as TabType, label: "Predictions", icon: TrendingUp, count: predictions.length },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className="flex-shrink-0 flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors relative whitespace-nowrap"
                style={{
                  color: isActive
                    ? "var(--color-sentinel-text-primary)"
                    : "var(--color-sentinel-text-secondary)",
                  borderBottom: isActive ? `2px solid var(--color-sentinel-blue)` : "2px solid transparent",
                }}
              >
                <Icon className="h-4 w-4" />
                <span>
                  {tab.label}
                  {tab.count !== undefined && ` (${tab.count})`}
                </span>
              </button>
            );
          })}
        </div>

        {/* Tab Content */}
        <div className="p-4 md:p-6">
          {/* Equipment Tab */}
          {activeTab === "equipment" && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setEquipmentExpanded(!equipmentExpanded)}
                    className="flex items-center gap-2 hover:opacity-80 transition-opacity"
                    style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
                  >
                    {equipmentExpanded ? (
                      <ChevronDown className="h-5 w-5" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                    ) : (
                      <ChevronRight className="h-5 w-5" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                    )}
                    <h3
                      className="text-lg font-semibold"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      Equipment
                    </h3>
                  </button>
                  <div
                    className="px-2 py-1 rounded text-xs font-medium"
                    style={{
                      background: "rgba(59, 130, 246, 0.15)",
                      color: "var(--color-sentinel-blue)",
                    }}
                  >
                    {equipment.length} Total
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div
                    className="px-2 py-1 rounded text-xs font-medium"
                    style={{
                      background: "rgba(16, 185, 129, 0.15)",
                      color: "var(--color-sentinel-green)",
                    }}
                  >
                    {healthyEquipment} OK
                  </div>
                  <div
                    className="px-2 py-1 rounded text-xs font-medium flex items-center gap-1"
                    style={{
                      background: "rgba(59, 130, 246, 0.15)",
                      color: "var(--color-sentinel-blue)",
                    }}
                    title="Equipment with BMS controls"
                  >
                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    {equipment.filter(e => e.controllable).length} Controllable
                  </div>
                  <button
                    onClick={() => {
                      // Filter to warning equipment and show first prediction if available
                      const warningItems = equipment.filter((e) => e.status === "warning");
                      if (warningItems.length > 0) {
                        const prediction = predictions.find(
                          (p) => warningItems.some((w) => p.equipment_id === w.id || p.equipment_name === w.name)
                        );
                        if (prediction) {
                          setSelectedPrediction(prediction);
                          setIsPredictionDetailOpen(true);
                        } else {
                          // No prediction yet - show the first warning equipment in control panel
                          const firstWarning = warningItems[0];
                          handleEquipmentClick(firstWarning);
                        }
                      }
                    }}
                    className="px-2 py-1 rounded text-xs font-medium transition-all hover:brightness-110 cursor-pointer"
                    style={{
                      background: "rgba(245, 158, 11, 0.15)",
                      color: "var(--color-sentinel-amber)",
                    }}
                    title="Click to view failure predictions for warning equipment"
                  >
                    {warningEquipment} Warning
                  </button>
                  <button
                    onClick={() => {
                      // Filter to critical equipment and show first prediction if available
                      const criticalItems = equipment.filter((e) => e.status === "critical" || (e.status as string) === "offline" || (e.status as string) === "maintenance");
                      if (criticalItems.length > 0) {
                        const prediction = predictions.find(
                          (p) => criticalItems.some((c) => p.equipment_id === c.id || p.equipment_name === c.name)
                        );
                        if (prediction) {
                          setSelectedPrediction(prediction);
                          setIsPredictionDetailOpen(true);
                        } else {
                          // No prediction yet - show the first critical equipment in control panel
                          const firstCritical = criticalItems[0];
                          handleEquipmentClick(firstCritical);
                        }
                      }
                    }}
                    className="px-2 py-1 rounded text-xs font-medium transition-all hover:brightness-110 cursor-pointer"
                    style={{
                      background: "rgba(220, 38, 38, 0.15)",
                      color: "var(--color-sentinel-red)",
                    }}
                    title="Click to view failure predictions for critical equipment"
                  >
                    {criticalEquipment} Critical
                  </button>
                </div>
              </div>

              {/* Category Filter Chips + Equipment Table (collapsible) */}
              {equipmentExpanded && Object.keys(equipmentCategories).length > 0 && (
                <div className="flex flex-wrap gap-2 mb-4">
                  <button
                    onClick={() => setSelectedCategory(null)}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                      selectedCategory === null ? "ring-2 ring-offset-1" : ""
                    }`}
                    style={{
                      background: selectedCategory === null
                        ? "var(--color-sentinel-blue)"
                        : "var(--color-sentinel-bg-secondary)",
                      color: selectedCategory === null
                        ? "white"
                        : "var(--color-sentinel-text-secondary)",
                      "--tw-ring-color": "var(--color-sentinel-blue)",
                    } as React.CSSProperties}
                  >
                    All ({equipment.length})
                  </button>
                  {Object.entries(equipmentCategories).map(([category, stats]) => (
                    <button
                      key={category}
                      onClick={() => setSelectedCategory(category)}
                      className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                        selectedCategory === category ? "ring-2 ring-offset-1" : ""
                      }`}
                      style={{
                        background: selectedCategory === category
                          ? "var(--color-sentinel-blue)"
                          : "var(--color-sentinel-bg-secondary)",
                        color: selectedCategory === category
                          ? "white"
                          : "var(--color-sentinel-text-secondary)",
                        "--tw-ring-color": "var(--color-sentinel-blue)",
                      } as React.CSSProperties}
                    >
                      {category} ({stats.total})
                      {stats.critical > 0 && (
                        <span
                          className="ml-1 px-1 rounded"
                          style={{
                            background: "rgba(220, 38, 38, 0.3)",
                            color: "var(--color-sentinel-red)",
                          }}
                        >
                          {stats.critical}
                        </span>
                      )}
                      {stats.warning > 0 && (
                        <span
                          className="ml-1 px-1 rounded"
                          style={{
                            background: "rgba(245, 158, 11, 0.3)",
                            color: "var(--color-sentinel-amber)",
                          }}
                        >
                          {stats.warning}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              )}

              {equipmentExpanded && (() => {
                // Filter by category, then sort: warnings/critical first, then by health (lowest first)
                const filteredEquipment = (selectedCategory
                  ? equipment.filter((eq) => eq.category === selectedCategory)
                  : equipment
                ).sort((a, b) => {
                  // Priority: critical > warning > normal
                  const statusPriority = { critical: 0, warning: 1, normal: 2 };
                  const aPriority = statusPriority[a.status as keyof typeof statusPriority] ?? 2;
                  const bPriority = statusPriority[b.status as keyof typeof statusPriority] ?? 2;
                  if (aPriority !== bPriority) return aPriority - bPriority;
                  // Same status: sort by health (lowest first)
                  return (a.health ?? 100) - (b.health ?? 100);
                });

                return filteredEquipment.length === 0 ? (
                  <div className="text-center py-12">
                    <Cpu
                      className="h-12 w-12 mx-auto mb-3"
                      style={{ color: "var(--color-sentinel-text-disabled)" }}
                    />
                    <p style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {selectedCategory
                        ? `No ${selectedCategory} equipment found`
                        : "No equipment found for this site"}
                    </p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                          {["Equipment", "Category", "Type", "Location", "Status", "Health"].map((header) => (
                            <th
                              key={header}
                              className="text-left py-3 px-4 text-xs font-medium uppercase tracking-wider"
                              style={{ color: "var(--color-sentinel-text-secondary)" }}
                            >
                              {header}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {filteredEquipment.map((item) => (
                          <tr
                            key={item.id}
                            className="hover:brightness-110 cursor-pointer transition-colors"
                            style={{
                              borderBottom: "1px solid var(--color-sentinel-border)",
                            }}
                            onClick={() => handleEquipmentClick(item)}
                          >
                            <td className="py-3 px-4">
                              <div className="flex items-center gap-3">
                                {getStatusIcon(item.status)}
                                <div>
                                  <div className="flex items-center gap-2">
                                    <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                      {item.name}
                                    </p>
                                    {item.controllable && (
                                      <span
                                        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium"
                                        style={{
                                          background: "rgba(16, 185, 129, 0.15)",
                                          color: "var(--color-sentinel-green)",
                                        }}
                                        title="BMS Controllable - Click to open control panel"
                                      >
                                        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                        </svg>
                                        BMS
                                      </span>
                                    )}
                                  </div>
                                  <p className="text-xs font-mono" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                                    {item.id}
                                  </p>
                                </div>
                              </div>
                            </td>
                            <td className="py-3 px-4">
                              <div
                                className="inline-block px-2 py-1 rounded text-xs font-medium"
                                style={{
                                  background: item.category === "HVAC"
                                    ? "rgba(59, 130, 246, 0.15)"
                                    : item.category === "Generator Plant"
                                    ? "rgba(245, 158, 11, 0.15)"
                                    : item.category === "Energy Centre"
                                    ? "rgba(168, 85, 247, 0.15)"
                                    : item.category === "Lighting"
                                    ? "rgba(251, 191, 36, 0.15)"
                                    : "var(--color-sentinel-bg-secondary)",
                                  color: item.category === "HVAC"
                                    ? "var(--color-sentinel-blue)"
                                    : item.category === "Generator Plant"
                                    ? "var(--color-sentinel-amber)"
                                    : item.category === "Energy Centre"
                                    ? "#a78bfa"
                                    : item.category === "Lighting"
                                    ? "#fbbf24"
                                    : "var(--color-sentinel-text-secondary)",
                                }}
                              >
                                {item.category}
                              </div>
                            </td>
                            <td className="py-3 px-4">
                              <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                {item.type.replace(/_/g, " ")}
                              </span>
                            </td>
                            <td className="py-3 px-4">
                              <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                {item.location || "—"}
                              </span>
                            </td>
                            <td className="py-3 px-4">
                              {item.status === "warning" || item.status === "critical" ? (
                                <button
                                  onClick={(e) => handleEquipmentRiskClick(item, e)}
                                  className="inline-block px-2 py-1 rounded text-xs font-medium cursor-pointer hover:opacity-80 transition-opacity"
                                  style={{
                                    background: getStatusColor(item.status) + "20",
                                    color: getStatusColor(item.status),
                                    border: "none",
                                  }}
                                  title="Click to view prediction details"
                                >
                                  {item.status}
                                </button>
                              ) : (
                                <div
                                  className="inline-block px-2 py-1 rounded text-xs font-medium"
                                  style={{
                                    background: getStatusColor(item.status) + "20",
                                    color: getStatusColor(item.status),
                                  }}
                                >
                                  {item.status}
                                </div>
                              )}
                            </td>
                            <td className="py-3 px-4">
                              <div className="flex items-center gap-2">
                                <div className="flex-1 max-w-[80px] h-2 rounded-full overflow-hidden" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <div
                                    className="h-full rounded-full"
                                    style={{
                                      width: `${item.health_score}%`,
                                      background: getStatusColor(item.status),
                                    }}
                                  />
                                </div>
                                <span className="text-sm font-medium w-10" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                  {item.health_score}%
                                </span>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })()}
            </div>
          )}

          {/* Alerts Tab */}
          {activeTab === "alerts" && (
            <div>
              <h3
                className="text-lg font-semibold mb-4"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Active Alerts
              </h3>

              {alerts.length === 0 ? (
                <div className="text-center py-12">
                  <CheckCircle
                    className="h-12 w-12 mx-auto mb-3"
                    style={{ color: "var(--color-sentinel-green)" }}
                  />
                  <p style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    No active alerts for this site
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {alerts.map((alert) => {
                    const severityConfig = getSeverityConfig(alert.severity);
                    return (
                      <div
                        key={alert.id}
                        className="rounded-md p-4"
                        style={{
                          background: severityConfig.bg,
                          border: `1px solid ${severityConfig.border}`,
                        }}
                      >
                        <div className="flex items-start gap-3">
                          <AlertTriangle className="h-5 w-5 mt-0.5" style={{ color: severityConfig.color }} />
                          <div className="flex-1">
                            <div className="flex items-start justify-between mb-2">
                              <div>
                                <p className="font-medium text-sm mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                  {alert.message}
                                </p>
                                <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                  {alert.equipment_name}
                                </p>
                              </div>
                              <div
                                className="px-2 py-1 rounded text-xs font-medium"
                                style={{
                                  background: severityConfig.bg,
                                  color: severityConfig.color,
                                }}
                              >
                                {alert.severity}
                              </div>
                            </div>
                            <p className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                              {formatDateTime(alert.created_at)}
                            </p>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Energy Tab */}
          {activeTab === "energy" && (
            <div>
              <h3
                className="text-lg font-semibold mb-4"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Energy Consumption - Last 30 Days
              </h3>
              <EnergyChart
                data={energyData}
                loading={false}
                selectedSiteId={siteId}
                days={30}
              />
            </div>
          )}

          {/* Predictions Tab */}
          {activeTab === "predictions" && (
            <div>
              <h3
                className="text-lg font-semibold mb-4"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                AI Failure Predictions
              </h3>

              {predictions.length === 0 ? (
                <div className="text-center py-12">
                  <TrendingUp
                    className="h-12 w-12 mx-auto mb-3"
                    style={{ color: "var(--color-sentinel-text-disabled)" }}
                  />
                  <p style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    No predictions for this site
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {predictions.map((prediction) => (
                    <PredictionCard
                      key={prediction.id}
                      prediction={prediction}
                      onClick={() => handlePredictionClick(prediction)}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════
          Site Intelligence Panels (moved from main dashboard)
          These are site-specific and belong in the building detail view.
          Gated on sentinel_processing_enabled — when SENTINEL is off,
          show a clean offline state instead of stale/empty panels.
          ═══════════════════════════════════════════════════════════ */}

      {!sentinelEnabled ? (
        <div
          className="mb-6 rounded-lg border p-8 text-center"
          style={{
            borderColor: "var(--color-sentinel-border)",
            background: "var(--color-sentinel-bg-secondary)",
          }}
        >
          <XCircle
            className="h-10 w-10 mx-auto mb-3"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          />
          <h3
            className="text-lg font-medium mb-1"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            SENTINEL Processing Offline
          </h3>
          <p
            className="text-sm"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Intelligence panels are disabled while SENTINEL is not processing this site.
            Enable processing from the building card toggle to activate AI insights.
          </p>
        </div>
      ) : (
      <>
      {/* CardLibrary inline toggle */}
      <CardLibrary
        visibleKpiCards={visibleKpiCards}
        visibleSections={visibleSections}
        onKpiVisibilityChange={(id, visible) => {
          setVisibleKpiCards(prev => visible ? [...prev, id] : prev.filter(c => c !== id));
        }}
        onSectionVisibilityChange={(id, visible) => {
          setVisibleSections(prev => visible ? [...prev, id] : prev.filter(c => c !== id));
        }}
        onResetToDefaults={() => {
          setVisibleKpiCards(DEFAULT_KPI_CARDS);
          setVisibleSections(DEFAULT_SECTIONS);
        }}
      />

      {/* ── Discipline Intelligence Cards ── */}
      <div className="space-y-4">
        {isModuleActive('hvac') && visibleSections.includes('hvac-intelligence') && (
          <HVACIntelligenceCard siteId={siteId} onNavigate={() => setActiveMainTab('hvac')} />
        )}
        {isModuleActive('energy') && visibleSections.includes('energy-intelligence') && (
          <EnergyIntelligenceCard siteId={siteId} onNavigate={() => setActiveMainTab('energy')} />
        )}
        {isModuleActive('solar') && visibleSections.includes('solar-intelligence') && (
          <SolarIntelligenceCard siteId={siteId} onNavigate={() => setActiveMainTab('solar-bess')} />
        )}
        {isModuleActive('water') && visibleSections.includes('water-intelligence') && (
          <WaterIntelligenceCard siteId={siteId} onNavigate={() => setActiveMainTab('water')} />
        )}
        {isModuleActive('fire') && visibleSections.includes('fire-intelligence') && (
          <FireIntelligenceCard siteId={siteId} onNavigate={() => setActiveMainTab('fire')} />
        )}
        {isModuleActive('security') && visibleSections.includes('security-intelligence') && (
          <SecurityIntelligenceCard siteId={siteId} onNavigate={() => setActiveMainTab('security')} />
        )}
        {/* #7 Occupancy */}
        {isModuleActive('lighting') && visibleSections.includes('occupancy-dashboard') && (
          <OccupancyPanel compact={true} />
        )}
        {/* #8 Lighting Intelligence */}
        {isModuleActive('lighting') && visibleSections.includes('lighting-intelligence') && (
          <LightingIntelligencePanel siteId={siteId} compact />
        )}
      </div>
      </>
      )}
      </>
      ) : !sentinelEnabled ? (
      /* When SENTINEL is off, all non-overview tabs show offline banner */
      <div
        className="rounded-lg border p-12 text-center"
        style={{
          borderColor: "var(--color-sentinel-border)",
          background: "var(--color-sentinel-bg-secondary)",
        }}
      >
        <XCircle
          className="h-12 w-12 mx-auto mb-4"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        />
        <h3
          className="text-lg font-medium mb-2"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          SENTINEL Processing Offline
        </h3>
        <p
          className="text-sm max-w-md mx-auto"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          This tab requires active SENTINEL processing.
          Enable processing from the building card toggle to access system health, operations, and analytics.
        </p>
      </div>
      ) : (
      /* ═══════════════════════════════════════════════════════════
         Non-overview tabs — consolidated with sub-tab pills
         ═══════════════════════════════════════════════════════════ */
      <Suspense fallback={<TabLoading />}>
        <div className="min-h-[400px]">
          {/* HVAC — Zone temps, equipment status, optimization */}
          {activeMainTab === "hvac" && (
            <HVACDashboard siteId={siteId} />
          )}

          {/* Energy — Optimization (control features gated by energy_control) */}
          {activeMainTab === "energy" && (
            <OptimizationPage />
          )}

          {/* Lighting — Lighting | Occupancy | Analytics | Correlation */}
          {activeMainTab === "lighting" && (
            <>
              <div className="flex overflow-x-auto gap-2 mb-4 scrollbar-hide">
                {(["Lighting", "Occupancy", "Analytics", "Correlation"] as LightingSub[]).map(sub => (
                  <button
                    key={sub}
                    onClick={() => setLightingSub(sub)}
                    className="flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-colors whitespace-nowrap"
                    style={{
                      background: lightingSub === sub ? "var(--color-sentinel-amber)" : "var(--color-sentinel-bg-secondary)",
                      color: lightingSub === sub ? "white" : "var(--color-sentinel-text-secondary)",
                    }}
                  >
                    {sub}
                  </button>
                ))}
              </div>
              {lightingSub === "Lighting" && <LightingPage />}
              {lightingSub === "Occupancy" && (
                <div className="p-4 md:p-6"><OccupancyFullPanel compact={false} /></div>
              )}
              {lightingSub === "Analytics" && <OccupancyAnalyticsPage />}
              {lightingSub === "Correlation" && <OccupancyEnergyCorrelationPage />}
            </>
          )}

          {/* Solar & BESS — Dashboard | AEGIS (AEGIS gated by solar_control) */}
          {activeMainTab === "solar-bess" && (
            <>
              <div className="flex overflow-x-auto gap-2 mb-4 scrollbar-hide">
                {(["Dashboard", ...(isModuleActive('solar_control') ? ["AEGIS"] : [])] as SolarBessSub[]).map(sub => (
                  <button
                    key={sub}
                    onClick={() => setSolarBessSub(sub)}
                    className="flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-colors whitespace-nowrap"
                    style={{
                      background: solarBessSub === sub ? "var(--color-sentinel-amber)" : "var(--color-sentinel-bg-secondary)",
                      color: solarBessSub === sub ? "white" : "var(--color-sentinel-text-secondary)",
                    }}
                  >
                    {sub}
                  </button>
                ))}
              </div>
              {solarBessSub === "Dashboard" && <SolarDashboard />}
              {solarBessSub === "AEGIS" && isModuleActive('solar_control') && <AegisConsolePage />}
            </>
          )}

          {/* Water */}
          {activeMainTab === "water" && <WaterPanel />}

          {/* Fire — always read-only, no control toggle */}
          {activeMainTab === "fire" && <FireSafetyPage />}

          {/* Security (control features gated by security_control) */}
          {activeMainTab === "security" && <SecurityDashboard />}

          {/* Digital Twin (write actions gated by digital_twin_control) */}
          {activeMainTab === "digital-twin" && (
            <div className="h-[calc(100vh-300px)]"><DigitalTwin /></div>
          )}

          {/* Controls — all-device control panel (visible when any control add-on active) */}
          {activeMainTab === "controls" && (
            <ControlDashboard onError={() => {}} />
          )}

          {/* Simulation — only visible when simulation add-on is active */}
          {activeMainTab === "simulation" && isModuleActive('simulation') && (
            <SimulationDashboard />
          )}
        </div>
      </Suspense>
      )}

      {/* Prediction Detail Modal */}
      {selectedPrediction && (
        <PredictionDetail
          prediction={selectedPrediction}
          isOpen={isPredictionDetailOpen}
          onClose={() => {
            setIsPredictionDetailOpen(false);
            setSelectedPrediction(null);
          }}
        />
      )}

      {/* Equipment Control Modal */}
      {showEquipmentControl && selectedEquipment && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(0, 0, 0, 0.7)" }}
          onClick={() => {
            setShowEquipmentControl(false);
            setSelectedEquipment(null);
            setSelectedDevice(null);
          }}
        >
          <div
            className="rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div
              className="p-4 border-b flex items-center justify-between"
              style={{ borderColor: "var(--color-sentinel-border)" }}
            >
              <div>
                <h3
                  className="text-lg font-semibold"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  {selectedEquipment.name}
                </h3>
                <p
                  className="text-sm"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  {selectedEquipment.type.replace("_", " ")} • {selectedEquipment.id}
                </p>
              </div>
              <button
                onClick={() => {
                  setShowEquipmentControl(false);
                  setSelectedEquipment(null);
                  setSelectedDevice(null);
                }}
                className="p-2 rounded transition-colors"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                <XCircle className="h-5 w-5" />
              </button>
            </div>

            {/* Control Panel */}
            <div className="p-4 overflow-y-auto" style={{ maxHeight: "calc(90vh - 80px)" }}>
              {loadingDevice ? (
                <div className="flex items-center justify-center py-12">
                  <div
                    className="animate-spin h-8 w-8 border-4 rounded-full"
                    style={{
                      borderColor: "var(--color-sentinel-blue)",
                      borderTopColor: "transparent",
                    }}
                  />
                </div>
              ) : selectedDevice ? (
                <ControlPanel
                  device={selectedDevice}
                  onControl={handleEquipmentControl}
                  safetyStatus={{
                    status: selectedDevice.safety_status === "critical" ? "blocked" :
                            selectedDevice.safety_status === "warning" ? "warning" : "safe",
                  }}
                />
              ) : (
                <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {/* Equipment Info Header with Discovery Button */}
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-4">
                      <div
                        className="p-3 rounded-lg"
                        style={{
                          background: selectedEquipment.category === "HVAC"
                            ? "rgba(59, 130, 246, 0.15)"
                            : selectedEquipment.category === "Lighting"
                            ? "rgba(251, 191, 36, 0.15)"
                            : selectedEquipment.category === "Energy Centre"
                            ? "rgba(168, 85, 247, 0.15)"
                            : "var(--color-sentinel-bg-secondary)",
                        }}
                      >
                        <Cpu className="h-8 w-8" style={{ color: "var(--color-sentinel-text-disabled)" }} />
                      </div>
                      <div>
                        <p className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {selectedEquipment.name}
                        </p>
                        <p className="text-sm font-mono" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                          {selectedEquipment.id}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={handleDiscoverEquipment}
                      disabled={discovering}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors hover:brightness-110"
                      style={{
                        background: "var(--color-sentinel-blue)",
                        color: "white",
                        opacity: discovering ? 0.7 : 1,
                      }}
                    >
                      <RefreshCw className={`h-4 w-4 ${discovering ? "animate-spin" : ""}`} />
                      {discovering ? "Discovering..." : "Discover"}
                    </button>
                  </div>

                  {/* Metadata Tabs */}
                  <div
                    className="flex gap-1 mb-4 p-1 rounded-lg"
                    style={{ background: "var(--color-sentinel-bg-secondary)" }}
                  >
                    {[
                      { id: "info" as const, label: "Info", icon: Info },
                      { id: "network" as const, label: "Network", icon: Wifi },
                      { id: "device" as const, label: "Device", icon: Server },
                      { id: "operating" as const, label: "Operating", icon: Activity },
                      { id: "notes" as const, label: "Notes", icon: FileText },
                    ].map((tab) => {
                      const Icon = tab.icon;
                      const isActive = metadataTab === tab.id;
                      return (
                        <button
                          key={tab.id}
                          onClick={() => setMetadataTab(tab.id)}
                          className="flex-1 flex items-center justify-center gap-1.5 px-2 py-2 rounded-md text-xs font-medium transition-colors"
                          style={{
                            background: isActive ? "var(--color-sentinel-bg-panel)" : "transparent",
                            color: isActive ? "var(--color-sentinel-text-primary)" : "var(--color-sentinel-text-secondary)",
                          }}
                        >
                          <Icon className="h-3.5 w-3.5" />
                          {tab.label}
                        </button>
                      );
                    })}
                  </div>

                  {/* Tab Content */}
                  {loadingMetadata ? (
                    <div className="flex items-center justify-center py-8">
                      <div
                        className="animate-spin h-6 w-6 border-2 rounded-full"
                        style={{ borderColor: "var(--color-sentinel-blue)", borderTopColor: "transparent" }}
                      />
                    </div>
                  ) : (
                    <>
                      {/* Info Tab */}
                      {metadataTab === "info" && (
                        <div className="grid grid-cols-2 gap-3">
                          <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                            <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Category</p>
                            <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{selectedEquipment.category}</p>
                          </div>
                          <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                            <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Type</p>
                            <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{selectedEquipment.type.replace(/_/g, " ")}</p>
                          </div>
                          <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                            <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Status</p>
                            <div className="flex items-center gap-2">
                              {getStatusIcon(selectedEquipment.status)}
                              <p className="font-medium text-sm" style={{ color: getStatusColor(selectedEquipment.status) }}>{selectedEquipment.status}</p>
                            </div>
                          </div>
                          <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                            <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Health</p>
                            <div className="flex items-center gap-2">
                              <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
                                <div className="h-full rounded-full" style={{ width: `${selectedEquipment.health_score}%`, background: getStatusColor(selectedEquipment.status) }} />
                              </div>
                              <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{selectedEquipment.health_score}%</span>
                            </div>
                          </div>
                          {selectedEquipment.location && (
                            <div className="p-3 rounded-lg col-span-2" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                              <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Location</p>
                              <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{selectedEquipment.location}</p>
                            </div>
                          )}
                          {equipmentMetadata?.commissioning_date && (
                            <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                              <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Commissioned</p>
                              <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.commissioning_date}</p>
                            </div>
                          )}
                          {equipmentMetadata?.warranty_expiry && (
                            <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                              <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Warranty Expiry</p>
                              <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.warranty_expiry}</p>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Network Tab */}
                      {metadataTab === "network" && (
                        <div className="space-y-3">
                          {equipmentMetadata?.network_info && Object.keys(equipmentMetadata.network_info).length > 0 ? (
                            <div className="grid grid-cols-2 gap-3">
                              {equipmentMetadata.network_info.ip_address && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>IP Address</p>
                                  <p className="font-mono text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.network_info.ip_address}</p>
                                </div>
                              )}
                              {equipmentMetadata.network_info.mac_address && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>MAC Address</p>
                                  <p className="font-mono text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.network_info.mac_address}</p>
                                </div>
                              )}
                              {equipmentMetadata.network_info.protocol && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Protocol</p>
                                  <p className="font-medium text-sm uppercase" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.network_info.protocol}</p>
                                </div>
                              )}
                              {equipmentMetadata.network_info.dali_address !== undefined && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>DALI Address</p>
                                  <p className="font-mono text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>Line {equipmentMetadata.network_info.dali_line || 1}, Address {equipmentMetadata.network_info.dali_address}</p>
                                </div>
                              )}
                              {equipmentMetadata.network_info.bacnet_device_id !== undefined && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>BACnet Device ID</p>
                                  <p className="font-mono text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.network_info.bacnet_device_id}</p>
                                </div>
                              )}
                              {equipmentMetadata.network_info.modbus_address !== undefined && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Modbus Address</p>
                                  <p className="font-mono text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.network_info.modbus_address}</p>
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="text-center py-8" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                              <Wifi className="h-8 w-8 mx-auto mb-2 opacity-50" />
                              <p className="text-sm">No network information available</p>
                              <p className="text-xs mt-1">Click "Discover" to fetch network details</p>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Device Tab */}
                      {metadataTab === "device" && (
                        <div className="space-y-3">
                          {equipmentMetadata?.device_info && Object.keys(equipmentMetadata.device_info).length > 0 ? (
                            <div className="grid grid-cols-2 gap-3">
                              {equipmentMetadata.device_info.manufacturer && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Manufacturer</p>
                                  <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.device_info.manufacturer}</p>
                                </div>
                              )}
                              {equipmentMetadata.device_info.model && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Model</p>
                                  <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.device_info.model}</p>
                                </div>
                              )}
                              {equipmentMetadata.device_info.serial_number && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Serial Number</p>
                                  <p className="font-mono text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.device_info.serial_number}</p>
                                </div>
                              )}
                              {equipmentMetadata.device_info.gtin && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>GTIN</p>
                                  <p className="font-mono text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.device_info.gtin}</p>
                                </div>
                              )}
                              {equipmentMetadata.device_info.firmware_version && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Firmware</p>
                                  <p className="font-mono text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>v{equipmentMetadata.device_info.firmware_version}</p>
                                </div>
                              )}
                              {equipmentMetadata.device_info.hardware_version && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Hardware</p>
                                  <p className="font-mono text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>v{equipmentMetadata.device_info.hardware_version}</p>
                                </div>
                              )}
                              {equipmentMetadata.device_info.device_type && (
                                <div className="p-3 rounded-lg col-span-2" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Device Type</p>
                                  <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.device_info.device_type}</p>
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="text-center py-8" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                              <Server className="h-8 w-8 mx-auto mb-2 opacity-50" />
                              <p className="text-sm">No device information available</p>
                              <p className="text-xs mt-1">Click "Discover" to fetch device details</p>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Operating Tab */}
                      {metadataTab === "operating" && (
                        <div className="space-y-3">
                          {equipmentMetadata?.operating_data && Object.keys(equipmentMetadata.operating_data).length > 0 ? (
                            <div className="grid grid-cols-2 gap-3">
                              {equipmentMetadata.operating_data.runtime_hours !== undefined && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Runtime Hours</p>
                                  <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.operating_data.runtime_hours.toLocaleString()} hrs</p>
                                </div>
                              )}
                              {equipmentMetadata.operating_data.lamp_hours !== undefined && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Lamp Hours</p>
                                  <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.operating_data.lamp_hours.toLocaleString()} hrs</p>
                                </div>
                              )}
                              {equipmentMetadata.operating_data.power_cycles !== undefined && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Power Cycles</p>
                                  <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.operating_data.power_cycles.toLocaleString()}</p>
                                </div>
                              )}
                              {equipmentMetadata.operating_data.rated_capacity && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Rated Capacity</p>
                                  <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.operating_data.rated_capacity}</p>
                                </div>
                              )}
                              {equipmentMetadata.operating_data.system_status && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>System Status</p>
                                  <p className="font-medium text-sm capitalize" style={{ color: "var(--color-sentinel-green)" }}>{equipmentMetadata.operating_data.system_status}</p>
                                </div>
                              )}
                              {equipmentMetadata.operating_data.energy_kwh !== undefined && (
                                <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Energy (Total)</p>
                                  <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.operating_data.energy_kwh.toLocaleString()} kWh</p>
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="text-center py-8" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                              <Activity className="h-8 w-8 mx-auto mb-2 opacity-50" />
                              <p className="text-sm">No operating data available</p>
                              <p className="text-xs mt-1">Click "Discover" to fetch operating statistics</p>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Notes Tab */}
                      {metadataTab === "notes" && (
                        <div className="space-y-3">
                          {editingNotes ? (
                            <div>
                              <textarea
                                value={notesValue}
                                onChange={(e) => setNotesValue(e.target.value)}
                                className="w-full h-32 p-3 rounded-lg text-sm resize-none"
                                style={{
                                  background: "var(--color-sentinel-bg-secondary)",
                                  color: "var(--color-sentinel-text-primary)",
                                  border: "1px solid var(--color-sentinel-border)",
                                }}
                                placeholder="Add notes about this equipment..."
                              />
                              <div className="flex gap-2 mt-2">
                                <button
                                  onClick={handleSaveNotes}
                                  disabled={savingNotes}
                                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm"
                                  style={{ background: "var(--color-sentinel-green)", color: "white" }}
                                >
                                  <Save className="h-4 w-4" />
                                  {savingNotes ? "Saving..." : "Save"}
                                </button>
                                <button
                                  onClick={() => {
                                    setEditingNotes(false);
                                    setNotesValue(equipmentMetadata?.notes || "");
                                  }}
                                  className="px-3 py-2 rounded-lg text-sm"
                                  style={{ background: "var(--color-sentinel-bg-secondary)", color: "var(--color-sentinel-text-secondary)" }}
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div>
                              {equipmentMetadata?.notes ? (
                                <div
                                  className="p-4 rounded-lg whitespace-pre-wrap text-sm"
                                  style={{ background: "var(--color-sentinel-bg-secondary)", color: "var(--color-sentinel-text-primary)" }}
                                >
                                  {equipmentMetadata.notes}
                                </div>
                              ) : (
                                <div className="text-center py-6" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                                  <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
                                  <p className="text-sm">No notes for this equipment</p>
                                </div>
                              )}
                              <button
                                onClick={() => setEditingNotes(true)}
                                className="flex items-center gap-2 px-3 py-2 mt-3 rounded-lg text-sm"
                                style={{ background: "var(--color-sentinel-bg-secondary)", color: "var(--color-sentinel-text-secondary)" }}
                              >
                                <Edit3 className="h-4 w-4" />
                                {equipmentMetadata?.notes ? "Edit Notes" : "Add Notes"}
                              </button>
                            </div>
                          )}
                          {equipmentMetadata?.last_discovery && (
                            <p className="text-xs mt-4" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                              Last discovered: {new Date(equipmentMetadata.last_discovery).toLocaleString()}
                            </p>
                          )}
                        </div>
                      )}
                    </>
                  )}

                  {/* Control Status Banner */}
                  {!selectedEquipment.controllable && (
                    <div
                      className="p-3 rounded-lg text-center mt-4"
                      style={{
                        background: "rgba(107, 114, 128, 0.1)",
                        border: "1px solid var(--color-sentinel-border)",
                      }}
                    >
                      <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        This equipment is monitored only — no BMS control points available.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SiteDetail;

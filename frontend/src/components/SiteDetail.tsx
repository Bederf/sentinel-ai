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

import { useState, useEffect, useRef, useMemo, lazy, Suspense } from "react";
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
  ChevronRight,
  Shield,
  ClipboardList,
} from "lucide-react";
import api, { createWorkOrder } from '@/lib/api';
import type {
  Prediction,
  EnergyDataPoint,
  Device,
  BuildingEquipmentItem,
  CategoryStatus,
  EquipmentMetadata,
} from '@/lib/api';
import { getTimezoneAbbreviation, isDifferentTimezone } from "../lib/timeFormat";
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
import { ChatWidget } from "./ChatWidget";
import { DEFAULT_KPI_CARDS, DEFAULT_SECTIONS } from "../lib/cardDefinitions";
import { ArcadeView } from "./arcade/ArcadeView";
import { OverviewCockpitHost } from "./cockpit/OverviewCockpitHost";

import { TabBar } from "./TabBar";
import { PageLoading } from "./PageLoading";
import type { BuildingTabId } from "../lib/navigation";
import { phaseAllows, PHASE_LABELS, PHASE_COLORS, PHASE_DESCRIPTIONS, type OnboardingPhase } from "../lib/onboardingPhase";
import { setStoredSelectedSite } from "../lib/siteSelection";

// ─── Lazy-loaded tab components ─────────────────────────────────────
// HVAC
const HVACDashboard = lazy(() => import("./hvac/HVACDashboard"));
// Controls (all-device control panel)
const ControlDashboard = lazy(() => import("./ControlDashboard").then(m => ({ default: m.ControlDashboard })));
// Energy
const OptimizationPage = lazy(() => import("../pages/OptimizationPage").then(m => ({ default: m.OptimizationPage })));
// Lighting
const LightingPage = lazy(() => import("./lighting/LightingPage").then(m => ({ default: m.LightingPage })));
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
// Space Optimization
const SpaceOptimizationPage = lazy(() => import("./SpaceOptimizationPage").then(m => ({ default: m.SpaceOptimizationPage })));
// Fuel
const FuelDashboard = lazy(() => import("./fuel/FuelDashboard").then(m => ({ default: m.FuelDashboard })));
// ESG & Sustainability
const SustainabilityDashboard = lazy(() => import("./sustainability/SustainabilityDashboard").then(m => ({ default: m.SustainabilityDashboard })));
const AssetWorkflowDashboard = lazy(() => import("./AssetWorkflowDashboard").then(m => ({ default: m.AssetWorkflowDashboard })));
const DigitalTwin = lazy(() => import("./digital-twin").then(m => ({ default: m.DigitalTwin })));
const CompliancePage = lazy(() => import("../pages/CompliancePage").then(m => ({ default: m.CompliancePage })));

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
  defaultMainTab?: BuildingTabId;
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
  // Last phase transition record (from phase_transition_log)
  last_phase_transition?: {
    to_phase: string;
    changed_by: string;
    created_at: string;
    reason?: string | null;
  } | null;
  // Bridge ingestion status
  bridge_connected?: boolean;
  bridge_data_source?: "simbiot" | "simulation" | "none";
  bridge_last_sync?: string | null;
  bridge_sync_error?: string | null;
}

// Extended equipment interface for local state (combines API response with local fields)
interface Equipment extends BuildingEquipmentItem {
  health_score: number;  // Alias for health (for backwards compat)
  last_maintenance?: string;
}

type TabType = "equipment" | "energy" | "predictions";

export function SiteDetail({ siteId, onBack, defaultMainTab }: SiteDetailProps) {
  const [site, setSite] = useState<SiteDetailData | null>(null);
  const [siteFloors, setSiteFloors] = useState<string[] | null>(null);
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [equipmentCategories, setEquipmentCategories] = useState<Record<string, CategoryStatus>>({});
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [alertsTotal, setAlertsTotal] = useState<number>(0);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [totalRiskExposure, setTotalRiskExposure] = useState<number>(0);
  const [energyData, setEnergyData] = useState<EnergyDataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>("equipment");
  const [activeMainTab, setActiveMainTab] = useState<BuildingTabId>(defaultMainTab || "overview");
  const [lightingSub, setLightingSub] = useState<LightingSub>("Lighting");
  const [solarBessSub, setSolarBessSub] = useState<SolarBessSub>("Dashboard");
  const [equipmentExpanded, setEquipmentExpanded] = useState(false);
  /** Building spatial view (ArcadeView) — collapsed by default */
  const [spatialViewExpanded, setSpatialViewExpanded] = useState(false);

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
  const [equipmentAlerts, setEquipmentAlerts] = useState<any[] | null>(null);
  const [loadingEquipmentAlerts, setLoadingEquipmentAlerts] = useState(false);
  const [sitePhase, setSitePhase] = useState<OnboardingPhase>("shadow");
  const [liveBridgeConnected, setLiveBridgeConnected] = useState<boolean | null>(null);
  const [liveBridgeLastSync, setLiveBridgeLastSync] = useState<string | null>(null);
  const [liveBridgeSource, setLiveBridgeSource] = useState<string | null>(null);

  // Prediction detail modal
  const [selectedPrediction, setSelectedPrediction] = useState<Prediction | null>(null);
  const [isPredictionDetailOpen, setIsPredictionDetailOpen] = useState(false);

  // Card visibility (CardLibrary toggle) — persisted to localStorage
  const [visibleKpiCards, setVisibleKpiCards] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem("sentinel_visible_kpi_cards");
      return saved ? JSON.parse(saved) : DEFAULT_KPI_CARDS;
    } catch { return DEFAULT_KPI_CARDS; }
  });
  const [visibleSections, setVisibleSections] = useState<string[]>(() => {
    try {
      // v2 key: forces reset to new defaults (intelligence cards hidden by default)
      const saved = localStorage.getItem("sentinel_visible_sections_v2");
      return saved ? JSON.parse(saved) : DEFAULT_SECTIONS;
    } catch { return DEFAULT_SECTIONS; }
  });

  // Trigger-engine overrides from ArcadeView floor clicks
  const [triggerVisibleSections, setTriggerVisibleSections] = useState<string[]>([]);

  // Map module keys (from trigger API) to section IDs used in render conditions
  const MODULE_TO_SECTION: Record<string, string> = {
    hvac: "hvac-intelligence",
    energy: "energy-intelligence",
    solar: "solar-intelligence",
    water: "water-intelligence",
    fire: "fire-intelligence",
    security: "security-intelligence",
    occupancy: "occupancy-dashboard",
    lighting: "lighting-intelligence",
  };

  const handleModuleDisplayChange = (moduleDisplay: Record<string, string>) => {
    const revealed = Object.entries(moduleDisplay)
      .filter(([, state]) => state !== "hidden")
      .map(([module]) => MODULE_TO_SECTION[module])
      .filter(Boolean) as string[];
    setTriggerVisibleSections(revealed);
  };

  // Combine user preference sections with transient trigger overrides.
  // useMemo is mandatory — prevents stale closure bugs in render conditions.
  const effectiveVisibleSections = useMemo(
    () => [...new Set([...visibleSections, ...triggerVisibleSections])],
    [visibleSections, triggerVisibleSections]
  );

  // Scroll container ref — reset to top on mount
  const containerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    containerRef.current?.scrollTo(0, 0);
  }, [siteId]);

  // Health thresholds
  const { thresholds } = useHealthThresholds();

  // Module gating for site-specific intelligence panels
  const { isModuleActive, activeModules: _activeModules, setSite: setModuleSite } = useModules();

  // Switch module context to current site so tabs/features reflect this site's modules
  useEffect(() => {
    if (siteId) {
      setModuleSite(siteId, siteId);
      setStoredSelectedSite(siteId);
    }
  }, [siteId, setModuleSite]);

  // SENTINEL processing state — gates all intelligence panels
  const sentinelEnabled = site?.sentinel_processing_enabled !== false;
  const systemFilter = ({
    hvac: 'hvac',
    energy: 'energy',
    lighting: 'lighting',
    water: 'water',
    fire: 'fire',
    security: 'security',
    'solar-bess': 'solar_bess',
  } as const)[activeMainTab] ?? null;
  const bridgeSourceValue = liveBridgeSource ?? site?.bridge_data_source ?? null;
  const bridgeConnectedValue = liveBridgeConnected ?? site?.bridge_connected ?? false;
  const bridgeLastSyncValue = liveBridgeLastSync ?? site?.bridge_last_sync ?? null;
  const bridgeSourceLabel =
    bridgeSourceValue === "remote_bridge"
      ? "SIMBIOT"
      : bridgeSourceValue === "local_adapter"
      ? "Local Adapter"
      : bridgeSourceValue === "none" || !bridgeSourceValue
      ? "SIMBIOT"
      : bridgeSourceValue;

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
        setSitePhase((siteData.onboarding_phase as OnboardingPhase) ?? "shadow");

        // Bridge status from site data (status/telemetry endpoints were removed with Cloudflare Worker)
        setLiveBridgeConnected(siteData.sentinel_processing_enabled ? true : null);
        setLiveBridgeLastSync(siteData.last_telemetry_at ?? null);
        setLiveBridgeSource(siteData.bridge_data_source ?? null);

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

        // Fetch equipment for this building using new building equipment endpoint
        try {
          const buildingEquipment = await api.getSiteEquipment(siteId);
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
        const { total } = await api.getAlerts(siteId);
        setAlertsTotal(total);

        // Fetch predictions for this site
        const predictionsData = await api.getPredictions(siteId);
        // Gate: only show predictions with last_reading data (confidence-gated at source)
        const predictionsWithData = (predictionsData.predictions || []).filter(
          (p: Prediction) => p.latest_reading?.value != null
        );
        setPredictions(predictionsWithData);
        // Sum potential_loss_zar for risk exposure KPI (all predictions, not just filtered)
        const riskSum = (predictionsData.predictions || []).reduce(
          (sum: number, p: Prediction) => sum + (p.financial_impact?.potential_loss_zar || 0),
          0
        );
        setTotalRiskExposure(riskSum);

        // Fetch energy data for this site
        const energyResponse = await api.getEnergy(siteId, 30);
        setEnergyData(energyResponse.data || []);

        // Fetch building config for cockpit floor configuration
        try {
          const floorsRes = await authorizedFetch(`/api/buildings/${encodeURIComponent(siteId)}`);
          if (floorsRes.ok) {
            const config = await floorsRes.json();
            if (config.floors?.length) setSiteFloors(config.floors);
          }
        } catch {
          // Building config fetch failure is silent — cockpit falls back to SITE_TOWER_PROFILES
        }

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

  const handleCreateWorkOrderFromPrediction = async (equipmentId: string, equipmentName: string) => {
    if (!siteId) return;
    try {
      const pred = selectedPrediction;
      const faultDesc = pred
        ? `${equipmentName} — ${pred.prediction_type || "predicted failure"} (${pred.probability_percent}% probability)`
        : `${equipmentName} — maintenance required`;
      const diagnosis = pred?.recommended_action || `Predicted failure for ${equipmentName}`;
      const priority = pred?.severity === "critical" ? "critical" as const : "high" as const;

      const wo = await createWorkOrder({
        site_id: siteId,
        equipment_id: equipmentId,
        fault_description: faultDesc,
        diagnosis,
        priority,
      });
      alert(`Work Order ${wo.id} created for ${equipmentName}`);
    } catch (err) {
      console.error("Failed to create work order:", err);
      alert("Failed to create work order. Check console for details.");
    }
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
      setEquipmentAlerts(null);
      setLoadingEquipmentAlerts(true);

      // Fetch equipment controls, metadata, and alerts in parallel
      const [deviceResult, metadataResult, alertsResult] = await Promise.allSettled([
        api.getEquipmentControls(equip.id),
        api.getEquipmentMetadata(equip.id),
        api.getEquipmentAlerts(siteId, equip.id),
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

      if (alertsResult.status === "fulfilled") {
        setEquipmentAlerts(alertsResult.value.alerts);
      } else {
        setEquipmentAlerts([]);
      }
    } catch (error) {
      console.error("Failed to load equipment details:", error);
    } finally {
      setLoadingDevice(false);
      setLoadingMetadata(false);
      setLoadingEquipmentAlerts(false);
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
      try {
        const buildingEquipment = await api.getSiteEquipment(siteId);
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
    return <PageLoading message="Loading site details..." />;
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

  // Calculate summary stats — status field tracks BMS comms, health_score tracks mechanical equipment condition
  // Critical = health degradation (operational). Offline = comms loss (BMS not reporting, may be healthy).
  // Phase 226 — passive devices (DALI, meters, sensors) have health_score: null and are excluded.
  // Phase 230 — thresholds aligned to DB/backend standard: OK >= 85, Warning 65-84, Critical < 65.
  // Status field (offline/maintenance/needs_attention) is comms/lifecycle state, kept separate from
  // health-score-derived buckets to avoid double-counting items that are both e.g. "needs_attention"
  // AND have a healthy score (the old code's `||` caused exactly this overlap).
  const scorableEquipment = equipment.filter((e) => e.health_score != null);
  const healthyEquipment = scorableEquipment.filter((e) => e.health_score! >= 85).length;
  const warningEquipment = scorableEquipment.filter((e) => e.health_score! >= 65 && e.health_score! < 85).length;
  const criticalEquipment = scorableEquipment.filter((e) => e.health_score! < 65).length;
  const offlineEquipment = equipment.filter((e) => (e.status as string) === "offline" || (e.status as string) === "maintenance").length;
  const healthValues = scorableEquipment.map((e) => e.health_score!).filter((v): v is number => typeof v === "number" && v > 0);
  const avgHealth = healthValues.length > 0
    ? Math.round(healthValues.reduce((sum, v) => sum + v, 0) / healthValues.length)
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
      className="overflow-y-auto p-3 sm:p-4 md:p-6"
      style={{ background: "var(--color-sentinel-bg-canvas)", height: 'calc(100dvh - 3.5rem)' }}
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
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-3">
                <Building2
                  className="h-7 w-7 shrink-0 sm:h-8 sm:w-8"
                  style={{ color: "var(--color-sentinel-blue)" }}
                />
                <h1
                  className="min-w-0 flex-[1_1_14rem] text-xl font-semibold leading-tight sm:text-2xl"
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
                {/* Data valve badge - shows if data is flowing and from where */}
                {(bridgeSourceValue && bridgeSourceValue !== "none") || liveBridgeConnected !== null || sentinelEnabled === false ? (
                  <div
                    className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium"
                    title={
                      sentinelEnabled === false
                        ? "Data valve closed - no data flowing"
                        : bridgeConnectedValue
                        ? `Data flowing from ${bridgeSourceLabel}${bridgeLastSyncValue ? ` (last sync: ${new Date(bridgeLastSyncValue).toLocaleTimeString()})` : ""}`
                        : `Data valve open, source: ${bridgeSourceLabel} ${site.bridge_sync_error ? `- ${site.bridge_sync_error}` : "- not connected"}`
                    }
                    style={{
                      background:
                        sentinelEnabled === false
                          ? "rgba(107, 114, 128, 0.15)" // Gray when closed
                          : bridgeConnectedValue
                          ? "rgba(16, 185, 129, 0.15)" // Green when connected
                          : "rgba(239, 68, 68, 0.15)", // Red when open but not connected
                      color:
                        sentinelEnabled === false
                          ? "var(--color-sentinel-text-secondary)"
                          : bridgeConnectedValue
                          ? "var(--color-sentinel-green)"
                          : "var(--color-sentinel-red)",
                      border: `1px solid ${
                        sentinelEnabled === false
                          ? "rgba(107, 114, 128, 0.3)"
                          : bridgeConnectedValue
                          ? "rgba(16, 185, 129, 0.3)"
                          : "rgba(239, 68, 68, 0.3)"
                      }`,
                    }}
                  >
                    <Wifi className="h-3 w-3" />
                    {sentinelEnabled === false ? (
                      <span>Valve Closed</span>
                    ) : (
                      <>
                        <span>{bridgeSourceLabel}</span>
                        <div
                          className="w-1.5 h-1.5 rounded-full"
                          style={{
                            background: bridgeConnectedValue
                              ? "var(--color-sentinel-green)"
                              : "var(--color-sentinel-red)",
                          }}
                        />
                      </>
                    )}
                  </div>
                ) : null}

                {/* Onboarding phase — view-only badge (set via Settings page) */}
                <div className="flex items-center gap-2">
                  <span
                    className="text-xs font-medium rounded px-2 py-1"
                    style={{
                      backgroundColor: `${PHASE_COLORS[sitePhase]}22`,
                      color: PHASE_COLORS[sitePhase],
                      border: `1px solid ${PHASE_COLORS[sitePhase]}44`,
                    }}
                    title={PHASE_DESCRIPTIONS[sitePhase]}
                  >
                    {PHASE_LABELS[sitePhase]}
                  </span>
                  {site?.last_phase_transition && (() => {
                    const d = new Date(site.last_phase_transition.created_at);
                    const dateStr = isNaN(d.getTime()) ? "unknown date" : d.toLocaleDateString("en-ZA");
                    return (
                      <span
                        title={`Phase set to ${site.last_phase_transition.to_phase} by ${site.last_phase_transition.changed_by} on ${dateStr}`}
                        className="cursor-help"
                      >
                        ℹ
                      </span>
                    );
                  })()}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-3 sm:gap-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                <div className="flex min-w-0 items-center gap-1.5">
                  <MapPin className="h-4 w-4 shrink-0" />
                  <span className="min-w-0 text-sm break-words">{site.address}</span>
                </div>
                {site.operating_hours && (
                  <div className="flex min-w-0 items-center gap-1.5">
                    <Clock className="h-4 w-4 shrink-0" />
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
      {effectiveVisibleSections.includes('ai-optimization') && (
        <OptimizationInfoCard
          siteId={siteId}
          optimizationEnabled={site.optimization_enabled || false}
          onboardingPhase={sitePhase}
        />
      )}

      {/* KPI Cards Row — only on overview tab to avoid duplication with module-specific sections */}
      {activeMainTab === "overview" && (
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
            value={sentinelEnabled ? alertsTotal : "—"}
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
        {visibleKpiCards.includes('kpi-savings') && (
          <KPICard
            title="Risk Exposure"
            value={`R${totalRiskExposure.toLocaleString()}`}
            icon={<AlertTriangle className="h-5 w-5" />}
            accentColor="orange"
            subtitle="Predicted loss exposure — all active predictions"
          />
        )}
      </div>
      )}

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
            <div className="min-w-0">
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
                color: "var(--color-sentinel-purple)",
              }}
            >
              <Calendar className="h-5 w-5" />
            </div>
            <div className="min-w-0">
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
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Contact
              </p>
              <p className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {site.contact_phone || "N/A"}
              </p>
            </div>
          </div>
        </div>

        {site.contact_email && (
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
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Email
                </p>
                <p className="text-sm font-semibold break-all" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {site.contact_email}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════════
          Sentinel Cockpit + tabs — persists across all tabs
          ═══════════════════════════════════════════════════════════ */}
      {sentinelEnabled && site && (
        <div className="mb-6">
          <OverviewCockpitHost
            siteId={siteId}
            siteName={site.name}
            gpsLat={site.latitude ?? null}
            gpsLon={site.longitude ?? null}
            orientationDegrees={site.orientation_degrees ?? null}
            onboardingPhase={sitePhase}
            activeAlerts={alertsTotal}
            predictionsCount={predictions.length}
            equipmentCount={equipment.length}
            siteFloors={siteFloors ?? undefined}
            systemFilter={systemFilter}
            activeMainTab={activeMainTab}
            onMainTabChange={setActiveMainTab}
            isModuleActive={isModuleActive}
          />
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════
          Tab Content
          ═══════════════════════════════════════════════════════════ */}

      {activeMainTab === "overview" ? (
      <>
      <div className="mb-6">
        <button
          type="button"
          onClick={() => setSpatialViewExpanded((v) => !v)}
          className="w-full flex items-center justify-between rounded-md px-4 py-2.5 mb-2 text-left text-sm font-medium transition-colors hover:brightness-110"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
            color: "var(--color-sentinel-text-primary)",
          }}
          aria-expanded={spatialViewExpanded}
        >
          <span className="flex items-center gap-2">
            <ChevronRight
              className={`h-4 w-4 shrink-0 transition-transform ${spatialViewExpanded ? "rotate-90" : ""}`}
              aria-hidden
            />
            Building spatial view
          </span>
          <span className="text-xs font-normal" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {spatialViewExpanded ? "Hide" : "Show"}
          </span>
        </button>
        {spatialViewExpanded && (
          <ArcadeView siteId={siteId} onModuleDisplayChange={handleModuleDisplayChange} />
        )}
      </div>
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
                    <div className="space-y-4">
                      {/* Equipment Controls Row */}
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setEquipmentExpanded(!equipmentExpanded)}
                            className="flex items-center gap-2 text-sm font-medium transition-colors hover:opacity-80"
                            style={{ color: "var(--color-sentinel-text-primary)" }}
                          >
                            <ChevronRight
                              className={`h-4 w-4 transition-transform ${equipmentExpanded ? "rotate-90" : ""}`}
                            />
                            <h3
                              className="text-lg font-semibold"
                              style={{ color: "var(--color-sentinel-text-primary)" }}
                            >
                              Equipment
                            </h3>
                          </button>
                          {equipment.length > 0 && (
                          <div
                            className="px-2 py-1 rounded text-xs font-medium"
                            style={{
                              background: "rgba(59, 130, 246, 0.15)",
                              color: "var(--color-sentinel-blue)",
                            }}
                          >
                            {equipment.length} Total
                          </div>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {(healthyEquipment > 0 || equipment.length === 0) && (
                          <div
                            className="px-2 py-1 rounded text-xs font-medium"
                            style={{
                              background: "rgba(16, 185, 129, 0.15)",
                              color: "var(--color-sentinel-green)",
                            }}
                          >
                            {healthyEquipment} OK
                          </div>
                          )}
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
                      // Filter to warning equipment (health 65-84) and show first prediction if available
                      const warningItems = equipment.filter((e) => e.health_score != null && e.health_score >= 65 && e.health_score < 85);
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
                      // Filter to critical equipment (health < 65) and show first prediction if available
                      const criticalItems = equipment.filter((e) => e.health_score != null && e.health_score < 65);
                      if (criticalItems.length > 0) {
                        const prediction = predictions.find(
                          (p) => criticalItems.some((c) => p.equipment_id === c.id || p.equipment_name === c.name)
                        );
                        if (prediction) {
                          setSelectedPrediction(prediction);
                          setIsPredictionDetailOpen(true);
                        } else {
                          // No prediction yet — show the first critical equipment in control panel
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
                  {offlineEquipment > 0 && (
                    <button
                      onClick={() => {
                        // Filter to offline equipment (comms loss, not health degradation)
                        const offlineItems = equipment.filter((e) => (e.status as string) === "offline" || (e.status as string) === "maintenance");
                        if (offlineItems.length > 0) {
                          const firstOffline = offlineItems[0];
                          handleEquipmentClick(firstOffline);
                        }
                      }}
                      className="px-2 py-1 rounded text-xs font-medium transition-all hover:brightness-110 cursor-pointer"
                      style={{
                        background: "rgba(107, 114, 128, 0.15)",
                        color: "var(--color-sentinel-text-secondary)",
                      }}
                      title="Equipment with lost BMS communications — may be healthy"
                    >
                      {offlineEquipment} Offline
                    </button>
                  )}
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
                          {["Equipment", "Category", "Type", "Location", "Status", "Alerts", "Health"].map((header) => (
                            <th
                              key={header}
                              className="text-left py-3 px-4 text-xs font-medium uppercase tracking-wider"
                              style={{ color: "var(--color-sentinel-text-secondary)" }}
                              title={header === "Health" ? "ML cold-start baseline · real scores populate after 72h telemetry" : undefined}
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
                                    ? "var(--color-sentinel-purple)"
                                    : item.category === "Lighting"
                                    ? "var(--color-sentinel-amber)"
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
                              {(item as any).alert_count > 0 ? (
                                <div
                                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"
                                  style={{
                                    background: "rgba(220, 38, 38, 0.15)",
                                    color: "var(--color-sentinel-red, #ef4444)",
                                  }}
                                >
                                  <span className="h-2 w-2 rounded-full" style={{ background: "var(--color-sentinel-red, #ef4444)" }} />
                                  {(item as any).alert_count}
                                </div>
                              ) : (
                                <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>—</span>
                              )}
                            </td>
                            <td className="py-3 px-4">
                              <div className="flex items-center gap-2">
                                <div className="flex-1 max-w-[80px] h-2 rounded-full overflow-hidden" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                  <div
                                    className="h-full rounded-full"
                                    style={{
                                      width: item.health_score != null ? `${item.health_score}%` : '0%',
                                      background: getStatusColor(item.status),
                                    }}
                                  />
                                </div>
                                <span className="text-sm font-medium w-10" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                  {item.health_score != null ? `${item.health_score}%` : '—'}
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
          setVisibleKpiCards(prev => {
            const next = visible ? [...prev, id] : prev.filter(c => c !== id);
            localStorage.setItem("sentinel_visible_kpi_cards", JSON.stringify(next));
            return next;
          });
        }}
        onSectionVisibilityChange={(id, visible) => {
          setVisibleSections(prev => {
            const next = visible ? [...prev, id] : prev.filter(c => c !== id);
            localStorage.setItem("sentinel_visible_sections_v2", JSON.stringify(next));
            return next;
          });
        }}
        onResetToDefaults={() => {
          setVisibleKpiCards(DEFAULT_KPI_CARDS);
          setVisibleSections(DEFAULT_SECTIONS);
          localStorage.removeItem("sentinel_visible_kpi_cards");
          localStorage.removeItem("sentinel_visible_sections_v2");
        }}
      />

      {/* ── Discipline Intelligence Cards ── */}
      <div className="space-y-4">
        {isModuleActive('hvac') && effectiveVisibleSections.includes('hvac-intelligence') && (
          <HVACIntelligenceCard siteId={siteId} onNavigate={() => setActiveMainTab('hvac')} />
        )}
        {isModuleActive('energy') && effectiveVisibleSections.includes('energy-intelligence') && (
          <EnergyIntelligenceCard siteId={siteId} onNavigate={() => setActiveMainTab('energy')} />
        )}
        {isModuleActive('solar') && effectiveVisibleSections.includes('solar-intelligence') && (
          <SolarIntelligenceCard siteId={siteId} onNavigate={() => setActiveMainTab('solar-bess')} />
        )}
        {isModuleActive('water') && effectiveVisibleSections.includes('water-intelligence') && (
          <WaterIntelligenceCard siteId={siteId} onNavigate={() => setActiveMainTab('water')} />
        )}
        {isModuleActive('fire') && effectiveVisibleSections.includes('fire-intelligence') && (
          <FireIntelligenceCard siteId={siteId} onNavigate={() => setActiveMainTab('fire')} />
        )}
        {isModuleActive('security') && effectiveVisibleSections.includes('security-intelligence') && (
          <SecurityIntelligenceCard siteId={siteId} onNavigate={() => setActiveMainTab('security')} />
        )}
        {/* #7 Occupancy */}
        {isModuleActive('lighting') && effectiveVisibleSections.includes('occupancy-dashboard') && (
          <OccupancyPanel compact={true} />
        )}
        {/* #8 Lighting Intelligence */}
        {isModuleActive('lighting') && effectiveVisibleSections.includes('lighting-intelligence') && (
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
            <>
              <div className="mb-4"><HVACIntelligenceCard siteId={siteId} /></div>
              <HVACDashboard siteId={siteId} onboardingPhase={sitePhase} />
            </>
          )}

          {/* Energy — Optimization (control features gated by energy_control) */}
          {activeMainTab === "energy" && (
            <>
              <div className="mb-4"><EnergyIntelligenceCard siteId={siteId} /></div>
              <OptimizationPage />
            </>
          )}

          {/* Lighting — Lighting | Occupancy | Analytics | Correlation */}
          {activeMainTab === "lighting" && (
            <>
              <div className="mb-4"><LightingIntelligencePanel siteId={siteId} compact /></div>
              <TabBar
                tabs={[
                  { id: "Lighting", label: "Lighting" },
                  { id: "Occupancy", label: "Occupancy" },
                  { id: "Analytics", label: "Analytics" },
                  { id: "Correlation", label: "Correlation" },
                ]}
                active={lightingSub}
                onChange={(id) => setLightingSub(id as LightingSub)}
                accentColor="var(--color-sentinel-blue)"
              />
              {lightingSub === "Lighting" && <LightingPage siteId={siteId} />}
              {lightingSub === "Occupancy" && (
                <div className="p-4 md:p-6"><OccupancyPanel compact={false} /></div>
              )}
              {lightingSub === "Analytics" && <OccupancyAnalyticsPage />}
              {lightingSub === "Correlation" && <OccupancyEnergyCorrelationPage />}
            </>
          )}

          {/* Solar & BESS — Dashboard | AEGIS (AEGIS gated by solar_control) */}
          {activeMainTab === "solar-bess" && (
            <>
              <div className="mb-4"><SolarIntelligenceCard siteId={siteId} /></div>
              <TabBar
                tabs={[
                  { id: "Dashboard", label: "Dashboard" },
                  ...(isModuleActive('solar_control') ? [{ id: "AEGIS", label: "AEGIS" }] : []),
                ]}
                active={solarBessSub}
                onChange={(id) => setSolarBessSub(id as SolarBessSub)}
                accentColor="var(--color-sentinel-blue)"
              />
              {solarBessSub === "Dashboard" && <SolarDashboard />}
              {solarBessSub === "AEGIS" && isModuleActive('solar_control') && <AegisConsolePage />}
            </>
          )}

          {/* Water */}
          {activeMainTab === "water" && (
            <>
              <div className="mb-4"><WaterIntelligenceCard siteId={siteId} /></div>
              <WaterPanel />
            </>
          )}

          {/* Fire — always read-only, no control toggle */}
          {activeMainTab === "fire" && (
            <>
              <div className="mb-4"><FireIntelligenceCard siteId={siteId} /></div>
              <FireSafetyPage />
            </>
          )}

          {/* Security (control features gated by security_control) */}
          {activeMainTab === "security" && (
            <>
              <div className="mb-4"><SecurityIntelligenceCard siteId={siteId} /></div>
              <SecurityDashboard />
            </>
           )}

          {/* Controls — all-device control panel (visible when any control add-on active) */}
          {activeMainTab === "controls" && (
            <ControlDashboard onError={() => {}} />
          )}

          {/* Space Optimization — only visible when space_optimization add-on is active */}
          {activeMainTab === "space" && isModuleActive('space_optimization') && (
            <SpaceOptimizationPage siteId={siteId} />
          )}

          {/* Fuel — only visible when fuel add-on is active */}
          {activeMainTab === "fuel" && isModuleActive('fuel') && (
            <FuelDashboard siteId={siteId} />
          )}

          {/* ESG & Sustainability — only visible when compliance add-on is active */}
          {activeMainTab === "esg" && isModuleActive('compliance') && (
            <SustainabilityDashboard siteId={siteId} />
          )}

          {/* Maintenance — work orders, equipment lifecycle */}
          {activeMainTab === "maintenance" && isModuleActive('maintenance') && (
            <AssetWorkflowDashboard />
          )}

          {/* Digital Twin — 3D building visualization */}
          {activeMainTab === "digital-twin" && isModuleActive('digital_twin') && (
            <div className="h-full"><DigitalTwin siteId={siteId} /></div>
          )}

          {/* Compliance — OHS, Fire, Electrical, Lift safety */}
          {activeMainTab === "compliance" && isModuleActive('compliance') && (
            <CompliancePage />
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
          onCreateWorkOrder={handleCreateWorkOrderFromPrediction}
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
              ) : selectedDevice && phaseAllows(sitePhase, "approve_reject") ? (
                <ControlPanel
                  device={selectedDevice}
                  onControl={handleEquipmentControl}
                  safetyStatus={{
                    status: selectedDevice.safety_status === "critical" ? "blocked" :
                            selectedDevice.safety_status === "warning" ? "warning" : "safe",
                    message: selectedDevice.safety_status === "critical"
                      ? `Safety interlock active — ${selectedEquipment.name} has a critical safety condition that prevents control operations.`
                      : selectedDevice.safety_status === "warning"
                      ? `Safety warning — ${selectedEquipment.name} has an active safety warning. Controls available with caution.`
                      : undefined,
                  }}
                  equipmentHealth={{
                    score: selectedEquipment.health_score,
                    status: selectedEquipment.status as "normal" | "warning" | "critical",
                  }}
                />
              ) : selectedDevice ? (
                <div
                  className="flex flex-col items-center justify-center py-12"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  <Shield className="h-10 w-10 mb-3 opacity-40" />
                  <p className="text-sm font-medium">
                    Device controls not available in {PHASE_LABELS[sitePhase]} mode
                  </p>
                  <p className="text-xs mt-1">
                    Controls are enabled in Supervised or Automatic phases.
                  </p>
                </div>
              ) : (
                <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {/* ── A. Equipment Overview Header ── */}
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
                        <div className="flex items-center gap-2 mt-0.5">
                          <span
                            className="inline-block px-2 py-0.5 rounded text-xs font-medium"
                            style={{
                              background: selectedEquipment.category === "HVAC"
                                ? "rgba(59, 130, 246, 0.15)"
                                : selectedEquipment.category === "Lighting"
                                ? "rgba(251, 191, 36, 0.15)"
                                : "var(--color-sentinel-bg-secondary)",
                              color: "var(--color-sentinel-text-secondary)",
                            }}
                          >
                            {selectedEquipment.category}
                          </span>
                          <span className="text-xs font-mono" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                            {selectedEquipment.id}
                          </span>
                        </div>
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

                  {/* ── Health Status Bar ── */}
                  <div
                    className="p-3 rounded-lg mb-4"
                    style={{
                      background: selectedEquipment.status === "critical" ? "rgba(220, 38, 38, 0.1)"
                        : selectedEquipment.status === "warning" ? "rgba(245, 158, 11, 0.1)"
                        : "rgba(16, 185, 129, 0.1)",
                      border: `1px solid ${getStatusColor(selectedEquipment.status)}30`,
                    }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        {getStatusIcon(selectedEquipment.status)}
                        <span className="text-sm font-medium capitalize" style={{ color: getStatusColor(selectedEquipment.status) }}>
                          {selectedEquipment.status === "normal" ? "Healthy" : selectedEquipment.status}
                        </span>
                      </div>
                      <span className="text-sm font-bold" style={{ color: getStatusColor(selectedEquipment.status) }}>
                        {selectedEquipment.health_score != null ? `${selectedEquipment.health_score}%` : '—'}
                      </span>
                    </div>
                    <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
                      <div className="h-full w-full origin-left rounded-full transition-transform will-change-transform" style={{ transform: `scaleX(${(selectedEquipment.health_score ?? 0) / 100})`, background: getStatusColor(selectedEquipment.status) }} />
                    </div>
                  </div>

                  {/* ── Metadata Tabs ── */}
                  <div
                    className="flex gap-1 mb-4 p-1 rounded-lg overflow-x-auto"
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
                          className="flex-1 flex items-center justify-center gap-1.5 px-2 py-2 rounded-md text-xs font-medium transition-colors whitespace-nowrap"
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

                  {/* ── Tab Content ── */}
                  {loadingMetadata ? (
                    <div className="flex items-center justify-center py-8">
                      <div
                        className="animate-spin h-6 w-6 border-2 rounded-full"
                        style={{ borderColor: "var(--color-sentinel-blue)", borderTopColor: "transparent" }}
                      />
                    </div>
                  ) : (
                    <>
                      {/* Info Tab — expanded with specs, warranty, location */}
                      {metadataTab === "info" && (
                        <div className="space-y-4">
                          <div className="grid grid-cols-2 gap-3">
                            <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                              <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Type</p>
                              <p className="font-medium text-sm capitalize" style={{ color: "var(--color-sentinel-text-primary)" }}>{selectedEquipment.type.replace(/_/g, " ")}</p>
                            </div>
                            {selectedEquipment.location && (
                              <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Location</p>
                                <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{selectedEquipment.location}</p>
                              </div>
                            )}
                            {(equipmentMetadata?.device_info?.manufacturer || equipmentMetadata?.manufacturer) && (
                              <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Manufacturer</p>
                                <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata?.device_info?.manufacturer || equipmentMetadata?.manufacturer}</p>
                              </div>
                            )}
                            {(equipmentMetadata?.device_info?.model || equipmentMetadata?.model) && (
                              <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Model</p>
                                <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata?.device_info?.model || equipmentMetadata?.model}</p>
                              </div>
                            )}
                            {equipmentMetadata?.device_info?.serial_number && (
                              <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Serial Number</p>
                                <p className="font-mono text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.device_info.serial_number}</p>
                              </div>
                            )}
                            {equipmentMetadata?.commissioning_date && (
                              <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Commissioned</p>
                                <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{equipmentMetadata.commissioning_date}</p>
                              </div>
                            )}
                          </div>

                          {/* Warranty Status */}
                          {equipmentMetadata?.warranty_expiry && (() => {
                            const expiryDate = new Date(equipmentMetadata.warranty_expiry);
                            const now = new Date();
                            const isExpired = expiryDate < now;
                            const daysUntil = Math.ceil((expiryDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
                            const isExpiringSoon = !isExpired && daysUntil <= 90;
                            return (
                              <div
                                className="p-3 rounded-lg flex items-center gap-3"
                                style={{
                                  background: isExpired ? "rgba(220, 38, 38, 0.1)" : isExpiringSoon ? "rgba(245, 158, 11, 0.1)" : "rgba(16, 185, 129, 0.1)",
                                  border: `1px solid ${isExpired ? "var(--color-sentinel-red)" : isExpiringSoon ? "var(--color-sentinel-amber)" : "var(--color-sentinel-green)"}30`,
                                }}
                              >
                                <Shield className="h-4 w-4 flex-shrink-0" style={{ color: isExpired ? "var(--color-sentinel-red)" : isExpiringSoon ? "var(--color-sentinel-amber)" : "var(--color-sentinel-green)" }} />
                                <div>
                                  <p className="text-xs font-medium" style={{ color: isExpired ? "var(--color-sentinel-red)" : isExpiringSoon ? "var(--color-sentinel-amber)" : "var(--color-sentinel-green)" }}>
                                    Warranty {isExpired ? "Expired" : isExpiringSoon ? `Expiring in ${daysUntil} days` : "Active"}
                                  </p>
                                  <p className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                                    {isExpired ? "Expired" : "Expires"}: {expiryDate.toLocaleDateString()}
                                  </p>
                                </div>
                              </div>
                            );
                          })()}

                          {/* Operating Data Summary (inline in Info tab) */}
                          {equipmentMetadata?.operating_data && Object.keys(equipmentMetadata.operating_data).length > 0 && (
                            <div>
                              <h4 className="text-xs font-medium uppercase tracking-wider mb-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                Current Readings
                              </h4>
                              <div className="grid grid-cols-3 gap-2">
                                {equipmentMetadata.operating_data.runtime_hours !== undefined && (
                                  <div className="p-2 rounded-lg text-center" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                    <p className="text-lg font-bold" style={{ color: "var(--color-sentinel-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                                      {equipmentMetadata.operating_data.runtime_hours.toLocaleString()}
                                    </p>
                                    <p className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>Runtime hrs</p>
                                  </div>
                                )}
                                {equipmentMetadata.operating_data.power_cycles !== undefined && (
                                  <div className="p-2 rounded-lg text-center" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                    <p className="text-lg font-bold" style={{ color: "var(--color-sentinel-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                                      {equipmentMetadata.operating_data.power_cycles.toLocaleString()}
                                    </p>
                                    <p className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>Power Cycles</p>
                                  </div>
                                )}
                                {equipmentMetadata.operating_data.energy_kwh !== undefined && (
                                  <div className="p-2 rounded-lg text-center" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                    <p className="text-lg font-bold" style={{ color: "var(--color-sentinel-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                                      {equipmentMetadata.operating_data.energy_kwh.toLocaleString()}
                                    </p>
                                    <p className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>kWh Total</p>
                                  </div>
                                )}
                                {equipmentMetadata.operating_data.fault_count !== undefined && (
                                  <div className="p-2 rounded-lg text-center" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                    <p className="text-lg font-bold" style={{ color: equipmentMetadata.operating_data.fault_count > 0 ? "var(--color-sentinel-amber)" : "var(--color-sentinel-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                                      {equipmentMetadata.operating_data.fault_count}
                                    </p>
                                    <p className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>Faults</p>
                                  </div>
                                )}
                                {equipmentMetadata.operating_data.lamp_hours !== undefined && (
                                  <div className="p-2 rounded-lg text-center" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                    <p className="text-lg font-bold" style={{ color: "var(--color-sentinel-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                                      {equipmentMetadata.operating_data.lamp_hours.toLocaleString()}
                                    </p>
                                    <p className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>Lamp hrs</p>
                                  </div>
                                )}
                                {equipmentMetadata.operating_data.rated_capacity && (
                                  <div className="p-2 rounded-lg text-center" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                    <p className="text-sm font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                      {equipmentMetadata.operating_data.rated_capacity}
                                    </p>
                                    <p className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>Capacity</p>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Maintenance Section */}
                          <div>
                            <h4 className="text-xs font-medium uppercase tracking-wider mb-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                              Maintenance
                            </h4>
                            <div className="grid grid-cols-2 gap-2">
                              <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Last Service</p>
                                <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                  {equipmentMetadata?.last_service
                                    ? new Date(equipmentMetadata.last_service).toLocaleDateString()
                                    : "No records"}
                                </p>
                              </div>
                              <div className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                                <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>Install Date</p>
                                <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                  {equipmentMetadata?.install_date
                                    ? new Date(equipmentMetadata.install_date).toLocaleDateString()
                                    : equipmentMetadata?.commissioning_date
                                    ? new Date(equipmentMetadata.commissioning_date).toLocaleDateString()
                                    : "Unknown"}
                                </p>
                              </div>
                            </div>
                          </div>

                          {/* Related Alerts */}
                          {(() => {
                            if (loadingEquipmentAlerts) {
                              return (
                                <div>
                                  <h4 className="text-xs font-medium uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: "var(--color-sentinel-amber)" }}>
                                    <AlertTriangle className="h-3.5 w-3.5" />
                                    Active Alerts
                                  </h4>
                                  <div className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>Loading...</div>
                                </div>
                              );
                            }
                            const eqAlerts = equipmentAlerts; // from API
                            return eqAlerts && eqAlerts.length > 0 ? (
                              <div>
                                <h4 className="text-xs font-medium uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: "var(--color-sentinel-amber)" }}>
                                  <AlertTriangle className="h-3.5 w-3.5" />
                                  Active Alerts ({eqAlerts.length})
                                </h4>
                                <div className="space-y-2">
                                  {eqAlerts.slice(0, 5).map(alert => (
                                    <div
                                      key={alert.id}
                                      className="p-2 rounded-lg flex items-start gap-2"
                                      style={{
                                        background: alert.severity === "critical" ? "rgba(220, 38, 38, 0.1)" : "rgba(245, 158, 11, 0.1)",
                                        border: `1px solid ${alert.severity === "critical" ? "var(--color-sentinel-red)" : "var(--color-sentinel-amber)"}20`,
                                      }}
                                    >
                                      <AlertCircle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" style={{ color: alert.severity === "critical" ? "var(--color-sentinel-red)" : "var(--color-sentinel-amber)" }} />
                                      <div className="flex-1 min-w-0">
                                        <div className="flex items-start justify-between gap-2">
                                          <p className="text-xs font-medium truncate" style={{ color: "var(--color-sentinel-text-primary)" }}>{alert.type_label}</p>
                                          {alert.severity && (
                                            <span
                                              className="flex-shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded"
                                              style={{
                                                background: alert.severity === "critical" ? "rgba(220, 38, 38, 0.2)" : "rgba(245, 158, 11, 0.2)",
                                                color: alert.severity === "critical" ? "var(--color-sentinel-red)" : "var(--color-sentinel-amber)",
                                              }}
                                            >
                                              {alert.severity}
                                            </span>
                                          )}
                                        </div>
                                        <p className="text-xs mt-0.5" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                                          {alert.event_at ? new Date(alert.event_at).toLocaleString() : new Date(alert.created_at).toLocaleString()}
                                        </p>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ) : null;
                          })()}

                          {/* Related Predictions */}
                          {(() => {
                            const eqPredictions = predictions.filter(p => p.equipment_id === selectedEquipment.id);
                            return eqPredictions.length > 0 ? (
                              <div>
                                <h4 className="text-xs font-medium uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: "var(--color-sentinel-blue)" }}>
                                  <TrendingUp className="h-3.5 w-3.5" />
                                  Predictions ({eqPredictions.length})
                                </h4>
                                <div className="space-y-2">
                                  {eqPredictions.slice(0, 3).map(pred => (
                                    <div
                                      key={pred.id}
                                      className="p-2 rounded-lg flex items-start gap-2"
                                      style={{
                                        background: "rgba(59, 130, 246, 0.1)",
                                        border: "1px solid rgba(59, 130, 246, 0.2)",
                                      }}
                                    >
                                      <TrendingUp className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" style={{ color: "var(--color-sentinel-blue)" }} />
                                      <div>
                                        <p className="text-xs font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{pred.prediction_type.replace(/_/g, " ")}</p>
                                        <p className="text-xs mt-0.5" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                                          {pred.probability_percent}% probability
                                          {pred.predicted_failure_date && ` — ${new Date(pred.predicted_failure_date).toLocaleDateString()}`}
                                        </p>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ) : null;
                          })()}

                          {/* Actions */}
                          <div className="flex gap-2 pt-2">
                            {isModuleActive('maintenance') && (
                              <button
                                className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors hover:brightness-110"
                                style={{
                                  background: "var(--color-sentinel-amber)",
                                  color: "white",
                                }}
                                onClick={() => {
                                  window.open(`/work-orders?equipment=${selectedEquipment.id}`, '_blank');
                                }}
                              >
                                <ClipboardList className="h-4 w-4" />
                                Create Work Order
                              </button>
                            )}
                          </div>
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

                  {/* Mark as Replaced */}
                  <div className="mt-4 pt-4 border-t" style={{ borderColor: "var(--color-sentinel-border)" }}>
                    <button
                      onClick={async () => {
                        const date = window.prompt("Enter replacement date (YYYY-MM-DD):");
                        if (!date) return;
                        const notes = window.prompt("Replacement notes (optional):");
                        try {
                          const resp = await fetch(
                            `/api/equipment/${selectedEquipment.id}/mark-replaced`,
                            {
                              method: "PATCH",
                              headers: { "Content-Type": "application/json" },
                              body: JSON.stringify({ replaced_on: date, replacement_notes: notes || "" }),
                            }
                          );
                          if (resp.ok) {
                            alert("Equipment marked as replaced. Baseline will be recalculated.");
                          } else {
                            const err = await resp.json();
                            alert(`Failed: ${err.detail || "unknown error"}`);
                          }
                        } catch (e) {
                          alert(`Error: ${e}`);
                        }
                      }}
                      className="text-xs px-3 py-1.5 rounded transition-colors cursor-pointer"
                      style={{
                        background: "rgba(245, 158, 11, 0.15)",
                        color: "var(--color-sentinel-amber)",
                        border: "1px solid rgba(245, 158, 11, 0.3)",
                      }}
                    >
                      Mark as Replaced
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <ChatWidget siteId={siteId} />
    </div>
  );
}

export default SiteDetail;

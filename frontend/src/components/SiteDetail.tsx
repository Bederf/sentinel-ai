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

import { useState, useEffect } from "react";
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
} from "lucide-react";
import api from "../lib/api";
import type { Alert, Prediction, EnergyDataPoint, Device, BuildingEquipmentItem, CategoryStatus } from "../lib/api";
import { formatDateTime, getTimezoneAbbreviation, isDifferentTimezone } from "../lib/timeFormat";
import { KPICard } from "./KPICard";
import { EnergyChart } from "./EnergyChart";
import { PredictionCard } from "./PredictionCard";
import { PredictionDetail } from "./PredictionDetail";
import { OptimizationInfoCard } from "./OptimizationInfoCard";
import { ControlPanel } from "./ControlPanel";
import { useHealthThresholds } from "../hooks/useHealthThresholds";

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

  // Equipment control
  const [selectedEquipment, setSelectedEquipment] = useState<Equipment | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [showEquipmentControl, setShowEquipmentControl] = useState(false);
  const [loadingDevice, setLoadingDevice] = useState(false);

  // Prediction detail modal
  const [selectedPrediction, setSelectedPrediction] = useState<Prediction | null>(null);
  const [isPredictionDetailOpen, setIsPredictionDetailOpen] = useState(false);

  // Health thresholds
  const { thresholds } = useHealthThresholds();

  useEffect(() => {
    const loadSiteData = async () => {
      try {
        setLoading(true);

        // Fetch site details using API client
        const siteData = await api.getSite(siteId);
        // Map the response to SiteDetailData format
        setSite({
          ...siteData,
          address: siteData.address || siteData.location || "",
          location: siteData.location,
        } as SiteDetailData);

        // Determine building_id from site_id (mapping sites.json to building folders)
        // site-002 -> sandton
        const SITE_TO_BUILDING: Record<string, string> = {
          "site-002": "sandton",
        };
        const buildingId = SITE_TO_BUILDING[siteId] || siteId;

        // Fetch equipment for this building using new building equipment endpoint
        try {
          const buildingEquipment = await api.getBuildingEquipment(buildingId);
          // Map to Equipment interface (add health_score alias)
          const mappedEquipment: Equipment[] = buildingEquipment.equipment.map((eq) => ({
            ...eq,
            health_score: eq.health,
          }));
          setEquipment(mappedEquipment);
          setEquipmentCategories(buildingEquipment.categories);
        } catch (eqErr) {
          console.warn("Building equipment endpoint failed, falling back to legacy:", eqErr);
          // Fallback to legacy equipment endpoint
          const equipmentData = await api.getEquipment(siteId);
          setEquipment(equipmentData.map((eq) => ({
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

      // Try to fetch equipment controls from Supabase
      try {
        const deviceData = await api.getEquipmentControls(equip.id);
        setSelectedDevice(deviceData);
      } catch (deviceErr) {
        console.warn("Could not load equipment controls:", deviceErr);
        // Still show the modal with basic info, just no controls
        setSelectedDevice(null);
      }
    } catch (error) {
      console.error("Failed to load equipment details:", error);
    } finally {
      setLoadingDevice(false);
    }
  };

  const handleEquipmentControl = async (deviceId: string, point: string, value: number | boolean) => {
    try {
      // Use equipment control endpoint for Supabase equipment
      await api.controlEquipment(deviceId, point, value);
      // Refresh equipment list after control action
      const SITE_TO_BUILDING: Record<string, string> = { "site-002": "sandton" };
      const buildingId = SITE_TO_BUILDING[siteId] || siteId;
      try {
        const buildingEquipment = await api.getBuildingEquipment(buildingId);
        setEquipment(buildingEquipment.equipment.map((eq) => ({
          ...eq,
          health_score: eq.health,
        })));
        setEquipmentCategories(buildingEquipment.categories);
      } catch {
        // Fallback
        const equipmentData = await api.getEquipment(siteId);
        setEquipment(equipmentData.map((eq) => ({
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
  const healthyEquipment = equipment.filter((e) => e.status === "normal" || e.status === "online").length;
  const warningEquipment = equipment.filter((e) => e.status === "warning").length;
  const criticalEquipment = equipment.filter((e) => e.status === "critical" || e.status === "offline" || e.status === "maintenance").length;
  const avgHealth = equipment.length > 0
    ? Math.round(equipment.reduce((sum, e) => sum + e.health_score, 0) / equipment.length)
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
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
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
      <OptimizationInfoCard
        siteId={siteId}
        optimizationEnabled={site.optimization_enabled || false}
      />

      {/* KPI Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KPICard
          title="Equipment"
          value={site.equipment_count}
          icon={<Cpu className="h-5 w-5" />}
          accentColor="blue"
        />
        <KPICard
          title="Active Alerts"
          value={alerts.length}
          icon={<AlertTriangle className="h-5 w-5" />}
          accentColor="orange"
        />
        <KPICard
          title="Avg Health"
          value={`${avgHealth}%`}
          icon={<TrendingUp className="h-5 w-5" />}
          accentColor={avgHealth >= thresholds.healthy ? "green" : avgHealth >= thresholds.warning ? "orange" : "red"}
        />
        <KPICard
          title="Predictions"
          value={predictions.length}
          icon={<TrendingUp className="h-5 w-5" />}
          accentColor="purple"
        />
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

      {/* Tabs */}
      <div
        className="rounded-md overflow-hidden mb-6"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        {/* Tab Navigation */}
        <div
          className="flex border-b"
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
                className="flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors relative"
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
                  <h3
                    className="text-lg font-semibold"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    Equipment
                  </h3>
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
                      const criticalItems = equipment.filter((e) => e.status === "critical" || e.status === "offline" || e.status === "maintenance");
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

              {/* Category Filter Chips */}
              {Object.keys(equipmentCategories).length > 0 && (
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

              {(() => {
                const filteredEquipment = selectedCategory
                  ? equipment.filter((eq) => eq.category === selectedCategory)
                  : equipment;

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
                            onClick={() => item.controllable ? handleEquipmentClick(item) : null}
                          >
                            <td className="py-3 px-4">
                              <div className="flex items-center gap-3">
                                {getStatusIcon(item.status)}
                                <div>
                                  <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                    {item.name}
                                  </p>
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
                <div
                  className="text-center py-12"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  <Cpu className="h-12 w-12 mx-auto mb-4" style={{ color: "var(--color-sentinel-text-disabled)" }} />
                  <p className="text-lg font-medium mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {selectedEquipment.name}
                  </p>
                  <p className="text-sm mb-4">
                    Health: {selectedEquipment.health_score}% • Status: {selectedEquipment.status}
                  </p>
                  <p className="text-xs">
                    No control points available for this equipment.
                  </p>
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

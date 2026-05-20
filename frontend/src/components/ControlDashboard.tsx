

/**
 * Control Dashboard Component - Building Management Control Center
 *
 * Features:
 * - Two-column layout: Device list (left), Control panel + Recent actions (right)
 * - Real-time device status updates
 * - Safety validation indicators
 * - Inline audit trail showing recent control actions
 * - Grafana-style design consistency
 *
 * Integration with:
 * - Device abstraction service (backend)
 * - Safety interlock validation
 * - Audit logger (via RecentActions component)
 * - Existing dashboard theme
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  Cpu,
  Activity,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  Clock,
  ChevronDown,
  ChevronUp,
  Shield,
  X,
  Bell,
} from "lucide-react";
import api from '@/lib/api';
import type { Device, Site, Prediction } from '@/lib/api';
import { safetyBatcher } from '@/lib/api/batchers';
import { DeviceList } from "./DeviceList";
import { ControlPanel } from "./ControlPanel";
import { PageLoading } from "./PageLoading";
import { RecentActions } from "./RecentActions";
import { PredictionDetail } from "./PredictionDetail";
import { BuildingSelector } from "./BuildingSelector";
import { authorizedFetch } from '@/lib/api/client';

interface ControlDashboardProps {
  onError?: (error: string) => void;
  siteId?: string;
}

interface AlertContext {
  message: string;
  severity: string;
  equipment_name: string;
  created_at: string;
  title?: string;
  type?: string;
}

const _SAFETY_STATUS_BATCH_SIZE = 2;
const _SAFETY_STATUS_BATCH_DELAY_MS = 1000;
const SAFETY_STATUS_MAX_PER_SITE = 6;

function mapSafetyStatusToDeviceStatus(
  status: "safe" | "warning" | "blocked" | "alarm" | "unknown"
): "safe" | "warning" | "critical" | "unknown" {
  if (status === "safe") return "safe";
  if (status === "warning") return "warning";
  if (status === "blocked" || status === "alarm") return "critical";
  return "unknown";
}

export function ControlDashboard({ onError, siteId: propSiteId }: ControlDashboardProps) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(propSiteId || null);
  const [bridgeTelemetry, setBridgeTelemetry] = useState<{
    status: "live" | "unavailable";
    zones_with_readings?: number;
    zone_count?: number;
    power?: { hvac_kw?: number; lighting_kw?: number; total_kw?: number };
  } | null>(null);
  const [sentinelGuidance, setSentinelGuidance] = useState<string | null>(null);
  const [sentinelPosture, setSentinelPosture] = useState<string | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [selectedPrediction, setSelectedPrediction] = useState<Prediction | null>(null);
  const [isPredictionDetailOpen, setIsPredictionDetailOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshDevices, setRefreshDevices] = useState(0);
  const [recentActionsExpanded, setRecentActionsExpanded] = useState(true);
  const [auditRefreshTrigger, setAuditRefreshTrigger] = useState(0);
  const [pendingEquipmentSelection, setPendingEquipmentSelection] = useState<string | null>(null);
  const [alertContext, setAlertContext] = useState<AlertContext | null>(null);
  const safetyLoadedDeviceIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (propSiteId) {
      setSelectedSiteId(propSiteId);
    }
  }, [propSiteId]);

  // Check for pre-selected equipment from Dashboard/Alert navigation
  useEffect(() => {
    const storedEquipmentId = sessionStorage.getItem("sentinel_selected_equipment");
    const storedSiteId = sessionStorage.getItem("sentinel_selected_site");
    const storedAlertContext = sessionStorage.getItem("sentinel_alert_context");

    if (storedEquipmentId && storedSiteId) {
      // Use the stored site ID for device matching
      setSelectedSiteId(storedSiteId);
      setPendingEquipmentSelection(storedEquipmentId);

      // Load alert context if available
      if (storedAlertContext) {
        try {
          setAlertContext(JSON.parse(storedAlertContext));
        } catch (e) {
          console.error("Failed to parse alert context:", e);
        }
        sessionStorage.removeItem("sentinel_alert_context");
      }

      // Clear from storage
      sessionStorage.removeItem("sentinel_selected_equipment");
      sessionStorage.removeItem("sentinel_selected_site");
    }
  }, []);

  // Filter sites to only show buildings with devices, then sort alphabetically
  const filteredSortedSites = useMemo(() => {
    // Get unique site_ids from devices
    const siteIdsWithDevices = new Set(devices.map(device => device.site_id));

    // Filter sites to only include those with devices
    const sitesWithDevices = sites.filter(site => siteIdsWithDevices.has(site.id));

    // Sort alphabetically by name
    return sitesWithDevices.sort((a, b) => a.name.localeCompare(b.name));
  }, [sites, devices]);

  // Filter devices by selected site
  const filteredDevices = useMemo(() => {
    if (!selectedSiteId) return devices;
    const filtered = devices.filter((d) => d.site_id === selectedSiteId);

    // If no devices for selected site, clear selection
    if (filtered.length === 0 && selectedSiteId) {
      const siteIdsWithDevices = new Set(devices.map(device => device.site_id));
      if (!siteIdsWithDevices.has(selectedSiteId)) {
        // Site has no devices, reset selection
        const sitesWithDevices = sites.filter(site => siteIdsWithDevices.has(site.id));
        if (sitesWithDevices.length > 0) {
          const sortedSitesWithDevices = sitesWithDevices.sort((a, b) => a.name.localeCompare(b.name));
          const preferredSite =
            sortedSitesWithDevices.find((site) => site.id === "site-002")
            ?? sortedSitesWithDevices.find((site) => /sandton city office tower/i.test(site.name))
            ?? sortedSitesWithDevices[0];
          setSelectedSiteId(preferredSite?.id || null);
        } else {
          setSelectedSiteId(null);
        }
      }
    }

    return filtered;
  }, [devices, selectedSiteId, sites]);


  // Load devices and sites on mount
  useEffect(() => {
    const loadDevices = async () => {
      try {
        setIsLoading(true);

        // Add delay to prevent concurrent requests hitting rate limiter on initial load
        // TODO: Remove once backend rate-limit is fixed (see P2 #11)
        await new Promise((resolve) => setTimeout(resolve, 800));
        // Fetch core data first, then predictions to reduce request burst on mount
        // Use equipment endpoint (Supabase) instead of device abstraction (empty in island mode)
        const devicesData = await api.getEquipmentDevices();
        // Stagger subsequent requests by 250ms to avoid 429 rate limiting
        await new Promise((resolve) => setTimeout(resolve, 250));
        const sitesData = await api.getSites();
        const predictionsData = await api.getPredictions().catch(() => ({ predictions: [] }));

        setSites(sitesData);
        setPredictions(predictionsData.predictions || []);

        // Set devices with unknown safety first; safety statuses are lazily loaded per active site
        const devicesWithUnknownSafety: Device[] = devicesData.map((device) => ({
          ...device,
          safety_status: device.safety_status ?? "unknown",
        }));
        safetyLoadedDeviceIdsRef.current = new Set();
        setDevices(devicesWithUnknownSafety);

        // Set default selected site to first with devices (after devices are set)
        if (sitesData.length > 0 && devicesWithUnknownSafety.length > 0 && !selectedSiteId) {
          const siteIdsWithDevices = new Set(devicesWithUnknownSafety.map(device => device.site_id));
          const sitesWithDevices = sitesData.filter(site => siteIdsWithDevices.has(site.id));
          if (sitesWithDevices.length > 0) {
            const sortedSitesWithDevices = sitesWithDevices.sort((a, b) => a.name.localeCompare(b.name));
            const preferredSite =
              sortedSitesWithDevices.find((site) => site.id === "site-002")
              ?? sortedSitesWithDevices.find((site) => /sandton city office tower/i.test(site.name))
              ?? sortedSitesWithDevices[0];
            setSelectedSiteId(preferredSite.id);
          }
        }
      } catch (error) {
        console.error("Failed to load devices:", error);
        onError?.("Failed to load control devices");
      } finally {
        setIsLoading(false);
      }
    };

    loadDevices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshDevices]);

  useEffect(() => {
    if (!selectedSiteId) return;
    const siteIdForTelemetry = selectedSiteId;
    let mounted = true;
    async function loadTelemetrySummary() {
      try {
        const [rawTelemetryResp, stateResp] = await Promise.all([
          authorizedFetch(`/api/sites/${encodeURIComponent(siteIdForTelemetry)}/telemetry`).catch(() => null),
          authorizedFetch(`/api/building-state/${encodeURIComponent(siteIdForTelemetry)}`).catch(() => null),
        ]);
        if (!mounted) return;
        if (rawTelemetryResp && rawTelemetryResp.ok) {
          const raw = await rawTelemetryResp.json();
          setBridgeTelemetry({
            status: "live",
            zones_with_readings: raw?.zones_with_readings ?? 0,
            zone_count: raw?.zone_count ?? 0,
            power: raw?.power ?? {},
          });
        } else {
          setBridgeTelemetry({ status: "unavailable" });
        }
        if (stateResp && stateResp.ok) {
          const state = await stateResp.json();
          setSentinelGuidance(state?.payload?.operator_guidance?.headline || null);
          setSentinelPosture(state?.payload?.building_posture || null);
        } else {
          setSentinelGuidance(null);
          setSentinelPosture(null);
        }
      } catch {
        if (mounted) {
          setBridgeTelemetry({ status: "unavailable" });
          setSentinelGuidance(null);
          setSentinelPosture(null);
        }
      }
    }
    loadTelemetrySummary();
    return () => {
      mounted = false;
    };
  }, [selectedSiteId]);

  // Lazily fetch safety statuses only for the currently selected site
  useEffect(() => {
    if (!selectedSiteId || filteredDevices.length === 0) return;

    let isCancelled = false;
    const loadSiteSafetyStatuses = async () => {
      const prioritizedDevices = [...filteredDevices].sort((a, b) => {
        if (selectedDevice && a.id === selectedDevice.id) return -1;
        if (selectedDevice && b.id === selectedDevice.id) return 1;
        return 0;
      });

      const devicesToLoad = prioritizedDevices
        .filter((device) => !safetyLoadedDeviceIdsRef.current.has(device.id))
        .slice(0, SAFETY_STATUS_MAX_PER_SITE);

      // Use batch aggregator to collect requests over 50ms window instead of individual calls
      const updates = await Promise.all(
        devicesToLoad.map(async (device) => {
          try {
            const safetyStatus = await safetyBatcher(device.id);
            return { id: device.id, safety_status: mapSafetyStatusToDeviceStatus(safetyStatus.status as any) };
          } catch (error: any) {
            console.warn(`Failed to fetch safety status for device ${device.id}:`, error);
            return { id: device.id, safety_status: "unknown" as const };
          } finally {
            safetyLoadedDeviceIdsRef.current.add(device.id);
          }
        })
      );

      if (isCancelled) return;
      const statusById = new Map(updates.map((update) => [update.id, update.safety_status]));
      setDevices((prevDevices) =>
        prevDevices.map((device) =>
          statusById.has(device.id)
            ? { ...device, safety_status: statusById.get(device.id) ?? device.safety_status }
            : device
        )
      );
    };

    loadSiteSafetyStatuses();
    return () => {
      isCancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredDevices, selectedDevice?.id, selectedSiteId]);

  // Auto-select first device when site changes or devices load
  // Also handle pending equipment selection from Dashboard navigation
  useEffect(() => {
    if (filteredDevices.length > 0) {
      // Check if there's a pending equipment selection from navigation
      if (pendingEquipmentSelection) {
        // Try to find the device by ID (equipment ID format may differ)
        const pendingDevice = filteredDevices.find(
          (d) =>
            d.id === pendingEquipmentSelection ||
            d.id.includes(pendingEquipmentSelection) ||
            pendingEquipmentSelection.includes(d.id)
        );

        if (pendingDevice) {
          setSelectedDevice(pendingDevice);
          setPendingEquipmentSelection(null);
          return;
        }
        // If not found in current filter, clear pending selection
        setPendingEquipmentSelection(null);
      }

      // Check if currently selected device is in the filtered list
      const currentDeviceInList = selectedDevice && filteredDevices.some((d) => d.id === selectedDevice.id);
      if (!currentDeviceInList) {
        setSelectedDevice(filteredDevices[0]);
      }
    } else {
      setSelectedDevice(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredDevices, selectedSiteId, pendingEquipmentSelection]);

  const handleDeviceSelect = useCallback(async (device: Device) => {
    try {
      setSelectedDevice(device);
      // Fetch full equipment details including control points via equipment endpoint
      const refreshedDevice = await api.getEquipmentDevice(device.id);
      try {
        const safetyStatus = await api.getDeviceSafetyStatus(device.id);
        safetyLoadedDeviceIdsRef.current.add(device.id);
        const mappedStatus = mapSafetyStatusToDeviceStatus(safetyStatus.overall_status);
        setDevices((prevDevices) =>
          prevDevices.map((d) =>
            d.id === device.id ? { ...d, safety_status: mappedStatus } : d
          )
        );
        setSelectedDevice({ ...refreshedDevice, safety_status: mappedStatus });
      } catch {
        setSelectedDevice(refreshedDevice);
      }
    } catch (error) {
      console.error("Failed to refresh device:", error);
      // Keep the device selected even if refresh fails
    }
  }, []);

  const handleControlAction = useCallback(async (deviceId: string, point: string, value: number | boolean) => {
    try {
      // Use equipment control endpoint for devices from Supabase
      await api.controlEquipment(deviceId, point, value);

      // Only refresh audit trail - don't reload all devices (causes jarring page reload)
      // The ControlPanel handles optimistic updates locally
      setAuditRefreshTrigger((prev) => prev + 1);

      // Selectively update the specific device's point value in state
      // This avoids a full page reload while keeping data in sync
      setDevices((prevDevices) =>
        prevDevices.map((device) => {
          if (device.id !== deviceId) return device;
          // Update the point value in the device's points
          const updatedPoints = { ...device.points };
          if (updatedPoints[point]) {
            updatedPoints[point] = {
              ...updatedPoints[point],
              current_value: value,
            };
          }
          return { ...device, points: updatedPoints };
        })
      );

      // Also update selectedDevice if it's the one being controlled
      setSelectedDevice((prevSelected) => {
        if (!prevSelected || prevSelected.id !== deviceId) return prevSelected;
        const updatedPoints = { ...prevSelected.points };
        if (updatedPoints[point]) {
          updatedPoints[point] = {
            ...updatedPoints[point],
            current_value: value,
          };
        }
        return { ...prevSelected, points: updatedPoints };
      });
    } catch (error) {
      console.error("Control action failed:", error);
      throw error;
    }
  }, []);

  // Handle click on risk/warning icon to open prediction detail
  const handleRiskClick = useCallback((device: Device) => {
    // Find prediction for this device by matching equipment_id to device.id
    const prediction = predictions.find(
      (p) => p.equipment_id === device.id || p.equipment_name === device.name
    );
    if (prediction) {
      setSelectedPrediction(prediction);
      setIsPredictionDetailOpen(true);
    }
  }, [predictions]);

  if (isLoading) {
    return (
      <PageLoading message="Loading control dashboard..." />
    );
  }

  return (
    <div
      className="h-full overflow-hidden flex flex-col"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Page Header — matches Lighting tab pattern */}
      <div className="flex-none px-4 md:px-6 pt-4 md:pt-6 pb-2">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: "rgba(16, 185, 129, 0.15)" }}>
            <Cpu className="h-6 w-6" style={{ color: "var(--color-sentinel-green)" }} />
          </div>
          <div>
            <h1 className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Device Control
            </h1>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Building Management Control Centre
            </p>
          </div>
        </div>
      </div>

      <div className="flex-none px-4 md:px-6 pb-3">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Raw Bridge Telemetry
              </h2>
              <span className="text-xs px-2 py-1 rounded" style={{ background: bridgeTelemetry?.status === "live" ? "rgba(16,185,129,0.15)" : "rgba(245,158,11,0.15)", color: bridgeTelemetry?.status === "live" ? "var(--color-sentinel-green)" : "var(--color-sentinel-amber)" }}>
                {bridgeTelemetry?.status === "live" ? "Live" : "Unavailable"}
              </span>
            </div>
            <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Zones: {bridgeTelemetry?.zones_with_readings ?? 0}/{bridgeTelemetry?.zone_count ?? 0}
            </p>
          </div>
          <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <h2 className="text-sm font-semibold mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
              SENTINEL Controls Interpretation
            </h2>
            <p className="text-xs capitalize" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Posture: <span style={{ color: "var(--color-sentinel-text-primary)" }}>{sentinelPosture || "unknown"}</span>
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {sentinelGuidance || "No active guidance yet."}
            </p>
          </div>
        </div>
      </div>

      {/* Alert Context Banner - shown when navigating from an alert */}
      {alertContext && (
        <div
          className="flex-none px-4 py-3 flex items-start gap-3 border-b"
          style={{
            background: alertContext.severity === "critical"
              ? "rgba(220, 38, 38, 0.15)"
              : alertContext.severity === "high"
                ? "rgba(245, 158, 11, 0.15)"
                : "rgba(59, 130, 246, 0.15)",
            borderColor: alertContext.severity === "critical"
              ? "rgba(220, 38, 38, 0.3)"
              : alertContext.severity === "high"
                ? "rgba(245, 158, 11, 0.3)"
                : "rgba(59, 130, 246, 0.3)",
          }}
        >
          <div
            className="flex-none p-2 rounded"
            style={{
              background: alertContext.severity === "critical"
                ? "rgba(220, 38, 38, 0.2)"
                : alertContext.severity === "high"
                  ? "rgba(245, 158, 11, 0.2)"
                  : "rgba(59, 130, 246, 0.2)",
            }}
          >
            <Bell
              className="h-5 w-5"
              style={{
                color: alertContext.severity === "critical"
                  ? "var(--color-sentinel-red)"
                  : alertContext.severity === "high"
                    ? "var(--color-sentinel-orange)"
                    : "var(--color-sentinel-blue)",
              }}
            />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span
                className="text-xs font-medium px-2 py-0.5 rounded uppercase"
                style={{
                  background: alertContext.severity === "critical"
                    ? "rgba(220, 38, 38, 0.3)"
                    : alertContext.severity === "high"
                      ? "rgba(245, 158, 11, 0.3)"
                      : "rgba(59, 130, 246, 0.3)",
                  color: alertContext.severity === "critical"
                    ? "var(--color-sentinel-red)"
                    : alertContext.severity === "high"
                      ? "var(--color-sentinel-orange)"
                      : "var(--color-sentinel-blue)",
                }}
              >
                {alertContext.severity} Alert
              </span>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {alertContext.equipment_name}
              </span>
            </div>
            <p
              className="text-sm"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {alertContext.message}
            </p>
            {alertContext.created_at && (
              <p
                className="text-xs mt-1"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                {new Date(alertContext.created_at).toLocaleString()}
              </p>
            )}
          </div>
          <button
            onClick={() => setAlertContext(null)}
            className="flex-none p-1 rounded hover:brightness-125 transition-colors"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
            aria-label="Dismiss alert context"
          >
            <X
              className="h-4 w-4"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            />
          </button>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 overflow-hidden flex">
      {/* Left Column: Device List */}
      {/* TODO: Remove once backend rate-limit is fixed (see P2 #11) */}
      <div className="flex-none flex flex-col border-r shrink-0" style={{ width: "min(288px, 28vw)", minWidth: "200px", borderColor: "var(--color-sentinel-border)" }}>
        {/* Site Selector Dropdown */}
        <div
          className="flex-none p-3 border-b"
          style={{ borderColor: "var(--color-sentinel-border)" }}
        >
          <BuildingSelector
            value={selectedSiteId || ""}
            onChange={setSelectedSiteId}
            sites={filteredSortedSites}
            disabled={filteredSortedSites.length === 0}
          />
        </div>

        {/* Device List Header */}
        <div
          className="flex-none p-4 border-b flex items-center justify-between"
          style={{ borderColor: "var(--color-sentinel-border)" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{ background: "rgba(59, 130, 246, 0.15)" }}
            >
              <Cpu className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
            </div>
            <div>
              <h3
                className="font-medium text-sm"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Control Devices
              </h3>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {filteredDevices.filter((d) => d.status === "online").length} online, {filteredDevices.filter((d) => d.status === "offline").length} offline
              </span>
            </div>
          </div>
          <button
            onClick={() => setRefreshDevices((prev) => prev + 1)}
            className="p-1 rounded transition-colors"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
            title="Refresh devices"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <DeviceList
            devices={filteredDevices}
            selectedDevice={selectedDevice}
            onDeviceSelect={handleDeviceSelect}
            onRiskClick={handleRiskClick}
            sites={sites}
          />
        </div>
      </div>

      {/* Center Column: Control Panel + Recent Actions */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Control Panel Header */}
        <div
          className="flex-none p-4 border-b flex items-center justify-between"
          style={{ borderColor: "var(--color-sentinel-border)" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{ background: "rgba(245, 158, 11, 0.15)" }}
            >
              <Activity className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
            </div>
            <div>
              <h3
                className="font-medium text-sm"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Control Panel
              </h3>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {selectedDevice ? selectedDevice.name : "Select a device"}
              </span>
            </div>
          </div>
          {selectedDevice && (
            <div className="flex items-center gap-2">
              {selectedDevice.safety_status === "warning" || selectedDevice.safety_status === "critical" ? (
                <button
                  onClick={() => handleRiskClick(selectedDevice)}
                  className={`px-2 py-1 rounded text-xs font-medium cursor-pointer hover:opacity-80 transition-opacity ${
                    selectedDevice.safety_status === "warning"
                      ? "bg-yellow-500/10 text-yellow-500"
                      : "bg-red-500/10 text-red-500"
                  }`}
                  title="View risk intelligence"
                >
                  {selectedDevice.safety_status === "warning" ? (
                    <AlertTriangle className="h-3 w-3 inline mr-1" />
                  ) : (
                    <XCircle className="h-3 w-3 inline mr-1" />
                  )}
                  {selectedDevice.safety_status.toUpperCase()}
                </button>
              ) : (
                <div
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    selectedDevice.safety_status === "safe"
                      ? "bg-green-500/10 text-green-500"
                      : "bg-gray-500/10 text-gray-500"
                  }`}
                >
                  {selectedDevice.safety_status === "safe" ? (
                    <CheckCircle className="h-3 w-3 inline mr-1" />
                  ) : (
                    <Shield className="h-3 w-3 inline mr-1" />
                  )}
                  {(selectedDevice.safety_status || "unknown").toUpperCase()}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Control Panel Content */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {selectedDevice && (
            <ControlPanel
              device={selectedDevice}
              onControl={handleControlAction}
              safetyStatus={{
                status: (selectedDevice.safety_status === "critical" ? "blocked" : selectedDevice.safety_status || "safe") as "safe" | "warning" | "blocked",
              }}
            />
          )}
        </div>

        {/* Recent Actions Section (Collapsible) */}
        <div
          className="flex-none border-t"
          style={{
            borderColor: "var(--color-sentinel-border)",
            background: "var(--color-sentinel-bg-primary)",
          }}
        >
          {/* Collapsible Header */}
          <button
            onClick={() => setRecentActionsExpanded(!recentActionsExpanded)}
            className="w-full p-3 flex items-center justify-between hover:bg-opacity-80 transition-colors"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <div className="flex items-center gap-2">
              <div
                className="p-1.5 rounded"
                style={{ background: "rgba(59, 130, 246, 0.15)" }}
              >
                <Clock className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
              </div>
              <span
                className="font-medium text-sm"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Recent Actions
              </span>
              {selectedDevice && (
                <span
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  ({selectedDevice.name})
                </span>
              )}
            </div>
            {recentActionsExpanded ? (
              <ChevronDown
                className="h-4 w-4"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              />
            ) : (
              <ChevronUp
                className="h-4 w-4"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              />
            )}
          </button>

          {/* Collapsible Content */}
          {recentActionsExpanded && (
            <div
              className="max-h-64 overflow-y-auto"
              style={{ background: "var(--color-sentinel-bg-primary)" }}
            >
              <RecentActions
                deviceId={selectedDevice?.id}
                limit={5}
                autoRefresh={true}
                refreshInterval={5000}
                refreshTrigger={auditRefreshTrigger}
              />
            </div>
          )}
        </div>
      </div>
      </div>

      {/* Risk Intelligence Detail Modal */}
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
    </div>
  );
}

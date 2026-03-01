/**
 * SecurityDashboard Component - Security monitoring page
 *
 * Features:
 * - Section 1: Status Overview (4 KPI cards: Doors, Cameras, Alarms, Occupancy)
 * - Section 2: Access Events (AccessEventsPanel with badge event table)
 * - Section 3: Camera & Alarm Status (2-column grid)
 * - Section 4: Occupancy (SecurityOccupancyPanel with cross-module recommendations)
 * - Auto-refresh status every 15 seconds
 * - Responsive layout (1 col mobile, 2 col tablet, full layout desktop)
 * - Follows SENTINEL dark theme design
 */

import { useState, useEffect, useCallback } from "react";
import {
  Shield,
  DoorClosed,
  Camera,
  Bell,
  Users,
  RefreshCw,
  AlertTriangle,
  ShieldCheck,
  ShieldAlert,
  Video,
  VideoOff,
  Lock,
  Unlock,
} from "lucide-react";
import api, { isExpectedApiError, securityApi } from '@/lib/api';
import type {
  SecuritySystemStatus,
  SecurityCamera,
  SecurityAlarmZone,
  Site,
} from '@/lib/api';
import { AccessEventsPanel } from "./AccessEventsPanel";
import { SecurityOccupancyPanel } from "./SecurityOccupancyPanel";
import { SecurityAnomaliesPanel } from "./SecurityAnomaliesPanel";
import { PageLoading } from "./PageLoading";
import { BuildingSelector } from "./BuildingSelector";

export function SecurityDashboard() {
  const [status, setStatus] = useState<SecuritySystemStatus | null>(null);
  const [cameras, setCameras] = useState<SecurityCamera[]>([]);
  const [alarmZones, setAlarmZones] = useState<SecurityAlarmZone[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const fetchData = useCallback(async (showRefreshing = false) => {
    try {
      if (showRefreshing) setIsRefreshing(true);

      const statusResult = await securityApi.getStatus(selectedSiteId);
      // Stagger subsequent requests by 250ms to avoid 429 rate limiting
      await new Promise((resolve) => setTimeout(resolve, 250));
      const camerasResult = await securityApi.getCameras(selectedSiteId);
      await new Promise((resolve) => setTimeout(resolve, 250));
      const alarmsResult = await securityApi.getAlarmZones(selectedSiteId);

      setStatus(statusResult);
      setCameras(camerasResult.cameras);
      setAlarmZones(alarmsResult.alarm_zones);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      if (!isExpectedApiError(err)) {
        console.error("Failed to fetch security data:", err);
      }
      setError("Failed to load security data. Check that the backend is running.");
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, [selectedSiteId]);

  // Fetch sites on mount
  useEffect(() => {
    const loadSites = async () => {
      try {
        const sitesData = await api.getSites();
        setSites(sitesData.sort((a, b) => a.name.localeCompare(b.name)));
        // Default to site-002 (Sandton City) if available, otherwise first site
        const defaultSite = sitesData[0];
        if (defaultSite) {
          setSelectedSiteId(defaultSite.id);
        }
      } catch (err) {
        if (!isExpectedApiError(err)) {
          console.error("Failed to load sites:", err);
        }
      }
    };
    loadSites();
  }, []);

  // Fetch security data on mount and when site changes
  useEffect(() => {
    fetchData();
  }, [fetchData, selectedSiteId]);

  // Auto-refresh every 15 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchData(true);
      setRefreshKey((k) => k + 1);
    }, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleRefresh = () => {
    fetchData(true);
    setRefreshKey((k) => k + 1);
  };

  const handleArmZone = async (zoneId: string) => {
    try {
      await securityApi.armAlarmZone(zoneId, "full");
      fetchData(true);
    } catch (err) {
      if (!isExpectedApiError(err)) {
        console.error("Failed to arm zone:", err);
      }
    }
  };

  const handleDisarmZone = async (zoneId: string) => {
    try {
      await securityApi.disarmAlarmZone(zoneId);
      fetchData(true);
    } catch (err) {
      if (!isExpectedApiError(err)) {
        console.error("Failed to disarm zone:", err);
      }
    }
  };

  const formatTime = (date: Date) =>
    date.toLocaleTimeString("en-ZA", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });

  const getCameraStatusColor = (status: string) => {
    switch (status) {
      case "online":
        return "var(--color-sentinel-green)";
      case "offline":
        return "var(--color-sentinel-red)";
      case "fault":
        return "var(--color-sentinel-amber)";
      default:
        return "var(--color-sentinel-text-disabled)";
    }
  };

  const getAlarmStatusColor = (status: string) => {
    switch (status) {
      case "armed":
        return "var(--color-sentinel-green)";
      case "disarmed":
        return "var(--color-sentinel-text-disabled)";
      case "triggered":
        return "var(--color-sentinel-red)";
      case "fault":
        return "var(--color-sentinel-amber)";
      default:
        return "var(--color-sentinel-text-disabled)";
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="h-full overflow-y-auto p-4 md:p-6">
        <div className="space-y-6">
          <div className="animate-pulse space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="h-24 rounded-md"
                  style={{ background: "var(--color-sentinel-bg-panel)" }}
                />
              ))}
            </div>
            <div
              className="h-64 rounded-md"
              style={{ background: "var(--color-sentinel-bg-panel)" }}
            />
            <div
              className="h-64 rounded-md"
              style={{ background: "var(--color-sentinel-bg-panel)" }}
            />
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return <PageLoading message="Loading security dashboard..." />;
  }

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6">
      <div className="space-y-6 max-w-7xl mx-auto">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div
              className="p-2.5 rounded"
              style={{ background: "rgba(59, 130, 246, 0.15)" }}
            >
              <Shield
                className="h-6 w-6"
                style={{ color: "var(--color-sentinel-blue)" }}
              />
            </div>
            <div>
              <h2
                className="font-medium text-base"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Security Dashboard
              </h2>
              <p
                className="text-sm"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Access control, cameras, alarms, and occupancy monitoring
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Building Selector */}
            <div style={{ minWidth: "200px" }}>
              <BuildingSelector
                value={selectedSiteId}
                onChange={setSelectedSiteId}
                sites={sites}
              />
            </div>
            {lastUpdated && (
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                Updated: {formatTime(lastUpdated)}
              </span>
            )}
            <button
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium transition-colors hover:brightness-110 disabled:opacity-50"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                color: "var(--color-sentinel-text-primary)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <RefreshCw
                className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
              />
              Refresh
            </button>
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div
            className="rounded-md p-4 flex items-center gap-3"
            style={{
              background: "rgba(220, 38, 38, 0.1)",
              border: "1px solid rgba(220, 38, 38, 0.3)",
            }}
          >
            <AlertTriangle
              className="h-5 w-5 flex-shrink-0"
              style={{ color: "var(--color-sentinel-red)" }}
            />
            <span
              className="text-sm"
              style={{ color: "var(--color-sentinel-red)" }}
            >
              {error}
            </span>
          </div>
        )}

        {/* Section 1: Status Overview - 4 KPI Cards */}
        {status && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Doors Secure */}
            <div
              className="rounded-md p-4"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <div className="flex items-center gap-2 mb-3">
                <div
                  className="p-2 rounded"
                  style={{
                    background:
                      status.doors_secure === status.total_doors
                        ? "rgba(16, 185, 129, 0.15)"
                        : "rgba(245, 158, 11, 0.15)",
                  }}
                >
                  <DoorClosed
                    className="h-5 w-5"
                    style={{
                      color:
                        status.doors_secure === status.total_doors
                          ? "var(--color-sentinel-green)"
                          : "var(--color-sentinel-amber)",
                    }}
                  />
                </div>
                <span
                  className="text-xs font-medium uppercase tracking-wide"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Doors Secure
                </span>
              </div>
              <span
                className="text-3xl font-bold"
                style={{
                  color:
                    status.doors_secure === status.total_doors
                      ? "var(--color-sentinel-green)"
                      : "var(--color-sentinel-amber)",
                }}
              >
                {status.doors_secure}
                <span
                  className="text-lg font-normal"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  /{status.total_doors}
                </span>
              </span>
            </div>

            {/* Cameras Online */}
            <div
              className="rounded-md p-4"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <div className="flex items-center gap-2 mb-3">
                <div
                  className="p-2 rounded"
                  style={{
                    background:
                      status.cameras_online === status.cameras_total
                        ? "rgba(16, 185, 129, 0.15)"
                        : "rgba(220, 38, 38, 0.15)",
                  }}
                >
                  <Camera
                    className="h-5 w-5"
                    style={{
                      color:
                        status.cameras_online === status.cameras_total
                          ? "var(--color-sentinel-green)"
                          : "var(--color-sentinel-red)",
                    }}
                  />
                </div>
                <span
                  className="text-xs font-medium uppercase tracking-wide"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Cameras Online
                </span>
              </div>
              <span
                className="text-3xl font-bold"
                style={{
                  color:
                    status.cameras_online === status.cameras_total
                      ? "var(--color-sentinel-green)"
                      : "var(--color-sentinel-red)",
                }}
              >
                {status.cameras_online}
                <span
                  className="text-lg font-normal"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  /{status.cameras_total}
                </span>
              </span>
            </div>

            {/* Alarm Zones Armed */}
            <div
              className="rounded-md p-4"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <div className="flex items-center gap-2 mb-3">
                <div
                  className="p-2 rounded"
                  style={{ background: "rgba(59, 130, 246, 0.15)" }}
                >
                  <Bell
                    className="h-5 w-5"
                    style={{ color: "var(--color-sentinel-blue)" }}
                  />
                </div>
                <span
                  className="text-xs font-medium uppercase tracking-wide"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Alarms Armed
                </span>
              </div>
              <span
                className="text-3xl font-bold"
                style={{ color: "var(--color-sentinel-blue)" }}
              >
                {status.alarm_zones_armed}
                <span
                  className="text-lg font-normal"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  /{status.alarm_zones_total}
                </span>
              </span>
            </div>

            {/* Building Occupancy */}
            <div
              className="rounded-md p-4"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <div className="flex items-center gap-2 mb-3">
                <div
                  className="p-2 rounded"
                  style={{ background: "rgba(168, 85, 247, 0.15)" }}
                >
                  <Users
                    className="h-5 w-5"
                    style={{ color: "#a855f7" }}
                  />
                </div>
                <span
                  className="text-xs font-medium uppercase tracking-wide"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Building Occupancy
                </span>
              </div>
              <span
                className="text-3xl font-bold"
                style={{ color: "#a855f7" }}
              >
                {status.occupancy_total}
              </span>
              <span
                className="text-xs block"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                people in building
              </span>
            </div>
          </div>
        )}

        {/* Active Alerts Banner */}
        {status && status.active_alerts > 0 && (
          <div
            className="rounded-md p-4 flex items-center gap-3"
            style={{
              background: "rgba(220, 38, 38, 0.1)",
              border: "1px solid rgba(220, 38, 38, 0.3)",
            }}
          >
            <ShieldAlert
              className="h-5 w-5 flex-shrink-0"
              style={{ color: "var(--color-sentinel-red)" }}
            />
            <div>
              <span
                className="font-medium text-sm block"
                style={{ color: "var(--color-sentinel-red)" }}
              >
                {status.active_alerts} Active Security Alert
                {status.active_alerts > 1 ? "s" : ""}
              </span>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Requires immediate attention
              </span>
            </div>
          </div>
        )}

        {/* C•CURE 9000 Integration Status Card */}
        <div
          className="rounded-md p-4 col-span-full"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Shield
                className="h-5 w-5"
                style={{ color: "var(--color-sentinel-amber)" }}
              />
              <div>
                <span
                  className="font-medium text-sm"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  C•CURE 9000 Integration
                </span>
                <span
                  className="text-xs block mt-1"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Johnson Controls / Software House - Demo Mode
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span
                className="text-xs px-2 py-1 rounded"
                style={{
                  background: "rgba(245, 158, 11, 0.15)",
                  color: "var(--color-sentinel-amber)",
                  border: "1px solid rgba(245, 158, 11, 0.3)",
                }}
              >
                DEMO MODE
              </span>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-3 gap-4">
            <div>
              <span
                className="text-xs block"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                Protocol
              </span>
              <span
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                victor Web Service API
              </span>
            </div>
            <div>
              <span
                className="text-xs block"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                Demo Events
              </span>
              <span
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                5 badge events
              </span>
            </div>
            <div>
              <span
                className="text-xs block"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                License Status
              </span>
              <span
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-amber)" }}
              >
                Partner Program Required
              </span>
            </div>
          </div>

          <div
            className="mt-3 text-xs p-2 rounded"
            style={{
              background: "rgba(59, 130, 246, 0.1)",
              color: "var(--color-sentinel-text-secondary)",
              border: "1px solid rgba(59, 130, 246, 0.2)",
            }}
          >
            💡 <strong>Client Onboarding:</strong> When your client has C•CURE 9000
            installed, apply to Software House Connected Partner Program for live
            integration. See{" "}
            <code>docs/integrations/ccure-partner-program-roadmap.md</code> for steps.
          </div>
        </div>

        {/* Section 2: Security Anomalies */}
        <SecurityAnomaliesPanel siteId={selectedSiteId} refreshKey={refreshKey} />

        {/* Section 3: Access Events */}
        <AccessEventsPanel siteId={selectedSiteId} refreshKey={refreshKey} />

        {/* Section 4: Camera & Alarm Status (2-column grid) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Camera List */}
          <div
            className="rounded-md overflow-hidden"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div
              className="p-4 flex items-center justify-between"
              style={{
                borderBottom: "1px solid var(--color-sentinel-border)",
              }}
            >
              <div className="flex items-center gap-2">
                <Camera
                  className="h-5 w-5"
                  style={{ color: "var(--color-sentinel-green)" }}
                />
                <span
                  className="font-medium text-sm"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  CCTV Cameras
                </span>
              </div>
              <span
                className="text-xs px-2 py-0.5 rounded"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  color: "var(--color-sentinel-text-secondary)",
                }}
              >
                {cameras.length}
              </span>
            </div>
            <div className="divide-y" style={{ borderColor: "var(--color-sentinel-border)" }}>
              {cameras.map((cam) => (
                <div
                  key={cam.camera_id}
                  className="px-4 py-3 flex items-center justify-between"
                  style={{
                    borderBottom: "1px solid var(--color-sentinel-border)",
                  }}
                >
                  <div className="flex items-center gap-3">
                    {cam.status === "online" ? (
                      <Video
                        className="h-4 w-4"
                        style={{ color: getCameraStatusColor(cam.status) }}
                      />
                    ) : (
                      <VideoOff
                        className="h-4 w-4"
                        style={{ color: getCameraStatusColor(cam.status) }}
                      />
                    )}
                    <div>
                      <span
                        className="text-sm block"
                        style={{
                          color: "var(--color-sentinel-text-primary)",
                        }}
                      >
                        {cam.name}
                      </span>
                      <span
                        className="text-xs"
                        style={{
                          color: "var(--color-sentinel-text-disabled)",
                        }}
                      >
                        {cam.floor} | {cam.type.toUpperCase()} | {cam.resolution}
                        {cam.has_analytics ? " | AI Analytics" : ""}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {cam.motion_detected && (
                      <span
                        className="text-xs px-2 py-0.5 rounded"
                        style={{
                          background: "rgba(245, 158, 11, 0.15)",
                          color: "var(--color-sentinel-amber)",
                        }}
                      >
                        Motion
                      </span>
                    )}
                    <span
                      className="text-xs font-medium px-2 py-0.5 rounded capitalize"
                      style={{
                        background: `${getCameraStatusColor(cam.status)}20`,
                        color: getCameraStatusColor(cam.status),
                      }}
                    >
                      {cam.status}
                    </span>
                  </div>
                </div>
              ))}
              {cameras.length === 0 && (
                <div
                  className="px-4 py-8 text-center text-sm"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  No cameras configured
                </div>
              )}
            </div>
          </div>

          {/* Alarm Zones */}
          <div
            className="rounded-md overflow-hidden"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div
              className="p-4 flex items-center justify-between"
              style={{
                borderBottom: "1px solid var(--color-sentinel-border)",
              }}
            >
              <div className="flex items-center gap-2">
                <ShieldCheck
                  className="h-5 w-5"
                  style={{ color: "var(--color-sentinel-blue)" }}
                />
                <span
                  className="font-medium text-sm"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Alarm Zones
                </span>
              </div>
              <span
                className="text-xs px-2 py-0.5 rounded"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  color: "var(--color-sentinel-text-secondary)",
                }}
              >
                {alarmZones.length}
              </span>
            </div>
            <div className="divide-y" style={{ borderColor: "var(--color-sentinel-border)" }}>
              {alarmZones.map((zone) => (
                <div
                  key={zone.zone_id}
                  className="px-4 py-3 flex items-center justify-between"
                  style={{
                    borderBottom: "1px solid var(--color-sentinel-border)",
                    background:
                      zone.status === "triggered"
                        ? "rgba(220, 38, 38, 0.05)"
                        : "transparent",
                  }}
                >
                  <div className="flex items-center gap-3">
                    {zone.status === "armed" ? (
                      <Lock
                        className="h-4 w-4"
                        style={{
                          color: getAlarmStatusColor(zone.status),
                        }}
                      />
                    ) : zone.status === "triggered" ? (
                      <ShieldAlert
                        className="h-4 w-4"
                        style={{
                          color: getAlarmStatusColor(zone.status),
                        }}
                      />
                    ) : (
                      <Unlock
                        className="h-4 w-4"
                        style={{
                          color: getAlarmStatusColor(zone.status),
                        }}
                      />
                    )}
                    <div>
                      <span
                        className="text-sm block"
                        style={{
                          color: "var(--color-sentinel-text-primary)",
                        }}
                      >
                        {zone.name}
                      </span>
                      <span
                        className="text-xs capitalize"
                        style={{
                          color: "var(--color-sentinel-text-disabled)",
                        }}
                      >
                        {zone.arm_type} mode
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className="text-xs font-medium px-2 py-0.5 rounded capitalize"
                      style={{
                        background: `${getAlarmStatusColor(zone.status)}20`,
                        color: getAlarmStatusColor(zone.status),
                      }}
                    >
                      {zone.status}
                    </span>
                    {zone.status === "disarmed" ? (
                      <button
                        onClick={() => handleArmZone(zone.zone_id)}
                        className="text-xs px-2.5 py-1 rounded font-medium transition-colors hover:brightness-110"
                        style={{
                          background: "rgba(16, 185, 129, 0.15)",
                          color: "var(--color-sentinel-green)",
                          border:
                            "1px solid rgba(16, 185, 129, 0.3)",
                        }}
                      >
                        Arm
                      </button>
                    ) : zone.status === "armed" ? (
                      <button
                        onClick={() => handleDisarmZone(zone.zone_id)}
                        className="text-xs px-2.5 py-1 rounded font-medium transition-colors hover:brightness-110"
                        style={{
                          background: "rgba(220, 38, 38, 0.15)",
                          color: "var(--color-sentinel-red)",
                          border:
                            "1px solid rgba(220, 38, 38, 0.3)",
                        }}
                      >
                        Disarm
                      </button>
                    ) : null}
                  </div>
                </div>
              ))}
              {alarmZones.length === 0 && (
                <div
                  className="px-4 py-8 text-center text-sm"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  No alarm zones configured
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Section 4: Occupancy */}
        <SecurityOccupancyPanel siteId={selectedSiteId} refreshKey={refreshKey} />
      </div>
    </div>
  );
}

export default SecurityDashboard;

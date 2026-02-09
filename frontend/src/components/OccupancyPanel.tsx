/**
 * OccupancyPanel Component - DALI Occupancy Dashboard Container
 *
 * Features:
 * - Compact mode (for dashboard): Stats cards, floor summary bars, View Details button
 * - Full mode (dedicated page): Header with sensor count, 4-card stats grid,
 *   OccupancyHeatmap, auto-refresh every 30 seconds
 * - Loading state with LoadingCard
 * - Error handling
 * - Refresh button with spinner
 * - Timestamp display
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect, useCallback } from "react";
import { RefreshCw, Users, Lightbulb, AlertTriangle, Cpu, Eye, Zap, Building2, ChevronDown, X, Radio, Clock, ThermometerSun, Wrench } from "lucide-react";
import { OccupancyHeatmap } from "./OccupancyHeatmap";
import { api, daliApi, isExpectedApiError } from "../lib/api";
import type { BuildingOccupancy, DALIStats, ZoneLighting, ZoneOccupancy, DALISensor, DALILuminaire, Site } from "../lib/api";

// Get occupancy color based on percentage
function getOccupancyColor(percent: number): string {
  if (percent > 70) return "var(--color-sentinel-red)";
  if (percent >= 40) return "var(--color-sentinel-amber)";
  if (percent >= 10) return "var(--color-sentinel-green)";
  return "var(--color-sentinel-text-disabled)";
}

interface OccupancyPanelProps {
  compact?: boolean;
  onViewDetails?: () => void;
}

// Sites with DALI-2 lighting integration installed
const DALI_ENABLED_SITES = ["site-002"]; // Sandton City

export function OccupancyPanel({ compact = false, onViewDetails }: OccupancyPanelProps) {
  const [buildingOccupancy, setBuildingOccupancy] = useState<BuildingOccupancy | null>(null);
  const [daliStats, setDaliStats] = useState<DALIStats | null>(null);
  const [zoneLighting, setZoneLighting] = useState<Record<string, ZoneLighting>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("site-002"); // Default to Sandton City

  // Zone details panel state
  const [selectedZone, setSelectedZone] = useState<ZoneOccupancy | null>(null);
  const [zoneDetails, setZoneDetails] = useState<{
    sensors: DALISensor[];
    luminaires: DALILuminaire[];
    lighting: ZoneLighting | null;
  } | null>(null);
  const [loadingZoneDetails, setLoadingZoneDetails] = useState(false);

  // Filter sites to only show DALI-enabled buildings
  const daliSites = sites.filter(site => DALI_ENABLED_SITES.includes(site.id));

  const fetchData = useCallback(async (showRefreshing = false) => {
    try {
      if (showRefreshing) {
        setIsRefreshing(true);
      }

      const [occupancy, stats] = await Promise.all([
        daliApi.getBuildingOccupancy(),
        daliApi.getStats(),
      ]);

      // Fetch lighting for energy waste zones (low occupancy)
      const wasteZoneLighting: Record<string, ZoneLighting> = {};
      for (const floor of occupancy.floors) {
        for (const zone of floor.zones) {
          if (zone.occupancy_percent < 20) {
            try {
              const lighting = await daliApi.getZoneLighting(zone.zone_id);
              if (lighting.energy_waste_detected) {
                wasteZoneLighting[zone.zone_id] = lighting;
              }
            } catch {
              // Zone may not have lighting data
            }
          }
        }
      }

      setBuildingOccupancy(occupancy);
      setDaliStats(stats);
      setZoneLighting(wasteZoneLighting);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      if (!isExpectedApiError(err)) {
        console.error("Failed to fetch occupancy data:", err);
      }
      setError("Failed to load occupancy data. Check that the backend is running.");
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  // Fetch sites on mount
  useEffect(() => {
    async function loadSites() {
      try {
        const sitesData = await api.getSites();
        setSites(sitesData);
      } catch (err) {
        if (!isExpectedApiError(err)) {
          console.error("Failed to fetch sites:", err);
        }
      }
    }
    loadSites();
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (compact) return; // Don't auto-refresh in compact mode

    const interval = setInterval(() => {
      fetchData(true);
    }, 30000);

    return () => clearInterval(interval);
  }, [compact, fetchData]);

  const handleRefresh = () => {
    fetchData(true);
  };

  // Handle zone click - fetch zone details
  const handleZoneClick = async (zone: ZoneOccupancy) => {
    setSelectedZone(zone);
    setLoadingZoneDetails(true);
    setZoneDetails(null);

    try {
      const [sensors, luminaires, lighting] = await Promise.all([
        daliApi.getSensors(zone.zone_id),
        daliApi.getLuminaires(zone.zone_id),
        daliApi.getZoneLighting(zone.zone_id),
      ]);

      setZoneDetails({ sensors, luminaires, lighting });
    } catch (err) {
      if (!isExpectedApiError(err)) {
        console.error("Failed to fetch zone details:", err);
      }
    } finally {
      setLoadingZoneDetails(false);
    }
  };

  const closeZoneDetails = () => {
    setSelectedZone(null);
    setZoneDetails(null);
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString("en-ZA", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  };

  // Loading state
  if (loading) {
    return (
      <div
        className="rounded-md overflow-hidden"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="p-4">
          <div className="animate-pulse space-y-4">
            <div className="flex items-center gap-2">
              <div
                className="h-5 w-5 rounded"
                style={{ background: "var(--color-sentinel-bg-secondary)" }}
              />
              <div
                className="h-4 w-32 rounded"
                style={{ background: "var(--color-sentinel-bg-secondary)" }}
              />
            </div>
            <div className="grid grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-20 rounded"
                  style={{ background: "var(--color-sentinel-bg-secondary)" }}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div
        className="rounded-md overflow-hidden"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="p-4">
          <div className="flex items-center gap-2 text-sm" style={{ color: "var(--color-sentinel-red)" }}>
            <AlertTriangle className="h-4 w-4" />
            <span>{error}</span>
          </div>
        </div>
      </div>
    );
  }

  // Compact mode for dashboard
  if (compact && buildingOccupancy && daliStats) {
    return (
      <div
        className="rounded-md overflow-hidden"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        {/* Header */}
        <div
          className="p-4 flex items-center justify-between"
          style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
        >
          <div className="flex items-center gap-2">
            <div
              className="p-2 rounded"
              style={{ background: "rgba(59, 130, 246, 0.15)" }}
            >
              <Users className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
            </div>
            <div>
              <span className="font-medium text-sm block" style={{ color: "var(--color-sentinel-text-primary)" }}>
                DALI Occupancy
              </span>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {daliStats.total_sensors} sensors • {daliStats.total_luminaires} luminaires
              </span>
            </div>
          </div>
          <span
            className="text-xs px-2 py-1 rounded"
            style={{
              background: "rgba(59, 130, 246, 0.15)",
              color: "var(--color-sentinel-blue)",
            }}
          >
            DALI-2
          </span>
        </div>

        {/* Stats Cards */}
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-3 gap-4">
            {/* Occupancy */}
            <div className="text-center">
              <span
                className="text-2xl font-bold block"
                style={{ color: getOccupancyColor(buildingOccupancy.occupancy_percent) }}
              >
                {buildingOccupancy.occupancy_percent}%
              </span>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Occupancy
              </span>
            </div>

            {/* Power */}
            <div className="text-center">
              <span className="text-2xl font-bold block" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {(daliStats.current_power_watts / 1000).toFixed(1)}
              </span>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                kW
              </span>
            </div>

            {/* Issues */}
            <div className="text-center">
              <span
                className="text-2xl font-bold block"
                style={{
                  color: daliStats.faulty_luminaires > 0
                    ? "var(--color-sentinel-amber)"
                    : "var(--color-sentinel-green)",
                }}
              >
                {daliStats.faulty_luminaires}
              </span>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Faulty
              </span>
            </div>
          </div>

          {/* Floor Summary Bars */}
          <div className="space-y-2">
            {buildingOccupancy.floors.map((floor) => (
              <div key={floor.floor} className="flex items-center gap-2">
                <span
                  className="text-xs w-8 text-right"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  {floor.floor}
                </span>
                <div
                  className="flex-1 h-4 rounded overflow-hidden"
                  style={{ background: "var(--color-sentinel-bg-secondary)" }}
                >
                  <div
                    className="h-full rounded transition-all duration-300"
                    style={{
                      width: `${floor.occupancy_percent}%`,
                      background: getOccupancyColor(floor.occupancy_percent),
                    }}
                  />
                </div>
                <span
                  className="text-xs w-8"
                  style={{ color: getOccupancyColor(floor.occupancy_percent) }}
                >
                  {floor.occupancy_percent}%
                </span>
              </div>
            ))}
          </div>

          {/* View Details Button */}
          <button
            onClick={onViewDetails}
            className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded text-sm font-medium transition-colors hover:brightness-110"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              color: "var(--color-sentinel-text-primary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <Eye className="h-4 w-4" />
            View Details
          </button>
        </div>
      </div>
    );
  }

  // Full mode for dedicated page
  if (buildingOccupancy && daliStats) {
    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            {/* Building Selector */}
            <div className="relative min-w-[200px]">
              <Building2
                className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              />
              <select
                value={selectedSiteId}
                onChange={(e) => setSelectedSiteId(e.target.value)}
                className="w-full pl-9 pr-8 py-2 text-sm rounded appearance-none cursor-pointer"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                }}
              >
                {daliSites.map((site) => (
                  <option key={site.id} value={site.id}>
                    {site.name}
                  </option>
                ))}
              </select>
              <ChevronDown
                className="absolute right-2 top-1/2 transform -translate-y-1/2 h-4 w-4 pointer-events-none"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              />
            </div>
            <div>
              <h2 className="font-medium text-base mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                DALI Occupancy
              </h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {daliStats.total_sensors} DALI-2 sensors • {daliStats.total_luminaires} luminaires
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {lastUpdated && (
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
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
              <RefreshCw className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Occupancy */}
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
                <Users className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
              </div>
              <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Occupancy
              </span>
            </div>
            <span
              className="text-3xl font-bold block"
              style={{ color: getOccupancyColor(buildingOccupancy.occupancy_percent) }}
            >
              {buildingOccupancy.occupancy_percent}%
            </span>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {buildingOccupancy.occupied_sensors} of {buildingOccupancy.total_sensors} sensors
            </span>
          </div>

          {/* Controllers */}
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
                style={{ background: "rgba(16, 185, 129, 0.15)" }}
              >
                <Cpu className="h-5 w-5" style={{ color: "var(--color-sentinel-green)" }} />
              </div>
              <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Controllers
              </span>
            </div>
            <span className="text-3xl font-bold block" style={{ color: "var(--color-sentinel-green)" }}>
              {daliStats.online_controllers}/{daliStats.total_controllers}
            </span>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Online
            </span>
          </div>

          {/* Lighting */}
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
                style={{ background: "rgba(245, 158, 11, 0.15)" }}
              >
                <Lightbulb className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
              </div>
              <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Lighting Power
              </span>
            </div>
            <span className="text-3xl font-bold block" style={{ color: "var(--color-sentinel-text-primary)" }}>
              {(daliStats.current_power_watts / 1000).toFixed(1)} kW
            </span>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {daliStats.energy_today_kwh} kWh today
            </span>
          </div>

          {/* Maintenance */}
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
                style={{ background: "rgba(220, 38, 38, 0.15)" }}
              >
                <Zap className="h-5 w-5" style={{ color: "var(--color-sentinel-red)" }} />
              </div>
              <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Maintenance
              </span>
            </div>
            <span
              className="text-3xl font-bold block"
              style={{
                color: daliStats.faulty_luminaires > 0
                  ? "var(--color-sentinel-amber)"
                  : "var(--color-sentinel-green)",
              }}
            >
              {daliStats.faulty_luminaires}
            </span>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Faulty luminaires
            </span>
          </div>
        </div>

        {/* Energy Waste Alerts */}
        {daliStats.energy_waste_alerts > 0 && (
          <div
            className="rounded-md p-4 flex items-center gap-3"
            style={{
              background: "rgba(245, 158, 11, 0.1)",
              border: "1px solid rgba(245, 158, 11, 0.3)",
            }}
          >
            <AlertTriangle className="h-5 w-5 flex-shrink-0" style={{ color: "var(--color-sentinel-amber)" }} />
            <div>
              <span className="font-medium text-sm block" style={{ color: "var(--color-sentinel-amber)" }}>
                {daliStats.energy_waste_alerts} Energy Waste Alert{daliStats.energy_waste_alerts > 1 ? "s" : ""}
              </span>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Empty or low-occupancy zones with active lighting detected
              </span>
            </div>
          </div>
        )}

        {/* Floor/Zone Heatmap */}
        <OccupancyHeatmap
          floors={buildingOccupancy.floors}
          zoneLighting={zoneLighting}
          loading={loading}
          onZoneClick={handleZoneClick}
        />

        {/* Zone Detail Slide-out Panel */}
        {selectedZone && (
          <div
            className="fixed inset-0 z-50 flex justify-end"
            style={{ background: "rgba(0, 0, 0, 0.5)" }}
            onClick={closeZoneDetails}
          >
            <div
              className="w-full max-w-md h-full overflow-y-auto"
              style={{
                background: "var(--color-sentinel-bg-primary)",
                borderLeft: "1px solid var(--color-sentinel-border)",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div
                className="sticky top-0 p-4 flex items-center justify-between"
                style={{
                  background: "var(--color-sentinel-bg-primary)",
                  borderBottom: "1px solid var(--color-sentinel-border)",
                }}
              >
                <div>
                  <h3
                    className="font-medium text-base"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    {selectedZone.zone_name}
                  </h3>
                  <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Floor {selectedZone.floor} • {selectedZone.total_sensors} sensors
                  </span>
                </div>
                <button
                  onClick={closeZoneDetails}
                  className="p-2 rounded hover:brightness-110"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    color: "var(--color-sentinel-text-secondary)",
                  }}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {/* Loading State */}
              {loadingZoneDetails && (
                <div className="p-4 space-y-4">
                  {[1, 2, 3].map((i) => (
                    <div
                      key={i}
                      className="animate-pulse h-20 rounded"
                      style={{ background: "var(--color-sentinel-bg-secondary)" }}
                    />
                  ))}
                </div>
              )}

              {/* Zone Details */}
              {zoneDetails && !loadingZoneDetails && (
                <div className="p-4 space-y-4">
                  {/* Zone Stats */}
                  <div className="grid grid-cols-2 gap-3">
                    <div
                      className="rounded p-3"
                      style={{
                        background: "var(--color-sentinel-bg-panel)",
                        border: "1px solid var(--color-sentinel-border)",
                      }}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <Users className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
                        <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          Occupancy
                        </span>
                      </div>
                      <span
                        className="text-xl font-bold"
                        style={{ color: getOccupancyColor(selectedZone.occupancy_percent) }}
                      >
                        {selectedZone.occupancy_percent}%
                      </span>
                    </div>
                    <div
                      className="rounded p-3"
                      style={{
                        background: "var(--color-sentinel-bg-panel)",
                        border: "1px solid var(--color-sentinel-border)",
                      }}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <Zap className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
                        <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          Power
                        </span>
                      </div>
                      <span
                        className="text-xl font-bold"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        {((zoneDetails.lighting?.total_power_watts || 0) / 1000).toFixed(2)} kW
                      </span>
                    </div>
                  </div>

                  {/* Energy Waste Alert */}
                  {zoneDetails.lighting?.energy_waste_detected && (
                    <div
                      className="rounded p-3 flex items-center gap-2"
                      style={{
                        background: "rgba(245, 158, 11, 0.1)",
                        border: "1px solid rgba(245, 158, 11, 0.3)",
                      }}
                    >
                      <AlertTriangle className="h-4 w-4 flex-shrink-0" style={{ color: "var(--color-sentinel-amber)" }} />
                      <span className="text-xs" style={{ color: "var(--color-sentinel-amber)" }}>
                        {zoneDetails.lighting.energy_waste_reason || "Energy waste detected"}
                      </span>
                    </div>
                  )}

                  {/* Sensors Section */}
                  <div>
                    <h4
                      className="text-sm font-medium mb-2 flex items-center gap-2"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      <Radio className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
                      Sensors ({zoneDetails.sensors.length})
                    </h4>
                    <div className="space-y-2">
                      {zoneDetails.sensors.length === 0 ? (
                        <div
                          className="text-xs p-2 rounded"
                          style={{
                            background: "var(--color-sentinel-bg-secondary)",
                            color: "var(--color-sentinel-text-secondary)",
                          }}
                        >
                          No sensors in this zone
                        </div>
                      ) : (
                        zoneDetails.sensors.map((sensor) => (
                          <div
                            key={sensor.id}
                            className="rounded p-3"
                            style={{
                              background: "var(--color-sentinel-bg-panel)",
                              border: "1px solid var(--color-sentinel-border)",
                            }}
                          >
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                {sensor.id}
                              </span>
                              <span
                                className="text-xs px-2 py-0.5 rounded"
                                style={{
                                  background: (sensor.status || "unknown") === "online"
                                    ? "rgba(16, 185, 129, 0.15)"
                                    : "rgba(220, 38, 38, 0.15)",
                                  color: (sensor.status || "unknown") === "online"
                                    ? "var(--color-sentinel-green)"
                                    : "var(--color-sentinel-red)",
                                }}
                              >
                                {sensor.status || "unknown"}
                              </span>
                            </div>
                            <div className="grid grid-cols-2 gap-2 text-xs">
                              <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                <span>Type: </span>
                                <span style={{ color: "var(--color-sentinel-text-primary)" }}>{sensor.type || "unknown"}</span>
                              </div>
                              <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                <span>Desk: </span>
                                <span style={{ color: "var(--color-sentinel-text-primary)" }}>{sensor.desk_id || "-"}</span>
                              </div>
                              <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                <span>Occupied: </span>
                                <span style={{ color: sensor.occupied ? "var(--color-sentinel-green)" : "var(--color-sentinel-text-disabled)" }}>
                                  {sensor.occupied ? "Yes" : "No"}
                                </span>
                              </div>
                              {sensor.lux_level !== null && (
                                <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                  <span>Lux: </span>
                                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>{sensor.lux_level}</span>
                                </div>
                              )}
                            </div>
                            {sensor.last_motion && (
                              <div className="mt-2 flex items-center gap-1 text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                                <Clock className="h-3 w-3" />
                                Last motion: {new Date(sensor.last_motion).toLocaleTimeString()}
                              </div>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Luminaires Section */}
                  <div>
                    <h4
                      className="text-sm font-medium mb-2 flex items-center gap-2"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      <Lightbulb className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
                      Luminaires ({zoneDetails.luminaires.length})
                    </h4>
                    <div className="space-y-2">
                      {zoneDetails.luminaires.length === 0 ? (
                        <div
                          className="text-xs p-2 rounded"
                          style={{
                            background: "var(--color-sentinel-bg-secondary)",
                            color: "var(--color-sentinel-text-secondary)",
                          }}
                        >
                          No luminaires in this zone
                        </div>
                      ) : (
                        zoneDetails.luminaires.map((luminaire) => (
                          <div
                            key={luminaire.id}
                            className="rounded p-3"
                            style={{
                              background: "var(--color-sentinel-bg-panel)",
                              border: (luminaire.status || "unknown") === "fault"
                                ? "1px solid rgba(220, 38, 38, 0.5)"
                                : "1px solid var(--color-sentinel-border)",
                            }}
                          >
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                {luminaire.id}
                              </span>
                              <span
                                className="text-xs px-2 py-0.5 rounded"
                                style={{
                                  background: (luminaire.status || "unknown") === "online"
                                    ? "rgba(16, 185, 129, 0.15)"
                                    : (luminaire.status || "unknown") === "fault"
                                    ? "rgba(220, 38, 38, 0.15)"
                                    : "rgba(142, 142, 142, 0.15)",
                                  color: (luminaire.status || "unknown") === "online"
                                    ? "var(--color-sentinel-green)"
                                    : (luminaire.status || "unknown") === "fault"
                                    ? "var(--color-sentinel-red)"
                                    : "var(--color-sentinel-text-secondary)",
                                }}
                              >
                                {luminaire.status || "unknown"}
                              </span>
                            </div>
                            <div className="grid grid-cols-2 gap-2 text-xs">
                              <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                <span>Type: </span>
                                <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                                  {(luminaire.type || "unknown").replace("_", " ")}
                                </span>
                              </div>
                              <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                <span>Power: </span>
                                <span style={{ color: "var(--color-sentinel-text-primary)" }}>{luminaire.power_watts ?? 0}W</span>
                              </div>
                              <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                <span>Brightness: </span>
                                <span style={{ color: "var(--color-sentinel-text-primary)" }}>{luminaire.brightness_percent ?? 0}%</span>
                              </div>
                              <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                <span>Runtime: </span>
                                <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                                  {(luminaire.runtime_hours ?? 0).toLocaleString()}h
                                </span>
                              </div>
                              {luminaire.color_temp_kelvin && (
                                <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                  <ThermometerSun className="h-3 w-3 inline mr-1" />
                                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                                    {luminaire.color_temp_kelvin}K
                                  </span>
                                </div>
                              )}
                            </div>
                            {luminaire.fault_code && (
                              <div
                                className="mt-2 flex items-center gap-1 text-xs p-2 rounded"
                                style={{
                                  background: "rgba(220, 38, 38, 0.1)",
                                  color: "var(--color-sentinel-red)",
                                }}
                              >
                                <Wrench className="h-3 w-3" />
                                Fault: {luminaire.fault_code}
                              </div>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Summary Footer */}
                  {zoneDetails.lighting && (
                    <div
                      className="rounded p-3 text-xs"
                      style={{
                        background: "var(--color-sentinel-bg-secondary)",
                        color: "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      <div className="flex justify-between mb-1">
                        <span>Active Luminaires:</span>
                        <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {zoneDetails.lighting.active_luminaires} / {zoneDetails.lighting.total_luminaires}
                        </span>
                      </div>
                      <div className="flex justify-between mb-1">
                        <span>Avg Brightness:</span>
                        <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {zoneDetails.lighting.avg_brightness}%
                        </span>
                      </div>
                      {zoneDetails.lighting.faulty_luminaires > 0 && (
                        <div className="flex justify-between">
                          <span>Faulty:</span>
                          <span style={{ color: "var(--color-sentinel-amber)" }}>
                            {zoneDetails.lighting.faulty_luminaires}
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    );
  }

  return null;
}

export default OccupancyPanel;

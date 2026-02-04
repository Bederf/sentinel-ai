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
import { RefreshCw, Users, Lightbulb, AlertTriangle, Cpu, Eye, Zap, Building2, ChevronDown } from "lucide-react";
import { OccupancyHeatmap } from "./OccupancyHeatmap";
import { api, daliApi } from "../lib/api";
import type { BuildingOccupancy, DALIStats, ZoneLighting, Site } from "../lib/api";

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
      console.error("Failed to fetch occupancy data:", err);
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
        console.error("Failed to fetch sites:", err);
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
        />
      </div>
    );
  }

  return null;
}

export default OccupancyPanel;

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
import { RefreshCw, Users, Lightbulb, AlertTriangle, Cpu, Eye, Zap } from "lucide-react";
import { OccupancyHeatmap } from "./OccupancyHeatmap";
import type { BuildingOccupancy, DALIStats, FloorSummary, ZoneLighting } from "../lib/api";

// Mock data for development until backend API is ready
const mockBuildingOccupancy: BuildingOccupancy = {
  building_id: "bldg-001",
  building_name: "Discovery Place",
  total_floors: 3,
  total_zones: 12,
  total_sensors: 1315,
  occupied_sensors: 428,
  occupancy_percent: 33,
  total_luminaires: 619,
  faulty_luminaires: 7,
  total_power_watts: 48500,
  energy_waste_zones: 2,
  last_updated: new Date().toISOString(),
  floors: [
    {
      floor: "L12",
      floor_name: "Level 12 - Executive",
      total_zones: 4,
      total_sensors: 285,
      occupied_sensors: 142,
      occupancy_percent: 50,
      total_luminaires: 145,
      faulty_luminaires: 2,
      total_power_watts: 12800,
      zones: [
        { zone_id: "z-12-a", zone_name: "Executive Suite A", floor: "L12", total_sensors: 65, occupied_sensors: 45, occupancy_percent: 69, avg_lux_level: 420, status: "moderate", last_updated: new Date().toISOString() },
        { zone_id: "z-12-b", zone_name: "Executive Suite B", floor: "L12", total_sensors: 70, occupied_sensors: 52, occupancy_percent: 74, avg_lux_level: 380, status: "busy", last_updated: new Date().toISOString() },
        { zone_id: "z-12-c", zone_name: "Boardroom Wing", floor: "L12", total_sensors: 80, occupied_sensors: 35, occupancy_percent: 44, avg_lux_level: 550, status: "moderate", last_updated: new Date().toISOString() },
        { zone_id: "z-12-d", zone_name: "Reception Area", floor: "L12", total_sensors: 70, occupied_sensors: 10, occupancy_percent: 14, avg_lux_level: 600, status: "quiet", last_updated: new Date().toISOString() },
      ],
    },
    {
      floor: "L11",
      floor_name: "Level 11 - Operations",
      total_zones: 4,
      total_sensors: 520,
      occupied_sensors: 182,
      occupancy_percent: 35,
      total_luminaires: 260,
      faulty_luminaires: 3,
      total_power_watts: 19500,
      zones: [
        { zone_id: "z-11-a", zone_name: "Open Plan North", floor: "L11", total_sensors: 180, occupied_sensors: 75, occupancy_percent: 42, avg_lux_level: 380, status: "moderate", last_updated: new Date().toISOString() },
        { zone_id: "z-11-b", zone_name: "Open Plan South", floor: "L11", total_sensors: 180, occupied_sensors: 62, occupancy_percent: 34, avg_lux_level: 420, status: "quiet", last_updated: new Date().toISOString() },
        { zone_id: "z-11-c", zone_name: "Meeting Rooms", floor: "L11", total_sensors: 80, occupied_sensors: 38, occupancy_percent: 48, avg_lux_level: 350, status: "moderate", last_updated: new Date().toISOString() },
        { zone_id: "z-11-d", zone_name: "Break Area", floor: "L11", total_sensors: 80, occupied_sensors: 7, occupancy_percent: 9, avg_lux_level: 480, status: "empty", last_updated: new Date().toISOString() },
      ],
    },
    {
      floor: "L10",
      floor_name: "Level 10 - Support",
      total_zones: 4,
      total_sensors: 510,
      occupied_sensors: 104,
      occupancy_percent: 20,
      total_luminaires: 214,
      faulty_luminaires: 2,
      total_power_watts: 16200,
      zones: [
        { zone_id: "z-10-a", zone_name: "Call Center", floor: "L10", total_sensors: 200, occupied_sensors: 58, occupancy_percent: 29, avg_lux_level: 360, status: "quiet", last_updated: new Date().toISOString() },
        { zone_id: "z-10-b", zone_name: "Training Room", floor: "L10", total_sensors: 100, occupied_sensors: 12, occupancy_percent: 12, avg_lux_level: 520, status: "quiet", last_updated: new Date().toISOString() },
        { zone_id: "z-10-c", zone_name: "IT Support", floor: "L10", total_sensors: 110, occupied_sensors: 32, occupancy_percent: 29, avg_lux_level: 340, status: "quiet", last_updated: new Date().toISOString() },
        { zone_id: "z-10-d", zone_name: "Storage Wing", floor: "L10", total_sensors: 100, occupied_sensors: 2, occupancy_percent: 2, avg_lux_level: 180, status: "empty", last_updated: new Date().toISOString() },
      ],
    },
  ],
};

const mockDALIStats: DALIStats = {
  total_controllers: 24,
  online_controllers: 23,
  total_sensors: 1315,
  online_sensors: 1298,
  total_luminaires: 619,
  faulty_luminaires: 7,
  current_occupancy_percent: 33,
  current_power_watts: 48500,
  energy_today_kwh: 312,
  energy_waste_alerts: 2,
  last_sync: new Date().toISOString(),
};

const mockZoneLighting: Record<string, ZoneLighting> = {
  "z-11-d": {
    zone_id: "z-11-d",
    zone_name: "Break Area",
    floor: "L11",
    total_luminaires: 20,
    active_luminaires: 18,
    faulty_luminaires: 0,
    total_power_watts: 1440,
    avg_brightness: 85,
    energy_waste_detected: true,
    energy_waste_reason: "Zone at 9% occupancy but 90% lighting",
  },
  "z-10-d": {
    zone_id: "z-10-d",
    zone_name: "Storage Wing",
    floor: "L10",
    total_luminaires: 12,
    active_luminaires: 10,
    faulty_luminaires: 0,
    total_power_watts: 850,
    avg_brightness: 70,
    energy_waste_detected: true,
    energy_waste_reason: "Zone empty but lighting active",
  },
};

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

export function OccupancyPanel({ compact = false, onViewDetails }: OccupancyPanelProps) {
  const [buildingOccupancy, setBuildingOccupancy] = useState<BuildingOccupancy | null>(null);
  const [daliStats, setDaliStats] = useState<DALIStats | null>(null);
  const [zoneLighting, setZoneLighting] = useState<Record<string, ZoneLighting>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async (showRefreshing = false) => {
    try {
      if (showRefreshing) {
        setIsRefreshing(true);
      }

      // TODO: Replace with actual API calls when backend is ready
      // const [occupancy, stats] = await Promise.all([
      //   daliApi.getBuildingOccupancy(),
      //   daliApi.getStats(),
      // ]);

      // Simulate API delay
      await new Promise(resolve => setTimeout(resolve, 500));

      setBuildingOccupancy(mockBuildingOccupancy);
      setDaliStats(mockDALIStats);
      setZoneLighting(mockZoneLighting);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      console.error("Failed to fetch occupancy data:", err);
      setError("Failed to load occupancy data");
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
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
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-medium text-base mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Building Occupancy
            </h2>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {daliStats.total_sensors} DALI-2 sensors • {daliStats.total_luminaires} luminaires
            </p>
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

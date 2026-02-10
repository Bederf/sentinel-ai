/**
 * OccupancyHeatmap Component - DALI Floor/Zone Occupancy Visualization
 *
 * Features:
 * - FloorRow component for each floor (L10, L11, L12)
 * - ZoneCard component for each zone showing:
 *   - Occupancy percentage bar
 *   - Sensor count (occupied/total)
 *   - Lux level indicator (sun icon for high daylight)
 *   - Color coding: red (>70%), yellow (40-70%), green (10-40%), gray (<10%)
 * - Badge showing Busy/Moderate/Quiet/Empty
 * - Energy waste alert for empty zones with high power
 *
 * Follows SENTINEL dark theme design.
 */

import { Users, Sun, Zap, AlertTriangle } from "lucide-react";
import type { ZoneOccupancy, FloorSummary, ZoneLighting } from '@/lib/api';

// Sentinel-styled Badge component
interface SentinelBadgeProps {
  children: React.ReactNode;
  variant?: "success" | "warning" | "error" | "info" | "neutral";
  size?: "sm" | "md" | "lg";
  className?: string;
}

function SentinelBadge({ children, variant = "neutral", size = "md", className = "" }: SentinelBadgeProps) {
  const variantStyles = {
    success: {
      bg: "rgba(16, 185, 129, 0.15)",
      color: "var(--color-sentinel-green)",
      border: "rgba(16, 185, 129, 0.3)",
    },
    warning: {
      bg: "rgba(245, 158, 11, 0.15)",
      color: "var(--color-sentinel-amber)",
      border: "rgba(245, 158, 11, 0.3)",
    },
    error: {
      bg: "rgba(220, 38, 38, 0.15)",
      color: "var(--color-sentinel-red)",
      border: "rgba(220, 38, 38, 0.3)",
    },
    info: {
      bg: "rgba(59, 130, 246, 0.15)",
      color: "var(--color-sentinel-blue)",
      border: "rgba(59, 130, 246, 0.3)",
    },
    neutral: {
      bg: "rgba(142, 142, 142, 0.15)",
      color: "var(--color-sentinel-text-secondary)",
      border: "rgba(142, 142, 142, 0.3)",
    },
  };

  const sizeStyles = {
    sm: "text-xs px-2 py-0.5",
    md: "text-sm px-2.5 py-0.5",
    lg: "text-sm px-3 py-1",
  };

  const style = variantStyles[variant];
  const sizeStyle = sizeStyles[size];

  return (
    <span
      className={`inline-flex items-center justify-center rounded font-medium whitespace-nowrap ${sizeStyle} ${className}`}
      style={{
        background: style.bg,
        color: style.color,
        border: `1px solid ${style.border}`,
      }}
    >
      {children}
    </span>
  );
}

// Get occupancy color based on percentage
function getOccupancyColor(percent: number): string {
  if (percent > 70) return "var(--color-sentinel-red)";
  if (percent >= 40) return "var(--color-sentinel-amber)";
  if (percent >= 10) return "var(--color-sentinel-green)";
  return "var(--color-sentinel-text-disabled)";
}

// Get status badge variant based on occupancy status
function getStatusVariant(status: ZoneOccupancy["status"]): "error" | "warning" | "success" | "neutral" {
  switch (status) {
    case "busy": return "error";
    case "moderate": return "warning";
    case "quiet": return "success";
    case "empty": return "neutral";
    default: return "neutral";
  }
}

// Get status label
function getStatusLabel(status: ZoneOccupancy["status"]): string {
  switch (status) {
    case "busy": return "Busy";
    case "moderate": return "Moderate";
    case "quiet": return "Quiet";
    case "empty": return "Empty";
    default: return "Unknown";
  }
}

// Zone lighting data for energy waste detection
interface ZoneWithLighting extends ZoneOccupancy {
  lighting?: ZoneLighting;
}

interface ZoneCardProps {
  zone: ZoneWithLighting;
  onClick?: (zone: ZoneOccupancy) => void;
}

function ZoneCard({ zone, onClick }: ZoneCardProps) {
  const occupancyColor = getOccupancyColor(zone.occupancy_percent);
  const hasEnergyWaste = zone.lighting?.energy_waste_detected ||
    (zone.status === "empty" && zone.lighting && zone.lighting.total_power_watts > 100);
  const hasHighDaylight = zone.avg_lux_level > 500;

  return (
    <div
      className={`rounded-md p-3 transition-all ${onClick ? 'cursor-pointer hover:brightness-110' : ''}`}
      style={{
        background: "var(--color-sentinel-bg-secondary)",
        border: hasEnergyWaste
          ? "1px solid rgba(245, 158, 11, 0.5)"
          : "1px solid var(--color-sentinel-border)",
      }}
      onClick={() => onClick?.(zone)}
    >
      {/* Zone Header */}
      <div className="flex items-center justify-between mb-2">
        <span
          className="text-sm font-medium truncate"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          {zone.zone_name}
        </span>
        <SentinelBadge variant={getStatusVariant(zone.status)} size="sm">
          {getStatusLabel(zone.status)}
        </SentinelBadge>
      </div>

      {/* Occupancy Bar */}
      <div className="mb-2">
        <div
          className="h-2 rounded-full overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-primary)" }}
        >
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{
              width: `${Math.min(zone.occupancy_percent, 100)}%`,
              background: occupancyColor,
            }}
          />
        </div>
      </div>

      {/* Stats Row */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-1">
          <Users className="h-3.5 w-3.5" style={{ color: occupancyColor }} />
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {zone.occupied_sensors}/{zone.total_sensors}
          </span>
          <span
            className="ml-1 font-medium"
            style={{ color: occupancyColor }}
          >
            {zone.occupancy_percent}%
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Daylight indicator */}
          {hasHighDaylight && (
            <div className="flex items-center gap-0.5" title="High daylight available">
              <Sun className="h-3.5 w-3.5" style={{ color: "var(--color-sentinel-amber)" }} />
            </div>
          )}

          {/* Lux level */}
          <span
            style={{ color: "var(--color-sentinel-text-disabled)" }}
            title={`Light level: ${zone.avg_lux_level} lux`}
          >
            {zone.avg_lux_level} lux
          </span>
        </div>
      </div>

      {/* Energy Waste Alert */}
      {hasEnergyWaste && (
        <div
          className="mt-2 pt-2 flex items-center gap-1 text-xs"
          style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
        >
          <AlertTriangle className="h-3.5 w-3.5" style={{ color: "var(--color-sentinel-amber)" }} />
          <span style={{ color: "var(--color-sentinel-amber)" }}>
            {zone.lighting?.energy_waste_reason || "Empty zone with active lighting"}
          </span>
        </div>
      )}
    </div>
  );
}

interface FloorRowProps {
  floor: FloorSummary;
  zoneLighting?: Record<string, ZoneLighting>;
  onZoneClick?: (zone: ZoneOccupancy) => void;
}

function FloorRow({ floor, zoneLighting, onZoneClick }: FloorRowProps) {
  const floorOccupancyColor = getOccupancyColor(floor.occupancy_percent);

  return (
    <div
      className="rounded-md overflow-hidden mb-4"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      {/* Floor Header */}
      <div
        className="p-4 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded flex items-center justify-center text-sm font-bold"
            style={{
              background: `${floorOccupancyColor}20`,
              color: floorOccupancyColor,
            }}
          >
            {floor.floor}
          </div>
          <div>
            <span
              className="font-medium text-sm block"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {floor.floor_name || `Floor ${floor.floor}`}
            </span>
            <span
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {floor.total_zones} zones • {floor.total_sensors} sensors
            </span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Floor Occupancy */}
          <div className="text-right">
            <span
              className="text-lg font-bold block"
              style={{ color: floorOccupancyColor }}
            >
              {floor.occupancy_percent}%
            </span>
            <span
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              occupied
            </span>
          </div>

          {/* Power Usage */}
          <div className="text-right">
            <div className="flex items-center gap-1">
              <Zap className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
              <span
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {(floor.total_power_watts / 1000).toFixed(1)} kW
              </span>
            </div>
            {floor.faulty_luminaires > 0 && (
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-amber)" }}
              >
                {floor.faulty_luminaires} faulty
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Zone Grid */}
      <div className="p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {floor.zones.map((zone) => (
            <ZoneCard
              key={zone.zone_id}
              zone={{
                ...zone,
                lighting: zoneLighting?.[zone.zone_id],
              }}
              onClick={onZoneClick}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

interface OccupancyHeatmapProps {
  floors: FloorSummary[];
  zoneLighting?: Record<string, ZoneLighting>;
  onZoneClick?: (zone: ZoneOccupancy) => void;
  loading?: boolean;
}

export function OccupancyHeatmap({ floors, zoneLighting, onZoneClick, loading }: OccupancyHeatmapProps) {
  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="rounded-md animate-pulse"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div className="p-4" style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
              <div className="flex items-center gap-3">
                <div
                  className="w-10 h-10 rounded"
                  style={{ background: "var(--color-sentinel-bg-secondary)" }}
                />
                <div className="space-y-2">
                  <div
                    className="h-4 w-24 rounded"
                    style={{ background: "var(--color-sentinel-bg-secondary)" }}
                  />
                  <div
                    className="h-3 w-32 rounded"
                    style={{ background: "var(--color-sentinel-bg-secondary)" }}
                  />
                </div>
              </div>
            </div>
            <div className="p-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {[1, 2, 3, 4].map((j) => (
                  <div
                    key={j}
                    className="h-24 rounded"
                    style={{ background: "var(--color-sentinel-bg-secondary)" }}
                  />
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (floors.length === 0) {
    return (
      <div
        className="rounded-md p-8 text-center"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <Users
          className="h-12 w-12 mx-auto mb-3"
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        />
        <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
          No occupancy data available
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {floors.map((floor) => (
        <FloorRow
          key={floor.floor}
          floor={floor}
          zoneLighting={zoneLighting}
          onZoneClick={onZoneClick}
        />
      ))}
    </div>
  );
}

export default OccupancyHeatmap;

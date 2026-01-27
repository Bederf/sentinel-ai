/**
 * ControlPanel Component - SENTINEL device control panel
 *
 * Features:
 * - Grafana-style control panel for building devices
 * - Device status and safety indicators
 * - Control widgets for different point types
 * - Safety status integration
 * - Consistent with SENTINEL design system
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect } from "react";
import {
  Cpu,
  Thermometer,
  ToggleLeft,
  ToggleRight,
  Sliders,
  ChevronDown,
  AlertTriangle,
  Shield,
  CheckCircle,
  XCircle,
  RefreshCw,
} from "lucide-react";
import type { Device, DevicePoint } from "../lib/api";
import { TemperatureControl } from "./TemperatureControl";
import { SwitchControl } from "./SwitchControl";
import { SelectorControl } from "./SelectorControl";

interface ControlPanelProps {
  device: Device;
  onControl?: (deviceId: string, point: string, value: number | boolean) => Promise<void>;
  safetyStatus?: {
    status: "safe" | "warning" | "blocked";
    message?: string;
    rules?: Array<{ rule: string; status: string }>;
  };
  refreshInterval?: number;
}

/**
 * Get safety status configuration for SENTINEL styling
 */
function getSafetyStatusConfig(status: string): {
  color: string;
  bg: string;
  icon: React.ReactNode;
  label: string;
} {
  switch (status) {
    case "safe":
      return {
        color: "var(--color-sentinel-green)",
        bg: "rgba(16, 185, 129, 0.15)",
        icon: <CheckCircle className="h-4 w-4" />,
        label: "SAFE",
      };
    case "warning":
      return {
        color: "var(--color-sentinel-amber)",
        bg: "rgba(245, 158, 11, 0.15)",
        icon: <AlertTriangle className="h-4 w-4" />,
        label: "WARNING",
      };
    case "blocked":
      return {
        color: "var(--color-sentinel-red)",
        bg: "rgba(220, 38, 38, 0.15)",
        icon: <XCircle className="h-4 w-4" />,
        label: "BLOCKED",
      };
    default:
      return {
        color: "var(--color-sentinel-text-secondary)",
        bg: "rgba(142, 142, 142, 0.15)",
        icon: <Shield className="h-4 w-4" />,
        label: "UNKNOWN",
      };
  }
}

/**
 * Get device type icon
 */
function getDeviceTypeIcon(deviceType: string): React.ReactNode {
  switch (deviceType) {
    case "hvac":
      return <Thermometer className="h-5 w-5" />;
    case "lighting":
      return <Sliders className="h-5 w-5" />;
    case "security":
    case "fire_safety":
      return <Shield className="h-5 w-5" />;
    default:
      return <Cpu className="h-5 w-5" />;
  }
}

/**
 * Get device type label
 */
function getDeviceTypeLabel(deviceType: string): string {
  switch (deviceType) {
    case "hvac":
      return "HVAC";
    case "lighting":
      return "Lighting";
    case "security":
      return "Security";
    case "fire_safety":
      return "Fire Safety";
    default:
      return deviceType.charAt(0).toUpperCase() + deviceType.slice(1);
  }
}

export function ControlPanel({
  device,
  onControl,
  safetyStatus,
  refreshInterval = 10000,
}: ControlPanelProps) {
  const [expanded, setExpanded] = useState(true);
  const [pointValues, setPointValues] = useState<Record<string, number | boolean>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const safetyConfig = getSafetyStatusConfig(safetyStatus?.status || "safe");

  // Get writable points
  const writablePoints = Object.entries(device.points || {}).filter(
    ([_, point]) => point.writable
  );

  // Get readable points
  const readablePoints = Object.entries(device.points || {}).filter(
    ([_, point]) => !point.writable
  );

  // Handle control action
  const handleControl = async (point: string, value: number | boolean) => {
    if (!onControl) return;

    try {
      setLoading(true);
      setError(null);
      await onControl(device.id, point, value);

      // Update local state
      setPointValues((prev) => ({
        ...prev,
        [point]: value,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Control action failed");
      console.error("Control action failed:", err);
    } finally {
      setLoading(false);
    }
  };

  // Render control widget based on point type
  const renderControlWidget = (pointName: string, point: DevicePoint) => {
    const currentValue = pointValues[pointName] ?? point.default_value;
    const disabled = loading || safetyStatus?.status === "blocked";

    switch (point.point_type) {
      case "analog_value":
        return (
          <TemperatureControl
            key={pointName}
            label={point.description}
            unit={point.unit}
            value={currentValue as number}
            min={point.min_value}
            max={point.max_value}
            onChange={(value) => handleControl(pointName, value)}
            disabled={disabled}
            error={error}
          />
        );

      case "binary_value":
        return (
          <SwitchControl
            key={pointName}
            label={point.description}
            value={currentValue as boolean}
            onChange={(value) => handleControl(pointName, value)}
            disabled={disabled}
            error={error}
          />
        );

      case "multistate_value":
        const states = point.metadata?.states || {};
        const options = Object.entries(states).map(([key, label]) => ({
          value: parseInt(key),
          label: String(label),
        }));

        return (
          <SelectorControl
            key={pointName}
            label={point.description}
            value={currentValue as number}
            options={options}
            onChange={(value) => handleControl(pointName, value)}
            disabled={disabled}
            error={error}
          />
        );

      default:
        return (
          <div
            key={pointName}
            className="p-3 rounded"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div className="text-xs mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
              {point.description}
            </div>
            <div className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
              {String(currentValue)} {point.unit}
            </div>
            <div className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Read-only {point.point_type}
            </div>
          </div>
        );
    }
  };

  return (
    <div
      className="rounded-md overflow-hidden transition-all duration-150"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      {/* Top accent based on safety status */}
      <div
        className="h-1"
        style={{ background: safetyConfig.color }}
      />

      <div className="p-4 pt-5">
        {/* Header: Device info and safety status */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-start gap-3">
            <div
              className="p-2 rounded"
              style={{ background: "rgba(59, 130, 246, 0.15)" }}
            >
              {getDeviceTypeIcon(device.device_type)}
            </div>
            <div>
              <h3
                className="font-medium text-sm mb-1"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {device.name}
              </h3>
              <div className="flex items-center gap-2 text-xs">
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {device.location}
                </span>
                <span style={{ color: "var(--color-sentinel-text-disabled)" }}>•</span>
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {getDeviceTypeLabel(device.device_type)}
                </span>
                {device.manufacturer && (
                  <>
                    <span style={{ color: "var(--color-sentinel-text-disabled)" }}>•</span>
                    <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {device.manufacturer}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Safety status badge */}
          <div className="flex items-center gap-2">
            <div
              className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium"
              style={{
                background: safetyConfig.bg,
                color: safetyConfig.color,
              }}
            >
              {safetyConfig.icon}
              {safetyConfig.label}
            </div>
            <button
              onClick={() => setExpanded(!expanded)}
              className="p-1 rounded hover:brightness-110 transition-colors"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                color: "var(--color-sentinel-text-secondary)",
              }}
            >
              <ChevronDown
                className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`}
              />
            </button>
          </div>
        </div>

        {/* Safety warning message */}
        {safetyStatus?.message && safetyStatus.status !== "safe" && (
          <div
            className="p-3 rounded mb-4 flex items-start gap-2"
            style={{
              background: safetyConfig.bg,
              border: `1px solid ${safetyConfig.color}30`,
            }}
          >
            <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" style={{ color: safetyConfig.color }} />
            <div className="flex-1">
              <span
                className="text-xs font-medium"
                style={{ color: safetyConfig.color }}
              >
                Safety {safetyStatus.status === "warning" ? "Warning" : "Block"}
              </span>
              <p
                className="text-xs mt-0.5"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {safetyStatus.message}
              </p>
            </div>
          </div>
        )}

        {/* Error message */}
        {error && (
          <div
            className="p-3 rounded mb-4 flex items-start gap-2"
            style={{
              background: "rgba(220, 38, 38, 0.15)",
              border: "1px solid var(--color-sentinel-red)30",
            }}
          >
            <XCircle className="h-4 w-4 flex-shrink-0 mt-0.5" style={{ color: "var(--color-sentinel-red)" }} />
            <div className="flex-1">
              <span
                className="text-xs font-medium"
                style={{ color: "var(--color-sentinel-red)" }}
              >
                Control Error
              </span>
              <p
                className="text-xs mt-0.5"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {error}
              </p>
            </div>
          </div>
        )}

        {/* Expanded content */}
        {expanded && (
          <>
            {/* Device description */}
            {device.description && (
              <div
                className="p-3 rounded mb-4"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--color-sentinel-border)",
                }}
              >
                <p
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  {device.description}
                </p>
              </div>
            )}

            {/* Control widgets */}
            {writablePoints.length > 0 && (
              <div className="mb-6">
                <h4
                  className="font-medium text-xs mb-3 uppercase tracking-wider"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Controls
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {writablePoints.map(([pointName, point]) =>
                    renderControlWidget(pointName, point)
                  )}
                </div>
              </div>
            )}

            {/* Read-only points */}
            {readablePoints.length > 0 && (
              <div>
                <h4
                  className="font-medium text-xs mb-3 uppercase tracking-wider"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Monitoring
                </h4>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {readablePoints.map(([pointName, point]) => {
                    const currentValue = pointValues[pointName] ?? point.default_value;
                    return (
                      <div
                        key={pointName}
                        className="p-3 rounded"
                        style={{
                          background: "var(--color-sentinel-bg-secondary)",
                          border: "1px solid var(--color-sentinel-border)",
                        }}
                      >
                        <div
                          className="text-xs mb-1"
                          style={{ color: "var(--color-sentinel-text-disabled)" }}
                        >
                          {point.description}
                        </div>
                        <div
                          className="text-lg font-medium"
                          style={{
                            color: "var(--color-sentinel-text-primary)",
                            fontVariantNumeric: "tabular-nums",
                          }}
                        >
                          {String(currentValue)}
                          {point.unit && (
                            <span
                              className="text-xs ml-1"
                              style={{ color: "var(--color-sentinel-text-disabled)" }}
                            >
                              {point.unit}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Loading indicator */}
            {loading && (
              <div className="flex items-center justify-center py-4">
                <RefreshCw
                  className="h-5 w-5 animate-spin"
                  style={{ color: "var(--color-sentinel-amber)" }}
                />
                <span
                  className="text-xs ml-2"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Processing control action...
                </span>
              </div>
            )}
          </>
        )}

        {/* Footer: Device metadata */}
        {expanded && device.metadata && Object.keys(device.metadata).length > 0 && (
          <div
            className="pt-4 mt-4"
            style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
          >
            <div className="flex flex-wrap gap-2">
              {Object.entries(device.metadata).map(([key, value]) => (
                <span
                  key={key}
                  className="text-xs px-2 py-1 rounded"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    color: "var(--color-sentinel-text-secondary)",
                  }}
                >
                  {key}: {String(value)}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default ControlPanel;
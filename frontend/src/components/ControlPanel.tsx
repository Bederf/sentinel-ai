/**
 * ControlPanel Component - SENTINEL device control panel
 *
 * Features:
 * - Grafana-style control panel for building devices
 * - Device status and safety indicators
 * - Control widgets for different point types
 * - Confirmation modal before executing control actions
 * - Real-time feedback for control operations
 * - Safety status integration
 * - Consistent with SENTINEL design system
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useCallback } from "react";
import {
  Cpu,
  Thermometer,
  Sliders,
  ChevronDown,
  AlertTriangle,
  Shield,
  CheckCircle,
  XCircle,
} from "lucide-react";
import type { Device, DevicePoint } from '@/lib/api';
import type { ModuleType } from '@/lib/moduleRegistry';
import { useModules } from '@/contexts/ModuleHooks';
import { TemperatureControl } from "./TemperatureControl";
import { SwitchControl } from "./SwitchControl";
import { SelectorControl } from "./SelectorControl";
import { ControlConfirmModal } from "./ControlConfirmModal";
import { ControlFeedback, type FeedbackState } from "./ControlFeedback";
import { useControlAction, type ControlResult } from "../hooks/useControlAction";

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
 * Pending control action for confirmation modal
 */
interface PendingAction {
  pointName: string;
  point: DevicePoint;
  currentValue: number | boolean;
  newValue: number | boolean;
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

/**
 * Map a device to its controlling module based on device type/code.
 * Returns null if no control module applies.
 */
function getControlModuleForDevice(device: Device): ModuleType | null {
  const type = (device.device_type || '').toLowerCase();
  const code = (device.id || device.name || '').toLowerCase();
  if (/hvac|ahu|fcu|chiller|cooling|vav|crac/i.test(type) || /ahu|fcu|chiller|vav|ct-/i.test(code)) return 'hvac_control';
  if (/dali|lighting|luminaire|lum/i.test(type) || /dali|lum/i.test(code)) return 'lighting_control';
  if (/solar|inverter|bess|battery/i.test(type) || /inv-|bess/i.test(code)) return 'solar_control';
  if (/generator|ups|ats|meter/i.test(type) || /gen-|ups|ats|mtr/i.test(code)) return 'energy_control';
  if (/water|pump|tank|valve/i.test(type) || /pump|tank/i.test(code)) return 'water_control';
  if (/door|cctv|access|security/i.test(type) || /acc-|cctv/i.test(code)) return 'security_control';
  return null;
}

export function ControlPanel({
  device,
  onControl,
  safetyStatus,
  refreshInterval: _refreshInterval = 10000,
}: ControlPanelProps) {
  const [expanded, setExpanded] = useState(true);
  const [pointValues, setPointValues] = useState<Record<string, number | boolean>>({});
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const { isModuleActive } = useModules();

  // Check if write controls are allowed for this device's discipline
  const controlModule = getControlModuleForDevice(device);
  const writeEnabled = controlModule ? isModuleActive(controlModule) : false;

  // Use the control action hook
  const {
    isExecuting,
    result,
    error,
    executeControl,
    clearResult,
    retry,
  } = useControlAction({
    onSuccess: (controlResult: ControlResult) => {
      // Update local state on success
      setPointValues((prev) => ({
        ...prev,
        [controlResult.point]: controlResult.value,
      }));
    },
  });

  const safetyConfig = getSafetyStatusConfig(safetyStatus?.status || "safe");

  // Determine feedback state
  const getFeedbackState = (): FeedbackState => {
    if (isExecuting) return "pending";
    if (result) return "success";
    if (error) return "error";
    return "idle";
  };

  // Get writable points
  const writablePoints = Object.entries(device.points || {}).filter(
    ([_, point]) => point.writable
  );

  // Get readable points
  const readablePoints = Object.entries(device.points || {}).filter(
    ([_, point]) => !point.writable
  );

  // Handle control request - direct action for toggles, confirmation for analog values
  const handleControlRequest = useCallback(async (
    pointName: string,
    point: DevicePoint,
    newValue: number | boolean
  ) => {
    // Priority: local state > current_value from adapter > default_value
    const currentValue = pointValues[pointName] ?? point.current_value ?? point.default_value;

    // Don't act if value hasn't changed
    if (currentValue === newValue) return;

    // For binary values (toggles), execute immediately without confirmation
    if (point.point_type === "binary_value") {
      if (onControl) {
        try {
          await onControl(device.id, pointName, newValue);
          setPointValues((prev) => ({
            ...prev,
            [pointName]: newValue,
          }));
        } catch (err) {
          console.error("Control action failed:", err);
        }
      } else {
        await executeControl(device.id, pointName, newValue);
      }
      return;
    }

    // For analog/multistate values, show confirmation modal
    setPendingAction({
      pointName,
      point,
      currentValue,
      newValue,
    });
  }, [pointValues, device.id, onControl, executeControl]);

  // Handle confirmation
  const handleConfirm = useCallback(async () => {
    if (!pendingAction) return;

    const { pointName, newValue } = pendingAction;
    setPendingAction(null);

    // Use external onControl if provided, otherwise use the hook
    if (onControl) {
      try {
        await onControl(device.id, pointName, newValue);
        setPointValues((prev) => ({
          ...prev,
          [pointName]: newValue,
        }));
      } catch (err) {
        console.error("Control action failed:", err);
      }
    } else {
      await executeControl(device.id, pointName, newValue);
    }
  }, [pendingAction, device.id, onControl, executeControl]);

  // Handle cancel
  const handleCancel = useCallback(() => {
    setPendingAction(null);
  }, []);

  // Render control widget based on point type
  const renderControlWidget = (pointName: string, point: DevicePoint) => {
    // Priority: local state > current_value from adapter > default_value
    const currentValue = pointValues[pointName] ?? point.current_value ?? point.default_value;
    const disabled = isExecuting || safetyStatus?.status === "blocked";

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
            onChange={(value) => handleControlRequest(pointName, point, value)}
            disabled={disabled}
          />
        );

      case "binary_value":
        return (
          <SwitchControl
            key={pointName}
            label={point.description}
            value={currentValue as boolean}
            onChange={(value) => handleControlRequest(pointName, point, value)}
            disabled={disabled}
          />
        );

      case "multistate_value": {
        // Handle states as array (from backend) or object (legacy)
        const statesData = (point as unknown as { states?: string[] }).states || point.metadata?.states || [];
        const options = Array.isArray(statesData)
          ? statesData.map((label: string, index: number) => ({
              value: index,
              label: String(label),
            }))
          : Object.entries(statesData).map(([key, label]) => ({
              value: parseInt(key),
              label: String(label),
            }));

        return (
          <SelectorControl
            key={pointName}
            label={point.description}
            value={currentValue as number}
            options={options}
            onChange={(value) => handleControlRequest(pointName, point, value)}
            disabled={disabled}
          />
        );
      }

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
    <>
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
                  <span style={{ color: "var(--color-sentinel-text-disabled)" }}>-</span>
                  <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {getDeviceTypeLabel(device.device_type)}
                  </span>
                  {device.manufacturer && (
                    <>
                      <span style={{ color: "var(--color-sentinel-text-disabled)" }}>-</span>
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

          {/* Control feedback */}
          <ControlFeedback
            state={getFeedbackState()}
            result={result}
            error={error}
            onRetry={retry}
            onDismiss={clearResult}
          />

          {/* Expanded content */}
          {expanded && (
            <>
              {/* Device description */}
              {device.description && (
                <div
                  className="p-3 rounded mb-4 mt-4"
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

              {/* Control widgets — gated by discipline control module */}
              {writeEnabled && writablePoints.length > 0 && (
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
                    className="font-medium text-xs mb-3 uppercase tracking-wider flex items-center gap-2"
                    style={{ color: "var(--color-sentinel-amber)" }}
                  >
                    <span className="w-2 h-2 rounded-full" style={{ background: "var(--color-sentinel-amber)" }} />
                    Live Readings (Read Only)
                  </h4>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    {readablePoints.map(([pointName, point]) => {
                      const currentValue = pointValues[pointName] ?? point.default_value;
                      return (
                        <div
                          key={pointName}
                          className="p-3 rounded"
                          style={{
                            background: "rgba(245, 158, 11, 0.1)",
                            border: "1px solid rgba(245, 158, 11, 0.3)",
                          }}
                        >
                          <div
                            className="text-xs mb-1 flex items-center gap-1"
                            style={{ color: "var(--color-sentinel-amber)" }}
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-current" />
                            {point.description}
                          </div>
                          <div
                            className="text-lg font-medium"
                            style={{
                              color: "var(--color-sentinel-amber)",
                              fontVariantNumeric: "tabular-nums",
                            }}
                          >
                            {String(currentValue)}
                            {point.unit && (
                              <span
                                className="text-xs ml-1"
                                style={{ color: "var(--color-sentinel-amber)", opacity: 0.7 }}
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

      {/* Confirmation Modal */}
      {pendingAction && (
        <ControlConfirmModal
          isOpen={true}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
          deviceName={device.name}
          point={pendingAction.pointName}
          pointDescription={pendingAction.point.description}
          currentValue={pendingAction.currentValue}
          newValue={pendingAction.newValue}
          unit={pendingAction.point.unit}
          safetyStatus={safetyStatus}
          confirmDisabled={isExecuting}
        />
      )}
    </>
  );
}

export default ControlPanel;

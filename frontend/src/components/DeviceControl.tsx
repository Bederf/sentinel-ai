/**
 * DeviceControl Component - SENTINEL individual device control widgets
 *
 * Features:
 * - Reusable control widgets for different point types
 * - Consistent styling with ControlPanel
 * - Error handling and validation
 * - Grafana-style design
 *
 * Follows SENTINEL dark theme design.
 */

import { TemperatureControl } from "./TemperatureControl";
import { SwitchControl } from "./SwitchControl";
import { SelectorControl } from "./SelectorControl";
import { ChillerToggleControl } from "./ChillerToggleControl";
import type { DevicePoint } from '@/lib/api';

interface DeviceControlProps {
  point: DevicePoint;
  value: number | boolean;
  onChange: (value: number | boolean) => void;
  disabled?: boolean;
  error?: string | null;
}

export function DeviceControl({
  point,
  value,
  onChange,
  disabled = false,
  error = null,
}: DeviceControlProps) {
  // Render appropriate control based on point type
  switch (point.point_type) {
    case "analog_value":
      return (
        <TemperatureControl
          label={point.description}
          unit={point.unit}
          value={value as number}
          min={point.min_value}
          max={point.max_value}
          step={1}
          onChange={(val) => onChange(val)}
          disabled={disabled}
          error={error}
        />
      );

    case "binary_value":
      return (
        <SwitchControl
          label={point.description}
          value={value as boolean}
          onChange={(val) => onChange(val)}
          disabled={disabled}
          error={error}
        />
      );

    case "multistate_value": {
      // Special handling for chiller status points
      if (point.name.toLowerCase().includes('chiller_status') ||
          point.description.toLowerCase().includes('chiller operational status')) {
        return (
          <ChillerToggleControl
            deviceId={point.device_id || ''}
            point={{
              id: point.id || '',
              name: point.name,
              value: value as number,
              type: point.point_type,
              unit: point.unit,
              min_value: point.min_value,
              max_value: point.max_value,
              states: point.metadata?.states
            }}
            onUpdate={(val) => onChange(val)}
            disabled={disabled}
          />
        );
      }

      // Default multistate selector for other points
      const states = point.metadata?.states || {};
      const options = Object.entries(states).map(([key, label]) => ({
        value: parseInt(key),
        label: String(label),
      }));

      return (
        <SelectorControl
          label={point.description}
          value={value as number}
          options={options}
          onChange={(val) => onChange(val)}
          disabled={disabled}
          error={error}
        />
      );
    }

    default:
      // Read-only display for non-writable points
      return (
        <div
          className="p-4 rounded"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
            opacity: disabled ? 0.6 : 1,
          }}
        >
          <div className="flex items-center justify-between mb-2">
            <span
              className="text-xs font-medium"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {point.description}
            </span>
            {disabled && (
              <span
                className="text-xs px-2 py-1 rounded"
                style={{
                  background: "rgba(142, 142, 142, 0.15)",
                  color: "var(--color-sentinel-text-disabled)",
                }}
              >
                Read-only
              </span>
            )}
          </div>

          <div className="flex items-baseline gap-1">
            <span
              className="text-2xl font-bold"
              style={{
                color: disabled
                  ? "var(--color-sentinel-text-disabled)"
                  : "var(--color-sentinel-text-primary)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {String(value)}
            </span>
            {point.unit && (
              <span
                className="text-sm"
                style={{
                  color: disabled
                    ? "var(--color-sentinel-text-disabled)"
                    : "var(--color-sentinel-text-secondary)",
                }}
              >
                {point.unit}
              </span>
            )}
          </div>

          <div className="mt-2">
            <span
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              {point.point_type} • {point.writable ? "Writable" : "Read-only"}
            </span>
          </div>
        </div>
      );
  }
}

export default DeviceControl;

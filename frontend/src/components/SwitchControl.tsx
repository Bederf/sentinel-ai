/**
 * SwitchControl Component - SENTINEL binary switch control widget
 *
 * Features:
 * - Toggle switch for on/off control
 * - Visual feedback for state changes
 * - Grafana-style design
 *
 * Follows SENTINEL dark theme design.
 */

import { useState } from "react";
import { Power, PowerOff } from "lucide-react";

interface SwitchControlProps {
  label: string;
  value: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
  error?: string | null;
}

export function SwitchControl({
  label,
  value,
  onChange,
  disabled = false,
  error = null,
}: SwitchControlProps) {
  const [isAnimating, setIsAnimating] = useState(false);

  // Handle toggle
  const handleToggle = () => {
    if (disabled) return;

    setIsAnimating(true);
    const newValue = !value;
    onChange(newValue);

    // Reset animation state
    setTimeout(() => setIsAnimating(false), 300);
  };

  return (
    <div
      className="p-4 rounded transition-all duration-150"
      style={{
        background: "var(--color-sentinel-bg-secondary)",
        border: `1px solid ${error ? "var(--color-sentinel-red)" : "var(--color-sentinel-border)"}`,
        opacity: disabled ? 0.6 : 1,
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          {value ? (
            <Power
              className="h-4 w-4"
              style={{ color: "var(--color-sentinel-green)" }}
            />
          ) : (
            <PowerOff
              className="h-4 w-4"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            />
          )}
          <span
            className="text-xs font-medium"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            {label}
          </span>
        </div>
        {disabled && (
          <span
            className="text-xs px-2 py-1 rounded"
            style={{
              background: "rgba(142, 142, 142, 0.15)",
              color: "var(--color-sentinel-text-disabled)",
            }}
          >
            Disabled
          </span>
        )}
      </div>

      {/* Error message */}
      {error && (
        <div
          className="mb-4 p-2 rounded text-xs"
          style={{
            background: "rgba(220, 38, 38, 0.15)",
            color: "var(--color-sentinel-red)",
          }}
        >
          {error}
        </div>
      )}

      {/* Toggle switch */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span
            className="text-xs"
            style={{
              color: value
                ? "var(--color-sentinel-text-disabled)"
                : "var(--color-sentinel-text-primary)",
            }}
          >
            OFF
          </span>

          {/* Toggle button */}
          <button
            onClick={handleToggle}
            disabled={disabled}
            className={`relative w-14 h-7 rounded-full transition-all duration-300 ${isAnimating ? "scale-105" : ""}`}
            style={{
              background: value
                ? "var(--color-sentinel-green)"
                : "var(--color-sentinel-border)",
              cursor: disabled ? "not-allowed" : "pointer",
            }}
          >
            {/* Toggle knob */}
            <div
              className={`absolute top-1 w-5 h-5 rounded-full bg-white transition-all duration-300 ${value ? "left-8" : "left-1"}`}
              style={{
                boxShadow: "0 1px 3px rgba(0, 0, 0, 0.3)",
              }}
            />
          </button>

          <span
            className="text-xs"
            style={{
              color: value
                ? "var(--color-sentinel-text-primary)"
                : "var(--color-sentinel-text-disabled)",
            }}
          >
            ON
          </span>
        </div>

        {/* Status badge */}
        <div
          className="px-3 py-1 rounded text-xs font-medium"
          style={{
            background: value
              ? "rgba(16, 185, 129, 0.15)"
              : "rgba(142, 142, 142, 0.15)",
            color: value
              ? "var(--color-sentinel-green)"
              : "var(--color-sentinel-text-disabled)",
          }}
        >
          {value ? "ACTIVE" : "INACTIVE"}
        </div>
      </div>

      {/* State description */}
      <div className="mt-4">
        <p
          className="text-xs"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          {value
            ? "Device is currently active and running."
            : "Device is currently inactive or in standby mode."}
        </p>
      </div>
    </div>
  );
}

export default SwitchControl;
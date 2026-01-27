/**
 * SelectorControl Component - SENTINEL dropdown selector control widget
 *
 * Features:
 * - Dropdown for mode/state selection
 * - Visual feedback for current selection
 * - Grafana-style design
 *
 * Follows SENTINEL dark theme design.
 */

import { useState } from "react";
import { ChevronDown, Settings } from "lucide-react";

interface SelectorOption {
  value: number;
  label: string;
}

interface SelectorControlProps {
  label: string;
  value: number;
  options: SelectorOption[];
  onChange: (value: number) => void;
  disabled?: boolean;
  error?: string | null;
}

export function SelectorControl({
  label,
  value,
  options,
  onChange,
  disabled = false,
  error = null,
}: SelectorControlProps) {
  const [isOpen, setIsOpen] = useState(false);

  // Find current option
  const currentOption = options.find((opt) => opt.value === value) || options[0];

  // Handle option selection
  const handleSelect = (optionValue: number) => {
    if (disabled) return;
    onChange(optionValue);
    setIsOpen(false);
  };

  // Get color for option
  const getOptionColor = (optionValue: number) => {
    if (disabled) return "var(--color-sentinel-text-disabled)";

    switch (optionValue) {
      case 0: // off/standby
        return "var(--color-sentinel-text-disabled)";
      case 1: // running/normal
        return "var(--color-sentinel-green)";
      case 2: // alarm/fault
        return "var(--color-sentinel-red)";
      case 3: // maintenance
        return "var(--color-sentinel-amber)";
      default:
        return "var(--color-sentinel-blue)";
    }
  };

  // Get background color for option
  const getOptionBgColor = (optionValue: number) => {
    if (disabled) return "rgba(142, 142, 142, 0.15)";

    switch (optionValue) {
      case 0: // off/standby
        return "rgba(142, 142, 142, 0.15)";
      case 1: // running/normal
        return "rgba(16, 185, 129, 0.15)";
      case 2: // alarm/fault
        return "rgba(220, 38, 38, 0.15)";
      case 3: // maintenance
        return "rgba(245, 158, 11, 0.15)";
      default:
        return "rgba(59, 130, 246, 0.15)";
    }
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
          <Settings
            className="h-4 w-4"
            style={{ color: "var(--color-sentinel-blue)" }}
          />
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

      {/* Current selection */}
      <div className="relative">
        <button
          onClick={() => !disabled && setIsOpen(!isOpen)}
          disabled={disabled}
          className="w-full flex items-center justify-between p-3 rounded transition-colors"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
            cursor: disabled ? "not-allowed" : "pointer",
          }}
        >
          <div className="flex items-center gap-3">
            <div
              className="w-2 h-2 rounded-full"
              style={{
                background: getOptionColor(value),
              }}
            />
            <span
              className="text-sm font-medium"
              style={{
                color: disabled
                  ? "var(--color-sentinel-text-disabled)"
                  : "var(--color-sentinel-text-primary)",
              }}
            >
              {currentOption.label}
            </span>
          </div>
          <ChevronDown
            className={`h-4 w-4 transition-transform ${isOpen ? "rotate-180" : ""}`}
            style={{
              color: disabled
                ? "var(--color-sentinel-text-disabled)"
                : "var(--color-sentinel-text-secondary)",
            }}
          />
        </button>

        {/* Dropdown options */}
        {isOpen && !disabled && (
          <div
            className="absolute top-full left-0 right-0 mt-1 rounded overflow-hidden z-10"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
              boxShadow: "0 4px 12px rgba(0, 0, 0, 0.15)",
            }}
          >
            {options.map((option) => (
              <button
                key={option.value}
                onClick={() => handleSelect(option.value)}
                className="w-full flex items-center gap-3 p-3 text-left transition-colors hover:brightness-110"
                style={{
                  background:
                    option.value === value
                      ? getOptionBgColor(option.value)
                      : "transparent",
                  borderBottom: "1px solid var(--color-sentinel-border)",
                }}
              >
                <div
                  className="w-2 h-2 rounded-full"
                  style={{
                    background: getOptionColor(option.value),
                  }}
                />
                <div className="flex-1">
                  <span
                    className="text-sm font-medium"
                    style={{
                      color: getOptionColor(option.value),
                    }}
                  >
                    {option.label}
                  </span>
                </div>
                {option.value === value && (
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{
                      background: getOptionColor(option.value),
                    }}
                  />
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Option descriptions */}
      <div className="mt-4">
        <div className="grid grid-cols-2 gap-2">
          {options.slice(0, 4).map((option) => (
            <div
              key={option.value}
              className="p-2 rounded text-xs"
              style={{
                background: getOptionBgColor(option.value),
                border: `1px solid ${getOptionColor(option.value)}30`,
              }}
            >
              <div
                className="font-medium mb-0.5"
                style={{
                  color: getOptionColor(option.value),
                }}
              >
                {option.label}
              </div>
              <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {getOptionDescription(option.value)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Helper function to get option descriptions
function getOptionDescription(value: number): string {
  switch (value) {
    case 0:
      return "Device is off or in standby";
    case 1:
      return "Device is running normally";
    case 2:
      return "Device has an alarm or fault";
    case 3:
      return "Device is in maintenance mode";
    default:
      return "Custom operating mode";
  }
}

export default SelectorControl;
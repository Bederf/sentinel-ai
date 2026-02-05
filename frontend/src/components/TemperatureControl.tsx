/**
 * TemperatureControl Component - SENTINEL temperature control widget
 *
 * Features:
 * - Slider for temperature setpoint adjustment
 * - Numeric input with validation
 * - Min/max limits with visual indicators
 * - Grafana-style design
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect } from "react";
import { Thermometer } from "lucide-react";

interface TemperatureControlProps {
  label: string;
  unit: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  error?: string | null;
}

export function TemperatureControl({
  label,
  unit,
  value,
  min = 0,
  max = 100,
  step = 1,
  onChange,
  disabled = false,
  error = null,
}: TemperatureControlProps) {
  const [inputValue, setInputValue] = useState(value.toString());
  const [isEditing, setIsEditing] = useState(false);
  const [sliderValue, setSliderValue] = useState(value);
  const [isDragging, setIsDragging] = useState(false);

  // Sync inputValue and sliderValue when value prop changes externally
  // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional prop sync
  useEffect(() => {
    if (!isEditing) {
      setInputValue(value.toString());
    }
    if (!isDragging) {
      setSliderValue(value);
    }
  }, [value, isEditing, isDragging]);

  // Handle slider change - update local state during drag
  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = parseInt(e.target.value, 10);
    if (!isNaN(newValue)) {
      setSliderValue(newValue);
      setInputValue(newValue.toString());
    }
  };

  // Handle slider drag start
  const handleSliderMouseDown = () => {
    setIsDragging(true);
  };

  // Handle slider release - trigger onChange with final value
  const handleSliderMouseUp = () => {
    setIsDragging(false);
    if (sliderValue !== value) {
      onChange(sliderValue);
    }
  };

  // Handle input change
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
  };

  // Handle input blur - validate and apply (use integer)
  const handleInputBlur = () => {
    setIsEditing(false);
    const newValue = parseInt(inputValue, 10);
    if (!isNaN(newValue)) {
      // Clamp value to min/max
      const clampedValue = Math.max(min, Math.min(max, newValue));
      onChange(clampedValue);
      setInputValue(clampedValue.toString());
    } else {
      // Reset to current value if invalid
      setInputValue(value.toString());
    }
  };

  // Handle input focus
  const handleInputFocus = () => {
    setIsEditing(true);
  };

  // Handle key press (Enter to apply)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      handleInputBlur();
    }
  };

  // Calculate slider background gradient using local slider value for smooth dragging
  const sliderPercentage = ((sliderValue - min) / (max - min)) * 100;

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
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Thermometer
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
        <div className="flex items-center gap-1">
          <span
            className="text-xs"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            {min}
          </span>
          <span
            className="text-xs"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            {unit}
          </span>
          <span
            className="text-xs"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            {max}
          </span>
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div
          className="mb-3 p-2 rounded text-xs"
          style={{
            background: "rgba(220, 38, 38, 0.15)",
            color: "var(--color-sentinel-red)",
          }}
        >
          {error}
        </div>
      )}

      {/* Value display and input */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-baseline gap-1">
          <input
            type="text"
            value={isEditing ? inputValue : (isDragging ? sliderValue.toString() : value.toString())}
            onChange={handleInputChange}
            onBlur={handleInputBlur}
            onFocus={handleInputFocus}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            className="bg-transparent border-none outline-none text-2xl font-bold w-20"
            style={{
              color: disabled
                ? "var(--color-sentinel-text-disabled)"
                : "var(--color-sentinel-text-primary)",
              fontVariantNumeric: "tabular-nums",
            }}
          />
          <span
            className="text-sm"
            style={{
              color: disabled
                ? "var(--color-sentinel-text-disabled)"
                : "var(--color-sentinel-text-secondary)",
            }}
          >
            {unit}
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

      {/* Slider */}
      <div className="relative mb-2">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={sliderValue}
          onChange={handleSliderChange}
          onMouseDown={handleSliderMouseDown}
          onMouseUp={handleSliderMouseUp}
          onTouchStart={handleSliderMouseDown}
          onTouchEnd={handleSliderMouseUp}
          disabled={disabled}
          className="w-full h-2 appearance-none rounded-full cursor-pointer"
          style={{
            background: `linear-gradient(to right, var(--color-sentinel-blue) 0%, var(--color-sentinel-blue) ${sliderPercentage}%, var(--color-sentinel-border) ${sliderPercentage}%, var(--color-sentinel-border) 100%)`,
            opacity: disabled ? 0.5 : 1,
          }}
        />
        <div
          className="absolute top-1/2 h-4 w-4 rounded-full pointer-events-none -translate-x-1/2 -translate-y-1/2"
          style={{
            left: `${sliderPercentage}%`,
            background: disabled
              ? "var(--color-sentinel-text-disabled)"
              : "var(--color-sentinel-blue)",
          }}
        />
      </div>

      {/* Min/Max labels */}
      <div className="flex justify-between text-xs">
        <span style={{ color: "var(--color-sentinel-text-disabled)" }}>
          Min: {min}
        </span>
        <span style={{ color: "var(--color-sentinel-text-disabled)" }}>
          Max: {max}
        </span>
      </div>
    </div>
  );
}

export default TemperatureControl;
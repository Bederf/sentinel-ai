import { useState } from 'react';
import { Power, PowerOff } from 'lucide-react';
import { useControlAction } from '../hooks/useControlAction';

interface ChillerToggleControlProps {
  deviceId: string;
  point: {
    id: string;
    name: string;
    value: number;
    type: string;
    unit?: string;
    min_value?: number;
    max_value?: number;
    states?: { [key: number]: string };
  };
  onUpdate?: (value: number) => void;
  disabled?: boolean;
}

export function ChillerToggleControl({ deviceId, point, onUpdate, disabled = false }: ChillerToggleControlProps) {
  // Map multistate values to binary on/off
  // 1 = running (ON), all others = OFF
  const isOn = point.value === 1;
  const [isAnimating, setIsAnimating] = useState(false);

  const { isExecuting, error, executeControl } = useControlAction();

  // Handle toggle with optimistic update
  const handleToggle = async () => {
    if (disabled || isExecuting) return;

    setIsAnimating(true);
    const newValue = isOn ? 0 : 1; // Toggle between off(0) and running(1)

    try {
      const result = await executeControl(deviceId, point.name, newValue);
      if (result?.success) {
        onUpdate?.(newValue);
      }
    } catch (err) {
      console.error('Failed to toggle chiller:', err);
    } finally {
      setTimeout(() => setIsAnimating(false), 300);
    }
  };

  // Display states for user feedback
  const getDisplayState = () => {
    if (isExecuting) {
      return isOn ? 'Turning Off...' : 'Turning On...';
    }

    switch (point.value) {
      case 0:
        return 'Off';
      case 1:
        return 'On';
      case 2:
        return 'Off (Alarm)';
      case 3:
        return 'Off (Maintenance)';
      default:
        return 'Off';
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
          {isOn ? (
            <Power
              className="h-4 w-4"
              style={{ color: "var(--color-sentinel-green)" }}
            />
          ) : (
            <PowerOff
              className="h-4 w-4"
              style={{ color: "var(--color-sentinel-red)" }}
            />
          )}
          <span
            className="text-xs font-medium"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Chiller
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
              color: isOn
                ? "var(--color-sentinel-text-disabled)"
                : "var(--color-sentinel-red)",
            }}
          >
            OFF
          </span>

          {/* Toggle button */}
          <button
            onClick={handleToggle}
            disabled={disabled || isExecuting}
            className={`relative w-14 h-7 rounded-full transition-all duration-300 ${isAnimating ? "scale-105" : ""}`}
            style={{
              background: isOn
                ? "var(--color-sentinel-green)"
                : "var(--color-sentinel-red)",
              cursor: disabled || isExecuting ? "not-allowed" : "pointer",
            }}
          >
            {/* Toggle knob */}
            <div
              className={`absolute top-1 w-5 h-5 rounded-full bg-white transition-all duration-300 ${isOn ? "left-8" : "left-1"}`}
              style={{
                boxShadow: "0 1px 3px rgba(0, 0, 0, 0.3)",
              }}
            />
          </button>

          <span
            className="text-xs"
            style={{
              color: isOn
                ? "var(--color-sentinel-green)"
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
            background: isOn
              ? "rgba(16, 185, 129, 0.15)"
              : "rgba(220, 38, 38, 0.15)",
            color: isOn
              ? "var(--color-sentinel-green)"
              : "var(--color-sentinel-red)",
          }}
        >
          {getDisplayState()}
        </div>
      </div>
    </div>
  );
}

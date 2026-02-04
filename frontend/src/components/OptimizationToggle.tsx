/**
 * OptimizationToggle Component - Enable/disable AI optimization toggle
 *
 * iOS-style toggle switch for controlling AI optimization per building.
 * Shows loading state during API calls and provides visual feedback.
 *
 * Features:
 * - Toggle switch with smooth animation
 * - Status text (Enabled/Disabled)
 * - Tooltip with description
 * - Loading state during API calls
 * - Error handling with toast notifications
 */

import { useState } from "react";
import api from "../lib/api";

interface OptimizationToggleProps {
  siteId: string;
  enabled: boolean;
  onToggle?: (enabled: boolean) => void;
  disabled?: boolean;
  className?: string;
}

export function OptimizationToggle({
  siteId,
  enabled,
  onToggle,
  disabled = false,
  className = "",
}: OptimizationToggleProps) {
  const [loading, setLoading] = useState(false);
  const [currentEnabled, setCurrentEnabled] = useState(enabled);

  const handleToggle = async () => {
    if (loading || disabled) return;

    const newEnabled = !currentEnabled;
    setLoading(true);

    try {
      // Call API to toggle optimization
      const result = await api.toggleOptimization(siteId, newEnabled);

      // Update local state
      setCurrentEnabled(result.optimization_enabled);

      // Call parent callback if provided
      if (onToggle) {
        onToggle(result.optimization_enabled);
      }
    } catch (error) {
      console.error("Failed to toggle optimization:", error);
      // Revert to original state on error
      // Note: In production, you'd show a toast notification here
      alert("Failed to update optimization setting. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const bgColor = currentEnabled
    ? "var(--color-sentinel-green)"
    : "var(--color-sentinel-text-secondary)";

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <span
        className="text-xs whitespace-nowrap"
        style={{ color: "var(--color-sentinel-text-secondary)" }}
      >
        {currentEnabled ? "Auto" : "Supervised"}
      </span>

      <button
        type="button"
        onClick={handleToggle}
        disabled={loading || disabled}
        className="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-offset-2"
        style={{
          backgroundColor: bgColor,
          opacity: loading || disabled ? 0.5 : 1,
          cursor: loading || disabled ? "not-allowed" : "pointer",
        }}
        title={
          loading
            ? "Updating..."
            : disabled
            ? "Cannot modify optimization settings"
            : currentEnabled
            ? "Switch to supervised mode (requires human approval)"
            : "Switch to automatic mode (AI auto-applies changes)"
        }
        role="switch"
        aria-checked={currentEnabled}
      >
        <span
          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
            currentEnabled ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}

export default OptimizationToggle;

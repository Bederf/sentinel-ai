/**
 * ControlStatus Component - SENTINEL safety status indicators
 *
 * Features:
 * - Visual safety status indicators (safe/warning/blocked)
 * - Safety rule violations display
 * - Grafana-style design
 *
 * Follows SENTINEL dark theme design.
 */

import { AlertTriangle, CheckCircle, XCircle, Shield, Info } from "lucide-react";

interface ControlStatusProps {
  status: "safe" | "warning" | "blocked";
  message?: string;
  rules?: Array<{
    rule: string;
    status: "passed" | "warning" | "failed";
    description?: string;
  }>;
  deviceType?: string;
  lastValidated?: string;
}

/**
 * Get safety status configuration
 */
function getSafetyStatusConfig(status: string): {
  color: string;
  bg: string;
  icon: React.ReactNode;
  label: string;
  description: string;
} {
  switch (status) {
    case "safe":
      return {
        color: "var(--color-sentinel-green)",
        bg: "rgba(16, 185, 129, 0.15)",
        icon: <CheckCircle className="h-5 w-5" />,
        label: "SAFE",
        description: "All safety rules passed",
      };
    case "warning":
      return {
        color: "var(--color-sentinel-amber)",
        bg: "rgba(245, 158, 11, 0.15)",
        icon: <AlertTriangle className="h-5 w-5" />,
        label: "WARNING",
        description: "Safety warnings detected",
      };
    case "blocked":
      return {
        color: "var(--color-sentinel-red)",
        bg: "rgba(220, 38, 38, 0.15)",
        icon: <XCircle className="h-5 w-5" />,
        label: "BLOCKED",
        description: "Safety violations detected",
      };
    default:
      return {
        color: "var(--color-sentinel-text-secondary)",
        bg: "rgba(142, 142, 142, 0.15)",
        icon: <Shield className="h-5 w-5" />,
        label: "UNKNOWN",
        description: "Safety status unknown",
      };
  }
}

/**
 * Get rule status configuration
 */
function getRuleStatusConfig(status: string): {
  color: string;
  icon: React.ReactNode;
} {
  switch (status) {
    case "passed":
      return {
        color: "var(--color-sentinel-green)",
        icon: <CheckCircle className="h-3 w-3" />,
      };
    case "warning":
      return {
        color: "var(--color-sentinel-amber)",
        icon: <AlertTriangle className="h-3 w-3" />,
      };
    case "failed":
      return {
        color: "var(--color-sentinel-red)",
        icon: <XCircle className="h-3 w-3" />,
      };
    default:
      return {
        color: "var(--color-sentinel-text-secondary)",
        icon: <Info className="h-3 w-3" />,
      };
  }
}

export function ControlStatus({
  status,
  message,
  rules = [],
  deviceType,
  lastValidated,
}: ControlStatusProps) {
  const safetyConfig = getSafetyStatusConfig(status);

  return (
    <div
      className="rounded-md overflow-hidden"
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

      <div className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-start gap-3">
            <div
              className="p-2 rounded"
              style={{ background: safetyConfig.bg }}
            >
              {safetyConfig.icon}
            </div>
            <div>
              <h3
                className="font-medium text-sm mb-1"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Safety Status
              </h3>
              <div className="flex items-center gap-2">
                <span
                  className="text-xs font-medium px-2 py-0.5 rounded"
                  style={{
                    background: safetyConfig.bg,
                    color: safetyConfig.color,
                  }}
                >
                  {safetyConfig.label}
                </span>
                {deviceType && (
                  <span
                    className="text-xs px-2 py-0.5 rounded"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      color: "var(--color-sentinel-text-secondary)",
                    }}
                  >
                    {deviceType}
                  </span>
                )}
              </div>
            </div>
          </div>

          {lastValidated && (
            <div className="text-right">
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                Last validated
              </span>
              <div
                className="text-xs font-medium"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {new Date(lastValidated).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </div>
            </div>
          )}
        </div>

        {/* Safety message */}
        {message && (
          <div
            className="p-3 rounded mb-4"
            style={{
              background: safetyConfig.bg,
              border: `1px solid ${safetyConfig.color}30`,
            }}
          >
            <p
              className="text-xs"
              style={{ color: safetyConfig.color }}
            >
              {message}
            </p>
          </div>
        )}

        {/* Safety description */}
        <div className="mb-4">
          <p
            className="text-xs"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            {safetyConfig.description}
            {status === "safe" && " Control actions are permitted."}
            {status === "warning" && " Control actions may have safety implications."}
            {status === "blocked" && " Control actions are blocked for safety."}
          </p>
        </div>

        {/* Safety rules */}
        {rules.length > 0 && (
          <div>
            <h4
              className="font-medium text-xs mb-3 uppercase tracking-wider"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Safety Rules
            </h4>
            <div className="space-y-2">
              {rules.map((rule, index) => {
                const ruleConfig = getRuleStatusConfig(rule.status);
                return (
                  <div
                    key={index}
                    className="flex items-start gap-2 p-2 rounded"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      border: "1px solid var(--color-sentinel-border)",
                    }}
                  >
                    <div className="mt-0.5" style={{ color: ruleConfig.color }}>
                      {ruleConfig.icon}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <span
                          className="text-xs font-medium"
                          style={{ color: "var(--color-sentinel-text-primary)" }}
                        >
                          {rule.rule}
                        </span>
                        <span
                          className="text-xs px-2 py-0.5 rounded capitalize"
                          style={{
                            background: `${ruleConfig.color}20`,
                            color: ruleConfig.color,
                          }}
                        >
                          {rule.status}
                        </span>
                      </div>
                      {rule.description && (
                        <p
                          className="text-xs mt-1"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          {rule.description}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Legend */}
        <div className="mt-4 pt-4" style={{ borderTop: "1px solid var(--color-sentinel-border)" }}>
          <div className="grid grid-cols-3 gap-2">
            <div className="flex items-center gap-1">
              <div
                className="w-2 h-2 rounded-full"
                style={{ background: "var(--color-sentinel-green)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Safe
              </span>
            </div>
            <div className="flex items-center gap-1">
              <div
                className="w-2 h-2 rounded-full"
                style={{ background: "var(--color-sentinel-amber)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Warning
              </span>
            </div>
            <div className="flex items-center gap-1">
              <div
                className="w-2 h-2 rounded-full"
                style={{ background: "var(--color-sentinel-red)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Blocked
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ControlStatus;
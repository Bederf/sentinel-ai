/**
 * AlertFeed Component - Grafana-inspired alert list
 *
 * Displays:
 * - Severity-coded alert rows with left border accent
 * - Site and equipment context
 * - Relative timestamps
 * - Auto-refresh with visual indicator
 *
 * Follows Grafana alert panel design with dark theme.
 */

import { useState, useEffect, useCallback } from "react";
import { Bell, Clock, RefreshCw, CheckCircle } from "lucide-react";
import api from "../lib/api";
import type { Alert } from "../lib/api";

interface AlertFeedProps {
  /** Maximum number of alerts to display */
  limit?: number;
  /** Auto-refresh interval in milliseconds (0 to disable) */
  refreshInterval?: number;
  /** Initial alerts (optional, will fetch if not provided) */
  initialAlerts?: Alert[];
  /** Callback when alerts are refreshed */
  onRefresh?: (alerts: Alert[]) => void;
}

/**
 * Get relative time string from timestamp
 */
function getRelativeTime(timestamp: string): string {
  const now = new Date();
  const alertTime = new Date(timestamp);
  const diffMs = now.getTime() - alertTime.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) {
    return "Just now";
  }
  if (diffMins < 60) {
    return `${diffMins}m ago`;
  }
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  return `${diffDays}d ago`;
}

/**
 * Get severity configuration for Grafana styling
 */
function getSeverityConfig(severity: Alert["severity"]): {
  color: string;
  bg: string;
  label: string;
} {
  switch (severity) {
    case "critical":
      return {
        color: "var(--color-status-error)",
        bg: "rgba(242, 73, 92, 0.1)",
        label: "CRITICAL",
      };
    case "high":
      return {
        color: "var(--color-status-warning)",
        bg: "rgba(255, 152, 48, 0.1)",
        label: "HIGH",
      };
    case "medium":
      return {
        color: "var(--color-grafana-yellow)",
        bg: "rgba(242, 204, 12, 0.1)",
        label: "MEDIUM",
      };
    case "low":
      return {
        color: "var(--color-grafana-blue)",
        bg: "rgba(50, 116, 217, 0.1)",
        label: "LOW",
      };
    default:
      return {
        color: "var(--color-grafana-text-secondary)",
        bg: "rgba(142, 142, 142, 0.1)",
        label: "INFO",
      };
  }
}

export function AlertFeed({
  limit = 10,
  refreshInterval = 30000,
  initialAlerts,
  onRefresh,
}: AlertFeedProps) {
  const [alerts, setAlerts] = useState<Alert[]>(initialAlerts || []);
  const [loading, setLoading] = useState(!initialAlerts);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  // Fetch alerts from API
  const fetchAlerts = useCallback(async () => {
    try {
      const data = await api.getAlerts();
      const sortedAlerts = data
        .sort(
          (a, b) =>
            new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
        )
        .slice(0, limit);
      setAlerts(sortedAlerts);
      setLastRefresh(new Date());
      setError(null);
      if (onRefresh) {
        onRefresh(sortedAlerts);
      }
    } catch (err) {
      console.error("Failed to fetch alerts:", err);
      setError("Failed to load alerts");
    } finally {
      setLoading(false);
    }
  }, [limit, onRefresh]);

  // Initial load
  useEffect(() => {
    if (!initialAlerts) {
      fetchAlerts();
    }
  }, [fetchAlerts, initialAlerts]);

  // Auto-refresh
  useEffect(() => {
    if (refreshInterval <= 0) return;

    const interval = setInterval(fetchAlerts, refreshInterval);
    return () => clearInterval(interval);
  }, [fetchAlerts, refreshInterval]);

  // Manual refresh handler
  const handleManualRefresh = () => {
    setLoading(true);
    fetchAlerts();
  };

  // Count by severity
  const criticalCount = alerts.filter((a) => a.severity === "critical").length;
  const warningCount = alerts.filter((a) => a.severity === "high" || a.severity === "medium").length;

  // Loading state
  if (loading && alerts.length === 0) {
    return (
      <div
        className="h-full rounded overflow-hidden flex flex-col"
        style={{
          background: "var(--color-grafana-bg-panel)",
          border: "1px solid var(--color-grafana-border)",
        }}
      >
        <div
          className="p-4 flex items-center gap-2"
          style={{ borderBottom: "1px solid var(--color-grafana-border)" }}
        >
          <Bell className="h-5 w-5" style={{ color: "var(--color-grafana-orange)" }} />
          <span
            className="font-medium text-sm"
            style={{ color: "var(--color-grafana-text-primary)" }}
          >
            Recent Alerts
          </span>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <RefreshCw
            className="h-6 w-6 animate-spin"
            style={{ color: "var(--color-grafana-text-disabled)" }}
          />
        </div>
      </div>
    );
  }

  return (
    <div
      className="h-full rounded overflow-hidden flex flex-col"
      style={{
        background: "var(--color-grafana-bg-panel)",
        border: "1px solid var(--color-grafana-border)",
      }}
    >
      {/* Header */}
      <div
        className="p-4 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--color-grafana-border)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: "rgba(255, 152, 48, 0.15)" }}
          >
            <Bell className="h-5 w-5" style={{ color: "var(--color-grafana-orange)" }} />
          </div>
          <div>
            <h3
              className="font-medium text-sm"
              style={{ color: "var(--color-grafana-text-primary)" }}
            >
              Recent Alerts
            </h3>
            <div className="flex items-center gap-2 mt-0.5">
              {criticalCount > 0 && (
                <span
                  className="text-xs px-1.5 py-0.5 rounded"
                  style={{
                    background: "rgba(242, 73, 92, 0.15)",
                    color: "var(--color-status-error)",
                  }}
                >
                  {criticalCount} critical
                </span>
              )}
              {warningCount > 0 && (
                <span
                  className="text-xs px-1.5 py-0.5 rounded"
                  style={{
                    background: "rgba(255, 152, 48, 0.15)",
                    color: "var(--color-status-warning)",
                  }}
                >
                  {warningCount} warning
                </span>
              )}
            </div>
          </div>
        </div>
        <button
          onClick={handleManualRefresh}
          className="p-2 rounded transition-colors hover:brightness-125"
          style={{ background: "var(--color-grafana-bg-secondary)" }}
          title="Refresh alerts"
        >
          <RefreshCw
            className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
            style={{ color: "var(--color-grafana-text-secondary)" }}
          />
        </button>
      </div>

      {/* Error State */}
      {error && (
        <div
          className="mx-4 mt-4 p-3 rounded"
          style={{
            background: "rgba(242, 73, 92, 0.1)",
            border: "1px solid rgba(242, 73, 92, 0.3)",
            color: "var(--color-status-error)",
          }}
        >
          {error}
        </div>
      )}

      {/* Alert List */}
      <div className="flex-1 overflow-y-auto p-2">
        {alerts.length === 0 ? (
          <div className="text-center py-8">
            <CheckCircle
              className="h-12 w-12 mx-auto mb-2"
              style={{ color: "var(--color-status-success)" }}
            />
            <span style={{ color: "var(--color-grafana-text-secondary)" }}>
              No active alerts
            </span>
          </div>
        ) : (
          <div className="space-y-1">
            {alerts.map((alert) => {
              const config = getSeverityConfig(alert.severity);

              return (
                <div
                  key={alert.id}
                  className="rounded overflow-hidden transition-all hover:brightness-110"
                  style={{
                    background: config.bg,
                    borderLeft: `3px solid ${config.color}`,
                  }}
                >
                  <div className="p-3">
                    {/* Header: Message and Severity */}
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <span
                        className="font-medium text-sm line-clamp-2"
                        style={{ color: "var(--color-grafana-text-primary)" }}
                      >
                        {alert.message}
                      </span>
                      <span
                        className="flex-shrink-0 text-xs font-medium px-1.5 py-0.5 rounded"
                        style={{
                          color: config.color,
                          background: "rgba(0, 0, 0, 0.2)",
                        }}
                      >
                        {config.label}
                      </span>
                    </div>

                    {/* Context: Site and Equipment */}
                    <div className="flex items-center gap-2 text-xs mb-2">
                      <span style={{ color: "var(--color-grafana-text-secondary)" }}>
                        {alert.site_name}
                      </span>
                      <span style={{ color: "var(--color-grafana-text-disabled)" }}>•</span>
                      <span style={{ color: "var(--color-grafana-text-secondary)" }}>
                        {alert.equipment_name}
                      </span>
                    </div>

                    {/* Timestamp */}
                    <div className="flex items-center gap-1">
                      <Clock
                        className="h-3 w-3"
                        style={{ color: "var(--color-grafana-text-disabled)" }}
                      />
                      <span
                        className="text-xs"
                        style={{ color: "var(--color-grafana-text-disabled)" }}
                      >
                        {getRelativeTime(alert.timestamp)}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer with last refresh time */}
      <div
        className="p-3 text-center"
        style={{ borderTop: "1px solid var(--color-grafana-border)" }}
      >
        <span
          className="text-xs"
          style={{ color: "var(--color-grafana-text-disabled)" }}
        >
          Updated: {lastRefresh.toLocaleTimeString()}
          {refreshInterval > 0 && (
            <span className="ml-2">
              <span
                className="inline-block w-1.5 h-1.5 rounded-full pulse-live mr-1"
                style={{ background: "var(--color-status-success)" }}
              />
              Auto-refresh
            </span>
          )}
        </span>
      </div>
    </div>
  );
}

export default AlertFeed;

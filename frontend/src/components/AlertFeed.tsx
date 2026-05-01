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
import { Bell, Clock, RefreshCw, CheckCircle, CheckCheck, ClipboardList } from "lucide-react";
import api from '@/lib/api';
import type { Alert } from '@/lib/api';

interface AlertFeedProps {
  /** Maximum number of alerts to display */
  limit?: number;
  /** Auto-refresh interval in milliseconds (0 to disable) */
  refreshInterval?: number;
  /** Initial alerts (optional, will fetch if not provided) */
  initialAlerts?: Alert[];
  /** Callback when alerts are refreshed */
  onRefresh?: (alerts: Alert[]) => void;
  /** Callback when an alert is marked as read */
  onAlertRead?: (alertId: string) => void;
  /** Callback when all alerts are cleared/marked as read */
  onClearAll?: () => void;
  /** Callback when an alert is clicked - for navigation to equipment */
  onAlertClick?: (alert: Alert) => void;
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
  onAlertRead,
  onClearAll,
  onAlertClick,
}: AlertFeedProps) {
  const [alerts, setAlerts] = useState<Alert[]>(initialAlerts || []);
  const [loading, setLoading] = useState(!initialAlerts);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  // Track locally read alerts for immediate UI feedback
  const [locallyReadAlerts, setLocallyReadAlerts] = useState<Set<string>>(new Set());
  // Per-alert ack state: acking = spinner, wo = work order was auto-created
  const [ackState, setAckState] = useState<Record<string, { acking: boolean; wo: boolean }>>({});

  // Fetch alerts from API
  const fetchAlerts = useCallback(async () => {
    try {
      const { alerts } = await api.getAlerts();
      const sortedAlerts = alerts
        .sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
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

  // Handle alert click - mark as read and navigate to equipment
  const handleAlertClick = async (alertId: string) => {
    const alert = alerts.find(a => a.id === alertId);
    if (!alert) return;

    // Always trigger navigation callback (even if already read)
    if (onAlertClick) {
      onAlertClick(alert);
    }

    // If already read (acknowledged or locally marked), skip marking as read
    if (alert.acknowledged || locallyReadAlerts.has(alertId)) {
      return;
    }

    // Mark as locally read immediately for UI feedback
    setLocallyReadAlerts(prev => new Set(prev).add(alertId));

    // Notify parent about read status change
    if (onAlertRead) {
      onAlertRead(alertId);
    }

    // Call API to acknowledge (fire and forget, UI already updated)
    try {
      await api.acknowledgeAlert(alertId);
    } catch (err) {
      console.error("Failed to acknowledge alert:", err);
      // Don't revert UI - local read state is still valid
    }
  };

  // Check if an alert is read (either acknowledged or locally marked)
  const isAlertRead = (alert: Alert): boolean => {
    return alert.acknowledged || locallyReadAlerts.has(alert.id);
  };

  // Handle clear all - acknowledge and remove all alerts
  const handleClearAll = async () => {
    const alertsToClear = [...alerts];
    if (alertsToClear.length === 0) return;

    // Remove all alerts from the list immediately
    setAlerts([]);
    setLocallyReadAlerts(new Set());

    // Notify parent
    if (onClearAll) {
      onClearAll();
    }

    // Acknowledge each alert on the backend (fire and forget)
    for (const alert of alertsToClear) {
      try {
        await api.acknowledgeAlert(alert.id);
      } catch (err) {
        console.error(`Failed to acknowledge alert ${alert.id}:`, err);
      }
    }
  };

  // Explicit acknowledge button handler — separate from row click/navigate
  const handleAckButton = async (e: React.MouseEvent, alertId: string) => {
    e.stopPropagation(); // don't trigger row click / navigation
    if (ackState[alertId]?.acking || locallyReadAlerts.has(alertId)) return;

    setAckState(prev => ({ ...prev, [alertId]: { acking: true, wo: false } }));
    setLocallyReadAlerts(prev => new Set(prev).add(alertId));
    if (onAlertRead) onAlertRead(alertId);

    try {
      const result = await api.acknowledgeAlert(alertId);
      setAckState(prev => ({
        ...prev,
        [alertId]: { acking: false, wo: result.work_order_created ?? false },
      }));
      // Clear WO badge after 4 seconds
      if (result.work_order_created) {
        setTimeout(() => {
          setAckState(prev => ({ ...prev, [alertId]: { acking: false, wo: false } }));
        }, 4000);
      }
    } catch {
      setAckState(prev => ({ ...prev, [alertId]: { acking: false, wo: false } }));
    }
  };

  // Count unread alerts
  const unreadCount = alerts.filter(a => !isAlertRead(a)).length;

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
        <div className="flex items-center gap-2">
          {unreadCount > 0 && (
            <button
              onClick={handleClearAll}
              className="px-2 py-1 rounded text-xs font-medium transition-colors hover:brightness-125 flex items-center gap-1"
              style={{
                background: "var(--color-grafana-bg-secondary)",
                color: "var(--color-grafana-text-secondary)",
              }}
              title="Mark all as read"
            >
              <CheckCheck className="h-3.5 w-3.5" />
              <span>Clear</span>
            </button>
          )}
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
              const isRead = isAlertRead(alert);

              return (
                <div
                  key={alert.id}
                  onClick={() => handleAlertClick(alert.id)}
                  className="rounded overflow-hidden transition-all hover:brightness-110 cursor-pointer"
                  style={{
                    background: config.bg,
                    borderLeft: `3px solid ${config.color}`,
                    opacity: isRead ? 0.6 : 1,
                  }}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleAlertClick(alert.id);
                    }
                  }}
                  aria-label={`${isRead ? 'Read' : 'Unread'} alert: ${alert.message}`}
                >
                  <div className="p-3">
                    {/* Header: Message and Severity */}
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <span
                        className="text-sm line-clamp-2"
                        style={{
                          color: "var(--color-grafana-text-primary)",
                          fontWeight: isRead ? 400 : 500,
                        }}
                      >
                        {alert.message}
                      </span>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        {!isRead && (
                          <span
                            className="w-2 h-2 rounded-full"
                            style={{ background: "var(--color-sentinel-blue)" }}
                            title="Unread"
                          />
                        )}
                        <span
                          className="text-xs font-medium px-1.5 py-0.5 rounded"
                          style={{
                            color: config.color,
                            background: "rgba(0, 0, 0, 0.2)",
                          }}
                        >
                          {config.label}
                        </span>
                      </div>
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

                    {/* Recommended Action */}
                    {alert.recommended_action && (
                      <div
                        className="text-xs mb-2 px-2 py-1.5 rounded"
                        style={{
                          borderLeft: "3px solid var(--color-grafana-blue)",
                          backgroundColor: "rgba(61, 113, 217, 0.08)",
                          color: "var(--color-grafana-text-primary)",
                        }}
                      >
                        <span style={{ color: "var(--color-grafana-blue)", fontWeight: 600 }}>Action: </span>
                        {alert.recommended_action}
                      </div>
                    )}

                    {/* Operational Context Tags */}
                    {alert.operational_context && (
                      <div className="flex items-center gap-1.5 flex-wrap text-xs mb-2">
                        {alert.operational_context.is_peak_hours && (
                          <span
                            className="px-1.5 py-0.5 rounded"
                            style={{
                              backgroundColor: "rgba(245, 158, 11, 0.15)",
                              color: "var(--color-sentinel-amber)",
                              fontSize: "0.65rem",
                            }}
                          >
                            Peak Hours
                          </span>
                        )}
                        <span
                          className="px-1.5 py-0.5 rounded"
                          style={{
                            backgroundColor: "rgba(140, 140, 140, 0.12)",
                            color: "var(--color-grafana-text-secondary)",
                            fontSize: "0.65rem",
                          }}
                        >
                          {alert.operational_context.building_state.replace(/_/g, " ")}
                        </span>
                        {alert.operational_context.occupancy_pct > 0 && (
                          <span
                            className="px-1.5 py-0.5 rounded"
                            style={{
                              backgroundColor: "rgba(140, 140, 140, 0.12)",
                              color: "var(--color-grafana-text-secondary)",
                              fontSize: "0.65rem",
                            }}
                          >
                            {Math.round(alert.operational_context.occupancy_pct)}% occupied
                          </span>
                        )}
                      </div>
                    )}

                    {/* Timestamp + Ack button row */}
                    <div className="flex items-center justify-between gap-1">
                      <div className="flex items-center gap-1">
                        <Clock
                          className="h-3 w-3"
                          style={{ color: "var(--color-grafana-text-disabled)" }}
                        />
                        <span
                          className="text-xs"
                          style={{ color: "var(--color-grafana-text-disabled)" }}
                        >
                          {getRelativeTime(alert.created_at)}
                        </span>
                      </div>

                      {/* Acknowledge button — only shown on unread alerts */}
                      {!isRead && (
                        <div className="flex items-center gap-1.5">
                          {ackState[alert.id]?.wo && (
                            <span
                              className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded"
                              style={{
                                background: "rgba(16, 185, 129, 0.15)",
                                color: "var(--color-sentinel-green)",
                              }}
                            >
                              <ClipboardList className="h-3 w-3" />
                              WO queued
                            </span>
                          )}
                          <button
                            onClick={(e) => handleAckButton(e, alert.id)}
                            className="flex items-center gap-1 text-xs px-2 py-1 rounded transition-colors hover:brightness-125"
                            style={{
                              background: "rgba(61, 113, 217, 0.15)",
                              color: "var(--color-sentinel-blue)",
                              border: "1px solid rgba(61, 113, 217, 0.3)",
                            }}
                            title="Acknowledge alert and create work order"
                          >
                            {ackState[alert.id]?.acking ? (
                              <RefreshCw className="h-3 w-3 animate-spin" />
                            ) : (
                              <CheckCheck className="h-3 w-3" />
                            )}
                            Ack
                          </button>
                        </div>
                      )}
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

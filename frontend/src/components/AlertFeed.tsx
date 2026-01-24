/**
 * AlertFeed Component - Real-time alert list
 *
 * Displays:
 * - Severity badge (critical=red, warning=yellow, info=blue)
 * - Site name
 * - Equipment ID
 * - Alert message
 * - Timestamp (relative: "2h ago")
 *
 * Features:
 * - Auto-refresh every 30 seconds
 * - Limit to 10 most recent
 *
 * Requirement: DASH-02 - Alert feed with severity colors
 */

import { useState, useEffect, useCallback } from "react";
import { Card, Title, Text, Badge, Flex } from "@tremor/react";
import { Activity, Clock, RefreshCw } from "lucide-react";
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
 * Get badge color based on severity
 */
function getSeverityColor(
  severity: Alert["severity"]
): "red" | "orange" | "yellow" | "blue" | "gray" {
  switch (severity) {
    case "critical":
      return "red";
    case "high":
      return "orange";
    case "medium":
      return "yellow";
    case "low":
      return "blue";
    default:
      return "gray";
  }
}

/**
 * Get background color class based on severity
 */
function getSeverityBgClass(severity: Alert["severity"]): string {
  switch (severity) {
    case "critical":
      return "bg-red-50 border-l-4 border-red-500";
    case "high":
      return "bg-orange-50 border-l-4 border-orange-500";
    case "medium":
      return "bg-yellow-50 border-l-4 border-yellow-500";
    case "low":
      return "bg-blue-50 border-l-4 border-blue-500";
    default:
      return "bg-gray-50 border-l-4 border-gray-300";
  }
}

export function AlertFeed({
  limit = 10,
  refreshInterval = 30000, // 30 seconds default
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
      // Sort by timestamp descending and limit
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

  // Count critical alerts
  const criticalCount = alerts.filter((a) => a.severity === "critical").length;

  if (loading && alerts.length === 0) {
    return (
      <Card className="h-full">
        <Title className="mb-4">Recent Alerts</Title>
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="h-6 w-6 text-gray-400 animate-spin" />
        </div>
      </Card>
    );
  }

  return (
    <Card className="h-full flex flex-col">
      {/* Header */}
      <Flex justifyContent="between" alignItems="center" className="mb-4">
        <div className="flex items-center gap-2">
          <Title>Recent Alerts</Title>
          {loading && alerts.length > 0 && (
            <Text className="text-xs text-gray-400 animate-pulse">Refreshing...</Text>
          )}
          {criticalCount > 0 && (
            <Badge color="red" size="sm">
              {criticalCount} critical
            </Badge>
          )}
        </div>
        <button
          onClick={handleManualRefresh}
          className="p-2 hover:bg-gray-100 rounded-full transition-colors"
          title="Refresh alerts"
        >
          <RefreshCw
            className={`h-4 w-4 text-gray-500 ${loading ? "animate-spin" : ""}`}
          />
        </button>
      </Flex>

      {/* Error State */}
      {error && (
        <div className="p-3 bg-red-50 text-red-700 rounded-lg mb-4">
          {error}
        </div>
      )}

      {/* Alert List */}
      <div className="flex-1 space-y-3 overflow-y-auto">
        {alerts.length === 0 ? (
          <div className="text-center py-8">
            <Activity className="h-12 w-12 text-green-500 mx-auto mb-2" />
            <Text className="text-gray-500">No active alerts</Text>
          </div>
        ) : (
          alerts.map((alert) => (
            <div
              key={alert.id}
              className={`p-3 rounded-lg ${getSeverityBgClass(alert.severity)}`}
            >
              <Flex justifyContent="between" alignItems="start">
                <div className="flex-1 min-w-0">
                  <Text className="font-medium text-gray-900 truncate">
                    {alert.message}
                  </Text>
                  <div className="flex items-center gap-2 mt-1">
                    <Text className="text-sm text-gray-500 truncate">
                      {alert.site_name}
                    </Text>
                    <span className="text-gray-300">·</span>
                    <Text className="text-sm text-gray-500 truncate">
                      {alert.equipment_name}
                    </Text>
                  </div>
                  <div className="flex items-center gap-1 mt-1">
                    <Clock className="h-3 w-3 text-gray-400" />
                    <Text className="text-xs text-gray-400">
                      {getRelativeTime(alert.timestamp)}
                    </Text>
                  </div>
                </div>
                <Badge color={getSeverityColor(alert.severity)} size="sm">
                  {alert.severity}
                </Badge>
              </Flex>
            </div>
          ))
        )}
      </div>

      {/* Footer with last refresh time */}
      <div className="mt-4 pt-3 border-t border-gray-100">
        <Text className="text-xs text-gray-400 text-center">
          Last updated: {lastRefresh.toLocaleTimeString()}
          {refreshInterval > 0 && ` · Auto-refresh every ${refreshInterval / 1000}s`}
        </Text>
      </div>
    </Card>
  );
}

export default AlertFeed;

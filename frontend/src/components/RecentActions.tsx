/**
 * RecentActions Component - Compact inline audit trail for control dashboard
 *
 * Displays recent control actions in a compact, auto-refreshing list.
 * Designed for embedding in the control dashboard, not as a standalone page.
 *
 * Features:
 * - Compact list of recent actions
 * - Auto-refresh with configurable interval
 * - Device filtering
 * - Color-coded success/failure
 * - Click to expand details
 * - "View all" link to full audit trail
 */

import { useState, useEffect, useCallback } from "react";
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  ExternalLink,
} from "lucide-react";
import api from "../lib/api";
import type { AuditEntry } from "../lib/api";
import { formatDateTime } from "../lib/timeFormat";

interface RecentActionsProps {
  /** Filter to specific device (optional) */
  deviceId?: string;
  /** Maximum entries to display (default: 5) */
  limit?: number;
  /** Auto-refresh enabled (default: true) */
  autoRefresh?: boolean;
  /** Refresh interval in ms (default: 5000) */
  refreshInterval?: number;
  /** Trigger refresh externally */
  refreshTrigger?: number;
  /** Link to full audit trail */
  onViewAll?: () => void;
}

/**
 * Get relative time string from timestamp
 */
function getRelativeTime(timestamp: string): string {
  const now = new Date();
  const logTime = new Date(timestamp);
  const diffMs = now.getTime() - logTime.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

/**
 * Format value for display
 */
function formatValue(value: any): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "boolean") return value ? "ON" : "OFF";
  if (typeof value === "number") {
    // Add unit based on common patterns
    if (value >= 15 && value <= 30) return `${value}°C`;
    if (value >= 0 && value <= 100) return `${value}%`;
    return String(value);
  }
  return String(value);
}

export function RecentActions({
  deviceId,
  limit = 5,
  autoRefresh = true,
  refreshInterval = 5000,
  refreshTrigger,
  onViewAll,
}: RecentActionsProps) {
  const [actions, setActions] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchActions = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      try {
        const entries = await api.getRecentAuditLogs(limit, deviceId);
        // Filter out duplicate entries by ID
        const uniqueEntries = entries.filter((entry, index, self) =>
          index === self.findIndex((e) => e.id === entry.id)
        );
        setActions(uniqueEntries);
        setError(null);
      } catch (err) {
        console.error("Failed to fetch recent actions:", err);
        setError("Failed to load actions");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [limit, deviceId]
  );

  // Initial load
  useEffect(() => {
    fetchActions();
  }, [fetchActions]);

  // Auto-refresh
  useEffect(() => {
    if (!autoRefresh) return;

    const intervalId = setInterval(() => {
      fetchActions(true);
    }, refreshInterval);

    return () => clearInterval(intervalId);
  }, [autoRefresh, refreshInterval, fetchActions]);

  // External refresh trigger
  useEffect(() => {
    if (refreshTrigger !== undefined && refreshTrigger > 0) {
      fetchActions(true);
    }
  }, [refreshTrigger, fetchActions]);

  // Loading skeleton
  if (loading && actions.length === 0) {
    return (
      <div className="space-y-2 p-3">
        {[...Array(3)].map((_, i) => (
          <div key={`skeleton-${i}`} className="animate-pulse">
            <div
              className="h-10 rounded"
              style={{ background: "var(--color-sentinel-bg-secondary)" }}
            />
          </div>
        ))}
      </div>
    );
  }

  // Error state
  if (error && actions.length === 0) {
    return (
      <div
        className="p-4 text-sm rounded"
        style={{
          background: "rgba(239, 68, 68, 0.1)",
          color: "var(--color-sentinel-red)",
        }}
      >
        {error}
      </div>
    );
  }

  // Empty state
  if (actions.length === 0) {
    return (
      <div
        className="p-4 text-center text-sm"
        style={{ color: "var(--color-sentinel-text-secondary)" }}
      >
        No recent actions
        {deviceId && " for this device"}
      </div>
    );
  }

  return (
    <div className="relative">
      {/* Refresh indicator */}
      {refreshing && (
        <div
          className="absolute top-2 right-2 flex items-center gap-1 text-xs"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          <RefreshCw className="w-3 h-3 animate-spin" />
        </div>
      )}

      {/* Actions list */}
      <div className="space-y-1 p-2">
        {actions.map((action) => (
          <div
            key={action.id}
            className="group cursor-pointer rounded transition-colors"
            style={{
              background:
                expandedId === action.id
                  ? "var(--color-sentinel-bg-secondary)"
                  : "transparent",
            }}
            onClick={() =>
              setExpandedId(expandedId === action.id ? null : action.id)
            }
          >
            {/* Compact row */}
            <div
              className="flex items-center gap-2 py-2 px-2 text-sm group-hover:bg-opacity-50"
              style={{
                borderLeft: `3px solid ${
                  action.success
                    ? "var(--color-sentinel-green)"
                    : "var(--color-sentinel-red)"
                }`,
              }}
            >
              {/* Status icon */}
              {action.success ? (
                <CheckCircle
                  className="w-4 h-4 flex-shrink-0"
                  style={{ color: "var(--color-sentinel-green)" }}
                />
              ) : action.message?.includes("warning") ? (
                <AlertTriangle
                  className="w-4 h-4 flex-shrink-0"
                  style={{ color: "var(--color-sentinel-amber)" }}
                />
              ) : (
                <XCircle
                  className="w-4 h-4 flex-shrink-0"
                  style={{ color: "var(--color-sentinel-red)" }}
                />
              )}

              {/* Action summary */}
              <div className="flex-1 min-w-0">
                <div
                  className="truncate"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {getRelativeTime(action.timestamp)}
                  </span>
                  {" · "}
                  <span className="font-medium">{action.device_name}</span>
                  {" · "}
                  <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {action.point}
                  </span>
                  {" → "}
                  <span style={{ color: "var(--color-sentinel-blue)" }}>
                    {formatValue(action.new_value)}
                  </span>
                </div>
              </div>

              {/* User */}
              <span
                className="text-xs flex-shrink-0"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {action.user}
              </span>
            </div>

            {/* Expanded details */}
            {expandedId === action.id && (
              <div
                className="px-4 pb-3 pt-1 text-xs space-y-1"
                style={{
                  borderLeft: `3px solid ${
                    action.success
                      ? "var(--color-sentinel-green)"
                      : "var(--color-sentinel-red)"
                  }`,
                }}
              >
                <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  <span className="font-medium">Time:</span>{" "}
                  {formatDateTime(action.timestamp)}
                </div>
                <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  <span className="font-medium">Device ID:</span> {action.device_id}
                </div>
                <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  <span className="font-medium">Change:</span>{" "}
                  {formatValue(action.old_value)} → {formatValue(action.new_value)}
                </div>
                {action.message && (
                  <div
                    style={{
                      color: action.success
                        ? "var(--color-sentinel-text-secondary)"
                        : "var(--color-sentinel-red)",
                    }}
                  >
                    <span className="font-medium">Message:</span> {action.message}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* View all link */}
      {onViewAll && (
        <div
          className="border-t px-3 py-2"
          style={{ borderColor: "var(--color-sentinel-border)" }}
        >
          <button
            onClick={(e) => {
              e.stopPropagation();
              onViewAll();
            }}
            className="flex items-center gap-1 text-xs hover:underline"
            style={{ color: "var(--color-sentinel-blue)" }}
          >
            View full audit trail
            <ExternalLink className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}

export default RecentActions;

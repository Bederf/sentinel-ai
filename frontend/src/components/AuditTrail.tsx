/**
 * AuditTrail Component - Grafana-inspired audit log display
 *
 * Displays:
 * - Audit log entries in a clean, readable table
 * - Color-coded results (success, warning, blocked, failed)
 * - Filtering by device, action, user, result
 * - Pagination and auto-refresh
 * - Progressive disclosure to detail view
 *
 * Follows Grafana table panel design with dark theme.
 */

import { useState, useEffect, useCallback } from "react";
import {
  Clock,
  Filter,
  User,
  Server,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Shield,
  RefreshCw,
  ChevronRight,
  Download,
} from "lucide-react";
import api from "../lib/api";
import type {
  AuditLogEntryResponse,
  AuditLogsResponse,
  AuditStatsResponse,
} from "../lib/api";
import AuditLogDetail from "./AuditLogDetail";

interface AuditTrailProps {
  /** Maximum number of entries to display per page */
  pageSize?: number;
  /** Auto-refresh interval in milliseconds (0 to disable) */
  refreshInterval?: number;
  /** Initial filter by device ID */
  initialDeviceId?: string;
  /** Initial filter by user */
  initialUser?: string;
  /** Initial filter by action */
  initialAction?: string;
  /** Initial filter by result */
  initialResult?: string;
  /** Callback when audit logs are refreshed */
  onRefresh?: (logs: AuditLogEntryResponse[]) => void;
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
 * Get color class for result type
 */
function getResultColor(result: string): string {
  switch (result.toLowerCase()) {
    case "success":
      return "text-green-400";
    case "warning":
      return "text-yellow-400";
    case "blocked":
      return "text-orange-400";
    case "failed":
      return "text-red-400";
    default:
      return "text-gray-400";
  }
}

/**
 * Get icon for result type
 */
function getResultIcon(result: string) {
  switch (result.toLowerCase()) {
    case "success":
      return <CheckCircle className="w-4 h-4" />;
    case "warning":
      return <AlertTriangle className="w-4 h-4" />;
    case "blocked":
      return <Shield className="w-4 h-4" />;
    case "failed":
      return <XCircle className="w-4 h-4" />;
    default:
      return <CheckCircle className="w-4 h-4" />;
  }
}

/**
 * Get display name for action type
 */
function getActionDisplayName(action: string): string {
  const actionMap: Record<string, string> = {
    device_control: "Device Control",
    safety_validation: "Safety Validation",
    system_event: "System Event",
    config_change: "Config Change",
  };
  return actionMap[action] || action.replace("_", " ").toUpperCase();
}

export default function AuditTrail({
  pageSize = 20,
  refreshInterval = 30000, // 30 seconds
  initialDeviceId,
  initialUser,
  initialAction,
  initialResult,
  onRefresh,
}: AuditTrailProps) {
  // State
  const [logs, setLogs] = useState<AuditLogEntryResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [stats, setStats] = useState<AuditStatsResponse | null>(null);

  // Filters
  const [deviceId, setDeviceId] = useState(initialDeviceId || "");
  const [user, setUser] = useState(initialUser || "");
  const [action, setAction] = useState(initialAction || "");
  const [result, setResult] = useState(initialResult || "");
  const [showFilters, setShowFilters] = useState(false);

  // Detail view
  const [selectedLog, setSelectedLog] = useState<AuditLogEntryResponse | null>(
    null
  );
  const [showDetail, setShowDetail] = useState(false);

  // Available filter options (would come from API in production)
  const actionOptions = [
    { value: "", label: "All Actions" },
    { value: "device_control", label: "Device Control" },
    { value: "safety_validation", label: "Safety Validation" },
    { value: "system_event", label: "System Event" },
    { value: "config_change", label: "Config Change" },
  ];

  const resultOptions = [
    { value: "", label: "All Results" },
    { value: "success", label: "Success" },
    { value: "warning", label: "Warning" },
    { value: "blocked", label: "Blocked" },
    { value: "failed", label: "Failed" },
  ];

  /**
   * Fetch audit logs with current filters
   */
  const fetchAuditLogs = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      try {
        const response = await api.getAuditLogs(
          page,
          pageSize,
          undefined, // startTime
          undefined, // endTime
          deviceId || undefined,
          action || undefined,
          user || undefined,
          result || undefined
        );

        setLogs(response.entries);
        setTotalCount(response.total_count);
        setHasMore(response.has_more);
        setError(null);

        if (onRefresh) {
          onRefresh(response.entries);
        }
      } catch (err) {
        console.error("Failed to fetch audit logs:", err);
        setError(
          err instanceof Error ? err.message : "Failed to load audit logs"
        );
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [page, pageSize, deviceId, user, action, result, onRefresh]
  );

  /**
   * Fetch audit statistics
   */
  const fetchAuditStats = useCallback(async () => {
    try {
      const response = await api.getAuditStats();
      setStats(response);
    } catch (err) {
      console.error("Failed to fetch audit stats:", err);
    }
  }, []);

  /**
   * Load initial data
   */
  useEffect(() => {
    fetchAuditLogs();
    fetchAuditStats();
  }, [fetchAuditLogs, fetchAuditStats]);

  /**
   * Set up auto-refresh
   */
  useEffect(() => {
    if (refreshInterval <= 0) return;

    const intervalId = setInterval(() => {
      fetchAuditLogs(true);
      fetchAuditStats();
    }, refreshInterval);

    return () => clearInterval(intervalId);
  }, [refreshInterval, fetchAuditLogs, fetchAuditStats]);

  /**
   * Handle filter changes
   */
  const handleFilterChange = () => {
    setPage(1); // Reset to first page when filters change
    fetchAuditLogs();
  };

  /**
   * Handle next page
   */
  const handleNextPage = () => {
    if (hasMore) {
      setPage(page + 1);
    }
  };

  /**
   * Handle previous page
   */
  const handlePreviousPage = () => {
    if (page > 1) {
      setPage(page - 1);
    }
  };

  /**
   * Handle log entry click
   */
  const handleLogClick = (log: AuditLogEntryResponse) => {
    setSelectedLog(log);
    setShowDetail(true);
  };

  /**
   * Export logs as CSV
   */
  const handleExportCSV = () => {
    const headers = [
      "Timestamp",
      "Action",
      "User",
      "Device",
      "Point",
      "Old Value",
      "New Value",
      "Result",
      "Error Message",
    ];

    const csvRows = [
      headers.join(","),
      ...logs.map((log) =>
        [
          `"${log.timestamp}"`,
          `"${log.action}"`,
          `"${log.user}"`,
          `"${log.device_id || ""}"`,
          `"${log.point_name || ""}"`,
          `"${log.old_value || ""}"`,
          `"${log.new_value || ""}"`,
          `"${log.result}"`,
          `"${log.error_message || ""}"`,
        ].join(",")
      ),
    ];

    const csvContent = csvRows.join("\n");
    const blob = new Blob([csvContent], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-logs-${new Date().toISOString().split("T")[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Loading state
  if (loading && !refreshing) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-gray-400" />
            <h3 className="text-lg font-semibold text-gray-200">Audit Trail</h3>
          </div>
        </div>
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="animate-pulse">
              <div className="h-12 bg-gray-800 rounded"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Clock className="w-5 h-5 text-gray-400" />
          <h3 className="text-lg font-semibold text-gray-200">Audit Trail</h3>
          {stats && (
            <span className="text-sm text-gray-400">
              ({stats.total_entries.toLocaleString()} total entries)
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-1 px-3 py-1.5 text-sm rounded-md transition-colors ${
              showFilters
                ? "bg-blue-900/30 text-blue-300 border border-blue-800"
                : "bg-gray-800 text-gray-300 hover:bg-gray-700"
            }`}
          >
            <Filter className="w-4 h-4" />
            Filters
          </button>

          <button
            onClick={handleExportCSV}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-gray-800 text-gray-300 rounded-md hover:bg-gray-700 transition-colors"
            title="Export as CSV"
          >
            <Download className="w-4 h-4" />
            Export
          </button>

          <button
            onClick={() => {
              fetchAuditLogs(true);
              fetchAuditStats();
            }}
            disabled={refreshing}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-gray-800 text-gray-300 rounded-md hover:bg-gray-700 transition-colors disabled:opacity-50"
            title="Refresh audit logs"
          >
            <RefreshCw
              className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`}
            />
            Refresh
          </button>
        </div>
      </div>

      {/* Filters */}
      {showFilters && (
        <div className="mb-4 p-3 bg-gray-800/50 border border-gray-700 rounded-lg">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">
                <User className="w-3 h-3 inline mr-1" />
                User
              </label>
              <input
                type="text"
                value={user}
                onChange={(e) => setUser(e.target.value)}
                onBlur={handleFilterChange}
                placeholder="Filter by user..."
                className="w-full px-3 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">
                <Server className="w-3 h-3 inline mr-1" />
                Device ID
              </label>
              <input
                type="text"
                value={deviceId}
                onChange={(e) => setDeviceId(e.target.value)}
                onBlur={handleFilterChange}
                placeholder="Filter by device..."
                className="w-full px-3 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">
                Action Type
              </label>
              <select
                value={action}
                onChange={(e) => {
                  setAction(e.target.value);
                  handleFilterChange();
                }}
                className="w-full px-3 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              >
                {actionOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">
                Result
              </label>
              <select
                value={result}
                onChange={(e) => {
                  setResult(e.target.value);
                  handleFilterChange();
                }}
                className="w-full px-3 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              >
                {resultOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="mt-3 text-xs text-gray-500">
            Showing {logs.length} of {totalCount.toLocaleString()} entries
            {deviceId && ` for device "${deviceId}"`}
            {user && ` by user "${user}"`}
            {action && ` with action "${action}"`}
            {result && ` with result "${result}"`}
          </div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="mb-4 p-3 bg-red-900/20 border border-red-800 rounded text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Audit log table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left py-2 px-3 text-sm font-medium text-gray-400">
                Time
              </th>
              <th className="text-left py-2 px-3 text-sm font-medium text-gray-400">
                Action
              </th>
              <th className="text-left py-2 px-3 text-sm font-medium text-gray-400">
                User
              </th>
              <th className="text-left py-2 px-3 text-sm font-medium text-gray-400">
                Device / Point
              </th>
              <th className="text-left py-2 px-3 text-sm font-medium text-gray-400">
                Result
              </th>
              <th className="text-left py-2 px-3 text-sm font-medium text-gray-400">
                Details
              </th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="py-8 px-3 text-center text-gray-500 text-sm"
                >
                  {loading
                    ? "Loading audit logs..."
                    : "No audit log entries found with current filters"}
                </td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr
                  key={log.id}
                  className="border-b border-gray-800/50 hover:bg-gray-800/30 cursor-pointer transition-colors"
                  onClick={() => handleLogClick(log)}
                >
                  <td className="py-3 px-3">
                    <div className="text-sm text-gray-300">
                      {getRelativeTime(log.timestamp)}
                    </div>
                    <div className="text-xs text-gray-500">
                      {new Date(log.timestamp).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </div>
                  </td>
                  <td className="py-3 px-3">
                    <div className="text-sm text-gray-300">
                      {getActionDisplayName(log.action)}
                    </div>
                  </td>
                  <td className="py-3 px-3">
                    <div className="text-sm text-gray-300">{log.user}</div>
                  </td>
                  <td className="py-3 px-3">
                    <div className="text-sm text-gray-300">
                      {log.device_id || "System"}
                    </div>
                    {log.point_name && (
                      <div className="text-xs text-gray-500">
                        {log.point_name}
                      </div>
                    )}
                  </td>
                  <td className="py-3 px-3">
                    <div
                      className={`flex items-center gap-1 text-sm ${getResultColor(
                        log.result
                      )}`}
                    >
                      {getResultIcon(log.result)}
                      <span className="capitalize">{log.result}</span>
                    </div>
                  </td>
                  <td className="py-3 px-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm text-gray-400 truncate max-w-[200px]">
                        {log.error_message ||
                          (log.old_value !== undefined &&
                            log.new_value !== undefined &&
                            `${log.old_value} → ${log.new_value}`) ||
                          "View details"}
                      </div>
                      <ChevronRight className="w-4 h-4 text-gray-500" />
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {logs.length > 0 && (
        <div className="mt-4 flex items-center justify-between">
          <div className="text-sm text-gray-400">
            Page {page} • {logs.length} entries
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handlePreviousPage}
              disabled={page <= 1}
              className="px-3 py-1.5 text-sm bg-gray-800 text-gray-300 rounded-md hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <button
              onClick={handleNextPage}
              disabled={!hasMore}
              className="px-3 py-1.5 text-sm bg-gray-800 text-gray-300 rounded-md hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Auto-refresh indicator */}
      {refreshing && (
        <div className="mt-3 text-xs text-gray-500 flex items-center gap-1">
          <RefreshCw className="w-3 h-3 animate-spin" />
          Refreshing audit logs...
        </div>
      )}

      {/* Detail modal */}
      {selectedLog && (
        <AuditLogDetail
          log={selectedLog}
          isOpen={showDetail}
          onClose={() => {
            setShowDetail(false);
            setSelectedLog(null);
          }}
        />
      )}
    </div>
  );
}
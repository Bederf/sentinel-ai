/**
 * Control Audit Trail Component - Full-page audit log for building control systems
 *
 * Features:
 * - Dedicated full-page view for control system audit logs
 * - Comprehensive filtering and search capabilities
 * - Larger display area for detailed audit information
 * - Direct integration with control system device actions
 * - Auto-refresh with backend scheduler integration
 */

import { useState, useEffect, useCallback } from "react";
import {
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
  Zap,
} from "lucide-react";
import api from "../lib/api";
import type {
  AuditLogEntryResponse,
} from "../lib/api";
import { formatDateTime } from "../lib/timeFormat";
import AuditLogDetail from "./AuditLogDetail";
import { LoadingCard } from "./LoadingCard";

interface ControlAuditTrailProps {
  onError?: (error: string) => void;
  onViewDevice?: (deviceId: string) => void;
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

export function ControlAuditTrail({ onError, onViewDevice }: ControlAuditTrailProps) {
  // State
  const [logs, setLogs] = useState<AuditLogEntryResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  // Filters
  const [deviceId, setDeviceId] = useState("");
  const [user, setUser] = useState("");
  const [action, setAction] = useState("");
  const [result, setResult] = useState("");
  const [showFilters, setShowFilters] = useState(false);

  // Detail view
  const [selectedLog, setSelectedLog] = useState<AuditLogEntryResponse | null>(
    null
  );
  const [showDetail, setShowDetail] = useState(false);

  // Available filter options
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

  const pageSizeOptions = [20, 50, 100, 200];

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

        // Deduplicate entries by ID to prevent React key warnings
        const uniqueEntries = response.entries.filter(
          (entry, index, self) => index === self.findIndex((e) => e.id === entry.id)
        );

        setLogs(uniqueEntries);
        setTotalCount(response.total_count);
        setHasMore(response.has_more);
        setError(null);
      } catch (err) {
        console.error("Failed to fetch audit logs:", err);
        const errorMessage = err instanceof Error ? err.message : "Failed to load audit logs";
        setError(errorMessage);
        onError?.(errorMessage);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [page, pageSize, deviceId, user, action, result, onError]
  );

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
      "Safety Validation",
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
          `"${log.safety_validation ? JSON.stringify(log.safety_validation) : ""}"`,
        ].join(",")
      ),
    ];

    const csvContent = csvRows.join("\n");
    const blob = new Blob([csvContent], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `control-audit-trail-${new Date().toISOString().split("T")[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  /**
   * Load initial data
   */
  useEffect(() => {
    fetchAuditLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Set up auto-refresh (every 60 seconds as per backend scheduler)
   */
  useEffect(() => {
    const intervalId = setInterval(() => {
      fetchAuditLogs(true);
    }, 60000);

    return () => clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Loading state
  if (loading && !refreshing) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <LoadingCard />
      </div>
    );
  }

  return (
    <div
      className="h-full overflow-hidden flex flex-col"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Header */}
      <div
        className="flex-none p-4 border-b flex items-center justify-between"
        style={{ borderColor: "var(--color-sentinel-border)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: "rgba(139, 92, 246, 0.15)" }}
          >
            <Shield className="h-5 w-5" style={{ color: "var(--color-sentinel-purple)" }} />
          </div>
          <div>
            <h2
              className="font-medium text-lg"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Control Audit Trail
            </h2>
            <span
              className="text-sm"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {totalCount.toLocaleString()} total entries • Auto-refresh: 60s
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-1 px-3 py-1.5 text-sm rounded-md transition-colors ${
              showFilters
                ? "bg-blue-900/30 text-blue-300 border border-blue-800"
                : "bg-gray-900 text-gray-300 hover:bg-gray-700 border border-gray-700"
            }`}
          >
            <Filter className="w-4 h-4" />
            Filters
          </button>

          <button
            onClick={handleExportCSV}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-gray-900 text-gray-300 rounded-md hover:bg-gray-700 transition-colors border border-gray-700"
            title="Export as CSV"
          >
            <Download className="w-4 h-4" />
            Export
          </button>

          <button
            onClick={() => fetchAuditLogs(true)}
            disabled={refreshing}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-gray-900 text-gray-300 rounded-md hover:bg-gray-700 transition-colors disabled:opacity-50 border border-gray-700"
            title="Refresh audit logs"
          >
            <RefreshCw
              className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`}
            />
            Refresh
          </button>
        </div>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div
          className="flex-none p-4 border-b"
          style={{ borderColor: "var(--color-sentinel-border)" }}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                <User className="w-3 h-3 inline mr-1" />
                User
              </label>
              <input
                type="text"
                value={user}
                onChange={(e) => setUser(e.target.value)}
                onBlur={handleFilterChange}
                placeholder="Filter by user..."
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                <Server className="w-3 h-3 inline mr-1" />
                Device ID
              </label>
              <input
                type="text"
                value={deviceId}
                onChange={(e) => setDeviceId(e.target.value)}
                onBlur={handleFilterChange}
                placeholder="Filter by device..."
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Action Type
              </label>
              <select
                value={action}
                onChange={(e) => {
                  setAction(e.target.value);
                  handleFilterChange();
                }}
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              >
                {actionOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Result
              </label>
              <select
                value={result}
                onChange={(e) => {
                  setResult(e.target.value);
                  handleFilterChange();
                }}
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              >
                {resultOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Page Size
              </label>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(1);
                  fetchAuditLogs();
                }}
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              >
                {pageSizeOptions.map((size) => (
                  <option key={size} value={size}>
                    {size} per page
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="mt-3 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Showing {logs.length} of {totalCount.toLocaleString()} entries
            {deviceId && ` • Device: "${deviceId}"`}
            {user && ` • User: "${user}"`}
            {action && ` • Action: "${action}"`}
            {result && ` • Result: "${result}"`}
          </div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="m-4 p-3 bg-red-900/20 border border-red-800 rounded text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Audit log table */}
      <div className="flex-1 overflow-auto p-4">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
                <th className="text-left py-3 px-4 text-sm font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Time
                </th>
                <th className="text-left py-3 px-4 text-sm font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Action
                </th>
                <th className="text-left py-3 px-4 text-sm font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  User
                </th>
                <th className="text-left py-3 px-4 text-sm font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Device / Point
                </th>
                <th className="text-left py-3 px-4 text-sm font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Changes
                </th>
                <th className="text-left py-3 px-4 text-sm font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Result
                </th>
                <th className="text-left py-3 px-4 text-sm font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Details
                </th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    className="py-12 px-4 text-center text-gray-500 text-sm"
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
                    className="border-b hover:bg-gray-800/30 cursor-pointer transition-colors"
                    style={{ borderColor: "var(--color-sentinel-border)" }}
                    onClick={() => handleLogClick(log)}
                  >
                    <td className="py-4 px-4">
                      <div className="text-sm text-gray-300">
                        {getRelativeTime(log.timestamp)}
                      </div>
                      <div className="text-xs text-gray-500">
                        {formatDateTime(log.timestamp)}
                      </div>
                    </td>
                    <td className="py-4 px-4">
                      <div className="text-sm text-gray-300">
                        {getActionDisplayName(log.action)}
                      </div>
                    </td>
                    <td className="py-4 px-4">
                      {log.user === "SENTINEL" ? (
                        <div className="flex items-center gap-1.5">
                          <Zap className="w-3.5 h-3.5" style={{ color: "var(--color-sentinel-purple)" }} />
                          <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-purple)" }}>
                            SENTINEL
                          </span>
                        </div>
                      ) : (
                        <div className="text-sm text-gray-300">{log.user}</div>
                      )}
                    </td>
                    <td className="py-4 px-4">
                      <div className="text-sm font-medium text-gray-300">
                        {log.device_id || "System"}
                      </div>
                      {log.point_name && (
                        <div className="text-xs text-gray-500">
                          {log.point_name}
                        </div>
                      )}
                    </td>
                    <td className="py-4 px-4">
                      <div className="text-sm text-gray-400">
                        {log.old_value !== undefined && log.new_value !== undefined
                          ? `${log.old_value} → ${log.new_value}`
                          : "-"}
                      </div>
                    </td>
                    <td className="py-4 px-4">
                      <div
                        className={`flex items-center gap-2 text-sm ${getResultColor(
                          log.result
                        )}`}
                      >
                        {getResultIcon(log.result)}
                        <span className="capitalize font-medium">{log.result}</span>
                      </div>
                    </td>
                    <td className="py-4 px-4">
                      <div className="flex items-center justify-between">
                        <div className="text-sm text-gray-400 truncate max-w-xs">
                          {log.error_message || "View details"}
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

        {/* Auto-refresh indicator */}
        {refreshing && (
          <div className="mt-4 text-sm flex items-center gap-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            <RefreshCw className="w-3 h-3 animate-spin" />
            Refreshing audit logs...
          </div>
        )}

        {/* Pagination */}
        {logs.length > 0 && (
          <div className="mt-6 flex items-center justify-between">
            <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Page {page} • {logs.length} entries
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handlePreviousPage}
                disabled={page <= 1}
                className="px-4 py-2 text-sm bg-gray-900 text-gray-300 rounded-md hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed border border-gray-700"
              >
                Previous
              </button>
              <button
                onClick={handleNextPage}
                disabled={!hasMore}
                className="px-4 py-2 text-sm bg-gray-900 text-gray-300 rounded-md hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed border border-gray-700"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Detail modal */}
      {selectedLog && (
        <AuditLogDetail
          log={selectedLog}
          isOpen={showDetail}
          onClose={() => {
            setShowDetail(false);
            setSelectedLog(null);
          }}
          onViewDevice={onViewDevice}
        />
      )}
    </div>
  );
}

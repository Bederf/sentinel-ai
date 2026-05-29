/**
 * AuditLogDetail Component - Detailed view of an audit log entry
 *
 * Displays:
 * - Complete audit log entry details
 * - Safety validation information
 * - Before/after values for device control
 * - Error messages and metadata
 * - Action buttons for related actions
 *
 * Follows Grafana modal design with dark theme.
 */

import { X, Clock, User, Server, Settings, Shield, AlertTriangle, Zap } from "lucide-react";
import type { AuditLogEntryResponse } from '@/lib/api';

interface AuditLogDetailProps {
  /** The audit log entry to display */
  log: AuditLogEntryResponse;
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal is closed */
  onClose: () => void;
  /** Callback to navigate to device in Control Dashboard */
  onViewDevice?: (deviceId: string) => void;
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
 * Get background color for result type
 */
function getResultBgColor(result: string): string {
  switch (result.toLowerCase()) {
    case "success":
      return "bg-green-900/20";
    case "warning":
      return "bg-yellow-900/20";
    case "blocked":
      return "bg-orange-900/20";
    case "failed":
      return "bg-red-900/20";
    default:
      return "bg-gray-900/20";
  }
}

/**
 * Format timestamp for display
 */
function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/**
 * Format value for display
 */
function formatValue(value: any): string {
  if (value === null || value === undefined) {
    return "N/A";
  }
  if (typeof value === "boolean") {
    return value ? "True" : "False";
  }
  if (typeof value === "number") {
    return value.toString();
  }
  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

export default function AuditLogDetail({
  log,
  isOpen,
  onClose,
  onViewDevice,
}: AuditLogDetailProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70">
      <div
        className="absolute inset-0"
        onClick={onClose}
        aria-hidden="true"
      ></div>

      <div className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto bg-gray-900 border border-gray-800 rounded-lg shadow-md">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between p-6 bg-gray-900 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <div
              className={`p-2 rounded-lg ${getResultBgColor(log.result)} ${getResultColor(
                log.result
              )}`}
            >
              {log.result === "warning" ? (
                <AlertTriangle className="w-6 h-6" />
              ) : log.result === "blocked" ? (
                <Shield className="w-6 h-6" />
              ) : (
                <Settings className="w-6 h-6" />
              )}
            </div>
            <div>
              <h2 className="text-xl font-semibold text-gray-200">
                {getActionDisplayName(log.action)}
              </h2>
              <div className="flex items-center gap-4 mt-1 text-sm text-gray-400">
                <span className={`capitalize ${getResultColor(log.result)}`}>
                  {log.result}
                </span>
                <span>•</span>
                <span>{formatTimestamp(log.timestamp)}</span>
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-200 hover:bg-gray-800 rounded-lg transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Basic Information */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <div>
                <h3 className="text-sm font-medium text-gray-400 mb-2 flex items-center gap-2">
                  <User className="w-4 h-4" />
                  User Information
                </h3>
                <div className="p-3 bg-gray-800/50 border border-gray-700 rounded">
                  {log.user === "SENTINEL" ? (
                    <div className="flex items-center gap-2">
                      <Zap className="w-5 h-5" style={{ color: "var(--color-sentinel-purple)" }} />
                      <span className="text-lg font-medium" style={{ color: "var(--color-sentinel-purple)" }}>
                        SENTINEL
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded" style={{ background: "rgba(139, 92, 246, 0.15)", color: "var(--color-sentinel-purple)" }}>
                        AI Auto
                      </span>
                    </div>
                  ) : (
                    <div className="text-lg font-medium text-gray-200">
                      {log.user}
                    </div>
                  )}
                  {log.correlation_id && (
                    <div className="mt-2 text-sm text-gray-400">
                      Correlation ID:{" "}
                      <code className="text-gray-300">{log.correlation_id}</code>
                    </div>
                  )}
                </div>
              </div>

              <div>
                <h3 className="text-sm font-medium text-gray-400 mb-2 flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  Timing
                </h3>
                <div className="p-3 bg-gray-800/50 border border-gray-700 rounded space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Timestamp:</span>
                    <span className="text-gray-200">
                      {formatTimestamp(log.timestamp)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Relative Time:</span>
                    <span className="text-gray-200">
                      {new Date(log.timestamp).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}{" "}
                      ({new Date().getTime() - new Date(log.timestamp).getTime() < 86400000
                        ? "Today"
                        : new Date(log.timestamp).toLocaleDateString()})
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <h3 className="text-sm font-medium text-gray-400 mb-2 flex items-center gap-2">
                  <Server className="w-4 h-4" />
                  Device Information
                </h3>
                <div className="p-3 bg-gray-800/50 border border-gray-700 rounded">
                  {log.device_id ? (
                    <>
                      <div className="text-lg font-medium text-gray-200">
                        {log.device_id}
                      </div>
                      {log.point_name && (
                        <div className="mt-2 text-sm text-gray-400">
                          Point:{" "}
                          <span className="text-gray-300">{log.point_name}</span>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-gray-400 italic">System Event</div>
                  )}
                </div>
              </div>

              <div>
                <h3 className="text-sm font-medium text-gray-400 mb-2">
                  Action Details
                </h3>
                <div className="p-3 bg-gray-800/50 border border-gray-700 rounded space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Action Type:</span>
                    <span className="text-gray-200">
                      {getActionDisplayName(log.action)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Result:</span>
                    <span className={`capitalize ${getResultColor(log.result)}`}>
                      {log.result}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Value Changes (for device control) */}
          {log.action === "device_control" &&
            (log.old_value !== undefined || log.new_value !== undefined) && (
              <div>
                <h3 className="text-sm font-medium text-gray-400 mb-2">
                  Value Changes
                </h3>
                <div className="p-4 bg-gray-800/50 border border-gray-700 rounded">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="p-3 bg-gray-900/50 border border-gray-700 rounded">
                      <div className="text-sm text-gray-400 mb-1">
                        Previous Value
                      </div>
                      <div className="text-lg font-mono text-gray-200">
                        {formatValue(log.old_value)}
                      </div>
                    </div>
                    <div className="p-3 bg-gray-900/50 border border-gray-700 rounded">
                      <div className="text-sm text-gray-400 mb-1">
                        New Value
                      </div>
                      <div className="text-lg font-mono text-gray-200">
                        {formatValue(log.new_value)}
                      </div>
                    </div>
                  </div>
                  {log.old_value !== undefined &&
                    log.new_value !== undefined && (
                      <div className="mt-4 text-sm text-gray-400">
                        Change:{" "}
                        <span className="text-gray-200">
                          {formatValue(log.old_value)} →{" "}
                          {formatValue(log.new_value)}
                        </span>
                      </div>
                    )}
                </div>
              </div>
            )}

          {/* Safety Validation */}
          {log.safety_validation && (
            <div>
              <h3 className="text-sm font-medium text-gray-400 mb-2 flex items-center gap-2">
                <Shield className="w-4 h-4" />
                Safety Validation
              </h3>
              <div className="p-4 bg-gray-800/50 border border-gray-700 rounded">
                <div className="space-y-3">
                  {log.safety_validation.rules_checked && (
                    <div>
                      <div className="text-sm text-gray-400 mb-1">
                        Rules Checked
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {log.safety_validation.rules_checked.map(
                          (rule: string, index: number) => (
                            <span
                              key={index}
                              className="px-2 py-1 text-xs bg-gray-900 text-gray-300 rounded"
                            >
                              {rule}
                            </span>
                          )
                        )}
                      </div>
                    </div>
                  )}

                  {log.safety_validation.passed_rules && (
                    <div>
                      <div className="text-sm text-gray-400 mb-1">
                        Passed Rules
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {log.safety_validation.passed_rules.map(
                          (rule: string, index: number) => (
                            <span
                              key={index}
                              className="px-2 py-1 text-xs bg-green-900/30 text-green-300 rounded"
                            >
                              ✓ {rule}
                            </span>
                          )
                        )}
                      </div>
                    </div>
                  )}

                  {log.safety_validation.failed_rules && (
                    <div>
                      <div className="text-sm text-gray-400 mb-1">
                        Failed Rules
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {log.safety_validation.failed_rules.map(
                          (rule: string, index: number) => (
                            <span
                              key={index}
                              className="px-2 py-1 text-xs bg-red-900/30 text-red-300 rounded"
                            >
                              ✗ {rule}
                            </span>
                          )
                        )}
                      </div>
                    </div>
                  )}

                  {log.safety_validation.warnings && (
                    <div>
                      <div className="text-sm text-gray-400 mb-1">Warnings</div>
                      <div className="flex flex-wrap gap-2">
                        {log.safety_validation.warnings.map(
                          (warning: string, index: number) => (
                            <span
                              key={index}
                              className="px-2 py-1 text-xs bg-yellow-900/30 text-yellow-300 rounded"
                            >
                              ⚠ {warning}
                            </span>
                          )
                        )}
                      </div>
                    </div>
                  )}

                  {log.safety_validation.details && (
                    <div>
                      <div className="text-sm text-gray-400 mb-1">Details</div>
                      <div className="text-gray-200">
                        {log.safety_validation.details}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Error Message */}
          {log.error_message && (
            <div>
              <h3 className="text-sm font-medium text-gray-400 mb-2">
                Error Details
              </h3>
              <div className="p-4 bg-red-900/20 border border-red-800 rounded">
                <div className="text-red-300">{log.error_message}</div>
              </div>
            </div>
          )}

          {/* Metadata */}
          {log.metadata && Object.keys(log.metadata).length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-gray-400 mb-2">
                Additional Information
              </h3>
              <div className="p-4 bg-gray-800/50 border border-gray-700 rounded">
                <pre className="text-sm text-gray-300 overflow-x-auto">
                  {JSON.stringify(log.metadata, null, 2)}
                </pre>
              </div>
            </div>
          )}

          {/* Raw Data (for debugging) */}
          <div className="pt-4 border-t border-gray-800">
            <details className="group">
              <summary className="cursor-pointer text-sm font-medium text-gray-400 hover:text-gray-300">
                Raw Audit Log Data
              </summary>
              <div className="mt-2 p-3 bg-gray-900 border border-gray-800 rounded">
                <pre className="text-xs text-gray-400 overflow-x-auto">
                  {JSON.stringify(log, null, 2)}
                </pre>
              </div>
            </details>
          </div>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 p-6 bg-gray-900 border-t border-gray-800">
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-400">
              Audit Log ID: <code className="text-gray-300">{log.id}</code>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm bg-gray-800 text-gray-300 rounded-md hover:bg-gray-700 transition-colors"
              >
                Close
              </button>
              {log.device_id && onViewDevice && (
                <button
                  onClick={() => {
                    onViewDevice(log.device_id!);
                    onClose();
                  }}
                  className="px-4 py-2 text-sm bg-blue-900/30 text-blue-300 rounded-md hover:bg-blue-900/50 transition-colors"
                >
                  View Device
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

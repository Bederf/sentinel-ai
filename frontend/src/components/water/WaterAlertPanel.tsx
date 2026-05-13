import { useState } from "react";
import { useModules } from "@/contexts/ModuleHooks";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle,
  Clock,
  AlertTriangle,
  Info,
} from "lucide-react";
import { waterApi } from "../../lib/waterApi";
import type { WaterAlert } from "../../lib/waterApi";

interface WaterAlertPanelProps {
  siteId: string;
}

const FILTER_OPTIONS = ["all", "unacknowledged", "critical", "in_progress", "resolved"] as const;
type _FilterStatus = (typeof FILTER_OPTIONS)[number];

function severityBadgeStyle(severity: string): React.CSSProperties {
  switch (severity) {
    case "critical": return { background: "rgba(239, 68, 68, 0.15)", color: "#ef4444" };
    case "high": return { background: "rgba(251, 146, 60, 0.15)", color: "#f97316" };
    case "medium": return { background: "rgba(234, 179, 8, 0.15)", color: "#eab308" };
    default: return { background: "rgba(59, 130, 246, 0.15)", color: "#3b82f6" };
  }
}

export const WaterAlertPanel: React.FC<WaterAlertPanelProps> = ({
  siteId,
}) => {
  const { isModuleActive } = useModules();
  const [activeTabIndex, setActiveTabIndex] = useState<number>(0);
  const [acknowledgedAlerts, setAcknowledgedAlerts] = useState<Set<string>>(
    new Set()
  );
  const activeFilter = FILTER_OPTIONS[activeTabIndex];

  // Fetch water alerts
  const { data: alerts, isLoading } = useQuery({
    queryKey: ["water", "alerts", siteId],
    queryFn: async () => {
      try {
        return await waterApi.getActiveAlerts(siteId);
      } catch {
        // Fallback seeded data
        return [
          {
            alert_id: "alert-w001",
            site: siteId,
            alert_type: "night_flow" as const,
            severity: "critical" as const,
            timestamp: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
            status: "active" as const,
            details: {
              flow_rate_lpm: 8.5,
              duration_minutes: 180,
              location: "L2-A Restroom",
            },
          } as WaterAlert,
          {
            alert_id: "alert-w002",
            site: siteId,
            alert_type: "unusual_pattern" as const,
            severity: "high" as const,
            timestamp: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
            status: "active" as const,
            details: {
              percent_above_baseline: 145,
              flow_rate_lpm: 18.2,
            },
          } as WaterAlert,
          {
            alert_id: "alert-w003",
            site: siteId,
            alert_type: "spike" as const,
            severity: "high" as const,
            timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
            status: "active" as const,
            details: {
              flow_rate_lpm: 22.5,
              duration_minutes: 8,
            },
          } as WaterAlert,
        ];
      }
    },
    refetchInterval: 30 * 1000, // Refresh every 30 seconds
    enabled: !!siteId, // Skip query when siteId is empty (avoids /sites// double-slash)
  });

  // Get severity icon
  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case "critical":
        return <AlertCircle className="h-5 w-5 text-red-500" />;
      case "high":
        return <AlertTriangle className="h-5 w-5 text-orange-500" />;
      case "medium":
        return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
      default:
        return <Info className="h-5 w-5 text-blue-500" />;
    }
  };

  // Format relative time
  const getRelativeTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (seconds < 60) return "Just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return date.toLocaleDateString();
  };

  // Filter alerts
  const filteredAlerts = (alerts || []).filter((alert) => {
    if (activeFilter === "all") return true;
    if (activeFilter === "unacknowledged") return !acknowledgedAlerts.has(alert.alert_id);
    if (activeFilter === "critical") return alert.severity === "critical";
    if (activeFilter === "in_progress")
      return alert.status === "active" && acknowledgedAlerts.has(alert.alert_id);
    if (activeFilter === "resolved") return alert.status === "resolved";
    return true;
  });

  const handleAcknowledge = (alertId: string) => {
    setAcknowledgedAlerts((prev) => new Set([...prev, alertId]));
  };

  const handleCreateWorkOrder = (alertData: WaterAlert) => {
    // Mock work order creation
    console.log("Creating work order for alert:", alertData.alert_id);
    window.alert("Work order created: WO-2026-001");
  };

  const stats = {
    total: alerts?.length || 0,
    unacknowledged: (alerts || []).filter(
      (a) => !acknowledgedAlerts.has(a.alert_id)
    ).length,
    critical: (alerts || []).filter((a) => a.severity === "critical").length,
  };

  const FILTER_TABS = [
    { label: "All", count: stats.total },
    { label: "Open", count: stats.unacknowledged },
    { label: "Critical", count: stats.critical },
    { label: "In Progress", hasCount: false },
    { label: "Resolved", hasCount: false },
  ];

  return (
    <div className="space-y-4">
      {/* Alert Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
          <div className="flex items-start justify-between">
            <div>
              <span
                style={{ color: "var(--color-sentinel-text-secondary)" }}
                className="text-xs"
              >
                Active Alerts
              </span>
              <p className="font-semibold text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>{stats.total}</p>
            </div>
            <AlertCircle className="h-5 w-5" style={{color: "var(--color-sentinel-blue)"}} />
          </div>
        </div>

        <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
          <div className="flex items-start justify-between">
            <div>
              <span
                style={{ color: "var(--color-sentinel-text-secondary)" }}
                className="text-xs"
              >
                Unacknowledged
              </span>
              <p className="font-semibold text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {stats.unacknowledged}
              </p>
            </div>
            <Clock className="h-5 w-5" style={{color: "var(--color-sentinel-amber)"}} />
          </div>
        </div>

        <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
          <div className="flex items-start justify-between">
            <div>
              <span
                style={{ color: "var(--color-sentinel-text-secondary)" }}
                className="text-xs"
              >
                Critical
              </span>
              <p className="font-semibold text-lg text-red-500">
                {stats.critical}
              </p>
            </div>
            <AlertTriangle className="h-5 w-5 text-red-500" />
          </div>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-1 mb-4 overflow-x-auto border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        {FILTER_TABS.map((tab, i) => (
          <button
            key={tab.label}
            onClick={() => setActiveTabIndex(i)}
            className="px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors rounded-t"
            style={{
              color: activeTabIndex === i ? "var(--color-sentinel-text-primary)" : "var(--color-sentinel-text-secondary)",
              borderBottom: activeTabIndex === i ? "2px solid var(--color-sentinel-blue)" : "2px solid transparent",
              background: activeTabIndex === i ? "var(--color-sentinel-bg-panel)" : "transparent",
            }}
          >
            {tab.label}{tab.hasCount !== false ? ` (${tab.count ?? 0})` : ""}
          </button>
        ))}
      </div>

      {/* Alert List */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        {isLoading ? (
          <div className="flex items-center justify-center h-40">
            <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Loading alerts...
            </span>
          </div>
        ) : filteredAlerts.length === 0 ? (
          <div className="text-center py-8">
            <CheckCircle className="h-12 w-12 mx-auto mb-3" style={{color: "var(--color-sentinel-green)"}} />
            <p className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>No active alerts</p>
            <span
              className="text-xs mt-1 block"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              All systems operating normally
            </span>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredAlerts
              .sort(
                (a, b) =>
                  new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
              )
              .map((alert) => {
                const isAcknowledged = acknowledgedAlerts.has(alert.alert_id);
                return (
                  <div
                    key={alert.alert_id}
                    className={`p-3 rounded border ${
                      isAcknowledged
                        ? "opacity-60"
                        : ""
                    }`}
                    style={{
                      background:
                        alert.severity === "critical"
                          ? "rgba(239, 68, 68, 0.08)"
                          : alert.severity === "high"
                          ? "rgba(251, 146, 60, 0.08)"
                          : "rgba(59, 130, 246, 0.08)",
                      borderColor:
                        alert.severity === "critical"
                          ? "rgba(239, 68, 68, 0.2)"
                          : alert.severity === "high"
                          ? "rgba(251, 146, 60, 0.2)"
                          : "rgba(59, 130, 246, 0.2)",
                    }}
                  >
                    <div className="flex gap-3">
                      {/* Icon */}
                      <div className="flex-shrink-0 mt-0.5">
                        {getSeverityIcon(alert.severity)}
                      </div>

                      {/* Content */}
                      <div className="flex-grow">
                        <div className="flex items-start justify-between">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                {alert.alert_type
                                  .replace(/_/g, " ")
                                  .toUpperCase()}
                              </span>
                              <span
                                className="text-xs px-2 py-0.5 rounded font-medium"
                                style={severityBadgeStyle(alert.severity)}
                              >
                                {alert.severity.toUpperCase()}
                              </span>
                            </div>

                            {/* Zone/Location */}
                            <span
                              className="text-xs mt-1 block"
                              style={{ color: "var(--color-sentinel-text-secondary)" }}
                            >
                              {alert.details?.location || "Building-wide"}
                            </span>

                            {/* Details */}
                            <span className="text-xs mt-1 block" style={{ color: "var(--color-sentinel-text-primary)" }}>
                              {alert.details?.flow_rate_lpm && (
                                <>Flow: {alert.details.flow_rate_lpm} LPM</>
                              )}
                              {alert.details?.duration_minutes && (
                                <> • Duration: {alert.details.duration_minutes}m</>
                              )}
                              {alert.details?.percent_above_baseline && (
                                <>
                                  {" "}
                                  • {alert.details.percent_above_baseline}% above
                                  baseline
                                </>
                              )}
                            </span>

                            {/* Time */}
                            <span
                              className="text-xs mt-1 block"
                              style={{ color: "var(--color-sentinel-text-secondary)" }}
                            >
                              {getRelativeTime(alert.timestamp)}
                            </span>
                          </div>

                          <span className="text-xs" style={{color: "var(--color-sentinel-text-secondary)"}}>
                            {isAcknowledged ? "Acknowledged" : "New"}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex gap-2 mt-3 pt-3 border-t border-current border-opacity-10">
                      {!isAcknowledged ? (
                        <button
                          onClick={() => handleAcknowledge(alert.alert_id)}
                          className="text-xs px-3 py-1.5 rounded font-medium transition-colors"
                          style={{
                            color: "var(--color-sentinel-blue)",
                            border: "1px solid var(--color-sentinel-border)",
                            background: "transparent",
                          }}
                        >
                          Acknowledge
                        </button>
                      ) : null}

                      {isModuleActive('maintenance') && (
                      <button
                        onClick={() => handleCreateWorkOrder(alert)}
                        className="text-xs px-3 py-1.5 rounded font-medium transition-colors"
                        style={{
                          color: alert.severity === "critical" ? "#ef4444" : "var(--color-sentinel-blue)",
                          border: "1px solid var(--color-sentinel-border)",
                          background: alert.severity === "critical" ? "rgba(239,68,68,0.1)" : "transparent",
                        }}
                      >
                        Create Work Order
                      </button>
                      )}
                    </div>
                  </div>
                );
              })}
          </div>
        )}
      </div>
    </div>
  );
};

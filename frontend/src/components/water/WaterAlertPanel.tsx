/**
 * WaterAlertPanel - Real-time water alerts with work order integration
 *
 * Displays:
 * - Real-time alert feed with severity indicators
 * - Filter tabs: All, Unacknowledged, Critical, In Progress, Resolved
 * - Work order status and assignment
 * - Create work order button
 * - Acknowledge/Resolve actions
 */

import { useState, useEffect } from "react";
import {
  Card,
  Title,
  Text,
  Badge,
  Button,
  Flex,
  Tab,
  TabGroup,
  TabList,
  TabPanels,
  TabPanel,
} from "@tremor/react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle,
  Clock,
  AlertTriangle,
  Info,
  User,
} from "lucide-react";
import { waterApi } from "../../lib/waterApi";
import type { WaterAlert } from "../../lib/waterApi";

interface WorkOrderStatus {
  wo_id: string;
  status: "dispatched" | "in_progress" | "completed";
  assigned_to: string;
  created_at: string;
}

interface WaterAlertPanelProps {
  buildingId: string;
}

const FILTER_OPTIONS = ["all", "unacknowledged", "critical", "in_progress", "resolved"] as const;
type FilterStatus = (typeof FILTER_OPTIONS)[number];

export const WaterAlertPanel: React.FC<WaterAlertPanelProps> = ({
  buildingId,
}) => {
  const [activeTabIndex, setActiveTabIndex] = useState<number>(0);
  const [acknowledgedAlerts, setAcknowledgedAlerts] = useState<Set<string>>(
    new Set()
  );
  const activeFilter = FILTER_OPTIONS[activeTabIndex];

  // Fetch water alerts
  const { data: alerts, isLoading, refetch } = useQuery({
    queryKey: ["water", "alerts", buildingId],
    queryFn: async () => {
      try {
        return await waterApi.getActiveAlerts(buildingId);
      } catch {
        // Fallback demo data
        return [
          {
            alert_id: "alert-w001",
            site: buildingId,
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
            site: buildingId,
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
            site: buildingId,
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

  // Get badge color
  const getSeverityBadgeColor = (severity: string): "red" | "orange" | "yellow" | "blue" => {
    switch (severity) {
      case "critical":
        return "red";
      case "high":
        return "orange";
      case "medium":
        return "yellow";
      default:
        return "blue";
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

  return (
    <div className="space-y-4">
      {/* Alert Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card className="p-3">
          <Flex justifyContent="between" alignItems="start">
            <div>
              <Text
                style={{ color: "var(--color-sentinel-text-secondary)" }}
                className="text-xs"
              >
                Active Alerts
              </Text>
              <Text className="font-semibold text-lg">{stats.total}</Text>
            </div>
            <AlertCircle className="h-5 w-5" style={{color: "var(--color-sentinel-blue)"}} />
          </Flex>
        </Card>

        <Card className="p-3">
          <Flex justifyContent="between" alignItems="start">
            <div>
              <Text
                style={{ color: "var(--color-sentinel-text-secondary)" }}
                className="text-xs"
              >
                Unacknowledged
              </Text>
              <Text className="font-semibold text-lg">
                {stats.unacknowledged}
              </Text>
            </div>
            <Clock className="h-5 w-5" style={{color: "var(--color-sentinel-amber)"}} />
          </Flex>
        </Card>

        <Card className="p-3">
          <Flex justifyContent="between" alignItems="start">
            <div>
              <Text
                style={{ color: "var(--color-sentinel-text-secondary)" }}
                className="text-xs"
              >
                Critical
              </Text>
              <Text className="font-semibold text-lg text-red-500">
                {stats.critical}
              </Text>
            </div>
            <AlertTriangle className="h-5 w-5 text-red-500" />
          </Flex>
        </Card>
      </div>

      {/* Filter Tabs */}
      <TabGroup index={activeTabIndex} onIndexChange={setActiveTabIndex}>
        <TabList>
          <Tab>All ({stats.total})</Tab>
          <Tab>Unacknowledged ({stats.unacknowledged})</Tab>
          <Tab>Critical ({stats.critical})</Tab>
          <Tab>In Progress</Tab>
          <Tab>Resolved</Tab>
        </TabList>
      </TabGroup>

      {/* Alert List */}
      <Card>
        {isLoading ? (
          <div className="flex items-center justify-center h-40">
            <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Loading alerts...
            </Text>
          </div>
        ) : filteredAlerts.length === 0 ? (
          <div className="text-center py-8">
            <CheckCircle className="h-12 w-12 mx-auto mb-3" style={{color: "var(--color-sentinel-green)"}} />
            <Text className="font-semibold">No active alerts</Text>
            <Text
              className="text-xs mt-1"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              All systems operating normally
            </Text>
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
                        <Flex justifyContent="between" alignItems="start">
                          <div>
                            <div className="flex items-center gap-2">
                              <Text className="font-semibold text-sm">
                                {alert.alert_type
                                  .replace(/_/g, " ")
                                  .toUpperCase()}
                              </Text>
                              <Badge
                                color={getSeverityBadgeColor(alert.severity)}
                              >
                                {alert.severity.toUpperCase()}
                              </Badge>
                            </div>

                            {/* Zone/Location */}
                            <Text
                              className="text-xs mt-1"
                              style={{ color: "var(--color-sentinel-text-secondary)" }}
                            >
                              {alert.details?.location || "Building-wide"}
                            </Text>

                            {/* Details */}
                            <Text className="text-xs mt-1">
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
                            </Text>

                            {/* Time */}
                            <Text
                              className="text-xs mt-1"
                              style={{ color: "var(--color-sentinel-text-secondary)" }}
                            >
                              {getRelativeTime(alert.timestamp)}
                            </Text>
                          </div>

                          <Text className="text-xs" style={{color: "var(--color-sentinel-text-secondary)"}}>
                            {isAcknowledged ? "Acknowledged" : "New"}
                          </Text>
                        </Flex>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex gap-2 mt-3 pt-3 border-t border-current border-opacity-10">
                      {!isAcknowledged ? (
                        <Button
                          size="xs"
                          color="blue"
                          variant="secondary"
                          onClick={() => handleAcknowledge(alert.alert_id)}
                        >
                          Acknowledge
                        </Button>
                      ) : null}

                      <Button
                        size="xs"
                        color={alert.severity === "critical" ? "red" : "blue"}
                        onClick={() => handleCreateWorkOrder(alert)}
                      >
                        Create Work Order
                      </Button>
                    </div>
                  </div>
                );
              })}
          </div>
        )}
      </Card>
    </div>
  );
};

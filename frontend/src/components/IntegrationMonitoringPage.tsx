/**
 * Integration Monitoring Page Component
 *
 * Features:
 * - Health Summary Cards (top row)
 * - Alerts Panel (if alerts exist)
 * - Sync Job History Table
 * - Unmatched Points Queue
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect, useCallback } from "react";
import {
  Activity,
  Database,
  Link as LinkIcon,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  ChevronRight,
  Server,
  Zap,
} from "lucide-react";
import { Badge, Callout, Title } from "@tremor/react";
import { monitoringApi } from "../lib/api";
import { GoLiveChecklist } from "./GoLiveChecklist";
import type {
  IntegrationHealthSummary,
  IntegrationAlert,
  DataQualityMetrics,
  SyncJobSummary,
  Site,
} from "../lib/api";
import api from "../lib/api";

// Health summary card component
interface HealthCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  accentColor: "blue" | "green" | "amber" | "red" | "purple";
}

function HealthCard({ title, value, subtitle, icon, accentColor }: HealthCardProps) {
  const colorMap = {
    blue: "var(--color-sentinel-blue)",
    green: "var(--color-sentinel-green)",
    amber: "var(--color-sentinel-amber)",
    red: "var(--color-sentinel-red)",
    purple: "#a855f7",
  };

  return (
    <div
      className="rounded-md p-4"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      <div className="flex items-center gap-3 mb-2">
        <div
          className="p-2 rounded"
          style={{ background: `${colorMap[accentColor]}20` }}
        >
          <div style={{ color: colorMap[accentColor] }}>{icon}</div>
        </div>
        <span
          className="text-xs font-medium uppercase tracking-wide"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          {title}
        </span>
      </div>
      <div
        className="text-2xl font-semibold mb-1"
        style={{ color: "var(--color-sentinel-text-primary)" }}
      >
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      {subtitle && (
        <div
          className="text-xs"
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        >
          {subtitle}
        </div>
      )}
    </div>
  );
}

// Alert item component
interface AlertItemProps {
  alert: IntegrationAlert;
  onDismiss: (id: string) => void;
}

function AlertItem({ alert, onDismiss }: AlertItemProps) {
  const severityColors = {
    critical: { bg: "rose", text: "var(--color-sentinel-red)" },
    warning: { bg: "amber", text: "var(--color-sentinel-amber)" },
    info: { bg: "blue", text: "var(--color-sentinel-blue)" },
  };

  const colors = severityColors[alert.severity];

  return (
    <Callout
      title={alert.type.replace(/_/g, " ").toUpperCase()}
      color={colors.bg as "rose" | "amber" | "blue"}
      className="mb-2"
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm">{alert.message}</p>
          <p className="text-xs mt-1 opacity-70">
            {new Date(alert.timestamp).toLocaleString()}
          </p>
        </div>
        <button
          onClick={() => onDismiss(alert.id)}
          className="px-2 py-1 text-xs rounded hover:opacity-80 transition-colors"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            color: "var(--color-sentinel-text-secondary)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          Dismiss
        </button>
      </div>
    </Callout>
  );
}

// Status badge component
function StatusBadge({ status }: { status: SyncJobSummary["status"] }) {
  const statusStyles = {
    success: { color: "green", text: "Success" },
    failed: { color: "red", text: "Failed" },
    running: { color: "blue", text: "Running" },
    partial: { color: "amber", text: "Partial" },
  };

  const style = statusStyles[status];

  return (
    <Badge color={style.color as "green" | "red" | "blue" | "amber"}>
      {style.text}
    </Badge>
  );
}

// Format processing time
function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}min`;
}

// Format relative time
function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins} minutes ago`;
  if (diffHours < 24) return `${diffHours} hours ago`;
  return `${diffDays} days ago`;
}

// Quality score color
function getQualityColor(score: number): string {
  if (score < 50) return "var(--color-sentinel-red)";
  if (score < 80) return "var(--color-sentinel-amber)";
  return "var(--color-sentinel-green)";
}

// Main component
export function IntegrationMonitoringPage() {
  // State
  const [health, setHealth] = useState<IntegrationHealthSummary | null>(null);
  const [qualityMetrics, setQualityMetrics] = useState<DataQualityMetrics | null>(null);
  const [syncJobs, setSyncJobs] = useState<SyncJobSummary[]>([]);
  const [unmatchedPoints, setUnmatchedPoints] = useState<Array<{
    point_id: string;
    point_name: string;
    last_seen: string;
    occurrence_count: number;
  }>>([]);
  const [unmatchedTotal, setUnmatchedTotal] = useState(0);
  const [dismissedAlerts, setDismissedAlerts] = useState<Set<string>>(new Set());
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedBuildingId, setSelectedBuildingId] = useState<string | null>(null);

  // Loading states
  const [loadingHealth, setLoadingHealth] = useState(true);
  const [loadingQuality, setLoadingQuality] = useState(false);
  const [loadingSyncJobs, setLoadingSyncJobs] = useState(true);
  const [loadingPoints, setLoadingPoints] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Pagination states
  const [syncJobsPage, setSyncJobsPage] = useState(0);
  const [pointsPage, setPointsPage] = useState(0);
  const syncJobsPerPage = 20;
  const pointsPerPage = 10;

  // Error state
  const [error, setError] = useState<string | null>(null);

  // Fetch all data
  const fetchData = useCallback(async (showRefreshing = false) => {
    if (showRefreshing) setIsRefreshing(true);
    setError(null);

    try {
      // Fetch health and sync jobs (no building filter required)
      setLoadingHealth(true);
      setLoadingSyncJobs(true);

      const [healthData, syncJobsData, sitesData] = await Promise.all([
        monitoringApi.getIntegrationHealth(selectedBuildingId || undefined),
        monitoringApi.getSyncJobs(selectedBuildingId || undefined),
        api.getSites(),
      ]);

      setHealth(healthData);
      setSyncJobs(syncJobsData);
      setSites(sitesData);
      setLoadingHealth(false);
      setLoadingSyncJobs(false);

      // Fetch unmatched points
      setLoadingPoints(true);
      try {
        const pointsData = await monitoringApi.getUnmatchedPoints(
          selectedBuildingId || undefined,
          pointsPerPage,
          pointsPage * pointsPerPage
        );
        setUnmatchedPoints(pointsData.points);
        setUnmatchedTotal(pointsData.total);
      } catch {
        // Gracefully handle if endpoint doesn't exist yet
        setUnmatchedPoints([]);
        setUnmatchedTotal(0);
      }
      setLoadingPoints(false);

      // Fetch quality metrics only if building selected
      if (selectedBuildingId) {
        setLoadingQuality(true);
        try {
          const qualityData = await monitoringApi.getDataQualityMetrics(selectedBuildingId);
          setQualityMetrics(qualityData);
        } catch {
          setQualityMetrics(null);
        }
        setLoadingQuality(false);
      } else {
        setQualityMetrics(null);
      }
    } catch (err) {
      console.error("Failed to fetch monitoring data:", err);
      setError("Failed to load integration monitoring data");
    } finally {
      setIsRefreshing(false);
      setLoadingHealth(false);
      setLoadingSyncJobs(false);
      setLoadingPoints(false);
      setLoadingQuality(false);
    }
  }, [selectedBuildingId, pointsPage]);

  // Initial data load
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Refresh handler
  const handleRefresh = () => {
    fetchData(true);
  };

  // Dismiss alert handler
  const handleDismissAlert = (alertId: string) => {
    setDismissedAlerts((prev) => new Set([...prev, alertId]));
  };

  // Filter out dismissed alerts
  const activeAlerts = health?.alerts.filter((a) => !dismissedAlerts.has(a.id)) || [];

  // Skeleton loader component
  const SkeletonCard = () => (
    <div
      className="rounded-md p-4 animate-pulse"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      <div className="flex items-center gap-3 mb-2">
        <div
          className="w-10 h-10 rounded"
          style={{ background: "var(--color-sentinel-bg-secondary)" }}
        />
        <div
          className="h-3 w-20 rounded"
          style={{ background: "var(--color-sentinel-bg-secondary)" }}
        />
      </div>
      <div
        className="h-6 w-16 rounded mb-1"
        style={{ background: "var(--color-sentinel-bg-secondary)" }}
      />
      <div
        className="h-3 w-24 rounded"
        style={{ background: "var(--color-sentinel-bg-secondary)" }}
      />
    </div>
  );

  // Error state
  if (error) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <Callout title="Error" color="rose" className="max-w-md">
          <p>{error}</p>
          <button
            onClick={handleRefresh}
            className="mt-4 px-4 py-2 rounded text-sm flex items-center gap-2"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            <RefreshCw className="w-4 h-4" />
            Retry
          </button>
        </Callout>
      </div>
    );
  }

  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1
            className="text-xl font-semibold"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Integration Monitoring
          </h1>
          <p
            className="text-sm"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Monitor BMS integration health, sync status, and data quality
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Building Filter */}
          <select
            value={selectedBuildingId || ""}
            onChange={(e) => setSelectedBuildingId(e.target.value || null)}
            className="text-sm rounded px-3 py-2"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            <option value="">All Buildings</option>
            {sites.map((site) => (
              <option key={site.id} value={site.id}>
                {site.name}
              </option>
            ))}
          </select>

          {/* Refresh button */}
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-3 py-2 rounded text-sm transition-colors hover:opacity-80"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-secondary)",
            }}
          >
            <RefreshCw
              className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`}
            />
            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </div>

      {/* Section 1: Health Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {loadingHealth ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <HealthCard
              title="Sources"
              value={health?.sources_count || 0}
              subtitle={`${health?.active_sources || 0} active`}
              icon={<Server className="w-5 h-5" />}
              accentColor="blue"
            />
            <HealthCard
              title="Records"
              value={health?.total_records_ingested || 0}
              subtitle="Total ingested"
              icon={<Database className="w-5 h-5" />}
              accentColor="green"
            />
            <HealthCard
              title="Point Coverage"
              value={`${health?.total_points_mapped || 0} mapped`}
              subtitle={`${health?.unmatched_points || 0} unmatched`}
              icon={<LinkIcon className="w-5 h-5" />}
              accentColor="amber"
            />
            <HealthCard
              title="Quality Score"
              value={
                qualityMetrics ? (
                  <span style={{ color: getQualityColor(qualityMetrics.overall_score) }}>
                    {qualityMetrics.overall_score.toFixed(0)}%
                  </span>
                ) : selectedBuildingId ? (
                  loadingQuality ? "..." : "N/A"
                ) : (
                  "Select building"
                )
              }
              subtitle={
                qualityMetrics
                  ? `Trend: ${qualityMetrics.trend}`
                  : selectedBuildingId
                  ? undefined
                  : "Building required"
              }
              icon={<Activity className="w-5 h-5" />}
              accentColor={
                qualityMetrics
                  ? qualityMetrics.overall_score >= 80
                    ? "green"
                    : qualityMetrics.overall_score >= 50
                    ? "amber"
                    : "red"
                  : "purple"
              }
            />
          </>
        )}
      </div>

      {/* Section 2: Alerts Panel */}
      {activeAlerts.length > 0 && (
        <div className="mb-6">
          <h2
            className="text-sm font-medium mb-3"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Active Alerts
          </h2>
          <div className="space-y-2">
            {activeAlerts.map((alert) => (
              <AlertItem
                key={alert.id}
                alert={alert}
                onDismiss={handleDismissAlert}
              />
            ))}
          </div>
        </div>
      )}

      {/* Section 3: Sync Job History */}
      <div
        className="rounded-md mb-6"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div
          className="p-4 flex items-center justify-between"
          style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{ background: "rgba(59, 130, 246, 0.15)" }}
            >
              <Zap
                className="w-5 h-5"
                style={{ color: "var(--color-sentinel-blue)" }}
              />
            </div>
            <div>
              <h3
                className="font-medium text-sm"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Sync Job History
              </h3>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Last 7 days
              </span>
            </div>
          </div>
        </div>

        <div className="overflow-x-auto">
          {loadingSyncJobs ? (
            <div className="p-8 text-center">
              <RefreshCw
                className="w-6 h-6 animate-spin mx-auto mb-2"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              />
              <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Loading sync jobs...
              </span>
            </div>
          ) : syncJobs.length === 0 ? (
            <div className="p-8 text-center">
              <Zap
                className="w-12 h-12 mx-auto mb-2"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              />
              <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                No sync jobs found
              </span>
            </div>
          ) : (
            <>
              <table className="w-full text-sm">
                <thead>
                  <tr
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      color: "var(--color-sentinel-text-secondary)",
                    }}
                  >
                    <th className="text-left px-4 py-3 font-medium">Source</th>
                    <th className="text-left px-4 py-3 font-medium">Status</th>
                    <th className="text-left px-4 py-3 font-medium">Records</th>
                    <th className="text-left px-4 py-3 font-medium">Duration</th>
                    <th className="text-left px-4 py-3 font-medium">Started</th>
                  </tr>
                </thead>
                <tbody>
                  {syncJobs
                    .slice(
                      syncJobsPage * syncJobsPerPage,
                      (syncJobsPage + 1) * syncJobsPerPage
                    )
                    .map((job) => (
                      <tr
                        key={job.id}
                        className="border-t"
                        style={{
                          borderColor: "var(--color-sentinel-border)",
                          color: "var(--color-sentinel-text-primary)",
                        }}
                      >
                        <td className="px-4 py-3">
                          {job.source_name || job.log_source_id}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={job.status} />
                          {job.error_message && (
                            <span
                              className="block text-xs mt-1"
                              style={{ color: "var(--color-sentinel-red)" }}
                            >
                              {job.error_message}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-xs">
                            {job.records_processed} processed
                            {job.records_failed > 0 && (
                              <span
                                style={{ color: "var(--color-sentinel-red)" }}
                              >
                                {" "}
                                / {job.records_failed} failed
                              </span>
                            )}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {formatDuration(job.processing_time_ms)}
                        </td>
                        <td
                          className="px-4 py-3"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          {formatRelativeTime(job.started_at)}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>

              {/* Load More button */}
              {syncJobs.length > (syncJobsPage + 1) * syncJobsPerPage && (
                <div className="p-4 text-center">
                  <button
                    onClick={() => setSyncJobsPage((p) => p + 1)}
                    className="px-4 py-2 rounded text-sm transition-colors hover:opacity-80"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-secondary)",
                    }}
                  >
                    Load More
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Section 4: Unmatched Points Queue */}
      <div
        className="rounded-md"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div
          className="p-4 flex items-center justify-between"
          style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{ background: "rgba(245, 158, 11, 0.15)" }}
            >
              <AlertTriangle
                className="w-5 h-5"
                style={{ color: "var(--color-sentinel-amber)" }}
              />
            </div>
            <div>
              <h3
                className="font-medium text-sm"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Unmatched Points Queue
              </h3>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Points awaiting asset mapping
              </span>
            </div>
          </div>

          <Badge color="amber">{unmatchedTotal} unmatched</Badge>
        </div>

        {unmatchedTotal > 0 && (
          <Callout
            title="Action Required"
            color="amber"
            className="m-4"
          >
            Unmatched points won't trigger alerts or predictions. Review and map
            them to assets.
          </Callout>
        )}

        <div className="overflow-x-auto">
          {loadingPoints ? (
            <div className="p-8 text-center">
              <RefreshCw
                className="w-6 h-6 animate-spin mx-auto mb-2"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              />
              <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Loading unmatched points...
              </span>
            </div>
          ) : unmatchedPoints.length === 0 ? (
            <div className="p-8 text-center">
              <CheckCircle
                className="w-12 h-12 mx-auto mb-2"
                style={{ color: "var(--color-sentinel-green)" }}
              />
              <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                All points are mapped
              </span>
            </div>
          ) : (
            <>
              <table className="w-full text-sm">
                <thead>
                  <tr
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      color: "var(--color-sentinel-text-secondary)",
                    }}
                  >
                    <th className="text-left px-4 py-3 font-medium">Point ID</th>
                    <th className="text-left px-4 py-3 font-medium">Point Name</th>
                    <th className="text-left px-4 py-3 font-medium">Last Seen</th>
                    <th className="text-left px-4 py-3 font-medium">Occurrences</th>
                    <th className="text-right px-4 py-3 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {unmatchedPoints.map((point) => (
                    <tr
                      key={point.point_id}
                      className="border-t"
                      style={{
                        borderColor: "var(--color-sentinel-border)",
                        color: "var(--color-sentinel-text-primary)",
                      }}
                    >
                      <td className="px-4 py-3 font-mono text-xs">
                        {point.point_id}
                      </td>
                      <td className="px-4 py-3">{point.point_name}</td>
                      <td
                        className="px-4 py-3"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
                      >
                        {formatRelativeTime(point.last_seen)}
                      </td>
                      <td className="px-4 py-3">{point.occurrence_count}</td>
                      <td className="px-4 py-3 text-right">
                        <a
                          href="/integrations/wizard"
                          className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors hover:opacity-80"
                          style={{
                            background: "var(--color-sentinel-bg-secondary)",
                            border: "1px solid var(--color-sentinel-border)",
                            color: "var(--color-sentinel-text-secondary)",
                          }}
                        >
                          Review
                          <ChevronRight className="w-3 h-3" />
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Pagination */}
              {unmatchedTotal > pointsPerPage && (
                <div className="p-4 flex items-center justify-between">
                  <span
                    className="text-xs"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Showing {pointsPage * pointsPerPage + 1}-
                    {Math.min(
                      (pointsPage + 1) * pointsPerPage,
                      unmatchedTotal
                    )}{" "}
                    of {unmatchedTotal}
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setPointsPage((p) => Math.max(0, p - 1))}
                      disabled={pointsPage === 0}
                      className="px-3 py-1 rounded text-xs transition-colors hover:opacity-80 disabled:opacity-50"
                      style={{
                        background: "var(--color-sentinel-bg-secondary)",
                        border: "1px solid var(--color-sentinel-border)",
                        color: "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      Previous
                    </button>
                    <button
                      onClick={() => setPointsPage((p) => p + 1)}
                      disabled={
                        (pointsPage + 1) * pointsPerPage >= unmatchedTotal
                      }
                      className="px-3 py-1 rounded text-xs transition-colors hover:opacity-80 disabled:opacity-50"
                      style={{
                        background: "var(--color-sentinel-bg-secondary)",
                        border: "1px solid var(--color-sentinel-border)",
                        color: "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Section 5: Go-Live Validation */}
      {selectedBuildingId && (
        <div className="mt-6">
          <Title className="mb-4">Go-Live Validation</Title>
          <GoLiveChecklist buildingId={selectedBuildingId} />
        </div>
      )}
    </div>
  );
}

export default IntegrationMonitoringPage;

/**
 * ML Metrics Dashboard
 *
 * Visualizes MLOps health, success metrics, drift status, alerts,
 * and performance reports.
 *
 * Phase 45-03: MLOps Monitoring and Success Metrics.
 */

import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  Target,
  BarChart3,
  Shield,
  XCircle,
  Clock,
  FileText,
} from "lucide-react";
import {
  mlopsApi,
  type SuccessMetrics,
  type AllDriftResult,
  type MLAlert,
  type MLOpsHealth,
  type PerformanceReport,
} from "../lib/mlopsApi";

// --- Skeleton ---
function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded ${className}`}
      style={{ background: "var(--color-sentinel-bg-secondary)" }}
    />
  );
}

// --- Metric Card ---
function MetricCard({
  title,
  current,
  target,
  unit,
  met,
  inverse = false,
  description,
}: {
  title: string;
  current: number;
  target: number;
  unit: string;
  met: boolean;
  inverse?: boolean;
  description: string;
}) {
  // Calculate progress as percentage of target
  const progress = inverse
    ? Math.max(0, Math.min(100, (1 - current / target) * 100))
    : Math.min(100, (current / target) * 100);

  return (
    <div
      className="rounded-lg p-4"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: `1px solid ${met ? "rgba(16, 185, 129, 0.3)" : "rgba(245, 158, 11, 0.3)"}`,
      }}
    >
      <div className="flex items-start justify-between mb-2">
        <span
          className="text-xs font-medium uppercase tracking-wide"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          {title}
        </span>
        {met ? (
          <CheckCircle className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
        ) : (
          <AlertTriangle className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
        )}
      </div>

      <div className="flex items-baseline gap-2 mb-1">
        <span
          className="text-2xl font-bold"
          style={{
            color: met ? "var(--color-sentinel-green)" : "var(--color-sentinel-amber)",
          }}
        >
          {current}
          <span className="text-sm font-normal ml-0.5">{unit}</span>
        </span>
        <span
          className="text-xs"
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        >
          {inverse ? `< ${target}${unit} target` : `${target}${unit} target`}
        </span>
      </div>

      {/* Progress bar */}
      <div
        className="h-1.5 rounded-full overflow-hidden mb-2"
        style={{ background: "var(--color-sentinel-bg-secondary)" }}
      >
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${progress}%`,
            background: met ? "var(--color-sentinel-green)" : "var(--color-sentinel-amber)",
          }}
        />
      </div>

      <p
        className="text-xs"
        style={{ color: "var(--color-sentinel-text-disabled)" }}
      >
        {description}
      </p>
    </div>
  );
}

// --- Overall Score Ring ---
function ScoreRing({ score, label }: { score: number; label: string }) {
  const circumference = 2 * Math.PI * 40;
  const dashoffset = circumference - (score / 100) * circumference;
  const color =
    score >= 80
      ? "var(--color-sentinel-green)"
      : score >= 60
        ? "var(--color-sentinel-amber)"
        : "var(--color-sentinel-red)";

  return (
    <div className="flex flex-col items-center">
      <svg width="96" height="96" viewBox="0 0 96 96">
        <circle
          cx="48"
          cy="48"
          r="40"
          fill="none"
          stroke="var(--color-sentinel-bg-secondary)"
          strokeWidth="6"
        />
        <circle
          cx="48"
          cy="48"
          r="40"
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashoffset}
          transform="rotate(-90 48 48)"
          className="transition-all duration-700"
        />
        <text
          x="48"
          y="44"
          textAnchor="middle"
          fill={color}
          fontSize="20"
          fontWeight="bold"
        >
          {Math.round(score)}
        </text>
        <text
          x="48"
          y="58"
          textAnchor="middle"
          fill="var(--color-sentinel-text-disabled)"
          fontSize="10"
        >
          / 100
        </text>
      </svg>
      <span
        className="text-xs mt-1"
        style={{ color: "var(--color-sentinel-text-secondary)" }}
      >
        {label}
      </span>
    </div>
  );
}

// --- Drift Status Row ---
function DriftRow({
  label,
  drifted,
  details,
}: {
  label: string;
  drifted: boolean;
  details: string;
}) {
  return (
    <div
      className="flex items-center justify-between py-2 px-3 rounded"
      style={{
        background: drifted
          ? "rgba(245, 158, 11, 0.08)"
          : "rgba(16, 185, 129, 0.05)",
      }}
    >
      <div className="flex items-center gap-2">
        {drifted ? (
          <TrendingDown className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
        ) : (
          <TrendingUp className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
        )}
        <span
          className="text-sm font-medium"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          {label}
        </span>
      </div>
      <span
        className="text-xs"
        style={{
          color: drifted
            ? "var(--color-sentinel-amber)"
            : "var(--color-sentinel-text-disabled)",
        }}
      >
        {details}
      </span>
    </div>
  );
}

// --- Alert Item ---
function AlertItem({ alert }: { alert: MLAlert }) {
  const severityColor =
    alert.severity === "critical"
      ? "var(--color-sentinel-red)"
      : alert.severity === "warning"
        ? "var(--color-sentinel-amber)"
        : "var(--color-sentinel-text-secondary)";

  return (
    <div
      className="flex items-start gap-3 py-2 px-3 rounded"
      style={{
        background: "var(--color-sentinel-bg-secondary)",
        borderLeft: `3px solid ${severityColor}`,
      }}
    >
      <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" style={{ color: severityColor }} />
      <div className="flex-1 min-w-0">
        <div
          className="text-sm font-medium"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          {alert.title}
        </div>
        <div
          className="text-xs mt-0.5 truncate"
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        >
          {alert.message}
        </div>
      </div>
      <span
        className="text-[10px] px-1.5 py-0.5 rounded uppercase font-medium flex-shrink-0"
        style={{
          background: `${severityColor}22`,
          color: severityColor,
        }}
      >
        {alert.severity}
      </span>
    </div>
  );
}

// --- Main Component ---
export function MLMetrics() {
  const [health, setHealth] = useState<MLOpsHealth | null>(null);
  const [metrics, setMetrics] = useState<SuccessMetrics | null>(null);
  const [drift, setDrift] = useState<AllDriftResult | null>(null);
  const [alerts, setAlerts] = useState<MLAlert[]>([]);
  const [report, setReport] = useState<PerformanceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadData = async () => {
    try {
      setError(null);
      const [healthData, metricsData, driftData, alertsData] = await Promise.all([
        mlopsApi.getHealth(),
        mlopsApi.getMetrics(),
        mlopsApi.getAllDrift(),
        mlopsApi.getAlerts({ limit: 10 }),
      ]);
      setHealth(healthData);
      setMetrics(metricsData);
      setDrift(driftData);
      setAlerts(alertsData.alerts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load MLOps data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 60000);
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const handleGenerateReport = async (period: "weekly" | "monthly") => {
    try {
      const r = await mlopsApi.generateReport(period);
      setReport(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report generation failed");
    }
  };

  if (loading) {
    return (
      <div className="h-full overflow-y-auto p-4 md:p-6 space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-8 w-24" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  const m = metrics?.metrics;

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Activity
            className="h-6 w-6"
            style={{ color: "var(--color-sentinel-amber)" }}
          />
          <div>
            <h1
              className="text-lg font-bold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              MLOps Monitoring
            </h1>
            <p
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              Model performance, drift detection, and success metrics
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Health badge */}
          {health && (
            <span
              className="text-xs px-2 py-1 rounded font-medium uppercase"
              style={{
                background:
                  health.status === "healthy"
                    ? "rgba(16, 185, 129, 0.15)"
                    : health.status === "warning"
                      ? "rgba(245, 158, 11, 0.15)"
                      : "rgba(220, 38, 38, 0.15)",
                color:
                  health.status === "healthy"
                    ? "var(--color-sentinel-green)"
                    : health.status === "warning"
                      ? "var(--color-sentinel-amber)"
                      : "var(--color-sentinel-red)",
              }}
            >
              {health.status === "healthy" ? (
                <Shield className="h-3 w-3 inline mr-1" />
              ) : (
                <AlertTriangle className="h-3 w-3 inline mr-1" />
              )}
              {health.status}
            </span>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="p-2 rounded-md transition-colors hover:brightness-110"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <RefreshCw
              className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`}
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            />
          </button>
        </div>
      </div>

      {error && (
        <div
          className="p-3 rounded flex items-center gap-2"
          style={{
            background: "rgba(220, 38, 38, 0.1)",
            border: "1px solid rgba(220, 38, 38, 0.3)",
          }}
        >
          <XCircle className="h-4 w-4" style={{ color: "var(--color-sentinel-red)" }} />
          <span className="text-sm" style={{ color: "var(--color-sentinel-red)" }}>
            {error}
          </span>
        </div>
      )}

      {/* Overall Score + Targets Summary */}
      <div
        className="rounded-lg p-4 flex flex-col md:flex-row items-center gap-6"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <ScoreRing
          score={health?.overall_score ?? metrics?.overall_score ?? 0}
          label="ML System Score"
        />
        <div className="flex-1 grid grid-cols-2 md:grid-cols-3 gap-3">
          <div className="text-center">
            <div
              className="text-2xl font-bold"
              style={{ color: "var(--color-sentinel-green)" }}
            >
              {metrics?.targets_met ?? 0}/{metrics?.total_targets ?? 5}
            </div>
            <div
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              Targets Met
            </div>
          </div>
          <div className="text-center">
            <div
              className="text-2xl font-bold"
              style={{
                color: health?.critical_alerts
                  ? "var(--color-sentinel-red)"
                  : "var(--color-sentinel-green)",
              }}
            >
              {health?.critical_alerts ?? 0}
            </div>
            <div
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              Critical Alerts
            </div>
          </div>
          <div className="text-center">
            <div
              className="text-2xl font-bold"
              style={{
                color: health?.drift_detected
                  ? "var(--color-sentinel-amber)"
                  : "var(--color-sentinel-green)",
              }}
            >
              {health?.drift_detected ? "Yes" : "No"}
            </div>
            <div
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              Drift Detected
            </div>
          </div>
        </div>
      </div>

      {/* Success Metrics Cards */}
      {m && (
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
          <MetricCard
            title="Failure Reduction"
            current={m.unplanned_failure_reduction.current}
            target={m.unplanned_failure_reduction.target}
            unit={m.unplanned_failure_reduction.unit}
            met={m.unplanned_failure_reduction.met}
            description={m.unplanned_failure_reduction.description}
          />
          <MetricCard
            title="Planning Accuracy"
            current={m.maintenance_planning_accuracy.current}
            target={m.maintenance_planning_accuracy.target}
            unit={m.maintenance_planning_accuracy.unit}
            met={m.maintenance_planning_accuracy.met}
            description={m.maintenance_planning_accuracy.description}
          />
          <MetricCard
            title="False Positive Rate"
            current={m.false_positive_rate.current}
            target={m.false_positive_rate.target}
            unit={m.false_positive_rate.unit}
            met={m.false_positive_rate.met}
            inverse
            description={m.false_positive_rate.description}
          />
          <MetricCard
            title="Time to Detect"
            current={m.mean_time_to_detect.current}
            target={m.mean_time_to_detect.target}
            unit={m.mean_time_to_detect.unit}
            met={m.mean_time_to_detect.met}
            inverse
            description={m.mean_time_to_detect.description}
          />
          <MetricCard
            title="Lead Time"
            current={m.prediction_lead_time.current}
            target={m.prediction_lead_time.target}
            unit={m.prediction_lead_time.unit}
            met={m.prediction_lead_time.met}
            description={m.prediction_lead_time.description}
          />
        </div>
      )}

      {/* Drift Status + Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Drift Status */}
        <div
          className="rounded-lg p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Target className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
            <h2
              className="text-sm font-bold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Drift Detection
            </h2>
          </div>

          <div className="space-y-2">
            {drift?.feature_drift.map((fd) => (
              <DriftRow
                key={fd.equipment_type}
                label={fd.equipment_type ?? "unknown"}
                drifted={fd.drift_detected}
                details={
                  fd.drift_detected
                    ? `${fd.features_drifted}/${fd.features_checked} features`
                    : "Stable"
                }
              />
            ))}
            {drift?.model_drift.map((md) => (
              <DriftRow
                key={md.model_type}
                label={`${md.model_type} model`}
                drifted={md.drift_detected}
                details={
                  md.drift_detected
                    ? `${md.degradation_pct}% degradation`
                    : `${((md.recent_accuracy ?? 0) * 100).toFixed(1)}% accuracy`
                }
              />
            ))}
          </div>
        </div>

        {/* ML Alerts */}
        <div
          className="rounded-lg p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
              <h2
                className="text-sm font-bold"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                ML Alerts
              </h2>
            </div>
            <span
              className="text-xs px-2 py-0.5 rounded"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                color: "var(--color-sentinel-text-disabled)",
              }}
            >
              {alerts.length} alert{alerts.length !== 1 ? "s" : ""}
            </span>
          </div>

          <div className="space-y-2 max-h-64 overflow-y-auto">
            {alerts.length === 0 ? (
              <div
                className="text-center py-6 text-sm"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                <CheckCircle className="h-8 w-8 mx-auto mb-2 opacity-50" />
                No active alerts
              </div>
            ) : (
              alerts.map((alert) => <AlertItem key={alert.id} alert={alert} />)
            )}
          </div>
        </div>
      </div>

      {/* Reports Section */}
      <div
        className="rounded-lg p-4"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
            <h2
              className="text-sm font-bold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Performance Reports
            </h2>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleGenerateReport("weekly")}
              className="text-xs px-3 py-1.5 rounded transition-colors hover:brightness-110"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              <Clock className="h-3 w-3 inline mr-1" />
              Weekly
            </button>
            <button
              onClick={() => handleGenerateReport("monthly")}
              className="text-xs px-3 py-1.5 rounded transition-colors hover:brightness-110"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              <BarChart3 className="h-3 w-3 inline mr-1" />
              Monthly
            </button>
          </div>
        </div>

        {report ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {report.period_label}
              </span>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                Generated {new Date(report.generated_at).toLocaleString("en-ZA")}
              </span>
            </div>

            {/* Recommendations */}
            {report.recommendations.map((rec, i) => (
              <div
                key={i}
                className="flex items-start gap-2 py-2 px-3 rounded"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  borderLeft: `3px solid ${
                    rec.priority === "high"
                      ? "var(--color-sentinel-red)"
                      : rec.priority === "medium"
                        ? "var(--color-sentinel-amber)"
                        : "var(--color-sentinel-green)"
                  }`,
                }}
              >
                <span
                  className="text-[10px] px-1 py-0.5 rounded uppercase font-medium flex-shrink-0 mt-0.5"
                  style={{
                    background:
                      rec.priority === "high"
                        ? "rgba(220, 38, 38, 0.15)"
                        : rec.priority === "medium"
                          ? "rgba(245, 158, 11, 0.15)"
                          : "rgba(16, 185, 129, 0.15)",
                    color:
                      rec.priority === "high"
                        ? "var(--color-sentinel-red)"
                        : rec.priority === "medium"
                          ? "var(--color-sentinel-amber)"
                          : "var(--color-sentinel-green)",
                  }}
                >
                  {rec.priority}
                </span>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  {rec.action}
                </span>
              </div>
            ))}

            {/* Prediction Outcomes */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-2">
              {[
                { label: "Total Predictions", value: report.prediction_outcomes.total },
                { label: "True Positives", value: report.prediction_outcomes.true_positives },
                { label: "False Positives", value: report.prediction_outcomes.false_positives },
                { label: "False Negatives", value: report.prediction_outcomes.false_negatives },
              ].map((stat) => (
                <div
                  key={stat.label}
                  className="text-center py-2 rounded"
                  style={{ background: "var(--color-sentinel-bg-secondary)" }}
                >
                  <div
                    className="text-lg font-bold"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    {stat.value}
                  </div>
                  <div
                    className="text-[10px]"
                    style={{ color: "var(--color-sentinel-text-disabled)" }}
                  >
                    {stat.label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div
            className="text-center py-8 text-sm"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
            Generate a weekly or monthly report to see performance analysis
          </div>
        )}
      </div>
    </div>
  );
}

export default MLMetrics;

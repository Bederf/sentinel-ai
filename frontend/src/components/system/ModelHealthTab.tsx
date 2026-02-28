/**
 * Model Health Tab — ML model status, performance, and A/B testing
 *
 * Extracted from SimulationDashboard ModelHealthTab.
 * Shows model freshness, prediction accuracy (with confusion matrix),
 * model status table, and A/B test tracking.
 */

import { useState, useEffect, useCallback } from "react";
import type { ReactElement } from "react";
import {
  Activity,
  AlertTriangle,
  Brain,
  CheckCircle,
  XCircle,
  Clock,
  RefreshCw,
  Target,
  FlaskConical,
} from "lucide-react";
import {
  fetchModelStatus,
  fetchModelHealth,
  fetchPerformance,
  fetchABTests,
} from "../../lib/simulationApi";
import type {
  ModelStatusResponse,
  ModelHealthSummary,
  PerformanceEvaluation,
  ABTest,
} from "../../lib/simulationApi";
import { PageLoading } from "../PageLoading";

// ---------- Helpers ----------

function MetricBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 80
      ? "var(--color-sentinel-green)"
      : pct >= 50
        ? "var(--color-sentinel-amber)"
        : "var(--color-sentinel-red)";

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span
          className="text-xs font-medium"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          {label}
        </span>
        <span className="text-xs font-mono font-bold" style={{ color }}>
          {pct}%
        </span>
      </div>
      <div
        className="h-2 rounded-full overflow-hidden"
        style={{ background: "var(--color-sentinel-bg-primary)" }}
      >
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}

function modelStatusColor(status: string): string {
  switch (status) {
    case "fresh":
      return "var(--color-sentinel-green)";
    case "stale":
      return "var(--color-sentinel-amber)";
    case "missing":
      return "var(--color-sentinel-red)";
    case "underperforming":
      return "var(--color-sentinel-red)";
    default:
      return "var(--color-sentinel-text-secondary)";
  }
}

function abTestStatusColor(status: string): string {
  switch (status) {
    case "running":
      return "var(--color-sentinel-blue)";
    case "completed":
      return "var(--color-sentinel-green)";
    case "promoted":
      return "var(--color-sentinel-green)";
    case "cancelled":
      return "var(--color-sentinel-text-disabled)";
    default:
      return "var(--color-sentinel-text-secondary)";
  }
}

function KpiCard({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: string;
  icon: ReactElement;
  color?: string;
}) {
  return (
    <div
      className="rounded-md p-4"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span style={{ color: color ?? "var(--color-sentinel-text-secondary)" }}>
          {icon}
        </span>
        <span
          className="text-xs font-medium"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          {label}
        </span>
      </div>
      <div
        className="text-2xl font-bold"
        style={{ color: color ?? "var(--color-sentinel-text-primary)" }}
      >
        {value}
      </div>
    </div>
  );
}

// ---------- Main Component ----------

export function ModelHealthTab() {
  const [modelStatus, setModelStatus] = useState<ModelStatusResponse | null>(null);
  const [health, setHealth] = useState<ModelHealthSummary | null>(null);
  const [performance, setPerformance] = useState<PerformanceEvaluation | null>(null);
  const [abTests, setAbTests] = useState<ABTest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusData, healthData, perfData, testsData] = await Promise.all([
        fetchModelStatus(),
        fetchModelHealth(),
        fetchPerformance(),
        fetchABTests(),
      ]);
      setModelStatus(statusData);
      setHealth(healthData);
      setPerformance(perfData);
      setAbTests(testsData.tests);
    } catch {
      setError("Failed to load model health data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return <PageLoading message="Loading model health data..." />;
  }

  const summary = health?.summary;
  const metrics = performance?.metrics;

  return (
    <div className="space-y-6">
      {/* Error */}
      {error && (
        <div
          className="rounded-md p-4 flex items-center gap-3"
          style={{
            background: "rgba(220, 38, 38, 0.1)",
            border: "1px solid rgba(220, 38, 38, 0.3)",
          }}
        >
          <AlertTriangle className="h-5 w-5" style={{ color: "var(--color-sentinel-red)" }} />
          <span style={{ color: "var(--color-sentinel-text-primary)" }}>{error}</span>
        </div>
      )}

      {/* Header + Refresh */}
      <div className="flex items-center justify-between">
        <div>
          <h3
            className="text-sm font-semibold"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            ML Model Health Overview
          </h3>
          <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Model freshness, prediction accuracy, and A/B test status
          </p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
            color: "var(--color-sentinel-text-primary)",
          }}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>

      {/* Health Summary KPIs */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <KpiCard
            label="Health"
            value={`${summary.health_pct.toFixed(0)}%`}
            icon={<Brain className="h-4 w-4" />}
            color={
              summary.health_pct >= 80
                ? "var(--color-sentinel-green)"
                : summary.health_pct >= 50
                  ? "var(--color-sentinel-amber)"
                  : "var(--color-sentinel-red)"
            }
          />
          <KpiCard
            label="Fresh"
            value={String(summary.fresh)}
            icon={<CheckCircle className="h-4 w-4" />}
            color="var(--color-sentinel-green)"
          />
          <KpiCard
            label="Stale"
            value={String(summary.stale)}
            icon={<Clock className="h-4 w-4" />}
            color={summary.stale > 0 ? "var(--color-sentinel-amber)" : undefined}
          />
          <KpiCard
            label="Missing"
            value={String(summary.missing)}
            icon={<XCircle className="h-4 w-4" />}
            color={summary.missing > 0 ? "var(--color-sentinel-red)" : undefined}
          />
          <KpiCard
            label="Total Slots"
            value={String(summary.total_model_slots)}
            icon={<Activity className="h-4 w-4" />}
          />
        </div>
      )}

      {/* Prediction Performance Metrics */}
      {metrics && (
        <div
          className="rounded-md p-5"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center gap-2 mb-4">
            <Target className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
            <h3
              className="text-sm font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Prediction Accuracy
            </h3>
            {performance?.period_days && (
              <span
                className="text-xs ml-auto"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Last {performance.period_days} days
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricBar label="Accuracy" value={metrics.accuracy} />
            <MetricBar label="Precision" value={metrics.precision} />
            <MetricBar label="Recall" value={metrics.recall} />
            <MetricBar label="F1 Score" value={metrics.f1_score} />
          </div>
          {performance?.confusion_matrix && (
            <div className="mt-4 grid grid-cols-4 gap-2 text-center">
              <div
                className="rounded p-2"
                style={{ background: "var(--color-sentinel-bg-primary)" }}
              >
                <div className="text-lg font-bold" style={{ color: "var(--color-sentinel-green)" }}>
                  {performance.confusion_matrix.true_positives}
                </div>
                <div className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>True Pos</div>
              </div>
              <div
                className="rounded p-2"
                style={{ background: "var(--color-sentinel-bg-primary)" }}
              >
                <div className="text-lg font-bold" style={{ color: "var(--color-sentinel-red)" }}>
                  {performance.confusion_matrix.false_positives}
                </div>
                <div className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>False Pos</div>
              </div>
              <div
                className="rounded p-2"
                style={{ background: "var(--color-sentinel-bg-primary)" }}
              >
                <div className="text-lg font-bold" style={{ color: "var(--color-sentinel-amber)" }}>
                  {performance.confusion_matrix.false_negatives}
                </div>
                <div className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>False Neg</div>
              </div>
              <div
                className="rounded p-2"
                style={{ background: "var(--color-sentinel-bg-primary)" }}
              >
                <div className="text-lg font-bold" style={{ color: "var(--color-sentinel-green)" }}>
                  {performance.confusion_matrix.true_negatives}
                </div>
                <div className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>True Neg</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Model Status Table */}
      {modelStatus && modelStatus.models.length > 0 && (
        <div
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
          >
            <h3 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Model Status
            </h3>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {modelStatus.needs_retrain} of {modelStatus.total_models_checked} need retraining
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                  <th className="text-left px-4 py-2 font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>Model Type</th>
                  <th className="text-left px-4 py-2 font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>Equipment</th>
                  <th className="text-left px-4 py-2 font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>Status</th>
                  <th className="text-right px-4 py-2 font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>Age (days)</th>
                  <th className="text-right px-4 py-2 font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>R² Score</th>
                  <th className="text-left px-4 py-2 font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>Reason</th>
                </tr>
              </thead>
              <tbody>
                {modelStatus.models.map((m, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                    <td className="px-4 py-2 font-mono uppercase" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {m.model_type}
                    </td>
                    <td className="px-4 py-2 capitalize" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {m.equipment_type}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className="px-2 py-0.5 rounded text-xs font-medium"
                        style={{
                          background: modelStatusColor(m.status) + "20",
                          color: modelStatusColor(m.status),
                        }}
                      >
                        {m.status}
                      </span>
                    </td>
                    <td className="text-right px-4 py-2 font-mono" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {m.age_days != null ? m.age_days : "-"}
                    </td>
                    <td
                      className="text-right px-4 py-2 font-mono"
                      style={{
                        color:
                          m.r2_score != null
                            ? m.r2_score >= 0.65
                              ? "var(--color-sentinel-green)"
                              : "var(--color-sentinel-red)"
                            : "var(--color-sentinel-text-disabled)",
                      }}
                    >
                      {m.r2_score != null ? m.r2_score.toFixed(3) : "-"}
                    </td>
                    <td className="px-4 py-2 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {m.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* A/B Tests */}
      {abTests.length > 0 && (
        <div
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div
            className="p-4 flex items-center gap-2"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
          >
            <FlaskConical className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
            <h3 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              A/B Tests
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                  <th className="text-left px-4 py-2 font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>Test ID</th>
                  <th className="text-left px-4 py-2 font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>Model</th>
                  <th className="text-left px-4 py-2 font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>Control vs Candidate</th>
                  <th className="text-left px-4 py-2 font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>Status</th>
                  <th className="text-left px-4 py-2 font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>Split</th>
                </tr>
              </thead>
              <tbody>
                {abTests.map((t) => (
                  <tr key={t.test_id} style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                    <td className="px-4 py-2 font-mono text-xs" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {t.test_id.slice(0, 12)}...
                    </td>
                    <td className="px-4 py-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {t.model_type} / {t.equipment_type}
                    </td>
                    <td className="px-4 py-2 text-xs font-mono" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {t.control_model_id} vs {t.candidate_model_id}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className="px-2 py-0.5 rounded text-xs font-medium"
                        style={{
                          background: abTestStatusColor(t.status) + "20",
                          color: abTestStatusColor(t.status),
                        }}
                      >
                        {t.status}
                      </span>
                    </td>
                    <td className="px-4 py-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {Math.round((1 - t.traffic_split) * 100)}/{Math.round(t.traffic_split * 100)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Empty state when no A/B tests */}
      {abTests.length === 0 && !loading && (
        <div
          className="rounded-md p-5"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center gap-2 mb-2">
            <FlaskConical className="h-4 w-4" style={{ color: "var(--color-sentinel-text-disabled)" }} />
            <h3 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              A/B Tests
            </h3>
          </div>
          <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            No A/B tests currently running. Tests are created when candidate models are
            ready for comparison against the active production model.
          </p>
        </div>
      )}
    </div>
  );
}

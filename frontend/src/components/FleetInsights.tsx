/**
 * Fleet Insights Dashboard
 *
 * Fleet-wide analytics showing cross-site failure patterns,
 * risk distribution, benchmarking, and model performance.
 *
 * Phase 45-02: Fleet Learning and Cross-Site Insights.
 */

import { useEffect, useState } from "react";
import {
  BarChart3,
  AlertTriangle,
  TrendingUp,
  Building2,
  Cpu,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";
import {
  fleetApi,
  type FleetSummary,
  type FailurePattern,
  type RiskDistribution,
  type Benchmark,
  type GlobalModel,
  type FineTunedModel,
  type ImprovementSummary,
} from "../lib/fleetApi";
import { PageLoading } from "./PageLoading";

// --- Skeleton Loading ---
function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded ${className}`}
      style={{ background: "var(--color-sentinel-bg-secondary)" }}
    />
  );
}

// --- KPI Card ---
function KPICard({
  label,
  value,
  subtext,
  icon: Icon,
  color = "var(--color-sentinel-amber)",
}: {
  label: string;
  value: string | number;
  subtext?: string;
  icon: typeof BarChart3;
  color?: string;
}) {
  return (
    <div
      className="rounded-lg p-4"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      <div className="flex items-center justify-between mb-2">
        <span
          className="text-xs uppercase tracking-wide"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          {label}
        </span>
        <Icon className="h-4 w-4" style={{ color }} />
      </div>
      <div
        className="text-2xl font-bold"
        style={{ color: "var(--color-sentinel-text-primary)" }}
      >
        {value}
      </div>
      {subtext && (
        <div
          className="text-xs mt-1"
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        >
          {subtext}
        </div>
      )}
    </div>
  );
}

// --- Risk Bar ---
function RiskBar({
  distribution,
}: {
  distribution: RiskDistribution["distribution"];
}) {
  const levels = [
    { key: "critical", color: "var(--color-sentinel-red)", label: "Critical" },
    { key: "high", color: "#F59E0B", label: "High" },
    { key: "medium", color: "#3B82F6", label: "Medium" },
    { key: "low", color: "var(--color-sentinel-green)", label: "Low" },
  ] as const;

  return (
    <div>
      {/* Stacked bar */}
      <div className="flex h-6 rounded-md overflow-hidden mb-3">
        {levels.map(({ key, color }) => {
          const d = distribution[key];
          return d.percentage > 0 ? (
            <div
              key={key}
              style={{ width: `${d.percentage}%`, background: color }}
              title={`${key}: ${d.count} (${d.percentage}%)`}
            />
          ) : null;
        })}
      </div>
      {/* Legend */}
      <div className="flex flex-wrap gap-4">
        {levels.map(({ key, color, label }) => {
          const d = distribution[key];
          return (
            <div key={key} className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded-sm"
                style={{ background: color }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {label}: {d.count} ({d.percentage}%)
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// --- Failure Pattern Row ---
function PatternRow({ pattern }: { pattern: FailurePattern }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="border-b last:border-b-0"
      style={{ borderColor: "var(--color-sentinel-border)" }}
    >
      <button
        className="w-full flex items-center justify-between py-3 px-2 text-left hover:brightness-110 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3 flex-1">
          {expanded ? (
            <ChevronDown
              className="h-4 w-4 flex-shrink-0"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            />
          ) : (
            <ChevronRight
              className="h-4 w-4 flex-shrink-0"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            />
          )}
          <div>
            <span
              className="text-sm font-medium"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {pattern.equipment_type} - {pattern.failure_type.replace(/_/g, " ")}
            </span>
            <div className="flex gap-3 mt-0.5">
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                {pattern.occurrence_count} occurrences
              </span>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                {pattern.sites_affected} sites
              </span>
            </div>
          </div>
        </div>
        <span
          className="text-sm font-mono"
          style={{ color: "var(--color-sentinel-amber)" }}
        >
          R{pattern.avg_repair_cost_zar.toLocaleString()}
        </span>
      </button>

      {expanded && (
        <div
          className="px-9 pb-3 grid grid-cols-2 gap-3 text-xs"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          <div>
            <span className="font-medium">Avg age at failure:</span>{" "}
            {pattern.avg_age_at_failure_years} years
          </div>
          <div>
            <span className="font-medium">Avg health at detection:</span>{" "}
            {pattern.avg_health_at_detection}%
          </div>
          <div>
            <span className="font-medium">Avg downtime:</span>{" "}
            {pattern.avg_downtime_hours} hours
          </div>
          <div>
            <span className="font-medium">Sites affected:</span>{" "}
            {pattern.sites_affected}
          </div>
          <div className="col-span-2">
            <span className="font-medium">Common precursors:</span>{" "}
            {pattern.common_precursors.map((p) => p.replace(/_/g, " ")).join(", ")}
          </div>
        </div>
      )}
    </div>
  );
}

// --- Benchmark Row ---
function BenchmarkRow({ benchmark }: { benchmark: Benchmark }) {
  return (
    <div
      className="flex items-center justify-between py-3 border-b last:border-b-0"
      style={{ borderColor: "var(--color-sentinel-border)" }}
    >
      <div>
        <span
          className="text-sm font-medium"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          {benchmark.equipment_type}
        </span>
        <div className="flex gap-3 mt-0.5">
          <span
            className="text-xs"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            {benchmark.total_equipment_count} units
          </span>
          <span
            className="text-xs"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            {benchmark.total_sites} sites
          </span>
        </div>
      </div>
      <div className="text-right">
        <div className="flex items-center gap-2">
          <span
            className="text-sm font-mono"
            style={{
              color:
                benchmark.fleet_avg_health >= 75
                  ? "var(--color-sentinel-green)"
                  : benchmark.fleet_avg_health >= 50
                    ? "var(--color-sentinel-amber)"
                    : "var(--color-sentinel-red)",
            }}
          >
            {benchmark.fleet_avg_health}%
          </span>
          <span
            className="text-xs"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            health
          </span>
        </div>
        <span
          className="text-xs"
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        >
          MTBF: {benchmark.fleet_avg_mtbf_days}d | R
          {(benchmark.fleet_avg_maintenance_cost_zar / 1000).toFixed(0)}k/yr
        </span>
      </div>
    </div>
  );
}

// --- Model Card ---
function ModelCard({
  model,
  isFineTuned = false,
}: {
  model: GlobalModel | FineTunedModel;
  isFineTuned?: boolean;
}) {
  const ft = model as FineTunedModel;
  return (
    <div
      className="rounded-lg p-3"
      style={{
        background: "var(--color-sentinel-bg-secondary)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      <div className="flex items-center justify-between mb-2">
        <span
          className="text-sm font-medium"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          {model.model_type.toUpperCase()} / {model.equipment_type}
        </span>
        <span
          className="text-xs px-2 py-0.5 rounded"
          style={{
            background: isFineTuned
              ? "rgba(16, 185, 129, 0.15)"
              : "rgba(59, 130, 246, 0.15)",
            color: isFineTuned
              ? "var(--color-sentinel-green)"
              : "#3B82F6",
          }}
        >
          {isFineTuned ? "Fine-tuned" : "Global"}
        </span>
      </div>
      <div className="flex items-center gap-4 text-xs">
        <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
          R2: {model.metrics.r2_score.toFixed(3)}
        </span>
        <span style={{ color: "var(--color-sentinel-text-disabled)" }}>
          MAE: {model.metrics.mae.toFixed(3)}
        </span>
        {isFineTuned && ft.improvement && (
          <span className="flex items-center gap-1" style={{ color: "var(--color-sentinel-green)" }}>
            {ft.improvement.r2_pct > 0 ? (
              <ArrowUpRight className="h-3 w-3" />
            ) : (
              <ArrowDownRight className="h-3 w-3" />
            )}
            {ft.improvement.r2_pct > 0 ? "+" : ""}
            {ft.improvement.r2_pct}%
          </span>
        )}
      </div>
      {isFineTuned && (
        <div
          className="text-xs mt-1"
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        >
          Site: {ft.site_code} | {ft.samples_used.toLocaleString()} samples
        </div>
      )}
    </div>
  );
}

// ---------- Main Component ----------

export function FleetInsights() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [summary, setSummary] = useState<FleetSummary | null>(null);
  const [patterns, setPatterns] = useState<FailurePattern[]>([]);
  const [risk, setRisk] = useState<RiskDistribution | null>(null);
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>([]);
  const [globalModels, setGlobalModels] = useState<GlobalModel[]>([]);
  const [fineTunedModels, setFineTunedModels] = useState<FineTunedModel[]>([]);
  const [improvement, setImprovement] = useState<ImprovementSummary | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      // Stagger requests with 600ms delays to prevent rate limiting (100 req/min limit)
      const sumRes = await fleetApi.getSummary();
      setSummary(sumRes);

      await new Promise(resolve => setTimeout(resolve, 600));
      const patRes = await fleetApi.getFailurePatterns();
      setPatterns(patRes.patterns);

      await new Promise(resolve => setTimeout(resolve, 600));
      const riskRes = await fleetApi.getRiskDistribution();
      setRisk(riskRes);

      await new Promise(resolve => setTimeout(resolve, 600));
      const benchRes = await fleetApi.getBenchmarks();
      setBenchmarks(benchRes.benchmarks);

      await new Promise(resolve => setTimeout(resolve, 600));
      const gmRes = await fleetApi.getGlobalModels();
      setGlobalModels(gmRes.models);

      await new Promise(resolve => setTimeout(resolve, 600));
      const ftRes = await fleetApi.getFineTunedModels();
      setFineTunedModels(ftRes.models);

      await new Promise(resolve => setTimeout(resolve, 600));
      const impRes = await fleetApi.getImprovementSummary();
      setImprovement(impRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load fleet data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading && !summary) {
    return <PageLoading message="Loading fleet analytics..." />;
  }

  if (error) {
    return (
      <div className="h-full overflow-y-auto p-4 md:p-6">
        <div
          className="rounded-lg p-6 text-center"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid rgba(220, 38, 38, 0.3)",
          }}
        >
          <AlertTriangle
            className="h-8 w-8 mx-auto mb-2"
            style={{ color: "var(--color-sentinel-red)" }}
          />
          <p style={{ color: "var(--color-sentinel-text-primary)" }}>{error}</p>
          <button
            onClick={fetchData}
            className="mt-3 px-4 py-2 rounded text-sm"
            style={{
              background: "var(--color-sentinel-amber)",
              color: "#000",
            }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2
            className="text-lg font-semibold"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Fleet-Wide Analytics
          </h2>
          <p
            className="text-sm"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Cross-site insights from {summary?.fleet_overview.total_sites || "-"}{" "}
            buildings and {summary?.fleet_overview.total_equipment || "-"} equipment
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded text-sm transition-colors hover:brightness-110"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
            color: "var(--color-sentinel-text-secondary)",
          }}
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* KPI Cards */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : summary ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard
            label="Fleet Health"
            value={`${summary.fleet_overview.avg_fleet_health}%`}
            subtext={`${summary.fleet_overview.total_sites} sites monitored`}
            icon={BarChart3}
            color={
              summary.fleet_overview.avg_fleet_health >= 75
                ? "var(--color-sentinel-green)"
                : "var(--color-sentinel-amber)"
            }
          />
          <KPICard
            label="Total Equipment"
            value={summary.fleet_overview.total_equipment}
            subtext={`${summary.fleet_overview.failure_patterns_tracked} patterns tracked`}
            icon={Cpu}
          />
          <KPICard
            label="Open Alerts"
            value={summary.fleet_overview.total_open_alerts}
            subtext="Across fleet"
            icon={AlertTriangle}
            color="var(--color-sentinel-red)"
          />
          <KPICard
            label="Monthly Maintenance"
            value={`R${(summary.fleet_overview.monthly_maintenance_zar / 1000).toFixed(0)}k`}
            subtext={`${summary.fleet_overview.total_recorded_failures} total failures recorded`}
            icon={Building2}
          />
        </div>
      ) : null}

      {/* Risk Distribution + Failure Patterns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Risk Distribution */}
        <div
          className="rounded-lg p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <h3
            className="text-sm font-semibold mb-4"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Fleet Risk Distribution
          </h3>
          {loading ? (
            <Skeleton className="h-32" />
          ) : risk ? (
            <RiskBar distribution={risk.distribution} />
          ) : null}
          {risk && (
            <div
              className="mt-3 text-xs"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              {risk.sites_with_critical} of {risk.total_sites} sites have
              critical equipment
            </div>
          )}
        </div>

        {/* Common Failure Patterns */}
        <div
          className="rounded-lg p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <h3
            className="text-sm font-semibold mb-4"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Common Failure Patterns
          </h3>
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : (
            <div className="max-h-72 overflow-y-auto">
              {patterns.map((p, i) => (
                <PatternRow key={i} pattern={p} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Benchmarking + Site Comparison */}
      <div
        className="rounded-lg p-4"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <h3
          className="text-sm font-semibold mb-4"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          Equipment Benchmarking
        </h3>
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        ) : (
          <div>
            {benchmarks.map((b, i) => (
              <BenchmarkRow key={i} benchmark={b} />
            ))}
          </div>
        )}
      </div>

      {/* Global Models + Fine-Tuned Models */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Global Models */}
        <div
          className="rounded-lg p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center justify-between mb-4">
            <h3
              className="text-sm font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Global Fleet Models
            </h3>
            <span
              className="text-xs px-2 py-0.5 rounded"
              style={{
                background: "rgba(59, 130, 246, 0.15)",
                color: "#3B82F6",
              }}
            >
              {globalModels.length} models
            </span>
          </div>
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-20" />
              ))}
            </div>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {globalModels.map((m) => (
                <ModelCard key={m.model_id} model={m} />
              ))}
            </div>
          )}
        </div>

        {/* Fine-Tuned Models */}
        <div
          className="rounded-lg p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center justify-between mb-4">
            <h3
              className="text-sm font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Site Fine-Tuned Models
            </h3>
            {improvement && (
              <span
                className="text-xs flex items-center gap-1"
                style={{ color: "var(--color-sentinel-green)" }}
              >
                <TrendingUp className="h-3 w-3" />
                Avg +{improvement.avg_improvement_pct}% vs global
              </span>
            )}
          </div>
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-20" />
              ))}
            </div>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {fineTunedModels.map((m) => (
                <ModelCard
                  key={m.model_id}
                  model={m}
                  isFineTuned
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default FleetInsights;

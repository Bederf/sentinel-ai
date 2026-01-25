/**
 * PredictionDetail Component - Grafana-styled prediction details modal
 *
 * Features:
 * - Complete prediction evidence
 * - Contributing factors with weights
 * - Similar historical failures
 * - Technician notes
 * - Financial impact analysis
 * - Recommended actions
 */

import { useState } from "react";
import { Dialog, DialogPanel } from "@tremor/react";
import {
  X,
  AlertTriangle,
  TrendingUp,
  Wrench,
  Clock,
  FileText,
  Activity,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { CostCard } from "./CostCard";
import { CostBreakdownDetail } from "./CostBreakdownDetail";

interface PredictionDetailProps {
  prediction: {
    id: string;
    equipment_name: string;
    site_name: string;
    equipment_type: string;
    prediction_type: string;
    probability_percent: number;
    confidence: "high" | "medium" | "low";
    predicted_failure_date: string;
    timeframe_days: number;
    severity: "critical" | "high" | "medium" | "low";
    evidence: {
      repeat_work_orders: number;
      repeat_period_months: number;
      alarm_frequency: Record<string, number>;
      asset_age_years: number;
      expected_life_years: number;
      technician_notes: string[];
      latest_reading: {
        parameter: string;
        value: number;
        baseline: number;
        threshold: number;
        trend: string;
      };
    };
    contributing_factors: Array<{
      factor: string;
      weight: number;
      description: string;
    }>;
    similar_failures: Array<{
      site: string;
      equipment: string;
      failure_date: string;
      common_factors: string[];
    }>;
    financial_impact: {
      repair_cost_zar: number;
      replacement_cost_zar: number;
      downtime_cost_per_hour_zar: number;
      estimated_repair_hours: number;
      potential_loss_zar: number;
    };
    costImpact?: {
      estimatedFailureCost: number;
      estimatedPreventiveCost: number;
      potentialSavings: number;
      failureBreakdown: {
        parts: number;
        labor: number;
        downtime: number;
        secondaryDamage: number;
      };
      preventiveBreakdown: {
        parts: number;
        labor: number;
        downtime: number;
      };
      story?: string;
    };
    recommended_action: string;
    parts_required: string[];
    urgency: string;
  };
  isOpen: boolean;
  onClose: () => void;
}

// Severity color configuration
function getSeverityConfig(severity: string) {
  switch (severity) {
    case "critical":
      return { color: "var(--color-status-error)", bg: "rgba(242, 73, 92, 0.15)" };
    case "high":
      return { color: "var(--color-status-warning)", bg: "rgba(255, 152, 48, 0.15)" };
    case "medium":
      return { color: "var(--color-grafana-yellow)", bg: "rgba(242, 204, 12, 0.15)" };
    case "low":
      return { color: "var(--color-grafana-blue)", bg: "rgba(50, 116, 217, 0.15)" };
    default:
      return { color: "var(--color-grafana-text-secondary)", bg: "rgba(142, 142, 142, 0.15)" };
  }
}

function getConfidenceConfig(confidence: string) {
  switch (confidence) {
    case "high":
      return { color: "var(--color-status-success)", label: "HIGH CONFIDENCE" };
    case "medium":
      return { color: "var(--color-grafana-yellow)", label: "MEDIUM CONFIDENCE" };
    case "low":
      return { color: "var(--color-grafana-text-secondary)", label: "LOW CONFIDENCE" };
    default:
      return { color: "var(--color-grafana-text-secondary)", label: "UNKNOWN" };
  }
}

export function PredictionDetail({ prediction, isOpen, onClose }: PredictionDetailProps) {
  const [showCostBreakdown, setShowCostBreakdown] = useState(false);

  if (!isOpen) return null;

  const severityConfig = getSeverityConfig(prediction.severity);
  const confidenceConfig = getConfidenceConfig(prediction.confidence);

  // Format currency
  const formatZAR = (amount: number) =>
    new Intl.NumberFormat("en-ZA", {
      style: "currency",
      currency: "ZAR",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);

  // Calculate trend percentage
  const trendPercent = Math.round(
    ((prediction.evidence.latest_reading.value - prediction.evidence.latest_reading.baseline) /
      prediction.evidence.latest_reading.baseline) *
      100
  );

  return (
    <Dialog open={isOpen} onClose={onClose} className="z-50">
      <DialogPanel
        className="w-full h-full md:w-2/3 md:h-auto md:max-w-5xl md:max-h-[90vh] md:overflow-y-auto md:rounded"
        style={{
          background: "var(--color-grafana-bg-canvas)",
          border: "1px solid var(--color-grafana-border)",
        }}
      >
        {/* Header */}
        <div
          className="sticky top-0 z-10 p-4 flex items-start justify-between"
          style={{
            background: "var(--color-grafana-bg-primary)",
            borderBottom: "1px solid var(--color-grafana-border)",
          }}
        >
          <div>
            <h2
              className="text-xl font-bold mb-2"
              style={{ color: "var(--color-grafana-text-primary)" }}
            >
              Failure Prediction Details
            </h2>
            <div className="flex flex-wrap gap-2">
              <span
                className="text-xs font-medium px-2 py-0.5 rounded"
                style={{
                  background: severityConfig.bg,
                  color: severityConfig.color,
                }}
              >
                {prediction.severity.toUpperCase()}
              </span>
              <span
                className="text-xs font-medium px-2 py-0.5 rounded"
                style={{
                  background: `${confidenceConfig.color}20`,
                  color: confidenceConfig.color,
                }}
              >
                {confidenceConfig.label}
              </span>
              <span
                className="text-xs font-medium px-2 py-0.5 rounded"
                style={{
                  background: "var(--color-grafana-bg-secondary)",
                  color: "var(--color-grafana-text-secondary)",
                }}
              >
                {prediction.equipment_type.toUpperCase()}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded transition-colors"
            style={{ background: "var(--color-grafana-bg-secondary)" }}
          >
            <X className="h-5 w-5" style={{ color: "var(--color-grafana-text-secondary)" }} />
          </button>
        </div>

        <div className="p-4 space-y-6">
          {/* Key Metrics Row */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <MetricCard
              value={`${prediction.probability_percent}%`}
              label="Failure Probability"
              color={severityConfig.color}
            />
            <MetricCard
              value={prediction.timeframe_days.toString()}
              label="Days Until Failure"
              color="var(--color-grafana-orange)"
            />
            <MetricCard
              value={`${prediction.evidence.asset_age_years} yrs`}
              label="Asset Age"
              color="var(--color-grafana-cyan)"
            />
          </div>

          {/* Equipment Info Card */}
          <div
            className="rounded p-4"
            style={{
              background: "var(--color-grafana-bg-panel)",
              border: "1px solid var(--color-grafana-border)",
            }}
          >
            <h3
              className="text-lg font-semibold mb-2"
              style={{ color: "var(--color-grafana-text-primary)" }}
            >
              {prediction.equipment_name}
            </h3>
            <div className="flex items-center gap-2 text-sm mb-4">
              <Activity className="h-4 w-4" style={{ color: "var(--color-grafana-text-disabled)" }} />
              <span style={{ color: "var(--color-grafana-text-secondary)" }}>
                {prediction.site_name} • {prediction.equipment_type}
              </span>
            </div>

            {/* Prediction Alert */}
            <div
              className="p-3 rounded flex items-start gap-3"
              style={{
                background: severityConfig.bg,
                border: `1px solid ${severityConfig.color}30`,
              }}
            >
              <AlertTriangle className="h-5 w-5 mt-0.5" style={{ color: severityConfig.color }} />
              <div>
                <span className="font-medium text-sm" style={{ color: severityConfig.color }}>
                  {formatPredictionType(prediction.prediction_type)}
                </span>
                <p className="text-sm mt-1" style={{ color: "var(--color-grafana-text-secondary)" }}>
                  Predicted failure:{" "}
                  {new Date(prediction.predicted_failure_date).toLocaleDateString("en-ZA", {
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                  })}
                </p>
              </div>
            </div>

            <div className="flex gap-3 mt-4">
              <span
                className="text-xs px-2 py-1 rounded flex items-center gap-1"
                style={{
                  background: "rgba(255, 152, 48, 0.15)",
                  color: "var(--color-status-warning)",
                }}
              >
                <Wrench className="h-3 w-3" />
                {prediction.evidence.repeat_work_orders} work orders in {prediction.evidence.repeat_period_months} months
              </span>
              <span
                className="text-xs px-2 py-1 rounded flex items-center gap-1"
                style={{
                  background: "rgba(50, 116, 217, 0.15)",
                  color: "var(--color-grafana-blue)",
                }}
              >
                <Clock className="h-3 w-3" />
                Expected life: {prediction.evidence.expected_life_years} years
              </span>
            </div>
          </div>

          {/* Contributing Factors */}
          <SectionCard title="Contributing Factors">
            <div className="space-y-4">
              {prediction.contributing_factors.map((factor, index) => (
                <div key={index}>
                  <div className="flex justify-between mb-1">
                    <span
                      className="text-sm font-medium"
                      style={{ color: "var(--color-grafana-text-primary)" }}
                    >
                      {factor.factor}
                    </span>
                    <span
                      className="text-sm"
                      style={{ color: "var(--color-grafana-text-secondary)" }}
                    >
                      {Math.round(factor.weight * 100)}%
                    </span>
                  </div>
                  <div
                    className="h-2 rounded-full overflow-hidden"
                    style={{ background: "var(--color-grafana-border)" }}
                  >
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${factor.weight * 100}%`,
                        background: severityConfig.color,
                      }}
                    />
                  </div>
                  <p
                    className="text-xs mt-1"
                    style={{ color: "var(--color-grafana-text-secondary)" }}
                  >
                    {factor.description}
                  </p>
                </div>
              ))}
            </div>
          </SectionCard>

          {/* Cost Impact Analysis */}
          {prediction.costImpact && (
            <SectionCard title="Cost Impact Analysis">
              {!showCostBreakdown ? (
                <div>
                  <CostCard costImpact={prediction.costImpact} />
                  <button
                    onClick={() => setShowCostBreakdown(true)}
                    className="mt-3 text-sm flex items-center gap-1"
                    style={{ color: "var(--color-grafana-text-link)" }}
                  >
                    <ChevronDown className="h-4 w-4" />
                    View detailed breakdown
                  </button>
                </div>
              ) : (
                <div>
                  <CostBreakdownDetail costImpact={prediction.costImpact} />
                  <button
                    onClick={() => setShowCostBreakdown(false)}
                    className="mt-3 text-sm flex items-center gap-1"
                    style={{ color: "var(--color-grafana-text-link)" }}
                  >
                    <ChevronUp className="h-4 w-4" />
                    Hide breakdown
                  </button>
                </div>
              )}
            </SectionCard>
          )}

          {/* Evidence Details Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Latest Reading */}
            <SectionCard title="Latest Reading">
              <div className="flex justify-between items-start mb-3">
                <span style={{ color: "var(--color-grafana-text-secondary)" }}>
                  {prediction.evidence.latest_reading.parameter.replace(/_/g, " ")}
                </span>
                <span
                  className="text-xs px-2 py-0.5 rounded flex items-center gap-1"
                  style={{
                    background:
                      prediction.evidence.latest_reading.trend === "increasing"
                        ? "rgba(242, 73, 92, 0.15)"
                        : "rgba(50, 116, 217, 0.15)",
                    color:
                      prediction.evidence.latest_reading.trend === "increasing"
                        ? "var(--color-status-error)"
                        : "var(--color-grafana-blue)",
                  }}
                >
                  {prediction.evidence.latest_reading.trend === "increasing" ? (
                    <TrendingUp className="h-3 w-3" />
                  ) : (
                    <Activity className="h-3 w-3" />
                  )}
                  {prediction.evidence.latest_reading.trend}
                </span>
              </div>
              <div
                className="text-3xl font-bold mb-2"
                style={{ color: "var(--color-grafana-text-primary)" }}
              >
                {prediction.evidence.latest_reading.value}
                <span
                  className="text-sm ml-2"
                  style={{ color: "var(--color-grafana-text-disabled)" }}
                >
                  (baseline: {prediction.evidence.latest_reading.baseline})
                </span>
              </div>
              <div className="flex gap-4">
                <div>
                  <span
                    className="text-xs"
                    style={{ color: "var(--color-grafana-text-disabled)" }}
                  >
                    Change
                  </span>
                  <div
                    className="text-sm font-semibold"
                    style={{
                      color: trendPercent > 0 ? "var(--color-status-error)" : "var(--color-status-success)",
                    }}
                  >
                    {trendPercent > 0 ? "+" : ""}
                    {trendPercent}%
                  </div>
                </div>
                <div>
                  <span
                    className="text-xs"
                    style={{ color: "var(--color-grafana-text-disabled)" }}
                  >
                    Threshold
                  </span>
                  <div
                    className="text-sm font-semibold"
                    style={{ color: "var(--color-grafana-text-primary)" }}
                  >
                    {prediction.evidence.latest_reading.threshold}
                  </div>
                </div>
              </div>
            </SectionCard>

            {/* Alarm Frequency */}
            <SectionCard title="Alarm Frequency (30 days)">
              <div className="space-y-2">
                {Object.entries(prediction.evidence.alarm_frequency).map(([alarm, count]) => (
                  <div key={alarm} className="flex justify-between items-center">
                    <span
                      className="text-sm"
                      style={{ color: "var(--color-grafana-text-secondary)" }}
                    >
                      {alarm.replace(/_/g, " ")}
                    </span>
                    <span
                      className="text-xs font-medium px-2 py-0.5 rounded"
                      style={{
                        background: "rgba(242, 73, 92, 0.15)",
                        color: "var(--color-status-error)",
                      }}
                    >
                      {count}
                    </span>
                  </div>
                ))}
              </div>
            </SectionCard>
          </div>

          {/* Technician Notes */}
          <SectionCard title="Technician Notes">
            <div className="space-y-3">
              {prediction.evidence.technician_notes.map((note, index) => (
                <div key={index} className="flex gap-3">
                  <FileText
                    className="h-4 w-4 mt-0.5 flex-shrink-0"
                    style={{ color: "var(--color-grafana-text-disabled)" }}
                  />
                  <div>
                    <span
                      className="text-xs"
                      style={{ color: "var(--color-grafana-text-disabled)" }}
                    >
                      {note.split(":")[0]}
                    </span>
                    <p
                      className="text-sm"
                      style={{ color: "var(--color-grafana-text-primary)" }}
                    >
                      {note.split(":").slice(1).join(":")}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          {/* Similar Failures */}
          {prediction.similar_failures.length > 0 && (
            <SectionCard title="Similar Historical Failures">
              <div className="space-y-3">
                {prediction.similar_failures.map((failure, index) => (
                  <div
                    key={index}
                    className="p-3 rounded"
                    style={{
                      background: "var(--color-grafana-bg-secondary)",
                      border: "1px solid var(--color-grafana-border)",
                    }}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <span
                        className="font-medium text-sm"
                        style={{ color: "var(--color-grafana-text-primary)" }}
                      >
                        {failure.site} - {failure.equipment}
                      </span>
                      <XCircle className="h-4 w-4" style={{ color: "var(--color-status-error)" }} />
                    </div>
                    <p
                      className="text-xs mb-2"
                      style={{ color: "var(--color-grafana-text-secondary)" }}
                    >
                      Failed:{" "}
                      {new Date(failure.failure_date).toLocaleDateString("en-ZA", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      })}
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {failure.common_factors.map((factor, i) => (
                        <span
                          key={i}
                          className="text-xs px-1.5 py-0.5 rounded"
                          style={{
                            background: "var(--color-grafana-bg-panel)",
                            color: "var(--color-grafana-text-secondary)",
                          }}
                        >
                          {factor}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          {/* Financial Impact */}
          <SectionCard title="Financial Impact Analysis">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <div
                  className="text-xl font-bold"
                  style={{ color: "var(--color-grafana-text-primary)" }}
                >
                  {formatZAR(prediction.financial_impact.repair_cost_zar)}
                </div>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-grafana-text-secondary)" }}
                >
                  Repair Cost
                </span>
              </div>
              <div>
                <div
                  className="text-xl font-bold"
                  style={{ color: "var(--color-status-error)" }}
                >
                  {formatZAR(prediction.financial_impact.potential_loss_zar)}
                </div>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-grafana-text-secondary)" }}
                >
                  Potential Loss
                </span>
              </div>
              <div>
                <div
                  className="text-xl font-bold"
                  style={{ color: "var(--color-status-success)" }}
                >
                  {formatZAR(
                    prediction.financial_impact.potential_loss_zar -
                      prediction.financial_impact.repair_cost_zar
                  )}
                </div>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-grafana-text-secondary)" }}
                >
                  Potential Savings
                </span>
              </div>
              <div>
                <div
                  className="text-xl font-bold"
                  style={{ color: "var(--color-grafana-orange)" }}
                >
                  {prediction.financial_impact.estimated_repair_hours}h
                </div>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-grafana-text-secondary)" }}
                >
                  Est. Downtime
                </span>
              </div>
            </div>
          </SectionCard>

          {/* Recommended Action */}
          <div
            className="p-4 rounded"
            style={{
              background: severityConfig.bg,
              border: `1px solid ${severityConfig.color}30`,
            }}
          >
            <div className="flex items-start gap-3">
              <CheckCircle2 className="h-5 w-5 mt-0.5" style={{ color: severityConfig.color }} />
              <div>
                <span className="text-sm font-semibold" style={{ color: severityConfig.color }}>
                  {prediction.urgency.toUpperCase()}
                </span>
                <p
                  className="text-sm mt-1"
                  style={{ color: "var(--color-grafana-text-primary)" }}
                >
                  {prediction.recommended_action}
                </p>
              </div>
            </div>
          </div>

          {/* Parts Required */}
          <SectionCard title="Parts Required">
            <div className="space-y-2">
              {prediction.parts_required.map((part, index) => (
                <div key={index} className="flex items-center gap-2">
                  <Wrench
                    className="h-4 w-4"
                    style={{ color: "var(--color-grafana-text-disabled)" }}
                  />
                  <span style={{ color: "var(--color-grafana-text-primary)" }}>{part}</span>
                </div>
              ))}
            </div>
          </SectionCard>

          {/* Footer Actions */}
          <div className="flex justify-end gap-3 pt-4">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded text-sm font-medium transition-colors"
              style={{
                background: "var(--color-grafana-bg-secondary)",
                color: "var(--color-grafana-text-primary)",
                border: "1px solid var(--color-grafana-border)",
              }}
            >
              Close
            </button>
            <button
              className="px-4 py-2 rounded text-sm font-medium flex items-center gap-2 transition-colors"
              style={{
                background: severityConfig.color,
                color: "white",
              }}
            >
              <Wrench className="h-4 w-4" />
              Schedule Maintenance
            </button>
          </div>
        </div>
      </DialogPanel>
    </Dialog>
  );
}

// Helper Components
function MetricCard({ value, label, color }: { value: string; label: string; color: string }) {
  return (
    <div
      className="rounded p-4 text-center"
      style={{
        background: "var(--color-grafana-bg-panel)",
        border: "1px solid var(--color-grafana-border)",
      }}
    >
      <div className="text-3xl font-bold mb-1" style={{ color }}>
        {value}
      </div>
      <span className="text-xs" style={{ color: "var(--color-grafana-text-secondary)" }}>
        {label}
      </span>
    </div>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="rounded overflow-hidden"
      style={{
        background: "var(--color-grafana-bg-panel)",
        border: "1px solid var(--color-grafana-border)",
      }}
    >
      <div
        className="px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-grafana-border)" }}
      >
        <h3 className="font-semibold text-sm" style={{ color: "var(--color-grafana-text-primary)" }}>
          {title}
        </h3>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function formatPredictionType(type: string): string {
  return type
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export default PredictionDetail;

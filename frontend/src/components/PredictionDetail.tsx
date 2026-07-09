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

import { useEffect, useState } from "react";

import {
  X,
  AlertTriangle,
  TrendingUp,
  Wrench,
  Clock,
  Activity,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Link2,
} from "lucide-react";
import { authorizedFetch } from "@/lib/api";
import { CostCard } from "./CostCard";
import { CostBreakdownDetail } from "./CostBreakdownDetail";
import { PatternTimeline } from "./PatternTimeline";
import { HighlightedNotes } from "./HighlightedNotes";
import { MaintenanceHistoryTabs } from "./maintenance/MaintenanceHistoryTabs";

interface PredictionDetailProps {
  prediction: {
    id: string;
    equipment_id?: string;
    equipment_code?: string;
    equipment_name: string;
    site_name: string;
    site_id?: string;
    equipment_type: string;
    prediction_type: string;
    probability_percent: number;
    confidence: "high" | "medium" | "low";
    predicted_failure_date: string;
    timeframe_days: number;
    severity: "critical" | "warning" | "healthy";
    evidence: {
      repeat_work_orders?: number;
      repeat_period_months?: number;
      alarm_frequency?: Record<string, number>;
      asset_age_years?: number;
      age_years?: number; // Alternate field name from API
      expected_life_years?: number;
      technician_notes?: string[];
      health_score?: number;
      health_trend?: string;
      anomaly_score?: number;
      observation?: string;
      // Support both latest_reading (legacy) and last_reading (auto-generated)
      latest_reading?: {
        parameter: string;
        value: number;
        baseline: number;
        threshold: number;
        trend: string;
      };
      last_reading?: {
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
    cost_impact?: {
      preventive_breakdown: {
        labor_cost_zar: number;
        parts_cost_zar: number;
        downtime_hours: number;
        total_zar: number;
      };
      failure_breakdown: {
        emergency_repair_zar: number;
        downtime_loss_zar: number;
        downtime_hours: number;
        total_zar: number;
      };
      potential_savings_zar: number;
      savings_percent: number;
      roi_message: string;
    };
    recommended_action: string;
    parts_required: Array<{
      part_number: string;
      name: string;
      quantity: number;
      cost_zar: number;
      lead_time_days: number;
    }> | string[];
    urgency: string;
  };
  isOpen: boolean;
  onClose: () => void;
  onCreateWorkOrder?: (equipmentId: string, equipmentName: string) => void;
}

// Severity color configuration
function getSeverityConfig(severity: string) {
  switch (severity) {
    case "critical":
      return { color: "var(--color-status-error)", bg: "rgba(242, 73, 92, 0.15)" };
    case "high":
      return { color: "var(--color-status-warning)", bg: "rgba(255, 152, 48, 0.15)" };
    case "medium":
      return { color: "var(--color-sentinel-amber)", bg: "rgba(242, 204, 12, 0.15)" };
    case "low":
      return { color: "var(--color-sentinel-blue)", bg: "rgba(50, 116, 217, 0.15)" };
    default:
      return { color: "var(--color-sentinel-text-secondary)", bg: "rgba(142, 142, 142, 0.15)" };
  }
}

function getConfidenceConfig(confidence: string) {
  switch (confidence) {
    case "high":
      return { color: "var(--color-status-success)", label: "HIGH CONFIDENCE" };
    case "medium":
      return { color: "var(--color-sentinel-amber)", label: "MEDIUM CONFIDENCE" };
    case "low":
      return { color: "var(--color-sentinel-text-secondary)", label: "LOW CONFIDENCE" };
    default:
      return { color: "var(--color-sentinel-text-secondary)", label: "UNKNOWN" };
  }
}

export function PredictionDetail({ prediction, isOpen, onClose, onCreateWorkOrder }: PredictionDetailProps) {
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

  // Get reading data (support both latest_reading and last_reading)
  const reading = prediction.evidence?.latest_reading || prediction.evidence?.last_reading;

  // Calculate trend percentage
  const trendPercent = reading?.baseline
    ? Math.round(((reading.value - reading.baseline) / reading.baseline) * 100)
    : 0;

  return (
    <>{isOpen && <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div
        className="relative z-10 w-full h-full md:w-2/3 md:h-auto md:max-w-5xl md:max-h-[90vh] md:overflow-y-auto md:rounded"
        style={{
          background: "var(--color-sentinel-bg-canvas)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        {/* Header */}
        <div
          className="sticky top-0 z-10 p-4 flex items-start justify-between"
          style={{
            background: "var(--color-sentinel-bg-primary)",
            borderBottom: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div>
            <h2
              className="text-xl font-bold mb-2"
              style={{ color: "var(--color-sentinel-text-primary)" }}
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
                {(prediction.severity || "unknown").toUpperCase()}
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
                  background: "var(--color-sentinel-bg-secondary)",
                  color: "var(--color-sentinel-text-secondary)",
                }}
              >
                {(prediction.equipment_type || "equipment").toUpperCase()}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded transition-colors"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <X className="h-5 w-5" style={{ color: "var(--color-sentinel-text-secondary)" }} />
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
              color="var(--color-sentinel-amber)"
            />
            <MetricCard
              value={(prediction.evidence?.asset_age_years ?? prediction.evidence?.age_years) ? `${prediction.evidence?.asset_age_years ?? prediction.evidence?.age_years} yrs` : (prediction.evidence?.health_score ? `${prediction.evidence.health_score}%` : "N/A")}
              label={(prediction.evidence?.asset_age_years ?? prediction.evidence?.age_years) ? "Asset Age" : "Health Score"}
              color="var(--sentinel-cyan)"
            />
          </div>

          {/* Equipment Info Card */}
          <div
            className="rounded p-4"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <h3
              className="text-lg font-semibold mb-2"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {prediction.equipment_name}
            </h3>
            <div className="flex items-center gap-2 text-sm mb-4">
              <Activity className="h-4 w-4" style={{ color: "var(--color-sentinel-text-disabled)" }} />
              <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
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
                <p className="text-sm mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Predicted failure:{" "}
                  {new Date(prediction.predicted_failure_date).toLocaleDateString("en-ZA", {
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                  })}
                </p>
              </div>
            </div>

            <div className="flex gap-3 mt-4 flex-wrap">
              {prediction.evidence?.repeat_work_orders !== undefined && (
                <span
                  className="text-xs px-2 py-1 rounded flex items-center gap-1"
                  style={{
                    background: "rgba(255, 152, 48, 0.15)",
                    color: "var(--color-status-warning)",
                  }}
                >
                  <Wrench className="h-3 w-3" />
                  {prediction.evidence.repeat_work_orders} work orders in {prediction.evidence.repeat_period_months || 12} months
                </span>
              )}
              {prediction.evidence?.anomaly_score !== undefined && (
                <span
                  className="text-xs px-2 py-1 rounded flex items-center gap-1"
                  style={{
                    background: prediction.evidence.anomaly_score > 0.5 ? "rgba(220, 38, 38, 0.15)" : prediction.evidence.anomaly_score > 0.3 ? "rgba(255, 152, 48, 0.15)" : "rgba(50, 116, 217, 0.15)",
                    color: prediction.evidence.anomaly_score > 0.5 ? "var(--color-sentinel-red)" : prediction.evidence.anomaly_score > 0.3 ? "var(--color-status-warning)" : "var(--color-sentinel-blue)",
                  }}
                >
                  <Activity className="h-3 w-3" />
                  Anomaly score: {Math.round(prediction.evidence.anomaly_score * 100)}%
                </span>
              )}
              {prediction.evidence?.health_trend && (
                <span
                  className="text-xs px-2 py-1 rounded flex items-center gap-1"
                  style={{
                    background: prediction.evidence.health_trend === "declining" ? "rgba(220, 38, 38, 0.15)" : "rgba(50, 116, 217, 0.15)",
                    color: prediction.evidence.health_trend === "declining" ? "var(--color-sentinel-red)" : "var(--color-sentinel-blue)",
                  }}
                >
                  <TrendingUp className="h-3 w-3" />
                  Health trend: {prediction.evidence.health_trend}
                </span>
              )}
              {prediction.evidence?.expected_life_years !== undefined && (
                <span
                  className="text-xs px-2 py-1 rounded flex items-center gap-1"
                  style={{
                    background: "rgba(50, 116, 217, 0.15)",
                    color: "var(--color-sentinel-blue)",
                  }}
                >
                  <Clock className="h-3 w-3" />
                  Expected life: {prediction.evidence.expected_life_years} years
                </span>
              )}
            </div>

            {/* Observation note if available */}
            {prediction.evidence?.observation && (
              <div
                className="mt-3 p-3 rounded text-sm"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-secondary)",
                }}
              >
                <span className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>Observation: </span>
                {prediction.evidence.observation}
              </div>
            )}
          </div>

          {/* Contributing Factors */}
          <SectionCard title="Contributing Factors">
            <div className="space-y-4">
              {(prediction.contributing_factors || []).map((factor, index) => (
                <div key={index}>
                  <div className="flex justify-between mb-1">
                    <span
                      className="text-sm font-medium"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {factor.factor}
                    </span>
                    <span
                      className="text-sm"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      {Math.round(factor.weight * 100)}%
                    </span>
                  </div>
                  <div
                    className="h-2 rounded-full overflow-hidden"
                    style={{ background: "var(--color-sentinel-border)" }}
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
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    {factor.description}
                  </p>
                </div>
              ))}
            </div>
          </SectionCard>

          {/* Cost Impact Analysis */}
          {(prediction.costImpact || prediction.cost_impact) && (
            <SectionCard title="Cost Impact Analysis">
              {prediction.costImpact ? (
                // Original costImpact format
                !showCostBreakdown ? (
                  <div>
                    <CostCard costImpact={prediction.costImpact} />
                    <button
                      onClick={() => setShowCostBreakdown(true)}
                      className="mt-3 text-sm flex items-center gap-1"
                      style={{ color: "var(--color-sentinel-text-link)" }}
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
                      style={{ color: "var(--color-sentinel-text-link)" }}
                    >
                      <ChevronUp className="h-4 w-4" />
                      Hide breakdown
                    </button>
                  </div>
                )
              ) : prediction.cost_impact ? (
                // New cost_impact format from backend
                <div className="space-y-4">
                  {/* Summary message */}
                  <div
                    className="p-3 rounded"
                    style={{
                      background: "rgba(115, 191, 105, 0.15)",
                      border: "1px solid rgba(115, 191, 105, 0.3)",
                    }}
                  >
                    <span
                      className="text-sm font-medium"
                      style={{ color: "var(--color-status-success)" }}
                    >
                      {prediction.cost_impact.roi_message}
                    </span>
                  </div>

                  {/* Comparison grid */}
                  <div className="grid grid-cols-2 gap-4">
                    {/* Preventive */}
                    <div
                      className="p-3 rounded"
                      style={{
                        background: "var(--color-sentinel-bg-secondary)",
                        border: "1px solid var(--color-sentinel-border)",
                      }}
                    >
                      <div className="text-xs mb-2" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                        Preventive Maintenance
                      </div>
                      <div className="text-xl font-bold" style={{ color: "var(--color-status-success)" }}>
                        {formatZAR(prediction.cost_impact.preventive_breakdown.total_zar)}
                      </div>
                      <div className="text-xs mt-2 space-y-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        <div className="flex justify-between">
                          <span>Labor:</span>
                          <span>{formatZAR(prediction.cost_impact.preventive_breakdown.labor_cost_zar)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Parts:</span>
                          <span>{formatZAR(prediction.cost_impact.preventive_breakdown.parts_cost_zar)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Downtime:</span>
                          <span>{prediction.cost_impact.preventive_breakdown.downtime_hours}h</span>
                        </div>
                      </div>
                    </div>

                    {/* Failure */}
                    <div
                      className="p-3 rounded"
                      style={{
                        background: "var(--color-sentinel-bg-secondary)",
                        border: "1px solid var(--color-sentinel-border)",
                      }}
                    >
                      <div className="text-xs mb-2" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                        If Failure Occurs
                      </div>
                      <div className="text-xl font-bold" style={{ color: "var(--color-status-error)" }}>
                        {formatZAR(prediction.cost_impact.failure_breakdown.total_zar)}
                      </div>
                      <div className="text-xs mt-2 space-y-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        <div className="flex justify-between">
                          <span>Emergency repair:</span>
                          <span>{formatZAR(prediction.cost_impact.failure_breakdown.emergency_repair_zar)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Downtime loss:</span>
                          <span>{formatZAR(prediction.cost_impact.failure_breakdown.downtime_loss_zar)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Downtime:</span>
                          <span>{prediction.cost_impact.failure_breakdown.downtime_hours}h</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Savings highlight */}
                  <div className="flex justify-between items-center">
                    <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      Potential Savings
                    </span>
                    <span className="text-lg font-bold" style={{ color: "var(--color-status-success)" }}>
                      {formatZAR(prediction.cost_impact.potential_savings_zar)} ({prediction.cost_impact.savings_percent}%)
                    </span>
                  </div>
                </div>
              ) : null}
            </SectionCard>
          )}

          {/* Evidence Details Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Latest Reading */}
            <SectionCard title="Latest Reading">
              {reading ? (
                <>
                  <div className="flex justify-between items-start mb-3">
                    <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {reading.parameter.replace(/_/g, " ")}
                    </span>
                    <span
                      className="text-xs px-2 py-0.5 rounded flex items-center gap-1"
                      style={{
                        background:
                          reading.trend === "increasing" || reading.trend === "declining"
                            ? "rgba(242, 73, 92, 0.15)"
                            : "rgba(50, 116, 217, 0.15)",
                        color:
                          reading.trend === "increasing" || reading.trend === "declining"
                            ? "var(--color-status-error)"
                            : "var(--color-sentinel-blue)",
                      }}
                    >
                      {reading.trend === "increasing" || reading.trend === "declining" ? (
                        <TrendingUp className="h-3 w-3" />
                      ) : (
                        <Activity className="h-3 w-3" />
                      )}
                      {reading.trend}
                    </span>
                  </div>
                  <div
                    className="text-3xl font-bold mb-2"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    {reading.value}
                    <span
                      className="text-sm ml-2"
                      style={{ color: "var(--color-sentinel-text-disabled)" }}
                    >
                      (baseline: {reading.baseline})
                    </span>
                  </div>
                  <div className="flex gap-4">
                    <div>
                      <span
                        className="text-xs"
                        style={{ color: "var(--color-sentinel-text-disabled)" }}
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
                        style={{ color: "var(--color-sentinel-text-disabled)" }}
                      >
                        Threshold
                      </span>
                      <div
                        className="text-sm font-semibold"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        {reading.threshold}
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div style={{ color: "var(--color-sentinel-text-disabled)" }}>
                  No reading data available
                </div>
              )}
            </SectionCard>

            {/* Alarm Frequency */}
            <SectionCard title="Alarm Frequency (30 days)">
              <div className="space-y-2">
                {prediction.evidence?.alarm_frequency ? (
                  Object.entries(prediction.evidence.alarm_frequency).map(([alarm, count]) => (
                    <div key={alarm} className="flex justify-between items-center">
                      <span
                        className="text-sm"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
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
                  ))
                ) : (
                  <div style={{ color: "var(--color-sentinel-text-disabled)" }}>
                    No alarm data available
                  </div>
                )}
              </div>
            </SectionCard>
          </div>

          {/* Technician Notes with AI Highlighting */}
          {prediction.evidence?.technician_notes && prediction.evidence.technician_notes.length > 0 && (
            <HighlightedNotes notes={prediction.evidence.technician_notes} />
          )}

          {/* Pattern Timeline - Cross-site pattern recognition */}
          {prediction.similar_failures && prediction.similar_failures.length > 0 && (
            <PatternTimeline
              currentSite={prediction.site_name}
              currentEquipment={prediction.equipment_name}
              predictedDate={prediction.predicted_failure_date}
              similarFailures={prediction.similar_failures}
            />
          )}

          {/* Financial Impact */}
          {prediction.financial_impact && (
            <SectionCard title="Financial Impact Analysis">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <div
                    className="text-xl font-bold"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    {formatZAR(prediction.financial_impact.repair_cost_zar || 0)}
                  </div>
                  <span
                    className="text-xs"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Repair Cost
                  </span>
                </div>
                <div>
                  <div
                    className="text-xl font-bold"
                    style={{ color: "var(--color-status-error)" }}
                  >
                    {formatZAR(prediction.financial_impact.potential_loss_zar || 0)}
                  </div>
                  <span
                    className="text-xs"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
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
                      (prediction.financial_impact.potential_loss_zar || 0) -
                        (prediction.financial_impact.repair_cost_zar || 0)
                    )}
                  </div>
                  <span
                    className="text-xs"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Potential Savings
                  </span>
                </div>
                <div>
                  <div
                    className="text-xl font-bold"
                    style={{ color: "var(--color-sentinel-amber)" }}
                  >
                    {prediction.financial_impact.estimated_repair_hours || 0}h
                  </div>
                  <span
                    className="text-xs"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Est. Downtime
                  </span>
                </div>
              </div>
            </SectionCard>
          )}

          {/* Maintenance History Section */}
          {prediction.id && (
            <div
              style={{
                backgroundColor: "var(--sentinel-bg-panel)",
                padding: "1.5rem",
                borderRadius: "8px",
                border: "1px solid var(--color-sentinel-border)",
                marginBottom: "1.5rem",
              }}
            >
              <h3
                style={{
                  fontSize: "1.125rem",
                  fontWeight: 600,
                  marginBottom: "1rem",
                  color: "var(--color-sentinel-text-primary)",
                }}
              >
                Maintenance History
              </h3>
              <MaintenanceHistoryTabs equipmentId={prediction.id} equipmentCode={prediction.equipment_code} />
            </div>
          )}

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
                  {(prediction.urgency || "pending").toUpperCase()}
                </span>
                <p
                  className="text-sm mt-1"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  {prediction.recommended_action}
                </p>
              </div>
            </div>
          </div>

          {/* Parts Required */}
          {prediction.parts_required && prediction.parts_required.length > 0 && (
            <SectionCard title="Parts Required">
              <div className="space-y-3">
                {prediction.parts_required.map((part, index) => (
                  typeof part === 'string' ? (
                    // Old format: simple string
                    <div key={index} className="flex items-center gap-2">
                      <Wrench
                        className="h-4 w-4"
                        style={{ color: "var(--color-sentinel-text-disabled)" }}
                      />
                      <span style={{ color: "var(--color-sentinel-text-primary)" }}>{part}</span>
                    </div>
                  ) : (
                    // New format: object with details
                    <div
                      key={index}
                      className="p-3 rounded"
                      style={{
                        background: "var(--color-sentinel-bg-secondary)",
                        border: "1px solid var(--color-sentinel-border)",
                      }}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-2">
                          <Wrench
                            className="h-4 w-4 mt-0.5"
                            style={{ color: "var(--color-sentinel-text-disabled)" }}
                          />
                          <div>
                            <div className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                              {part.name}
                            </div>
                            <div className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                              Part #: {part.part_number} • Qty: {part.quantity}
                            </div>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                            {formatZAR(part.cost_zar)}
                          </div>
                          <div className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                            {part.lead_time_days} day{part.lead_time_days !== 1 ? 's' : ''} lead time
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                ))}

                {/* Total parts cost for new format */}
                {typeof prediction.parts_required[0] !== 'string' && (
                  <div
                    className="pt-3 mt-3 flex justify-between items-center"
                    style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
                  >
                    <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      Total Parts Cost
                    </span>
                    <span className="text-lg font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {formatZAR(
                        (prediction.parts_required as Array<{ cost_zar: number; quantity: number }>)
                          .reduce((sum, p) => sum + (p.cost_zar * p.quantity), 0)
                      )}
                    </span>
                  </div>
                )}
              </div>
            </SectionCard>
          )}

          {/* Baseline Lineage (Phase 236-01 AC-7): the evidence chain that
              produced this prediction — active rollup baseline → source
              service record / WO → structured readings. */}
          <BaselineLineageSection predictionCode={prediction.id} />

          {/* Footer Actions */}
          <div className="flex justify-end gap-3 pt-4">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded text-sm font-medium transition-colors cursor-pointer hover:brightness-110"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                color: "var(--color-sentinel-text-primary)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              Close
            </button>
            <button
              onClick={() => {
                if (onCreateWorkOrder) {
                  onCreateWorkOrder(prediction.equipment_id || prediction.id, prediction.equipment_name);
                }
                onClose();
              }}
              className="px-4 py-2 rounded text-sm font-medium flex items-center gap-2 transition-colors cursor-pointer hover:brightness-110"
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
      </div>
    </div>}</>
  );
}

// Helper Components
function MetricCard({ value, label, color }: { value: string; label: string; color: string }) {
  return (
    <div
      className="rounded p-4 text-center"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      <div className="text-3xl font-bold mb-1" style={{ color }}>
        {value}
      </div>
      <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
        {label}
      </span>
    </div>
  );
}

interface PredictionLineage {
  baseline_state: string;
  grounded: boolean;
  baseline: {
    baseline_date?: string;
    baseline_type?: string;
    captured_by?: string;
    elements: Array<{ element_id: string; value?: number; sigma?: number; n?: number; unit?: string }>;
  } | null;
  service_record: { code?: string; work_order_id?: string; technician_name?: string } | null;
  readings: Array<{ element_id?: string; reading_type?: string; numeric_value?: number; value?: string; unit?: string }>;
}

function BaselineLineageSection({ predictionCode }: { predictionCode: string }) {
  const [lineage, setLineage] = useState<PredictionLineage | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    authorizedFetch(`/api/predictions/${encodeURIComponent(predictionCode)}/lineage`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!cancelled) setLineage(data);
      })
      .catch(() => {
        if (!cancelled) setLineage(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [predictionCode]);

  if (loading || !lineage) return null;

  const secondary = { color: "var(--color-sentinel-text-secondary)" };
  const primary = { color: "var(--color-sentinel-text-primary)" };

  return (
    <SectionCard title="Baseline Lineage">
      {!lineage.grounded ? (
        <div className="flex items-start gap-2">
          <Link2 className="h-4 w-4 mt-0.5" style={{ color: "var(--color-sentinel-amber)" }} />
          <p className="text-sm" style={secondary}>
            {lineage.baseline_state === "seed_only"
              ? "Seed baseline only — this prediction is not yet grounded in measured readings. It unlocks once the first PPM service readings roll into an active baseline."
              : "No measured baseline yet — this equipment has no rolling baseline, so no service record backs this prediction."}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
            <span className="text-sm" style={primary}>
              Grounded in a rolling baseline
              {lineage.service_record?.work_order_id ? ` from ${lineage.service_record.work_order_id}` : ""}
              {lineage.service_record?.technician_name ? ` · ${lineage.service_record.technician_name}` : ""}
            </span>
          </div>

          {lineage.baseline?.elements && lineage.baseline.elements.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr style={secondary}>
                    <th className="text-left py-1 pr-4">Element</th>
                    <th className="text-right py-1 pr-4">Baseline (mean)</th>
                    <th className="text-right py-1 pr-4">σ</th>
                    <th className="text-right py-1">n</th>
                  </tr>
                </thead>
                <tbody>
                  {lineage.baseline.elements.map((el) => (
                    <tr key={el.element_id} style={{ borderTop: "1px solid var(--color-sentinel-border)" }}>
                      <td className="py-1 pr-4" style={primary}>
                        {el.element_id}
                      </td>
                      <td className="text-right py-1 pr-4" style={primary}>
                        {el.value != null ? el.value : "—"}
                        {el.unit ? ` ${el.unit}` : ""}
                      </td>
                      <td className="text-right py-1 pr-4" style={secondary}>
                        {el.sigma != null ? el.sigma : "—"}
                      </td>
                      <td className="text-right py-1" style={secondary}>
                        {el.n != null ? el.n : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {lineage.readings.length > 0 && (
            <p className="text-xs" style={secondary}>
              {lineage.readings.length} technician reading{lineage.readings.length === 1 ? "" : "s"} captured
              {lineage.service_record?.code ? ` on service record ${lineage.service_record.code}` : ""}.
            </p>
          )}
        </div>
      )}
    </SectionCard>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="rounded overflow-hidden"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      <div
        className="px-4 py-3"
        style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
      >
        <h3 className="font-semibold text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
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

/**
 * PredictionCard Component - SENTINEL risk prediction panel
 *
 * Features:
 * - Gauge-style risk probability indicator
 * - Asset and site context
 * - Timeframe and risk level badges
 * - Evidence metrics preview
 * - Clickable for full details
 *
 * Follows SENTINEL dark theme design.
 */

import {
  AlertTriangle,
  Clock,
  Activity,
  Calendar,
  ChevronRight,
} from "lucide-react";

interface PredictionCardProps {
  prediction: {
    id: string;
    equipment_name: string;
    site_name: string;
    site_id: string;
    equipment_type: string;
    prediction_type: string;
    probability_percent: number;
    confidence: "high" | "medium" | "low";
    predicted_failure_date: string;
    timeframe_days: number;
    severity: "critical" | "warning" | "healthy";
    evidence: {
      repeat_work_orders?: number;
      asset_age_years?: number;
      age_years?: number; // Alternate field name
      expected_life_years?: number;
      health_score?: number;
      health_trend?: string;
      anomaly_score?: number;
      observation?: string;
      alarm_frequency?: Record<string, number>;
      latest_reading?: {
        parameter?: string;
        value?: number;
        baseline?: number;
        threshold?: number;
        trend?: string;
      };
    };
  };
  onClick?: () => void;
}

/**
 * Get risk level configuration for SENTINEL styling
 */
function getSeverityConfig(severity: string): {
  color: string;
  bg: string;
  label: string;
} {
  switch (severity) {
    case "critical":
      return {
        color: "var(--color-sentinel-red)",
        bg: "rgba(220, 38, 38, 0.15)",
        label: "CRITICAL",
      };
    case "warning":
      return {
        color: "var(--color-sentinel-amber)",
        bg: "rgba(245, 158, 11, 0.15)",
        label: "WARNING",
      };
    case "high":
      return {
        color: "#F97316",
        bg: "rgba(249, 115, 22, 0.15)",
        label: "HIGH RISK",
      };
    case "medium":
      return {
        color: "var(--color-sentinel-amber)",
        bg: "rgba(245, 158, 11, 0.15)",
        label: "ELEVATED",
      };
    case "low":
      return {
        color: "var(--color-sentinel-green)",
        bg: "rgba(16, 185, 129, 0.15)",
        label: "LOW RISK",
      };
    default:
      return {
        color: "var(--color-sentinel-text-secondary)",
        bg: "rgba(142, 142, 142, 0.15)",
        label: "UNKNOWN",
      };
  }
}

/**
 * Get confidence configuration
 */
function getConfidenceConfig(confidence: string): {
  color: string;
  label: string;
} {
  switch (confidence) {
    case "high":
      return {
        color: "var(--color-sentinel-green)",
        label: "HIGH CONFIDENCE",
      };
    case "medium":
      return {
        color: "var(--color-sentinel-amber)",
        label: "MEDIUM CONFIDENCE",
      };
    case "low":
      return {
        color: "var(--color-sentinel-text-secondary)",
        label: "LOW CONFIDENCE",
      };
    default:
      return {
        color: "var(--color-sentinel-text-secondary)",
        label: "UNKNOWN",
      };
  }
}

/**
 * Get gauge color based on probability
 */
function getGaugeColor(probability: number): string {
  if (probability >= 75) return "var(--color-sentinel-red)";
  if (probability >= 50) return "#F97316";
  if (probability >= 25) return "var(--color-sentinel-amber)";
  return "var(--color-sentinel-green)";
}

/**
 * Format prediction type for display
 */
function formatPredictionType(type: string): string {
  return type
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function PredictionCard({ prediction, onClick }: PredictionCardProps) {
  const severityConfig = getSeverityConfig(prediction.severity);
  const confidenceConfig = getConfidenceConfig(prediction.confidence);
  const gaugeColor = getGaugeColor(prediction.probability_percent);

  // Format date
  const failureDate = new Date(prediction.predicted_failure_date);
  const formattedDate = failureDate.toLocaleDateString("en-ZA", {
    day: "numeric",
    month: "short",
  });

  // Calculate gauge arc
  const circumference = 2 * Math.PI * 40; // radius = 40
  const progress = (prediction.probability_percent / 100) * (circumference * 0.75); // 270 degrees

  return (
    <div
      className={`relative rounded-md overflow-hidden transition-all duration-150 ${onClick ? "cursor-pointer hover:brightness-110" : ""}`}
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
      onClick={onClick}
    >
      {/* Top accent based on risk level */}
      <div
        className="absolute top-0 left-0 right-0 h-1"
        style={{ background: severityConfig.color }}
      />

      <div className="p-4 pt-5">
        {/* Header: Gauge and Timeframe */}
        <div className="flex items-start gap-4 mb-4">
          {/* Risk Gauge Circle */}
          <div className="relative w-20 h-20 flex-shrink-0">
            <svg
              className="w-full h-full"
              viewBox="0 0 100 100"
              style={{ transform: "rotate(-225deg)" }}
            >
              {/* Background arc */}
              <circle
                cx="50"
                cy="50"
                r="40"
                fill="none"
                stroke="var(--color-sentinel-border)"
                strokeWidth="8"
                strokeDasharray={`${circumference * 0.75} ${circumference}`}
                strokeLinecap="round"
              />
              {/* Progress arc */}
              <circle
                cx="50"
                cy="50"
                r="40"
                fill="none"
                stroke={gaugeColor}
                strokeWidth="8"
                strokeDasharray={`${progress} ${circumference}`}
                strokeLinecap="round"
                style={{ transition: "stroke-dasharray 0.5s ease" }}
              />
            </svg>
            {/* Center value */}
            <div
              className="absolute inset-0 flex flex-col items-center justify-center"
              style={{ transform: "translateY(-4px)" }}
            >
              <span
                className="text-2xl font-bold"
                style={{
                  color: gaugeColor,
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {prediction.probability_percent}
              </span>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                %
              </span>
            </div>
          </div>

          {/* Timeframe and Risk Level */}
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <span
                className="text-xs font-medium px-2 py-0.5 rounded"
                style={{
                  background: severityConfig.bg,
                  color: severityConfig.color,
                }}
              >
                {severityConfig.label}
              </span>
            </div>
            <div className="flex items-center gap-1 mb-1">
              <Clock
                className="h-4 w-4"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              />
              <span
                className="text-lg font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {prediction.timeframe_days} days
              </span>
            </div>
            <span
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              until predicted risk event
            </span>
          </div>
        </div>

        {/* Asset Info */}
        <div
          className="pb-3 mb-3"
          style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
        >
          <h4
            className="font-medium text-sm mb-1"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            {prediction.equipment_name}
          </h4>
          <div className="flex items-center gap-2 text-xs">
            <Activity
              className="h-3 w-3"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            />
            <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {prediction.site_name}
            </span>
            <span style={{ color: "var(--color-sentinel-text-disabled)" }}>•</span>
            <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Site ID: {prediction.site_id}
            </span>
            <span style={{ color: "var(--color-sentinel-text-disabled)" }}>•</span>
            <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {prediction.equipment_type}
            </span>
          </div>
        </div>

        {/* Risk Type Alert */}
        <div
          className="flex items-center gap-2 p-2 rounded mb-3"
          style={{
            background: severityConfig.bg,
            border: `1px solid ${severityConfig.color}30`,
          }}
        >
          <AlertTriangle
            className="h-4 w-4 flex-shrink-0"
            style={{ color: severityConfig.color }}
          />
          <div className="flex-1">
            <span
              className="text-xs font-medium"
              style={{ color: severityConfig.color }}
            >
              {formatPredictionType(prediction.prediction_type)}
            </span>
            <div className="flex items-center gap-1 mt-0.5">
              <Calendar
                className="h-3 w-3"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {formattedDate}
              </span>
            </div>
          </div>
        </div>

        {/* Evidence Metrics */}
        <div className="grid grid-cols-3 gap-2 mb-3">
          {/* Health Score */}
          <div
            className="p-2 rounded"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <div className="flex items-center gap-1 mb-1">
              <Activity
                className="h-3 w-3"
                style={{ color: "var(--color-sentinel-blue)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                Health
              </span>
            </div>
            <span
              className="text-lg font-medium"
              style={{
                color: "var(--color-sentinel-blue)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {prediction.evidence?.health_score ?? "N/A"}
              {prediction.evidence?.health_score !== undefined && (
                <span
                  className="text-xs ml-1"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  %
                </span>
              )}
            </span>
          </div>

          {/* Health Trend */}
          <div
            className="p-2 rounded"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <div className="flex items-center gap-1 mb-1">
              <Clock
                className="h-3 w-3"
                style={{ color: "#a78bfa" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                Trend
              </span>
            </div>
            <span
              className="text-sm font-medium capitalize"
              style={{
                color: prediction.evidence?.latest_reading?.trend === "decreasing" || prediction.evidence?.health_trend === "declining"
                  ? "var(--color-sentinel-red)"
                  : "#a78bfa",
              }}
            >
              {prediction.evidence?.latest_reading?.trend ?? prediction.evidence?.health_trend ?? "N/A"}
            </span>
          </div>

          {/* Asset Age */}
          <div
            className="p-2 rounded"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <div className="flex items-center gap-1 mb-1">
              <Calendar
                className="h-3 w-3"
                style={{ color: "var(--color-sentinel-amber)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                Age
              </span>
            </div>
            <span
              className="text-sm font-medium"
              style={{
                color: (prediction.evidence?.asset_age_years ?? prediction.evidence?.age_years) !== undefined &&
                       prediction.evidence?.expected_life_years !== undefined &&
                       (prediction.evidence?.asset_age_years ?? prediction.evidence?.age_years ?? 0) > prediction.evidence.expected_life_years * 0.8
                  ? "var(--color-sentinel-red)"
                  : "var(--color-sentinel-amber)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {(prediction.evidence?.asset_age_years ?? prediction.evidence?.age_years) !== undefined
                ? `${prediction.evidence?.asset_age_years ?? prediction.evidence?.age_years}y`
                : "N/A"}
              {prediction.evidence?.expected_life_years !== undefined && (
                <span
                  className="text-xs ml-0.5"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  /{prediction.evidence.expected_life_years}y
                </span>
              )}
            </span>
          </div>
        </div>

        {/* Second row of evidence */}
        <div className="grid grid-cols-2 gap-2 mb-3">
          {/* Anomaly Score / Alarms */}
          <div
            className="p-2 rounded"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <div className="flex items-center gap-1 mb-1">
              <AlertTriangle
                className="h-3 w-3"
                style={{ color: "var(--color-sentinel-red)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                {prediction.evidence?.anomaly_score !== undefined ? "Anomaly" : "Alarms"}
              </span>
            </div>
            <span
              className="text-sm font-medium"
              style={{
                color: prediction.evidence?.anomaly_score !== undefined
                  ? prediction.evidence.anomaly_score > 0.5
                    ? "var(--color-sentinel-red)"
                    : prediction.evidence.anomaly_score > 0.3
                      ? "var(--color-sentinel-amber)"
                      : "var(--color-sentinel-text-primary)"
                  : prediction.evidence?.alarm_frequency
                    ? Object.values(prediction.evidence.alarm_frequency).reduce((a, b) => a + b, 0) > 5
                      ? "var(--color-sentinel-red)"
                      : "var(--color-sentinel-text-primary)"
                    : "var(--color-sentinel-text-disabled)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {prediction.evidence?.anomaly_score !== undefined
                ? `${Math.round(prediction.evidence.anomaly_score * 100)}%`
                : prediction.evidence?.alarm_frequency
                  ? Object.values(prediction.evidence.alarm_frequency).reduce((a, b) => a + b, 0)
                  : "N/A"}
            </span>
          </div>

          {/* Last Reading */}
          <div
            className="p-2 rounded"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <div className="flex items-center gap-1 mb-1">
              <Activity
                className="h-3 w-3"
                style={{ color: "var(--color-sentinel-green)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                Last Reading
              </span>
            </div>
            <span
              className="text-sm font-medium"
              style={{
                color: prediction.evidence?.latest_reading?.value !== undefined &&
                       prediction.evidence?.latest_reading?.threshold !== undefined &&
                       prediction.evidence.latest_reading.value < prediction.evidence.latest_reading.threshold
                  ? "var(--color-sentinel-red)"
                  : "var(--color-sentinel-green)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {prediction.evidence?.latest_reading?.value ?? "N/A"}
              {prediction.evidence?.latest_reading?.baseline !== undefined && (
                <span
                  className="text-xs ml-1"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  / {prediction.evidence.latest_reading.baseline}
                </span>
              )}
            </span>
          </div>
        </div>

        {/* Footer: Confidence and Action */}
        <div className="flex items-center justify-between">
          <span
            className="text-xs font-medium px-2 py-0.5 rounded"
            style={{
              background: `${confidenceConfig.color}20`,
              color: confidenceConfig.color,
            }}
          >
            {confidenceConfig.label}
          </span>
          {onClick && (
            <div
              className="flex items-center gap-1 text-xs"
              style={{ color: "var(--color-sentinel-amber)" }}
            >
              View Details
              <ChevronRight className="h-3 w-3" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default PredictionCard;

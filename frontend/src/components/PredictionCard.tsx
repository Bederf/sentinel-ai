/**
 * PredictionCard Component - Grafana-inspired prediction panel
 *
 * Features:
 * - Gauge-style probability indicator
 * - Asset and site context
 * - Timeframe and severity badges
 * - Evidence metrics preview
 * - Clickable for full details
 *
 * Follows Grafana gauge panel design with dark theme.
 */

import {
  AlertTriangle,
  Clock,
  Activity,
  Wrench,
  Calendar,
  ChevronRight,
} from "lucide-react";

interface PredictionCardProps {
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
      asset_age_years: number;
    };
  };
  onClick?: () => void;
}

/**
 * Get severity configuration for Grafana styling
 */
function getSeverityConfig(severity: string): {
  color: string;
  bg: string;
  label: string;
} {
  switch (severity) {
    case "critical":
      return {
        color: "var(--color-status-error)",
        bg: "rgba(242, 73, 92, 0.15)",
        label: "CRITICAL",
      };
    case "high":
      return {
        color: "var(--color-status-warning)",
        bg: "rgba(255, 152, 48, 0.15)",
        label: "HIGH",
      };
    case "medium":
      return {
        color: "var(--color-grafana-yellow)",
        bg: "rgba(242, 204, 12, 0.15)",
        label: "MEDIUM",
      };
    case "low":
      return {
        color: "var(--color-grafana-blue)",
        bg: "rgba(50, 116, 217, 0.15)",
        label: "LOW",
      };
    default:
      return {
        color: "var(--color-grafana-text-secondary)",
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
        color: "var(--color-status-success)",
        label: "HIGH CONFIDENCE",
      };
    case "medium":
      return {
        color: "var(--color-grafana-yellow)",
        label: "MEDIUM CONFIDENCE",
      };
    case "low":
      return {
        color: "var(--color-grafana-text-secondary)",
        label: "LOW CONFIDENCE",
      };
    default:
      return {
        color: "var(--color-grafana-text-secondary)",
        label: "UNKNOWN",
      };
  }
}

/**
 * Get gauge color based on probability
 */
function getGaugeColor(probability: number): string {
  if (probability >= 75) return "var(--color-status-error)";
  if (probability >= 50) return "var(--color-status-warning)";
  if (probability >= 25) return "var(--color-grafana-yellow)";
  return "var(--color-status-success)";
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
      className={`relative rounded overflow-hidden transition-all duration-150 ${onClick ? "cursor-pointer hover:brightness-110" : ""}`}
      style={{
        background: "var(--color-grafana-bg-panel)",
        border: "1px solid var(--color-grafana-border)",
      }}
      onClick={onClick}
    >
      {/* Top accent based on severity */}
      <div
        className="absolute top-0 left-0 right-0 h-1"
        style={{ background: severityConfig.color }}
      />

      <div className="p-4 pt-5">
        {/* Header: Gauge and Timeframe */}
        <div className="flex items-start gap-4 mb-4">
          {/* Gauge Circle */}
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
                stroke="var(--color-grafana-border)"
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
                style={{ color: "var(--color-grafana-text-disabled)" }}
              >
                %
              </span>
            </div>
          </div>

          {/* Timeframe and Severity */}
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
                style={{ color: "var(--color-grafana-text-secondary)" }}
              />
              <span
                className="text-lg font-medium"
                style={{ color: "var(--color-grafana-text-primary)" }}
              >
                {prediction.timeframe_days} days
              </span>
            </div>
            <span
              className="text-xs"
              style={{ color: "var(--color-grafana-text-disabled)" }}
            >
              until predicted failure
            </span>
          </div>
        </div>

        {/* Equipment Info */}
        <div
          className="pb-3 mb-3"
          style={{ borderBottom: "1px solid var(--color-grafana-border)" }}
        >
          <h4
            className="font-medium text-sm mb-1"
            style={{ color: "var(--color-grafana-text-primary)" }}
          >
            {prediction.equipment_name}
          </h4>
          <div className="flex items-center gap-2 text-xs">
            <Activity
              className="h-3 w-3"
              style={{ color: "var(--color-grafana-text-disabled)" }}
            />
            <span style={{ color: "var(--color-grafana-text-secondary)" }}>
              {prediction.site_name}
            </span>
            <span style={{ color: "var(--color-grafana-text-disabled)" }}>•</span>
            <span style={{ color: "var(--color-grafana-text-secondary)" }}>
              {prediction.equipment_type}
            </span>
          </div>
        </div>

        {/* Prediction Type Alert */}
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
                style={{ color: "var(--color-grafana-text-disabled)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-grafana-text-secondary)" }}
              >
                {formattedDate}
              </span>
            </div>
          </div>
        </div>

        {/* Evidence Metrics */}
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div
            className="p-2 rounded"
            style={{ background: "var(--color-grafana-bg-secondary)" }}
          >
            <div className="flex items-center gap-1 mb-1">
              <Wrench
                className="h-3 w-3"
                style={{ color: "var(--color-grafana-cyan)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-grafana-text-disabled)" }}
              >
                Repeat Calls
              </span>
            </div>
            <span
              className="text-lg font-medium"
              style={{
                color: "var(--color-grafana-cyan)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {prediction.evidence.repeat_work_orders}
            </span>
          </div>
          <div
            className="p-2 rounded"
            style={{ background: "var(--color-grafana-bg-secondary)" }}
          >
            <div className="flex items-center gap-1 mb-1">
              <Clock
                className="h-3 w-3"
                style={{ color: "var(--color-grafana-purple)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-grafana-text-disabled)" }}
              >
                Asset Age
              </span>
            </div>
            <span
              className="text-lg font-medium"
              style={{
                color: "var(--color-grafana-purple)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {prediction.evidence.asset_age_years}
              <span
                className="text-xs ml-1"
                style={{ color: "var(--color-grafana-text-disabled)" }}
              >
                yrs
              </span>
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
              style={{ color: "var(--color-grafana-text-link)" }}
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

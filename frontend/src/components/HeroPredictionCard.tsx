/**
 * HeroPredictionCard Component - Featured high-risk prediction
 *
 * Draws immediate attention to the highest-risk prediction with:
 * - Large animated probability gauge
 * - Cost comparison trio (Failure | Preventive | Savings)
 * - Story excerpt
 * - Similar patterns badge
 */

import { AlertTriangle, TrendingUp, Clock, Zap } from "lucide-react";
import type { Prediction } from '@/lib/api';

interface HeroPredictionCardProps {
  prediction: Prediction;
  onClick: () => void;
}

export function HeroPredictionCard({ prediction, onClick }: HeroPredictionCardProps) {
  // Format currency with better readability
  const formatZAR = (amount: number) => {
    // Use en-ZA locale for proper South African Rand formatting
    return new Intl.NumberFormat("en-ZA", {
      style: "currency",
      currency: "ZAR",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
      notation: "standard",
    }).format(amount);
  };

  // Calculate costs and savings
  // Failure Cost = total cost if failure occurs (potential_loss_zar includes repair + downtime)
  // Preventive Cost = cost to prevent failure (repair_cost_zar)
  // Savings = how much you save by doing preventive maintenance
  const failureCost = prediction.financial_impact.potential_loss_zar;
  const preventiveCost = prediction.financial_impact.repair_cost_zar;

  // Calculate savings: failure cost - preventive cost
  // If preventive cost is higher, there's no savings (edge case in data)
  const savings = failureCost - preventiveCost;

  // Ensure we show positive savings only (if preventive > failure, show 0)
  const displaySavings = Math.max(0, savings);

  // Severity colors
  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "critical":
        return "var(--color-status-error)";
      case "high":
        return "var(--color-status-warning)";
      case "medium":
        return "var(--color-grafana-yellow)";
      default:
        return "var(--color-grafana-blue)";
    }
  };

  const severityColor = getSeverityColor(prediction.severity);

  // Get story from contributing factors or generate one
  const storyExcerpt =
    prediction.contributing_factors.length > 0
      ? prediction.contributing_factors
          .slice(0, 2)
          .map((f) => f.description)
          .join(" ")
      : `${prediction.equipment_name} shows ${prediction.probability_percent}% probability of failure within ${prediction.timeframe_days} days.`;

  return (
    <div
      className="rounded-lg overflow-hidden cursor-pointer transition-all hover:scale-[1.01] glass-card"
      style={{
        background: `linear-gradient(135deg, var(--glass-bg) 0%, ${severityColor}15 100%)`,
        borderColor: `${severityColor}40`,
        boxShadow: `0 4px 24px ${severityColor}20`,
      }}
      onClick={onClick}
    >
      {/* Header ribbon */}
      <div
        className="px-4 py-2 flex items-center justify-between"
        style={{ background: `${severityColor}20` }}
      >
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4" style={{ color: severityColor }} />
          <span className="text-xs font-bold uppercase tracking-wider" style={{ color: severityColor }}>
            Highest Risk - Immediate Attention Required
          </span>
        </div>
        {prediction.similar_failures.length > 0 && (
          <span
            className="text-xs px-2 py-0.5 rounded-full font-medium"
            style={{
              background: "var(--color-grafana-purple)",
              color: "white",
            }}
          >
            {prediction.similar_failures.length} similar patterns detected
          </span>
        )}
      </div>

      <div className="p-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Equipment Info + Gauge */}
          <div className="flex flex-col items-center lg:items-start">
            {/* Large Probability Gauge */}
            <div className="relative mb-4">
              <svg width="120" height="120" viewBox="0 0 120 120">
                {/* Background circle */}
                <circle
                  cx="60"
                  cy="60"
                  r="52"
                  fill="none"
                  stroke="var(--color-grafana-border)"
                  strokeWidth="12"
                />
                {/* Progress circle */}
                <circle
                  cx="60"
                  cy="60"
                  r="52"
                  fill="none"
                  stroke={severityColor}
                  strokeWidth="12"
                  strokeLinecap="round"
                  strokeDasharray={`${(prediction.probability_percent / 100) * 327} 327`}
                  transform="rotate(-90 60 60)"
                  className="transition-all duration-1000"
                  style={{
                    filter: `drop-shadow(0 0 8px ${severityColor})`,
                  }}
                />
                {/* Percentage text */}
                <text
                  x="60"
                  y="55"
                  textAnchor="middle"
                  className="text-2xl font-bold"
                  fill={severityColor}
                >
                  {prediction.probability_percent}%
                </text>
                <text
                  x="60"
                  y="72"
                  textAnchor="middle"
                  className="text-xs"
                  fill="var(--color-grafana-text-secondary)"
                >
                  PROBABILITY
                </text>
              </svg>
            </div>

            {/* Equipment Name */}
            <h3
              className="text-xl font-bold mb-1 text-center lg:text-left"
              style={{ color: "var(--color-grafana-text-primary)" }}
            >
              {prediction.equipment_name}
            </h3>
            <p
              className="text-sm mb-3 text-center lg:text-left"
              style={{ color: "var(--color-grafana-text-secondary)" }}
            >
              {prediction.site_name} • {prediction.equipment_type}
            </p>

            {/* Time badge */}
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded-full"
              style={{ background: "rgba(255, 152, 48, 0.15)" }}
            >
              <Clock className="h-4 w-4" style={{ color: "var(--color-status-warning)" }} />
              <span className="text-sm font-medium" style={{ color: "var(--color-status-warning)" }}>
                {prediction.timeframe_days} days until predicted failure
              </span>
            </div>
          </div>

          {/* Center: Cost Comparison Trio */}
          <div className="flex flex-col justify-center px-2">
            <h4
              className="text-xs font-semibold uppercase tracking-wider mb-5 text-center"
              style={{ color: "var(--color-grafana-text-secondary)" }}
            >
              Cost Impact Analysis
            </h4>

            <div className="grid grid-cols-3 gap-3 lg:gap-5">
              {/* Failure Cost */}
              <div className="text-center flex flex-col items-center">
                <div
                  className="text-lg lg:text-xl xl:text-2xl font-bold mb-2 leading-tight"
                  style={{
                    color: "var(--color-status-error)",
                    fontVariantNumeric: "tabular-nums",
                    letterSpacing: "-0.02em"
                  }}
                >
                  {formatZAR(failureCost)}
                </div>
                <div
                  className="text-[10px] lg:text-xs uppercase tracking-wider font-medium mb-2"
                  style={{ color: "var(--color-grafana-text-secondary)" }}
                >
                  Failure Cost
                </div>
                <div
                  className="h-1 w-full rounded-full"
                  style={{ background: "var(--color-status-error)" }}
                />
              </div>

              {/* Preventive Cost */}
              <div className="text-center flex flex-col items-center">
                <div
                  className="text-lg lg:text-xl xl:text-2xl font-bold mb-2 leading-tight"
                  style={{
                    color: "var(--color-grafana-blue)",
                    fontVariantNumeric: "tabular-nums",
                    letterSpacing: "-0.02em"
                  }}
                >
                  {formatZAR(preventiveCost)}
                </div>
                <div
                  className="text-[10px] lg:text-xs uppercase tracking-wider font-medium mb-2"
                  style={{ color: "var(--color-grafana-text-secondary)" }}
                >
                  Preventive Cost
                </div>
                <div
                  className="h-1 w-full rounded-full"
                  style={{ background: "var(--color-grafana-blue)" }}
                />
              </div>

              {/* Savings */}
              <div className="text-center flex flex-col items-center">
                <div
                  className="text-lg lg:text-xl xl:text-2xl font-bold mb-2 leading-tight"
                  style={{
                    color: displaySavings > 0 ? "var(--color-status-success)" : "var(--color-grafana-text-secondary)",
                    fontVariantNumeric: "tabular-nums",
                    letterSpacing: "-0.02em"
                  }}
                >
                  {displaySavings > 0 ? formatZAR(displaySavings) : formatZAR(0)}
                </div>
                <div
                  className="text-[10px] lg:text-xs uppercase tracking-wider font-medium mb-2"
                  style={{ color: "var(--color-grafana-text-secondary)" }}
                >
                  Savings
                </div>
                <div
                  className="h-1 w-full rounded-full"
                  style={{
                    background: displaySavings > 0 ? "var(--color-status-success)" : "var(--color-grafana-text-secondary)",
                    opacity: displaySavings > 0 ? 1 : 0.3
                  }}
                />
              </div>
            </div>
          </div>

          {/* Right: Story Excerpt + CTA */}
          <div className="flex flex-col justify-between">
            {/* Story */}
            <div
              className="p-4 rounded-lg mb-4"
              style={{
                background: "var(--color-grafana-bg-secondary)",
                border: "1px solid var(--color-grafana-border)",
              }}
            >
              <div className="flex items-start gap-2 mb-2">
                <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" style={{ color: severityColor }} />
                <span
                  className="text-xs font-semibold uppercase"
                  style={{ color: severityColor }}
                >
                  AI Analysis
                </span>
                <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-sky-900/30 text-sky-300 border border-sky-800/40 ml-auto">
                  AI
                </span>
              </div>
              <p
                className="text-sm leading-relaxed line-clamp-3"
                style={{ color: "var(--color-grafana-text-primary)" }}
              >
                {storyExcerpt}
              </p>
            </div>

            {/* CTA Button */}
            <button
              className="w-full py-3 px-4 rounded-lg font-medium flex items-center justify-center gap-2 transition-all hover:brightness-110"
              style={{
                background: severityColor,
                color: "white",
              }}
            >
              <TrendingUp className="h-5 w-5" />
              View Full Analysis
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default HeroPredictionCard;

/**
 * ROISummaryCard Component - Portfolio ROI Summary
 *
 * Tells the business value story upfront with:
 * - Risk Exposure total
 * - Investment required
 * - Net Savings
 * - ROI percentage
 * - Summary stats
 */

import { TrendingUp, Shield, DollarSign, Target, Calendar } from "lucide-react";
import type { Prediction } from "../lib/api";

interface ROISummaryCardProps {
  predictions: Prediction[];
}

export function ROISummaryCard({ predictions }: ROISummaryCardProps) {
  // Calculate totals
  const totalRiskExposure = predictions.reduce(
    (sum, p) => sum + p.financial_impact.potential_loss_zar,
    0
  );

  const totalInvestment = predictions.reduce(
    (sum, p) => sum + p.financial_impact.repair_cost_zar,
    0
  );

  const netSavings = totalRiskExposure - totalInvestment;
  const roiPercent = totalInvestment > 0 ? Math.round((netSavings / totalInvestment) * 100) : 0;

  // Calculate timeframe range
  const timeframeDays = predictions.map((p) => p.timeframe_days);
  const minDays = Math.min(...timeframeDays);
  const maxDays = Math.max(...timeframeDays);

  // Format currency
  const formatZAR = (amount: number) =>
    new Intl.NumberFormat("en-ZA", {
      style: "currency",
      currency: "ZAR",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);

  // Calculate bar widths for visual comparison
  const maxValue = Math.max(totalRiskExposure, totalInvestment, netSavings);
  const riskWidth = (totalRiskExposure / maxValue) * 100;
  const investWidth = (totalInvestment / maxValue) * 100;
  const savingsWidth = (netSavings / maxValue) * 100;

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        background: "var(--color-grafana-bg-panel)",
        border: "1px solid var(--color-grafana-border)",
      }}
    >
      {/* Header */}
      <div
        className="px-6 py-4 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--color-grafana-border)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded-lg"
            style={{ background: "rgba(115, 191, 105, 0.15)" }}
          >
            <Target className="h-5 w-5" style={{ color: "var(--color-status-success)" }} />
          </div>
          <div>
            <h3
              className="font-semibold text-base"
              style={{ color: "var(--color-grafana-text-primary)" }}
            >
              AI Predictive Maintenance ROI Summary
            </h3>
            <p
              className="text-xs"
              style={{ color: "var(--color-grafana-text-secondary)" }}
            >
              Potential value from acting on all predictions
            </p>
          </div>
        </div>

        {/* ROI Badge */}
        <div
          className="px-4 py-2 rounded-lg flex items-center gap-2"
          style={{
            background: "rgba(115, 191, 105, 0.15)",
            border: "1px solid var(--color-status-success)",
          }}
        >
          <TrendingUp className="h-5 w-5" style={{ color: "var(--color-status-success)" }} />
          <span
            className="text-2xl font-bold"
            style={{ color: "var(--color-status-success)" }}
          >
            {roiPercent}% ROI
          </span>
        </div>
      </div>

      <div className="p-6">
        {/* Main Value Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
          {/* Risk Exposure */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Shield className="h-4 w-4" style={{ color: "var(--color-status-error)" }} />
              <span
                className="text-xs font-medium uppercase tracking-wider"
                style={{ color: "var(--color-grafana-text-secondary)" }}
              >
                Risk Exposure
              </span>
            </div>
            <div
              className="text-3xl font-bold mb-2"
              style={{ color: "var(--color-status-error)" }}
            >
              {formatZAR(totalRiskExposure)}
            </div>
            <div
              className="h-2 rounded-full overflow-hidden"
              style={{ background: "var(--color-grafana-border)" }}
            >
              <div
                className="h-full rounded-full transition-all duration-1000"
                style={{
                  width: `${riskWidth}%`,
                  background: "var(--color-status-error)",
                }}
              />
            </div>
            <p
              className="text-xs mt-2"
              style={{ color: "var(--color-grafana-text-disabled)" }}
            >
              Total potential loss if failures occur
            </p>
          </div>

          {/* Investment Required */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <DollarSign className="h-4 w-4" style={{ color: "var(--color-grafana-blue)" }} />
              <span
                className="text-xs font-medium uppercase tracking-wider"
                style={{ color: "var(--color-grafana-text-secondary)" }}
              >
                Investment Required
              </span>
            </div>
            <div
              className="text-3xl font-bold mb-2"
              style={{ color: "var(--color-grafana-blue)" }}
            >
              {formatZAR(totalInvestment)}
            </div>
            <div
              className="h-2 rounded-full overflow-hidden"
              style={{ background: "var(--color-grafana-border)" }}
            >
              <div
                className="h-full rounded-full transition-all duration-1000"
                style={{
                  width: `${investWidth}%`,
                  background: "var(--color-grafana-blue)",
                }}
              />
            </div>
            <p
              className="text-xs mt-2"
              style={{ color: "var(--color-grafana-text-disabled)" }}
            >
              Cost to implement preventive maintenance
            </p>
          </div>

          {/* Net Savings */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp className="h-4 w-4" style={{ color: "var(--color-status-success)" }} />
              <span
                className="text-xs font-medium uppercase tracking-wider"
                style={{ color: "var(--color-grafana-text-secondary)" }}
              >
                Net Savings
              </span>
            </div>
            <div
              className="text-3xl font-bold mb-2"
              style={{ color: "var(--color-status-success)" }}
            >
              {formatZAR(netSavings)}
            </div>
            <div
              className="h-2 rounded-full overflow-hidden"
              style={{ background: "var(--color-grafana-border)" }}
            >
              <div
                className="h-full rounded-full transition-all duration-1000"
                style={{
                  width: `${savingsWidth}%`,
                  background: "var(--color-status-success)",
                }}
              />
            </div>
            <p
              className="text-xs mt-2"
              style={{ color: "var(--color-grafana-text-disabled)" }}
            >
              Value protected by acting proactively
            </p>
          </div>
        </div>

        {/* Bottom Stats Row */}
        <div
          className="flex flex-wrap items-center justify-center gap-6 pt-4"
          style={{ borderTop: "1px solid var(--color-grafana-border)" }}
        >
          <div className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded-full"
              style={{ background: "var(--color-grafana-purple)" }}
            />
            <span style={{ color: "var(--color-grafana-text-secondary)" }}>
              <strong style={{ color: "var(--color-grafana-text-primary)" }}>
                {predictions.length}
              </strong>{" "}
              predictions
            </span>
          </div>

          <div
            className="w-px h-4"
            style={{ background: "var(--color-grafana-border)" }}
          />

          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4" style={{ color: "var(--color-grafana-orange)" }} />
            <span style={{ color: "var(--color-grafana-text-secondary)" }}>
              <strong style={{ color: "var(--color-grafana-text-primary)" }}>
                {minDays}-{maxDays}
              </strong>{" "}
              day window to act
            </span>
          </div>

          <div
            className="w-px h-4"
            style={{ background: "var(--color-grafana-border)" }}
          />

          <div className="flex items-center gap-2">
            <span style={{ color: "var(--color-grafana-text-secondary)" }}>
              Avg. confidence:{" "}
              <strong style={{ color: "var(--color-grafana-text-primary)" }}>
                {Math.round(
                  predictions.reduce((sum, p) => sum + p.probability_percent, 0) /
                    predictions.length
                )}
                %
              </strong>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ROISummaryCard;

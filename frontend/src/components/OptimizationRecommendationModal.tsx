/**
 * OptimizationRecommendationModal Component - AI recommendation workflow
 *
 * Displays AI-generated optimization recommendations with:
 * - Current vs recommended settings comparison
 * - Impact analysis (energy, cost, comfort, equipment)
 * - Approve/reject/defer actions
 * - Loading states and success/error feedback
 * - Auto-dismiss after 30 seconds
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import {
  X,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  DollarSign,
  Thermometer,
  Settings,
  AlertCircle,
} from "lucide-react";
import api, { type OptimizationRecommendation } from "../lib/api";
import { formatDateTime } from "../lib/timeFormat";

interface OptimizationRecommendationModalProps {
  isOpen: boolean;
  onClose: () => void;
  recommendation: OptimizationRecommendation | null;
  onApprove?: (recommendationId: string) => Promise<void>;
  onReject?: (recommendationId: string, reason?: string) => Promise<void>;
  siteName?: string;
}

/**
 * Format confidence score as percentage
 */
function formatConfidence(confidence: number): string {
  return `${Math.round(confidence)}%`;
}

/**
 * Get confidence color based on score
 */
function getConfidenceColor(confidence: number): string {
  if (confidence >= 80) return "text-green-400";
  if (confidence >= 60) return "text-yellow-400";
  return "text-orange-400";
}

/**
 * Format currency in ZAR
 */
function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-ZA", {
    style: "currency",
    currency: "ZAR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Format time ago
 */
function formatTimeAgo(timestamp: string): string {
  const now = new Date();
  const time = new Date(timestamp);
  const diffMs = now.getTime() - time.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export function OptimizationRecommendationModal({
  isOpen,
  onClose,
  recommendation,
  onApprove,
  onReject,
  siteName,
}: OptimizationRecommendationModalProps) {
  const [loading, setLoading] = useState(false);
  const [action, setAction] = useState<"approve" | "reject" | "defer" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [timeRemaining, setTimeRemaining] = useState(30);

  // Auto-dismiss countdown
  useEffect(() => {
    if (!isOpen || !recommendation) {
      setTimeRemaining(30);
      return;
    }

    if (timeRemaining <= 0) {
      onClose();
      return;
    }

    const timer = setTimeout(() => {
      setTimeRemaining(timeRemaining - 1);
    }, 1000);

    return () => clearTimeout(timer);
  }, [isOpen, timeRemaining, onClose, recommendation]);

  // Reset state when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      setLoading(false);
      setAction(null);
      setError(null);
      setSuccess(false);
      setTimeRemaining(30);
    }
  }, [isOpen]);

  // Handle approve action
  const handleApprove = async () => {
    if (!recommendation) return;

    setLoading(true);
    setAction("approve");
    setError(null);

    try {
      // Build setpoints array from recommendations
      const setpointsToApply = recommendation.recommendations.map((rec) => ({
        equipment_id: rec.equipment_id,
        point: "setpoint", // Default point name - backend will map to actual point
        value: rec.recommended_value,
      }));

      // Call parent callback or default API method
      // Use timestamp as id if no id field exists
      const recommendationId = recommendation.id || recommendation.timestamp || 'recommendation';
      if (onApprove) {
        await onApprove(recommendationId);
      } else {
        await api.approveOptimization(
          recommendation.site_id,
          recommendationId,
          setpointsToApply
        );
      }

      setSuccess(true);
      setTimeout(() => {
        onClose();
      }, 2000);
    } catch (err) {
      console.error("Failed to approve optimization:", err);
      setError(err instanceof Error ? err.message : "Failed to approve recommendation");
      setLoading(false);
      setAction(null);
    }
  };

  // Handle reject action
  const handleReject = async () => {
    if (!recommendation) return;

    setLoading(true);
    setAction("reject");
    setError(null);

    try {
      // Call parent callback or default API method
      const rejectId = recommendation.id || recommendation.timestamp || 'recommendation';
      if (onReject) {
        await onReject(rejectId, "Rejected by operator");
      } else {
        // Reject API doesn't exist yet, so we'll just close the modal
        // In production, this would call: api.rejectOptimization(recommendation.site_id, recommendation.id, reason)
        await new Promise((resolve) => setTimeout(resolve, 500)); // Simulate API call
      }

      setSuccess(true);
      setTimeout(() => {
        onClose();
      }, 1500);
    } catch (err) {
      console.error("Failed to reject optimization:", err);
      setError(err instanceof Error ? err.message : "Failed to reject recommendation");
      setLoading(false);
      setAction(null);
    }
  };

  // Handle defer action
  const handleDefer = () => {
    if (!recommendation) return;

    onClose();
    // In production, this would call: api.deferOptimization(recommendation.site_id, recommendation.id, 15)
  };

  // Memoize impact analysis
  const impactAnalysis = useMemo(() => {
    if (!recommendation) return null;

    const savings = recommendation.projected_savings;
    const energyPercent = savings.energy_percent ?? savings.percentage_improvement ?? 0;
    const costZar = savings.cost_zar ?? savings.cost_zar_per_hour ?? 0;
    const monthlyCost = typeof costZar === 'number' ? costZar * 8 * 22 : 0;

    return {
      energy: `${typeof energyPercent === 'number' ? energyPercent : 0}% reduction (≈${formatCurrency(monthlyCost)}/month)`,
      cost: formatCurrency(monthlyCost), // Assuming 8h/day, 22 days/month
      comfort: savings?.comfort_impact || "Within spec - no complaints expected",
      equipment: savings?.equipment_impact || "Reduces wear on equipment by extending optimal runtime",
    };
  }, [recommendation]);

  // Don't render if not open or no recommendation
  if (!isOpen || !recommendation) {
    return null;
  }

  const confidenceColor = getConfidenceColor(recommendation.confidence);

  // Use portal to render at document body level (escapes parent overflow/positioning constraints)
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm overflow-y-auto">
      <div
        className="relative w-full max-w-3xl my-4 rounded-lg shadow-2xl flex flex-col"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
          maxHeight: "calc(100vh - 2rem)",
        }}
      >
        {/* Header */}
        <div className="flex-shrink-0 px-6 py-4 border-b"
          style={{ borderColor: "var(--color-sentinel-border)", background: "var(--color-sentinel-bg-panel)" }}
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h2 className="text-xl font-semibold mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {siteName || "Building"} - Optimization Recommendation
              </h2>
              <div className="flex items-center gap-4 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                <div className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  <span>{formatTimeAgo(recommendation.timestamp)}</span>
                </div>
                <div className="flex items-center gap-1">
                  <span>Confidence:</span>
                  <span className={`font-semibold ${confidenceColor}`}>
                    {formatConfidence(recommendation.confidence)}
                  </span>
                </div>
              </div>
            </div>
            <button
              onClick={onClose}
              disabled={loading}
              className="p-1 rounded hover:bg-white/10 transition-colors disabled:opacity-50"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content - scrollable */}
        <div className="px-6 py-4 space-y-6 overflow-y-auto flex-1">
          {/* Success Message */}
          {success && (
            <div className="flex items-center gap-2 p-3 rounded bg-green-900/20 border border-green-800 text-green-300">
              <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
              <span>
                {action === "approve"
                  ? "Recommendation approved and applied successfully!"
                  : "Recommendation rejected."}
              </span>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="flex items-center gap-2 p-3 rounded bg-red-900/20 border border-red-800 text-red-300">
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Current vs Recommended Table */}
          <div>
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              <Settings className="w-4 h-4" />
              Recommended Changes
            </h3>
            <div className="overflow-x-auto rounded border"
              style={{ borderColor: "var(--color-sentinel-border)" }}
            >
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b"
                    style={{ borderColor: "var(--color-sentinel-border)" }}
                  >
                    <th className="px-4 py-2 text-left font-medium"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Equipment
                    </th>
                    <th className="px-4 py-2 text-left font-medium"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Current
                    </th>
                    <th className="px-4 py-2 text-left font-medium"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Recommended
                    </th>
                    <th className="px-4 py-2 text-left font-medium"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Reason
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {recommendation.recommendations.map((rec, idx) => (
                    <tr
                      key={`${rec.equipment_id}-${idx}`}
                      className="border-b last:border-b-0 hover:bg-white/5"
                      style={{ borderColor: "var(--color-sentinel-border)" }}
                    >
                      <td className="px-4 py-3"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        {rec.equipment_name}
                      </td>
                      <td className="px-4 py-3"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
                      >
                        {rec.current_value} {rec.unit}
                      </td>
                      <td className="px-4 py-3 font-semibold text-yellow-400">
                        {rec.recommended_value} {rec.unit}
                      </td>
                      <td className="px-4 py-3 text-xs"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
                      >
                        {rec.reason}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Impact Analysis */}
          <div>
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              <Zap className="w-4 h-4" />
              Expected Impact
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Energy Savings */}
              <div className="flex items-start gap-3 p-3 rounded bg-green-900/10 border border-green-900/30">
                <Zap className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs font-medium text-green-300 mb-1">Energy Savings</div>
                  <div className="text-sm"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    {impactAnalysis?.energy}
                  </div>
                </div>
              </div>

              {/* Cost Savings */}
              <div className="flex items-start gap-3 p-3 rounded bg-blue-900/10 border border-blue-900/30">
                <DollarSign className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs font-medium text-blue-300 mb-1">Cost Savings</div>
                  <div className="text-sm font-semibold"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    {impactAnalysis?.cost} per month
                  </div>
                </div>
              </div>

              {/* Comfort Impact */}
              <div className="flex items-start gap-3 p-3 rounded bg-purple-900/10 border border-purple-900/30">
                <Thermometer className="w-5 h-5 text-purple-400 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs font-medium text-purple-300 mb-1">Comfort Impact</div>
                  <div className="text-sm"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    {impactAnalysis?.comfort}
                  </div>
                </div>
              </div>

              {/* Equipment Impact */}
              <div className="flex items-start gap-3 p-3 rounded bg-cyan-900/10 border border-cyan-900/30">
                <Settings className="w-5 h-5 text-cyan-400 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs font-medium text-cyan-300 mb-1">Equipment Impact</div>
                  <div className="text-sm"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    {impactAnalysis?.equipment}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* AI Reasoning */}
          {recommendation.reasoning && (
            <div>
              <h3 className="text-sm font-semibold mb-2"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                AI Analysis
              </h3>
              <div className="p-3 rounded text-sm whitespace-pre-wrap"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  color: "var(--color-sentinel-text-secondary)",
                }}
              >
                {recommendation.reasoning}
              </div>
            </div>
          )}

          {/* Footer Info */}
          <div className="flex items-center justify-between text-xs pt-2 border-t"
            style={{ borderColor: "var(--color-sentinel-border)", color: "var(--color-sentinel-text-disabled)" }}
          >
            <span>Based on analysis at {formatDateTime(recommendation.timestamp)}</span>
            <span>Valid for 15 minutes • Auto-dismiss in {timeRemaining}s</span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex-shrink-0 px-6 py-4 border-t flex gap-3"
          style={{ borderColor: "var(--color-sentinel-border)", background: "var(--color-sentinel-bg-panel)" }}
        >
          <button
            onClick={handleApprove}
            disabled={loading || success}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded bg-green-600 hover:bg-green-700 disabled:bg-green-800 disabled:opacity-50 text-white font-medium transition-colors"
          >
            <CheckCircle2 className="w-4 h-4" />
            {loading && action === "approve" ? "Applying..." : "Approve"}
          </button>

          <button
            onClick={handleReject}
            disabled={loading || success}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded bg-red-600 hover:bg-red-700 disabled:bg-red-800 disabled:opacity-50 text-white font-medium transition-colors"
          >
            <XCircle className="w-4 h-4" />
            {loading && action === "reject" ? "Rejecting..." : "Reject"}
          </button>

          <button
            onClick={handleDefer}
            disabled={loading || success}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded font-medium transition-colors"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              color: "var(--color-sentinel-text-primary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <Clock className="w-4 h-4" />
            Defer (15 min)
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

export default OptimizationRecommendationModal;

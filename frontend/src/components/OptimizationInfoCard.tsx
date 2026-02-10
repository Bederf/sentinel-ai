/**
 * Optimization Info Card Component - AI optimization status for building detail page
 *
 * Features:
 * - Large, prominent optimization status display
 * - Enable/disable toggle
 * - Last optimization timestamp
 * - Current recommendation preview
 * - Quick action buttons
 * - SENTINEL dark theme styling
 */

import { useState, useEffect } from "react";
import {
  Brain,
  TrendingUp,
  CheckCircle,
  Clock,
  Lightbulb,
  Zap,
} from "lucide-react";
import { OptimizationToggle } from "./OptimizationToggle";
import { OptimizationRecommendationModal } from "./OptimizationRecommendationModal";
import { formatRelativeTime } from "../lib/timeFormat";
import api from '@/lib/api';
import type {
  OptimizationStatusResponse,
  OptimizationRecommendation,
  MonthlySavingsSummary,
} from '@/lib/api';

type OptimizationStatusType = OptimizationStatusResponse['optimization_status'];

interface OptimizationInfoCardProps {
  siteId: string;
  optimizationEnabled: boolean;
}

export function OptimizationInfoCard({
  siteId,
  optimizationEnabled,
}: OptimizationInfoCardProps) {
  const [optimizationStatus, setOptimizationStatus] =
    useState<OptimizationStatusType>("unknown");
  const [lastOptimization, setLastOptimization] = useState<string | null>(null);
  const [currentRecommendation, setCurrentRecommendation] =
    useState<OptimizationRecommendation | null>(null);
  const [monthlySavings, setMonthlySavings] = useState<MonthlySavingsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [showRecommendationModal, setShowRecommendationModal] = useState(false);

  // Derive mode from toggle: ON = automatic, OFF = supervised
  const isAutomatic = optimizationEnabled;

  // Always fetch optimization status (both modes run optimization)
  useEffect(() => {
    console.log("[OptimizationInfoCard] Component mounted", { siteId, optimizationEnabled });

    const fetchStatus = async () => {
      try {
        console.log("[OptimizationInfoCard] Fetching status for", siteId);
        const status = await api.getOptimizationStatus(siteId);
        console.log("[OptimizationInfoCard] Status response:", status);
        setOptimizationStatus(status.optimization_status);
        setLastOptimization(status.last_optimization);
        setCurrentRecommendation(status.last_recommendation);
        setMonthlySavings(status.monthly_savings || null);
      } catch (error) {
        console.error("[OptimizationInfoCard] Failed to fetch optimization status:", error);
        setOptimizationStatus("error");
      } finally {
        setLoading(false);
      }
    };

    fetchStatus();
    // Refresh every 30 seconds
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, [siteId, optimizationEnabled]);

  if (loading) {
    return (
      <div
        className="rounded-md p-6"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="flex items-center justify-center py-8">
          <div
            className="animate-spin h-6 w-6 border-3 rounded-full mr-3"
            style={{
              borderColor: "var(--color-sentinel-blue)",
              borderTopColor: "transparent",
            }}
          />
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Loading optimization status...
          </span>
        </div>
      </div>
    );
  }


  // Handle approve recommendation
  const handleApproveRecommendation = async (_recommendationId: string) => {
    try {
      // Build setpoints array from recommendation
      // Note: recommendation uses device_id and point_name fields
      console.log("[OptimizationInfoCard] Current recommendation:", currentRecommendation);
      const setpointsToApply = currentRecommendation?.recommendations.map((rec) => ({
        device_id: (rec as any).device_id || (rec as any).equipment_id,
        point_name: (rec as any).point_name || "setpoint",
        value: rec.recommended_value,
      })) || [];

      console.log("[OptimizationInfoCard] Setpoints to apply:", setpointsToApply);

      if (setpointsToApply.length === 0) {
        console.error("No recommendations found to approve");
        alert("No recommendations found to approve. Please ensure the recommendation has setpoints.");
        return;
      }

      const result = await api.approveOptimization(siteId, _recommendationId, setpointsToApply);

      console.log("[OptimizationInfoCard] Approval result:", result);

      // Show success message
      if (result.success) {
        // Optional: You could add a toast notification here
        console.log(`✅ Successfully applied ${result.results.filter((r: any) => r.success).length} of ${result.results.length} recommendations`);
      }

      // Refresh optimization status after approve
      const status = await api.getOptimizationStatus(siteId);
      setOptimizationStatus(status.optimization_status);
      setCurrentRecommendation(status.last_recommendation);

      setShowRecommendationModal(false);
    } catch (error) {
      console.error('Failed to approve recommendation:', error);
      throw error;
    }
  };

  // Handle reject recommendation
  const handleRejectRecommendation = async (_recommendationId: string, _reason?: string) => {
    try {
      // Refresh optimization status after reject
      const status = await api.getOptimizationStatus(siteId);
      setOptimizationStatus(status.optimization_status);
      setCurrentRecommendation(status.last_recommendation);

      setShowRecommendationModal(false);
    } catch (error) {
      console.error('Failed to reject recommendation:', error);
      throw error;
    }
  };

  return (
    <div
      className="rounded-md overflow-hidden"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      {/* Header */}
      <div
        className="p-4 border-b flex items-center justify-between"
        style={{ borderColor: "var(--color-sentinel-border)" }}
      >
        <div className="flex items-center gap-3">
          <Brain className="h-6 w-6" style={{ color: "var(--color-sentinel-purple)" }} />
          <div>
            <h3
              className="font-semibold text-lg"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              AI Optimization
            </h3>
            <p
              className="text-sm"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {isAutomatic
                ? "Auto-applying changes"
                : "Recommendations require approval"}
              {lastOptimization && ` \u00B7 Last: ${formatRelativeTime(lastOptimization)}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Automatic mode: show auto-applied indicator */}
          {isAutomatic && optimizationStatus === "optimized" && (
            <div
              className="p-2 rounded"
              style={{
                background: "rgba(16, 185, 129, 0.2)",
                border: "1px solid var(--color-sentinel-green)",
              }}
              title="AI auto-applied optimizations"
            >
              <Zap className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
            </div>
          )}
          {/* Supervised mode: show success checkmark when optimized (manually approved) */}
          {!isAutomatic && optimizationStatus === "optimized" && (
            <div
              className="p-2 rounded"
              style={{
                background: "rgba(16, 185, 129, 0.2)",
                border: "1px solid var(--color-sentinel-green)",
              }}
              title="Recommendation applied successfully"
            >
              <CheckCircle className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
            </div>
          )}
          {/* Supervised mode: show recommendation button when pending */}
          {!isAutomatic && currentRecommendation && (optimizationStatus === "recommendation_pending" || optimizationStatus === "warning") && (
            <button
              onClick={() => setShowRecommendationModal(true)}
              className="p-2 rounded transition-all hover:scale-110 animate-pulse"
              style={{
                background: "rgba(245, 158, 11, 0.2)",
                border: "1px solid var(--color-sentinel-amber)",
              }}
              title="View recommendation - approval required"
            >
              <Lightbulb className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
            </button>
          )}
          <OptimizationToggle siteId={siteId} enabled={optimizationEnabled} />
        </div>
      </div>

      {/* Stats Row */}
      <div className="p-4">
        <div className="grid grid-cols-2 gap-3">
          <div
            className="p-3 rounded-md"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div className="flex items-center gap-2 mb-1">
              <TrendingUp
                className="h-4 w-4"
                style={{ color: "var(--color-sentinel-green)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                This Month
              </span>
            </div>
            <div
              className="text-lg font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              R{monthlySavings?.monthly_savings_zar?.toLocaleString() || "0"}
            </div>
            <div
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Saved {monthlySavings?.applied_recommendations ? `(${monthlySavings.applied_recommendations} optimizations)` : ""}
            </div>
          </div>

          <div
            className="p-3 rounded-md"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div className="flex items-center gap-2 mb-1">
              <Clock
                className="h-4 w-4"
                style={{ color: isAutomatic ? "var(--color-sentinel-green)" : "var(--color-sentinel-blue)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Mode
              </span>
            </div>
            <div
              className="text-lg font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {isAutomatic ? "Automatic" : "Supervised"}
            </div>
            <div
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {isAutomatic ? "AI auto-applies" : "Human approval"}
            </div>
          </div>
        </div>

        {/* Pending Recommendation Preview - show projected savings */}
        {currentRecommendation && currentRecommendation.projected_savings && (
          <div
            className="mt-3 p-3 rounded-md"
            style={{
              background: "rgba(245, 158, 11, 0.1)",
              border: "1px solid var(--color-sentinel-amber)",
            }}
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Lightbulb
                    className="h-4 w-4"
                    style={{ color: "var(--color-sentinel-amber)" }}
                  />
                  <span
                    className="text-xs font-medium"
                    style={{ color: "var(--color-sentinel-amber)" }}
                  >
                    {isAutomatic ? "Next Optimization" : "Pending Approval"}
                  </span>
                </div>
                <div
                  className="text-sm"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  {currentRecommendation.recommendations?.length || 0} setpoint changes
                </div>
              </div>
              <div className="text-right">
                <div
                  className="text-lg font-semibold"
                  style={{ color: "var(--color-sentinel-green)" }}
                >
                  R{currentRecommendation.projected_savings.cost_zar_per_hour?.toFixed(0) || "0"}/hr
                </div>
                <div
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  projected savings
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Recommendation Modal - only in supervised mode */}
      {!isAutomatic && showRecommendationModal && currentRecommendation && (
        <OptimizationRecommendationModal
          isOpen={showRecommendationModal}
          onClose={() => setShowRecommendationModal(false)}
          recommendation={currentRecommendation}
          onApprove={handleApproveRecommendation}
          onReject={handleRejectRecommendation}
        />
      )}
    </div>
  );
}

export default OptimizationInfoCard;

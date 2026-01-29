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
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  Lightbulb,
} from "lucide-react";
import { OptimizationToggle } from "./OptimizationToggle";
import { OptimizationRecommendationModal } from "./OptimizationRecommendationModal";
import api from "../lib/api";
import type {
  OptimizationStatusResponse,
  OptimizationRecommendation,
} from "../lib/api";

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
  const [loading, setLoading] = useState(true);
  const [showRecommendationModal, setShowRecommendationModal] = useState(false);

  // Fetch optimization status
  useEffect(() => {
    console.log("[OptimizationInfoCard] Component mounted", { siteId, optimizationEnabled });

    if (!optimizationEnabled) {
      setOptimizationStatus("unknown");
      setLoading(false);
      return;
    }

    const fetchStatus = async () => {
      try {
        console.log("[OptimizationInfoCard] Fetching status for", siteId);
        const status = await api.getOptimizationStatus(siteId);
        console.log("[OptimizationInfoCard] Status response:", status);
        setOptimizationStatus(status.optimization_status);
        setLastOptimization(status.last_optimization);
        setCurrentRecommendation(status.last_recommendation);
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

  if (!optimizationEnabled) {
    return (
      <div
        className="rounded-md p-4"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Brain
              className="h-5 w-5"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            />
            <div>
              <h3
                className="font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                AI Optimization
              </h3>
              <p
                className="text-sm"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Enable AI-powered optimization for this building
              </p>
            </div>
          </div>
          <OptimizationToggle siteId={siteId} enabled={false} />
        </div>
      </div>
    );
  }

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

  // Debug: Always render something
  console.log("[OptimizationInfoCard] Rendering with status:", optimizationStatus);

  const getStatusConfig = (status: OptimizationStatusType) => {
    switch (status) {
      case "optimized":
        return {
          icon: <CheckCircle className="h-5 w-5" />,
          color: "var(--color-sentinel-green)",
          bgColor: "rgba(16, 185, 129, 0.15)",
          label: "Optimized",
          message: "Building is running at optimal settings",
        };
      case "recommendation_pending":
        return {
          icon: <Lightbulb className="h-5 w-5" />,
          color: "var(--color-sentinel-amber)",
          bgColor: "rgba(245, 158, 11, 0.15)",
          label: "Recommendation Available",
          message: "AI has suggestions to improve efficiency",
        };
      case "warning":
        return {
          icon: <AlertTriangle className="h-5 w-5" />,
          color: "var(--color-sentinel-amber)",
          bgColor: "rgba(245, 158, 11, 0.15)",
          label: "Review Needed",
          message: "Recommendation requires attention",
        };
      case "error":
        return {
          icon: <XCircle className="h-5 w-5" />,
          color: "var(--color-sentinel-red)",
          bgColor: "rgba(220, 38, 38, 0.15)",
          label: "Optimization Error",
          message: "Last optimization failed",
        };
      default:
        return {
          icon: <Clock className="h-5 w-5" />,
          color: "var(--color-sentinel-text-disabled)",
          bgColor: "rgba(142, 142, 142, 0.15)",
          label: "Analyzing...",
          message: "AI is analyzing building conditions",
        };
    }
  };

  // Status config for potential future use
  void getStatusConfig(optimizationStatus);

  const formatRelativeTime = (timestamp: string | null) => {
    if (!timestamp) return "Never";
    const now = new Date();
    const then = new Date(timestamp);
    const diffMs = now.getTime() - then.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);

    if (diffMins < 2) return "Just now";
    if (diffMins < 60) return `${diffMins} minutes ago`;
    if (diffHours < 24) return `${diffHours} hours ago`;
    return then.toLocaleDateString();
  };

  // Handle approve recommendation
  const handleApproveRecommendation = async (_recommendationId: string) => {
    try {
      // Build setpoints array from recommendation
      // Note: recommendation uses device_id and point_name fields
      console.log("[OptimizationInfoCard] Current recommendation:", currentRecommendation);
      const setpointsToApply = currentRecommendation?.recommendations.map((rec) => ({
        device_id: (rec as any).device_id,
        point_name: (rec as any).point_name || "setpoint",
        value: rec.recommended_value,
      })) || [];

      console.log("[OptimizationInfoCard] Setpoints to apply:", setpointsToApply);

      if (setpointsToApply.length === 0) {
        console.error("No recommendations found to approve");
        alert("No recommendations found to approve. Please ensure the recommendation has setpoints.");
        return;
      }

      await api.approveOptimization(siteId, _recommendationId, setpointsToApply);

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
              Last updated: {formatRelativeTime(lastOptimization)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {currentRecommendation && (
            <button
              onClick={() => setShowRecommendationModal(true)}
              className="p-2 rounded transition-all hover:scale-110 animate-pulse"
              style={{
                background: "rgba(245, 158, 11, 0.2)",
                border: "1px solid var(--color-sentinel-amber)",
              }}
              title="View recommendation"
            >
              <Lightbulb className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
            </button>
          )}
          <OptimizationToggle siteId={siteId} enabled={true} />
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
              R0
            </div>
            <div
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Saved
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
                style={{ color: "var(--color-sentinel-blue)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Analysis
              </span>
            </div>
            <div
              className="text-lg font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Every 15 min
            </div>
            <div
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Automatic
            </div>
          </div>
        </div>
      </div>

      {/* Recommendation Modal */}
      {showRecommendationModal && currentRecommendation && (
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

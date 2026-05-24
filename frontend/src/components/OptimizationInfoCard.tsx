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
import { fetchApi } from "@/lib/api/client";
import {
  Brain,
  TrendingUp,
  Clock,
  Lightbulb,
  Shield,
  Sliders,
} from "lucide-react";
import { OptimizationToggle } from "./OptimizationToggle";
import { OptimizationRecommendationModal } from "./OptimizationRecommendationModal";
import { formatRelativeTime } from "../lib/timeFormat";
import api, { type ROISummaryResponse } from '@/lib/api';
import type {
  OptimizationStatusResponse,
  OptimizationRecommendation,
  MonthlySavingsSummary,
} from '@/lib/api';

type OptimizationStatusType = OptimizationStatusResponse['optimization_status'];

interface OptimizationInfoCardProps {
  siteId: string;
  optimizationEnabled: boolean;
  onboardingPhase?: "shadow" | "advisory" | "supervised" | "auto";
}

export function OptimizationInfoCard({
  siteId,
  optimizationEnabled,
  onboardingPhase,
}: OptimizationInfoCardProps) {
  const [optimizationStatus, setOptimizationStatus] =
    useState<OptimizationStatusType>("unknown");
  const [lastOptimization, setLastOptimization] = useState<string | null>(null);
  const [currentRecommendation, setCurrentRecommendation] =
    useState<OptimizationRecommendation | null>(null);
  const [monthlySavings, setMonthlySavings] = useState<MonthlySavingsSummary | null>(null);
  const [roiData, setRoiData] = useState<ROISummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [showRecommendationModal, setShowRecommendationModal] = useState(false);
  const [mode, setMode] = useState("supervised");
  const [activeProfile, setActiveProfile] = useState<string>("balanced");
  const [sitePhase, setSitePhase] = useState<string>(onboardingPhase || "shadow_live");

  // Phase-aware mode label: onboarding_phase from settings page is the master
  const effectivePhase = sitePhase;
  const isAdvisory = effectivePhase === "shadow_live" || effectivePhase === "advisory";
  const isAutoMode = mode === "automatic" && effectivePhase === "automatic";

  // Sync mode with onboardingPhase prop when it changes
  useEffect(() => {
    if (onboardingPhase) {
      setSitePhase(onboardingPhase);
      // If phase is supervised, mode should be supervised too
      if (onboardingPhase === "supervised") {
        setMode("supervised");
      }
    }
  }, [onboardingPhase]);

  // Always fetch optimization status (both modes run optimization)
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        // Add timestamp to bypass cache
        const timestamp = Date.now();
        const status = await fetchApi<Record<string, unknown>>(`/api/optimization/status/${siteId}?_t=${timestamp}`);
        console.log('[OptimizationInfoCard] API Response:', {
          mode: status.optimization_settings?.mode,
          control_tier: status.optimization_settings?.control_tier,
          onboarding_phase: status.onboarding_phase,
          full_settings: status.optimization_settings
        });
        setOptimizationStatus(status.optimization_status);
        setLastOptimization(status.last_optimization);
        setCurrentRecommendation(status.last_recommendation);
        setMonthlySavings(status.monthly_savings || null);
        if (status.optimization_settings?.mode) {
          setMode(status.optimization_settings.mode);
        }
        if (status.onboarding_phase) {
          setSitePhase(status.onboarding_phase);
        }
        if (status.active_profile) {
          setActiveProfile(status.active_profile);
        }
      } catch (error) {
        console.error("[OptimizationInfoCard] Failed to fetch optimization status:", error);
        setOptimizationStatus("error");
      } finally {
        setLoading(false);
      }
    };

    const fetchROI = async () => {
      try {
        const roi = await api.getROISummary(siteId);
        setRoiData(roi);
      } catch (error) {
        console.error("[OptimizationInfoCard] Failed to fetch ROI summary:", error);
      }
    };

    fetchStatus();
    fetchROI();
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

  const profileLabels: Record<string, string> = {
    comfort: "Comfort First",
    cost_saving: "Cost Saving",
    asset_preservation: "Asset Preservation",
    balanced: "Balanced",
  };

  const statusLabels: Record<string, { label: string; color: string; bg: string }> = {
    learning: { label: "Learning", color: "var(--color-sentinel-amber)", bg: "rgba(245, 158, 11, 0.15)" },
    active: { label: "Active", color: "var(--color-sentinel-green)", bg: "rgba(16, 185, 129, 0.15)" },
    optimized: { label: "Optimized", color: "var(--color-sentinel-green)", bg: "rgba(16, 185, 129, 0.2)" },
    recommendation_pending: { label: "Pending", color: "var(--color-sentinel-amber)", bg: "rgba(245, 158, 11, 0.2)" },
    disabled: { label: "Disabled", color: "var(--color-sentinel-text-secondary)", bg: "var(--color-sentinel-bg-secondary)" },
    error: { label: "Error", color: "var(--color-sentinel-red)", bg: "rgba(239, 68, 68, 0.15)" },
    unknown: { label: "Unknown", color: "var(--color-sentinel-text-secondary)", bg: "var(--color-sentinel-bg-secondary)" },
    warning: { label: "Warning", color: "var(--color-sentinel-amber)", bg: "rgba(245, 158, 11, 0.15)" },
  };

  const st = statusLabels[optimizationStatus] || statusLabels.unknown;

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
            <div className="flex items-center gap-2 mt-0.5">
              {/* Policy badge */}
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium"
                style={{
                  background: effectivePhase === "automatic" ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
                  color: effectivePhase === "automatic" ? "var(--color-sentinel-green)" : "var(--color-sentinel-amber)",
                }}
              >
                <Shield className="h-3 w-3" />
                {effectivePhase.replace(/_/g, " ")}
              </span>
              {/* Status badge */}
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium"
                style={{ background: st.bg, color: st.color }}
              >
                {st.label}
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Pending recommendation button */}
          {currentRecommendation && optimizationStatus === "recommendation_pending" && (
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
          {isAutoMode && (
            <OptimizationToggle siteId={siteId} enabled={optimizationEnabled} />
          )}
        </div>
      </div>

      {/* Stats Row */}
      <div className="p-4">
        <div className="grid grid-cols-3 gap-3">
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
            {roiData && (roiData.verified_savings_zar > 0 || roiData.estimated_savings_zar > 0) ? (
              <>
                <div
                  className="text-lg font-semibold"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  R{roiData.verified_savings_zar.toLocaleString()}
                </div>
                <div
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  verified
                  {roiData.estimated_savings_zar > 0 && (
                    <span> · +R{roiData.estimated_savings_zar.toLocaleString()} estimated</span>
                  )}
                </div>
              </>
            ) : (
              <>
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
                  {monthlySavings?.applied_recommendations
                    ? `${monthlySavings.applied_recommendations} optimizations`
                    : effectivePhase === "shadow_live" || effectivePhase === "advisory"
                      ? "Advisory mode — pending phase promotion"
                      : "No optimizations yet"}
                </div>
              </>
            )}
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
                style={{ color: mode === "automatic" ? "var(--color-sentinel-green)" : "var(--color-sentinel-blue)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Control
              </span>
            </div>
            <div
              className="text-lg font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {isAdvisory ? "Advisory" : mode.charAt(0).toUpperCase() + mode.slice(1)}
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
              <Sliders
                className="h-4 w-4"
                style={{ color: "var(--color-sentinel-purple)" }}
              />
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Profile
              </span>
            </div>
            <div
              className="text-lg font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {profileLabels[activeProfile] || activeProfile}
            </div>
            <div
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {activeProfile === "comfort"
                ? "Prioritise comfort"
                : activeProfile === "cost_saving"
                  ? "Minimise energy spend"
                  : activeProfile === "asset_preservation"
                    ? "Protect equipment"
                    : "Balance cost & comfort"}
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
                    {isAdvisory ? "Advisory Recommendation" : "Pending Approval"}
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

      {/* Recommendation Modal — readOnly in advisory modes */}
      {showRecommendationModal && currentRecommendation && (
        <OptimizationRecommendationModal
          isOpen={showRecommendationModal}
          onClose={() => setShowRecommendationModal(false)}
          recommendation={currentRecommendation}
          onApprove={isAdvisory ? undefined : handleApproveRecommendation}
          onReject={isAdvisory ? undefined : handleRejectRecommendation}
          readOnly={isAdvisory}
        />
      )}
    </div>
  );
}

export default OptimizationInfoCard;

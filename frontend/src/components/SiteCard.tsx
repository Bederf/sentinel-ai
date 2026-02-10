/**
 * SiteCard Component - SENTINEL site panel
 *
 * Displays:
 * - Site name with protection status indicator
 * - Location and type information
 * - Equipment count metric
 * - Risk alerts with severity coloring
 * - Safety status indicators (via useSiteSummary)
 * - Status-based left border accent
 *
 * Migrated to use batch hooks (Phase 75-04):
 * - useSiteSummary replaces per-device API calls
 * - Single aggregated query returns all site data
 * - Eliminates 30+ concurrent requests
 */

import { Building2, Cpu, AlertTriangle, MapPin, Shield, Clock } from "lucide-react";
import { useState } from "react";
import { useSiteSummary } from "@/hooks/useSiteSummary";
import { useQuery } from "@tanstack/react-query";
import api, { type Site, type OptimizationRecommendation, type BuildingEquipmentItem, createWorkOrder } from '@/lib/api';
import { OptimizationStatusBadge } from "./OptimizationStatusBadge";
import { OptimizationRecommendationModal } from "./OptimizationRecommendationModal";
import { ExpandableRiskList } from "./ExpandableRiskList";
import { RiskDetailModal } from "./RiskDetailModal";
import { getTimezoneAbbreviation, isDifferentTimezone } from "../lib/timeFormat";

interface SiteCardProps {
  site: Site;
  onClick?: (site: Site) => void;
  showSafetyStatus?: boolean;
  showOptimizationStatus?: boolean;
  onEquipmentControlNavigate?: (equipmentId: string, siteId: string) => void;
}

type SafetyStatus = 'safe' | 'warning' | 'blocked' | 'alarm' | 'unknown';

interface DeviceSafetySummary {
  total: number;
  safe: number;
  warning: number;
  blocked: number;
  alarm: number;
  overallStatus: SafetyStatus;
}

type OptimizationStatusType = "optimized" | "recommendation_pending" | "warning" | "error" | "unknown";

/**
 * Get status colors for SENTINEL theme
 */
function getStatusConfig(status: Site["status"]): {
  color: string;
  bg: string;
  border: string;
  label: string;
} {
  switch (status) {
    case "normal":
      return {
        color: "var(--color-sentinel-green)",
        bg: "rgba(16, 185, 129, 0.15)",
        border: "rgba(16, 185, 129, 0.5)",
        label: "Protected",
      };
    case "warning":
      return {
        color: "var(--color-sentinel-amber)",
        bg: "rgba(245, 158, 11, 0.15)",
        border: "rgba(245, 158, 11, 0.5)",
        label: "Elevated",
      };
    case "critical":
      return {
        color: "var(--color-sentinel-red)",
        bg: "rgba(220, 38, 38, 0.15)",
        border: "rgba(220, 38, 38, 0.5)",
        label: "Critical",
      };
    default:
      return {
        color: "var(--color-sentinel-text-secondary)",
        bg: "rgba(142, 142, 142, 0.15)",
        border: "rgba(142, 142, 142, 0.5)",
        label: "Unknown",
      };
  }
}

/**
 * Get color for safe percentage based on thresholds
 * Red: 0-49%, Amber: 50-79%, Green: 80-100%
 */
function getSafePercentageColor(safe: number, total: number): string {
  if (total === 0) return "var(--color-sentinel-text-disabled)";
  
  const percentage = (safe / total) * 100;
  
  if (percentage < 50) {
    return "var(--color-sentinel-red)"; // 0-49%
  } else if (percentage < 80) {
    return "var(--color-sentinel-amber)"; // 50-79%
  } else {
    return "var(--color-sentinel-green)"; // 80-100%
  }
}

export function SiteCard({ site, onClick, showSafetyStatus = true, showOptimizationStatus = false, onEquipmentControlNavigate }: SiteCardProps) {
  const statusConfig = getStatusConfig(site.status);
  const hasAlerts = site.alert_count > 0;
  
  // Fetch aggregated site summary (replaces per-device API calls)
  const { data: siteSummary, isLoading: loadingSafety } = useSiteSummary(site.id, {
    enabled: showSafetyStatus,
  });

  const [optimizationStatus, setOptimizationStatus] = useState<OptimizationStatusType>("unknown");
  const [optimizationMode, setOptimizationMode] = useState<"automatic" | "supervised">("supervised");
  const [hasRecommendation, setHasRecommendation] = useState(false);
  const [showRecommendationModal, setShowRecommendationModal] = useState(false);
  const [currentRecommendation, setCurrentRecommendation] = useState<OptimizationRecommendation | null>(null);

  // Expandable risk list state
  const [riskListExpanded, setRiskListExpanded] = useState(false);
  const [selectedRiskEquipment, setSelectedRiskEquipment] = useState<BuildingEquipmentItem | null>(null);
  const [showRiskModal, setShowRiskModal] = useState(false);

  const handleClick = () => {
    if (onClick) {
      onClick(site);
    }
  };

  // Build safety summary from site summary response
  const safetySummary: DeviceSafetySummary | null = siteSummary ? {
    total: siteSummary.equipment_count,
    safe: siteSummary.safety.safe,
    warning: siteSummary.safety.warning,
    blocked: siteSummary.safety.blocked,
    alarm: siteSummary.safety.alarm,
    overallStatus: 
      siteSummary.safety.blocked > 0 ? 'blocked' :
      siteSummary.safety.alarm > 0 ? 'alarm' :
      siteSummary.safety.warning > 0 ? 'warning' :
      siteSummary.safety.safe > 0 ? 'safe' :
      'unknown'
  } : null;

  // Fetch optimization status for this site
  const { data: optimizationResponse } = useQuery({
    queryKey: ['optimization-status', site.id],
    queryFn: () => (site.optimization_enabled ? api.getOptimizationStatus(site.id) : Promise.resolve(null)),
    enabled: showOptimizationStatus && site.optimization_enabled,
    staleTime: 30 * 1000,
  });

  // Update optimization status when response changes
  if (optimizationResponse) {
    if (optimizationResponse.optimization_status !== optimizationStatus) {
      setOptimizationStatus(optimizationResponse.optimization_status);
    }
    const mode = optimizationResponse.optimization_settings?.mode || "supervised";
    if (mode !== optimizationMode) {
      setOptimizationMode(mode);
    }
    const hasRecs = !!(optimizationResponse.last_recommendation &&
                    optimizationResponse.last_recommendation.recommendations &&
                    optimizationResponse.last_recommendation.recommendations.length > 0);
    if (hasRecs !== hasRecommendation) {
      setHasRecommendation(hasRecs);
    }
  }

  // Handle optimization badge click - show modal if there's a recommendation to review
  const handleOptimizationClick = async (e: React.MouseEvent) => {
    e.stopPropagation();

    try {
      const status = await api.getOptimizationStatus(site.id);
      const hasRecs = !!(status.last_recommendation &&
                      status.last_recommendation.recommendations &&
                      status.last_recommendation.recommendations.length > 0);

      setHasRecommendation(hasRecs);

      if (hasRecs) {
        setCurrentRecommendation(status.last_recommendation);
        setShowRecommendationModal(true);
      }
    } catch (error) {
      console.error('Failed to refresh optimization status:', error);
      if (hasRecommendation) {
        setShowRecommendationModal(true);
      }
    }
  };

  // Handle approve recommendation
  const handleApproveRecommendation = async (recommendationId: string) => {
    try {
      const setpointsToApply = currentRecommendation?.recommendations.map((rec) => ({
        device_id: rec.equipment_id,
        point_name: rec.point_name || "setpoint",
        value: rec.recommended_value,
      })) || [];

      await api.approveOptimization(site.id, recommendationId, setpointsToApply);

      const status = await api.getOptimizationStatus(site.id);
      setOptimizationStatus(status.optimization_status);

      setShowRecommendationModal(false);
      setCurrentRecommendation(null);
    } catch (error) {
      console.error('Failed to approve recommendation:', error);
      throw error;
    }
  };

  // Handle reject recommendation
  const handleRejectRecommendation = async (_recommendationId: string, _reason?: string) => {
    try {
      const status = await api.getOptimizationStatus(site.id);
      setOptimizationStatus(status.optimization_status);

      setShowRecommendationModal(false);
      setCurrentRecommendation(null);
    } catch (error) {
      console.error('Failed to reject recommendation:', error);
      throw error;
    }
  };

  // Handle equipment click from risk list
  const handleEquipmentClick = (equipment: BuildingEquipmentItem) => {
    if (onEquipmentControlNavigate) {
      onEquipmentControlNavigate(equipment.id, site.id);
    }
  };

  // Handle status badge click from risk list
  const handleStatusBadgeClick = (equipment: BuildingEquipmentItem) => {
    setSelectedRiskEquipment(equipment);
    setShowRiskModal(true);
  };

  // Handle navigation to control from risk modal
  const handleNavigateToControl = (equipmentId: string) => {
    if (onEquipmentControlNavigate) {
      onEquipmentControlNavigate(equipmentId, site.id);
    }
  };

  // Handle work order creation from risk modal
  const handleCreateWorkOrder = async (equipmentId: string) => {
    const equipment = selectedRiskEquipment;
    if (!equipment) return;

    try {
      const workOrder = await createWorkOrder({
        site_id: site.id,
        equipment_id: equipment.id || equipmentId,
        fault_description: `${equipment.name} health at ${equipment.health}% - maintenance required`,
        diagnosis: `Equipment health below threshold. Status: ${equipment.status}`,
        priority: equipment.status === "critical" ? "high" : "medium",
      });

      alert(`Work Order ${workOrder.id} created for ${equipment.name}`);
    } catch (error) {
      console.error("Failed to create work order:", error);
      alert("Failed to create work order. Please try again.");
    }
  };

  return (
    <div
      className={`relative rounded-md overflow-hidden transition-all duration-150 glass-card ${onClick ? "cursor-pointer hover:brightness-110" : ""}`}
      onClick={handleClick}
    >
      {/* Left status accent bar */}
      <div
        className="absolute left-0 top-0 bottom-0 w-1"
        style={{ background: statusConfig.color }}
      />

      <div className="p-4 pl-5">
        {/* Header: Site Number, Name and Status */}
        <div className="flex items-start justify-between mb-2">
          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2">
              <Building2
                className="h-4 w-4"
                style={{ color: "var(--color-sentinel-blue)" }}
              />
              <span
                className="text-xs font-medium uppercase tracking-wide"
                style={{ color: "var(--color-sentinel-blue)" }}
              >
                {site.id}
              </span>
            </div>
            <span
              className="font-medium text-sm ml-6"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {site.name}
            </span>
          </div>
          <div className="flex flex-col items-end gap-1">
            {/* Status badge */}
            <div
              className="flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium"
              style={{
                background: statusConfig.bg,
                color: statusConfig.color,
              }}
            >
              <div
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: statusConfig.color }}
              />
              {statusConfig.label}
            </div>
            {/* Optimization badge (if enabled) */}
            {showOptimizationStatus && site.optimization_enabled && (
              <div
                className={hasRecommendation ? "cursor-pointer hover:opacity-80 transition-opacity" : ""}
                onClick={handleOptimizationClick}
                title={hasRecommendation ? "Click to view recommendation" : undefined}
              >
                <OptimizationStatusBadge
                  status={optimizationStatus}
                  mode={optimizationMode}
                  size="sm"
                  lastOptimization={site.last_optimization}
                  hasRecommendation={hasRecommendation}
                />
              </div>
            )}
          </div>
        </div>

        {/* Location */}
        <div className="flex items-center gap-1.5 mb-2">
          <MapPin
            className="h-3 w-3"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          />
          <span
            className="text-xs"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            {site.location}
          </span>
        </div>

        {/* Operating Hours */}
        {site.operating_hours && (
          <div className="flex items-center gap-1.5 mb-3">
            <Clock
              className="h-3 w-3"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            />
            <span
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {site.operating_hours.start} - {site.operating_hours.end}
              {isDifferentTimezone(site.timezone) && site.timezone && (
                <span
                  className="ml-1.5 px-1 py-0.5 rounded text-xs font-medium"
                  style={{
                    background: "rgba(59, 130, 246, 0.15)",
                    color: "var(--color-sentinel-blue)",
                  }}
                  title={`Building timezone: ${site.timezone}`}
                >
                  {getTimezoneAbbreviation(site.timezone)}
                </span>
              )}
            </span>
          </div>
        )}

        {/* Type badge */}
        <div
          className="inline-block px-2 py-0.5 rounded text-xs mb-3"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            color: "var(--color-sentinel-text-secondary)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {site.type}
        </div>

        {/* Stats Row */}
        <div
          className="flex items-center justify-between pt-3"
          style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
        >
          {/* Equipment Count */}
          <div
            className="flex items-center gap-2 group relative"
            title={
              site.equipment_breakdown
                ? `Equipment Breakdown:\n` +
                  `├─ ${site.equipment_breakdown.equipment} Legacy Equipment\n` +
                  `├─ ${site.equipment_breakdown.hvac_zones} HVAC Zones\n` +
                  `├─ ${site.equipment_breakdown.generators + site.equipment_breakdown.generator_groups + site.equipment_breakdown.diesel_tanks} Generator Plant\n` +
                  `├─ ${site.equipment_breakdown.energy_centre} Energy Centre\n` +
                  `└─ ${site.equipment_breakdown.dali_controllers} DALI Controllers`
                : `${site.equipment_count} Total Equipment`
            }
          >
            <Cpu
              className="h-4 w-4"
              style={{ color: "var(--color-sentinel-blue)" }}
            />
            <div>
              <div
                className="text-lg font-medium"
                style={{
                  color: "var(--color-sentinel-text-primary)",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {site.equipment_count}
              </div>
              <div
                className="text-xs flex items-center gap-1"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                Equipment
                {site.equipment_breakdown && (
                  <span
                    className="inline-block w-1 h-1 rounded-full"
                    style={{ background: "var(--color-sentinel-blue)" }}
                    title="Detailed breakdown available"
                  />
                )}
              </div>
            </div>
          </div>

          {/* Safety Status */}
          {showSafetyStatus && (
            <div className="flex items-center gap-2">
              <Shield
                className="h-4 w-4"
                style={{
                  color: safetySummary
                    ? getSafePercentageColor(safetySummary.safe, safetySummary.total)
                    : getSafePercentageColor(
                        Math.max(0, (site.equipment_count || 0) - (site.alert_count || 0)),
                        site.equipment_count || 0
                      ),
                }}
              />
              <div className="text-right">
                {loadingSafety ? (
                  <div
                    className="text-lg font-medium"
                    style={{
                      color: "var(--color-sentinel-text-disabled)",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    ...
                  </div>
                ) : safetySummary ? (
                  <>
                    <div
                      className="text-lg font-medium"
                      style={{
                        color: getSafePercentageColor(safetySummary.safe, safetySummary.total),
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {safetySummary.safe}/{site.equipment_count}
                    </div>
                    <div
                      className="text-xs"
                      style={{ color: "var(--color-sentinel-text-disabled)" }}
                    >
                      Safe
                    </div>
                  </>
                ) : (
                  <>
                    <div
                      className="text-lg font-medium"
                      style={{
                        color: getSafePercentageColor(
                          Math.max(0, (site.equipment_count || 0) - (site.alert_count || 0)),
                          site.equipment_count || 0
                        ),
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {Math.max(0, (site.equipment_count || 0) - (site.alert_count || 0))}/{site.equipment_count || 0}
                    </div>
                    <div
                      className="text-xs"
                      style={{ color: "var(--color-sentinel-text-disabled)" }}
                    >
                      Safe
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Risk Alert Count - Show warning + alarm equipment from summary */}
          {showSafetyStatus && safetySummary ? (
            <div className="flex items-center gap-2">
              <AlertTriangle
                className="h-4 w-4"
                style={{
                  color: (safetySummary.warning + safetySummary.alarm) > 0
                    ? "var(--color-sentinel-amber)"
                    : "var(--color-sentinel-text-disabled)",
                }}
              />
              <div className="text-right">
                <div
                  className="text-lg font-medium"
                  style={{
                    color: (safetySummary.warning + safetySummary.alarm) > 0
                      ? "var(--color-sentinel-amber)"
                      : "var(--color-sentinel-text-primary)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {safetySummary.warning + safetySummary.alarm}
                </div>
                <div
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  Risks
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <AlertTriangle
                className="h-4 w-4"
                style={{
                  color: hasAlerts
                    ? "var(--color-sentinel-amber)"
                    : "var(--color-sentinel-text-disabled)",
                }}
              />
              <div className="text-right">
                <div
                  className="text-lg font-medium"
                  style={{
                    color: hasAlerts
                      ? "var(--color-sentinel-amber)"
                      : "var(--color-sentinel-text-primary)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {site.alert_count}
                </div>
                <div
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  Risks
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Expandable Risk List */}
      {hasAlerts && (
        <ExpandableRiskList
          siteId={site.id}
          expanded={riskListExpanded}
          onToggle={() => setRiskListExpanded(!riskListExpanded)}
          onEquipmentClick={handleEquipmentClick}
          onStatusBadgeClick={handleStatusBadgeClick}
        />
      )}

      {/* Recommendation Modal */}
      {showRecommendationModal && currentRecommendation && (
        <OptimizationRecommendationModal
          isOpen={showRecommendationModal}
          onClose={() => {
            setShowRecommendationModal(false);
            setCurrentRecommendation(null);
          }}
          recommendation={currentRecommendation}
          onApprove={handleApproveRecommendation}
          onReject={handleRejectRecommendation}
          siteName={site.name}
        />
      )}

      {/* Risk Detail Modal */}
      {showRiskModal && selectedRiskEquipment && (
        <RiskDetailModal
          isOpen={showRiskModal}
          onClose={() => {
            setShowRiskModal(false);
            setSelectedRiskEquipment(null);
          }}
          equipment={selectedRiskEquipment}
          onNavigateToControl={handleNavigateToControl}
          onCreateWorkOrder={handleCreateWorkOrder}
        />
      )}
    </div>
  );
}

export default SiteCard;

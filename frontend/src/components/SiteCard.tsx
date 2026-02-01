/**
 * SiteCard Component - SENTINEL site panel
 *
 * Displays:
 * - Site name with protection status indicator
 * - Location and type information
 * - Equipment count metric
 * - Risk alerts with severity coloring
 * - Safety status indicators
 * - Status-based left border accent
 *
 * Follows SENTINEL dark theme design.
 */

import { Building2, Cpu, AlertTriangle, MapPin, Shield, Clock } from "lucide-react";
import { useState, useEffect } from "react";
import api, { type Site, type OptimizationRecommendation, type BuildingEquipmentItem } from "../lib/api";
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
  const [safetySummary, setSafetySummary] = useState<DeviceSafetySummary | null>(null);
  const [loadingSafety, setLoadingSafety] = useState(false);
  const [optimizationStatus, setOptimizationStatus] = useState<OptimizationStatusType>("unknown");
  const [hasRecommendation, setHasRecommendation] = useState(false);
  const [showRecommendationModal, setShowRecommendationModal] = useState(false);
  const [currentRecommendation, setCurrentRecommendation] = useState<OptimizationRecommendation | null>(null);
  const [, setLoadingRecommendation] = useState(false);

  // Expandable risk list state
  const [riskListExpanded, setRiskListExpanded] = useState(false);
  const [selectedRiskEquipment, setSelectedRiskEquipment] = useState<BuildingEquipmentItem | null>(null);
  const [showRiskModal, setShowRiskModal] = useState(false);

  const handleClick = () => {
    if (onClick) {
      onClick(site);
    }
  };

  // Fetch safety status for devices at this site
  useEffect(() => {
    if (!showSafetyStatus) return;

    const fetchSafetyStatus = async () => {
      setLoadingSafety(true);
      try {
        // Get devices for this site
        const devices = await api.getSiteDevices(site.id);

        // If no devices from API, use equipment_count from site as fallback
        if (devices.length === 0) {
          const totalAssets = site.equipment_count || 0;
          const alertCount = site.alert_count || 0;
          // Calculate safe assets as total - alert_count
          // This gives us a reasonable estimate when device API returns no results
          setSafetySummary({
            total: totalAssets,
            safe: Math.max(0, totalAssets - alertCount),
            warning: 0,
            blocked: 0,
            alarm: alertCount,
            overallStatus: alertCount > 0 ? 'alarm' : 'safe',
          });
          return;
        }

        // Fetch safety status for all devices
        // For performance, we'll check all devices but limit concurrent requests
        const BATCH_SIZE = 10;
        const allStatuses: SafetyStatus[] = [];
        
        for (let i = 0; i < devices.length; i += BATCH_SIZE) {
          const batch = devices.slice(i, i + BATCH_SIZE);
          const batchPromises = batch.map(async (device) => {
            try {
              const status = await api.getDeviceSafetyStatus(device.id);
              return status.overall_status;
            } catch {
              return 'unknown' as SafetyStatus;
            }
          });
          const batchStatuses = await Promise.all(batchPromises);
          allStatuses.push(...batchStatuses);
        }

        // Use site.equipment_count as the total, not devices.length
        // This ensures consistency with the displayed total
        const totalEquipment = site.equipment_count || devices.length;
        
        // Calculate safe count based on equipment_count - alert_count
        // This gives accurate totals that match the displayed equipment_count
        const alertCount = site.alert_count || 0;
        const safeCount = Math.max(0, totalEquipment - alertCount);
        
        // Use device statuses to determine overall status, but use equipment_count for totals
        const summary: DeviceSafetySummary = {
          total: totalEquipment,
          safe: safeCount,
          warning: allStatuses.filter((s) => s === 'warning').length,
          blocked: allStatuses.filter((s) => s === 'blocked').length,
          alarm: alertCount > 0 ? alertCount : allStatuses.filter((s) => s === 'alarm').length,
          overallStatus: 'unknown',
        };

        // Determine overall status
        if (summary.blocked > 0) {
          summary.overallStatus = 'blocked';
        } else if (summary.alarm > 0) {
          summary.overallStatus = 'alarm';
        } else if (summary.warning > 0) {
          summary.overallStatus = 'warning';
        } else if (summary.safe > 0) {
          summary.overallStatus = 'safe';
        }

        setSafetySummary(summary);
      } catch (error) {
        console.error('Failed to fetch safety status:', error);
        // Fallback to equipment_count if API fails
        const totalAssets = site.equipment_count || 0;
        const alertCount = site.alert_count || 0;
        setSafetySummary({
          total: totalAssets,
          safe: Math.max(0, totalAssets - alertCount),
          warning: 0,
          blocked: 0,
          alarm: alertCount,
          overallStatus: alertCount > 0 ? 'alarm' : 'safe',
        });
      } finally {
        setLoadingSafety(false);
      }
    };

    fetchSafetyStatus();
  }, [site.id, showSafetyStatus]);

  // Fetch optimization status for this site
  useEffect(() => {
    if (!showOptimizationStatus || !site.optimization_enabled) return;

    const fetchOptimizationStatus = async () => {
      try {
        const status = await api.getOptimizationStatus(site.id);
        setOptimizationStatus(status.optimization_status);
        // Track if there's a recommendation available (for lightbulb icon)
        // Only show lightbulb if there are actual recommendations to review
        const hasRecs = !!(status.last_recommendation &&
                        status.last_recommendation.recommendations &&
                        status.last_recommendation.recommendations.length > 0);
        setHasRecommendation(hasRecs);
      } catch (error) {
        console.error('Failed to fetch optimization status:', error);
        setOptimizationStatus('error');
        setHasRecommendation(false);
      }
    };

    fetchOptimizationStatus();
    // Refresh every 30 seconds
    const interval = setInterval(fetchOptimizationStatus, 30000);
    return () => clearInterval(interval);
  }, [site.id, showOptimizationStatus, site.optimization_enabled]);

  // Fetch latest recommendation when modal opens
  useEffect(() => {
    if (!showRecommendationModal || !site.id) return;

    const fetchRecommendation = async () => {
      setLoadingRecommendation(true);
      try {
        // For demo purposes, we'll fetch the full status and extract the recommendation
        const status = await api.getOptimizationStatus(site.id);
        if (status.last_recommendation &&
            status.last_recommendation.recommendations &&
            status.last_recommendation.recommendations.length > 0) {
          setCurrentRecommendation(status.last_recommendation);
        } else {
          // If no pending recommendation or empty recommendations, close modal
          setShowRecommendationModal(false);
          setCurrentRecommendation(null);
        }
      } catch (error) {
        console.error('Failed to fetch recommendation:', error);
        setShowRecommendationModal(false);
        setCurrentRecommendation(null);
      } finally {
        setLoadingRecommendation(false);
      }
    };

    fetchRecommendation();
  }, [showRecommendationModal, site.id]);

  // Handle optimization badge click - show modal if there's a recommendation to review
  const handleOptimizationClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click from firing
    // Double-check there are actual recommendations before opening modal
    if (hasRecommendation && currentRecommendation &&
        currentRecommendation.recommendations &&
        currentRecommendation.recommendations.length > 0) {
      setShowRecommendationModal(true);
    }
  };

  // Handle approve recommendation
  const handleApproveRecommendation = async (recommendationId: string) => {
    try {
      // Build setpoints array from recommendation
      // Map equipment_id to device_id for backend compatibility
      const setpointsToApply = currentRecommendation?.recommendations.map((rec) => ({
        device_id: rec.equipment_id,
        point_name: rec.point_name || "setpoint",
        value: rec.recommended_value,
      })) || [];

      await api.approveOptimization(site.id, recommendationId, setpointsToApply);

      // Refresh optimization status after approve
      const status = await api.getOptimizationStatus(site.id);
      setOptimizationStatus(status.optimization_status);

      // Close modal
      setShowRecommendationModal(false);
      setCurrentRecommendation(null);
    } catch (error) {
      console.error('Failed to approve recommendation:', error);
      throw error; // Re-throw to show error in modal
    }
  };

  // Handle reject recommendation
  const handleRejectRecommendation = async (_recommendationId: string, _reason?: string) => {
    try {
      // Note: reject API endpoint doesn't exist yet, so we'll just update status
      // In production, this would call: api.rejectOptimization(site.id, recommendationId, reason)

      // Refresh optimization status after reject
      const status = await api.getOptimizationStatus(site.id);
      setOptimizationStatus(status.optimization_status);

      // Close modal
      setShowRecommendationModal(false);
      setCurrentRecommendation(null);
    } catch (error) {
      console.error('Failed to reject recommendation:', error);
      throw error; // Re-throw to show error in modal
    }
  };

  // Handle equipment click from risk list - navigate to control
  const handleEquipmentClick = (equipment: BuildingEquipmentItem) => {
    if (onEquipmentControlNavigate) {
      onEquipmentControlNavigate(equipment.id, site.id);
    }
  };

  // Handle status badge click from risk list - show risk detail modal
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

  return (
    <div
      className={`relative rounded-md overflow-hidden transition-all duration-150 ${onClick ? "cursor-pointer hover:brightness-110" : ""}`}
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
      onClick={handleClick}
    >
      {/* Left status accent bar */}
      <div
        className="absolute left-0 top-0 bottom-0 w-1"
        style={{ background: statusConfig.color }}
      />

      <div className="p-4 pl-5">
        {/* Header: Name and Status */}
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <Building2
              className="h-4 w-4"
              style={{ color: "var(--color-sentinel-blue)" }}
            />
            <span
              className="font-medium text-sm"
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
          {/* Equipment Count with breakdown tooltip */}
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

          {/* Risk Alert Count */}
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
        </div>
      </div>

      {/* Expandable Risk List - only show if there are alerts */}
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
        />
      )}
    </div>
  );
}

export default SiteCard;

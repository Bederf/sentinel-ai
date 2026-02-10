/**
 * RiskDetailModal Component - Equipment risk detail view
 *
 * Shows detailed equipment risk information:
 * - Equipment header with status badge
 * - Large health score with color indicator
 * - Health factors breakdown with progress bars
 * - Equipment details (manufacturer, model, etc.)
 * - Recommended action badge
 * - Action buttons
 *
 * Follows SENTINEL dark theme design.
 */

import { createPortal } from "react-dom";
import {
  X,
  AlertTriangle,
  AlertCircle,
  Clock,
  Wrench,
  Activity,
  Calendar,
  Settings,
  ChevronRight,
  ClipboardList,
  FileText,
  Building2,
} from "lucide-react";
import { RecentActions } from "./RecentActions";
import type { BuildingEquipmentItem } from '@/lib/api';

interface RiskDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  equipment: BuildingEquipmentItem | null;
  onNavigateToControl?: (equipmentId: string) => void;
  onCreateWorkOrder?: (equipmentId: string) => void;
  onNavigateToSite?: (siteId: string) => void;
  showEquipmentLogs?: boolean;
}

/**
 * Get color for health score
 */
function getHealthColor(health: number): string {
  if (health >= 80) return "var(--color-sentinel-green)";
  if (health >= 60) return "var(--color-sentinel-amber)";
  return "var(--color-sentinel-red)";
}

/**
 * Get color for factor score
 */
function getFactorColor(score: number): string {
  if (score >= 80) return "var(--color-sentinel-green)";
  if (score >= 60) return "var(--color-sentinel-amber)";
  return "var(--color-sentinel-red)";
}

/**
 * Get recommended action based on status and health
 */
function getRecommendedAction(
  status: string,
  health: number
): { label: string; color: string; bgColor: string } {
  if (status === "critical" || health < 50) {
    return {
      label: "Immediate Action Required",
      color: "var(--color-sentinel-red)",
      bgColor: "rgba(220, 38, 38, 0.15)",
    };
  }
  if (status === "warning" || health < 70) {
    return {
      label: "Schedule Maintenance",
      color: "var(--color-sentinel-amber)",
      bgColor: "rgba(245, 158, 11, 0.15)",
    };
  }
  return {
    label: "Monitor",
    color: "var(--color-sentinel-green)",
    bgColor: "rgba(16, 185, 129, 0.15)",
  };
}

/**
 * Format equipment type for display
 */
function formatEquipmentType(type: string): string {
  const typeLabels: Record<string, string> = {
    luminaire_group: "LED Luminaires",
    dali_controller: "DALI Controller",
    daylight_sensor: "Daylight Sensor",
    occupancy_sensor: "Occupancy Sensor",
    bms_controller: "BMS Controller",
    bms_scada: "BMS SCADA",
    "lift-passenger": "Passenger Lift",
    generator_group: "Generator Group",
    diesel_tank: "Diesel Tank",
    cooling_tower: "Cooling Tower",
    split_unit: "Split Unit",
    hvac_zone: "HVAC Zone",
    mv_incomer: "MV Incomer",
    lv_switchboard: "LV Switchboard",
    power_meter: "Power Meter",
    pfc_bank: "PFC Bank",
    fire_panel: "Fire Panel",
    water_heater: "Water Heater",
  };
  return typeLabels[type] || type.toUpperCase();
}

/**
 * Format factor label for display
 */
function formatFactorLabel(key: string): string {
  const labels: Record<string, string> = {
    age: "Age Score",
    service: "Service Status",
    runtime: "Runtime Hours",
    fault_history: "Fault History",
  };
  return labels[key] || key.replace(/_/g, " ");
}

export function RiskDetailModal({
  isOpen,
  onClose,
  equipment,
  onNavigateToControl,
  onCreateWorkOrder,
  onNavigateToSite,
  showEquipmentLogs = true,
}: RiskDetailModalProps) {
  // Handle ESC key to close
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
    }
  };

  // Don't render if not open or no equipment
  if (!isOpen || !equipment) {
    return null;
  }

  const healthColor = getHealthColor(equipment.health);
  const recommendedAction = getRecommendedAction(
    equipment.status,
    equipment.health
  );

  // Generate demo health factors if not present
  const healthFactors = equipment.health_factors || {
    age: { score: Math.min(100, equipment.health + 10), value: "5 years" },
    service: {
      score: Math.max(0, equipment.health - 5),
      value: equipment.status === "critical" ? "45 days overdue" : "On schedule",
    },
    runtime: { score: equipment.health, value: "12,500 hours" },
    fault_history: {
      score: Math.max(0, equipment.health - 10),
      value:
        equipment.status === "critical"
          ? "12 faults this month"
          : "2 faults this month",
    },
  };

  // Use portal to render at document body level
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm overflow-y-auto"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      onKeyDown={handleKeyDown}
      tabIndex={-1}
    >
      <div
        className="relative w-full max-w-2xl my-4 glass-panel shadow-2xl flex flex-col"
        style={{
          maxHeight: "calc(100vh - 2rem)",
        }}
      >
        {/* Header */}
        <div
          className="flex-shrink-0 px-6 py-4 border-b"
          style={{ borderColor: "var(--color-sentinel-border)" }}
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                {equipment.status === "critical" ? (
                  <AlertCircle
                    className="h-5 w-5"
                    style={{ color: "var(--color-sentinel-red)" }}
                  />
                ) : (
                  <AlertTriangle
                    className="h-5 w-5"
                    style={{ color: "var(--color-sentinel-amber)" }}
                  />
                )}
                <h2
                  className="text-lg font-semibold"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  {equipment.name}
                </h2>
                <span
                  className="px-2 py-0.5 rounded text-xs font-medium uppercase"
                  style={{
                    background:
                      equipment.status === "critical"
                        ? "rgba(220, 38, 38, 0.15)"
                        : "rgba(245, 158, 11, 0.15)",
                    color:
                      equipment.status === "critical"
                        ? "var(--color-sentinel-red)"
                        : "var(--color-sentinel-amber)",
                  }}
                >
                  {equipment.status}
                </span>
              </div>
              <div
                className="text-sm"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {equipment.category} | {formatEquipmentType(equipment.type)} | {equipment.location}
              </div>
              <div
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                {equipment.building_name}
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-1 rounded hover:bg-white/10 transition-colors cursor-pointer"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content - scrollable */}
        <div className="px-6 py-4 space-y-5 overflow-y-auto flex-1">
          {/* Health Score Display */}
          <div
            className="p-4 rounded-lg text-center"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <div
              className="text-5xl font-bold mb-1"
              style={{ color: healthColor }}
            >
              {equipment.health}%
            </div>
            <div
              className="text-sm"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Equipment Health Score
            </div>
            {/* Health bar */}
            <div
              className="mt-3 h-2 rounded-full overflow-hidden"
              style={{ background: "var(--color-sentinel-border)" }}
            >
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${equipment.health}%`,
                  background: healthColor,
                }}
              />
            </div>
          </div>

          {/* Recommended Action Badge */}
          <div
            className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg"
            style={{
              background: recommendedAction.bgColor,
              border: `1px solid ${recommendedAction.color}40`,
            }}
          >
            <Activity className="h-4 w-4" style={{ color: recommendedAction.color }} />
            <span
              className="font-medium text-sm"
              style={{ color: recommendedAction.color }}
            >
              {recommendedAction.label}
            </span>
          </div>

          {/* Health Factors Breakdown */}
          <div>
            <h3
              className="text-sm font-semibold mb-3 flex items-center gap-2"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              <Settings className="w-4 h-4" />
              Health Factors
            </h3>
            <div className="space-y-3">
              {Object.entries(healthFactors).map(([key, factor]) => {
                if (!factor) return null;
                const factorColor = getFactorColor(factor.score);
                return (
                  <div key={key}>
                    <div className="flex items-center justify-between mb-1">
                      <span
                        className="text-sm"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
                      >
                        {formatFactorLabel(key)}
                      </span>
                      <div className="flex items-center gap-2">
                        <span
                          className="text-xs"
                          style={{ color: "var(--color-sentinel-text-disabled)" }}
                        >
                          {factor.value}
                        </span>
                        <span
                          className="text-sm font-medium"
                          style={{ color: factorColor }}
                        >
                          {factor.score}%
                        </span>
                      </div>
                    </div>
                    <div
                      className="h-1.5 rounded-full overflow-hidden"
                      style={{ background: "var(--color-sentinel-border)" }}
                    >
                      <div
                        className="h-full rounded-full transition-all duration-300"
                        style={{
                          width: `${factor.score}%`,
                          background: factorColor,
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Equipment Details */}
          <div>
            <h3
              className="text-sm font-semibold mb-3 flex items-center gap-2"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              <Wrench className="w-4 h-4" />
              Equipment Details
            </h3>
            <div
              className="space-y-2 text-sm"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {equipment.details?.manufacturer && (
                <div className="flex justify-between">
                  <span>Manufacturer</span>
                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {equipment.details.manufacturer}
                  </span>
                </div>
              )}
              {equipment.details?.model && (
                <div className="flex justify-between">
                  <span>Model</span>
                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {equipment.details.model}
                  </span>
                </div>
              )}
              {equipment.details?.last_service && (
                <div className="flex justify-between items-center">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    Last Service
                  </span>
                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {new Date(equipment.details.last_service).toLocaleDateString()}
                  </span>
                </div>
              )}
              {equipment.details?.install_date && (
                <div className="flex justify-between items-center">
                  <span className="flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    Install Date
                  </span>
                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {new Date(equipment.details.install_date).toLocaleDateString()}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span>Equipment ID</span>
                <span
                  className="font-mono text-xs"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  {equipment.id}
                </span>
              </div>
            </div>
          </div>

          {/* Recent Activity */}
          {showEquipmentLogs && (
            <div>
              <h3
                className="text-sm font-semibold mb-3 flex items-center gap-2"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                <FileText className="w-4 h-4" />
                Recent Activity
              </h3>
              <div
                className="rounded-lg overflow-hidden"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--color-sentinel-border)",
                }}
              >
                <RecentActions
                  deviceId={equipment.id}
                  limit={5}
                  autoRefresh={false}
                />
              </div>
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div
          className="flex-shrink-0 px-6 py-4 border-t flex gap-3"
          style={{ borderColor: "var(--color-sentinel-border)" }}
        >
          {onNavigateToControl && equipment.controllable && (
            <button
              onClick={() => {
                onNavigateToControl(equipment.id);
                onClose();
              }}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded font-medium transition-colors cursor-pointer hover:brightness-110"
              style={{
                background: "var(--color-sentinel-blue)",
                color: "white",
              }}
            >
              <Settings className="w-4 h-4" />
              Open Control Panel
              <ChevronRight className="w-4 h-4" />
            </button>
          )}

          {onCreateWorkOrder && (
            <button
              onClick={() => {
                onCreateWorkOrder(equipment.id);
                onClose();
              }}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded font-medium transition-colors cursor-pointer hover:brightness-110"
              style={{
                background: "var(--color-sentinel-amber)",
                color: "white",
              }}
            >
              <ClipboardList className="w-4 h-4" />
              Create Work Order
            </button>
          )}

          {onNavigateToSite && (
            <button
              onClick={() => {
                onNavigateToSite(equipment.site_id);
                onClose();
              }}
              className="flex items-center justify-center gap-2 px-4 py-2.5 rounded font-medium transition-colors cursor-pointer hover:brightness-110"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                color: "var(--color-sentinel-text-primary)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <Building2 className="w-4 h-4" />
              View Site
            </button>
          )}

          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded font-medium transition-colors cursor-pointer hover:brightness-110"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              color: "var(--color-sentinel-text-primary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

export default RiskDetailModal;

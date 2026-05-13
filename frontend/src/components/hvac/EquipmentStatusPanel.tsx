/**
 * EquipmentStatusPanel - HVAC equipment grid with health scores
 *
 * Features:
 * - Equipment cards by type (AHU, FCU, Chiller)
 * - Health score with breakdown
 * - Status indicators
 * - Service/maintenance info
 */

import { useState, useEffect, useRef } from "react";
import { Fan, Thermometer, Activity, AlertTriangle, CheckCircle, Clock, Wrench, ClipboardList } from "lucide-react";
import { hvacApi, type HVACEquipment } from "../../lib/hvacApi";

interface EquipmentStatusPanelProps {
  siteId?: string;
  compact?: boolean;
  onEquipmentSelect?: (equipment: HVACEquipment) => void;
}

export function EquipmentStatusPanel({ siteId, compact = false, onEquipmentSelect }: EquipmentStatusPanelProps) {
  const [equipment, setEquipment] = useState<HVACEquipment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    async function loadEquipment() {
      try {
        const response = await hvacApi.getEquipment(siteId);
        if (!mountedRef.current) return;
        setEquipment(response.equipment);
        setLoading(false);
      } catch (err) {
        if (!mountedRef.current) return;
        setError(err instanceof Error ? err.message : "Failed to load equipment");
        setLoading(false);
      }
    }

    loadEquipment();
    const interval = setInterval(loadEquipment, 30000);

    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [siteId]);

  function getHealthColor(score: number): "green" | "amber" | "red" {
    if (score >= 80) return "green";
    if (score >= 60) return "amber";
    return "red";
  }

  function getStatusIcon(status: string) {
    switch (status) {
      case "normal":
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case "warning":
        return <AlertTriangle className="w-4 h-4 text-amber-500" />;
      case "fault":
      case "off":
        return <AlertTriangle className="w-4 h-4 text-red-500" />;
      default:
        return <Activity className="w-4 h-4" style={{ color: "var(--color-sentinel-text-disabled)" }} />;
    }
  }

  function getEquipmentIcon(type: string) {
    switch (type) {
      case "ahu":
        return <Fan className="w-5 h-5" style={{ color: "var(--color-sentinel-blue)" }} />;
      case "fcu":
        return <Fan className="w-5 h-5" style={{ color: "var(--color-sentinel-green)" }} />;
      case "chiller":
        return <Thermometer className="w-5 h-5" style={{ color: "var(--color-sentinel-cyan)" }} />;
      case "cooling_tower":
        return <Activity className="w-5 h-5" style={{ color: "var(--color-sentinel-purple)" }} />;
      default:
        return <Activity className="w-5 h-5" style={{ color: "var(--color-sentinel-text-secondary)" }} />;
    }
  }

  function chipStyle(kind: "green" | "amber" | "red" | "gray") {
    switch (kind) {
      case "green":
        return {
          background: "rgba(34, 197, 94, 0.14)",
          color: "var(--color-sentinel-green)",
          border: "1px solid rgba(34, 197, 94, 0.30)",
        };
      case "amber":
        return {
          background: "rgba(245, 158, 11, 0.14)",
          color: "var(--color-sentinel-amber)",
          border: "1px solid rgba(245, 158, 11, 0.30)",
        };
      case "red":
        return {
          background: "rgba(239, 68, 68, 0.14)",
          color: "var(--color-sentinel-red)",
          border: "1px solid rgba(239, 68, 68, 0.30)",
        };
      default:
        return {
          background: "rgba(148, 163, 184, 0.14)",
          color: "var(--color-sentinel-text-secondary)",
          border: "1px solid rgba(148, 163, 184, 0.28)",
        };
    }
  }

  function isMeaningfulValue(value: unknown): boolean {
    if (value === null || value === undefined) return false;
    const normalized = String(value).trim().toLowerCase();
    return !["", "n/a", "na", "none", "null", "undefined", "unknown", "never", "-"].includes(normalized);
  }

  function formatDateOrNull(value: unknown): string | null {
    if (!isMeaningfulValue(value)) return null;
    const date = new Date(String(value));
    if (Number.isNaN(date.getTime())) return null;
    return date.toLocaleDateString();
  }

  if (loading) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Equipment Status</h3>
        <div className="animate-pulse space-y-4 mt-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-32 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }} />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Equipment Status</h3>
        <span className="text-red-500 mt-4">{error}</span>
      </div>
    );
  }

  // Group equipment by type
  const equipmentByType = equipment.reduce((acc, eq) => {
    const type = eq.type;
    if (!acc[type]) acc[type] = [];
    acc[type].push(eq);
    return acc;
  }, {} as Record<string, HVACEquipment[]>);

  const typeLabels: Record<string, string> = {
    ahu: "AHUs",
    fcu: "FCUs",
    chiller: "Chillers",
    cooling_tower: "Cooling Towers",
    vav: "VAV Boxes",
    pump: "Pumps",
    crac: "CRACs",
  };

  const types = Object.keys(equipmentByType);

  const EquipmentCard = ({ eq }: { eq: HVACEquipment }) => (
    <div
      className="rounded-md p-4 cursor-pointer hover:ring-2 hover:ring-blue-500/30 transition-all"
      style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
      onClick={() => onEquipmentSelect?.(eq)}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          {getEquipmentIcon(eq.type)}
          <div>
            <span className="font-medium">{eq.name}</span>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>{eq.location}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {getStatusIcon(eq.status)}
          <span
            className="text-xs px-2 py-0.5 rounded capitalize"
            style={chipStyle(eq.status === "normal" ? "green" : eq.status === "warning" ? "amber" : "red")}
          >
            {eq.status}
          </span>
        </div>
      </div>

      {/* Health Score */}
      <div
        className="p-3 rounded-lg mb-3"
        style={{ background: "var(--color-sentinel-bg-secondary)" }}
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm">Health Score</span>
          <span
            className="text-sm px-2.5 py-0.5 rounded font-medium"
            style={chipStyle(getHealthColor(eq.calculated_health ?? eq.health_score))}
          >
            {(() => { const h = eq.calculated_health ?? eq.health_score; return h != null ? h.toFixed(0) : "--"; })()}%
          </span>
        </div>

        {/* Health Factors Breakdown */}
        {!compact && eq.health_factors && (
          <div className="space-y-1">
            {Object.entries(eq.health_factors).map(([key, factor]) => (
              <div key={key} className="flex items-center justify-between text-xs">
                <span className="capitalize" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                  {key.replace("_", " ")}
                </span>
                <div className="flex items-center gap-2">
                  <div
                    className="w-16 h-1.5 rounded-full overflow-hidden"
                    style={{ background: "var(--color-sentinel-border)" }}
                  >
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${factor.score}%`,
                        background:
                          factor.score >= 80
                            ? "var(--color-sentinel-green)"
                            : factor.score >= 60
                            ? "var(--color-sentinel-amber)"
                            : "var(--color-sentinel-red)",
                      }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Equipment Info */}
      {!compact && (
        <div className="space-y-2 text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
          {isMeaningfulValue(eq.manufacturer) && (
            <div className="flex justify-between">
              <span>Manufacturer</span>
              <span style={{ color: "var(--color-sentinel-text-secondary)" }}>{eq.manufacturer}</span>
            </div>
          )}
          {isMeaningfulValue(eq.model) && (
            <div className="flex justify-between">
              <span>Model</span>
              <span style={{ color: "var(--color-sentinel-text-secondary)" }}>{eq.model}</span>
            </div>
          )}
          {isMeaningfulValue(eq.capacity) && (
            <div className="flex justify-between">
              <span>Capacity</span>
              <span style={{ color: "var(--color-sentinel-text-secondary)" }}>{eq.capacity}</span>
            </div>
          )}
          {formatDateOrNull(eq.last_service) && (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1">
                <Wrench className="w-3 h-3" />
                <span>Last Service</span>
              </div>
              <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {formatDateOrNull(eq.last_service)}
              </span>
            </div>
          )}
          {formatDateOrNull(eq.install_date) && (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                <span>Installed</span>
              </div>
              <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {formatDateOrNull(eq.install_date)}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Create Work Order button for warning/critical equipment */}
      {(eq.status === "warning" || eq.status === "fault") && (
        <button
          className="w-full mt-3 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors"
          style={{
            background: eq.status === "fault"
              ? "rgba(239, 68, 68, 0.15)"
              : "rgba(245, 158, 11, 0.15)",
            color: eq.status === "fault"
              ? "rgb(239, 68, 68)"
              : "rgb(245, 158, 11)",
            border: `1px solid ${eq.status === "fault" ? "rgba(239, 68, 68, 0.3)" : "rgba(245, 158, 11, 0.3)"}`,
          }}
          onClick={(e) => {
            e.stopPropagation();
            window.dispatchEvent(
              new CustomEvent("create-work-order", {
                detail: { equipmentCode: eq.name, equipmentId: eq.id, status: eq.status, healthScore: eq.health_score },
              })
            );
          }}
        >
          <ClipboardList className="w-3.5 h-3.5" />
          Create Work Order
        </button>
      )}
    </div>
  );

  if (compact) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="font-medium">Equipment</span>
          <span className="text-xs px-2 py-0.5 rounded" style={chipStyle("gray")}>
            {equipment.length} total
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {equipment.slice(0, 4).map((eq) => (
            <EquipmentCard key={eq.id} eq={eq} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Equipment Status</h3>
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>{equipment.length} HVAC equipment items</span>
        </div>
        <div className="flex gap-2">
          <span className="text-sm px-2.5 py-0.5 rounded" style={chipStyle("green")}>
            {equipment.filter((e) => e.health_status === "healthy").length} Healthy
          </span>
          <span className="text-sm px-2.5 py-0.5 rounded" style={chipStyle("amber")}>
            {equipment.filter((e) => e.health_status === "attention").length} Attention
          </span>
          <span className="text-sm px-2.5 py-0.5 rounded" style={chipStyle("red")}>
            {equipment.filter((e) => e.health_status === "critical").length} Critical
          </span>
        </div>
      </div>

      <div>
        <div className="flex gap-2 mb-4 overflow-x-auto">
          <button
            className={`px-3 py-1.5 text-sm rounded-md font-medium transition-colors whitespace-nowrap ${activeTab === 0 ? 'bg-blue-500/20 text-blue-400' : ''}`}
            style={{ color: activeTab === 0 ? undefined : "var(--color-sentinel-text-secondary)" }}
            onClick={() => setActiveTab(0)}
          >
            All
          </button>
          {types.map((type, idx) => (
            <button
              key={type}
              className={`px-3 py-1.5 text-sm rounded-md font-medium transition-colors whitespace-nowrap ${activeTab === idx + 1 ? 'bg-blue-500/20 text-blue-400' : ''}`}
              style={{ color: activeTab === idx + 1 ? undefined : "var(--color-sentinel-text-secondary)" }}
              onClick={() => setActiveTab(idx + 1)}
            >
              {typeLabels[type] || type.toUpperCase()} ({equipmentByType[type].length})
            </button>
          ))}
        </div>

        {activeTab === 0 ? (
          <div className="grid grid-cols-3 gap-4">
            {equipment.map((eq) => (
              <EquipmentCard key={eq.id} eq={eq} />
            ))}
          </div>
        ) : (
          types.map((type, idx) =>
            activeTab === idx + 1 ? (
              <div key={type} className="grid grid-cols-3 gap-4">
                {equipmentByType[type].map((eq) => (
                  <EquipmentCard key={eq.id} eq={eq} />
                ))}
              </div>
            ) : null
          )
        )}
      </div>
    </div>
  );
}

export default EquipmentStatusPanel;

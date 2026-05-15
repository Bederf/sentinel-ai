import { useState, useEffect, useRef } from "react";
import { Thermometer, AlertTriangle, Settings, Pencil } from "lucide-react";
import { hvacApi, type HVACZone } from "../../lib/hvacApi";
import TemperatureControl from "../TemperatureControl";

interface ZoneOverviewPanelProps {
  siteId?: string;
  compact?: boolean;
  onZoneSelect?: (zone: HVACZone) => void;
}

export function ZoneOverviewPanel({ siteId, compact = false, onZoneSelect }: ZoneOverviewPanelProps) {
  const [zones, setZones] = useState<HVACZone[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingZone, setEditingZone] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const loadZonesRef = useRef<() => Promise<void>>();

  useEffect(() => {
    mountedRef.current = true;

    async function loadZones() {
      try {
        const response = await hvacApi.getZones(siteId);
        if (!mountedRef.current) return;
        setZones(response.zones);
        setLoading(false);
      } catch (err) {
        if (!mountedRef.current) return;
        setError(err instanceof Error ? err.message : "Failed to load zones");
        setLoading(false);
      }
    }

    loadZonesRef.current = loadZones;
    loadZones();
    const interval = setInterval(loadZones, 30000);

    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [siteId]);

  async function handleSetpointChange(zoneId: string, newSetpoint: number) {
    try {
      await hvacApi.setZoneSetpoint(zoneId, newSetpoint);
      setEditingZone(null);
      loadZonesRef.current?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update setpoint");
    }
  }

  function getStatusColor(status: string): "green" | "amber" | "red" | "gray" {
    switch (status) {
      case "running":
        return "green";
      case "fault":
        return "red";
      case "offline":
        return "gray";
      default:
        return "amber";
    }
  }

  function getDeviationColor(deviation: number): string {
    const abs = Math.abs(deviation);
    if (abs <= 1) return "var(--color-sentinel-green)";
    if (abs <= 2) return "var(--color-sentinel-amber)";
    return "var(--color-sentinel-red)";
  }

  function getChipStyle(kind: "green" | "amber" | "red" | "gray") {
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

  if (loading) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Zone Overview</h3>
        <div className="animate-pulse space-y-4 mt-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }} />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Zone Overview</h3>
        <p className="text-red-500 mt-4">{error}</p>
        <button
          className="mt-2 text-xs px-3 py-1.5 rounded font-medium"
          style={{ background: "var(--color-sentinel-bg-secondary)", color: "var(--color-sentinel-text-primary)", border: "1px solid var(--color-sentinel-border)" }}
          onClick={() => { setError(null); loadZonesRef.current?.(); }}
        >
          Retry
        </button>
      </div>
    );
  }

  const zonesByFloor = zones.reduce((acc, zone) => {
    const floor = zone.floor || "Unknown";
    if (!acc[floor]) acc[floor] = [];
    acc[floor].push(zone);
    return acc;
  }, {} as Record<string, HVACZone[]>);

  return (
    <div className="space-y-4">
      {!compact && (
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Zone Overview</h3>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>{zones.length} zones configured</p>
          </div>
          <div className="flex gap-2">
            <span className="text-xs px-2 py-0.5 rounded capitalize" style={getChipStyle("green")}>
              {zones.filter(z => z.status === "running").length} Running
            </span>
            <span className="text-xs px-2 py-0.5 rounded capitalize" style={getChipStyle("red")}>
              {zones.filter(z => z.status === "fault").length} Fault
            </span>
          </div>
        </div>
      )}

      {Object.entries(zonesByFloor).map(([floor, floorZones]) => (
        <div key={floor}>
          {!compact && (
            <p className="font-medium text-sm mb-2" style={{ color: "var(--color-sentinel-text-disabled)" }}>Floor {floor}</p>
          )}
          <div className={`grid ${compact ? 'grid-cols-2' : 'grid-cols-3'} gap-3`}>
            {floorZones.map((zone) => (
              <div
                key={zone.zone_id}
                className="rounded-md p-3 cursor-pointer hover:ring-2 hover:ring-blue-500/30 transition-all"
                style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
                onClick={() => !editingZone && onZoneSelect?.(zone)}
              >
                <div className="flex items-start justify-between mb-2">
                  <span className="text-xs font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {zone.fcu_id || zone.ahu_id || zone.zone_name}
                  </span>
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded capitalize"
                    style={getChipStyle(getStatusColor(zone.status))}
                  >
                    {zone.status}
                  </span>
                </div>

                <div className="flex items-baseline gap-1 mb-2">
                  <span
                    className="text-2xl font-bold tabular-nums"
                    style={{ color: getDeviationColor(zone.temp_deviation ?? 0) }}
                  >
                    {zone.current_temp != null ? zone.current_temp.toFixed(1) : "--"}
                  </span>
                  <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>°C</span>
                </div>

                {editingZone === zone.zone_id ? (
                  <div onClick={(e) => e.stopPropagation()}>
                    <TemperatureControl
                      label="Setpoint"
                      unit="°C"
                      value={zone.setpoint}
                      min={zone.temp_min}
                      max={zone.temp_max}
                      step={0.5}
                      onChange={(value) => handleSetpointChange(zone.zone_id, value)}
                      disabled={zone.status === "offline"}
                    />
                    <button
                      onClick={() => setEditingZone(null)}
                      className="mt-2 text-xs px-2 py-1 rounded"
                      style={{ background: "var(--color-sentinel-bg-secondary)", color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div
                    className="flex items-center justify-between px-2 py-1 rounded"
                    style={{ background: "var(--color-sentinel-bg-secondary)" }}
                  >
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Thermometer className="w-3 h-3 shrink-0" style={{ color: "var(--color-sentinel-blue)" }} />
                      <span className="text-xs truncate" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {zone.setpoint}°C
                      </span>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); setEditingZone(zone.zone_id); }}
                      disabled={zone.status === "offline"}
                      className="p-1 rounded transition-colors shrink-0"
                      style={{ color: "var(--color-sentinel-text-disabled)" }}
                      title="Adjust setpoint"
                    >
                      <Pencil className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default ZoneOverviewPanel;

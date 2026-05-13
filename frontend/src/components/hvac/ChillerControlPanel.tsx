/**
 * ChillerControlPanel - Grid of chiller controls
 *
 * Features:
 * - Chiller status cards with toggle control
 * - CHW supply temperature setpoint adjustment
 * - Health score display
 * - Live temperature readings
 * - Safety rule awareness
 */

import { useState, useEffect, useRef } from "react";
import { Thermometer, Power, PowerOff, Activity, AlertTriangle, Clock, Droplets } from "lucide-react";
import { hvacApi, type Chiller } from "../../lib/hvacApi";
import { useHealthThresholds } from "../../hooks/useHealthThresholds";
import { LockedFeatureOverlay } from "../LockedFeatureOverlay";

interface ChillerControlPanelProps {
  siteId?: string;
  compact?: boolean;
  onChillerChange?: (chillerId: string, action: "on" | "off") => void;
}

// Setpoint limits
const SETPOINT_MIN = 5;
const SETPOINT_MAX = 12;

export function ChillerControlPanel({ siteId, compact = false, onChillerChange }: ChillerControlPanelProps) {
  const [chillers, setChillers] = useState<Chiller[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [controllingChiller, setControllingChiller] = useState<string | null>(null);
  const [adjustingSetpoint, setAdjustingSetpoint] = useState<string | null>(null);
  const [pendingSetpoints, setPendingSetpoints] = useState<Record<string, number>>({});
  const mountedRef = useRef(true);
  const loadChillersRef = useRef<() => Promise<void>>();
  const { thresholds } = useHealthThresholds();

  useEffect(() => {
    mountedRef.current = true;

    async function loadChillers() {
      try {
        const response = await hvacApi.getChillers(siteId);
        if (!mountedRef.current) return;
        setChillers(response.chillers);
        setLoading(false);
      } catch (err) {
        if (!mountedRef.current) return;
        setError(err instanceof Error ? err.message : "Failed to load chillers");
        setLoading(false);
      }
    }

    loadChillersRef.current = loadChillers;
    loadChillers();
    const interval = setInterval(loadChillers, 10000);

    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [siteId]);

  async function handleToggle(chillerId: string, currentlyRunning: boolean) {
    setControllingChiller(chillerId);
    const action = currentlyRunning ? "off" : "on";

    try {
      await hvacApi.controlChiller(chillerId, action);
      onChillerChange?.(chillerId, action);
      loadChillersRef.current?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to control chiller");
    } finally {
      setControllingChiller(null);
    }
  }

  async function handleSetpointChange(chillerId: string, newSetpoint: number) {
    setAdjustingSetpoint(chillerId);

    try {
      await hvacApi.setChillerSetpoint(chillerId, newSetpoint);
      // Clear pending setpoint after successful save
      setPendingSetpoints((prev) => {
        const updated = { ...prev };
        delete updated[chillerId];
        return updated;
      });
      loadChillersRef.current?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update setpoint");
    } finally {
      setAdjustingSetpoint(null);
    }
  }

  function handleSliderChange(chillerId: string, value: number) {
    setPendingSetpoints((prev) => ({ ...prev, [chillerId]: value }));
  }

  function getHealthColor(score: number): "green" | "amber" | "red" {
    if (score >= thresholds.healthy) return "green";
    if (score >= thresholds.warning) return "amber";
    return "red";
  }

  function getSetpointColor(current: number, setpoint: number): string {
    const diff = Math.abs(current - setpoint);
    if (diff <= 0.5) return "var(--color-sentinel-green)";
    if (diff <= 1.5) return "var(--color-sentinel-amber)";
    return "var(--color-sentinel-red)";
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

  if (loading) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Chiller Control</h3>
        <div className="animate-pulse space-y-4 mt-4">
          {[1, 2].map((i) => (
            <div key={i} className="h-40 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }} />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Chiller Control</h3>
        <p className="text-red-500 mt-4">{error}</p>
      </div>
    );
  }

  if (chillers.length === 0) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Chiller Control</h3>
        <p className="mt-4" style={{ color: "var(--color-sentinel-text-disabled)" }}>No chillers found</p>
      </div>
    );
  }

  const runningCount = chillers.filter((c) => c.is_running).length;

  return (
    <div className="space-y-4">
      {!compact && (
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Chiller Control</h3>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>{chillers.length} chillers configured</p>
          </div>
          <span
            className="text-sm px-2.5 py-0.5 rounded font-medium"
            style={chipStyle(runningCount > 0 ? "green" : "gray")}
          >
            {runningCount}/{chillers.length} Running
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {chillers.map((chiller) => {
          const isControlling = controllingChiller === chiller.id;
          const isAdjusting = adjustingSetpoint === chiller.id;
          const metadata = chiller.metadata || {};
          const currentSetpoint = pendingSetpoints[chiller.id] ?? metadata.chw_supply_setpoint ?? 7.0;
          const hasChanges = pendingSetpoints[chiller.id] !== undefined;

          return (
            <div
              key={chiller.id}
              className="rounded-md p-4 relative overflow-hidden"
              style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
            >
              {/* Status indicator line */}
              <div
                className="absolute top-0 left-0 right-0 h-1"
                style={{
                  background: chiller.is_running
                    ? "var(--color-sentinel-green)"
                    : "var(--color-sentinel-red)",
                }}
              />

              {/* Header */}
              <div className="flex items-start justify-between mb-4 mt-2">
                <div>
                  <div className="flex items-center gap-2">
                    <Thermometer
                      className="w-5 h-5"
                      style={{ color: "var(--color-sentinel-cyan)" }}
                    />
                    <span className="font-medium text-lg">{chiller.name}</span>
                  </div>
                  <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>{chiller.location}</span>
                </div>
                <span
                  className="text-sm px-2.5 py-0.5 rounded font-medium"
                  style={chipStyle(getHealthColor(chiller.calculated_health ?? chiller.health_score))}
                >
                  Health: {(() => { const h = chiller.calculated_health ?? chiller.health_score; return h != null ? h.toFixed(0) : "--"; })()}%
                </span>
              </div>

              {/* Status and Control - Gated by Controls Module */}
              <LockedFeatureOverlay
                module="control"
                featureName={`${chiller.name} Toggle`}
                customMessage={`Enable Controls module to let SENTINEL automatically manage chiller operations and reduce cycling losses by 10-15%.`}
              >
                <div
                  className="p-4 rounded-lg mb-4"
                  style={{ background: "var(--color-sentinel-bg-secondary)" }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {chiller.is_running ? (
                        <Power
                          className="w-6 h-6"
                          style={{ color: "var(--color-sentinel-green)" }}
                        />
                      ) : (
                        <PowerOff
                          className="w-6 h-6"
                          style={{ color: "var(--color-sentinel-red)" }}
                        />
                      )}
                      <div>
                        <span className="font-medium">
                          {chiller.is_running ? "RUNNING" : "STOPPED"}
                        </span>
                        <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                          {chiller.manufacturer} {chiller.model}
                        </span>
                      </div>
                    </div>

                    {/* Toggle Button */}
                    <button
                      onClick={() => handleToggle(chiller.id, chiller.is_running)}
                      disabled={isControlling}
                      className={`relative w-14 h-7 rounded-full transition-all duration-300 ${
                        isControlling ? "opacity-50 cursor-not-allowed" : "cursor-pointer"
                      }`}
                      style={{
                        background: chiller.is_running
                          ? "var(--color-sentinel-green)"
                          : "var(--color-sentinel-red)",
                      }}
                    >
                      {/* Toggle knob */}
                      <div
                        className={`absolute top-1 w-5 h-5 rounded-full bg-white transition-all duration-300 ${
                          chiller.is_running ? "left-8" : "left-1"
                        }`}
                        style={{
                          boxShadow: "0 1px 3px rgba(0, 0, 0, 0.3)",
                        }}
                      />
                      {isControlling && (
                        <div className="absolute inset-0 flex items-center justify-center">
                          <Activity className="w-4 h-4 text-white animate-spin" />
                        </div>
                      )}
                    </button>
                  </div>
                </div>
              </LockedFeatureOverlay>

              {/* CHW Setpoint Control - Also Gated by Controls Module */}
              {!compact && (
                <LockedFeatureOverlay
                  module="control"
                  featureName={`${chiller.name} Setpoint`}
                  customMessage={`Enable Controls module to optimize CHW supply temperature and achieve 3-5% energy savings on chiller operation.`}
                >
                  <div
                    className="p-4 rounded-lg mb-4"
                    style={{ background: "var(--color-sentinel-bg-secondary)" }}
                  >
                  <div className="flex items-center gap-2 mb-3">
                    <Droplets className="w-4 h-4" style={{ color: "var(--color-sentinel-cyan)" }} />
                    <span className="font-medium text-sm">CHW Supply Setpoint</span>
                  </div>

                  {/* Slider */}
                  <div className="mb-3">
                    <input
                      type="range"
                      min={SETPOINT_MIN}
                      max={SETPOINT_MAX}
                      step={0.5}
                      value={currentSetpoint}
                      onChange={(e) => handleSliderChange(chiller.id, parseFloat(e.target.value))}
                      className="w-full h-2 rounded-lg appearance-none cursor-pointer"
                      style={{
                        background: `linear-gradient(to right, var(--color-sentinel-cyan) 0%, var(--color-sentinel-cyan) ${
                          ((currentSetpoint - SETPOINT_MIN) / (SETPOINT_MAX - SETPOINT_MIN)) * 100
                        }%, var(--color-sentinel-border) ${
                          ((currentSetpoint - SETPOINT_MIN) / (SETPOINT_MAX - SETPOINT_MIN)) * 100
                        }%, var(--color-sentinel-border) 100%)`,
                      }}
                    />
                    <div className="flex justify-between text-xs mt-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                      <span>{SETPOINT_MIN}°C</span>
                      <span className="font-medium text-base" style={{ color: "var(--color-sentinel-cyan)" }}>
                        {currentSetpoint.toFixed(1)}°C
                      </span>
                      <span>{SETPOINT_MAX}°C</span>
                    </div>
                  </div>

                  {/* Apply Button */}
                  {hasChanges && (
                    <button
                      onClick={() => handleSetpointChange(chiller.id, currentSetpoint)}
                      disabled={isAdjusting}
                      className="w-full py-2 px-4 rounded-lg font-medium text-sm transition-all"
                      style={{
                        background: isAdjusting ? "var(--color-sentinel-border)" : "var(--color-sentinel-cyan)",
                        color: "white",
                        opacity: isAdjusting ? 0.7 : 1,
                      }}
                    >
                      {isAdjusting ? (
                        <div className="flex items-center justify-center gap-2">
                          <Activity className="w-4 h-4 animate-spin" />
                          Applying...
                        </div>
                      ) : (
                        `Apply ${currentSetpoint.toFixed(1)}°C`
                      )}
                    </button>
                  )}

                  {/* Current Temps */}
                  <div className="flex justify-between mt-3 text-xs">
                    <div>
                      <span style={{ color: "var(--color-sentinel-text-disabled)" }}>Supply</span>
                      <span
                        className="font-medium"
                        style={{
                          color: metadata.chw_supply_temp
                            ? getSetpointColor(metadata.chw_supply_temp, currentSetpoint)
                            : "var(--color-sentinel-text-secondary)",
                        }}
                      >
                        {Number(metadata.chw_supply_temp)?.toFixed(1) ?? "--"}°C
                      </span>
                    </div>
                    <div>
                      <span style={{ color: "var(--color-sentinel-text-disabled)" }}>Return</span>
                      <span className="font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {Number(metadata.chw_return_temp)?.toFixed(1) ?? "--"}°C
                      </span>
                    </div>
                    <div>
                      <span style={{ color: "var(--color-sentinel-text-disabled)" }}>Load</span>
                      <span className="font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {metadata.load_percent ?? "--"}%
                      </span>
                    </div>
                    <div>
                      <span style={{ color: "var(--color-sentinel-text-disabled)" }}>Power</span>
                      <span className="font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {metadata.power_kw ?? "--"} kW
                      </span>
                    </div>
                  </div>
                  </div>
                </LockedFeatureOverlay>
              )}

              {/* Equipment Info */}
              {!compact && (
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                    <span>Capacity</span>
                    <span style={{ color: "var(--color-sentinel-text-secondary)" }}>{chiller.capacity || "660 kW"}</span>
                  </div>
                  <div className="flex justify-between" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                    <div className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      <span>Installed</span>
                    </div>
                    <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {chiller.install_date
                        ? new Date(chiller.install_date).toLocaleDateString()
                        : "N/A"}
                    </span>
                  </div>
                  <div className="flex justify-between" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                    <span>Last Service</span>
                    <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {chiller.last_service
                        ? new Date(chiller.last_service).toLocaleDateString()
                        : "N/A"}
                    </span>
                  </div>
                </div>
              )}

              {/* Health Warning */}
              {(chiller.calculated_health || chiller.health_score) < thresholds.warning && (
                <div
                  className="flex items-center gap-2 mt-3 p-2 rounded"
                  style={{
                    background: "rgba(245, 158, 11, 0.15)",
                    color: "var(--color-sentinel-amber)",
                  }}
                >
                  <AlertTriangle className="w-4 h-4" />
                  <span className="text-xs">Service recommended</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Safety Note */}
      {!compact && (
        <div className="rounded-md p-4" style={{ background: "rgba(30, 58, 138, 0.1)", border: "1px solid rgba(59, 130, 246, 0.3)" }}>
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-medium text-blue-300">Safety Rules Active</span>
              <span className="text-xs text-blue-400/80 mt-1">
                Chillers are protected by runtime limits (min 5 min, max 4 starts/hour),
                pressure monitoring, and CHW setpoint limits (5-12°C). All controls are validated before execution.
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ChillerControlPanel;

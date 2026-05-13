/**
 * ThermalOptimizationPanel - Pre-cooling and thermal runway visualization
 *
 * Features:
 * - Wraps ThermalRunwayChart and PrecoolingSchedule
 * - Fetches thermal data from HVAC API
 * - Shows load shedding preparedness
 */

import { useState, useEffect, useRef } from "react";
import { Thermometer, Clock, Zap, AlertTriangle } from "lucide-react";
import { hvacApi, type ThermalRunway } from "../../lib/hvacApi";
import api from "../../lib/api";
import { ThermalRunwayChart } from "../ThermalRunwayChart";
import { PrecoolingSchedule } from "../PrecoolingSchedule";

/** Parse a datetime string that may be an ISO datetime or a HH:MM time string. */
function parseDatetime(value: string | undefined | null, fallback: Date): Date {
  if (!value) return fallback;
  // Try ISO parse first
  const parsed = new Date(value);
  if (!isNaN(parsed.getTime())) return parsed;
  // Handle HH:MM time string — use today's date
  const timeMatch = value.match(/^(\d{2}):(\d{2})$/);
  if (timeMatch) {
    const today = new Date();
    today.setHours(parseInt(timeMatch[1], 10), parseInt(timeMatch[2], 10), 0, 0);
    return today;
  }
  return fallback;
}

interface ThermalOptimizationPanelProps {
  siteId: string;
  compact?: boolean;
  /** Optional pre-computed thermal runway from scenario data (with/without pre-cooling values). */
  scenarioRunwayMetrics?: {
    without_precooling: number;
    with_precooling: number;
    comfort_breach_time?: string;
  };
}

export function ThermalOptimizationPanel({ siteId, compact = false, scenarioRunwayMetrics }: ThermalOptimizationPanelProps) {
  const [thermalData, setThermalData] = useState<ThermalRunway | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    async function loadThermalData() {
      try {
        // Use scenario-provided metrics when available (real computed values)
        if (scenarioRunwayMetrics) {
          const runwayWithout = scenarioRunwayMetrics.without_precooling;
          const runwayWith = scenarioRunwayMetrics.with_precooling;
          const improvementPercent = runwayWithout > 0
            ? Math.round(((runwayWith - runwayWithout) / runwayWithout) * 100)
            : 0;
          const now = new Date();
          const breachTime = parseDatetime(
            scenarioRunwayMetrics.comfort_breach_time,
            new Date(now.getTime() + runwayWithout * 60 * 1000),
          );

          const fakeData: ThermalRunway = {
            site_id: siteId,
            timestamp: now.toISOString(),
            data: { time_points: [], without_precooling: [], with_precooling: [] },
            outage_period: {
              start: now.toISOString(),
              end: new Date(now.getTime() + runwayWithout * 60 * 1000).toISOString(),
            },
            metrics: {
              runway_without: runwayWithout,
              runway_with: runwayWith,
              comfort_breach_time: breachTime.toISOString(),
              recovery_time: new Date(now.getTime() + (runwayWith + 30) * 60 * 1000).toISOString(),
              improvement_percent: improvementPercent,
            },
            current_conditions: { avg_temperature: 22.4, avg_setpoint: 22.0, comfort_limit: 26.0 },
          };
          if (!mountedRef.current) return;
          setThermalData(fakeData);
          setLoading(false);
          return;
        }

        // Try to get real pre-cooling scenario values first
        const scenarios = await api.getOptimizationScenarios().catch(() => []);
        const siteScenario = scenarios.find((s: { site_id: string }) => s.site_id === siteId);
        if (siteScenario && siteScenario.thermal_runway) {
          const runwayWithout = siteScenario.thermal_runway.without_precooling;
          const runwayWith = siteScenario.thermal_runway.with_precooling;
          const improvementPercent = runwayWithout > 0
            ? Math.round(((runwayWith - runwayWithout) / runwayWithout) * 100)
            : 0;
          const now = new Date();
          const breachTime = parseDatetime(
            siteScenario.thermal_runway.comfort_breach_time,
            new Date(now.getTime() + runwayWithout * 60 * 1000),
          );
          const scenarioData: ThermalRunway = {
            site_id: siteId,
            timestamp: now.toISOString(),
            data: { time_points: [], without_precooling: [], with_precooling: [] },
            outage_period: {
              start: now.toISOString(),
              end: new Date(now.getTime() + runwayWithout * 60 * 1000).toISOString(),
            },
            metrics: {
              runway_without: runwayWithout,
              runway_with: runwayWith,
              comfort_breach_time: breachTime.toISOString(),
              recovery_time: new Date(now.getTime() + (runwayWith + 30) * 60 * 1000).toISOString(),
              improvement_percent: improvementPercent,
            },
            current_conditions: { avg_temperature: 22.4, avg_setpoint: 22.0, comfort_limit: 26.0 },
          };
          if (!mountedRef.current) return;
          setThermalData(scenarioData);
          setLoading(false);
          return;
        }

        // Fallback: use computed thermal runway from API
        const data = await hvacApi.getThermalRunway(siteId);
        if (!mountedRef.current) return;
        setThermalData(data);
        setLoading(false);
      } catch (err) {
        if (!mountedRef.current) return;
        setError(err instanceof Error ? err.message : "Failed to load thermal data");
        setLoading(false);
      }
    }

    loadThermalData();
    if (!scenarioRunwayMetrics) {
      const interval = setInterval(loadThermalData, 60000);
      return () => {
        mountedRef.current = false;
        clearInterval(interval);
      };
    }
    return () => {
      mountedRef.current = false;
    };
  }, [siteId, scenarioRunwayMetrics]);

  if (loading) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Thermal Optimization</h3>
        <div className="animate-pulse h-64 rounded mt-4" style={{ background: "var(--color-sentinel-bg-secondary)" }} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Thermal Optimization</h3>
        <span className="text-red-500 mt-4">{error}</span>
      </div>
    );
  }

  if (!thermalData) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Thermal Optimization</h3>
        <span className="mt-4" style={{ color: "var(--color-sentinel-text-disabled)" }}>No thermal data available</span>
      </div>
    );
  }

  const { data, metrics, outage_period, current_conditions } = thermalData;

  function chipStyle(kind: "blue" | "gray" | "red") {
    if (kind === "blue") {
      return {
        background: "rgba(59, 130, 246, 0.14)",
        color: "var(--color-sentinel-blue)",
        border: "1px solid rgba(59, 130, 246, 0.30)",
      };
    }
    if (kind === "red") {
      return {
        background: "rgba(239, 68, 68, 0.14)",
        color: "var(--color-sentinel-red)",
        border: "1px solid rgba(239, 68, 68, 0.30)",
      };
    }
    return {
      background: "rgba(148, 163, 184, 0.14)",
      color: "var(--color-sentinel-text-secondary)",
      border: "1px solid rgba(148, 163, 184, 0.28)",
    };
  }

  // Compact view
  if (compact) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Thermometer className="w-5 h-5" style={{ color: "var(--color-sentinel-blue)" }} />
            <span className="font-medium">Thermal Runway</span>
          </div>
          <span className="text-base px-3.5 py-0.5 rounded font-medium" style={chipStyle("blue")}>
            +{metrics.improvement_percent}% with pre-cooling
          </span>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div
            className="p-3 rounded-lg"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>Without Pre-cooling</span>
            <span className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-disabled)" }}>
              {metrics.runway_without} min
            </span>
            <div>
              <span className="text-xs text-red-400">
                Breach at {metrics.comfort_breach_time}
              </span>
            </div>
          </div>
          <div
            className="p-3 rounded-lg border border-blue-500/30"
            style={{ background: "rgba(59, 130, 246, 0.1)" }}
          >
            <span className="text-xs text-blue-300">With Pre-cooling</span>
            <span className="text-2xl font-bold text-blue-300">
              {metrics.runway_with} min
            </span>
            <div>
              <span className="text-xs text-green-400">Comfort maintained</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Full view with tabs
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Thermal Optimization</h3>
          <span>Load shedding preparation and thermal modeling</span>
        </div>
        <div className="flex gap-2">
          <span className="text-xs px-2 py-0.5 rounded" style={chipStyle("gray")}>
            Current: {current_conditions.avg_temperature}°C
          </span>
          <span className="text-xs px-2 py-0.5 rounded" style={chipStyle("red")}>
            Comfort Limit: {current_conditions.comfort_limit}°C
          </span>
        </div>
      </div>

      {/* Key Metrics Summary */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <div className="grid grid-cols-4 gap-4">
          <div
            className="p-4 rounded-lg text-center"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <Thermometer className="w-6 h-6 mx-auto mb-2" style={{ color: "var(--color-sentinel-blue)" }} />
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>Current Temp</span>
            <div>
              <span className="text-2xl font-bold">{current_conditions.avg_temperature}°C</span>
            </div>
          </div>
          <div
            className="p-4 rounded-lg text-center"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <Clock className="w-6 h-6 mx-auto mb-2" style={{ color: "var(--color-sentinel-amber)" }} />
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>Runway (No Pre-cool)</span>
            <div>
              <span className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-disabled)" }}>{metrics.runway_without} min</span>
            </div>
          </div>
          <div
            className="p-4 rounded-lg text-center border border-blue-500/30"
            style={{ background: "rgba(59, 130, 246, 0.1)" }}
          >
            <Zap className="w-6 h-6 mx-auto mb-2 text-blue-400" />
            <span className="text-xs text-blue-300">Runway (Pre-cooled)</span>
            <div>
              <span className="text-2xl font-bold text-blue-300">{metrics.runway_with} min</span>
            </div>
          </div>
          <div
            className="p-4 rounded-lg text-center border border-green-500/30"
            style={{ background: "rgba(16, 185, 129, 0.1)" }}
          >
            <AlertTriangle className="w-6 h-6 mx-auto mb-2 text-green-400" />
            <span className="text-xs text-green-300">Improvement</span>
            <div>
              <span className="text-2xl font-bold text-green-300">+{metrics.improvement_percent}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Custom Tabs */}
      <div role="tablist" className="flex gap-1 mb-4 overflow-x-auto">
        <button
          role="tab"
          aria-selected={activeTab === 0}
          onClick={() => setActiveTab(0)}
          className="px-4 py-2 text-sm font-medium rounded-md transition-colors"
          style={{
            background: activeTab === 0 ? "var(--color-sentinel-bg-secondary)" : "transparent",
            color: activeTab === 0 ? "var(--color-sentinel-text-primary)" : "var(--color-sentinel-text-secondary)",
          }}
        >
          Temp Curves
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 1}
          onClick={() => setActiveTab(1)}
          className="px-4 py-2 text-sm font-medium rounded-md transition-colors"
          style={{
            background: activeTab === 1 ? "var(--color-sentinel-bg-secondary)" : "transparent",
            color: activeTab === 1 ? "var(--color-sentinel-text-primary)" : "var(--color-sentinel-text-secondary)",
          }}
        >
          Pre-cooling
        </button>
      </div>

      {activeTab === 0 && (
        <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
          <ThermalRunwayChart
            data={data}
            outagePeriod={outage_period}
            metrics={{
              runwayWithout: metrics.runway_without,
              runwayWith: metrics.runway_with,
              comfortBreachTime: metrics.comfort_breach_time,
              recoveryTime: metrics.recovery_time,
            }}
          />
        </div>
      )}

      {activeTab === 1 && (
        <PrecoolingSchedule
          schedule={[
            {
              type: "precooling",
              start: "14:45",
              end: outage_period.start,
              label: "PRE-COOLING",
              color: "blue",
              actions: [
                {
                  time: "14:45",
                  action: "CHW setpoint",
                  value: "7°C → 5°C",
                  description: "Lower chilled water setpoint for maximum pre-cooling",
                },
                {
                  time: "14:50",
                  action: "AHU fan speed",
                  value: "70% → 90%",
                  description: "Increase air handling for faster cooling",
                },
                {
                  time: "15:30",
                  action: "Temperature check",
                  value: `${(current_conditions.avg_temperature - 2).toFixed(1)}°C`,
                  description: "Verify pre-cooling target achieved",
                },
              ],
            },
            {
              type: "load_shedding",
              start: outage_period.start,
              end: outage_period.end,
              label: "LOAD SHEDDING",
              color: "red",
              actions: [
                {
                  time: outage_period.start,
                  action: "Power loss",
                  value: "Grid offline",
                  description: "Load shedding begins",
                },
                {
                  time: "17:30",
                  action: "Monitor",
                  value: `${(current_conditions.avg_temperature + 1.5).toFixed(1)}°C`,
                  description: "Temperature drift within limits",
                },
              ],
            },
            {
              type: "recovery",
              start: outage_period.end,
              end: "19:30",
              label: "RECOVERY",
              color: "green",
              actions: [
                {
                  time: outage_period.end,
                  action: "Power restored",
                  value: "Grid online",
                  description: "Begin staged restart",
                },
                {
                  time: "19:00",
                  action: "Temperature recovery",
                  value: `${current_conditions.avg_setpoint}°C`,
                  description: "Return to normal setpoint",
                },
              ],
            },
          ]}
          currentTime={new Date().toLocaleTimeString("en-GB", {
            hour: "2-digit",
            minute: "2-digit",
          })}
          readinessChecks={[
            {
              check: "Chiller status",
              status: "Normal operation",
              time: "Current",
              passed: true,
            },
            {
              check: "Generator test",
              status: "PASSED",
              time: "13:45",
              passed: true,
            },
            {
              check: "UPS capacity",
              status: "96%",
              time: "Current",
              passed: true,
            },
          ]}
        />
      )}
    </div>
  );
}

export default ThermalOptimizationPanel;

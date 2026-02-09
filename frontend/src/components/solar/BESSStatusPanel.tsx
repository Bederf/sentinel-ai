/**
 * BESS Status Panel
 *
 * Battery Energy Storage System monitoring:
 * - SOC gauge (circular progress)
 * - Color coding: >60% green, 30-60% yellow, <30% red
 * - Mode indicator: Charging/Discharging/Idle/Standby
 * - Charge/discharge power bar
 * - State of Health percentage
 * - Estimated runtime at current discharge rate
 *
 * Follows UPSStatusPanel pattern.
 */

import { useState, useEffect, useCallback } from "react";
import {
  Battery,
  BatteryCharging,
  BatteryFull,
  BatteryLow,
  BatteryWarning,
  Zap,
  Heart,
  Clock,
  AlertTriangle,
} from "lucide-react";
import type { BESSStatus } from "../../lib/solarApi";
import { fetchBESSStatus } from "../../lib/solarApi";
import { isExpectedApiError } from "../../lib/api";

interface BESSStatusPanelProps {
  siteId: string;
}

function getSocColor(soc: number): string {
  if (soc > 60) return "var(--color-sentinel-green)";
  if (soc > 30) return "var(--color-sentinel-amber)";
  return "var(--color-sentinel-red)";
}

function getSocBgColor(soc: number): string {
  if (soc > 60) return "rgba(16, 185, 129, 0.15)";
  if (soc > 30) return "rgba(245, 158, 11, 0.15)";
  return "rgba(220, 38, 38, 0.15)";
}

function getModeIcon(mode: BESSStatus["mode"]) {
  switch (mode) {
    case "charging":
      return <BatteryCharging className="h-5 w-5" />;
    case "discharging":
      return <Zap className="h-5 w-5" />;
    case "idle":
      return <Battery className="h-5 w-5" />;
    case "standby":
      return <BatteryFull className="h-5 w-5" />;
    case "fault":
      return <BatteryWarning className="h-5 w-5" />;
    default:
      return <Battery className="h-5 w-5" />;
  }
}

function getModeColor(mode: BESSStatus["mode"]): string {
  switch (mode) {
    case "charging":
      return "var(--color-sentinel-blue)";
    case "discharging":
      return "var(--color-sentinel-amber)";
    case "idle":
      return "var(--color-sentinel-text-secondary)";
    case "standby":
      return "var(--color-sentinel-green)";
    case "fault":
      return "var(--color-sentinel-red)";
    default:
      return "var(--color-sentinel-text-secondary)";
  }
}

export function BESSStatusPanel({ siteId }: BESSStatusPanelProps) {
  const [bess, setBess] = useState<BESSStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const data = await fetchBESSStatus(siteId);
      setBess(data);
      setError(null);
    } catch (err) {
      if (!isExpectedApiError(err)) {
        console.error("Failed to load BESS status:", err);
      }
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 15000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (loading) {
    return (
      <div
        className="rounded-md p-6"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="animate-pulse space-y-4">
          <div className="h-4 w-32 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }} />
          <div className="h-32 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }} />
        </div>
      </div>
    );
  }

  if (error || !bess) {
    return (
      <div
        className="rounded-md p-6 text-center"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <BatteryLow className="h-8 w-8 mx-auto mb-2" style={{ color: "var(--color-sentinel-text-disabled)" }} />
        <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {error || "No BESS data available"}
        </span>
      </div>
    );
  }

  const socColor = getSocColor(bess.soc_percent);
  const socBg = getSocBgColor(bess.soc_percent);
  const modeColor = getModeColor(bess.mode);

  // SVG circular gauge dimensions
  const size = 120;
  const strokeWidth = 10;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const socOffset = circumference - (bess.soc_percent / 100) * circumference;

  // Power bar
  const maxPower = bess.total_capacity_kwh / 2; // approximate 0.5C rate
  const powerPercent = maxPower > 0 ? (Math.abs(bess.current_power_kw) / maxPower) * 100 : 0;

  return (
    <div
      className="rounded-md overflow-hidden"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      {/* Panel Header */}
      <div
        className="p-4 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: socBg }}>
            <Battery className="h-5 w-5" style={{ color: socColor }} />
          </div>
          <div>
            <h3 className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Battery Storage (BESS)
            </h3>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {bess.name} &mdash; {bess.total_capacity_kwh.toLocaleString()} kWh
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {bess.alarms.length > 0 && (
            <span
              className="text-xs px-2 py-1 rounded flex items-center gap-1"
              style={{ background: "rgba(220, 38, 38, 0.15)", color: "var(--color-sentinel-red)" }}
            >
              <AlertTriangle className="h-3 w-3" />
              {bess.alarms.length} alarm{bess.alarms.length !== 1 ? "s" : ""}
            </span>
          )}
          <span
            className="text-xs px-2 py-1 rounded uppercase font-medium flex items-center gap-1"
            style={{ background: `${modeColor}22`, color: modeColor }}
          >
            {getModeIcon(bess.mode)}
            {bess.mode}
          </span>
        </div>
      </div>

      {/* Main Content */}
      <div className="p-4">
        <div className="flex flex-col md:flex-row items-center gap-6">
          {/* SOC Circular Gauge */}
          <div className="flex-shrink-0 relative">
            <svg width={size} height={size} className="transform -rotate-90">
              {/* Background circle */}
              <circle
                cx={size / 2}
                cy={size / 2}
                r={radius}
                fill="none"
                stroke="rgba(255,255,255,0.1)"
                strokeWidth={strokeWidth}
              />
              {/* SOC arc */}
              <circle
                cx={size / 2}
                cy={size / 2}
                r={radius}
                fill="none"
                stroke={socColor}
                strokeWidth={strokeWidth}
                strokeDasharray={circumference}
                strokeDashoffset={socOffset}
                strokeLinecap="round"
                className="transition-all duration-700"
              />
            </svg>
            {/* Center text */}
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-2xl font-bold" style={{ color: socColor }}>
                {bess.soc_percent.toFixed(0)}%
              </span>
              <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                SOC
              </span>
            </div>
          </div>

          {/* Stats Grid */}
          <div className="flex-1 grid grid-cols-2 gap-3 w-full">
            {/* Power Flow */}
            <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
              <div className="flex items-center gap-1.5 mb-1">
                <Zap className="h-3.5 w-3.5" style={{ color: modeColor }} />
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Power
                </span>
              </div>
              <div className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {Math.abs(bess.current_power_kw).toFixed(0)} kW
              </div>
              <div className="mt-1.5">
                <div className="w-full h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.1)" }}>
                  <div
                    className="h-1.5 rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(powerPercent, 100)}%`,
                      background: modeColor,
                    }}
                  />
                </div>
              </div>
            </div>

            {/* State of Health */}
            <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
              <div className="flex items-center gap-1.5 mb-1">
                <Heart className="h-3.5 w-3.5" style={{ color: bess.soh_percent >= 80 ? "var(--color-sentinel-green)" : "var(--color-sentinel-amber)" }} />
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Health (SoH)
                </span>
              </div>
              <div className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {bess.soh_percent.toFixed(1)}%
              </div>
              <div className="text-[10px] mt-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                {bess.cycle_count.toLocaleString()} cycles
              </div>
            </div>

            {/* Runtime Estimate */}
            <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
              <div className="flex items-center gap-1.5 mb-1">
                <Clock className="h-3.5 w-3.5" style={{ color: "var(--color-sentinel-blue)" }} />
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Est. Runtime
                </span>
              </div>
              <div className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {bess.estimated_runtime_min >= 60
                  ? `${Math.floor(bess.estimated_runtime_min / 60)}h ${bess.estimated_runtime_min % 60}m`
                  : `${bess.estimated_runtime_min} min`}
              </div>
              <div className="text-[10px] mt-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                at current load
              </div>
            </div>

            {/* Temperature */}
            <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-xs" style={{ color: bess.temperature_c > 40 ? "var(--color-sentinel-red)" : "var(--color-sentinel-text-secondary)" }}>
                  Temp
                </span>
              </div>
              <div
                className="text-lg font-semibold"
                style={{
                  color: bess.temperature_c > 40
                    ? "var(--color-sentinel-red)"
                    : bess.temperature_c > 35
                    ? "var(--color-sentinel-amber)"
                    : "var(--color-sentinel-text-primary)",
                }}
              >
                {bess.temperature_c.toFixed(1)}&deg;C
              </div>
              <div className="text-[10px] mt-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                {bess.rack_count} racks
              </div>
            </div>
          </div>
        </div>

        {/* Alarms */}
        {bess.alarms.length > 0 && (
          <div
            className="mt-4 p-3 rounded flex flex-wrap gap-2"
            style={{ background: "rgba(220, 38, 38, 0.1)" }}
          >
            {bess.alarms.map((alarm, idx) => (
              <span
                key={idx}
                className="text-xs px-2 py-1 rounded"
                style={{ background: "rgba(220, 38, 38, 0.2)", color: "var(--color-sentinel-red)" }}
              >
                {alarm}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default BESSStatusPanel;

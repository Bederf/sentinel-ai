/**
 * OptimizationPanel Component - Load Shedding Optimization Interface
 *
 * Three-column layout showing:
 * 1. Eskom status and schedule
 * 2. Thermal runway visualization
 * 3. Pre-cooling schedule and actions
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect } from "react";
import { Button } from "@tremor/react";
import { Zap, Clock, Thermometer, CheckCircle, Play, Eye } from "lucide-react";
import { ThermalRunwayChart } from "./ThermalRunwayChart";
import type {
  EskomStatusResponse,
  SiteScheduleResponse,
  ThermalRunwayResponse
} from "../lib/api";

// Sentinel-styled Badge component
interface SentinelBadgeProps {
  children: React.ReactNode;
  variant?: "success" | "warning" | "error" | "info" | "neutral";
  size?: "sm" | "md" | "lg";
  className?: string;
}

function SentinelBadge({ children, variant = "neutral", size = "md", className = "" }: SentinelBadgeProps) {
  const variantStyles = {
    success: {
      bg: "rgba(16, 185, 129, 0.15)",
      color: "var(--color-sentinel-green)",
      border: "rgba(16, 185, 129, 0.3)",
    },
    warning: {
      bg: "rgba(245, 158, 11, 0.15)",
      color: "var(--color-sentinel-amber)",
      border: "rgba(245, 158, 11, 0.3)",
    },
    error: {
      bg: "rgba(220, 38, 38, 0.15)",
      color: "var(--color-sentinel-red)",
      border: "rgba(220, 38, 38, 0.3)",
    },
    info: {
      bg: "rgba(59, 130, 246, 0.15)",
      color: "var(--color-sentinel-blue)",
      border: "rgba(59, 130, 246, 0.3)",
    },
    neutral: {
      bg: "rgba(142, 142, 142, 0.15)",
      color: "var(--color-sentinel-text-secondary)",
      border: "rgba(142, 142, 142, 0.3)",
    },
  };

  const sizeStyles = {
    sm: "text-xs px-2 py-0.5",
    md: "text-sm px-2.5 py-0.5",
    lg: "text-sm px-3 py-1",
  };

  const style = variantStyles[variant];
  const sizeStyle = sizeStyles[size];

  return (
    <span
      className={`inline-flex items-center justify-center rounded font-medium whitespace-nowrap ${sizeStyle} ${className}`}
      style={{
        background: style.bg,
        color: style.color,
        border: `1px solid ${style.border}`,
      }}
    >
      {children}
    </span>
  );
}

interface OptimizationPanelProps {
  siteId?: string;
  scenarioId?: string;
  compact?: boolean;
}

// Mock data for development
const mockEskomStatus: EskomStatusResponse = {
  current_stage: 4,
  updated_at: new Date().toISOString(),
  next_stages: [
    { stage: 4, start_time: "16:00", end_time: "18:30" },
    { stage: 3, start_time: "18:30", end_time: "20:30" },
    { stage: 2, start_time: "20:30", end_time: "22:30" }
  ],
  area_schedules: {}
};

const mockSiteSchedule: SiteScheduleResponse = {
  site_id: "site-001",
  site_name: "Gateway Theatre",
  current_stage: 4,
  schedules: [
    { stage: 4, start_time: "16:00", end_time: "18:30" },
    { stage: 3, start_time: "20:00", end_time: "22:00" }
  ],
  next_outage: { stage: 4, start_time: "16:00", end_time: "18:30" }
};

const mockThermalRunway: ThermalRunwayResponse = {
  site_id: "site-001",
  site_name: "Gateway Theatre",
  current_temperature: 22.4,
  comfort_limit: 26.0,
  thermal_runway_minutes: 52,
  comfort_breach_time: "16:52",
  calculation_method: "thermal_model",
  building_params: {
    thermal_mass: 0.8,
    insulation_factor: 0.6,
    internal_heat_gain: 0.5
  },
  weather_forecast: {
    outside_temp: 32.0,
    solar_load: 0.7,
    humidity: 65
  }
};

const mockPrecoolingSchedule = {
  start: "14:45",
  duration_minutes: 45,
  target_temp: 20.0,
  actions: [
    { time: "14:45", action: "CHW setpoint", value: "6°C → 5°C", description: "Reduce chilled water setpoint" },
    { time: "14:50", action: "AHU fan speed", value: "70% → 85%", description: "Increase air circulation" },
    { time: "15:00", action: "Night purge", value: "Enabled", description: "Use outside air cooling" },
    { time: "15:15", action: "VAV optimization", value: "Balanced", description: "Uniform cooling distribution" },
    { time: "15:30", action: "Temperature check", value: "20.5°C", description: "Target achieved" }
  ],
  energy_impact_kwh: 85,
  peak_demand_increase_percent: 12
};

const mockGeneratorReadiness = [
  { check: "Generator test", status: "PASSED", time: "13:45" },
  { check: "UPS status", status: "96% capacity", time: "Current" },
  { check: "Fuel level", status: "85%", time: "Current" }
];

// Get stage badge variant
function getStageVariant(stage: number): "success" | "warning" | "error" | "info" {
  if (stage === 0) return "success";
  if (stage <= 2) return "warning";
  if (stage <= 4) return "error";
  return "error";
}

export function OptimizationPanel({ siteId = "site-001", scenarioId, compact = false }: OptimizationPanelProps) {
  const [eskomStatus, setEskomStatus] = useState<EskomStatusResponse | null>(mockEskomStatus);
  const [siteSchedule, setSiteSchedule] = useState<SiteScheduleResponse | null>(mockSiteSchedule);
  const [thermalRunway, setThermalRunway] = useState<ThermalRunwayResponse | null>(mockThermalRunway);
  const [loading, setLoading] = useState(false);

  // Load data on mount
  useEffect(() => {
    // TODO: Replace with actual API calls
    setLoading(true);
    setTimeout(() => {
      setEskomStatus(mockEskomStatus);
      setSiteSchedule(mockSiteSchedule);
      setThermalRunway(mockThermalRunway);
      setLoading(false);
    }, 500);
  }, [siteId, scenarioId]);

  if (loading) {
    return (
      <div
        className="rounded-md overflow-hidden mt-6"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="p-4">
          <div className="animate-pulse space-y-4">
            <div className="h-4 rounded w-1/4" style={{ background: "var(--color-sentinel-bg-secondary)" }}></div>
            <div className="h-32 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}></div>
          </div>
        </div>
      </div>
    );
  }

  if (compact) {
    return (
      <div
        className="rounded-md overflow-hidden mt-6"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Zap className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
              <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Load Shedding Optimization
              </span>
            </div>
            <SentinelBadge variant="success">Active</SentinelBadge>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Current Stage
              </span>
              <SentinelBadge variant={getStageVariant(eskomStatus?.current_stage || 0)} size="lg">
                Stage {eskomStatus?.current_stage || 0}
              </SentinelBadge>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Next Outage
              </span>
              <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {siteSchedule?.next_outage ?
                  `${siteSchedule.next_outage.start_time} - ${siteSchedule.next_outage.end_time}` :
                  "None scheduled"}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Thermal Runway
              </span>
              <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {thermalRunway?.thermal_runway_minutes || 0} min
              </span>
            </div>

            <Button size="xs" variant="secondary" icon={Eye}>
              View Details
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-6 space-y-6">
      {/* Header Section */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-medium text-base mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Load Shedding Optimization
          </h2>
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Optimize building comfort and energy use during load shedding
          </p>
        </div>
        <div className="flex items-center gap-2">
          <SentinelBadge variant="success" size="lg">
            Active Monitoring
          </SentinelBadge>
          <Button size="xs" variant="secondary" icon={Play}>
            Start Pre-cool
          </Button>
        </div>
      </div>

      {/* Three Column Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Left Column: Eskom Status */}
        <div
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {/* Card Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
          >
            <div className="flex items-center gap-2">
              <div
                className="p-2 rounded"
                style={{ background: "rgba(59, 130, 246, 0.15)" }}
              >
                <Zap className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
              </div>
              <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Eskom Status
              </span>
            </div>
            <SentinelBadge variant={getStageVariant(eskomStatus?.current_stage || 0)} size="lg">
              Stage {eskomStatus?.current_stage || 0}
            </SentinelBadge>
          </div>

          {/* Card Content */}
          <div className="p-4 space-y-4">
            <div>
              <span className="text-sm font-medium mb-2 block" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Next Outages
              </span>
              <div className="space-y-2">
                {siteSchedule?.schedules?.map((schedule, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 rounded"
                    style={{ background: "var(--color-sentinel-bg-secondary)" }}
                  >
                    <div className="flex items-center gap-2">
                      <Clock className="h-4 w-4" style={{ color: "var(--color-sentinel-text-disabled)" }} />
                      <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        {schedule.start_time} - {schedule.end_time}
                      </span>
                    </div>
                    <SentinelBadge variant={getStageVariant(schedule.stage)} size="sm">
                      Stage {schedule.stage}
                    </SentinelBadge>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <span className="text-sm font-medium mb-2 block" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Area Status
              </span>
              <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                <span className="text-sm font-medium block mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {siteSchedule?.site_name}
                </span>
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {siteSchedule?.next_outage ?
                    `Next outage: ${siteSchedule.next_outage.start_time}-${siteSchedule.next_outage.end_time}` :
                    "No outages scheduled"}
                </span>
              </div>
            </div>

            <div className="pt-2" style={{ borderTop: "1px solid var(--color-sentinel-border)" }}>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                Updated: {new Date(eskomStatus?.updated_at || "").toLocaleTimeString()}
              </span>
            </div>
          </div>
        </div>

        {/* Middle Column: Thermal Runway */}
        <div
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {/* Card Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
          >
            <div className="flex items-center gap-2">
              <div
                className="p-2 rounded"
                style={{ background: "rgba(245, 158, 11, 0.15)" }}
              >
                <Thermometer className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
              </div>
              <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Thermal Runway
              </span>
            </div>
            <SentinelBadge
              variant={thermalRunway?.thermal_runway_minutes && thermalRunway.thermal_runway_minutes > 60 ? "success" : "warning"}
            >
              {thermalRunway?.thermal_runway_minutes || 0} min
            </SentinelBadge>
          </div>

          {/* Card Content */}
          {thermalRunway && (
            <div className="p-4 space-y-4">
              <ThermalRunwayChart
                data={{
                  time_points: ["14:30", "15:00", "15:30", "16:00", "16:30", "17:00", "17:30", "18:00", "18:30"],
                  without_precooling: [22.4, 23.1, 24.0, 24.9, 25.7, 26.5, 27.3, 28.1, 28.9],
                  with_precooling: [22.4, 21.8, 21.2, 21.5, 22.1, 22.9, 23.8, 24.7, 25.5]
                }}
                outagePeriod={{ start: "16:00", end: "18:30" }}
                metrics={{
                  runwayWithout: 52,
                  runwayWith: 108,
                  comfortBreachTime: "16:52",
                  recoveryTime: "19:00"
                }}
              />

              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                  <span className="text-xs block mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Without Pre-cooling
                  </span>
                  <span className="text-xl font-bold block mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    52 min
                  </span>
                  <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Breach at 16:52
                  </span>
                </div>
                <div
                  className="p-3 rounded"
                  style={{
                    background: "rgba(59, 130, 246, 0.15)",
                    border: "1px solid rgba(59, 130, 246, 0.3)",
                  }}
                >
                  <span className="text-xs block mb-1" style={{ color: "var(--color-sentinel-blue)" }}>
                    With SENTINEL
                  </span>
                  <span className="text-xl font-bold block mb-1" style={{ color: "var(--color-sentinel-blue)" }}>
                    1h 48min
                  </span>
                  <span className="text-xs" style={{ color: "var(--color-sentinel-blue)", opacity: 0.8 }}>
                    Comfort maintained
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Pre-cooling Schedule */}
        <div
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {/* Card Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
          >
            <div className="flex items-center gap-2">
              <div
                className="p-2 rounded"
                style={{ background: "rgba(16, 185, 129, 0.15)" }}
              >
                <Clock className="h-5 w-5" style={{ color: "var(--color-sentinel-green)" }} />
              </div>
              <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Pre-cooling Schedule
              </span>
            </div>
            <Button size="xs" variant="primary" icon={Play}>
              Start Now
            </Button>
          </div>

          {/* Card Content */}
          <div className="p-4 space-y-4">
            <div>
              <span className="text-sm font-medium mb-2 block" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Timeline
              </span>
              <div className="space-y-2">
                {mockPrecoolingSchedule.actions.map((action, idx) => (
                  <div
                    key={idx}
                    className="flex items-start gap-3 p-2 rounded"
                    style={{ background: "var(--color-sentinel-bg-secondary)" }}
                  >
                    <div className="flex-shrink-0 w-12">
                      <SentinelBadge variant="info" size="sm">
                        {action.time}
                      </SentinelBadge>
                    </div>
                    <div className="flex-grow">
                      <span className="text-sm font-medium block mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        {action.action}
                      </span>
                      <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {action.value} • {action.description}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <span className="text-sm font-medium mb-2 block" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Generator Readiness
              </span>
              <div className="space-y-2">
                {mockGeneratorReadiness.map((check, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 rounded"
                    style={{ background: "var(--color-sentinel-bg-secondary)" }}
                  >
                    <div className="flex items-center gap-2">
                      <CheckCircle className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
                      <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        {check.check}
                      </span>
                    </div>
                    <div className="text-right">
                      <span className="text-sm font-medium block" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        {check.status}
                      </span>
                      <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {check.time}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-2" style={{ borderTop: "1px solid var(--color-sentinel-border)" }}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Energy Impact
                </span>
                <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  +85 kWh (+12%)
                </span>
              </div>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Pre-cooling uses extra energy now to save generator fuel later
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
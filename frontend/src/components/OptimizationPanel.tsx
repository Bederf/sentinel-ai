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
import { Zap, Clock, Thermometer, CheckCircle, Play, Square, Eye, Building2, ChevronDown, ShieldCheck } from "lucide-react";
import { ThermalRunwayChart } from "./ThermalRunwayChart";
import api from "../lib/api";
import type {
  EskomStatusResponse,
  SiteScheduleResponse,
  ThermalRunwayResponse,
  OptimizationScenario,
  Site,
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

// Helper to build generator readiness display from scenario data
function buildGeneratorReadiness(scenario: OptimizationScenario | null): Array<{ check: string; status: string; time: string }> {
  if (!scenario?.generator_readiness) return [];
  const gr = scenario.generator_readiness;
  return [
    {
      check: "Generator test",
      status: gr.test_passed ? "PASSED" : "FAILED",
      time: gr.last_test ? new Date(gr.last_test).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Unknown",
    },
    { check: "UPS status", status: gr.ups_status === "online" ? "Online" : gr.ups_status, time: "Current" },
    { check: "Fuel level", status: `${gr.fuel_level_percent}%`, time: "Current" },
    { check: "Est. runtime", status: `${gr.estimated_runtime_hours}h (${gr.load_capacity_kw} kW)`, time: "Current" },
  ];
}

// Get stage badge variant
function getStageVariant(stage: number): "success" | "warning" | "error" | "info" {
  if (stage === 0) return "success";
  if (stage <= 2) return "warning";
  if (stage <= 4) return "error";
  return "error";
}

export function OptimizationPanel({ siteId: initialSiteId = "site-001", scenarioId, compact = false }: OptimizationPanelProps) {
  const [selectedSiteId, setSelectedSiteId] = useState(initialSiteId);
  const [sites, setSites] = useState<Site[]>([]);
  const [eskomStatus, setEskomStatus] = useState<EskomStatusResponse | null>(null);
  const [siteSchedule, setSiteSchedule] = useState<SiteScheduleResponse | null>(null);
  const [thermalRunway, setThermalRunway] = useState<ThermalRunwayResponse | null>(null);
  const [scenario, setScenario] = useState<OptimizationScenario | null>(null);
  const [loading, setLoading] = useState(true);

  // Precooling state
  const [precoolingStatus, setPrecoolingStatus] = useState<"idle" | "starting" | "running" | "stopped">("idle");
  const [_precoolingActions, setPrecoolingActions] = useState<any[]>([]);

  // Fetch sites on mount
  useEffect(() => {
    async function loadSites() {
      try {
        const sitesData = await api.getSites();
        setSites(sitesData);
      } catch (err) {
        console.error("Failed to fetch sites:", err);
      }
    }
    loadSites();
  }, []);

  // Check precooling status on mount / site change
  useEffect(() => {
    const checkPrecooling = async () => {
      try {
        const status = await api.getPrecoolingStatus(selectedSiteId);
        if (status.status === "running") {
          setPrecoolingStatus("running");
          setPrecoolingActions(status.actions || []);
        } else {
          setPrecoolingStatus("idle");
          setPrecoolingActions([]);
        }
      } catch {
        // Ignore - precooling status is optional
      }
    };
    checkPrecooling();
  }, [selectedSiteId]);

  const handleStartPrecooling = async () => {
    if (precoolingStatus === "starting") return;
    setPrecoolingStatus("starting");
    try {
      const result = await api.startPrecooling(selectedSiteId, scenarioId);
      if (result.success) {
        setPrecoolingStatus(result.status === "already_running" ? "running" : "running");
        setPrecoolingActions(result.actions || []);
      }
    } catch (error) {
      console.error("Failed to start precooling:", error);
      setPrecoolingStatus("idle");
    }
  };

  const handleStopPrecooling = async () => {
    try {
      const result = await api.stopPrecooling(selectedSiteId);
      if (result.success) {
        setPrecoolingStatus("idle");
        setPrecoolingActions([]);
      }
    } catch (error) {
      console.error("Failed to stop precooling:", error);
    }
  };

  // Load data on mount / site change
  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      setLoading(true);
      try {
        // Fetch eskom status, site schedule, thermal runway, and scenarios with staggered delays
        const eskomData = await api.getEskomStatus().catch(() => null);
        // Stagger subsequent requests by 250ms to avoid 429 rate limiting
        await new Promise((resolve) => setTimeout(resolve, 250));
        const scheduleData = await api.getSiteEskomStatus(selectedSiteId).catch(() => null);
        await new Promise((resolve) => setTimeout(resolve, 250));
        const thermalData = await api.getThermalRunway(selectedSiteId).catch(() => null);
        await new Promise((resolve) => setTimeout(resolve, 250));
        const scenarios = await api.getOptimizationScenarios().catch(() => [] as OptimizationScenario[]);
        if (cancelled) return;

        setEskomStatus(eskomData);
        setSiteSchedule(scheduleData);
        setThermalRunway(thermalData);

        // Find matching scenario: by scenarioId prop, or by site_id
        const matched = scenarioId
          ? scenarios.find((s) => s.scenario_id === scenarioId) ?? null
          : scenarios.find((s) => s.site_id === selectedSiteId) ?? scenarios[0] ?? null;
        setScenario(matched);
      } catch (err) {
        console.error("Failed to load optimization data:", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchData();
    return () => { cancelled = true; };
  }, [selectedSiteId, scenarioId]);

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

  const currentStage = eskomStatus?.current_stage ?? 0;
  const isLoadShedding = currentStage > 0;

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
            <SentinelBadge variant={isLoadShedding ? getStageVariant(currentStage) : "success"}>
              {isLoadShedding ? `Stage ${currentStage}` : "No Load Shedding"}
            </SentinelBadge>
          </div>

          {isLoadShedding ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Current Stage
                </span>
                <SentinelBadge variant={getStageVariant(currentStage)} size="lg">
                  Stage {currentStage}
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
          ) : (
            <div className="flex items-center gap-2 py-2">
              <ShieldCheck className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
              <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Grid supply is stable — no outages scheduled
              </span>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="mt-6 space-y-6">
      {/* Header Section */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          {/* Building Selector */}
          <div className="relative min-w-[200px]">
            <Building2
              className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            />
            <select
              value={selectedSiteId}
              onChange={(e) => setSelectedSiteId(e.target.value)}
              className="w-full pl-9 pr-8 py-2 text-sm rounded appearance-none cursor-pointer"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              {sites.map((site) => (
                <option key={site.id} value={site.id}>
                  {site.name}
                </option>
              ))}
            </select>
            <ChevronDown
              className="absolute right-2 top-1/2 transform -translate-y-1/2 h-4 w-4 pointer-events-none"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            />
          </div>
          <div>
            <h2 className="font-medium text-base mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Load Shedding Optimization
            </h2>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Optimize building comfort and energy use during load shedding
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <SentinelBadge variant={isLoadShedding ? getStageVariant(currentStage) : "success"} size="lg">
            {isLoadShedding ? `Stage ${currentStage} Active` : "No Load Shedding"}
          </SentinelBadge>
          {precoolingStatus === "running" ? (
            <Button size="xs" variant="secondary" icon={Square} onClick={handleStopPrecooling}>
              Stop Pre-cool
            </Button>
          ) : (
            <Button
              size="xs"
              variant="secondary"
              icon={Play}
              onClick={handleStartPrecooling}
              loading={precoolingStatus === "starting"}
            >
              Start Pre-cool
            </Button>
          )}
        </div>
      </div>

      {/* Stacked Cards */}
      <div className="space-y-6">
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
            <SentinelBadge variant={getStageVariant(currentStage)} size="lg">
              {isLoadShedding ? `Stage ${currentStage}` : "No Load Shedding"}
            </SentinelBadge>
          </div>

          {/* Card Content */}
          <div className="p-4 space-y-4">
            {isLoadShedding ? (
              <>
                <div>
                  <span className="text-sm font-medium mb-2 block" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    Next Outages
                  </span>
                  <div className="space-y-2">
                    {siteSchedule?.schedules?.length ? (
                      siteSchedule.schedules.map((schedule, idx) => (
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
                      ))
                    ) : (
                      <div className="p-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                        <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          No area schedule available
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div>
                  <span className="text-sm font-medium mb-2 block" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    Area Status
                  </span>
                  <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                    <span className="text-sm font-medium block mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {siteSchedule?.area_name || siteSchedule?.site_name}
                    </span>
                    <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {siteSchedule?.next_outage ?
                        `Next outage: ${siteSchedule.next_outage.start_time}-${siteSchedule.next_outage.end_time}` :
                        "No outages scheduled for this area"}
                    </span>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex flex-col items-center justify-center py-6 gap-3">
                <div
                  className="p-3 rounded-full"
                  style={{ background: "rgba(16, 185, 129, 0.15)" }}
                >
                  <ShieldCheck className="h-8 w-8" style={{ color: "var(--color-sentinel-green)" }} />
                </div>
                <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  No Load Shedding Active
                </span>
                <span className="text-xs text-center" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  The national grid is stable. No outages are currently scheduled.
                  {eskomStatus?.source === "eskomsepush" && " Data from EskomSePush."}
                  {eskomStatus?.source === "not_configured" && " Configure EskomSePush API for live data."}
                </span>
              </div>
            )}

            <div className="pt-2" style={{ borderTop: "1px solid var(--color-sentinel-border)" }}>
              <div className="flex items-center justify-between">
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                  Updated: {new Date(eskomStatus?.updated_at || "").toLocaleTimeString()}
                </span>
                {eskomStatus?.source && (
                  <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                    Source: {eskomStatus.source === "eskomsepush" ? "EskomSePush" : eskomStatus.source === "not_configured" ? "Not configured" : "Unavailable"}
                  </span>
                )}
              </div>
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
              {scenario?.visualization_data ? (
                <ThermalRunwayChart
                  data={{
                    time_points: scenario.visualization_data.thermal_curve.map(([min]) => {
                      const base = scenario.current_conditions?.time_of_day || "14:00";
                      const [h, m] = base.split(":").map(Number);
                      const totalMin = h * 60 + m + min;
                      return `${String(Math.floor(totalMin / 60)).padStart(2, "0")}:${String(totalMin % 60).padStart(2, "0")}`;
                    }),
                    without_precooling: scenario.visualization_data.thermal_curve.map(([, temp]) => temp),
                    with_precooling: scenario.visualization_data.precooling_curve.map(([, temp]) => temp),
                  }}
                  outagePeriod={{
                    start: scenario.load_shedding.start,
                    end: scenario.load_shedding.end,
                  }}
                  metrics={{
                    runwayWithout: scenario.thermal_runway.without_precooling,
                    runwayWith: scenario.thermal_runway.with_precooling,
                    comfortBreachTime: scenario.thermal_runway.comfort_breach_time,
                    recoveryTime: scenario.restart_plan?.estimated_restoration_time || "",
                  }}
                />
              ) : (
                <ThermalRunwayChart
                  data={{
                    time_points: [],
                    without_precooling: [],
                    with_precooling: [],
                  }}
                  outagePeriod={{ start: "", end: "" }}
                  metrics={{
                    runwayWithout: thermalRunway.thermal_runway_minutes,
                    runwayWith: thermalRunway.thermal_runway_minutes,
                    comfortBreachTime: thermalRunway.comfort_breach_time || "",
                    recoveryTime: "",
                  }}
                />
              )}

              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                  <span className="text-xs block mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Without Pre-cooling
                  </span>
                  <span className="text-xl font-bold block mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {scenario ? scenario.thermal_runway.without_precooling : thermalRunway.thermal_runway_minutes} min
                  </span>
                  <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Breach at {scenario?.thermal_runway.comfort_breach_time || thermalRunway.comfort_breach_time || "N/A"}
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
                    {(() => {
                      const mins = scenario?.thermal_runway.with_precooling || thermalRunway.thermal_runway_minutes;
                      return mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}min` : `${mins} min`;
                    })()}
                  </span>
                  <span className="text-xs" style={{ color: "var(--color-sentinel-blue)", opacity: 0.8 }}>
                    {scenario?.thermal_runway.comfort_maintained ? "Comfort maintained" : "Comfort at risk"}
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
            {precoolingStatus === "running" ? (
              <SentinelBadge variant="success" size="sm">Running</SentinelBadge>
            ) : (
              <Button
                size="xs"
                variant="primary"
                icon={Play}
                onClick={handleStartPrecooling}
                loading={precoolingStatus === "starting"}
              >
                Start Now
              </Button>
            )}
          </div>

          {/* Card Content */}
          <div className="p-4 space-y-4">
            <div>
              <span className="text-sm font-medium mb-2 block" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Timeline
              </span>
              <div className="space-y-2">
                {(scenario?.pre_cooling_schedule?.actions || []).map((action, idx) => (
                  <div
                    key={idx}
                    className="flex items-start gap-3 p-2 rounded"
                    style={{
                      background: precoolingStatus === "running"
                        ? "rgba(16, 185, 129, 0.1)"
                        : "var(--color-sentinel-bg-secondary)",
                      border: precoolingStatus === "running"
                        ? "1px solid rgba(16, 185, 129, 0.2)"
                        : "1px solid transparent",
                    }}
                  >
                    <div className="flex-shrink-0 w-12">
                      <SentinelBadge variant={precoolingStatus === "running" ? "success" : "info"} size="sm">
                        {action.time}
                      </SentinelBadge>
                    </div>
                    <div className="flex-grow">
                      <span className="text-sm font-medium block mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        {action.action.replace(/_/g, " ")}
                      </span>
                      <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {action.value} • {action.description}
                      </span>
                    </div>
                    {precoolingStatus === "running" && (
                      <CheckCircle className="h-4 w-4 flex-shrink-0 mt-0.5" style={{ color: "var(--color-sentinel-green)" }} />
                    )}
                  </div>
                ))}
                {(!scenario?.pre_cooling_schedule?.actions || scenario.pre_cooling_schedule.actions.length === 0) && (
                  <div className="p-3 rounded text-center" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                    <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      No scenario data for this site
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div>
              <span className="text-sm font-medium mb-2 block" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Generator Readiness
              </span>
              <div className="space-y-2">
                {buildGeneratorReadiness(scenario).map((check, idx) => (
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
                  +{scenario?.pre_cooling_schedule?.energy_impact_kwh ?? 0} kWh (+{scenario?.pre_cooling_schedule?.peak_demand_increase_percent ?? 0}%)
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
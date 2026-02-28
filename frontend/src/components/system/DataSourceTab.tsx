/**
 * Data Source Tab — Site 002 lifecycle simulator driver
 *
 * Extracted from SimulationDashboard ControlTab.
 * Admin-only tool for starting/stopping/pausing the Site 002 BMS simulator.
 * Renders inside the SIMBIOT page as a sub-tab.
 * For production buildings, this wouldn't exist — data flows from the real BMS.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import type { ReactElement } from "react";
import {
  Play,
  Square,
  Pause,
  RotateCcw,
  Activity,
  AlertTriangle,
  Wrench,
  Clock,
} from "lucide-react";
import {
  fetchScenarios,
  startSimulation,
  stopSimulation,
  pauseSimulation,
  resumeSimulation,
  getSimulationStatus,
  getSimulationEvents,
} from "../../lib/simulationApi";
import type {
  ScenarioInfo,
  SimulationStatus,
  LiveEvent,
} from "../../lib/simulationApi";
import type { OptimizationRecommendation, OptimizationAction } from "@/lib/api";
import { SimulationTimeIndicator } from "../SimulationTimeIndicator";
import { Simulation3DViewer } from "../Simulation3DViewer";
import { OptimizationRecommendationModal } from "../OptimizationRecommendationModal";

// ---------- Constants ----------

const DURATION_PRESETS = [
  { label: "2 min", value: 2 },
  { label: "5 min", value: 5 },
  { label: "12 min", value: 12 },
  { label: "24 min", value: 24 },
];

const EVENT_TYPE_LABELS: Record<string, string> = {
  building_wake: "Building Wake",
  building_sleep: "Building Sleep",
  ai_optimization: "AI Optimization",
  equipment_fault: "Equipment Fault",
  alert_generated: "Alert Generated",
  work_order_created: "Work Order",
  repair_completed: "Repair Complete",
  setpoint_change: "Setpoint Change",
  health_restored: "Health Restored",
  service_feedback: "Service Feedback",
};

// ---------- Helpers ----------

function formatHour(h: number): string {
  return `${String(h).padStart(2, "0")}:00`;
}

function statusColor(running: boolean, paused: boolean): string {
  if (running && !paused) return "var(--color-sentinel-green)";
  if (paused) return "var(--color-sentinel-amber)";
  return "var(--color-sentinel-text-disabled)";
}

function statusLabel(running: boolean, paused: boolean): string {
  if (running && !paused) return "Running";
  if (paused) return "Paused";
  return "Stopped";
}

function eventTypeColor(type: string): string {
  switch (type) {
    case "equipment_fault":
    case "alert_generated":
      return "var(--color-sentinel-red)";
    case "ai_optimization":
    case "setpoint_change":
      return "var(--color-sentinel-blue)";
    case "repair_completed":
    case "health_restored":
    case "service_feedback":
      return "var(--color-sentinel-green)";
    case "work_order_created":
      return "var(--color-sentinel-amber)";
    default:
      return "var(--color-sentinel-text-secondary)";
  }
}

function StatusCard({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: string;
  icon: ReactElement;
  color?: string;
}) {
  return (
    <div
      className="rounded-md p-3"
      style={{
        background: "var(--color-sentinel-bg-primary)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span style={{ color: color ?? "var(--color-sentinel-text-secondary)" }}>
          {icon}
        </span>
        <span
          className="text-xs font-medium"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          {label}
        </span>
      </div>
      <div
        className="text-xl font-bold"
        style={{ color: color ?? "var(--color-sentinel-text-primary)" }}
      >
        {value}
      </div>
    </div>
  );
}

// ---------- Main Component ----------

interface DataSourceTabProps {
  siteId?: string;
}

export function DataSourceTab({ siteId = "site-002" }: DataSourceTabProps) {
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [selectedScenario, setSelectedScenario] = useState("fault_day");
  const [duration, setDuration] = useState(5);
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showRecommendationModal, setShowRecommendationModal] = useState(false);
  const [currentRecommendation, setCurrentRecommendation] = useState<OptimizationRecommendation | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load scenarios once
  useEffect(() => {
    fetchScenarios()
      .then((s) => {
        setScenarios(s);
        if (s.length > 0 && !s.find((x) => x.id === selectedScenario)) {
          setSelectedScenario(s[0].id);
        }
      })
      .catch(() => setError("Failed to load scenarios"));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll status while running
  const pollStatus = useCallback(async () => {
    try {
      const [st, ev] = await Promise.all([
        getSimulationStatus(),
        getSimulationEvents({ limit: 50 }),
      ]);
      setStatus(st);
      setEvents(ev.events);
      if (!st.running && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch {
      // ignore transient errors during polling
    }
  }, []);

  // Initial status check
  useEffect(() => {
    pollStatus();
  }, [pollStatus]);

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(pollStatus, 5000);
  }, [pollStatus]);

  // Watch for AI optimization events
  useEffect(() => {
    const aiOptEvent = events.find((ev) => ev.event_type === "ai_optimization");
    if (aiOptEvent && aiOptEvent.details) {
      const details = aiOptEvent.details as any;
      if (details.recommendations && Array.isArray(details.recommendations)) {
        const recs = details.recommendations as any[];
        const totalSavings = recs.reduce((sum: number, r: any) => sum + (r.savings || 0), 0);

        const rec: OptimizationRecommendation = {
          id: `${aiOptEvent.timestamp}`,
          site_id: "S002",
          timestamp: aiOptEvent.timestamp || new Date().toISOString(),
          recommendations: recs.map((r: any) => ({
            equipment_id: r.equipment || "unknown",
            equipment_name: r.equipment || "unknown",
            point_name: r.control_point || "setpoint",
            current_value: 21,
            recommended_value: typeof r.target_value === "number" ? r.target_value : 22,
          } as OptimizationAction)),
          projected_savings: {
            energy_kwh: totalSavings,
            cost_zar_per_hour: totalSavings * 5,
            percentage_improvement: Math.min(35, totalSavings),
          },
          confidence: 0.85,
          reasoning: `AI optimization (${details.context}) - Occupancy ${details.occupancy_percent}%, Daylight ${details.daylight_factor}%`,
        };
        setCurrentRecommendation(rec);
        setShowRecommendationModal(true);
      }
    }
  }, [events]);

  const handleApproveRecommendation = async (_recommendationId: string) => {
    setShowRecommendationModal(false);
    setCurrentRecommendation(null);
  };

  const handleRejectRecommendation = async (_recommendationId: string) => {
    setShowRecommendationModal(false);
    setCurrentRecommendation(null);
  };

  const handleStart = async () => {
    setLoading(true);
    setError(null);
    try {
      await startSimulation({ scenario: selectedScenario, duration_minutes: duration });
      await pollStatus();
      startPolling();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start");
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await stopSimulation();
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      await pollStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to stop");
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async () => {
    try {
      if (status?.paused) {
        await resumeSimulation();
      } else {
        await pauseSimulation();
      }
      await pollStatus();
    } catch {
      // ignore
    }
  };

  const isRunning = status?.running ?? false;
  const isPaused = status?.paused ?? false;
  const currentScenario = scenarios.find((s) => s.id === selectedScenario);

  return (
    <div className="space-y-6">
      {/* Error */}
      {error && (
        <div
          className="rounded-md p-4 flex items-center gap-3"
          style={{
            background: "rgba(220, 38, 38, 0.1)",
            border: "1px solid rgba(220, 38, 38, 0.3)",
          }}
        >
          <AlertTriangle className="h-5 w-5 flex-shrink-0" style={{ color: "var(--color-sentinel-red)" }} />
          <span style={{ color: "var(--color-sentinel-text-primary)" }}>{error}</span>
        </div>
      )}

      {/* Controls Row */}
      <div
        className="rounded-md p-5"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <h3
          className="text-sm font-semibold mb-4 uppercase tracking-wider"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Data Source Controls
        </h3>

        <div className="flex flex-wrap gap-4 items-end">
          {/* Scenario Select */}
          <div className="flex-1 min-w-[200px]">
            <label
              className="block text-xs font-medium mb-1"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Scenario
            </label>
            <select
              value={selectedScenario}
              onChange={(e) => setSelectedScenario(e.target.value)}
              disabled={isRunning}
              className="w-full rounded-md px-3 py-2 text-sm"
              style={{
                background: "var(--color-sentinel-bg-primary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          {/* Duration Select */}
          <div>
            <label
              className="block text-xs font-medium mb-1"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Duration
            </label>
            <div className="flex gap-1">
              {DURATION_PRESETS.map((p) => (
                <button
                  key={p.value}
                  onClick={() => setDuration(p.value)}
                  disabled={isRunning}
                  className="px-3 py-2 rounded-md text-sm font-medium transition-colors"
                  style={{
                    background:
                      duration === p.value
                        ? "var(--color-sentinel-amber)"
                        : "var(--color-sentinel-bg-primary)",
                    color:
                      duration === p.value
                        ? "#000"
                        : "var(--color-sentinel-text-primary)",
                    border: "1px solid var(--color-sentinel-border)",
                    opacity: isRunning ? 0.5 : 1,
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-2">
            {!isRunning ? (
              <button
                onClick={handleStart}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors"
                style={{
                  background: "var(--color-sentinel-green)",
                  color: "#000",
                  opacity: loading ? 0.5 : 1,
                }}
              >
                <Play className="h-4 w-4" />
                Start
              </button>
            ) : (
              <>
                <button
                  onClick={handlePause}
                  className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors"
                  style={{
                    background: "var(--color-sentinel-amber)",
                    color: "#000",
                  }}
                >
                  {isPaused ? (
                    <>
                      <RotateCcw className="h-4 w-4" />
                      Resume
                    </>
                  ) : (
                    <>
                      <Pause className="h-4 w-4" />
                      Pause
                    </>
                  )}
                </button>
                <button
                  onClick={handleStop}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors"
                  style={{
                    background: "var(--color-sentinel-red)",
                    color: "#fff",
                    opacity: loading ? 0.5 : 1,
                  }}
                >
                  <Square className="h-4 w-4" />
                  Stop
                </button>
              </>
            )}
          </div>
        </div>

        {/* Scenario description */}
        {currentScenario && (
          <p
            className="mt-3 text-xs"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            {currentScenario.description}
          </p>
        )}
      </div>

      {/* Status Panel */}
      <div
        className="rounded-md p-5"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <h3
            className="text-sm font-semibold uppercase tracking-wider"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Live Status
          </h3>
          <span
            className="flex items-center gap-2 text-xs font-medium px-2 py-1 rounded"
            style={{
              background: `${statusColor(isRunning, isPaused)}20`,
              color: statusColor(isRunning, isPaused),
            }}
          >
            <span
              className="w-2 h-2 rounded-full"
              style={{ background: statusColor(isRunning, isPaused) }}
            />
            {statusLabel(isRunning, isPaused)}
          </span>
        </div>

        {/* KPI cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <StatusCard
            label="Simulated Hour"
            value={status?.simulated_hour != null ? formatHour(status.simulated_hour) : "--:--"}
            icon={<Clock className="h-4 w-4" />}
          />
          <StatusCard
            label="Events"
            value={String(status?.events_count ?? 0)}
            icon={<Activity className="h-4 w-4" />}
          />
          <StatusCard
            label="Active Faults"
            value={String(status?.active_faults ?? 0)}
            icon={<AlertTriangle className="h-4 w-4" />}
            color={
              (status?.active_faults ?? 0) > 0
                ? "var(--color-sentinel-red)"
                : undefined
            }
          />
          <StatusCard
            label="Pending Repairs"
            value={String(status?.pending_repairs ?? 0)}
            icon={<Wrench className="h-4 w-4" />}
          />
        </div>

        {/* 3D Visualization & Recent Events Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* 3D Viewer - 2 columns */}
          <div className="lg:col-span-2">
            <h4
              className="text-xs font-semibold mb-2 uppercase tracking-wider"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              3D Occupancy Visualization
            </h4>
            <div
              className="rounded-md overflow-hidden"
              style={{
                background: "var(--color-sentinel-bg-primary)",
                border: "1px solid var(--color-sentinel-border)",
                height: "400px",
              }}
            >
              <Simulation3DViewer
                events={events}
                isRunning={isRunning}
                simulatedHour={status?.simulated_hour ?? 0}
              />
            </div>
          </div>

          {/* Recent Events - 1 column */}
          {events.length > 0 && (
            <div>
              <h4
                className="text-xs font-semibold mb-2 uppercase tracking-wider"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Recent Events
              </h4>
              <div className="space-y-1 max-h-[400px] overflow-y-auto">
                {events.map((ev, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-3 text-xs px-3 py-2 rounded"
                    style={{
                      background: "var(--color-sentinel-bg-primary)",
                      border: "1px solid var(--color-sentinel-border)",
                    }}
                  >
                    <span
                      className="font-mono w-12 flex-shrink-0"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      {formatHour(ev.hour)}
                    </span>
                    <span
                      className="px-2 py-0.5 rounded text-xs font-medium flex-shrink-0"
                      style={{
                        background: eventTypeColor(ev.event_type) + "20",
                        color: eventTypeColor(ev.event_type),
                      }}
                    >
                      {EVENT_TYPE_LABELS[ev.event_type] ?? ev.event_type}
                    </span>
                    <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {ev.description}
                    </span>
                    {ev.equipment_name && (
                      <span
                        className="ml-auto flex-shrink-0"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
                      >
                        {ev.equipment_name}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* AI Optimization Recommendation Modal */}
      {currentRecommendation && (
        <OptimizationRecommendationModal
          isOpen={showRecommendationModal}
          onClose={() => {
            setShowRecommendationModal(false);
            setCurrentRecommendation(null);
          }}
          recommendation={currentRecommendation}
          onApprove={handleApproveRecommendation}
          onReject={handleRejectRecommendation}
          siteName="Site 002"
        />
      )}

      {/* Time Indicator */}
      <SimulationTimeIndicator simulationRunning={isRunning} siteId={siteId} />
    </div>
  );
}

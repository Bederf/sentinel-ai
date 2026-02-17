/**
 * Simulation Dashboard - Control & Analytics
 *
 * Control tab: start/stop simulations, choose scenario, view live status + events
 * Analytics tab: select past runs, KPI cards, charts, profile scores, event table
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
  Zap,
  Clock,
  ChevronLeft,
  ChevronRight,
  Filter,
  Brain,
  CheckCircle,
  XCircle,
  RefreshCw,
  Target,
  FlaskConical,
} from "lucide-react";
import {
  Tab,
  TabGroup,
  TabList,
  TabPanel,
  TabPanels,
  BarChart,
} from "@tremor/react";
import {
  fetchScenarios,
  startSimulation,
  stopSimulation,
  pauseSimulation,
  resumeSimulation,
  getSimulationStatus,
  getSimulationEvents,
  fetchRuns,
  fetchRunAnalysis,
  fetchRunEvents,
  fetchModelStatus,
  fetchModelHealth,
  fetchPerformance,
  fetchABTests,
} from "../lib/simulationApi";
import type {
  ScenarioInfo,
  SimulationStatus,
  LiveEvent,
  SimulationRunRecord,
  SimulationAnalysisReport,
  SimulationEvent,
  ModelStatusResponse,
  ModelHealthSummary,
  PerformanceEvaluation,
  ABTest,
} from "../lib/simulationApi";
import api from '@/lib/api';
import type { Site } from '@/lib/api';
import { PageLoading } from "./PageLoading";
import { BuildingSelector } from "./BuildingSelector";
import { SimulationTimeIndicator } from "./SimulationTimeIndicator";
import { Simulation3DViewer } from "./Simulation3DViewer";
import { OptimizationRecommendationModal } from "./OptimizationRecommendationModal";
import type { OptimizationRecommendation, OptimizationAction } from "@/lib/api";

// ---------- Duration presets ----------

const DURATION_PRESETS = [
  { label: "2 min", value: 2 },
  { label: "5 min", value: 5 },
  { label: "12 min", value: 12 },
  { label: "24 min", value: 24 },
];

// ---------- Profile display config ----------

const PROFILE_LABELS: Record<string, string> = {
  asset_sweating: "Asset Sweating",
  comfort_first: "Comfort First",
  cost_saving: "Cost Saving",
};

const DIMENSION_LABELS: Record<string, string> = {
  runtime: "Runtime",
  comfort: "Comfort",
  cost: "Cost",
  maintenance: "Maintenance",
  energy: "Energy",
};

// ---------- Event type labels ----------

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

// ============================================================
// Main Component
// ============================================================

export function SimulationDashboard() {
  const [activeTab, setActiveTab] = useState(0);
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("site-002");

  // Load sites on mount
  useEffect(() => {
    const loadSites = async () => {
      try {
        const sitesData = await api.getSites();
        setSites(sitesData.sort((a, b) => a.name.localeCompare(b.name)));
        const defaultSite = sitesData.find((s) => s.id === "site-002") || sitesData[0];
        if (defaultSite) setSelectedSiteId(defaultSite.id);
      } catch {
        // fall back to default
      }
    };
    loadSites();
  }, []);

  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Header with building selector */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2
            className="text-lg font-semibold"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Simulation
          </h2>
          <p
            className="text-sm"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            24-hour lifecycle simulation & analytics
          </p>
        </div>
        <div style={{ minWidth: "200px" }}>
          <BuildingSelector
            value={selectedSiteId}
            onChange={setSelectedSiteId}
            sites={sites}
          />
        </div>
      </div>

      <TabGroup index={activeTab} onIndexChange={setActiveTab}>
        <TabList className="mb-6">
          {[
            <Tab key="control">Control</Tab>,
            <Tab key="analytics">Analytics</Tab>,
            <Tab key="model-health">Model Health</Tab>,
          ] as unknown as ReactElement}
        </TabList>
        <TabPanels>
          {[
            <TabPanel key="control">
              <ControlTab selectedSiteId={selectedSiteId} />
            </TabPanel>,
            <TabPanel key="analytics">
              <AnalyticsTab selectedSiteId={selectedSiteId} />
            </TabPanel>,
            <TabPanel key="model-health">
              <ModelHealthTab selectedSiteId={selectedSiteId} />
            </TabPanel>,
          ] as unknown as ReactElement}
        </TabPanels>
      </TabGroup>
    </div>
  );
}

// ============================================================
// Control Tab
// ============================================================

function ControlTab({ selectedSiteId: _selectedSiteId }: { selectedSiteId: string }) {
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
      // Stop polling when simulation finishes
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

  // Set up polling interval
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(pollStatus, 5000);
  }, [pollStatus]);

  // Watch for AI optimization events and show recommendation modal
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
      setError(e instanceof Error ? e.message : "Failed to start simulation");
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
      setError(e instanceof Error ? e.message : "Failed to stop simulation");
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
          Simulation Controls
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
          siteName="Simulation"
        />
      )}

      {/* Simulation Time Indicator - Sun/Moon Floating Widget */}
      <SimulationTimeIndicator simulationRunning={isRunning} siteId={_selectedSiteId} />
    </div>
  );
}

// ---------- StatusCard ----------

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

// ---------- Event type color helper ----------

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

// ============================================================
// Analytics Tab
// ============================================================

function AnalyticsTab({ selectedSiteId: _selectedSiteId }: { selectedSiteId: string }) {
  const [runs, setRuns] = useState<SimulationRunRecord[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<SimulationAnalysisReport | null>(null);
  const [events, setEvents] = useState<SimulationEvent[]>([]);
  const [eventsTotal, setEventsTotal] = useState(0);
  const [eventsPage, setEventsPage] = useState(0);
  const [eventTypeFilter, setEventTypeFilter] = useState("");
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const PAGE_SIZE = 20;

  // Load runs
  useEffect(() => {
    fetchRuns()
      .then((r) => {
        setRuns(r);
        if (r.length > 0) setSelectedRunId(r[0].run_id);
      })
      .catch(() => setError("Failed to load simulation runs"))
      .finally(() => setLoadingRuns(false));
  }, []);

  // Load analysis when run changes
  const loadAnalysis = useCallback(async (runId: string) => {
    setLoadingAnalysis(true);
    setError(null);
    try {
      const report = await fetchRunAnalysis(runId);
      setAnalysis(report);
    } catch {
      setError("Failed to load analysis");
    } finally {
      setLoadingAnalysis(false);
    }
  }, []);

  useEffect(() => {
    if (selectedRunId) loadAnalysis(selectedRunId);
  }, [selectedRunId, loadAnalysis]);

  // Load events when run/page/filter changes
  useEffect(() => {
    if (!selectedRunId) return;
    fetchRunEvents(selectedRunId, {
      event_type: eventTypeFilter || undefined,
      offset: eventsPage * PAGE_SIZE,
      limit: PAGE_SIZE,
    })
      .then((r) => {
        setEvents(r.events);
        setEventsTotal(r.count);
      })
      .catch(() => {
        /* ignore */
      });
  }, [selectedRunId, eventsPage, eventTypeFilter]);

  const handleRunChange = useCallback((runId: string) => {
    setSelectedRunId(runId);
    setEventsPage(0);
  }, []);

  const handleEventTypeFilterChange = useCallback((value: string) => {
    setEventTypeFilter(value);
    setEventsPage(0);
  }, []);

  if (loadingRuns) {
    return (
      <div className="flex items-center justify-center py-12">
        <Activity
          className="h-6 w-6 animate-spin mr-3"
          style={{ color: "var(--color-sentinel-blue)" }}
        />
        <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Loading simulation runs...
        </span>
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div
        className="rounded-md p-8 text-center"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <Activity
          className="h-8 w-8 mx-auto mb-3"
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        />
        <p style={{ color: "var(--color-sentinel-text-secondary)" }}>
          No simulation runs found. Start a simulation from the Control tab.
        </p>
      </div>
    );
  }

  const selectedRun = runs.find((r) => r.run_id === selectedRunId);
  const metrics = analysis?.metrics;
  const profileResults = analysis?.profile_results ?? {};
  const profileKeys = Object.keys(profileResults);

  // Build events-by-hour chart data
  const eventsByHourData = buildEventsByHourData(metrics?.events_by_hour);

  // Build profile scores chart data
  const profileScoresData = buildProfileScoresData(profileResults);

  // Collect unique event types for filter
  const allEventTypes = Array.from(new Set(events.map((e) => e.event_type)));

  // Collect all flags & recommendations across profiles
  const allFlags = profileKeys.flatMap((k) => profileResults[k].flags);
  const allRecs = profileKeys.flatMap((k) =>
    profileResults[k].recommendations.map((r) => ({
      profile: PROFILE_LABELS[k] ?? k,
      text: r,
    }))
  );

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
          <AlertTriangle className="h-5 w-5" style={{ color: "var(--color-sentinel-red)" }} />
          <span style={{ color: "var(--color-sentinel-text-primary)" }}>{error}</span>
        </div>
      )}

      {/* Run Selector */}
      <div
        className="rounded-md p-5"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <label
          className="block text-xs font-medium mb-1"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Select Run
        </label>
        <select
          value={selectedRunId ?? ""}
          onChange={(e) => handleRunChange(e.target.value)}
          className="w-full rounded-md px-3 py-2 text-sm"
          style={{
            background: "var(--color-sentinel-bg-primary)",
            border: "1px solid var(--color-sentinel-border)",
            color: "var(--color-sentinel-text-primary)",
          }}
        >
          {runs.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {r.run_id} &mdash; {r.scenario} ({r.event_count} events)
              {r.ended_at ? "" : " [in progress]"}
            </option>
          ))}
        </select>
        {selectedRun && (
          <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Building: {selectedRun.building_code} | Started:{" "}
            {new Date(selectedRun.started_at).toLocaleString()}
            {selectedRun.duration_minutes != null &&
              ` | Duration: ${selectedRun.duration_minutes.toFixed(1)} min`}
          </p>
        )}
      </div>

      {loadingAnalysis ? (
        <div className="flex items-center justify-center py-12">
          <Activity
            className="h-6 w-6 animate-spin mr-3"
            style={{ color: "var(--color-sentinel-blue)" }}
          />
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Loading analysis...
          </span>
        </div>
      ) : (
        analysis && (
          <>
            {/* KPI Row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <KpiCard
                label="Total Events"
                value={String(metrics?.total_events ?? 0)}
                icon={<Activity className="h-4 w-4" />}
              />
              <KpiCard
                label="Faults / Repaired"
                value={`${metrics?.total_faults ?? 0} / ${metrics?.faults_repaired ?? 0}`}
                icon={<AlertTriangle className="h-4 w-4" />}
                color="var(--color-sentinel-amber)"
              />
              <KpiCard
                label="MTTR"
                value={
                  metrics?.mean_time_to_repair_hours != null
                    ? `${metrics.mean_time_to_repair_hours.toFixed(1)}h`
                    : "N/A"
                }
                icon={<Wrench className="h-4 w-4" />}
              />
              <KpiCard
                label="AI Optimizations"
                value={String(metrics?.ai_optimizations ?? 0)}
                icon={<Zap className="h-4 w-4" />}
                color="var(--color-sentinel-blue)"
              />
            </div>

            {/* Charts Row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Events by Hour */}
              <div
                className="rounded-md p-5 w-full h-80 min-w-0 flex flex-col"
                style={{
                  background: "var(--color-sentinel-bg-panel)",
                  border: "1px solid var(--color-sentinel-border)",
                }}
              >
                <h3
                  className="text-sm font-semibold mb-3"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Events by Hour
                </h3>
                {eventsByHourData.length > 0 ? (
                  <div className="flex-1 w-full min-w-0" style={{ minHeight: "200px" }}>
                    <BarChart
                      data={eventsByHourData}
                      index="hour"
                      categories={["events"]}
                      colors={["blue"]}
                      valueFormatter={(v) => String(v)}
                      showAnimation={true}
                      showLegend={false}
                      className="w-full h-full"
                    />
                  </div>
                ) : (
                  <p
                    className="text-xs text-center py-8 flex-1 flex items-center justify-center"
                    style={{ color: "var(--color-sentinel-text-disabled)" }}
                  >
                    No event data available
                  </p>
                )}
              </div>

              {/* Profile Scores */}
              <div
                className="rounded-md p-5 w-full h-80 min-w-0 flex flex-col"
                style={{
                  background: "var(--color-sentinel-bg-panel)",
                  border: "1px solid var(--color-sentinel-border)",
                }}
              >
                <h3
                  className="text-sm font-semibold mb-3"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Profile Scores
                </h3>
                {profileScoresData.length > 0 ? (
                  <div className="flex-1 w-full min-w-0" style={{ minHeight: "200px" }}>
                    <BarChart
                      data={profileScoresData}
                      index="profile"
                      categories={["score"]}
                      colors={["amber"]}
                      valueFormatter={(v) => v.toFixed(0)}
                      showAnimation={true}
                      showLegend={false}
                      className="w-full h-full"
                    />
                  </div>
                ) : (
                  <p
                    className="text-xs text-center py-8 flex-1 flex items-center justify-center"
                    style={{ color: "var(--color-sentinel-text-disabled)" }}
                  >
                    No profile data available
                  </p>
                )}
              </div>
            </div>

            {/* Component Scores Table */}
            {profileKeys.length > 0 && (
              <div
                className="rounded-md overflow-hidden"
                style={{
                  background: "var(--color-sentinel-bg-panel)",
                  border: "1px solid var(--color-sentinel-border)",
                }}
              >
                <div
                  className="p-4"
                  style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
                >
                  <h3
                    className="text-sm font-semibold"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    Component Scores
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr
                        style={{
                          borderBottom: "1px solid var(--color-sentinel-border)",
                        }}
                      >
                        <th
                          className="text-left px-4 py-2 font-medium"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          Dimension
                        </th>
                        {profileKeys.map((k) => (
                          <th
                            key={k}
                            className="text-right px-4 py-2 font-medium"
                            style={{ color: profileColor(k) }}
                          >
                            {PROFILE_LABELS[k] ?? k}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {["runtime", "comfort", "cost", "maintenance", "energy"].map(
                        (dim) => (
                          <tr
                            key={dim}
                            style={{
                              borderBottom: "1px solid var(--color-sentinel-border)",
                            }}
                          >
                            <td
                              className="px-4 py-2 font-medium"
                              style={{ color: "var(--color-sentinel-text-primary)" }}
                            >
                              {DIMENSION_LABELS[dim] ?? dim}
                            </td>
                            {profileKeys.map((k) => {
                              const score =
                                profileResults[k].component_scores[dim] ?? 0;
                              return (
                                <td
                                  key={k}
                                  className="text-right px-4 py-2 font-mono"
                                  style={{
                                    color: scoreColor(score),
                                  }}
                                >
                                  {score.toFixed(1)}
                                </td>
                              );
                            })}
                          </tr>
                        )
                      )}
                      {/* Overall row */}
                      <tr>
                        <td
                          className="px-4 py-2 font-bold"
                          style={{ color: "var(--color-sentinel-text-primary)" }}
                        >
                          Overall
                        </td>
                        {profileKeys.map((k) => (
                          <td
                            key={k}
                            className="text-right px-4 py-2 font-mono font-bold"
                            style={{ color: profileColor(k) }}
                          >
                            {profileResults[k].overall_score.toFixed(1)}
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Flags & Recommendations */}
            {(allFlags.length > 0 || allRecs.length > 0) && (
              <div
                className="rounded-md p-5"
                style={{
                  background: "var(--color-sentinel-bg-panel)",
                  border: "1px solid var(--color-sentinel-border)",
                }}
              >
                <h3
                  className="text-sm font-semibold mb-3"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Flags & Recommendations
                </h3>
                {allFlags.length > 0 && (
                  <div className="space-y-1 mb-3">
                    {dedup(allFlags).map((f, i) => (
                      <div
                        key={i}
                        className="flex items-start gap-2 text-xs"
                        style={{ color: "var(--color-sentinel-amber)" }}
                      >
                        <AlertTriangle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
                        <span>{f}</span>
                      </div>
                    ))}
                  </div>
                )}
                {allRecs.length > 0 && (
                  <div className="space-y-1">
                    {allRecs.map((r, i) => (
                      <div
                        key={i}
                        className="flex items-start gap-2 text-xs"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        <span style={{ color: "var(--color-sentinel-green)" }}>&#8594;</span>
                        <span>
                          <span
                            className="font-medium"
                            style={{ color: "var(--color-sentinel-text-secondary)" }}
                          >
                            [{r.profile}]
                          </span>{" "}
                          {r.text}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Events Table */}
            <div
              className="rounded-md overflow-hidden"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <div
                className="p-4 flex items-center justify-between"
                style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
              >
                <h3
                  className="text-sm font-semibold"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Events
                </h3>
                <div className="flex items-center gap-2">
                  <Filter
                    className="h-4 w-4"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  />
                  <select
                    value={eventTypeFilter}
                    onChange={(e) => handleEventTypeFilterChange(e.target.value)}
                    className="rounded-md px-2 py-1 text-xs"
                    style={{
                      background: "var(--color-sentinel-bg-primary)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  >
                    <option value="">All types</option>
                    {allEventTypes.map((t) => (
                      <option key={t} value={t}>
                        {EVENT_TYPE_LABELS[t] ?? t}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr
                      style={{
                        borderBottom: "1px solid var(--color-sentinel-border)",
                      }}
                    >
                      <th
                        className="text-left px-4 py-2 font-medium w-16"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
                      >
                        Hour
                      </th>
                      <th
                        className="text-left px-4 py-2 font-medium w-32"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
                      >
                        Type
                      </th>
                      <th
                        className="text-left px-4 py-2 font-medium w-32"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
                      >
                        Equipment
                      </th>
                      <th
                        className="text-left px-4 py-2 font-medium"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
                      >
                        Description
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((ev, i) => (
                      <tr
                        key={i}
                        style={{
                          borderBottom: "1px solid var(--color-sentinel-border)",
                        }}
                      >
                        <td
                          className="px-4 py-2 font-mono"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          {formatHour(ev.simulated_hour)}
                        </td>
                        <td className="px-4 py-2">
                          <span
                            className="px-2 py-0.5 rounded text-xs font-medium"
                            style={{
                              background: eventTypeColor(ev.event_type) + "20",
                              color: eventTypeColor(ev.event_type),
                            }}
                          >
                            {EVENT_TYPE_LABELS[ev.event_type] ?? ev.event_type}
                          </span>
                        </td>
                        <td
                          className="px-4 py-2"
                          style={{ color: "var(--color-sentinel-text-primary)" }}
                        >
                          {ev.equipment_name ?? "-"}
                        </td>
                        <td
                          className="px-4 py-2"
                          style={{ color: "var(--color-sentinel-text-primary)" }}
                        >
                          {ev.description}
                        </td>
                      </tr>
                    ))}
                    {events.length === 0 && (
                      <tr>
                        <td
                          colSpan={4}
                          className="px-4 py-8 text-center"
                          style={{ color: "var(--color-sentinel-text-disabled)" }}
                        >
                          No events found
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {eventsTotal > PAGE_SIZE && (
                <div
                  className="flex items-center justify-between p-3"
                  style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
                >
                  <span
                    className="text-xs"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    {eventsPage * PAGE_SIZE + 1}-
                    {Math.min((eventsPage + 1) * PAGE_SIZE, eventsTotal)} of{" "}
                    {eventsTotal}
                  </span>
                  <div className="flex gap-1">
                    <button
                      onClick={() => setEventsPage((p) => Math.max(0, p - 1))}
                      disabled={eventsPage === 0}
                      className="p-1 rounded"
                      style={{
                        color: "var(--color-sentinel-text-secondary)",
                        opacity: eventsPage === 0 ? 0.3 : 1,
                      }}
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => setEventsPage((p) => p + 1)}
                      disabled={(eventsPage + 1) * PAGE_SIZE >= eventsTotal}
                      className="p-1 rounded"
                      style={{
                        color: "var(--color-sentinel-text-secondary)",
                        opacity:
                          (eventsPage + 1) * PAGE_SIZE >= eventsTotal ? 0.3 : 1,
                      }}
                    >
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )
      )}
    </div>
  );
}

// ============================================================
// Model Health Tab
// ============================================================

function ModelHealthTab({ selectedSiteId: _selectedSiteId }: { selectedSiteId: string }) {
  const [modelStatus, setModelStatus] = useState<ModelStatusResponse | null>(null);
  const [health, setHealth] = useState<ModelHealthSummary | null>(null);
  const [performance, setPerformance] = useState<PerformanceEvaluation | null>(null);
  const [abTests, setAbTests] = useState<ABTest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusData, healthData, perfData, testsData] = await Promise.all([
        fetchModelStatus(),
        fetchModelHealth(),
        fetchPerformance(),
        fetchABTests(),
      ]);
      setModelStatus(statusData);
      setHealth(healthData);
      setPerformance(perfData);
      setAbTests(testsData.tests);
    } catch {
      setError("Failed to load model health data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return <PageLoading message="Loading simulation data..." />;
  }

  const summary = health?.summary;
  const metrics = performance?.metrics;

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
          <AlertTriangle className="h-5 w-5" style={{ color: "var(--color-sentinel-red)" }} />
          <span style={{ color: "var(--color-sentinel-text-primary)" }}>{error}</span>
        </div>
      )}

      {/* Refresh Button */}
      <div className="flex items-center justify-between">
        <div>
          <h3
            className="text-sm font-semibold"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            ML Model Health Overview
          </h3>
          <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Model freshness, prediction accuracy, and A/B test status
          </p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
            color: "var(--color-sentinel-text-primary)",
          }}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>

      {/* Health Summary KPIs */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <KpiCard
            label="Health"
            value={`${summary.health_pct.toFixed(0)}%`}
            icon={<Brain className="h-4 w-4" />}
            color={
              summary.health_pct >= 80
                ? "var(--color-sentinel-green)"
                : summary.health_pct >= 50
                  ? "var(--color-sentinel-amber)"
                  : "var(--color-sentinel-red)"
            }
          />
          <KpiCard
            label="Fresh"
            value={String(summary.fresh)}
            icon={<CheckCircle className="h-4 w-4" />}
            color="var(--color-sentinel-green)"
          />
          <KpiCard
            label="Stale"
            value={String(summary.stale)}
            icon={<Clock className="h-4 w-4" />}
            color={summary.stale > 0 ? "var(--color-sentinel-amber)" : undefined}
          />
          <KpiCard
            label="Missing"
            value={String(summary.missing)}
            icon={<XCircle className="h-4 w-4" />}
            color={summary.missing > 0 ? "var(--color-sentinel-red)" : undefined}
          />
          <KpiCard
            label="Total Slots"
            value={String(summary.total_model_slots)}
            icon={<Activity className="h-4 w-4" />}
          />
        </div>
      )}

      {/* Prediction Performance Metrics */}
      {metrics && (
        <div
          className="rounded-md p-5"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center gap-2 mb-4">
            <Target className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
            <h3
              className="text-sm font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Prediction Accuracy
            </h3>
            {performance?.period_days && (
              <span
                className="text-xs ml-auto"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Last {performance.period_days} days
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricBar label="Accuracy" value={metrics.accuracy} />
            <MetricBar label="Precision" value={metrics.precision} />
            <MetricBar label="Recall" value={metrics.recall} />
            <MetricBar label="F1 Score" value={metrics.f1_score} />
          </div>
          {performance?.confusion_matrix && (
            <div className="mt-4 grid grid-cols-4 gap-2 text-center">
              <div
                className="rounded p-2"
                style={{ background: "var(--color-sentinel-bg-primary)" }}
              >
                <div
                  className="text-lg font-bold"
                  style={{ color: "var(--color-sentinel-green)" }}
                >
                  {performance.confusion_matrix.true_positives}
                </div>
                <div
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  True Pos
                </div>
              </div>
              <div
                className="rounded p-2"
                style={{ background: "var(--color-sentinel-bg-primary)" }}
              >
                <div
                  className="text-lg font-bold"
                  style={{ color: "var(--color-sentinel-red)" }}
                >
                  {performance.confusion_matrix.false_positives}
                </div>
                <div
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  False Pos
                </div>
              </div>
              <div
                className="rounded p-2"
                style={{ background: "var(--color-sentinel-bg-primary)" }}
              >
                <div
                  className="text-lg font-bold"
                  style={{ color: "var(--color-sentinel-amber)" }}
                >
                  {performance.confusion_matrix.false_negatives}
                </div>
                <div
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  False Neg
                </div>
              </div>
              <div
                className="rounded p-2"
                style={{ background: "var(--color-sentinel-bg-primary)" }}
              >
                <div
                  className="text-lg font-bold"
                  style={{ color: "var(--color-sentinel-green)" }}
                >
                  {performance.confusion_matrix.true_negatives}
                </div>
                <div
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  True Neg
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Model Status Table */}
      {modelStatus && modelStatus.models.length > 0 && (
        <div
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
          >
            <h3
              className="text-sm font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Model Status
            </h3>
            <span
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {modelStatus.needs_retrain} of {modelStatus.total_models_checked} need retraining
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                  <th
                    className="text-left px-4 py-2 font-medium"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Model Type
                  </th>
                  <th
                    className="text-left px-4 py-2 font-medium"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Equipment
                  </th>
                  <th
                    className="text-left px-4 py-2 font-medium"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Status
                  </th>
                  <th
                    className="text-right px-4 py-2 font-medium"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Age (days)
                  </th>
                  <th
                    className="text-right px-4 py-2 font-medium"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    R² Score
                  </th>
                  <th
                    className="text-left px-4 py-2 font-medium"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Reason
                  </th>
                </tr>
              </thead>
              <tbody>
                {modelStatus.models.map((m, i) => (
                  <tr
                    key={i}
                    style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
                  >
                    <td
                      className="px-4 py-2 font-mono uppercase"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {m.model_type}
                    </td>
                    <td
                      className="px-4 py-2 capitalize"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {m.equipment_type}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className="px-2 py-0.5 rounded text-xs font-medium"
                        style={{
                          background: modelStatusColor(m.status) + "20",
                          color: modelStatusColor(m.status),
                        }}
                      >
                        {m.status}
                      </span>
                    </td>
                    <td
                      className="text-right px-4 py-2 font-mono"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {m.age_days != null ? m.age_days : "-"}
                    </td>
                    <td
                      className="text-right px-4 py-2 font-mono"
                      style={{
                        color:
                          m.r2_score != null
                            ? m.r2_score >= 0.65
                              ? "var(--color-sentinel-green)"
                              : "var(--color-sentinel-red)"
                            : "var(--color-sentinel-text-disabled)",
                      }}
                    >
                      {m.r2_score != null ? m.r2_score.toFixed(3) : "-"}
                    </td>
                    <td
                      className="px-4 py-2 text-xs"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      {m.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* A/B Tests */}
      {abTests.length > 0 && (
        <div
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div
            className="p-4 flex items-center gap-2"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
          >
            <FlaskConical
              className="h-4 w-4"
              style={{ color: "var(--color-sentinel-blue)" }}
            />
            <h3
              className="text-sm font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              A/B Tests
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                  <th
                    className="text-left px-4 py-2 font-medium"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Test ID
                  </th>
                  <th
                    className="text-left px-4 py-2 font-medium"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Model
                  </th>
                  <th
                    className="text-left px-4 py-2 font-medium"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Control vs Candidate
                  </th>
                  <th
                    className="text-left px-4 py-2 font-medium"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Status
                  </th>
                  <th
                    className="text-left px-4 py-2 font-medium"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Split
                  </th>
                </tr>
              </thead>
              <tbody>
                {abTests.map((t) => (
                  <tr
                    key={t.test_id}
                    style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
                  >
                    <td
                      className="px-4 py-2 font-mono text-xs"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {t.test_id.slice(0, 12)}...
                    </td>
                    <td
                      className="px-4 py-2"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {t.model_type} / {t.equipment_type}
                    </td>
                    <td
                      className="px-4 py-2 text-xs font-mono"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      {t.control_model_id} vs {t.candidate_model_id}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className="px-2 py-0.5 rounded text-xs font-medium"
                        style={{
                          background: abTestStatusColor(t.status) + "20",
                          color: abTestStatusColor(t.status),
                        }}
                      >
                        {t.status}
                      </span>
                    </td>
                    <td
                      className="px-4 py-2"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {Math.round((1 - t.traffic_split) * 100)}/{Math.round(t.traffic_split * 100)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Empty state when no A/B tests */}
      {abTests.length === 0 && !loading && (
        <div
          className="rounded-md p-5"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center gap-2 mb-2">
            <FlaskConical
              className="h-4 w-4"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            />
            <h3
              className="text-sm font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              A/B Tests
            </h3>
          </div>
          <p
            className="text-xs"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            No A/B tests currently running. Tests are created when candidate models are
            ready for comparison against the active production model.
          </p>
        </div>
      )}
    </div>
  );
}

// ---------- MetricBar ----------

function MetricBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 80
      ? "var(--color-sentinel-green)"
      : pct >= 50
        ? "var(--color-sentinel-amber)"
        : "var(--color-sentinel-red)";

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span
          className="text-xs font-medium"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          {label}
        </span>
        <span className="text-xs font-mono font-bold" style={{ color }}>
          {pct}%
        </span>
      </div>
      <div
        className="h-2 rounded-full overflow-hidden"
        style={{ background: "var(--color-sentinel-bg-primary)" }}
      >
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}

// ---------- Model status color helper ----------

function modelStatusColor(status: string): string {
  switch (status) {
    case "fresh":
      return "var(--color-sentinel-green)";
    case "stale":
      return "var(--color-sentinel-amber)";
    case "missing":
      return "var(--color-sentinel-red)";
    case "underperforming":
      return "var(--color-sentinel-red)";
    default:
      return "var(--color-sentinel-text-secondary)";
  }
}

// ---------- A/B test status color helper ----------

function abTestStatusColor(status: string): string {
  switch (status) {
    case "running":
      return "var(--color-sentinel-blue)";
    case "completed":
      return "var(--color-sentinel-green)";
    case "promoted":
      return "var(--color-sentinel-green)";
    case "cancelled":
      return "var(--color-sentinel-text-disabled)";
    default:
      return "var(--color-sentinel-text-secondary)";
  }
}

// ---------- KpiCard ----------

function KpiCard({
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
      className="rounded-md p-4"
      style={{
        background: "var(--color-sentinel-bg-panel)",
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
        className="text-2xl font-bold"
        style={{ color: color ?? "var(--color-sentinel-text-primary)" }}
      >
        {value}
      </div>
    </div>
  );
}

// ---------- Chart data builders ----------

function buildEventsByHourData(
  eventsByHour: Record<string, number> | undefined
): { hour: string; events: number }[] {
  if (!eventsByHour) return [];
  return Object.entries(eventsByHour)
    .map(([h, count]) => ({
      hour: formatHour(Number(h)),
      events: count,
    }))
    .sort((a, b) => a.hour.localeCompare(b.hour));
}

function buildProfileScoresData(
  profileResults: Record<string, { overall_score: number; profile_name: string }>
): { profile: string; score: number }[] {
  return Object.entries(profileResults).map(([key, r]) => ({
    profile: PROFILE_LABELS[key] ?? r.profile_name,
    score: r.overall_score,
  }));
}

// ---------- Color helpers ----------

function profileColor(key: string): string {
  const map: Record<string, string> = {
    asset_sweating: "var(--color-sentinel-amber)",
    comfort_first: "var(--color-sentinel-blue)",
    cost_saving: "var(--color-sentinel-green)",
  };
  return map[key] ?? "var(--color-sentinel-text-primary)";
}

function scoreColor(score: number): string {
  if (score >= 80) return "var(--color-sentinel-green)";
  if (score >= 50) return "var(--color-sentinel-amber)";
  return "var(--color-sentinel-red)";
}

// ---------- Dedup helper ----------

function dedup(arr: string[]): string[] {
  return [...new Set(arr)];
}

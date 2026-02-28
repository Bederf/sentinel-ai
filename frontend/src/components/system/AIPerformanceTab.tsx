/**
 * AI Performance Tab — Optimization performance analytics
 *
 * Extracted from SimulationDashboard AnalyticsTab.
 * Shows past optimization run analysis: KPI cards, events-by-hour chart,
 * profile scores, component dimension breakdown, flags & recommendations,
 * paginated event table with type filtering.
 */

import { useState, useEffect, useCallback } from "react";
import type { ReactElement } from "react";
import {
  Activity,
  AlertTriangle,
  Wrench,
  Zap,
  ChevronLeft,
  ChevronRight,
  Filter,
} from "lucide-react";
import { BarChart } from "@tremor/react";
import {
  fetchRuns,
  fetchRunAnalysis,
  fetchRunEvents,
} from "../../lib/simulationApi";
import type {
  SimulationRunRecord,
  SimulationAnalysisReport,
  SimulationEvent,
} from "../../lib/simulationApi";

// ---------- Constants ----------

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

function dedup(arr: string[]): string[] {
  return [...new Set(arr)];
}

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

// ---------- Main Component ----------

export function AIPerformanceTab() {
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
      .catch(() => setError("Failed to load optimization runs"))
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
          Loading optimization runs...
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
          No optimization runs found yet. Performance data will appear once SENTINEL has processed building data.
        </p>
      </div>
    );
  }

  const selectedRun = runs.find((r) => r.run_id === selectedRunId);
  const metrics = analysis?.metrics;
  const profileResults = analysis?.profile_results ?? {};
  const profileKeys = Object.keys(profileResults);

  const eventsByHourData = buildEventsByHourData(metrics?.events_by_hour);
  const profileScoresData = buildProfileScoresData(profileResults);
  const allEventTypes = Array.from(new Set(events.map((e) => e.event_type)));

  const allFlags = profileKeys.flatMap((k) => profileResults[k]?.flags ?? []);
  const allRecs = profileKeys.flatMap((k) =>
    (profileResults[k]?.recommendations ?? []).map((r) => ({
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
                                profileResults[k]?.component_scores?.[dim] ?? 0;
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
                            {(profileResults[k]?.overall_score ?? 0).toFixed(1)}
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
                      <th className="text-left px-4 py-2 font-medium w-16" style={{ color: "var(--color-sentinel-text-secondary)" }}>Hour</th>
                      <th className="text-left px-4 py-2 font-medium w-32" style={{ color: "var(--color-sentinel-text-secondary)" }}>Type</th>
                      <th className="text-left px-4 py-2 font-medium w-32" style={{ color: "var(--color-sentinel-text-secondary)" }}>Equipment</th>
                      <th className="text-left px-4 py-2 font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>Description</th>
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
                        <td className="px-4 py-2 font-mono" style={{ color: "var(--color-sentinel-text-secondary)" }}>
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
                        <td className="px-4 py-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {ev.equipment_name ?? "-"}
                        </td>
                        <td className="px-4 py-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
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

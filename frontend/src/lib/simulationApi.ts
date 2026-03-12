/**
 * Simulation API Client
 *
 * Lifecycle control + simulation analytics endpoints.
 * Uses shared authorizedFetch from client.ts to benefit from request batching.
 */

import { authorizedFetch } from "./api/client";

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await authorizedFetch(`${API_BASE_URL}${endpoint}`, options);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const err = await res.json();
      msg = err.detail || err.message || JSON.stringify(err);
    } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

// ---------- Types ----------

export interface ScenarioInfo {
  id: string;
  name: string;
  description: string;
  fault_probability: number;
  fault_hour: number | null;
  fault_equipment_type: string | null;
  auto_repair: boolean;
  repair_delay_hours: number;
  optimization_enabled: boolean;
  sentry_notifications: boolean;
}

export interface SimulationStatus {
  running: boolean;
  paused: boolean;
  scenario: string | null;
  simulated_time: string | null;
  simulated_hour: number | null;
  real_elapsed_seconds: number;
  events_count: number;
  active_faults: number;
  pending_repairs: number;
  recent_events: LiveEvent[];
}

export interface LiveEvent {
  hour: number;
  event_type: string;
  description: string;
  equipment_id: string | null;
  equipment_name: string | null;
  details: Record<string, unknown>;
  success: boolean;
  timestamp: string;
}

export interface SimulationRunRecord {
  run_id: string;
  scenario: string;
  site_code: string;
  started_at: string;
  ended_at: string | null;
  duration_minutes: number | null;
  event_count: number;
  events_file: string;
  config: Record<string, unknown>;
}

export interface SimulationEvent {
  timestamp: string;
  simulated_hour: number;
  event_type: string;
  equipment_id: string | null;
  equipment_name: string | null;
  description: string;
  details: Record<string, unknown>;
  success: boolean;
}

export interface SimulationMetrics {
  total_events: number;
  total_faults: number;
  faults_repaired: number;
  mean_time_to_repair_hours: number | null;
  alerts_generated: number;
  work_orders_created: number;
  ai_optimizations: number;
  setpoint_changes: number;
  comfort_deviations: Record<string, unknown>[];
  equipment_runtime_hours: Record<string, number>;
  energy_events: number;
  fault_types: Record<string, number>;
  events_by_hour: Record<string, number>;
}

export interface ProfileAnalysisResult {
  profile_name: string;
  overall_score: number;
  component_scores: Record<string, number>;
  recommendations: string[];
  flags: string[];
}

export interface SimulationAnalysisReport {
  run_id: string;
  scenario: string;
  site_code: string;
  analyzed_at: string;
  metrics: SimulationMetrics;
  profile_results: Record<string, ProfileAnalysisResult>;
}

export interface OptimizationProfile {
  name: string;
  description: string;
  weights: Record<string, number>;
  thresholds: Record<string, number>;
}

// ---------- Lifecycle Control ----------

export async function fetchScenarios(): Promise<ScenarioInfo[]> {
  const data = await fetchJson<{ scenarios: ScenarioInfo[] }>("/api/lifecycle/scenarios");
  return data.scenarios;
}

export async function startSimulation(opts: {
  scenario: string;
  duration_minutes: number;
  start_hour?: number;
}): Promise<{ success: boolean; run_id: string; scenario: string; duration_minutes: number }> {
  return fetchJson("/api/lifecycle/start", {
    method: "POST",
    body: JSON.stringify(opts),
  });
}

export async function stopSimulation(): Promise<{ success: boolean }> {
  return fetchJson("/api/lifecycle/stop", { method: "POST" });
}

export async function pauseSimulation(): Promise<{ success: boolean }> {
  return fetchJson("/api/lifecycle/pause", { method: "POST" });
}

export async function resumeSimulation(): Promise<{ success: boolean }> {
  return fetchJson("/api/lifecycle/resume", { method: "POST" });
}

/** Persist simulation stopped state so it survives restarts. */
export async function setSimulationStopped(stopped: boolean): Promise<{ stopped: boolean }> {
  return fetchJson("/api/settings/simulation", {
    method: "PUT",
    body: JSON.stringify({ stopped }),
  });
}

/** Get persistent simulation stopped state. */
export async function getSimulationStopped(): Promise<{ stopped: boolean }> {
  return fetchJson("/api/settings/simulation");
}

export async function changeSimulationSpeed(
  speedMultiplier: number
): Promise<{ success: boolean; speed: number; seconds_per_hour: number }> {
  return fetchJson("/api/lifecycle/speed", {
    method: "POST",
    body: JSON.stringify({ speed_multiplier: speedMultiplier }),
  });
}

export async function getSimulationStatus(): Promise<SimulationStatus> {
  return fetchJson("/api/lifecycle/status");
}

export async function getSimulationEvents(opts?: {
  event_type?: string;
  limit?: number;
}): Promise<{ count: number; events: LiveEvent[] }> {
  const params = new URLSearchParams();
  if (opts?.event_type) params.set("event_type", opts.event_type);
  if (opts?.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return fetchJson(`/api/lifecycle/events${qs ? `?${qs}` : ""}`);
}

// ---------- ML Retraining Types ----------

export interface ModelCheckResult {
  model_type: string;
  equipment_type: string;
  model_id?: string;
  status: "fresh" | "stale" | "missing" | "underperforming";
  age_days: number | null;
  r2_score: number | null;
  needs_retrain: boolean;
  reason: string;
}

export interface ModelStatusResponse {
  total_models_checked: number;
  needs_retrain: number;
  models: ModelCheckResult[];
}

export interface PerformanceMetrics {
  accuracy: number;
  precision: number;
  recall: number;
  f1_score: number;
}

export interface PerformanceEvaluation {
  evaluated_at: string;
  period_days: number;
  site_code: string;
  predictions_count: number;
  alerts_count: number;
  metrics: PerformanceMetrics;
  confusion_matrix: {
    true_positives: number;
    false_positives: number;
    false_negatives: number;
    true_negatives: number;
  };
  error?: string;
}

export interface ModelHealthSummary {
  summary: {
    total_model_slots: number;
    fresh: number;
    stale: number;
    missing: number;
    underperforming: number;
    health_pct: number;
  };
  latest_evaluation: PerformanceEvaluation | null;
  models: ModelCheckResult[];
  evaluated_at: string;
}

export interface ABTest {
  test_id: string;
  model_type: string;
  equipment_type: string;
  control_model_id: string;
  candidate_model_id: string;
  status: string;
  traffic_split: number;
  created_at: string;
}

// ---------- ML Retraining Endpoints ----------

export async function fetchModelStatus(): Promise<ModelStatusResponse> {
  return fetchJson("/api/ml-retraining/status");
}

export async function fetchModelHealth(): Promise<ModelHealthSummary> {
  return fetchJson("/api/ml-retraining/performance/health");
}

export async function fetchPerformance(opts?: {
  days_back?: number;
  site_code?: string;
}): Promise<PerformanceEvaluation> {
  const params = new URLSearchParams();
  if (opts?.days_back) params.set("days_back", String(opts.days_back));
  if (opts?.site_code) params.set("site_code", opts.site_code);
  const qs = params.toString();
  return fetchJson(`/api/ml-retraining/performance${qs ? `?${qs}` : ""}`);
}

export async function fetchABTests(): Promise<{ tests: ABTest[] }> {
  return fetchJson("/api/ml-retraining/ab-tests");
}

// ---------- Analytics ----------

export async function fetchRuns(): Promise<SimulationRunRecord[]> {
  const data = await fetchJson<{ runs: SimulationRunRecord[]; count: number }>(
    "/api/simulation-analytics/runs"
  );
  return data.runs;
}

export async function fetchRunAnalysis(runId: string): Promise<SimulationAnalysisReport> {
  return fetchJson(`/api/simulation-analytics/runs/${runId}/analysis`);
}

export async function fetchRunEvents(
  runId: string,
  opts?: { event_type?: string; offset?: number; limit?: number }
): Promise<{ run_id: string; events: SimulationEvent[]; count: number; offset: number; limit: number }> {
  const params = new URLSearchParams();
  if (opts?.event_type) params.set("event_type", opts.event_type);
  if (opts?.offset != null) params.set("offset", String(opts.offset));
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return fetchJson(`/api/simulation-analytics/runs/${runId}/events${qs ? `?${qs}` : ""}`);
}

export async function fetchProfiles(): Promise<Record<string, OptimizationProfile>> {
  const data = await fetchJson<{ profiles: Record<string, OptimizationProfile>; count: number }>(
    "/api/simulation-analytics/profiles"
  );
  return data.profiles;
}

/**
 * Fleet Learning API Client
 *
 * Endpoints for fleet aggregation, global models, fine-tuning, and benchmarking.
 * Phase 45-02: Fleet Learning and Cross-Site Insights.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || window.location.origin;

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("sentinel_token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: { ...authHeaders(), ...options?.headers },
  });
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

export interface FleetOverview {
  total_sites: number;
  total_equipment: number;
  avg_fleet_health: number;
  total_open_alerts: number;
  monthly_maintenance_zar: number;
  failure_patterns_tracked: number;
  total_recorded_failures: number;
}

export interface TopFailurePattern {
  equipment_type: string;
  failure_type: string;
  count: number;
  sites_affected: number;
}

export interface FleetSummary {
  fleet_overview: FleetOverview;
  type_distribution: Record<string, { failures: number; total_cost_zar: number }>;
  top_failure_patterns: TopFailurePattern[];
  last_aggregation: string;
}

export interface FailurePattern {
  equipment_type: string;
  failure_type: string;
  occurrence_count: number;
  avg_age_at_failure_years: number;
  avg_health_at_detection: number;
  common_precursors: string[];
  avg_repair_cost_zar: number;
  avg_downtime_hours: number;
  sites_affected: number;
}

export interface RiskDistribution {
  total_equipment: number;
  distribution: {
    critical: { count: number; percentage: number };
    high: { count: number; percentage: number };
    medium: { count: number; percentage: number };
    low: { count: number; percentage: number };
  };
  sites_with_critical: number;
  total_sites: number;
}

export interface Benchmark {
  equipment_type: string;
  fleet_avg_health: number;
  fleet_avg_mtbf_days: number;
  fleet_avg_maintenance_cost_zar: number;
  fleet_best_health: number;
  fleet_worst_health: number;
  total_equipment_count: number;
  total_sites: number;
}

export interface SiteBenchmark {
  site_health: number;
  fleet_avg_health: number;
  fleet_best: number;
  fleet_worst: number;
  percentile: number;
  status: string;
  message: string;
  equipment_type: string;
  benchmarks: Benchmark[];
}

export interface GlobalModel {
  model_id: string;
  model_type: string;
  equipment_type: string;
  variant: string;
  sites_included: number;
  samples_used: number;
  metrics: { r2_score: number; mae: number; rmse: number };
  trained_at: string;
  status: string;
}

export interface FineTunedModel {
  model_id: string;
  site_code: string;
  model_type: string;
  equipment_type: string;
  variant: string;
  global_model_id: string;
  metrics: { r2_score: number; mae: number; rmse: number };
  global_metrics: { r2_score: number; mae: number; rmse: number };
  improvement: { r2_score: number; r2_pct: number };
  samples_used: number;
  fine_tuned_at: string;
  status: string;
}

export interface ImprovementSummary {
  models_count: number;
  avg_improvement_pct: number;
  max_improvement_pct: number;
  min_improvement_pct: number;
  site_code: string;
  best_model: FineTunedModel | null;
}

// ---------- API ----------

export const fleetApi = {
  getSummary: () =>
    fetchJson<FleetSummary>("/api/fleet/summary"),

  getFailurePatterns: (equipmentType?: string) => {
    const params = equipmentType ? `?equipment_type=${equipmentType}` : "";
    return fetchJson<{ patterns: FailurePattern[]; total: number }>(
      `/api/fleet/failure-patterns${params}`
    );
  },

  getRiskDistribution: () =>
    fetchJson<RiskDistribution>("/api/fleet/risk-distribution"),

  getBenchmarks: (equipmentType?: string) => {
    const params = equipmentType ? `?equipment_type=${equipmentType}` : "";
    return fetchJson<{ benchmarks: Benchmark[]; total: number }>(
      `/api/fleet/benchmarks${params}`
    );
  },

  benchmarkSite: (siteCode: string, siteHealth: number, equipmentType?: string) => {
    const params = new URLSearchParams({
      site_code: siteCode,
      site_health: siteHealth.toString(),
    });
    if (equipmentType) params.set("equipment_type", equipmentType);
    return fetchJson<SiteBenchmark>(
      `/api/fleet/benchmark-site?${params.toString()}`
    );
  },

  getGlobalModels: (modelType?: string, equipmentType?: string) => {
    const params = new URLSearchParams();
    if (modelType) params.set("model_type", modelType);
    if (equipmentType) params.set("equipment_type", equipmentType);
    const qs = params.toString();
    return fetchJson<{ models: GlobalModel[]; total: number }>(
      `/api/fleet/global-models${qs ? `?${qs}` : ""}`
    );
  },

  getFineTunedModels: (siteCode?: string) => {
    const params = siteCode ? `?site_code=${siteCode}` : "";
    return fetchJson<{ models: FineTunedModel[]; total: number }>(
      `/api/fleet/fine-tuned${params}`
    );
  },

  getImprovementSummary: (siteCode?: string) => {
    const params = siteCode ? `?site_code=${siteCode}` : "";
    return fetchJson<ImprovementSummary>(
      `/api/fleet/fine-tuned/improvement${params}`
    );
  },
};

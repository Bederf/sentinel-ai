/**
 * MLOps Monitoring API Client
 *
 * Endpoints for drift detection, ML alerting, success metrics,
 * and automated reporting.
 * Phase 45-03: MLOps Monitoring and Success Metrics.
 */

import { getAccessToken } from "./api";
const API_BASE_URL = import.meta.env.VITE_API_URL || window.location.origin;

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const token = getAccessToken();
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
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

export interface MetricValue {
  current: number;
  target: number;
  unit: string;
  met: boolean;
  inverse?: boolean;
  description: string;
}

export interface SuccessMetrics {
  calculated_at: string;
  metrics: {
    unplanned_failure_reduction: MetricValue;
    maintenance_planning_accuracy: MetricValue;
    false_positive_rate: MetricValue;
    mean_time_to_detect: MetricValue;
    prediction_lead_time: MetricValue;
  };
  overall_score: number;
  targets_met: number;
  total_targets: number;
}

export interface DriftResult {
  equipment_type?: string;
  model_type?: string;
  detected_at: string;
  drift_detected: boolean;
  feature_drift_scores?: Record<string, number>;
  drifted_features?: string[];
  features_checked?: number;
  features_drifted?: number;
  recent_accuracy?: number;
  historical_accuracy?: number;
  degradation_pct?: number;
}

export interface AllDriftResult {
  detected_at: string;
  summary: {
    equipment_types_checked: number;
    equipment_types_with_drift: number;
    model_types_checked: number;
    model_types_with_drift: number;
    any_drift_detected: boolean;
  };
  feature_drift: DriftResult[];
  model_drift: DriftResult[];
}

export interface MLAlert {
  id: string;
  alert_type: string;
  severity: string;
  title: string;
  message: string;
  source: string;
  metadata: Record<string, unknown>;
  created_at: string;
  acknowledged: boolean;
  acknowledged_at: string | null;
}

export interface AlertSummary {
  total_alerts: number;
  unacknowledged: number;
  by_severity: Record<string, number>;
  by_type: Record<string, number>;
  checked_at: string;
}

export interface MLOpsHealth {
  status: string;
  checked_at: string;
  overall_score: number;
  targets_met: number;
  total_targets: number;
  critical_alerts: number;
  drift_detected: boolean;
  metrics_summary: Record<string, { current: number; target: number; met: boolean }>;
  alert_summary: AlertSummary;
}

export interface PerformanceReport {
  report_id: string;
  period: string;
  period_label: string;
  start_date: string;
  end_date: string;
  generated_at: string;
  success_metrics: Record<string, MetricValue>;
  overall_score: number;
  targets_met: number;
  total_targets: number;
  drift_summary: Record<string, unknown>;
  model_health: Record<string, unknown>;
  alert_summary: AlertSummary;
  prediction_outcomes: {
    total: number;
    correct: number;
    true_positives: number;
    false_positives: number;
    false_negatives: number;
  };
  recommendations: Array<{ priority: string; area: string; action: string }>;
}

// ---------- API Functions ----------

export const mlopsApi = {
  // Health
  getHealth: () => fetchJson<MLOpsHealth>("/api/mlops/health"),

  // Metrics
  getMetrics: () => fetchJson<SuccessMetrics>("/api/mlops/metrics"),
  getMetricsTrend: (limit = 30) =>
    fetchJson<{ trend: SuccessMetrics[] }>(`/api/mlops/metrics/trend?limit=${limit}`),

  // Drift
  getAllDrift: () => fetchJson<AllDriftResult>("/api/mlops/drift/all"),
  getFeatureDrift: (equipmentType: string) =>
    fetchJson<DriftResult>(`/api/mlops/drift/feature/${equipmentType}`),
  getModelDrift: (modelType: string) =>
    fetchJson<DriftResult>(`/api/mlops/drift/model/${modelType}`),

  // Alerts
  getAlerts: (params?: { severity?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.severity) qs.set("severity", params.severity);
    if (params?.limit) qs.set("limit", String(params.limit));
    return fetchJson<{ alerts: MLAlert[] }>(`/api/mlops/alerts?${qs}`);
  },
  getAlertSummary: () => fetchJson<AlertSummary>("/api/mlops/alerts/summary"),
  runAlertCheck: () =>
    fetchJson<{ new_alerts: number; alerts: MLAlert[] }>("/api/mlops/alerts/check", {
      method: "POST",
    }),
  acknowledgeAlert: (alertId: string) =>
    fetchJson<{ acknowledged: boolean }>(`/api/mlops/alerts/${alertId}/acknowledge`, {
      method: "POST",
    }),

  // Triggers
  evaluateTriggers: () =>
    fetchJson<Record<string, unknown>>("/api/mlops/triggers/evaluate", {
      method: "POST",
    }),

  // Reports
  generateReport: (period: "weekly" | "monthly") =>
    fetchJson<PerformanceReport>(`/api/mlops/reports/${period}`),
};

/**
 * System Health & Diagnostics API Client
 *
 * Provides access to unified system health monitoring, historical trends,
 * and SIMBIOT-powered diagnostics.
 */

import React from 'react';
import { fetchApi } from './client';

export interface ComponentHealth {
  name: string;
  status: 'healthy' | 'degraded' | 'critical';
  score: number;  // 0-100
  message?: string;
  details?: Record<string, any>;
}

export interface SystemHealthSnapshot {
  timestamp: string;
  overall_status: 'healthy' | 'degraded' | 'critical';
  overall_score: number;  // 0-100
  components: Record<string, ComponentHealth>;
  active_alerts: Array<any>;
  recommendations: string[];
}

export interface DiagnosticResult {
  diagnostic_id: string;
  timestamp: string;
  target: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  duration_seconds?: number;
  device_inventory?: Record<string, any>;
  building_config?: Record<string, any>;
  alarms_found?: Array<any>;
  health_scores?: Record<string, number>;
  asset_details?: Array<any>;
  issues_found: string[];
  recommendations: string[];
  next_steps: string[];
  error_message?: string;
}

export interface ErrorLog {
  id: string;
  timestamp: string;
  category: 'bms' | 'api' | 'database' | 'service' | 'other';
  severity: 'warning' | 'error' | 'critical';
  component: string;
  message: string;
  details?: Record<string, any>;
  resolved: boolean;
  resolved_at?: string;
}

export interface ErrorLogFilters {
  category?: string;
  severity?: string;
  resolved?: boolean;
  limit?: number;
  offset?: number;
}

export interface ErrorLogResponse {
  total: number;
  logs: ErrorLog[];
  page: number;
  page_size: number;
}

export interface HealthHistoryData {
  range: '24h' | '7d' | '30d';
  snapshots: Array<{
    timestamp: string;
    overall_score: number;
    overall_status: string;
  }>;
  metrics: {
    avg_score: number;
    min_score: number;
    max_score: number;
    uptime_percentage: number;
    trend: 'improving' | 'stable' | 'degrading' | 'unknown';
  };
  snapshot_count: number;
}

export interface CommissioningSnapshot {
  ingestion_mode: string;
  all_gates_passed: boolean;
  blocking_gates: string[];
  gates_passed: number;
  gates_total: number;
  consecutive_pass_days: number;
  can_promote: boolean;
  stage_calendar_days?: number;
}

export interface QualityMetricDetail {
  metric: string;
  value: number | null;
  state: 'pass' | 'warn' | 'fail' | 'na';
  pass_bound: number | null;
  warn_bound: number | null;
}

export interface QualityGateStatus {
  overall_status: 'pass' | 'warn' | 'fail';
  enforcement_action: string;
  mode: string;
  failed_rules: string[];
  warn_rules: string[];
  reason_codes: string[];
  rule_results: QualityMetricDetail[];
}

export interface IngestionKPIs {
  freshness_hours: number;
  error_rate: number;
  match_coverage: number;
  unmatched_points: number;
  total_points: number;
}

export interface ControlKPIs {
  shadow_writes_24h: number;
  blocked_writes_24h: number;
  approved_writes_24h: number;
  safety_violations_24h: number;
}

export interface MlReadinessThreshold {
  pass_bound: number | null;
  warn_bound: number | null;
  direction: string;
}

export interface MlReadinessMetric {
  metric: string;
  value: number | null;
  state: 'pass' | 'warn' | 'fail' | 'na';
  threshold: MlReadinessThreshold;
}

export interface MlTrainingReadiness {
  ready: boolean;
  overall: 'pass' | 'warn' | 'fail' | 'unknown';
  blocking_metrics: string[];
  telemetry_results: MlReadinessMetric[];
  evaluated_at: string | null;
  error?: string;
}

/**
 * System health API client
 */
export const systemApi = {
  /**
   * Get current unified system health snapshot
   */
  async getCurrentHealth(): Promise<SystemHealthSnapshot> {
    return fetchApi<SystemHealthSnapshot>('/api/system/health');
  },

  /**
   * Get historical health data for trend analysis
   */
  async getHealthHistory(range: '24h' | '7d' | '30d'): Promise<HealthHistoryData> {
    return fetchApi<HealthHistoryData>(`/api/system/health/history?range=${range}`);
  },

  /**
   * Trigger SIMBIOT diagnostics workflow
   *
   * Returns immediately with diagnostic_id for polling.
   * Client should poll getDiagnosticResults() every 5 seconds until complete.
   */
  async runDiagnostics(target: string = 'full_system', siteCode?: string): Promise<{ diagnostic_id: string; status: string }> {
    return fetchApi<{ diagnostic_id: string; status: string }>('/api/system/diagnostics', {
      method: 'POST',
      body: JSON.stringify({ target, site_code: siteCode }),
    });
  },

  /**
   * Poll diagnostic results by ID
   *
   * Returns current status and partial/complete results as they're available.
   * Keep polling until status is 'completed' or 'failed'.
   */
  async getDiagnosticResults(diagnosticId: string): Promise<DiagnosticResult> {
    return fetchApi<DiagnosticResult>(`/api/system/diagnostics/${diagnosticId}`);
  },

  /**
   * Get error logs with optional filtering
   */
  async getErrorLogs(filters?: ErrorLogFilters): Promise<ErrorLogResponse> {
    const params = new URLSearchParams();
    if (filters) {
      if (filters.category) params.append('category', filters.category);
      if (filters.severity) params.append('severity', filters.severity);
      if (filters.resolved !== undefined) params.append('resolved', String(filters.resolved));
      if (filters.limit) params.append('limit', String(filters.limit));
      if (filters.offset !== undefined) params.append('offset', String(filters.offset));
    }
    const query = params.toString();
    const url = query ? `/api/system/error-logs?${query}` : '/api/system/error-logs';
    return fetchApi<ErrorLogResponse>(url);
  },
};

/**
 * Hook for using system health with auto-refresh
 */
export function useSystemHealth(autoRefreshMs: number = 30000) {
  const [health, setHealth] = React.useState<SystemHealthSnapshot | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const fetchHealth = React.useCallback(async () => {
    try {
      setLoading(true);
      const data = await systemApi.getCurrentHealth();
      setHealth(data);
      setError(null);
    } catch (err) {
      setError('Failed to load system health');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, autoRefreshMs);
    return () => clearInterval(interval);
  }, [autoRefreshMs, fetchHealth]);

  return { health, loading, error, refresh: fetchHealth };
}

/**
 * Hook for polling diagnostics results
 */
export function useDiagnostics() {
  const [result, setResult] = React.useState<DiagnosticResult | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [diagnosticId, setDiagnosticId] = React.useState<string | null>(null);

  const runDiagnostics = async (target: string = 'full_system', siteCode?: string) => {
    setLoading(true);
    try {
      const { diagnostic_id } = await systemApi.runDiagnostics(target, siteCode);
      setDiagnosticId(diagnostic_id);

      // Start polling for results
      const pollResults = async () => {
        try {
          const result = await systemApi.getDiagnosticResults(diagnostic_id);
          setResult(result);

          // Continue polling if still running
          if (result.status === 'pending' || result.status === 'running') {
            setTimeout(pollResults, 5000);
          } else {
            setLoading(false);
          }
        } catch (err) {
          console.error('Error polling diagnostics:', err);
          setLoading(false);
        }
      };

      await pollResults();
    } catch (err) {
      console.error('Diagnostics failed:', err);
      setLoading(false);
    }
  };

  return { result, loading, diagnosticId, runDiagnostics };
}

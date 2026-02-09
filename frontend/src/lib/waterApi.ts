/**
 * Water Meter API Client
 *
 * Fetches water consumption data from backend:
 *  - Current flow rate
 *  - Consumption history (daily, weekly, monthly)
 *  - Leak alerts (active, resolved, by severity)
 *  - Trending analysis (period comparisons)
 *  - Meter metadata and configuration
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("sentinel_token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: authHeaders(),
    ...options,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const err = await res.json();
      msg = err.detail || err.message || JSON.stringify(err);
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

// ============= Type Interfaces =============

/** Water meter installation details */
export interface WaterMeter {
  meter_id: string;
  site: string;
  location?: string;
  pulse_weight: number; // Liters per pulse
  installation_date: string; // ISO date
  status: "active" | "inactive" | "maintenance";
  last_reading_date?: string;
  total_volume_liters?: number;
}

/** Water consumption reading */
export interface WaterConsumption {
  timestamp: string; // ISO datetime
  volume_liters: number;
  flow_rate_lpm?: number; // Liters per minute
  meter_id: string;
}

/** Leak alert with severity and resolution status */
export interface WaterAlert {
  alert_id: string;
  site: string;
  alert_type: "continuous_flow" | "unusual_pattern" | "spike" | "night_flow";
  severity: "low" | "medium" | "high" | "critical";
  timestamp: string; // ISO datetime
  status?: "active" | "acknowledged" | "resolved" | "false_positive";
  resolution?: {
    timestamp: string;
    resolved_by: string;
    notes: string;
  };
  details: {
    flow_rate_lpm?: number;
    duration_minutes?: number;
    baseline_flow_lpm?: number;
    percent_above_baseline?: number;
    location?: string;
  };
}

/** Trending data for period comparisons */
export interface WaterTrending {
  site: string;
  period: string;
  start_date: string;
  end_date: string;
  total_volume_liters: number;
  average_flow_rate_lpm: number;
  peak_flow_rate_lpm: number;
  baseline_comparison_percent: number;
  trend_direction: "up" | "down" | "stable";
  record_count: number;
}

/** Current flow rate response */
export interface CurrentFlowResponse {
  site: string;
  flow_rate_lpm: number;
  timestamp: string;
  meter_id: string;
}

// ============= API Methods =============

/**
 * Get current flow rate for a site
 * GET /api/water/sites/{site}/flow
 */
export async function getCurrentFlow(site: string): Promise<CurrentFlowResponse> {
  return fetchJson<CurrentFlowResponse>(`/api/water/sites/${site}/flow`);
}

/**
 * Get consumption history for a site
 * GET /api/water/sites/{site}/consumption?start_date={start}&end_date={end}
 */
export async function getConsumption(
  site: string,
  start_date?: string,
  end_date?: string
): Promise<WaterConsumption[]> {
  const params = new URLSearchParams();
  if (start_date) params.set("start_date", start_date);
  if (end_date) params.set("end_date", end_date);

  const query = params.toString() ? `?${params}` : "";
  const response = await fetchJson<{ site: string; meter_id: string | null; record_count: number; consumption: WaterConsumption[] }>(`/api/water/sites/${site}/consumption${query}`);
  return response.consumption;
}

/**
 * Get all alerts for a site (optional severity filter)
 * GET /api/water/sites/{site}/alerts?severity={severity}&status={status}
 */
export async function getAlerts(
  site: string,
  options?: {
    severity?: "low" | "medium" | "high" | "critical";
    start_date?: string;
    end_date?: string;
    status?: string;
  }
): Promise<WaterAlert[]> {
  const params = new URLSearchParams();
  if (options?.severity) params.set("severity", options.severity);
  if (options?.start_date) params.set("start_date", options.start_date);
  if (options?.end_date) params.set("end_date", options.end_date);
  if (options?.status !== undefined) params.set("status", options.status);

  const query = params.toString() ? `?${params}` : "";
  const response = await fetchJson<{ site: string; alert_count: number; alerts: WaterAlert[] }>(`/api/water/sites/${site}/alerts${query}`);
  return response.alerts;
}

/**
 * Get active (unresolved) alerts for a site
 * GET /api/water/sites/{site}/alerts/active
 */
export async function getActiveAlerts(site: string): Promise<WaterAlert[]> {
  const response = await fetchJson<{ site: string; active_alert_count: number; alerts: WaterAlert[] }>(`/api/water/sites/${site}/alerts/active`);
  return response.alerts;
}

/**
 * Resolve an alert with resolution notes
 * PATCH /api/water/alerts/{alertId}/resolve?resolved_by={user}&resolution_notes={notes}
 */
export async function resolveAlert(
  alertId: string,
  resolution: { notes: string; resolved_by: string }
): Promise<void> {
  const params = new URLSearchParams({
    resolved_by: resolution.resolved_by,
    resolution_notes: resolution.notes,
  });
  await fetchJson<void>(`/api/water/alerts/${alertId}/resolve?${params}`, {
    method: "PATCH",
  });
}

/**
 * Get trending analysis for a site
 * GET /api/water/sites/{site}/trending?period={period}
 */
export async function getTrending(
  site: string,
  period: "day" | "week" | "month" = "week"
): Promise<WaterTrending> {
  return fetchJson<WaterTrending>(`/api/water/sites/${site}/trending?period=${period}`);
}

/**
 * Get meter metadata for a site
 * GET /api/water/sites/{site}/meters
 */
export async function getMeters(site: string): Promise<WaterMeter[]> {
  return fetchJson<WaterMeter[]>(`/api/water/sites/${site}/meters`);
}

// ============= Export API Client Object =============

export const waterApi = {
  getCurrentFlow,
  getConsumption,
  getAlerts,
  getActiveAlerts,
  resolveAlert,
  getTrending,
  getMeters,
};

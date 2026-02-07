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
  alert_type: "continuous_flow" | "unusual_pattern" | "high_flow" | "no_flow";
  severity: "critical" | "warning" | "info";
  timestamp: string; // ISO datetime
  resolved: boolean;
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
  period: "daily" | "weekly" | "monthly";
  current_period: {
    start: string;
    end: string;
    total_volume_liters: number;
    average_daily_liters: number;
  };
  previous_period: {
    start: string;
    end: string;
    total_volume_liters: number;
    average_daily_liters: number;
  };
  comparison_percent: number; // Positive = increase, negative = decrease
  trend: "increasing" | "decreasing" | "stable";
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
  return fetchJson<WaterConsumption[]>(`/api/water/sites/${site}/consumption${query}`);
}

/**
 * Get all alerts for a site (optional severity filter)
 * GET /api/water/sites/{site}/alerts?severity={severity}&resolved={resolved}
 */
export async function getAlerts(
  site: string,
  options?: {
    severity?: "critical" | "warning" | "info";
    start_date?: string;
    end_date?: string;
    resolved?: boolean;
  }
): Promise<WaterAlert[]> {
  const params = new URLSearchParams();
  if (options?.severity) params.set("severity", options.severity);
  if (options?.start_date) params.set("start_date", options.start_date);
  if (options?.end_date) params.set("end_date", options.end_date);
  if (options?.resolved !== undefined) params.set("resolved", String(options.resolved));

  const query = params.toString() ? `?${params}` : "";
  return fetchJson<WaterAlert[]>(`/api/water/sites/${site}/alerts${query}`);
}

/**
 * Get active (unresolved) alerts for a site
 * GET /api/water/sites/{site}/alerts/active
 */
export async function getActiveAlerts(site: string): Promise<WaterAlert[]> {
  return fetchJson<WaterAlert[]>(`/api/water/sites/${site}/alerts/active`);
}

/**
 * Resolve an alert with resolution notes
 * POST /api/water/alerts/{alertId}/resolve
 */
export async function resolveAlert(
  alertId: string,
  resolution: { notes: string; resolved_by: string }
): Promise<void> {
  await fetchJson<void>(`/api/water/alerts/${alertId}/resolve`, {
    method: "POST",
    body: JSON.stringify(resolution),
  });
}

/**
 * Get trending analysis for a site
 * GET /api/water/sites/{site}/trending?period={period}
 */
export async function getTrending(
  site: string,
  period: "daily" | "weekly" | "monthly" = "weekly"
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

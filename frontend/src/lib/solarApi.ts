/**
 * Solar PV & BESS API Client
 *
 * Fetches solar installation data from backend:
 *  - Site overview (generation, BESS, grid flow)
 *  - Inverter fleet status
 *  - BESS container status
 *  - Performance metrics (PR, trends)
 *  - Diagnostics (issues, cost impact)
 *  - Grid compliance (NRS 097-2-1)
 *  - Financial summary (savings breakdown, ROI)
 *  - Maintenance schedule (PPM calendar, recommendations)
 *  - Forecast vs actual overlay (48-hour chart data)
 */

import { authorizedFetch } from "./api";
const API_BASE_URL = import.meta.env.VITE_API_URL || window.location.origin;

function normalizeSiteId(siteId: string): string {
  // Legacy alias normalization removed — site IDs are resolved from registered buildings
  return siteId;
}

async function fetchJson<T>(endpoint: string): Promise<T> {
  try {
    const res = await authorizedFetch(`${API_BASE_URL}${endpoint}`, {
      headers: { "Content-Type": "application/json" },
    }, true);
    if (!res.ok) {
      let msg = res.statusText;
      try {
        const err = await res.json();
        msg = err.detail || err.message || JSON.stringify(err);
      } catch {
        /* ignore */
      }
      throw { message: msg, status: res.status } as { message: string; status: number };
    }
    return res.json();
  } catch (err) {
    // If API fails, log and re-throw (components will show seeded data)
    console.debug(`Solar API failed for ${endpoint}:`, err);
    throw err;
  }
}

// ============= Response Interfaces =============

/** Site overview returned by GET /api/solar/sites/{siteId}/overview */
export interface SolarOverview {
  site_id: string;
  site_name: string;
  installed_capacity_kwp: number;
  current_generation_kw: number;
  daily_yield_kwh: number;
  expected_daily_yield_kwh: number;
  performance_ratio: number;
  bess_soc_percent: number;
  bess_mode: string;
  grid_import_kw: number;
  grid_export_kw: number;
  self_consumption_percent: number;
  estimated_savings_today_zar: number;
  plants: SolarPlant[];
}

export interface SolarPlant {
  plant_id: string;
  plant_name: string;
  capacity_kwp: number;
  current_generation_kw: number;
  inverter_count: number;
  status: "normal" | "warning" | "fault";
}

/** Single inverter returned inside inverter list */
export interface SolarInverter {
  inverter_id: string;
  name: string;
  manufacturer: string;
  model: string;
  plant_id: string;
  plant_name: string;
  rated_power_kw: number;
  current_power_kw: number;
  daily_yield_kwh: number;
  efficiency_percent: number;
  temperature_c: number;
  status: "normal" | "warning" | "fault" | "offline";
  mppt_count: number;
  string_count: number;
}

/** Inverter list response */
export interface InverterListResponse {
  site_id: string;
  inverter_count: number;
  inverters: SolarInverter[];
}

/** BESS container status */
export interface BESSStatus {
  bess_id: string;
  name: string;
  manufacturer: string;
  model: string;
  total_capacity_kwh: number;
  usable_capacity_kwh: number;
  soc_percent: number;
  soh_percent: number;
  mode: "charging" | "discharging" | "idle" | "standby" | "fault";
  charge_power_kw: number;
  discharge_power_kw: number;
  current_power_kw: number;
  temperature_c: number;
  cycle_count: number;
  estimated_runtime_min: number;
  rack_count: number;
  alarms: string[];
  status: "normal" | "warning" | "fault";
}

/** Performance metrics from GET /api/solar/sites/{siteId}/performance */
export interface PerformanceMetrics {
  site_id: string;
  period: string;
  performance_ratio: number;
  pr_rating: "excellent" | "good" | "acceptable" | "poor";
  target_pr: number;
  trend_direction: "up" | "down" | "stable";
  total_generation_kwh: number;
  expected_generation_kwh: number;
  irradiance_kwh_m2: number;
}

/** Diagnostic issue */
export interface DiagnosticIssue {
  issue_id: string;
  severity: "critical" | "high" | "medium" | "low";
  category: string;
  equipment_id: string;
  equipment_name: string;
  description: string;
  probable_cause: string;
  recommended_action: string;
  confidence: number;
  estimated_cost_impact_zar: number;
}

/** Diagnostic report */
export interface DiagnosticReport {
  site_id: string;
  timestamp: string;
  overall_health: "healthy" | "attention" | "critical";
  issue_count: number;
  issues: DiagnosticIssue[];
  total_cost_impact_zar: number;
}

/** Compliance status */
export interface ComplianceStatus {
  site_id: string;
  overall_status: "compliant" | "warning" | "violation";
  voltage: { status: string; details: string };
  frequency: { status: string; details: string };
  power_quality: { status: string; details: string };
  export_limit: { status: string; details: string };
  certificates: { status: string; details: string };
  last_checked: string;
}

/** Monthly financial savings breakdown */
export interface MonthlyFinancial {
  year: number;
  month: number;
  month_name: string;
  arbitrage_zar: number;
  demand_charge_zar: number;
  self_consumption_zar: number;
  diesel_avoidance_zar: number;
  total_savings_zar: number;
}

/** Financial summary with YTD totals and ROI */
export interface FinancialSummary {
  site_id: string;
  period: string;
  months: MonthlyFinancial[];
  cumulative_savings_zar: number;
  average_monthly_savings_zar: number;
  roi_percentage: number;
  sentinel_licence_fee_zar: number;
  payback_months: number;
}

/** Maintenance recommendation */
export interface MaintenanceRecommendation {
  type: string;
  equipment_id: string;
  equipment_name: string;
  priority: "routine" | "soon" | "urgent";
  reason: string;
  estimated_cost_zar: number;
  next_due_date: string;
}

/** Maintenance schedule (90-day PPM calendar) */
export interface MaintenanceSchedule {
  site_id: string;
  generated_at: string;
  recommendations: MaintenanceRecommendation[];
  schedule: Array<{
    date: string;
    tasks: Array<{ equipment_id: string; task: string; priority: string }>;
  }>;
}

/** Forecast hourly entry with optional actual reading */
export interface ForecastHour {
  hour: string;
  generation_kw: number;
  confidence_high_kw: number;
  confidence_low_kw: number;
  clear_sky_kw: number;
  cloud_factor: number;
  actual_kw: number | null;
}

/** Forecast accuracy metrics */
export interface ForecastAccuracyMetrics {
  rmse_kw: number;
  mae_kw: number;
  bias_pct: number;
  rmse_pct_of_peak: number;
}

/** Forecast vs actual combined response */
export interface ForecastWithActual {
  site_id: string;
  model: string;
  generated_at: string;
  hourly: ForecastHour[];
  accuracy: ForecastAccuracyMetrics | null;
}

/** Solar site entry from GET /api/solar/sites */
export interface SolarSite {
  site_id: string;
  site_name: string;
  plants: number;
  connectors: number;
  last_poll: string | null;
}

// ============= API Functions =============

/**
 * Fetch list of registered solar sites.
 */
export async function fetchSolarSites(): Promise<SolarSite[]> {
  const res = await fetchJson<{ sites: SolarSite[] }>("/api/solar/sites");
  return res.sites.map((site) => ({
    ...site,
    site_id: normalizeSiteId(site.site_id),
  }));
}

/**
 * Fetch site overview with generation, BESS SOC, grid flow.
 *
 * Uses request batching to prevent 429 rate limit errors when multiple
 * components request overview simultaneously. Requests are debounced
 * and sent sequentially to avoid overwhelming the API.
 */
export async function fetchSolarOverview(siteId: string): Promise<SolarOverview> {
  // Import batcher dynamically to avoid circular dependencies
  const { solarOverviewBatcher } = await import('./api/batchers');
  return solarOverviewBatcher(siteId);
}

/**
 * Fetch all inverters for a site with current readings.
 */
export async function fetchInverters(siteId: string): Promise<InverterListResponse> {
  const normalizedId = normalizeSiteId(siteId);
  return fetchJson<InverterListResponse>(`/api/solar/sites/${normalizedId}/inverters`);
}

/**
 * Fetch BESS container status: SOC, mode, power, health.
 */
export async function fetchBESSStatus(siteId: string): Promise<BESSStatus> {
  const normalizedId = normalizeSiteId(siteId);
  return fetchJson<BESSStatus>(`/api/solar/sites/${normalizedId}/bess`);
}

/**
 * Fetch performance metrics (PR, trends).
 */
export async function fetchPerformance(siteId: string): Promise<PerformanceMetrics> {
  const normalizedId = normalizeSiteId(siteId);
  return fetchJson<PerformanceMetrics>(`/api/solar/sites/${normalizedId}/performance`);
}

/**
 * Fetch prioritised diagnostic issues with cost impact.
 */
export async function fetchDiagnostics(siteId: string): Promise<DiagnosticReport> {
  const normalizedId = normalizeSiteId(siteId);
  return fetchJson<DiagnosticReport>(`/api/solar/sites/${normalizedId}/diagnostics`);
}

/**
 * Fetch NRS 097-2-1 compliance status.
 */
export async function fetchCompliance(siteId: string): Promise<ComplianceStatus> {
  const normalizedId = normalizeSiteId(siteId);
  return fetchJson<ComplianceStatus>(`/api/solar/sites/${normalizedId}/compliance`);
}

/**
 * Fetch financial summary (YTD or custom period).
 */
export async function fetchFinancialSummary(
  siteId: string,
  period: string = "ytd"
): Promise<FinancialSummary> {
  const normalizedId = normalizeSiteId(siteId);
  return fetchJson<FinancialSummary>(
    `/api/solar/sites/${normalizedId}/financial/summary?period=${period}`
  );
}

/**
 * Fetch maintenance schedule (90-day PPM calendar + recommendations).
 */
export async function fetchMaintenanceSchedule(
  siteId: string
): Promise<MaintenanceSchedule> {
  const normalizedId = normalizeSiteId(siteId);
  return fetchJson<MaintenanceSchedule>(
    `/api/solar/sites/${normalizedId}/maintenance/schedule`
  );
}

/**
 * Fetch 48-hour forecast with actual generation overlay.
 *
 * Combines the forecast endpoint with simulated actual readings
 * for hours that have elapsed. Used by ForecastActualChart.
 */
export async function fetchForecastWithActual(
  siteId: string
): Promise<ForecastWithActual> {
  const normalizedId = normalizeSiteId(siteId);
  // Fetch the forecast data
  const forecast = await fetchJson<{
    site_id: string;
    generated_at: string;
    model: string;
    hourly: Array<{
      hour: string;
      generation_kw: number;
      confidence_high_kw: number;
      confidence_low_kw: number;
      clear_sky_kw: number;
      cloud_factor: number;
    }>;
    accuracy_7d?: {
      rmse_kw: number;
      mae_kw: number;
      bias_pct: number;
      rmse_pct_of_peak: number;
    };
  }>(`/api/solar/sites/${normalizedId}/forecast?hours=48`);

  const now = new Date();

  // Enrich hourly data with simulated actuals for past hours
  const hourly: ForecastHour[] = (forecast.hourly || []).map((h) => {
    const hourTime = new Date(h.hour);
    let actual_kw: number | null = null;

    if (hourTime < now) {
      // Simulate actual as forecast + small random deviation
      const deviation = (Math.random() - 0.45) * h.generation_kw * 0.15;
      actual_kw = Math.max(0, h.generation_kw + deviation);
    }

    return {
      hour: h.hour,
      generation_kw: h.generation_kw,
      confidence_high_kw: h.confidence_high_kw,
      confidence_low_kw: h.confidence_low_kw,
      clear_sky_kw: h.clear_sky_kw,
      cloud_factor: h.cloud_factor,
      actual_kw,
    };
  });

  return {
    site_id: forecast.site_id,
    model: forecast.model,
    generated_at: forecast.generated_at,
    hourly,
    accuracy: forecast.accuracy_7d || null,
  };
}

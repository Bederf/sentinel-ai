/**
 * API Client for BMS Intelligence Backend
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "";
const ACCESS_TOKEN_KEY = "sentinel_token";
const REFRESH_TOKEN_KEY = "sentinel_refresh_token";
export const AUTH_EXPIRED_EVENT = "sentinel:auth-expired";
let refreshInFlight: Promise<string | null> | null = null;
const MAX_RATE_LIMIT_RETRIES = 0;
const BASE_RATE_LIMIT_DELAY_MS = 500;
const MAX_CONCURRENT_API_REQUESTS = 4;
let activeApiRequests = 0;
const apiRequestWaiters: Array<() => void> = [];
const inFlightGetRequests = new Map<string, Promise<Response>>();
const cachedGetResponses = new Map<string, { response: Response; expiresAt: number }>();
const rateLimitedUntilByBucket = new Map<string, number>();
const DEFAULT_RATE_LIMIT_COOLDOWN_MS = 30000;
const DEFAULT_GET_CACHE_TTL_MS = 30000;
const SITES_CACHE_KEY = "sentinel_cached_sites";

// Re-export solar configuration API/types for legacy imports.
export type {
  SolarPlant,
  SolarInverter,
  BESSConfig,
  GridMeterConfig,
  SolarConfig,
  SolarSiteRequest,
} from "./api/solar_config";
export {
  solarConfigApi,
  isValidEquipmentCode,
  calculateInverterCoverage,
  suggestEquipmentId,
} from "./api/solar_config";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function acquireApiRequestSlot(): Promise<void> {
  if (activeApiRequests < MAX_CONCURRENT_API_REQUESTS) {
    activeApiRequests += 1;
    return;
  }

  await new Promise<void>((resolve) => {
    apiRequestWaiters.push(resolve);
  });
}

function releaseApiRequestSlot(): void {
  const nextWaiter = apiRequestWaiters.shift();
  if (nextWaiter) {
    nextWaiter();
    return;
  }

  activeApiRequests = Math.max(0, activeApiRequests - 1);
}

async function performFetchWithLimits(url: string, options?: RequestInit): Promise<Response> {
  await acquireApiRequestSlot();
  try {
    return await fetch(url, options);
  } finally {
    releaseApiRequestSlot();
  }
}

function getRetryAfterMs(response: Response): number | null {
  const retryAfter = response.headers.get("Retry-After");
  if (!retryAfter) return null;

  const seconds = Number(retryAfter);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return seconds * 1000;
  }

  const retryAt = Date.parse(retryAfter);
  if (Number.isNaN(retryAt)) return null;

  const delayMs = retryAt - Date.now();
  return delayMs > 0 ? delayMs : null;
}

function getRateLimitBucket(url: string): string {
  if (url.includes("/safety-status")) return "safety-status";
  if (url.includes("/api/devices") || url.includes("/api/sites") || url.includes("/api/predictions")) {
    return "dashboard-core";
  }
  if (url.includes("/api/integration/")) return "integration";
  if (url.includes("/api/optimization/")) return "optimization";
  if (url.includes("/api/lighting/")) return "lighting";
  if (url.includes("/api/security/")) return "security";
  if (url.includes("/api/solar/")) return "solar";
  if (url.includes("/api/alerts")) return "alerts";
  if (url.includes("/api/modules/") && url.includes("/recommendations")) return "module-recommendations";
  return url;
}

function createClientRateLimitResponse(bucket: string): Response {
  return new Response(
    JSON.stringify({ detail: `Client cooldown active for ${bucket} after recent 429` }),
    {
      status: 429,
      statusText: "Too Many Requests",
      headers: { "Content-Type": "application/json" },
    }
  );
}

function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

function setTokens(accessToken: string, refreshToken?: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
}

export function clearAuthStorage(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem("sentinel_user");
}

function notifyAuthExpired(): void {
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
}

async function tryRefreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      // SECURITY: Send refresh token in request body, NOT in URL (Phase 75-07)
      const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) return null;
      const data = await response.json() as { access_token?: string; refresh_token?: string };
      if (!data.access_token) return null;
      setTokens(data.access_token, data.refresh_token);
      return data.access_token;
    } catch {
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

async function fetchWithAuthRetry(
  url: string,
  options?: RequestInit,
  allowRetry: boolean = true,
  rateLimitRetryCount: number = 0
): Promise<Response> {
  const token = getAccessToken();
  const response = await performFetchWithLimits(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });

  const isRefreshEndpoint = url.includes("/api/auth/refresh");
  if (response.status === 401 && allowRetry && !isRefreshEndpoint) {
    const refreshedToken = await tryRefreshAccessToken();
    if (refreshedToken) {
      return performFetchWithLimits(url, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          ...(refreshedToken ? { Authorization: `Bearer ${refreshedToken}` } : {}),
          ...options?.headers,
        },
      });
    }

    clearAuthStorage();
    notifyAuthExpired();
  }

  const requestMethod = (options?.method || "GET").toUpperCase();
  const isSafeMethod = requestMethod === "GET" || requestMethod === "HEAD" || requestMethod === "OPTIONS";
  if (
    response.status === 429 &&
    isSafeMethod &&
    rateLimitRetryCount < MAX_RATE_LIMIT_RETRIES
  ) {
    const retryAfterMs = getRetryAfterMs(response);
    const fallbackDelayMs = BASE_RATE_LIMIT_DELAY_MS * (2 ** rateLimitRetryCount);
    const jitterMs = Math.floor(Math.random() * 200);
    await sleep((retryAfterMs ?? fallbackDelayMs) + jitterMs);

    return fetchWithAuthRetry(url, options, allowRetry, rateLimitRetryCount + 1);
  }

  return response;
}

export async function authorizedFetch(
  endpoint: string,
  options?: RequestInit,
  absoluteUrl: boolean = false
): Promise<Response> {
  const url = absoluteUrl ? endpoint : `${API_BASE_URL}${endpoint}`;
  const bucket = getRateLimitBucket(url);
  const method = (options?.method || "GET").toUpperCase();
  const canDeduplicateGet = method === "GET" && (!options?.body || options.body === undefined);
  const dedupeKey = `${method}:${url}`;

  if (canDeduplicateGet) {
    const cachedEntry = cachedGetResponses.get(dedupeKey);
    if (cachedEntry && cachedEntry.expiresAt > Date.now()) {
      return cachedEntry.response.clone();
    }
  }

  const rateLimitedUntil = rateLimitedUntilByBucket.get(bucket);
  if (rateLimitedUntil && rateLimitedUntil > Date.now()) {
    if (canDeduplicateGet) {
      const cachedEntry = cachedGetResponses.get(dedupeKey);
      if (cachedEntry && cachedEntry.expiresAt > Date.now()) {
        return cachedEntry.response.clone();
      }
    }
    return createClientRateLimitResponse(bucket);
  }

  if (!canDeduplicateGet) {
    const response = await fetchWithAuthRetry(url, options, true);
    if (response.status === 429) {
      const retryAfterMs = getRetryAfterMs(response) ?? DEFAULT_RATE_LIMIT_COOLDOWN_MS;
      rateLimitedUntilByBucket.set(bucket, Date.now() + retryAfterMs);
    }
    return response;
  }

  const existing = inFlightGetRequests.get(dedupeKey);
  if (existing) {
    return existing.then((response) => response.clone());
  }

  const requestPromise = fetchWithAuthRetry(url, options, true);
  inFlightGetRequests.set(dedupeKey, requestPromise);

  try {
    const response = await requestPromise;
    if (response.status === 429) {
      const retryAfterMs = getRetryAfterMs(response) ?? DEFAULT_RATE_LIMIT_COOLDOWN_MS;
      rateLimitedUntilByBucket.set(bucket, Date.now() + retryAfterMs);
      const cachedEntry = cachedGetResponses.get(dedupeKey);
      if (cachedEntry && cachedEntry.expiresAt > Date.now()) {
        return cachedEntry.response.clone();
      }
    }
    if (response.ok) {
      cachedGetResponses.set(dedupeKey, {
        response: response.clone(),
        expiresAt: Date.now() + DEFAULT_GET_CACHE_TTL_MS,
      });
    }
    return response.clone();
  } finally {
    inFlightGetRequests.delete(dedupeKey);
  }
}

// ============= Response Interfaces =============

export interface HealthResponse {
  status: string;
  version: string;
}

export interface ApiError {
  message: string;
  status: number;
}

export function isExpectedApiError(error: unknown): error is ApiError {
  const maybeError = error as { status?: number; message?: string } | null;
  if (maybeError?.status === 401 || maybeError?.status === 429) return true;
  const message = (maybeError?.message || "").toLowerCase();
  return message.includes("status 401") || message.includes("status 429");
}

export type {
  PortfolioMetrics,
  ContractProfitabilityDetail,
  ProfitabilityTrend,
  LossLeaderAnalysis,
  AssetROI,
  ContractListItem,
} from "./profitabilityApi";

export type {
  WaterMeter,
  WaterConsumption,
  WaterAlert,
  WaterTrending,
  CurrentFlowResponse,
} from "./waterApi";

// Equipment breakdown by category (from Supabase view)
export interface EquipmentBreakdown {
  equipment: number;
  hvac_zones: number;
  generators: number;
  generator_groups: number;
  diesel_tanks: number;
  energy_centre: number;
  dali_controllers: number;
}

// Equipment summary response (from /api/buildings/{id}/equipment-summary)
export interface EquipmentSummary {
  site_id: string;
  site_name: string;
  total_assets: number;
  categories: {
    equipment: number;
    hvac_zones: number;
    generators: number;
    generator_groups: number;
    diesel_tanks: number;
    energy_centres: number;
    mv_incomers: number;
    transformers: number;
    lv_switchboards: number;
    ats_units: number;
    power_meters: number;
    pfc_banks: number;
    ups_systems: number;
    feeders: number;
    dali_controllers: number;
  };
  supplementary: {
    desks: number;
    luminaires: number;
    dali_sensors: number;
  };
  source: "supabase" | "json";
}

// Health factor breakdown for equipment
export interface HealthFactor {
  score: number;
  value: string;
}

// Building equipment item (from /api/buildings/{id}/equipment)
export interface BuildingEquipmentItem {
  id: string;
  name: string;
  type: string;
  category: string;
  status: "normal" | "warning" | "critical" | "unknown";
  health: number;
  location: string;
  site_id: string;
  site_name: string;
  details: Record<string, any>;
  controllable: boolean;
  health_factors?: {
    age?: HealthFactor;
    service?: HealthFactor;
    runtime?: HealthFactor;
    fault_history?: HealthFactor;
  };
}

// Category status counts
export interface CategoryStatus {
  total: number;
  normal: number;
  warning: number;
  critical: number;
}

// Building equipment response (from /api/buildings/{id}/equipment)
// NOTE: This is deprecated - use the version from lib/api/sites.ts instead
// Keeping for backward compatibility but should use Equipment[] not BuildingEquipmentItem[]
export interface BuildingEquipmentResponse {
  site_id: string;
  site_name: string;
  total_equipment: number;
  categories: Record<string, CategoryStatus>;
  // Use Equipment array (from modular API) instead of BuildingEquipmentItem
  equipment: Equipment[];
}

// Equipment metadata (from /api/equipment/{id}/metadata)
export interface EquipmentNetworkInfo {
  ip_address?: string;
  mac_address?: string;
  gateway_ip?: string;
  dali_line?: number;
  dali_address?: number;
  bacnet_device_id?: number;
  bacnet_network?: number;
  modbus_address?: number;
  modbus_port?: number;
  protocol?: string;
}

export interface EquipmentDeviceInfo {
  gtin?: string;
  serial_number?: string;
  manufacturer?: string;
  model?: string;
  firmware_version?: string;
  hardware_version?: string;
  device_type?: string;
  vendor_id?: number;
}

export interface EquipmentOperatingData {
  lamp_hours?: number;
  runtime_hours?: number;
  power_cycles?: number;
  total_runtime_hours?: number;
  last_fault?: string;
  fault_count?: number;
  energy_kwh?: number;
  system_status?: string;
  rated_capacity?: string;
  battery_cycles?: number;
  transfer_count?: number;
}

export interface EquipmentMetadata {
  id: string;
  code: string;
  name: string;
  type: string;
  manufacturer?: string;
  model?: string;
  serial_number?: string;
  notes?: string;
  network_info?: EquipmentNetworkInfo;
  device_info?: EquipmentDeviceInfo;
  operating_data?: EquipmentOperatingData;
  commissioning_date?: string;
  warranty_expiry?: string;
  last_discovery?: string;
  install_date?: string;
  last_service?: string;
  status?: string;
  health_score?: number;
  location?: string;
}

export interface EquipmentMetadataResponse {
  equipment: EquipmentMetadata;
  has_notes: boolean;
  has_network_info: boolean;
  has_device_info: boolean;
  last_discovery?: string;
}

export interface NotesHistoryItem {
  id: string;
  equipment_id: string;
  notes_before?: string;
  notes_after?: string;
  changed_by: string;
  changed_at: string;
  change_reason?: string;
}

export interface EquipmentDiscoveryResult {
  equipment_code: string;
  protocol: string;
  status: string;
  network_info?: EquipmentNetworkInfo;
  device_info?: EquipmentDeviceInfo;
  operating_data?: EquipmentOperatingData;
  saved: boolean;
  error?: string;
}

// Site/Building interface (summary view)
export interface Site {
  id: string;
  name: string;
  location: string;
  address?: string; // Full address from backend
  region: string;
  type: string;
  equipment_count: number; // Total equipment count
  alert_count: number;
  status: "normal" | "warning" | "critical";
  // Extended fields from backend (optional for summary, required for detail)
  sqm?: number;
  floors?: number;
  year_built?: number;
  operating_hours?: { start: string; end: string };
  timezone?: string; // IANA timezone (e.g., "Africa/Johannesburg")
  occupancy_pattern?: string;
  contact_email?: string;
  contact_phone?: string;
  active_alerts?: number;
  // Equipment breakdown (when available from Supabase or JSON)
  equipment_breakdown?: EquipmentBreakdown;
  // Equipment status counts (ok/warning/critical)
  equipment_status?: {
    total: number;
    ok: number;
    warning: number;
    critical: number;
  };
  // Optimization fields (Phase 8)
  optimization_enabled?: boolean;
  optimization_status?: "optimized" | "recommendation_pending" | "warning" | "error" | "unknown";
  optimization_settings?: {
    mode: "supervised" | "automatic";
    last_analysis: string | null;
    analysis_interval_minutes?: number;
  };
  last_optimization?: string;
  optimization_history?: OptimizationHistoryEntry[];
  // SENTINEL processing toggle (Phase 125)
  sentinel_processing_enabled?: boolean;
}

// Equipment interface
export interface Equipment {
  id: string;
  name: string;
  type: string;
  site_id: string;
  site_name: string;
  status: "online" | "offline" | "maintenance" | "normal" | "warning" | "critical" | "unknown";
  location?: string;
  last_reading?: {
    timestamp: string;
    value: number;
    unit: string;
  };
}

// Alert interface
export interface Alert {
  id: string;
  site_id: string;
  site_name: string;
  equipment_id: string;
  equipment_name: string;
  severity: "low" | "medium" | "high" | "critical" | "warning" | "info";
  message: string;
  created_at: string;
  acknowledged: boolean;
  title?: string;
  type?: string;
  status?: string;
  category?: string;
  device_id?: string; // Maps to mock_devices.json for control navigation
  recommended_action?: string;
  operational_context?: {
    building_state: string;
    is_peak_hours: boolean;
    occupancy_pct: number;
    hvac_mode: string;
    hour: number;
  };
}

// Anomaly prediction interface
export interface Anomaly {
  id: string;
  site_id: string;
  site_name: string;
  equipment_id: string;
  equipment_name: string;
  prediction: string;
  confidence: number;
  predicted_date: string;
  recommendation: string;
}

// ============= Device Interfaces =============

// Device point interface
export interface DevicePoint {
  id?: string; // Point ID
  device_id?: string; // Device ID this point belongs to
  name: string;
  point_type: string;
  description: string;
  unit: string;
  min_value?: number;
  max_value?: number;
  default_value: number | boolean;
  current_value?: number | boolean; // Actual current value from device adapter
  writable: boolean;
  priority?: number;
  metadata?: Record<string, any>;
}

// Device interface
export interface Device {
  id: string;
  name: string;
  device_type: string;
  type?: string; // Alias for device_type for backward compatibility
  protocol: string;
  location: string;
  site_id: string;
  description: string;
  manufacturer?: string;
  model?: string;
  points: Record<string, DevicePoint>;
  metadata?: Record<string, any>;
  // Status properties
  status?: "online" | "offline" | "maintenance";
  safety_status?: "safe" | "warning" | "critical" | "unknown";
  last_communication?: string; // ISO timestamp
  current_value?: number;
}

// Device value interface
export interface DeviceValue {
  device_id: string;
  point_name: string;
  value: number | boolean;
  unit: string;
  timestamp: string;
  quality: string;
}

// Device control response interface
export interface DeviceControlResponse {
  success: boolean;
  message: string;
  device_id: string;
  point: string;
  value: number | boolean;
  priority: number;
}

// Device status interface
export interface DeviceStatus {
  device_id: string;
  device_name: string;
  status: string;
  last_seen: string;
  protocol: string;
}

// ============= Audit Interfaces =============

// Audit entry interface (for RecentActions component)
export interface AuditEntry {
  id: string;
  timestamp: string;
  device_id: string;
  device_name: string;
  action: string;
  point: string;
  old_value: any;
  new_value: any;
  user: string;
  success: boolean;
  message?: string;
}

// Audit log entry interface
export interface AuditLogEntryResponse {
  id: string;
  timestamp: string;
  action: string;
  user: string;
  device_id?: string;
  point_name?: string;
  old_value?: any;
  new_value?: any;
  result: string;
  safety_validation?: Record<string, any>;
  error_message?: string;
  correlation_id?: string;
  metadata: Record<string, any>;
}

// Safety status for devices
export interface DeviceSafetyStatus {
  device_id: string;
  device_name: string;
  overall_status: 'safe' | 'warning' | 'blocked' | 'alarm' | 'unknown';
  point_statuses: Record<string, {
    value: any;
    allowed: boolean;
    warnings: string[];
    alarms: string[];
  }>;
  active_rule_count: number;
  last_check: string;
}

// Audit logs response with pagination
export interface AuditLogsResponse {
  entries: AuditLogEntryResponse[];
  total_count: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

// Audit statistics response
export interface AuditStatsResponse {
  total_entries: number;
  by_action: Record<string, number>;
  by_result: Record<string, number>;
  by_user: Record<string, number>;
  recent_activity_count: number;
  last_updated: string;
}

// Demo audit data generation response
export interface DemoAuditDataResponse {
  status: string;
  entries_created: number;
  message: string;
}

// ============= Optimization Interfaces =============

// Load shedding stage interface
export interface LoadSheddingStage {
  stage: number;
  start_time: string;
  end_time: string;
}

// Eskom status response interface
export interface EskomStatusResponse {
  current_stage: number;
  updated_at: string;
  next_stages: LoadSheddingStage[];
  area_schedules: Record<string, LoadSheddingStage[]>;
  source: string; // "eskomsepush" | "not_configured" | "unavailable"
}

// Site-specific schedule response interface
export interface SiteScheduleResponse {
  site_id: string;
  site_name: string;
  current_stage: number;
  schedules: LoadSheddingStage[];
  next_outage: LoadSheddingStage | null;
  area_name?: string;
  source: string; // "eskomsepush" | "not_configured" | "unavailable"
}

// Thermal runway response interface
export interface ThermalRunwayResponse {
  site_id: string;
  site_name: string;
  current_temperature: number;
  comfort_limit: number;
  thermal_runway_minutes: number;
  comfort_breach_time: string | null;
  calculation_method: string;
  building_params: {
    thermal_mass: number;
    insulation_factor: number;
    internal_heat_gain: number;
  };
  weather_forecast: {
    outside_temp: number;
    solar_load: number;
    humidity: number;
  };
}

// Optimization scenario interface (from optimization_scenarios.json)
export interface OptimizationScenario {
  scenario_id: string;
  site_id: string;
  site_name: string;
  description: string;
  current_conditions: {
    inside_temp: number;
    comfort_limit: number;
    outside_temp: number;
    humidity: number;
    solar_load: number;
    time_of_day: string;
  };
  load_shedding: {
    stage: number;
    start: string;
    end: string;
    duration_minutes: number;
    area: string;
    confidence: string;
  };
  thermal_runway: {
    without_precooling: number;
    with_precooling: number;
    comfort_breach_time: string;
    comfort_maintained: boolean;
    calculation_params: {
      thermal_mass: number;
      insulation_factor: number;
      internal_heat_gain: number;
    };
  };
  pre_cooling_schedule: {
    start: string;
    duration_minutes: number;
    target_temp: number;
    actions: Array<{
      time: string;
      action: string;
      value: string;
      description: string;
    }>;
    energy_impact_kwh: number;
    peak_demand_increase_percent: number;
  };
  savings: {
    energy_savings_percent: number;
    comfort_extension_minutes: number;
    fuel_savings_percent: number;
    total_savings_zar: number;
    breakdown: {
      reduced_generator_runtime: number;
      avoided_peak_demand_charges: number;
      improved_efficiency: number;
      reduced_restart_energy: number;
    };
  };
  generator_readiness: {
    test_passed: boolean;
    last_test: string;
    fuel_level_percent: number;
    ups_status: string;
    estimated_runtime_hours: number;
    load_capacity_kw: number;
    critical_loads: string[];
  };
  restart_plan: {
    staged_restart: boolean;
    sequence: Array<{
      time_offset: number;
      action: string;
      loads?: string[];
      zones?: string[];
      description?: string;
    }>;
    estimated_restoration_time: string;
  };
  visualization_data: {
    thermal_curve: number[][];
    precooling_curve: number[][];
    comfort_limit_line: number;
    outage_period: number[];
  };
  created_at: string;
  updated_at: string;
}

// ============= AI Optimization Interfaces (Phase 8) =============

// Optimization action (setpoint change recommendation)
export interface OptimizationAction {
  equipment_id: string;
  equipment_name: string;
  point_name: string;
  current_value: number;
  recommended_value: number;
  unit: string;
  reason: string;
}

// Projected savings from optimization
export interface ProjectedSavings {
  energy_kwh: number;
  cost_zar_per_hour: number;
  percentage_improvement: number;
  // Legacy property names (for backwards compatibility)
  energy_percent?: number;
  cost_zar?: number;
  comfort_impact?: string;
  equipment_impact?: string;
}

// Optimization recommendation from AI analysis
export interface OptimizationRecommendation {
  id?: string; // Optional - may use timestamp as fallback
  site_id: string;
  timestamp: string;
  recommendations: OptimizationAction[];
  projected_savings: ProjectedSavings;
  confidence: number; // 0-100
  reasoning: string;
}

// Optimization history entry
export interface OptimizationHistoryEntry {
  timestamp: string;
  action: string;
  result: string;
  user: string;
  details?: string;
}

// Monthly savings summary
export interface MonthlySavingsSummary {
  monthly_savings_zar: number;
  savings_per_hour_zar: number;
  applied_recommendations: number;
}

// Full optimization status response
export interface OptimizationStatusResponse {
  site_id: string;
  optimization_enabled: boolean;
  optimization_status: "optimized" | "recommendation_pending" | "warning" | "error" | "unknown";
  optimization_settings: {
    mode: "supervised" | "automatic";
    last_analysis: string | null;
    analysis_interval_minutes: number;
  };
  last_recommendation: OptimizationRecommendation | null;
  last_optimization: string | null;
  optimization_history: OptimizationHistoryEntry[];
  error_message?: string;
  monthly_savings?: MonthlySavingsSummary;
}

// Dashboard stats interface
export interface DashboardStats {
  total_sites: number;
  total_equipment: number;
  total_sensors: number;
  active_alerts: number;
  critical_alerts: number;
  pending_anomalies: number;
  uptime_percent: number;
}

// Health thresholds interface
export interface HealthThresholds {
  healthy: number;
  warning: number;
  critical: number;
}

// Safety rule interface
export interface SafetyRule {
  id: string;
  name: string;
  rule_type: 'temperature_range' | 'pressure_limit' | 'interlock' | 'runtime_limit' | 'brightness_limit' | 'custom';
  severity: 'block' | 'warning' | 'alarm';
  description: string;
  device_type: string | null;
  device_id: string | null;
  point_name: string | null;
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
  // Type-specific parameters
  min_temp?: number;
  max_temp?: number;
  min_pressure?: number;
  max_pressure?: number;
  min_brightness?: number;
  max_brightness?: number;
  min_runtime_minutes?: number;
  max_starts_per_hour?: number;
  trigger_device_id?: string;
  trigger_device_type?: string;
  trigger_point?: string;
  trigger_value?: any;
  action?: string;
  action_value?: any;
  min_value?: number;
  max_value?: number;
  validation_logic?: string;
  unit?: string;
}

// Safety rules response
export interface SafetyRulesResponse {
  rules: SafetyRule[];
  count: number;
}

// Settings interface
export interface Settings {
  healthThresholds: HealthThresholds;
  notifications: Record<string, any>;
  display: Record<string, any>;
}

// Energy data point interface
export interface EnergyDataPoint {
  date: string;
  site_id: string;
  site_name: string;
  hvac_kwh: number;
  lighting_kwh: number;
  other_kwh: number;
  total_kwh: number;
}

// Energy response interface
export interface EnergyResponse {
  days: number;
  site_id: string | null;
  data: EnergyDataPoint[];
}

// Prediction interface
export interface Prediction {
  id: string;
  equipment_id: string;
  site_id: string;
  site_name: string;
  equipment_name: string;
  equipment_type: string;
  prediction_type: string;
  probability_percent: number;
  confidence: "high" | "medium" | "low";
  predicted_failure_date: string;
  timeframe_days: number;
  severity: "critical" | "warning" | "healthy";
  evidence: {
    repeat_work_orders: number;
    repeat_period_months: number;
    alarm_frequency: Record<string, number>;
    asset_age_years: number;
    expected_life_years: number;
    technician_notes: string[];
    latest_reading: {
      parameter: string;
      value: number;
      baseline: number;
      threshold: number;
      trend: string;
    };
  };
  contributing_factors: Array<{
    factor: string;
    weight: number;
    description: string;
  }>;
  similar_failures: Array<{
    site: string;
    equipment: string;
    failure_date: string;
    common_factors: string[];
  }>;
  financial_impact: {
    repair_cost_zar: number;
    replacement_cost_zar: number;
    downtime_cost_per_hour_zar: number;
    estimated_repair_hours: number;
    potential_loss_zar: number;
  };
  cost_impact?: {
    preventive_breakdown: {
      labor_cost_zar: number;
      parts_cost_zar: number;
      downtime_hours: number;
      total_zar: number;
    };
    failure_breakdown: {
      emergency_repair_zar: number;
      downtime_loss_zar: number;
      downtime_hours: number;
      total_zar: number;
    };
    potential_savings_zar: number;
    savings_percent: number;
    roi_message: string;
  };
  recommended_action: string;
  parts_required: Array<{
    part_number: string;
    name: string;
    quantity: number;
    cost_zar: number;
    lead_time_days: number;
  }> | string[];
  urgency: string;
}

// Predictions response interface
export interface PredictionsResponse {
  total: number;
  avg_probability: number;
  total_repair_cost_zar: number;
  total_potential_loss_zar: number;
  potential_savings_zar: number;
  by_severity: Record<string, number>;
  by_equipment_type: Record<string, number>;
  predictions: Prediction[];
}

/**
 * Generic fetch wrapper with error handling
 */
async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const response = await authorizedFetch(endpoint, options);

  if (!response.ok) {
    let errorMessage = response.statusText;
    try {
      const errorData = await response.json();
      // Handle Pydantic validation errors (detail is an array)
      if (Array.isArray(errorData.detail)) {
        errorMessage = errorData.detail.map((e: { msg?: string; loc?: string[] }) =>
          `${e.loc?.join('.') || 'field'}: ${e.msg || 'invalid'}`
        ).join(', ');
      } else {
        errorMessage = errorData.detail || errorData.message || JSON.stringify(errorData);
      }
    } catch {
      // If response isn't JSON, use statusText
    }
    const error: ApiError = {
      message: `API Error: ${errorMessage}`,
      status: response.status,
    };
    throw error;
  }

  return response.json();
}

/**
 * Stream chat response using Server-Sent Events
 *
 * @param message - User message to send
 * @param conversationId - Optional conversation ID for context
 * @param onChunk - Callback called for each text chunk received
 * @param siteId - Optional site ID for building context
 */
export async function streamChat(
  message: string,
  conversationId: string | undefined,
  onChunk: (chunk: string) => void,
  siteId?: string
): Promise<void> {
  const url = `${API_BASE_URL}/api/chat`;

  // Get JWT token from localStorage if available
  const token = localStorage.getItem("sentinel_token");

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      site_id: siteId,
    }),
  });

  if (!response.ok) {
    throw new Error(`Chat API error: ${response.status} ${response.statusText}`);
  }

  if (!response.body) {
    throw new Error("No response body available for streaming");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = ""; // Buffer for incomplete lines across chunk boundaries
  let eventDataLines: string[] = []; // Collect data lines for current SSE event

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // Decode the chunk and append to buffer
      buffer += decoder.decode(value, { stream: true });

      // Process complete lines from buffer
      const lines = buffer.split("\n");
      // Keep the last (potentially incomplete) line in the buffer
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6); // Remove "data: " prefix

          // Check for completion sentinel
          if (data === "[DONE]") {
            return;
          }

          // Collect data line for this event
          // SSE spec: consecutive "data:" lines are joined with newlines
          eventDataLines.push(data);
        } else if (line === "" && eventDataLines.length > 0) {
          // Empty line marks end of SSE event
          // Join all collected data lines with newlines and emit
          const eventData = eventDataLines.join("\n");
          onChunk(eventData);
          eventDataLines = [];
        }
      }
    }

    // Process any remaining data
    if (eventDataLines.length > 0) {
      const eventData = eventDataLines.join("\n");
      onChunk(eventData);
    }
    if (buffer.startsWith("data: ")) {
      const data = buffer.slice(6);
      if (data && data !== "[DONE]") {
        onChunk(data);
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * API Methods
 */
export const api = {
  /**
   * Check backend health status
   */
  async health(): Promise<HealthResponse> {
    return fetchApi<HealthResponse>("/api/health");
  },

  /**
   * Stream chat with AI assistant
   */
  streamChat,

  /**
   * Convert text to speech audio via ElevenLabs TTS
   * Returns MP3 audio blob for playback
   */
  async textToSpeech(text: string): Promise<Blob> {
    const token = localStorage.getItem("sentinel_token");
    const response = await fetch(`${API_BASE_URL}/api/chat/tts`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) {
      throw new Error(`TTS API error: ${response.status} ${response.statusText}`);
    }
    return response.blob();
  },

  // ============= Dashboard API Methods =============

  /**
   * Get all sites/buildings
   */
  async getSites(): Promise<Site[]> {
    try {
      const response = await fetchApi<{ total: number; sites: Site[] }>("/api/sites");
      localStorage.setItem(SITES_CACHE_KEY, JSON.stringify(response.sites));
      return response.sites;
    } catch (error) {
      const maybeApiError = error as { status?: number };
      if (maybeApiError?.status === 429) {
        const cachedSites = localStorage.getItem(SITES_CACHE_KEY);
        if (cachedSites) {
          try {
            return JSON.parse(cachedSites) as Site[];
          } catch {
            // ignore malformed cache and rethrow original error
          }
        }
      }
      throw error;
    }
  },

  /**
   * Get a single site by ID
   * @param siteId - Site ID
   */
  async getSite(siteId: string): Promise<Site> {
    return fetchApi<Site>(`/api/sites/${siteId}`);
  },

  /**
   * Get equipment summary breakdown for a building
   * @param siteId - Building ID (e.g., 'sandton')
   */
  async getEquipmentSummary(siteId: string): Promise<EquipmentSummary> {
    return fetchApi<EquipmentSummary>(`/api/buildings/${siteId}/equipment-summary`);
  },

  /**
   * Get all equipment for a building with status
   * @param siteId - Building ID (e.g., 'sandton')
   */
  async getSiteEquipment(siteId: string): Promise<BuildingEquipmentResponse> {
    return fetchApi<BuildingEquipmentResponse>(`/api/buildings/${siteId}/equipment`);
  },

  /**
   * Get dashboard statistics overview
   */
  async getStats(): Promise<DashboardStats> {
    return fetchApi<DashboardStats>("/api/stats");
  },

  /**
   * Get active alerts
   */
  async getAlerts(): Promise<Alert[]> {
    try {
      const response = await fetchApi<{ total: number; alerts: Alert[] }>("/api/alerts");
      return response.alerts;
    } catch (err) {
      const apiError = err as ApiError | undefined;
      const message = apiError?.message?.toLowerCase() || "";
      if (apiError?.status === 401 && message.includes("authentication required")) {
        return [];
      }
      if (apiError?.status === 429) {
        return [];
      }
      throw err;
    }
  },

  /**
   * Acknowledge/mark an alert as read
   * @param alertId - ID of the alert to acknowledge
   * @param acknowledgedBy - Name of the person acknowledging (defaults to "operator")
   */
  async acknowledgeAlert(alertId: string, acknowledgedBy: string = "operator"): Promise<{ status: string; alert_id: string }> {
    return fetchApi<{ status: string; alert_id: string }>(`/api/alerts/${alertId}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({ acknowledged_by: acknowledgedBy }),
    });
  },

  /**
   * Get anomaly predictions
   */
  async getAnomalies(): Promise<Anomaly[]> {
    return fetchApi<Anomaly[]>("/api/anomalies");
  },

  /**
   * Get equipment list
   * @param siteId - Optional site ID filter
   */
  async getEquipment(siteId?: string): Promise<Equipment[]> {
    const params = new URLSearchParams();
    if (siteId) {
      params.append("site_id", siteId);
    }
    const queryString = params.toString();
    const response = await fetchApi<{ total: number; equipment: Equipment[] }>(
      `/api/equipment${queryString ? `?${queryString}` : ""}`
    );
    return response.equipment;
  },

  /**
   * Get equipment with control points from Supabase
   * @param equipmentId - Equipment code (e.g., "eqp-079")
   */
  async getEquipmentControls(equipmentId: string): Promise<Device> {
    return fetchApi<Device>(`/api/equipment/${equipmentId}/controls`);
  },

  /**
   * Control an equipment point (write value to Supabase)
   * @param equipmentId - Equipment code (e.g., "eqp-004")
   * @param point - Point name to control
   * @param value - Value to write
   * @param priority - Write priority (1-16, default: 8)
   */
  async controlEquipment(
    equipmentId: string,
    point: string,
    value: number | boolean,
    priority: number = 8
  ): Promise<DeviceControlResponse> {
    return fetchApi<DeviceControlResponse>(`/api/equipment/${equipmentId}/control`, {
      method: "POST",
      body: JSON.stringify({ point, value, priority }),
    });
  },

  // ============= Equipment Metadata API Methods =============

  /**
   * Get full metadata for equipment
   * @param equipmentId - Equipment UUID or code
   */
  async getEquipmentMetadata(equipmentId: string): Promise<EquipmentMetadataResponse> {
    return fetchApi<EquipmentMetadataResponse>(`/api/equipment/${equipmentId}/metadata`);
  },

  /**
   * Update equipment notes
   * @param equipmentId - Equipment UUID or code
   * @param notes - New notes content
   * @param changedBy - User making the change
   * @param changeReason - Optional reason for change
   */
  async updateEquipmentNotes(
    equipmentId: string,
    notes: string,
    changedBy: string,
    changeReason?: string
  ): Promise<{ status: string; equipment: EquipmentMetadata; message: string }> {
    return fetchApi(`/api/equipment/${equipmentId}/notes`, {
      method: "PATCH",
      body: JSON.stringify({
        notes,
        changed_by: changedBy,
        change_reason: changeReason,
      }),
    });
  },

  /**
   * Get notes change history for equipment
   * @param equipmentId - Equipment UUID or code
   * @param limit - Max records to return
   */
  async getEquipmentNotesHistory(
    equipmentId: string,
    limit: number = 20
  ): Promise<{ equipment_id: string; history: NotesHistoryItem[]; count: number }> {
    return fetchApi(`/api/equipment/${equipmentId}/notes/history?limit=${limit}`);
  },

  /**
   * Discover equipment information (auto-detect protocol)
   * @param equipmentCode - Equipment code
   * @param useSimulated - Fall back to simulated data if discovery fails
   */
  async discoverEquipment(
    equipmentCode: string,
    useSimulated: boolean = true
  ): Promise<EquipmentDiscoveryResult> {
    return fetchApi<EquipmentDiscoveryResult>(
      `/api/equipment/${equipmentCode}/discover?use_simulated=${useSimulated}`
    );
  },

  /**
   * Trigger full discovery for equipment
   * @param equipmentCode - Equipment code
   * @param protocol - Protocol: dali, bacnet, modbus, or auto
   * @param options - Additional discovery options
   */
  async triggerEquipmentDiscovery(
    equipmentCode: string,
    protocol: string = "auto",
    options: {
      ipAddress?: string;
      daliLine?: number;
      daliAddress?: number;
      bacnetDeviceId?: number;
      modbusUnitId?: number;
      useSimulated?: boolean;
    } = {}
  ): Promise<EquipmentDiscoveryResult> {
    return fetchApi<EquipmentDiscoveryResult>("/api/equipment/discover", {
      method: "POST",
      body: JSON.stringify({
        equipment_code: equipmentCode,
        protocol,
        ip_address: options.ipAddress,
        dali_line: options.daliLine,
        dali_address: options.daliAddress,
        bacnet_device_id: options.bacnetDeviceId,
        modbus_unit_id: options.modbusUnitId,
        use_simulated: options.useSimulated ?? true,
      }),
    });
  },

  /**
   * Get energy consumption data
   * @param siteId - Optional site ID filter
   * @param days - Number of days (default 30)
   */
  async getEnergy(
    siteId: string | null = null,
    days: number = 30
  ): Promise<EnergyResponse> {
    const params = new URLSearchParams();
    if (siteId) {
      params.append("site_id", siteId);
    }
    params.append("days", days.toString());
    return fetchApi<EnergyResponse>(`/api/energy?${params.toString()}`);
  },

  /**
   * Get AI-driven failure predictions
   * @param siteId - Optional site ID filter
   * @param equipmentType - Optional equipment type filter
   * @param severity - Optional severity filter
   * @param minProbability - Optional minimum probability filter
   */
  async getPredictions(
    siteId?: string,
    equipmentType?: string,
    severity?: string,
    minProbability?: number
  ): Promise<PredictionsResponse> {
    const params = new URLSearchParams();
    if (siteId) {
      params.append("site_code", siteId);
    }
    if (equipmentType) {
      params.append("equipment_type", equipmentType);
    }
    if (severity) {
      params.append("severity", severity);
    }
    if (minProbability !== undefined) {
      params.append("min_probability", minProbability.toString());
    }
    const queryString = params.toString();
    return fetchApi<PredictionsResponse>(
      `/api/predictions${queryString ? `?${queryString}` : ""}`
    );
  },

  /**
   * Get single prediction detail by ID
   * @param predictionId - Prediction ID
   */
  async getPrediction(predictionId: string): Promise<Prediction> {
    return fetchApi<Prediction>(`/api/predictions/${predictionId}`);
  },

  // ============= Optimization API Methods =============

  /**
   * Get current Eskom load shedding status
   * @param siteId - Optional site ID for area-specific schedules
   */
  async getEskomStatus(siteId?: string): Promise<EskomStatusResponse> {
    const params = new URLSearchParams();
    if (siteId) {
      params.append("site_id", siteId);
    }
    const queryString = params.toString();
    try {
      return await fetchApi<EskomStatusResponse>(
        `/api/optimization/eskom-status${queryString ? `?${queryString}` : ""}`
      );
    } catch (error) {
      if (isExpectedApiError(error)) {
        return {
          current_stage: 0,
          updated_at: new Date().toISOString(),
          next_stages: [],
          area_schedules: {},
          source: "unavailable",
        };
      }
      throw error;
    }
  },

  /**
   * Get load shedding schedule for a specific site
   * @param siteId - Site ID to get schedule for
   */
  async getSiteEskomStatus(siteId: string): Promise<SiteScheduleResponse> {
    try {
      return await fetchApi<SiteScheduleResponse>(`/api/optimization/eskom-status/${siteId}`);
    } catch (error) {
      if (isExpectedApiError(error)) {
        return {
          site_id: siteId,
          site_name: siteId,
          current_stage: 0,
          schedules: [],
          next_outage: null,
          source: "unavailable",
        };
      }
      throw error;
    }
  },

  /**
   * Calculate thermal runway for a building during load shedding
   * @param siteId - Site ID
   * @param currentTemp - Current inside temperature in °C (optional)
   * @param comfortLimit - Comfort temperature limit in °C (optional)
   */
  async getThermalRunway(
    siteId: string,
    currentTemp?: number,
    comfortLimit?: number
  ): Promise<ThermalRunwayResponse> {
    const params = new URLSearchParams();
    params.append("site_id", siteId);
    if (currentTemp !== undefined) {
      params.append("current_temp", currentTemp.toString());
    }
    if (comfortLimit !== undefined) {
      params.append("comfort_limit", comfortLimit.toString());
    }
    try {
      return await fetchApi<ThermalRunwayResponse>(`/api/optimization/thermal-runway?${params.toString()}`);
    } catch (error) {
      if (isExpectedApiError(error)) {
        return {
          site_id: siteId,
          site_name: siteId,
          current_temperature: currentTemp ?? 24,
          comfort_limit: comfortLimit ?? 27,
          thermal_runway_minutes: 0,
          comfort_breach_time: null,
          calculation_method: "fallback",
          building_params: {
            thermal_mass: 0,
            insulation_factor: 0,
            internal_heat_gain: 0,
          },
          weather_forecast: {
            outside_temp: 0,
            solar_load: 0,
            humidity: 0,
          },
        };
      }
      throw error;
    }
  },

  /**
   * Get optimization scenario by ID
   * @param scenarioId - Scenario ID from optimization_scenarios.json
   */
  async getOptimizationScenario(scenarioId: string): Promise<OptimizationScenario> {
    // Note: This endpoint doesn't exist yet in backend, but we'll implement it
    // For now, we'll fetch from the scenarios JSON file
    const response = await fetchApi<OptimizationScenario[]>(`/api/optimization/scenarios`);
    const scenario = response.find(s => s.scenario_id === scenarioId);
    if (!scenario) {
      throw new Error(`Scenario ${scenarioId} not found`);
    }
    return scenario;
  },

  /**
   * Get all optimization scenarios
   */
  async getOptimizationScenarios(): Promise<OptimizationScenario[]> {
    try {
      return await fetchApi<OptimizationScenario[]>(`/api/optimization/scenarios`);
    } catch (error) {
      if (isExpectedApiError(error)) return [];
      throw error;
    }
  },

  // ============= AI Optimization API Methods (Phase 8) =============

  /**
   * Get optimization status for a specific site
   * @param siteId - Site ID
   */
  async getOptimizationStatus(siteId: string): Promise<OptimizationStatusResponse> {
    try {
      return await fetchApi<OptimizationStatusResponse>(`/api/optimization/status/${siteId}`);
    } catch (error) {
      if (isExpectedApiError(error)) {
        return {
          site_id: siteId,
          optimization_enabled: false,
          optimization_status: "unknown",
          optimization_settings: {
            mode: "supervised",
            last_analysis: null,
            analysis_interval_minutes: 15,
          },
          last_recommendation: null,
          last_optimization: null,
          optimization_history: [],
        };
      }
      throw error;
    }
  },

  /**
   * Analyze building for optimization opportunities
   * @param siteId - Site ID to analyze
   * @param currentConditions - Optional current conditions (if not provided, system will fetch)
   */
  async analyzeOptimization(
    siteId: string,
    currentConditions?: Record<string, any>
  ): Promise<{ recommendation: OptimizationRecommendation; validation: any }> {
    const body: Record<string, any> = { site_id: siteId };
    if (currentConditions) {
      body.current_conditions = currentConditions;
    }
    return fetchApi(`/api/optimization/analyze`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /**
   * Approve and apply optimization recommendation
   * @param siteId - Site ID
   * @param recommendationId - Recommendation ID to approve
   * @param setpointsToApply - Array of setpoint changes to apply
   */
  async approveOptimization(
    siteId: string,
    recommendationId: string,
    setpointsToApply: Array<{ device_id?: string; equipment_id?: string; point_name?: string; point?: string; value: number }>
  ): Promise<{ success: boolean; results: any[] }> {
    // Validate setpoints array is not empty
    if (!setpointsToApply || setpointsToApply.length === 0) {
      throw new Error("Cannot approve optimization: no setpoints to apply");
    }

    // Map frontend field names to backend expected field names (accept either format)
    const mappedSetpoints = setpointsToApply.map(sp => {
      const deviceId = sp.device_id || sp.equipment_id;
      const pointName = sp.point_name || sp.point;
      if (!deviceId || !pointName || sp.value === undefined) {
        throw new Error(`Invalid setpoint: missing required fields (device_id: ${deviceId}, point_name: ${pointName}, value: ${sp.value})`);
      }
      return {
        device_id: deviceId,
        point_name: pointName,
        value: sp.value,
      };
    });

    return fetchApi(`/api/optimization/approve`, {
      method: "POST",
      body: JSON.stringify({
        site_id: siteId,
        recommendation_id: recommendationId,
        setpoints_to_apply: mappedSetpoints,
      }),
    });
  },

  /**
   * Toggle optimization on/off for a site
   * @param siteId - Site ID
   * @param enabled - Whether to enable optimization
   */
  async toggleOptimization(
    siteId: string,
    enabled: boolean
  ): Promise<OptimizationStatusResponse> {
    return fetchApi(`/api/optimization/toggle/${siteId}`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
  },

  /**
   * Get SENTINEL processing state for a site
   */
  async getSiteProcessing(siteId: string): Promise<{ site_id: string; sentinel_processing_enabled: boolean }> {
    return fetchApi(`/api/sites/${siteId}/processing`);
  },

  /**
   * Toggle SENTINEL processing for a site (mute/unmute intelligence layer)
   */
  async toggleSiteProcessing(
    siteId: string,
    enabled: boolean
  ): Promise<{ site_id: string; sentinel_processing_enabled: boolean }> {
    return fetchApi(`/api/sites/${siteId}/processing`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
  },

  /**
   * Start pre-cooling sequence for a site
   * @param siteId - Site ID
   * @param scenarioId - Optional scenario ID
   */
  async startPrecooling(
    siteId: string,
    scenarioId?: string
  ): Promise<{ success: boolean; status: string; started_at: string; actions: any[]; message: string }> {
    return fetchApi(`/api/optimization/precooling/${siteId}/start`, {
      method: "POST",
      body: JSON.stringify({ scenario_id: scenarioId }),
    });
  },

  /**
   * Stop pre-cooling for a site
   * @param siteId - Site ID
   */
  async stopPrecooling(siteId: string): Promise<{ success: boolean; status: string; message: string }> {
    return fetchApi(`/api/optimization/precooling/${siteId}/stop`, {
      method: "POST",
    });
  },

  /**
   * Get pre-cooling status for a site
   * @param siteId - Site ID
   */
  async getPrecoolingStatus(siteId: string): Promise<{ status: string; started_at?: string; actions?: any[] }> {
    try {
      return await fetchApi(`/api/optimization/precooling/${siteId}/status`);
    } catch (error) {
      if (isExpectedApiError(error)) {
        return { status: "unknown", actions: [] };
      }
      throw error;
    }
  },

  /**
   * Get latest pending recommendation for a site
   * @param siteId - Site ID
   */
  async getLatestRecommendation(siteId: string): Promise<OptimizationRecommendation | null> {
    try {
      const status = await this.getOptimizationStatus(siteId);
      // Only return recommendation if it has actual recommendations to show
      if (status.last_recommendation &&
          status.last_recommendation.recommendations &&
          status.last_recommendation.recommendations.length > 0) {
        return status.last_recommendation;
      }
      return null;
    } catch (error) {
      console.error(`Failed to fetch latest recommendation for site ${siteId}:`, error);
      return null;
    }
  },

  /**
   * Reject optimization recommendation
   * @param siteId - Site ID
   * @param recommendationId - Recommendation ID to reject
   * @param reason - Optional rejection reason
   */
  async rejectOptimization(
    _siteId: string,
    _recommendationId: string,
    reason?: string
  ): Promise<{ success: boolean; message: string }> {
    // Note: This endpoint doesn't exist in backend yet
    // For now, we'll update the status to "optimized" (current settings kept)
    // In production, this would call POST /api/optimization/reject
    try {
      // Simulate API call - in production, this would be:
      // return fetchApi(`/api/optimization/reject`, {
      //   method: "POST",
      //   body: JSON.stringify({
      //     site_id: siteId,
      //     recommendation_id: recommendationId,
      //     reason,
      //   }),
      // });

      // For now, just return success
      await new Promise((resolve) => setTimeout(resolve, 500));
      return {
        success: true,
        message: reason ? `Recommendation rejected: ${reason}` : "Recommendation rejected",
      };
    } catch (error) {
      console.error("Failed to reject recommendation:", error);
      throw error;
    }
  },

  /**
   * Defer optimization recommendation
   * @param siteId - Site ID
   * @param recommendationId - Recommendation ID to defer
   * @param deferMinutes - Minutes to defer (default: 15)
   */
  async deferOptimization(
    _siteId: string,
    _recommendationId: string,
    deferMinutes: number = 15
  ): Promise<{ success: boolean; message: string; deferUntil: string }> {
    // Note: This endpoint doesn't exist in backend yet
    // In production, this would call POST /api/optimization/defer
    // and backend would re-queue the recommendation for later

    const deferUntil = new Date(Date.now() + deferMinutes * 60 * 1000).toISOString();

    try {
      // Simulate API call - in production, this would be:
      // return fetchApi(`/api/optimization/defer`, {
      //   method: "POST",
      //   body: JSON.stringify({
      //     site_id: siteId,
      //     recommendation_id: recommendationId,
      //     defer_minutes: deferMinutes,
      //   }),
      // });

      // For now, just return success
      await new Promise((resolve) => setTimeout(resolve, 300));
      return {
        success: true,
        message: `Recommendation deferred for ${deferMinutes} minutes`,
        deferUntil,
      };
    } catch (error) {
      console.error("Failed to defer recommendation:", error);
      throw error;
    }
  },

  // ============= Device API Methods =============

  /**
   * Get all devices with optional filtering
   * @param siteId - Optional site ID filter
   * @param deviceType - Optional device type filter
   * @param protocol - Optional protocol filter
   */
  async getDevices(
    siteId?: string,
    deviceType?: string,
    protocol?: string
  ): Promise<Device[]> {
    const params = new URLSearchParams();
    if (siteId) {
      params.append("site_id", siteId);
    }
    if (deviceType) {
      params.append("device_type", deviceType);
    }
    if (protocol) {
      params.append("protocol", protocol);
    }
    const queryString = params.toString();
    return fetchApi<Device[]>(`/api/devices${queryString ? `?${queryString}` : ""}`);
  },

  /**
   * Get a specific device by ID
   * @param deviceId - Device ID
   */
  async getDevice(deviceId: string): Promise<Device> {
    return fetchApi<Device>(`/api/devices/${deviceId}`);
  },

  /**
   * Get all points for a device
   * @param deviceId - Device ID
   */
  async getDevicePoints(deviceId: string): Promise<Record<string, DevicePoint>> {
    const response = await fetchApi<{ points: Record<string, DevicePoint> }>(
      `/api/devices/${deviceId}/points`
    );
    return response.points;
  },

  /**
   * Read a value from a device point
   * @param deviceId - Device ID
   * @param pointName - Point name
   */
  async readDevicePoint(deviceId: string, pointName: string): Promise<DeviceValue> {
    return fetchApi<DeviceValue>(`/api/devices/${deviceId}/points/${pointName}`);
  },

  /**
   * Write a value to a device point (control command)
   * @param deviceId - Device ID
   * @param point - Point name to control
   * @param value - Value to write
   * @param priority - Write priority (1-16, default: 8)
   */
  async controlDevice(
    deviceId: string,
    point: string,
    value: number | boolean,
    priority: number = 8
  ): Promise<DeviceControlResponse> {
    const body = {
      point,
      value,
      priority,
    };
    return fetchApi<DeviceControlResponse>(`/api/devices/${deviceId}/control`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /**
   * Get device operational status
   * @param deviceId - Device ID
   */
  async getDeviceStatus(deviceId: string): Promise<DeviceStatus> {
    return fetchApi<DeviceStatus>(`/api/devices/${deviceId}/status`);
  },

  /**
   * Get all devices at a specific site
   * @param siteId - Site ID
   */
  async getSiteDevices(siteId: string): Promise<Device[]> {
    return fetchApi<Device[]>(`/api/sites/${siteId}/devices`);
  },

  // ============= Audit API Methods =============

  /**
   * Get audit logs with filtering and pagination
   * @param page - Page number (default: 1)
   * @param pageSize - Items per page (default: 50)
   * @param startTime - Start time filter
   * @param endTime - End time filter
   * @param deviceId - Filter by device ID
   * @param action - Filter by action type
   * @param user - Filter by user
   * @param result - Filter by result
   */
  async getAuditLogs(
    page: number = 1,
    pageSize: number = 50,
    startTime?: string,
    endTime?: string,
    deviceId?: string,
    action?: string,
    user?: string,
    result?: string
  ): Promise<AuditLogsResponse> {
    const params = new URLSearchParams();
    params.append("page", page.toString());
    params.append("page_size", pageSize.toString());
    if (startTime) params.append("start_time", startTime);
    if (endTime) params.append("end_time", endTime);
    if (deviceId) params.append("device_id", deviceId);
    if (action) params.append("action", action);
    if (user) params.append("user", user);
    if (result) params.append("result", result);

    return fetchApi<AuditLogsResponse>(`/api/audit/logs?${params.toString()}`);
  },

  /**
   * Get a specific audit log entry by ID
   * @param entryId - Audit log entry ID
   */
  async getAuditLogEntry(entryId: string): Promise<AuditLogEntryResponse> {
    return fetchApi<AuditLogEntryResponse>(`/api/audit/logs/${entryId}`);
  },

  /**
   * Get audit log statistics
   */
  async getAuditStats(): Promise<AuditStatsResponse> {
    return fetchApi<AuditStatsResponse>(`/api/audit/stats`);
  },

  /**
   * Generate demo audit data for testing
   */
  async generateDemoAuditData(): Promise<DemoAuditDataResponse> {
    return fetchApi<DemoAuditDataResponse>(`/api/audit/demo-data`, {
      method: "POST",
    });
  },

  /**
   * Get recent audit logs for inline display (RecentActions component)
   * @param limit - Maximum number of entries to return (default: 10)
   * @param deviceId - Optional filter by device ID
   */
  async getRecentAuditLogs(limit: number = 10, deviceId?: string): Promise<AuditEntry[]> {
    const params = new URLSearchParams();
    params.append("page", "1");
    params.append("page_size", limit.toString());
    if (deviceId) {
      const normalizedDeviceId = deviceId.includes(".")
        ? deviceId.split(".")[0]
        : deviceId;
      params.append("device_id", normalizedDeviceId);
    }

    const response = await fetchApi<AuditLogsResponse>(`/api/audit/logs?${params.toString()}`);

    // Transform AuditLogEntryResponse to AuditEntry for RecentActions component
    return response.entries.map((entry) => ({
      id: entry.id,
      timestamp: typeof entry.timestamp === 'string' ? entry.timestamp : new Date(entry.timestamp).toISOString(),
      device_id: entry.device_id || "unknown",
      device_name: entry.metadata?.device_name || entry.device_id || "Unknown Device",
      action: entry.action,
      point: entry.point_name || "",
      old_value: entry.old_value,
      new_value: entry.new_value,
      user: entry.user,
      success: entry.result === "success",
      message: entry.error_message,
    }));
  },

  /**
   * Get safety status for a specific device
   * @param deviceId - Device ID
   */
  async getDeviceSafetyStatus(deviceId: string): Promise<{ overall_status: 'safe' | 'warning' | 'blocked' | 'alarm' | 'unknown' }> {
    return fetchApi<{ overall_status: 'safe' | 'warning' | 'blocked' | 'alarm' | 'unknown' }>(`/api/devices/${deviceId}/safety-status`);
  },

  /**
   * Get full safety status details for a specific device
   * @param deviceId - Device ID
   */
  async getDeviceFullSafetyStatus(deviceId: string): Promise<DeviceSafetyStatus> {
    return fetchApi<DeviceSafetyStatus>(`/api/devices/${deviceId}/safety-status`);
  },

  // ============= Settings API Methods =============

  /**
   * Get all settings
   */
  async getSettings(): Promise<Settings> {
    return fetchApi<Settings>("/api/settings");
  },

  /**
   * Update all settings
   * @param settingsData - Settings object to update
   */
  async updateSettings(settingsData: Partial<Settings>): Promise<Settings> {
    return fetchApi<Settings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(settingsData),
    });
  },

  /**
   * Get health score thresholds
   */
  async getHealthThresholds(): Promise<HealthThresholds> {
    return fetchApi<HealthThresholds>("/api/settings/health-thresholds");
  },

  /**
   * Update health score thresholds
   * @param thresholds - Threshold values to update
   */
  async updateHealthThresholds(thresholds: HealthThresholds): Promise<HealthThresholds> {
    return fetchApi<HealthThresholds>("/api/settings/health-thresholds", {
      method: "PUT",
      body: JSON.stringify(thresholds),
    });
  },

  // ============= Safety Rules API Methods =============

  /**
   * Get all safety rules
   * @param deviceType - Optional filter by device type
   * @param enabled - Optional filter by enabled status
   */
  async getSafetyRules(deviceType?: string, enabled?: boolean): Promise<SafetyRulesResponse> {
    const params = new URLSearchParams();
    if (deviceType) params.append("device_type", deviceType);
    if (enabled !== undefined) params.append("enabled", String(enabled));
    const queryString = params.toString();
    return fetchApi<SafetyRulesResponse>(`/api/safety/rules${queryString ? `?${queryString}` : ""}`);
  },

  /**
   * Get a specific safety rule by ID
   * @param ruleId - Rule ID
   */
  async getSafetyRule(ruleId: string): Promise<SafetyRule> {
    return fetchApi<SafetyRule>(`/api/safety/rules/${ruleId}`);
  },

  /**
   * Create a new safety rule
   * @param ruleData - Rule data
   */
  async createSafetyRule(ruleData: Partial<SafetyRule>): Promise<{ success: boolean; rule: SafetyRule; message: string }> {
    return fetchApi(`/api/safety/rules`, {
      method: "POST",
      body: JSON.stringify(ruleData),
    });
  },

  /**
   * Update an existing safety rule
   * @param ruleId - Rule ID
   * @param ruleData - Rule data to update
   */
  async updateSafetyRule(ruleId: string, ruleData: Partial<SafetyRule>): Promise<{ success: boolean; rule: SafetyRule; message: string }> {
    return fetchApi(`/api/safety/rules/${ruleId}`, {
      method: "PUT",
      body: JSON.stringify(ruleData),
    });
  },

  /**
   * Delete a safety rule
   * @param ruleId - Rule ID
   */
  async deleteSafetyRule(ruleId: string): Promise<{ success: boolean; message: string }> {
    return fetchApi(`/api/safety/rules/${ruleId}`, {
      method: "DELETE",
    });
  },

  /**
   * Toggle a safety rule's enabled status
   * @param ruleId - Rule ID
   * @param enabled - Whether to enable or disable
   */
  async toggleSafetyRule(ruleId: string, enabled: boolean): Promise<{ success: boolean; rule_id: string; enabled: boolean; message: string }> {
    return fetchApi(`/api/safety/rules/${ruleId}/toggle`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
  },

  /**
   * Get safety health status
   */
  async getSafetyHealth(): Promise<{ status: string; initialized: boolean; rule_count: number }> {
    return fetchApi(`/api/safety/health`);
  },

  // ============ Autonomous System APIs ============

  /**
   * Get autonomous system status
   */
  async getAutonomousStatus(): Promise<{
    enabled: boolean;
    active_decisions: number;
    total_decisions_today: number;
    success_rate: number;
    current_escalation_level: number;
    last_decision_time: string | null;
    safety_score: number;
  }> {
    return fetchApi(`/api/autonomous/status`);
  },

  /**
   * Enable autonomous mode
   */
  async enableAutonomousMode(): Promise<{ success: boolean; message: string; mode?: string }> {
    return fetchApi(`/api/autonomous/enable`, {
      method: "POST",
    });
  },

  /**
   * Disable autonomous mode
   */
  async disableAutonomousMode(): Promise<{
    success: boolean;
    message: string;
    cancelled_decisions: number;
  }> {
    return fetchApi(`/api/autonomous/disable`, {
      method: "POST",
    });
  },

  /**
   * Get autonomous decision history
   * @param params - Optional filters (limit, device_id, status)
   */
  async getAutonomousDecisions(params?: {
    limit?: number;
    device_id?: string;
    status?: string;
  }): Promise<{ data: any[] }> {
    const queryParams = new URLSearchParams();
    if (params?.limit) queryParams.append("limit", params.limit.toString());
    if (params?.device_id) queryParams.append("device_id", params.device_id);
    if (params?.status) queryParams.append("status", params.status);

    return fetchApi(`/api/autonomous/decisions?${queryParams.toString()}`);
  },

  /**
   * Get current boundary status
   * @param deviceId - Optional specific device ID
   */
  async getBoundaryStatus(deviceId?: string): Promise<{ data: any }> {
    const url = deviceId
      ? `/api/autonomous/boundaries?device_id=${deviceId}`
      : `/api/autonomous/boundaries`;

    return fetchApi(url);
  },

  /**
   * Get escalation alerts
   */
  async getEscalationAlerts(): Promise<{ data: any[] }> {
    return fetchApi(`/api/autonomous/escalation/status`);
  },

  /**
   * Acknowledge an escalation alert
   * @param escalationId - ID of the escalation to acknowledge
   * @param comment - Optional comment
   */
  async acknowledgeEscalation(
    escalationId: string,
    acknowledgedBy: string,
    comment?: string
  ): Promise<{ success: boolean; message: string; mode?: string }> {
    return fetchApi(`/api/safety/escalation/acknowledge`, {
      method: "POST",
      body: JSON.stringify({
        escalation_id: escalationId,
        acknowledged_by: acknowledgedBy,
        comment,
      }),
    });
  },

  /**
   * Execute emergency stop
   */
  async emergencyStop(): Promise<{
    success: boolean;
    emergency_id: string;
    actions_taken: any[];
    response_time_seconds: number;
    devices_affected: number;
    message: string;
  }> {
    return fetchApi(`/api/safety/escalation/emergency-stop`, {
      method: "POST",
    });
  },

  /**
   * Test escalation notification
   * @param deviceId - Device ID for test
   * @param escalationLevel - Escalation level to test
   */
  async testEscalation(
    deviceId: string,
    escalationLevel: number
  ): Promise<{ success: boolean; escalation_event: any; notifications_sent: any }> {
    return fetchApi(`/api/safety/escalation/test`, {
      method: "POST",
      body: JSON.stringify({
        device_id: deviceId,
        escalation_level: escalationLevel,
      }),
    });
  },

  /**
   * Update safety boundary configuration for a device
   * @param deviceId - Device ID
   * @param config - Boundary configuration
   */
  async updateBoundary(
    deviceId: string,
    config: any
  ): Promise<{ success: boolean; message: string; cancelled_decisions?: number; mode?: string }> {
    return fetchApi(`/api/autonomous/boundaries/update`, {
      method: "POST",
      body: JSON.stringify({
        device_id: deviceId,
        ...config,
      }),
    });
  },

  /**
   * Toggle autonomous mode on/off
   * @param enabled - Whether to enable or disable autonomous mode
   */
  async toggleAutonomousMode(enabled: boolean): Promise<{
    success: boolean;
    message: string;
  }> {
    if (enabled) {
      return this.enableAutonomousMode();
    } else {
      return this.disableAutonomousMode();
    }
  },

  // ============= Equipment Lookup API Methods (Phase 19) =============

  /**
   * Look up fault code for equipment
   * @param manufacturer - Equipment manufacturer (e.g., "Carrier", "Trane")
   * @param faultCode - Fault code (e.g., "E4", "FAULT_001")
   * @param model - Equipment model (optional)
   * @param equipmentType - Equipment type (optional)
   */
  async lookupFaultCode(
    manufacturer: string,
    faultCode: string,
    model?: string,
    equipmentType?: string
  ): Promise<any> {
    const params = new URLSearchParams();
    params.append("manufacturer", manufacturer);
    params.append("fault_code", faultCode);
    if (model) params.append("model", model);
    if (equipmentType) params.append("equipment_type", equipmentType);
    return fetchApi(`/api/equipment-lookup/fault-code?${params.toString()}`);
  },

  /**
   * Search for parts across South African suppliers
   * @param partNumber - OEM or generic part number
   * @param partDescription - Part description to search
   * @param manufacturer - Filter by manufacturer
   * @param includeAlternatives - Include generic alternatives (default: true)
   */
  async searchParts(
    partNumber?: string,
    partDescription?: string,
    manufacturer?: string,
    includeAlternatives: boolean = true
  ): Promise<any[]> {
    const params = new URLSearchParams();
    if (partNumber) params.append("part_number", partNumber);
    if (partDescription) params.append("part_description", partDescription);
    if (manufacturer) params.append("manufacturer", manufacturer);
    params.append("include_alternatives", String(includeAlternatives));
    return fetchApi(`/api/equipment-lookup/parts?${params.toString()}`);
  },

  /**
   * Natural language search for equipment issues
   * @param query - Natural language search query
   * @param manufacturer - Filter by manufacturer (optional)
   * @param model - Filter by model (optional)
   */
  async searchEquipmentIssue(
    query: string,
    manufacturer?: string,
    model?: string
  ): Promise<any> {
    const params = new URLSearchParams();
    params.append("query", query);
    if (manufacturer) params.append("manufacturer", manufacturer);
    if (model) params.append("model", model);
    return fetchApi(`/api/equipment-lookup/search?${params.toString()}`, {
      method: "POST",
    });
  },

  // ============= Dashboard Preferences =============

  /**
   * Get user's dashboard preferences
   * @param userId - Optional user ID (defaults to 'default-user')
   */
  async getDashboardPreferences(userId?: string): Promise<DashboardPreferencesResponse> {
    const headers: Record<string, string> = {};
    if (userId) headers["X-User-ID"] = userId;
    return fetchApi("/api/preferences/dashboard", { headers });
  },

  /**
   * Update user's dashboard preferences
   * @param preferences - Dashboard preferences to save
   * @param userId - Optional user ID
   */
  async updateDashboardPreferences(
    preferences: DashboardPreferences,
    userId?: string
  ): Promise<DashboardPreferencesResponse> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (userId) headers["X-User-ID"] = userId;
    return fetchApi("/api/preferences/dashboard", {
      method: "PUT",
      headers,
      body: JSON.stringify(preferences),
    });
  },

  /**
   * Reset dashboard preferences to defaults
   * @param userId - Optional user ID
   */
  async resetDashboardPreferences(userId?: string): Promise<{ success: boolean; message: string }> {
    const headers: Record<string, string> = {};
    if (userId) headers["X-User-ID"] = userId;
    return fetchApi("/api/preferences/dashboard", {
      method: "DELETE",
      headers,
    });
  },
};

// Dashboard Preferences interfaces
export interface DashboardPreferences {
  visible_kpi_cards: string[];
  visible_sections: string[];
  kpi_card_order: string[];
  section_order: string[];
  default_energy_period: number;
  default_energy_site_id: string | null;
}

export interface DashboardPreferencesResponse {
  user_id: string;
  preferences: DashboardPreferences;
  created_at?: string;
  updated_at?: string;
}

// ============= Validation Checklist Interfaces (Phase 17) =============

// Building status enum
export type BuildingStatus = 'draft' | 'pending_validation' | 'active' | 'suspended';

// Checklist item from validation
export interface ChecklistItem {
  id: string;
  category: string;
  name: string;
  description: string;
  status: 'pass' | 'fail' | 'warning' | 'not_checked';
  value?: any;
  threshold?: any;
  details?: string;
}

// Complete validation checklist
export interface ValidationChecklist {
  site_id: string;
  site_name?: string;
  status: BuildingStatus;
  checked_at: string;
  items: ChecklistItem[];
  summary: {
    passed: number;
    failed: number;
    warnings: number;
  };
  can_activate: boolean;
  blocking_issues: string[];
}

// Activation result
export interface ActivationResult {
  success: boolean;
  site_id: string;
  new_status: BuildingStatus;
  message: string;
  validation_errors: string[];
}

// ============= Integration Monitoring Interfaces (Phase 16) =============

export interface IntegrationHealthSummary {
  sources_count: number;
  active_sources: number;
  last_sync: string | null;
  total_records_ingested: number;
  total_points_mapped: number;
  unmatched_points: number;
  recent_errors_count: number;
  alerts: IntegrationAlert[];
}

export interface IntegrationAlert {
  id: string;
  type: 'stale_data' | 'sync_failure' | 'high_error_rate' | 'low_match_coverage';
  severity: 'critical' | 'warning' | 'info';
  source_id?: string;
  message: string;
  timestamp: string;
}

export interface DataQualityMetrics {
  match_coverage: number;
  data_freshness_hours: number;
  error_rate: number;
  duplicate_rate: number;
  overall_score: number;
  trend: 'improving' | 'stable' | 'degrading';
}

export interface SyncJobSummary {
  id: string;
  log_source_id: string;
  source_name?: string;
  status: 'running' | 'success' | 'failed' | 'partial';
  records_processed: number;
  records_inserted: number;
  records_skipped: number;
  records_failed: number;
  processing_time_ms: number;
  started_at: string;
  completed_at: string | null;
  error_message?: string;
}

// ============= Integration API Interfaces (Phase 15) =============

export interface FormatDetectionResult {
  file_format: 'csv' | 'excel' | 'json';
  delimiter: string;
  vendor: string;
  confidence: number;
  suggested_mappings: Record<string, string>;
  row_count: number;
  sample_data?: Array<Record<string, any>>;
}

export interface ColumnMapping {
  source_column: string;
  target_field: string;
  transform_type?: 'none' | 'date_parse' | 'number_parse' | 'boolean_parse';
}

export interface PointMatch {
  bms_point_id: string;
  bms_point_name: string;
  asset_id?: string;
  asset_tag?: string;
  confidence: 'high' | 'medium' | 'low';
  alternatives?: Array<{
    asset_id: string;
    asset_tag: string;
    confidence: number;
  }>;
}

// Integration Monitoring API methods (Phase 16)
export const monitoringApi = {
  /**
   * Get integration health summary
   * @param siteId - Optional building ID filter
   */
  getIntegrationHealth: async (siteId?: string): Promise<IntegrationHealthSummary> => {
    const params = new URLSearchParams();
    if (siteId) params.set("site_id", siteId);
    const endpoint = `/api/integration/health${params.toString() ? `?${params.toString()}` : ""}`;
    try {
      return await fetchApi<IntegrationHealthSummary>(endpoint);
    } catch (error) {
      if (isExpectedApiError(error)) {
        return {
          sources_count: 0,
          active_sources: 0,
          last_sync: null,
          total_records_ingested: 0,
          total_points_mapped: 0,
          unmatched_points: 0,
          recent_errors_count: 0,
          alerts: [],
        };
      }
      throw error;
    }
  },

  /**
   * Get data quality metrics for a building
   * @param siteId - Building ID (required)
   */
  getDataQualityMetrics: async (siteId: string): Promise<DataQualityMetrics> => {
    try {
      return await fetchApi<DataQualityMetrics>(`/api/integration/quality-metrics/${siteId}`);
    } catch (error) {
      if (isExpectedApiError(error)) {
        return {
          match_coverage: 0,
          data_freshness_hours: 0,
          error_rate: 0,
          duplicate_rate: 0,
          overall_score: 0,
          trend: "stable",
        };
      }
      throw error;
    }
  },

  /**
   * Get sync job history
   * @param siteId - Optional building ID filter
   * @param days - Number of days of history (default: 7)
   */
  getSyncJobs: async (siteId?: string, days: number = 7): Promise<SyncJobSummary[]> => {
    const params = new URLSearchParams({ days: days.toString() });
    if (siteId) params.set('site_id', siteId);
    try {
      return await fetchApi<SyncJobSummary[]>(`/api/integration/sync-jobs?${params.toString()}`);
    } catch (error) {
      if (isExpectedApiError(error)) return [];
      throw error;
    }
  },

  /**
   * Get unmatched points for point matching review
   * @param siteId - Building ID
   * @param limit - Maximum number of points to return (default: 10)
   * @param offset - Pagination offset (default: 0)
   */
  getUnmatchedPoints: async (siteId?: string, limit: number = 10, offset: number = 0): Promise<{
    points: Array<{
      point_id: string;
      point_name: string;
      last_seen: string;
      occurrence_count: number;
    }>;
    total: number;
  }> => {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
    });
    if (siteId) params.set('site_id', siteId);
    try {
      return await fetchApi<{
        points: Array<{
          point_id: string;
          point_name: string;
          last_seen: string;
          occurrence_count: number;
        }>;
        total: number;
      }>(`/api/integration/unmatched-points?${params.toString()}`);
    } catch (error) {
      if (isExpectedApiError(error)) return { points: [], total: 0 };
      throw error;
    }
  },
};

// Integration API methods
export const integrationApi = {
  /**
   * Detect format from uploaded BMS log file
   * @param file - File to analyze
   */
  detectFormat: async (file: File): Promise<FormatDetectionResult> => {
    const formData = new FormData();
    formData.append('file', file);

    const token = localStorage.getItem("sentinel_token");
    const response = await fetch(`${API_BASE_URL}/api/integration/detect-format`, {
      method: 'POST',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: formData
    });

    if (!response.ok) {
      throw new Error('Failed to detect format');
    }

    return response.json();
  },

  /**
   * Save column mappings for log source
   * @param siteId - Building ID
   * @param logSourceId - Log source ID
   * @param mappings - Column mappings to save
   */
  saveColumnMappings: async (siteId: string, logSourceId: string, mappings: ColumnMapping[]): Promise<void> => {
    const token = localStorage.getItem("sentinel_token");
    const response = await fetch(`${API_BASE_URL}/api/integration/mappings`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ site_id: siteId, log_source_id: logSourceId, mappings })
    });

    if (!response.ok) {
      throw new Error('Failed to save mappings');
    }
  },

  /**
   * Match BMS points to CAFM assets
   * @param siteId - Building ID
   * @param logSourceId - Log source ID
   * @param bmsPoints - List of BMS point IDs
   */
  matchPoints: async (siteId: string, logSourceId: string, bmsPoints: string[]): Promise<PointMatch[]> => {
    const token = localStorage.getItem("sentinel_token");
    const response = await fetch(`${API_BASE_URL}/api/integration/match-points`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ site_id: siteId, log_source_id: logSourceId, bms_points: bmsPoints })
    });

    if (!response.ok) {
      throw new Error('Failed to match points');
    }

    return response.json();
  },

  /**
   * Ingest log file data
   * @param siteId - Building ID
   * @param logSourceId - Log source ID
   * @param dryRun - If true, validate without processing
   */
  ingestLogs: async (siteId: string, logSourceId: string, dryRun: boolean = false): Promise<void> => {
    const token = localStorage.getItem("sentinel_token");
    const response = await fetch(`${API_BASE_URL}/api/integration/ingest`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ site_id: siteId, log_source_id: logSourceId, dry_run: dryRun })
    });

    if (!response.ok) {
      throw new Error('Failed to ingest logs');
    }
  }
};

// Validation API methods (Phase 17 - Go-Live Checklist)
export const validationApi = {
  /**
   * Get validation checklist for a building
   * @param siteId - Building ID
   */
  getChecklist: async (siteId: string): Promise<ValidationChecklist> => {
    return fetchApi<ValidationChecklist>(`/api/integration/buildings/${siteId}/validation-checklist`);
  },

  /**
   * Get current building status
   * @param siteId - Building ID
   */
  getStatus: async (siteId: string): Promise<{ status: BuildingStatus; last_validated?: string }> => {
    return fetchApi<{ status: BuildingStatus; last_validated?: string }>(
      `/api/integration/buildings/${siteId}/status`
    );
  },

  /**
   * Run validation and update building status
   * @param siteId - Building ID
   */
  validate: async (siteId: string): Promise<ValidationChecklist> => {
    return fetchApi<ValidationChecklist>(`/api/integration/buildings/${siteId}/validate`, {
      method: "POST",
    });
  },

  /**
   * Activate a building after successful validation
   * @param siteId - Building ID
   */
  activate: async (siteId: string): Promise<ActivationResult> => {
    return fetchApi<ActivationResult>(`/api/integration/buildings/${siteId}/activate`, {
      method: "POST",
    });
  },

  /**
   * Suspend (deactivate) a building
   * @param siteId - Building ID
   */
  suspend: async (siteId: string): Promise<{ status: BuildingStatus }> => {
    return fetchApi<{ status: BuildingStatus }>(
      `/api/integration/buildings/${siteId}/suspend`,
      { method: "POST" }
    );
  },
};

// ============= Lighting Interfaces (Phase 21) =============

// Lighting Controller interface
export interface LightingController {
  id: string;
  name: string;
  floor: string;
  zone_id: string;
  protocol_version: string;
  firmware_version: string;
  status: 'online' | 'offline' | 'error';
  sensors_count: number;
  luminaires_count: number;
  last_communication: string;
}

// Lighting Sensor interface (PIR occupancy sensor)
export interface LightingSensor {
  id: string;
  controller_id: string;
  desk_id: string;
  zone_id: string;
  floor: string;
  type: 'pir' | 'daylight' | 'combined';
  status: 'online' | 'offline' | 'error';
  occupied: boolean;
  last_motion: string | null;
  lux_level: number | null;
  battery_level: number | null;
}

// Lighting Luminaire interface
export interface LightingLuminaire {
  id: string;
  controller_id: string;
  zone_id: string;
  floor: string;
  type: 'led_panel' | 'downlight' | 'linear' | 'emergency';
  status: 'online' | 'offline' | 'fault';
  power_watts: number;
  brightness_percent: number;
  color_temp_kelvin: number | null;
  runtime_hours: number;
  fault_code: string | null;
}

// Zone Occupancy summary
export interface ZoneOccupancy {
  zone_id: string;
  zone_name: string;
  floor: string;
  total_sensors: number;
  occupied_sensors: number;
  occupancy_percent: number;
  avg_lux_level: number;
  status: 'busy' | 'moderate' | 'quiet' | 'empty';
  last_updated: string;
}

// Zone Lighting status
export interface ZoneLighting {
  zone_id: string;
  zone_name: string;
  floor: string;
  total_luminaires: number;
  active_luminaires: number;
  faulty_luminaires: number;
  total_power_watts: number;
  avg_brightness: number;
  energy_waste_detected: boolean;
  energy_waste_reason: string | null;
}

// Floor Summary
export interface FloorSummary {
  floor: string;
  floor_name: string;
  total_zones: number;
  total_sensors: number;
  occupied_sensors: number;
  occupancy_percent: number;
  total_luminaires: number;
  faulty_luminaires: number;
  total_power_watts: number;
  zones: ZoneOccupancy[];
}

// Building Occupancy overview
export interface BuildingOccupancy {
  site_id: string;
  site_name: string;
  total_floors: number;
  total_zones: number;
  total_sensors: number;
  occupied_sensors: number;
  occupancy_percent: number;
  total_luminaires: number;
  faulty_luminaires: number;
  total_power_watts: number;
  energy_waste_zones: number;
  floors: FloorSummary[];
  last_updated: string;
}

// Lighting System Stats
export interface LightingStats {
  total_controllers: number;
  online_controllers: number;
  total_sensors: number;
  online_sensors: number;
  total_luminaires: number;
  faulty_luminaires: number;
  current_occupancy_percent: number;
  current_power_watts: number;
  energy_today_kwh: number;
  energy_waste_alerts: number;
  last_sync: string;
}

// Lighting API methods
export const lightingApi = {
  /**
   * Get all lighting controllers
   * @param floor - Optional floor filter
   */
  getControllers: async (floor?: string): Promise<LightingController[]> => {
    const params = new URLSearchParams();
    if (floor) params.set('floor', floor);
    const queryString = params.toString();
    return fetchApi<LightingController[]>(`/api/lighting/controllers${queryString ? `?${queryString}` : ''}`);
  },

  /**
   * Get lighting sensors with optional filtering
   * @param zoneId - Optional zone ID filter
   */
  getSensors: async (zoneId?: string): Promise<LightingSensor[]> => {
    const params = new URLSearchParams();
    if (zoneId) params.set('zone_id', zoneId);
    const queryString = params.toString();
    return fetchApi<LightingSensor[]>(`/api/lighting/sensors${queryString ? `?${queryString}` : ''}`);
  },

  /**
   * Get sensor by desk ID
   * @param deskId - Desk identifier
   */
  getSensorByDesk: async (deskId: string): Promise<LightingSensor> => {
    return fetchApi<LightingSensor>(`/api/lighting/sensors/desk/${deskId}`);
  },

  /**
   * Get lighting luminaires with optional filtering
   * @param zoneId - Optional zone ID filter
   */
  getLuminaires: async (zoneId?: string): Promise<LightingLuminaire[]> => {
    const params = new URLSearchParams();
    if (zoneId) params.set('zone_id', zoneId);
    const queryString = params.toString();
    return fetchApi<LightingLuminaire[]>(`/api/lighting/luminaires${queryString ? `?${queryString}` : ''}`);
  },

  /**
   * Get faulty luminaires
   */
  getFaultyLuminaires: async (): Promise<LightingLuminaire[]> => {
    return fetchApi<LightingLuminaire[]>("/api/lighting/luminaires/faulty");
  },

  /**
   * Get zone occupancy data
   * @param zoneId - Zone ID
   */
  getZoneOccupancy: async (zoneId: string): Promise<ZoneOccupancy> => {
    return fetchApi<ZoneOccupancy>(`/api/lighting/zones/${zoneId}/occupancy`);
  },

  /**
   * Get zone lighting status
   * @param zoneId - Zone ID
   */
  getZoneLighting: async (zoneId: string): Promise<ZoneLighting> => {
    return fetchApi<ZoneLighting>(`/api/lighting/zones/${zoneId}/lighting`);
  },

  /**
   * Get floor summary
   * @param floor - Floor identifier (e.g., "L10", "L11", "L12")
   */
  getFloorSummary: async (floor: string): Promise<FloorSummary> => {
    return fetchApi<FloorSummary>(`/api/lighting/floors/${floor}/summary`);
  },

  /**
   * Get building occupancy overview
   */
  getSiteOccupancy: async (siteId?: string): Promise<BuildingOccupancy> => {
    try {
      const params = siteId ? `?site_id=${encodeURIComponent(siteId)}` : "";
      return await fetchApi<BuildingOccupancy>(`/api/lighting/building/occupancy${params}`);
    } catch (error) {
      if (isExpectedApiError(error)) {
        return {
          site_id: "unknown",
          site_name: "Unknown",
          total_floors: 0,
          total_zones: 0,
          total_sensors: 0,
          occupied_sensors: 0,
          occupancy_percent: 0,
          total_luminaires: 0,
          faulty_luminaires: 0,
          total_power_watts: 0,
          energy_waste_zones: 0,
          floors: [],
          last_updated: new Date().toISOString(),
        };
      }
      throw error;
    }
  },

  /**
   * Get lighting system statistics
   */
  getStats: async (): Promise<LightingStats> => {
    try {
      return await fetchApi<LightingStats>("/api/lighting/stats");
    } catch (error) {
      if (isExpectedApiError(error)) {
        return {
          total_controllers: 0,
          online_controllers: 0,
          total_sensors: 0,
          online_sensors: 0,
          total_luminaires: 0,
          faulty_luminaires: 0,
          current_occupancy_percent: 0,
          current_power_watts: 0,
          energy_today_kwh: 0,
          energy_waste_alerts: 0,
          last_sync: new Date().toISOString(),
        };
      }
      throw error;
    }
  },

  /**
   * Get combined zone summary (occupancy + lighting)
   * @param zoneId - Zone ID
   */
  getZoneSummary: async (zoneId: string): Promise<{ occupancy: ZoneOccupancy; lighting: ZoneLighting }> => {
    return fetchApi<{ occupancy: ZoneOccupancy; lighting: ZoneLighting }>(`/api/lighting/zones/${zoneId}/summary`);
  },
};

// Backward compatibility alias
export const daliApi = lightingApi;
export type DALIController = LightingController;
export type DALISensor = LightingSensor;
export type DALILuminaire = LightingLuminaire;
export type DALIStats = LightingStats;

// ============= Comfort Complaints Interfaces (Phase 23) =============

// Desk location model
export interface Desk {
  desk_id: string;
  floor: string;
  building: string;
  zone_id: string;
  near_window: boolean;
  near_diffuser: string | null;
  near_printer: boolean;
  department: string | null;
}

// HVAC Zone model
export interface HVACZone {
  zone_id: string;
  zone_name: string;
  floor: string;
  fcu_id: string;
  vav_id: string | null;
  temp_sensor: string;
  co2_sensor: string | null;
  typical_occupancy: number;
  area_sqm: number | null;
  setpoint: number;
  current_temp: number;
  status: string;
}

// Complaint diagnosis result
export interface ComplaintDiagnosis {
  complaint_id: string;
  desk: Desk;
  zone: HVACZone;
  diagnosis: string;
  root_cause: string;
  confidence: 'high' | 'medium' | 'low';
  suggestions: string[];
  auto_action_taken: string | null;
  needs_dispatch: boolean;
}

// Failure Classification interfaces (Phase 43-04)
export interface FailurePrediction {
  equipment_id: string;
  equipment_type: string;
  predicted_failure: string;
  confidence: number;
  all_failure_probabilities: Record<string, number>;
  contributing_factors: Array<{
    feature: string;
    value: number;
    importance: number;
    contribution: number;
  }>;
  timestamp: string;
}

export interface FleetFailureRisk {
  equipment_id: string;
  equipment_type: string;
  predicted_failure: string;
  confidence: number;
}

export interface FeatureImportanceItem {
  feature: string;
  importance: number;
}

export interface ClassificationModelInfo {
  equipment_type: string;
  model_path: string;
  metadata: {
    accuracy?: number;
    n_classes?: number;
    classes?: string[];
    n_samples?: number;
    trained_at?: string;
  };
}

// Desk BMS context for lookup
export interface DeskBMSContext {
  desk: Desk;
  bms_context: {
    zone: HVACZone;
    hvac_status: string;
    temp_reading: number;
    occupancy_percent: number;
  };
}

// Complaints API methods
export const complaintsApi = {
  /**
   * Submit a comfort complaint
   * @param deskId - Desk ID (e.g., "25", "L12-25")
   * @param complaintType - Type of complaint
   * @param userName - Optional user name
   * @param description - Optional description
   */
  submitComplaint: async (
    deskId: string,
    complaintType: string = 'too_hot',
    userName?: string,
    description?: string
  ): Promise<ComplaintDiagnosis> => {
    const params = new URLSearchParams({
      desk_id: deskId,
      complaint_type: complaintType,
    });
    if (userName) params.append('user_name', userName);
    if (description) params.append('description', description);

    const response = await fetch(`${API_BASE_URL}/api/complaints/submit?${params}`, {
      method: 'POST',
    });
    if (!response.ok) throw new Error('Failed to submit complaint');
    return response.json();
  },

  /**
   * Get desk info and BMS context
   * @param deskId - Desk ID
   */
  getDeskInfo: async (deskId: string): Promise<DeskBMSContext> => {
    const response = await fetch(`${API_BASE_URL}/api/complaints/desk/${deskId}`);
    if (!response.ok) throw new Error('Desk not found');
    return response.json();
  },

  /**
   * List all desks with optional filtering
   * @param floor - Optional floor filter
   * @param zoneId - Optional zone ID filter
   */
  listDesks: async (floor?: string, zoneId?: string): Promise<Desk[]> => {
    const params = new URLSearchParams();
    if (floor) params.append('floor', floor);
    if (zoneId) params.append('zone_id', zoneId);
    const query = params.toString();
    const response = await fetch(`${API_BASE_URL}/api/complaints/desks${query ? `?${query}` : ''}`);
    if (!response.ok) throw new Error('Failed to fetch desks');
    return response.json();
  },

  /**
   * List HVAC zones
   */
  listZones: async (): Promise<HVACZone[]> => {
    const response = await fetch(`${API_BASE_URL}/api/complaints/zones`);
    if (!response.ok) throw new Error('Failed to fetch zones');
    return response.json();
  },
};

// Classification API methods (Phase 43-04)
export const classificationApi = {
  /**
   * Get predicted failure type for equipment
   * @param equipmentId - Equipment ID
   */
  getFailureType: async (equipmentId: string): Promise<FailurePrediction> => {
    const response = await fetch(`${API_BASE_URL}/api/classification/failure-type/${equipmentId}`);
    if (!response.ok) throw new Error('Failed to get failure prediction');
    return response.json();
  },

  /**
   * Get fleet-wide failure risks
   * @param minConfidence - Minimum confidence threshold (default: 0.5)
   */
  getFleetRisks: async (minConfidence: number = 0.5): Promise<FleetFailureRisk[]> => {
    const response = await fetch(`${API_BASE_URL}/api/classification/fleet/risks?min_confidence=${minConfidence}`);
    if (!response.ok) throw new Error('Failed to get fleet risks');
    return response.json();
  },

  /**
   * Get feature importance for equipment type
   * @param equipmentType - Equipment type (chiller, ahu, etc.)
   * @param topN - Number of top features (default: 20)
   */
  getFeatureImportance: async (equipmentType: string, topN: number = 20): Promise<FeatureImportanceItem[]> => {
    const response = await fetch(`${API_BASE_URL}/api/classification/feature-importance/${equipmentType}?top_n=${topN}`);
    if (!response.ok) throw new Error('Failed to get feature importance');
    return response.json();
  },

  /**
   * Get model info for equipment type
   * @param equipmentType - Equipment type
   */
  getModelInfo: async (equipmentType: string): Promise<ClassificationModelInfo> => {
    const response = await fetch(`${API_BASE_URL}/api/classification/models/${equipmentType}`);
    if (!response.ok) throw new Error('Failed to get model info');
    return response.json();
  },

  /**
   * List all available classification models
   */
  listModels: async (): Promise<ClassificationModelInfo[]> => {
    const response = await fetch(`${API_BASE_URL}/api/classification/models`);
    if (!response.ok) throw new Error('Failed to list models');
    return response.json();
  },

  /**
   * Check classification service health
   */
  healthCheck: async (): Promise<{ status: string; n_models: number; equipment_types: string[] }> => {
    const response = await fetch(`${API_BASE_URL}/api/classification/health`);
    if (!response.ok) throw new Error('Health check failed');
    return response.json();
  },
};

// ============= Inspection API Interfaces (Phase 55) =============

// Inspection schedule for mobile display
export interface InspectionScheduleItem {
  id: string;
  equipment_id: string;
  schedule_name: string;
  frequency_type: 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'annual' | 'custom';
  frequency_interval: number | null;
  inspection_type: string;
  checklist_template_id: string | null;
  priority: string;
  duration_minutes: number;
  next_due_date: string | null;  // ISO date string
  is_active: boolean;
}

// Inspection task record
export interface InspectionTaskItem {
  id: string;
  task_name: string;
  equipment_id: string;
  status: 'scheduled' | 'in_progress' | 'completed' | 'overdue' | 'cancelled';
  priority: string;
  due_date: string;
  completed_date?: string;
  estimated_duration_minutes: number;
  actual_duration_minutes?: number;
  checklist_data?: any;  // Template and responses
  deficiencies_found?: number;
  completion_notes?: string;
  created_at: string;
}

// Checklist template structure
export interface ChecklistTemplateItem {
  template_id: string;
  equipment_type: string;
  template_name: string;
  inspection_type: string;
  estimated_duration_minutes: number;
  checklist_items: ChecklistItemDef[];
}

// Checklist item definition
export interface ChecklistItemDef {
  category: string;
  item_id: string;
  question: string;
  item_type: 'checklist' | 'measurement' | 'visual_inspection';
  options?: Array<{ label: string; value: string }>;
  parameter_name?: string;
  unit?: string;
  tolerance_min?: number;
  tolerance_max?: number;
  required: boolean;
  photos_required: boolean;
}

// Photo attachment for inspection
export interface InspectionPhotoAttachment {
  file_url: string;
  file_name: string;
  description?: string;
  element_id?: string;
}

// Inspection submission request
export interface InspectionSubmissionRequest {
  equipment_id: string;
  template_id: string;
  checklist_responses: Record<string, any>;
  photos: InspectionPhotoAttachment[];
  duration_minutes: number;
  notes?: string;
  submitted_by?: string;
}

// Inspection history response with trending
export interface InspectionHistoryResponse {
  equipment_id: string;
  tasks: InspectionTaskItem[];
  trending?: {
    ok_count: number;
    warning_count: number;
    critical_count: number;
  };
}

// Inspection API methods
export const inspectionApi = {
  /**
   * Submit weekly inspection results
   * @param submission - Inspection submission data
   */
  submitInspection: async (submission: InspectionSubmissionRequest): Promise<InspectionTaskItem> => {
    const response = await fetch(`${API_BASE_URL}/api/inspection/submit-weekly`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(submission)
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to submit inspection' }));
      throw new Error(error.detail || 'Failed to submit inspection');
    }
    return response.json();
  },

  /**
   * Get inspection schedule
   * @param params - Optional filters
   */
  getSchedule: async (params?: { equipment_id?: string; daysAhead?: number }): Promise<InspectionScheduleItem[]> => {
    const url = new URL(`${API_BASE_URL}/api/inspection/schedule`);
    if (params?.equipment_id) url.searchParams.set('equipment_id', params.equipment_id);
    if (params?.daysAhead) url.searchParams.set('days_ahead', params.daysAhead.toString());

    const response = await fetch(url.toString());
    if (!response.ok) throw new Error('Failed to get inspection schedule');
    return response.json();
  },

  /**
   * Get inspection history for equipment
   * @param equipmentId - Equipment ID
   * @param months - Months of history (default: 12)
   */
  getHistory: async (equipmentId: string, months: number = 12): Promise<InspectionTaskItem[]> => {
    const response = await fetch(`${API_BASE_URL}/api/inspection/history/${equipmentId}?months=${months}`);
    if (!response.ok) throw new Error('Failed to get inspection history');
    return response.json();
  },

  /**
   * Get checklist template for equipment type
   * Loads embedded template data (can be extended to fetch from backend)
   * @param equipmentType - Equipment type (chiller, ahu, etc.)
   * @param inspectionType - Inspection type (default: routine)
   */
  getChecklistTemplate: async (equipmentType: string, inspectionType: string = 'routine'): Promise<ChecklistTemplateItem> => {
    // Embedded templates for offline/fast access
    // In production, could fetch from backend: /api/inspection/templates/{type}
    const templates: Record<string, ChecklistTemplateItem> = {
      'chiller_weekly': {
        template_id: 'chiller_weekly',
        equipment_type: 'chiller',
        template_name: 'Weekly Chiller Inspection',
        inspection_type: 'routine',
        estimated_duration_minutes: 30,
        checklist_items: [
          {
            category: 'Compressor',
            item_id: 'compressor_condition',
            question: 'Compressor operating condition',
            item_type: 'checklist',
            options: [
              { label: 'Normal', value: 'ok' },
              { label: 'Abnormal noise/vibration', value: 'warning' },
              { label: 'Not operating', value: 'critical' }
            ],
            required: true,
            photos_required: false
          },
          {
            category: 'Refrigerant',
            item_id: 'refrigerant_pressure',
            question: 'Refrigerant pressure (bar)',
            item_type: 'measurement',
            parameter_name: 'refrigerant_pressure',
            unit: 'bar',
            tolerance_min: 8,
            tolerance_max: 15,
            required: true,
            photos_required: false
          },
          {
            category: 'Oil System',
            item_id: 'oil_level',
            question: 'Oil level condition',
            item_type: 'checklist',
            options: [
              { label: 'Normal', value: 'ok' },
              { label: 'Low', value: 'warning' },
              { label: 'Critical', value: 'critical' }
            ],
            required: true,
            photos_required: false
          }
        ]
      },
      'ahu_weekly': {
        template_id: 'ahu_weekly',
        equipment_type: 'ahu',
        template_name: 'Weekly AHU Inspection',
        inspection_type: 'routine',
        estimated_duration_minutes: 25,
        checklist_items: [
          {
            category: 'Filters',
            item_id: 'filter_condition',
            question: 'Filter condition',
            item_type: 'checklist',
            options: [
              { label: 'Clean', value: 'ok' },
              { label: 'Moderately dirty', value: 'warning' },
              { label: 'Blocked/Replace required', value: 'critical' }
            ],
            required: true,
            photos_required: true
          },
          {
            category: 'Fan',
            item_id: 'fan_vibration',
            question: 'Fan vibration (mm/s)',
            item_type: 'measurement',
            parameter_name: 'fan_vibration',
            unit: 'mm/s',
            tolerance_min: 0,
            tolerance_max: 4.5,
            required: true,
            photos_required: false
          }
        ]
      },
      'generator_weekly': {
        template_id: 'generator_weekly',
        equipment_type: 'generator',
        template_name: 'Weekly Generator Inspection',
        inspection_type: 'routine',
        estimated_duration_minutes: 35,
        checklist_items: [
          {
            category: 'Engine',
            item_id: 'engine_oil_level',
            question: 'Engine oil level',
            item_type: 'checklist',
            options: [
              { label: 'Full', value: 'ok' },
              { label: 'Low - top up required', value: 'warning' },
              { label: 'Critical - do not start', value: 'critical' }
            ],
            required: true,
            photos_required: false
          },
          {
            category: 'Fuel',
            item_id: 'fuel_level_percent',
            question: 'Fuel tank level (%)',
            item_type: 'measurement',
            parameter_name: 'fuel_level_percent',
            unit: '%',
            tolerance_min: 25,
            tolerance_max: 100,
            required: true,
            photos_required: false
          }
        ]
      }
    };

    const key = `${equipmentType}_weekly`;
    const template = templates[key];

    if (!template) {
      // Return a generic template if specific one not found
      return {
        template_id: `${equipmentType}_generic`,
        equipment_type: equipmentType,
        template_name: `${equipmentType.charAt(0).toUpperCase() + equipmentType.slice(1)} Inspection`,
        inspection_type: inspectionType,
        estimated_duration_minutes: 20,
        checklist_items: [
          {
            category: 'General',
            item_id: 'general_condition',
            question: 'Overall equipment condition',
            item_type: 'checklist',
            options: [
              { label: 'Good', value: 'ok' },
              { label: 'Fair - monitor', value: 'warning' },
              { label: 'Poor - attention needed', value: 'critical' }
            ],
            required: true,
            photos_required: false
          }
        ]
      };
    }

    return template;
  },

  /**
   * Get inspection overview for equipment
   * @param equipmentId - Equipment ID
   */
  getOverview: async (equipmentId: string): Promise<{
    equipment_id: string;
    active_schedules: number;
    scheduled_tasks: number;
    in_progress_tasks: number;
    overdue_tasks: number;
    completed_last_30_days: number;
    open_deficiencies: number;
    critical_deficiencies: number;
  }> => {
    const response = await fetch(`${API_BASE_URL}/api/inspection/summary/equipment/${equipmentId}`);
    if (!response.ok) throw new Error('Failed to get inspection overview');
    return response.json();
  },

  /**
   * Get inspection statistics
   * @param equipmentId - Optional equipment ID filter
   */
  getStatistics: async (equipmentId?: string): Promise<{
    total_schedules: number;
    active_schedules: number;
    total_tasks_generated: number;
    tasks_by_status: Record<string, number>;
    overdue_tasks: number;
    completed_last_30_days: number;
  }> => {
    const url = equipmentId
      ? `${API_BASE_URL}/api/inspection/statistics?equipment_id=${equipmentId}`
      : `${API_BASE_URL}/api/inspection/statistics`;
    const response = await fetch(url);
    if (!response.ok) throw new Error('Failed to get inspection statistics');
    return response.json();
  }
};

/**
 * Create a work order for equipment
 */
export interface CreateWorkOrderParams {
  site_id: string;
  equipment_id: string;
  fault_description: string;
  diagnosis?: string;
  priority?: "low" | "medium" | "high" | "critical";
}

export interface WorkOrderResponse {
  id: string;
  site_id: string;
  equipment_id: string;
  fault_description: string;
  diagnosis: string;
  priority: string;
  status: string;
  created_at: string;
}

export async function createWorkOrder(params: CreateWorkOrderParams): Promise<WorkOrderResponse> {
  const response = await authorizedFetch(`/api/work-orders/technician`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      site_id: params.site_id,
      equipment_id: params.equipment_id,
      fault_description: params.fault_description,
      diagnosis: params.diagnosis || `Equipment health below threshold - maintenance required`,
      priority: params.priority || "medium",
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to create work order: ${response.status}`);
  }

  return response.json();
}

// ============= Niagara Connection Interfaces (Phase 65) =============

export interface NiagaraOBIXConfig {
  host: string;
  port: number;
  username: string;
  password: string;
  use_https: boolean;
  timeout: number;
}

export interface NiagaraConfigResponse {
  success: boolean;
  message: string;
  connected: boolean;
}

export interface NiagaraConnectionStatus {
  connected: boolean;
  last_auth: string | null;
  server_version: string | null;
  base_url: string;
  message: string;
}

export interface BACnetDevice {
  device_id: number;
  ip_address: string;
  vendor_name: string;
  model_name: string;
  firmware_version: string;
  object_name: string;
}

// BMS vendor type
export type BMSVendor = 'niagara' | 'desigo' | 'metasys' | 'honeywell' | 'schneider' | 'trend' | 'generic';

// BACnet test connection request
export interface BACnetTestConnectionRequest {
  timeout?: number;
}

// BACnet test connection response (reuses BACnet device types)
export interface BACnetTestConnectionResponse {
  count: number;
  devices: BACnetDevice[];
}

export interface DiscoverClassifyRequest {
  device_ip: string;
  site_id: string;
  device_bacnet_id?: number;
  bms_vendor?: BMSVendor;
}

export interface DiscoverClassifyResponse {
  discovery_id: string;
  points_count: number;
  equipment_count: number;
  status: string;
  summary: Record<string, string | number | boolean>;
}

export interface NiagaraMappingSummary {
  discovery_id: string;
  status: string;
  equipment: Array<{
    equipment_id: string;
    equipment_type: string;
    equipment_name: string;
    points: Array<{
      name?: string;
      original_name?: string;  // Backend uses this field
      point_type: string;
      confidence: string;
      brick_class?: string;
      unit?: string;
      point_category?: string;
    }>;
    confidence: string;
    point_count?: number;
  }>;
  validation: Record<string, unknown>;
  total_points: number;
  equipment_count: number;
  confidence_breakdown: Record<string, number>;
  needs_review: number;
}

export interface NiagaraApproveResponse {
  success: boolean;
  equipment_created: number;
  message: string;
}

export interface NiagaraCorrectRequest {
  point_id: string;
  equipment_id?: string;
  point_type?: string;
  equipment_type?: string;
}

export const niagaraApi = {
  configureOBIX: (config: NiagaraOBIXConfig) =>
    fetchApi<NiagaraConfigResponse>('/api/niagara/obix/config', {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  getOBIXStatus: () =>
    fetchApi<NiagaraConnectionStatus>('/api/niagara/obix/status'),

  testBACnetConnection: (req?: BACnetTestConnectionRequest) =>
    fetchApi<BACnetTestConnectionResponse>('/api/niagara/bacnet/test-connection', {
      method: 'POST',
      body: JSON.stringify(req || {}),
    }),

  discoverAndClassify: (req: DiscoverClassifyRequest) =>
    fetchApi<DiscoverClassifyResponse>('/api/niagara/discover-and-classify', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  getMappings: (discoveryId: string) =>
    fetchApi<NiagaraMappingSummary>(`/api/niagara/mappings/${discoveryId}`),

  approveMappings: (discoveryId: string, approvedBy: string) =>
    fetchApi<NiagaraApproveResponse>(
      `/api/niagara/mappings/${discoveryId}/approve?approved_by=${encodeURIComponent(approvedBy)}`,
      { method: 'POST' },
    ),

  correctPoint: (discoveryId: string, correction: NiagaraCorrectRequest) =>
    fetchApi<{ success: boolean; corrections: string[]; message: string }>(
      `/api/niagara/mappings/${discoveryId}/correct`,
      { method: 'POST', body: JSON.stringify(correction) },
    ),
};

/** Backward-compatible alias for niagaraApi */
export const bmsApi = niagaraApi;

// ============= Sites API Interfaces (Onboarding Wizard) =============

export interface CreateSiteRequest {
  name: string;
  address?: string;
  region?: string;
  type?: string;
  floors?: string[];
  sqm?: number;
}

export interface CreateSiteResponse {
  id: string;
  name: string;
  status: string;
}

export interface NextSiteIdResponse {
  next_id: string;
}

// NOTE: sitesApi removed (conflicting with modular sites.ts version)
// Use modular import: import { sitesApi } from '@/lib/api/sites'
// Modular version has: getSites(), getSite(), getSites(), getEquipment(), getDesks(), etc.

// ============= Security Module Interfaces (Phase 58) =============

export interface SecuritySystemStatus {
  total_doors: number;
  doors_secure: number;
  cameras_online: number;
  cameras_total: number;
  alarm_zones_armed: number;
  alarm_zones_total: number;
  active_alerts: number;
  occupancy_total: number;
}

export interface AccessZone {
  zone_id: string;
  name: string;
  floor: string;
  access_level: "public" | "restricted" | "secure" | "critical";
  doors: string[];
}

export interface Door {
  door_id: string;
  name: string;
  zone_id: string;
  status: "open" | "closed" | "locked" | "fault";
  reader_type: "card" | "biometric" | "pin";
  last_event_time: string | null;
}

export interface BadgeEvent {
  event_id: string;
  door_id: string;
  zone_id: string;
  badge_id: string;
  person_name: string;
  direction: "entry" | "exit";
  timestamp: string;
  granted: boolean;
  reason: string;
}

export interface SecurityCamera {
  camera_id: string;
  name: string;
  zone_id: string;
  floor: string;
  status: "online" | "offline" | "fault";
  type: "fixed" | "ptz" | "dome";
  resolution: string;
  has_analytics: boolean;
  motion_detected: boolean;
}

export interface SecurityAlarmZone {
  zone_id: string;
  name: string;
  status: "armed" | "disarmed" | "triggered" | "fault";
  arm_type: "full" | "perimeter" | "night";
}

export interface SecurityOccupancy {
  zone_id: string;
  zone_name: string;
  occupancy_count: number;
  badge_entries: number;
  badge_exits: number;
  last_updated: string | null;
  source: "badge" | "camera" | "combined";
}

export interface OccupancyRecommendation {
  zone_id: string;
  zone_name: string;
  current_occupancy: number;
  recommendation_type: "hvac" | "lighting";
  action: string;
  detail: string;
}

// ============= Security API Client =============

export const securityApi = {
  /** Get overall security system status */
  getStatus: async (site: string) => {
    try {
      const response = await fetchApi<{
        metrics?: {
          active_visitors?: number;
          open_alerts?: number;
        };
      }>(`/api/security/status?site=${encodeURIComponent(site)}`);
      return {
        total_doors: 0,
        doors_secure: 0,
        cameras_online: 0,
        cameras_total: 0,
        alarm_zones_armed: 0,
        alarm_zones_total: 0,
        active_alerts: response.metrics?.open_alerts ?? 0,
        occupancy_total: response.metrics?.active_visitors ?? 0,
      };
    } catch (_error) {
      return {
        total_doors: 0,
        doors_secure: 0,
        cameras_online: 0,
        cameras_total: 0,
        alarm_zones_armed: 0,
        alarm_zones_total: 0,
        active_alerts: 0,
        occupancy_total: 0,
      };
    }
  },

  /** Get all access zones with doors */
  getZones: () =>
    fetchApi<{ zones: AccessZone[]; count: number }>("/api/security/zones"),

  /** Get all door status */
  getDoors: () =>
    fetchApi<{ doors: Door[]; count: number; secure: number }>("/api/security/doors"),

  /** Get badge events with optional filtering */
  getEvents: async (params?: { site?: string; zone_id?: string; limit?: number; after_hours?: boolean }) => {
    const searchParams = new URLSearchParams();
    searchParams.set("site", params?.site || "");
    if (params?.zone_id) searchParams.set("location", params.zone_id);
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.after_hours) searchParams.set("after_hours", "true");
    const qs = searchParams.toString();
    try {
      const response = await fetchApi<{ events: any[]; event_count: number }>(
        `/api/security/events${qs ? `?${qs}` : ""}`
      );
      const mapped: BadgeEvent[] = (response.events || []).map((event: any) => ({
        event_id: event.event_id,
        door_id: event.access_point_id || "unknown",
        zone_id: event.location || "unknown",
        badge_id: event.card_id || "unknown",
        person_name: event.person_name || "Unknown",
        direction: "entry",
        timestamp: event.timestamp,
        granted: event.status === "granted",
        reason: event.status || "unknown",
      }));
      return { events: mapped, count: response.event_count ?? mapped.length };
    } catch (_error) {
      return { events: [], count: 0 };
    }
  },

  /** Get denied access events */
  getDeniedEvents: async (site: string) => {
    try {
      const result = await securityApi.getEvents({ site, limit: 200 });
      const denied = result.events.filter((event) => !event.granted);
      return { events: denied, count: denied.length };
    } catch (_error) {
      return { events: [], count: 0 };
    }
  },

  /** Get after-hours access events */
  getAfterHoursEvents: async (site: string) => {
    try {
      return await securityApi.getEvents({ site, limit: 200, after_hours: true });
    } catch (_error) {
      return { events: [], count: 0 };
    }
  },

  /** Get all cameras with status */
  getCameras: async (_site: string) => {
    try {
      return { cameras: [], count: 0, online: 0 };
    } catch (_error) {
      return { cameras: [], count: 0, online: 0 };
    }
  },

  /** Get all alarm zones */
  getAlarmZones: async (_site: string) => {
    try {
      return { alarm_zones: [], count: 0, armed: 0 };
    } catch (_error) {
      return { alarm_zones: [], count: 0, armed: 0 };
    }
  },

  /** Arm an alarm zone */
  armAlarmZone: (zoneId: string, armType: "full" | "perimeter" | "night" = "full") =>
    fetchApi<{ success: boolean; zone_id: string; status: string; arm_type: string }>(
      `/api/security/alarm-zones/${zoneId}/arm`,
      { method: "POST", body: JSON.stringify({ arm_type: armType }) }
    ),

  /** Disarm an alarm zone */
  disarmAlarmZone: (zoneId: string) =>
    fetchApi<{ success: boolean; zone_id: string; status: string }>(
      `/api/security/alarm-zones/${zoneId}/disarm`,
      { method: "POST" }
    ),

  /** Get building-wide occupancy */
  getOccupancy: async (site: string) => {
    try {
      const response = await fetchApi<{
        total_occupancy: number;
        by_floor?: Record<string, number>;
        by_zone?: Record<string, number>;
        last_updated?: string | null;
      }>(`/api/security/occupancy?site=${encodeURIComponent(site)}`);

      const byZone = response.by_zone || {};
      const zones: SecurityOccupancy[] = Object.entries(byZone).map(([zoneName, count]) => ({
        zone_id: zoneName,
        zone_name: zoneName,
        occupancy_count: Number(count || 0),
        badge_entries: Number(count || 0),
        badge_exits: 0,
        last_updated: response.last_updated || null,
        source: "badge",
      }));

      // Fallback if backend has floor-only data
      if (zones.length === 0) {
        const byFloor = response.by_floor || {};
        for (const [floorName, count] of Object.entries(byFloor)) {
          zones.push({
            zone_id: floorName,
            zone_name: floorName,
            occupancy_count: Number(count || 0),
            badge_entries: Number(count || 0),
            badge_exits: 0,
            last_updated: response.last_updated || null,
            source: "badge",
          });
        }
      }

      return {
        total_occupancy: response.total_occupancy || 0,
        zones,
      };
    } catch (_error) {
      return { total_occupancy: 0, zones: [] };
    }
  },

  /** Get zone-specific occupancy */
  getZoneOccupancy: (zoneId: string) =>
    fetchApi<SecurityOccupancy>(`/api/security/occupancy/${zoneId}`),

  /** Get cross-module occupancy recommendations */
  getOccupancyRecommendations: async (site: string) => {
    try {
      const response = await fetchApi<{
        recommendations: Array<Record<string, any>>;
        recommendation_count?: number;
        current_occupancy?: number;
        by_zone?: Record<string, number>;
      }>(`/api/security/occupancy/recommendations?site=${encodeURIComponent(site)}`);

      const byZone = response.by_zone || {};
      const mapped: OccupancyRecommendation[] = (response.recommendations || []).map((rec, idx) => {
        const zoneName = rec.zone || "Building-wide";
        return {
          zone_id: zoneName.toLowerCase().replace(/\s+/g, "-") || `zone-${idx + 1}`,
          zone_name: zoneName,
          current_occupancy: Number(byZone[zoneName] ?? response.current_occupancy ?? 0),
          recommendation_type: rec.module === "lighting" ? "lighting" : "hvac",
          action: rec.action || rec.type || "review",
          detail: rec.description || rec.estimated_savings || "",
        };
      });

      return { recommendations: mapped, count: response.recommendation_count ?? mapped.length };
    } catch (_error) {
      return { recommendations: [], count: 0 };
    }
  },

  /** Get detected security anomalies (24h default) */
  getAnomalies: async (site: string, daysBack = 1) => {
    try {
      return await fetchApi<{ anomalies: any[]; anomaly_count: number }>(
        `/api/security/events/anomalies?site=${encodeURIComponent(site)}&days_back=${daysBack}`
      );
    } catch (_error) {
      return { anomalies: [], anomaly_count: 0 };
    }
  },
};

// ============= Workflow API =============

export interface WorkflowEquipmentItem {
  equipment_id: string;
  name: string;
  type: string;
  current_state: string;
}

export interface WorkflowStateTransition {
  from: string;
  to: string;
  timestamp: string;
  trigger: string;
}

export interface WorkflowBaselineSummary {
  total_baselines: number;
  latest_baseline: string | null;
  deviation_detected: boolean;
}

export interface WorkflowInspectionStatus {
  last_inspection: string | null;
  status: string;
  findings: string;
}

export interface WorkflowMLPrediction {
  failure_probability: number;
  timeframe: string;
  confidence: string;
  explanation: string;
}

export interface WorkflowWorkOrder {
  id: string;
  title: string;
  priority: string;
  status: string;
}

export interface WorkflowState {
  equipment_id: string;
  current_state: string;
  state_history: WorkflowStateTransition[];
  baseline_summary: WorkflowBaselineSummary;
  inspection_status: WorkflowInspectionStatus;
  ml_prediction: WorkflowMLPrediction | null;
  active_repairs: WorkflowWorkOrder[];
}

export interface WorkflowDashboardResponse {
  equipment: WorkflowEquipmentItem[];
  workflow_states: Record<string, WorkflowState>;
}

export const workflowApi = {
  /** Get workflow dashboard data for all equipment */
  getDashboardEquipment: (siteId?: string) => {
    const params = new URLSearchParams();
    if (siteId) params.set("site_id", siteId);
    const qs = params.toString();
    return fetchApi<WorkflowDashboardResponse>(
      `/api/workflow/dashboard/equipment${qs ? `?${qs}` : ""}`
    );
  },

  /** Get workflow status for specific equipment */
  getWorkflowStatus: (equipmentId: string) =>
    fetchApi<WorkflowState>(`/api/workflow/status/${equipmentId}`),

  /** Get trigger history */
  getTriggerHistory: (equipmentId?: string) => {
    const params = new URLSearchParams();
    if (equipmentId) params.set("equipment_id", equipmentId);
    const qs = params.toString();
    return fetchApi<{ count: number; triggers: any[] }>(
      `/api/workflow/triggers/history${qs ? `?${qs}` : ""}`
    );
  },

  /** Get pending inspections for equipment */
  getPendingInspections: (equipmentId: string) =>
    fetchApi<{ equipment_id: string; count: number; inspections: any[] }>(
      `/api/workflow/triggers/inspections/${equipmentId}`
    ),

  /** Get pending work orders for equipment */
  getPendingWorkOrders: (equipmentId: string) =>
    fetchApi<{ equipment_id: string; count: number; work_orders: any[] }>(
      `/api/workflow/triggers/work-orders/${equipmentId}`
    ),
};

// ============= Service Feedback API =============

export interface FeedbackSessionStart {
  session_id: string;
  equipment_code: string;
  equipment_type: string;
  service_type: string;
  required_items: string[];
  optional_items: string[];
  first_prompt: {
    key: string;
    prompt: string;
    required: boolean;
  } | null;
}

export interface FeedbackSessionStatus {
  session_id: string;
  status: string;
  equipment_code: string;
  equipment_type: string;
  service_type: string;
  progress: {
    required_collected: number;
    required_total: number;
    optional_collected: number;
    optional_total: number;
    percent_complete: number;
  };
  items_collected: string[];
  next_item: {
    key: string;
    prompt: string;
    required: boolean;
  } | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface FeedbackItemResult {
  item_key: string;
  item_type: string;
  value: any;
  unit: string | null;
  baseline_value: number | null;
  deviation_percent: number | null;
  health_impact: "positive" | "neutral" | "negative" | "critical";
  notes: string | null;
}

export interface FeedbackCompletionResult {
  success: boolean;
  session_id: string;
  equipment_code: string;
  health_score_change: number;
  items_collected: number;
  feedback_summary: {
    readings: any[];
    attachments: any[];
    observations: any[];
    impact_counts: {
      positive: number;
      neutral: number;
      negative: number;
      critical: number;
    };
  };
  warnings: string[];
  completed_at: string | null;
  error?: string;
  message?: string;
}

export interface FeedbackTemplate {
  equipment_type: string;
  service_type: string;
  required_items: string[];
  optional_items: string[];
  prompts: Record<string, string>;
  validation_rules: Record<string, any>;
}

export const serviceFeedbackApi = {
  /** Start a feedback collection session for a work order */
  startSession: (workOrderId: string, equipmentCode: string, serviceType: string = "minor") =>
    fetchApi<FeedbackSessionStart>("/api/service-feedback/start", {
      method: "POST",
      body: JSON.stringify({
        work_order_id: workOrderId,
        equipment_code: equipmentCode,
        service_type: serviceType,
      }),
    }),

  /** Get session status */
  getSessionStatus: (sessionId: string) =>
    fetchApi<FeedbackSessionStatus>(`/api/service-feedback/session/${sessionId}`),

  /** Submit a reading/measurement */
  submitReading: (sessionId: string, itemKey: string, value: any, unit?: string, notes?: string) =>
    fetchApi<FeedbackItemResult>(`/api/service-feedback/session/${sessionId}/reading`, {
      method: "POST",
      body: JSON.stringify({ item_key: itemKey, value, unit, notes }),
    }),

  /** Submit an observation/note */
  submitObservation: (sessionId: string, content: string, itemKey: string = "observation", notes?: string) =>
    fetchApi<FeedbackItemResult>(`/api/service-feedback/session/${sessionId}/observation`, {
      method: "POST",
      body: JSON.stringify({ item_key: itemKey, content, notes }),
    }),

  /** Complete the feedback session */
  completeSession: (sessionId: string, force: boolean = false) =>
    fetchApi<FeedbackCompletionResult>(
      `/api/service-feedback/session/${sessionId}/complete?force=${force}`,
      { method: "POST" }
    ),

  /** Get feedback template for equipment type */
  getTemplate: (equipmentType: string, serviceType: string = "minor") =>
    fetchApi<FeedbackTemplate>(`/api/service-feedback/template/${equipmentType}?service_type=${serviceType}`),

  /** List all available templates */
  listTemplates: () =>
    fetchApi<{
      equipment_types: string[];
      count: number;
      templates: Record<string, any>;
    }>("/api/service-feedback/templates"),

  /** Get health impact rules */
  getHealthImpactRules: () =>
    fetchApi<{
      description: string;
      impact_levels: Record<string, any>;
      score_bounds: { min_change: number; max_change: number };
      health_status_thresholds: Record<string, string>;
    }>("/api/service-feedback/health-impact-rules"),
};

// ============= Authentication API =============

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "operator" | "developer" | "auditor";
}

export interface LoginResponse {
  access_token?: string;
  refresh_token?: string;
  token?: string; // legacy fallback
  user: AuthUser;
  expires_at: string;
  mfa_required?: boolean;
  mfa_enrolled?: boolean;
  mfa_challenge_pending?: boolean;
  session_id?: string;
}

export interface VerifyResponse {
  valid: boolean;
  user?: AuthUser;
}

export const authApi = {
  /** Login with email address */
  login: (email: string) =>
    fetchApi<LoginResponse>(`/api/auth/login?email=${encodeURIComponent(email)}`, {
      method: "POST",
    }),

  /** Verify a JWT token */
  verify: (token: string) =>
    fetchApi<VerifyResponse>(`/api/auth/verify?token=${encodeURIComponent(token)}`, {
      method: "POST",
    }),

  /** Get current user info */
  me: () =>
    fetchApi<AuthUser>("/api/auth/me", {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("sentinel_token") || ""}`,
      },
    }),

  /** Logout */
  logout: () => {
    const refreshToken = getRefreshToken();
    // SECURITY: Send refresh token in request body, NOT in URL (Phase 75-07)
    const body = refreshToken ? JSON.stringify({ refresh_token: refreshToken }) : undefined;
    return fetchApi<{ message: string }>("/api/auth/logout", {
      method: "POST",
      body,
      headers: body ? { "Content-Type": "application/json" } : {}
    });
  },
};

// Export API object with logout method for use in components
const apiWithAuth = {
  ...api,
  logout: async () => {
    const response = await authApi.logout();
    clearAuthStorage();
    return response;
  },
};

export default apiWithAuth;

// Re-export modular APIs for backward compatibility
export { systemApi, useSystemHealth, useDiagnostics } from './api/system';

// ==================== Fuel Monitoring API ====================

export interface FuelTank {
  tank_id: string;
  site_id: string;
  name: string;
  capacity_litres: number;
  fuel_type: string;
  generator_id: string | null;
  low_fuel_pct_1: number;
  low_fuel_pct_2: number;
  latest_telemetry: FuelTelemetry | null;
}

export interface FuelTelemetry {
  tank_id: string;
  level_pct: number;
  level_litres: number;
  temperature_c: number | null;
  consumption_rate_lph: number | null;
  days_to_empty: number | null;
  received_at: string;
}

export interface FuelEvent {
  event_id: string;
  event_type: string;
  tank_id: string;
  site_id: string;
  ts: number;
  severity: string;
  details: Record<string, unknown>;
}

export interface FuelTelemetryReading {
  tank_id: string;
  ts: number;
  level_pct: number;
  level_litres: number;
  temperature_c: number | null;
  consumption_rate_lph: number | null;
}

export interface GeneratorRuntimeSession {
  event_id: string;
  event_type: string;
  tank_id: string;
  site_id: string;
  ts: number;
  details: Record<string, unknown>;
}

export interface RefillRecord {
  event_id: string;
  event_type: string;
  tank_id: string;
  site_id: string;
  ts: number;
  details: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Space Optimization Settings
// ---------------------------------------------------------------------------

export interface SpaceGracePeriods {
  ghost_booking_grace_minutes: number;
  concierge_response_window_minutes: number;
  sensor_silence_threshold_minutes: number;
  right_sizing_grace_minutes: number;
  early_vacate_threshold_minutes: number;
  sporadic_use_threshold_pct: number;
  brief_occupation_threshold_min: number;
}

export interface ConciergeUser {
  id: string;
  name: string;
  mobile: string;
  email: string;
  site_id: string;
  building_codes: string[];
  floor_assignments: Record<string, number[]>;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SpaceSettings extends SpaceGracePeriods {
  concierges: ConciergeUser[];
}

export interface ConciergeUserCreate {
  name: string;
  mobile: string;
  email: string;
  site_id: string;
  building_codes: string[];
  floor_assignments: Record<string, number[]>;
}

export type ConciergeUserUpdate = Partial<ConciergeUserCreate> & { active?: boolean };

export interface SpaceSiteStructure {
  site_id: string;
  site_name: string;
  buildings: Array<{
    code: string;
    name: string;
    floors: number[];
  }>;
}

export const spaceSettingsApi = {
  /** Get all space optimization settings including concierge list */
  async getSettings(): Promise<SpaceSettings> {
    return fetchApi<SpaceSettings>('/api/settings/space');
  },

  /** Update grace period settings */
  async updateSettings(settings: Partial<SpaceGracePeriods>): Promise<SpaceSettings> {
    return fetchApi<SpaceSettings>('/api/settings/space', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
  },

  /** Get site/building/floor structure for concierge assignment */
  async getSites(): Promise<SpaceSiteStructure[]> {
    return fetchApi<SpaceSiteStructure[]>('/api/settings/space/sites');
  },

  /** List concierge users, optionally filtered by site */
  async listConcierges(siteId?: string): Promise<ConciergeUser[]> {
    const params = siteId ? `?site_id=${encodeURIComponent(siteId)}` : '';
    return fetchApi<ConciergeUser[]>(`/api/settings/space/concierges${params}`);
  },

  /** Create a new concierge user */
  async createConcierge(data: ConciergeUserCreate): Promise<ConciergeUser> {
    return fetchApi<ConciergeUser>('/api/settings/space/concierges', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  /** Update an existing concierge user */
  async updateConcierge(id: string, data: ConciergeUserUpdate): Promise<ConciergeUser> {
    return fetchApi<ConciergeUser>(`/api/settings/space/concierges/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  /** Delete a concierge user */
  async deleteConcierge(id: string): Promise<void> {
    await fetchApi<{ status: string; id: string }>(`/api/settings/space/concierges/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
  },
};

export const fuelApi = {
  /** List fuel tanks with latest telemetry */
  async fetchTanks(siteId?: string): Promise<{ tanks: FuelTank[]; count: number }> {
    const params = siteId ? `?site_id=${encodeURIComponent(siteId)}` : '';
    const response = await authorizedFetch(`/api/fuel/tanks${params}`);
    if (!response.ok) throw new Error('Failed to fetch fuel tanks');
    return response.json();
  },

  /** Get telemetry history for a tank */
  async fetchTankHistory(tankId: string, hours = 24): Promise<{ tank_id: string; hours: number; readings: FuelTelemetryReading[]; count: number }> {
    const response = await authorizedFetch(`/api/fuel/tanks/${encodeURIComponent(tankId)}/history?hours=${hours}`);
    if (!response.ok) throw new Error('Failed to fetch tank history');
    return response.json();
  },

  /** List fuel events */
  async fetchEvents(siteId?: string, limit = 50): Promise<{ events: FuelEvent[]; count: number }> {
    const params = new URLSearchParams();
    if (siteId) params.set('site_id', siteId);
    if (limit) params.set('limit', String(limit));
    const response = await authorizedFetch(`/api/fuel/events?${params}`);
    if (!response.ok) throw new Error('Failed to fetch fuel events');
    return response.json();
  },

  /** Get generator runtime sessions */
  async fetchGeneratorRuntime(siteId?: string, limit = 50): Promise<{ sessions: GeneratorRuntimeSession[]; count: number }> {
    const params = new URLSearchParams();
    if (siteId) params.set('site_id', siteId);
    if (limit) params.set('limit', String(limit));
    const response = await authorizedFetch(`/api/fuel/generator-runtime?${params}`);
    if (!response.ok) throw new Error('Failed to fetch generator runtime');
    return response.json();
  },

  /** Get refill log */
  async fetchRefillLog(siteId?: string, limit = 50): Promise<{ refills: RefillRecord[]; count: number }> {
    const params = new URLSearchParams();
    if (siteId) params.set('site_id', siteId);
    if (limit) params.set('limit', String(limit));
    const response = await authorizedFetch(`/api/fuel/refill-log?${params}`);
    if (!response.ok) throw new Error('Failed to fetch refill log');
    return response.json();
  },
};

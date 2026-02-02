/**
 * API Client for BMS Intelligence Backend
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

// ============= Response Interfaces =============

export interface HealthResponse {
  status: string;
  version: string;
}

interface ApiError {
  message: string;
  status: number;
}

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
  building_id: string;
  building_name: string;
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
  building_id: string;
  building_name: string;
  site_id: string;
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
export interface BuildingEquipmentResponse {
  building_id: string;
  building_name: string;
  total_equipment: number;
  categories: Record<string, CategoryStatus>;
  equipment: BuildingEquipmentItem[];
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
  building_id?: string;
  building_name?: string;
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
}

// Site-specific schedule response interface
export interface SiteScheduleResponse {
  site_id: string;
  site_name: string;
  current_stage: number;
  schedules: LoadSheddingStage[];
  next_outage: LoadSheddingStage | null;
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
  severity: "critical" | "high" | "medium" | "low";
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
  const url = `${API_BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

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
 */
export async function streamChat(
  message: string,
  conversationId: string | undefined,
  onChunk: (chunk: string) => void
): Promise<void> {
  const url = `${API_BASE_URL}/api/chat`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
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

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // Decode the chunk
      const text = decoder.decode(value, { stream: true });

      // Parse SSE format: "data: <content>\n\n"
      const lines = text.split("\n");
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6); // Remove "data: " prefix

          // Check for completion sentinel
          if (data === "[DONE]") {
            return;
          }

          // Call callback with the chunk
          onChunk(data);
        }
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

  // ============= Dashboard API Methods =============

  /**
   * Get all sites/buildings
   */
  async getSites(): Promise<Site[]> {
    const response = await fetchApi<{ total: number; sites: Site[] }>("/api/sites");
    return response.sites;
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
   * @param buildingId - Building ID (e.g., 'sandton')
   */
  async getEquipmentSummary(buildingId: string): Promise<EquipmentSummary> {
    return fetchApi<EquipmentSummary>(`/api/buildings/${buildingId}/equipment-summary`);
  },

  /**
   * Get all equipment for a building with status
   * @param buildingId - Building ID (e.g., 'sandton')
   */
  async getBuildingEquipment(buildingId: string): Promise<BuildingEquipmentResponse> {
    return fetchApi<BuildingEquipmentResponse>(`/api/buildings/${buildingId}/equipment`);
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
    const response = await fetchApi<{ total: number; alerts: Alert[] }>("/api/alerts");
    return response.alerts;
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
      params.append("site_id", siteId);
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
    return fetchApi<EskomStatusResponse>(
      `/api/optimization/eskom-status${queryString ? `?${queryString}` : ""}`
    );
  },

  /**
   * Get load shedding schedule for a specific site
   * @param siteId - Site ID to get schedule for
   */
  async getSiteEskomStatus(siteId: string): Promise<SiteScheduleResponse> {
    return fetchApi<SiteScheduleResponse>(`/api/optimization/eskom-status/${siteId}`);
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
    return fetchApi<ThermalRunwayResponse>(`/api/optimization/thermal-runway?${params.toString()}`);
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
    return fetchApi<OptimizationScenario[]>(`/api/optimization/scenarios`);
  },

  // ============= AI Optimization API Methods (Phase 8) =============

  /**
   * Get optimization status for a specific site
   * @param siteId - Site ID
   */
  async getOptimizationStatus(siteId: string): Promise<OptimizationStatusResponse> {
    return fetchApi<OptimizationStatusResponse>(`/api/optimization/status/${siteId}`);
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
      params.append("device_id", deviceId);
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
  async enableAutonomousMode(): Promise<{ success: boolean; message: string }> {
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
  ): Promise<{ success: boolean; message: string }> {
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
  building_id: string;
  building_name?: string;
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
  building_id: string;
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
   * @param buildingId - Optional building ID filter
   */
  getIntegrationHealth: async (buildingId?: string): Promise<IntegrationHealthSummary> => {
    const url = buildingId
      ? `${API_BASE_URL}/api/integration/health?building_id=${buildingId}`
      : `${API_BASE_URL}/api/integration/health`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to fetch integration health');
    return res.json();
  },

  /**
   * Get data quality metrics for a building
   * @param buildingId - Building ID (required)
   */
  getDataQualityMetrics: async (buildingId: string): Promise<DataQualityMetrics> => {
    const res = await fetch(`${API_BASE_URL}/api/integration/quality-metrics/${buildingId}`);
    if (!res.ok) throw new Error('Failed to fetch quality metrics');
    return res.json();
  },

  /**
   * Get sync job history
   * @param buildingId - Optional building ID filter
   * @param days - Number of days of history (default: 7)
   */
  getSyncJobs: async (buildingId?: string, days: number = 7): Promise<SyncJobSummary[]> => {
    const params = new URLSearchParams({ days: days.toString() });
    if (buildingId) params.set('building_id', buildingId);
    const res = await fetch(`${API_BASE_URL}/api/integration/sync-jobs?${params}`);
    if (!res.ok) throw new Error('Failed to fetch sync jobs');
    return res.json();
  },

  /**
   * Get unmatched points for point matching review
   * @param buildingId - Building ID
   * @param limit - Maximum number of points to return (default: 10)
   * @param offset - Pagination offset (default: 0)
   */
  getUnmatchedPoints: async (buildingId?: string, limit: number = 10, offset: number = 0): Promise<{
    points: Array<{
      point_id: string;
      point_name: string;
      last_seen: string;
      occurrence_count: number;
    }>;
    total: number;
  }> => {
    const params = new URLSearchParams({
      confidence: 'unmatched',
      limit: limit.toString(),
      offset: offset.toString(),
    });
    if (buildingId) params.set('building_id', buildingId);
    const res = await fetch(`${API_BASE_URL}/api/integration/point-mappings?${params}`);
    if (!res.ok) throw new Error('Failed to fetch unmatched points');
    return res.json();
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

    const response = await fetch(`${API_BASE_URL}/api/integration/detect-format`, {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      throw new Error('Failed to detect format');
    }

    return response.json();
  },

  /**
   * Save column mappings for log source
   * @param buildingId - Building ID
   * @param logSourceId - Log source ID
   * @param mappings - Column mappings to save
   */
  saveColumnMappings: async (buildingId: string, logSourceId: string, mappings: ColumnMapping[]): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/integration/mappings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ building_id: buildingId, log_source_id: logSourceId, mappings })
    });

    if (!response.ok) {
      throw new Error('Failed to save mappings');
    }
  },

  /**
   * Match BMS points to CAFM assets
   * @param buildingId - Building ID
   * @param logSourceId - Log source ID
   * @param bmsPoints - List of BMS point IDs
   */
  matchPoints: async (buildingId: string, logSourceId: string, bmsPoints: string[]): Promise<PointMatch[]> => {
    const response = await fetch(`${API_BASE_URL}/api/integration/match-points`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ building_id: buildingId, log_source_id: logSourceId, bms_points: bmsPoints })
    });

    if (!response.ok) {
      throw new Error('Failed to match points');
    }

    return response.json();
  },

  /**
   * Ingest log file data
   * @param buildingId - Building ID
   * @param logSourceId - Log source ID
   * @param dryRun - If true, validate without processing
   */
  ingestLogs: async (buildingId: string, logSourceId: string, dryRun: boolean = false): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/integration/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ building_id: buildingId, log_source_id: logSourceId, dry_run: dryRun })
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
   * @param buildingId - Building ID
   */
  getChecklist: async (buildingId: string): Promise<ValidationChecklist> => {
    const response = await fetch(`${API_BASE_URL}/api/integration/buildings/${buildingId}/validation-checklist`);
    if (!response.ok) throw new Error('Failed to fetch validation checklist');
    return response.json();
  },

  /**
   * Get current building status
   * @param buildingId - Building ID
   */
  getStatus: async (buildingId: string): Promise<{ status: BuildingStatus; last_validated?: string }> => {
    const response = await fetch(`${API_BASE_URL}/api/integration/buildings/${buildingId}/status`);
    if (!response.ok) throw new Error('Failed to fetch building status');
    return response.json();
  },

  /**
   * Run validation and update building status
   * @param buildingId - Building ID
   */
  validate: async (buildingId: string): Promise<ValidationChecklist> => {
    const response = await fetch(`${API_BASE_URL}/api/integration/buildings/${buildingId}/validate`, {
      method: 'POST',
    });
    if (!response.ok) throw new Error('Validation failed');
    return response.json();
  },

  /**
   * Activate a building after successful validation
   * @param buildingId - Building ID
   */
  activate: async (buildingId: string): Promise<ActivationResult> => {
    const response = await fetch(`${API_BASE_URL}/api/integration/buildings/${buildingId}/activate`, {
      method: 'POST',
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Activation failed');
    }
    return response.json();
  },

  /**
   * Suspend (deactivate) a building
   * @param buildingId - Building ID
   */
  suspend: async (buildingId: string): Promise<{ status: BuildingStatus }> => {
    const response = await fetch(`${API_BASE_URL}/api/integration/buildings/${buildingId}/suspend`, {
      method: 'POST',
    });
    if (!response.ok) throw new Error('Suspend failed');
    return response.json();
  },
};

// ============= DALI Lighting Interfaces (Phase 21) =============

// DALI Controller interface
export interface DALIController {
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

// DALI Sensor interface (PIR occupancy sensor)
export interface DALISensor {
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

// DALI Luminaire interface
export interface DALILuminaire {
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
  building_id: string;
  building_name: string;
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

// DALI System Stats
export interface DALIStats {
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

// DALI API methods
export const daliApi = {
  /**
   * Get all DALI controllers
   * @param floor - Optional floor filter
   */
  getControllers: async (floor?: string): Promise<DALIController[]> => {
    const params = new URLSearchParams();
    if (floor) params.set('floor', floor);
    const queryString = params.toString();
    const response = await fetch(`${API_BASE_URL}/api/dali/controllers${queryString ? `?${queryString}` : ''}`);
    if (!response.ok) throw new Error('Failed to fetch DALI controllers');
    return response.json();
  },

  /**
   * Get DALI sensors with optional filtering
   * @param zoneId - Optional zone ID filter
   */
  getSensors: async (zoneId?: string): Promise<DALISensor[]> => {
    const params = new URLSearchParams();
    if (zoneId) params.set('zone_id', zoneId);
    const queryString = params.toString();
    const response = await fetch(`${API_BASE_URL}/api/dali/sensors${queryString ? `?${queryString}` : ''}`);
    if (!response.ok) throw new Error('Failed to fetch DALI sensors');
    return response.json();
  },

  /**
   * Get sensor by desk ID
   * @param deskId - Desk identifier
   */
  getSensorByDesk: async (deskId: string): Promise<DALISensor> => {
    const response = await fetch(`${API_BASE_URL}/api/dali/sensors/desk/${deskId}`);
    if (!response.ok) throw new Error('Failed to fetch sensor for desk');
    return response.json();
  },

  /**
   * Get DALI luminaires with optional filtering
   * @param zoneId - Optional zone ID filter
   */
  getLuminaires: async (zoneId?: string): Promise<DALILuminaire[]> => {
    const params = new URLSearchParams();
    if (zoneId) params.set('zone_id', zoneId);
    const queryString = params.toString();
    const response = await fetch(`${API_BASE_URL}/api/dali/luminaires${queryString ? `?${queryString}` : ''}`);
    if (!response.ok) throw new Error('Failed to fetch DALI luminaires');
    return response.json();
  },

  /**
   * Get faulty luminaires
   */
  getFaultyLuminaires: async (): Promise<DALILuminaire[]> => {
    const response = await fetch(`${API_BASE_URL}/api/dali/luminaires/faulty`);
    if (!response.ok) throw new Error('Failed to fetch faulty luminaires');
    return response.json();
  },

  /**
   * Get zone occupancy data
   * @param zoneId - Zone ID
   */
  getZoneOccupancy: async (zoneId: string): Promise<ZoneOccupancy> => {
    const response = await fetch(`${API_BASE_URL}/api/dali/zones/${zoneId}/occupancy`);
    if (!response.ok) throw new Error('Failed to fetch zone occupancy');
    return response.json();
  },

  /**
   * Get zone lighting status
   * @param zoneId - Zone ID
   */
  getZoneLighting: async (zoneId: string): Promise<ZoneLighting> => {
    const response = await fetch(`${API_BASE_URL}/api/dali/zones/${zoneId}/lighting`);
    if (!response.ok) throw new Error('Failed to fetch zone lighting');
    return response.json();
  },

  /**
   * Get floor summary
   * @param floor - Floor identifier (e.g., "L10", "L11", "L12")
   */
  getFloorSummary: async (floor: string): Promise<FloorSummary> => {
    const response = await fetch(`${API_BASE_URL}/api/dali/floors/${floor}/summary`);
    if (!response.ok) throw new Error('Failed to fetch floor summary');
    return response.json();
  },

  /**
   * Get building occupancy overview
   */
  getBuildingOccupancy: async (): Promise<BuildingOccupancy> => {
    const response = await fetch(`${API_BASE_URL}/api/dali/building/occupancy`);
    if (!response.ok) throw new Error('Failed to fetch building occupancy');
    return response.json();
  },

  /**
   * Get DALI system statistics
   */
  getStats: async (): Promise<DALIStats> => {
    const response = await fetch(`${API_BASE_URL}/api/dali/stats`);
    if (!response.ok) throw new Error('Failed to fetch DALI stats');
    return response.json();
  },
};

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

export default api;

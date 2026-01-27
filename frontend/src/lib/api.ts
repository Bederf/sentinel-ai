/**
 * API Client for BMS Intelligence Backend
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

// ============= Response Interfaces =============

interface HealthResponse {
  status: string;
  version: string;
}

interface ApiError {
  message: string;
  status: number;
}

// Site/Building interface (summary view)
export interface Site {
  id: string;
  name: string;
  location: string;
  address?: string; // Full address from backend
  region: string;
  type: string;
  equipment_count: number;
  alert_count: number;
  status: "normal" | "warning" | "critical";
  // Extended fields from backend (optional for summary, required for detail)
  sqm?: number;
  floors?: number;
  year_built?: number;
  operating_hours?: { start: string; end: string };
  occupancy_pattern?: string;
  contact_email?: string;
  contact_phone?: string;
  active_alerts?: number;
}

// Equipment interface
export interface Equipment {
  id: string;
  name: string;
  type: string;
  site_id: string;
  site_name: string;
  status: "online" | "offline" | "maintenance";
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
  recommended_action: string;
  parts_required: string[];
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
    const error: ApiError = {
      message: `API Error: ${response.statusText}`,
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
};

export default api;

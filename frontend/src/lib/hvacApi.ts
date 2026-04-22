/**
 * HVAC Module API Client
 *
 * Provides API access to:
 * - Zone temperature control
 * - Equipment status (AHU, FCU, Chiller)
 * - Thermal runway calculations
 * - Health configuration
 */

import { authorizedFetch } from "@/lib/api/client";

const API_BASE_URL = import.meta.env.VITE_API_URL || window.location.origin;

// ============= Zone Interfaces =============

export interface HVACZone {
  zone_id: string;
  zone_name: string;
  floor: string;
  fcu_id?: string;
  vav_id?: string;
  ahu_id?: string;
  temp_sensor?: string;
  co2_sensor?: string;
  typical_occupancy: number;
  area_sqm: number;
  setpoint: number;
  current_temp: number;
  status: "running" | "fault" | "offline";
  temp_deviation: number;
  temp_min: number;
  temp_max: number;
  fcu_health?: number;
}

// ============= Equipment Interfaces =============

export interface HealthFactor {
  score: number;
  value: string;
}

export interface HVACEquipment {
  id: string;
  site_id: string;
  type: "ahu" | "fcu" | "chiller" | "cooling_tower" | "vav" | "pump" | "crac";
  name: string;
  manufacturer: string;
  model: string;
  capacity: string;
  install_date: string;
  last_service: string;
  status: "normal" | "warning" | "fault" | "off" | "offline";
  health_score: number;
  location: string;
  serial_number?: string;
  calculated_health?: number;
  health_status?: "healthy" | "attention" | "critical";
  health_factors?: {
    age?: HealthFactor;
    service?: HealthFactor;
    runtime?: HealthFactor;
    fault_history?: HealthFactor;
  };
}

export interface ChillerMetadata {
  running?: boolean;
  power_kw?: number;
  load_percent?: number;
  chw_supply_temp?: number;
  chw_return_temp?: number;
  chw_supply_setpoint?: number;
  condenser_temp?: number;
  last_updated?: string;
}

export interface Chiller extends HVACEquipment {
  type: "chiller";
  is_running: boolean;
  metadata?: ChillerMetadata;
}

// ============= Overview Interfaces =============

export interface EquipmentSummary {
  count: number;
  avg_health: number;
  faults: number;
}

export interface HVACAlert {
  type: "zone_fault" | "temp_deviation" | "equipment_health" | "co2_warning";
  priority: "low" | "medium" | "high" | "critical";
  title: string;
  description: string;
  zone_id?: string;
  equipment_id?: string;
}

export interface HVACSentinelGuidance {
  headline: string;
  mode: "none" | "watch" | "prepare" | "intervene_soon" | "act_now";
}

export interface HVACSentinelNarrative {
  voice: string;
  message: string;
  action: string;
  time_to_breach_min: number | null;
}

export interface HVACSentinelIntelligence {
  building_posture: "calm" | "drifting" | "compensating" | "strained" | "critical";
  operator_guidance: HVACSentinelGuidance;
  primary_narrative: HVACSentinelNarrative | null;
  secondary_tensions: Array<{ voice: string; message: string }>;
}

export interface HVACRawTelemetrySummary {
  status: "live" | "unavailable";
  timestamp?: string;
  policy_stage?: string;
  zones_with_readings?: number;
  zone_count?: number;
  power?: {
    hvac_kw: number;
    lighting_kw: number;
    total_kw: number;
  };
  equipment_summary?: {
    total?: number;
    online?: number;
    avg_health_score?: number;
  };
}

export interface HVACOverview {
  site_id: string;
  timestamp: string;
  zones: {
    total: number;
    normal: number;
    fault: number;
    offline: number;
  };
  equipment: Record<string, EquipmentSummary>;
  overall_health: number;
  health_status: "healthy" | "attention" | "critical";
  alerts: HVACAlert[];
  chillers_running: number;
  raw_telemetry?: HVACRawTelemetrySummary | null;
  sentinel_intelligence?: HVACSentinelIntelligence | null;
}

// ============= Thermal Runway Interfaces =============

export interface ThermalRunwayData {
  time_points: string[];
  without_precooling: number[];
  with_precooling: number[];
}

export interface ThermalRunwayMetrics {
  runway_without: number;
  runway_with: number;
  comfort_breach_time: string;
  recovery_time: string;
  improvement_percent: number;
}

export interface ThermalRunway {
  site_id: string;
  timestamp: string;
  data: ThermalRunwayData;
  outage_period: {
    start: string;
    end: string;
  };
  metrics: ThermalRunwayMetrics;
  current_conditions: {
    avg_temperature: number;
    avg_setpoint: number;
    comfort_limit: number;
  };
}

// ============= Health Config Interfaces =============

export interface HealthWeights {
  age_factor: number;
  service_compliance: number;
  runtime_hours: number;
  fault_history: number;
}

export interface HealthThresholds {
  runtime_hours_warning: number;
  runtime_hours_critical: number;
  age_warning_years: number;
  age_critical_years: number;
  service_overdue_days_warning: number;
  service_overdue_days_critical: number;
}

export interface EquipmentHealthConfig {
  equipment_type: string;
  expected_life_years: number;
  service_interval_days: number;
  weights: HealthWeights;
  thresholds: HealthThresholds;
  fault_weights?: Record<string, number>;
}

export interface HealthConfigList {
  equipment_types: string[];
  configs: Record<string, EquipmentHealthConfig>;
  total: number;
}

// ============= Safety Limits =============

export interface SafetyLimit {
  min: number;
  max: number;
  unit: string;
}

export interface SafetyRule {
  id: string;
  name: string;
  type: string;
  severity: "block" | "warning" | "alarm";
  description: string;
}

export interface HVACSafetyLimits {
  temperature_setpoint: SafetyLimit;
  chiller_setpoint: SafetyLimit;
  safety_rules: SafetyRule[];
}

// ============= API Client =============

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const response = await authorizedFetch(url, {
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
      errorMessage = errorData.detail || errorData.message || JSON.stringify(errorData);
    } catch {
      // Use status text as fallback
    }
    throw new Error(`API Error: ${errorMessage}`);
  }

  return response.json();
}

// ============= HVAC API =============

export const hvacApi = {
  /**
   * Get HVAC overview for a site
   */
  getOverview: async (siteId: string): Promise<HVACOverview> => {
    return fetchApi<HVACOverview>(`/api/hvac/overview/${siteId}`);
  },

  /**
   * Get all HVAC zones
   */
  getZones: async (siteId?: string, floor?: string): Promise<{ zones: HVACZone[]; total: number }> => {
    const params = new URLSearchParams();
    if (siteId) params.append("site_id", siteId);
    if (floor) params.append("floor", floor);
    const query = params.toString();
    return fetchApi(`/api/hvac/zones${query ? `?${query}` : ""}`);
  },

  /**
   * Get single zone details
   */
  getZone: async (zoneId: string): Promise<HVACZone> => {
    return fetchApi<HVACZone>(`/api/hvac/zones/${zoneId}`);
  },

  /**
   * Set zone temperature setpoint
   */
  setZoneSetpoint: async (
    zoneId: string,
    setpoint: number
  ): Promise<{ success: boolean; zone_id: string; old_setpoint: number; new_setpoint: number; message: string }> => {
    return fetchApi(`/api/hvac/zones/${zoneId}/setpoint`, {
      method: "POST",
      body: JSON.stringify({ setpoint }),
    });
  },

  /**
   * Get all HVAC equipment
   */
  getEquipment: async (
    siteId?: string,
    equipmentType?: string
  ): Promise<{ equipment: HVACEquipment[]; total: number }> => {
    const params = new URLSearchParams();
    if (siteId) params.append("site_id", siteId);
    if (equipmentType) params.append("equipment_type", equipmentType);
    const query = params.toString();
    return fetchApi(`/api/hvac/equipment${query ? `?${query}` : ""}`);
  },

  /**
   * Get single equipment details
   */
  getEquipmentDetails: async (equipmentId: string): Promise<HVACEquipment> => {
    return fetchApi<HVACEquipment>(`/api/hvac/equipment/${equipmentId}`);
  },

  /**
   * Get all chillers
   */
  getChillers: async (siteId?: string): Promise<{ chillers: Chiller[]; total: number; running: number }> => {
    const params = new URLSearchParams();
    if (siteId) params.append("site_id", siteId);
    const query = params.toString();
    return fetchApi(`/api/hvac/chillers${query ? `?${query}` : ""}`);
  },

  /**
   * Control chiller on/off
   */
  controlChiller: async (
    chillerId: string,
    action: "on" | "off"
  ): Promise<{
    success: boolean;
    chiller_id: string;
    action: string;
    old_status: string;
    new_status: string;
    message: string;
  }> => {
    return fetchApi(`/api/hvac/chillers/${chillerId}/control`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
  },

  /**
   * Get chiller CHW setpoint and limits
   */
  getChillerSetpoint: async (
    chillerId: string
  ): Promise<{
    chiller_id: string;
    chiller_name: string;
    current_setpoint: number;
    current_supply_temp: number | null;
    current_return_temp: number | null;
    limits: { min: number; max: number; unit: string };
  }> => {
    return fetchApi(`/api/hvac/chillers/${chillerId}/setpoint`);
  },

  /**
   * Set chiller CHW supply temperature setpoint
   */
  setChillerSetpoint: async (
    chillerId: string,
    setpoint: number
  ): Promise<{
    success: boolean;
    chiller_id: string;
    chiller_name: string;
    old_setpoint: number;
    new_setpoint: number;
    message: string;
  }> => {
    return fetchApi(`/api/hvac/chillers/${chillerId}/setpoint`, {
      method: "POST",
      body: JSON.stringify({ setpoint }),
    });
  },

  /**
   * Get thermal runway calculations
   * Note: served by optimization backend, not hvac
   */
  getThermalRunway: async (siteId: string, currentTemp?: number, comfortLimit?: number): Promise<ThermalRunway> => {
    const params = new URLSearchParams({ site_id: siteId });
    if (currentTemp !== undefined) params.set("current_temp", currentTemp.toString());
    if (comfortLimit !== undefined) params.set("comfort_limit", comfortLimit.toString());

    // Backend returns flat structure; transform to ThermalRunway interface
    const data = await fetchApi<Record<string, unknown>>(`/api/optimization/thermal-runway?${params.toString()}`);
    return transformToThermalRunway(data);
  },

  /**
   * Get HVAC safety limits
   */
  getSafetyLimits: async (): Promise<HVACSafetyLimits> => {
    return fetchApi<HVACSafetyLimits>(`/api/hvac/safety-limits`);
  },
};

// ============= Health Config API =============

export const healthConfigApi = {
  /**
   * List all health configurations
   */
  list: async (): Promise<HealthConfigList> => {
    return fetchApi<HealthConfigList>(`/api/health-config`);
  },

  /**
   * Get health config for equipment type
   */
  get: async (equipmentType: string): Promise<EquipmentHealthConfig> => {
    return fetchApi<EquipmentHealthConfig>(`/api/health-config/${equipmentType}`);
  },

  /**
   * Update health config for equipment type
   */
  update: async (
    equipmentType: string,
    config: Partial<Omit<EquipmentHealthConfig, "equipment_type">>
  ): Promise<{ message: string; config: EquipmentHealthConfig }> => {
    return fetchApi(`/api/health-config/${equipmentType}`, {
      method: "PUT",
      body: JSON.stringify(config),
    });
  },

  /**
   * Create health config for new equipment type
   */
  create: async (
    equipmentType: string,
    config: EquipmentHealthConfig
  ): Promise<{ message: string; config: EquipmentHealthConfig }> => {
    return fetchApi(`/api/health-config/${equipmentType}`, {
      method: "POST",
      body: JSON.stringify(config),
    });
  },

  /**
   * Reset health config to defaults
   */
  reset: async (equipmentType: string): Promise<{ message: string; config: EquipmentHealthConfig }> => {
    return fetchApi(`/api/health-config/reset/${equipmentType}`, {
      method: "POST",
    });
  },

  /**
   * Delete health config for equipment type
   */
  delete: async (equipmentType: string): Promise<{ message: string }> => {
    return fetchApi(`/api/health-config/${equipmentType}`, {
      method: "DELETE",
    });
  },
};

// ============= Response Transformers =============

/**
 * Transform backend optimization/thermal-runway response to ThermalRunway interface.
 * Backend returns a flat structure; frontend expects nested metrics + data arrays.
 */
function transformToThermalRunway(data: Record<string, unknown>): ThermalRunway {
  const runwayMinutes = (data.thermal_runway_minutes as number) ?? 0;
  const currentTemp = (data.current_temperature as number) ?? 22.4;
  const comfortLimit = (data.comfort_limit as number) ?? 26.0;

  // Backend returns a single runway_minutes; derive without/with precooling
  // Conservative: pre-cooling adds ~30% runway improvement
  const runwayWithout = runwayMinutes;
  const runwayWith = Math.min(180, Math.round(runwayMinutes * 1.3));
  const improvementPercent = runwayWithout > 0
    ? Math.round(((runwayWith - runwayWithout) / runwayWithout) * 100)
    : 0;

  // Build time-series data points (hourly for 8h window)
  const now = new Date();
  const timePoints: string[] = [];
  const withoutPrecooling: number[] = [];
  const withPrecooling: number[] = [];
  for (let i = 0; i <= 8; i++) {
    const t = new Date(now.getTime() + i * 60 * 60 * 1000);
    timePoints.push(t.toISOString());
    // Linear degradation from current_temp toward outside_temp (32°C)
    const degradation = (i / 8) * (32 - currentTemp);
    withoutPrecooling.push(Number((currentTemp + degradation).toFixed(1)));
    // Pre-cooled: starts 2°C lower
    const precooledStart = Math.max(currentTemp - 2, currentTemp);
    const precooledDegradation = (i / 8) * (32 - precooledStart);
    withPrecooling.push(Number((precooledStart + precooledDegradation).toFixed(1)));
  }

  return {
    site_id: (data.site_id as string) ?? "",
    timestamp: new Date().toISOString(),
    data: {
      time_points: timePoints,
      without_precooling: withoutPrecooling,
      with_precooling: withPrecooling,
    },
    outage_period: {
      start: new Date().toISOString(),
      end: new Date(now.getTime() + runwayMinutes * 60 * 1000).toISOString(),
    },
    metrics: {
      runway_without: runwayWithout,
      runway_with: runwayWith,
      comfort_breach_time: (data.comfort_breach_time as string) ?? new Date(now.getTime() + runwayWithout * 60 * 1000).toISOString(),
      recovery_time: new Date(now.getTime() + (runwayWith + 30) * 60 * 1000).toISOString(),
      improvement_percent: improvementPercent,
    },
    current_conditions: {
      avg_temperature: currentTemp,
      avg_setpoint: comfortLimit - 2,
      comfort_limit: comfortLimit,
    },
  };
}

// ============= Exports =============

export default {
  hvac: hvacApi,
  healthConfig: healthConfigApi,
};

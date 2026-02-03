/**
 * HVAC Module API Client
 *
 * Provides API access to:
 * - Zone temperature control
 * - Equipment status (AHU, FCU, Chiller)
 * - Thermal runway calculations
 * - Health configuration
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

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
   */
  getThermalRunway: async (siteId: string): Promise<ThermalRunway> => {
    return fetchApi<ThermalRunway>(`/api/hvac/thermal-runway/${siteId}`);
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

// ============= Exports =============

export default {
  hvac: hvacApi,
  healthConfig: healthConfigApi,
};

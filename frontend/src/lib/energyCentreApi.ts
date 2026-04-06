/**
 * Energy Centre API Client - Bolt-on Module
 *
 * Provides API access to:
 * - Generators (DeepSea DSE controllers)
 * - ATS (Automatic Transfer Switch)
 * - MV/LV Switchgear
 * - Transformers
 * - Power Metering
 * - PFC (Power Factor Correction)
 * - UPS Systems
 * - SCADA Overview
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

// ============= Generator Interfaces =============

export interface GeneratorEngine {
  rpm: number;
  oil_pressure_kpa: number;
  coolant_temp_c: number;
  oil_temp_c?: number;
  exhaust_temp_c?: number;
  turbo_pressure_kpa?: number;
  run_hours: number;
  total_starts: number;
  current_runtime_sec: number;
  fuel_rate_lph: number;
}

export interface GeneratorElectrical {
  voltage_l1: number;
  voltage_l2: number;
  voltage_l3: number;
  voltage_l1_l2: number;
  voltage_l2_l3: number;
  voltage_l3_l1: number;
  current_l1: number;
  current_l2: number;
  current_l3: number;
  frequency_hz: number;
  power_kw: number;
  power_kva: number;
  power_factor: number;
  total_kwh: number;
}

export interface GeneratorAlarm {
  code: string;
  description: string;
  severity: 'warning' | 'alarm' | 'shutdown';
  timestamp: string;
  acknowledged: boolean;
}

export interface Generator {
  generator_id: string;
  name: string;
  site_id: string;
  building: string;
  location: string;
  controller_model: string;
  controller_ip: string;
  modbus_port: number;
  modbus_unit_id: number;
  rated_power_kw: number;
  rated_power_kva: number;
  rated_voltage: number;
  rated_frequency: number;
  status: 'standby' | 'running' | 'on_load' | 'cooling' | 'maintenance' | 'fault' | 'offline';
  mains_available: boolean;
  engine_running: boolean;
  on_load: boolean;
  battery_voltage: number;
  charger_current: number;
  start_attempts: number;
  fuel_level_pct: number;
  fuel_tank_id?: string;
  engine?: GeneratorEngine;
  electrical?: GeneratorElectrical;
  alarms: GeneratorAlarm[];
  next_service_hours: number;
  last_service_date?: string;
  group_id?: string;
  priority: number;
  last_poll?: string;
}

export interface GeneratorGroup {
  group_id: string;
  name: string;
  site_id: string;
  building: string;
  total_generators: number;
  required_running: number;
  transfer_mode: 'open' | 'closed' | 'soft_load';
  generator_ids: string[];
  generators_running: number;
  total_load_kw: number;
  total_capacity_kw: number;
  load_percent: number;
  ats_position: 'mains' | 'generator' | 'transitioning';
  mains_healthy: boolean;
  diesel_tank_id?: string;
}

export interface DieselTank {
  tank_id: string;
  name: string;
  capacity_liters: number;
  current_level_liters: number;
  current_level_pct: number;
  low_level_alarm_pct: number;
  reorder_level_pct: number;
  last_fill_date?: string;
  last_fill_liters?: number;
  daily_consumption_avg: number;
  days_remaining?: number;
  supplier?: string;
}

export interface PredictiveIndicator {
  parameter: string;
  current_value: number;
  threshold_low?: number;
  threshold_high?: number;
  trend: 'improving' | 'stable' | 'degrading' | 'critical';
  days_to_threshold?: number;
  recommendation?: string;
}

export interface GeneratorHealth {
  generator_id: string;
  overall_score: number;
  status: 'healthy' | 'attention' | 'warning' | 'critical';
  indicators: PredictiveIndicator[];
  last_assessment?: string;
}

// ============= Energy Centre Interfaces =============

export interface ATSUnit {
  ats_id: string;
  name: string;
  site_id: string;
  location: string;
  ats_type: 'mechanical' | 'electronic' | 'hybrid';
  rated_current_a: number;
  rated_voltage: number;
  poles: number;
  transfer_mode: 'open' | 'closed' | 'soft_load';
  position: 'mains' | 'generator' | 'off' | 'transitioning' | 'parallel';
  mains_available: boolean;
  generator_available: boolean;
  mains_breaker: 'open' | 'closed' | 'tripped';
  gen_breaker: 'open' | 'closed' | 'tripped';
  bus_coupler?: string;
  last_transfer_time_ms: number;
  transfer_count: number;
  last_transfer_timestamp?: string;
  last_transfer_reason?: string;
  mechanical_interlock_ok: boolean;
  electrical_interlock_ok: boolean;
  controller_ip?: string;
  protocol: string;
  last_poll?: string;
}

export interface MVIncomer {
  incomer_id: string;
  name: string;
  site_id: string;
  location: string;
  nominal_voltage_kv: number;
  rated_current_a: number;
  fault_level_mva: number;
  voltage_kv: number;
  current_a: number;
  power_kw: number;
  power_factor: number;
  frequency_hz: number;
  breaker_state: 'open' | 'closed' | 'tripped';
  healthy: boolean;
  protection_relay_model?: string;
  overcurrent_pickup_a: number;
  earth_fault_pickup_a: number;
  last_trip_timestamp?: string;
  last_trip_code?: string;
  supply_point_id?: string;
  tariff_type?: string;
}

export interface Transformer {
  transformer_id: string;
  name: string;
  site_id: string;
  location: string;
  rated_power_kva: number;
  primary_voltage_kv: number;
  secondary_voltage_v: number;
  vector_group: string;
  impedance_pct: number;
  load_kva: number;
  load_percent: number;
  oil_temp_c?: number;
  winding_temp_c?: number;
  ambient_temp_c?: number;
  tap_position: number;
  tap_range_pct: number;
  on_load_tap_changer: boolean;
  healthy: boolean;
  oil_level_ok: boolean;
  buchholz_alarm: boolean;
  pressure_relief_ok: boolean;
  cooling_type: string;
  fans_running: number;
}

export interface LVSwitchboard {
  switchboard_id: string;
  name: string;
  site_id: string;
  location: string;
  rated_voltage: number;
  rated_current_a: number;
  fault_rating_ka: number;
  bus_sections: number;
  bus_coupler_closed: boolean;
  voltage_l1_n: number;
  voltage_l2_n: number;
  voltage_l3_n: number;
  voltage_l1_l2: number;
  voltage_l2_l3: number;
  voltage_l3_l1: number;
  frequency_hz: number;
  mains_incomer_closed: boolean;
  gen_incomer_closed: boolean;
  total_power_kw: number;
  total_power_kva: number;
  power_factor: number;
  total_kwh: number;
  healthy: boolean;
  temperature_c?: number;
}

export interface PowerMeter {
  meter_id: string;
  name: string;
  site_id: string;
  location: string;
  meter_type: 'main' | 'sub' | 'check' | 'generator';
  manufacturer: string;
  model?: string;
  serial_number?: string;
  ct_ratio: string;
  vt_ratio?: string;
  voltage_l1_n: number;
  voltage_l2_n: number;
  voltage_l3_n: number;
  current_l1: number;
  current_l2: number;
  current_l3: number;
  current_n: number;
  active_power_kw: number;
  reactive_power_kvar: number;
  apparent_power_kva: number;
  power_factor: number;
  frequency_hz: number;
  kwh_import: number;
  kwh_export: number;
  kvarh_import: number;
  kvarh_export: number;
  max_demand_kw: number;
  max_demand_timestamp?: string;
  thd_voltage_pct?: number;
  thd_current_pct?: number;
  voltage_unbalance_pct?: number;
  tariff_type?: string;
  tou_period?: string;
  protocol: string;
  ip_address?: string;
  last_poll?: string;
}

export interface PFCBank {
  pfc_id: string;
  name: string;
  site_id: string;
  location: string;
  total_kvar: number;
  steps: number;
  step_size_kvar: number;
  active_steps: number;
  active_kvar: number;
  target_power_factor: number;
  current_power_factor: number;
  controller_model?: string;
  auto_mode: boolean;
  healthy: boolean;
  capacitor_temps_ok: boolean;
  fuse_status_ok: boolean;
}

export interface UPSSystem {
  ups_id: string;
  name: string;
  site_id: string;
  location: string;
  rated_power_kva: number;
  rated_power_kw: number;
  topology: 'online' | 'line-interactive' | 'offline';
  input_voltage: number;
  input_frequency: number;
  input_healthy: boolean;
  output_voltage: number;
  output_frequency: number;
  load_kw: number;
  load_percent: number;
  battery_voltage: number;
  battery_current: number;
  battery_charge_pct: number;
  battery_runtime_min: number;
  battery_temp_c?: number;
  battery_health_pct: number;
  battery_test_date?: string;
  battery_replace_date?: string;
  mode: 'online' | 'battery' | 'bypass' | 'standby' | 'fault';
  on_battery: boolean;
  on_bypass: boolean;
  overload: boolean;
  alarms: string[];
  protocol: string;
  ip_address?: string;
  last_poll?: string;
}

export interface Feeder {
  feeder_id: string;
  name: string;
  breaker_state: 'open' | 'closed' | 'tripped';
  rated_current_a: number;
  current_a: number;
  power_kw: number;
}

export interface SLDNode {
  id: string;
  type: 'mv_incomer' | 'transformer' | 'ats' | 'generator' | 'switchboard' | 'ups';
  label: string;
  status?: string;
  voltage?: number;
  breaker?: string;
  load_percent?: number;
  temp_c?: number;
  position?: string;
  mains_breaker?: string;
  gen_breaker?: string;
  running?: boolean;
  on_load?: boolean;
  mode?: string;
  battery_pct?: number;
  on_battery?: boolean;
  power_kw?: number;
}

export interface SLDConnection {
  from: string;
  to: string;
  type: 'mv_cable' | 'lv_cable' | 'busbar';
  energized: boolean;
  port?: string;
}

export interface SLDData {
  site_id: string;
  timestamp: string;
  nodes: SLDNode[];
  connections: SLDConnection[];
  status: {
    mains_healthy: boolean;
    on_generator: boolean;
    all_systems_normal: boolean;
  };
}

export interface SCADAOverview {
  site_id: string;
  centre?: any;
  timestamp: string;
  status: {
    mains_healthy: boolean;
    on_generator: boolean;
    all_systems_normal: boolean;
  };
  mv_supply: {
    incomers: MVIncomer[];
    voltage_kv: number;
    healthy: boolean;
  };
  transformers: {
    units: Transformer[];
    total_capacity_kva: number;
    total_load_kva: number;
    avg_load_percent: number;
  };
  ats: {
    units: ATSStatus[];
    current_source: string;
  };
  generators: any;
  lv_distribution: {
    switchboards: LVSwitchboard[];
    feeders: Feeder[];
    total_power_kw: number;
  };
  power_metering: {
    main: PowerMeter | null;
    total_kwh: number;
    power_factor: number;
    tariff: string | null;
    tou_period: string | null;
  };
  power_factor_correction: {
    banks: PFCBank[];
    total_kvar: number;
    active_kvar: number;
    current_pf: number;
  };
  ups: UPSSummary;
  scada_network: any;
}

export interface ATSStatus {
  ats_id: string;
  name: string;
  timestamp: string;
  position: string;
  type: string;
  transfer_mode: string;
  sources: {
    mains: { available: boolean; breaker: string };
    generator: { available: boolean; breaker: string };
  };
  interlocks: {
    mechanical_ok: boolean;
    electrical_ok: boolean;
  };
  transfer_stats: {
    total_transfers: number;
    last_transfer_time_ms: number;
    last_transfer: string | null;
    last_reason: string | null;
  };
}

export interface UPSSummary {
  site_id: string;
  timestamp: string;
  total_capacity_kva: number;
  total_load_kw: number;
  all_healthy: boolean;
  any_on_battery: boolean;
  systems: {
    ups_id: string;
    name: string;
    mode: string;
    load_percent: number;
    battery_charge_pct: number;
    runtime_min: number;
    on_battery: boolean;
    alarms: string[];
  }[];
}

export interface GeneratorGroupStatus {
  group_id: string;
  name: string;
  timestamp: string;
  generators: {
    total: number;
    running: number;
    on_load: number;
    faulted: number;
    required: number;
  };
  load: {
    current_kw: number;
    capacity_kw: number;
    percent: number;
  };
  ats: {
    position: string;
    mains_healthy: boolean;
    transfer_mode: string;
  };
  fuel: DieselTank | null;
  generator_details: {
    generator_id: string;
    name: string;
    status: string;
    priority: number;
    engine_running: boolean;
    on_load: boolean;
    load_kw: number;
    battery_voltage: number;
    fuel_level_pct: number;
  }[];
}

export interface FuelStatus {
  tank_id: string;
  name: string;
  capacity_liters: number;
  current_liters: number;
  current_pct: number;
  low_alarm_pct: number;
  reorder_pct: number;
  current_burn_rate_lph: number;
  hours_remaining: number | null;
  days_remaining: number | null;
  last_fill_date: string | null;
  alerts: {
    severity: string;
    message: string;
    action: string;
  }[];
}

// ============= API Client =============

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const token =
    (typeof window !== "undefined" && localStorage.getItem("access_token")) ||
    (typeof window !== "undefined" && localStorage.getItem("sentinel_token")) ||
    "";
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let errorMessage = response.statusText;
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || JSON.stringify(errorData);
    } catch { /* ignore JSON parse errors */ }
    throw new Error(`API Error: ${errorMessage}`);
  }

  return response.json();
}

// ============= Generator API =============

export const generatorApi = {
  /**
   * Get all generators
   */
  getGenerators: async (siteId?: string, groupId?: string): Promise<Generator[]> => {
    const params = new URLSearchParams();
    if (siteId) params.append('site_id', siteId);
    if (groupId) params.append('group_id', groupId);
    const query = params.toString();
    const response = await fetchApi<{ generators: Generator[]; total: number }>(
      `/api/generators${query ? `?${query}` : ''}`
    );
    return response.generators;
  },

  /**
   * Get single generator
   */
  getGenerator: async (generatorId: string): Promise<Generator> => {
    return fetchApi<Generator>(`/api/generators/${generatorId}`);
  },

  /**
   * Get generator telemetry (Modbus poll data)
   */
  getTelemetry: async (generatorId: string): Promise<any> => {
    return fetchApi(`/api/generators/${generatorId}/telemetry`);
  },

  /**
   * Get generator health assessment
   */
  getHealth: async (generatorId: string): Promise<GeneratorHealth> => {
    return fetchApi<GeneratorHealth>(`/api/generators/${generatorId}/health`);
  },

  /**
   * Get all generator groups
   */
  getGroups: async (siteId?: string): Promise<GeneratorGroup[]> => {
    const params = new URLSearchParams();
    if (siteId) params.append('site_id', siteId);
    const query = params.toString();
    const response = await fetchApi<{ groups: GeneratorGroup[]; total: number }>(
      `/api/generators/groups/list${query ? `?${query}` : ''}`
    );
    return response.groups;
  },

  /**
   * Get generator group status
   */
  getGroupStatus: async (groupId: string): Promise<GeneratorGroupStatus> => {
    return fetchApi<GeneratorGroupStatus>(`/api/generators/groups/${groupId}/status`);
  },

  /**
   * Get fuel status for a group
   */
  getFuelStatus: async (groupId: string): Promise<FuelStatus> => {
    return fetchApi<FuelStatus>(`/api/generators/groups/${groupId}/fuel`);
  },

  /**
   * Get all diesel tanks
   */
  getTanks: async (): Promise<DieselTank[]> => {
    const response = await fetchApi<{ tanks: DieselTank[]; total: number }>(
      `/api/generators/tanks/list`
    );
    return response.tanks;
  },

  /**
   * Get generator SCADA overview
   */
  getSCADA: async (siteId: string): Promise<any> => {
    return fetchApi(`/api/generators/scada/${siteId}`);
  },

  /**
   * Get site health summary
   */
  getSiteHealth: async (siteId: string): Promise<any> => {
    return fetchApi(`/api/generators/health/${siteId}`);
  },

  /**
   * Simulate event (local fallback)
   */
  simulate: async (event: 'load_shedding' | 'mains_restored' | 'normal'): Promise<any> => {
    return fetchApi(`/api/generators/simulate/${event}`, { method: 'POST' });
  },
};

// ============= Energy Centre API =============

export const energyCentreApi = {
  /**
   * Get complete SCADA overview
   */
  getSCADAOverview: async (siteId: string): Promise<SCADAOverview> => {
    return fetchApi<SCADAOverview>(`/api/energy-centre/scada/${siteId}`);
  },

  /**
   * Get single-line diagram data
   */
  getSLDData: async (siteId: string): Promise<SLDData> => {
    return fetchApi<SLDData>(`/api/energy-centre/sld/${siteId}`);
  },

  /**
   * Get all ATS units
   */
  getATSUnits: async (siteId?: string): Promise<ATSUnit[]> => {
    const params = new URLSearchParams();
    if (siteId) params.append('site_id', siteId);
    const query = params.toString();
    const response = await fetchApi<{ ats_units: ATSUnit[]; total: number }>(
      `/api/energy-centre/ats${query ? `?${query}` : ''}`
    );
    return response.ats_units;
  },

  /**
   * Get ATS status
   */
  getATSStatus: async (atsId: string): Promise<ATSStatus> => {
    return fetchApi<ATSStatus>(`/api/energy-centre/ats/${atsId}/status`);
  },

  /**
   * Get all MV incomers
   */
  getMVIncomers: async (siteId?: string): Promise<MVIncomer[]> => {
    const params = new URLSearchParams();
    if (siteId) params.append('site_id', siteId);
    const query = params.toString();
    const response = await fetchApi<{ mv_incomers: MVIncomer[]; total: number }>(
      `/api/energy-centre/mv-incomers${query ? `?${query}` : ''}`
    );
    return response.mv_incomers;
  },

  /**
   * Get all transformers
   */
  getTransformers: async (siteId?: string): Promise<Transformer[]> => {
    const params = new URLSearchParams();
    if (siteId) params.append('site_id', siteId);
    const query = params.toString();
    const response = await fetchApi<{ transformers: Transformer[]; total: number }>(
      `/api/energy-centre/transformers${query ? `?${query}` : ''}`
    );
    return response.transformers;
  },

  /**
   * Get all power meters
   */
  getMeters: async (siteId?: string, meterType?: string): Promise<PowerMeter[]> => {
    const params = new URLSearchParams();
    if (siteId) params.append('site_id', siteId);
    if (meterType) params.append('meter_type', meterType);
    const query = params.toString();
    const response = await fetchApi<{ meters: PowerMeter[]; total: number }>(
      `/api/energy-centre/meters${query ? `?${query}` : ''}`
    );
    return response.meters;
  },

  /**
   * Get power summary
   */
  getPowerSummary: async (siteId: string): Promise<any> => {
    return fetchApi(`/api/energy-centre/power-summary/${siteId}`);
  },

  /**
   * Get all PFC banks
   */
  getPFCBanks: async (siteId?: string): Promise<PFCBank[]> => {
    const params = new URLSearchParams();
    if (siteId) params.append('site_id', siteId);
    const query = params.toString();
    const response = await fetchApi<{ pfc_banks: PFCBank[]; total: number }>(
      `/api/energy-centre/pfc${query ? `?${query}` : ''}`
    );
    return response.pfc_banks;
  },

  /**
   * Get all UPS systems
   */
  getUPSSystems: async (siteId?: string): Promise<UPSSystem[]> => {
    const params = new URLSearchParams();
    if (siteId) params.append('site_id', siteId);
    const query = params.toString();
    const response = await fetchApi<{ ups_systems: UPSSystem[]; total: number }>(
      `/api/energy-centre/ups${query ? `?${query}` : ''}`
    );
    return response.ups_systems;
  },

  /**
   * Get UPS summary
   */
  getUPSSummary: async (siteId: string): Promise<UPSSummary> => {
    return fetchApi<UPSSummary>(`/api/energy-centre/ups-summary/${siteId}`);
  },

  /**
   * Get all feeders
   */
  getFeeders: async (siteId?: string): Promise<Feeder[]> => {
    const params = new URLSearchParams();
    if (siteId) params.append('site_id', siteId);
    const query = params.toString();
    const response = await fetchApi<{ feeders: Feeder[]; total: number }>(
      `/api/energy-centre/feeders${query ? `?${query}` : ''}`
    );
    return response.feeders;
  },
};

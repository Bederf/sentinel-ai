/**
 * Mock Data Factories - Consistent test data generation
 *
 * Factories for Phase 4 complex page component testing:
 * - Optimization scenarios and status
 * - Dashboard stats, predictions, buildings
 * - Profitability contracts and metrics
 * - Technician chat messages and responses
 */

import type {
  OptimizationScenario,
  OptimizationStatusResponse,
  Site,
  DashboardStats,
  Prediction,
  BuildingEquipmentItem,
  EnergyDataPoint,
  Device,
  DeviceStatus,
  DeviceSafetyStatus,
  Equipment,
  Alert,
} from '@/lib/api';
import type { ModuleContextValue } from '@/contexts/moduleContextStore';

/**
 * Optimization Scenario Factory
 */
export function createMockOptimizationScenario(overrides?: Partial<OptimizationScenario>): OptimizationScenario {
  return {
    scenario_id: 'scenario-001',
    site_id: 'site-002',
    site_name: 'Sandton City',
    thermal_runway: {
      without_precooling: 45,
      with_precooling: 120,
      comfort_maintained: true,
      comfort_breach_time: '00:45:00',
      calculation_params: {
        thermal_mass: 100,
        insulation_factor: 0.8,
        internal_heat_gain: 50,
      },
    },
    savings: {
      energy_savings_percent: 18,
      comfort_extension_minutes: 75,
      fuel_savings_percent: 12,
      total_savings_zar: 4250,
      breakdown: {
        reduced_generator_runtime: 1000,
        avoided_peak_demand_charges: 500,
        improved_efficiency: 1500,
        reduced_restart_energy: 250,
      },
    },
    ...overrides,
  } as any;
}

/**
 * Optimization Status Factory
 */
export function createMockOptimizationStatus(overrides?: Partial<OptimizationStatusResponse>): OptimizationStatusResponse {
  return {
    site_id: 'site-002',
    next_scheduled: new Date(Date.now() + 86400000).toISOString(),
    optimization_history: [
      {
        timestamp: new Date().toISOString(),
        action: 'Precooling enabled',
        result: 'success',
        user: 'System',
      },
      {
        timestamp: new Date(Date.now() - 3600000).toISOString(),
        action: 'Load shed started',
        result: 'success',
        user: 'Operator',
      },
    ],
    ...overrides,
  } as any;
}

/**
 * Dashboard Stats Factory
 */
export function createMockDashboardStats(overrides?: Partial<DashboardStats>): DashboardStats {
  return {
    total_sites: 5,
    total_equipment: 156,
    total_sensors: 500,
    active_alerts: 3,
    critical_alerts: 1,
    pending_anomalies: 2,
    uptime_percent: 97.2,
    ...overrides,
  } as any;
}

/**
 * Prediction Factory
 */
export function createMockPrediction(overrides?: Partial<Prediction>): Prediction {
  return {
    id: 'pred-001',
    site_id: 'site-002',
    site_name: 'Sandton City',
    equipment_id: 'S002-CHILLER-B1-001',
    equipment_name: 'Primary Chiller',
    equipment_type: 'CHILLER',
    prediction_type: 'bearing_failure',
    severity: 'critical',
    probability_percent: 78,
    timeframe_days: 14,
    confidence: 'high',
    financial_impact: {
      repair_cost_zar: 50000,
      replacement_cost_zar: 150000,
      downtime_cost_per_hour_zar: 5000,
      estimated_repair_hours: 4,
      potential_loss_zar: 85000,
    },
    ...overrides,
  } as any;
}

/**
 * Building Equipment Item Factory
 */
export function createMockBuildingEquipmentItem(overrides?: Partial<BuildingEquipmentItem>): BuildingEquipmentItem {
  return {
    id: 'equipment-001',
    name: 'Primary Chiller',
    type: 'chiller',
    category: 'hvac',
    health: 45,
    status: 'warning',
    site_id: 'site-002',
    location: 'Basement - Plant Room',
    building_id: 'building-001',
    building_name: 'Test Building',
    details: {},
    controllable: false,
    ...overrides,
  };
}

/**
 * Energy Data Point Factory
 */
export function createMockEnergyDataPoint(overrides?: Partial<EnergyDataPoint>): EnergyDataPoint {
  return {
    timestamp: new Date().toISOString(),
    consumption_kwh: 2450,
    cost_zar: 3675,
    peak_kw: 450,
    avg_kw: 102,
    ...overrides,
  } as any;
}

/**
 * Energy Response Factory
 */
export function createMockEnergyResponse(overrides?: any) {
  return {
    days: 30,
    site_id: 'site-002',
    data: [createMockEnergyDataPoint()],
    ...overrides,
  };
}

/**
 * Site Factory
 */
export function createMockSite(overrides?: Partial<Site>): Site {
  return {
    id: 'site-002',
    name: 'Sandton City Office Tower',
    type: 'office',
    status: 'normal',
    location: 'Johannesburg, South Africa',
    equipment_count: 175,
    alert_count: 3,
    ...overrides,
  } as any;
}

/**
 * Profitability Contract Factory
 */
export function createMockContractProfitability(overrides?: any) {
  return {
    contract_id: 'contract-001',
    contract_name: 'Sandton Maintenance Agreement',
    building_id: 'building-001',
    building_name: 'Sandton City Office Tower',
    net_revenue_zar: 250000,
    total_cost_zar: 180000,
    gross_margin_zar: 70000,
    gross_margin_percentage: 28,
    status: 'profitable' as const,
    ...overrides,
  };
}

/**
 * Technician Chat Message Factory
 */
export function createMockChatMessage(overrides?: any) {
  return {
    id: `msg-${Date.now()}`,
    role: 'user' as const,
    content: 'Carrier E4 fault',
    timestamp: new Date(),
    type: 'text' as const,
    ...overrides,
  };
}

/**
 * Fault Diagnosis Factory
 */
export function createMockFaultDiagnosis(overrides?: any) {
  return {
    fault: {
      code: 'E4',
      name: 'Low Superheat',
      severity: 'high' as const,
      description: 'Refrigerant superheat too low, indicating possible liquid slugging',
      probable_causes: [
        {
          cause: 'Low refrigerant charge',
          likelihood: 'high' as const,
          check: 'Check suction pressure and temperature',
        },
        {
          cause: 'Expansion device malfunction',
          likelihood: 'medium' as const,
          check: 'Verify TXV valve operation',
        },
      ],
      recommended_fix: {
        immediate: [
          'Check suction temperature and pressure',
          'Verify expansion device operation',
          'Check for refrigerant leaks',
        ],
        scenarios: {
          low_charge: 'Add refrigerant carefully and recheck',
          txv_stuck: 'Clean or replace expansion valve',
        },
      },
    },
    parts: [
      {
        part_name: 'Thermostatic Expansion Valve',
        part_number: 'TXV-1-8',
        manufacturer: 'Danfoss',
        suppliers: [
          {
            supplier: 'Carrier Direct',
            price: 'R3,500',
            lead_time: '2 days',
          },
        ],
      },
    ],
    forum_solutions: [
      {
        source: 'HVAC Forum',
        url: 'https://example.com/forum/e4-fix',
        title: 'How to fix E4 error on Carrier chiller',
      },
    ],
    ...overrides,
  };
}

/**
 * Portfolio Metrics Factory
 */
export function createMockPortfolioMetrics(overrides?: any) {
  return {
    total_revenue_zar: 5000000,
    gross_margin_zar: 1400000,
    avg_margin_percentage: 28,
    total_contracts: 42,
    profit_contracts: 35,
    loss_contracts: 7,
    ...overrides,
  };
}

/**
 * Alert Factory
 */
export function createMockAlert(overrides?: Partial<Alert>): Alert {
  return {
    id: 'alert-001',
    site_id: 'site-002',
    site_name: 'Sandton City',
    equipment_id: 'equipment-001',
    equipment_name: 'Primary Chiller',
    severity: 'warning',
    message: 'Equipment health declining',
    created_at: new Date().toISOString(),
    acknowledged: false,
    status: 'active',
    ...overrides,
  };
}

/**
 * Device Factory
 */
export function createMockDevice(overrides?: Partial<Device>): Device {
  return {
    id: 'device-001',
    name: 'Chiller Primary',
    device_type: 'CHILLER',
    type: 'HVAC_CHILLER',
    location: 'Basement - Plant Room',
    status: 'online',
    site_id: 'site-002',
    protocol: 'mock',
    description: 'Primary cooling system',
    points: {},
    safety_status: 'safe',
    last_communication: new Date().toISOString(),
    ...overrides,
  } as any;
}

/**
 * Device Status Factory
 */
export function createMockDeviceStatus(overrides?: Partial<DeviceStatus>): DeviceStatus {
  return {
    device_id: 'device-001',
    status: 'online',
    last_seen_seconds_ago: 5,
    last_reading_time: new Date().toISOString(),
    ...overrides,
  } as any;
}

/**
 * Device Safety Status Factory
 */
export function createMockDeviceSafetyStatus(overrides?: Partial<DeviceSafetyStatus>): DeviceSafetyStatus {
  return {
    device_id: 'device-001',
    overall_status: 'safe' as const,
    point_statuses: {},
    active_rule_count: 0,
    ...overrides,
  } as any;
}

/**
 * Equipment Factory
 */
export function createMockEquipment(overrides?: Partial<Equipment>): Equipment {
  return {
    id: 'equipment-001',
    name: 'Primary Chiller',
    type: 'CHILLER',
    site_id: 'site-002',
    health_score: 85,
    status: 'online',
    ...overrides,
  } as any;
}

/**
 * Audit Log Factory
 */
export function createMockAuditLog(overrides?: any) {
  return {
    id: `audit-${Date.now()}`,
    action: 'device_control',
    resource_type: 'device',
    resource_id: 'device-001',
    changes: { status: 'on' },
    timestamp: new Date().toISOString(),
    user_email: 'technician@example.com',
    ...overrides,
  };
}

/**
 * Predictions Response Factory (plural)
 */
export function createMockPredictions(predictions?: Partial<Prediction>[]) {
  const defaultPredictions = [
    createMockPrediction(),
  ];
  return {
    total: predictions?.length || 1,
    predictions: predictions?.map(p => createMockPrediction(p)) || defaultPredictions,
    avg_probability: 78,
    total_repair_cost_zar: 85000,
    total_potential_loss_zar: 85000,
    critical_count: 1,
    warning_count: 0,
    healthy_count: 0,
  };
}

/**
 * Dashboard Preferences Response Factory
 */
export function createMockDashboardPreferencesResponse(overrides?: any) {
  return {
    user_id: 'user-001',
    preferences: {
      visible_kpi_cards: ['uptime', 'energy', 'alerts'],
      visible_sections: ['alerts', 'predictions', 'equipment'],
      kpi_card_order: ['uptime', 'energy', 'alerts'],
      section_order: ['alerts', 'predictions', 'equipment'],
      default_energy_period: 30,
      default_energy_site_id: 'site-002',
    },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

/**
 * Loss Leader Factory
 */
export function createMockLossLeader(overrides?: any) {
  return {
    contract_id: 'contract-999',
    contract_name: 'Loss-Making Contract',
    loss_amount_zar: 125000,
    loss_percentage: 12.5,
    root_causes: ['High labor costs', 'Scope creep'],
    ...overrides,
  };
}

/**
 * Module Context Factory - Creates mock ModuleContext for testing module-dependent components
 *
 * Provides:
 * - Default state with all modules disabled
 * - Async methods for module activation/deactivation
 * - Mock API responses
 */
export function createMockModuleContext(overrides?: Partial<ModuleContextValue>): ModuleContextValue {
  return {
    siteId: 'test-site',
    siteName: 'Test Site',
    activeModules: [],
    availableModules: [
      { module_type: 'hvac', name: 'HVAC', description: 'HVAC system', integrates_with: [] },
      { module_type: 'energy', name: 'Energy', description: 'Energy management', integrates_with: [] },
      { module_type: 'security', name: 'Security', description: 'Security systems', integrates_with: [] },
      { module_type: 'lighting', name: 'Lighting', description: 'Lighting control', integrates_with: [] },
      { module_type: 'solar', name: 'Solar', description: 'Solar management', integrates_with: [] },
      { module_type: 'water', name: 'Water', description: 'Water management', integrates_with: [] },
      { module_type: 'fire', name: 'Fire', description: 'Fire safety', integrates_with: [] },
      { module_type: 'digital_twin', name: 'Digital Twin', description: 'Building visualization', integrates_with: [] },
    ],
    recommendations: [],
    integrationSummary: null,
    loading: false,
    error: null,
    setSite: async () => {},
    activateModule: async () => {},
    deactivateModule: async () => {},
    isMandatory: () => false,
    isModuleActive: () => false,
    addRecommendation: () => {},
    acknowledgeRecommendation: async () => {},
    resolveRecommendation: async () => {},
    refreshIntegration: async () => {},
    refreshRecommendations: async () => {},
    getActiveIntegrations: () => [],
    canIntegrateWith: () => [],
    ...overrides,
  };
}

/**
 * Batch Response Factory - Creates mock batch API responses for batch aggregator tests
 *
 * Generates device responses for batch endpoints (/api/devices/batch/safety, etc.)
 * Each device ID maps to a mock item of type T with id and appropriate fields
 *
 * @param endpoint - Batch endpoint name (e.g., 'safety', 'readings', 'conditions')
 * @param items - Object mapping device IDs to item data, or undefined for default items
 * @returns Record<string, T> suitable for mocking batch API responses
 *
 * @example
 * // Mock safety status batch response
 * const response = createBatchResponse('safety', {
 *   'device-1': { status: 'safe' },
 *   'device-2': { status: 'warning' }
 * });
 *
 * // Mock with default items
 * const response = createBatchResponse('readings', {
 *   'device-1': undefined,  // Will get default { id: 'device-1', value: 'mock' }
 *   'device-2': undefined
 * });
 */
export function createBatchResponse<T extends { id: string }>(
  endpoint: string,
  items?: Record<string, Partial<T> | undefined>,
): Record<string, T> {
  const response: Record<string, T> = {};

  if (items) {
    for (const [id, itemData] of Object.entries(items)) {
      response[id] = {
        id,
        ...(itemData || { value: `mock-${id}` }),
      } as T;
    }
  }

  return response;
}

/**
 * Work Order Factory
 */
export function createMockWorkOrder(overrides?: any) {
  return {
    id: 'wo-001',
    code: 'WO-2026-001',
    work_type: 'maintenance',
    status: 'scheduled',
    priority: 'medium',
    equipment_id: 'equipment-001',
    assigned_to: 'technician@example.com',
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

/**
 * Building Factory
 */
export function createMockBuilding(overrides?: any) {
  return {
    id: 'building-001',
    code: 'S002-B1',
    name: 'Test Building',
    type: 'office',
    site_id: 'site-002',
    floors: 3,
    equipment_count: 42,
    ...overrides,
  };
}

/**
 * Solar Data Factory (for solar dashboard hooks)
 */
export function createMockSolarData(overrides?: any) {
  return {
    site_id: 'site-002',
    current_generation_kw: 150,
    peak_generation_kw: 250,
    generation_percent: 60,
    bess_soc_percent: 65,
    bess_discharge_available_kw: 100,
    forecast_24h: [
      { hour: 0, generation_kw: 0 },
      { hour: 6, generation_kw: 50 },
      { hour: 12, generation_kw: 250 },
      { hour: 18, generation_kw: 100 },
    ],
    ...overrides,
  };
}

/**
 * BESS Status Factory
 */
export function createMockBESSStatus(overrides?: any) {
  return {
    site_id: 'site-002',
    soc_percent: 65,
    discharge_power_kw: 50,
    charge_power_kw: 0,
    status: 'idle',
    health_percent: 95,
    ...overrides,
  };
}

/**
 * Peak Demand Status Factory
 */
export function createMockPeakDemandStatus(overrides?: any) {
  return {
    site_id: 'site-002',
    current_demand_kw: 5500,
    nmd_limit_kva: 6000,
    headroom_kw: 500,
    headroom_percent: 8.3,
    headroom_level: 'critical',
    active_modules: ['solar', 'hvac'],
    available_reductions: {
      solar: { max_reduction_kw: 200, method: 'bess_discharge' },
      hvac: { max_reduction_kw: 50, method: 'setpoint_increase' },
    },
    ...overrides,
  };
}

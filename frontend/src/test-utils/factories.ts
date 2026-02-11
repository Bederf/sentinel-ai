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
    },
    savings: {
      energy_savings_percent: 18,
      comfort_extension_minutes: 75,
      fuel_savings_percent: 12,
      total_savings_zar: 4250,
    },
    ...overrides,
  };
}

/**
 * Optimization Status Factory
 */
export function createMockOptimizationStatus(overrides?: Partial<OptimizationStatusResponse>): OptimizationStatusResponse {
  return {
    site_id: 'site-002',
    current_status: 'active',
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
  };
}

/**
 * Dashboard Stats Factory
 */
export function createMockDashboardStats(overrides?: Partial<DashboardStats>): DashboardStats {
  return {
    total_equipment: 156,
    uptime_percent: 97.2,
    active_alerts: 3,
    critical_alerts: 1,
    ...overrides,
  };
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
    confidence: 'HIGH',
    financial_impact: {
      potential_loss_zar: 85000,
      downtime_hours: 24,
    },
    ...overrides,
  };
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
    date: new Date().toISOString().split('T')[0],
    consumption_kwh: 2450,
    cost_zar: 3675,
    peak_kw: 450,
    avg_kw: 102,
    ...overrides,
  };
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
    code: 'SCT',
    type: 'office',
    status: 'normal',
    location: 'Johannesburg, South Africa',
    equipment_count: 175,
    alert_count: 3,
    ...overrides,
  };
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
    location: 'Basement - Plant Room',
    status: 'normal',
    ...overrides,
  };
}

/**
 * Device Status Factory
 */
export function createMockDeviceStatus(overrides?: Partial<DeviceStatus>): DeviceStatus {
  return {
    device_id: 'device-001',
    is_responsive: true,
    last_seen_seconds_ago: 5,
    last_reading_time: new Date().toISOString(),
    is_critical: false,
    ...overrides,
  };
}

/**
 * Device Safety Status Factory
 */
export function createMockDeviceSafetyStatus(overrides?: Partial<DeviceSafetyStatus>): DeviceSafetyStatus {
  return {
    device_id: 'device-001',
    is_safe: true,
    safety_status: 'healthy',
    temp_c: 22.5,
    setpoint_c: 23,
    pressure_bar: 4.2,
    ...overrides,
  };
}

/**
 * Equipment Factory
 */
export function createMockEquipment(overrides?: Partial<Equipment>): Equipment {
  return {
    id: 'equipment-001',
    code: 'S002-CHILLER-B1-001',
    name: 'Primary Chiller',
    equipment_type: 'CHILLER',
    health_score: 85,
    status: 'normal',
    ...overrides,
  };
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

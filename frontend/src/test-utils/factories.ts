/**
 * Test data factories for creating mock objects
 */

import type {
  Site,
  Device,
  Alert,
  Prediction,
  Equipment,
  AuditLogEntryResponse,
  DashboardStats,
  OptimizationStatusResponse,
  DeviceStatus,
  DeviceSafetyStatus,
} from '@/lib/api';

/**
 * Create a mock Site
 */
export function createMockSite(overrides?: Partial<Site>): Site {
  return {
    id: 'site-001',
    name: 'Test Site',
    location: 'Test Location',
    region: 'Gauteng',
    type: 'office',
    equipment_count: 10,
    alert_count: 2,
    status: 'normal',
    ...overrides,
  };
}

/**
 * Create a mock Device
 */
export function createMockDevice(overrides?: Partial<Device>): Device {
  return {
    id: 'device-001',
    name: 'Test Device',
    device_type: 'HVAC_CHILLER',
    type: 'HVAC_CHILLER',
    protocol: 'mock',
    location: 'Test Location',
    site_id: 'site-001',
    description: 'Test device description',
    points: {
      setpoint: {
        name: 'setpoint',
        point_type: 'analog_output',
        description: 'Temperature setpoint',
        unit: '°C',
        min_value: 16,
        max_value: 28,
        default_value: 22,
        writable: true,
        priority: 8,
      },
    },
    status: 'online',
    safety_status: 'safe',
    ...overrides,
  };
}

/**
 * Create a mock Alert
 */
export function createMockAlert(overrides?: Partial<Alert>): Alert {
  return {
    id: 'alert-001',
    site_id: 'site-001',
    site_name: 'Test Site',
    equipment_id: 'equipment-001',
    equipment_name: 'Test Equipment',
    severity: 'warning',
    message: 'Test alert message',
    created_at: new Date().toISOString(),
    acknowledged: false,
    ...overrides,
  };
}

/**
 * Create a mock Prediction
 */
export function createMockPrediction(overrides?: Partial<Prediction>): Prediction {
  return {
    id: 'prediction-001',
    site_id: 'site-001',
    site_name: 'Test Site',
    equipment_id: 'equipment-001',
    equipment_name: 'Test Equipment',
    equipment_type: 'chiller',
    prediction_type: 'bearing_failure',
    probability_percent: 85,
    confidence: 'high' as const,
    predicted_failure_date: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
    timeframe_days: 30,
    severity: 'critical' as const,
    evidence: {
      repeat_work_orders: 2,
      repeat_period_months: 6,
      alarm_frequency: { vibration: 15 },
      asset_age_years: 21,
      expected_life_years: 25,
      technician_notes: ['Vibration trending upward'],
      latest_reading: {
        parameter: 'vibration',
        value: 4.5,
        baseline: 2.0,
        threshold: 3.0,
        trend: 'increasing',
      },
    },
    contributing_factors: [
      { factor: 'Vibration trending upward', weight: 0.8, description: 'Vibration levels increasing' },
      { factor: 'Oil analysis shows contamination', weight: 0.7, description: 'Contamination detected in oil sample' },
    ],
    similar_failures: [],
    financial_impact: {
      repair_cost_zar: 45000,
      replacement_cost_zar: 180000,
      downtime_cost_per_hour_zar: 5000,
      estimated_repair_hours: 8,
      potential_loss_zar: 135000,
    },
    recommended_action: 'Schedule preventive maintenance',
    parts_required: ['bearings', 'seals'],
    urgency: 'high',
    ...overrides,
  };
}

/**
 * Create a mock Equipment
 */
export function createMockEquipment(overrides?: Partial<Equipment>): Equipment {
  return {
    id: 'equipment-001',
    name: 'Test Equipment',
    type: 'chiller',
    site_id: 'site-001',
    site_name: 'Test Site',
    status: 'online',
    last_reading: {
      timestamp: new Date().toISOString(),
      value: 22.5,
      unit: '°C',
    },
    ...overrides,
  };
}

/**
 * Create a mock AuditLogEntryResponse
 */
export function createMockAuditLog(overrides?: Partial<AuditLogEntryResponse>): AuditLogEntryResponse {
  return {
    id: 'audit-001',
    timestamp: new Date().toISOString(),
    action: 'DEVICE_CONTROL',
    user: 'operator-1',
    device_id: 'device-001',
    point_name: 'setpoint',
    old_value: 21.5,
    new_value: 22.0,
    result: 'SUCCESS',
    safety_validation: {
      rules_checked: ['temperature_range'],
      passed_rules: ['temperature_range'],
    },
    metadata: {},
    ...overrides,
  };
}

/**
 * Create a mock DashboardStats
 */
export function createMockDashboardStats(overrides?: Partial<DashboardStats>): DashboardStats {
  return {
    total_sites: 10,
    total_equipment: 50,
    total_sensors: 200,
    active_alerts: 5,
    critical_alerts: 2,
    pending_anomalies: 3,
    uptime_percent: 99.5,
    ...overrides,
  };
}

/**
 * Create a mock OptimizationStatusResponse
 */
export function createMockOptimizationStatus(overrides?: Partial<OptimizationStatusResponse>): OptimizationStatusResponse {
  return {
    site_id: 'site-001',
    optimization_enabled: false,
    optimization_status: 'unknown',
    optimization_settings: {
      mode: 'supervised',
      last_analysis: null,
      analysis_interval_minutes: 60,
    },
    last_recommendation: null,
    last_optimization: null,
    optimization_history: [],
    ...overrides,
  };
}

/**
 * Create a mock DeviceStatus
 */
export function createMockDeviceStatus(overrides?: Partial<DeviceStatus>): DeviceStatus {
  return {
    device_id: 'device-001',
    device_name: 'Test Device',
    status: 'online',
    last_seen: new Date().toISOString(),
    protocol: 'mock',
    ...overrides,
  };
}

/**
 * Create a mock DeviceSafetyStatus
 */
export function createMockDeviceSafetyStatus(overrides?: Partial<DeviceSafetyStatus>): DeviceSafetyStatus {
  return {
    device_id: 'device-001',
    device_name: 'Test Device',
    overall_status: 'safe',
    point_statuses: {},
    active_rule_count: 0,
    last_check: new Date().toISOString(),
    ...overrides,
  };
}

/**
 * Create multiple mock objects
 */
export function createMockSites(count: number): Site[] {
  return Array.from({ length: count }, (_, i) =>
    createMockSite({
      id: `site-${String(i + 1).padStart(3, '0')}`,
      name: `Test Site ${i + 1}`,
    })
  );
}

export function createMockDevices(count: number): Device[] {
  return Array.from({ length: count }, (_, i) =>
    createMockDevice({
      id: `device-${String(i + 1).padStart(3, '0')}`,
      name: `Test Device ${i + 1}`,
    })
  );
}

export function createMockAlerts(count: number): Alert[] {
  return Array.from({ length: count }, (_, i) =>
    createMockAlert({
      id: `alert-${String(i + 1).padStart(3, '0')}`,
      severity: i % 3 === 0 ? 'critical' : i % 3 === 1 ? 'warning' : 'info',
    })
  );
}

export function createMockPredictions(count: number): Prediction[] {
  const confidenceLevels: Array<'high' | 'medium' | 'low'> = ['high', 'medium', 'low'];
  return Array.from({ length: count }, (_, i) =>
    createMockPrediction({
      id: `prediction-${String(i + 1).padStart(3, '0')}`,
      confidence: confidenceLevels[i % confidenceLevels.length],
    })
  );
}

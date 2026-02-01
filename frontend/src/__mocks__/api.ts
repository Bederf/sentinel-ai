/**
 * Mock API client for testing
 * Provides pre-configured responses that can be overridden per test
 */

import { vi } from 'vitest';
import type {
  Site,
  Device,
  Alert,
  Prediction,
  Equipment,
  DashboardStats,
  OptimizationStatusResponse,
  DeviceStatus,
  DeviceSafetyStatus,
  DeviceControlResponse,
  HealthResponse,
  EnergyResponse,
} from '../lib/api';
import {
  createMockSite,
  createMockDevice,
  createMockAlert,
  createMockPrediction,
  createMockEquipment,
  createMockAuditLog,
  createMockDashboardStats,
  createMockOptimizationStatus,
  createMockDeviceStatus,
  createMockDeviceSafetyStatus,
} from '../test-utils/factories';

/**
 * Mock API client with default responses
 */
const createMockApi = () => {
  const mockApi = {
    health: vi.fn().mockResolvedValue({
      status: 'healthy',
      version: '1.0.0',
    } satisfies HealthResponse),

    getSites: vi.fn().mockResolvedValue([
      createMockSite({ id: 'site-001', name: 'Test Site 1' }),
      createMockSite({ id: 'site-002', name: 'Test Site 2' }),
    ] satisfies Site[]),

    getSite: vi.fn().mockResolvedValue(
      createMockSite() satisfies Site
    ),

    getStats: vi.fn().mockResolvedValue(
      createMockDashboardStats() satisfies DashboardStats
    ),

    getAlerts: vi.fn().mockResolvedValue([
      createMockAlert({ id: 'alert-001', severity: 'warning' }),
      createMockAlert({ id: 'alert-002', severity: 'critical' }),
    ] satisfies Alert[]),

    getAnomalies: vi.fn().mockResolvedValue([] satisfies Prediction[]),

    getEquipment: vi.fn().mockResolvedValue([
      createMockEquipment({ id: 'equipment-001' }),
    ] satisfies Equipment[]),

    getEnergy: vi.fn().mockResolvedValue({
      days: 30,
      site_id: null,
      data: [],
    } as EnergyResponse),

    getPredictions: vi.fn().mockResolvedValue({
      total: 1,
      avg_probability: 0.85,
      total_repair_cost_zar: 45000,
      total_potential_loss_zar: 180000,
      potential_savings_zar: 135000,
      by_severity: { critical: 1 },
      by_equipment_type: { chiller: 1 },
      predictions: [createMockPrediction()],
    }),

    getPrediction: vi.fn().mockResolvedValue(
      createMockPrediction() satisfies Prediction
    ),

    streamChat: vi.fn().mockImplementation(async function* () {
      yield { type: 'text', content: 'Test response' };
    }),

    // Device API methods
    getDevices: vi.fn().mockResolvedValue([
      createMockDevice({ id: 'device-001' }),
    ] satisfies Device[]),

    getDevice: vi.fn().mockResolvedValue(
      createMockDevice() satisfies Device
    ),

    getDevicePoints: vi.fn().mockResolvedValue({
      setpoint: {
        name: 'setpoint',
        point_type: 'analog_output',
        description: 'Temperature setpoint',
        unit: '°C',
        default_value: 22,
        writable: true,
      },
    } satisfies Record<string, any>),

    readDevicePoint: vi.fn().mockResolvedValue({
      device_id: 'device-001',
      point_name: 'setpoint',
      value: 22.0,
      unit: '°C',
      timestamp: new Date().toISOString(),
      quality: 'good',
    }),

    controlDevice: vi.fn().mockResolvedValue({
      success: true,
      message: 'Control command executed successfully',
      device_id: 'device-001',
      point: 'setpoint',
      value: 22.0,
      priority: 8,
    } satisfies DeviceControlResponse),

    getDeviceStatus: vi.fn().mockResolvedValue(
      createMockDeviceStatus() satisfies DeviceStatus
    ),

    getSiteDevices: vi.fn().mockResolvedValue([
      createMockDevice({ id: 'device-001' }),
    ] satisfies Device[]),

    // Safety API methods
    getDeviceFullSafetyStatus: vi.fn().mockResolvedValue(
      createMockDeviceSafetyStatus() satisfies DeviceSafetyStatus
    ),

    validateControlAction: vi.fn().mockResolvedValue({
      is_safe: true,
      result: 'ALLOW',
      passed_rules: ['temperature_range'],
      failed_rules: [],
      warnings: [],
    }),

    // Audit API methods
    getAuditLogs: vi.fn().mockResolvedValue({
      entries: [createMockAuditLog()],
      total_count: 1,
      page: 1,
      page_size: 50,
      has_more: false,
    }),

    getAuditLog: vi.fn().mockResolvedValue(createMockAuditLog()),

    getAuditStats: vi.fn().mockResolvedValue({
      total_entries: 100,
      by_action: { DEVICE_CONTROL: 50 },
      by_result: { SUCCESS: 45, BLOCKED: 5 },
      by_user: { 'operator-1': 30 },
      recent_activity_count: 10,
      last_updated: new Date().toISOString(),
    }),

    // Optimization API methods
    getEskomStatus: vi.fn().mockResolvedValue({
      current_stage: 0,
      updated_at: new Date().toISOString(),
      next_stages: [],
      area_schedules: {},
    }),

    getSiteEskomStatus: vi.fn().mockResolvedValue({
      site_id: 'site-001',
      site_name: 'Test Site',
      current_stage: 0,
      schedules: [],
      next_outage: null,
    }),

    getThermalRunway: vi.fn().mockResolvedValue({
      site_id: 'site-001',
      site_name: 'Test Site',
      current_temperature: 22.0,
      comfort_limit: 26.0,
      thermal_runway_minutes: 52,
      comfort_breach_time: null,
      calculation_method: 'simplified',
      building_params: {
        thermal_mass: 1000,
        insulation_factor: 0.8,
        internal_heat_gain: 50,
      },
      weather_forecast: {
        outside_temp: 28.0,
        solar_load: 200,
        humidity: 60,
      },
    }),

    getOptimizationScenarios: vi.fn().mockResolvedValue([]),

    getOptimizationScenario: vi.fn().mockResolvedValue({
      scenario_id: 'scenario-001',
      site_id: 'site-001',
      site_name: 'Test Site',
      description: 'Test scenario',
      current_conditions: {},
      load_shedding: {},
      thermal_runway: {},
      pre_cooling_schedule: {},
      savings: {},
    }),

    getOptimizationStatus: vi.fn().mockResolvedValue(
      createMockOptimizationStatus() as OptimizationStatusResponse
    ),

    analyzeOptimization: vi.fn().mockResolvedValue({
      recommendation: {
        id: 'rec-001',
        site_id: 'site-001',
        timestamp: new Date().toISOString(),
        recommendations: [],
        projected_savings: {
          energy_kwh: 100,
          cost_zar_per_hour: 50,
          percentage_improvement: 12,
        },
        confidence: 85,
        reasoning: 'Test reasoning',
      },
      validation: {},
    }),

    approveOptimization: vi.fn().mockResolvedValue({
      success: true,
      results: [],
    }),

    toggleOptimization: vi.fn().mockResolvedValue(
      createMockOptimizationStatus({ optimization_enabled: true }) as OptimizationStatusResponse
    ),

    getLatestRecommendation: vi.fn().mockResolvedValue(null),

    rejectOptimization: vi.fn().mockResolvedValue({
      success: true,
      message: 'Recommendation rejected',
    }),

    deferOptimization: vi.fn().mockResolvedValue({
      success: true,
      message: 'Recommendation deferred',
      deferUntil: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
    }),

    // Health thresholds API methods
    getHealthThresholds: vi.fn().mockResolvedValue({
      warning: 70,
      critical: 40,
    }),

    updateHealthThresholds: vi.fn().mockResolvedValue({
      warning: 70,
      critical: 40,
    }),

    // Device safety status (simple version)
    getDeviceSafetyStatus: vi.fn().mockResolvedValue({
      overall_status: 'safe' as const,
    }),
  };

  return mockApi;
};

// Create default mock API instance
const mockApi = createMockApi();

/**
 * Reset all mocks to default state
 */
export function resetMockApi() {
  Object.assign(mockApi, createMockApi());
}

/**
 * Get the mock API instance
 */
export function getMockApi() {
  return mockApi;
}

export default mockApi;

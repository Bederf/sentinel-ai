/**
 * Solar & BESS API Module
 *
 * Exposes dashboard-specific API calls for solar monitoring:
 * - System overview (power, BESS, yield)
 * - Performance metrics (efficiency, strings, capacity factor)
 * - Grid compliance (frequency, load shedding, violations)
 * - BESS status (charge, temperature, health, cycles)
 */

import { authorizedFetch } from './client';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// Helper to normalize site IDs
function normalizeSiteId(siteId: string): string {
  // Legacy alias normalization removed — site IDs are resolved from registered buildings
  return siteId;
}

// ============= Type Definitions =============

/**
 * Live System Data - Real-time power generation and BESS status
 * Stale time: 10s (power data frequently changes)
 */
export interface LiveSystemData {
  site_id: string;
  timestamp: string;
  current_generation_kw: number;
  rated_capacity_kwp: number;
  generation_percent: number;
  daily_yield_kwh: number;
  peak_power_kw: number;
  average_power_kw: number;
  energy_exported_kwh: number;
  bess_soc_percent: number;
  bess_discharge_hours: number;
  inverter_operating: number;
  inverter_offline: number;
  inverter_faulted: number;
}

/**
 * Performance Summary - Efficiency and health metrics
 * Stale time: 30s (calculations stable over longer periods)
 */
export interface PerformanceSummary {
  site_id: string;
  timestamp: string;
  system_efficiency_percent: number;
  peer_average_efficiency_percent: number;
  efficiency_trend: 'improving' | 'stable' | 'declining';
  string_health: Array<{
    string_id: string;
    health_percent: number;
  }>;
  capacity_factor_24h: number;
  capacity_factor_7d: number;
  capacity_factor_30d: number;
  soiling_loss_percent: number;
  soiling_annual_percent: number;
  soiling_trend: 'improving' | 'stable' | 'declining';
  degradation_yearly_percent: number;
  degradation_annual_percent: number;
  warranty_status: 'active' | 'expired' | 'limited';
}

/**
 * Grid Compliance Status - Grid parameters and compliance checks
 * Stale time: 5s (grid frequency changes rapidly)
 */
export interface GridComplianceStatus {
  site_id: string;
  timestamp: string;
  grid_frequency_hz: number;
  frequency_safe: boolean;
  frequency_band_status: 'green' | 'yellow' | 'red';
  frequency_trend_1h: number[];
  load_shedding_stage: number;
  load_shedding_active: boolean;
  violations_count: number;
  violations: Array<{
    timestamp: string;
    parameter: string;
    status: string;
  }>;
  auto_response_curtailment_percent: number;
  auto_response_standby: boolean;
  auto_response_droop: number;
  compliance_badge: 'compliant' | 'non_compliant';
  last_check_time: string;
}

/**
 * BESS Status Data - Battery system health and performance
 * Stale time: 15s (battery data moderately dynamic)
 */
export interface BESSStatusData {
  site_id: string;
  timestamp: string;
  charge_power_kw: number;
  discharge_power_kw: number;
  power_direction: 'charging' | 'discharging' | 'idle';
  current_power_kw: number;
  battery_charge_percent: number;
  battery_curve_24h: Array<{
    timestamp: string;
    charge_percent: number;
  }>;
  temperature_c: number;
  temperature_alert: boolean;
  state_of_health_percent: number;
  soh_trend: 'declining' | 'stable';
  cycle_count: number;
  estimated_remaining_years: number;
  efficiency_roundtrip_percent: number;
  efficiency_rated_percent: number;
  energy_reserve_kwh: number;
  suitable_for_hours: number;
  thermal_limit_c: number;
}

// ============= API Functions =============

/**
 * Fetch live system data (power, BESS, yield, inverters)
 * GET /api/solar/sites/{id}/overview
 *
 * @param siteId - Solar site identifier
 * @returns LiveSystemData with real-time metrics
 */
export async function fetchLiveSystemData(siteId: string): Promise<LiveSystemData> {
  const normalizedId = normalizeSiteId(siteId);
  const response = await authorizedFetch(
    `${API_BASE_URL}/api/solar/sites/${normalizedId}/overview`,
    { method: 'GET' }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch system overview: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch performance metrics (efficiency, string health, soiling, degradation)
 * GET /api/solar/performance/{id}/summary
 *
 * @param siteId - Solar site identifier
 * @returns PerformanceSummary with performance indicators
 */
export async function fetchPerformanceSummary(siteId: string): Promise<PerformanceSummary> {
  const normalizedId = normalizeSiteId(siteId);
  const response = await authorizedFetch(
    `${API_BASE_URL}/api/solar/performance/${normalizedId}/summary`,
    { method: 'GET' }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch performance summary: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch grid compliance status (frequency, load shedding, violations)
 * GET /api/solar/grid/status/{id}
 *
 * @param siteId - Solar site identifier
 * @returns GridComplianceStatus with grid parameters and compliance info
 */
export async function fetchGridComplianceStatus(siteId: string): Promise<GridComplianceStatus> {
  const normalizedId = normalizeSiteId(siteId);
  const response = await authorizedFetch(
    `${API_BASE_URL}/api/solar/grid/status/${normalizedId}`,
    { method: 'GET' }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch grid compliance status: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch BESS status (charge, temperature, health, cycles)
 * GET /api/solar/batteries/{id}/status
 *
 * @param siteId - Solar site identifier
 * @returns BESSStatusData with battery system metrics
 */
export async function fetchBESSStatusData(siteId: string): Promise<BESSStatusData> {
  const normalizedId = normalizeSiteId(siteId);
  const response = await authorizedFetch(
    `${API_BASE_URL}/api/solar/batteries/${normalizedId}/status`,
    { method: 'GET' }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch BESS status: ${response.statusText}`);
  }

  return response.json();
}

// ============= Exports for use in hooks =============

export {
  normalizeSiteId,
};

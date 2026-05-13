/**
 * Energy API Client
 *
 * Handles fetching energy comparison, actual, and prediction data
 */

import { authorizedFetch } from './client';

export interface EnergyMetrics {
  total_kwh: number
  total_cost_zar: number
  carbon_kg: number
  hvac_kwh: number
  hvac_percent: number
  lighting_kwh: number
  lighting_percent: number
  power_kwh: number
  power_percent: number
  timestamp: string
}

export interface ComparisonSummary {
  actual: EnergyMetrics
  sentinel: EnergyMetrics
  daily_savings_zar: number
  daily_savings_percent: number
  progress_to_target_percent: number
  ai_confidence_percent: number
}

export interface EnergyActual {
  site_id: string
  period_days: number
  metrics: EnergyMetrics[]
  period_start: string
  period_end: string
}

export interface EnergyPrediction {
  site_id: string
  scenario: 'sentinel_optimized' | 'standard_ems' | 'baseline'
  period_days: number
  metrics: EnergyMetrics[]
  period_start: string
  period_end: string
  model_confidence: number
}

const API_BASE = '/api'

/**
 * Fetch energy comparison summary for a site
 * Shows actual vs SENTINEL AI predictions side-by-side
 */
export async function fetchEnergyComparisonSummary(
  siteId: string,
): Promise<ComparisonSummary> {
  const response = await authorizedFetch(
    `${API_BASE}/energy/comparison-summary?site_id=${encodeURIComponent(siteId)}`,
  )
  if (!response.ok) {
    throw new Error(`Failed to fetch energy comparison: ${response.statusText}`)
  }
  return response.json()
}

/**
 * Fetch actual energy data for a period
 * Retrieved from device telemetry and real-time meters
 */
export async function fetchEnergyActual(
  siteId: string,
  days: number = 30,
): Promise<EnergyActual> {
  const response = await fetch(
    `${API_BASE}/energy/actual?site_id=${encodeURIComponent(siteId)}&days=${days}`,
  )
  if (!response.ok) {
    throw new Error(`Failed to fetch actual energy: ${response.statusText}`)
  }
  return response.json()
}

/**
 * Fetch SENTINEL AI energy prediction
 * ML model-based forecast based on historical patterns and current conditions
 */
export async function fetchEnergyPrediction(
  siteId: string,
  scenario: 'sentinel_optimized' | 'standard_ems' = 'sentinel_optimized',
  days: number = 30,
): Promise<EnergyPrediction> {
  const response = await fetch(
    `${API_BASE}/energy/prediction?site_id=${encodeURIComponent(siteId)}&scenario=${scenario}&days=${days}`,
  )
  if (!response.ok) {
    throw new Error(`Failed to fetch energy prediction: ${response.statusText}`)
  }
  return response.json()
}

/**
 * Fetch both actual and prediction data for comparison
 * Useful when you need both datasets for analysis
 */
export async function fetchEnergyComparison(
  siteId: string,
  days: number = 30,
): Promise<{
  actual: EnergyActual
  sentinel: EnergyPrediction
}> {
  const [actual, sentinel] = await Promise.all([
    fetchEnergyActual(siteId, days),
    fetchEnergyPrediction(siteId, 'sentinel_optimized', days),
  ])
  return { actual, sentinel }
}

/**
 * Calculate percentage savings between actual and predicted
 */
export function calculateSavingsPercent(actual: number, predicted: number): number {
  if (actual === 0) return 0
  return ((actual - predicted) / actual) * 100
}

/**
 * Calculate carbon offset (kg CO₂)
 * Based on energy reduction and grid carbon intensity (0.35 kg CO₂/kWh in SA)
 */
export function calculateCarbonOffset(energyReductionKwh: number): number {
  const SA_CARBON_INTENSITY = 0.35 // kg CO₂/kWh
  return energyReductionKwh * SA_CARBON_INTENSITY
}

/**
 * Format energy metrics for display
 */
export function formatEnergyMetrics(metrics: EnergyMetrics) {
  return {
    energy: `${metrics.total_kwh.toLocaleString()} kWh`,
    cost: `R${metrics.total_cost_zar.toLocaleString()}`,
    carbon: `${metrics.carbon_kg.toLocaleString()} kg CO₂`,
    hvac: {
      kwh: metrics.hvac_kwh,
      percent: metrics.hvac_percent,
    },
    lighting: {
      kwh: metrics.lighting_kwh,
      percent: metrics.lighting_percent,
    },
    power: {
      kwh: metrics.power_kwh,
      percent: metrics.power_percent,
    },
  }
}

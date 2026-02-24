/**
 * Solar Annual Simulation API Client
 * Handles 365-day simulation requests and result retrieval
 */

import { authorizedFetch } from './client';

export interface MonthSummary {
  month: number
  month_name: string
  season: string
  solar_generated_kwh: number
  bess_charged_kwh: number
  bess_discharged_kwh: number
  grid_import_kwh: number
  grid_export_kwh: number
  building_load_kwh: number
  self_consumption_kwh: number
  peak_demand_kw: number
  peak_hour_utc: string | null
  energy_cost_zar: number
  demand_cost_zar: number
  total_cost_standard_ems_zar: number
  total_cost_sentinel_ai_zar: number
  savings_zar: number
  savings_pct: number
  learning_factor: number
  avg_bess_soc_pct: number
  capacity_factor_pct: number
}

export interface SeasonSummary {
  season: string
  start_month: number
  end_month: number
  months: MonthSummary[]
  total_solar_kwh: number
  total_grid_import_kwh: number
  total_grid_export_kwh: number
  total_cost_zar: number
  avg_savings_pct: number
}

export interface LearningCurvePoint {
  month: number
  month_name: string
  savings_pct: number
  learning_factor: number
}

export interface AnnualSummary {
  site_id: string
  year: number
  scenario: string
  monthly_data: MonthSummary[]
  seasonal_data: SeasonSummary[]
  total_solar_kwh: number
  total_grid_import_kwh: number
  total_grid_export_kwh: number
  total_building_load_kwh: number
  total_self_consumption_kwh: number
  total_cost_standard_ems_zar: number
  total_cost_sentinel_ai_zar: number
  annual_savings_zar: number
  annual_savings_pct: number
  capacity_factor_pct: number
  self_consumption_pct: number
  avg_bess_cycles_per_day: number
  peak_demand_reduction_kw: number
  learning_curve: LearningCurvePoint[]
  simulation_started_at: string | null
  simulation_completed_at: string | null
  simulation_duration_seconds: number
}

export interface SimulationStatus {
  task_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress_pct: number
  days_completed: number
  estimated_time_remaining_seconds: number
  started_at: string
  error?: string
}

/**
 * Fetch cached annual summary results
 * Returns 404 if not cached - client should call startAnnualSimulation
 */
export async function fetchAnnualSummary(
  siteId: string,
  year?: number
): Promise<AnnualSummary> {
  const url = new URL(`${import.meta.env.VITE_API_URL}/api/solar/annual/${siteId}/summary`)
  if (year) {
    url.searchParams.set('year', year.toString())
  }

  const response = await authorizedFetch(url.toString(), undefined, true)

  if (!response.ok) {
    const error: any = new Error(`Failed to fetch annual summary (${response.status})`)
    error.status = response.status
    throw error
  }

  return response.json()
}

/**
 * Start 365-day simulation in background
 * Returns task_id for polling progress
 */
export async function startAnnualSimulation(
  siteId: string,
  scenario: string = 'sentinel_annual',
  durationMinutes: number = 240.0
): Promise<{ task_id: string; site_id: string; scenario: string }> {
  const response = await authorizedFetch(
    `/api/solar/annual/${siteId}/simulate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario, duration_minutes: durationMinutes }),
    }
  )

  if (!response.ok) {
    throw new Error(`Failed to start simulation: ${response.statusText}`)
  }

  return response.json()
}

/**
 * Poll simulation progress
 */
export async function pollSimulationStatus(
  siteId: string,
  taskId: string
): Promise<SimulationStatus> {
  const response = await authorizedFetch(
    `/api/solar/annual/${siteId}/status/${taskId}`
  )

  if (!response.ok) {
    throw new Error(`Failed to fetch simulation status: ${response.statusText}`)
  }

  return response.json()
}

/**
 * Utility: Format ZAR currency
 */
export function formatZAR(value: number): string {
  if (value >= 1_000_000) {
    return `R${(value / 1_000_000).toFixed(1)}M`
  }
  if (value >= 1_000) {
    return `R${(value / 1_000).toFixed(1)}k`
  }
  return `R${value.toFixed(0)}`
}

/**
 * Utility: Format energy (kWh)
 */
export function formatKWh(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M kWh`
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(0)}k kWh`
  }
  return `${value.toFixed(0)} kWh`
}

/**
 * Utility: Format percentage
 */
export function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`
}

/**
 * Utility: Get learning phase label
 */
export function getLearningPhase(month: number): string {
  if (month <= 2) return 'Learning'
  if (month <= 6) return 'Optimization'
  return 'Mature'
}

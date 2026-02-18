import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'

/**
 * Real-time simulation state available to all pages.
 * Automatically polls /api/lifecycle/status/{site_id} every 3 seconds.
 */
export interface SimulationState {
  running: boolean
  paused: boolean
  simulatedHour: number           // 0-23
  simulatedTime: string           // ISO datetime string
  daysSimulated: number           // 0-365
  cycleNum: number                // Number of cycles completed
  progressPct: number             // 0-100

  // Weather & Environment
  ambientTemp: number             // °C
  isRaining: boolean
  cloudCover: number              // 0-100 (%)
  solarEfficiency: number         // 0-100 (%)
  occupancyPercent: number        // 0-100 (%)
  currentSeason: string           // 'summer' | 'autumn' | 'winter' | 'spring'

  // Energy/Load Data
  hvacLoadPercent: number         // 0-100 (%)
  totalEnergyKwh: number          // Cumulative kWh consumed
  currentHourPowerKw: number      // Current hour's power in kW

  // Metadata
  scenario: string | null
  recentEvents: Array<{
    hour: number
    type: string
    description: string
    equipment: string
  }>

  // Status flags
  lastUpdated: number             // Timestamp (ms) of last successful poll
  isLoading: boolean
  error: string | null
}

const initialState: SimulationState = {
  running: false,
  paused: false,
  simulatedHour: 0,
  simulatedTime: new Date().toISOString(),
  daysSimulated: 0,
  cycleNum: 0,
  progressPct: 0,
  ambientTemp: 22,
  isRaining: false,
  cloudCover: 0,
  solarEfficiency: 100,
  occupancyPercent: 0,
  currentSeason: 'spring',
  hvacLoadPercent: 0,
  totalEnergyKwh: 0,
  currentHourPowerKw: 0,
  scenario: null,
  recentEvents: [],
  lastUpdated: 0,
  isLoading: false,
  error: null,
}

type SimulationContextType = {
  state: SimulationState
  refresh: () => Promise<void>
}

const SimulationContext = createContext<SimulationContextType | undefined>(undefined)

interface SimulationProviderProps {
  children: React.ReactNode
  siteId?: string
}

export function SimulationProvider({ children, siteId = 'site-002' }: SimulationProviderProps) {
  const [state, setState] = useState<SimulationState>(initialState)

  const refresh = useCallback(async () => {
    setState(prev => ({ ...prev, isLoading: true }))
    try {
      const response = await fetch(`/api/lifecycle/status/${siteId}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const data = await response.json()

      setState(prev => ({
        ...prev,
        running: data.running ?? prev.running,
        paused: data.paused ?? prev.paused,
        simulatedHour: data.simulated_hour ?? prev.simulatedHour,
        simulatedTime: data.simulated_time ? new Date(data.simulated_time).toISOString() : prev.simulatedTime,
        daysSimulated: data.days_simulated ?? prev.daysSimulated,
        cycleNum: Math.floor((data.days_simulated ?? 0) / 365),
        progressPct: data.progress_pct ?? data.progress_percent ?? prev.progressPct,
        ambientTemp: data.ambient_temp ?? prev.ambientTemp,
        isRaining: data.is_raining ?? prev.isRaining,
        cloudCover: data.cloud_cover ?? prev.cloudCover,
        solarEfficiency: data.solar_efficiency ?? prev.solarEfficiency,
        occupancyPercent: data.occupancy_percent ?? prev.occupancyPercent,
        currentSeason: data.current_season ?? prev.currentSeason,
        scenario: data.scenario ?? prev.scenario,
        recentEvents: data.recent_events ?? prev.recentEvents,

        // Estimate hvacLoadPercent from ambient_temp
        hvacLoadPercent: data.ambient_temp
          ? Math.max(0, Math.min(100, 30 + (data.ambient_temp - 22) * 3))
          : prev.hvacLoadPercent,

        // Energy consumption data
        totalEnergyKwh: data.total_energy_kwh ?? prev.totalEnergyKwh,
        currentHourPowerKw: data.current_hour_power_kw ?? prev.currentHourPowerKw,

        lastUpdated: Date.now(),
        isLoading: false,
        error: null,
      }))
    } catch (err) {
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err.message : 'Unknown error',
      }))
    }
  }, [siteId])

  // Poll every 25s for backend sync (1 simulated hour at 10min/day compression)
  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 25000)
    return () => clearInterval(interval)
  }, [refresh])

  // Smooth client-side interpolation: advance displayed time every second
  // between backend polls so the clock ticks smoothly instead of jumping.
  // Compression: 1 day = 10 real minutes → 1 hour = 25s → ~2.4 sim-minutes/real-second
  const SIM_MINUTES_PER_TICK = 2.4
  const lastPollHourRef = useRef<number>(0)

  useEffect(() => {
    lastPollHourRef.current = state.simulatedHour
  }, [state.lastUpdated]) // only reset on actual backend poll

  useEffect(() => {
    if (!state.running || state.paused) return

    const ticker = setInterval(() => {
      setState(prev => {
        if (!prev.running || prev.paused) return prev
        try {
          const t = new Date(prev.simulatedTime)
          t.setMinutes(t.getMinutes() + Math.round(SIM_MINUTES_PER_TICK))
          const newHour = t.getHours()
          // If hour wrapped past 23→0, let the backend poll handle the day increment
          if (newHour < prev.simulatedHour && prev.simulatedHour >= 22) return prev
          return {
            ...prev,
            simulatedTime: t.toISOString(),
            simulatedHour: newHour,
          }
        } catch {
          return prev
        }
      })
    }, 1000)

    return () => clearInterval(ticker)
  }, [state.running, state.paused])

  return (
    <SimulationContext.Provider value={{ state, refresh }}>
      {children}
    </SimulationContext.Provider>
  )
}

/**
 * Hook to access simulation state in components.
 * Returns current simulation state and a refresh function.
 *
 * Usage:
 * ```tsx
 * const { simulatedHour, occupancyPercent, running } = useSimulation()
 * ```
 */
export function useSimulation(): SimulationState & { refresh: () => Promise<void> } {
  const context = useContext(SimulationContext)
  if (context === undefined) {
    throw new Error('useSimulation must be used within SimulationProvider')
  }
  return { ...context.state, refresh: context.refresh }
}

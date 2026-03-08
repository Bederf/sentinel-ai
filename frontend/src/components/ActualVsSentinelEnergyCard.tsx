/**
 * Smart Lighting vs SENTINEL AI Energy Comparison Card
 *
 * Side-by-side energy comparison driven reactively by simulation context:
 * - Left column: Smart Lighting (occupancy + daylight harvesting)
 * - Right column: SENTINEL AI (full AI optimization)
 *
 * Computes hourly energy accumulation based on:
 * - Simulated hour (0-23): drives solar curve, occupancy patterns
 * - Cloud cover: affects daylight harvesting efficiency
 * - Occupancy percent: drives HVAC and lighting demand
 *
 * Values update live as the simulation clock advances.
 */

import { useMemo } from 'react'
import {
  TrendingDown,
  Wind,
  Lightbulb,
  Plug,
  Leaf,
  Target,
  AlertCircle,
} from 'lucide-react'
import { useSimulation } from '@/contexts/SimulationContext'

interface EnergyMetrics {
  total_kwh: number
  total_cost_zar: number
  carbon_kg: number
  hvac_kwh: number
  hvac_percent: number
  lighting_kwh: number
  lighting_percent: number
  power_kwh: number
  power_percent: number
}

interface ComparisonData {
  actual: EnergyMetrics
  sentinel: EnergyMetrics
  daily_savings_zar: number
  daily_savings_percent: number
  progress_to_target_percent: number
  ai_confidence_percent: number
}

interface ActualVsSentinelEnergyCardProps {
  siteId: string
}

function getSystemIcon(system: 'hvac' | 'lighting' | 'power') {
  switch (system) {
    case 'hvac':
      return <Wind className="h-4 w-4" />
    case 'lighting':
      return <Lightbulb className="h-4 w-4" />
    case 'power':
      return <Plug className="h-4 w-4" />
  }
}

/**
 * Compute hourly energy for each system based on time-of-day, cloud, occupancy.
 *
 * Building specs (Sandton City S002, ~5,000 m² GFA):
 * - Lighting: 8 DALI zones, ~2,500 luminaires × 50W = 125 kW capacity
 * - HVAC: 2 chillers + AHUs + FCUs = ~300 kW peak
 * - General power: UPS + lifts + plugs + servers = ~70 kW base
 *
 * Target energy split (typical commercial): ~55% HVAC, ~25% Lighting, ~20% Other
 *
 * Smart lighting reduces lighting via daylight harvesting + occupancy sensing.
 * SENTINEL AI further reduces HVAC (predictive setpoints) + lighting (pre-emptive dimming).
 */
function computeComparison(
  simulatedHour: number,
  cloudCover: number,
  occupancyPercent: number,
  daysSimulated: number,
): ComparisonData {
  const rate = 5      // R5/kWh
  const carbonRate = 0.35  // 0.35 kg CO₂/kWh SA grid

  // Accumulate energy hour-by-hour up to current simulated hour
  let triHvacAccum = 0
  let triLightAccum = 0
  let triPowerAccum = 0
  let senHvacAccum = 0
  let senLightAccum = 0
  let senPowerAccum = 0

  for (let h = 0; h <= simulatedHour; h++) {
    const isBusinessHour = h >= 7 && h <= 18
    const isCoreBusiness = h >= 8 && h <= 17

    // Occupancy curve: peaks 9-12, drops 13-14 (lunch), back 14-17
    let hourOcc = 5 // base nighttime
    if (isCoreBusiness) {
      hourOcc = occupancyPercent * (h >= 12 && h <= 13 ? 0.6 : 1.0) // lunch dip
    } else if (isBusinessHour) {
      hourOcc = occupancyPercent * 0.4 // early/late partial occupancy
    }
    hourOcc = Math.max(5, Math.min(100, hourOcc))

    // Solar daylight factor: cos curve 6-18, 0 at night
    let solarFactor = 0
    if (h >= 6 && h <= 18) {
      solarFactor = Math.max(0, Math.cos((h - 12) * Math.PI / 12))
    }
    const cloudMult = 1 - (cloudCover / 100) * 0.6
    const daylight = solarFactor * cloudMult // 0-1

    // --- HVAC (kW this hour) ---
    // 300 kW peak during business (2 chillers + AHUs + FCUs), 50 kW standby off-hours
    const hvacBase = isBusinessHour ? 300 : 50
    // Smart lighting: HVAC not affected by lighting automation (same as baseline occupancy-scaled)
    const triHvacHour = hvacBase * (hourOcc / 100) * 0.85
    // SENTINEL: predictive setpoints reduce HVAC 12-18% during business hours
    const sentinelHvacSaving = isBusinessHour ? 0.85 : 0.95 // 15% saving business, 5% off
    const senHvacHour = hvacBase * (hourOcc / 100) * 0.85 * sentinelHvacSaving

    // --- Lighting (kW this hour) ---
    // 125 kW total lighting capacity (8 DALI zones × ~15.6 kW each)
    const lightingCapacity = 125
    // Smart lighting: daylight harvesting reduces artificial light
    const triDaylightReduction = daylight * 0.65 // harvests up to 65% from daylight
    const triOccReduction = hourOcc < 15 ? 0.7 : 0 // standby mode saves 70% in empty zones
    const triLightHour = lightingCapacity * (hourOcc / 100)
      * Math.max(0.15, 1 - triDaylightReduction - triOccReduction)
    // SENTINEL: predictive pre-dimming + tighter occupancy thresholds
    const senDaylightReduction = daylight * 0.75 // AI predicts cloud gaps, harvests more
    const senOccReduction = hourOcc < 25 ? 0.8 : (hourOcc < 50 ? 0.3 : 0) // more aggressive
    const senLightHour = lightingCapacity * (hourOcc / 100)
      * Math.max(0.10, 1 - senDaylightReduction - senOccReduction)

    // --- General power (kW this hour) ---
    // 70 kW business (lifts, UPS, plugs, servers), 40 kW off-hours
    const powerBase = isBusinessHour ? 70 : 40
    const triPowerHour = powerBase * 0.95
    const senPowerHour = powerBase * 0.92 // UPS optimization, lift scheduling

    triHvacAccum += triHvacHour
    triLightAccum += triLightHour
    triPowerAccum += triPowerHour
    senHvacAccum += senHvacHour
    senLightAccum += senLightHour
    senPowerAccum += senPowerHour
  }

  // Project to monthly (×30 working days) so numbers are meaningful
  const monthlyMultiplier = 30

  const triHvac = Math.round(triHvacAccum * monthlyMultiplier)
  const triLight = Math.round(triLightAccum * monthlyMultiplier)
  const triPower = Math.round(triPowerAccum * monthlyMultiplier)
  const triTotal = triHvac + triLight + triPower

  const senHvac = Math.round(senHvacAccum * monthlyMultiplier)
  const senLight = Math.round(senLightAccum * monthlyMultiplier)
  const senPower = Math.round(senPowerAccum * monthlyMultiplier)
  const senTotal = senHvac + senLight + senPower

  const triCost = triTotal * rate
  const senCost = senTotal * rate
  const savingsZar = triCost - senCost
  const savingsPct = triCost > 0 ? (savingsZar / triCost) * 100 : 0

  // AI confidence grows with simulation days (learning curve)
  const aiConfidence = Math.min(95, 60 + (daysSimulated / 365) * 35)

  return {
    actual: {
      total_kwh: triTotal,
      total_cost_zar: triCost,
      carbon_kg: Math.round(triTotal * carbonRate),
      hvac_kwh: triHvac,
      hvac_percent: triTotal > 0 ? Math.round((triHvac / triTotal) * 100) : 0,
      lighting_kwh: triLight,
      lighting_percent: triTotal > 0 ? Math.round((triLight / triTotal) * 100) : 0,
      power_kwh: triPower,
      power_percent: triTotal > 0 ? Math.round((triPower / triTotal) * 100) : 0,
    },
    sentinel: {
      total_kwh: senTotal,
      total_cost_zar: senCost,
      carbon_kg: Math.round(senTotal * carbonRate),
      hvac_kwh: senHvac,
      hvac_percent: senTotal > 0 ? Math.round((senHvac / senTotal) * 100) : 0,
      lighting_kwh: senLight,
      lighting_percent: senTotal > 0 ? Math.round((senLight / senTotal) * 100) : 0,
      power_kwh: senPower,
      power_percent: senTotal > 0 ? Math.round((senPower / senTotal) * 100) : 0,
    },
    daily_savings_zar: Math.round(savingsZar),
    daily_savings_percent: Math.round(savingsPct * 10) / 10,
    progress_to_target_percent: Math.min(Math.round(savingsPct / 15 * 100), 100),
    ai_confidence_percent: Math.round(aiConfidence),
  }
}

export function ActualVsSentinelEnergyCard({ siteId: _siteId }: ActualVsSentinelEnergyCardProps) {
  const {
    running,
    simulatedHour,
    cloudCover,
    occupancyPercent,
    daysSimulated,
  } = useSimulation()

  // Reactively compute comparison whenever simulation state changes
  const comparison = useMemo<ComparisonData | null>(() => {
    if (!running) return null
    return computeComparison(
      simulatedHour || 0,
      cloudCover || 0,
      occupancyPercent || 0,
      daysSimulated || 1,
    )
  }, [running, simulatedHour, cloudCover, occupancyPercent, daysSimulated])

  if (!comparison) {
    return (
      <div
        className="rounded-md p-6 text-center"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <AlertCircle className="h-8 w-8 mx-auto mb-2" style={{ color: 'var(--color-sentinel-text-disabled)' }} />
        <span className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          Start a simulation to see live energy comparison
        </span>
      </div>
    )
  }

  const { actual, sentinel, daily_savings_zar, daily_savings_percent, progress_to_target_percent, ai_confidence_percent } =
    comparison

  return (
    <div
      className="rounded-md overflow-hidden"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      {/* Panel Header */}
      <div
        className="p-4 flex items-center justify-between"
        style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: 'rgba(16, 185, 129, 0.15)' }}
          >
            <TrendingDown className="h-5 w-5" style={{ color: 'var(--color-sentinel-green)' }} />
          </div>
          <div>
            <h3 className="font-medium text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
              Energy: Smart Lighting vs SENTINEL AI
            </h3>
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Monthly projected energy comparison
            </span>
          </div>
        </div>
        <span
          className="text-xs px-2 py-1 rounded uppercase font-medium flex items-center gap-1"
          style={{ background: 'rgba(16, 185, 129, 0.15)', color: 'var(--color-sentinel-green)' }}
        >
          <Leaf className="h-3 w-3" />
          {daily_savings_percent.toFixed(1)}% Savings
        </span>
      </div>

      {/* Main Content */}
      <div className="p-4">
        {/* 2-Column Comparison */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          {/* Actual Column */}
          <div className="space-y-4">
            <div
              className="rounded-md p-4"
              style={{ background: 'var(--color-sentinel-bg-secondary)' }}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold uppercase" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                  Smart Lighting
                </span>
                <span className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                  Installed System
                </span>
              </div>

              {/* Primary Metric */}
              <div className="mb-3">
                <div className="text-3xl font-bold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                  {actual.total_kwh.toLocaleString()}
                </div>
                <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                  kWh
                </span>
              </div>

              {/* Cost & Carbon */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    Cost:
                  </span>
                  <span className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    R{actual.total_cost_zar.toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs flex items-center gap-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    <Leaf className="h-3 w-3" />
                    Carbon:
                  </span>
                  <span className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {actual.carbon_kg.toLocaleString()} kg CO₂
                  </span>
                </div>
              </div>
            </div>

            {/* System Breakdown */}
            <div className="space-y-2">
              {/* HVAC */}
              <div className="p-3 rounded" style={{ background: 'var(--color-sentinel-bg-secondary)' }}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    {getSystemIcon('hvac')}
                    <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                      HVAC
                    </span>
                  </div>
                  <span className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {actual.hvac_percent}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="w-full h-1.5 rounded-full mr-2" style={{ background: 'rgba(255,255,255,0.1)' }}>
                    <div
                      className="h-1.5 rounded-full transition-all duration-500"
                      style={{
                        width: `${actual.hvac_percent}%`,
                        background: 'var(--color-sentinel-blue)',
                      }}
                    />
                  </div>
                  <span className="text-xs text-right w-12" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    {actual.hvac_kwh} kWh
                  </span>
                </div>
              </div>

              {/* Lighting */}
              <div className="p-3 rounded" style={{ background: 'var(--color-sentinel-bg-secondary)' }}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    {getSystemIcon('lighting')}
                    <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                      Lighting
                    </span>
                  </div>
                  <span className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {actual.lighting_percent}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="w-full h-1.5 rounded-full mr-2" style={{ background: 'rgba(255,255,255,0.1)' }}>
                    <div
                      className="h-1.5 rounded-full transition-all duration-500"
                      style={{
                        width: `${actual.lighting_percent}%`,
                        background: 'var(--color-sentinel-amber)',
                      }}
                    />
                  </div>
                  <span className="text-xs text-right w-12" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    {actual.lighting_kwh} kWh
                  </span>
                </div>
              </div>

              {/* Power */}
              <div className="p-3 rounded" style={{ background: 'var(--color-sentinel-bg-secondary)' }}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    {getSystemIcon('power')}
                    <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                      Power
                    </span>
                  </div>
                  <span className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {actual.power_percent}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="w-full h-1.5 rounded-full mr-2" style={{ background: 'rgba(255,255,255,0.1)' }}>
                    <div
                      className="h-1.5 rounded-full transition-all duration-500"
                      style={{
                        width: `${actual.power_percent}%`,
                        background: 'var(--color-sentinel-red)',
                      }}
                    />
                  </div>
                  <span className="text-xs text-right w-12" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    {actual.power_kwh} kWh
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* SENTINEL Column */}
          <div className="space-y-4">
            <div
              className="rounded-md p-4"
              style={{ background: 'rgba(16, 185, 129, 0.1)' }}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold uppercase" style={{ color: 'var(--color-sentinel-green)' }}>
                  SENTINEL AI (Optimized)
                </span>
                <span className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                  Predicted
                </span>
              </div>

              {/* Primary Metric */}
              <div className="mb-3">
                <div className="text-3xl font-bold" style={{ color: 'var(--color-sentinel-green)' }}>
                  {sentinel.total_kwh.toLocaleString()}
                </div>
                <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                  kWh
                </span>
              </div>

              {/* Cost & Carbon */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    Cost:
                  </span>
                  <span className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-green)' }}>
                    R{sentinel.total_cost_zar.toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs flex items-center gap-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    <Leaf className="h-3 w-3" />
                    Carbon:
                  </span>
                  <span className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-green)' }}>
                    {sentinel.carbon_kg.toLocaleString()} kg CO₂
                  </span>
                </div>
              </div>
            </div>

            {/* System Breakdown */}
            <div className="space-y-2">
              {/* HVAC */}
              <div className="p-3 rounded" style={{ background: 'var(--color-sentinel-bg-secondary)' }}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    {getSystemIcon('hvac')}
                    <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                      HVAC
                    </span>
                  </div>
                  <span className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-green)' }}>
                    {sentinel.hvac_percent}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="w-full h-1.5 rounded-full mr-2" style={{ background: 'rgba(255,255,255,0.1)' }}>
                    <div
                      className="h-1.5 rounded-full transition-all duration-500"
                      style={{
                        width: `${sentinel.hvac_percent}%`,
                        background: 'var(--color-sentinel-blue)',
                      }}
                    />
                  </div>
                  <span className="text-xs text-right w-12" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    {sentinel.hvac_kwh} kWh
                  </span>
                </div>
              </div>

              {/* Lighting */}
              <div className="p-3 rounded" style={{ background: 'var(--color-sentinel-bg-secondary)' }}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    {getSystemIcon('lighting')}
                    <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                      Lighting
                    </span>
                  </div>
                  <span className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-green)' }}>
                    {sentinel.lighting_percent}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="w-full h-1.5 rounded-full mr-2" style={{ background: 'rgba(255,255,255,0.1)' }}>
                    <div
                      className="h-1.5 rounded-full transition-all duration-500"
                      style={{
                        width: `${sentinel.lighting_percent}%`,
                        background: 'var(--color-sentinel-amber)',
                      }}
                    />
                  </div>
                  <span className="text-xs text-right w-12" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    {sentinel.lighting_kwh} kWh
                  </span>
                </div>
              </div>

              {/* Power */}
              <div className="p-3 rounded" style={{ background: 'var(--color-sentinel-bg-secondary)' }}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    {getSystemIcon('power')}
                    <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                      Power
                    </span>
                  </div>
                  <span className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-green)' }}>
                    {sentinel.power_percent}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="w-full h-1.5 rounded-full mr-2" style={{ background: 'rgba(255,255,255,0.1)' }}>
                    <div
                      className="h-1.5 rounded-full transition-all duration-500"
                      style={{
                        width: `${sentinel.power_percent}%`,
                        background: 'var(--color-sentinel-red)',
                      }}
                    />
                  </div>
                  <span className="text-xs text-right w-12" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    {sentinel.power_kwh} kWh
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Comparison Metrics Band */}
        <div
          className="rounded-md p-4 space-y-3"
          style={{ background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.2)' }}
        >
          {/* Savings */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <TrendingDown className="h-4 w-4" style={{ color: 'var(--color-sentinel-green)' }} />
              <span className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Monthly Savings
              </span>
            </div>
            <div className="text-right">
              <div className="text-lg font-bold" style={{ color: 'var(--color-sentinel-green)' }}>
                R{daily_savings_zar.toLocaleString()}
              </div>
              <span className="text-xs" style={{ color: 'var(--color-sentinel-green)' }}>
                {daily_savings_percent.toFixed(1)}% reduction
              </span>
            </div>
          </div>

          {/* Progress to Target */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Target className="h-4 w-4" style={{ color: 'var(--color-sentinel-blue)' }} />
                <span className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                  Progress to Target
                </span>
              </div>
              <span className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {progress_to_target_percent.toFixed(0)}%
              </span>
            </div>
            <div className="w-full h-2 rounded-full" style={{ background: 'rgba(255,255,255,0.1)' }}>
              <div
                className="h-2 rounded-full transition-all duration-700"
                style={{
                  width: `${progress_to_target_percent}%`,
                  background: 'var(--color-sentinel-blue)',
                }}
              />
            </div>
          </div>

          {/* AI Confidence */}
          <div className="flex items-center justify-between">
            <span className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              AI Confidence
            </span>
            <span
              className="text-sm font-semibold px-2 py-1 rounded"
              style={{
                background: ai_confidence_percent >= 80 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                color: ai_confidence_percent >= 80 ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-amber)',
              }}
            >
              {ai_confidence_percent.toFixed(0)}%
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ActualVsSentinelEnergyCard

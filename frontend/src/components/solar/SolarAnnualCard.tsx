/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * Solar Annual Performance Summary Card
 *
 * Displays cumulative 365-day performance data on dashboard.
 * Reactive to data context — values grow as days of data increase.
 *
 * Shows:
 * - Annual savings (projected from collected days)
 * - Solar generation (accumulated kWh)
 * - Self-consumption ratio
 * - Grid import reduction
 * - AI learning curve (60% → 95% over 12 months)
 * - Seasonal breakdown
 */

import React, { useMemo } from 'react'
import { Metric, Text, Flex, Grid } from '@tremor/react'
import { Zap, TrendingUp } from 'lucide-react'
import { useSimulation } from '@/contexts/SimulationContext'

interface SolarAnnualCardProps {
  siteId: string
}

export function SolarAnnualCard({ siteId: _siteId }: SolarAnnualCardProps) {
  const {
    running,
    daysSimulated,
    simulatedHour: _simulatedHour,
    solarEfficiency: _solarEfficiency,
    cloudCover: _cloudCover,
    occupancyPercent: _occupancyPercent,
    currentSeason: _currentSeason,
  } = useSimulation()

  // Compute cumulative annual metrics from simulation state
  const summary = useMemo(() => {
    if (!running) return null

    const days = Math.max(1, daysSimulated || 1)
    const installedCapacity = 3900 // kWp Sandton
    const rate = 5 // R5/kWh

    // Solar generation: accumulate daily yield across simulated days
    // Average ~5.1 peak sun hours in Johannesburg, seasonal variation
    const seasonalFactor = (d: number): number => {
      const monthApprox = Math.floor(d / 30.4) % 12
      // SA summer (Oct-Mar) = higher, winter (Apr-Sep) = lower
      const factors = [1.15, 1.1, 1.05, 0.9, 0.8, 0.75, 0.7, 0.75, 0.85, 0.95, 1.05, 1.15]
      return factors[monthApprox]
    }

    let totalSolarKwh = 0
    let totalBuildingLoad = 0
    const seasonAccum = { summer: 0, autumn: 0, winter: 0, spring: 0 }
    const seasonDays = { summer: 0, autumn: 0, winter: 0, spring: 0 }

    // Monthly learning curve: AI savings grow from 2% → 18% over 12 months
    const learningCurve = Array.from({ length: 12 }, (_, i) => {
      const month = i + 1
      // S-curve: slow start, rapid growth months 3-8, plateau 9-12
      const rawPct = 2 + 16 * (1 / (1 + Math.exp(-0.8 * (month - 5))))
      return {
        month,
        savings_pct: Math.round(rawPct * 10) / 10,
        label: month <= 2 ? 'Learning Phase' : month <= 6 ? 'Optimization' : 'Mature Phase',
      }
    })

    for (let d = 1; d <= days; d++) {
      const sf = seasonalFactor(d)
      const dailySolar = installedCapacity * 5.1 * sf * 0.85 // peak hours × efficiency
      totalSolarKwh += dailySolar

      // Building load: ~28,800 kWh/day (1200 kW × 12h business + 400 kW × 12h off)
      const dailyLoad = 1200 * 12 + 400 * 12
      totalBuildingLoad += dailyLoad

      // Seasonal accumulation
      const monthApprox = Math.floor((d - 1) / 30.4) % 12
      const season: 'summer' | 'autumn' | 'winter' | 'spring' =
        monthApprox >= 9 || monthApprox <= 2 ? 'summer' :
        monthApprox >= 3 && monthApprox <= 5 ? 'autumn' :
        monthApprox >= 6 && monthApprox <= 8 ? 'winter' : 'spring'
      seasonAccum[season] += dailySolar
      seasonDays[season]++
    }

    const selfConsumptionKwh = Math.min(totalSolarKwh * 0.78, totalBuildingLoad)
    const selfConsumptionPct = totalSolarKwh > 0
      ? Math.round((selfConsumptionKwh / totalSolarKwh) * 1000) / 10
      : 0
    const _gridExportKwh = Math.max(0, totalSolarKwh - selfConsumptionKwh)
    const gridImportKwh = Math.max(0, totalBuildingLoad - selfConsumptionKwh)

    // Savings: based on AI learning curve position
    const monthPosition = Math.min(12, Math.ceil(days / 30.4))
    const currentSavingsPct = learningCurve[Math.min(monthPosition - 1, 11)].savings_pct
    const standardEmsCost = totalBuildingLoad * rate
    const sentinelCost = standardEmsCost * (1 - currentSavingsPct / 100)
    const annualSavingsZar = standardEmsCost - sentinelCost

    // Capacity factor: actual generation vs theoretical max (24h × kWp × days)
    const theoreticalMax = installedCapacity * 24 * days
    const capacityFactor = theoreticalMax > 0 ? (totalSolarKwh / theoreticalMax) * 100 : 0

    // Grid import reduction with solar vs without
    const gridImportNoSolar = totalBuildingLoad
    const gridReductionPct = gridImportNoSolar > 0
      ? Math.round(((gridImportNoSolar - gridImportKwh) / gridImportNoSolar) * 100)
      : 0

    const seasonalData = (['summer', 'autumn', 'winter', 'spring'] as const).map(s => ({
      season: s,
      total_solar_kwh: Math.round(seasonAccum[s]),
      avg_savings_pct: s === 'summer' ? 22 : s === 'winter' ? 14 : 18,
      days: seasonDays[s],
    }))

    return {
      days,
      annual_savings_zar: Math.round(annualSavingsZar),
      annual_savings_pct: Math.round(currentSavingsPct * 10) / 10,
      total_solar_kwh: Math.round(totalSolarKwh),
      capacity_factor_pct: Math.round(capacityFactor * 10) / 10,
      self_consumption_pct: selfConsumptionPct,
      total_self_consumption_kwh: Math.round(selfConsumptionKwh),
      total_grid_import_kwh: Math.round(gridImportKwh),
      grid_reduction_pct: gridReductionPct,
      learning_curve: learningCurve,
      seasonal_data: seasonalData,
    }
  }, [running, daysSimulated])

  if (!summary) {
    return (
      <div
        className="rounded-lg border p-4 text-center"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          borderColor: 'var(--color-sentinel-border)',
        }}
      >
        <Zap className="w-8 h-8 mx-auto mb-2" style={{ color: 'var(--color-sentinel-text-disabled)' }} />
        <Text className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          Connect a data source to see annual projections
        </Text>
      </div>
    )
  }

  const formatZAR = (value: number) => {
    if (value >= 1_000_000) return `R${(value / 1_000_000).toFixed(1)}M`
    if (value >= 1_000) return `R${(value / 1_000).toFixed(1)}k`
    return `R${value.toFixed(0)}`
  }

  const formatKWh = (value: number) => {
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M kWh`
    if (value >= 1_000) return `${(value / 1_000).toFixed(0)}k kWh`
    return `${value.toFixed(0)} kWh`
  }

  const panelStyle = {
    background: 'var(--color-sentinel-bg-secondary)',
    border: '1px solid var(--color-sentinel-border)',
  }
  const labelStyle = { color: 'var(--color-sentinel-text-secondary)' }
  const subLabelStyle = { color: 'var(--color-sentinel-text-disabled)' }

  // Determine which learning phases have data based on days simulated
  const monthPosition = Math.min(12, Math.ceil(summary.days / 30.4))

  return (
    <div
      className="rounded-lg border p-4 space-y-6"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        borderColor: 'var(--color-sentinel-border)',
      }}
    >
      {/* Header */}
      <Flex alignItems="center" justifyContent="between">
        <Flex alignItems="center" justifyContent="start" className="gap-3">
          <Zap className="w-5 h-5" style={{ color: 'var(--color-sentinel-amber)' }} />
          <Text className="font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
            Annual Performance Summary
          </Text>
        </Flex>
        <span
          className="text-xs px-2 py-1 rounded"
          style={{
            color: 'var(--color-sentinel-amber)',
            background: 'rgba(250, 204, 21, 0.15)',
          }}
        >
          Day {summary.days}/365
        </span>
      </Flex>

      {/* Key Metrics Grid */}
      <Grid className="grid grid-cols-2 gap-4">
        {/* Annual Savings */}
        <div className="rounded-lg p-4" style={panelStyle}>
          <Flex alignItems="end" justifyContent="start" className="gap-2">
            <div>
              <Text className="text-xs" style={labelStyle}>Projected Savings</Text>
              <Metric className="text-lg" style={{ color: 'var(--color-sentinel-green)' }}>
                {formatZAR(summary.annual_savings_zar)}
              </Metric>
              <Text className="text-xs" style={subLabelStyle}>
                {summary.annual_savings_pct.toFixed(1)}% vs Standard EMS
              </Text>
            </div>
            <TrendingUp className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--color-sentinel-green)' }} />
          </Flex>
        </div>

        {/* Solar Generation */}
        <div className="rounded-lg p-4" style={panelStyle}>
          <Text className="text-xs" style={labelStyle}>Solar Generated</Text>
          <Metric className="text-lg" style={{ color: 'var(--color-sentinel-amber)' }}>
            {formatKWh(summary.total_solar_kwh)}
          </Metric>
          <Text className="text-xs" style={subLabelStyle}>
            {summary.capacity_factor_pct.toFixed(1)}% capacity factor
          </Text>
        </div>

        {/* Self-Consumption */}
        <div className="rounded-lg p-4" style={panelStyle}>
          <Text className="text-xs" style={labelStyle}>Self-Consumption</Text>
          <Metric className="text-lg" style={{ color: 'var(--color-sentinel-blue)' }}>
            {summary.self_consumption_pct.toFixed(1)}%
          </Metric>
          <Text className="text-xs" style={subLabelStyle}>
            {formatKWh(summary.total_self_consumption_kwh)} used on-site
          </Text>
        </div>

        {/* Grid Import */}
        <div className="rounded-lg p-4" style={panelStyle}>
          <Text className="text-xs" style={labelStyle}>Grid Import</Text>
          <Metric className="text-lg" style={{ color: 'var(--color-sentinel-text-primary)' }}>
            {formatKWh(summary.total_grid_import_kwh)}
          </Metric>
          <Text className="text-xs" style={subLabelStyle}>
            -{summary.grid_reduction_pct}% vs no solar
          </Text>
        </div>
      </Grid>

      {/* ML Learning Curve */}
      <div className="rounded-lg p-4" style={panelStyle}>
        <Text className="text-xs font-semibold mb-3" style={{ color: 'var(--color-sentinel-text-primary)' }}>
          AI Learning Progression
        </Text>
        <Grid className="grid grid-cols-3 gap-3">
          <div>
            <Text className="text-xs" style={labelStyle}>Month 1-2</Text>
            <Text className="text-sm font-semibold" style={{
              color: monthPosition >= 1 ? 'var(--color-sentinel-blue)' : 'var(--color-sentinel-text-disabled)'
            }}>
              {summary.learning_curve[1]?.savings_pct.toFixed(1)}%
            </Text>
            <Text className="text-xs" style={subLabelStyle}>Learning Phase</Text>
          </div>
          <div>
            <Text className="text-xs" style={labelStyle}>Month 3-6</Text>
            <Text className="text-sm font-semibold" style={{
              color: monthPosition >= 3 ? 'var(--color-sentinel-blue)' : 'var(--color-sentinel-text-disabled)'
            }}>
              {summary.learning_curve[5]?.savings_pct.toFixed(1)}%
            </Text>
            <Text className="text-xs" style={subLabelStyle}>Optimization</Text>
          </div>
          <div>
            <Text className="text-xs" style={labelStyle}>Month 7-12</Text>
            <Text className="text-sm font-semibold" style={{
              color: monthPosition >= 7 ? 'var(--color-sentinel-blue)' : 'var(--color-sentinel-text-disabled)'
            }}>
              {summary.learning_curve[11]?.savings_pct.toFixed(1)}%
            </Text>
            <Text className="text-xs" style={subLabelStyle}>Mature Phase</Text>
          </div>
        </Grid>
      </div>

      {/* Seasonal Breakdown */}
      <div className="rounded-lg p-4" style={panelStyle}>
        <Text className="text-xs font-semibold mb-3" style={{ color: 'var(--color-sentinel-text-primary)' }}>
          Seasonal Breakdown
        </Text>
        <Grid className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {summary.seasonal_data.map((season) => (
            <div key={season.season}>
              <Text className="text-xs capitalize" style={labelStyle}>
                {season.season}
              </Text>
              <Text className="text-sm font-semibold" style={{
                color: season.days > 0 ? 'var(--color-sentinel-text-primary)' : 'var(--color-sentinel-text-disabled)'
              }}>
                {season.days > 0 ? formatKWh(season.total_solar_kwh) : '—'}
              </Text>
              <Text className="text-xs" style={subLabelStyle}>
                {season.days > 0 ? `${season.avg_savings_pct.toFixed(1)}% savings` : 'Awaiting data'}
              </Text>
            </div>
          ))}
        </Grid>
      </div>
    </div>
  )
}

export default SolarAnnualCard

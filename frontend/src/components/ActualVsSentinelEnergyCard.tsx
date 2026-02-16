/**
 * Actual vs SENTINEL Energy Comparison Card
 *
 * Side-by-side energy monitoring comparison:
 * - Left column: Actual (monitored) energy consumption
 * - Right column: SENTINEL AI (optimized) prediction
 *
 * Displays:
 * - Total energy (kWh) and cost (R/day)
 * - Carbon footprint (kg CO₂)
 * - System breakdown (HVAC, Lighting, Power) with percentages
 * - Daily savings and progress to target
 * - AI confidence score
 *
 * Follows BESSStatusPanel pattern with 30s auto-refresh.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  TrendingDown,
  Zap,
  Wind,
  Lightbulb,
  Plug,
  Leaf,
  Target,
  AlertCircle,
} from 'lucide-react'
import { isExpectedApiError, authorizedFetch } from '@/lib/api'
import { useModuleAccess } from '@/hooks/useModuleAccess'
import type { ModuleType } from '@/lib/moduleRegistry'

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
  timestamp: string
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

// Color utilities
function getCostColor(isOptimized: boolean): string {
  return isOptimized ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-text-secondary)'
}

function getCostBgColor(isOptimized: boolean): string {
  return isOptimized ? 'rgba(16, 185, 129, 0.15)' : 'rgba(107, 114, 128, 0.15)'
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

// Mock fetch for now - replace with actual API calls
// Savings vary by active modules:
// - Base (HVAC only): 10-12%
// - With Solar: +8-10% → 18-22%
// - With Lighting (DALI): +3-5% → 13-17%
// - With both: ~22-25%
async function fetchEnergyComparison(siteId: string, activeModuleTypes: string[] = []): Promise<ComparisonData> {
  try {
    const response = await authorizedFetch(`/api/energy/comparison-summary?site_id=${siteId}`)
    if (!response.ok) throw new Error('Failed to fetch energy comparison')
    return await response.json()
  } catch (err) {
    if (!isExpectedApiError(err)) {
      console.error('Failed to load energy comparison:', err)
    }
    
    // Calculate savings based on active modules (demo scenario)
    let savingsPercent = 11.5; // Base HVAC savings
    let savingsKwh = 2450 * 0.115; // ~282 kWh
    let confidencePercent = 78;
    
    if (activeModuleTypes.includes('solar')) {
      savingsPercent += 9.8; // Solar adds 9-10%
      savingsKwh += 2450 * 0.098;
      confidencePercent = 88;
    }
    
    if (activeModuleTypes.includes('lighting')) {
      savingsPercent += 4.2; // DALI adds 4-5%
      savingsKwh += 2450 * 0.042;
      confidencePercent = Math.min(confidencePercent + 5, 92);
    }
    
    // Return mock data for demo with dynamic savings
    const actualTotal = 2450;
    const sentinelTotal = actualTotal * (1 - (savingsPercent / 100));
    
    return {
      actual: {
        total_kwh: actualTotal,
        total_cost_zar: actualTotal * 5, // R5/kWh commercial rate
        carbon_kg: actualTotal * 0.35, // SA grid carbon intensity
        hvac_kwh: 1200,
        hvac_percent: 49,
        lighting_kwh: 850,
        lighting_percent: 35,
        power_kwh: 400,
        power_percent: 16,
        timestamp: new Date().toISOString(),
      },
      sentinel: {
        total_kwh: sentinelTotal,
        total_cost_zar: sentinelTotal * 5,
        carbon_kg: sentinelTotal * 0.35,
        hvac_kwh: 950,
        hvac_percent: 48,
        lighting_kwh: 650,
        lighting_percent: 33,
        power_kwh: 380,
        power_percent: 19,
        timestamp: new Date().toISOString(),
      },
      daily_savings_zar: (actualTotal - sentinelTotal) * 5,
      daily_savings_percent: savingsPercent,
      progress_to_target_percent: Math.min(savingsPercent / 25 * 100, 100),
      ai_confidence_percent: confidencePercent,
    }
  }
}

export function ActualVsSentinelEnergyCard({ siteId }: ActualVsSentinelEnergyCardProps) {
  const [comparison, setComparison] = useState<ComparisonData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  // Check which optimization modules are active (drives demo moment)
  const { isActive: isSolarActive } = useModuleAccess('solar' as ModuleType)
  const { isActive: isLightingActive } = useModuleAccess('lighting' as ModuleType)

  const loadData = useCallback(async () => {
    try {
      // Build array of active module types to pass to fetch
      const activeModules: string[] = []
      if (isSolarActive) activeModules.push('solar')
      if (isLightingActive) activeModules.push('lighting')
      
      const data = await fetchEnergyComparison(siteId, activeModules)
      setComparison(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [siteId, isSolarActive, isLightingActive])

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 30000) // 30s refresh
    return () => clearInterval(interval)
  }, [loadData])

  if (loading) {
    return (
      <div
        className="rounded-md p-6"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <div className="animate-pulse space-y-4">
          <div className="h-4 w-48 rounded" style={{ background: 'var(--color-sentinel-bg-secondary)' }} />
          <div className="grid grid-cols-2 gap-4">
            {[0, 1].map((i) => (
              <div key={i} className="space-y-3">
                <div className="h-16 rounded" style={{ background: 'var(--color-sentinel-bg-secondary)' }} />
                <div className="h-32 rounded" style={{ background: 'var(--color-sentinel-bg-secondary)' }} />
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error || !comparison) {
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
          {error || 'No energy comparison data available'}
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
              Energy Comparison: Actual vs SENTINEL AI
            </h3>
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Real-time monitoring vs AI-optimized prediction
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
                  Actual (Today)
                </span>
                <span className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                  Monitored
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
                Daily Savings
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

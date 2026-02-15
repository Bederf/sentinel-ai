// @ts-nocheck
/**
 * Solar Annual Simulation Card Component
 * Displays 365-day simulation summary on dashboard
 * Shows: Annual savings, solar generation, ML learning curve progress
 */

import React, { useEffect, useState } from 'react'
import { Card, Metric, Text, ProgressBar, Flex, Grid } from '@tremor/react'
import { ArrowUp, Zap, TrendingUp } from 'lucide-react'
import { fetchAnnualSummary, startAnnualSimulation } from '@/lib/api/solarAnnual'
import type { AnnualSummary } from '@/lib/api/solarAnnual'

interface SolarAnnualCardProps {
  siteId: string
  onSimulationComplete?: (summary: AnnualSummary) => void
}

export function SolarAnnualCard({ siteId, onSimulationComplete }: SolarAnnualCardProps) {
  const [summary, setSummary] = useState<AnnualSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [simulationProgress, setSimulationProgress] = useState(0)

  // Fetch cached results or start simulation on mount
  useEffect(() => {
    const loadSummary = async () => {
      try {
        const data = await fetchAnnualSummary(siteId)
        setSummary(data)
        setLoading(false)
      } catch (error: any) {
        if (error.status === 404) {
          // Results not cached, start simulation
          startSimulation()
        } else {
          console.error('Failed to fetch annual summary:', error)
          setLoading(false)
        }
      }
    }

    loadSummary()
  }, [siteId])

  const startSimulation = async () => {
    try {
      const result = await startAnnualSimulation(siteId)
      pollSimulationProgress(result.task_id)
    } catch (error) {
      console.error('Failed to start simulation:', error)
      setLoading(false)
    }
  }

  const pollSimulationProgress = async (taskId: string) => {
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/solar/annual/${siteId}/status/${taskId}`)
        const data = await response.json()

        setSimulationProgress(data.progress_pct)

        if (data.status === 'completed') {
          clearInterval(interval)
          const summary = await fetchAnnualSummary(siteId)
          setSummary(summary)
          setLoading(false)
          onSimulationComplete?.(summary)
        } else if (data.status === 'failed') {
          clearInterval(interval)
          console.error('Simulation failed:', data.error)
          setLoading(false)
        }
      } catch (error) {
        console.error('Failed to poll progress:', error)
      }
    }, 5000) // Poll every 5 seconds
  }

  if (loading) {
    return (
      <Card className="bg-gradient-to-br from-amber-50 to-yellow-50 border border-amber-200">
        <div className="space-y-4">
          <Flex alignItems="center" justifyContent="start" className="gap-3">
            <Zap className="w-5 h-5 text-amber-600" />
            <Text className="font-semibold">Solar + BESS Annual Simulation</Text>
          </Flex>
          <div>
            <Text className="text-sm text-gray-600 mb-2">
              Generating 365-day results... {simulationProgress}%
            </Text>
            <ProgressBar value={simulationProgress} className="h-2" />
          </div>
        </div>
      </Card>
    )
  }

  if (!summary) return null

  const formatZAR = (value: number) => `R${(value / 1000).toFixed(1)}k`
  const formatKWh = (value: number) => `${(value / 1000).toFixed(0)}k kWh`

  return (
    <Card className="bg-gradient-to-br from-green-50 to-emerald-50 border border-green-200">
      <div className="space-y-6">
        {/* Header */}
        <Flex alignItems="center" justifyContent="between">
          <Flex alignItems="center" justifyContent="start" className="gap-3">
            <Zap className="w-5 h-5 text-green-600" />
            <Text className="font-semibold">Annual Simulation Results</Text>
          </Flex>
          <Text className="text-xs text-green-600 bg-green-100 px-2 py-1 rounded">
            365 days
          </Text>
        </Flex>

        {/* Key Metrics Grid */}
        <Grid numColsSm={2} numColsLg={4} className="gap-4">
          {/* Annual Savings */}
          <div className="bg-white rounded-lg p-4 border border-green-100">
            <Flex alignItems="end" justifyContent="start" className="gap-2">
              <div>
                <Text className="text-xs text-gray-600">Annual Savings</Text>
                <Metric className="text-green-600">
                  {formatZAR(summary.annual_savings_zar)}
                </Metric>
                <Text className="text-xs text-gray-500">
                  {summary.annual_savings_pct.toFixed(1)}% vs Standard EMS
                </Text>
              </div>
              <TrendingUp className="w-5 h-5 text-green-500" />
            </Flex>
          </div>

          {/* Solar Generation */}
          <div className="bg-white rounded-lg p-4 border border-amber-100">
            <Text className="text-xs text-gray-600">Solar Generated</Text>
            <Metric className="text-amber-600">
              {formatKWh(summary.total_solar_kwh)}
            </Metric>
            <Text className="text-xs text-gray-500">
              {summary.capacity_factor_pct.toFixed(1)}% capacity factor
            </Text>
          </div>

          {/* Self-Consumption */}
          <div className="bg-white rounded-lg p-4 border border-blue-100">
            <Text className="text-xs text-gray-600">Self-Consumption</Text>
            <Metric className="text-blue-600">
              {summary.self_consumption_pct.toFixed(1)}%
            </Metric>
            <Text className="text-xs text-gray-500">
              {formatKWh(summary.total_self_consumption_kwh)} used on-site
            </Text>
          </div>

          {/* Grid Import */}
          <div className="bg-white rounded-lg p-4 border border-purple-100">
            <Text className="text-xs text-gray-600">Grid Import</Text>
            <Metric className="text-purple-600">
              {formatKWh(summary.total_grid_import_kwh)}
            </Metric>
            <Text className="text-xs text-gray-500">
              -{(((summary.total_solar_kwh + summary.total_grid_import_kwh - summary.total_grid_export_kwh) / summary.total_solar_kwh) * 100 - 100).toFixed(0)}% vs no solar
            </Text>
          </div>
        </Grid>

        {/* ML Learning Curve Preview */}
        {summary.learning_curve && (
          <div className="bg-white rounded-lg p-4 border border-blue-100">
            <Text className="text-xs font-semibold text-gray-700 mb-3">
              AI Learning Progression
            </Text>
            <Grid numColsSm={3} numColsLg={3} className="gap-3">
              <div>
                <Text className="text-xs text-gray-500">Month 1-2</Text>
                <Text className="text-sm font-semibold text-blue-600">
                  {summary.learning_curve[0]?.savings_pct.toFixed(1)}%
                </Text>
                <Text className="text-xs text-gray-400">Learning Phase</Text>
              </div>
              <div>
                <Text className="text-xs text-gray-500">Month 3-6</Text>
                <Text className="text-sm font-semibold text-blue-600">
                  {summary.learning_curve[3]?.savings_pct.toFixed(1)}%
                </Text>
                <Text className="text-xs text-gray-400">Optimization</Text>
              </div>
              <div>
                <Text className="text-xs text-gray-500">Month 7-12</Text>
                <Text className="text-sm font-semibold text-blue-600">
                  {summary.learning_curve[11]?.savings_pct.toFixed(1)}%
                </Text>
                <Text className="text-xs text-gray-400">Mature Phase</Text>
              </div>
            </Grid>
          </div>
        )}

        {/* Monthly Breakdown Summary */}
        <div className="bg-white rounded-lg p-4 border border-gray-100">
          <Text className="text-xs font-semibold text-gray-700 mb-3">
            Seasonal Breakdown
          </Text>
          <Grid numColsSm={2} numColsLg={4} className="gap-3">
            {summary.seasonal_data.map((season) => (
              <div key={season.season}>
                <Text className="text-xs text-gray-500 capitalize">
                  {season.season}
                </Text>
                <Text className="text-sm font-semibold text-gray-700">
                  {formatKWh(season.total_solar_kwh)}
                </Text>
                <Text className="text-xs text-gray-400">
                  {season.avg_savings_pct.toFixed(1)}% savings
                </Text>
              </div>
            ))}
          </Grid>
        </div>
      </div>
    </Card>
  )
}

export default SolarAnnualCard

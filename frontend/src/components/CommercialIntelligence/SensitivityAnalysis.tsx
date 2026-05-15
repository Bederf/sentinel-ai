/**
 * Sensitivity Analysis / What-If Component
 *
 * Provides tools for analyzing price variance and scenario comparison.
 * Allows sales teams to explore different pricing scenarios and negotiation ranges.
 *
 * Features:
 * - Variance slider (0-50%)
 * - Min/target/max price visualization
 * - Scenario comparison table
 * - Cost impact breakdown
 * - Copy to negotiation button
 *
 * Phase 52-02: Quote Generation UI
 */

import { useState, useMemo } from 'react'

import {
  Copy,
  TrendingUp,
  TrendingDown,
  AlertCircle,
} from 'lucide-react'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts'
import { formatZAR } from '@/lib/api/pricing'
import type { QuoteResponse } from '@/lib/api/pricing'
import { Badge } from '../Badge'

interface SensitivityAnalysisProps {
  quote: QuoteResponse
  onCopyToNegotiation?: (range: { min: number; target: number; max: number }) => void
}

interface ScenarioVariation {
  name: string
  description: string
  variance: number
  resultFee: number
}

export default function SensitivityAnalysis({
  quote,
  onCopyToNegotiation,
}: SensitivityAnalysisProps) {
  const [variance, setVariance] = useState<number>(10)

  // Parse decimal values from API response
  const baseFee = parseFloat(
    typeof quote.recommended_fee_zar === 'string'
      ? quote.recommended_fee_zar
      : String(quote.recommended_fee_zar)
  )

  // Calculate price points based on variance
  const pricePoints = useMemo(() => {
    const varianceDecimal = variance / 100
    const minFee = baseFee * (1 - varianceDecimal)
    const maxFee = baseFee * (1 + varianceDecimal)

    return {
      min: minFee,
      target: baseFee,
      max: maxFee,
      variance,
    }
  }, [baseFee, variance])

  // Pre-defined scenarios for analysis
  const scenarios: ScenarioVariation[] = useMemo(() => {
    const baseVariance = variance
    return [
      {
        name: 'Conservative (Lower Risk)',
        description: 'Slightly under market rate to secure contract',
        variance: Math.max(0, baseVariance - 5),
        resultFee: baseFee * (1 - Math.max(0, baseVariance - 5) / 100),
      },
      {
        name: 'Market Rate',
        description: 'Standard pricing with expected margin',
        variance: baseVariance,
        resultFee: baseFee,
      },
      {
        name: 'Premium (High Service)',
        description: 'Premium for enhanced support/faster response',
        variance: baseVariance + 10,
        resultFee: baseFee * (1 + (baseVariance + 10) / 100),
      },
      {
        name: 'Negotiated Range',
        description: 'Maximum acceptable price (min margin)',
        variance: baseVariance + 20,
        resultFee: baseFee * (1 + (baseVariance + 20) / 100),
      },
    ]
  }, [baseFee, variance])

  // Chart data for visualization
  const chartData = useMemo(() => {
    return [
      {
        name: `Variance -${variance}%`,
        'Fee (ZAR)': Math.round(pricePoints.min),
        'Margin Impact': -variance,
      },
      {
        name: 'Target',
        'Fee (ZAR)': Math.round(baseFee),
        'Margin Impact': 0,
      },
      {
        name: `Variance +${variance}%`,
        'Fee (ZAR)': Math.round(pricePoints.max),
        'Margin Impact': variance,
      },
    ]
  }, [variance, pricePoints, baseFee])

  // Cost impact analysis
  const impactAnalysis = useMemo(() => {
    const minImpact = baseFee - pricePoints.min
    const maxImpact = pricePoints.max - baseFee
    const annualMin = minImpact * 12
    const annualMax = maxImpact * 12

    return {
      monthlyMin: minImpact,
      monthlyMax: maxImpact,
      annualMin,
      annualMax,
      monthlyPercent: variance,
    }
  }, [baseFee, pricePoints, variance])

  // Handle copy to negotiation
  const handleCopyToNegotiation = () => {
    const range = {
      min: pricePoints.min,
      target: pricePoints.target,
      max: pricePoints.max,
    }
    if (onCopyToNegotiation) {
      onCopyToNegotiation(range)
    }
  }

  const tooltipStyle = {
    background: 'var(--color-sentinel-bg-secondary)',
    border: '1px solid var(--color-sentinel-border)',
    borderRadius: 4,
    color: 'var(--color-sentinel-text-primary)',
  }

  return (
    <div className="space-y-6">
      {/* Variance Control */}
      <div
        className="rounded-lg p-4"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <h2 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
          Price Variance Analysis
        </h2>
        <p className="mt-2 text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          Explore different pricing scenarios and negotiation ranges
        </p>

        <div className="mt-6 space-y-4">
          <div>
            <div className="flex items-center justify-between mb-3">
              <p className="font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                Variance Percentage
              </p>
              <Badge className="text-lg font-semibold bg-gray-100 text-gray-800">
                ±{variance}%
              </Badge>
            </div>
            <input
              type="range"
              min="0"
              max="50"
              step="1"
              value={variance}
              onChange={(e) => setVariance(parseInt(e.target.value))}
              className="w-full h-2 rounded-lg appearance-none cursor-pointer"
              style={{ background: 'var(--color-sentinel-bg-secondary)' }}
            />
            <p className="mt-2 text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Adjust variance to see min/max negotiation range (0-50%)
            </p>
          </div>
        </div>
      </div>

      {/* Price Range Summary */}
      <div
        className="rounded-lg p-4"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <h3 className="text-base font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
          Price Range Summary
        </h3>
        <div className="grid grid-cols-3 gap-4 mt-4">
          <div className="space-y-2 p-3 rounded-lg bg-red-50 border border-red-100">
            <p className="text-xs font-medium text-red-900">Minimum</p>
            <div className="text-2xl font-bold text-red-600">
              {formatZAR(pricePoints.min)}
            </div>
            <p className="text-xs text-red-700">-{variance}% below target</p>
          </div>
          <div className="space-y-2 p-3 rounded-lg bg-blue-50 border border-blue-100">
            <p className="text-xs font-medium text-blue-900">Target</p>
            <div className="text-2xl font-bold text-blue-600">
              {formatZAR(pricePoints.target)}
            </div>
            <p className="text-xs text-blue-700">Recommended price</p>
          </div>
          <div className="space-y-2 p-3 rounded-lg bg-green-50 border border-green-100">
            <p className="text-xs font-medium text-green-900">Maximum</p>
            <div className="text-2xl font-bold text-green-600">
              {formatZAR(pricePoints.max)}
            </div>
            <p className="text-xs text-green-700">+{variance}% above target</p>
          </div>
        </div>
      </div>

      {/* Visualization Chart */}
      <div
        className="rounded-lg p-4"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <h3 className="text-base font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
          Price Visualization
        </h3>
        <div className="mt-4" style={{ height: 256 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-sentinel-border)" />
              <XAxis dataKey="name" stroke="var(--color-sentinel-text-secondary)" style={{ fontSize: 12 }} />
              <YAxis stroke="var(--color-sentinel-text-secondary)" style={{ fontSize: 12 }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="Fee (ZAR)" fill="var(--color-sentinel-blue)" radius={[4, 4, 0, 0]} />
              <Legend />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Cost Impact Analysis */}
      <div
        className="rounded-lg p-4"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <h3 className="text-base font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
          Financial Impact Analysis
        </h3>
        <div className="grid grid-cols-2 gap-4 mt-4">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <TrendingDown className="h-4 w-4 text-red-500" />
              <p className="font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>Downside Risk</p>
            </div>
            <div className="space-y-1">
              <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Monthly loss vs. target:
              </p>
              <p className="text-lg font-semibold text-red-600">
                -{formatZAR(impactAnalysis.monthlyMin)}
              </p>
              <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Annual loss:
              </p>
              <p className="text-lg font-semibold text-red-600">
                -{formatZAR(impactAnalysis.annualMin)}
              </p>
            </div>
          </div>
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-green-500" />
              <p className="font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>Upside Opportunity</p>
            </div>
            <div className="space-y-1">
              <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Monthly gain vs. target:
              </p>
              <p className="text-lg font-semibold text-green-600">
                +{formatZAR(impactAnalysis.monthlyMax)}
              </p>
              <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Annual gain:
              </p>
              <p className="text-lg font-semibold text-green-600">
                +{formatZAR(impactAnalysis.annualMax)}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Scenario Comparison */}
      <div
        className="rounded-lg p-4"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <h3 className="text-base font-semibold mb-4" style={{ color: 'var(--color-sentinel-text-primary)' }}>
          Pricing Scenario Comparison
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr
                className="text-left text-xs font-medium uppercase tracking-wider"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              >
                <th className="pb-2">Scenario</th>
                <th className="pb-2">Description</th>
                <th className="pb-2 text-right">Monthly Fee</th>
                <th className="pb-2 text-right">Variance</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((scenario) => (
                <tr
                  key={scenario.name}
                  className="border-b"
                  style={{ borderColor: 'var(--color-sentinel-border)' }}
                >
                  <td className="py-2 pr-4 text-sm font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {scenario.name}
                  </td>
                  <td className="py-2 pr-4 text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    {scenario.description}
                  </td>
                  <td className="py-2 pr-4 text-sm text-right font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {formatZAR(scenario.resultFee)}
                  </td>
                  <td className="py-2 text-right">
                    <Badge
                      className={
                        scenario.variance < variance
                          ? 'bg-gray-100 text-gray-800'
                          : scenario.variance > variance
                            ? 'bg-green-100 text-green-800'
                            : 'bg-blue-100 text-blue-800'
                      }
                    >
                      {scenario.variance > 0 ? '+' : ''}
                      {scenario.variance}%
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Risk Notice */}
      {variance > 25 && (
        <div
          className="rounded-lg p-4"
          style={{
            background: 'rgba(245, 158, 11, 0.1)',
            border: '1px solid rgba(245, 158, 11, 0.3)',
          }}
        >
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-amber-600 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-base font-semibold" style={{ color: 'var(--color-sentinel-amber)' }}>
                High Variance
              </h3>
              <p className="text-sm mt-1" style={{ color: 'rgba(180, 83, 9, 0.9)' }}>
                Variance above 25% may impact margins significantly. Consider
                your cost structure and competitive positioning before offering
                quotes in this range.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex gap-3 mt-6">
        <button
          disabled={variance === 10}
          onClick={() => setVariance(10)}
          className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium disabled:opacity-50"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            color: 'var(--color-sentinel-text-primary)',
            border: '1px solid var(--color-sentinel-border)',
          }}
        >
          Reset to Default
        </button>
        <button
          onClick={handleCopyToNegotiation}
          className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium text-white"
          style={{ background: 'var(--color-sentinel-blue)' }}
        >
          <Copy className="h-4 w-4" />
          Copy Range to Negotiation
        </button>
      </div>
    </div>
  )
}

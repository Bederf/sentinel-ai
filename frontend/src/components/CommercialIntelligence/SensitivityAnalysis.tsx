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
  Card,
  Title,
  Text,
  Button,
  BarChart,
  LineChart,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  Badge,
  Grid,
  Col,
  Slider,
  ToggleButton,
  ToggleButtonGroup,
} from '@tremor/react'
import {
  Copy,
  TrendingUp,
  TrendingDown,
  DollarSign,
  AlertCircle,
} from 'lucide-react'
import {
  formatZAR,
  formatPercent,
  type QuoteResponse,
} from '@/lib/api'

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
  const [viewMode, setViewMode] = useState<'chart' | 'table'>('chart')

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

  return (
    <div className="space-y-6">
      {/* Variance Control */}
      <Card>
        <Title>Price Variance Analysis</Title>
        <Text className="text-tremor-content-subtitle mt-2">
          Explore different pricing scenarios and negotiation ranges
        </Text>

        <div className="mt-6 space-y-4">
          <div>
            <div className="flex items-center justify-between mb-3">
              <Text className="font-medium">Variance Percentage</Text>
              <Badge className="text-lg font-semibold">
                ±{variance}%
              </Badge>
            </div>
            <Slider
              value={[variance]}
              onValueChange={(values) => setVariance(values[0])}
              min={0}
              max={50}
              step={1}
              className="w-full"
            />
            <Text className="text-tremor-label text-tremor-content-subtitle mt-2">
              Adjust variance to see min/max negotiation range (0-50%)
            </Text>
          </div>
        </div>
      </Card>

      {/* Price Range Summary */}
      <Card>
        <Title className="text-base">Price Range Summary</Title>
        <Grid numItems={3} className="gap-4 mt-4">
          <Col>
            <div className="space-y-2 p-3 rounded-lg bg-red-50 border border-red-100">
              <Text className="text-tremor-label font-medium text-red-900">
                Minimum
              </Text>
              <div className="text-2xl font-bold text-red-600">
                {formatZAR(pricePoints.min)}
              </div>
              <Text className="text-tremor-label text-red-700 text-xs">
                -{variance}% below target
              </Text>
            </div>
          </Col>
          <Col>
            <div className="space-y-2 p-3 rounded-lg bg-blue-50 border border-blue-100">
              <Text className="text-tremor-label font-medium text-blue-900">
                Target
              </Text>
              <div className="text-2xl font-bold text-blue-600">
                {formatZAR(pricePoints.target)}
              </div>
              <Text className="text-tremor-label text-blue-700 text-xs">
                Recommended price
              </Text>
            </div>
          </Col>
          <Col>
            <div className="space-y-2 p-3 rounded-lg bg-green-50 border border-green-100">
              <Text className="text-tremor-label font-medium text-green-900">
                Maximum
              </Text>
              <div className="text-2xl font-bold text-green-600">
                {formatZAR(pricePoints.max)}
              </div>
              <Text className="text-tremor-label text-green-700 text-xs">
                +{variance}% above target
              </Text>
            </div>
          </Col>
        </Grid>
      </Card>

      {/* Visualization Toggle */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <Title className="text-base">Visualization</Title>
          <ToggleButtonGroup
            defaultValue="chart"
            onValueChange={(val) => setViewMode(val as 'chart' | 'table')}
          >
            <ToggleButton value="chart" text="Chart" />
            <ToggleButton value="table" text="Table" />
          </ToggleButtonGroup>
        </div>

        {viewMode === 'chart' ? (
          <BarChart
            data={chartData}
            index="name"
            categories={['Fee (ZAR)']}
            colors={['blue']}
            showYAxis={true}
            showTooltip={true}
            showLegend={true}
            yAxisLabel="Fee (ZAR)"
            className="mt-4 h-64"
          />
        ) : (
          <Table className="mt-4">
            <TableHead>
              <TableRow>
                <TableCell>Scenario</TableCell>
                <TableCell className="text-right">Fee</TableCell>
                <TableCell className="text-right">Variance</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {chartData.map((row) => (
                <TableRow key={row.name}>
                  <TableCell>{row.name}</TableCell>
                  <TableCell className="text-right font-semibold">
                    {formatZAR(row['Fee (ZAR)'])}
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge
                      variant={
                        row['Margin Impact'] < 0
                          ? 'neutral'
                          : row['Margin Impact'] > 0
                            ? 'success'
                            : 'default'
                      }
                    >
                      {row['Margin Impact'] > 0 ? '+' : ''}
                      {row['Margin Impact']}%
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {/* Cost Impact Analysis */}
      <Card>
        <Title className="text-base">Financial Impact Analysis</Title>
        <Grid numItems={2} className="gap-4 mt-4">
          <Col>
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <TrendingDown className="h-4 w-4 text-red-500" />
                <Text className="font-medium">Downside Risk</Text>
              </div>
              <div className="space-y-1">
                <Text className="text-tremor-label text-tremor-content-subtitle">
                  Monthly loss vs. target:
                </Text>
                <Text className="text-lg font-semibold text-red-600">
                  -{formatZAR(impactAnalysis.monthlyMin)}
                </Text>
                <Text className="text-tremor-label text-tremor-content-subtitle">
                  Annual loss:
                </Text>
                <Text className="text-lg font-semibold text-red-600">
                  -{formatZAR(impactAnalysis.annualMin)}
                </Text>
              </div>
            </div>
          </Col>
          <Col>
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-green-500" />
                <Text className="font-medium">Upside Opportunity</Text>
              </div>
              <div className="space-y-1">
                <Text className="text-tremor-label text-tremor-content-subtitle">
                  Monthly gain vs. target:
                </Text>
                <Text className="text-lg font-semibold text-green-600">
                  +{formatZAR(impactAnalysis.monthlyMax)}
                </Text>
                <Text className="text-tremor-label text-tremor-content-subtitle">
                  Annual gain:
                </Text>
                <Text className="text-lg font-semibold text-green-600">
                  +{formatZAR(impactAnalysis.annualMax)}
                </Text>
              </div>
            </div>
          </Col>
        </Grid>
      </Card>

      {/* Scenario Comparison */}
      <Card>
        <Title className="text-base">Pricing Scenario Comparison</Title>
        <Table className="mt-4">
          <TableHead>
            <TableRow>
              <TableCell>Scenario</TableCell>
              <TableCell>Description</TableCell>
              <TableCell className="text-right">Monthly Fee</TableCell>
              <TableCell className="text-right">Variance</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {scenarios.map((scenario) => (
              <TableRow key={scenario.name}>
                <TableCell className="font-medium">{scenario.name}</TableCell>
                <TableCell className="text-tremor-label">
                  {scenario.description}
                </TableCell>
                <TableCell className="text-right font-semibold">
                  {formatZAR(scenario.resultFee)}
                </TableCell>
                <TableCell className="text-right">
                  <Badge
                    variant={
                      scenario.variance < variance
                        ? 'neutral'
                        : scenario.variance > variance
                          ? 'success'
                          : 'default'
                    }
                  >
                    {scenario.variance > 0 ? '+' : ''}
                    {scenario.variance}%
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {/* Risk Notice */}
      {variance > 25 && (
        <Card className="bg-amber-50 border border-amber-200">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-amber-600 mt-1 flex-shrink-0" />
            <div>
              <Title className="text-amber-900 text-base">High Variance</Title>
              <Text className="text-amber-800 text-sm mt-1">
                Variance above 25% may impact margins significantly. Consider
                your cost structure and competitive positioning before offering
                quotes in this range.
              </Text>
            </div>
          </div>
        </Card>
      )}

      {/* Action Buttons */}
      <div className="flex gap-3 mt-6">
        <Button
          variant="secondary"
          disabled={variance === 10}
          onClick={() => setVariance(10)}
        >
          Reset to Default
        </Button>
        <Button
          variant="primary"
          icon={Copy}
          onClick={handleCopyToNegotiation}
        >
          Copy Range to Negotiation
        </Button>
      </div>
    </div>
  )
}

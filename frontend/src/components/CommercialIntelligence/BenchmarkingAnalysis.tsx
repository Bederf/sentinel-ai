// @ts-nocheck
import React, { useState, useMemo, useEffect } from 'react'
import {
  Card,
  CardHeader,
  Title,
  Text,
  BarChart,
  PieChart,
  LineChart,
  Table,
  TableHead,
  TableRow,
  TableHeaderCell,
  TableBody,
  TableCell,
  Badge,
  Button,
  Flex,
  Grid,
  Select,
  SelectItem,
  Metric,
} from '@tremor/react'
import { ArrowUpIcon, ArrowDownIcon, DocumentDownloadIcon } from '@heroicons/react/24/solid'
import { pricingApi } from '@/lib/api'
import type { EquipmentBenchmarkResponse, WinLossAnalysisResponse, PortfolioBenchmarkResponse } from '@/lib/api'

export function BenchmarkingAnalysis() {
  const [selectedEquipmentType, setSelectedEquipmentType] = useState('CHILLER')
  const [selectedSlaTier, setSelectedSlaTier] = useState<'basic' | 'standard' | 'premium' | 'enterprise'>('standard')
  const [benchmarkData, setBenchmarkData] = useState<EquipmentBenchmarkResponse | null>(null)
  const [winLossData, setWinLossData] = useState<WinLossAnalysisResponse | null>(null)
  const [portfolioData, setPortfolioData] = useState<PortfolioBenchmarkResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      setError('')
      try {
        const [benchmark, winLoss, portfolio] = await Promise.all([
          pricingApi.getEquipmentBenchmarks(selectedEquipmentType, selectedSlaTier),
          pricingApi.getWinLossAnalysis(),
          pricingApi.getPortfolioBenchmarks(false),
        ])
        setBenchmarkData(benchmark)
        setWinLossData(winLoss)
        setPortfolioData(portfolio)
      } catch (err) {
        setError(`Failed to load benchmarking data: ${err instanceof Error ? err.message : 'Unknown error'}`)
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [selectedEquipmentType, selectedSlaTier])

  const marketComparisonChart = useMemo(() => {
    if (!benchmarkData) return []
    const avgFee = typeof benchmarkData.avg_fee_zar === 'string'
      ? parseFloat(benchmarkData.avg_fee_zar)
      : benchmarkData.avg_fee_zar || 0

    return [
      {
        name: `${selectedEquipmentType} (${selectedSlaTier})`,
        'Market Avg': avgFee,
        'Your Portfolio Avg': avgFee * 0.95, // Placeholder - would come from portfolio data
        'Range Min': benchmarkData.min_fee_zar ? (typeof benchmarkData.min_fee_zar === 'string'
          ? parseFloat(benchmarkData.min_fee_zar)
          : benchmarkData.min_fee_zar) : 0,
        'Range Max': benchmarkData.max_fee_zar ? (typeof benchmarkData.max_fee_zar === 'string'
          ? parseFloat(benchmarkData.max_fee_zar)
          : benchmarkData.max_fee_zar) : 0,
      },
    ]
  }, [benchmarkData, selectedEquipmentType, selectedSlaTier])

  const winLossChart = useMemo(() => {
    if (!winLossData) return []
    return [
      {
        name: 'Quote Status',
        'Won': winLossData.total_won,
        'Lost': winLossData.total_lost,
        'Pending': winLossData.total_pending,
      },
    ]
  }, [winLossData])

  const lostReasonsChart = useMemo(() => {
    if (!winLossData) return []
    return Object.entries(winLossData.lost_reasons).map(([reason, count]) => ({
      name: reason,
      count,
    }))
  }, [winLossData])

  const contractVarianceChart = useMemo(() => {
    if (!portfolioData) return []

    // Combine all contract categories for trend visualization
    const allContracts = [
      ...portfolioData.above_market.map(c => ({ ...c, category: 'Above Market' })),
      ...portfolioData.at_market.map(c => ({ ...c, category: 'At Market' })),
      ...portfolioData.below_market.map(c => ({ ...c, category: 'Below Market' })),
    ]

    const grouped = allContracts.reduce((acc, curr) => {
      const idx = acc.findIndex(x => x.name === curr.category)
      if (idx >= 0) {
        acc[idx].count += 1
      } else {
        acc.push({ name: curr.category, count: 1 })
      }
      return acc
    }, [] as Array<{ name: string; count: number }>)

    return grouped
  }, [portfolioData])

  const exportBenchmarkReport = async () => {
    // Placeholder for PDF export functionality
    console.log('Exporting benchmarking report as PDF')
    alert('PDF export feature to be implemented')
  }

  const exportContractComparison = async () => {
    // Placeholder for CSV export functionality
    if (portfolioData) {
      const csv = `contract_id,variance_pct,category\n${
        [
          ...portfolioData.above_market.map(c => `${c.contract_id},${c.variance_pct},Above Market`),
          ...portfolioData.at_market.map(c => `${c.contract_id},${c.variance_pct},At Market`),
          ...portfolioData.below_market.map(c => `${c.contract_id},${c.variance_pct},Below Market`),
        ].join('\n')
      }`

      const blob = new Blob([csv], { type: 'text/csv' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'contract-comparison.csv'
      a.click()
      window.URL.revokeObjectURL(url)
    }
  }

  return (
    <div className="space-y-6">
      {/* Portfolio Overview */}
      <Card>
        <CardHeader>
          <Title>Portfolio Overview</Title>
        </CardHeader>
        <Grid numItems={1} numItemsSm={2} numItemsLg={4} className="gap-4">
          <Card>
            <Text className="text-gray-600">Total Contracts</Text>
            <Metric>{portfolioData?.portfolio_size || 0}</Metric>
          </Card>
          <Card>
            <Text className="text-gray-600">Win Rate</Text>
            <Metric>{winLossData?.win_rate_pct.toFixed(1) || 0}%</Metric>
          </Card>
          <Card>
            <Text className="text-gray-600">Avg Negotiation Time</Text>
            <Metric>{winLossData?.avg_negotiation_days || 0} days</Metric>
          </Card>
          <Card>
            <Text className="text-gray-600">Avg Negotiation Discount</Text>
            <Metric>{winLossData?.avg_discount_pct.toFixed(1) || 0}%</Metric>
          </Card>
        </Grid>
      </Card>

      {/* Equipment Type Benchmarking */}
      <Card>
        <CardHeader>
          <Title>Equipment Type Benchmarking</Title>
          <Text>Compare your pricing against market averages</Text>
        </CardHeader>
        <Flex className="gap-4 mb-6">
          <div className="flex-1">
            <Text className="text-sm text-gray-600 mb-2">Equipment Type</Text>
            <Select value={selectedEquipmentType} onValueChange={setSelectedEquipmentType}>
              <SelectItem value="CHILLER">CHILLER</SelectItem>
              <SelectItem value="AHU">AHU</SelectItem>
              <SelectItem value="FCU">FCU</SelectItem>
              <SelectItem value="PUMP">PUMP</SelectItem>
              <SelectItem value="GENERATOR">GENERATOR</SelectItem>
              <SelectItem value="UPS">UPS</SelectItem>
            </Select>
          </div>
          <div className="flex-1">
            <Text className="text-sm text-gray-600 mb-2">SLA Tier</Text>
            <Select value={selectedSlaTier} onValueChange={(val) => setSelectedSlaTier(val as any)}>
              <SelectItem value="basic">Basic</SelectItem>
              <SelectItem value="standard">Standard</SelectItem>
              <SelectItem value="premium">Premium</SelectItem>
              <SelectItem value="enterprise">Enterprise</SelectItem>
            </Select>
          </div>
        </Flex>

        {benchmarkData && (
          <>
            <Grid numItems={1} numItemsSm={3} className="gap-4 mb-6">
              <Card>
                <Text className="text-gray-600">Market Average Fee</Text>
                <Metric>
                  R{typeof benchmarkData.avg_fee_zar === 'string'
                    ? parseFloat(benchmarkData.avg_fee_zar).toLocaleString('en-ZA', { maximumFractionDigits: 0 })
                    : benchmarkData.avg_fee_zar?.toLocaleString('en-ZA', { maximumFractionDigits: 0 }) || 0}
                </Metric>
              </Card>
              <Card>
                <Text className="text-gray-600">Market Sample Size</Text>
                <Metric>{benchmarkData.sample_size} contracts</Metric>
              </Card>
              <Card>
                <Text className="text-gray-600">Confidence Level</Text>
                <Metric>{benchmarkData.confidence_pct}%</Metric>
              </Card>
            </Grid>

            {benchmarkData.min_fee_zar && benchmarkData.max_fee_zar && (
              <div>
                <Text className="mb-4 font-semibold">Market Price Range</Text>
                <BarChart
                  data={[
                    {
                      name: 'Price Range',
                      'Min': typeof benchmarkData.min_fee_zar === 'string' ? parseFloat(benchmarkData.min_fee_zar) : benchmarkData.min_fee_zar,
                      'Avg': typeof benchmarkData.avg_fee_zar === 'string' ? parseFloat(benchmarkData.avg_fee_zar) : benchmarkData.avg_fee_zar || 0,
                      'Max': typeof benchmarkData.max_fee_zar === 'string' ? parseFloat(benchmarkData.max_fee_zar) : benchmarkData.max_fee_zar,
                    },
                  ]}
                  index="name"
                  categories={['Min', 'Avg', 'Max']}
                  colors={['blue', 'amber', 'rose']}
                  showLegend={true}
                />
              </div>
            )}
          </>
        )}
      </Card>

      {/* Contract-Level Comparison */}
      {portfolioData && (
        <Card>
          <CardHeader>
            <Title>Contract-Level Market Comparison</Title>
            <Text>Identify contracts above, at, or below market pricing</Text>
          </CardHeader>

          <div className="mb-6">
            <Text className="mb-4 font-semibold">Portfolio Variance Distribution</Text>
            <PieChart
              data={contractVarianceChart}
              category="count"
              index="name"
              colors={['rose', 'blue', 'emerald']}
              showAnimation={true}
            />
          </div>

          {/* Top Opportunities */}
          <Grid numItems={1} numItemsSm={2} className="gap-4">
            <Card>
              <CardHeader>
                <Title>Top Underpriced Contracts</Title>
                <Text className="text-sm">Opportunities to raise fees</Text>
              </CardHeader>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableHeaderCell>Contract</TableHeaderCell>
                    <TableHeaderCell>Opportunity</TableHeaderCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {portfolioData.top_underpriced.slice(0, 5).map((contract) => (
                    <TableRow key={contract.contract_id}>
                      <TableCell>{contract.contract_id}</TableCell>
                      <TableCell>
                        <Badge color="emerald">
                          R{typeof contract.opportunity_zar === 'string'
                            ? parseFloat(contract.opportunity_zar).toLocaleString('en-ZA', { maximumFractionDigits: 0 })
                            : contract.opportunity_zar.toLocaleString('en-ZA', { maximumFractionDigits: 0 })}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>

            <Card>
              <CardHeader>
                <Title>Top Overpriced Contracts</Title>
                <Text className="text-sm">Risk of losing on renewal</Text>
              </CardHeader>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableHeaderCell>Contract</TableHeaderCell>
                    <TableHeaderCell>Risk</TableHeaderCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {portfolioData.top_overpriced.slice(0, 5).map((contract) => (
                    <TableRow key={contract.contract_id}>
                      <TableCell>{contract.contract_id}</TableCell>
                      <TableCell>
                        <Badge color="rose">
                          R{typeof contract.risk_zar === 'string'
                            ? parseFloat(contract.risk_zar).toLocaleString('en-ZA', { maximumFractionDigits: 0 })
                            : contract.risk_zar.toLocaleString('en-ZA', { maximumFractionDigits: 0 })}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          </Grid>
        </Card>
      )}

      {/* Win/Loss Analysis */}
      {winLossData && (
        <>
          <Card>
            <CardHeader>
              <Title>Quote Status Distribution</Title>
            </CardHeader>
            <PieChart
              data={winLossChart}
              category={Object.keys(winLossChart[0] || {}).find(k => k !== 'name') || ''}
              index="name"
              colors={['emerald', 'rose', 'amber']}
              showAnimation={true}
            />
          </Card>

          {lostReasonsChart.length > 0 && (
            <Card>
              <CardHeader>
                <Title>Lost Quote Reasons</Title>
                <Text>Analysis of why quotes were rejected</Text>
              </CardHeader>
              <BarChart
                data={lostReasonsChart}
                index="name"
                categories={['count']}
                colors={['rose']}
                showLegend={false}
              />
            </Card>
          )}
        </>
      )}

      {/* Market Insights */}
      {portfolioData && (
        <Card>
          <CardHeader>
            <Title>Market Positioning & Insights</Title>
          </CardHeader>
          <div className="space-y-4">
            <div className="border-l-4 border-blue-600 pl-4">
              <Text className="font-semibold">Market Average Position</Text>
              <Text className="text-sm text-gray-700 mt-1">
                Your portfolio is {portfolioData.avg_variance_pct > 0 ? 'above' : 'below'} market average by{' '}
                {Math.abs(portfolioData.avg_variance_pct).toFixed(1)}%
              </Text>
            </div>

            {portfolioData.above_market.length > 0 && (
              <div className="border-l-4 border-rose-600 pl-4">
                <Text className="font-semibold">{portfolioData.above_market.length} Contracts Above Market</Text>
                <Text className="text-sm text-gray-700 mt-1">
                  Consider competitive positioning and risk of loss during renewal
                </Text>
              </div>
            )}

            {portfolioData.below_market.length > 0 && (
              <div className="border-l-4 border-emerald-600 pl-4">
                <Text className="font-semibold">{portfolioData.below_market.length} Contracts Below Market</Text>
                <Text className="text-sm text-gray-700 mt-1">
                  Opportunity to increase fees at renewal or through renegotiation
                </Text>
              </div>
            )}

            {portfolioData.market_opportunities && portfolioData.market_opportunities.length > 0 && (
              <div className="border-l-4 border-amber-600 pl-4">
                <Text className="font-semibold">Identified Opportunities</Text>
                <ul className="list-disc list-inside space-y-1 mt-2">
                  {portfolioData.market_opportunities.map((opp, idx) => (
                    <li key={idx} className="text-sm text-gray-700">{opp}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Export Options */}
      <Card>
        <CardHeader>
          <Title>Export Options</Title>
        </CardHeader>
        <Flex className="gap-4">
          <Button onClick={exportBenchmarkReport} variant="secondary">
            <DocumentDownloadIcon className="w-4 h-4 mr-2" />
            Download Benchmarks Report (PDF)
          </Button>
          <Button onClick={exportContractComparison} variant="secondary">
            <DocumentDownloadIcon className="w-4 h-4 mr-2" />
            Export Contract Comparison (CSV)
          </Button>
        </Flex>
      </Card>

      {error && (
        <Card>
          <Text className="text-red-600">{error}</Text>
        </Card>
      )}

      {loading && (
        <Card>
          <Text className="text-center text-gray-600 py-8">Loading benchmarking data...</Text>
        </Card>
      )}
    </div>
  )
}

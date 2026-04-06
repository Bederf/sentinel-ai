/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
import React, { useState, useMemo } from 'react'
import {
  Card,
  CardHeader,
  Title,
  Text,
  BarChart,
  PieChart,
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
} from '@tremor/react'
import { ArrowUpIcon, ArrowDownIcon, CheckCircleIcon } from '@heroicons/react/24/solid'
import { pricingApi } from '@/lib/api'
import type { RenewalQuote, RenegotiationAnalysis } from '@/lib/api'

interface RenewalPricingDashboardProps {
  selectedContractId?: string
}

export function RenewalPricingDashboard({ selectedContractId }: RenewalPricingDashboardProps) {
  const [contractId, setContractId] = useState(selectedContractId || '')
  const [renewalData, setRenewalData] = useState<RenewalQuote | null>(null)
  const [renegotiationData, setRenegotiationData] = useState<RenegotiationAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const feeChange = useMemo(() => {
    if (!renewalData) return null
    const change = renewalData.recommended_monthly_fee - renewalData.original_monthly_fee
    const changePct = renewalData.fee_change_pct
    return { change, changePct }
  }, [renewalData])

  const handleLoadRenewal = async () => {
    if (!contractId) return
    setLoading(true)
    setError('')
    try {
      // Fetch renewal pricing
      const renewal = await pricingApi.getRenewalPrice(contractId)
      setRenewalData(renewal)

      // Fetch renegotiation analysis
      const renegotiation = await pricingApi.analyzeRenegotiation(contractId)
      setRenegotiationData(renegotiation)
    } catch (err) {
      setError(`Failed to load renewal data: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }

  const getBadgeColor = (confidence: string) => {
    switch (confidence) {
      case 'high':
        return 'success'
      case 'medium':
        return 'warning'
      case 'low':
        return 'rose'
      default:
        return 'gray'
    }
  }

  const _getFeeChangeColor = (changePct: number) => {
    if (changePct > 10) return 'rose'
    if (changePct > 0) return 'amber'
    return 'emerald'
  }

  const driverImpactData = useMemo(() => {
    if (!renewalData || renewalData.drivers.length === 0) return []
    // Create approximate distribution
    const baseImpact = 100 / renewalData.drivers.length
    return renewalData.drivers.map((driver, _idx) => ({
      name: driver,
      value: baseImpact,
    }))
  }, [renewalData])

  const renegotiationTableData = useMemo(() => {
    if (!renegotiationData) return []
    return renegotiationData.options.map(option => ({
      ...option,
      isRecommended: option.option_type === renegotiationData.recommended_option,
    }))
  }, [renegotiationData])

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <Title>Contract Renewal Analysis</Title>
          <Text>Select a contract to analyze renewal pricing options</Text>
        </CardHeader>
        <Flex className="gap-4">
          <div className="flex-1">
            <select
              value={contractId}
              onChange={(event) => setContractId(event.target.value)}
              className="w-full rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
              style={{
                background: "var(--color-grafana-bg-secondary)",
                border: "1px solid var(--color-grafana-border)",
                color: "var(--color-grafana-text-primary)",
                boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                outline: "none",
              }}
              aria-label="Select contract"
            >
              <option value="">-- Select contract --</option>
              {/* In production, populate from contracts list */}
              <option value="seed-contract-1">Seed Contract #1</option>
              <option value="seed-contract-2">Seed Contract #2</option>
            </select>
          </div>
          <Button onClick={handleLoadRenewal} disabled={!contractId || loading}>
            {loading ? 'Loading...' : 'Analyze Renewal'}
          </Button>
        </Flex>
        {error && <Text className="text-red-600 mt-4">{error}</Text>}
      </Card>

      {renewalData && (
        <>
          {/* Renewal Recommendation Card */}
          <Card>
            <CardHeader>
              <Title>Renewal Pricing Recommendation</Title>
              <Flex className="gap-2 mt-2">
                <Badge color={getBadgeColor(renewalData.confidence)}>
                  Confidence: {renewalData.confidence}
                </Badge>
              </Flex>
            </CardHeader>
            <Grid className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <Card>
                <Text className="text-gray-600">Original Monthly Fee</Text>
                <Title className="text-2xl">
                  R{renewalData.original_monthly_fee.toLocaleString('en-ZA', { maximumFractionDigits: 2 })}
                </Title>
              </Card>

              <Card>
                <Text className="text-gray-600">Recommended Renewal Fee</Text>
                <Title className="text-2xl">
                  R{renewalData.recommended_monthly_fee.toLocaleString('en-ZA', { maximumFractionDigits: 2 })}
                </Title>
              </Card>

              <Card>
                <Text className="text-gray-600">Fee Change</Text>
                <Flex className="gap-2 items-center mt-2">
                  <Title className="text-2xl">
                    {feeChange?.changePct && Math.abs(feeChange.changePct) > 0.01
                      ? `${feeChange.changePct > 0 ? '+' : ''}${feeChange.changePct.toFixed(1)}%`
                      : '0%'}
                  </Title>
                  {feeChange?.changePct && Math.abs(feeChange.changePct) > 0.01 && (
                    <>
                      {feeChange.changePct > 0 ? (
                        <ArrowUpIcon className="w-6 h-6 text-red-600" />
                      ) : (
                        <ArrowDownIcon className="w-6 h-6 text-green-600" />
                      )}
                    </>
                  )}
                </Flex>
              </Card>
            </Grid>

            {/* Fee Comparison Chart */}
            <div className="mt-6">
              <Text className="mb-4 font-semibold">Fee Comparison</Text>
              <BarChart
                data={[
                  {
                    name: 'Renewal Pricing',
                    'Original Fee': renewalData.original_monthly_fee,
                    'Recommended Fee': renewalData.recommended_monthly_fee,
                  },
                ]}
                index="name"
                categories={['Original Fee', 'Recommended Fee']}
                colors={['blue', 'amber']}
                showLegend={true}
              />
            </div>

            {/* Pricing Drivers */}
            <div className="mt-6">
              <Text className="mb-4 font-semibold">Factors Affecting Pricing</Text>
              <div className="space-y-2">
                {renewalData.drivers.map((driver, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    <CheckCircleIcon className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                    <Text>{driver}</Text>
                  </div>
                ))}
              </div>
            </div>

            {/* Assumptions */}
            <div className="mt-6">
              <Text className="mb-4 font-semibold text-gray-600">Key Assumptions</Text>
              <div className="space-y-1 text-sm text-gray-700">
                {renewalData.assumptions.map((assumption, idx) => (
                  <Text key={idx} className="text-xs">• {assumption}</Text>
                ))}
              </div>
            </div>
          </Card>

          {/* Driver Impact Distribution */}
          {driverImpactData.length > 0 && (
            <Card>
              <CardHeader>
                <Title>Pricing Driver Impact</Title>
              </CardHeader>
              <PieChart
                data={driverImpactData}
                category="value"
                index="name"
                colors={['blue', 'amber', 'rose', 'emerald', 'purple']}
                showAnimation={true}
              />
            </Card>
          )}

          {/* Renegotiation Options */}
          {renegotiationData && (
            <Card>
              <CardHeader>
                <Title>Renegotiation Options Analysis</Title>
                <Text>Three scenarios for contract renewal with NPV analysis</Text>
              </CardHeader>

              <Table>
                <TableHead>
                  <TableRow>
                    <TableHeaderCell>Option</TableHeaderCell>
                    <TableHeaderCell>Description</TableHeaderCell>
                    <TableHeaderCell>Recommended Fee</TableHeaderCell>
                    <TableHeaderCell>3-Year NPV</TableHeaderCell>
                    <TableHeaderCell>ROI %</TableHeaderCell>
                    <TableHeaderCell>Status</TableHeaderCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {renegotiationTableData.map((option) => (
                    <TableRow key={option.option_type}>
                      <TableCell>
                        <Badge
                          color={
                            option.option_type === 'maintain'
                              ? 'blue'
                              : option.option_type === 'invest'
                                ? 'green'
                                : 'amber'
                          }
                        >
                          {option.option_type.charAt(0).toUpperCase() + option.option_type.slice(1)}
                        </Badge>
                      </TableCell>
                      <TableCell>{option.description}</TableCell>
                      <TableCell>
                        R{option.recommended_fee.toLocaleString('en-ZA', { maximumFractionDigits: 2 })}
                      </TableCell>
                      <TableCell>
                        R{option.estimated_npv_zar.toLocaleString('en-ZA', { maximumFractionDigits: 0 })}
                      </TableCell>
                      <TableCell>{option.roi_pct.toFixed(1)}%</TableCell>
                      <TableCell>
                        {option.isRecommended && (
                          <Badge color="success">Recommended</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Implementation Notes */}
              <div className="mt-6 space-y-4">
                {renegotiationData.options.map((option) => (
                  <div key={option.option_type} className="border-t pt-4">
                    <Text className="font-semibold mb-2">
                      {option.option_type.charAt(0).toUpperCase() + option.option_type.slice(1)} Option - Key Points
                    </Text>
                    <ul className="space-y-1 text-sm text-gray-700">
                      {option.implementation_notes.map((note, idx) => (
                        <li key={idx} className="flex gap-2">
                          <span className="text-blue-600">•</span>
                          <span>{note}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Client Communication Template */}
          <Card>
            <CardHeader>
              <Title>Client Communication Template</Title>
              <Text>Use this template for renewal proposal email</Text>
            </CardHeader>
            <div className="bg-gray-50 p-4 rounded-lg text-sm space-y-3">
              <p>
                <strong>Subject:</strong> Contract Renewal Proposal - [Contract ID]
              </p>
              <p>
                <strong>Dear [Client Name],</strong>
              </p>
              <p>
                We are pleased to propose renewal terms for your facilities maintenance contract. Based on our
                analysis of current market conditions and your asset performance, we recommend a renewal fee of{' '}
                <strong>R{renewalData.recommended_monthly_fee.toLocaleString('en-ZA', { maximumFractionDigits: 2 })}</strong>.
              </p>
              <p>
                <strong>Key factors in this proposal:</strong>
              </p>
              <ul className="list-disc list-inside space-y-1 ml-2">
                {renewalData.drivers.map((driver, idx) => (
                  <li key={idx}>{driver}</li>
                ))}
              </ul>
              <p>
                This represents a {feeChange?.changePct && Math.abs(feeChange.changePct) > 0.01 ? `${feeChange.changePct > 0 ? '+' : ''}${feeChange.changePct.toFixed(1)}%` : '0%'} adjustment
                from your current fee, reflecting the current market dynamics and your specific operational needs.
              </p>
              <p>
                <strong>Best regards,<br />
                  [Your Name]</strong>
              </p>
            </div>

            <Flex className="gap-3 mt-6">
              <Button>Email Proposal</Button>
              <Button variant="secondary">Mark as Renewed</Button>
              <Button variant="secondary" color="red">
                Skip Renewal
              </Button>
            </Flex>
          </Card>
        </>
      )}

      {!renewalData && !error && contractId && (
        <Card>
          <Text className="text-center text-gray-600 py-8">
            Select a contract and click "Analyze Renewal" to see pricing recommendations
          </Text>
        </Card>
      )}
    </div>
  )
}

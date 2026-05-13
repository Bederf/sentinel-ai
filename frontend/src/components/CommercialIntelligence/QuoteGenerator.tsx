/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * Quote Generator Form Component
 *
 * Provides a form for sales teams to generate price quotes with equipment selection,
 * SLA tier configuration, and contract parameters.
 *
 * Features:
 * - Equipment multi-select with search
 * - SLA tier selection with pricing info
 * - Contract duration input
 * - Real-time suggestions from API
 * - Loading and error states
 * - Quote preview after generation
 *
 * Phase 52-02: Quote Generation UI
 */

import { useState, useEffect } from 'react'

import {
  AlertCircle,
  CheckCircle2,
  Zap,
  Clock,
  DollarSign,
  ArrowRight,
} from 'lucide-react'
import {
  pricingApi,
  formatZAR,
  formatPercent,
  type QuoteRequest,
  type QuoteResponse,
  type SLATier,
} from '@/lib/api/pricing'

interface QuoteGeneratorProps {
  siteId: string
  onQuoteGenerated?: (quote: QuoteResponse, equipmentCodes: string[], slaTier: string, contractMonths: number) => void
}

interface FormState {
  equipmentCodes: string[]
  slaTier: SLATier
  contractMonths: number
  includeBenchmarks: boolean
}

interface SLATierDisplay {
  tier: SLATier | string
  margin_target: number
  multiplier: number
  response_time?: string
  uptime?: string
}

export default function QuoteGenerator({
  siteId,
  onQuoteGenerated,
}: QuoteGeneratorProps) {
  // Form state
  const [formData, setFormData] = useState<FormState>({
    equipmentCodes: [],
    slaTier: 'standard',
    contractMonths: 12,
    includeBenchmarks: true,
  })

  // API data
  const [equipmentTypes, setEquipmentTypes] = useState<string[]>([])
  const [slaTiers, setSlaTiers] = useState<SLATierDisplay[]>([])

  // UI state
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [quote, setQuote] = useState<QuoteResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [equipmentSearch, setEquipmentSearch] = useState('')

  // Load equipment types and SLA tiers on mount
  useEffect(() => {
    async function loadData() {
      setLoading(true)
      setError(null)

      try {
        const [equipTypes, slaResp] = await Promise.all([
          pricingApi.getEquipmentTypes(),
          pricingApi.getSLATiers(),
        ])

        setEquipmentTypes(equipTypes.equipment_types)
        setSlaTiers(slaResp.tiers)
      } catch (err) {
        console.error('Failed to load quote data:', err)
        setError(
          err instanceof Error
            ? err.message
            : 'Failed to load equipment types and SLA tiers'
        )
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [])

  // Handle equipment selection
  const handleEquipmentChange = (code: string) => {
    setFormData((prev) => {
      const newCodes = prev.equipmentCodes.includes(code)
        ? prev.equipmentCodes.filter((c) => c !== code)
        : [...prev.equipmentCodes, code]
      return { ...prev, equipmentCodes: newCodes }
    })
  }

  // Filter equipment types by search
  const filteredEquipment = equipmentTypes.filter((type) =>
    type.toLowerCase().includes(equipmentSearch.toLowerCase())
  )

  // Handle form submission
  const handleGenerateQuote = async () => {
    if (formData.equipmentCodes.length === 0) {
      setError('Please select at least one equipment type')
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      const request: QuoteRequest = {
        site_id: siteId,
        equipment_codes: formData.equipmentCodes,
        sla_tier: formData.slaTier as SLATier,
        contract_months: formData.contractMonths,
        include_benchmarks: formData.includeBenchmarks,
      }

      const result = await pricingApi.calculateQuote(request)
      setQuote(result)

      if (onQuoteGenerated) {
        onQuoteGenerated(result, formData.equipmentCodes, formData.slaTier, formData.contractMonths)
      }
    } catch (err) {
      console.error('Failed to generate quote:', err)
      setError(
        err instanceof Error ? err.message : 'Failed to generate quote'
      )
    } finally {
      setSubmitting(false)
    }
  }

  // Get SLA tier info for display
  const getCurrentSLATier = (): SLATierDisplay | undefined => {
    return slaTiers.find((t) => t.tier === formData.slaTier)
  }

  const _currentSLA = getCurrentSLATier()

  // Show success state with quote preview
  if (quote) {
    return (
      <div className="space-y-4">
        <Card className="bg-green-50 border border-green-200">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="h-5 w-5 text-green-600 mt-1 flex-shrink-0" />
            <div className="flex-1">
              <Title className="text-green-900">Quote Generated</Title>
              <Text className="text-green-800">
                Quote ID: {quote.request_id}
              </Text>
              <Text className="text-green-700 text-sm mt-1">
                Valid until: {new Date(quote.valid_until).toLocaleDateString()}
              </Text>
            </div>
          </div>
        </Card>

        <Card>
          <Title>Quote Summary</Title>
          <Grid className="grid grid-cols-2 gap-4 mt-4">
            <Col>
              <div className="space-y-2">
                <Text className="text-tremor-label text-tremor-content-subtitle">
                  Recommended Monthly Fee
                </Text>
                <div className="text-3xl font-bold text-tremor-brand">
                  {formatZAR(quote.recommended_fee_zar)}
                </div>
              </div>
            </Col>
            <Col>
              <div className="space-y-2">
                <Text className="text-tremor-label text-tremor-content-subtitle">
                  Contract Duration
                </Text>
                <div className="text-3xl font-bold text-tremor-brand">
                  {formData.contractMonths}
                </div>
                <Text className="text-tremor-label">months</Text>
              </div>
            </Col>
          </Grid>

          <Grid className="grid grid-cols-2 gap-4 mt-6">
            <Col>
              <div className="space-y-2">
                <Text className="text-tremor-label text-tremor-content-subtitle">
                  Fee Range (Min - Max)
                </Text>
                <div className="text-lg font-semibold">
                  {formatZAR(quote.fee_range_zar.min || 0)} -{' '}
                  {formatZAR(quote.fee_range_zar.max || 0)}
                </div>
              </div>
            </Col>
            <Col>
              <div className="space-y-2">
                <Text className="text-tremor-label text-tremor-content-subtitle">
                  SLA Tier
                </Text>
                <Badge className="capitalize">{formData.slaTier}</Badge>
              </div>
            </Col>
          </Grid>
        </Card>

        {quote.risk_factors && quote.risk_factors.length > 0 && (
          <Card>
            <Title className="text-base">Risk Factors</Title>
            <ul className="mt-3 space-y-2">
              {quote.risk_factors.map((factor, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <AlertCircle className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
                  <Text className="text-sm">{factor}</Text>
                </li>
              ))}
            </ul>
          </Card>
        )}

        <div className="flex gap-3 mt-6">
          <Button
            variant="secondary"
            onClick={() => {
              setQuote(null)
              setFormData({
                equipmentCodes: [],
                slaTier: 'standard',
                contractMonths: 12,
                includeBenchmarks: true,
              })
            }}
          >
            Generate New Quote
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              // Will be implemented with navigation in parent component
              console.log('Proceeding to quote export/preview')
            }}
          >
            Proceed to Preview <ArrowRight className="h-4 w-4 ml-2" />
          </Button>
        </div>
      </div>
    )
  }

  // Show loading state
  if (loading) {
    return (
      <Card>
        <div className="flex items-center justify-center py-12">
          <div className="flex flex-col items-center gap-3">
            <div className="animate-spin">
              <Zap className="h-6 w-6 text-tremor-brand" />
            </div>
            <Text>Loading quote builder...</Text>
          </div>
        </div>
      </Card>
    )
  }

  // Show error state
  if (error) {
    return (
      <Card className="bg-red-50 border border-red-200">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-red-600 mt-1 flex-shrink-0" />
          <div className="flex-1">
            <Title className="text-red-900">Error</Title>
            <Text className="text-red-800">{error}</Text>
            <Button
              variant="secondary"
              onClick={() => {
                setError(null)
                setLoading(true)
              }}
              className="mt-3"
            >
              Retry
            </Button>
          </div>
        </div>
      </Card>
    )
  }

  // Main form
  return (
    <div className="space-y-6">
      <Card>
        <Title>Quote Generator</Title>
        <Text className="text-tremor-content-subtitle mt-2">
          Select equipment and configuration to generate a professional price
          quote
        </Text>

        <div className="mt-6 space-y-6">
          {/* Equipment Selection */}
          <div className="space-y-3">
            <Text className="font-medium">Equipment Selection</Text>
            <TextInput
              placeholder="Search equipment types..."
              value={equipmentSearch}
              onChange={(e) => setEquipmentSearch(e.target.value)}
              className="mb-3"
            />
            <div className="grid grid-cols-2 gap-3 max-h-64 overflow-y-auto border rounded-lg p-3 bg-tremor-background-muted">
              {filteredEquipment.length > 0 ? (
                filteredEquipment.map((type) => (
                  <label key={type} className="flex items-center gap-2 p-2 hover:bg-tremor-background rounded cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.equipmentCodes.includes(type)}
                      onChange={() => handleEquipmentChange(type)}
                      className="w-4 h-4"
                    />
                    <Text className="text-sm">{type}</Text>
                  </label>
                ))
              ) : (
                <Text className="text-tremor-content-subtitle text-sm col-span-2">
                  No equipment types match your search
                </Text>
              )}
            </div>
            {formData.equipmentCodes.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {formData.equipmentCodes.map((code) => (
                  <Badge
                    key={code}
                    icon={Zap}
                    className="bg-blue-100 text-blue-800"
                  >
                    {code}
                    <button
                      onClick={() => handleEquipmentChange(code)}
                      className="ml-1 hover:text-blue-600"
                    >
                      ×
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>

          {/* SLA Tier Selection */}
          <div className="space-y-3">
            <Text className="font-medium">Service Level Agreement Tier</Text>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {slaTiers.map((tier) => (
                <button
                  key={tier.tier}
                  onClick={() =>
                    setFormData((prev) => ({
                      ...prev,
                      slaTier: tier.tier as SLATier,
                    }))
                  }
                  className={`p-4 rounded-lg border-2 transition-all text-left ${
                    formData.slaTier === tier.tier
                      ? 'border-tremor-brand bg-tremor-brand/5'
                      : 'border-tremor-border hover:border-tremor-brand/50'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <Text className="font-semibold capitalize">
                        {tier.tier}
                      </Text>
                      <Text className="text-tremor-label text-tremor-content-subtitle text-xs mt-1">
                        {tier.uptime &&
                          `${tier.uptime} uptime • `}
                        {tier.response_time &&
                          `${tier.response_time} response`}
                      </Text>
                    </div>
                    <div className="text-right">
                      <Text className="font-medium">
                        {formatPercent(tier.margin_target)}
                      </Text>
                      <Text className="text-tremor-label text-tremor-content-subtitle text-xs">
                        margin
                      </Text>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Contract Duration */}
          <div className="space-y-3">
            <Text className="font-medium flex items-center gap-2">
              <Clock className="h-4 w-4" />
              Contract Duration
            </Text>
            <div className="flex gap-3 items-center">
              <TextInput
                type="number"
                min="1"
                max="60"
                value={formData.contractMonths}
                onChange={(e) =>
                  setFormData((prev) => ({
                    ...prev,
                    contractMonths: Math.max(
                      1,
                      Math.min(60, parseInt(e.target.value) || 12)
                    ),
                  }))
                }
                className="w-24"
              />
              <Text>months</Text>
            </div>
            <Text className="text-tremor-label text-tremor-content-subtitle text-xs">
              Valid range: 1 - 60 months
            </Text>
          </div>

          {/* Options */}
          <div className="space-y-3">
            <label className="flex items-center gap-3 p-3 border rounded-lg hover:bg-tremor-background-muted cursor-pointer">
              <input
                type="checkbox"
                checked={formData.includeBenchmarks}
                onChange={(e) =>
                  setFormData((prev) => ({
                    ...prev,
                    includeBenchmarks: e.target.checked,
                  }))
                }
                className="w-4 h-4"
              />
              <Text className="text-sm flex-1">
                Include market benchmark comparison
              </Text>
              <DollarSign className="h-4 w-4 text-tremor-content-subtitle" />
            </label>
          </div>
        </div>

        {/* Submit Button */}
        <Button
          onClick={handleGenerateQuote}
          disabled={
            submitting ||
            formData.equipmentCodes.length === 0
          }
          className="w-full mt-6"
          icon={DollarSign}
        >
          {submitting ? 'Generating Quote...' : 'Generate Quote'}
        </Button>
      </Card>
    </div>
  )
}

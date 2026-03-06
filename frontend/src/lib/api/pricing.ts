/**
 * Pricing API Client
 *
 * Provides TypeScript types and methods for pricing endpoints from Phase 52-01.
 * Includes quote generation, sensitivity analysis, and price range calculations.
 *
 * Phase 52-02: Quote Generation UI
 */

import { fetchApi } from './client'

/**
 * SLA Tier type matching backend definition
 */
export type SLATier = 'basic' | 'standard' | 'premium' | 'enterprise'

/**
 * Request for calculating a pricing quote
 */
export interface QuoteRequest {
  site_id: string
  equipment_codes: string[] // List of equipment codes to quote
  sla_tier: SLATier
  contract_months?: number // Default 12, range 1-60
  include_benchmarks?: boolean // Default true
}

/**
 * Response from quote calculation
 */
export interface QuoteResponse {
  request_id: string
  recommended_fee_zar: number | string // Decimal as string for precision
  fee_range_zar: {
    min?: number | string
    target?: number | string
    max?: number | string
  }
  cost_breakdown: {
    [key: string]: number | string
  }
  risk_factors: string[]
  assumptions: string[]
  market_comparison?: {
    [key: string]: any
  }
  valid_until: string // ISO date string
}

/**
 * Equipment type definition from budget templates
 */
export interface EquipmentType {
  name: string
  base_cost?: number | string
}

/**
 * SLA tier information with margin details
 */
export interface SLATierInfo {
  tier: SLATier | string
  margin_target: number
  multiplier: number
  response_time?: string
  uptime?: string
}

/**
 * Equipment types response
 */
export interface EquipmentTypesResponse {
  equipment_types: string[]
  count: number
  note?: string
}

/**
 * SLA tiers response
 */
export interface SLATiersResponse {
  tiers: SLATierInfo[]
  count: number
}

/**
 * Price range calculation response
 */
export interface PriceRangeResponse {
  base_fee: number | string
  min_fee: number | string
  max_fee: number | string
  variance_pct: number
}

/**
 * What-if scenario definition
 */
export interface WhatIfScenario {
  name: string
  sla_tier?: SLATier
  add_equipment_codes?: string[]
  condition_score_delta?: number
  risk_buffer_multiplier?: number
  target_margin_pct?: number
}

/**
 * What-if analysis request
 */
export interface WhatIfRequest {
  base: QuoteRequest
  scenarios: WhatIfScenario[]
}

/**
 * What-if analysis response
 */
export interface WhatIfResponse {
  base_quote: QuoteResponse
  scenarios: {
    [scenarioName: string]: QuoteResponse
  }
}

/**
 * Renewal quote with fee recommendations and drivers
 */
export interface RenewalQuote {
  original_monthly_fee: number | string
  recommended_monthly_fee: number | string
  fee_change_pct: number | string
  drivers: string[]
  confidence: 'high' | 'medium' | 'low'
  assumptions: string[]
}

/**
 * Comparable contract for benchmarking
 */
export interface ContractComparable {
  contract_id: string
  equipment_types: string[]
  monthly_fee: number | string
  sla_tier: SLATier
  profitability?: number | string
}

/**
 * Renegotiation option analysis
 */
export interface RenegotiationOption {
  option_type: 'maintain' | 'invest' | 'expand'
  description: string
  recommended_fee: number | string
  estimated_npv_zar: number | string
  roi_pct: number | string
  implementation_notes: string[]
}

/**
 * Renegotiation analysis response
 */
export interface RenegotiationAnalysis {
  contract_id: string
  options: RenegotiationOption[]
  recommended_option: string
  market_context: {
    [key: string]: any
  }
}

/**
 * Equipment benchmark response
 */
export interface EquipmentBenchmarkResponse {
  equipment_type: string
  sla_tier: string
  avg_fee_zar?: number | string
  min_fee_zar?: number | string
  max_fee_zar?: number | string
  sample_size: number
  confidence_pct: number
  note?: string
}

/**
 * Win/loss analysis response
 */
export interface WinLossAnalysisResponse {
  total_quotes: number
  total_won: number
  total_lost: number
  total_pending: number
  win_rate_pct: number
  avg_negotiation_days: number
  lost_reasons: { [key: string]: number }
  avg_discount_pct: number
  note?: string
}

/**
 * Portfolio benchmark response
 */
export interface PortfolioBenchmarkResponse {
  portfolio_size: number
  above_market: Array<{ contract_id: string; variance_pct: number }>
  below_market: Array<{ contract_id: string; variance_pct: number }>
  at_market: Array<{ contract_id: string; variance_pct: number }>
  avg_variance_pct: number
  top_underpriced: Array<{ contract_id: string; opportunity_zar: number }>
  top_overpriced: Array<{ contract_id: string; risk_zar: number }>
  market_opportunities: string[]
  note?: string
}

/**
 * Format a Decimal amount as ZAR currency string
 * E.g., 12345.67 → "R12,345.67"
 */
export function formatZAR(amount: number | string): string {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  if (isNaN(num)) return 'R0.00'

  const formatted = new Intl.NumberFormat('en-ZA', {
    style: 'currency',
    currency: 'ZAR',
  }).format(num)

  return formatted
}

/**
 * Parse ZAR currency string back to number
 * E.g., "R12,345.67" → 12345.67
 */
export function parseZAR(value: string): number {
  // Remove currency symbol and commas, parse as float
  const cleaned = value.replace(/[R,]/g, '').trim()
  return parseFloat(cleaned) || 0
}

/**
 * Format percentage value
 */
export function formatPercent(value: number | string): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return `${num.toFixed(2)}%`
}

/**
 * Pricing API client methods
 */
export const pricingApi = {
  /**
   * Calculate recommended price for a contract quote.
   *
   * Multi-factor pricing calculation:
   * - Base cost from equipment templates
   * - Condition adjustment (equipment health score)
   * - Age adjustment (equipment lifecycle position)
   * - Risk buffer (ML failure predictions)
   * - SLA tier premium
   * - Target margin application
   *
   * Returns quote with fee range, breakdown, risk factors, and assumptions.
   */
  calculateQuote: (request: QuoteRequest) =>
    fetchApi<QuoteResponse>(
      '/api/pricing/calculate-quote',
      {
        method: 'POST',
        body: JSON.stringify(request),
      }
    ),

  /**
   * Calculate price range with specified variance.
   *
   * Returns base fee, min/max range, and variance percentage.
   * Useful for what-if analysis and negotiation scenarios.
   */
  calculatePriceRange: (
    request: QuoteRequest,
    variancePct: number = 10
  ) =>
    fetchApi<PriceRangeResponse>(
      `/api/pricing/calculate-price-range?variance_pct=${variancePct}`,
      {
        method: 'POST',
        body: JSON.stringify(request),
      }
    ),

  /**
   * Get available equipment types for pricing.
   *
   * Returns list of equipment types with budget templates.
   * Used for quote building UI to populate equipment selectors.
   */
  getEquipmentTypes: () =>
    fetchApi<EquipmentTypesResponse>(
      '/api/pricing/equipment-types'
    ),

  /**
   * Get available SLA tiers with pricing.
   *
   * Returns SLA tiers with margin targets and pricing multipliers.
   * Used for quote building to show SLA tier options.
   */
  getSLATiers: () =>
    fetchApi<SLATiersResponse>(
      '/api/pricing/sla-tiers'
    ),

  /**
   * Run what-if analysis for pricing scenarios.
   *
   * Calculates pricing impact of different scenarios:
   * - Different SLA tiers
   * - Additional equipment
   * - Condition score changes
   * - Risk adjustments
   */
  whatIfAnalysis: (request: WhatIfRequest) =>
    fetchApi<WhatIfResponse>(
      '/api/pricing/what-if',
      {
        method: 'POST',
        body: JSON.stringify(request),
      }
    ),

  /**
   * Get renewal price recommendation for an existing contract.
   *
   * Compares original quoted fee to current recommended renewal fee,
   * showing drivers for change and confidence level.
   */
  getRenewalPrice: (contractId: string) =>
    fetchApi<RenewalQuote>(
      `/api/pricing/renewal/${contractId}`
    ),

  /**
   * Get market comparable pricing for equipment type and SLA tier.
   *
   * Returns average, min, and max fees from similar contracts.
   */
  getEquipmentBenchmarks: (equipmentType: string, slaTier: SLATier = 'standard') =>
    fetchApi<EquipmentBenchmarkResponse>(
      `/api/pricing/benchmarks-equipment/${equipmentType}?sla_tier=${slaTier}`
    ),

  /**
   * Analyze renegotiation options for contract renewal.
   *
   * Returns analysis of three options:
   * 1. Maintain margin - Raise fee to cover increased costs
   * 2. Invest in maintenance - Reduce risk buffer, maintain fee
   * 3. Add services - Justify higher fee with expanded scope
   */
  analyzeRenegotiation: (contractId: string, optionType?: string) =>
    fetchApi<RenegotiationAnalysis>(
      optionType
        ? `/api/pricing/renegotiation/${contractId}?option_type=${optionType}`
        : `/api/pricing/renegotiation/${contractId}`,
      {
        method: 'POST',
      }
    ),

  /**
   * Get portfolio-level win/loss statistics.
   *
   * Returns aggregate win rate, average negotiation time,
   * lost reasons, and negotiation discount analysis.
   */
  getWinLossAnalysis: () =>
    fetchApi<WinLossAnalysisResponse>(
      '/api/pricing/win-loss-analysis'
    ),

  /**
   * Compare all contracts in portfolio to market benchmarks.
   *
   * Returns list of contracts with variance from market average,
   * highlighting over/underpriced contracts.
   */
  getPortfolioBenchmarks: (includeDetails: boolean = false) =>
    fetchApi<PortfolioBenchmarkResponse>(
      `/api/pricing/portfolio-benchmarks?include_details=${includeDetails}`
    ),
}

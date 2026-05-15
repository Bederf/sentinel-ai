/**
 * Quote Preview and PDF Export Component
 *
 * Displays quotes in a professional format with PDF export capability.
 * Includes all required information: equipment list, cost breakdown, risk factors,
 * SLA details, assumptions, and market comparisons.
 *
 * Features:
 * - Professional quote layout
 * - PDF download generation (html2pdf)
 * - Email quote option (stub)
 * - Copy to clipboard
 * - Edit and regenerate
 *
 * Phase 52-02: Quote Generation UI
 */

import { useState, useRef } from 'react'

import {
  Download,
  Copy,
  Edit,
  AlertCircle,
  CheckCircle2,
  Calendar,
} from 'lucide-react'
import { formatZAR } from '@/lib/api/pricing'
import type { QuoteResponse } from '@/lib/api/pricing'
import { Badge } from '../Badge'

interface QuotePreviewProps {
  quote: QuoteResponse
  siteName?: string
  clientName?: string
  equipmentCodes: string[]
  slaTier: string
  contractMonths: number
  onEdit?: () => void
}

export default function QuotePreview({
  quote,
  siteName = 'Building',
  clientName = 'Client',
  equipmentCodes,
  slaTier,
  contractMonths,
  onEdit,
}: QuotePreviewProps) {
  const [copied, setCopied] = useState(false)
  const quoteRef = useRef<HTMLDivElement | null>(null)

  // Calculate totals
  const monthlyFee = parseFloat(
    typeof quote.recommended_fee_zar === 'string'
      ? quote.recommended_fee_zar
      : String(quote.recommended_fee_zar)
  )
  const totalContractValue = monthlyFee * contractMonths

  // SLA tier details
  const slaDetails: Record<string, { uptime: string; response: string; resolution: string }> = {
    basic: { uptime: '99%', response: '24 hours', resolution: '72 hours' },
    standard: { uptime: '99.5%', response: '8 hours', resolution: '24 hours' },
    premium: { uptime: '99.9%', response: '4 hours', resolution: '12 hours' },
    enterprise: { uptime: '99.95%', response: '2 hours', resolution: '4 hours' },
  }

  const slaInfo = slaDetails[slaTier as keyof typeof slaDetails] || slaDetails.standard

  // Generate PDF using browser print API
  const handleDownloadPDF = () => {
    const element = document.getElementById('quote-preview-content')
    if (!element) return

    // Use browser's print-to-PDF functionality
    const printWindow = window.open('', '', 'width=800,height=600')
    if (!printWindow) return

    printWindow.document.write(`
      <html>
        <head>
          <title>Quote ${quote.request_id}</title>
          <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            h1 { font-size: 24px; margin-bottom: 20px; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
            th { background-color: #f5f5f5; font-weight: bold; }
          </style>
        </head>
        <body>
          ${element.innerHTML}
          <script>
            window.print();
            window.close();
          </script>
        </body>
      </html>
    `)
    printWindow.document.close()
  }

  // Copy to clipboard
  const handleCopyToClipboard = () => {
    const text = `
Quote ID: ${quote.request_id}
Date: ${new Date().toISOString().split('T')[0]}

PRICING SUMMARY
Monthly Fee: ${formatZAR(monthlyFee)}
Contract Duration: ${contractMonths} months
Total Contract Value: ${formatZAR(totalContractValue)}

EQUIPMENT
${equipmentCodes.join('\n')}

SLA TIER: ${slaTier.toUpperCase()}
Uptime Target: ${slaInfo.uptime}
Response Time: ${slaInfo.response}

Valid until: ${quote.valid_until}
    `.trim()

    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="space-y-6">
      {/* Action Bar */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={handleDownloadPDF}
          className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium text-white"
          style={{ background: 'var(--color-sentinel-blue)' }}
        >
          <Download className="h-4 w-4" />
          Download PDF
        </button>
        <button
          onClick={handleCopyToClipboard}
          className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            color: 'var(--color-sentinel-text-primary)',
            border: '1px solid var(--color-sentinel-border)',
          }}
        >
          <Copy className="h-4 w-4" />
          {copied ? 'Copied!' : 'Copy to Clipboard'}
        </button>
        <button
          onClick={onEdit}
          className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            color: 'var(--color-sentinel-text-primary)',
            border: '1px solid var(--color-sentinel-border)',
          }}
        >
          <Edit className="h-4 w-4" />
          Edit & Regenerate
        </button>
      </div>

      {/* Preview Content */}
      <div
        id="quote-preview-content"
        className="space-y-6 bg-white p-8 rounded-lg"
        ref={quoteRef}
      >
        {/* Header */}
        <div className="space-y-4 border-b pb-6">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-2xl font-semibold">Professional Service Quote</h2>
              <p className="mt-1 text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                SENTINEL BMS Intelligence
              </p>
            </div>
            <div className="text-right">
              <div className="space-y-1">
                <p className="font-semibold">Quote ID</p>
                <p className="text-lg font-mono">{quote.request_id}</p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="space-y-2">
                <p className="font-medium text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Client</p>
                <p className="text-base">{clientName}</p>
              </div>
            </div>
            <div>
              <div className="space-y-2">
                <p className="font-medium text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Facility</p>
                <p className="text-base">{siteName}</p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="space-y-2">
                <p className="font-medium text-xs flex items-center gap-2" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                  <Calendar className="h-4 w-4" />
                  Quote Date
                </p>
                <p className="text-base">
                  {new Date().toLocaleDateString('en-ZA', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </p>
              </div>
            </div>
            <div>
              <div className="space-y-2">
                <p className="font-medium text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Valid Until</p>
                <p className="text-base">
                  {new Date(quote.valid_until).toLocaleDateString('en-ZA', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Pricing Summary */}
        <div className="space-y-4">
          <h3 className="text-base font-semibold">Pricing Summary</h3>
          <div className="grid grid-cols-3 gap-4">
            <div
              className="rounded-lg p-4"
              style={{
                background: 'var(--color-sentinel-bg-panel)',
                border: '1px solid var(--color-sentinel-border)',
              }}
            >
              <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Monthly Fee
              </p>
              <div className="mt-2 text-3xl font-semibold tabular-nums" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {formatZAR(monthlyFee)}
              </div>
            </div>
            <div
              className="rounded-lg p-4"
              style={{
                background: 'var(--color-sentinel-bg-panel)',
                border: '1px solid var(--color-sentinel-border)',
              }}
            >
              <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Contract Duration
              </p>
              <div className="mt-2 text-3xl font-semibold tabular-nums" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {contractMonths} months
              </div>
            </div>
            <div
              className="rounded-lg p-4"
              style={{
                background: 'var(--color-sentinel-bg-panel)',
                border: '1px solid var(--color-sentinel-border)',
              }}
            >
              <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Total Value
              </p>
              <div className="mt-2 text-3xl font-semibold tabular-nums" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {formatZAR(totalContractValue)}
              </div>
            </div>
          </div>
        </div>

        {/* Fee Range */}
        {quote.fee_range_zar && Object.keys(quote.fee_range_zar).length > 0 && (
          <div className="space-y-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h3 className="text-base font-semibold text-blue-900">Negotiation Range</h3>
            <div className="grid grid-cols-3 gap-3">
              {quote.fee_range_zar.min && (
                <div>
                  <div>
                    <p className="text-xs text-blue-700">Minimum</p>
                    <p className="text-lg font-semibold text-blue-900 mt-1">
                      {formatZAR(quote.fee_range_zar.min)}
                    </p>
                  </div>
                </div>
              )}
              {quote.fee_range_zar.target && (
                <div>
                  <div>
                    <p className="text-xs text-blue-700">Target</p>
                    <p className="text-lg font-semibold text-blue-900 mt-1">
                      {formatZAR(quote.fee_range_zar.target)}
                    </p>
                  </div>
                </div>
              )}
              {quote.fee_range_zar.max && (
                <div>
                  <div>
                    <p className="text-xs text-blue-700">Maximum</p>
                    <p className="text-lg font-semibold text-blue-900 mt-1">
                      {formatZAR(quote.fee_range_zar.max)}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Equipment List */}
        <div className="space-y-4">
          <h3 className="text-base font-semibold">Equipment Covered</h3>
          <div className="flex flex-wrap gap-2">
            {equipmentCodes.map((code) => (
              <Badge key={code} className="bg-blue-100 text-blue-900">
                {code}
              </Badge>
            ))}
          </div>
        </div>

        {/* Cost Breakdown */}
        {quote.cost_breakdown && Object.keys(quote.cost_breakdown).length > 0 && (
          <div className="space-y-4">
            <h3 className="text-base font-semibold">Cost Breakdown</h3>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr
                    className="border-b text-left text-xs font-medium uppercase tracking-wider"
                    style={{ borderColor: 'var(--color-sentinel-border)', color: 'var(--color-sentinel-text-secondary)' }}
                  >
                    <th className="pb-2">Component</th>
                    <th className="pb-2 text-right">Amount (ZAR)</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(quote.cost_breakdown).map(([key, value]) => (
                    <tr
                      key={key}
                      className="border-b"
                      style={{ borderColor: 'var(--color-sentinel-border)' }}
                    >
                      <td className="py-2 text-sm capitalize" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                        {key.replace(/_/g, ' ')}
                      </td>
                      <td className="py-2 text-sm text-right font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                        {formatZAR(value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* SLA Details */}
        <div className="space-y-4 bg-green-50 border border-green-200 rounded-lg p-4">
          <h3 className="text-base font-semibold text-green-900">
            SLA Tier: {slaTier.toUpperCase()}
          </h3>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <div>
                <p className="text-xs text-green-700">Uptime Target</p>
                <p className="text-lg font-semibold text-green-900 mt-1">
                  {slaInfo.uptime}
                </p>
              </div>
            </div>
            <div>
              <div>
                <p className="text-xs text-green-700">Response Time</p>
                <p className="text-lg font-semibold text-green-900 mt-1">
                  {slaInfo.response}
                </p>
              </div>
            </div>
            <div>
              <div>
                <p className="text-xs text-green-700">Resolution Time</p>
                <p className="text-lg font-semibold text-green-900 mt-1">
                  {slaInfo.resolution}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Risk Factors */}
        {quote.risk_factors && quote.risk_factors.length > 0 && (
          <div className="space-y-4">
            <h3 className="text-base font-semibold">Risk Factors</h3>
            <ul className="space-y-2">
              {quote.risk_factors.map((factor, idx) => (
                <li key={idx} className="flex items-start gap-3">
                  <AlertCircle className="h-5 w-5 text-amber-500 mt-0.5 flex-shrink-0" />
                  <p className="text-sm">{factor}</p>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Assumptions */}
        {quote.assumptions && quote.assumptions.length > 0 && (
          <div className="space-y-4">
            <h3 className="text-base font-semibold">Assumptions & Conditions</h3>
            <ul className="space-y-2">
              {quote.assumptions.map((assumption, idx) => (
                <li key={idx} className="flex items-start gap-3">
                  <CheckCircle2 className="h-5 w-5 text-green-600 mt-0.5 flex-shrink-0" />
                  <p className="text-sm">{assumption}</p>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Market Comparison */}
        {quote.market_comparison && (
          <div className="space-y-4 bg-purple-50 border border-purple-200 rounded-lg p-4">
            <h3 className="text-base font-semibold text-purple-900">Market Benchmark</h3>
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(quote.market_comparison).map(([key, value]) => (
                <div key={key}>
                  <div>
                    <p className="text-xs text-purple-700 capitalize">
                      {key.replace(/_/g, ' ')}
                    </p>
                    <p className="text-base font-semibold text-purple-900 mt-1">
                      {typeof value === 'number' ? formatZAR(value) : String(value)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="border-t pt-6 mt-6 space-y-3">
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            This quote is valid until {quote.valid_until} and is subject to the
            terms and conditions on the back page. All prices are in South African
            Rand (ZAR) and exclude VAT unless otherwise stated.
          </p>
          <p className="text-xs font-medium" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            For questions about this quote, please contact sales@sentinel-bms.com
          </p>
          <div className="flex items-end justify-between pt-6 border-t">
            <div>
              <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Authorized By</p>
              <div className="h-16 mt-2" />
              <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>_____________________</p>
              <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                {new Date().toLocaleDateString('en-ZA')}
              </p>
            </div>
            <div className="text-right text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              <p>SENTINEL BMS Intelligence</p>
              <p>quote-{quote.request_id}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

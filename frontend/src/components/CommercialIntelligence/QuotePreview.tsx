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
        <Button
          icon={Download}
          onClick={handleDownloadPDF}
          variant="primary"
        >
          Download PDF
        </Button>
        <Button
          icon={Copy}
          onClick={handleCopyToClipboard}
          variant="secondary"
        >
          {copied ? 'Copied!' : 'Copy to Clipboard'}
        </Button>
        <Button
          icon={Edit}
          onClick={onEdit}
          variant="secondary"
        >
          Edit & Regenerate
        </Button>
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
              <Title className="text-2xl">Professional Service Quote</Title>
              <Text className="text-tremor-content-subtitle mt-1">
                SENTINEL BMS Intelligence
              </Text>
            </div>
            <div className="text-right">
              <div className="space-y-1">
                <Text className="font-semibold">Quote ID</Text>
                <Text className="text-lg font-mono">{quote.request_id}</Text>
              </div>
            </div>
          </div>

          <Grid className="grid grid-cols-2 gap-4">
            <Col>
              <div className="space-y-2">
                <Text className="font-medium text-tremor-label">Client</Text>
                <Text className="text-base">{clientName}</Text>
              </div>
            </Col>
            <Col>
              <div className="space-y-2">
                <Text className="font-medium text-tremor-label">Facility</Text>
                <Text className="text-base">{siteName}</Text>
              </div>
            </Col>
          </Grid>

          <Grid className="grid grid-cols-2 gap-4">
            <Col>
              <div className="space-y-2">
                <Text className="font-medium text-tremor-label flex items-center gap-2">
                  <Calendar className="h-4 w-4" />
                  Quote Date
                </Text>
                <Text className="text-base">
                  {new Date().toLocaleDateString('en-ZA', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </Text>
              </div>
            </Col>
            <Col>
              <div className="space-y-2">
                <Text className="font-medium text-tremor-label">Valid Until</Text>
                <Text className="text-base">
                  {new Date(quote.valid_until).toLocaleDateString('en-ZA', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </Text>
              </div>
            </Col>
          </Grid>
        </div>

        {/* Pricing Summary */}
        <div className="space-y-4">
          <Title className="text-base">Pricing Summary</Title>
          <Grid className="grid grid-cols-3 gap-4">
            <Col>
              <Card>
                <Text className="text-tremor-label text-tremor-content-subtitle">
                  Monthly Fee
                </Text>
                <Metric className="mt-2">
                  {formatZAR(monthlyFee)}
                </Metric>
              </Card>
            </Col>
            <Col>
              <Card>
                <Text className="text-tremor-label text-tremor-content-subtitle">
                  Contract Duration
                </Text>
                <Metric className="mt-2">{contractMonths} months</Metric>
              </Card>
            </Col>
            <Col>
              <Card>
                <Text className="text-tremor-label text-tremor-content-subtitle">
                  Total Value
                </Text>
                <Metric className="mt-2">
                  {formatZAR(totalContractValue)}
                </Metric>
              </Card>
            </Col>
          </Grid>
        </div>

        {/* Fee Range */}
        {quote.fee_range_zar && Object.keys(quote.fee_range_zar).length > 0 && (
          <div className="space-y-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
            <Title className="text-base text-blue-900">Negotiation Range</Title>
            <Grid className="grid grid-cols-3 gap-3">
              {quote.fee_range_zar.min && (
                <Col>
                  <div>
                    <Text className="text-tremor-label text-blue-700">Minimum</Text>
                    <Text className="text-lg font-semibold text-blue-900 mt-1">
                      {formatZAR(quote.fee_range_zar.min)}
                    </Text>
                  </div>
                </Col>
              )}
              {quote.fee_range_zar.target && (
                <Col>
                  <div>
                    <Text className="text-tremor-label text-blue-700">Target</Text>
                    <Text className="text-lg font-semibold text-blue-900 mt-1">
                      {formatZAR(quote.fee_range_zar.target)}
                    </Text>
                  </div>
                </Col>
              )}
              {quote.fee_range_zar.max && (
                <Col>
                  <div>
                    <Text className="text-tremor-label text-blue-700">Maximum</Text>
                    <Text className="text-lg font-semibold text-blue-900 mt-1">
                      {formatZAR(quote.fee_range_zar.max)}
                    </Text>
                  </div>
                </Col>
              )}
            </Grid>
          </div>
        )}

        {/* Equipment List */}
        <div className="space-y-4">
          <Title className="text-base">Equipment Covered</Title>
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
            <Title className="text-base">Cost Breakdown</Title>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Component</TableCell>
                  <TableCell className="text-right">Amount (ZAR)</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {Object.entries(quote.cost_breakdown).map(([key, value]) => (
                  <TableRow key={key}>
                    <TableCell className="capitalize">
                      {key.replace(/_/g, ' ')}
                    </TableCell>
                    <TableCell className="text-right font-semibold">
                      {formatZAR(value)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {/* SLA Details */}
        <div className="space-y-4 bg-green-50 border border-green-200 rounded-lg p-4">
          <Title className="text-base text-green-900">
            SLA Tier: {slaTier.toUpperCase()}
          </Title>
          <Grid className="grid grid-cols-3 gap-3">
            <Col>
              <div>
                <Text className="text-tremor-label text-green-700">Uptime Target</Text>
                <Text className="text-lg font-semibold text-green-900 mt-1">
                  {slaInfo.uptime}
                </Text>
              </div>
            </Col>
            <Col>
              <div>
                <Text className="text-tremor-label text-green-700">Response Time</Text>
                <Text className="text-lg font-semibold text-green-900 mt-1">
                  {slaInfo.response}
                </Text>
              </div>
            </Col>
            <Col>
              <div>
                <Text className="text-tremor-label text-green-700">Resolution Time</Text>
                <Text className="text-lg font-semibold text-green-900 mt-1">
                  {slaInfo.resolution}
                </Text>
              </div>
            </Col>
          </Grid>
        </div>

        {/* Risk Factors */}
        {quote.risk_factors && quote.risk_factors.length > 0 && (
          <div className="space-y-4">
            <Title className="text-base">Risk Factors</Title>
            <ul className="space-y-2">
              {quote.risk_factors.map((factor, idx) => (
                <li key={idx} className="flex items-start gap-3">
                  <AlertCircle className="h-5 w-5 text-amber-500 mt-0.5 flex-shrink-0" />
                  <Text className="text-sm">{factor}</Text>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Assumptions */}
        {quote.assumptions && quote.assumptions.length > 0 && (
          <div className="space-y-4">
            <Title className="text-base">Assumptions & Conditions</Title>
            <ul className="space-y-2">
              {quote.assumptions.map((assumption, idx) => (
                <li key={idx} className="flex items-start gap-3">
                  <CheckCircle2 className="h-5 w-5 text-green-600 mt-0.5 flex-shrink-0" />
                  <Text className="text-sm">{assumption}</Text>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Market Comparison */}
        {quote.market_comparison && (
          <div className="space-y-4 bg-purple-50 border border-purple-200 rounded-lg p-4">
            <Title className="text-base text-purple-900">Market Benchmark</Title>
            <Grid className="grid grid-cols-2 gap-3">
              {Object.entries(quote.market_comparison).map(([key, value]) => (
                <Col key={key}>
                  <div>
                    <Text className="text-tremor-label text-purple-700 capitalize">
                      {key.replace(/_/g, ' ')}
                    </Text>
                    <Text className="text-base font-semibold text-purple-900 mt-1">
                      {typeof value === 'number' ? formatZAR(value) : String(value)}
                    </Text>
                  </div>
                </Col>
              ))}
            </Grid>
          </div>
        )}

        {/* Footer */}
        <div className="border-t pt-6 mt-6 space-y-3">
          <Text className="text-tremor-label">
            This quote is valid until {quote.valid_until} and is subject to the
            terms and conditions on the back page. All prices are in South African
            Rand (ZAR) and exclude VAT unless otherwise stated.
          </Text>
          <Text className="text-tremor-label font-medium">
            For questions about this quote, please contact sales@sentinel-bms.com
          </Text>
          <div className="flex items-end justify-between pt-6 border-t">
            <div>
              <Text className="text-tremor-label">Authorized By</Text>
              <div className="h-16 mt-2" />
              <Text className="text-tremor-label">_____________________</Text>
              <Text className="text-tremor-label text-xs">
                {new Date().toLocaleDateString('en-ZA')}
              </Text>
            </div>
            <div className="text-right text-tremor-label text-xs">
              <Text>SENTINEL BMS Intelligence</Text>
              <Text>quote-{quote.request_id}</Text>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

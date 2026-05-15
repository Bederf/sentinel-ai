/**
 * Commercial Intelligence Dashboard
 *
 * Main component for the commercial intelligence module.
 * Provides access to quote generation, pricing analysis, and negotiation tools.
 *
 * Features:
 * - Tab navigation between generator and preview
 * - Quote state management
 * - Integration with all commercial tools
 * - Navigation and breadcrumbs
 *
 * Phase 52-02: Quote Generation UI
 */

import { useState } from 'react'

import {
  FileText,
  BarChart3,
  Plus,
  ChevronLeft,
  TrendingUp,
} from 'lucide-react'
import type { QuoteResponse } from '@/lib/api/pricing'
import QuoteGenerator from './QuoteGenerator'
import SensitivityAnalysis from './SensitivityAnalysis'
import QuotePreview from './QuotePreview'
import { RenewalPricingDashboard } from './RenewalPricingDashboard'
import { BenchmarkingAnalysis } from './BenchmarkingAnalysis'
import { TabBar } from '../TabBar'
import type { TabDef } from '../TabBar'

interface CommercialIntelligenceDashboardProps {
  siteId: string
  siteName?: string
  onClose?: () => void
}

type ViewMode = 'quote-tools' | 'renewal-pipeline' | 'renewal-analysis' | 'benchmarks' | 'win-loss'

const MAIN_TABS: TabDef[] = [
  { id: 'quote-tools', label: 'Quotes', icon: <FileText className="h-4 w-4" /> },
  { id: 'renewal-analysis', label: 'Renewals', icon: <FileText className="h-4 w-4" /> },
  { id: 'benchmarks', label: 'Benchmarks', icon: <BarChart3 className="h-4 w-4" /> },
  { id: 'win-loss', label: 'Win/Loss', icon: <TrendingUp className="h-4 w-4" /> },
]

const INNER_TABS = ['details', 'what-if', 'preview'] as const

export default function CommercialIntelligenceDashboard({
  siteId,
  siteName = 'Building',
  onClose,
}: CommercialIntelligenceDashboardProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('quote-tools')
  const [activeTab, setActiveTab] = useState(0)
  const [currentQuote, setCurrentQuote] = useState<QuoteResponse | null>(null)
  const [equipmentCodes, setEquipmentCodes] = useState<string[]>([])
  const [slaTier, setSlaTier] = useState<string>('standard')
  const [contractMonths, setContractMonths] = useState(12)
  const [selectedContractId, _setSelectedContractId] = useState<string | undefined>()

  // Handle quote generation
  const handleQuoteGenerated = (quote: QuoteResponse, codes: string[], tier: string, months: number) => {
    setCurrentQuote(quote)
    setEquipmentCodes(codes)
    setSlaTier(tier)
    setContractMonths(months)
    setActiveTab(1) // Switch to preview/analysis tab
  }

  // Reset to new quote
  const handleNewQuote = () => {
    setCurrentQuote(null)
    setEquipmentCodes([])
    setSlaTier('standard')
    setContractMonths(12)
    setActiveTab(0) // Back to generator
  }

  return (
    <div className="space-y-6">
      {/* Navigation */}
      {onClose && (
        <button
          onClick={onClose}
          className="flex items-center gap-2 hover:underline"
          style={{ color: 'var(--color-sentinel-blue)' }}
        >
          <ChevronLeft className="h-4 w-4" />
          Back to Buildings
        </button>
      )}

      {/* Header */}
      <div
        className="rounded-lg p-4"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
              Commercial Intelligence Tools
            </h2>
            <p className="mt-2 text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Generate professional quotes, analyze pricing scenarios, manage renewals,
              and benchmark contract performance
            </p>
          </div>
          {currentQuote && viewMode === 'quote-tools' && (
            <button
              onClick={handleNewQuote}
              className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium"
              style={{
                background: 'var(--color-sentinel-bg-secondary)',
                color: 'var(--color-sentinel-text-primary)',
                border: '1px solid var(--color-sentinel-border)',
              }}
            >
              <Plus className="h-4 w-4" />
              New Quote
            </button>
          )}
        </div>
      </div>

      {/* Main Navigation Tabs */}
      <TabBar
        tabs={MAIN_TABS}
        active={viewMode}
        onChange={(id) => { setViewMode(id as ViewMode); setActiveTab(0) }}
      />

      {/* Quote Tools Tab */}
      {viewMode === 'quote-tools' && (
        currentQuote ? (
          <>
            {/* Inner tabs: Details / What-If / Preview */}
            <TabBar
              tabs={[
                { id: 'details', label: 'Details', icon: <FileText className="h-4 w-4" /> },
                { id: 'what-if', label: 'What-If', icon: <BarChart3 className="h-4 w-4" /> },
                { id: 'preview', label: 'Preview', icon: <FileText className="h-4 w-4" /> },
              ]}
              active={INNER_TABS[activeTab]}
              onChange={(id) => setActiveTab(INNER_TABS.indexOf(id as typeof INNER_TABS[number]))}
            />

            {activeTab === 0 && (
              <div
                className="rounded-lg p-4"
                style={{
                  background: 'var(--color-sentinel-bg-panel)',
                  border: '1px solid var(--color-sentinel-border)',
                }}
              >
                <QuoteGenerator
                  siteId={siteId}
                  onQuoteGenerated={() => {}}
                />
              </div>
            )}

            {activeTab === 1 && (
              <SensitivityAnalysis
                quote={currentQuote}
                onCopyToNegotiation={(range) => {
                  console.log('Range copied:', range)
                }}
              />
            )}

            {activeTab === 2 && (
              <QuotePreview
                quote={currentQuote}
                siteName={siteName}
                clientName="Client Name"
                equipmentCodes={equipmentCodes}
                slaTier={slaTier}
                contractMonths={contractMonths}
                onEdit={handleNewQuote}
              />
            )}
          </>
        ) : (
          <>
            <div
              className="rounded-lg p-4"
              style={{
                background: 'var(--color-sentinel-bg-panel)',
                border: '1px solid var(--color-sentinel-border)',
              }}
            >
              <QuoteGenerator
                siteId={siteId}
                onQuoteGenerated={(quote) => {
                  handleQuoteGenerated(quote, [], 'standard', 12)
                }}
              />
            </div>

            {/* Quick Start Tips */}
            <div
              className="rounded-lg p-4"
              style={{
                background: '#eff6ff',
                border: '1px solid #bfdbfe',
              }}
            >
              <h3 className="text-base font-semibold text-blue-900">Getting Started with Quotes</h3>
              <div className="mt-4 space-y-3 text-blue-800 text-sm">
                <p>1. Select one or more equipment types to include in the quote</p>
                <p>2. Choose an SLA tier that matches your service level commitment</p>
                <p>3. Set the contract duration in months (1-60)</p>
                <p>4. Click "Generate Quote" to see the pricing calculation</p>
                <p>5. Use the What-If analysis tab to explore different pricing scenarios</p>
                <p>6. Export your final quote as PDF from the Preview tab</p>
              </div>
            </div>
          </>
        )
      )}

      {/* Renewal Analysis Tab */}
      {viewMode === 'renewal-analysis' && (
        <RenewalPricingDashboard selectedContractId={selectedContractId} />
      )}

      {/* Benchmarks Tab */}
      {viewMode === 'benchmarks' && (
        <BenchmarkingAnalysis />
      )}

      {/* Win/Loss Analysis Tab */}
      {viewMode === 'win-loss' && (
        <div
          className="rounded-lg p-4"
          style={{
            background: 'var(--color-sentinel-bg-panel)',
            border: '1px solid var(--color-sentinel-border)',
          }}
        >
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
            Win/Loss Analysis
          </h2>
          <p className="mt-2 text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Integrated in the Benchmarking Analysis tab with market insights
          </p>
        </div>
      )}
    </div>
  )
}

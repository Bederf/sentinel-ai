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
  Card,
  Title,
  Text,
  TabGroup,
  TabList,
  Tab,
  TabPanels,
  TabPanel,
  Button,
} from '@tremor/react'
import {
  FileText,
  BarChart3,
  Plus,
  ChevronLeft,
  TrendingUp,
} from 'lucide-react'
import type { QuoteResponse, SLATier } from '@/lib/api/pricing'
import QuoteGenerator from './QuoteGenerator'
import SensitivityAnalysis from './SensitivityAnalysis'
import QuotePreview from './QuotePreview'
import { RenewalPricingDashboard } from './RenewalPricingDashboard'
import { BenchmarkingAnalysis } from './BenchmarkingAnalysis'

interface CommercialIntelligenceDashboardProps {
  siteId: string
  siteName?: string
  onClose?: () => void
}

type ViewMode = 'quote-tools' | 'renewal-pipeline' | 'renewal-analysis' | 'benchmarks' | 'win-loss'

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
  const [selectedContractId, setSelectedContractId] = useState<string | undefined>()

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
          className="flex items-center gap-2 text-tremor-brand hover:underline"
        >
          <ChevronLeft className="h-4 w-4" />
          Back to Buildings
        </button>
      )}

      {/* Header */}
      <Card>
        <div className="flex items-start justify-between">
          <div>
            <Title>Commercial Intelligence Tools</Title>
            <Text className="text-tremor-content-subtitle mt-2">
              Generate professional quotes, analyze pricing scenarios, manage renewals,
              and benchmark contract performance
            </Text>
          </div>
          {currentQuote && viewMode === 'quote-tools' && (
            <Button
              icon={Plus}
              onClick={handleNewQuote}
              variant="secondary"
            >
              New Quote
            </Button>
          )}
        </div>
      </Card>

      {/* Main Navigation Tabs */}
      <TabGroup index={viewMode === 'quote-tools' ? 0 : viewMode === 'renewal-analysis' ? 1 : viewMode === 'benchmarks' ? 2 : 3}>
        <TabList className="mb-4 overflow-x-auto">
          <Tab icon={FileText} onClick={() => { setViewMode('quote-tools'); setActiveTab(0) }}>
            Quotes
          </Tab>
          <Tab icon={FileText} onClick={() => { setViewMode('renewal-analysis'); setActiveTab(0) }}>
            Renewals
          </Tab>
          <Tab icon={BarChart3} onClick={() => { setViewMode('benchmarks'); setActiveTab(0) }}>
            Benchmarks
          </Tab>
          <Tab icon={TrendingUp} onClick={() => { setViewMode('win-loss'); setActiveTab(0) }}>
            Win/Loss
          </Tab>
        </TabList>
        <TabPanels>
          {/* Quote Tools Tab */}
          <TabPanel>
            {currentQuote ? (
              // After quote generation: show generator, analysis, and preview tabs
              <TabGroup index={activeTab} onIndexChange={setActiveTab}>
                <TabList className="mb-4 overflow-x-auto">
                  <Tab icon={FileText}>Details</Tab>
                  <Tab icon={BarChart3}>What-If</Tab>
                  <Tab icon={FileText}>Preview</Tab>
                </TabList>
                <TabPanels>
                  <TabPanel>
                    <Card>
                      <QuoteGenerator
                        siteId={siteId}
                        onQuoteGenerated={() => {}} // Already generated
                      />
                    </Card>
                  </TabPanel>
                  <TabPanel>
                    <SensitivityAnalysis
                      quote={currentQuote}
                      onCopyToNegotiation={(range) => {
                        console.log('Range copied:', range)
                      }}
                    />
                  </TabPanel>
                  <TabPanel>
                    <QuotePreview
                      quote={currentQuote}
                      siteName={siteName}
                      clientName="Client Name"
                      equipmentCodes={equipmentCodes}
                      slaTier={slaTier}
                      contractMonths={contractMonths}
                      onEdit={handleNewQuote}
                    />
                  </TabPanel>
                </TabPanels>
              </TabGroup>
            ) : (
              // Before quote generation: show only the generator
              <>
                <Card>
                  <QuoteGenerator
                    siteId={siteId}
                    onQuoteGenerated={(quote) => {
                      handleQuoteGenerated(quote, [], 'standard', 12)
                    }}
                  />
                </Card>

                {/* Quick Start Tips */}
                <Card className="bg-blue-50 border border-blue-200">
                  <Title className="text-blue-900">Getting Started with Quotes</Title>
                  <div className="mt-4 space-y-3 text-blue-800 text-sm">
                    <p>
                      1. Select one or more equipment types to include in the quote
                    </p>
                    <p>
                      2. Choose an SLA tier that matches your service level commitment
                    </p>
                    <p>
                      3. Set the contract duration in months (1-60)
                    </p>
                    <p>
                      4. Click "Generate Quote" to see the pricing calculation
                    </p>
                    <p>
                      5. Use the What-If analysis tab to explore different pricing scenarios
                    </p>
                    <p>
                      6. Export your final quote as PDF from the Preview tab
                    </p>
                  </div>
                </Card>
              </>
            )}
          </TabPanel>

          {/* Renewal Analysis Tab */}
          <TabPanel>
            <RenewalPricingDashboard selectedContractId={selectedContractId} />
          </TabPanel>

          {/* Benchmarks Tab */}
          <TabPanel>
            <BenchmarkingAnalysis />
          </TabPanel>

          {/* Win/Loss Analysis Tab */}
          <TabPanel>
            <Card>
              <Title>Win/Loss Analysis</Title>
              <Text className="mt-2">Integrated in the Benchmarking Analysis tab with market insights</Text>
            </Card>
          </TabPanel>
        </TabPanels>
      </TabGroup>
    </div>
  )
}

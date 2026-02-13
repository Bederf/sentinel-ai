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
  Breadcrumbs,
  BreadcrumbItem,
} from '@tremor/react'
import {
  ChevronLeft,
  FileText,
  BarChart3,
  Plus,
} from 'lucide-react'
import type { QuoteResponse } from '@/lib/api'
import QuoteGenerator from './QuoteGenerator'
import SensitivityAnalysis from './SensitivityAnalysis'
import QuotePreview from './QuotePreview'

interface CommercialIntelligenceDashboardProps {
  buildingId: string
  buildingName?: string
  onClose?: () => void
}

export default function CommercialIntelligenceDashboard({
  buildingId,
  buildingName = 'Building',
  onClose,
}: CommercialIntelligenceDashboardProps) {
  const [activeTab, setActiveTab] = useState(0)
  const [currentQuote, setCurrentQuote] = useState<QuoteResponse | null>(null)
  const [equipmentCodes, setEquipmentCodes] = useState<string[]>([])
  const [slaTier, setSlaTier] = useState<string>('standard')
  const [contractMonths, setContractMonths] = useState(12)

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
      {/* Breadcrumbs */}
      <Breadcrumbs>
        <BreadcrumbItem icon={ChevronLeft} onClick={onClose}>
          Buildings
        </BreadcrumbItem>
        <BreadcrumbItem>{buildingName}</BreadcrumbItem>
        <BreadcrumbItem>Commercial Intelligence</BreadcrumbItem>
      </Breadcrumbs>

      {/* Header */}
      <Card>
        <div className="flex items-start justify-between">
          <div>
            <Title>Commercial Intelligence Tools</Title>
            <Text className="text-tremor-content-subtitle mt-2">
              Generate professional quotes, analyze pricing scenarios, and
              manage commercial agreements
            </Text>
          </div>
          {currentQuote && (
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

      {/* Tab Navigation */}
      {currentQuote ? (
        // After quote generation: show generator, analysis, and preview tabs
        <TabGroup index={activeTab} onIndexChange={setActiveTab}>
          <TabList>
            <Tab icon={FileText}>Quote Details</Tab>
            <Tab icon={BarChart3}>What-If Analysis</Tab>
            <Tab icon={FileText}>Preview & Export</Tab>
          </TabList>
          <TabPanels>
            <TabPanel>
              <Card>
                <QuoteGenerator
                  buildingId={buildingId}
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
                buildingName={buildingName}
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
        <Card>
          <QuoteGenerator
            buildingId={buildingId}
            onQuoteGenerated={(quote) => {
              // Note: We need to pass additional data. This component
              // would need to be extended to track form state for this.
              handleQuoteGenerated(quote, [], 'standard', 12)
            }}
          />
        </Card>
      )}

      {/* Quick Start Tips */}
      {!currentQuote && (
        <Card className="bg-blue-50 border border-blue-200">
          <Title className="text-blue-900">Getting Started</Title>
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
              5. Use the What-If analysis tab to explore different pricing
              scenarios
            </p>
            <p>
              6. Export your final quote as PDF from the Preview tab
            </p>
          </div>
        </Card>
      )}
    </div>
  )
}

/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * Compliance Management Dashboard
 *
 * Multi-tab interface for managing OHS, Fire, Emergency Light, Legionella,
 * Electrical, and Lift compliance workflows.
 */

import { useState } from 'react'
import { TabGroup, TabList, Tab, TabPanels, TabPanel, Grid, Card, Title, Text, Badge } from '@tremor/react'
import { OHSPanel } from './OHSPanel'
import { FireEquipmentPanel } from './FireEquipmentPanel'
import { EmergencyLightPanel } from './EmergencyLightPanel'
import { LegionellaPanel } from './LegionellaPanel'
import { ElectricalCompliancePanel } from './ElectricalCompliancePanel'
import { LiftInspectionPanel } from './LiftInspectionPanel'
import { useComplianceStatus, useComplianceAudits } from '@/lib/api/compliance'

interface ComplianceDashboardProps {
  siteCode?: string
}

export function ComplianceDashboard({ siteCode }: ComplianceDashboardProps) {
  const [selectedTab, setSelectedTab] = useState(0)

  const { data: statusData, isLoading: statusLoading } = useComplianceStatus(siteCode)
  const { data: auditsData } = useComplianceAudits(siteCode)

  if (!siteCode) {
    return (
      <div className="p-6">
        <p className="text-gray-500">Select a site to view compliance data</p>
      </div>
    )
  }

  if (statusLoading) {
    return (
      <div className="p-6">
        <p className="text-gray-500">Loading compliance data...</p>
      </div>
    )
  }

  // Build tab array externally (Tremor pattern)
  const tabs = [
    { name: 'Overview', icon: '📋' },
    { name: 'OHS Compliance', icon: '⚠️' },
    { name: 'Fire Safety', icon: '🔥' },
    { name: 'Emergency Lights', icon: '💡' },
    { name: 'Legionella', icon: '💧' },
    { name: 'Electrical', icon: '⚡' },
    { name: 'Lift Safety', icon: '🛗' },
  ]

  const tabPanels = [
    // Overview Tab
    <TabPanel key="overview">
      <Grid className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <Title>Compliance Score</Title>
          <div className="text-3xl font-bold mt-2">
            {statusData?.compliance_score_percent || 0}%
          </div>
        </Card>
        <Card>
          <Title>Critical Issues</Title>
          <div className={`text-3xl font-bold mt-2 ${(statusData?.critical_issues_count || 0) > 0 ? 'text-red-600' : 'text-green-600'}`}>
            {statusData?.critical_issues_count || 0}
          </div>
        </Card>
        <Card>
          <Title>Expiring Soon (30 days)</Title>
          <div className={`text-3xl font-bold mt-2 ${(statusData?.items_expiring_30days || 0) > 0 ? 'text-yellow-600' : 'text-green-600'}`}>
            {statusData?.items_expiring_30days || 0}
          </div>
        </Card>
      </Grid>

      {/* Compliance Status Summary */}
      <Card className="mt-6">
        <Title>Compliance Status Summary</Title>
        <Grid className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <Text>OHS Compliance</Text>
              <Badge color={statusData?.summary?.ohs_status === 'compliant' ? 'green' : 'red'}>
                {statusData?.summary?.ohs_status || 'pending'}
              </Badge>
            </div>
            <div className="flex justify-between items-center">
              <Text>Fire Safety</Text>
              <Badge color={statusData?.summary?.fire_status === 'compliant' ? 'green' : 'red'}>
                {statusData?.summary?.fire_status || 'pending'}
              </Badge>
            </div>
            <div className="flex justify-between items-center">
              <Text>Electrical</Text>
              <Badge color={statusData?.summary?.electrical_status === 'compliant' ? 'green' : 'yellow'}>
                {statusData?.summary?.electrical_status || 'pending'}
              </Badge>
            </div>
          </div>
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <Text>Legionella</Text>
              <Badge color={statusData?.summary?.legionella_status === 'compliant' ? 'green' : 'red'}>
                {statusData?.summary?.legionella_status || 'pending'}
              </Badge>
            </div>
            <div className="flex justify-between items-center">
              <Text>Lift Safety</Text>
              <Badge color={statusData?.summary?.lift_status === 'compliant' ? 'green' : 'red'}>
                {statusData?.summary?.lift_status || 'pending'}
              </Badge>
            </div>
            <div className="flex justify-between items-center">
              <Text>Overdue Items</Text>
              <Badge color={statusData?.overdue_inspections ? 'red' : 'green'}>
                {statusData?.overdue_inspections || 0}
              </Badge>
            </div>
          </div>
        </Grid>
      </Card>

      {/* Recent Audits */}
      {auditsData?.audits && auditsData.audits.length > 0 && (
        <Card className="mt-6">
          <Title>Recent Audits</Title>
          <table className="w-full mt-4 text-sm">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2">Type</th>
                <th className="text-left py-2">Status</th>
                <th className="text-left py-2">Date</th>
              </tr>
            </thead>
            <tbody>
              {auditsData.audits.slice(0, 5).map((audit) => (
                <tr key={audit.id} className="border-b hover:bg-gray-50">
                  <td className="py-2">{audit.compliance_type}</td>
                  <td className="py-2">
                    <span
                      className={`px-2 py-1 rounded text-xs font-semibold
                      ${
                        audit.status === 'closed'
                          ? 'bg-green-100 text-green-800'
                          : audit.status === 'approved'
                            ? 'bg-blue-100 text-blue-800'
                            : 'bg-yellow-100 text-yellow-800'
                      }
                    `}
                    >
                      {audit.status}
                    </span>
                  </td>
                  <td className="py-2">{new Date(audit.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </TabPanel>,

    <OHSPanel key="ohs" siteCode={siteCode} />,
    <FireEquipmentPanel key="fire" siteCode={siteCode} />,
    <EmergencyLightPanel key="emerg" siteCode={siteCode} />,
    <LegionellaPanel key="legionella" siteCode={siteCode} />,
    <ElectricalCompliancePanel key="electrical" siteCode={siteCode} />,
    <LiftInspectionPanel key="lift" siteCode={siteCode} />,
  ] as unknown as React.ReactElement[]

  return (
    <div className="p-6">
      <h1 className="text-3xl font-bold mb-6">Compliance Management</h1>

      <TabGroup index={selectedTab} onIndexChange={setSelectedTab}>
        <TabList className="mb-4 overflow-x-auto">
          {tabs.map((tab) => (
            <Tab key={tab.name}>
              {tab.icon} {tab.name}
            </Tab>
          ))}
        </TabList>

        <TabPanels>{tabPanels}</TabPanels>
      </TabGroup>
    </div>
  )
}

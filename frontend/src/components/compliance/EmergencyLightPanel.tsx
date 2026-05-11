/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * Emergency Light Testing Panel
 *
 * IEC 62034 battery health monitoring and daily auto-test scheduling.
 */

import { Card, Title, Text, Grid } from '@tremor/react'
import { useEmergencyLightStatus, useRecordEmergencyLightTest } from '@/lib/api/compliance'

interface EmergencyLightPanelProps {
  siteCode: string
}

export function EmergencyLightPanel({ siteCode }: EmergencyLightPanelProps) {
  const { data: statusData, isLoading } = useEmergencyLightStatus(siteCode)
  const { mutate: recordTest } = useRecordEmergencyLightTest()

  const _handleRecordTest = (lightCode: string) => {
    recordTest(
      {
        lightCode,
        batteryHealth: 85,
        testResult: 'pass',
      },
      {
        onSuccess: () => {
          // Test recorded, data will refresh via React Query
        },
      }
    )
  }

  if (isLoading) {
    return (
      <div className="p-6">
        <p className="text-gray-500">Loading emergency light data...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Grid className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <Title>Total Lights</Title>
          <div className="text-3xl font-bold mt-2">
            {statusData?.summary ? Object.keys(statusData.summary).length : 0}
          </div>
        </Card>
        <Card>
          <Title>Battery Alerts</Title>
          <div className="text-3xl font-bold mt-2 text-yellow-600">
            {statusData?.high_risk_items_count || 0}
          </div>
          <Text className="text-xs mt-2">Battery health &lt; 75%</Text>
        </Card>
        <Card>
          <Title>Auto-Test Schedule</Title>
          <div className="text-sm mt-2 text-gray-600">Daily: 01:00-01:30 UTC</div>
        </Card>
      </Grid>

      <Card>
        <Title>Emergency Light Status</Title>
        <Text className="text-sm mt-2 mb-4">IEC 62034 compliance - Battery health trend monitoring</Text>

        <div className="mt-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2">Light Code</th>
                <th className="text-left py-2">Location</th>
                <th className="text-left py-2">Battery Health</th>
                <th className="text-left py-2">Last Test</th>
                <th className="text-left py-2">Status</th>
                <th className="text-left py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b hover:bg-gray-50">
                <td colSpan={6} className="py-4 text-center text-gray-500">
                  No emergency lights configured. Emergency lights are automatically tested daily between 01:00-01:30 UTC.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>

      {/* Battery Health Trends */}
      <Card>
        <Title>Battery Health Trends</Title>
        <Text className="text-sm mt-2 mb-4">Historical battery degradation over time</Text>
        <div className="mt-4 p-8 text-center text-gray-500">
          Trend chart placeholder - Shows 90-day battery health history
        </div>
      </Card>

      {/* Alert Thresholds */}
      <Card className="border-l-4 border-yellow-500 bg-yellow-50">
        <Title className="text-sm">Battery Alert Thresholds</Title>
        <Text className="text-xs mt-2">
          <ul className="list-disc list-inside mt-2 space-y-1">
            <li>75% battery health: Alert (3-hour runtime minimum)</li>
            <li>Daily auto-tests run 01:00-01:30 UTC per IEC 62034</li>
            <li>Trend tracking shows degradation over 90 days</li>
          </ul>
        </Text>
      </Card>
    </div>
  )
}

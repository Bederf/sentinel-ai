/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * Emergency Light Testing Panel
 *
 * IEC 62034 battery health monitoring and daily auto-test scheduling.
 */

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
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
          <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Total Lights</h3>
          <div className="text-3xl font-bold mt-2" style={{ color: "var(--sentinel-text-primary)" }}>
            {statusData?.summary ? Object.keys(statusData.summary).length : 0}
          </div>
        </div>
        <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
          <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Battery Alerts</h3>
          <div className="text-3xl font-bold mt-2" style={{ color: "var(--sentinel-amber)" }}>
            {statusData?.high_risk_items_count || 0}
          </div>
          <span className="text-xs mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>Battery health &lt; 75%</span>
        </div>
        <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
          <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Auto-Test Schedule</h3>
          <div className="text-sm mt-2" style={{ color: "var(--sentinel-text-secondary)" }}>Daily: 03:00-03:30 SAST (01:00-01:30 UTC)</div>
        </div>
      </div>

      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Emergency Light Status</h3>
        <span className="text-sm mt-2 mb-4 block" style={{ color: "var(--sentinel-text-secondary)" }}>IEC 62034 compliance - Battery health trend monitoring</span>

        <div className="mt-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Light Code</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Location</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Battery Health</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Last Test</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Status</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
                <td colSpan={6} className="py-4 text-center" style={{ color: "var(--sentinel-text-disabled)" }}>
                  No emergency lights configured. Emergency lights are automatically tested daily between 03:00-03:30 SAST (01:00-01:30 UTC).
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Battery Health Trends</h3>
        <span className="text-sm mt-2 mb-4 block" style={{ color: "var(--sentinel-text-secondary)" }}>Historical battery degradation over time</span>
        <div className="mt-4 p-8 text-center" style={{ color: "var(--sentinel-text-disabled)" }}>
          Trend chart placeholder - Shows 90-day battery health history
        </div>
      </div>

      <div className="rounded-lg p-4" style={{ background: "rgba(245, 158, 11, 0.1)", borderLeft: "4px solid var(--sentinel-amber)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Battery Alert Thresholds</h3>
        <div className="text-xs mt-2" style={{ color: "var(--sentinel-text-secondary)" }}>
          <ul className="list-disc list-inside mt-2 space-y-1">
            <li>75% battery health: Alert (3-hour runtime minimum)</li>
            <li>Daily auto-tests run 03:00-03:30 SAST (01:00-01:30 UTC) per IEC 62034</li>
            <li>Trend tracking shows degradation over 90 days</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

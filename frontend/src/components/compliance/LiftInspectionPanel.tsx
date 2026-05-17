/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * Lift Inspection Panel
 *
 * 6-month periodic, annual insurance, and post-repair inspection scheduling.
 */

import { useRecordLiftTestResults } from '@/lib/api/compliance'
import { useState } from 'react'

interface LiftInspectionPanelProps {
  siteCode: string
}

interface TestFormData {
  liftCode: string
  brake_load_test: boolean
  speed_governor_test: boolean
  emergency_stop_test: boolean
}

export function LiftInspectionPanel({ siteCode: _siteCode }: LiftInspectionPanelProps) {
  const { mutate: recordTestResults, isPending } = useRecordLiftTestResults()
  const [now] = useState(() => Date.now()) // Stable reference time for render purity
  const [showTestForm, setShowTestForm] = useState(false)
  const [testFormData, setTestFormData] = useState<TestFormData>({
    liftCode: '',
    brake_load_test: true,
    speed_governor_test: true,
    emergency_stop_test: true,
  })

  const lifts = [
    { code: 'LIFT-001', location: 'Passenger Lift - Main Building', type: 'periodic_6monthly' },
    { code: 'LIFT-002', location: 'Service Lift - Basement', type: 'annual_insurance' },
    { code: 'LIFT-003', location: 'Freight Lift - Warehouse', type: 'periodic_6monthly' },
  ]

  const handleRecordTestResults = () => {
    if (!testFormData.liftCode) return
    recordTestResults(
      {
        liftCode: testFormData.liftCode,
        testResults: {
          brake_load_test: testFormData.brake_load_test,
          speed_governor_test: testFormData.speed_governor_test,
          emergency_stop_test: testFormData.emergency_stop_test,
        },
      },
      {
        onSuccess: () => {
          setShowTestForm(false)
          setTestFormData({
            liftCode: '',
            brake_load_test: true,
            speed_governor_test: true,
            emergency_stop_test: true,
          })
        },
      }
    )
  }

  return (
    <div className="space-y-6">
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Lift Safety Inspection Scheduling</h3>
        <span className="text-sm mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>South African lift safety regulations - Periodic, annual, and post-repair testing</span>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
          <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
            <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>6-Month Periodic</h3>
            <span className="text-xs mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>Standard periodic inspection cycle for passenger lifts</span>
          </div>
          <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
            <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Annual Insurance</h3>
            <span className="text-xs mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>Annual compliance check required for insurance validity</span>
          </div>
          <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
            <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Post-Repair</h3>
            <span className="text-xs mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>Required after major repair or component replacement</span>
          </div>
        </div>
      </div>

      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Lift Equipment Inventory</h3>
          <button
            className="px-3 py-1.5 text-xs rounded font-medium"
            style={{ background: "var(--sentinel-bg-secondary)", color: "var(--sentinel-text-primary)" }}
            onClick={() => setShowTestForm(!showTestForm)}
          >
            {showTestForm ? 'Cancel' : 'Record Test'}
          </button>
        </div>

        {showTestForm && (
          <div className="rounded p-4 mb-4" style={{ background: "var(--sentinel-bg-secondary)", border: "1px solid var(--sentinel-border)" }}>
            <div className="mb-4">
              <label className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Lift Code</label>
              <select
                value={testFormData.liftCode}
                onChange={(e) => setTestFormData({ ...testFormData, liftCode: e.target.value })}
                className="w-full mt-1 px-3 py-2 border rounded text-sm"
                style={{ borderColor: "var(--sentinel-border)", background: "var(--sentinel-bg-panel)", color: "var(--sentinel-text-primary)" }}
              >
                <option value="">Select lift...</option>
                {lifts.map((lift) => (
                  <option key={lift.code} value={lift.code}>
                    {lift.code} - {lift.location}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-3 mb-4">
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="brake-test"
                  checked={testFormData.brake_load_test}
                  onChange={(e) => setTestFormData({ ...testFormData, brake_load_test: e.target.checked })}
                  className="h-4 w-4"
                />
                <label htmlFor="brake-test" className="ml-2 text-sm" style={{ color: "var(--sentinel-text-primary)" }}>
                  Brake Load Test
                </label>
              </div>
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="governor-test"
                  checked={testFormData.speed_governor_test}
                  onChange={(e) => setTestFormData({ ...testFormData, speed_governor_test: e.target.checked })}
                  className="h-4 w-4"
                />
                <label htmlFor="governor-test" className="ml-2 text-sm" style={{ color: "var(--sentinel-text-primary)" }}>
                  Speed Governor Test
                </label>
              </div>
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="emc-test"
                  checked={testFormData.emergency_stop_test}
                  onChange={(e) => setTestFormData({ ...testFormData, emergency_stop_test: e.target.checked })}
                  className="h-4 w-4"
                />
                <label htmlFor="emc-test" className="ml-2 text-sm" style={{ color: "var(--sentinel-text-primary)" }}>
                  Emergency Stop Test
                </label>
              </div>
            </div>

            <button
              className="px-3 py-1.5 text-xs rounded font-medium"
              style={{ background: "var(--sentinel-blue)", color: "white" }}
              disabled={isPending}
              onClick={handleRecordTestResults}
            >
              Save Test Results
            </button>
          </div>
        )}

        <table className="w-full text-sm mt-4">
          <thead>
            <tr className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
              <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Lift Code</th>
              <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Location</th>
              <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Inspection Type</th>
              <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Last Inspection</th>
              <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Next Due</th>
              <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Compliance</th>
              <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Recorded By</th>
            </tr>
          </thead>
          <tbody>
            {lifts.map((lift) => (
              <tr key={lift.code} className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
                <td className="py-2 font-medium">{lift.code}</td>
                <td className="py-2">{lift.location}</td>
                <td className="py-2 capitalize">{lift.type.replace(/_/g, ' ')}</td>
                <td className="py-2">{new Date(now - 30 * 24 * 60 * 60 * 1000).toLocaleDateString()}</td>
                <td className="py-2">
                  {new Date(now + (lift.type === 'periodic_6monthly' ? 180 : 365) * 24 * 60 * 60 * 1000).toLocaleDateString()}
                </td>
                <td className="py-2">
                  <span
                    className="text-xs px-2 py-0.5 rounded font-medium"
                    style={{ background: "rgba(34, 197, 94, 0.15)", color: "var(--sentinel-green)" }}
                  >
                    Compliant
                  </span>
                </td>
                <td className="py-2" style={{ color: "var(--sentinel-text-secondary)" }}>
                  <span className="text-xs">System</span>
                  <span className="block text-xs opacity-60">{new Date().toLocaleDateString()}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Lift Test Requirements</h3>
        <span className="text-sm mt-2 mb-4 block" style={{ color: "var(--sentinel-text-secondary)" }}>South African lift safety standards - Key test points</span>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
            <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Brake Load Test</h3>
            <span className="text-xs mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>
              Verifies emergency brake capacity and safe stopping distance from full speed
            </span>
          </div>
          <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
            <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Speed Governor Test</h3>
            <span className="text-xs mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>
              Confirms overspeed protection triggers at designated threshold
            </span>
          </div>
          <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
            <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Emergency Stop Test</h3>
            <span className="text-xs mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>
              Tests all emergency stop buttons and rope-break switches for immediate halt
            </span>
          </div>
        </div>
      </div>

      <div className="rounded-lg p-4" style={{ background: "rgba(239, 68, 68, 0.1)", borderLeft: "4px solid var(--sentinel-red)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Non-Compliance Alert Protocol</h3>
        <div className="text-xs mt-2" style={{ color: "var(--sentinel-text-secondary)" }}>
          <ul className="list-disc list-inside space-y-1 mt-2">
            <li>Failed test items must be recorded and remediated before next use</li>
            <li>Work orders auto-generated for non-compliant test results</li>
            <li>Lift taken out of service until remediation verified</li>
            <li>Post-repair inspection required after any failed component replacement</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

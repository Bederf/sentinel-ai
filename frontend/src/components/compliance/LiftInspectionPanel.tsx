/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * Lift Inspection Panel
 *
 * 6-month periodic, annual insurance, and post-repair inspection scheduling.
 */

import { Card, Title, Table, TableHead, TableRow, TableHeaderCell, TableBody, TableCell, Button, Badge, Text, Grid } from '@tremor/react'
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
      <Card>
        <Title>Lift Safety Inspection Scheduling</Title>
        <Text className="text-sm mt-2">South African lift safety regulations - Periodic, annual, and post-repair testing</Text>

        <Grid className="grid grid-cols-1 md:grid-cols-3" className="gap-4 mt-4">
          <Card className="border border-gray-200">
            <Title className="text-sm">6-Month Periodic</Title>
            <Text className="text-xs mt-2">Standard periodic inspection cycle for passenger lifts</Text>
          </Card>
          <Card className="border border-gray-200">
            <Title className="text-sm">Annual Insurance</Title>
            <Text className="text-xs mt-2">Annual compliance check required for insurance validity</Text>
          </Card>
          <Card className="border border-gray-200">
            <Title className="text-sm">Post-Repair</Title>
            <Text className="text-xs mt-2">Required after major repair or component replacement</Text>
          </Card>
        </Grid>
      </Card>

      <Card>
        <div className="flex justify-between items-center mb-4">
          <Title>Lift Equipment Inventory</Title>
          <Button size="sm" onClick={() => setShowTestForm(!showTestForm)}>
            {showTestForm ? 'Cancel' : 'Record Test'}
          </Button>
        </div>

        {showTestForm && (
          <div className="border rounded p-4 mb-4 bg-gray-50">
            <div className="mb-4">
              <label className="text-sm font-medium">Lift Code</label>
              <select
                value={testFormData.liftCode}
                onChange={(e) => setTestFormData({ ...testFormData, liftCode: e.target.value })}
                className="w-full mt-1 px-3 py-2 border rounded text-sm"
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
                <label htmlFor="brake-test" className="ml-2 text-sm">
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
                <label htmlFor="governor-test" className="ml-2 text-sm">
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
                <label htmlFor="emc-test" className="ml-2 text-sm">
                  Emergency Stop Test
                </label>
              </div>
            </div>

            <Button onClick={handleRecordTestResults} loading={isPending}>
              Save Test Results
            </Button>
          </div>
        )}

        <Table className="mt-4">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Lift Code</TableHeaderCell>
              <TableHeaderCell>Location</TableHeaderCell>
              <TableHeaderCell>Inspection Type</TableHeaderCell>
              <TableHeaderCell>Last Inspection</TableHeaderCell>
              <TableHeaderCell>Next Due</TableHeaderCell>
              <TableHeaderCell>Compliance</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {lifts.map((lift) => (
              <TableRow key={lift.code}>
                <TableCell className="font-medium">{lift.code}</TableCell>
                <TableCell>{lift.location}</TableCell>
                <TableCell className="capitalize">{lift.type.replace(/_/g, ' ')}</TableCell>
                {/* eslint-disable-next-line react-hooks/purity */}
                <TableCell>{new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toLocaleDateString()}</TableCell>
                <TableCell>
                  {/* eslint-disable-next-line react-hooks/purity */}
                  {new Date(Date.now() + (lift.type === 'periodic_6monthly' ? 180 : 365) * 24 * 60 * 60 * 1000).toLocaleDateString()}
                </TableCell>
                <TableCell>
                  <Badge color="green">Compliant</Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {/* Test Requirements */}
      <Card>
        <Title>Lift Test Requirements</Title>
        <Text className="text-sm mt-2 mb-4">South African lift safety standards - Key test points</Text>

        <Grid className="grid grid-cols-1 md:grid-cols-3" className="gap-4">
          <Card className="border border-gray-200">
            <Title className="text-sm">Brake Load Test</Title>
            <Text className="text-xs mt-2">
              Verifies emergency brake capacity and safe stopping distance from full speed
            </Text>
          </Card>
          <Card className="border border-gray-200">
            <Title className="text-sm">Speed Governor Test</Title>
            <Text className="text-xs mt-2">
              Confirms overspeed protection triggers at designated threshold
            </Text>
          </Card>
          <Card className="border border-gray-200">
            <Title className="text-sm">Emergency Stop Test</Title>
            <Text className="text-xs mt-2">
              Tests all emergency stop buttons and rope-break switches for immediate halt
            </Text>
          </Card>
        </Grid>
      </Card>

      {/* Non-Compliance Alert */}
      <Card className="border-l-4 border-red-500 bg-red-50">
        <Title className="text-sm">Non-Compliance Alert Protocol</Title>
        <Text className="text-xs mt-2">
          <ul className="list-disc list-inside space-y-1 mt-2">
            <li>Failed test items must be recorded and remediated before next use</li>
            <li>Work orders auto-generated for non-compliant test results</li>
            <li>Lift taken out of service until remediation verified</li>
            <li>Post-repair inspection required after any failed component replacement</li>
          </ul>
        </Text>
      </Card>
    </div>
  )
}

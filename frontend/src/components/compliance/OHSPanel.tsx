/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * OHS Act Compliance Panel
 *
 * Generates and tracks safety compliance checklists across zones.
 */

import { Card, Title, Text, Button, Grid } from '@tremor/react'
import { useGenerateOhsChecklist } from '@/lib/api/compliance'

interface OHSPanelProps {
  siteCode: string
}

export function OHSPanel({ siteCode }: OHSPanelProps) {
  const { mutate: generateChecklist, isPending } = useGenerateOhsChecklist()

  const zones = ['Zone-001', 'Zone-100', 'Zone-200', 'Zone-101']

  const handleGenerateChecklist = (zoneId: string) => {
    generateChecklist(
      { siteCode, zoneId },
      {
        onSuccess: () => {
          // Task created, list will refresh via React Query
        },
      }
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <Title>OHS Act Compliance Checklists</Title>
        <Text className="mt-2 mb-4">Generate and track safety compliance across zones</Text>

        <Grid className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {zones.map((zone) => (
            <Card key={zone} className="border border-gray-200">
              <div className="flex justify-between items-center">
                <div>
                  <Title className="text-lg">{zone}</Title>
                </div>
                <Button
                  size="sm"
                  onClick={() => handleGenerateChecklist(zone)}
                  loading={isPending}
                >
                  Generate
                </Button>
              </div>
            </Card>
          ))}
        </Grid>
      </Card>

      {/* Active Checklists */}
      <Card>
        <Title>Active Checklists</Title>
        <div className="mt-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2">Zone</th>
                <th className="text-left py-2">Items</th>
                <th className="text-left py-2">Status</th>
                <th className="text-left py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b hover:bg-gray-50">
                <td colSpan={4} className="py-4 text-center text-gray-500">
                  No active checklists yet. Generate a new checklist above.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>

      {/* Information */}
      <Card className="border-l-4 border-blue-500 bg-blue-50">
        <Title className="text-sm">OHS Act Requirements</Title>
        <Text className="text-xs mt-2">
          Checklists are generated for each zone following South African OHS Act requirements. Each checklist
          tracks hazard identification, risk assessment, and control measures.
        </Text>
      </Card>
    </div>
  )
}

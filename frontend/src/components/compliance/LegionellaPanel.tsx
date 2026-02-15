// @ts-nocheck
/**
 * Legionella Risk Assessment Panel
 *
 * SABS standard risk matrix, water temperature monitoring, and biocide treatment scheduling.
 */

import { Card, Title, Text, Button, Grid, Badge } from '@tremor/react'
import { useAssessLegionellaRisk } from '@/lib/api/compliance'
import { useState } from 'react'

interface LegionellaPanelProps {
  siteCode: string
}

export function LegionellaPanel({ siteCode }: LegionellaPanelProps) {
  const { mutate: assessRisk, isPending } = useAssessLegionellaRisk()
  const [formData, setFormData] = useState({
    towerCode: '',
    waterTemp: 30,
    lastTreatment: new Date().toISOString().split('T')[0],
  })

  const handleAssessRisk = () => {
    if (!formData.towerCode) return
    assessRisk(
      {
        towerCode: formData.towerCode,
        waterTemp: formData.waterTemp,
        lastTreatment: formData.lastTreatment,
      },
      {
        onSuccess: () => {
          // Risk assessed, data will refresh
          setFormData({ towerCode: '', waterTemp: 30, lastTreatment: new Date().toISOString().split('T')[0] })
        },
      }
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <Title>Legionella Risk Assessment</Title>
        <Text className="text-sm mt-2 mb-4">SABS standard - Water temperature monitoring and control measures</Text>

        <Grid numColsSm={1} numColsMd={3} className="gap-4">
          <div>
            <label className="text-sm font-medium">Cooling Tower Code</label>
            <input
              type="text"
              placeholder="e.g., CT-001"
              value={formData.towerCode}
              onChange={(e) => setFormData({ ...formData, towerCode: e.target.value })}
              className="w-full mt-1 px-3 py-2 border rounded text-sm"
            />
          </div>
          <div>
            <label className="text-sm font-medium">Water Temperature (°C)</label>
            <input
              type="number"
              min="0"
              max="100"
              value={formData.waterTemp}
              onChange={(e) => setFormData({ ...formData, waterTemp: parseInt(e.target.value) })}
              className="w-full mt-1 px-3 py-2 border rounded text-sm"
            />
          </div>
          <div>
            <label className="text-sm font-medium">Last Treatment Date</label>
            <input
              type="date"
              value={formData.lastTreatment}
              onChange={(e) => setFormData({ ...formData, lastTreatment: e.target.value })}
              className="w-full mt-1 px-3 py-2 border rounded text-sm"
            />
          </div>
        </Grid>

        <Button className="mt-4" onClick={handleAssessRisk} loading={isPending}>
          Assess Risk
        </Button>
      </Card>

      {/* Risk Matrix */}
      <Card>
        <Title>Risk Assessment Matrix</Title>
        <Text className="text-sm mt-2 mb-4">Assessment based on water temperature and treatment history</Text>

        <Grid numColsSm={1} numColsMd={3} className="gap-4 mt-4">
          <Card className="border-l-4 border-red-500 bg-red-50">
            <div className="flex items-center justify-between">
              <div>
                <Title className="text-sm">High Risk</Title>
                <Text className="text-xs">20-45°C + &gt;30 days untreated</Text>
              </div>
              <Badge color="red">⚠️</Badge>
            </div>
          </Card>

          <Card className="border-l-4 border-yellow-500 bg-yellow-50">
            <div className="flex items-center justify-between">
              <div>
                <Title className="text-sm">Medium Risk</Title>
                <Text className="text-xs">45-50°C or recent treatment</Text>
              </div>
              <Badge color="yellow">⚠️</Badge>
            </div>
          </Card>

          <Card className="border-l-4 border-green-500 bg-green-50">
            <div className="flex items-center justify-between">
              <div>
                <Title className="text-sm">Low Risk</Title>
                <Text className="text-xs">&lt;20°C or &lt;30 days treated</Text>
              </div>
              <Badge color="green">✓</Badge>
            </div>
          </Card>
        </Grid>
      </Card>

      {/* Treatment Schedule */}
      <Card>
        <Title>Treatment Schedule</Title>
        <Text className="text-sm mt-2 mb-4">Maintenance intervals by risk level</Text>

        <table className="w-full text-sm mt-4">
          <thead>
            <tr className="border-b">
              <th className="text-left py-2">Risk Level</th>
              <th className="text-left py-2">Biocide Interval</th>
              <th className="text-left py-2">Cleaning</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b">
              <td className="py-2">
                <Badge color="red">High</Badge>
              </td>
              <td className="py-2">14 days</td>
              <td className="py-2">Weekly</td>
            </tr>
            <tr className="border-b">
              <td className="py-2">
                <Badge color="yellow">Medium</Badge>
              </td>
              <td className="py-2">30 days</td>
              <td className="py-2">Bi-weekly</td>
            </tr>
            <tr>
              <td className="py-2">
                <Badge color="green">Low</Badge>
              </td>
              <td className="py-2">90 days</td>
              <td className="py-2">Monthly</td>
            </tr>
          </tbody>
        </table>
      </Card>

      {/* Information */}
      <Card className="border-l-4 border-blue-500 bg-blue-50">
        <Title className="text-sm">Legionella Control Measures</Title>
        <Text className="text-xs mt-2">
          <ul className="list-disc list-inside space-y-1 mt-2">
            <li>Temperature control: Maintain &lt;20°C (low) or &gt;55°C (hot water)</li>
            <li>Biocide treatment: 14-day to 90-day intervals based on risk</li>
            <li>UV systems and filtration for additional control</li>
            <li>Regular cleaning and descaling to remove biofilm</li>
          </ul>
        </Text>
      </Card>
    </div>
  )
}

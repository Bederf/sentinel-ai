/**
 * Fire Equipment Tracking Panel
 *
 * NFPA 10 and SABS 4066 compliance for fire extinguishers, hose reels, hydrants, etc.
 */

import { Card, Title, Table, TableHead, TableRow, TableHeaderCell, TableBody, TableCell, Button, Badge, Text } from '@tremor/react'
import { useFireEquipment, useScheduleFireInspection } from '@/lib/api/compliance'

interface FireEquipmentPanelProps {
  siteCode: string
}

export function FireEquipmentPanel({ siteCode }: FireEquipmentPanelProps) {
  const { data: equipment, isLoading } = useFireEquipment(siteCode)
  const { mutate: scheduleInspection } = useScheduleFireInspection()

  const handleScheduleInspection = (equipmentId: string) => {
    scheduleInspection(equipmentId)
  }

  if (isLoading) {
    return (
      <div className="p-6">
        <p className="text-gray-500">Loading fire equipment...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <Title>Fire Equipment Inventory & Inspection Scheduling</Title>
        <Text className="text-sm mt-2 mb-4">NFPA 10 & SABS 4066 Compliance</Text>

        {equipment && equipment.length > 0 ? (
          <Table className="mt-4">
            <TableHead>
              <TableRow>
                <TableHeaderCell>Equipment Type</TableHeaderCell>
                <TableHeaderCell>Location</TableHeaderCell>
                <TableHeaderCell>Last Inspection</TableHeaderCell>
                <TableHeaderCell>Next Due</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
                <TableHeaderCell>Action</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {equipment.map((item) => {
                /* eslint-disable react-hooks/purity */
                const daysUntilDue = Math.ceil(
                  (new Date(item.next_inspection_date).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
                )
                /* eslint-enable react-hooks/purity */
                const isOverdue = daysUntilDue < 0
                const isDueSoon = daysUntilDue < 30 && daysUntilDue >= 0

                return (
                  <TableRow key={item.id}>
                    <TableCell className="capitalize">{item.equipment_type.replace(/_/g, ' ')}</TableCell>
                    <TableCell>{item.location_description}</TableCell>
                    <TableCell>{new Date(item.last_inspection_date).toLocaleDateString()}</TableCell>
                    <TableCell>{new Date(item.next_inspection_date).toLocaleDateString()}</TableCell>
                    <TableCell>
                      <Badge
                        color={isOverdue ? 'red' : isDueSoon ? 'yellow' : 'green'}
                      >
                        {isOverdue ? 'OVERDUE' : isDueSoon ? 'DUE SOON' : 'OK'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Button
                        size="xs"
                        onClick={() => handleScheduleInspection(item.id)}
                      >
                        Schedule
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        ) : (
          <div className="mt-4 p-4 text-center text-gray-500">
            No fire equipment configured for this site.
          </div>
        )}
      </Card>

      {/* Inspection History */}
      <Card>
        <Title>Recent Inspections (12 months)</Title>
        <Text className="text-sm mt-2">Calendar view of inspection schedules and completion dates</Text>
        <div className="mt-4 p-4 text-center text-gray-500">
          Inspection calendar visualization
        </div>
      </Card>

      {/* Compliance Info */}
      <Card className="border-l-4 border-red-500 bg-red-50">
        <Title className="text-sm">Fire Safety Standards</Title>
        <Text className="text-xs mt-2">
          Fire equipment is subject to 12-month inspection intervals per NFPA 10. Pressure tests validate
          extinguisher integrity. Certification expiry must be tracked and renewed before expiration.
        </Text>
      </Card>
    </div>
  )
}

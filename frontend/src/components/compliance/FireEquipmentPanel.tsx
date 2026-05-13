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
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Fire Equipment Inventory & Inspection Scheduling</h3>
        <span className="text-sm mt-2 mb-4 block" style={{ color: "var(--sentinel-text-secondary)" }}>NFPA 10 & SABS 4066 Compliance</span>

        {equipment && equipment.length > 0 ? (
          <table className="w-full text-sm mt-4">
            <thead>
              <tr className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Equipment Type</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Location</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Last Inspection</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Next Due</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Status</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {equipment.map((item) => {
                const daysUntilDue = Math.ceil(
                  (new Date(item.next_inspection_date).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
                )
                const isOverdue = daysUntilDue < 0
                const isDueSoon = daysUntilDue < 30 && daysUntilDue >= 0

                return (
                  <tr key={item.id} className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
                    <td className="py-2 capitalize">{item.equipment_type.replace(/_/g, ' ')}</td>
                    <td className="py-2">{item.location_description}</td>
                    <td className="py-2">{new Date(item.last_inspection_date).toLocaleDateString()}</td>
                    <td className="py-2">{new Date(item.next_inspection_date).toLocaleDateString()}</td>
                    <td className="py-2">
                      <span
                        className="text-xs px-2 py-0.5 rounded font-medium"
                        style={{
                          background: isOverdue ? "rgba(239, 68, 68, 0.15)" : isDueSoon ? "rgba(245, 158, 11, 0.15)" : "rgba(34, 197, 94, 0.15)",
                          color: isOverdue ? "var(--sentinel-red)" : isDueSoon ? "var(--sentinel-amber)" : "var(--sentinel-green)",
                        }}
                      >
                        {isOverdue ? 'OVERDUE' : isDueSoon ? 'DUE SOON' : 'OK'}
                      </span>
                    </td>
                    <td className="py-2">
                      <button
                        className="px-2 py-1 text-xs rounded font-medium"
                        style={{ background: "var(--sentinel-bg-secondary)", color: "var(--sentinel-text-primary)" }}
                        onClick={() => handleScheduleInspection(item.id)}
                      >
                        Schedule
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : (
          <div className="mt-4 p-4 text-center" style={{ color: "var(--sentinel-text-disabled)" }}>
            No fire equipment configured for this site.
          </div>
        )}
      </div>

      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Recent Inspections (12 months)</h3>
        <span className="text-sm mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>Calendar view of inspection schedules and completion dates</span>
        <div className="mt-4 p-4 text-center" style={{ color: "var(--sentinel-text-disabled)" }}>
          Inspection calendar visualization
        </div>
      </div>

      <div className="rounded-lg p-4" style={{ background: "rgba(239, 68, 68, 0.1)", borderLeft: "4px solid var(--sentinel-red)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Fire Safety Standards</h3>
        <span className="text-xs mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>
          Fire equipment is subject to 12-month inspection intervals per NFPA 10. Pressure tests validate
          extinguisher integrity. Certification expiry must be tracked and renewed before expiration.
        </span>
      </div>
    </div>
  )
}

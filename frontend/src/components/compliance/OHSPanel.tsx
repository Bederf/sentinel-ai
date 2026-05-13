/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * OHS Act Compliance Panel
 *
 * Generates and tracks safety compliance checklists across zones.
 */

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
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>OHS Act Compliance Checklists</h3>
        <span className="mt-2 mb-4 block" style={{ color: "var(--sentinel-text-secondary)" }}>Generate and track safety compliance across zones</span>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {zones.map((zone) => (
            <div key={zone} className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="text-lg font-medium" style={{ color: "var(--sentinel-text-primary)" }}>{zone}</h3>
                </div>
                <button
                  className="px-3 py-1.5 text-xs rounded font-medium"
                  style={{ background: "var(--sentinel-bg-secondary)", color: "var(--sentinel-text-primary)" }}
                  disabled={isPending}
                  onClick={() => handleGenerateChecklist(zone)}
                >
                  Generate
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Active Checklists</h3>
        <div className="mt-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Zone</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Items</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Status</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
                <td colSpan={4} className="py-4 text-center" style={{ color: "var(--sentinel-text-disabled)" }}>
                  No active checklists yet. Generate a new checklist above.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-lg p-4" style={{ background: "rgba(59, 130, 246, 0.1)", borderLeft: "4px solid var(--sentinel-blue)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>OHS Act Requirements</h3>
        <span className="text-xs mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>
          Checklists are generated for each zone following South African OHS Act requirements. Each checklist
          tracks hazard identification, risk assessment, and control measures.
        </span>
      </div>
    </div>
  )
}

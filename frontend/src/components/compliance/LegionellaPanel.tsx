/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * Legionella Risk Assessment Panel
 *
 * SABS standard risk matrix, water temperature monitoring, and biocide treatment scheduling.
 */

import { useAssessLegionellaRisk } from '@/lib/api/compliance'
import { useState } from 'react'

interface LegionellaPanelProps {
  siteCode: string
}

export function LegionellaPanel({ siteCode: _siteCode }: LegionellaPanelProps) {
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
          setFormData({ towerCode: '', waterTemp: 30, lastTreatment: new Date().toISOString().split('T')[0] })
        },
      }
    )
  }

  return (
    <div className="space-y-6">
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Legionella Risk Assessment</h3>
        <span className="text-sm mt-2 mb-4 block" style={{ color: "var(--sentinel-text-secondary)" }}>SABS standard - Water temperature monitoring and control measures</span>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Cooling Tower Code</label>
            <input
              type="text"
              placeholder="e.g., CT-001"
              value={formData.towerCode}
              onChange={(e) => setFormData({ ...formData, towerCode: e.target.value })}
              className="w-full mt-1 px-3 py-2 border rounded text-sm"
              style={{ borderColor: "var(--sentinel-border)", background: "var(--sentinel-bg-panel)", color: "var(--sentinel-text-primary)" }}
            />
          </div>
          <div>
            <label className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Water Temperature (°C)</label>
            <input
              type="number"
              min="0"
              max="100"
              value={formData.waterTemp}
              onChange={(e) => setFormData({ ...formData, waterTemp: parseInt(e.target.value) })}
              className="w-full mt-1 px-3 py-2 border rounded text-sm"
              style={{ borderColor: "var(--sentinel-border)", background: "var(--sentinel-bg-panel)", color: "var(--sentinel-text-primary)" }}
            />
          </div>
          <div>
            <label className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Last Treatment Date</label>
            <input
              type="date"
              value={formData.lastTreatment}
              onChange={(e) => setFormData({ ...formData, lastTreatment: e.target.value })}
              className="w-full mt-1 px-3 py-2 border rounded text-sm"
              style={{ borderColor: "var(--sentinel-border)", background: "var(--sentinel-bg-panel)", color: "var(--sentinel-text-primary)" }}
            />
          </div>
        </div>

        <button
          className="mt-4 px-3 py-1.5 text-xs rounded font-medium"
          style={{ background: "var(--sentinel-blue)", color: "white" }}
          disabled={isPending}
          onClick={handleAssessRisk}
        >
          Assess Risk
        </button>
      </div>

      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Risk Assessment Matrix</h3>
        <span className="text-sm mt-2 mb-4 block" style={{ color: "var(--sentinel-text-secondary)" }}>Assessment based on water temperature and treatment history</span>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
          <div className="rounded-lg p-4" style={{ background: "rgba(239, 68, 68, 0.1)", borderLeft: "4px solid var(--sentinel-red)" }}>
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>High Risk</h3>
                <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>20-45°C + &gt;30 days untreated</span>
              </div>
              <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: "rgba(239, 68, 68, 0.15)", color: "var(--sentinel-red)" }}>
                ⚠️
              </span>
            </div>
          </div>

          <div className="rounded-lg p-4" style={{ background: "rgba(245, 158, 11, 0.1)", borderLeft: "4px solid var(--sentinel-amber)" }}>
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Medium Risk</h3>
                <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>45-50°C or recent treatment</span>
              </div>
              <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--sentinel-amber)" }}>
                ⚠️
              </span>
            </div>
          </div>

          <div className="rounded-lg p-4" style={{ background: "rgba(59, 130, 246, 0.1)", borderLeft: "4px solid var(--sentinel-blue)" }}>
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Marginal Risk</h3>
                <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>50-55°C — transitional zone</span>
              </div>
              <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--sentinel-blue)" }}>
                ○
              </span>
            </div>
          </div>

          <div className="rounded-lg p-4" style={{ background: "rgba(34, 197, 94, 0.1)", borderLeft: "4px solid var(--sentinel-green)" }}>
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Low Risk</h3>
                <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>&lt;20°C or &gt;55°C or &lt;30 days treated</span>
              </div>
              <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: "rgba(34, 197, 94, 0.15)", color: "var(--sentinel-green)" }}>
                ✓
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Treatment Schedule</h3>
        <span className="text-sm mt-2 mb-4 block" style={{ color: "var(--sentinel-text-secondary)" }}>Maintenance intervals by risk level</span>

        <table className="w-full text-sm mt-4">
          <thead>
            <tr className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
              <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Risk Level</th>
              <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Biocide Interval</th>
              <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Cleaning</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
              <td className="py-2">
                <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: "rgba(239, 68, 68, 0.15)", color: "var(--sentinel-red)" }}>
                  High
                </span>
              </td>
              <td className="py-2">14 days</td>
              <td className="py-2">Weekly</td>
            </tr>
            <tr className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
              <td className="py-2">
                <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--sentinel-amber)" }}>
                  Medium
                </span>
              </td>
              <td className="py-2">30 days</td>
              <td className="py-2">Bi-weekly</td>
            </tr>
            <tr className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
              <td className="py-2">
                <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--sentinel-blue)" }}>
                  Marginal
                </span>
              </td>
              <td className="py-2">60 days</td>
              <td className="py-2">Monthly</td>
            </tr>
            <tr>
              <td className="py-2">
                <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: "rgba(34, 197, 94, 0.15)", color: "var(--sentinel-green)" }}>
                  Low
                </span>
              </td>
              <td className="py-2">90 days</td>
              <td className="py-2">Monthly</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="rounded-lg p-4" style={{ background: "rgba(59, 130, 246, 0.1)", borderLeft: "4px solid var(--sentinel-blue)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Legionella Control Measures</h3>
        <div className="text-xs mt-2" style={{ color: "var(--sentinel-text-secondary)" }}>
          <ul className="list-disc list-inside space-y-1 mt-2">
            <li>Temperature control: Maintain &lt;20°C (low) or &gt;55°C (hot water)</li>
            <li>Danger zone: 20-45°C — immediate action required if untreated &gt;30 days</li>
            <li>Transitional zone: 50-55°C — not safe, monitor closely</li>
            <li>Biocide treatment: 14-day to 90-day intervals based on risk</li>
            <li>UV systems and filtration for additional control</li>
            <li>Regular cleaning and descaling to remove biofilm</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

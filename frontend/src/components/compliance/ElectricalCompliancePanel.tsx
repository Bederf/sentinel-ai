/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * Electrical Compliance Panel
 *
 * South African SABS Certificate of Compliance tracking and 5-year validity management.
 */

import { useElectricalCompliance, useTrackElectricalCertificate } from '@/lib/api/compliance'
import { useState } from 'react'

interface ElectricalCompliancePanelProps {
  siteCode: string
}

export function ElectricalCompliancePanel({ siteCode }: ElectricalCompliancePanelProps) {
  const { data: complianceData, isLoading } = useElectricalCompliance(siteCode)
  const { mutate: trackCertificate, isPending } = useTrackElectricalCertificate()
  const [showAddForm, setShowAddForm] = useState(false)
  const [formData, setFormData] = useState({
    certificate_type: 'CoC_new_installation' as const,
    issue_date: new Date().toISOString().split('T')[0],
    certifying_body: '',
    scope: '',
  })

  const handleAddCertificate = () => {
    trackCertificate(
      {
        site_code: siteCode,
        certificate_type: formData.certificate_type,
        issue_date: formData.issue_date,
        expiry_date: new Date(new Date(formData.issue_date).getTime() + 5 * 365 * 24 * 60 * 60 * 1000)
          .toISOString()
          .split('T')[0],
        certifying_body: formData.certifying_body,
        scope: formData.scope,
      },
      {
        onSuccess: () => {
          setShowAddForm(false)
          setFormData({
            certificate_type: 'CoC_new_installation',
            issue_date: new Date().toISOString().split('T')[0],
            certifying_body: '',
            scope: '',
          })
        },
      }
    )
  }

  if (isLoading) {
    return (
      <div className="p-6">
        <p className="text-gray-500">Loading electrical compliance data...</p>
      </div>
    )
  }

  const certificates = complianceData?.certificates || []

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
          <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Total Certificates</h3>
          <div className="text-3xl font-bold mt-2" style={{ color: "var(--sentinel-text-primary)" }}>{certificates.length}</div>
        </div>
        <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
          <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Active</h3>
          <div className="text-3xl font-bold mt-2" style={{ color: "var(--sentinel-green)" }}>
            {certificates.filter((c) => c.status === 'active').length}
          </div>
        </div>
        <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
          <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Expiring Soon</h3>
          <div className="text-3xl font-bold mt-2" style={{ color: "var(--sentinel-amber)" }}>
            {certificates.filter((c) => c.status?.includes('expiring')).length}
          </div>
        </div>
      </div>

      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Certificate of Compliance Tracking</h3>
          <button
            className="px-3 py-1.5 text-xs rounded font-medium"
            style={{ background: "var(--sentinel-bg-secondary)", color: "var(--sentinel-text-primary)" }}
            onClick={() => setShowAddForm(!showAddForm)}
          >
            {showAddForm ? 'Cancel' : 'Add Certificate'}
          </button>
        </div>

        {showAddForm && (
          <div className="rounded p-4 mb-4" style={{ background: "var(--sentinel-bg-secondary)", border: "1px solid var(--sentinel-border)" }}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div>
                <label className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Certificate Type</label>
                <select
                  value={formData.certificate_type}
                  onChange={(e) => setFormData({ ...formData, certificate_type: e.target.value as any })}
                  className="w-full mt-1 px-3 py-2 border rounded text-sm"
                  style={{ borderColor: "var(--sentinel-border)", background: "var(--sentinel-bg-panel)", color: "var(--sentinel-text-primary)" }}
                >
                  <option value="CoC_new_installation">CoC - New Installation</option>
                  <option value="CoC_alterations">CoC - Alterations</option>
                  <option value="SABS_inspection">SABS Inspection</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Issue Date</label>
                <input
                  type="date"
                  value={formData.issue_date}
                  onChange={(e) => setFormData({ ...formData, issue_date: e.target.value })}
                  className="w-full mt-1 px-3 py-2 border rounded text-sm"
                  style={{ borderColor: "var(--sentinel-border)", background: "var(--sentinel-bg-panel)", color: "var(--sentinel-text-primary)" }}
                />
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div>
                <label className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Certifying Body</label>
                <input
                  type="text"
                  placeholder="e.g., SABS, TUV"
                  value={formData.certifying_body}
                  onChange={(e) => setFormData({ ...formData, certifying_body: e.target.value })}
                  className="w-full mt-1 px-3 py-2 border rounded text-sm"
                  style={{ borderColor: "var(--sentinel-border)", background: "var(--sentinel-bg-panel)", color: "var(--sentinel-text-primary)" }}
                />
              </div>
              <div>
                <label className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Scope</label>
                <input
                  type="text"
                  placeholder="e.g., Main Distribution Board"
                  value={formData.scope}
                  onChange={(e) => setFormData({ ...formData, scope: e.target.value })}
                  className="w-full mt-1 px-3 py-2 border rounded text-sm"
                  style={{ borderColor: "var(--sentinel-border)", background: "var(--sentinel-bg-panel)", color: "var(--sentinel-text-primary)" }}
                />
              </div>
            </div>
            <button
              className="px-3 py-1.5 text-xs rounded font-medium"
              style={{ background: "var(--sentinel-blue)", color: "white" }}
              disabled={isPending}
              onClick={handleAddCertificate}
            >
              Save Certificate
            </button>
          </div>
        )}

        {certificates.length > 0 ? (
          <table className="w-full text-sm mt-4">
            <thead>
              <tr className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Type</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Issuing Body</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Issue Date</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Expiry Date</th>
                <th className="text-left py-2 font-medium" style={{ color: "var(--sentinel-text-secondary)" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {certificates.map((cert) => {
                const expiryDate = new Date(cert.expiry_date)
                const daysUntilExpiry = Math.ceil((expiryDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24))

                return (
                  <tr key={cert.id} className="border-b" style={{ borderColor: "var(--sentinel-border)" }}>
                    <td className="py-2 capitalize">{cert.certificate_type.replace(/_/g, ' ')}</td>
                    <td className="py-2">{cert.certifying_body}</td>
                    <td className="py-2">{new Date(cert.issue_date).toLocaleDateString()}</td>
                    <td className="py-2">{expiryDate.toLocaleDateString()}</td>
                    <td className="py-2">
                      <span
                        className="text-xs px-2 py-0.5 rounded font-medium"
                        style={{
                          background: cert.status === 'active'
                            ? "rgba(34, 197, 94, 0.15)"
                            : cert.status?.includes('expiring_30') || daysUntilExpiry < 30
                              ? "rgba(239, 68, 68, 0.15)"
                              : cert.status?.includes('expiring')
                                ? "rgba(245, 158, 11, 0.15)"
                                : "rgba(156, 163, 175, 0.15)",
                          color: cert.status === 'active'
                            ? "var(--sentinel-green)"
                            : cert.status?.includes('expiring_30') || daysUntilExpiry < 30
                              ? "var(--sentinel-red)"
                              : cert.status?.includes('expiring')
                                ? "var(--sentinel-amber)"
                                : "var(--sentinel-text-disabled)",
                        }}
                      >
                        {cert.status || 'unknown'}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : (
          <div className="mt-4 p-4 text-center" style={{ color: "var(--sentinel-text-disabled)" }}>
            No certificates recorded. Add a certificate above.
          </div>
        )}
      </div>

      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Certificate Validity Timeline</h3>
        <span className="text-sm mt-2 mb-4 block" style={{ color: "var(--sentinel-text-secondary)" }}>5-year validity from issue date per SABS standard</span>

        <div className="mt-4 space-y-2">
          {certificates.map((cert) => {
            const expiryDate = new Date(cert.expiry_date)
            const daysUntilExpiry = Math.ceil((expiryDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24))
            const yearsLeft = (daysUntilExpiry / 365).toFixed(1)

            return (
              <div key={cert.id} className="p-3 rounded" style={{ border: "1px solid var(--sentinel-border)" }}>
                <div className="flex justify-between items-center mb-2">
                  <span className="font-medium text-sm" style={{ color: "var(--sentinel-text-primary)" }}>{cert.scope || cert.certificate_type}</span>
                  <span
                    className="text-xs px-2 py-0.5 rounded font-medium"
                    style={{
                      background: daysUntilExpiry < 180 ? "rgba(239, 68, 68, 0.15)" : "rgba(34, 197, 94, 0.15)",
                      color: daysUntilExpiry < 180 ? "var(--sentinel-red)" : "var(--sentinel-green)",
                    }}
                  >
                    {daysUntilExpiry > 0 ? `${yearsLeft} years left` : 'EXPIRED'}
                  </span>
                </div>
                <div className="w-full rounded-full h-2" style={{ background: "var(--sentinel-bg-secondary)" }}>
                  <div
                    className="h-2 rounded-full"
                    style={{
                      width: `${Math.max(0, (daysUntilExpiry / 1825) * 100)}%`,
                      background: daysUntilExpiry < 180 ? "var(--sentinel-red)" : "var(--sentinel-green)",
                    }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="rounded-lg p-4" style={{ background: "rgba(59, 130, 246, 0.1)", borderLeft: "4px solid var(--sentinel-blue)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>SABS Certificate Requirements</h3>
        <div className="text-xs mt-2" style={{ color: "var(--sentinel-text-secondary)" }}>
          <ul className="list-disc list-inside space-y-1 mt-2">
            <li>5-year validity from issue date for Certificate of Compliance (CoC)</li>
            <li>Covers new installations, alterations, and maintenance work</li>
            <li>Must be issued by SABS-accredited certifiers</li>
            <li>Renewal alerts at 30-day and 90-day windows before expiry</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

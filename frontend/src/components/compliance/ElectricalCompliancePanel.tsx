/**
 * Electrical Compliance Panel
 *
 * South African SABS Certificate of Compliance tracking and 5-year validity management.
 */

import { Card, Title, Table, TableHead, TableRow, TableHeaderCell, TableBody, TableCell, Button, Badge, Text, Grid } from '@tremor/react'
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
      <Grid numColsSm={1} numColsMd={3} className="gap-4">
        <Card>
          <Title>Total Certificates</Title>
          <div className="text-3xl font-bold mt-2">{certificates.length}</div>
        </Card>
        <Card>
          <Title>Active</Title>
          <div className="text-3xl font-bold mt-2 text-green-600">
            {certificates.filter((c) => c.status === 'active').length}
          </div>
        </Card>
        <Card>
          <Title>Expiring Soon</Title>
          <div className="text-3xl font-bold mt-2 text-yellow-600">
            {certificates.filter((c) => c.status?.includes('expiring')).length}
          </div>
        </Card>
      </Grid>

      <Card>
        <div className="flex justify-between items-center mb-4">
          <Title>Certificate of Compliance Tracking</Title>
          <Button size="sm" onClick={() => setShowAddForm(!showAddForm)}>
            {showAddForm ? 'Cancel' : 'Add Certificate'}
          </Button>
        </div>

        {showAddForm && (
          <div className="border rounded p-4 mb-4 bg-gray-50">
            <Grid numColsSm={1} numColsMd={2} className="gap-4 mb-4">
              <div>
                <label className="text-sm font-medium">Certificate Type</label>
                <select
                  value={formData.certificate_type}
                  onChange={(e) => setFormData({ ...formData, certificate_type: e.target.value as any })}
                  className="w-full mt-1 px-3 py-2 border rounded text-sm"
                >
                  <option value="CoC_new_installation">CoC - New Installation</option>
                  <option value="CoC_alterations">CoC - Alterations</option>
                  <option value="SABS_inspection">SABS Inspection</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium">Issue Date</label>
                <input
                  type="date"
                  value={formData.issue_date}
                  onChange={(e) => setFormData({ ...formData, issue_date: e.target.value })}
                  className="w-full mt-1 px-3 py-2 border rounded text-sm"
                />
              </div>
            </Grid>
            <Grid numColsSm={1} numColsMd={2} className="gap-4 mb-4">
              <div>
                <label className="text-sm font-medium">Certifying Body</label>
                <input
                  type="text"
                  placeholder="e.g., SABS, TUV"
                  value={formData.certifying_body}
                  onChange={(e) => setFormData({ ...formData, certifying_body: e.target.value })}
                  className="w-full mt-1 px-3 py-2 border rounded text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium">Scope</label>
                <input
                  type="text"
                  placeholder="e.g., Main Distribution Board"
                  value={formData.scope}
                  onChange={(e) => setFormData({ ...formData, scope: e.target.value })}
                  className="w-full mt-1 px-3 py-2 border rounded text-sm"
                />
              </div>
            </Grid>
            <Button onClick={handleAddCertificate} loading={isPending}>
              Save Certificate
            </Button>
          </div>
        )}

        {certificates.length > 0 ? (
          <Table className="mt-4">
            <TableHead>
              <TableRow>
                <TableHeaderCell>Type</TableHeaderCell>
                <TableHeaderCell>Issuing Body</TableHeaderCell>
                <TableHeaderCell>Issue Date</TableHeaderCell>
                <TableHeaderCell>Expiry Date</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {certificates.map((cert) => {
                const expiryDate = new Date(cert.expiry_date)
                const daysUntilExpiry = Math.ceil((expiryDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24))

                return (
                  <TableRow key={cert.id}>
                    <TableCell className="capitalize">{cert.certificate_type.replace(/_/g, ' ')}</TableCell>
                    <TableCell>{cert.certifying_body}</TableCell>
                    <TableCell>{new Date(cert.issue_date).toLocaleDateString()}</TableCell>
                    <TableCell>{expiryDate.toLocaleDateString()}</TableCell>
                    <TableCell>
                      <Badge
                        color={
                          cert.status === 'active'
                            ? 'green'
                            : cert.status?.includes('expiring_30') || daysUntilExpiry < 30
                              ? 'red'
                              : cert.status?.includes('expiring')
                                ? 'yellow'
                                : 'gray'
                        }
                      >
                        {cert.status || 'unknown'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        ) : (
          <div className="mt-4 p-4 text-center text-gray-500">
            No certificates recorded. Add a certificate above.
          </div>
        )}
      </Card>

      {/* Expiry Countdown */}
      <Card>
        <Title>Certificate Validity Timeline</Title>
        <Text className="text-sm mt-2 mb-4">5-year validity from issue date per SABS standard</Text>

        <div className="mt-4 space-y-2">
          {certificates.map((cert) => {
            const expiryDate = new Date(cert.expiry_date)
            const daysUntilExpiry = Math.ceil((expiryDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24))
            const yearsLeft = (daysUntilExpiry / 365).toFixed(1)

            return (
              <div key={cert.id} className="p-3 border rounded">
                <div className="flex justify-between items-center mb-2">
                  <span className="font-medium text-sm">{cert.scope || cert.certificate_type}</span>
                  <Badge color={daysUntilExpiry < 180 ? 'red' : 'green'}>
                    {daysUntilExpiry > 0 ? `${yearsLeft} years left` : 'EXPIRED'}
                  </Badge>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${daysUntilExpiry < 180 ? 'bg-red-500' : 'bg-green-500'}`}
                    style={{ width: `${Math.max(0, (daysUntilExpiry / 1825) * 100)}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </Card>

      {/* Information */}
      <Card className="border-l-4 border-blue-500 bg-blue-50">
        <Title className="text-sm">SABS Certificate Requirements</Title>
        <Text className="text-xs mt-2">
          <ul className="list-disc list-inside space-y-1 mt-2">
            <li>5-year validity from issue date for Certificate of Compliance (CoC)</li>
            <li>Covers new installations, alterations, and maintenance work</li>
            <li>Must be issued by SABS-accredited certifiers</li>
            <li>Renewal alerts at 30-day and 90-day windows before expiry</li>
          </ul>
        </Text>
      </Card>
    </div>
  )
}

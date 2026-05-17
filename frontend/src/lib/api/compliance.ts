/**
 * Compliance Management API Client
 *
 * Handles OHS, Fire Safety, Emergency Lighting, Legionella, Electrical,
 * and Lift Compliance workflows with React Query integration.
 */

import { useQuery, useMutation, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { fetchApi } from './client'

/**
 * Compliance domain types
 */
export type ComplianceType = 'OHS' | 'Fire' | 'Electrical' | 'Legionella' | 'LiftSafety' | 'EmergencyLight'
export type RiskLevel = 'critical' | 'high' | 'medium' | 'marginal' | 'low'
export type AuditStatus = 'draft' | 'submitted' | 'approved' | 'remediation_pending' | 'closed'

/**
 * Audit trail fields for compliance records
 */
export interface AuditTrail {
  recorded_by?: string
  recorded_by_email?: string
  recorded_at: string
  updated_by?: string
  updated_at?: string
}

/**
 * OHS Compliance
 */
export interface OHSChecklistTask extends AuditTrail {
  id: string
  site_code: string
  zone_id: string
  checklist_items?: Array<{
    id: string
    requirement: string
    compliance_standard: string
    completed: boolean
    notes?: string
  }>
  status: 'pending' | 'in_progress' | 'completed'
  created_at: string
  completed_at?: string
}

/**
 * Fire Equipment
 */
export interface FireEquipmentItem extends AuditTrail {
  id: string
  site_code: string
  equipment_type: 'extinguisher' | 'hose_reel' | 'hydrant' | 'alarm' | 'detector'
  location_description: string
  last_inspection_date: string
  next_inspection_date: string
  certification_expiry_date?: string
  status: 'active' | 'overdue' | 'expired'
  pressure_test_result?: number
  test_date?: string
}

/**
 * Emergency Light Testing
 */
export interface EmergencyLight extends AuditTrail {
  light_code: string
  location: string
  battery_health_percent: number
  last_test_date: string
  next_test_date: string
  test_result: 'pass' | 'fail' | 'warning'
  status: 'ok' | 'alert' | 'failed'
}

/**
 * Legionella Risk Assessment
 */
export interface LegionellaAssessment extends AuditTrail {
  id: string
  tower_code: string
  water_temperature: number
  last_treatment_date: string
  days_since_treatment: number
  risk_level: RiskLevel
  control_measures?: string[]
  next_treatment_date: string
}

/**
 * Electrical Compliance
 */
export interface ElectricalCertificate extends AuditTrail {
  id: string
  site_code: string
  certificate_type: 'CoC_new_installation' | 'CoC_alterations' | 'SABS_inspection'
  issue_date: string
  expiry_date: string
  certifying_body: string
  status: 'active' | 'expiring_30days' | 'expiring_90days' | 'expired' | 'remediation_in_progress'
  scope?: string
}

/**
 * Lift Inspection
 */
export interface LiftInspection extends AuditTrail {
  id: string
  lift_code: string
  inspection_type: 'periodic_6monthly' | 'annual_insurance' | 'after_repair'
  last_inspection_date: string
  next_inspection_date: string
  status: 'compliant' | 'non_compliant' | 'pending'
  test_results?: {
    brake_load_test: boolean
    speed_governor_test: boolean
    emergency_stop_test: boolean
  }
}

/**
 * Compliance Audit
 */
export interface ComplianceAudit {
  id: string
  compliance_type: ComplianceType
  audit_type: 'scheduled' | 'unannounced' | 'certification'
  status: AuditStatus
  created_at: string
  findings?: Record<string, unknown>
}

/**
 * Compliance Status Dashboard
 */
export interface ComplianceStatus {
  site_id: string
  critical_issues_count: number
  high_risk_items_count: number
  items_expiring_30days: number
  overdue_inspections: number
  last_audit_date?: string
  compliance_score_percent: number
  summary?: {
    ohs_status: 'compliant' | 'non_compliant' | 'pending'
    fire_status: 'compliant' | 'non_compliant' | 'overdue'
    electrical_status: 'compliant' | 'expiring_soon' | 'expired'
    legionella_status: 'compliant' | 'high_risk' | 'pending'
    lift_status: 'compliant' | 'non_compliant' | 'pending'
  }
}

/**
 * POPIA Data Retention Status (SQL table retention enforcement)
 */
export interface RetentionStatus {
  categories: Array<{
    table: string
    tier: string
    retention_days: number
    description: string
    overdue_count: number
    cutoff: string
  }>
  updated_at: string
}

export interface RetentionExecutionLog {
  id: string
  tier: string
  execution_time: string
  rows_reviewed: number
  rows_deleted: number
  status: string
  details: Record<string, unknown>
  created_at: string
}

/**
 * API Client Functions
 */
export const complianceApi = {
  /**
   * OHS Compliance - Generate checklist for a zone
   */
  generateOhsChecklist: (siteCode: string, zoneId: string) =>
    fetchApi<OHSChecklistTask>('/api/compliance/ohs/checklist/generate', {
      method: 'POST',
      body: JSON.stringify({
        site_code: siteCode,
        zone_id: zoneId,
      }),
    }),

  /**
   * OHS Compliance - Complete checklist and record findings
   */
  completeOhsChecklist: (taskId: string, findings: Record<string, unknown>) =>
    fetchApi<OHSChecklistTask>(`/api/compliance/ohs/checklist/${taskId}/complete`, {
      method: 'POST',
      body: JSON.stringify(findings),
    }),

  /**
   * Fire Equipment - List fire equipment by site/zone
   */
  listFireEquipment: (siteCode: string, zoneId?: string) =>
    fetchApi<FireEquipmentItem[]>(
      `/api/compliance/fire/equipment?site_code=${encodeURIComponent(siteCode)}${zoneId ? `&zone_id=${encodeURIComponent(zoneId)}` : ''}`,
      { method: 'GET' },
    ),

  /**
   * Fire Equipment - Schedule inspection
   */
  scheduleFireInspection: (equipmentId: string) =>
    fetchApi<{ success: boolean }>(`/api/compliance/fire/equipment/${equipmentId}/inspect`, {
      method: 'POST',
    }),

  /**
   * Fire Equipment - Record pressure test
   */
  recordFireEquipmentCharge: (equipmentId: string, pressure: number, testDate: string) =>
    fetchApi<{ success: boolean }>(`/api/compliance/fire/equipment/${equipmentId}/charge`, {
      method: 'POST',
      body: JSON.stringify({
        pressure,
        test_date: testDate,
      }),
    }),

  /**
   * Emergency Light - Schedule auto-tests
   */
  scheduleEmergencyLightTests: (lightCodes: string[], autoTest: boolean = true) =>
    fetchApi<{ scheduled_count: number }>('/api/compliance/emergency-light/schedule', {
      method: 'POST',
      body: JSON.stringify({
        light_codes: lightCodes,
        auto_test: autoTest,
      }),
    }),

  /**
   * Emergency Light - Record test result
   */
  recordEmergencyLightTest: (lightCode: string, batteryHealth: number, testResult: string) =>
    fetchApi<{ success: boolean }>(`/api/compliance/emergency-light/${lightCode}/test`, {
      method: 'POST',
      body: JSON.stringify({
        battery_health_percent: batteryHealth,
        test_result: testResult,
      }),
    }),

  /**
   * Legionella - Assess risk
   */
  assessLegionellaRisk: (towerCode: string, waterTemp: number, lastTreatment: string) =>
    fetchApi<LegionellaAssessment>('/api/compliance/legionella/assess', {
      method: 'POST',
      body: JSON.stringify({
        tower_code: towerCode,
        water_temp: waterTemp,
        last_treatment: lastTreatment,
      }),
    }),

  /**
   * Electrical - Track certificate
   */
  trackElectricalCertificate: (certificate: Omit<ElectricalCertificate, 'id'>) =>
    fetchApi<ElectricalCertificate>('/api/compliance/electrical/certificate', {
      method: 'POST',
      body: JSON.stringify(certificate),
    }),

  /**
   * Electrical - Get compliance status by site
   */
  getElectricalComplianceStatus: (siteCode: string) =>
    fetchApi<{ certificates: ElectricalCertificate[] }>(
      `/api/compliance/electrical/status?site_code=${encodeURIComponent(siteCode)}`,
      { method: 'GET' },
    ),

  /**
   * Lift - Schedule inspection
   */
  scheduleLiftInspection: (liftCode: string, inspectionType: string) =>
    fetchApi<{ success: boolean }>('/api/compliance/lift/schedule', {
      method: 'POST',
      body: JSON.stringify({
        lift_code: liftCode,
        inspection_type: inspectionType,
      }),
    }),

  /**
   * Lift - Record test results
   */
  recordLiftTestResults: (liftCode: string, testResults: Record<string, boolean>) =>
    fetchApi<{ success: boolean }>(`/api/compliance/lift/${liftCode}/test-results`, {
      method: 'POST',
      body: JSON.stringify(testResults),
    }),

  /**
   * Overall Compliance Status - Get KPIs by site
   */
  getComplianceStatus: (siteCode: string) =>
    fetchApi<ComplianceStatus>(
      `/api/compliance/status?site_code=${encodeURIComponent(siteCode)}`,
      { method: 'GET' },
    ),

  /**
   * POPIA Retention - Get SQL table retention status (overdue counts)
   */
  getRetentionStatus: () =>
    fetchApi<RetentionStatus>('/api/privacy/retention/sql-status', { method: 'GET' }),

  /**
   * POPIA Retention - Get last N execution log entries
   */
  getRetentionHistory: (limit: number = 10) =>
    fetchApi<{ items: RetentionExecutionLog[]; count: number }>(
      `/api/privacy/retention/sql-history?limit=${limit}`,
      { method: 'GET' },
    ),

  /**
   * Compliance Audits - Get audit history with filtering
   */
  listComplianceAudits: (
    siteCode: string,
    complianceType?: ComplianceType,
    status?: AuditStatus,
    limit: number = 50
  ) => {
    const params = new URLSearchParams({ site_code: siteCode, limit: String(limit) });
    if (complianceType) params.set('compliance_type', complianceType);
    if (status) params.set('status', status);
    return fetchApi<{ audits: ComplianceAudit[] }>(`/api/compliance/audits?${params}`, { method: 'GET' });
  },
}

/**
 * React Query Hooks
 */

/**
 * Get overall compliance status by site
 */
export function useComplianceStatus(siteCode?: string): UseQueryResult<ComplianceStatus, unknown> {
  return useQuery({
    queryKey: ['compliance-status', siteCode],
    queryFn: () => complianceApi.getComplianceStatus(siteCode!),
    staleTime: 60_000,
    refetchInterval: 60_000,
    enabled: !!siteCode,
  })
}

/**
 * Get fire equipment list
 */
export function useFireEquipment(
  siteCode?: string,
  zoneId?: string
): UseQueryResult<FireEquipmentItem[], unknown> {
  return useQuery({
    queryKey: ['fire-equipment', siteCode, zoneId],
    queryFn: () => complianceApi.listFireEquipment(siteCode!, zoneId),
    staleTime: 60_000,
    enabled: !!siteCode,
  })
}

/**
 * Get emergency light status
 */
export function useEmergencyLightStatus(siteCode?: string): UseQueryResult<ComplianceStatus, unknown> {
  return useQuery({
    queryKey: ['emergency-lights', siteCode],
    queryFn: () => complianceApi.getComplianceStatus(siteCode!),
    staleTime: 60_000,
    enabled: !!siteCode,
  })
}

/**
 * Get electrical compliance status
 */
export function useElectricalCompliance(
  siteCode?: string
): UseQueryResult<{ certificates: ElectricalCertificate[] }, unknown> {
  return useQuery({
    queryKey: ['electrical-compliance', siteCode],
    queryFn: () => complianceApi.getElectricalComplianceStatus(siteCode!),
    staleTime: 60_000,
    enabled: !!siteCode,
  })
}

/**
 * Get compliance audit history
 */
export function useComplianceAudits(
  siteCode?: string,
  complianceType?: ComplianceType,
  status?: AuditStatus
): UseQueryResult<{ audits: ComplianceAudit[] }, unknown> {
  return useQuery({
    queryKey: ['compliance-audits', siteCode, complianceType, status],
    queryFn: () => complianceApi.listComplianceAudits(siteCode!, complianceType, status, 50),
    staleTime: 60_000,
    enabled: !!siteCode,
  })
}

/**
 * Get POPIA SQL table retention status
 */
export function useRetentionStatus(): UseQueryResult<RetentionStatus, unknown> {
  return useQuery({
    queryKey: ['retention-status'],
    queryFn: () => complianceApi.getRetentionStatus(),
    staleTime: 30_000,
    refetchInterval: 30_000,
  })
}

/**
 * Get POPIA retention execution history
 */
export function useRetentionHistory(
  limit: number = 10
): UseQueryResult<{ items: RetentionExecutionLog[]; count: number }, unknown> {
  return useQuery({
    queryKey: ['retention-history', limit],
    queryFn: () => complianceApi.getRetentionHistory(limit),
    staleTime: 30_000,
  })
}

/**
 * Mutations
 */

/**
 * Generate OHS checklist for a zone
 */
export function useGenerateOhsChecklist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ siteCode, zoneId }: { siteCode: string; zoneId: string }) =>
      complianceApi.generateOhsChecklist(siteCode, zoneId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance-status'] })
      queryClient.invalidateQueries({ queryKey: ['compliance-audits'] })
    },
  })
}

/**
 * Schedule fire equipment inspection
 */
export function useScheduleFireInspection() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (equipmentId: string) =>
      complianceApi.scheduleFireInspection(equipmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fire-equipment'] })
      queryClient.invalidateQueries({ queryKey: ['compliance-status'] })
    },
  })
}

/**
 * Record emergency light test
 */
export function useRecordEmergencyLightTest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { lightCode: string; batteryHealth: number; testResult: string }) =>
      complianceApi.recordEmergencyLightTest(data.lightCode, data.batteryHealth, data.testResult),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['emergency-lights'] })
      queryClient.invalidateQueries({ queryKey: ['compliance-status'] })
    },
  })
}

/**
 * Assess legionella risk
 */
export function useAssessLegionellaRisk() {
  return useMutation({
    mutationFn: (data: { towerCode: string; waterTemp: number; lastTreatment: string }) =>
      complianceApi.assessLegionellaRisk(data.towerCode, data.waterTemp, data.lastTreatment),
  })
}

/**
 * Track electrical certificate
 */
export function useTrackElectricalCertificate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (certificate: Omit<ElectricalCertificate, 'id'>) =>
      complianceApi.trackElectricalCertificate(certificate),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['electrical-compliance'] })
      queryClient.invalidateQueries({ queryKey: ['compliance-status'] })
    },
  })
}

/**
 * Record lift test results
 */
export function useRecordLiftTestResults() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { liftCode: string; testResults: Record<string, boolean> }) =>
      complianceApi.recordLiftTestResults(data.liftCode, data.testResults),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance-status'] })
    },
  })
}

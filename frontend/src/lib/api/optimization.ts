import { fetchApi } from './client'

export interface SiteProfileConfig {
  site_id: string
  active_profile: string
  control_tier: string
  zone_overrides: Array<{
    zone_id: string
    profile: string
    reason: string
  }>
}

export interface Recommendation {
  id: string
  recommendation_id?: string
  site_id: string
  source_module?: string
  recommendation_type?: string
  action_type: string
  action?: {
    point?: string
    parameter?: string
    value?: number | string | boolean
    target_value?: number | string | boolean
    unit?: string
    description?: string
  } | Record<string, unknown>
  risk_level: string
  priority?: string
  target_equipment: string
  title?: string
  description?: string
  reason: string
  expected_impact: Record<string, number>
  baseline_energy_kwh?: number | null
  actual_energy_kwh?: number | null
  actual_saving_kwh?: number | null
  actual_saving_zar?: number
  outcome_validated?: boolean
  outcome_notes?: string | null
  confidence: string | number
  profile: string
  multi_objective_score: number
  status: string
  timestamp: string
  executed_at?: string
  approved_at?: string
  execution_result?: Record<string, unknown> | null
  outcome?: Outcome
}

export interface Outcome {
  predicted: Record<string, number>
  actual: Record<string, number>
  accuracy: number
}

export const optimizationApi = {
  // Profiles
  getProfileSettings: (siteId: string) =>
    fetchApi<SiteProfileConfig>(`/api/optimization/settings/${siteId}`).then(
      (res) => {
        // Backend returns {success, site_id, config} — unwrap to SiteProfileConfig
        if ('config' in res) return res.config as SiteProfileConfig
        return res as SiteProfileConfig
      }
    ),

  updateProfileSettings: (siteId: string, config: Partial<SiteProfileConfig>) =>
    fetchApi(`/api/optimization/settings/${siteId}`, {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  // Recommendations
  getPending: (siteId: string, limit: number = 10) =>
    // Backend route: GET /api/modules/site/{site_id}/recommendations?limit=N
    // Returns a list directly (not wrapped in {recommendations: [...]})
    fetchApi<Recommendation[]>(
      `/api/modules/site/${siteId}/recommendations?limit=${limit}`
    ),

  getHistory: (
    siteId: string,
    filters: { status?: string; riskLevel?: string }
  ) =>
    fetchApi<{
      recommendations: Recommendation[]
      aggregates: {
        total: number
        actioned: number
        verified: number
        saving_kwh: number
        saving_zar: number
      }
    }>(
      `/api/recommendations/history/${siteId}`,
      { method: 'POST', body: JSON.stringify(filters) }
    ),

  // Use approvalsApi for actual approval workflow (Tier 2)
  // These are deprecated - use approvalsApi.approveRecommendation instead
  approve: (recId: string, approvedBy: string) =>
    fetchApi(`/api/approvals/recommendations/${recId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy }),
    }),

  reject: (recId: string, rejectedBy: string, reason: string) =>
    fetchApi(`/api/approvals/recommendations/${recId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ rejected_by: rejectedBy, reason }),
    }),
}

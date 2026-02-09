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
  site_id: string
  action_type: string
  risk_level: string
  target_equipment: string
  reason: string
  expected_impact: Record<string, number>
  confidence: string
  profile: string
  multi_objective_score: number
  status: string
  timestamp: string
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
    fetchApi<SiteProfileConfig>(`/api/optimization/settings/${siteId}`),

  updateProfileSettings: (siteId: string, config: Partial<SiteProfileConfig>) =>
    fetchApi(`/api/optimization/settings/${siteId}`, {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  // Recommendations
  getPending: (siteId: string, limit: number = 10) =>
    fetchApi<{ recommendations: Recommendation[] }>(
      `/api/recommendations/${siteId}?limit=${limit}`
    ),

  getHistory: (
    siteId: string,
    filters: { status?: string; riskLevel?: string }
  ) =>
    fetchApi<{ recommendations: Recommendation[] }>(
      `/api/recommendations/history/${siteId}`,
      { method: 'POST', body: JSON.stringify(filters) }
    ),

  approve: (recId: string, reason: string) =>
    fetchApi(`/api/recommendations/${recId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  reject: (recId: string, reason: string) =>
    fetchApi(`/api/recommendations/${recId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
}

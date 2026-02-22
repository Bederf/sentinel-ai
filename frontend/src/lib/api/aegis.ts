/**
 * AEGIS API client
 *
 * Frontend access to the AEGIS operations dashboard and decision details.
 */

import { fetchApi } from "./client";

export interface AegisDecision {
  id: string;
  site_id?: string;
  created_at: string;
  equipment_code?: string;
  decision_type?: string;
  tier?: string;
  write_status?: string | null;
  approved_at?: string | null;
  rejected_at?: string | null;
  contributing_factors?: Record<string, unknown>;
}

export interface AegisDashboardKpis {
  proposals_24h: number;
  approved_24h: number;
  rejected_24h: number;
  blocked_24h: number;
  avg_response_time_s: number | null;
}

export interface AegisDashboardFilters {
  execution_mode?: string;
  approval_outcome?: string;
  dispatch_action_type?: string;
  write_status?: string;
}

export interface AegisDashboardResponse {
  site_id: string;
  period: string;
  kpis: AegisDashboardKpis;
  pending_proposals: AegisDecision[];
  activity: AegisDecision[];
  filters_applied: {
    execution_mode: string | null;
    approval_outcome: string | null;
    dispatch_action_type: string | null;
    write_status: string | null;
  };
}

function buildQuery(siteId: string, filters?: AegisDashboardFilters): string {
  const params = new URLSearchParams({ site_id: siteId });
  if (!filters) return params.toString();

  if (filters.execution_mode) params.set("execution_mode", filters.execution_mode);
  if (filters.approval_outcome) params.set("approval_outcome", filters.approval_outcome);
  if (filters.dispatch_action_type) params.set("dispatch_action_type", filters.dispatch_action_type);
  if (filters.write_status) params.set("write_status", filters.write_status);

  return params.toString();
}

export const aegisApi = {
  async getDashboard(siteId: string, filters?: AegisDashboardFilters): Promise<AegisDashboardResponse> {
    const query = buildQuery(siteId, filters);
    return fetchApi<AegisDashboardResponse>(`/api/parasite/aegis/dashboard?${query}`);
  },

  async getDecision(decisionId: string): Promise<AegisDecision> {
    return fetchApi<AegisDecision>(`/api/parasite/decisions/${decisionId}`);
  },
};

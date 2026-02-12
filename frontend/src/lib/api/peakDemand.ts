/**
 * Peak Demand Management API Client
 *
 * Provides access to real-time NMD headroom monitoring and multi-module
 * peak shaving recommendations from the demand-aware coordinator.
 */

import { authorizedFetch } from './client';

export interface ModuleAction {
  module: string;
  action: string;
  duration_min?: number;
  reduction_kw?: number;
  estimated_savings_r?: number;
  comfort_impact?: string;
}

export interface MultiModuleRecommendation {
  recommendation_id: string;
  timestamp: string;
  type: string;
  urgency: 'normal' | 'caution' | 'warning' | 'critical';
  priority: string;
  modules_involved: string[];
  module_actions: ModuleAction[];
  estimated_reduction_kw: number;
  estimated_savings_r: number;
  reasoning: string;
  requires_approval: boolean;
}

export interface DemandStatusResponse {
  site_id: string;
  current_demand_kw: number;
  nmd_limit_kva: number;
  headroom_kw: number;
  headroom_percent: number;
  headroom_level: 'normal' | 'caution' | 'warning' | 'critical';
  demand_trend: 'rising' | 'stable' | 'falling';
  active_modules: string[];
  available_reductions: Record<string, any>;
  last_updated: string;
}

export interface ForecastInterval {
  hour: number;
  date: string;
  forecasted_demand_kw: number;
  confidence_low_kw: number;
  confidence_high_kw: number;
  nmd_headroom_kw: number;
  headroom_percent: number;
  risk_level: 'safe' | 'caution' | 'warning' | 'critical';
}

export interface DemandForecastResponse {
  site_id: string;
  forecast_start: string;
  forecast_hours: ForecastInterval[];
  peak_hour: number;
  peak_demand_kw: number;
  peak_headroom_kw: number;
  peak_headroom_percent: number;
  peak_risk_level: 'safe' | 'caution' | 'warning' | 'critical';
}

export interface DemandSummary {
  site_id: string;
  current_demand_kw: number;
  nmd_limit_kva: number;
  headroom_percent: number;
  risk_level: 'safe' | 'caution' | 'warning' | 'critical';
  active_modules: string[];
  coordinator_active: boolean;
}

class PeakDemandAPI {
  private baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:9095';

  /**
   * Get current demand status with NMD headroom and active modules
   */
  async getDemandStatus(siteId: string): Promise<DemandStatusResponse> {
    const response = await authorizedFetch(
      `${this.baseUrl}/api/peak-demand/${siteId}/status`
    );
    if (!response.ok) throw new Error(`Failed to fetch demand status: ${response.statusText}`);
    return response.json();
  }

  /**
   * Get 24-hour demand forecast with headroom predictions
   */
  async getDemandForecast(siteId: string): Promise<DemandForecastResponse> {
    const response = await authorizedFetch(
      `${this.baseUrl}/api/peak-demand/${siteId}/forecast-24h`
    );
    if (!response.ok) throw new Error(`Failed to fetch demand forecast: ${response.statusText}`);
    return response.json();
  }

  /**
   * Get pending multi-module peak shaving recommendations
   */
  async getRecommendations(
    siteId: string
  ): Promise<MultiModuleRecommendation[]> {
    const response = await authorizedFetch(
      `${this.baseUrl}/api/peak-demand/${siteId}/recommendations`
    );
    if (!response.ok) throw new Error(`Failed to fetch recommendations: ${response.statusText}`);
    return response.json();
  }

  /**
   * Approve and execute a peak shaving recommendation
   */
  async approveRecommendation(
    siteId: string,
    recommendationId: string,
    approvedBy: string,
    approvalNotes?: string
  ): Promise<any> {
    const response = await authorizedFetch(
      `${this.baseUrl}/api/peak-demand/${siteId}/approve-recommendation`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recommendation_id: recommendationId,
          approved_by: approvedBy,
          approval_notes: approvalNotes,
        }),
      }
    );
    if (!response.ok) throw new Error(`Failed to approve recommendation: ${response.statusText}`);
    return response.json();
  }

  /**
   * Get demand management summary for dashboard
   */
  async getDemandSummary(siteId: string): Promise<DemandSummary> {
    const response = await authorizedFetch(
      `${this.baseUrl}/api/peak-demand/${siteId}/summary`
    );
    if (!response.ok) throw new Error(`Failed to fetch demand summary: ${response.statusText}`);
    return response.json();
  }
}

export const peakDemandApi = new PeakDemandAPI();

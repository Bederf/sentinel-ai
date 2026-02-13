/**
 * Peak Demand Management API Client
 *
 * Handles forecast requests and peak demand status for solar + BESS integration.
 * Used for NMD headroom monitoring and multi-module optimization coordination.
 */

import { authorizedFetch } from './client';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:9095';

/**
 * Hourly demand forecast interval with confidence bounds and risk assessment
 */
export interface ForecastInterval {
  hour: number;
  date: string;
  forecasted_demand_kw: number;
  confidence_low_kw: number;      // Lower bound (confidence interval)
  confidence_high_kw: number;      // Upper bound (confidence interval)
  nmd_headroom_kw: number;        // NMD limit - forecasted demand
  headroom_percent: number;        // Headroom as % of NMD limit
  risk_level: 'safe' | 'caution' | 'warning' | 'critical';  // Risk assessment
}

/**
 * 24-hour demand forecast response
 */
export interface DemandForecastResponse {
  site_id: string;
  forecast_start: string;
  forecast_hours: ForecastInterval[];
  peak_hour: number;              // Hour with highest demand
  peak_demand_kw: number;         // Maximum demand in forecast period
  peak_headroom_kw: number;       // NMD headroom at peak
  peak_headroom_percent: number;  // Headroom % at peak
  peak_risk_level: 'safe' | 'caution' | 'warning' | 'critical';
}

/**
 * Current demand status with headroom urgency levels
 */
export interface DemandStatus {
  current_demand_kw: number;
  nmd_limit_kva: number;
  headroom_kw: number;
  headroom_percent: number;
  headroom_level: 'normal' | 'warning' | 'critical' | 'emergency';
  active_modules: string[];  // Which modules are active at this site
  available_reductions?: Record<string, any>;  // Module-specific reduction options
}

/**
 * Multi-module recommendation from coordinator
 */
export interface PeakDemandRecommendation {
  id: string;
  urgency: 'low' | 'medium' | 'high' | 'critical';
  modules_involved: string[];
  module_actions: Array<{
    module: string;
    action: string;
    duration_min?: number;
    reduction_kw?: number;
    estimated_savings_r?: number;
    comfort_impact?: string;
  }>;
  estimated_reduction_kw: number;
  estimated_savings_r: number;
  reasoning: string;
}

/**
 * Peak demand API client
 */
export const peakDemandApi = {
  /**
   * Get 24-hour demand forecast with ML predictions and confidence intervals
   * @param siteId Site identifier (e.g., 'S002', 'site-005')
   * @returns DemandForecastResponse with hourly predictions and peak analysis
   */
  async getDemandForecast(siteId: string): Promise<DemandForecastResponse> {
    const response = await authorizedFetch(
      `${API_BASE}/api/peak-demand/${siteId}/forecast-24h`
    );
    if (!response.ok) {
      throw new Error(
        `Failed to fetch demand forecast: ${response.statusText}`
      );
    }
    return response.json();
  },

  /**
   * Get current demand status vs NMD limit
   * @param siteId Site identifier
   * @returns DemandStatus with headroom level and active modules
   */
  async getDemandStatus(siteId: string): Promise<DemandStatus> {
    const response = await authorizedFetch(
      `${API_BASE}/api/peak-demand/${siteId}/status`
    );
    if (!response.ok) {
      throw new Error(
        `Failed to fetch demand status: ${response.statusText}`
      );
    }
    return response.json();
  },

  /**
   * Get multi-module recommendations for peak shaving
   * @param siteId Site identifier
   * @returns Array of recommendations coordinated across modules
   */
  async getRecommendations(
    siteId: string
  ): Promise<PeakDemandRecommendation[]> {
    const response = await authorizedFetch(
      `${API_BASE}/api/peak-demand/${siteId}/recommendations`
    );
    if (!response.ok) {
      throw new Error(
        `Failed to fetch recommendations: ${response.statusText}`
      );
    }
    const data = await response.json();
    return Array.isArray(data) ? data : (data.recommendations || []);
  },

  /**
   * Approve and execute a multi-module recommendation
   * @param siteId Site identifier
   * @param recommendationId Recommendation ID to execute
   * @param approvedBy User approving the recommendation
   * @returns Execution status
   */
  async approveRecommendation(
    siteId: string,
    recommendationId: string,
    approvedBy: string
  ): Promise<{ status: string; module_actions_executing: number }> {
    const response = await authorizedFetch(
      `${API_BASE}/api/peak-demand/${siteId}/approve-recommendation`,
      {
        method: 'POST',
        body: JSON.stringify({
          recommendation_id: recommendationId,
          approved_by: approvedBy,
        }),
      }
    );
    if (!response.ok) {
      throw new Error(
        `Failed to approve recommendation: ${response.statusText}`
      );
    }
    return response.json();
  },
};

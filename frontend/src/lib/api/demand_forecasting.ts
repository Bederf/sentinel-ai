/**
 * Demand Forecasting API Client
 *
 * Provides ML-based demand forecasting for peak management.
 */

import { authorizedFetch } from './client';

const API_BASE = import.meta.env.VITE_API_URL || '';

/**
 * Hourly demand forecast with confidence intervals
 */
export interface DemandForecast {
  hour: number;
  demand_kw: number;
  confidence_lower: number;
  confidence_upper: number;
  confidence_level: number; // 0-1
  trend: 'rising' | 'falling' | 'stable';
  load_shedding_risk: 'low' | 'medium' | 'high' | 'critical';
}

/**
 * Full 24-hour forecast response
 */
export interface DemandForecastResponse {
  site_id: string;
  timestamp: string;
  forecast_intervals: DemandForecast[];
  peak_hour: number;
  peak_demand_kw: number;
  nmd_limit_kva: number;
}

export const demandForecastingApi = {
  /**
   * Get 24-hour demand forecast for a site
   */
  async getForecast(siteId: string): Promise<DemandForecastResponse> {
    const response = await authorizedFetch(
      `${API_BASE}/api/peak-demand/${siteId}/forecast-24h`
    );
    if (!response.ok) {
      throw new Error(`Failed to fetch demand forecast: ${response.statusText}`);
    }
    return response.json();
  },

  /**
   * Get current demand status
   */
  async getStatus(siteId: string): Promise<any> {
    const response = await authorizedFetch(
      `${API_BASE}/api/peak-demand/${siteId}/status`
    );
    if (!response.ok) {
      throw new Error(`Failed to fetch demand status: ${response.statusText}`);
    }
    return response.json();
  },
};

/**
 * Sustainability & ESG API Client - Phase 29-01
 *
 * 8 endpoints for carbon emissions tracking, ESG metrics, and benchmarking
 */

import { fetchApi } from './client';

// ==================== Types ====================

export interface MonthlyEmission {
  month: string;
  scope1_kg_co2e: number;
  scope2_kg_co2e: number;
  scope3_kg_co2e: number;
  total_kg_co2e: number;
  intensity_kg_per_m2?: number;
}

export interface EmissionsSummary {
  status: string;
  site_id: string;
  year: number;
  scope1_total: number;
  scope2_total: number;
  scope3_total: number;
  total: number;
  total_tonnes: number;
  sources_breakdown: Array<{
    source: string;
    kg_co2e: number;
    pct_of_total: number;
  }>;
  timestamp: string;
}

export interface EmissionsBySource {
  status: string;
  site_id: string;
  months: number;
  data: Array<{
    source_type: string;
    kg_co2e: number;
    pct_of_total: number;
    scope: number;
  }>;
  timestamp: string;
}

export interface Benchmark {
  status: string;
  site_id: string;
  building_intensity: number;
  portfolio_avg_intensity: number;
  industry_avg_intensity: number;
  percentile: number;
  rating: string;
  timestamp: string;
}

export interface ESGMetrics {
  status: string;
  site_id: string;
  carbon_intensity_score: number;
  energy_efficiency_score: number;
  waste_diversion_score: number;
  water_efficiency_score: number;
  overall_esg_score: number;
  rating: string;
  target_score: number;
  target_year: number;
  timestamp: string;
}

export interface Certification {
  cert_type: string;
  current_score: number;
  target_score: number;
  pct_progress: number;
  status: string;
  categories: Array<{
    category: string;
    max_points: number;
    achieved_points: number;
  }>;
}

export interface Certifications {
  status: string;
  site_id: string;
  certifications: Certification[];
  timestamp: string;
}

export interface ForecastData {
  month: string;
  projected_kg_co2e: number;
  baseline_trend: number;
}

export interface Forecast {
  status: string;
  site_id: string;
  forecast_year: number;
  reduction_target_pct: number;
  data: ForecastData[];
  timestamp: string;
}

// ==================== API Methods ====================

export const sustainabilityApi = {
  /**
   * 1. GET /buildings/{site_id}/emissions/monthly
   * Monthly emissions breakdown by scope (last 12 months default)
   */
  getMonthlyEmissions: async (
    siteId: string,
    startDate?: string,
    endDate?: string,
  ): Promise<{ status: string; data: MonthlyEmission[] }> => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    const query = params.toString() ? `?${params.toString()}` : '';
    return fetchApi(`/api/sustainability/buildings/${siteId}/emissions/monthly${query}`);
  },

  /**
   * 2. GET /buildings/{site_id}/emissions/summary
   * Current year emissions summary with source breakdown
   */
  getEmissionsSummary: async (siteId: string): Promise<EmissionsSummary> => {
    return fetchApi(`/api/sustainability/buildings/${siteId}/emissions/summary`);
  },

  /**
   * 3. GET /buildings/{site_id}/emissions/by-source
   * Emissions breakdown by source for pie chart (last 12 months)
   */
  getEmissionsBySource: async (siteId: string, months = 12): Promise<EmissionsBySource> => {
    return fetchApi(`/api/sustainability/buildings/${siteId}/emissions/by-source?months=${months}`);
  },

  /**
   * 4. GET /portfolio/emissions/benchmark
   * Compare building to portfolio and industry benchmarks
   */
  getBenchmark: async (siteId: string): Promise<Benchmark> => {
    return fetchApi(`/api/sustainability/portfolio/emissions/benchmark?site_id=${siteId}`);
  },

  /**
   * 5. GET /buildings/{site_id}/esg-metrics
   * Overall ESG score and component metrics
   */
  getESGMetrics: async (siteId: string): Promise<ESGMetrics> => {
    return fetchApi(`/api/sustainability/buildings/${siteId}/esg-metrics`);
  },

  /**
   * 6. GET /buildings/{site_id}/certifications
   * Green Star/LEED/Carbon Trust certification progress
   */
  getCertifications: async (siteId: string): Promise<Certifications> => {
    return fetchApi(`/api/sustainability/buildings/${siteId}/certifications`);
  },

  /**
   * 7. POST /buildings/{site_id}/update-emissions
   * Record emissions data from energy systems
   */
  updateEmissions: async (
    siteId: string,
    sourceType: string,
    month: string,
    value: number,
    unit: string,
  ): Promise<{ status: string; calculated_co2e_kg: number }> => {
    return fetchApi(`/api/sustainability/buildings/${siteId}/update-emissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_type: sourceType,
        month,
        value,
        unit,
      }),
    });
  },

  /**
   * 8. GET /buildings/{site_id}/emissions/forecast
   * 12-month emissions projection with seasonal adjustment
   */
  getForecast: async (siteId: string): Promise<Forecast> => {
    return fetchApi(`/api/sustainability/buildings/${siteId}/emissions/forecast`);
  },
};

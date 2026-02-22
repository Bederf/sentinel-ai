/**
 * Sustainability & ESG API Client
 *
 * Carbon emissions, efficiency metrics, and Green Star SA tracking.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('sentinel_token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: { ...authHeaders(), ...options?.headers },
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const err = await res.json();
      msg = err.detail || err.message || JSON.stringify(err);
    } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

// ==================== Types ====================

export interface EmissionsSnapshot {
  month: string;
  site_id: string;
  scope1_kg_co2: number;
  scope2_kg_co2: number;
  scope3_kg_co2: number;
  total_kg_co2: number;
  grid_kwh: number;
  diesel_litres: number;
  carbon_intensity_kg_per_sqm: number;
  energy_intensity_kwh_per_sqm: number;
  breakdown_by_system: Record<string, number>;
  hvac_kg_co2?: number;
  lighting_kg_co2?: number;
  other_kg_co2?: number;
  solar_offset_kg_co2?: number;
  net_scope2_kg_co2?: number;
  data_source?: 'estimated' | 'measured' | 'simulation';
}

export interface EmissionsHistory {
  site_id: string;
  months: number;
  data: EmissionsSnapshot[];
}

export interface EmissionsBreakdown {
  site_id: string;
  month: string;
  by_scope: {
    scope1_diesel: number;
    scope2_grid: number;
    scope3_other: number;
    total: number;
  };
  by_system: Record<string, number>;
  scope_percentages: {
    scope1_pct: number;
    scope2_pct: number;
    scope3_pct: number;
  };
}

export interface GreenStarCategory {
  category_id: string;
  name: string;
  max_points: number;
  achieved_points: number;
  target_points: number;
  notes: string;
}

export interface GreenStarAssessment {
  site_id: string;
  tool_version: string;
  target_rating: string;
  categories: GreenStarCategory[];
  total_achieved: number;
  total_max: number;
  total_target: number;
  estimated_star_rating: string;
}

export interface EfficiencyMetrics {
  site_id: string;
  period: string;
  building_sqm: number;
  energy_intensity_kwh_per_sqm_yr: number;
  carbon_intensity_kg_per_sqm_yr: number;
  total_kwh_year: number;
  total_co2_tonnes_year: number;
  benchmarks: {
    energy_typical: number;
    energy_efficient: number;
    carbon_typical: number;
    carbon_efficient: number;
  };
  vs_typical: { energy_pct: number; carbon_pct: number };
  vs_efficient: { energy_pct: number; carbon_pct: number };
}

export interface SustainabilitySummary {
  site_id: string;
  current_month: EmissionsSnapshot;
  ytd: {
    total_co2_kg: number;
    total_co2_tonnes: number;
    total_kwh: number;
  };
  trend: 'improving' | 'stable' | 'worsening';
  target_reduction_pct: number;
  green_star: {
    total_achieved: number;
    total_max: number;
    estimated_rating: string;
    target_rating: string;
  };
  carbon_intensity_kg_per_sqm: number;
  energy_intensity_kwh_per_sqm: number;
}

export interface SustainabilityConfig {
  site_id: string;
  emission_factors: {
    grid_kg_co2_per_kwh: number;
    diesel_kg_co2_per_litre: number;
    water_kg_co2_per_kl: number;
    waste_kg_co2_per_ton: number;
    commute_kg_co2_per_person_day: number;
  };
  building_sqm: number;
  occupancy_capacity: number;
  target_reduction_pct: number;
  monthly_water_kl: number;
  monthly_waste_tons: number;
  working_days_per_month: number;
  avg_occupancy_pct: number;
}

// ==================== API Functions ====================

export const sustainabilityApi = {
  fetchSummary(siteId: string): Promise<SustainabilitySummary> {
    return fetchJson(`/api/sustainability/${siteId}/summary`);
  },

  fetchEmissions(siteId: string, months = 12): Promise<EmissionsHistory> {
    return fetchJson(`/api/sustainability/${siteId}/emissions?months=${months}`);
  },

  fetchCurrentEmissions(siteId: string): Promise<EmissionsSnapshot> {
    return fetchJson(`/api/sustainability/${siteId}/emissions/current`);
  },

  fetchEmissionsBreakdown(siteId: string): Promise<EmissionsBreakdown> {
    return fetchJson(`/api/sustainability/${siteId}/emissions/breakdown`);
  },

  fetchEfficiency(siteId: string): Promise<EfficiencyMetrics> {
    return fetchJson(`/api/sustainability/${siteId}/efficiency`);
  },

  fetchGreenStar(siteId: string): Promise<GreenStarAssessment> {
    return fetchJson(`/api/sustainability/${siteId}/green-star`);
  },

  updateGreenStarScore(
    siteId: string,
    categoryId: string,
    achievedPoints: number,
    notes?: string,
  ): Promise<GreenStarAssessment> {
    return fetchJson(`/api/sustainability/${siteId}/green-star/${categoryId}`, {
      method: 'PUT',
      body: JSON.stringify({ achieved_points: achievedPoints, notes }),
    });
  },

  fetchConfig(siteId: string): Promise<SustainabilityConfig> {
    return fetchJson(`/api/sustainability/${siteId}/config`);
  },

  updateConfig(
    siteId: string,
    updates: Partial<Omit<SustainabilityConfig, 'site_id'>>,
  ): Promise<SustainabilityConfig> {
    return fetchJson(`/api/sustainability/${siteId}/config`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  },
};

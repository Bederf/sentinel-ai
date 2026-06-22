/**
 * Sites & Buildings API Client
 *
 * Handles site and building management, equipment inventory, and facility data.
 */

import { fetchApi } from './client';
import { sitesBatcher } from './batchers';

// ============= Site & Building Types =============

export interface Site {
  id: string;
  code: string;
  name: string;
  address?: string;
  type?: string;
  status: "draft" | "active" | "archived";
  latitude?: number | null;
  longitude?: number | null;
  square_meters?: number;
  orientation_degrees?: number | null;
  created_at: string;
}

export interface Equipment {
  id: string;
  code: string;
  name: string;
  equipment_type: string;
  model?: string;
  serial_number?: string;
  installation_date?: string;
  health_score: number;
  status: string;
  zone_key?: string; // Normalized zone identifier (e.g., Zone-L1-1 for office, Zone-L3-ICU for hospital)
}

export interface BuildingEquipmentResponse {
  site_id: string;
  site_name: string;
  total_assets: number;
  equipment: Equipment[];
}

// ============= Desk & Zone Types =============

export interface DeskCoordinates {
  x: number;
  y: number;
  z: number;
}

export interface Desk {
  id: string;
  desk_id: string;
  zone_id: string;
  floor: string;
  context: 'near_diffuser' | 'near_window' | 'near_printer' | 'corner' | 'open_plan';
  x_coord: number;
  y_coord: number;
  z_coord: number;
  coordinates?: DeskCoordinates;
}

export interface ZoneCentroid {
  x: number;
  z: number;
}

export interface ZoneCentroidResponse {
  zone_id: string;
  centroid: ZoneCentroid;
  desk_count?: number;
}

export interface AllZoneCentroidsResponse {
  site_id: string;
  zone_count: number;
  centroid_count: number;
  centroids: Record<string, ZoneCentroid>;
}

export interface DeskStatsResponse {
  site_id: string;
  total_desks: number;
  total_zones: number;
  desks_per_zone: Record<string, number>;
  desks_per_floor: Record<string, number>;
  desks_by_context: Record<string, number>;
}

export interface CreateSiteRequest {
  name: string;
  address?: string;
  region?: string;
  type?: string;
  floors?: string[];
  sqm?: number;
  year_built?: number;
  latitude?: number;
  longitude?: number;
  contact_phone?: string;
  contact_email?: string;
  whatsapp_phone?: string;
  occupancy_capacity?: number;
  total_desks?: number;
  parking_bays?: number;
  nmd_limit_kva?: number;
  demand_charge_per_kva?: number;
  electricity_provider?: string;
  equipment_count?: number;
  operating_hours?: Record<string, unknown>;
  optimization_settings?: Record<string, unknown>;
  building_geometry?: Record<string, unknown>;
  features?: Record<string, boolean>;
}

export interface SiteListResponse {
  total: number;
  sites: Site[];
}

export interface OnboardingFactSource {
  source: string;
  confidence: number;
  evidence: string;
}

export interface OnboardingFactsResponse {
  status: string;
  values: Partial<CreateSiteRequest> & { address?: string };
  sources: Record<string, OnboardingFactSource>;
  missing: string[];
  scrape_available: boolean;
}

// ============= Sites API Methods =============

export const sitesApi = {
  /**
   * Get all accessible sites
   *
   * Returns { total, sites[] } - extract .sites for array of sites
   */
  getSites: async () => {
    const res = await fetchApi<{
      active: Site[]
      inactive: Site[]
      total: number
    }>("/api/buildings")
    return { sites: res.active, total: res.active.length }
  },

  /**
   * Get single site (batched to prevent 429 rate limit errors)
   *
   * Multiple simultaneous getSite calls are automatically batched and sent
   * in a single POST /api/sites/batch request, preventing rate limiting
   * when many dashboard components load site data simultaneously.
   */
  getSite: (siteId: string) =>
    sitesBatcher(siteId),

  /**
   * Create new site
   */
  create: (data: CreateSiteRequest) =>
    fetchApi<Site>("/api/buildings", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  scrapeOnboardingFacts: (data: { site_name: string; address?: string; building_type?: string }) =>
    fetchApi<OnboardingFactsResponse>("/api/sites/onboarding-facts", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /**
   * Get buildings in a site
   */
  getBuildings: (siteId: string) =>
    fetchApi<Site[]>(`/api/sites/${siteId}/buildings`),

  /**
   * Get equipment for a building
   */
  getEquipment: (siteId: string) =>
    fetchApi<BuildingEquipmentResponse>(`/api/buildings/${siteId}/equipment`),

  /**
   * Get equipment by code
   */
  getEquipmentByCode: (code: string) =>
    fetchApi<Equipment>(`/api/equipment/${code}`),

  // ============= Desk Data Methods =============

  /**
   * Get all desks for a building
   * Optionally filtered by floor
   *
   * @param siteId - Building UUID
   * @param floor - Optional floor code filter (e.g., "L0", "L1", "L2")
   * @returns List of desk records with positions and context
   */
  getDesks: (siteId: string, floor?: string) => {
    const url = floor
      ? `/api/buildings/${siteId}/desks?floor=${encodeURIComponent(floor)}`
      : `/api/buildings/${siteId}/desks`;
    return fetchApi<Desk[]>(url);
  },

  /**
   * Get all desks in a specific zone
   *
   * @param siteId - Building UUID
   * @param zoneId - Zone ID (e.g., "Zone-L1-A")
   * @returns List of desks in the zone
   */
  getDesksByZone: (siteId: string, zoneId: string) =>
    fetchApi<Desk[]>(`/api/buildings/${siteId}/desks/zones/${encodeURIComponent(zoneId)}`),

  /**
   * Get centroid for a specific zone
   *
   * Used for calculating zone center position from desk positions.
   *
   * @param siteId - Building UUID
   * @param zoneId - Zone ID (e.g., "Zone-L1-A")
   * @returns Zone centroid with x, z coordinates and desk count
   */
  getZoneCentroid: (siteId: string, zoneId: string) =>
    fetchApi<ZoneCentroidResponse>(
      `/api/buildings/${siteId}/desks/zones/${encodeURIComponent(zoneId)}/centroid`
    ),

  /**
   * Get centroids for all zones in a building
   *
   * Efficient operation: returns pre-calculated centroids for all zones.
   * ~80x smaller payload than loading all desks, ideal for Digital Twin.
   *
   * @param siteId - Building UUID
   * @returns Map of zone_id → centroid coordinates
   */
  getZoneCentroids: (siteId: string) =>
    fetchApi<AllZoneCentroidsResponse>(`/api/buildings/${siteId}/zone-ingestion/centroids`),

  /**
   * Get desk statistics for a building
   *
   * Provides summary information about desks and zones:
   * - Total desk count
   * - Desks per zone
   * - Desks per floor
   * - Distribution by context
   *
   * @param siteId - Building UUID
   * @returns Desk statistics
   */
  getDeskStats: (siteId: string) =>
    fetchApi<DeskStatsResponse>(`/api/buildings/${siteId}/desks/stats`),

  // ============= Zone Ingestion Methods =============

  /**
   * Ingest zone configuration for a building
   *
   * @param siteId - Building UUID
   * @param request - Object with zones array
   * @returns Ingestion response
   */
  ingestZones: (siteId: string, request: { zones: (Omit<ZoneCentroidResponse, 'centroid'> & Omit<ZoneCentroid, 'centroid'> & { zone_id: string; zone_name: string; floor: string; zone_type: string; typical_occupancy?: number; area_sqm?: number; zone_letter?: string })[] }) =>
    fetchApi(`/api/buildings/${siteId}/zone-ingestion/zones`, {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  /**
   * Ingest desk configuration for a building
   *
   * @param siteId - Building UUID
   * @param request - Object with desks array
   * @returns Ingestion response
   */
  ingestDesks: (siteId: string, request: { desks: (Desk & { coordinates: { x: number; y: number; z: number } })[] }) =>
    fetchApi(`/api/buildings/${siteId}/zone-ingestion/desks`, {
      method: 'POST',
      body: JSON.stringify(request),
    }),
};

// ============= Site Profile API (Phase 191) =============

export interface ObjectiveWeights {
  cost: number;
  comfort: number;
}

export interface OperatingSchedule {
  weekday_start: string;
  weekday_end: string;
  saturday_start?: string;
  saturday_end?: string;
  sunday_active: boolean;
  timezone: string;
  is_24_7: boolean;
  [key: string]: unknown;
}

export interface OnSiteGeneration {
  solar_kwp: number;
  bess_kwh: number;
  generator: boolean;
}

export interface SiteProfileRequest {
  building_type: string;
  primary_objective: string;
  objective_weights?: ObjectiveWeights;
  operating_schedule?: OperatingSchedule | Record<string, unknown>;
  tariff_structure?: string;
  on_site_generation?: OnSiteGeneration;
  temp_band_min_c?: number;
  temp_band_max_c?: number;
  clinical_zones_present?: boolean;
  regulatory_frameworks?: string[];
}

export interface SiteProfileResponse extends SiteProfileRequest {
  id: string;
  site_id: string;
  confirmed_at: string | null;
  confirmed_by: string | null;
  profile_version: number;
  created_at: string;
  updated_at: string;
}

export interface SiteProfileStatus {
  site_id: string;
  has_profile: boolean;
  confirmed_at: string | null;
}

export const siteProfileApi = {
  /** Create or update a building profile (called after wizard confirms scraped data) */
  create: (siteId: string, data: SiteProfileRequest) =>
    fetchApi<SiteProfileResponse>(`/api/site-profiles/${encodeURIComponent(siteId)}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /** Get the building profile for a site */
  get: (siteId: string) =>
    fetchApi<SiteProfileResponse>(`/api/site-profiles/${encodeURIComponent(siteId)}`),

  /** Lightweight status check (has profile? confirmed?) */
  getStatus: (siteId: string) =>
    fetchApi<SiteProfileStatus>(`/api/site-profiles/${encodeURIComponent(siteId)}/status`),
};

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
  gps_lat?: number;
  gps_lon?: number;
  square_meters?: number;
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
}

export interface SiteListResponse {
  total: number;
  sites: Site[];
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
    return { sites: [...res.active, ...res.inactive], total: res.total }
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

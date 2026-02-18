/**
 * Sites & Buildings API Client
 *
 * Handles site and building management, equipment inventory, and facility data.
 */

import { fetchApi } from './client';

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
  building_id: string;
  building_name: string;
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
  building_id: string;
  zone_count: number;
  centroid_count: number;
  centroids: Record<string, ZoneCentroid>;
}

export interface DeskStatsResponse {
  building_id: string;
  total_desks: number;
  total_zones: number;
  desks_per_zone: Record<string, number>;
  desks_per_floor: Record<string, number>;
  desks_by_context: Record<string, number>;
}

export interface DemoBuilding {
  id: string;
  name: string;
  type: string;
  equipment_count: number;
  description: string;
}

export interface CreateSiteRequest {
  code: string;
  name: string;
  address?: string;
  type?: string;
  gps_lat?: number;
  gps_lon?: number;
  square_meters?: number;
}

export interface SiteListResponse {
  total: number;
  sites: Site[];
}

// ============= Sites API Methods =============

export const sitesApi = {
  /**
   * Get demo/template buildings (for onboarding wizard)
   */
  getDemoBuildings: async () => {
    // Return demo buildings for site configuration
    return [
      {
        id: 'demo-001',
        name: 'Sandton Office Tower',
        type: 'Commercial',
        equipment_count: 156,
        description: '3-floor office building with HVAC, lighting, and security systems',
      },
      {
        id: 'demo-002',
        name: 'Retail Mall',
        type: 'Retail',
        equipment_count: 89,
        description: 'Multi-floor shopping center with climate control',
      },
      {
        id: 'demo-003',
        name: 'Data Center',
        type: 'Industrial',
        equipment_count: 234,
        description: 'Critical infrastructure facility with redundant systems',
      },
    ] as DemoBuilding[];
  },

  /**
   * Get all accessible sites
   *
   * Returns { total, sites[] } - extract .sites for array of sites
   */
  getSites: () =>
    fetchApi<SiteListResponse>("/api/sites"),

  /**
   * Get single site
   */
  getSite: (siteId: string) =>
    fetchApi<Site>(`/api/sites/${siteId}`),

  /**
   * Create new site
   */
  create: (data: CreateSiteRequest) =>
    fetchApi<Site>("/api/sites", {
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
  getEquipment: (buildingId: string) =>
    fetchApi<BuildingEquipmentResponse>(`/api/buildings/${buildingId}/equipment`),

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
   * @param buildingId - Building UUID
   * @param floor - Optional floor code filter (e.g., "L0", "L1", "L2")
   * @returns List of desk records with positions and context
   */
  getDesks: (buildingId: string, floor?: string) => {
    const url = floor
      ? `/api/buildings/${buildingId}/desks?floor=${encodeURIComponent(floor)}`
      : `/api/buildings/${buildingId}/desks`;
    return fetchApi<Desk[]>(url);
  },

  /**
   * Get all desks in a specific zone
   *
   * @param buildingId - Building UUID
   * @param zoneId - Zone ID (e.g., "Zone-L1-A")
   * @returns List of desks in the zone
   */
  getDesksByZone: (buildingId: string, zoneId: string) =>
    fetchApi<Desk[]>(`/api/buildings/${buildingId}/desks/zones/${encodeURIComponent(zoneId)}`),

  /**
   * Get centroid for a specific zone
   *
   * Used for calculating zone center position from desk positions.
   *
   * @param buildingId - Building UUID
   * @param zoneId - Zone ID (e.g., "Zone-L1-A")
   * @returns Zone centroid with x, z coordinates and desk count
   */
  getZoneCentroid: (buildingId: string, zoneId: string) =>
    fetchApi<ZoneCentroidResponse>(
      `/api/buildings/${buildingId}/desks/zones/${encodeURIComponent(zoneId)}/centroid`
    ),

  /**
   * Get centroids for all zones in a building
   *
   * Efficient operation: returns pre-calculated centroids for all zones.
   * ~80x smaller payload than loading all desks, ideal for Digital Twin.
   *
   * @param buildingId - Building UUID
   * @returns Map of zone_id → centroid coordinates
   */
  getZoneCentroids: (buildingId: string) =>
    fetchApi<AllZoneCentroidsResponse>(`/api/buildings/${buildingId}/zone-ingestion/centroids`),

  /**
   * Get desk statistics for a building
   *
   * Provides summary information about desks and zones:
   * - Total desk count
   * - Desks per zone
   * - Desks per floor
   * - Distribution by context
   *
   * @param buildingId - Building UUID
   * @returns Desk statistics
   */
  getDeskStats: (buildingId: string) =>
    fetchApi<DeskStatsResponse>(`/api/buildings/${buildingId}/desks/stats`),

  // ============= Zone Ingestion Methods =============

  /**
   * Ingest zone configuration for a building
   *
   * @param buildingId - Building UUID
   * @param request - Object with zones array
   * @returns Ingestion response
   */
  ingestZones: (buildingId: string, request: { zones: (Omit<ZoneCentroidResponse, 'centroid'> & Omit<ZoneCentroid, 'centroid'> & { zone_id: string; zone_name: string; floor: string; zone_type: string; typical_occupancy?: number; area_sqm?: number; zone_letter?: string })[] }) =>
    fetchApi(`/api/buildings/${buildingId}/zone-ingestion/zones`, {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  /**
   * Ingest desk configuration for a building
   *
   * @param buildingId - Building UUID
   * @param request - Object with desks array
   * @returns Ingestion response
   */
  ingestDesks: (buildingId: string, request: { desks: (Desk & { coordinates: { x: number; y: number; z: number } })[] }) =>
    fetchApi(`/api/buildings/${buildingId}/zone-ingestion/desks`, {
      method: 'POST',
      body: JSON.stringify(request),
    }),
};

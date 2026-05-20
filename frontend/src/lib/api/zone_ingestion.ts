/**
 * Zone Ingestion API Client
 *
 * Handles zone and desk configuration for building onboarding.
 */

import { fetchApi } from './client';

// ============= Zone & Desk Configuration Types =============

export interface ZoneConfig {
  zone_id: string;
  zone_name: string;
  floor: string;
  zone_letter?: string;
  zone_type: string;
  typical_occupancy?: number;
  area_sqm?: number;
}

export interface DeskCoordinates {
  x: number;
  y: number;
  z: number;
}

export interface DeskConfig {
  desk_id: string;
  zone_id: string;
  floor: string;
  context: 'near_diffuser' | 'near_window' | 'near_printer' | 'corner' | 'open_plan';
  coordinates: DeskCoordinates;
}

export interface ZonesIngestionRequest {
  zones: ZoneConfig[];
}

export interface DesksIngestionRequest {
  desks: DeskConfig[];
}

export interface IngestionResponse {
  status: 'success' | 'error';
  message?: string;
  items_created?: number;
}

export interface ZoneValidationResult {
  site_id: string;
  is_valid: boolean;
  errors: string[];
  error_count: number;
}

// ============= Zone Ingestion API Methods =============

export const zoneIngestionApi = {
  /**
   * Ingest zone configuration for a building
   *
   * @param siteId - Building UUID
   * @param request - Zone ingestion request with list of zones
   * @returns Ingestion response with status and count
   */
  ingestZones: (siteId: string, request: ZonesIngestionRequest) =>
    fetchApi<IngestionResponse>(
      `/api/buildings/${siteId}/zone-ingestion/zones`,
      {
        method: 'POST',
        body: JSON.stringify(request),
      }
    ),

  /**
   * Ingest desk configuration for a building
   *
   * @param siteId - Building UUID
   * @param request - Desk ingestion request with list of desks
   * @returns Ingestion response with status and count
   */
  ingestDesks: (siteId: string, request: DesksIngestionRequest) =>
    fetchApi<IngestionResponse>(
      `/api/buildings/${siteId}/zone-ingestion/desks`,
      {
        method: 'POST',
        body: JSON.stringify(request),
      }
    ),

  /**
   * Validate zone and desk structure for a building
   *
   * @param siteId - Building UUID
   * @returns Validation result with errors if any
   */
  validateZoneStructure: (siteId: string) =>
    fetchApi<ZoneValidationResult>(
      `/api/buildings/${siteId}/zone-ingestion/validate`
    ),

  /**
   * Get zone centroid from zone ingestion API
   *
   * @param siteId - Building UUID
   * @param zoneId - Zone ID
   * @returns Zone centroid response
   */
  getZoneCentroid: (siteId: string, zoneId: string) =>
    fetchApi(`/api/buildings/${siteId}/zone-ingestion/zones/${encodeURIComponent(zoneId)}/centroid`),

  /**
   * Get all zone centroids from zone ingestion API
   *
   * @param siteId - Building UUID
   * @returns All zone centroids for building
   */
  getAllCentroids: (siteId: string) =>
    fetchApi(`/api/buildings/${siteId}/zone-ingestion/centroids`),
};

// ============= Floor Plan Extraction Types =============

export interface FloorConfig {
  level: string;
  height: number;
  width: number;
  depth: number;
}

export interface EquipmentConfig {
  name: string;
  equipment_type: string;
  floor: string;
  x: number;
  y: number;
  zone: string | null;
  confidence: number | null;
}

export interface ZoneExtractConfig {
  zone_id: string;
  floor: string;
  zone_type: string;
  equipment: string[];
}

export interface BuildingConfigResponse {
  site_code: string;
  site_name: string;
  floors: FloorConfig[];
  equipment: EquipmentConfig[];
  zones: ZoneExtractConfig[];
  extraction_metadata: Record<string, unknown>;
}

// ============= Site Geocoding API =============

export interface GeocodeResult {
  lat: number;
  lon: number;
  display_name: string;
  orientation_degrees: number | null;
  type: string;
  address: {
    road?: string;
    suburb?: string;
    city?: string;
    province?: string;
    country?: string;
    postcode?: string;
  };
}

export const siteGeocodeApi = {
  /**
   * Geocode a building address and get GPS orientation
   *
   * @param address - Building name or address
   * @returns Lat/lon + orientation + normalized address
   */
  geocode: (address: string) =>
    fetchApi<GeocodeResult>(`/api/digital-twin/geocode?address=${encodeURIComponent(address)}`),
};

export const floorPlanApi = {
  /**
   * Extract building config from PDF floor plan
   *
   * @param file - PDF file
   * @param siteCode - Building code (e.g. 'site-002')
   * @param siteName - Building name
   * @param floorsCount - Expected number of floors
   * @returns Building configuration with floors, equipment, zones
   */
  extractFromPdf: (file: File, siteCode: string, siteName?: string, floorsCount = 3) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("site_code", siteCode);
    if (siteName) formData.append("site_name", siteName);
    formData.append("floors_count", String(floorsCount));
    formData.append("skip_sanitization", "true");

    return fetch("/api/digital-twin/extract-from-pdf", {
      method: "POST",
      body: formData,
    }).then((res) => {
      if (!res.ok) throw new Error(`PDF extraction failed: ${res.statusText}`);
      return res.json() as Promise<BuildingConfigResponse>;
    });
  },

  /**
   * Extract building config from DXF floor plan
   *
   * @param file - DXF file
   * @param siteCode - Building code (e.g. 'site-002')
   * @param siteName - Building name
   * @returns Building configuration with floors, equipment, zones
   */
  extractFromDxf: (file: File, siteCode: string, siteName?: string) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("site_code", siteCode);
    if (siteName) formData.append("site_name", siteName);

    return fetch("/api/digital-twin/extract-from-dxf", {
      method: "POST",
      body: formData,
    }).then((res) => {
      if (!res.ok) throw new Error(`DXF extraction failed: ${res.statusText}`);
      return res.json() as Promise<BuildingConfigResponse>;
    });
  },
};

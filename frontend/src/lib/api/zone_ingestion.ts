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

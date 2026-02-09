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

export interface CreateSiteRequest {
  code: string;
  name: string;
  address?: string;
  type?: string;
  gps_lat?: number;
  gps_lon?: number;
  square_meters?: number;
}

// ============= Sites API Methods =============

export const sitesApi = {
  /**
   * Get all accessible sites
   */
  getSites: () =>
    fetchApi<Site[]>("/api/sites"),

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
};


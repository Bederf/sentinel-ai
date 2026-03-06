/**
 * Digital Twin 3D Configuration API Client
 *
 * Fetches and updates stored equipment positions for the digital twin.
 * Stored positions override algorithmic placement from desk/zone data.
 */

import { fetchApi } from './client';

// ============= Types =============

export interface StoredEquipmentPosition {
  floor: string;
  x: number;
  y: number;
}

export interface EquipmentPositionsResponse {
  site_id: string;
  positions: Record<string, StoredEquipmentPosition>;
  count: number;
}

export interface PositionUpdateResponse {
  equipment_id: string;
  floor: string;
  x: number;
  y: number;
  status: string;
}

// ============= API Functions =============

/**
 * Fetch stored equipment positions for a site.
 * Returns a map of equipment_id -> {floor, x, y}.
 * Empty map means no stored positions (use algorithmic fallback).
 */
export async function getEquipmentPositions(
  siteId: string
): Promise<EquipmentPositionsResponse> {
  return fetchApi<EquipmentPositionsResponse>(
    `/api/buildings/${siteId}/equipment-positions`
  );
}

/**
 * Update a single equipment position.
 * Creates a 3D config record if none exists.
 */
export async function updateEquipmentPosition(
  siteId: string,
  equipmentId: string,
  position: { floor: string; x: number; y: number }
): Promise<PositionUpdateResponse> {
  return fetchApi<PositionUpdateResponse>(
    `/api/buildings/${siteId}/equipment-positions/${equipmentId}`,
    {
      method: 'PATCH',
      body: JSON.stringify({
        equipment_id: equipmentId,
        floor: position.floor,
        x: position.x,
        y: position.y,
      }),
    }
  );
}

export const digitalTwinApi = {
  getEquipmentPositions,
  updateEquipmentPosition,
};

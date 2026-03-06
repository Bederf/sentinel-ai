/**
 * React Query hook for stored equipment positions
 *
 * Fetches positions from site_3d_configs table.
 * Returns a map of equipment_id -> {floor, x, y} for overriding
 * algorithmic placement in the digital twin.
 *
 * Priority: stored positions > desk-derived > synthetic grid
 */

import { useQuery } from '@tanstack/react-query';
import { digitalTwinApi } from '@/lib/api/digitalTwin';
import type { StoredEquipmentPosition } from '@/lib/api/digitalTwin';

/**
 * Fetch stored equipment positions for a site.
 *
 * @param siteId Building UUID or site code
 * @returns Map of equipment_id -> StoredEquipmentPosition (empty if none stored)
 */
export function useStoredPositions(
  siteId: string
): Record<string, StoredEquipmentPosition> {
  const { data } = useQuery({
    queryKey: ['equipment-positions', siteId],
    queryFn: () => digitalTwinApi.getEquipmentPositions(siteId),
    staleTime: 2 * 60 * 1000, // 2 minutes — positions rarely change
    enabled: !!siteId,
    retry: 0,
    throwOnError: false,
  });

  return data?.positions ?? {};
}

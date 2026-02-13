/**
 * React Query hook for zone boundary calculations
 *
 * Fetches desk data and calculates min/max bounds for each zone.
 * Useful for adaptive equipment positioning within zones.
 */

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { sitesApi, type Desk } from '@/lib/api/sites';
import { calculateZoneBoundsFromCoords, type ZoneBounds } from '@/utils/equipmentPositioning';

/**
 * Fetch desk data for a building and calculate zone boundaries
 *
 * @param buildingId Building UUID
 * @returns Map of zone_id → ZoneBounds (e.g., "Zone-L1-A" → bounds)
 *
 * @example
 * const zoneBounds = useZoneBounds(buildingId);
 * // zoneBounds = { "Zone-L0-A": { minX, maxX, minZ, maxZ, ... }, ... }
 */
export function useZoneBounds(buildingId: string): Record<string, ZoneBounds> {
  // Fetch desk data via sitesApi.getDesks()
  // Cached with 5m staleTime (desk positions rarely change during operation)
  const { data: desks = [] } = useQuery({
    queryKey: ['desks', buildingId],
    queryFn: () => sitesApi.getDesks(buildingId),
    staleTime: 5 * 60 * 1000, // 5 minutes
    enabled: !!buildingId,
    retry: 0,
    // Return empty array on failure (fallback positioning will be used)
    throwOnError: false,
  });

  // Group desks by zone and calculate bounds
  return useMemo(() => {
    if (!desks || desks.length === 0) return {};

    // Group desks by zone_id
    const desksByZone = desks.reduce(
      (acc, desk) => {
        const zoneId = desk.zone_id || 'unknown';
        if (!acc[zoneId]) {
          acc[zoneId] = { xs: [], zs: [] };
        }
        acc[zoneId].xs.push(desk.x_coord);
        acc[zoneId].zs.push(desk.z_coord);
        return acc;
      },
      {} as Record<string, { xs: number[]; zs: number[] }>
    );

    // Calculate bounds for each zone
    const bounds: Record<string, ZoneBounds> = {};
    Object.entries(desksByZone).forEach(([zoneId, coords]) => {
      const zoneBounds = calculateZoneBoundsFromCoords(coords.xs, coords.zs);
      if (zoneBounds) {
        bounds[zoneId] = zoneBounds;
      }
    });

    return bounds;
  }, [desks]);
}

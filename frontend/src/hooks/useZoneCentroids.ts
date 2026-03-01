import { useQuery } from '@tanstack/react-query';
import { sitesApi, type ZoneCentroid } from '@/lib/api/sites';

/**
 * Hook to fetch zone centroids for a building
 * Used for accurate 3D positioning of equipment in DigitalTwin
 *
 * Cache: 5m staleTime, 30m gcTime (rarely changes)
 * Deduplicates identical queries via React Query
 *
 * @param buildingId - Building code (resolved from registered buildings)
 * @param options.enabled - Enable/disable query (default: true)
 */
export function useZoneCentroids(buildingId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['zone-centroids', buildingId],
    queryFn: async () => {
      const response = await sitesApi.getZoneCentroids(buildingId);
      return response?.centroids || {} as Record<string, ZoneCentroid>;
    },
    staleTime: 5 * 60 * 1000, // 5m - zone configs rarely change
    gcTime: 30 * 60 * 1000, // 30m
    enabled: !!buildingId && options?.enabled !== false,
    retry: 2,
  });
}

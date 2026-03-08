import { useQuery } from '@tanstack/react-query';
import { fetchSolarOverview } from '@/lib/solarApi';
// SolarOverview type available from '@/lib/solarApi' if needed

/**
 * Hook to fetch solar installation overview (generation, BESS SOC, grid flow)
 *
 * Returns:
 * - data: SolarOverview | undefined (undefined while loading)
 * - isLoading: boolean (true while fetching)
 * - error: Error | null (error if query failed)
 *
 * Caching:
 * - staleTime: 15s (dynamic data, refresh frequently)
 * - gcTime: 5m (keep in memory 5m after unmount)
 *
 * @param siteId - Solar site identifier (resolved from registered buildings)
 * @returns Query result with SolarOverview data
 */
export function useSolarOverview(siteId: string) {
  return useQuery({
    queryKey: ['solar-overview', siteId],
    queryFn: () => fetchSolarOverview(siteId),
    staleTime: 15 * 1000, // 15s - dynamic data
    gcTime: 5 * 60 * 1000, // 5m - garbage collection time
    enabled: !!siteId, // Only fetch if siteId provided
  });
}

export default useSolarOverview;

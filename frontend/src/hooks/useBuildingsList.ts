import { useQuery } from '@tanstack/react-query';
import { sitesApi } from '@/lib/api';

/**
 * Hook to fetch list of buildings/sites
 * Cache: 5m staleTime, 30m gcTime
 */
export function useBuildingsList(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['buildings-list'],
    queryFn: () => sitesApi.getSites(),
    staleTime: 5 * 60 * 1000, // 5m
    gcTime: 30 * 60 * 1000, // 30m
    enabled: options?.enabled !== false,
  });
}

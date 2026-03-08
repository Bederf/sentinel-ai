import { useQuery } from '@tanstack/react-query';
import { sitesApi } from '@/lib/api/sites';

/**
 * Hook to fetch list of all sites
 *
 * Cache: 30s staleTime, 5m gcTime
 * Deduplicates identical queries automatically via React Query
 */
export function useSitesList(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['sites-list'],
    queryFn: async () => {
      const response = await sitesApi.getSites();
      return response.sites || [];
    },
    staleTime: 30 * 1000, // 30s - sites rarely change
    gcTime: 5 * 60 * 1000, // 5m
    enabled: options?.enabled !== false,
    retry: 2,
  });
}

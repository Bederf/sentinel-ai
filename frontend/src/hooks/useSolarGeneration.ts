/**
 * useSolarGeneration - React Query hooks for solar generation data
 */

import { useQuery } from '@tanstack/react-query';

export function useSolarGeneration(siteId: string | undefined) {
  return useQuery({
    queryKey: ['solar', 'generation', siteId],
    queryFn: async () => {
      if (!siteId) return null;
      const response = await fetch(`/api/solar/${siteId}/generation`);
      if (!response.ok) throw new Error('Failed to fetch solar generation');
      return response.json();
    },
    enabled: !!siteId,
    staleTime: 15 * 1000,
    gcTime: 5 * 60 * 1000,
  });
}

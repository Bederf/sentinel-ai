/**
 * useOptimizationEngine - React Query hook for AI-driven equipment optimization
 */

import { useQuery } from '@tanstack/react-query';

export function useOptimizationEngine(siteId: string | undefined) {
  return useQuery({
    queryKey: ['optimization', 'engine', siteId],
    queryFn: async () => {
      if (!siteId) return null;
      const response = await fetch(`/api/optimization/${siteId}`);
      if (!response.ok) throw new Error('Failed to fetch optimization status');
      return response.json();
    },
    enabled: !!siteId,
    staleTime: 30 * 1000,
    gcTime: 5 * 60 * 1000,
  });
}

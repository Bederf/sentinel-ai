/**
 * useDemandForecasting - React Query hook for ML demand forecasting
 */

import { useQuery } from '@tanstack/react-query';

export function useDemandForecasting(siteId: string | undefined) {
  return useQuery({
    queryKey: ['demand', 'forecasting', siteId],
    queryFn: async () => {
      if (!siteId) return null;
      const response = await fetch(`/api/demand-forecasting/${siteId}`);
      if (!response.ok) throw new Error('Failed to fetch demand forecast');
      return response.json();
    },
    enabled: !!siteId,
    staleTime: 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });
}

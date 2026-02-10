import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api/fetchClient';

/**
 * Predictions summary type
 */
export interface PredictionSummary {
  high_risk: number;
  medium_risk: number;
  low_risk: number;
}

/**
 * Hook to fetch aggregated site predictions
 * Cache: 60s staleTime, 5m gcTime
 */
export function useSitePredictions(
  siteId: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: ['site-predictions', siteId],
    queryFn: () => apiFetch<PredictionSummary>(`/api/sites/${siteId}/predictions`),
    staleTime: 60 * 1000, // 60s
    gcTime: 5 * 60 * 1000, // 5m
    enabled: options?.enabled !== false,
  });
}

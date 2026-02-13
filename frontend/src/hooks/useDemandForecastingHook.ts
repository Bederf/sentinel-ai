/**
 * useDemandForecasting - Hook for ML-based demand forecasting
 *
 * Fetches 24-hour hourly demand predictions with confidence intervals.
 */

import { useQuery } from '@tanstack/react-query';
import { demandForecastingApi } from '../lib/api/demand_forecasting';
import type { DemandForecastResponse } from '../lib/api/demand_forecasting';

/**
 * Fetch 24-hour demand forecast for site
 */
export function useDemandForecasting(siteId: string | undefined) {
  return useQuery<DemandForecastResponse>({
    queryKey: ['demand', 'forecast', siteId],
    queryFn: () => demandForecastingApi.getForecast(siteId!),
    enabled: !!siteId,
    staleTime: 60 * 1000, // 60 seconds - demand changes frequently
    gcTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Fetch current demand status
 */
export function useDemandStatus(siteId: string | undefined) {
  return useQuery({
    queryKey: ['demand', 'status', siteId],
    queryFn: () => demandForecastingApi.getStatus(siteId!),
    enabled: !!siteId,
    staleTime: 15 * 1000, // 15 seconds - status changes in real-time
    gcTime: 3 * 60 * 1000, // 3 minutes
  });
}

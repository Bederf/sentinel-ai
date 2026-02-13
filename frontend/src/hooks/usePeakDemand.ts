/**
 * usePeakDemand - React Query hooks for peak demand management
 *
 * Provides hooks for fetching demand status, forecasts, and recommendations
 * with automatic caching and deduplication via React Query.
 *
 * Stale times:
 * - Demand status: 15s (frequently changing)
 * - Forecast: 60s (model runs infrequently)
 * - Recommendations: 30s (coordinator runs every 5 min)
 */

import { useQuery } from '@tanstack/react-query';
import { peakDemandApi } from '../lib/api/peakDemand';
import type {
  DemandStatusResponse,
  DemandForecastResponse,
  MultiModuleRecommendation,
  DemandSummary,
} from '../lib/api/peakDemand';

/**
 * Fetch current demand status with NMD headroom
 *
 * Stale time: 15s (demand changes frequently during peak periods)
 */
export function usePeakDemandStatus(siteId: string | undefined) {
  return useQuery<DemandStatusResponse, Error>({
    queryKey: ['peakDemand', 'status', siteId],
    queryFn: () => peakDemandApi.getDemandStatus(siteId!),
    enabled: !!siteId,
    staleTime: 15 * 1000,
    gcTime: 5 * 60 * 1000, // 5 minutes
    retry: 0,
  });
}

/**
 * Fetch 24-hour demand forecast
 *
 * Stale time: 60s (forecast updates on coordinator cycle)
 */
export function usePeakDemandForecast(siteId: string | undefined) {
  return useQuery<DemandForecastResponse, Error>({
    queryKey: ['peakDemand', 'forecast', siteId],
    queryFn: () => peakDemandApi.getDemandForecast(siteId!),
    enabled: !!siteId,
    staleTime: 60 * 1000,
    gcTime: 10 * 60 * 1000, // 10 minutes
    retry: 0,
  });
}

/**
 * Fetch pending peak shaving recommendations
 *
 * Stale time: 30s (coordinator runs every 5 minutes)
 */
export function usePeakDemandRecommendations(siteId: string | undefined) {
  return useQuery<MultiModuleRecommendation[], Error>({
    queryKey: ['peakDemand', 'recommendations', siteId],
    queryFn: () => peakDemandApi.getRecommendations(siteId!),
    enabled: !!siteId,
    staleTime: 30 * 1000,
    gcTime: 5 * 60 * 1000, // 5 minutes
    retry: 0,
  });
}

/**
 * Fetch demand summary for dashboard
 *
 * Stale time: 20s (quick overview)
 */
export function usePeakDemandSummary(siteId: string | undefined) {
  return useQuery<DemandSummary, Error>({
    queryKey: ['peakDemand', 'summary', siteId],
    queryFn: () => peakDemandApi.getDemandSummary(siteId!),
    enabled: !!siteId,
    staleTime: 20 * 1000,
    gcTime: 5 * 60 * 1000, // 5 minutes
    retry: 0,
  });
}

/**
 * Solar Dashboard Hooks
 *
 * Collection of React Query hooks for fetching and caching solar data
 * with appropriate stale times, error handling, and automatic retries.
 *
 * Hooks:
 * - useSolarSystemOverview: Live power, BESS, yield (stale: 10s)
 * - useSolarPerformance: Efficiency, strings, capacity, soiling (stale: 30s)
 * - useGridCompliance: Frequency, voltage, violations (stale: 5s)
 * - useBESSStatus: Charge, temperature, health, cycles (stale: 15s)
 * - useSolarDashboard: Aggregate all four (stale: depends on slowest)
 */

import { useQuery } from '@tanstack/react-query';
import type {
  LiveSystemData,
  PerformanceSummary,
  GridComplianceStatus,
  BESSStatusData,
} from '@/lib/api/solar';
import {
  fetchLiveSystemData,
  fetchPerformanceSummary,
  fetchGridComplianceStatus,
  fetchBESSStatusData,
} from '@/lib/api/solar';

/**
 * Fetch live system data (real-time power, BESS, yield, inverters)
 *
 * Caching strategy:
 * - staleTime: 10s (power data changes frequently)
 * - gcTime: 5m (keep in cache 5m after unmount)
 * - retry: exponential backoff on network errors
 * - refetchInterval: optional automatic polling
 *
 * @param siteId - Solar site identifier
 * @param refetchInterval - Optional polling interval in ms (undefined = no polling)
 * @returns Query result with LiveSystemData, isLoading, error
 */
export function useSolarSystemOverview(siteId: string, refetchInterval?: number) {
  return useQuery({
    queryKey: ['solar-system-overview', siteId],
    queryFn: () => fetchLiveSystemData(siteId),
    staleTime: 10 * 1000, // 10s - power data frequently changes
    gcTime: 5 * 60 * 1000, // 5m - garbage collection
    enabled: !!siteId,
    refetchInterval,
    retry: (failureCount) => failureCount < 3,
  });
}

/**
 * Fetch performance metrics (efficiency %, string health, capacity factor, soiling)
 *
 * Caching strategy:
 * - staleTime: 30s (calculated metrics stable over longer periods)
 * - gcTime: 5m
 * - retry: exponential backoff
 *
 * @param siteId - Solar site identifier
 * @param refetchInterval - Optional polling interval in ms
 * @returns Query result with PerformanceSummary
 */
export function useSolarPerformance(siteId: string, refetchInterval?: number) {
  return useQuery({
    queryKey: ['solar-performance', siteId],
    queryFn: () => fetchPerformanceSummary(siteId),
    staleTime: 30 * 1000, // 30s - less volatile than real-time
    gcTime: 5 * 60 * 1000, // 5m
    enabled: !!siteId,
    refetchInterval,
    retry: (failureCount) => failureCount < 3,
  });
}

/**
 * Fetch grid compliance status (frequency, load shedding, violations)
 *
 * Caching strategy:
 * - staleTime: 5s (grid parameters critical, must be fresh)
 * - gcTime: 5m
 * - retry: exponential backoff
 *
 * @param siteId - Solar site identifier
 * @param refetchInterval - Optional polling interval in ms
 * @returns Query result with GridComplianceStatus
 */
export function useGridCompliance(siteId: string, refetchInterval?: number) {
  return useQuery({
    queryKey: ['grid-compliance', siteId],
    queryFn: () => fetchGridComplianceStatus(siteId),
    staleTime: 5 * 1000, // 5s - grid frequency critical, must be fresh
    gcTime: 5 * 60 * 1000, // 5m
    enabled: !!siteId,
    refetchInterval,
    retry: (failureCount) => failureCount < 3,
  });
}

/**
 * Fetch BESS status (charge, temperature, SOH, cycle count)
 *
 * Caching strategy:
 * - staleTime: 15s (battery data moderately dynamic)
 * - gcTime: 5m
 * - retry: exponential backoff
 *
 * @param siteId - Solar site identifier
 * @param refetchInterval - Optional polling interval in ms
 * @returns Query result with BESSStatusData
 */
export function useBESSStatus(siteId: string, refetchInterval?: number) {
  return useQuery({
    queryKey: ['bess-status', siteId],
    queryFn: () => fetchBESSStatusData(siteId),
    staleTime: 15 * 1000, // 15s - dynamic but not as critical as frequency
    gcTime: 5 * 60 * 1000, // 5m
    enabled: !!siteId,
    refetchInterval,
    retry: (failureCount) => failureCount < 3,
  });
}

/**
 * Aggregate hook for full solar dashboard
 * Combines all four queries and returns consolidated result
 *
 * Usage: useSolarDashboard(siteId)
 *
 * Returns: {
 *   systemOverview: { data, isLoading, error, ... },
 *   performance: { data, isLoading, error, ... },
 *   gridCompliance: { data, isLoading, error, ... },
 *   bessStatus: { data, isLoading, error, ... },
 *   isLoading: boolean (any query loading),
 *   isError: boolean (any query error),
 * }
 *
 * @param siteId - Solar site identifier
 * @returns Object with all four query results
 */
export function useSolarDashboard(siteId: string) {
  const systemOverview = useSolarSystemOverview(siteId);
  const performance = useSolarPerformance(siteId);
  const gridCompliance = useGridCompliance(siteId);
  const bessStatus = useBESSStatus(siteId);

  return {
    systemOverview,
    performance,
    gridCompliance,
    bessStatus,
    isLoading:
      systemOverview.isLoading ||
      performance.isLoading ||
      gridCompliance.isLoading ||
      bessStatus.isLoading,
    isError:
      systemOverview.isError ||
      performance.isError ||
      gridCompliance.isError ||
      bessStatus.isError,
    error:
      systemOverview.error ||
      performance.error ||
      gridCompliance.error ||
      bessStatus.error,
  };
}

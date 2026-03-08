import { useQuery } from '@tanstack/react-query';
import {
  fetchBESSStatus,
  fetchInverters,
  fetchPerformance,
  fetchFinancialSummary,
} from '@/lib/solarApi';
// Types available from '@/lib/solarApi' if needed

/**
 * Hook to fetch BESS container status (SOC, mode, power, health)
 *
 * Caching:
 * - staleTime: 15s (dynamic data, frequently changing)
 * - gcTime: 5m
 *
 * @param siteId - Solar site identifier
 * @returns Query result with BESSStatus data
 */
export function useSolarBESS(siteId: string) {
  return useQuery({
    queryKey: ['solar-bess', siteId],
    queryFn: () => fetchBESSStatus(siteId),
    staleTime: 15 * 1000, // 15s
    gcTime: 5 * 60 * 1000, // 5m
    enabled: !!siteId,
  });
}

/**
 * Hook to fetch all inverters for a site with current readings
 *
 * Caching:
 * - staleTime: 30s (less frequently changing than BESS)
 * - gcTime: 5m
 *
 * @param siteId - Solar site identifier
 * @returns Query result with InverterListResponse data
 */
export function useSolarInverters(siteId: string) {
  return useQuery({
    queryKey: ['solar-inverters', siteId],
    queryFn: () => fetchInverters(siteId),
    staleTime: 30 * 1000, // 30s
    gcTime: 5 * 60 * 1000, // 5m
    enabled: !!siteId,
  });
}

/**
 * Hook to fetch performance metrics (PR, trends)
 *
 * Caching:
 * - staleTime: 60s (slower calculation, less volatile)
 * - gcTime: 5m
 *
 * @param siteId - Solar site identifier
 * @returns Query result with PerformanceMetrics data
 */
export function useSolarPerformance(siteId: string) {
  return useQuery({
    queryKey: ['solar-performance', siteId],
    queryFn: () => fetchPerformance(siteId),
    staleTime: 60 * 1000, // 60s
    gcTime: 5 * 60 * 1000, // 5m
    enabled: !!siteId,
  });
}

/**
 * Hook to fetch financial summary (savings breakdown, ROI)
 *
 * Caching:
 * - staleTime: 60s (less volatile than real-time data)
 * - gcTime: 5m
 *
 * @param siteId - Solar site identifier
 * @param period - Period for financial data (default: "ytd")
 * @returns Query result with FinancialSummary data
 */
export function useSolarFinancial(siteId: string, period: string = 'ytd') {
  return useQuery({
    queryKey: ['solar-financial', siteId, period],
    queryFn: () => fetchFinancialSummary(siteId, period),
    staleTime: 60 * 1000, // 60s
    gcTime: 5 * 60 * 1000, // 5m
    enabled: !!siteId,
  });
}

export { useSolarOverview } from './useSolarOverview';

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api/fetchClient';

/**
 * Alert item type
 */
export interface AlertItem {
  id: string;
  equipment_id: string;
  equipment_name: string;
  severity: string;
  description: string;
  created_at: string;
}

/**
 * Paginated alerts response
 */
export interface SiteAlerts {
  site_id: string;
  alerts: AlertItem[];
  total_count: number;
  offset: number;
  limit: number;
}

/**
 * Hook to fetch aggregated site alerts
 * Cache: 15s staleTime, refetchInterval: 30s
 */
export function useSiteAlerts(
  siteId: string,
  options?: { enabled?: boolean; offset?: number; limit?: number }
) {
  return useQuery({
    queryKey: ['site-alerts', siteId, options?.offset ?? 0, options?.limit ?? 50],
    queryFn: () =>
      apiFetch<SiteAlerts>(
        `/api/sites/${siteId}/alerts?offset=${options?.offset ?? 0}&limit=${options?.limit ?? 50}`
      ),
    staleTime: 15 * 1000, // 15s
    gcTime: 5 * 60 * 1000, // 5m
    refetchInterval: 30 * 1000, // 30s
    enabled: options?.enabled !== false,
  });
}

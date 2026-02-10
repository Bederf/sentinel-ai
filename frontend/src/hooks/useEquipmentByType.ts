import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api/fetchClient';
import type { Equipment } from '@/lib/api';

/**
 * Hook to fetch equipment filtered by type and site
 * Cache: 5m staleTime, 30m gcTime
 */
export function useEquipmentByType(
  siteId: string,
  type: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: ['equipment-by-type', siteId, type],
    queryFn: () =>
      apiFetch<Equipment[]>(
        `/api/equipment?site_id=${encodeURIComponent(siteId)}&type=${encodeURIComponent(type)}`
      ),
    staleTime: 5 * 60 * 1000, // 5m
    gcTime: 30 * 60 * 1000, // 30m
    enabled: options?.enabled !== false && !!siteId && !!type,
  });
}

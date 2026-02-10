import { useQuery } from '@tanstack/react-query';
import { safetyBatcher } from '@/lib/api/batchers';

/**
 * Hook to fetch safety status for a device
 * Uses batch aggregator to collect requests over 50ms window
 * Cache: 30s staleTime, 5m gcTime
 */
export function useDeviceSafetyStatus(
  deviceId: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: ['device-safety', deviceId],
    queryFn: async () => {
      return await safetyBatcher(deviceId);
    },
    staleTime: 30 * 1000, // 30s
    gcTime: 5 * 60 * 1000, // 5m
    enabled: options?.enabled !== false,
    retry: false,
  });
}

import { useQuery } from '@tanstack/react-query';
import { safetyBatcher } from '@/lib/api';
import type { DeviceSafetyStatus } from '@/lib/api/types';

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
      const result = await safetyBatcher.fetch(deviceId);
      return result;
    },
    staleTime: 30 * 1000, // 30s
    gcTime: 5 * 60 * 1000, // 5m
    enabled: options?.enabled !== false,
    retry: (failureCount) => {
      // Don't retry errors from batcher (they're per-item)
      return false;
    },
  });
}

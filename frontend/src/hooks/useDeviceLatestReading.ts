import { useQuery } from '@tanstack/react-query';
import { readingsBatcher } from '@/lib/api';
import type { DeviceStatus } from '@/lib/api/types';

/**
 * Hook to fetch latest reading for a device
 * Uses batch aggregator to collect requests over 50ms window
 * Cache: 15s staleTime, refetchInterval: 60s
 */
export function useDeviceLatestReading(
  deviceId: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: ['device-reading', deviceId],
    queryFn: async () => {
      const result = await readingsBatcher.fetch(deviceId);
      return result;
    },
    staleTime: 15 * 1000, // 15s
    gcTime: 5 * 60 * 1000, // 5m
    refetchInterval: 60 * 1000, // 60s
    enabled: options?.enabled !== false,
    retry: false,
  });
}

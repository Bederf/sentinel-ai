import { useQuery } from '@tanstack/react-query';
import { conditionBatcher } from '@/lib/api';

/**
 * Hook to fetch device condition/health status
 * Uses batch aggregator to collect requests over 50ms window
 * Cache: 30s staleTime, 5m gcTime
 */
export function useDeviceCondition(
  deviceId: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: ['device-condition', deviceId],
    queryFn: async () => {
      const result = await conditionBatcher.fetch(deviceId);
      return result;
    },
    staleTime: 30 * 1000, // 30s
    gcTime: 5 * 60 * 1000, // 5m
    enabled: options?.enabled !== false,
    retry: false,
  });
}

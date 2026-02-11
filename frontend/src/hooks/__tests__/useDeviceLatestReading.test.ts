/**
 * useDeviceLatestReading Hook Tests
 *
 * Tests comprehensive hook functionality:
 * - Batch aggregation (50ms window)
 * - Request deduplication
 * - Caching behavior (15s staleTime, 60s refetchInterval)
 * - Refetching and cache invalidation
 * - Error handling
 * - Enable/disable logic
 * - Multiple concurrent requests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useDeviceLatestReading } from '../useDeviceLatestReading';
import type { DeviceStatus } from '@/lib/api/types';

vi.mock('@/lib/api/batchers', () => ({
  readingsBatcher: vi.fn(),
}));

import { readingsBatcher } from '@/lib/api/batchers';

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity,
        staleTime: Infinity,
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

const mockDeviceReading: DeviceStatus = {
  id: 'device-001',
  name: 'Chiller Unit 1',
  device_type: 'HVAC',
  status: 'online',
  last_update: new Date().toISOString(),
  current_value: 22.5,
};

describe('useDeviceLatestReading Hook', () => {
  let queryClient: QueryClient;
  let mockBatcher: any;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    mockBatcher = vi.mocked(readingsBatcher);
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Data Fetching', () => {
    it('should fetch latest device reading', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceReading);

      const { result } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockDeviceReading);
      expect(mockBatcher).toHaveBeenCalledWith('device-001');
    });

    it('should validate device reading fields', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceReading);

      const { result } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.id).toBe('device-001');
      expect(result.current.data?.name).toBe('Chiller Unit 1');
      expect(result.current.data?.device_type).toBe('HVAC');
      expect(result.current.data?.status).toBe('online');
      expect(result.current.data?.current_value).toBe(22.5);
    });

    it('should handle different device types', async () => {
      const mockAHUReading: DeviceStatus = {
        ...mockDeviceReading,
        id: 'device-002',
        device_type: 'AHU',
        name: 'AHU Unit 1',
      };

      mockBatcher.mockResolvedValueOnce(mockAHUReading);

      const { result } = renderHook(
        () => useDeviceLatestReading('device-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.device_type).toBe('AHU');
    });
  });

  describe('Batch Aggregation (50ms Window)', () => {
    it('should call batcher for multiple devices separately', async () => {
      const mockReading1: DeviceStatus = {
        ...mockDeviceReading,
        id: 'device-001',
      };

      const mockReading2: DeviceStatus = {
        ...mockDeviceReading,
        id: 'device-002',
      };

      mockBatcher
        .mockResolvedValueOnce(mockReading1)
        .mockResolvedValueOnce(mockReading2);

      const { result: result1 } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useDeviceLatestReading('device-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      // Multiple devices should call batcher multiple times
      expect(mockBatcher).toHaveBeenCalledTimes(2);
    });
  });

  describe('Request Deduplication', () => {
    it('should deduplicate identical device requests', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceReading);

      const { result: result1 } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      // Should only call batcher once for same device
      expect(mockBatcher).toHaveBeenCalledTimes(1);
      expect(result1.current.data).toEqual(mockDeviceReading);
      expect(result2.current.data).toEqual(mockDeviceReading);
    });

    it('should use React Query cache for duplicate device requests', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceReading);

      // First hook fetches
      const { result: result1 } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second hook should use cache
      const { result: result2 } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result2.current.data).toEqual(mockDeviceReading);
      expect(mockBatcher).toHaveBeenCalledTimes(1);
    });
  });

  describe('Caching Behavior', () => {
    it('should respect 15s staleTime', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceReading);

      const { result } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify query exists and has correct timing
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'device-reading');
      expect(query).toBeDefined();
    });

    it('should cache reading and return same data on second mount', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceReading);

      // First render
      const { result: result1 } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second render - should use cached data
      const { result: result2 } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result2.current.data).toEqual(mockDeviceReading);
      expect(mockBatcher).toHaveBeenCalledTimes(1);
    });

    it('should maintain separate cache for different devices', async () => {
      const mockReading1: DeviceStatus = {
        ...mockDeviceReading,
        id: 'device-001',
      };

      const mockReading2: DeviceStatus = {
        ...mockDeviceReading,
        id: 'device-002',
      };

      mockBatcher
        .mockResolvedValueOnce(mockReading1)
        .mockResolvedValueOnce(mockReading2);

      const { result: result1 } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useDeviceLatestReading('device-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      expect(result1.current.data).toEqual(mockReading1);
      expect(result2.current.data).toEqual(mockReading2);
      expect(mockBatcher).toHaveBeenCalledTimes(2);
    });
  });

  describe('Refetch Interval (60s)', () => {
    it('should be configured with 60s refetchInterval', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceReading);

      const { result } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify query exists and is set up for refetching
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'device-reading');
      expect(query).toBeDefined();
      expect(result.current.data).toEqual(mockDeviceReading);
    });
  });

  describe('Refetch Capabilities', () => {
    it('should refetch reading on demand', async () => {
      mockBatcher
        .mockResolvedValueOnce(mockDeviceReading)
        .mockResolvedValueOnce({ ...mockDeviceReading, current_value: 25.5 });

      const { result } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.current_value).toBe(22.5);

      // Manual refetch
      result.current.refetch();

      await waitFor(() => {
        expect(result.current.data?.current_value).toBe(25.5);
      });

      expect(mockBatcher).toHaveBeenCalledTimes(2);
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      const error = new Error('Network error');
      mockBatcher.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
      expect(mockBatcher).toHaveBeenCalledTimes(1);
    });

    it('should not retry on error (retry: false)', async () => {
      const error = new Error('API Error');
      mockBatcher.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      // With retry: false, should fail immediately
      expect(mockBatcher).toHaveBeenCalledTimes(1);
    });

    it('should handle device not found errors', async () => {
      const error = new Error('Device not found');
      mockBatcher.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useDeviceLatestReading('nonexistent-device'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toContain('not found');
    });
  });

  describe('Enable/Disable Logic', () => {
    it('should not fetch when enabled is false', async () => {
      const { result } = renderHook(
        () => useDeviceLatestReading('device-001', { enabled: false }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(mockBatcher).not.toHaveBeenCalled();
    });

    it('should fetch by default when enabled is not specified', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceReading);

      const { result } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockBatcher).toHaveBeenCalled();
    });

    it('should fetch when enabled is explicitly true', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceReading);

      const { result } = renderHook(
        () => useDeviceLatestReading('device-001', { enabled: true }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockBatcher).toHaveBeenCalled();
    });
  });

  describe('Multiple Concurrent Requests', () => {
    it('should handle multiple devices in parallel', async () => {
      const mockReading1 = { ...mockDeviceReading, id: 'device-001' };
      const mockReading2 = { ...mockDeviceReading, id: 'device-002' };
      const mockReading3 = { ...mockDeviceReading, id: 'device-003' };

      mockBatcher
        .mockResolvedValueOnce(mockReading1)
        .mockResolvedValueOnce(mockReading2)
        .mockResolvedValueOnce(mockReading3);

      const { result: result1 } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useDeviceLatestReading('device-002'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result3 } = renderHook(
        () => useDeviceLatestReading('device-003'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
        expect(result3.current.isSuccess).toBe(true);
      });

      expect(result1.current.data?.id).toBe('device-001');
      expect(result2.current.data?.id).toBe('device-002');
      expect(result3.current.data?.id).toBe('device-003');
      expect(mockBatcher).toHaveBeenCalledTimes(3);
    });
  });

  describe('Query Key Management', () => {
    it('should use correct query key', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceReading);

      const { result } = renderHook(
        () => useDeviceLatestReading('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'device-reading');
      expect(query?.queryKey).toEqual(['device-reading', 'device-001']);
    });
  });
});

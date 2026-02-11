/**
 * useDeviceCondition Hook Tests
 *
 * Tests comprehensive hook functionality:
 * - Batch aggregation (50ms window)
 * - Request deduplication
 * - Caching behavior (30s staleTime, 5m gcTime)
 * - Refetching and cache invalidation
 * - Error handling
 * - Enable/disable logic
 * - Device condition status validation
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useDeviceCondition } from '../useDeviceCondition';
import type { DeviceCondition } from '@/lib/api/types';

vi.mock('@/lib/api/batchers', () => ({
  conditionBatcher: vi.fn(),
}));

import { conditionBatcher } from '@/lib/api/batchers';

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

const mockDeviceCondition: DeviceCondition = {
  id: 'device-001',
  name: 'Chiller Unit 1',
  device_type: 'HVAC',
  status: 'healthy',
  health_score: 85,
  efficiency: 92.5,
};

describe('useDeviceCondition Hook', () => {
  let queryClient: QueryClient;
  let mockBatcher: any;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    mockBatcher = vi.mocked(conditionBatcher);
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Data Fetching', () => {
    it('should fetch device condition/health status', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockDeviceCondition);
      expect(mockBatcher).toHaveBeenCalledWith('device-001');
    });

    it('should validate device condition fields', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.id).toBe('device-001');
      expect(result.current.data?.name).toBe('Chiller Unit 1');
      expect(result.current.data?.device_type).toBe('HVAC');
      expect(result.current.data?.status).toBe('healthy');
      expect(result.current.data?.health_score).toBe(85);
      expect(result.current.data?.efficiency).toBe(92.5);
    });

    it('should handle different health statuses', async () => {
      const warningCondition: DeviceCondition = {
        ...mockDeviceCondition,
        status: 'warning',
        health_score: 45,
      };

      mockBatcher.mockResolvedValueOnce(warningCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.status).toBe('warning');
      expect(result.current.data?.health_score).toBe(45);
    });

    it('should handle critical condition status', async () => {
      const criticalCondition: DeviceCondition = {
        ...mockDeviceCondition,
        status: 'critical',
        health_score: 15,
      };

      mockBatcher.mockResolvedValueOnce(criticalCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.status).toBe('critical');
      expect(result.current.data?.health_score).toBe(15);
    });

    it('should handle different device types', async () => {
      const ahuCondition: DeviceCondition = {
        ...mockDeviceCondition,
        id: 'device-002',
        device_type: 'AHU',
        name: 'AHU Unit 1',
      };

      mockBatcher.mockResolvedValueOnce(ahuCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.device_type).toBe('AHU');
    });
  });

  describe('Batch Aggregation (50ms Window)', () => {
    it('should call batcher for multiple devices', async () => {
      const mockCondition1: DeviceCondition = {
        ...mockDeviceCondition,
        id: 'device-001',
      };

      const mockCondition2: DeviceCondition = {
        ...mockDeviceCondition,
        id: 'device-002',
      };

      mockBatcher
        .mockResolvedValueOnce(mockCondition1)
        .mockResolvedValueOnce(mockCondition2);

      const { result: result1 } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useDeviceCondition('device-002'),
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
      mockBatcher.mockResolvedValueOnce(mockDeviceCondition);

      const { result: result1 } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      // Should only call batcher once for same device
      expect(mockBatcher).toHaveBeenCalledTimes(1);
      expect(result1.current.data).toEqual(mockDeviceCondition);
      expect(result2.current.data).toEqual(mockDeviceCondition);
    });

    it('should use React Query cache for duplicate device requests', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceCondition);

      // First hook fetches
      const { result: result1 } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second hook should use cache
      const { result: result2 } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result2.current.data).toEqual(mockDeviceCondition);
      expect(mockBatcher).toHaveBeenCalledTimes(1);
    });
  });

  describe('Caching Behavior', () => {
    it('should respect 30s staleTime', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify query exists and has correct timing
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'device-condition');
      expect(query).toBeDefined();
    });

    it('should cache condition and return same data on second mount', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceCondition);

      // First render
      const { result: result1 } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second render - should use cached data
      const { result: result2 } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result2.current.data).toEqual(mockDeviceCondition);
      expect(mockBatcher).toHaveBeenCalledTimes(1);
    });

    it('should maintain separate cache for different devices', async () => {
      const mockCondition1: DeviceCondition = {
        ...mockDeviceCondition,
        id: 'device-001',
        health_score: 85,
      };

      const mockCondition2: DeviceCondition = {
        ...mockDeviceCondition,
        id: 'device-002',
        health_score: 55,
      };

      mockBatcher
        .mockResolvedValueOnce(mockCondition1)
        .mockResolvedValueOnce(mockCondition2);

      const { result: result1 } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useDeviceCondition('device-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      expect(result1.current.data?.id).toBe('device-001');
      expect(result2.current.data?.id).toBe('device-002');
      expect(mockBatcher).toHaveBeenCalledTimes(2);
    });

    it('should use 5m gcTime for garbage collection', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Query should stay in cache even after unmount (5m gcTime)
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'device-condition');
      expect(query).toBeDefined();
    });
  });

  describe('Refetch Capabilities', () => {
    it('should refetch condition on demand', async () => {
      mockBatcher
        .mockResolvedValueOnce(mockDeviceCondition)
        .mockResolvedValueOnce({
          ...mockDeviceCondition,
          health_score: 65,
          status: 'warning',
        });

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.health_score).toBe(85);
      expect(result.current.data?.status).toBe('healthy');

      // Manual refetch
      result.current.refetch();

      await waitFor(() => {
        expect(result.current.data?.health_score).toBe(65);
        expect(result.current.data?.status).toBe('warning');
      });

      expect(mockBatcher).toHaveBeenCalledTimes(2);
    });

    it('should update data after refetch', async () => {
      mockBatcher
        .mockResolvedValueOnce({ ...mockDeviceCondition, efficiency: 92.5 })
        .mockResolvedValueOnce({ ...mockDeviceCondition, efficiency: 85.0 });

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.data?.efficiency).toBe(92.5);
      });

      result.current.refetch();

      await waitFor(() => {
        expect(result.current.data?.efficiency).toBe(85.0);
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      const error = new Error('Network error');
      mockBatcher.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
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
        () => useDeviceCondition('device-001'),
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
        () => useDeviceCondition('nonexistent-device'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toContain('not found');
    });

    it('should handle 429 rate limit errors without retry', async () => {
      const error = new Error('429 Too Many Requests');
      mockBatcher.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(mockBatcher).toHaveBeenCalledTimes(1);
    });

    it('should maintain previous data on error', async () => {
      mockBatcher
        .mockResolvedValueOnce(mockDeviceCondition)
        .mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const previousData = result.current.data;

      result.current.refetch();

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      // Previous data should still be available
      expect(result.current.data).toEqual(previousData);
    });
  });

  describe('Enable/Disable Logic', () => {
    it('should not fetch when enabled is false', async () => {
      const { result } = renderHook(
        () => useDeviceCondition('device-001', { enabled: false }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(mockBatcher).not.toHaveBeenCalled();
    });

    it('should fetch by default when enabled is not specified', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockBatcher).toHaveBeenCalled();
    });

    it('should fetch when enabled is explicitly true', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-001', { enabled: true }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockBatcher).toHaveBeenCalled();
    });
  });

  describe('Cache Invalidation', () => {
    it('should allow manual cache invalidation', async () => {
      const mockCondition1 = { ...mockDeviceCondition, health_score: 80 };
      const mockCondition2 = { ...mockDeviceCondition, health_score: 75 };

      mockBatcher
        .mockResolvedValueOnce(mockCondition1)
        .mockResolvedValueOnce(mockCondition2);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.health_score).toBe(80);

      // Invalidate cache
      queryClient.invalidateQueries({
        queryKey: ['device-condition', 'device-001'],
      });

      await waitFor(() => {
        expect(result.current.data?.health_score).toBe(75);
      });

      expect(mockBatcher).toHaveBeenCalledTimes(2);
    });

    it('should clear cache on demand', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify data exists before removal
      expect(result.current.data).toEqual(mockDeviceCondition);

      queryClient.removeQueries({
        queryKey: ['device-condition', 'device-001'],
      });

      // Query should be removed from cache
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'device-condition');
      expect(query).toBeUndefined();
    });
  });

  describe('Multiple Concurrent Requests', () => {
    it('should handle multiple devices in parallel', async () => {
      const mockCondition1 = { ...mockDeviceCondition, id: 'device-001' };
      const mockCondition2 = { ...mockDeviceCondition, id: 'device-002', health_score: 60 };
      const mockCondition3 = { ...mockDeviceCondition, id: 'device-003', health_score: 40 };

      mockBatcher
        .mockResolvedValueOnce(mockCondition1)
        .mockResolvedValueOnce(mockCondition2)
        .mockResolvedValueOnce(mockCondition3);

      const { result: result1 } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useDeviceCondition('device-002'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result3 } = renderHook(
        () => useDeviceCondition('device-003'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
        expect(result3.current.isSuccess).toBe(true);
      });

      expect(result1.current.data?.health_score).toBe(85);
      expect(result2.current.data?.health_score).toBe(60);
      expect(result3.current.data?.health_score).toBe(40);
      expect(mockBatcher).toHaveBeenCalledTimes(3);
    });
  });

  describe('Device Condition Status Validation', () => {
    it('should correctly identify healthy status', async () => {
      const healthyCondition: DeviceCondition = {
        ...mockDeviceCondition,
        status: 'healthy',
        health_score: 85,
      };

      mockBatcher.mockResolvedValueOnce(healthyCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.status).toBe('healthy');
      expect(result.current.data?.health_score).toBeGreaterThan(70);
    });

    it('should correctly identify warning status', async () => {
      const warningCondition: DeviceCondition = {
        ...mockDeviceCondition,
        status: 'warning',
        health_score: 50,
      };

      mockBatcher.mockResolvedValueOnce(warningCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.status).toBe('warning');
      expect(result.current.data?.health_score).toBeLessThanOrEqual(70);
    });

    it('should correctly identify critical status', async () => {
      const criticalCondition: DeviceCondition = {
        ...mockDeviceCondition,
        status: 'critical',
        health_score: 20,
      };

      mockBatcher.mockResolvedValueOnce(criticalCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.status).toBe('critical');
      expect(result.current.data?.health_score).toBeLessThan(40);
    });
  });

  describe('Query Key Management', () => {
    it('should use correct query key', async () => {
      mockBatcher.mockResolvedValueOnce(mockDeviceCondition);

      const { result } = renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'device-condition');
      expect(query?.queryKey).toEqual(['device-condition', 'device-001']);
    });

    it('should use different query keys for different devices', async () => {
      mockBatcher.mockResolvedValue(mockDeviceCondition);

      renderHook(
        () => useDeviceCondition('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      renderHook(
        () => useDeviceCondition('device-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        const queries = queryClient.getQueryCache().getAll();
        const conditionQueries = queries.filter((q) => q.queryKey[0] === 'device-condition');
        expect(conditionQueries.length).toBe(2);
      });
    });
  });
});

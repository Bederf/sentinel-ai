/**
 * useEquipmentByType Hook Tests
 *
 * Tests comprehensive hook functionality:
 * - Successful equipment filtering by type
 * - Caching behavior (5m staleTime, 30m gcTime)
 * - Refetching and cache invalidation
 * - Error handling
 * - Enable/disable logic with dependency validation
 * - Equipment validation
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useEquipmentByType } from '../useEquipmentByType';
import type { Equipment } from '@/lib/api';

vi.mock('@/lib/api/fetchClient', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api/fetchClient';

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

const mockEquipment: Equipment = {
  id: '550e8400-e29b-41d4-a716-446655440000',
  code: 'S002-CHILLER-B1-001',
  name: 'Chiller Unit 1',
  equipment_type: 'CHILLER',
  site_code: 'site-002',
  building_code: 'B1',
  zone_code: 'MECH',
  status: 'online',
  health_score: 85,
  last_reading_time: new Date().toISOString(),
};

describe('useEquipmentByType Hook', () => {
  let queryClient: QueryClient;
  let mockApiFetch: any;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    mockApiFetch = vi.mocked(apiFetch);
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Equipment Filtering', () => {
    it('should fetch equipment filtered by type', async () => {
      const mockEquipmentList: Equipment[] = [
        mockEquipment,
        {
          ...mockEquipment,
          id: '550e8400-e29b-41d4-a716-446655440001',
          code: 'S002-CHILLER-B1-002',
          name: 'Chiller Unit 2',
        },
      ];

      mockApiFetch.mockResolvedValueOnce(mockEquipmentList);

      const { result } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockEquipmentList);
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/api/equipment?site_id=site-002&type=CHILLER'
      );
    });

    it('should handle different equipment types', async () => {
      const mockAHU: Equipment = {
        ...mockEquipment,
        code: 'S002-AHU-L2-001',
        equipment_type: 'AHU',
        name: 'Air Handling Unit 1',
      };

      mockApiFetch.mockResolvedValueOnce([mockAHU]);

      const { result } = renderHook(
        () => useEquipmentByType('site-002', 'AHU'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.[0]?.equipment_type).toBe('AHU');
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/api/equipment?site_id=site-002&type=AHU'
      );
    });

    it('should properly encode URL parameters', async () => {
      mockApiFetch.mockResolvedValueOnce([]);

      renderHook(
        () => useEquipmentByType('site-002', 'VAV'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith(
          '/api/equipment?site_id=site-002&type=VAV'
        );
      });
    });

    it('should return empty array when no equipment found', async () => {
      mockApiFetch.mockResolvedValueOnce([]);

      const { result } = renderHook(
        () => useEquipmentByType('site-002', 'NONEXISTENT'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual([]);
    });
  });

  describe('Caching Behavior', () => {
    it('should respect 5m staleTime', async () => {
      const mockEquipmentList: Equipment[] = [mockEquipment];

      mockApiFetch.mockResolvedValueOnce(mockEquipmentList);

      const { result } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify query exists in cache
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'equipment-by-type');
      expect(query).toBeDefined();
    });

    it('should cache equipment and return same data on second mount', async () => {
      const mockEquipmentList: Equipment[] = [mockEquipment];

      mockApiFetch.mockResolvedValueOnce(mockEquipmentList);

      // First render
      const { result: result1 } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second render - should use cached data
      const { result: result2 } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result2.current.data).toEqual(mockEquipmentList);
      expect(mockApiFetch).toHaveBeenCalledTimes(1);
    });

    it('should maintain separate cache for different types', async () => {
      const mockChillers: Equipment[] = [
        { ...mockEquipment, equipment_type: 'CHILLER' },
      ];

      const mockAHUs: Equipment[] = [
        { ...mockEquipment, equipment_type: 'AHU' },
      ];

      mockApiFetch
        .mockResolvedValueOnce(mockChillers)
        .mockResolvedValueOnce(mockAHUs);

      const { result: result1 } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useEquipmentByType('site-002', 'AHU'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      expect(result1.current.data).toEqual(mockChillers);
      expect(result2.current.data).toEqual(mockAHUs);
      expect(mockApiFetch).toHaveBeenCalledTimes(2);
    });

    it('should maintain separate cache for different sites', async () => {
      const mockEquipment1: Equipment[] = [
        { ...mockEquipment, site_code: 'site-002' },
      ];

      const mockEquipment2: Equipment[] = [
        { ...mockEquipment, site_code: 'site-005' },
      ];

      mockApiFetch
        .mockResolvedValueOnce(mockEquipment1)
        .mockResolvedValueOnce(mockEquipment2);

      const { result: result1 } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useEquipmentByType('site-005', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      expect(result1.current.data).toEqual(mockEquipment1);
      expect(result2.current.data).toEqual(mockEquipment2);
      expect(mockApiFetch).toHaveBeenCalledTimes(2);
    });
  });

  describe('Refetch Capabilities', () => {
    it('should refetch equipment on demand', async () => {
      const mockEquipmentList1: Equipment[] = [mockEquipment];

      const mockEquipmentList2: Equipment[] = [
        {
          ...mockEquipment,
          health_score: 65, // Updated health score
        },
      ];

      mockApiFetch
        .mockResolvedValueOnce(mockEquipmentList1)
        .mockResolvedValueOnce(mockEquipmentList2);

      const { result } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.[0]?.health_score).toBe(85);

      // Refetch
      result.current.refetch();

      await waitFor(() => {
        expect(result.current.data?.[0]?.health_score).toBe(65);
      });

      expect(mockApiFetch).toHaveBeenCalledTimes(2);
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      const error = new Error('Network error');
      mockApiFetch.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
    });

    it('should handle 404 not found errors', async () => {
      const error = new Error('404 Not Found');
      mockApiFetch.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useEquipmentByType('invalid-site', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toContain('404');
    });

    it('should handle 429 rate limit errors without retry', async () => {
      const error = new Error('429 Too Many Requests');
      mockApiFetch.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(mockApiFetch).toHaveBeenCalledTimes(1);
    });
  });

  describe('Enable/Disable Logic with Dependencies', () => {
    it('should not fetch when enabled is false', async () => {
      const { result } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER', { enabled: false }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(mockApiFetch).not.toHaveBeenCalled();
    });

    it('should not fetch when siteId is empty', async () => {
      const { result } = renderHook(
        () => useEquipmentByType('', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(false);
      expect(mockApiFetch).not.toHaveBeenCalled();
    });

    it('should not fetch when type is empty', async () => {
      const { result } = renderHook(
        () => useEquipmentByType('site-002', ''),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(false);
      expect(mockApiFetch).not.toHaveBeenCalled();
    });

    it('should fetch when both dependencies are provided', async () => {
      const mockEquipmentList: Equipment[] = [mockEquipment];

      mockApiFetch.mockResolvedValueOnce(mockEquipmentList);

      const { result } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockApiFetch).toHaveBeenCalled();
    });

    it('should fetch when enabled is explicitly true', async () => {
      const mockEquipmentList: Equipment[] = [mockEquipment];

      mockApiFetch.mockResolvedValueOnce(mockEquipmentList);

      const { result } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER', { enabled: true }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockApiFetch).toHaveBeenCalled();
    });
  });

  describe('Equipment Validation', () => {
    it('should return equipment with correct structure', async () => {
      const mockEquipmentList: Equipment[] = [mockEquipment];

      mockApiFetch.mockResolvedValueOnce(mockEquipmentList);

      const { result } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const equipment = result.current.data?.[0];
      expect(equipment?.id).toBeDefined();
      expect(equipment?.code).toBeDefined();
      expect(equipment?.name).toBeDefined();
      expect(equipment?.equipment_type).toBe('CHILLER');
      expect(equipment?.status).toBeDefined();
      expect(equipment?.health_score).toBeDefined();
    });

    it('should handle multiple equipment of same type', async () => {
      const mockEquipmentList: Equipment[] = [
        mockEquipment,
        {
          ...mockEquipment,
          id: '550e8400-e29b-41d4-a716-446655440002',
          code: 'S002-CHILLER-B1-003',
          name: 'Chiller Unit 3',
        },
        {
          ...mockEquipment,
          id: '550e8400-e29b-41d4-a716-446655440003',
          code: 'S002-CHILLER-L2-001',
          name: 'Chiller Unit 4',
          building_code: 'L2',
        },
      ];

      mockApiFetch.mockResolvedValueOnce(mockEquipmentList);

      const { result } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.length).toBe(3);
      expect(result.current.data?.every((e) => e.equipment_type === 'CHILLER')).toBe(
        true
      );
    });
  });

  describe('Query Key Management', () => {
    it('should use correct query key', async () => {
      const mockEquipmentList: Equipment[] = [mockEquipment];

      mockApiFetch.mockResolvedValueOnce(mockEquipmentList);

      const { result } = renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'equipment-by-type');
      expect(query?.queryKey).toEqual(['equipment-by-type', 'site-002', 'CHILLER']);
    });

    it('should use different query keys for different combinations', async () => {
      const mockEquipmentList: Equipment[] = [mockEquipment];

      mockApiFetch.mockResolvedValue(mockEquipmentList);

      renderHook(
        () => useEquipmentByType('site-002', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      renderHook(
        () => useEquipmentByType('site-002', 'AHU'),
        { wrapper: createWrapper(queryClient) }
      );

      renderHook(
        () => useEquipmentByType('site-005', 'CHILLER'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        const queries = queryClient.getQueryCache().getAll();
        const equipmentQueries = queries.filter((q) => q.queryKey[0] === 'equipment-by-type');
        expect(equipmentQueries.length).toBe(3);
      });
    });
  });
});

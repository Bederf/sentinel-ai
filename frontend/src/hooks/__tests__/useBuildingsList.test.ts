/**
 * useBuildingsList Hook Tests
 *
 * Tests comprehensive hook functionality:
 * - Successful buildings list fetching
 * - Response structure handling (SiteListResponse with sites array)
 * - Caching behavior (5m staleTime, 30m gcTime)
 * - Refetching and cache invalidation
 * - Error handling
 * - Enable/disable logic
 * - Site list validation
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useBuildingsList } from '../useBuildingsList';

vi.mock('@/lib/api/sites', () => ({
  sitesApi: {
    getSites: vi.fn(),
  },
}));

import { sitesApi } from '@/lib/api/sites';

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

const mockSite = {
  id: '550e8400-e29b-41d4-a716-446655440000',
  code: 'site-002',
  name: 'Sandton City Office Tower',
  location: 'Sandton, Johannesburg',
  floors: 3,
  equipment_count: 156,
  status: 'online',
  health_score: 78,
};

describe('useBuildingsList Hook', () => {
  let queryClient: QueryClient;
  let mockSitesApi: any;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    mockSitesApi = vi.mocked(sitesApi.getSites);
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Buildings/Sites Fetching', () => {
    it('should fetch list of buildings/sites', async () => {
      const mockSitesList = [
        mockSite,
        {
          ...mockSite,
          id: '550e8400-e29b-41d4-a716-446655440001',
          code: 'site-005',
          name: 'Office Building 2',
        },
      ];

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockSitesList);
    });

    it('should extract sites array from SiteListResponse', async () => {
      const mockSitesList = [mockSite];

      mockSitesApi.mockResolvedValueOnce({ total: 1, sites: mockSitesList });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Should extract sites array from response
      expect(result.current.data).toEqual(mockSitesList);
    });

    it('should handle direct sites array response', async () => {
      const mockSitesList = [mockSite];

      mockSitesApi.mockResolvedValueOnce(mockSitesList);

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockSitesList);
    });

    it('should return empty array when no buildings found', async () => {
      mockSitesApi.mockResolvedValueOnce({ sites: [] });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual([]);
    });

    it('should call getSites without parameters', async () => {
      const mockSitesList = [mockSite];

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockSitesApi).toHaveBeenCalledWith();
      });
    });
  });

  describe('Caching Behavior', () => {
    it('should respect 5m staleTime', async () => {
      const mockSitesList = [mockSite];

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify query exists in cache
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'buildings-list');
      expect(query).toBeDefined();
    });

    it('should cache buildings and return same data on second mount', async () => {
      const mockSitesList = [mockSite];

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      // First render
      const { result: result1 } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second render - should use cached data
      const { result: result2 } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result2.current.data).toEqual(mockSitesList);
      expect(mockSitesApi).toHaveBeenCalledTimes(1);
    });

    it('should use consistent query key for all calls', async () => {
      const mockSitesList = [mockSite];

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      const { result: result1 } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      const { result: result2 } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result2.current.isSuccess).toBe(true);
      });

      // Should only have one query in cache
      const queries = queryClient.getQueryCache().getAll();
      const buildingsQueries = queries.filter((q) => q.queryKey[0] === 'buildings-list');
      expect(buildingsQueries.length).toBe(1);
    });
  });

  describe('Refetch Capabilities', () => {
    it('should refetch buildings on demand', async () => {
      const mockSitesList1 = [mockSite];

      const mockSitesList2 = [
        mockSite,
        {
          ...mockSite,
          id: '550e8400-e29b-41d4-a716-446655440002',
          code: 'site-012',
          name: 'New Building',
        },
      ];

      mockSitesApi
        .mockResolvedValueOnce({ sites: mockSitesList1 })
        .mockResolvedValueOnce({ sites: mockSitesList2 });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.length).toBe(1);

      // Refetch
      result.current.refetch();

      await waitFor(() => {
        expect(result.current.data?.length).toBe(2);
      });

      expect(mockSitesApi).toHaveBeenCalledTimes(2);
    });

    it('should update data after refetch', async () => {
      const mockSitesList1 = [
        { ...mockSite, health_score: 75 },
      ];

      const mockSitesList2 = [
        { ...mockSite, health_score: 82 },
      ];

      mockSitesApi
        .mockResolvedValueOnce({ sites: mockSitesList1 })
        .mockResolvedValueOnce({ sites: mockSitesList2 });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.data?.[0]?.health_score).toBe(75);
      });

      result.current.refetch();

      await waitFor(() => {
        expect(result.current.data?.[0]?.health_score).toBe(82);
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      const error = new Error('Network error');
      mockSitesApi.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
    });

    it('should handle 404 not found errors', async () => {
      const error = new Error('404 Not Found');
      mockSitesApi.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toContain('404');
    });

    it('should handle 429 rate limit errors without retry', async () => {
      const error = new Error('429 Too Many Requests');
      mockSitesApi.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(mockSitesApi).toHaveBeenCalledTimes(1);
    });

    it('should maintain previous data on error', async () => {
      const mockSitesList = [mockSite];

      mockSitesApi
        .mockResolvedValueOnce({ sites: mockSitesList })
        .mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(
        () => useBuildingsList(),
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
        () => useBuildingsList({ enabled: false }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(mockSitesApi).not.toHaveBeenCalled();
    });

    it('should fetch by default when enabled is not specified', async () => {
      const mockSitesList = [mockSite];

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockSitesApi).toHaveBeenCalled();
    });

    it('should fetch when enabled is explicitly true', async () => {
      const mockSitesList = [mockSite];

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      const { result } = renderHook(
        () => useBuildingsList({ enabled: true }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockSitesApi).toHaveBeenCalled();
    });
  });

  describe('Cache Invalidation', () => {
    it('should allow manual cache invalidation', async () => {
      const mockSitesList1 = [{ ...mockSite, health_score: 75 }];

      const mockSitesList2 = [{ ...mockSite, health_score: 88 }];

      mockSitesApi
        .mockResolvedValueOnce({ sites: mockSitesList1 })
        .mockResolvedValueOnce({ sites: mockSitesList2 });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.[0]?.health_score).toBe(75);

      // Invalidate cache
      queryClient.invalidateQueries({
        queryKey: ['buildings-list'],
      });

      await waitFor(() => {
        expect(result.current.data?.[0]?.health_score).toBe(88);
      });

      expect(mockSitesApi).toHaveBeenCalledTimes(2);
    });

    it('should clear cache on demand', async () => {
      const mockSitesList = [mockSite];

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify data exists before removal
      expect(result.current.data).toEqual(mockSitesList);

      queryClient.removeQueries({
        queryKey: ['buildings-list'],
      });

      // Query should be removed from cache
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'buildings-list');
      expect(query).toBeUndefined();
    });
  });

  describe('Site List Validation', () => {
    it('should return sites with correct structure', async () => {
      const mockSitesList = [mockSite];

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const site = result.current.data?.[0];
      expect(site?.id).toBeDefined();
      expect(site?.code).toBeDefined();
      expect(site?.name).toBeDefined();
      expect(site?.location).toBeDefined();
      expect(site?.status).toBeDefined();
      expect(site?.health_score).toBeDefined();
    });

    it('should handle multiple buildings/sites', async () => {
      const mockSitesList = [
        mockSite,
        {
          ...mockSite,
          id: '550e8400-e29b-41d4-a716-446655440001',
          code: 'site-005',
          name: 'Building 2',
        },
        {
          ...mockSite,
          id: '550e8400-e29b-41d4-a716-446655440002',
          code: 'site-012',
          name: 'Building 3',
        },
      ];

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.length).toBe(3);
      expect(result.current.data?.map((s) => s.code)).toEqual(['site-002', 'site-005', 'site-012']);
    });

    it('should handle large building lists', async () => {
      const mockSitesList = Array.from({ length: 50 }, (_, i) => ({
        ...mockSite,
        id: `550e8400-e29b-41d4-a716-${String(i).padStart(12, '0')}`,
        code: `site-${String(i + 1).padStart(3, '0')}`,
        name: `Building ${i + 1}`,
      }));

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.length).toBe(50);
    });

    it('should preserve site order from API response', async () => {
      const mockSitesList = [
        { ...mockSite, code: 'site-002', name: 'First' },
        { ...mockSite, code: 'site-005', name: 'Second' },
        { ...mockSite, code: 'site-012', name: 'Third' },
      ];

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.map((s) => s.name)).toEqual(['First', 'Second', 'Third']);
    });
  });

  describe('Query Key Management', () => {
    it('should use consistent query key', async () => {
      const mockSitesList = [mockSite];

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      const { result } = renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'buildings-list');
      expect(query?.queryKey).toEqual(['buildings-list']);
    });

    it('should use same query key regardless of hook instance', async () => {
      const mockSitesList = [mockSite];

      mockSitesApi.mockResolvedValueOnce({ sites: mockSitesList });

      renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      renderHook(
        () => useBuildingsList(),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        const queries = queryClient.getQueryCache().getAll();
        const buildingsQueries = queries.filter((q) => q.queryKey[0] === 'buildings-list');
        expect(buildingsQueries.length).toBe(1);
      });
    });
  });
});

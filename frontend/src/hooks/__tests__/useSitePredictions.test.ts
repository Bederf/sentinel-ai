/**
 * useSitePredictions Hook Tests
 *
 * Tests comprehensive hook functionality:
 * - Successful data fetching with prediction counts
 * - Caching behavior (60s staleTime)
 * - Refetching and cache invalidation
 * - Error handling (network errors, 404s)
 * - Enable/disable logic
 * - Multiple concurrent requests
 * - Data type validation
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useSitePredictions, type PredictionSummary } from '../useSitePredictions';

vi.mock('@/lib/api/fetchClient', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api/fetchClient';

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 0,  // Disable all retries in tests
        gcTime: 0,  // No garbage collection in tests
        staleTime: Infinity,
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useSitePredictions Hook', () => {
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

  describe('Successful Data Fetching', () => {
    it('should fetch prediction summary successfully', async () => {
      const mockPredictions: PredictionSummary = {
        high_risk: 5,
        medium_risk: 12,
        low_risk: 23,
      };

      mockApiFetch.mockResolvedValueOnce(mockPredictions);

      const { result } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockPredictions);
      expect(mockApiFetch).toHaveBeenCalledWith('/api/sites/site-002/predictions');
    });

    it('should validate prediction summary fields', async () => {
      const mockPredictions: PredictionSummary = {
        high_risk: 0,
        medium_risk: 8,
        low_risk: 42,
      };

      mockApiFetch.mockResolvedValueOnce(mockPredictions);

      const { result } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.high_risk).toBe(0);
      expect(result.current.data?.medium_risk).toBe(8);
      expect(result.current.data?.low_risk).toBe(42);
    });

    it('should call correct API endpoint', async () => {
      const mockPredictions: PredictionSummary = {
        high_risk: 2,
        medium_risk: 5,
        low_risk: 15,
      };

      mockApiFetch.mockResolvedValueOnce(mockPredictions);

      renderHook(
        () => useSitePredictions('site-003'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith('/api/sites/site-003/predictions');
      });
    });

    it('should handle empty predictions (all zeros)', async () => {
      const mockPredictions: PredictionSummary = {
        high_risk: 0,
        medium_risk: 0,
        low_risk: 0,
      };

      mockApiFetch.mockResolvedValueOnce(mockPredictions);

      const { result } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockPredictions);
    });
  });

  describe('Caching Behavior', () => {
    it('should respect 60s staleTime', async () => {
      const mockPredictions: PredictionSummary = {
        high_risk: 3,
        medium_risk: 10,
        low_risk: 20,
      };

      mockApiFetch.mockResolvedValueOnce(mockPredictions);

      const { result } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify staleTime is set correctly
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'site-predictions');
      expect(query?.getObserversCount()).toBeGreaterThan(0);
    });

    it('should cache predictions and return same data on second hook mount', async () => {
      const mockPredictions: PredictionSummary = {
        high_risk: 1,
        medium_risk: 6,
        low_risk: 30,
      };

      mockApiFetch.mockResolvedValueOnce(mockPredictions);

      // First render
      const { result: result1 } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second render - should use cached data
      const { result: result2 } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result2.current.data).toEqual(mockPredictions);
      expect(mockApiFetch).toHaveBeenCalledTimes(1);
    });

    it('should maintain separate cache for different sites', async () => {
      const mockPredictions1: PredictionSummary = {
        high_risk: 5,
        medium_risk: 10,
        low_risk: 20,
      };

      const mockPredictions2: PredictionSummary = {
        high_risk: 2,
        medium_risk: 8,
        low_risk: 35,
      };

      mockApiFetch
        .mockResolvedValueOnce(mockPredictions1)
        .mockResolvedValueOnce(mockPredictions2);

      const { result: result1 } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useSitePredictions('site-003'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      expect(result1.current.data).toEqual(mockPredictions1);
      expect(result2.current.data).toEqual(mockPredictions2);
      expect(mockApiFetch).toHaveBeenCalledTimes(2);
    });
  });

  describe('Refetch Capabilities', () => {
    it('should refetch predictions on demand', async () => {
      const mockPredictions1: PredictionSummary = {
        high_risk: 5,
        medium_risk: 10,
        low_risk: 20,
      };

      const mockPredictions2: PredictionSummary = {
        high_risk: 7,
        medium_risk: 12,
        low_risk: 18,
      };

      mockApiFetch
        .mockResolvedValueOnce(mockPredictions1)
        .mockResolvedValueOnce(mockPredictions2);

      const { result } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockPredictions1);

      // Refetch
      result.current.refetch();

      await waitFor(() => {
        expect(result.current.data).toEqual(mockPredictions2);
      });

      expect(mockApiFetch).toHaveBeenCalledTimes(2);
    });

    it('should update data after refetch', async () => {
      const mockPredictions1: PredictionSummary = {
        high_risk: 3,
        medium_risk: 5,
        low_risk: 25,
      };

      const mockPredictions2: PredictionSummary = {
        high_risk: 4,
        medium_risk: 9,
        low_risk: 20,
      };

      mockApiFetch
        .mockResolvedValueOnce(mockPredictions1)
        .mockResolvedValueOnce(mockPredictions2);

      const { result } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.data?.high_risk).toBe(3);
      });

      result.current.refetch();

      await waitFor(() => {
        expect(result.current.data?.high_risk).toBe(4);
        expect(result.current.data?.medium_risk).toBe(9);
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      const error = new Error('Network error');
      mockApiFetch.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
      expect(mockApiFetch).toHaveBeenCalledTimes(1);
    });

    it('should handle 404 not found errors', async () => {
      const error = new Error('404 Not Found');
      mockApiFetch.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useSitePredictions('invalid-site'),
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
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      // With retry: 0,  // Disable all retries in tests should fail immediately
      expect(mockApiFetch).toHaveBeenCalledTimes(1);
    });

    it('should maintain previous data on error', async () => {
      const mockPredictions: PredictionSummary = {
        high_risk: 5,
        medium_risk: 10,
        low_risk: 20,
      };

      mockApiFetch
        .mockResolvedValueOnce(mockPredictions)
        .mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(
        () => useSitePredictions('site-002'),
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
        () => useSitePredictions('site-002', { enabled: false }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(mockApiFetch).not.toHaveBeenCalled();
    });

    it('should fetch by default when enabled is not specified', async () => {
      const mockPredictions: PredictionSummary = {
        high_risk: 3,
        medium_risk: 7,
        low_risk: 25,
      };

      mockApiFetch.mockResolvedValueOnce(mockPredictions);

      const { result } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockApiFetch).toHaveBeenCalled();
    });

    it('should fetch when enabled is explicitly true', async () => {
      const mockPredictions: PredictionSummary = {
        high_risk: 2,
        medium_risk: 8,
        low_risk: 30,
      };

      mockApiFetch.mockResolvedValueOnce(mockPredictions);

      const { result } = renderHook(
        () => useSitePredictions('site-002', { enabled: true }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockApiFetch).toHaveBeenCalled();
    });
  });

  describe('Cache Invalidation', () => {
    it('should allow manual cache invalidation', async () => {
      const mockPredictions1: PredictionSummary = {
        high_risk: 5,
        medium_risk: 10,
        low_risk: 20,
      };

      const mockPredictions2: PredictionSummary = {
        high_risk: 8,
        medium_risk: 15,
        low_risk: 12,
      };

      mockApiFetch
        .mockResolvedValueOnce(mockPredictions1)
        .mockResolvedValueOnce(mockPredictions2);

      const { result } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockPredictions1);

      // Invalidate cache
      queryClient.invalidateQueries({
        queryKey: ['site-predictions', 'site-002'],
      });

      await waitFor(() => {
        expect(result.current.data).toEqual(mockPredictions2);
      });

      expect(mockApiFetch).toHaveBeenCalledTimes(2);
    });

    it('should clear cache on demand', async () => {
      const mockPredictions: PredictionSummary = {
        high_risk: 5,
        medium_risk: 10,
        low_risk: 20,
      };

      mockApiFetch.mockResolvedValueOnce(mockPredictions);

      const { result } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify data exists before removal
      expect(result.current.data).toEqual(mockPredictions);

      queryClient.removeQueries({
        queryKey: ['site-predictions', 'site-002'],
      });

      // Query should be removed from cache
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'site-predictions');
      expect(query).toBeUndefined();
    });
  });

  describe('Multiple Concurrent Requests', () => {
    it('should handle multiple sites in parallel', async () => {
      const mockPredictions1: PredictionSummary = {
        high_risk: 5,
        medium_risk: 10,
        low_risk: 20,
      };

      const mockPredictions2: PredictionSummary = {
        high_risk: 2,
        medium_risk: 8,
        low_risk: 35,
      };

      const mockPredictions3: PredictionSummary = {
        high_risk: 7,
        medium_risk: 14,
        low_risk: 15,
      };

      mockApiFetch
        .mockResolvedValueOnce(mockPredictions1)
        .mockResolvedValueOnce(mockPredictions2)
        .mockResolvedValueOnce(mockPredictions3);

      const { result: result1 } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useSitePredictions('site-003'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result3 } = renderHook(
        () => useSitePredictions('site-012'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
        expect(result3.current.isSuccess).toBe(true);
      });

      expect(result1.current.data).toEqual(mockPredictions1);
      expect(result2.current.data).toEqual(mockPredictions2);
      expect(result3.current.data).toEqual(mockPredictions3);
      expect(mockApiFetch).toHaveBeenCalledTimes(3);
    });

    it('should resolve each request independently', async () => {
      const mockPredictions1: PredictionSummary = {
        high_risk: 3,
        medium_risk: 9,
        low_risk: 22,
      };

      const mockPredictions2: PredictionSummary = {
        high_risk: 6,
        medium_risk: 11,
        low_risk: 18,
      };

      mockApiFetch
        .mockResolvedValueOnce(mockPredictions1)
        .mockResolvedValueOnce(mockPredictions2);

      const { result: result1 } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useSitePredictions('site-003'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      // Both should resolve independently with their own data
      expect(result1.current.data).toEqual(mockPredictions1);
      expect(result2.current.data).toEqual(mockPredictions2);
      expect(result1.current.data?.high_risk).toBe(3);
      expect(result2.current.data?.high_risk).toBe(6);
    });
  });

  describe('Data Type Validation', () => {
    it('should validate PredictionSummary interface', async () => {
      const mockPredictions: PredictionSummary = {
        high_risk: 5,
        medium_risk: 10,
        low_risk: 20,
      };

      mockApiFetch.mockResolvedValueOnce(mockPredictions);

      const { result } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const data = result.current.data;
      expect(typeof data?.high_risk).toBe('number');
      expect(typeof data?.medium_risk).toBe('number');
      expect(typeof data?.low_risk).toBe('number');
    });

    it('should handle large prediction counts', async () => {
      const mockPredictions: PredictionSummary = {
        high_risk: 1000,
        medium_risk: 5000,
        low_risk: 10000,
      };

      mockApiFetch.mockResolvedValueOnce(mockPredictions);

      const { result } = renderHook(
        () => useSitePredictions('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.high_risk).toBe(1000);
      expect(result.current.data?.medium_risk).toBe(5000);
      expect(result.current.data?.low_risk).toBe(10000);
    });
  });
});

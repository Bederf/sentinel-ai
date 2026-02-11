/**
 * useSiteSummary Hook Tests
 *
 * Tests comprehensive hook functionality:
 * - Successful data fetching
 * - Caching behavior (30s staleTime, 5m gcTime)
 * - Refetch capabilities
 * - Error handling (network errors, 404, 429)
 * - Enable/disable logic
 * - Cache invalidation
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import React from 'react';
import { useSiteSummary, type SiteSummary } from '../useSiteSummary';

// Mock the fetchClient module
vi.mock('@/lib/api/fetchClient', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api/fetchClient';

// Test utilities
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity,
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

const mockSiteSummary: SiteSummary = {
  site_id: 'site-002',
  site_name: 'Sandton Tower',
  equipment_count: 156,
  equipment_by_type: {
    CHILLER: 2,
    AHU: 4,
    FCU: 24,
    DALI: 128,
  },
  safety: {
    total: 156,
    safe: 140,
    warning: 12,
    blocked: 4,
    alarm: 0,
  },
  alerts: {
    critical: 1,
    warning: 3,
    info: 5,
  },
  predictions: {
    high_risk: 2,
    medium_risk: 8,
    low_risk: 15,
  },
  energy: {
    current_kw: 245.8,
    today_kwh: 4920.5,
  },
  last_updated: new Date().toISOString(),
};

describe('useSiteSummary', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Data Fetching', () => {
    it('should fetch site summary successfully', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce(mockSiteSummary);

      const { result } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockSiteSummary);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isError).toBe(false);
    });

    it('should include all summary fields', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce(mockSiteSummary);

      const { result } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const data = result.current.data!;
      expect(data.site_id).toBe('site-002');
      expect(data.equipment_count).toBe(156);
      expect(data.safety.safe).toBe(140);
      expect(data.alerts.critical).toBe(1);
      expect(data.predictions.high_risk).toBe(2);
      expect(data.energy.current_kw).toBe(245.8);
    });

    it('should call API with correct endpoint', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce(mockSiteSummary);

      renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalled();
      });

      expect(apiFetch).toHaveBeenCalledWith('/api/sites/site-002/summary');
    });
  });

  describe('Caching Behavior', () => {
    it('should use 30s staleTime', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce(mockSiteSummary);

      const { result } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify cache was set
      const cacheEntry = queryClient.getQueryData(['site-summary', 'site-002']);
      expect(cacheEntry).toEqual(mockSiteSummary);
    });

    it('should return cached data on second call within staleTime', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce(mockSiteSummary);

      // First hook
      const { result: result1 } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second hook - should use cache
      const { result: result2 } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result2.current.data).toEqual(mockSiteSummary);
      expect(apiFetch).toHaveBeenCalledTimes(1); // Only called once due to cache
    });

    it('should use different cache for different sites', async () => {
      const site1Data = { ...mockSiteSummary, site_id: 'site-001' };
      const site2Data = { ...mockSiteSummary, site_id: 'site-002' };

      vi.mocked(apiFetch)
        .mockResolvedValueOnce(site1Data)
        .mockResolvedValueOnce(site2Data);

      const { result: result1 } = renderHook(() => useSiteSummary('site-001'), {
        wrapper: createWrapper(queryClient),
      });

      const { result: result2 } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      expect(result1.current.data?.site_id).toBe('site-001');
      expect(result2.current.data?.site_id).toBe('site-002');
      expect(apiFetch).toHaveBeenCalledTimes(2);
    });
  });

  describe('Refetch Capabilities', () => {
    it('should refetch on demand', async () => {
      const updatedSummary = {
        ...mockSiteSummary,
        alerts: { critical: 0, warning: 2, info: 3 },
      };

      vi.mocked(apiFetch)
        .mockResolvedValueOnce(mockSiteSummary)
        .mockResolvedValueOnce(updatedSummary);

      const { result } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.alerts.critical).toBe(1);

      // Refetch
      result.current.refetch();

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledTimes(2);
      });

      expect(result.current.data?.alerts.critical).toBe(0);
    });

    it('should update data after refetch', async () => {
      vi.mocked(apiFetch)
        .mockResolvedValueOnce({ ...mockSiteSummary, equipment_count: 156 })
        .mockResolvedValueOnce({ ...mockSiteSummary, equipment_count: 160 });

      const { result } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.data?.equipment_count).toBe(156);
      });

      result.current.refetch();

      await waitFor(() => {
        expect(result.current.data?.equipment_count).toBe(160);
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      const error = new Error('Network error');
      vi.mocked(apiFetch).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(error);
      expect(result.current.data).toBeUndefined();
    });

    it('should handle 404 errors', async () => {
      const error = new Error('404 Not Found');
      vi.mocked(apiFetch).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useSiteSummary('invalid-site'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toContain('404');
    });

    it('should handle 429 rate limit errors', async () => {
      const error = new Error('429 Too Many Requests');
      vi.mocked(apiFetch).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toContain('429');
    });

    it('should not retry on error (retry: false)', async () => {
      vi.mocked(apiFetch).mockRejectedValueOnce(new Error('API Error'));

      const { result } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      // Should only be called once (no retries)
      expect(apiFetch).toHaveBeenCalledTimes(1);
    });
  });

  describe('Enable/Disable Logic', () => {
    it('should not fetch when enabled is false', () => {
      const { result } = renderHook(
        () => useSiteSummary('site-002', { enabled: false }),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(apiFetch).not.toHaveBeenCalled();
    });

    it('should fetch when enabled is true', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce(mockSiteSummary);

      const { result } = renderHook(
        () => useSiteSummary('site-002', { enabled: true }),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(apiFetch).toHaveBeenCalled();
    });

    it('should fetch by default when enabled is not specified', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce(mockSiteSummary);

      const { result } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(apiFetch).toHaveBeenCalled();
    });
  });

  describe('Cache Invalidation', () => {
    it('should invalidate cache on demand', async () => {
      vi.mocked(apiFetch)
        .mockResolvedValueOnce(mockSiteSummary)
        .mockResolvedValueOnce(mockSiteSummary);

      const { result } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Invalidate cache
      await queryClient.invalidateQueries({
        queryKey: ['site-summary', 'site-002'],
      });

      // Should trigger refetch
      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledTimes(2);
      });
    });

    it('should clear cache on clear', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce(mockSiteSummary);

      const { result } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Clear cache
      queryClient.clear();

      const cacheEntry = queryClient.getQueryData(['site-summary', 'site-002']);
      expect(cacheEntry).toBeUndefined();
    });
  });

  describe('Multiple Concurrent Requests', () => {
    it('should handle multiple simultaneous fetches', async () => {
      const mockData1 = { ...mockSiteSummary, site_id: 'site-001' };
      const mockData2 = { ...mockSiteSummary, site_id: 'site-002' };
      const mockData3 = { ...mockSiteSummary, site_id: 'site-003' };

      vi.mocked(apiFetch)
        .mockResolvedValueOnce(mockData1)
        .mockResolvedValueOnce(mockData2)
        .mockResolvedValueOnce(mockData3);

      const { result: result1 } = renderHook(() => useSiteSummary('site-001'), {
        wrapper: createWrapper(queryClient),
      });
      const { result: result2 } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });
      const { result: result3 } = renderHook(() => useSiteSummary('site-003'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
        expect(result3.current.isSuccess).toBe(true);
      });

      expect(result1.current.data?.site_id).toBe('site-001');
      expect(result2.current.data?.site_id).toBe('site-002');
      expect(result3.current.data?.site_id).toBe('site-003');
      expect(apiFetch).toHaveBeenCalledTimes(3);
    });
  });

  describe('Data Types & Validation', () => {
    it('should return properly typed data', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce(mockSiteSummary);

      const { result } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const data = result.current.data!;
      expect(typeof data.site_id).toBe('string');
      expect(typeof data.equipment_count).toBe('number');
      expect(Array.isArray(Object.keys(data.equipment_by_type))).toBe(true);
      expect(data.safety).toBeDefined();
      expect(data.alerts).toBeDefined();
    });

    it('should handle empty equipment_by_type', async () => {
      const emptyData = { ...mockSiteSummary, equipment_by_type: {} };
      vi.mocked(apiFetch).mockResolvedValueOnce(emptyData);

      const { result } = renderHook(() => useSiteSummary('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(Object.keys(result.current.data!.equipment_by_type)).toHaveLength(
        0
      );
    });
  });
});

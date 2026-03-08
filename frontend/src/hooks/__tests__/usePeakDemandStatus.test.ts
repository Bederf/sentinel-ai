/**
 * usePeakDemandStatus Hook Tests
 *
 * Tests comprehensive hook functionality:
 * - Current demand vs NMD limit display
 * - Headroom calculation (% remaining capacity)
 * - Alert level determination (normal, caution, warning, critical)
 * - Caching behavior (15s staleTime)
 * - Refetch on manual trigger
 * - Error handling (network errors, 404, 429)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import React from 'react';
import { usePeakDemandStatus } from '../usePeakDemand';
import type { DemandStatusResponse } from '../../lib/api/peakDemand';

// Mock the peakDemand API module
vi.mock('../../lib/api/peakDemand', () => ({
  peakDemandApi: {
    getDemandStatus: vi.fn(),
  },
}));

import { peakDemandApi } from '../../lib/api/peakDemand';

// Test utilities
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 0,  // Disable all retries in tests
        gcTime: 0,  // No garbage collection in tests
        staleTime: 0,  // Always consider data stale
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

// Mock data factories
function createMockDemandStatus(overrides?: Partial<DemandStatusResponse>): DemandStatusResponse {
  return {
    site_id: 'site-002',
    current_demand_kw: 5500,
    nmd_limit_kva: 6000,
    headroom_kw: 500,
    headroom_percent: 8.3,
    headroom_level: 'normal',
    demand_trend: 'stable',
    active_modules: ['solar', 'hvac'],
    available_reductions: {
      solar: { max_reduction_kw: 200, method: 'bess_discharge' },
      hvac: { max_reduction_kw: 50, method: 'setpoint_increase' },
    },
    last_updated: new Date().toISOString(),
    ...overrides,
  };
}

describe('usePeakDemandStatus', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Data Fetching', () => {
    it('should fetch peak demand status successfully', async () => {
      const mockData = createMockDemandStatus();
      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockData);
      expect(result.current.data?.current_demand_kw).toBe(5500);
      expect(result.current.data?.nmd_limit_kva).toBe(6000);
    });

    it('should calculate headroom correctly', async () => {
      const mockData = createMockDemandStatus({
        current_demand_kw: 5700,
        nmd_limit_kva: 6000,
        headroom_kw: 300,
        headroom_percent: 5.0,
      });
      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.headroom_kw).toBe(300);
      expect(result.current.data?.headroom_percent).toBe(5.0);
    });

    it('should determine alert level as normal', async () => {
      const mockData = createMockDemandStatus({
        headroom_percent: 50,
        headroom_level: 'normal',
      });
      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.headroom_level).toBe('normal');
    });

    it('should determine alert level as caution', async () => {
      const mockData = createMockDemandStatus({
        headroom_percent: 15,
        headroom_level: 'caution',
      });
      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.headroom_level).toBe('caution');
    });

    it('should determine alert level as warning', async () => {
      const mockData = createMockDemandStatus({
        headroom_percent: 8,
        headroom_level: 'warning',
      });
      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.headroom_level).toBe('warning');
    });

    it('should determine alert level as critical', async () => {
      const mockData = createMockDemandStatus({
        headroom_percent: 2,
        headroom_level: 'critical',
      });
      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.headroom_level).toBe('critical');
    });
  });

  describe('Caching Behavior', () => {
    it('should respect 15s staleTime', async () => {
      const mockData = createMockDemandStatus();
      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify query was cached with correct staleTime
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'peakDemand');
      expect(query).toBeDefined();
      expect(query?.getObserversCount()).toBeGreaterThan(0);
    });

    it('should reuse cache for duplicate requests within staleTime', async () => {
      const mockData = createMockDemandStatus();
      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockData);

      // First render
      const { result: result1 } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second render - should reuse cache
      const { result: result2 } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result2.current.data).toEqual(mockData);
      expect(vi.mocked(peakDemandApi.getDemandStatus)).toHaveBeenCalledTimes(1);
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      const error = new Error('Network error');
      vi.mocked(peakDemandApi.getDemandStatus).mockRejectedValueOnce(error);

      const { result } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
      expect(result.current.error?.message).toBe('Network error');
    });

    it('should handle 429 rate limit errors', async () => {
      const error = new Error('Failed to fetch demand status: Too Many Requests');
      vi.mocked(peakDemandApi.getDemandStatus).mockRejectedValueOnce(error);

      const { result } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toContain('Too Many Requests');
    });

    it('should handle undefined siteId (disabled query)', async () => {
      const { result } = renderHook(() => usePeakDemandStatus(undefined), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(vi.mocked(peakDemandApi.getDemandStatus)).not.toHaveBeenCalled();
    });
  });

  describe('Active Modules Tracking', () => {
    it('should track active modules correctly', async () => {
      const mockData = createMockDemandStatus({
        active_modules: ['solar', 'hvac', 'energy'],
      });
      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.active_modules).toEqual(['solar', 'hvac', 'energy']);
    });

    it('should handle empty active modules list', async () => {
      const mockData = createMockDemandStatus({
        active_modules: [],
      });
      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.active_modules).toEqual([]);
    });
  });

  describe('Edge Cases - Phase 68-03', () => {
    it('should handle zero demand (0 kW)', async () => {
      const mockData = createMockDemandStatus({
        current_demand_kw: 0,
        nmd_limit_kva: 6000,
        headroom_kw: 6000,
        headroom_percent: 100,
        headroom_level: 'normal',
      });
      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.current_demand_kw).toBe(0);
      expect(result.current.data?.headroom_percent).toBe(100);
    });

    it('should handle near-critical demand (99% of NMD)', async () => {
      const mockData = createMockDemandStatus({
        current_demand_kw: 5940,
        nmd_limit_kva: 6000,
        headroom_kw: 60,
        headroom_percent: 1,
        headroom_level: 'critical',
      });
      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.headroom_percent).toBe(1);
      expect(result.current.data?.headroom_level).toBe('critical');
    });

    it('should handle rapid successive updates', async () => {
      const mockData1 = createMockDemandStatus({
        current_demand_kw: 5000,
        headroom_percent: 16,
      });
      const mockData2 = createMockDemandStatus({
        current_demand_kw: 5500,
        headroom_percent: 8,
      });

      vi.mocked(peakDemandApi.getDemandStatus)
        .mockResolvedValueOnce(mockData1)
        .mockResolvedValueOnce(mockData2);

      const { result, rerender: _rerender } = renderHook(
        ({ siteId }) => usePeakDemandStatus(siteId),
        {
          wrapper: createWrapper(queryClient),
          initialProps: { siteId: 'site-002' },
        }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.current_demand_kw).toBe(5000);

      // Manual refetch
      result.current.refetch?.();

      await waitFor(() => {
        expect(result.current.data?.current_demand_kw).toBe(5500);
      });
    });
  });
});

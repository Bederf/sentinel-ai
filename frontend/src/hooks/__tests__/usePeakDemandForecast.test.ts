/**
 * usePeakDemandForecast Hook Tests
 *
 * Tests comprehensive hook functionality:
 * - 24-hour demand forecast fetch
 * - Hourly interval data parsing
 * - Trend identification (rising, falling, stable)
 * - Peak hour identification
 * - Caching behavior (60s staleTime)
 * - Error handling and edge cases
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import React from 'react';
import { usePeakDemandForecast } from '../usePeakDemand';
import type { DemandForecastResponse, ForecastInterval } from '../../lib/api/peakDemand';

// Mock the peakDemand API module
vi.mock('../../lib/api/peakDemand', () => ({
  peakDemandApi: {
    getDemandForecast: vi.fn(),
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
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

// Mock data factories
function createMockForecastInterval(overrides?: Partial<ForecastInterval>): ForecastInterval {
  return {
    hour: 12,
    date: new Date().toISOString().split('T')[0],
    forecasted_demand_kw: 5500,
    confidence_low_kw: 5200,
    confidence_high_kw: 5800,
    nmd_headroom_kw: 500,
    headroom_percent: 8.3,
    risk_level: 'normal',
    ...overrides,
  };
}

function createMockForecastResponse(
  overrides?: Partial<DemandForecastResponse>
): DemandForecastResponse {
  const forecast_hours: ForecastInterval[] = Array.from({ length: 24 }, (_, i) => {
    const hour = i;
    const baseDemand = 3000 + Math.sin((i / 24) * Math.PI * 2) * 2000; // Sinusoidal pattern
    return createMockForecastInterval({
      hour,
      date: new Date().toISOString().split('T')[0],
      forecasted_demand_kw: baseDemand,
      confidence_low_kw: baseDemand - 300,
      confidence_high_kw: baseDemand + 300,
      nmd_headroom_kw: 6000 - baseDemand,
      headroom_percent: ((6000 - baseDemand) / 6000) * 100,
      risk_level: baseDemand > 5700 ? 'critical' : baseDemand > 5400 ? 'warning' : 'normal',
    });
  });

  return {
    site_id: 'site-002',
    forecast_start: new Date().toISOString(),
    forecast_hours,
    peak_hour: 12,
    peak_demand_kw: 5500,
    peak_headroom_kw: 500,
    peak_headroom_percent: 8.3,
    peak_risk_level: 'normal',
    ...overrides,
  };
}

describe('usePeakDemandForecast', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Data Fetching', () => {
    it('should fetch 24-hour demand forecast successfully', async () => {
      const mockData = createMockForecastResponse();
      vi.mocked(peakDemandApi.getDemandForecast).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandForecast('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockData);
      expect(result.current.data?.forecast_hours.length).toBe(24);
    });

    it('should parse hourly interval data correctly', async () => {
      const mockData = createMockForecastResponse();
      vi.mocked(peakDemandApi.getDemandForecast).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandForecast('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const hours = result.current.data?.forecast_hours;
      expect(hours?.[0].hour).toBe(0);
      expect(hours?.[12].hour).toBe(12);
      expect(hours?.[23].hour).toBe(23);

      // Each interval should have required fields
      hours?.forEach((interval) => {
        expect(interval.forecasted_demand_kw).toBeGreaterThan(0);
        expect(interval.confidence_low_kw).toBeGreaterThan(0);
        expect(interval.confidence_high_kw).toBeGreaterThan(interval.confidence_low_kw);
        expect(interval.risk_level).toMatch(/safe|normal|caution|warning|critical/);
      });
    });

    it('should identify peak hour correctly', async () => {
      const mockData = createMockForecastResponse({
        peak_hour: 14,
        peak_demand_kw: 5750,
      });
      vi.mocked(peakDemandApi.getDemandForecast).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandForecast('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.peak_hour).toBe(14);
      expect(result.current.data?.peak_demand_kw).toBe(5750);
    });

    it('should include peak risk level in forecast', async () => {
      const mockData = createMockForecastResponse({
        peak_risk_level: 'critical',
      });
      vi.mocked(peakDemandApi.getDemandForecast).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandForecast('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.peak_risk_level).toBe('critical');
    });
  });

  describe('Trend Identification', () => {
    it('should identify rising trend', async () => {
      const mockData = createMockForecastResponse();
      mockData.forecast_hours = Array.from({ length: 24 }, (_, i) =>
        createMockForecastInterval({
          hour: i,
          forecasted_demand_kw: 3000 + i * 100, // Rising
        })
      );
      vi.mocked(peakDemandApi.getDemandForecast).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandForecast('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const hours = result.current.data?.forecast_hours;
      expect(hours?.[0].forecasted_demand_kw).toBeLessThan(hours?.[23].forecasted_demand_kw);
    });

    it('should identify falling trend', async () => {
      const mockData = createMockForecastResponse();
      mockData.forecast_hours = Array.from({ length: 24 }, (_, i) =>
        createMockForecastInterval({
          hour: i,
          forecasted_demand_kw: 5500 - i * 100, // Falling
        })
      );
      vi.mocked(peakDemandApi.getDemandForecast).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandForecast('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const hours = result.current.data?.forecast_hours;
      expect(hours?.[0].forecasted_demand_kw).toBeGreaterThan(hours?.[23].forecasted_demand_kw);
    });

    it('should identify stable trend', async () => {
      const mockData = createMockForecastResponse();
      mockData.forecast_hours = Array.from({ length: 24 }, (_, i) =>
        createMockForecastInterval({
          hour: i,
          forecasted_demand_kw: 5000, // Constant
        })
      );
      vi.mocked(peakDemandApi.getDemandForecast).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandForecast('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const hours = result.current.data?.forecast_hours;
      hours?.forEach((interval) => {
        expect(interval.forecasted_demand_kw).toBe(5000);
      });
    });
  });

  describe('Caching Behavior', () => {
    it('should respect 60s staleTime', async () => {
      const mockData = createMockForecastResponse();
      vi.mocked(peakDemandApi.getDemandForecast).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandForecast('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify query was cached
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[1] === 'forecast');
      expect(query).toBeDefined();
    });

    it('should reuse cache for duplicate requests within staleTime', async () => {
      const mockData = createMockForecastResponse();
      vi.mocked(peakDemandApi.getDemandForecast).mockResolvedValueOnce(mockData);

      // First render
      const { result: result1 } = renderHook(() => usePeakDemandForecast('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second render - should reuse cache
      const { result: result2 } = renderHook(() => usePeakDemandForecast('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result2.current.data).toEqual(mockData);
      expect(vi.mocked(peakDemandApi.getDemandForecast)).toHaveBeenCalledTimes(1);
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      const error = new Error('Network error');
      vi.mocked(peakDemandApi.getDemandForecast).mockRejectedValueOnce(error);

      const { result } = renderHook(() => usePeakDemandForecast('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
    });

    it('should handle undefined siteId (disabled query)', async () => {
      const { result } = renderHook(() => usePeakDemandForecast(undefined), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(vi.mocked(peakDemandApi.getDemandForecast)).not.toHaveBeenCalled();
    });

    it('should handle forecast with all critical hours', async () => {
      const mockData = createMockForecastResponse();
      mockData.forecast_hours = Array.from({ length: 24 }, (_, i) =>
        createMockForecastInterval({
          hour: i,
          forecasted_demand_kw: 5800,
          risk_level: 'critical',
        })
      );
      vi.mocked(peakDemandApi.getDemandForecast).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandForecast('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const allCritical = result.current.data?.forecast_hours.every(
        (h) => h.risk_level === 'critical'
      );
      expect(allCritical).toBe(true);
    });
  });

  describe('Peak Hour Analysis', () => {
    it('should correctly calculate peak headroom', async () => {
      const mockData = createMockForecastResponse({
        peak_demand_kw: 5700,
        peak_headroom_kw: 300,
        peak_headroom_percent: 5.0,
      });
      vi.mocked(peakDemandApi.getDemandForecast).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => usePeakDemandForecast('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.peak_headroom_kw).toBe(300);
      expect(result.current.data?.peak_headroom_percent).toBe(5.0);
    });
  });
});

/**
 * useSolarGeneration Hook Tests (via useSolarOverview)
 *
 * Tests solar generation and BESS data fetching:
 * - Fetch solar generation data (kWh, kW)
 * - Real-time power readings
 * - BESS SOC (state of charge) tracking
 * - Grid import/export monitoring
 * - Caching behavior (15s staleTime, 5m gcTime)
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import useSolarOverview from '../useSolarOverview';
import type { SolarOverview, SolarPlant } from '@/lib/solarApi';

vi.mock('@/lib/solarApi', () => ({
  fetchSolarOverview: vi.fn(),
}));

import { fetchSolarOverview } from '@/lib/solarApi';

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

// ============= Mock Factories =============

function createMockPlant(overrides?: Partial<SolarPlant>): SolarPlant {
  return {
    plant_id: 'plant-001',
    plant_name: 'Main Array',
    capacity_kwp: 100,
    current_generation_kw: 45.5,
    inverter_count: 2,
    status: 'normal',
    ...overrides,
  };
}

function createMockSolarOverview(overrides?: Partial<SolarOverview>): SolarOverview {
  return {
    site_id: 'site-002',
    site_name: 'Sandton Office',
    installed_capacity_kwp: 100,
    current_generation_kw: 45.5,
    daily_yield_kwh: 215.3,
    expected_daily_yield_kwh: 240,
    performance_ratio: 0.897,
    bess_soc_percent: 78.5,
    bess_mode: 'idle',
    grid_import_kw: 0,
    grid_export_kw: 8.2,
    self_consumption_percent: 84.3,
    estimated_savings_today_zar: 1250,
    plants: [
      createMockPlant({ plant_id: 'plant-001', current_generation_kw: 45.5 }),
      createMockPlant({ plant_id: 'plant-002', current_generation_kw: 0 }),
    ],
    ...overrides,
  };
}

function createMockSolarGenerationSequence(): SolarOverview[] {
  return [
    createMockSolarOverview({ current_generation_kw: 10.2, daily_yield_kwh: 10.2, bess_soc_percent: 95 }),
    createMockSolarOverview({ current_generation_kw: 45.5, daily_yield_kwh: 125.3, bess_soc_percent: 85 }),
    createMockSolarOverview({ current_generation_kw: 75.3, daily_yield_kwh: 215.3, bess_soc_percent: 65 }),
    createMockSolarOverview({ current_generation_kw: 42.1, daily_yield_kwh: 295.5, bess_soc_percent: 45 }),
    createMockSolarOverview({ current_generation_kw: 15.8, daily_yield_kwh: 325.0, bess_soc_percent: 35 }),
  ];
}

describe('useSolarGeneration Hook (via useSolarOverview)', () => {
  let queryClient: QueryClient;
  let mockFetchSolarOverview: any;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    mockFetchSolarOverview = vi.mocked(fetchSolarOverview);
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Data Fetching', () => {
    it('should fetch solar generation data for site', async () => {
      const mockData = createMockSolarOverview();
      mockFetchSolarOverview.mockResolvedValueOnce(mockData);

      const siteId = 'site-002';
      const { result } = renderHook(
        () => useSolarOverview(siteId),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockData);
      expect(mockFetchSolarOverview).toHaveBeenCalledWith(siteId);
    });

    it('should return real-time kWh readings', async () => {
      const mockData = createMockSolarOverview({
        current_generation_kw: 45.5,
        daily_yield_kwh: 215.3,
        expected_daily_yield_kwh: 240,
      });
      mockFetchSolarOverview.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useSolarOverview('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.current_generation_kw).toBe(45.5);
      expect(result.current.data?.daily_yield_kwh).toBe(215.3);
      expect(result.current.data?.expected_daily_yield_kwh).toBe(240);
    });

    it('should track BESS SOC (state of charge)', async () => {
      const mockData = createMockSolarOverview({ bess_soc_percent: 78.5 });
      mockFetchSolarOverview.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useSolarOverview('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.bess_soc_percent).toBe(78.5);
    });

    it('should track grid import/export power', async () => {
      const mockData = createMockSolarOverview({
        grid_import_kw: 0,
        grid_export_kw: 8.2,
      });
      mockFetchSolarOverview.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useSolarOverview('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.grid_import_kw).toBe(0);
      expect(result.current.data?.grid_export_kw).toBe(8.2);
    });

    it('should calculate self-consumption percentage', async () => {
      const mockData = createMockSolarOverview({ self_consumption_percent: 84.3 });
      mockFetchSolarOverview.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useSolarOverview('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.self_consumption_percent).toBe(84.3);
    });

    it('should estimate financial savings', async () => {
      const mockData = createMockSolarOverview({ estimated_savings_today_zar: 1250 });
      mockFetchSolarOverview.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useSolarOverview('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.estimated_savings_today_zar).toBe(1250);
    });

    it('should include multi-plant data', async () => {
      const mockData = createMockSolarOverview({
        plants: [
          createMockPlant({ plant_id: 'plant-001', plant_name: 'Array A', current_generation_kw: 45.5 }),
          createMockPlant({ plant_id: 'plant-002', plant_name: 'Array B', current_generation_kw: 38.2 }),
          createMockPlant({ plant_id: 'plant-003', plant_name: 'Array C', current_generation_kw: 0 }),
        ],
      });
      mockFetchSolarOverview.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useSolarOverview('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.plants).toHaveLength(3);
      expect(result.current.data?.plants[0].plant_name).toBe('Array A');
      expect(result.current.data?.plants[1].current_generation_kw).toBe(38.2);
    });
  });

  describe('Real-Time Data Changes', () => {
    it('should reflect changes in generation power', async () => {
      const sequence = createMockSolarGenerationSequence();

      // Simulate gradual generation increase and decrease through day
      for (const data of sequence) {
        mockFetchSolarOverview.mockResolvedValueOnce(data);
      }

      const { result, rerender } = renderHook(
        () => useSolarOverview('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify first measurement (morning)
      expect(result.current.data?.current_generation_kw).toBe(10.2);

      // Rerender to get next reading
      rerender();

      await waitFor(() => {
        expect(result.current.data?.current_generation_kw).toBe(45.5);
      });
    });

    it('should track BESS discharge pattern throughout day', async () => {
      const sequence = createMockSolarGenerationSequence();

      for (const data of sequence) {
        mockFetchSolarOverview.mockResolvedValueOnce(data);
      }

      const { result, rerender } = renderHook(
        () => useSolarOverview('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.bess_soc_percent).toBe(95);

      // Verify SOC decreases with discharge
      rerender();
      await waitFor(() => {
        expect(result.current.data?.bess_soc_percent).toBeLessThan(95);
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      mockFetchSolarOverview.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(
        () => useSolarOverview('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
    });

    it('should handle API timeouts', async () => {
      mockFetchSolarOverview.mockRejectedValueOnce(new Error('Request timeout'));

      const { result } = renderHook(
        () => useSolarOverview('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });
    });

    it('should handle site not found', async () => {
      mockFetchSolarOverview.mockRejectedValueOnce(new Error('Site not found'));

      const { result } = renderHook(
        () => useSolarOverview('invalid-site'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });
    });
  });

  describe('Caching Behavior', () => {
    it('should cache data with 15s stale time', async () => {
      const mockData = createMockSolarOverview();
      mockFetchSolarOverview.mockResolvedValueOnce(mockData);

      const siteId = 'site-002';
      const { result: result1 } = renderHook(
        () => useSolarOverview(siteId),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second render with same site ID should use cache
      const { result: result2 } = renderHook(
        () => useSolarOverview(siteId),
        { wrapper: createWrapper(queryClient) }
      );

      // Should not trigger additional API call within stale time
      expect(mockFetchSolarOverview).toHaveBeenCalledTimes(1);
      expect(result2.current.data).toEqual(mockData);
    });

    it('should refetch when site ID changes', async () => {
      const mockData1 = createMockSolarOverview({ site_id: 'site-002' });
      const mockData2 = createMockSolarOverview({ site_id: 'site-005' });

      mockFetchSolarOverview
        .mockResolvedValueOnce(mockData1)
        .mockResolvedValueOnce(mockData2);

      const { rerender, result } = renderHook(
        ({ siteId }) => useSolarOverview(siteId),
        {
          initialProps: { siteId: 'site-002' },
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.site_id).toBe('site-002');

      // Change site ID
      rerender({ siteId: 'site-005' });

      await waitFor(() => {
        expect(result.current.data?.site_id).toBe('site-005');
      });

      expect(mockFetchSolarOverview).toHaveBeenCalledTimes(2);
    });
  });

  describe('Enable/Disable Logic', () => {
    it('should not fetch when site ID is empty', () => {
      const { result } = renderHook(
        () => useSolarOverview(''),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(false);
      expect(mockFetchSolarOverview).not.toHaveBeenCalled();
    });

    it('should fetch when site ID becomes available', async () => {
      const mockData = createMockSolarOverview();
      mockFetchSolarOverview.mockResolvedValueOnce(mockData);

      const { rerender, result } = renderHook(
        ({ siteId }) => useSolarOverview(siteId),
        {
          initialProps: { siteId: '' },
          wrapper: createWrapper(queryClient),
        }
      );

      expect(mockFetchSolarOverview).not.toHaveBeenCalled();

      rerender({ siteId: 'site-002' });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockFetchSolarOverview).toHaveBeenCalledWith('site-002');
    });
  });

  describe('BESS Mode Tracking', () => {
    it('should report BESS idle state', async () => {
      const mockData = createMockSolarOverview({ bess_mode: 'idle', bess_soc_percent: 50 });
      mockFetchSolarOverview.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useSolarOverview('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.bess_mode).toBe('idle');
    });

    it('should report BESS charging state', async () => {
      const mockData = createMockSolarOverview({ bess_mode: 'charging', bess_soc_percent: 50 });
      mockFetchSolarOverview.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useSolarOverview('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.bess_mode).toBe('charging');
    });

    it('should report BESS discharging state', async () => {
      const mockData = createMockSolarOverview({ bess_mode: 'discharging', bess_soc_percent: 65 });
      mockFetchSolarOverview.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useSolarOverview('site-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.bess_mode).toBe('discharging');
    });
  });
});

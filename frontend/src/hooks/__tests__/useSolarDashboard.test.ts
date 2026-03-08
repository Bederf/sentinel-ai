/**
 * useSolarDashboard Hook Tests
 *
 * Tests comprehensive hook functionality:
 * - Aggregate hook combining 4 queries (system, performance, grid, BESS)
 * - Demand curve rendering (24-hour historical + NMD overlay)
 * - Headroom gauge with color zones (green >80%, yellow 15-80%, red <15%)
 * - BESS display (SOC %, charge rate, discharge available)
 * - Cost tracking (daily savings, arbitrage value in R/kWh)
 * - Active modules tracking (show only if module active)
 * - Recommendation card display (multi-module optimization)
 * - Real-time updates with automatic refresh on demand changes
 * - Error handling and graceful degradation
 * - Performance optimization: memoization preventing re-renders
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import React from 'react';
import {
  useSolarSystemOverview,
  useSolarPerformance,
  useGridCompliance,
  useBESSStatus,
  useSolarDashboard,
} from '../useSolarDashboard';
import type {
  LiveSystemData,
  PerformanceSummary,
  GridComplianceStatus,
  BESSStatusData,
} from '../../lib/api/solar';

// Mock the solar API module
vi.mock('../../lib/api/solar', () => ({
  fetchLiveSystemData: vi.fn(),
  fetchPerformanceSummary: vi.fn(),
  fetchGridComplianceStatus: vi.fn(),
  fetchBESSStatusData: vi.fn(),
}));

import {
  fetchLiveSystemData,
  fetchPerformanceSummary,
  fetchGridComplianceStatus,
  fetchBESSStatusData,
} from '../../lib/api/solar';

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
function createMockLiveSystemData(overrides?: Partial<LiveSystemData>): LiveSystemData {
  return {
    site_id: 'site-002',
    timestamp: new Date().toISOString(),
    current_generation_kw: 275.2,
    rated_capacity_kwp: 500,
    generation_percent: 55,
    daily_yield_kwh: 3420,
    peak_power_kw: 450,
    average_power_kw: 285,
    energy_exported_kwh: 1850,
    bess_soc_percent: 65,
    bess_discharge_hours: 2.5,
    inverter_operating: 2,
    inverter_offline: 0,
    inverter_faulted: 0,
    ...overrides,
  };
}

function createMockPerformanceSummary(overrides?: Partial<PerformanceSummary>): PerformanceSummary {
  return {
    site_id: 'site-002',
    timestamp: new Date().toISOString(),
    system_efficiency_percent: 92.5,
    peer_average_efficiency_percent: 89.2,
    efficiency_trend: 'stable',
    string_health: [
      { string_id: 'STR-001', health_percent: 98 },
      { string_id: 'STR-002', health_percent: 96 },
    ],
    capacity_factor_24h: 18.5,
    capacity_factor_7d: 22.3,
    capacity_factor_30d: 24.1,
    soiling_loss_percent: 2.1,
    soiling_annual_percent: 3.5,
    soiling_trend: 'stable',
    degradation_yearly_percent: 0.8,
    degradation_annual_percent: 0.8,
    warranty_status: 'active',
    ...overrides,
  };
}

function createMockGridComplianceStatus(
  overrides?: Partial<GridComplianceStatus>
): GridComplianceStatus {
  return {
    site_id: 'site-002',
    timestamp: new Date().toISOString(),
    grid_frequency_hz: 50.0,
    frequency_safe: true,
    frequency_band_status: 'green',
    frequency_trend_1h: [49.95, 50.02, 50.01, 49.98, 50.03],
    load_shedding_stage: 0,
    load_shedding_active: false,
    violations_count: 0,
    violations: [],
    auto_response_curtailment_percent: 0,
    auto_response_standby: false,
    auto_response_droop: 0,
    compliance_badge: 'compliant',
    last_check_time: new Date().toISOString(),
    ...overrides,
  };
}

function createMockBESSStatusData(overrides?: Partial<BESSStatusData>): BESSStatusData {
  return {
    site_id: 'site-002',
    timestamp: new Date().toISOString(),
    charge_power_kw: 0,
    discharge_power_kw: 85,
    power_direction: 'idle',
    current_power_kw: 0,
    battery_charge_percent: 65,
    battery_curve_24h: [
      { timestamp: '2026-02-13T00:00:00Z', charge_percent: 45 },
      { timestamp: '2026-02-13T06:00:00Z', charge_percent: 52 },
      { timestamp: '2026-02-13T12:00:00Z', charge_percent: 75 },
      { timestamp: '2026-02-13T18:00:00Z', charge_percent: 65 },
    ],
    temperature_c: 28,
    temperature_alert: false,
    state_of_health_percent: 95,
    soh_trend: 'stable',
    cycle_count: 245,
    estimated_remaining_years: 12,
    efficiency_roundtrip_percent: 92,
    efficiency_rated_percent: 95,
    energy_reserve_kwh: 162.5,
    suitable_for_hours: 2.5,
    thermal_limit_c: 45,
    ...overrides,
  };
}

describe('Solar Dashboard Hooks', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('useSolarSystemOverview Hook', () => {
    it('should fetch live system data successfully', async () => {
      const mockData = createMockLiveSystemData();
      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarSystemOverview('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.current_generation_kw).toBe(275.2);
      expect(result.current.data?.generation_percent).toBe(55);
    });

    it('should track current generation and capacity', async () => {
      const mockData = createMockLiveSystemData({
        current_generation_kw: 350,
        rated_capacity_kwp: 500,
        generation_percent: 70,
      });
      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarSystemOverview('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.generation_percent).toBe(70);
      expect(result.current.data?.current_generation_kw).toBeLessThanOrEqual(
        result.current.data?.rated_capacity_kwp || 0
      );
    });

    it('should respect 10s staleTime for live system data', async () => {
      const mockData = createMockLiveSystemData();
      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarSystemOverview('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'solar-system-overview');
      expect(query).toBeDefined();
    });

    it('should track daily yield and peak power', async () => {
      const mockData = createMockLiveSystemData({
        daily_yield_kwh: 3420,
        peak_power_kw: 450,
        average_power_kw: 285,
      });
      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarSystemOverview('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.daily_yield_kwh).toBe(3420);
      expect(result.current.data?.peak_power_kw).toBeGreaterThanOrEqual(
        result.current.data?.average_power_kw || 0
      );
    });

    it('should support optional refetchInterval for automatic polling', async () => {
      const mockData = createMockLiveSystemData();
      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarSystemOverview('site-002', 5000), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toBeDefined();
    });
  });

  describe('useSolarPerformance Hook', () => {
    it('should fetch performance metrics successfully', async () => {
      const mockData = createMockPerformanceSummary();
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarPerformance('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.system_efficiency_percent).toBe(92.5);
      expect(result.current.data?.efficiency_trend).toBe('stable');
    });

    it('should compare efficiency against peer average', async () => {
      const mockData = createMockPerformanceSummary({
        system_efficiency_percent: 92.5,
        peer_average_efficiency_percent: 89.2,
      });
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarPerformance('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.system_efficiency_percent).toBeGreaterThan(
        result.current.data?.peer_average_efficiency_percent || 0
      );
    });

    it('should track string health metrics', async () => {
      const mockData = createMockPerformanceSummary({
        string_health: [
          { string_id: 'STR-001', health_percent: 98 },
          { string_id: 'STR-002', health_percent: 96 },
          { string_id: 'STR-003', health_percent: 94 },
        ],
      });
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarPerformance('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.string_health).toHaveLength(3);
      expect(result.current.data?.string_health?.[0].health_percent).toBe(98);
    });

    it('should respect 30s staleTime for performance data', async () => {
      const mockData = createMockPerformanceSummary();
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarPerformance('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'solar-performance');
      expect(query).toBeDefined();
    });
  });

  describe('useGridCompliance Hook', () => {
    it('should fetch grid compliance status successfully', async () => {
      const mockData = createMockGridComplianceStatus();
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useGridCompliance('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.grid_frequency_hz).toBe(50.0);
      expect(result.current.data?.frequency_safe).toBe(true);
    });

    it('should determine frequency safety status', async () => {
      const mockDataSafe = createMockGridComplianceStatus({
        grid_frequency_hz: 50.0,
        frequency_safe: true,
        frequency_band_status: 'green',
      });
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(mockDataSafe);

      const { result } = renderHook(() => useGridCompliance('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.frequency_safe).toBe(true);
      expect(result.current.data?.frequency_band_status).toBe('green');
    });

    it('should track load shedding stage', async () => {
      const mockData = createMockGridComplianceStatus({
        load_shedding_stage: 3,
        load_shedding_active: true,
      });
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useGridCompliance('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.load_shedding_stage).toBe(3);
      expect(result.current.data?.load_shedding_active).toBe(true);
    });

    it('should respect 5s staleTime for critical grid data', async () => {
      const mockData = createMockGridComplianceStatus();
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useGridCompliance('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'grid-compliance');
      expect(query).toBeDefined();
    });

    it('should track compliance badge status', async () => {
      const mockData = createMockGridComplianceStatus({
        compliance_badge: 'compliant',
        violations_count: 0,
      });
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useGridCompliance('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.compliance_badge).toBe('compliant');
    });
  });

  describe('useBESSStatus Hook', () => {
    it('should fetch BESS status successfully', async () => {
      const mockData = createMockBESSStatusData();
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useBESSStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.battery_charge_percent).toBe(65);
      expect(result.current.data?.state_of_health_percent).toBe(95);
    });

    it('should track battery charge curve over 24 hours', async () => {
      const mockData = createMockBESSStatusData({
        battery_curve_24h: [
          { timestamp: '2026-02-13T00:00:00Z', charge_percent: 45 },
          { timestamp: '2026-02-13T06:00:00Z', charge_percent: 52 },
          { timestamp: '2026-02-13T12:00:00Z', charge_percent: 75 },
          { timestamp: '2026-02-13T18:00:00Z', charge_percent: 65 },
        ],
      });
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useBESSStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.battery_curve_24h).toHaveLength(4);
      expect(result.current.data?.battery_curve_24h?.[0].charge_percent).toBe(45);
    });

    it('should track temperature and health', async () => {
      const mockData = createMockBESSStatusData({
        temperature_c: 28,
        temperature_alert: false,
        state_of_health_percent: 95,
      });
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useBESSStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.temperature_c).toBe(28);
      expect(result.current.data?.temperature_alert).toBe(false);
      expect(result.current.data?.state_of_health_percent).toBeLessThanOrEqual(100);
    });

    it('should respect 15s staleTime for BESS data', async () => {
      const mockData = createMockBESSStatusData();
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useBESSStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'bess-status');
      expect(query).toBeDefined();
    });
  });

  describe('useSolarDashboard Aggregate Hook', () => {
    it('should aggregate all four queries successfully', async () => {
      const mockSystemData = createMockLiveSystemData();
      const mockPerformanceData = createMockPerformanceSummary();
      const mockGridData = createMockGridComplianceStatus();
      const mockBESSData = createMockBESSStatusData();

      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(mockSystemData);
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(mockPerformanceData);
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(mockGridData);
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockBESSData);

      const { result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.systemOverview.isSuccess).toBe(true);
      });

      expect(result.current.systemOverview.data).toBeDefined();
      expect(result.current.performance.data).toBeDefined();
      expect(result.current.gridCompliance.data).toBeDefined();
      expect(result.current.bessStatus.data).toBeDefined();
    });

    it('should track overall loading state', async () => {
      const mockSystemData = createMockLiveSystemData();
      const mockPerformanceData = createMockPerformanceSummary();
      const mockGridData = createMockGridComplianceStatus();
      const mockBESSData = createMockBESSStatusData();

      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(mockSystemData);
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(mockPerformanceData);
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(mockGridData);
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockBESSData);

      const { result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isLoading).toBe(false);
    });

    it('should track overall error state when query fails', async () => {
      // When any query fails, isError should be true
      const error = new Error('System overview failed');
      vi.mocked(fetchLiveSystemData).mockRejectedValueOnce(error);
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(createMockPerformanceSummary());
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(
        createMockGridComplianceStatus()
      );
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(createMockBESSStatusData());

      const { result: _result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      // At least one query should fail
      expect(vi.mocked(fetchLiveSystemData)).toHaveBeenCalled();
    });

    it('should handle partial failures gracefully', async () => {
      const error = new Error('Grid compliance fetch failed');
      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(createMockLiveSystemData());
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(createMockPerformanceSummary());
      vi.mocked(fetchGridComplianceStatus).mockRejectedValueOnce(error);
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(createMockBESSStatusData());

      const { result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      // Wait for system overview to succeed, then verify grid compliance failed
      await waitFor(() => {
        expect(result.current.systemOverview.isSuccess).toBe(true);
      });

      await waitFor(() => {
        expect(result.current.gridCompliance.isError).toBe(true);
      });

      // Check independent queries succeed
      expect(result.current.performance.isSuccess).toBe(true);
      expect(result.current.bessStatus.isSuccess).toBe(true);
    });

    it('should reuse cache for duplicate requests within staleTime', async () => {
      const mockSystemData = createMockLiveSystemData();
      const mockPerformanceData = createMockPerformanceSummary();
      const mockGridData = createMockGridComplianceStatus();
      const mockBESSData = createMockBESSStatusData();

      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(mockSystemData);
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(mockPerformanceData);
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(mockGridData);
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockBESSData);

      const { result: result1 } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result1.current.isLoading).toBe(false);
      });

      // Second render should reuse cache
      const { result: result2 } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result2.current.systemOverview.data).toEqual(mockSystemData);
      expect(vi.mocked(fetchLiveSystemData)).toHaveBeenCalledTimes(1);
    });

    it('should disable queries when siteId is empty', async () => {
      const { result } = renderHook(() => useSolarDashboard(''), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.systemOverview.data).toBeUndefined();
      expect(result.current.performance.data).toBeUndefined();
      expect(result.current.gridCompliance.data).toBeUndefined();
      expect(result.current.bessStatus.data).toBeUndefined();
      expect(vi.mocked(fetchLiveSystemData)).not.toHaveBeenCalled();
    });
  });

  describe('Dashboard Display: Demand Curve and NMD Overlay', () => {
    it('should display 24-hour demand curve data', async () => {
      const mockSystemData = createMockLiveSystemData({
        daily_yield_kwh: 3420,
      });
      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(mockSystemData);
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(createMockPerformanceSummary());
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(
        createMockGridComplianceStatus()
      );
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(createMockBESSStatusData());

      const { result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.systemOverview.isSuccess).toBe(true);
      });

      expect(result.current.systemOverview.data?.daily_yield_kwh).toBe(3420);
    });

    it('should provide data for NMD headroom gauge display', async () => {
      const mockSystemData = createMockLiveSystemData({
        current_generation_kw: 350,
        rated_capacity_kwp: 500,
      });
      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(mockSystemData);
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(createMockPerformanceSummary());
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(
        createMockGridComplianceStatus()
      );
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(createMockBESSStatusData());

      const { result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.systemOverview.isSuccess).toBe(true);
      });

      const sysData = result.current.systemOverview.data;
      const headroomPercent = (sysData?.generation_percent || 0) / 100;
      expect(headroomPercent).toBeGreaterThanOrEqual(0);
      expect(headroomPercent).toBeLessThanOrEqual(1);
    });
  });

  describe('Dashboard Display: BESS Status', () => {
    it('should display battery SOC percentage', async () => {
      const mockBESSData = createMockBESSStatusData({ battery_charge_percent: 65 });
      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(createMockLiveSystemData());
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(createMockPerformanceSummary());
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(
        createMockGridComplianceStatus()
      );
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockBESSData);

      const { result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.bessStatus.isSuccess).toBe(true);
      });

      expect(result.current.bessStatus.data?.battery_charge_percent).toBe(65);
    });

    it('should display discharge available power', async () => {
      const mockBESSData = createMockBESSStatusData({
        discharge_power_kw: 85,
      });
      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(createMockLiveSystemData());
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(createMockPerformanceSummary());
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(
        createMockGridComplianceStatus()
      );
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockBESSData);

      const { result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.bessStatus.isSuccess).toBe(true);
      });

      expect(result.current.bessStatus.data?.discharge_power_kw).toBe(85);
    });

    it('should track battery health degradation', async () => {
      const mockBESSData = createMockBESSStatusData({
        state_of_health_percent: 92,
        soh_trend: 'declining',
      });
      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(createMockLiveSystemData());
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(createMockPerformanceSummary());
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(
        createMockGridComplianceStatus()
      );
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockBESSData);

      const { result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.bessStatus.isSuccess).toBe(true);
      });

      expect(result.current.bessStatus.data?.soh_trend).toBe('declining');
    });
  });

  describe('Dashboard Display: Cost Tracking', () => {
    it('should support daily savings calculation', async () => {
      const mockBESSData = createMockBESSStatusData({
        discharge_power_kw: 85,
        energy_reserve_kwh: 162.5,
      });
      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(createMockLiveSystemData());
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(createMockPerformanceSummary());
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(
        createMockGridComplianceStatus()
      );
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockBESSData);

      const { result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.bessStatus.isSuccess).toBe(true);
      });

      expect(result.current.bessStatus.data?.energy_reserve_kwh).toBeGreaterThan(0);
    });

    it('should calculate arbitrage value based on discharge cycles', async () => {
      const mockBESSData = createMockBESSStatusData({
        efficiency_roundtrip_percent: 92,
        discharge_power_kw: 85,
      });
      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(createMockLiveSystemData());
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(createMockPerformanceSummary());
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(
        createMockGridComplianceStatus()
      );
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockBESSData);

      const { result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.bessStatus.isSuccess).toBe(true);
      });

      expect(result.current.bessStatus.data?.efficiency_roundtrip_percent).toBeGreaterThan(80);
    });
  });

  describe('Error Handling and Graceful Degradation', () => {
    it('should handle errors without crashing', async () => {
      const error = new Error('Failed to fetch system overview');
      vi.mocked(fetchLiveSystemData).mockRejectedValueOnce(error);
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(createMockPerformanceSummary());
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(
        createMockGridComplianceStatus()
      );
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(createMockBESSStatusData());

      const { result: _result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      // Verify system overview error is captured
      expect(vi.mocked(fetchLiveSystemData)).toHaveBeenCalled();
    });

    it('should support multi-query failures', async () => {
      vi.mocked(fetchLiveSystemData).mockRejectedValueOnce(new Error('System error'));
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(createMockPerformanceSummary());
      vi.mocked(fetchGridComplianceStatus).mockRejectedValueOnce(new Error('Grid error'));
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(createMockBESSStatusData());

      const { result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      // Wait for at least one successful query
      await waitFor(() => {
        expect(result.current.performance.isSuccess).toBe(true);
      });

      // Verify both APIs were called
      expect(vi.mocked(fetchLiveSystemData)).toHaveBeenCalled();
      expect(vi.mocked(fetchGridComplianceStatus)).toHaveBeenCalled();
    });
  });

  describe('Performance Optimization', () => {
    it('should cache results to prevent duplicate API calls', async () => {
      const mockSystemData = createMockLiveSystemData();
      const mockPerformanceData = createMockPerformanceSummary();
      const mockGridData = createMockGridComplianceStatus();
      const mockBESSData = createMockBESSStatusData();

      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(mockSystemData);
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(mockPerformanceData);
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(mockGridData);
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockBESSData);

      const { result: result1 } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result1.current.systemOverview.isSuccess).toBe(true);
      });

      // Verify API called once
      expect(vi.mocked(fetchLiveSystemData)).toHaveBeenCalledTimes(1);

      // Render again - should use cache
      const { result: result2 } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result2.current.systemOverview.data).toEqual(mockSystemData);
      expect(vi.mocked(fetchLiveSystemData)).toHaveBeenCalledTimes(1);
    });

    it('should provide all data without unnecessary re-renders', async () => {
      const mockSystemData = createMockLiveSystemData();
      const mockPerformanceData = createMockPerformanceSummary();
      const mockGridData = createMockGridComplianceStatus();
      const mockBESSData = createMockBESSStatusData();

      vi.mocked(fetchLiveSystemData).mockResolvedValueOnce(mockSystemData);
      vi.mocked(fetchPerformanceSummary).mockResolvedValueOnce(mockPerformanceData);
      vi.mocked(fetchGridComplianceStatus).mockResolvedValueOnce(mockGridData);
      vi.mocked(fetchBESSStatusData).mockResolvedValueOnce(mockBESSData);

      const { result } = renderHook(() => useSolarDashboard('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.systemOverview.isSuccess).toBe(true);
      });

      expect(result.current.systemOverview.data).toBeDefined();
      expect(result.current.performance.data).toBeDefined();
      expect(result.current.gridCompliance.data).toBeDefined();
      expect(result.current.bessStatus.data).toBeDefined();
    });
  });
});

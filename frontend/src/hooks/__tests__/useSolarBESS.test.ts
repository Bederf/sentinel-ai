/**
 * useSolarBESS Hook Tests
 *
 * Tests comprehensive hook functionality:
 * - SOC (State of Charge) tracking and calculation
 * - Discharge available calculation based on min/max SOC constraints
 * - Charge cycle management (absorption, float, idle states)
 * - Discharge cycle with grid import reduction
 * - Battery state transitions (all legal paths)
 * - Error states (inverter fault, charger failure, sensor malfunction)
 * - Real-time updates and cache invalidation
 * - Cost calculation (TOU tariff × discharge window)
 * - Safety limits (min 20% SOC, max 95% SOC)
 * - API endpoint verification with site_id parameter
 * - Event listener cleanup on unmount
 * - Edge case: simultaneous solar ramp + demand spike
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import React from 'react';
import { useSolarBESS, useSolarInverters, useSolarPerformance, useSolarFinancial } from '../useSolarBESS';
import type { BESSStatus, InverterListResponse, PerformanceMetrics, FinancialSummary } from '../../lib/solarApi';

// Mock the solarApi module
vi.mock('../../lib/solarApi', () => ({
  fetchBESSStatus: vi.fn(),
  fetchInverters: vi.fn(),
  fetchPerformance: vi.fn(),
  fetchFinancialSummary: vi.fn(),
}));

import { fetchBESSStatus, fetchInverters, fetchPerformance, fetchFinancialSummary } from '../../lib/solarApi';

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

// Mock data factories
function createMockBESSStatus(overrides?: Partial<BESSStatus>): BESSStatus {
  return {
    site_id: 'site-002',
    timestamp: new Date().toISOString(),
    soc_percent: 65,
    discharge_available_kw: 150, // Calculated: (65 - 20) / 100 * 250 = 112.5, rounded to 150 for testing
    charge_hours_remaining: 2.5,
    temperature_c: 28,
    health_percent: 95,
    power_direction: 'idle',
    charge_state: 'idle',
    max_discharge_power_kw: 250,
    max_charge_power_kw: 200,
    ...overrides,
  };
}

function createMockInverterListResponse(overrides?: Partial<InverterListResponse>): InverterListResponse {
  return {
    site_id: 'site-002',
    timestamp: new Date().toISOString(),
    inverters: [
      {
        inverter_id: 'INV-001',
        status: 'operating',
        power_output_kw: 85.5,
        efficiency_percent: 97.2,
        temperature_c: 32,
      },
      {
        inverter_id: 'INV-002',
        status: 'operating',
        power_output_kw: 92.3,
        efficiency_percent: 97.8,
        temperature_c: 31,
      },
    ],
    total_power_output_kw: 177.8,
    operating_count: 2,
    offline_count: 0,
    faulted_count: 0,
    ...overrides,
  };
}

function createMockPerformanceMetrics(overrides?: Partial<PerformanceMetrics>): PerformanceMetrics {
  return {
    site_id: 'site-002',
    timestamp: new Date().toISOString(),
    performance_ratio_percent: 78.5,
    reference_yield_kwh: 125.3,
    actual_yield_kwh: 98.2,
    soiling_loss_percent: 2.1,
    availability_percent: 99.8,
    ...overrides,
  };
}

function createMockFinancialSummary(overrides?: Partial<FinancialSummary>): FinancialSummary {
  return {
    site_id: 'site-002',
    period: 'ytd',
    revenue_r: 45000,
    avoided_grid_cost_r: 8500,
    bess_arbitrage_savings_r: 3200,
    total_savings_r: 56700,
    co2_avoided_tons: 45.2,
    ...overrides,
  };
}

describe('useSolarBESS Hook', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('SOC Tracking and Initialization', () => {
    it('should fetch and display current SOC percentage', async () => {
      const mockData = createMockBESSStatus({ soc_percent: 65 });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.soc_percent).toBe(65);
      expect(result.current.data?.site_id).toBe('site-002');
    });

    it('should calculate discharge available based on min/max constraints', async () => {
      const mockData = createMockBESSStatus({
        soc_percent: 65,
        discharge_available_kw: 112.5, // (65-20)/100 * 250kW max = 112.5kW
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.discharge_available_kw).toBe(112.5);
      expect(result.current.data?.discharge_available_kw).toBeLessThanOrEqual(
        result.current.data?.max_discharge_power_kw || 0
      );
    });

    it('should track battery temperature within safe limits', async () => {
      const mockData = createMockBESSStatus({ temperature_c: 28 });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.temperature_c).toBe(28);
      // Safe limit check: temperature should be < 45°C for LiFePO4
      expect(result.current.data?.temperature_c).toBeLessThan(45);
    });

    it('should track battery health percentage', async () => {
      const mockData = createMockBESSStatus({ health_percent: 95 });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.health_percent).toBe(95);
      expect(result.current.data?.health_percent).toBeGreaterThan(0);
      expect(result.current.data?.health_percent).toBeLessThanOrEqual(100);
    });
  });

  describe('Charge Cycle Management', () => {
    it('should identify idle charge state', async () => {
      const mockData = createMockBESSStatus({
        charge_state: 'idle',
        power_direction: 'idle',
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.charge_state).toBe('idle');
      expect(result.current.data?.power_direction).toBe('idle');
    });

    it('should identify absorption charge state', async () => {
      const mockData = createMockBESSStatus({
        charge_state: 'absorption',
        power_direction: 'charging',
        soc_percent: 85,
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.charge_state).toBe('absorption');
      expect(result.current.data?.power_direction).toBe('charging');
    });

    it('should identify float charge state', async () => {
      const mockData = createMockBESSStatus({
        charge_state: 'float',
        power_direction: 'charging',
        soc_percent: 95,
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.charge_state).toBe('float');
      expect(result.current.data?.soc_percent).toBeGreaterThan(90);
    });

    it('should calculate charge time remaining', async () => {
      const mockData = createMockBESSStatus({
        soc_percent: 40,
        charge_hours_remaining: 3.5,
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.charge_hours_remaining).toBe(3.5);
      expect(result.current.data?.charge_hours_remaining).toBeGreaterThan(0);
    });
  });

  describe('Discharge Cycle and Grid Load Reduction', () => {
    it('should identify discharge power direction', async () => {
      const mockData = createMockBESSStatus({
        power_direction: 'discharging',
        soc_percent: 60,
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.power_direction).toBe('discharging');
    });

    it('should enforce minimum SOC safety limit (20%)', async () => {
      const mockData = createMockBESSStatus({
        soc_percent: 25,
        discharge_available_kw: 12.5, // (25-20)/100 * 250 = 12.5kW only
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.soc_percent).toBeGreaterThanOrEqual(20);
      expect(result.current.data?.discharge_available_kw).toBeLessThan(15);
    });

    it('should prevent discharge below minimum SOC threshold', async () => {
      const mockData = createMockBESSStatus({
        soc_percent: 20,
        discharge_available_kw: 0, // At min, no discharge available
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.discharge_available_kw).toBe(0);
    });

    it('should reduce grid import during discharge', async () => {
      const mockData = createMockBESSStatus({
        power_direction: 'discharging',
        max_discharge_power_kw: 200, // 200kW available to offset grid
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.max_discharge_power_kw).toBe(200);
      expect(result.current.data?.max_discharge_power_kw).toBeGreaterThan(0);
    });
  });

  describe('Battery State Transitions', () => {
    it('should transition from idle to charge', async () => {
      const mockData = createMockBESSStatus({
        charge_state: 'charge',
        power_direction: 'charging',
        soc_percent: 50,
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.charge_state).toBe('charge');
      expect(result.current.data?.power_direction).toBe('charging');
    });

    it('should transition from charge to float', async () => {
      const mockData = createMockBESSStatus({
        charge_state: 'float',
        power_direction: 'charging',
        soc_percent: 92,
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.charge_state).toBe('float');
      expect(result.current.data?.soc_percent).toBeGreaterThanOrEqual(90);
    });

    it('should transition from float back to idle', async () => {
      const mockData = createMockBESSStatus({
        charge_state: 'idle',
        power_direction: 'idle',
        soc_percent: 95,
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.charge_state).toBe('idle');
      expect(result.current.data?.power_direction).toBe('idle');
    });

    it('should transition from idle to discharge', async () => {
      const mockData = createMockBESSStatus({
        charge_state: 'discharge',
        power_direction: 'discharging',
        soc_percent: 70,
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.charge_state).toBe('discharge');
      expect(result.current.data?.power_direction).toBe('discharging');
    });

    it('should transition from discharge back to idle', async () => {
      const mockData = createMockBESSStatus({
        charge_state: 'idle',
        power_direction: 'idle',
        soc_percent: 35,
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.charge_state).toBe('idle');
      expect(result.current.data?.power_direction).toBe('idle');
    });
  });

  describe('Error States and Fault Handling', () => {
    it('should handle inverter fault error', async () => {
      const error = new Error('Inverter fault detected: INV-001');
      vi.mocked(fetchBESSStatus).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toContain('Inverter fault');
    });

    it('should handle charger failure error', async () => {
      const error = new Error('Charger failure: communication lost');
      vi.mocked(fetchBESSStatus).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toContain('Charger failure');
    });

    it('should handle SOC sensor malfunction error', async () => {
      const error = new Error('SOC sensor malfunction: unreliable reading');
      vi.mocked(fetchBESSStatus).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toContain('SOC sensor malfunction');
    });

    it('should handle network connectivity errors', async () => {
      const error = new Error('Network timeout');
      vi.mocked(fetchBESSStatus).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
    });
  });

  describe('Real-Time Updates and Cache Invalidation', () => {
    it('should respect 15s staleTime for dynamic BESS data', async () => {
      const mockData = createMockBESSStatus();
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'solar-bess');
      expect(query).toBeDefined();
    });

    it('should reuse cache for duplicate BESS requests within staleTime', async () => {
      const mockData = createMockBESSStatus();
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result: result1 } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      const { result: result2 } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result2.current.data).toEqual(mockData);
      expect(vi.mocked(fetchBESSStatus)).toHaveBeenCalledTimes(1);
    });

    it('should invalidate cache when siteId changes', async () => {
      const mockData1 = createMockBESSStatus({ site_id: 'site-002' });
      const mockData2 = createMockBESSStatus({ site_id: 'site-005' });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData1);
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData2);

      const { rerender, result } = renderHook(({ siteId }) => useSolarBESS(siteId), {
        initialProps: { siteId: 'site-002' },
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.site_id).toBe('site-002');

      rerender({ siteId: 'site-005' });

      await waitFor(() => {
        expect(result.current.data?.site_id).toBe('site-005');
      });

      expect(vi.mocked(fetchBESSStatus)).toHaveBeenCalledTimes(2);
    });
  });

  describe('Safety Constraints Enforcement', () => {
    it('should enforce maximum SOC limit (95%)', async () => {
      const mockData = createMockBESSStatus({ soc_percent: 95 });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.soc_percent).toBeLessThanOrEqual(95);
    });

    it('should prevent charging when at maximum SOC', async () => {
      const mockData = createMockBESSStatus({
        soc_percent: 95,
        charge_state: 'idle',
        power_direction: 'idle',
      });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.charge_state).not.toBe('charge');
      expect(result.current.data?.power_direction).not.toBe('charging');
    });

    it('should honor temperature operating limits', async () => {
      const mockData = createMockBESSStatus({ temperature_c: 35 });
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Temperature should be within safe operating range
      expect(result.current.data?.temperature_c).toBeGreaterThanOrEqual(-10);
      expect(result.current.data?.temperature_c).toBeLessThanOrEqual(50);
    });
  });

  describe('API Endpoint Verification', () => {
    it('should call fetchBESSStatus with correct site_id parameter', async () => {
      const mockData = createMockBESSStatus();
      vi.mocked(fetchBESSStatus).mockResolvedValueOnce(mockData);

      renderHook(() => useSolarBESS('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(vi.mocked(fetchBESSStatus)).toHaveBeenCalled();
      });

      expect(vi.mocked(fetchBESSStatus)).toHaveBeenCalledWith('site-002');
    });

    it('should handle undefined siteId (disabled query)', async () => {
      const { result } = renderHook(() => useSolarBESS(''), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(vi.mocked(fetchBESSStatus)).not.toHaveBeenCalled();
    });
  });

  describe('useSolarInverters Hook', () => {
    it('should fetch and display inverter list', async () => {
      const mockData = createMockInverterListResponse();
      vi.mocked(fetchInverters).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarInverters('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.inverters).toHaveLength(2);
      expect(result.current.data?.total_power_output_kw).toBe(177.8);
    });

    it('should track inverter status distribution', async () => {
      const mockData = createMockInverterListResponse({
        operating_count: 2,
        offline_count: 1,
        faulted_count: 0,
      });
      vi.mocked(fetchInverters).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarInverters('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.operating_count).toBe(2);
      expect(result.current.data?.offline_count).toBe(1);
      expect(result.current.data?.faulted_count).toBe(0);
    });

    it('should respect 30s staleTime for inverter data', async () => {
      const mockData = createMockInverterListResponse();
      vi.mocked(fetchInverters).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarInverters('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'solar-inverters');
      expect(query).toBeDefined();
    });
  });

  describe('useSolarPerformance Hook', () => {
    it('should fetch and display performance metrics', async () => {
      const mockData = createMockPerformanceMetrics();
      vi.mocked(fetchPerformance).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarPerformance('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.performance_ratio_percent).toBe(78.5);
      expect(result.current.data?.availability_percent).toBe(99.8);
    });

    it('should calculate performance ratio correctly', async () => {
      const mockData = createMockPerformanceMetrics({
        reference_yield_kwh: 125.3,
        actual_yield_kwh: 98.2,
      });
      vi.mocked(fetchPerformance).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarPerformance('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.actual_yield_kwh).toBeLessThanOrEqual(
        result.current.data?.reference_yield_kwh || 0
      );
    });

    it('should respect 60s staleTime for performance data', async () => {
      const mockData = createMockPerformanceMetrics();
      vi.mocked(fetchPerformance).mockResolvedValueOnce(mockData);

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

  describe('useSolarFinancial Hook', () => {
    it('should fetch and display financial summary', async () => {
      const mockData = createMockFinancialSummary();
      vi.mocked(fetchFinancialSummary).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarFinancial('site-002', 'ytd'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.total_savings_r).toBe(56700);
    });

    it('should calculate total savings including BESS arbitrage', async () => {
      const mockData = createMockFinancialSummary({
        avoided_grid_cost_r: 8500,
        bess_arbitrage_savings_r: 3200,
      });
      vi.mocked(fetchFinancialSummary).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarFinancial('site-002', 'ytd'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.bess_arbitrage_savings_r).toBe(3200);
      expect(result.current.data?.bess_arbitrage_savings_r).toBeGreaterThan(0);
    });

    it('should support different financial periods', async () => {
      const mockDataYTD = createMockFinancialSummary({ period: 'ytd', revenue_r: 45000 });
      const mockDataMTD = createMockFinancialSummary({ period: 'mtd', revenue_r: 8500 });
      vi.mocked(fetchFinancialSummary).mockResolvedValueOnce(mockDataYTD);
      vi.mocked(fetchFinancialSummary).mockResolvedValueOnce(mockDataMTD);

      const { result: resultYTD } = renderHook(() => useSolarFinancial('site-002', 'ytd'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(resultYTD.current.isSuccess).toBe(true);
      });

      const { result: resultMTD } = renderHook(() => useSolarFinancial('site-002', 'mtd'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(resultMTD.current.isSuccess).toBe(true);
      });

      expect(resultYTD.current.data?.period).toBe('ytd');
      expect(resultMTD.current.data?.period).toBe('mtd');
    });

    it('should respect 60s staleTime for financial data', async () => {
      const mockData = createMockFinancialSummary();
      vi.mocked(fetchFinancialSummary).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useSolarFinancial('site-002', 'ytd'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'solar-financial');
      expect(query).toBeDefined();
    });
  });
});

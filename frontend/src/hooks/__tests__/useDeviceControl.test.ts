/**
 * useDeviceControl Hook Tests - Phase 68-03 Coverage
 *
 * Comprehensive testing of device control operations:
 * - Device data fetching and initialization
 * - Control operations with safety validation
 * - Device value reading and writing
 * - COV (Change of Value) feedback verification
 * - Error handling and recovery
 * - Real-time polling and refresh
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import React from 'react';
import { useDeviceControl } from '../useDeviceControl';
import type { Device, DeviceValue } from '@/lib/api';

// Mock the API module
vi.mock('@/lib/api', () => ({
  default: {
    getDevice: vi.fn(),
    getDevicePoints: vi.fn(),
    readDevicePoint: vi.fn(),
    controlDevice: vi.fn(),
  },
}));

import api from '@/lib/api';

// Test utilities
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: 0, gcTime: Infinity },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

// Mock data factories
function createMockDevice(overrides?: Partial<Device>): Device {
  return {
    id: 'device-001',
    name: 'Test Chiller',
    type: 'CHILLER',
    protocol: 'BACnet',
    status: 'operational',
    last_read: new Date().toISOString(),
    metadata: {
      critical: false,
      life_safety: false,
    },
    points: {
      setpoint: { name: 'setpoint', writable: true, unit: '°C', default_value: 20 },
      supply_temp: { name: 'supply_temp', writable: false, unit: '°C', default_value: 0 },
      status: { name: 'status', writable: false, unit: '', default_value: 'on' },
    },
    ...overrides,
  };
}

function createMockDeviceValue(overrides?: Partial<DeviceValue>): DeviceValue {
  return {
    device_id: 'device-001',
    point_name: 'setpoint',
    value: 20,
    unit: '°C',
    timestamp: new Date().toISOString(),
    quality: 'good',
    ...overrides,
  };
}

describe('useDeviceControl', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    queryClient.clear();
  });

  describe('Device Initialization', () => {
    it('should fetch device and points on mount', async () => {
      const mockDevice = createMockDevice();
      const mockPoints = {
        setpoint: { writable: true, unit: '°C', default_value: 20 },
        supply_temp: { writable: false, unit: '°C', default_value: 0 },
      };

      vi.mocked(api.getDevice).mockResolvedValueOnce(mockDevice);
      vi.mocked(api.getDevicePoints).mockResolvedValueOnce(mockPoints);
      vi.mocked(api.readDevicePoint).mockResolvedValueOnce(
        createMockDeviceValue({ point_name: 'supply_temp', value: 18 })
      );

      const { result } = renderHook(() => useDeviceControl({ deviceId: 'device-001' }), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.loading).toBe(true);

      await waitFor(() => {
        expect(result.current.device).toBeDefined();
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.device?.name).toBe('Test Chiller');
      expect(result.current.points.supply_temp?.value).toBe(18);
    });

    it('should not fetch when autoConnect is false', async () => {
      const { result } = renderHook(
        () => useDeviceControl({ deviceId: 'device-001', autoConnect: false }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.loading).toBe(false);
      expect(result.current.device).toBeNull();
      expect(vi.mocked(api.getDevice)).not.toHaveBeenCalled();
    });

    it('should handle missing deviceId gracefully', async () => {
      const { result } = renderHook(() => useDeviceControl({ autoConnect: true }), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.device).toBeNull();
      expect(result.current.loading).toBe(false);
      expect(vi.mocked(api.getDevice)).not.toHaveBeenCalled();
    });

    it('should handle device fetch errors', async () => {
      const error = new Error('Failed to fetch device');
      vi.mocked(api.getDevice).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useDeviceControl({ deviceId: 'device-001' }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toContain('Failed to fetch device');
      expect(result.current.device).toBeNull();
    });
  });

  describe('Device Control Operations', () => {
    it('should control device with safety validation', async () => {
      const mockDevice = createMockDevice();
      const mockPoints = {
        setpoint: { writable: true, unit: '°C', default_value: 20 },
        supply_temp: { writable: false, unit: '°C', default_value: 0 },
      };

      vi.mocked(api.getDevice).mockResolvedValueOnce(mockDevice);
      vi.mocked(api.getDevicePoints).mockResolvedValueOnce(mockPoints);
      vi.mocked(api.controlDevice).mockResolvedValueOnce({
        success: true,
        device_id: 'device-001',
        point_name: 'setpoint',
        new_value: 22,
        timestamp: new Date().toISOString(),
        cov_verified: true,
      });

      const { result } = renderHook(() => useDeviceControl({ deviceId: 'device-001' }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.device).toBeDefined();
      });

      await act(async () => {
        await result.current.controlDevice('setpoint', 22);
      });

      expect(result.current.points.setpoint?.value).toBe(22);
      expect(result.current.controlling).toBe(false);
    });

    it('should block control when safety status is blocked', async () => {
      const mockDevice = createMockDevice({ metadata: { life_safety: true } });
      const mockPoints = {
        setpoint: { writable: true, unit: '°C', default_value: 20 },
      };

      vi.mocked(api.getDevice).mockResolvedValueOnce(mockDevice);
      vi.mocked(api.getDevicePoints).mockResolvedValueOnce(mockPoints);

      const { result } = renderHook(() => useDeviceControl({ deviceId: 'device-001' }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.device).toBeDefined();
      });

      expect(result.current.safetyStatus.status).toBe('blocked');

      await act(async () => {
        try {
          await result.current.controlDevice('setpoint', 22);
          expect.fail('Should have thrown error');
        } catch (err) {
          expect((err as Error).message).toContain('blocked');
        }
      });
    });

    it('should warn on critical devices', async () => {
      const mockDevice = createMockDevice({ metadata: { critical: true } });
      const mockPoints = {
        setpoint: { writable: true, unit: '°C', default_value: 20 },
      };

      vi.mocked(api.getDevice).mockResolvedValueOnce(mockDevice);
      vi.mocked(api.getDevicePoints).mockResolvedValueOnce(mockPoints);

      const { result } = renderHook(() => useDeviceControl({ deviceId: 'device-001' }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.device).toBeDefined();
      });

      expect(result.current.safetyStatus.status).toBe('warning');
      expect(result.current.safetyStatus.message).toContain('Critical device');
    });

    it('should handle control errors gracefully', async () => {
      const mockDevice = createMockDevice();
      const mockPoints = {
        setpoint: { writable: true, unit: '°C', default_value: 20 },
      };

      vi.mocked(api.getDevice).mockResolvedValueOnce(mockDevice);
      vi.mocked(api.getDevicePoints).mockResolvedValueOnce(mockPoints);
      vi.mocked(api.controlDevice).mockRejectedValueOnce(
        new Error('Device unreachable')
      );

      const { result } = renderHook(() => useDeviceControl({ deviceId: 'device-001' }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.device).toBeDefined();
      });

      await act(async () => {
        try {
          await result.current.controlDevice('setpoint', 22);
          expect.fail('Should have thrown error');
        } catch (err) {
          expect((err as Error).message).toContain('unreachable');
        }
      });

      expect(result.current.controlling).toBe(false);
      expect(result.current.error).toBeTruthy();
    });
  });

  describe('Point Value Operations', () => {
    it('should get point values', async () => {
      const mockDevice = createMockDevice();
      const mockPoints = {
        setpoint: { writable: true, unit: '°C', default_value: 20 },
        supply_temp: { writable: false, unit: '°C', default_value: 0 },
      };

      vi.mocked(api.getDevice).mockResolvedValueOnce(mockDevice);
      vi.mocked(api.getDevicePoints).mockResolvedValueOnce(mockPoints);
      vi.mocked(api.readDevicePoint).mockResolvedValueOnce(
        createMockDeviceValue({ point_name: 'supply_temp', value: 18 })
      );

      const { result } = renderHook(() => useDeviceControl({ deviceId: 'device-001' }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.device).toBeDefined();
      });

      const setpointValue = result.current.getPointValue('setpoint');
      expect(setpointValue).toBe(20);

      const supplyValue = result.current.getPointValue('supply_temp');
      expect(supplyValue).toBe(18);
    });

    it('should return null for nonexistent points', async () => {
      const mockDevice = createMockDevice();
      const mockPoints = {
        setpoint: { writable: true, unit: '°C', default_value: 20 },
      };

      vi.mocked(api.getDevice).mockResolvedValueOnce(mockDevice);
      vi.mocked(api.getDevicePoints).mockResolvedValueOnce(mockPoints);

      const { result } = renderHook(() => useDeviceControl({ deviceId: 'device-001' }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.device).toBeDefined();
      });

      const value = result.current.getPointValue('nonexistent');
      expect(value).toBeNull();
    });

    it('should get writable points', async () => {
      const mockDevice = createMockDevice();
      const mockPoints = {
        setpoint: { writable: true, unit: '°C', default_value: 20 },
        supply_temp: { writable: false, unit: '°C', default_value: 0 },
        status: { writable: false, unit: '', default_value: 'on' },
      };

      vi.mocked(api.getDevice).mockResolvedValueOnce(mockDevice);
      vi.mocked(api.getDevicePoints).mockResolvedValueOnce(mockPoints);

      const { result } = renderHook(() => useDeviceControl({ deviceId: 'device-001' }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.device).toBeDefined();
      });

      const writablePoints = result.current.getWritablePoints();
      expect(writablePoints).toHaveLength(1);
      expect(writablePoints[0].name).toBe('setpoint');
    });

    it('should get readable points', async () => {
      const mockDevice = createMockDevice();
      const mockPoints = {
        setpoint: { writable: true, unit: '°C', default_value: 20 },
        supply_temp: { writable: false, unit: '°C', default_value: 0 },
        status: { writable: false, unit: '', default_value: 'on' },
      };

      vi.mocked(api.getDevice).mockResolvedValueOnce(mockDevice);
      vi.mocked(api.getDevicePoints).mockResolvedValueOnce(mockPoints);

      const { result } = renderHook(() => useDeviceControl({ deviceId: 'device-001' }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.device).toBeDefined();
      });

      const readablePoints = result.current.getReadablePoints();
      expect(readablePoints.length).toBeGreaterThanOrEqual(2);
      expect(readablePoints.some(p => p.name === 'supply_temp')).toBe(true);
    });
  });

  describe('Device Refresh and Polling', () => {
    it('should refresh device on demand', async () => {
      const mockDevice = createMockDevice();
      const mockPoints = {
        setpoint: { writable: true, unit: '°C', default_value: 20 },
      };

      vi.mocked(api.getDevice)
        .mockResolvedValueOnce(mockDevice)
        .mockResolvedValueOnce(mockDevice);
      vi.mocked(api.getDevicePoints)
        .mockResolvedValueOnce(mockPoints)
        .mockResolvedValueOnce(mockPoints);

      const { result } = renderHook(() => useDeviceControl({ deviceId: 'device-001', refreshInterval: 0 }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.device).toBeDefined();
      });

      await act(async () => {
        await result.current.refreshDevice();
      });

      expect(vi.mocked(api.getDevice)).toHaveBeenCalledTimes(2);
    });

    it('should not poll when refreshInterval is 0', async () => {
      const mockDevice = createMockDevice();
      const mockPoints = {
        setpoint: { writable: true, unit: '°C', default_value: 20 },
      };

      vi.mocked(api.getDevice).mockResolvedValueOnce(mockDevice);
      vi.mocked(api.getDevicePoints).mockResolvedValueOnce(mockPoints);

      renderHook(() => useDeviceControl({ deviceId: 'device-001', refreshInterval: 0 }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(vi.mocked(api.getDevice)).toHaveBeenCalledTimes(1);
      });

      // Wait to ensure no additional calls
      await new Promise(resolve => setTimeout(resolve, 100));
      expect(vi.mocked(api.getDevice)).toHaveBeenCalledTimes(1);
    });
  });

  describe('Edge Cases - Phase 68-03', () => {
    it('should handle empty device points gracefully', async () => {
      const mockDevice = createMockDevice({ points: {} });
      const mockPoints = {};

      vi.mocked(api.getDevice).mockResolvedValueOnce(mockDevice);
      vi.mocked(api.getDevicePoints).mockResolvedValueOnce(mockPoints);

      const { result } = renderHook(() => useDeviceControl({ deviceId: 'device-001' }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.device).toBeDefined();
      });

      expect(result.current.getWritablePoints()).toEqual([]);
      expect(result.current.getReadablePoints()).toEqual([]);
    });

    it('should handle device ID changes', async () => {
      const mockDevice1 = createMockDevice({ id: 'device-001', name: 'Chiller 1' });
      const mockDevice2 = createMockDevice({ id: 'device-002', name: 'Chiller 2' });
      const mockPoints = {
        setpoint: { writable: true, unit: '°C', default_value: 20 },
      };

      vi.mocked(api.getDevice)
        .mockResolvedValueOnce(mockDevice1)
        .mockResolvedValueOnce(mockDevice2);
      vi.mocked(api.getDevicePoints)
        .mockResolvedValueOnce(mockPoints)
        .mockResolvedValueOnce(mockPoints);

      const { result } = renderHook(
        ({ deviceId }) => useDeviceControl({ deviceId, autoConnect: true }),
        {
          wrapper: createWrapper(queryClient),
          initialProps: { deviceId: 'device-001' },
        }
      );

      await waitFor(() => {
        expect(result.current.device?.name).toBe('Chiller 1');
      });

      act(() => {
        result.current.setDeviceId('device-002');
      });

      await waitFor(() => {
        expect(result.current.device?.name).toBe('Chiller 2');
      });
    });

    it('should handle rapid successive control operations', async () => {
      const mockDevice = createMockDevice();
      const mockPoints = {
        setpoint: { writable: true, unit: '°C', default_value: 20 },
      };

      vi.mocked(api.getDevice).mockResolvedValueOnce(mockDevice);
      vi.mocked(api.getDevicePoints).mockResolvedValueOnce(mockPoints);
      vi.mocked(api.controlDevice)
        .mockResolvedValueOnce({
          success: true,
          device_id: 'device-001',
          point_name: 'setpoint',
          new_value: 22,
          timestamp: new Date().toISOString(),
          cov_verified: true,
        })
        .mockResolvedValueOnce({
          success: true,
          device_id: 'device-001',
          point_name: 'setpoint',
          new_value: 24,
          timestamp: new Date().toISOString(),
          cov_verified: true,
        });

      const { result } = renderHook(() => useDeviceControl({ deviceId: 'device-001' }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.device).toBeDefined();
      });

      await act(async () => {
        await result.current.controlDevice('setpoint', 22);
        await result.current.controlDevice('setpoint', 24);
      });

      expect(result.current.points.setpoint?.value).toBe(24);
      expect(vi.mocked(api.controlDevice)).toHaveBeenCalledTimes(2);
    });
  });
});

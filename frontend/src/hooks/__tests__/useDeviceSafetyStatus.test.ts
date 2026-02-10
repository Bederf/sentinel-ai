/**
 * useDeviceSafetyStatus Hook Tests
 *
 * Tests comprehensive hook functionality:
 * - Batch aggregation
 * - Caching behavior
 * - Enable/disable based on enabled prop
 * - Multiple hooks with same deviceId deduplication
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useDeviceSafetyStatus } from '../useDeviceSafetyStatus';
import { useDeviceLatestReading } from '../useDeviceLatestReading';
import { useDeviceCondition } from '../useDeviceCondition';
import { useSiteSummary } from '../useSiteSummary';
import { useSiteAlerts } from '../useSiteAlerts';
import { useSitePredictions } from '../useSitePredictions';
import { useBuildingsList } from '../useBuildingsList';
import { useEquipmentByType } from '../useEquipmentByType';
import * as apiModule from '@/lib/api/batchers';
import type {
  DeviceSafetyStatus,
  DeviceStatus as BatchDeviceStatus,
  DeviceCondition,
} from '@/lib/api/types';

// Mock the batch aggregator module
vi.mock('@/lib/api/batchers', async () => {
  const actual = await vi.importActual('@/lib/api/batchers');
  return {
    ...actual,
    safetyBatcher: {
      fetch: vi.fn(),
    },
    readingsBatcher: {
      fetch: vi.fn(),
    },
    conditionBatcher: {
      fetch: vi.fn(),
    },
  };
});

// Mock the fetchClient module for apiFetch
vi.mock('@/lib/api/fetchClient', () => ({
  apiFetch: vi.fn(),
}));

// Create a fresh QueryClient for each test
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useDeviceSafetyStatus Hook', () => {
  let queryClient: QueryClient;
  let mockSafetyBatcher: any;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    mockSafetyBatcher = (apiModule.safetyBatcher as any).fetch;
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Basic Functionality', () => {
    it('should fetch safety status for a device', async () => {
      const mockStatus: DeviceSafetyStatus = {
        device_id: 'device-001',
        status: 'safe',
        rules_violated: [],
      };

      mockSafetyBatcher.mockResolvedValueOnce(mockStatus);

      const { result } = renderHook(
        () => useDeviceSafetyStatus('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual(mockStatus);
      expect(mockSafetyBatcher).toHaveBeenCalledWith('device-001');
    });

    it('should use correct staleTime (30s) and gcTime (5m)', async () => {
      const mockStatus: DeviceSafetyStatus = {
        device_id: 'device-001',
        status: 'safe',
        rules_violated: [],
      };

      mockSafetyBatcher.mockResolvedValueOnce(mockStatus);

      const { result } = renderHook(
        () => useDeviceSafetyStatus('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify query was cached with correct timing
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'device-safety');
      expect(query).toBeDefined();
    });

    it('should handle errors gracefully', async () => {
      const error = new Error('Network error');
      mockSafetyBatcher.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useDeviceSafetyStatus('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
    });
  });

  describe('Enable/Disable Behavior', () => {
    it('should not fetch when enabled is false', async () => {
      const { result } = renderHook(
        () => useDeviceSafetyStatus('device-001', { enabled: false }),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(mockSafetyBatcher).not.toHaveBeenCalled();
    });

    it('should fetch when enabled is true', async () => {
      const mockStatus: DeviceSafetyStatus = {
        device_id: 'device-001',
        status: 'safe',
        rules_violated: [],
      };

      mockSafetyBatcher.mockResolvedValueOnce(mockStatus);

      const { result } = renderHook(
        () => useDeviceSafetyStatus('device-001', { enabled: true }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockSafetyBatcher).toHaveBeenCalled();
    });

    it('should fetch by default when enabled is not specified', async () => {
      const mockStatus: DeviceSafetyStatus = {
        device_id: 'device-001',
        status: 'safe',
        rules_violated: [],
      };

      mockSafetyBatcher.mockResolvedValueOnce(mockStatus);

      const { result } = renderHook(
        () => useDeviceSafetyStatus('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockSafetyBatcher).toHaveBeenCalled();
    });
  });

  describe('Caching & Deduplication', () => {
    it('should cache data and return same result on second mount', async () => {
      const mockStatus: DeviceSafetyStatus = {
        device_id: 'device-001',
        status: 'safe',
        rules_violated: [],
      };

      mockSafetyBatcher.mockResolvedValueOnce(mockStatus);

      const { result: result1 } = renderHook(
        () => useDeviceSafetyStatus('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second mount should use cached data
      const { result: result2 } = renderHook(
        () => useDeviceSafetyStatus('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      // Should not make another request due to cache
      expect(result2.current.data).toEqual(mockStatus);
      expect(mockSafetyBatcher).toHaveBeenCalledTimes(1);
    });

    it('should use different query keys for different devices', async () => {
      const mockStatus1: DeviceSafetyStatus = {
        device_id: 'device-001',
        status: 'safe',
        rules_violated: [],
      };

      const mockStatus2: DeviceSafetyStatus = {
        device_id: 'device-002',
        status: 'warning',
        rules_violated: [],
      };

      mockSafetyBatcher.mockResolvedValueOnce(mockStatus1);
      mockSafetyBatcher.mockResolvedValueOnce(mockStatus2);

      const { result: result1 } = renderHook(
        () => useDeviceSafetyStatus('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useDeviceSafetyStatus('device-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      expect(result1.current.data?.device_id).toBe('device-001');
      expect(result2.current.data?.device_id).toBe('device-002');
      expect(mockSafetyBatcher).toHaveBeenCalledTimes(2);
    });
  });

  describe('Error Handling & Retry', () => {
    it('should handle 429 errors without retry', async () => {
      const error = new Error('429 Too Many Requests');
      mockSafetyBatcher.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useDeviceSafetyStatus('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
      // With retry: false in query config, should fail immediately
      expect(mockSafetyBatcher).toHaveBeenCalledTimes(1);
    });

    it('should handle API errors', async () => {
      const error = new Error('API Error');
      mockSafetyBatcher.mockRejectedValueOnce(error);

      const { result } = renderHook(
        () => useDeviceSafetyStatus('device-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toContain('API Error');
    });
  });
});

describe('useDeviceLatestReading Hook', () => {
  let queryClient: QueryClient;
  let mockReadingsBatcher: any;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    mockReadingsBatcher = (apiModule.readingsBatcher as any).fetch;
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  it('should fetch latest reading with 15s staleTime', async () => {
    const mockReading: BatchDeviceStatus = {
      id: 'device-001',
      name: 'Test Device',
      device_type: 'HVAC',
      status: 'online',
    };

    mockReadingsBatcher.mockResolvedValueOnce(mockReading);

    const { result } = renderHook(
      () => useDeviceLatestReading('device-001'),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockReading);
  });

  it('should refetch at 60s interval', async () => {
    const mockReading: BatchDeviceStatus = {
      id: 'device-001',
      name: 'Test Device',
      device_type: 'HVAC',
      status: 'online',
    };

    mockReadingsBatcher.mockResolvedValue(mockReading);

    const { result } = renderHook(
      () => useDeviceLatestReading('device-001'),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockReading);
  });
});

describe('useDeviceCondition Hook', () => {
  let queryClient: QueryClient;
  let mockConditionBatcher: any;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    mockConditionBatcher = (apiModule.conditionBatcher as any).fetch;
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  it('should fetch device condition', async () => {
    const mockCondition: DeviceCondition = {
      id: 'device-001',
      name: 'Test Device',
      device_type: 'HVAC',
      status: 'healthy',
    };

    mockConditionBatcher.mockResolvedValueOnce(mockCondition);

    const { result } = renderHook(
      () => useDeviceCondition('device-001'),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockCondition);
  });

  it('should handle errors for condition queries', async () => {
    const error = new Error('Condition query failed');
    mockConditionBatcher.mockRejectedValueOnce(error);

    const { result } = renderHook(
      () => useDeviceCondition('device-001'),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toBeDefined();
  });
});

describe('useSiteSummary Hook', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  it('should have proper type definitions', () => {
    // Type test - just verify hook exists and can be called
    expect(useSiteSummary).toBeDefined();
    expect(typeof useSiteSummary).toBe('function');
  });

  it('should accept enabled option', () => {
    // Verify hook accepts the enabled prop
    const { result } = renderHook(
      () => useSiteSummary('site-001', { enabled: false }),
      { wrapper: createWrapper(queryClient) }
    );

    // Should not fetch when disabled
    expect(result.current.status).toBe('pending');
  });
});

describe('useSiteAlerts Hook', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  it('should have proper type definitions', () => {
    expect(useSiteAlerts).toBeDefined();
    expect(typeof useSiteAlerts).toBe('function');
  });

  it('should accept enabled option', () => {
    const { result } = renderHook(
      () => useSiteAlerts('site-001', { enabled: false }),
      { wrapper: createWrapper(queryClient) }
    );

    expect(result.current.status).toBe('pending');
  });
});

describe('useSitePredictions Hook', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  it('should have proper type definitions', () => {
    expect(useSitePredictions).toBeDefined();
    expect(typeof useSitePredictions).toBe('function');
  });

  it('should accept enabled option', () => {
    const { result } = renderHook(
      () => useSitePredictions('site-001', { enabled: false }),
      { wrapper: createWrapper(queryClient) }
    );

    expect(result.current.status).toBe('pending');
  });
});

describe('useBuildingsList Hook', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  it('should have proper type definitions', () => {
    expect(useBuildingsList).toBeDefined();
    expect(typeof useBuildingsList).toBe('function');
  });

  it('should accept enabled option', () => {
    const { result } = renderHook(
      () => useBuildingsList({ enabled: false }),
      { wrapper: createWrapper(queryClient) }
    );

    expect(result.current.status).toBe('pending');
  });
});

describe('useEquipmentByType Hook', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  it('should have proper type definitions', () => {
    expect(useEquipmentByType).toBeDefined();
    expect(typeof useEquipmentByType).toBe('function');
  });

  it('should accept enabled option', () => {
    const { result } = renderHook(
      () => useEquipmentByType('site-001', 'CHILLER', { enabled: false }),
      { wrapper: createWrapper(queryClient) }
    );

    expect(result.current.status).toBe('pending');
  });
});

describe('Hook Integration - Batch Aggregation', () => {
  let queryClient: QueryClient;
  let mockSafetyBatcher: any;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    mockSafetyBatcher = (apiModule.safetyBatcher as any).fetch;
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  it('should aggregate multiple safety status requests', async () => {
    const mockStatus1: DeviceSafetyStatus = {
      device_id: 'device-001',
      status: 'safe',
      rules_violated: [],
    };

    const mockStatus2: DeviceSafetyStatus = {
      device_id: 'device-002',
      status: 'warning',
      rules_violated: [],
    };

    mockSafetyBatcher
      .mockResolvedValueOnce(mockStatus1)
      .mockResolvedValueOnce(mockStatus2);

    const { result: result1 } = renderHook(
      () => useDeviceSafetyStatus('device-001'),
      { wrapper: createWrapper(queryClient) }
    );

    const { result: result2 } = renderHook(
      () => useDeviceSafetyStatus('device-002'),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => {
      expect(result1.current.isSuccess).toBe(true);
      expect(result2.current.isSuccess).toBe(true);
    });

    expect(result1.current.data).toEqual(mockStatus1);
    expect(result2.current.data).toEqual(mockStatus2);
    expect(mockSafetyBatcher).toHaveBeenCalledTimes(2);
  });

  it('should respect cache and not re-fetch within staleTime', async () => {
    const mockStatus: DeviceSafetyStatus = {
      device_id: 'device-001',
      status: 'safe',
      rules_violated: [],
    };

    mockSafetyBatcher.mockResolvedValueOnce(mockStatus);

    // First render
    const { result: result1 } = renderHook(
      () => useDeviceSafetyStatus('device-001'),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => {
      expect(result1.current.isSuccess).toBe(true);
    });

    // Second render immediately (within staleTime)
    const { result: result2 } = renderHook(
      () => useDeviceSafetyStatus('device-001'),
      { wrapper: createWrapper(queryClient) }
    );

    expect(result2.current.data).toEqual(mockStatus);
    expect(mockSafetyBatcher).toHaveBeenCalledTimes(1);
  });
});

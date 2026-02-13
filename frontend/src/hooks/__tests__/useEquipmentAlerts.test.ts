/**
 * useEquipmentAlerts Hook Tests
 *
 * Tests equipment-specific alert history fetching:
 * - Fetch alerts for specific equipment
 * - Severity filtering (critical, warning, medium, low)
 * - Status tracking (active, acknowledged, resolved)
 * - Limit parameter (pagination)
 * - Caching behavior (30s staleTime, 3m gcTime)
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useEquipmentAlerts } from '../useEquipmentHistory';
import type { EquipmentAlert } from '@/lib/api/equipment_history';

vi.mock('@/lib/api/equipment_history', () => ({
  equipmentHistoryApi: {
    getAlerts: vi.fn(),
  },
}));

import { equipmentHistoryApi } from '@/lib/api/equipment_history';

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

// ============= Mock Factories =============

function createMockAlert(overrides?: Partial<EquipmentAlert>): EquipmentAlert {
  return {
    id: 'alert-001',
    title: 'High Temperature Warning',
    message: 'Equipment temperature exceeds safe threshold',
    severity: 'warning',
    status: 'active',
    created_at: '2026-02-12T10:00:00Z',
    acknowledged_at: undefined,
    resolved_at: undefined,
    ...overrides,
  };
}

function createMockAlertList(count: number = 10): EquipmentAlert[] {
  const severities: EquipmentAlert['severity'][] = ['critical', 'warning', 'medium', 'low', 'warning'];
  const statuses: EquipmentAlert['status'][] = ['active', 'acknowledged', 'resolved', 'active', 'acknowledged'];

  return Array.from({ length: count }, (_, i) => ({
    ...createMockAlert(),
    id: `alert-${String(i + 1).padStart(3, '0')}`,
    title: `Alert ${i + 1}`,
    severity: severities[i % severities.length],
    status: statuses[i % statuses.length],
    created_at: new Date(2026, 1, 12 - Math.floor(i / 2)).toISOString(),
    acknowledged_at: [1, 3].includes(i % 5) ? new Date(2026, 1, 12 - Math.floor(i / 2), 1).toISOString() : undefined,
    resolved_at: [2, 4].includes(i % 5) ? new Date(2026, 1, 12 - Math.floor(i / 2), 2).toISOString() : undefined,
  }));
}

describe('useEquipmentAlerts Hook', () => {
  let queryClient: QueryClient;
  let mockGetAlerts: any;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    mockGetAlerts = vi.mocked(equipmentHistoryApi.getAlerts);
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Data Fetching', () => {
    it('should fetch alerts for specific equipment', async () => {
      const mockData = createMockAlertList(5);
      mockGetAlerts.mockResolvedValueOnce(mockData);

      const equipmentId = 'equipment-001';
      const { result } = renderHook(
        () => useEquipmentAlerts(equipmentId, 10),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockData);
      expect(mockGetAlerts).toHaveBeenCalledWith(equipmentId, 10);
    });

    it('should respect limit parameter (pagination)', async () => {
      const mockData = createMockAlertList(5);
      mockGetAlerts.mockResolvedValueOnce(mockData);

      const equipmentId = 'equipment-001';
      const limit = 5;
      const { result } = renderHook(
        () => useEquipmentAlerts(equipmentId, limit),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockGetAlerts).toHaveBeenCalledWith(equipmentId, limit);
      expect(result.current.data).toHaveLength(5);
    });

    it('should filter by severity levels', async () => {
      const mockData = [
        createMockAlert({ severity: 'critical' }),
        createMockAlert({ severity: 'warning' }),
        createMockAlert({ severity: 'medium' }),
        createMockAlert({ severity: 'low' }),
      ];
      mockGetAlerts.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useEquipmentAlerts('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const alerts = result.current.data;
      expect(alerts?.[0].severity).toBe('critical');
      expect(alerts?.[1].severity).toBe('warning');
      expect(alerts?.[2].severity).toBe('medium');
      expect(alerts?.[3].severity).toBe('low');
    });

    it('should track status states correctly', async () => {
      const mockData = [
        createMockAlert({ status: 'active' }),
        createMockAlert({ status: 'acknowledged' }),
        createMockAlert({ status: 'resolved' }),
      ];
      mockGetAlerts.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useEquipmentAlerts('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const alerts = result.current.data;
      expect(alerts?.[0].status).toBe('active');
      expect(alerts?.[1].status).toBe('acknowledged');
      expect(alerts?.[2].status).toBe('resolved');
    });

    it('should handle empty results (no alerts)', async () => {
      mockGetAlerts.mockResolvedValueOnce([]);

      const { result } = renderHook(
        () => useEquipmentAlerts('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual([]);
    });

    it('should parse alert timestamps', async () => {
      const createdAt = '2026-02-12T10:00:00Z';
      const acknowledgedAt = '2026-02-12T10:15:00Z';
      const resolvedAt = '2026-02-12T11:00:00Z';

      const mockData = [
        createMockAlert({
          created_at: createdAt,
          acknowledged_at: acknowledgedAt,
          resolved_at: resolvedAt,
          status: 'resolved',
        }),
      ];
      mockGetAlerts.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useEquipmentAlerts('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const alert = result.current.data?.[0];
      expect(alert?.created_at).toBe(createdAt);
      expect(alert?.acknowledged_at).toBe(acknowledgedAt);
      expect(alert?.resolved_at).toBe(resolvedAt);
    });

    it('should handle alerts with missing optional timestamps', async () => {
      const mockData = [
        createMockAlert({
          status: 'active',
          acknowledged_at: undefined,
          resolved_at: undefined,
        }),
      ];
      mockGetAlerts.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useEquipmentAlerts('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const alert = result.current.data?.[0];
      expect(alert?.acknowledged_at).toBeUndefined();
      expect(alert?.resolved_at).toBeUndefined();
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors gracefully', async () => {
      mockGetAlerts.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(
        () => useEquipmentAlerts('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
    });

    it('should handle API timeouts', async () => {
      mockGetAlerts.mockRejectedValueOnce(new Error('Request timeout'));

      const { result } = renderHook(
        () => useEquipmentAlerts('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });
    });

    it('should handle 429 rate limit errors', async () => {
      mockGetAlerts.mockRejectedValueOnce(new Error('Rate limit exceeded'));

      const { result } = renderHook(
        () => useEquipmentAlerts('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });
    });
  });

  describe('Caching Behavior', () => {
    it('should cache alerts with 30s stale time', async () => {
      const mockData = createMockAlertList(3);
      mockGetAlerts.mockResolvedValueOnce(mockData);

      const equipmentId = 'equipment-001';
      const { result: result1 } = renderHook(
        () => useEquipmentAlerts(equipmentId),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second render with same equipment ID should use cache
      const { result: result2 } = renderHook(
        () => useEquipmentAlerts(equipmentId),
        { wrapper: createWrapper(queryClient) }
      );

      // Should not trigger additional API call within stale time
      expect(mockGetAlerts).toHaveBeenCalledTimes(1);
      expect(result2.current.data).toEqual(mockData);
    });

    it('should refetch when equipment ID changes', async () => {
      const mockData1 = [createMockAlert({ id: 'alert-001' })];
      const mockData2 = [createMockAlert({ id: 'alert-002' })];

      mockGetAlerts
        .mockResolvedValueOnce(mockData1)
        .mockResolvedValueOnce(mockData2);

      const { rerender, result } = renderHook(
        ({ equipmentId }) => useEquipmentAlerts(equipmentId),
        {
          initialProps: { equipmentId: 'equipment-001' },
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.[0].id).toBe('alert-001');

      // Change equipment ID
      rerender({ equipmentId: 'equipment-002' });

      await waitFor(() => {
        expect(result.current.data?.[0].id).toBe('alert-002');
      });

      expect(mockGetAlerts).toHaveBeenCalledTimes(2);
    });
  });

  describe('Enable/Disable Logic', () => {
    it('should not fetch when equipment ID is empty', () => {
      const { result } = renderHook(
        () => useEquipmentAlerts(''),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(false);
      expect(mockGetAlerts).not.toHaveBeenCalled();
    });

    it('should fetch when equipment ID becomes available', async () => {
      const mockData = createMockAlertList(1);
      mockGetAlerts.mockResolvedValueOnce(mockData);

      const { rerender, result } = renderHook(
        ({ equipmentId }) => useEquipmentAlerts(equipmentId),
        {
          initialProps: { equipmentId: '' },
          wrapper: createWrapper(queryClient),
        }
      );

      expect(mockGetAlerts).not.toHaveBeenCalled();

      rerender({ equipmentId: 'equipment-001' });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockGetAlerts).toHaveBeenCalledWith('equipment-001', 10);
    });
  });

  describe('Default Values', () => {
    it('should use default limit of 10 when not specified', async () => {
      const mockData = createMockAlertList(10);
      mockGetAlerts.mockResolvedValueOnce(mockData);

      renderHook(
        () => useEquipmentAlerts('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockGetAlerts).toHaveBeenCalledWith('equipment-001', 10);
      });
    });

    it('should accept custom limit parameter', async () => {
      const mockData = createMockAlertList(20);
      mockGetAlerts.mockResolvedValueOnce(mockData);

      renderHook(
        () => useEquipmentAlerts('equipment-001', 20),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockGetAlerts).toHaveBeenCalledWith('equipment-001', 20);
      });
    });
  });
});

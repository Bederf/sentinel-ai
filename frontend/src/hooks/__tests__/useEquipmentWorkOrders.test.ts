/**
 * useEquipmentWorkOrders Hook Tests
 *
 * Tests equipment work order history fetching:
 * - Fetch work orders for specific equipment
 * - Filtering by equipment ID
 * - Limit parameter (pagination)
 * - Status field mapping (scheduled, assigned, in_progress, completed)
 * - Priority level display
 * - Caching behavior (60s staleTime, 5m gcTime)
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useEquipmentWorkOrders } from '../useEquipmentHistory';
import type { WorkOrder } from '@/lib/api/equipment_history';

vi.mock('@/lib/api/equipment_history', () => ({
  equipmentHistoryApi: {
    getWorkOrders: vi.fn(),
  },
}));

import { equipmentHistoryApi } from '@/lib/api/equipment_history';

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

function createMockWorkOrder(overrides?: Partial<WorkOrder>): WorkOrder {
  return {
    id: 'wo-001',
    code: 'WO-2026-0001',
    title: 'Filter Replacement',
    description: 'Replace HVAC filter',
    priority: 'high',
    status: 'completed',
    assigned_to: 'hvac-team',
    technician_name: 'John Smith',
    created_at: '2026-02-10T10:00:00Z',
    completed_at: '2026-02-12T14:30:00Z',
    updated_at: '2026-02-12T14:30:00Z',
    ...overrides,
  };
}

function createMockWorkOrderList(count: number = 5): WorkOrder[] {
  const statuses: WorkOrder['status'][] = ['scheduled', 'assigned', 'in_progress', 'completed', 'completed'];
  const priorities: WorkOrder['priority'][] = ['low', 'medium', 'high', 'high', 'urgent'];

  return Array.from({ length: count }, (_, i) => ({
    ...createMockWorkOrder(),
    id: `wo-${String(i + 1).padStart(3, '0')}`,
    code: `WO-2026-${String(i + 1).padStart(4, '0')}`,
    title: `Work Order ${i + 1}`,
    status: statuses[i % statuses.length],
    priority: priorities[i % priorities.length],
    created_at: new Date(2026, 1, 10 - i).toISOString(),
  }));
}

describe('useEquipmentWorkOrders Hook', () => {
  let queryClient: QueryClient;
  let mockGetWorkOrders: any;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    mockGetWorkOrders = vi.mocked(equipmentHistoryApi.getWorkOrders);
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Data Fetching', () => {
    it('should fetch work orders for specific equipment', async () => {
      const mockData = createMockWorkOrderList(3);
      mockGetWorkOrders.mockResolvedValueOnce(mockData);

      const equipmentId = 'equipment-001';
      const { result } = renderHook(
        () => useEquipmentWorkOrders(equipmentId, 10),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockData);
      expect(mockGetWorkOrders).toHaveBeenCalledWith(equipmentId, 10);
    });

    it('should respect limit parameter (pagination)', async () => {
      const mockData = createMockWorkOrderList(5);
      mockGetWorkOrders.mockResolvedValueOnce(mockData);

      const equipmentId = 'equipment-001';
      const limit = 5;
      const { result } = renderHook(
        () => useEquipmentWorkOrders(equipmentId, limit),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockGetWorkOrders).toHaveBeenCalledWith(equipmentId, limit);
      expect(result.current.data).toHaveLength(5);
    });

    it('should map status fields correctly', async () => {
      const mockData = [
        createMockWorkOrder({ status: 'scheduled' }),
        createMockWorkOrder({ status: 'assigned' }),
        createMockWorkOrder({ status: 'in_progress' }),
        createMockWorkOrder({ status: 'completed' }),
      ];
      mockGetWorkOrders.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useEquipmentWorkOrders('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const workOrders = result.current.data;
      expect(workOrders?.[0].status).toBe('scheduled');
      expect(workOrders?.[1].status).toBe('assigned');
      expect(workOrders?.[2].status).toBe('in_progress');
      expect(workOrders?.[3].status).toBe('completed');
    });

    it('should display priority level correctly', async () => {
      const mockData = [
        createMockWorkOrder({ priority: 'low' }),
        createMockWorkOrder({ priority: 'medium' }),
        createMockWorkOrder({ priority: 'high' }),
        createMockWorkOrder({ priority: 'urgent' }),
      ];
      mockGetWorkOrders.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useEquipmentWorkOrders('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const workOrders = result.current.data;
      expect(workOrders?.[0].priority).toBe('low');
      expect(workOrders?.[1].priority).toBe('medium');
      expect(workOrders?.[2].priority).toBe('high');
      expect(workOrders?.[3].priority).toBe('urgent');
    });

    it('should handle empty results (no work orders)', async () => {
      mockGetWorkOrders.mockResolvedValueOnce([]);

      const { result } = renderHook(
        () => useEquipmentWorkOrders('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual([]);
    });

    it('should include technician assignment info', async () => {
      const mockData = [
        createMockWorkOrder({
          assigned_to: 'hvac-team',
          technician_name: 'John Smith',
        }),
        createMockWorkOrder({
          assigned_to: 'electrical-team',
          technician_name: 'Jane Doe',
        }),
      ];
      mockGetWorkOrders.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useEquipmentWorkOrders('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const workOrders = result.current.data;
      expect(workOrders?.[0].technician_name).toBe('John Smith');
      expect(workOrders?.[1].technician_name).toBe('Jane Doe');
    });

    it('should parse completion timestamps', async () => {
      const completedAt = '2026-02-12T14:30:00Z';
      const mockData = [
        createMockWorkOrder({
          status: 'completed',
          completed_at: completedAt,
        }),
      ];
      mockGetWorkOrders.mockResolvedValueOnce(mockData);

      const { result } = renderHook(
        () => useEquipmentWorkOrders('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.[0].completed_at).toBe(completedAt);
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors gracefully', async () => {
      mockGetWorkOrders.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(
        () => useEquipmentWorkOrders('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
    });

    it('should handle API timeouts', async () => {
      mockGetWorkOrders.mockRejectedValueOnce(new Error('Request timeout'));

      const { result } = renderHook(
        () => useEquipmentWorkOrders('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });
    });
  });

  describe('Caching Behavior', () => {
    it('should cache work orders with 60s stale time', async () => {
      const mockData = createMockWorkOrderList(3);
      mockGetWorkOrders.mockResolvedValueOnce(mockData);

      const equipmentId = 'equipment-001';
      const { result: result1 } = renderHook(
        () => useEquipmentWorkOrders(equipmentId),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second render with same equipment ID should use cache
      const { result: result2 } = renderHook(
        () => useEquipmentWorkOrders(equipmentId),
        { wrapper: createWrapper(queryClient) }
      );

      // Should not trigger additional API call within stale time
      expect(mockGetWorkOrders).toHaveBeenCalledTimes(1);
      expect(result2.current.data).toEqual(mockData);
    });

    it('should refetch when equipment ID changes', async () => {
      const mockData1 = [createMockWorkOrder({ id: 'wo-001' })];
      const mockData2 = [createMockWorkOrder({ id: 'wo-002' })];

      mockGetWorkOrders
        .mockResolvedValueOnce(mockData1)
        .mockResolvedValueOnce(mockData2);

      const { rerender, result } = renderHook(
        ({ equipmentId }) => useEquipmentWorkOrders(equipmentId),
        {
          initialProps: { equipmentId: 'equipment-001' },
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.[0].id).toBe('wo-001');

      // Change equipment ID
      rerender({ equipmentId: 'equipment-002' });

      await waitFor(() => {
        expect(result.current.data?.[0].id).toBe('wo-002');
      });

      expect(mockGetWorkOrders).toHaveBeenCalledTimes(2);
    });
  });

  describe('Enable/Disable Logic', () => {
    it('should not fetch when equipment ID is empty', () => {
      const { result } = renderHook(
        () => useEquipmentWorkOrders(''),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result.current.isLoading).toBe(false);
      expect(mockGetWorkOrders).not.toHaveBeenCalled();
    });

    it('should fetch when equipment ID becomes available', async () => {
      const mockData = createMockWorkOrderList(1);
      mockGetWorkOrders.mockResolvedValueOnce(mockData);

      const { rerender, result } = renderHook(
        ({ equipmentId }) => useEquipmentWorkOrders(equipmentId),
        {
          initialProps: { equipmentId: '' },
          wrapper: createWrapper(queryClient),
        }
      );

      expect(mockGetWorkOrders).not.toHaveBeenCalled();

      rerender({ equipmentId: 'equipment-001' });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockGetWorkOrders).toHaveBeenCalledWith('equipment-001', 10);
    });
  });

  describe('Default Values', () => {
    it('should use default limit of 10 when not specified', async () => {
      const mockData = createMockWorkOrderList(10);
      mockGetWorkOrders.mockResolvedValueOnce(mockData);

      renderHook(
        () => useEquipmentWorkOrders('equipment-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockGetWorkOrders).toHaveBeenCalledWith('equipment-001', 10);
      });
    });

    it('should accept custom limit parameter', async () => {
      const mockData = createMockWorkOrderList(20);
      mockGetWorkOrders.mockResolvedValueOnce(mockData);

      renderHook(
        () => useEquipmentWorkOrders('equipment-001', 20),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(mockGetWorkOrders).toHaveBeenCalledWith('equipment-001', 20);
      });
    });
  });
});

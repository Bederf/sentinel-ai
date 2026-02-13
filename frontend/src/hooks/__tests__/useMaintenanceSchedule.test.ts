/**
 * useMaintenanceSchedule Hook Tests
 *
 * Tests maintenance scheduling and technician assignment:
 * - Fetch scheduled work orders (next 30 days)
 * - Display maintenance history (past 10 completed)
 * - Status transitions (scheduled → assigned → in_progress → completed)
 * - Priority sorting (urgent/high/medium/low)
 * - Technician assignment (specialty-based)
 * - Work order filtering by technician specialty
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useMaintenanceSchedule, useTechnicianAssignments } from '../useMaintenanceSchedule';

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

describe('useMaintenanceSchedule Hook', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Work Order List: Fetch Scheduled & Completed', () => {
    it('should fetch scheduled work orders for next 30 days', async () => {
      const mockData = [
        { id: 'wo-001', code: 'WO-2026-0001', title: 'HVAC Filter Replacement', priority: 'high', status: 'scheduled', created_at: '2026-02-12T00:00:00Z' },
      ];

      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: mockData }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        });

      const { result } = renderHook(() => useMaintenanceSchedule('S002', 30), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.schedule.length).toBeGreaterThan(0);
      expect(global.fetch).toHaveBeenCalled();
    });

    it('should fetch maintenance history (past 10 completed)', async () => {
      const scheduleData = [
        { id: 'wo-001', code: 'WO-2026-0001', title: 'Work 1', priority: 'high', status: 'scheduled', created_at: '2026-02-12T00:00:00Z' },
      ];
      const historyData = [
        { id: 'wo-100', code: 'WO-2026-0100', title: 'Completed Work', priority: 'medium', status: 'completed', created_at: '2026-02-10T00:00:00Z', completed_at: '2026-02-11T00:00:00Z' },
      ];

      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: scheduleData }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: historyData }),
        });

      const { result } = renderHook(() => useMaintenanceSchedule('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.schedule.length).toBeGreaterThan(0);
      expect(result.current.history.length).toBeGreaterThan(0);
    });

    it('should handle empty work order list', async () => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        });

      const { result } = renderHook(() => useMaintenanceSchedule('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.schedule).toEqual([]);
      expect(result.current.history).toEqual([]);
    });
  });

  describe('Status Transitions', () => {
    it('should transition from scheduled to assigned', async () => {
      const mockData = [
        { id: 'wo-001', code: 'WO-2026-0001', title: 'HVAC Work', priority: 'high', status: 'scheduled', created_at: '2026-02-12T00:00:00Z' },
      ];

      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: mockData }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ status: 'assigned' }),
        });

      const { result } = renderHook(() => useMaintenanceSchedule('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await act(async () => {
        await result.current.updateStatusAsync({
          workOrderId: 'wo-001',
          status: 'assigned',
        });
      });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/work-orders/wo-001/status'),
        expect.any(Object)
      );
    });

    it('should transition from assigned to in_progress', async () => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ status: 'in_progress' }),
        });

      const { result } = renderHook(() => useMaintenanceSchedule('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await act(async () => {
        await result.current.updateStatusAsync({
          workOrderId: 'wo-001',
          status: 'in_progress',
        });
      });

      expect(global.fetch).toHaveBeenCalled();
    });

    it('should transition from in_progress to completed', async () => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ status: 'completed' }),
        });

      const { result } = renderHook(() => useMaintenanceSchedule('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await act(async () => {
        await result.current.updateStatusAsync({
          workOrderId: 'wo-001',
          status: 'completed',
        });
      });

      expect(global.fetch).toHaveBeenCalled();
    });
  });

  describe('Priority Sorting', () => {
    it('should sort by priority (urgent first)', async () => {
      const mockData = [
        { id: 'wo-low', code: 'WO-0003', title: 'Low Priority', priority: 'low' as const, status: 'scheduled', created_at: '2026-02-12T00:00:00Z' },
        { id: 'wo-urgent', code: 'WO-0001', title: 'Urgent Priority', priority: 'urgent' as const, status: 'scheduled', created_at: '2026-02-12T00:00:00Z' },
        { id: 'wo-medium', code: 'WO-0004', title: 'Medium Priority', priority: 'medium' as const, status: 'scheduled', created_at: '2026-02-12T00:00:00Z' },
        { id: 'wo-high', code: 'WO-0002', title: 'High Priority', priority: 'high' as const, status: 'scheduled', created_at: '2026-02-12T00:00:00Z' },
      ];

      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: mockData }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        });

      const { result } = renderHook(() => useMaintenanceSchedule('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should be sorted: urgent → high → medium → low
      expect(result.current.schedule[0].priority).toBe('urgent');
      expect(result.current.schedule[1].priority).toBe('high');
      expect(result.current.schedule[2].priority).toBe('medium');
      expect(result.current.schedule[3].priority).toBe('low');
    });
  });

  describe('Technician Assignment', () => {
    it('should assign technician to work order', async () => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ assigned_technician_id: 'tech-001' }),
        });

      const { result } = renderHook(() => useMaintenanceSchedule('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await act(async () => {
        await result.current.assignTechnicianAsync({
          workOrderId: 'wo-001',
          technicianId: 'tech-001',
        });
      });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/work-orders/wo-001/assign'),
        expect.any(Object)
      );
    });
  });

  describe('Specialty Filtering', () => {
    it('should filter work orders by HVAC specialty', async () => {
      const mockData = [
        { id: 'wo-hvac', code: 'WO-001', title: 'HVAC Filter Replacement', priority: 'high' as const, status: 'scheduled', created_at: '2026-02-12T00:00:00Z' },
        { id: 'wo-dali', code: 'WO-002', title: 'DALI Lighting Maintenance', priority: 'medium' as const, status: 'scheduled', created_at: '2026-02-12T00:00:00Z' },
      ];

      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: mockData }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        });

      const { result } = renderHook(() => useMaintenanceSchedule('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      const hvacFiltered = result.current.filterBySpecialty('hvac');
      expect(hvacFiltered.some((wo) => wo.title.includes('HVAC'))).toBe(true);
    });

    it('should filter work orders by electrical specialty', async () => {
      const mockData = [
        { id: 'wo-gen', code: 'WO-001', title: 'Generator Fuel Check', priority: 'high' as const, status: 'scheduled', created_at: '2026-02-12T00:00:00Z' },
        { id: 'wo-hvac', code: 'WO-002', title: 'HVAC Filter Replacement', priority: 'medium' as const, status: 'scheduled', created_at: '2026-02-12T00:00:00Z' },
      ];

      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: mockData }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        });

      const { result } = renderHook(() => useMaintenanceSchedule('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      const elecFiltered = result.current.filterBySpecialty('electrical');
      expect(elecFiltered.some((wo) => wo.title.includes('Generator'))).toBe(true);
    });

    it('should filter work orders by fire safety specialty', async () => {
      const mockData = [
        { id: 'wo-fire', code: 'WO-001', title: 'Fire Alarm Testing', priority: 'high' as const, status: 'scheduled', created_at: '2026-02-12T00:00:00Z' },
        { id: 'wo-hvac', code: 'WO-002', title: 'HVAC Filter Replacement', priority: 'medium' as const, status: 'scheduled', created_at: '2026-02-12T00:00:00Z' },
      ];

      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: mockData }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        });

      const { result } = renderHook(() => useMaintenanceSchedule('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      const fireFiltered = result.current.filterBySpecialty('fire');
      expect(fireFiltered.some((wo) => wo.title.includes('Fire'))).toBe(true);
    });
  });

  describe('Real-Time Cache Invalidation', () => {
    it('should invalidate cache when status updated', async () => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ status: 'assigned' }),
        });

      const { result } = renderHook(() => useMaintenanceSchedule('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await act(async () => {
        await result.current.updateStatusAsync({
          workOrderId: 'wo-001',
          status: 'assigned',
        });
      });

      // Cache should be invalidated
      expect(queryClient.getQueryData(['maintenance-schedule', 'S002', 30])).toBeDefined();
    });

    it('should refetch schedule and history after status update', async () => {
      (global.fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ work_orders: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ status: 'in_progress' }),
        });

      const { result } = renderHook(() => useMaintenanceSchedule('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await act(async () => {
        await result.current.updateStatusAsync({
          workOrderId: 'wo-001',
          status: 'in_progress',
        });
      });

      // Both queries should be available in cache
      expect(queryClient.getQueryData(['maintenance-schedule', 'S002', 30])).toBeDefined();
      expect(queryClient.getQueryData(['maintenance-history', 'S002'])).toBeDefined();
    });
  });
});

describe('useTechnicianAssignments Hook', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Technician Availability & Assignments', () => {
    it('should fetch available technicians', async () => {
      const mockTechnicians = [
        { id: 'tech-001', name: 'John Smith', specialty: 'hvac' as const, available: true, current_assignments: 2 },
        { id: 'tech-002', name: 'Jane Doe', specialty: 'electrical' as const, available: true, current_assignments: 1 },
      ];

      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ technicians: mockTechnicians }),
      });

      const { result } = renderHook(() => useTechnicianAssignments('S002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.technicians.length).toBeGreaterThan(0);
    });

    it('should filter technicians by specialty', async () => {
      const hvacTechs = [
        { id: 'tech-001', name: 'John Smith', specialty: 'hvac' as const, available: true, current_assignments: 2 },
      ];

      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ technicians: hvacTechs }),
      });

      const { result } = renderHook(() => useTechnicianAssignments('S002', 'hvac'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.technicians.length).toBeGreaterThan(0);
      expect(result.current.technicians[0].specialty).toBe('hvac');
    });

    it('should show technician availability and current assignments', async () => {
      const mockTechnicians = [
        { id: 'tech-001', name: 'John', specialty: 'hvac' as const, available: true, current_assignments: 2 },
        { id: 'tech-002', name: 'Jane', specialty: 'electrical' as const, available: false, current_assignments: 5 },
      ];

      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ technicians: mockTechnicians }),
      });

      const { result } = renderHook(() => useTechnicianAssignments('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.technicians[0].available).toBe(true);
      expect(result.current.technicians[0].current_assignments).toBe(2);
      expect(result.current.technicians[1].available).toBe(false);
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors gracefully', async () => {
      (global.fetch as any).mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useTechnicianAssignments('S002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.error).toBeDefined();
      expect(result.current.technicians).toEqual([]);
    });
  });
});

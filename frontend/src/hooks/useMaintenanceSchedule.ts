/**
 * React Query Hook for Maintenance Schedule Management
 *
 * Manages work order scheduling, technician assignments, and maintenance history:
 * - Fetch scheduled work orders (next 30 days)
 * - Track work order status transitions
 * - Display technician assignments
 * - Show maintenance history (past 10 completed)
 * - Filter by priority and technician specialty
 * - Link alerts to maintenance actions
 *
 * All data cached by React Query with appropriate stale times.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { WorkOrder, EquipmentAlert } from '@/lib/api/equipment_history';

export interface MaintenanceScheduleItem extends WorkOrder {
  equipment_id?: string;
  technician_specialty?: 'hvac' | 'electrical' | 'dali' | 'fire' | 'security' | 'general';
  linked_alert?: EquipmentAlert;
  days_to_deadline?: number;
}

export interface TechnicianInfo {
  id: string;
  name: string;
  specialty: 'hvac' | 'electrical' | 'dali' | 'fire' | 'security' | 'general';
  available: boolean;
  current_assignments: number;
}

/**
 * Hook for managing maintenance schedule
 *
 * @param siteId - Building identifier
 * @param daysAhead - Look-ahead period (default: 30 days)
 * @returns Schedule state with work orders, filters, and management functions
 */
export function useMaintenanceSchedule(siteId: string, daysAhead: number = 30) {
  const queryClient = useQueryClient();

  // Fetch scheduled work orders (next N days)
  const scheduleQuery = useQuery({
    queryKey: ['maintenance-schedule', siteId, daysAhead],
    queryFn: async () => {
      const response = await fetch(
        `/api/work-orders/schedule/${siteId}?days_ahead=${daysAhead}`
      );
      if (!response.ok) throw new Error('Failed to fetch maintenance schedule');
      const data = await response.json();
      return data.work_orders || [];
    },
    staleTime: 60000, // 1 minute (schedules change infrequently)
    gcTime: 10 * 60 * 1000, // 10 minutes
    enabled: !!siteId,
    retry: 2,
  });

  // Fetch maintenance history (past 10 completed)
  const historyQuery = useQuery({
    queryKey: ['maintenance-history', siteId],
    queryFn: async () => {
      const response = await fetch(
        `/api/work-orders/history/${siteId}?limit=10&status=completed`
      );
      if (!response.ok) throw new Error('Failed to fetch maintenance history');
      const data = await response.json();
      return data.work_orders || [];
    },
    staleTime: 120000, // 2 minutes (history changes when work orders complete)
    gcTime: 15 * 60 * 1000, // 15 minutes
    enabled: !!siteId,
    retry: 2,
  });

  // Update work order status
  const updateStatusMutation = useMutation({
    mutationFn: async ({
      workOrderId,
      status,
      technician,
    }: {
      workOrderId: string;
      status: 'assigned' | 'in_progress' | 'completed';
      technician?: string;
    }) => {
      const response = await fetch(
        `/api/work-orders/${workOrderId}/status`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status, assigned_to: technician }),
        }
      );
      if (!response.ok) throw new Error('Failed to update work order');
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['maintenance-schedule', siteId] });
      queryClient.invalidateQueries({ queryKey: ['maintenance-history', siteId] });
    },
  });

  // Assign technician to work order
  const assignTechnicianMutation = useMutation({
    mutationFn: async ({
      workOrderId,
      technicianId,
    }: {
      workOrderId: string;
      technicianId: string;
    }) => {
      const response = await fetch(
        `/api/work-orders/${workOrderId}/assign`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ technician_id: technicianId }),
        }
      );
      if (!response.ok) throw new Error('Failed to assign technician');
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['maintenance-schedule', siteId] });
    },
  });

  // Calculate days to deadline
  const calculateDaysToDeadline = (createdAt: string): number => {
    const created = new Date(createdAt);
    const today = new Date();
    const diffTime = created.getTime() - today.getTime();
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays;
  };

  // Get priority sorted schedule
  const getSortedSchedule = (schedule: WorkOrder[]): MaintenanceScheduleItem[] => {
    const priorityOrder = { urgent: 0, high: 1, medium: 2, low: 3 };
    return schedule
      .map((wo) => ({
        ...wo,
        days_to_deadline: calculateDaysToDeadline(wo.created_at),
      }))
      .sort((a, b) => {
        const priorityDiff =
          (priorityOrder[a.priority as keyof typeof priorityOrder] ?? 4) -
          (priorityOrder[b.priority as keyof typeof priorityOrder] ?? 4);
        if (priorityDiff !== 0) return priorityDiff;
        return (a.days_to_deadline ?? 999) - (b.days_to_deadline ?? 999);
      });
  };

  // Filter by technician specialty
  const filterBySpecialty = (
    specialty: 'hvac' | 'electrical' | 'dali' | 'fire' | 'security' | 'general'
  ): WorkOrder[] => {
    const schedule = scheduleQuery.data || [];
    return schedule.filter((wo) => {
      // Map work order title/type to specialty
      const title = wo.title?.toLowerCase() || '';
      const specialty_map: Record<string, string[]> = {
        hvac: ['hvac', 'chiller', 'ahu', 'fcу', 'vav', 'split', 'ct', 'crac'],
        electrical: ['generator', 'gen', 'ups', 'transformer', 'meter', 'panel'],
        dali: ['dali', 'lighting', 'lum'],
        fire: ['fire', 'alarm', 'sprinkler'],
        security: ['access', 'cctv', 'lock'],
        general: [],
      };
      return specialty_map[specialty]?.some((type) => title.includes(type)) ?? false;
    });
  };

  return {
    schedule: getSortedSchedule(scheduleQuery.data || []),
    history: historyQuery.data || [],
    isLoading: scheduleQuery.isLoading || historyQuery.isLoading,
    error: scheduleQuery.error || historyQuery.error,
    updateStatus: updateStatusMutation.mutate,
    updateStatusAsync: updateStatusMutation.mutateAsync,
    isUpdating: updateStatusMutation.isPending,
    assignTechnician: assignTechnicianMutation.mutate,
    assignTechnicianAsync: assignTechnicianMutation.mutateAsync,
    isAssigning: assignTechnicianMutation.isPending,
    filterBySpecialty,
    refetch: scheduleQuery.refetch,
  };
}

/**
 * Hook for retrieving available technicians for assignment
 *
 * @param siteId - Building identifier
 * @param specialty - Optional filter by specialty
 * @returns List of available technicians
 */
export function useTechnicianAssignments(
  siteId: string,
  specialty?: 'hvac' | 'electrical' | 'dali' | 'fire' | 'security' | 'general'
) {
  const techniciansQuery = useQuery({
    queryKey: ['technicians', siteId, specialty],
    queryFn: async () => {
      const url = new URL(`/api/technicians/${siteId}`, window.location.origin);
      if (specialty) url.searchParams.append('specialty', specialty);

      const response = await fetch(url);
      if (!response.ok) throw new Error('Failed to fetch technicians');
      const data = await response.json();
      return data.technicians || [];
    },
    staleTime: 60000, // 1 minute
    gcTime: 10 * 60 * 1000, // 10 minutes
    enabled: !!siteId,
  });

  return {
    technicians: techniciansQuery.data || [],
    isLoading: techniciansQuery.isLoading,
    error: techniciansQuery.error,
    refetch: techniciansQuery.refetch,
  };
}

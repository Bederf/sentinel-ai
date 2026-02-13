/**
 * useEquipmentHistory - React Query hooks for equipment maintenance and alert history
 *
 * Provides hooks for fetching work order and alert history with caching.
 */

import { useQuery } from '@tanstack/react-query';
import type { WorkOrder, EquipmentAlert } from '../lib/api';

/**
 * Fetch work order history for equipment
 */
export function useEquipmentWorkOrders(equipmentId: string | undefined, limit = 10) {
  return useQuery({
    queryKey: ['equipment', 'workOrders', equipmentId, limit],
    queryFn: async () => {
      if (!equipmentId) return [];
      const response = await fetch(`/api/work-orders/supabase?equipment_id=${equipmentId}&limit=${limit}`);
      if (!response.ok) throw new Error('Failed to fetch work orders');
      return response.json();
    },
    enabled: !!equipmentId,
    staleTime: 60 * 1000, // 60 seconds
    gcTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Fetch alert history for equipment
 */
export function useEquipmentAlerts(equipmentId: string | undefined, limit = 10) {
  return useQuery({
    queryKey: ['equipment', 'alerts', equipmentId, limit],
    queryFn: async () => {
      if (!equipmentId) return [];
      const response = await fetch(`/api/alerts?equipment_id=${equipmentId}&limit=${limit}`);
      if (!response.ok) throw new Error('Failed to fetch alerts');
      return response.json();
    },
    enabled: !!equipmentId,
    staleTime: 30 * 1000, // 30 seconds
    gcTime: 3 * 60 * 1000, // 3 minutes
  });
}

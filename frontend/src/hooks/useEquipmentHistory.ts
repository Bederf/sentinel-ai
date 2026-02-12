/**
 * React Query Hooks for Equipment History
 *
 * Provides hooks for querying work orders and alerts for equipment.
 */

import { useQuery } from '@tanstack/react-query';
import { equipmentHistoryApi, type WorkOrder, type EquipmentAlert } from '@/lib/api/equipment_history';

/**
 * Hook to fetch work orders for equipment
 *
 * @param equipmentId - Equipment UUID
 * @param limit - Maximum number of work orders to return (default: 10)
 * @returns Query result with work orders array
 */
export function useEquipmentWorkOrders(equipmentId: string, limit: number = 10) {
  return useQuery({
    queryKey: ['equipment-work-orders', equipmentId, limit],
    queryFn: () => equipmentHistoryApi.getWorkOrders(equipmentId, limit),
    staleTime: 60000, // 1 minute (work orders change infrequently)
    gcTime: 5 * 60 * 1000, // 5 minutes (formerly cacheTime)
    enabled: !!equipmentId,
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
  });
}

/**
 * Hook to fetch alerts for equipment
 *
 * @param equipmentId - Equipment UUID
 * @param limit - Maximum number of alerts to return (default: 10)
 * @returns Query result with alerts array
 */
export function useEquipmentAlerts(equipmentId: string, limit: number = 10) {
  return useQuery({
    queryKey: ['equipment-alerts', equipmentId, limit],
    queryFn: () => equipmentHistoryApi.getAlerts(equipmentId, limit),
    staleTime: 30000, // 30 seconds (alerts update more frequently)
    gcTime: 3 * 60 * 1000, // 3 minutes (formerly cacheTime)
    enabled: !!equipmentId,
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
  });
}

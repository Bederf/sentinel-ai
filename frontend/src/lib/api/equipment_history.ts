/**
 * Equipment History API Client
 *
 * Handles work order and alert history queries for equipment.
 */

import { fetchApi } from './client';

// ============= Equipment History Types =============

export interface WorkOrder {
  id: string;
  code: string;               // e.g., WO-2026-0001
  title: string;
  description?: string;
  priority: "low" | "medium" | "high" | "urgent";
  status: "scheduled" | "assigned" | "in_progress" | "completed" | "cancelled";
  assigned_to?: string;
  technician_name?: string;
  created_at: string;
  completed_at?: string;
  updated_at?: string;
}

export interface EquipmentAlert {
  id: string;
  title: string;
  message: string;
  severity: "critical" | "warning" | "medium" | "low";
  status: "active" | "acknowledged" | "resolved";
  created_at: string;
  acknowledged_at?: string;
  resolved_at?: string;
}

// ============= Equipment History API Methods =============

export const equipmentHistoryApi = {
  /**
   * Get work orders for equipment by equipment UUID
   *
   * @param equipmentId - Equipment UUID
   * @param limit - Maximum number of work orders to return (default: 10)
   */
  getWorkOrders: async (equipmentId: string, limit: number = 10): Promise<WorkOrder[]> => {
    try {
      const response = await fetchApi<{ data?: WorkOrder[]; work_orders?: WorkOrder[] }>(
        `/api/work-orders/supabase?limit=${limit}&equipment_id=${equipmentId}`
      );

      // Handle both response formats
      const workOrders = response?.data || response?.work_orders || [];
      return Array.isArray(workOrders) ? workOrders : [];
    } catch (error) {
      console.error('Failed to fetch work orders:', error);
      return [];
    }
  },

  /**
   * Get alerts for equipment by equipment UUID
   *
   * @param equipmentId - Equipment UUID
   * @param limit - Maximum number of alerts to return (default: 10)
   */
  getAlerts: async (equipmentId: string, limit: number = 10): Promise<EquipmentAlert[]> => {
    try {
      const response = await fetchApi<EquipmentAlert[] | { data: EquipmentAlert[] }>(
        `/api/alerts?equipment_id=${equipmentId}&limit=${limit}`
      );

      // Handle both response formats
      if (Array.isArray(response)) {
        return response;
      }
      if (response?.data && Array.isArray(response.data)) {
        return response.data;
      }
      return [];
    } catch (error) {
      console.error('Failed to fetch alerts:', error);
      return [];
    }
  },
};

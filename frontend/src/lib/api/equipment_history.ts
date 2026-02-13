/**
 * Equipment History API Client
 *
 * Fetches equipment maintenance and alert history.
 */

import { authorizedFetch } from './client';

const API_BASE = import.meta.env.VITE_API_URL || '';

/**
 * Alert with status and severity
 */
export interface EquipmentAlert {
  id: string;
  title: string;
  message: string;
  severity: 'critical' | 'warning' | 'medium' | 'low';
  status: 'active' | 'acknowledged' | 'resolved';
  created_at: string;
  acknowledged_at?: string;
  resolved_at?: string;
}

/**
 * Work order with status and priority
 */
export interface WorkOrder {
  id: string;
  code: string;
  work_type: string;
  status: 'scheduled' | 'in_progress' | 'completed' | 'cancelled';
  priority: 'low' | 'medium' | 'high' | 'urgent';
  title: string;
  assigned_to?: string;
  created_at: string;
  completed_at?: string;
}

export const equipmentHistoryApi = {
  /**
   * Fetch work orders for specific equipment
   */
  async getWorkOrders(equipmentId: string, limit: number = 10): Promise<WorkOrder[]> {
    const response = await authorizedFetch(
      `${API_BASE}/api/work-orders/supabase?equipment_id=${equipmentId}&limit=${limit}`
    );
    if (!response.ok) {
      throw new Error(`Failed to fetch work orders: ${response.statusText}`);
    }
    const data = await response.json();
    // Handle both array and object with work_orders property
    return Array.isArray(data) ? data : (data.work_orders || []);
  },

  /**
   * Fetch alerts for specific equipment
   */
  async getAlerts(equipmentId: string, limit: number = 10): Promise<EquipmentAlert[]> {
    const response = await authorizedFetch(
      `${API_BASE}/api/alerts?equipment_id=${equipmentId}&limit=${limit}`
    );
    if (!response.ok) {
      throw new Error(`Failed to fetch alerts: ${response.statusText}`);
    }
    const data = await response.json();
    // Handle both array and object with alerts property
    return Array.isArray(data) ? data : (data.alerts || []);
  },
};

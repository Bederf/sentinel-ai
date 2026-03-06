/**
 * Workflow & Inspection API Client
 *
 * Handles building inspections, maintenance workflows, and task management.
 */

import { fetchApi } from './client';

// ============= Inspection Types =============

export interface InspectionScheduleItem {
  equipment_id: string;
  site_id: string;
  equipment_name: string;
  frequency_days: number;
  last_inspected: string | null;
  next_due: string | null;
  days_until_due: number;
  overdue: boolean;
}

export interface ChecklistItem {
  id: string;
  name: string;
  completed: boolean;
  notes: string;
}

export interface ValidationChecklist {
  id: string;
  equipment_id: string;
  checklist_items: ChecklistItem[];
  completed_at: string | null;
}

// ============= Workflow Types =============

export interface WorkflowEquipmentItem {
  equipment_id: string;
  equipment_name: string;
  status: string;
  health_score: number;
}

export interface WorkflowState {
  state: string;
  timestamp: string;
  message: string;
}

export interface WorkflowDashboardResponse {
  site_id: string;
  buildings_count: number;
  total_assets: number;
  onboarded_assets: number;
  onboarding_progress: number;
  inspection_schedule_items: InspectionScheduleItem[];
  recent_workflows: WorkflowState[];
}

// ============= Inspection API Methods =============

export const inspectionApi = {
  /**
   * Get inspection schedule for a building
   */
  getSchedule: (siteId: string) =>
    fetchApi<InspectionScheduleItem[]>(`/api/buildings/${siteId}/inspection-schedule`),

  /**
   * Submit inspection checklist
   */
  submitChecklist: (siteId: string, equipmentId: string, data: { checklist_items: ChecklistItem[] }) =>
    fetchApi(`/api/buildings/${siteId}/equipment/${equipmentId}/inspection`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /**
   * Get validation checklist
   */
  getChecklist: (siteId: string, equipmentId: string) =>
    fetchApi<ValidationChecklist>(`/api/buildings/${siteId}/equipment/${equipmentId}/validation-checklist`),
};

// ============= Workflow API Methods =============

export const workflowApi = {
  /**
   * Get current workflow state
   */
  getStatus: (siteId: string) =>
    fetchApi<WorkflowDashboardResponse>(`/api/buildings/${siteId}/workflow`),

  /**
   * Update workflow state
   */
  updateState: (siteId: string, state: string, message: string) =>
    fetchApi(`/api/buildings/${siteId}/workflow/state`, {
      method: "POST",
      body: JSON.stringify({ state, message }),
    }),

  /**
   * Get equipment with workflow states for dashboard
   * Returns equipment list + workflow state for each
   */
  getDashboardEquipment: (siteId?: string) => {
    const url = siteId
      ? `/api/workflow/dashboard/equipment?site_id=${encodeURIComponent(siteId)}`
      : `/api/workflow/dashboard/equipment`;
    return fetchApi<{
      equipment: Array<{
        equipment_id: string;
        name: string;
        type: string;
        current_state: string;
      }>;
      workflow_states: Record<string, any>;
    }>(url);
  },
};

/**
 * Workflow & Inspection API Client
 *
 * Handles building inspections, maintenance workflows, and task management.
 */

import { fetchApi } from './client';

// ============= Inspection Types =============

export interface InspectionScheduleItem {
  equipment_id: string;
  building_id: string;
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
  building_id: string;
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
  getSchedule: (buildingId: string) =>
    fetchApi<InspectionScheduleItem[]>(`/api/buildings/${buildingId}/inspection-schedule`),

  /**
   * Submit inspection checklist
   */
  submitChecklist: (buildingId: string, equipmentId: string, data: { checklist_items: ChecklistItem[] }) =>
    fetchApi(`/api/buildings/${buildingId}/equipment/${equipmentId}/inspection`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /**
   * Get validation checklist
   */
  getChecklist: (buildingId: string, equipmentId: string) =>
    fetchApi<ValidationChecklist>(`/api/buildings/${buildingId}/equipment/${equipmentId}/validation-checklist`),
};

// ============= Workflow API Methods =============

export const workflowApi = {
  /**
   * Get current workflow state
   */
  getStatus: (buildingId: string) =>
    fetchApi<WorkflowDashboardResponse>(`/api/buildings/${buildingId}/workflow`),

  /**
   * Update workflow state
   */
  updateState: (buildingId: string, state: string, message: string) =>
    fetchApi(`/api/buildings/${buildingId}/workflow/state`, {
      method: "POST",
      body: JSON.stringify({ state, message }),
    }),
};


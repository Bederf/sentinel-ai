/**
 * Checklist API Client
 *
 * Handles OEM-specific checklist template generation, retrieval, and lookup.
 * Integrates with Phase 66 checklist generation service.
 */

import { fetchApi } from './client';

// ============= Types =============

export interface ChecklistItem {
  item_id: string;
  question: string;
  item_type: string;
  category: string;
  required: boolean;
  tolerance_min?: number;
  tolerance_max?: number;
  unit?: string;
}

export interface ChecklistTemplate {
  id: string;
  template_name: string;
  equipment_type: string;
  inspection_type: string;
  manufacturer?: string;
  model?: string;
  frequency_type?: string;
  estimated_duration_minutes?: number;
  checklist_items: ChecklistItem[];
  required_tools?: string[];
  required_skills?: string[];
  safety_requirements?: string[];
  ppe_required?: string[];
  version: number;
  is_active: boolean;
}

export interface ChecklistGenerateRequest {
  equipment_code: string;
  force?: boolean;
}

export interface ChecklistGenerateResponse {
  status: 'success' | 'error' | 'skipped';
  equipment_code: string;
  generated_templates: Array<{
    id: string;
    template_name: string;
    inspection_type: string;
  }>;
  message?: string;
}

export interface ChecklistOemLookupResponse {
  template: ChecklistTemplate | null;
  message?: string;
}

// ============= Checklist API Methods =============

export const checklistApi = {
  /**
   * Generate OEM-specific checklists for equipment
   *
   * Generates 3 template variants:
   * - routine_inspection
   * - preventive_maintenance
   * - annual_major_service
   */
  generateForEquipment: (equipmentCode: string, force?: boolean) =>
    fetchApi<ChecklistGenerateResponse>('/api/checklists/generate', {
      method: 'POST',
      body: JSON.stringify({
        equipment_code: equipmentCode,
        force: force || false,
      }),
    }),

  /**
   * Get a complete checklist template by ID
   */
  getTemplate: (templateId: string) =>
    fetchApi<ChecklistTemplate>(`/api/checklists/${templateId}`),

  /**
   * List all templates for a specific equipment type
   */
  listTemplates: (equipmentType: string, isActive?: boolean) =>
    fetchApi<ChecklistTemplate[]>(
      `/api/checklists/equipment/${equipmentType}?is_active=${isActive !== false}`
    ),

  /**
   * Lookup OEM-specific template with cascade matching
   *
   * Searches in priority order:
   * 1. Model + manufacturer match
   * 2. Manufacturer-only match
   * 3. Generic template
   */
  getOemTemplate: (
    equipmentType: string,
    manufacturer: string,
    model?: string,
    inspectionType?: string
  ) => {
    const params = new URLSearchParams({
      equipment_type: equipmentType,
      manufacturer,
    });
    if (model) params.append('model', model);
    if (inspectionType) params.append('inspection_type', inspectionType);

    return fetchApi<ChecklistOemLookupResponse>(
      `/api/checklists/oem/lookup?${params.toString()}`
    );
  },

  /**
   * List all active checklist templates
   */
  listAll: (isActive?: boolean) =>
    fetchApi<ChecklistTemplate[]>(
      `/api/checklists?is_active=${isActive !== false}`
    ),
};

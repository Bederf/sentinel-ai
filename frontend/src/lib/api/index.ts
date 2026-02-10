/**
 * Barrel export for API client modules
 *
 * This file re-exports all API utilities, types, and methods.
 * Domain-specific APIs are organized in separate modules:
 * - client.ts: Core HTTP utilities and auth
 * - auth.ts: Authentication APIs
 * - devices.ts: Device control and queries
 * - sites.ts: Sites and buildings management
 * - workflow.ts: Inspection and workflow APIs
 * - checklist.ts: Checklist templates and items
 * - optimization.ts: Optimization profiles and recommendations
 *
 * IMPORTANT: Modular exports come BEFORE legacy export
 * so they take precedence over outdated definitions in legacy api.ts
 */

// Core utilities and types
export {
  authorizedFetch,
  fetchApi,
  clearAuthStorage,
  isExpectedApiError,
  AUTH_EXPIRED_EVENT,
  API_BASE_URL,
  SITES_CACHE_KEY,
  type HealthResponse,
  type ApiError,
} from './client';

// Domain-specific modules (these take precedence over legacy versions)
export { authApi, type AuthUser, type LoginResponse, type VerifyResponse } from './auth';
export {
  devicesApi,
  type Device,
  type DevicePoint,
  type DeviceStatus,
  type DeviceSafetyStatus,
  type DeviceControlResponse,
} from './devices';
export {
  sitesApi,
  type Site,
  type Equipment,
  type BuildingEquipmentResponse,
  type CreateSiteRequest,
} from './sites';
export {
  inspectionApi,
  workflowApi,
  type InspectionScheduleItem,
  type WorkflowDashboardResponse,
} from './workflow';
export {
  checklistApi,
  type ChecklistTemplate,
  type ChecklistItem,
  type ChecklistGenerateResponse,
  type ChecklistOemLookupResponse,
} from './checklist';
export {
  optimizationApi,
  type SiteProfileConfig,
  type Recommendation,
  type Outcome,
} from './optimization';

// Legacy: import everything from original api.ts AFTER modular exports for backward compatibility
// This provides fallback for any APIs not yet migrated to modular structure
// NOTE: Modular exports above will override legacy versions with the same name
export * from '../api';

/**
 * Barrel export for API client modules
 *
 * This file re-exports all API utilities, types, and methods.
 * Domain-specific APIs are organized in separate modules:
 * - client.ts: Core HTTP utilities and auth
 * - auth.ts: Authentication APIs
 * - workflow.ts: Inspection and workflow APIs
 * - (Future) devices.ts, sites.ts, chat.ts, solar.ts, etc.
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

// Domain-specific modules
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
} from './sites';
export {
  inspectionApi,
  workflowApi,
  type InspectionScheduleItem,
  type WorkflowDashboardResponse,
} from './workflow';

// Legacy: import everything from original api.ts for now
// TODO: Gradually migrate to domain-specific imports as modules are created
export * from '../api';

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
  type HealthResponse,
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
  equipmentHistoryApi,
  type WorkOrder,
  type EquipmentAlert,
} from './equipment_history';
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
export {
  approvalsApi,
  type ApprovalResponse,
  type ApprovalStatus,
} from './approvals';
export {
  peakDemandApi,
  type DemandStatusResponse,
  type DemandForecastResponse,
  type MultiModuleRecommendation,
  type ModuleAction,
  type DemandSummary,
} from './peakDemand';
export {
  zoneIngestionApi,
  type ZoneConfig,
  type DeskConfig,
  type DeskCoordinates,
  type IngestionResponse,
  type ZoneValidationResult,
} from './zone_ingestion';

// Desk positioning data types
export {
  type Desk,
  type ZoneCentroid,
  type ZoneCentroidResponse,
  type AllZoneCentroidsResponse,
  type DeskStatsResponse,
} from './sites';

// Document management
export {
  documentsApi,
  type Document,
  type DocumentUploadResponse,
} from './documents';

// System Health & Diagnostics
export {
  systemApi,
  useSystemHealth,
  useDiagnostics,
  type SystemHealthSnapshot,
  type ComponentHealth,
  type DiagnosticResult,
  type ErrorLog,
  type ErrorLogFilters,
  type ErrorLogResponse,
  type HealthHistoryData,
} from './system';

// Legacy: import everything from original api.ts for backward compatibility
// This provides fallback for any APIs not yet migrated to modular structure
export * from '../api';

// Batch aggregators and fetch client (AFTER wildcard to ensure they take precedence)
export {
  safetyBatcher,
  readingsBatcher,
  conditionBatcher,
} from './batchers';
export {
  type DeviceSafetyStatus as BatchDeviceSafetyStatus,
  type DeviceStatus as BatchDeviceStatus,
  type DeviceCondition,
  type BatchResponse,
} from './types';
export { apiFetch, type ApiError } from './fetchClient';

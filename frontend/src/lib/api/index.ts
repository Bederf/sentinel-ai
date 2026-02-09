/**
 * Barrel export for API client modules
 *
 * This file re-exports all API utilities, types, and methods.
 * Domain-specific APIs are organized in separate modules:
 * - client.ts: Core HTTP utilities and auth
 * - Eventually: auth.ts, devices.ts, sites.ts, chat.ts, workflow.ts, etc.
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

// Legacy: import everything from original api.ts for now
// TODO: Gradually migrate to domain-specific imports as modules are created
export * from '../api';

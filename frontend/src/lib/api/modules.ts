/**
 * Modules API Client
 *
 * Handles module management and integration status tracking.
 */

import { authorizedFetch } from './client';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:9095';

/**
 * Integration health status for external services
 */
export interface IntegrationHealthStatus {
  name: string;
  status: 'healthy' | 'degraded' | 'unavailable';
  last_check: string;
  error?: string;
}

/**
 * Integration status response for a site
 */
export interface IntegrationStatusResponse {
  site_id: string;
  coordinator_active: boolean;
  active_modules: string[];
  integrations: IntegrationHealthStatus[];
  last_updated: string;
}

/**
 * Module definition with capabilities
 */
export interface ModuleDefinition {
  module_type: string;
  name: string;
  version: string;
  description: string;
  status?: 'active' | 'inactive' | 'error';
  capabilities?: Array<{ id: string; name: string; description: string }>;
  integrates_with?: string[];
  ai_features?: string[];
  health_score?: number;
}

/**
 * Module request/response types
 */
export interface ModuleActivationRequest {
  site_id: string;
  module_type: string;
}

export interface ModuleActivationResponse {
  success: boolean;
  module_type: string;
  status: string;
}

/**
 * Modules API client
 */
export const modulesApi = {
  /**
   * Get integration status for a site
   * @param siteId Site identifier
   * @returns IntegrationStatusResponse with module and integration health
   */
  async getIntegrationStatus(siteId: string): Promise<IntegrationStatusResponse> {
    const response = await authorizedFetch(
      `${API_BASE}/api/modules/${siteId}/integration`
    );
    if (!response.ok) {
      throw new Error(
        `Failed to fetch integration status: ${response.statusText}`
      );
    }
    return response.json();
  },

  /**
   * Get list of available modules
   * @returns Array of available module definitions
   */
  async getAvailableModules(): Promise<ModuleDefinition[]> {
    const response = await authorizedFetch(
      `${API_BASE}/api/modules/available`
    );
    if (!response.ok) {
      throw new Error(
        `Failed to fetch available modules: ${response.statusText}`
      );
    }
    const data = await response.json();
    return Array.isArray(data) ? data : (data.modules || []);
  },

  /**
   * Activate a module at a site
   * @param siteId Site identifier
   * @param moduleType Module type to activate
   * @returns Activation response
   */
  async activateModule(
    siteId: string,
    moduleType: string
  ): Promise<ModuleActivationResponse> {
    const response = await authorizedFetch(
      `${API_BASE}/api/modules/activate`,
      {
        method: 'POST',
        body: JSON.stringify({ site_id: siteId, module_type: moduleType }),
      }
    );
    if (!response.ok) {
      throw new Error(
        `Failed to activate module: ${response.statusText}`
      );
    }
    return response.json();
  },

  /**
   * Deactivate a module at a site
   * @param siteId Site identifier
   * @param moduleType Module type to deactivate
   * @returns Activation response
   */
  async deactivateModule(
    siteId: string,
    moduleType: string
  ): Promise<ModuleActivationResponse> {
    const response = await authorizedFetch(
      `${API_BASE}/api/modules/site/${siteId}/deactivate/${moduleType}`,
      { method: 'POST' }
    );
    if (!response.ok) {
      throw new Error(
        `Failed to deactivate module: ${response.statusText}`
      );
    }
    return response.json();
  },
};

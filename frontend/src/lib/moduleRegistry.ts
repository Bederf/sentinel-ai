/**
 * Module Registry API Client
 *
 * Manages bolt-on module system:
 * - HVAC, Energy, Security, Lighting modules
 * - Each operates standalone but integrates when multiple active
 */

import { authorizedFetch } from "./api";
const API_BASE = import.meta.env.VITE_API_URL || "";
const RECOMMENDATIONS_CACHE_PREFIX = "sentinel_module_recommendations_";

// ==================== Types ====================

export type ModuleType = string;
export type ModuleStatus = 'active' | 'inactive' | 'error' | 'maintenance';
export type RecommendationType = 'optimization' | 'maintenance' | 'alert' | 'cross_system' | 'predictive';
export type RecommendationPriority = 'low' | 'medium' | 'high' | 'critical';

export interface ModuleCapability {
  id: string;
  name: string;
  description: string;
}

export interface ModuleDefinition {
  module_type: ModuleType;
  name: string;
  version: string;
  description: string;
  enabled: boolean;
  mandatory: boolean;
  capabilities: ModuleCapability[];
  integrates_with: ModuleType[];
  telemetry_points: string[];
  ai_features: string[];
}

type ModuleRegistryPayload = Record<string, ModuleDefinition> | ModuleDefinition[];

// Cache for available modules (5 minute TTL)
const MODULES_CACHE_TTL = 5 * 60 * 1000;
let modulesCache: { data: ModuleDefinition[] | null; timestamp: number } = { data: null, timestamp: 0 };

function normalizeModuleRegistryPayload(payload: ModuleRegistryPayload): ModuleDefinition[] {
  return Array.isArray(payload) ? payload : Object.values(payload);
}

export interface ModuleInstance {
  instance_id: string;
  site_id: string;
  module_type: ModuleType;
  status: ModuleStatus;
  activated_at: string;
  health_score: number;
  last_telemetry?: string;
}

export interface AIRecommendation {
  recommendation_id: string;
  timestamp: string;
  source_module: ModuleType;
  source?: string;  // "ai_optimizer" | "health_alert" | "financial_roi" | "anomaly_detector"
  source_type?: string;  // "ml_model" | "rule_based"
  recommendation_type: RecommendationType;
  priority: RecommendationPriority;
  title: string;
  description: string;
  confidence: number;
  related_modules: ModuleType[];
  auto_actionable: boolean;
  acknowledged: boolean;
  resolved: boolean;
}

export interface CrossModuleIntegration {
  id: string;
  name: string;
  description: string;
  source: ModuleType;
  target: ModuleType;
}

export interface PotentialIntegration {
  id: string;
  name: string;
  requires_module: ModuleType;
}

export interface IntegrationSummary {
  site_id: string;
  site_name: string;
  active_modules: {
    type: ModuleType;
    name: string;
    health: number;
    status: ModuleStatus;
  }[];
  active_integrations: CrossModuleIntegration[];
  potential_integrations: PotentialIntegration[];
  ai_enabled: boolean;
  pending_recommendations: number;
}

export interface UnifiedTelemetry {
  site_id: string;
  timestamp: string;
  modules: Record<ModuleType, {
    status: ModuleStatus;
    health_score: number;
    last_telemetry?: string;
    capabilities: string[];
    ai_features: string[];
  }>;
  cross_module_status: Record<string, {
    source: ModuleType;
    target: ModuleType;
    enabled: boolean;
  }>;
}

// ==================== API Functions ====================

async function fetchWithAuth(input: RequestInfo, init?: RequestInit) {
  return authorizedFetch(String(input), init, true);
}

export const moduleRegistryApi = {
  /**
   * Get all available module definitions
   * Cached for 5 minutes to prevent rate limit hits
   */
  async getModuleRegistry(): Promise<ModuleDefinition[]> {
    const now = Date.now();

    // Return cached data if still valid
    if (modulesCache.data && (now - modulesCache.timestamp) < MODULES_CACHE_TTL) {
      return modulesCache.data;
    }

    try {
      const response = await fetchWithAuth(`${API_BASE}/api/modules/registry`);
      if (!response.ok) throw new Error('Failed to fetch module registry');
      const data = normalizeModuleRegistryPayload(await response.json() as ModuleRegistryPayload);

      // Update cache
      modulesCache = { data, timestamp: now };
      return data;
    } catch (error) {
      // If request fails but we have cached data, return it even if expired
      if (modulesCache.data) {
        console.warn('Failed to fetch modules, using stale cache:', error);
        return modulesCache.data;
      }
      throw error;
    }
  },

  async getAvailableModules(): Promise<ModuleDefinition[]> {
    return moduleRegistryApi.getModuleRegistry();
  },

  /**
   * Get definition for a specific module type
   */
  async getModuleDefinition(moduleType: ModuleType): Promise<ModuleDefinition> {
    const response = await fetchWithAuth(`${API_BASE}/api/modules/definition/${moduleType}`);
    if (!response.ok) throw new Error(`Failed to fetch module definition: ${moduleType}`);
    return response.json();
  },

  /**
   * Get active modules for a site
   */
  async getActiveModules(siteId: string): Promise<ModuleInstance[]> {
    const response = await fetchWithAuth(`${API_BASE}/api/modules/site/${siteId}/active`);
    if (!response.ok) throw new Error('Failed to fetch active modules');
    return response.json();
  },

  /**
   * Activate a module for a site
   */
  async activateModule(
    siteId: string,
    siteName: string,
    moduleType: ModuleType,
    config?: Record<string, unknown>
  ): Promise<ModuleInstance> {
    const response = await fetchWithAuth(`${API_BASE}/api/modules/activate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        site_id: siteId,
        site_name: siteName,
        module_type: moduleType,
        config,
      }),
    });
    if (!response.ok) {
      try {
        const errorData = await response.json();
        throw new Error(errorData.detail || `Failed to activate module (${response.status})`);
      } catch (e) {
        if (e instanceof Error) throw e;
        throw new Error(`Failed to activate module (HTTP ${response.status})`);
      }
    }
    return response.json();
  },

  /**
   * Deactivate a module for a site
   */
  async deactivateModule(siteId: string, moduleType: ModuleType): Promise<void> {
    const response = await fetchWithAuth(
      `${API_BASE}/api/modules/site/${siteId}/deactivate/${moduleType}`,
      { method: 'POST' }
    );
    if (!response.ok) {
      try {
        const errorData = await response.json();
        throw new Error(errorData.detail || `Failed to deactivate module (${response.status})`);
      } catch (e) {
        if (e instanceof Error) throw e;
        throw new Error(`Failed to deactivate module (HTTP ${response.status})`);
      }
    }
  },

  /**
   * Check if a module is active
   */
  async isModuleActive(siteId: string, moduleType: ModuleType): Promise<boolean> {
    const response = await fetchWithAuth(
      `${API_BASE}/api/modules/site/${siteId}/check/${moduleType}`
    );
    if (!response.ok) return false;
    const data = await response.json();
    return data.active;
  },

  /**
   * Get integration summary for a site
   */
  async getIntegrationSummary(siteId: string): Promise<IntegrationSummary | null> {
    const response = await fetchWithAuth(`${API_BASE}/api/modules/site/${siteId}/integration`);
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) throw new Error('Failed to fetch integration summary');
    return response.json();
  },

  /**
   * Get unified telemetry from all active modules
   */
  async getUnifiedTelemetry(siteId: string): Promise<UnifiedTelemetry | null> {
    const response = await fetchWithAuth(`${API_BASE}/api/modules/site/${siteId}/telemetry`);
    if (response.status === 404) return null;
    if (!response.ok) throw new Error('Failed to fetch unified telemetry');
    return response.json();
  },

  /**
   * Get AI recommendations for a site
   */
  async getRecommendations(
    siteId: string,
    options?: {
      modules?: ModuleType[];
      priorities?: RecommendationPriority[];
      includeResolved?: boolean;
      limit?: number;
    }
  ): Promise<AIRecommendation[]> {
    const params = new URLSearchParams();
    if (options?.modules?.length) {
      params.set('modules', options.modules.join(','));
    }
    if (options?.priorities?.length) {
      params.set('priorities', options.priorities.join(','));
    }
    if (options?.includeResolved) {
      params.set('include_resolved', 'true');
    }
    if (options?.limit) {
      params.set('limit', options.limit.toString());
    }

    const url = `${API_BASE}/api/modules/site/${siteId}/recommendations?${params}`;
    const response = await fetchWithAuth(url);
    const cacheKey = `${RECOMMENDATIONS_CACHE_PREFIX}${siteId}`;

    if (!response.ok) {
      if (response.status === 429) {
        const cached = localStorage.getItem(cacheKey);
        if (cached) {
          try {
            return JSON.parse(cached) as AIRecommendation[];
          } catch {
            // ignore malformed cache
          }
        }
        return [];
      }
      throw new Error(`Failed to fetch recommendations (${response.status})`);
    }

    const recommendations = await response.json() as AIRecommendation[];
    localStorage.setItem(cacheKey, JSON.stringify(recommendations));
    return recommendations;
  },

  /**
   * Add a recommendation (usually called by module components)
   */
  async addRecommendation(
    siteId: string,
    recommendation: {
      source_module: ModuleType;
      recommendation_type: RecommendationType;
      priority: RecommendationPriority;
      title: string;
      description: string;
      confidence?: number;
      related_modules?: ModuleType[];
      telemetry_context?: Record<string, unknown>;
      suggested_action?: Record<string, unknown>;
      auto_actionable?: boolean;
    }
  ): Promise<{ recommendation_id: string; timestamp: string }> {
    const response = await fetchWithAuth(`${API_BASE}/api/modules/site/${siteId}/recommendations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(recommendation),
    });
    if (!response.ok) throw new Error('Failed to add recommendation');
    return response.json();
  },

  /**
   * Acknowledge a recommendation
   */
  async acknowledgeRecommendation(siteId: string, recommendationId: string): Promise<void> {
    const response = await fetchWithAuth(
      `${API_BASE}/api/modules/site/${siteId}/recommendations/${recommendationId}/acknowledge`,
      { method: 'POST' }
    );
    if (!response.ok) throw new Error('Failed to acknowledge recommendation');
  },

  /**
   * Resolve a recommendation
   */
  async resolveRecommendation(siteId: string, recommendationId: string): Promise<void> {
    const response = await fetchWithAuth(
      `${API_BASE}/api/modules/site/${siteId}/recommendations/${recommendationId}/resolve`,
      { method: 'POST' }
    );
    if (!response.ok) throw new Error('Failed to resolve recommendation');
  },

  /**
   * Update module health
   */
  async updateModuleHealth(
    siteId: string,
    moduleType: ModuleType,
    healthScore: number
  ): Promise<void> {
    const response = await fetchWithAuth(
      `${API_BASE}/api/modules/site/${siteId}/health/${moduleType}?health_score=${healthScore}`,
      { method: 'POST' }
    );
    if (!response.ok) throw new Error('Failed to update module health');
  },
};

// ==================== Module Metadata ====================

export const MODULE_ICONS: Record<ModuleType, string> = {
  // Base Platform
  kpi: 'grid',
  ml: 'bar-chart',
  notifications: 'bell',
  integrations: 'activity',
  simbiot: 'plug',
  logging: 'file-text',
  assets: 'git-branch',
  // Base Building Systems
  hvac: 'thermometer',
  energy: 'zap',
  lighting: 'sun',
  solar: 'sun',
  water: 'droplets',
  fire: 'flame',
  security: 'shield-check',
  digital_twin: 'cube',
  // Control Add-ons
  hvac_control: 'thermometer',
  energy_control: 'zap',
  lighting_control: 'sun',
  solar_control: 'sun',
  water_control: 'droplets',
  security_control: 'shield-check',
  digital_twin_control: 'cube',
  // Standalone Add-ons
  maintenance: 'wrench',
  financial: 'dollar-sign',
  compliance: 'leaf',
  fleet_ml: 'brain',
  block_booking: 'calendar-check',
  space_optimization: 'layout-grid',
  sustainability: 'leaf',
  contracts: 'file-signature',
  access: 'key-round',
  control: 'sliders-horizontal',
  fuel: 'fuel',
  fuel_alerts: 'bell-ring',
};

export const MODULE_COLORS: Record<ModuleType, string> = {
  // Base Platform
  kpi: 'slate',
  ml: 'cyan',
  notifications: 'rose',
  integrations: 'sky',
  simbiot: 'teal',
  logging: 'slate',
  assets: 'indigo',
  // Base Building Systems
  hvac: 'blue',
  energy: 'amber',
  lighting: 'yellow',
  solar: 'yellow',
  water: 'blue',
  fire: 'red',
  security: 'purple',
  digital_twin: 'violet',
  // Control Add-ons
  hvac_control: 'blue',
  energy_control: 'amber',
  lighting_control: 'yellow',
  solar_control: 'yellow',
  water_control: 'blue',
  security_control: 'purple',
  digital_twin_control: 'violet',
  // Standalone Add-ons
  maintenance: 'orange',
  financial: 'orange',
  compliance: 'emerald',
  fleet_ml: 'cyan',
  block_booking: 'rose',
  space_optimization: 'teal',
  sustainability: 'emerald',
  contracts: 'orange',
  access: 'purple',
  control: 'slate',
  fuel: 'orange',
  fuel_alerts: 'red',
};

export const PRIORITY_COLORS: Record<RecommendationPriority, string> = {
  low: 'gray',
  medium: 'blue',
  high: 'amber',
  critical: 'red',
};

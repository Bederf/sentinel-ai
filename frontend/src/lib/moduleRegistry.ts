/**
 * Module Registry API Client
 *
 * Manages bolt-on module system:
 * - HVAC, Energy, Security, Lighting modules
 * - Each operates standalone but integrates when multiple active
 */

const API_BASE = import.meta.env.VITE_API_URL || "";

// ==================== Types ====================

export type ModuleType = 'control' | 'assets' | 'simbiot' | 'integrations' | 'notifications' | 'hvac' | 'energy' | 'security' | 'lighting' | 'fire' | 'access' | 'solar' | 'water' | 'ml' | 'sustainability' | 'contracts';
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
  capabilities: ModuleCapability[];
  integrates_with: ModuleType[];
  ai_features: string[];
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

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem("sentinel_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchWithAuth(input: RequestInfo, init?: RequestInit) {
  const authHeaders = getAuthHeaders();
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> || {}),
    ...authHeaders,
  };

  return fetch(input, {
    ...init,
    headers,
  });
}

export const moduleRegistryApi = {
  /**
   * Get all available module definitions
   */
  async getAvailableModules(): Promise<ModuleDefinition[]> {
    const response = await fetchWithAuth(`${API_BASE}/api/modules/available`);
    if (!response.ok) throw new Error('Failed to fetch available modules');
    return response.json();
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
    if (!response.ok) throw new Error('Failed to activate module');
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
    if (!response.ok) throw new Error('Failed to deactivate module');
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
  async getIntegrationSummary(siteId: string): Promise<IntegrationSummary> {
    const response = await fetchWithAuth(`${API_BASE}/api/modules/site/${siteId}/integration`);
    if (!response.ok) throw new Error('Failed to fetch integration summary');
    return response.json();
  },

  /**
   * Get unified telemetry from all active modules
   */
  async getUnifiedTelemetry(siteId: string): Promise<UnifiedTelemetry> {
    const response = await fetchWithAuth(`${API_BASE}/api/modules/site/${siteId}/telemetry`);
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
    if (!response.ok) throw new Error('Failed to fetch recommendations');
    return response.json();
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
  control: 'shield',
  assets: 'git-branch',
  simbiot: 'plug',
  integrations: 'activity',
  notifications: 'bell',
  hvac: 'thermometer',
  energy: 'zap',
  security: 'shield-check',
  lighting: 'sun',
  fire: 'flame',
  access: 'key',
  solar: 'sun',
  water: 'droplets',
  ml: 'bar-chart',
  sustainability: 'leaf',
  contracts: 'file-text',
};

export const MODULE_COLORS: Record<ModuleType, string> = {
  control: 'slate',
  assets: 'indigo',
  simbiot: 'teal',
  integrations: 'sky',
  notifications: 'rose',
  hvac: 'blue',
  energy: 'amber',
  security: 'purple',
  lighting: 'yellow',
  fire: 'red',
  access: 'green',
  solar: 'yellow',
  water: 'blue',
  ml: 'cyan',
  sustainability: 'emerald',
  contracts: 'orange',
};

export const PRIORITY_COLORS: Record<RecommendationPriority, string> = {
  low: 'gray',
  medium: 'blue',
  high: 'amber',
  critical: 'red',
};

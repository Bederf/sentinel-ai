/**
 * Module Context - Manages Bolt-on Module State
 *
 * Provides:
 * - Active module tracking
 * - Cross-module integration status
 * - Unified AI recommendations
 * - Module activation/deactivation
 */

import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import {
  moduleRegistryApi,
} from '../lib/moduleRegistry';
import type {
  ModuleType,
  ModuleInstance,
  ModuleDefinition,
  AIRecommendation,
  IntegrationSummary,
} from '../lib/moduleRegistry';

interface ModuleContextValue {
  // State
  siteId: string | null;
  siteName: string | null;
  activeModules: ModuleInstance[];
  availableModules: ModuleDefinition[];
  recommendations: AIRecommendation[];
  integrationSummary: IntegrationSummary | null;
  loading: boolean;
  error: string | null;

  // Actions
  setSite: (siteId: string, siteName: string) => void;
  activateModule: (moduleType: ModuleType, config?: Record<string, unknown>) => Promise<void>;
  deactivateModule: (moduleType: ModuleType) => Promise<void>;
  isModuleActive: (moduleType: ModuleType) => boolean;
  addRecommendation: (recommendation: Omit<AIRecommendation, 'recommendation_id' | 'timestamp' | 'acknowledged' | 'resolved'>) => void;
  acknowledgeRecommendation: (recommendationId: string) => Promise<void>;
  resolveRecommendation: (recommendationId: string) => Promise<void>;
  refreshIntegration: () => Promise<void>;
  refreshRecommendations: () => Promise<void>;

  // Integration helpers
  getActiveIntegrations: () => { source: ModuleType; target: ModuleType; name: string }[];
  canIntegrateWith: (moduleType: ModuleType) => ModuleType[];
}

const ModuleContext = createContext<ModuleContextValue | undefined>(undefined);

interface ModuleProviderProps {
  children: ReactNode;
  initialSiteId?: string;
  initialSiteName?: string;
}

export function ModuleProvider({
  children,
  initialSiteId,
  initialSiteName,
}: ModuleProviderProps) {
  const [siteId, setSiteIdState] = useState<string | null>(initialSiteId || null);
  const [siteName, setSiteNameState] = useState<string | null>(initialSiteName || null);
  const [activeModules, setActiveModules] = useState<ModuleInstance[]>([]);
  const [availableModules, setAvailableModules] = useState<ModuleDefinition[]>([]);
  const [recommendations, setRecommendations] = useState<AIRecommendation[]>([]);
  const [integrationSummary, setIntegrationSummary] = useState<IntegrationSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Define loaders as useCallback to satisfy exhaustive-deps
  const loadAvailableModules = useCallback(async () => {
    try {
      const modules = await moduleRegistryApi.getAvailableModules();
      setAvailableModules(modules);
    } catch (err) {
      console.error('Failed to load available modules:', err);
    }
  }, []);

  const loadSiteData = useCallback(async () => {
    if (!siteId) return;

    setLoading(true);
    setError(null);

    try {
      const [modules, summary, recs] = await Promise.all([
        moduleRegistryApi.getActiveModules(siteId),
        moduleRegistryApi.getIntegrationSummary(siteId).catch(() => null),
        moduleRegistryApi.getRecommendations(siteId),
      ]);

      setActiveModules(modules);
      setIntegrationSummary(summary);
      setRecommendations(recs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load site data');
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  const loadRecommendations = useCallback(async () => {
    if (!siteId) return;

    try {
      const recs = await moduleRegistryApi.getRecommendations(siteId);
      setRecommendations(recs);
    } catch (err) {
      console.error('Failed to load recommendations:', err);
    }
  }, [siteId]);

  // Load available modules on mount
  useEffect(() => {
    loadAvailableModules();
  }, [loadAvailableModules]);

  // Load site data when site changes
  useEffect(() => {
    if (siteId) {
      loadSiteData();
    }
  }, [siteId, loadSiteData]);

  // Poll recommendations
  useEffect(() => {
    if (siteId) {
      const interval = setInterval(() => {
        loadRecommendations();
      }, 15000); // Every 15 seconds
      return () => clearInterval(interval);
    }
  }, [siteId, loadRecommendations]);

  const setSite = useCallback((id: string, name: string) => {
    setSiteIdState(id);
    setSiteNameState(name);
  }, []);

  const activateModule = useCallback(async (
    moduleType: ModuleType,
    config?: Record<string, unknown>
  ) => {
    if (!siteId || !siteName) {
      throw new Error('Site not set');
    }

    const instance = await moduleRegistryApi.activateModule(siteId, siteName, moduleType, config);
    setActiveModules(prev => {
      const existing = prev.findIndex(m => m.module_type === moduleType);
      if (existing >= 0) {
        const updated = [...prev];
        updated[existing] = instance;
        return updated;
      }
      return [...prev, instance];
    });

    // Refresh integration summary
    const summary = await moduleRegistryApi.getIntegrationSummary(siteId);
    setIntegrationSummary(summary);
  }, [siteId, siteName]);

  const deactivateModule = useCallback(async (moduleType: ModuleType) => {
    if (!siteId) return;

    await moduleRegistryApi.deactivateModule(siteId, moduleType);
    setActiveModules(prev => prev.filter(m => m.module_type !== moduleType));

    // Refresh integration summary
    const summary = await moduleRegistryApi.getIntegrationSummary(siteId).catch(() => null);
    setIntegrationSummary(summary);
  }, [siteId]);

  const isModuleActive = useCallback((moduleType: ModuleType): boolean => {
    return activeModules.some(m => m.module_type === moduleType && m.status === 'active');
  }, [activeModules]);

  const addRecommendation = useCallback((
    recommendation: Omit<AIRecommendation, 'recommendation_id' | 'timestamp' | 'acknowledged' | 'resolved'>
  ) => {
    if (!siteId) return;

    moduleRegistryApi.addRecommendation(siteId, {
      source_module: recommendation.source_module,
      recommendation_type: recommendation.recommendation_type,
      priority: recommendation.priority,
      title: recommendation.title,
      description: recommendation.description,
      confidence: recommendation.confidence,
      related_modules: recommendation.related_modules,
      auto_actionable: recommendation.auto_actionable,
    }).then(() => {
      loadRecommendations();
    }).catch(err => {
      console.error('Failed to add recommendation:', err);
    });
  }, [siteId, loadRecommendations]);

  const acknowledgeRecommendation = useCallback(async (recommendationId: string) => {
    if (!siteId) return;

    await moduleRegistryApi.acknowledgeRecommendation(siteId, recommendationId);
    setRecommendations(prev =>
      prev.map(r =>
        r.recommendation_id === recommendationId
          ? { ...r, acknowledged: true }
          : r
      )
    );
  }, [siteId]);

  const resolveRecommendation = useCallback(async (recommendationId: string) => {
    if (!siteId) return;

    await moduleRegistryApi.resolveRecommendation(siteId, recommendationId);
    setRecommendations(prev =>
      prev.map(r =>
        r.recommendation_id === recommendationId
          ? { ...r, resolved: true }
          : r
      )
    );
  }, [siteId]);

  const refreshIntegration = useCallback(async () => {
    if (!siteId) return;

    const summary = await moduleRegistryApi.getIntegrationSummary(siteId);
    setIntegrationSummary(summary);
  }, [siteId]);

  const refreshRecommendations = useCallback(async () => {
    await loadRecommendations();
  }, [loadRecommendations]);

  const getActiveIntegrations = useCallback(() => {
    if (!integrationSummary) return [];
    return integrationSummary.active_integrations.map(i => ({
      source: i.source,
      target: i.target,
      name: i.name,
    }));
  }, [integrationSummary]);

  const canIntegrateWith = useCallback((moduleType: ModuleType): ModuleType[] => {
    const moduleDef = availableModules.find(m => m.module_type === moduleType);
    if (!moduleDef) return [];
    return moduleDef.integrates_with;
  }, [availableModules]);

  const value: ModuleContextValue = {
    siteId,
    siteName,
    activeModules,
    availableModules,
    recommendations,
    integrationSummary,
    loading,
    error,
    setSite,
    activateModule,
    deactivateModule,
    isModuleActive,
    addRecommendation,
    acknowledgeRecommendation,
    resolveRecommendation,
    refreshIntegration,
    refreshRecommendations,
    getActiveIntegrations,
    canIntegrateWith,
  };

  return (
    <ModuleContext.Provider value={value}>
      {children}
    </ModuleContext.Provider>
  );
}

export function useModules() {
  const context = useContext(ModuleContext);
  if (!context) {
    throw new Error('useModules must be used within a ModuleProvider');
  }
  return context;
}

// ==================== Convenience Hooks ====================

/**
 * Check if a specific module is active
 */
export function useModuleActive(moduleType: ModuleType): boolean {
  const { isModuleActive } = useModules();
  return isModuleActive(moduleType);
}

/**
 * Get recommendations filtered by priority
 */
export function useCriticalRecommendations(): AIRecommendation[] {
  const { recommendations } = useModules();
  return recommendations.filter(
    r => r.priority === 'critical' && !r.resolved
  );
}

/**
 * Get cross-system recommendations
 */
export function useCrossSystemRecommendations(): AIRecommendation[] {
  const { recommendations } = useModules();
  return recommendations.filter(
    r => r.recommendation_type === 'cross_system' && !r.resolved
  );
}

/**
 * Get recommendations for a specific module
 */
export function useModuleRecommendations(moduleType: ModuleType): AIRecommendation[] {
  const { recommendations } = useModules();
  return recommendations.filter(
    r => (r.source_module === moduleType || r.related_modules.includes(moduleType)) && !r.resolved
  );
}

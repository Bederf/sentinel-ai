/**
 * Module Context - Manages Bolt-on Module State
 *
 * Provides:
 * - Active module tracking
 * - Cross-module integration status
 * - Unified AI recommendations
 * - Module activation/deactivation
 */

import { useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import {
  moduleRegistryApi,
} from '../lib/moduleRegistry';
import { isExpectedApiError } from '@/lib/api';
import { isMandatoryModule as checkMandatoryModule, getMandatoryModuleErrorMessage } from '../lib/mandatoryModules';
import type {
  AIRecommendation,
  ModuleType,
  ModuleInstance,
  ModuleDefinition,
  IntegrationSummary,
} from '../lib/moduleRegistry';
import type { ModuleContextValue } from "./moduleContextStore";
import { ModuleContext } from "./moduleContextStore";

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

  // Sync prop changes into state — initialSiteId arrives async after buildings load
  useEffect(() => {
    if (initialSiteId && initialSiteId !== siteId) {
      setSiteIdState(initialSiteId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSiteId]);

  useEffect(() => {
    if (initialSiteName && initialSiteName !== siteName) {
      setSiteNameState(initialSiteName);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSiteName]);

  // Define loaders as useCallback to satisfy exhaustive-deps
  const loadAvailableModules = useCallback(async () => {
    try {
      const modules = await moduleRegistryApi.getAvailableModules();
      setAvailableModules(modules);
    } catch (err) {
      // Suppress rate limit errors - they're expected and will retry
      if (err instanceof Error && err.message.includes('429')) {
        console.warn('Module API rate limited, will retry with cache');
        return;
      }
      if (!isExpectedApiError(err)) {
        console.error('Failed to load available modules:', err);
      }
    }
  }, []);

  const loadSiteData = useCallback(async () => {
    if (!siteId) return;

    setLoading(true);
    setError(null);

    try {
      const [modules, summary] = await Promise.all([
        moduleRegistryApi.getActiveModules(siteId),
        moduleRegistryApi.getIntegrationSummary(siteId),
      ]);

      setActiveModules(modules);
      setIntegrationSummary(summary);
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
      if (!isExpectedApiError(err)) {
        console.error('Failed to load recommendations:', err);
      }
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

  // Retry loading modules if initial load failed (e.g. backend was offline)
  useEffect(() => {
    if (!siteId || activeModules.length > 0 || !error) return;

    let retryCount = 0;
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const retry = () => {
      if (cancelled || retryCount >= 5) return;
      const delay = Math.min(3000 * Math.pow(2, retryCount), 30000);
      timeoutId = setTimeout(async () => {
        if (cancelled) return;
        retryCount++;
        try {
          const [modules, summary] = await Promise.all([
            moduleRegistryApi.getActiveModules(siteId),
            moduleRegistryApi.getIntegrationSummary(siteId),
          ]);
          if (!cancelled && modules.length > 0) {
            setActiveModules(modules);
            setIntegrationSummary(summary);
            setError(null);
          } else if (!cancelled) {
            retry();
          }
        } catch {
          if (!cancelled) retry();
        }
      }, delay);
    };

    retry();

    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [siteId, activeModules.length, error]);

  // Poll recommendations
  useEffect(() => {
    if (!siteId) return;

    let failureCount = 0;
    let timeoutId: number | null = null;
    let isCancelled = false;

    const scheduleRecommendationsRefresh = async () => {
      if (isCancelled) return;
      if (document.hidden) {
        timeoutId = window.setTimeout(scheduleRecommendationsRefresh, 60000);
        return;
      }

      try {
        await loadRecommendations();
        failureCount = 0;
      } catch {
        failureCount += 1;
      }

      const baseIntervalMs = 60000;
      const backoffIntervalMs = Math.min(300000, baseIntervalMs * (2 ** failureCount));
      timeoutId = window.setTimeout(scheduleRecommendationsRefresh, backoffIntervalMs);
    };

    scheduleRecommendationsRefresh();

    return () => {
      isCancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
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

    // Prevent deactivation of mandatory base modules
    if (checkMandatoryModule(moduleType)) {
      const errorMessage = getMandatoryModuleErrorMessage(moduleType);
      console.warn(errorMessage);
      throw new Error(errorMessage);
    }

    await moduleRegistryApi.deactivateModule(siteId, moduleType);
    setActiveModules(prev => prev.filter(m => m.module_type !== moduleType));

    // Refresh integration summary
    const summary = await moduleRegistryApi.getIntegrationSummary(siteId);
    setIntegrationSummary(summary);
  }, [siteId]);

  const isModuleActive = useCallback((moduleType: ModuleType): boolean => {
    return activeModules.some(m => m.module_type === moduleType && m.status === 'active');
  }, [activeModules]);

  const isMandatory = useCallback((moduleType: ModuleType): boolean => {
    return checkMandatoryModule(moduleType);
  }, []);

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
      if (!isExpectedApiError(err)) {
        console.error('Failed to add recommendation:', err);
      }
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
    isMandatory,
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

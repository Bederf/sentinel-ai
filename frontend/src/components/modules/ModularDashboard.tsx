import { useState, useEffect, Suspense, lazy } from 'react';

import { useModules, useCriticalRecommendations } from '../../contexts/ModuleHooks';
import { MODULE_COLORS } from '../../lib/moduleRegistry';
import type { ModuleType } from '../../lib/moduleRegistry';
import { useHealthThresholds } from '../../hooks/useHealthThresholds';
import { AIRecommendationsPanel } from './AIRecommendationsPanel';
import { ModuleSelector } from './ModuleSelector';
import { IntegrationStatusBar } from './IntegrationStatusBar';
import { Badge } from '../Badge';
import { TabBar } from '../TabBar';
import type { TabDef } from '../TabBar';

const EnergyCentreDashboard = lazy(() =>
  import('../energy-centre/EnergyCentreDashboard').then(m => ({ default: m.EnergyCentreDashboard }))
);

const HVACDashboard = lazy(() =>
  import('../hvac/HVACDashboard').then(m => ({ default: m.HVACDashboard }))
);

const SolarDashboard = lazy(() =>
  import('../solar/SolarDashboard').then(m => ({ default: m.SolarDashboard }))
);

const SecurityPanel = lazy(() =>
  import('./SecurityPanel').then(m => ({ default: m.SecurityPanel }))
);

const LightingDashboard = lazy(() =>
  Promise.resolve({
    default: () => (
      <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
        <h3 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Lighting Module</h3>
        <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Lighting dashboard will be loaded here when available</p>
      </div>
    )
  })
);

interface ModularDashboardProps {
  siteId?: string;
  siteName?: string;
  sitePhase?: string;
  showModuleSelector?: boolean;
  showRecommendations?: boolean;
}

const LoadingFallback = () => (
  <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
    <div className="animate-pulse">
      <div className="h-6 bg-gray-200 rounded w-1/3 mb-4" />
      <div className="h-64 bg-gray-100 rounded" />
    </div>
  </div>
);

export function ModularDashboard({
  siteId: propSiteId,
  siteName: propSiteName,
  sitePhase,
  showModuleSelector = true,
  showRecommendations = true,
}: ModularDashboardProps) {
  const { activeModules, addRecommendation, setSite, siteId: contextSiteId } = useModules();
  const criticalRecs = useCriticalRecommendations();
  const { thresholds } = useHealthThresholds();
  const [activeTabId, setActiveTabId] = useState('overview');

  const siteId = propSiteId || contextSiteId || '';
  const _siteName = propSiteName || siteId;

  useEffect(() => {
    if (propSiteId) {
      setSite(propSiteId, propSiteName || propSiteId);
    }
  }, [propSiteId, propSiteName, setSite]);

  const getModuleDashboard = (moduleType: ModuleType) => {
    switch (moduleType) {
      case 'energy':
        return (
          <EnergyCentreDashboard
            siteId={siteId}
            enabledModules={activeModules.map(m => m.module_type)}
            onAIRecommendation={(rec) => {
              addRecommendation({
                source_module: 'energy' as ModuleType,
                recommendation_type: rec.type === 'cross_system' ? 'cross_system' : 'alert',
                priority: rec.priority,
                title: rec.title,
                description: rec.description,
                confidence: 0.85,
                related_modules: rec.related_modules as ModuleType[] || [],
                auto_actionable: !!rec.action,
              });
            }}
          />
        );
      case 'hvac':
        return (
          <HVACDashboard
            siteId={siteId}
            enabledModules={activeModules.map(m => m.module_type)}
            onboardingPhase={sitePhase}
            onAIRecommendation={(rec) => {
              addRecommendation({
                source_module: 'hvac' as ModuleType,
                recommendation_type: rec.type === 'cross_system' ? 'cross_system' : 'alert',
                priority: rec.priority,
                title: rec.title,
                description: rec.description,
                confidence: 0.85,
                related_modules: rec.related_modules as ModuleType[] || [],
                auto_actionable: !!rec.action,
              });
            }}
          />
        );
      case 'solar':
        return <SolarDashboard />;
      case 'security':
        return <SecurityPanel siteId={siteId} />;
      case 'lighting':
        return <LightingDashboard />;
      default:
        return (
          <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
            <h3 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>{moduleType.toUpperCase()} Module</h3>
            <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Module dashboard not implemented</p>
          </div>
        );
    }
  };

  if (activeModules.length === 0) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Building Intelligence Dashboard</h2>
          <p className="text-sm mt-2" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            No modules are currently active. Activate modules to enable building monitoring.
          </p>
        </div>

        {showModuleSelector && <ModuleSelector />}
      </div>
    );
  }

  if (activeModules.length === 1) {
    const module = activeModules[0];
    return (
      <div className="space-y-4">
        <IntegrationStatusBar />

        {showRecommendations && criticalRecs.length > 0 && (
          <AIRecommendationsPanel compact maxItems={3} siteId={siteId} sitePhase={sitePhase} />
        )}

        <Suspense fallback={<LoadingFallback />}>
          {getModuleDashboard(module.module_type)}
        </Suspense>

        {showModuleSelector && (
          <div className="mt-6">
            <ModuleSelector />
          </div>
        )}
      </div>
    );
  }

  const tabDefs: TabDef[] = [
    {
      id: 'overview',
      label: 'Overview',
      count: criticalRecs.length > 0 ? criticalRecs.length : undefined,
    },
    ...activeModules.map(m => ({
      id: m.module_type,
      label: m.module_type.toUpperCase(),
      count: m.health_score < thresholds.healthy ? Math.round(m.health_score) : undefined,
    })),
    ...(showModuleSelector ? [{ id: 'modules', label: 'Modules' } as TabDef] : []),
  ];

  return (
    <div className="space-y-4">
      <IntegrationStatusBar />

      {criticalRecs.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-bold text-red-700">
                {criticalRecs.length} Critical Recommendation(s)
              </p>
              <p className="text-sm text-red-600">
                {criticalRecs[0].title}
              </p>
            </div>
            <Badge style={{ background: 'rgba(220,38,38,0.15)', color: 'var(--color-sentinel-red)' }}>Action Required</Badge>
          </div>
        </div>
      )}

      <TabBar tabs={tabDefs} active={activeTabId} onChange={setActiveTabId} />

      {activeTabId === 'overview' && (
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 lg:col-span-1">
            <AIRecommendationsPanel maxItems={5} siteId={siteId} sitePhase={sitePhase} />
          </div>
          <div className="space-y-4">
            {activeModules.map(m => (
              <div
                key={m.module_type}
                className="rounded-lg p-4"
                style={{
                  background: 'var(--color-sentinel-bg-panel)',
                  borderLeft: `4px solid var(--color-sentinel-${MODULE_COLORS[m.module_type] || 'gray'})`,
                  border: '1px solid var(--color-sentinel-border)',
                  borderLeftWidth: '4px',
                }}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-bold" style={{ color: 'var(--color-sentinel-text-primary)' }}>{m.module_type.toUpperCase()}</p>
                    <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                      Last update: {m.last_telemetry
                        ? new Date(m.last_telemetry).toLocaleTimeString()
                        : 'N/A'}
                    </p>
                  </div>
                  <div className="text-right">
                    <Badge style={{
                      background: m.health_score >= thresholds.healthy ? 'rgba(16,185,129,0.15)' :
                        m.health_score >= thresholds.warning ? 'rgba(245,158,11,0.15)' : 'rgba(220,38,38,0.15)',
                      color: m.health_score >= thresholds.healthy ? 'var(--color-sentinel-green)' :
                        m.health_score >= thresholds.warning ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-red)',
                    }}>
                      Health: {m.health_score.toFixed(0)}%
                    </Badge>
                    <Badge className="ml-2" style={{ background: 'rgba(16,185,129,0.15)', color: 'var(--color-sentinel-green)' }}>
                      {m.status}
                    </Badge>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeModules.map(m => (
        activeTabId === m.module_type && (
          <Suspense key={m.module_type} fallback={<LoadingFallback />}>
            {getModuleDashboard(m.module_type)}
          </Suspense>
        )
      ))}

      {showModuleSelector && activeTabId === 'modules' && (
        <ModuleSelector />
      )}
    </div>
  );
}

export default ModularDashboard;

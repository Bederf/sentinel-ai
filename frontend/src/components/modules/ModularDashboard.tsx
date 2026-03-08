/**
 * Modular Dashboard - Dynamic Module Loading
 *
 * Dynamically loads and displays dashboards for active modules.
 * Handles cross-system AI recommendations and integration.
 */

import { useState, useEffect, Suspense, lazy } from 'react';
import { Card, Title, Text, Grid, Tab, TabGroup, TabList, TabPanel, TabPanels, Badge, Flex } from '@tremor/react';
import { useModules, useCriticalRecommendations } from '../../contexts/ModuleHooks';
import { MODULE_COLORS } from '../../lib/moduleRegistry';
import type { ModuleType } from '../../lib/moduleRegistry';
import { useHealthThresholds } from '../../hooks/useHealthThresholds';
import { AIRecommendationsPanel } from './AIRecommendationsPanel';
import { ModuleSelector } from './ModuleSelector';
import { IntegrationStatusBar } from './IntegrationStatusBar';

// Lazy load module dashboards
const EnergyCentreDashboard = lazy(() =>
  import('../energy-centre/EnergyCentreDashboard').then(m => ({ default: m.EnergyCentreDashboard }))
);

// HVAC Module Dashboard
const HVACDashboard = lazy(() =>
  import('../hvac/HVACDashboard').then(m => ({ default: m.HVACDashboard }))
);

// Solar & BESS Module Dashboard
const SolarDashboard = lazy(() =>
  import('../solar/SolarDashboard').then(m => ({ default: m.SolarDashboard }))
);

// Security Module Dashboard
const SecurityPanel = lazy(() =>
  import('./SecurityPanel').then(m => ({ default: m.SecurityPanel }))
);

const LightingDashboard = lazy(() =>
  Promise.resolve({
    default: () => (
      <Card>
        <Title>Lighting Module</Title>
        <Text className="text-gray-500">Lighting dashboard will be loaded here when available</Text>
      </Card>
    )
  })
);

interface ModularDashboardProps {
  siteId?: string;
  siteName?: string;
  showModuleSelector?: boolean;
  showRecommendations?: boolean;
}

// Loading fallback - defined outside component to avoid re-creation
const LoadingFallback = () => (
  <Card>
    <div className="animate-pulse">
      <div className="h-6 bg-gray-200 rounded w-1/3 mb-4" />
      <div className="h-64 bg-gray-100 rounded" />
    </div>
  </Card>
);

export function ModularDashboard({
  siteId: propSiteId,
  siteName: propSiteName,
  showModuleSelector = true,
  showRecommendations = true,
}: ModularDashboardProps) {
  const { activeModules, addRecommendation, setSite, siteId: contextSiteId } = useModules();
  const criticalRecs = useCriticalRecommendations();
  const { thresholds } = useHealthThresholds();
  const [activeTab, setActiveTab] = useState(0);

  // Use provided siteId or fall back to context siteId
  const siteId = propSiteId || contextSiteId || '';
  const _siteName = propSiteName || siteId;

  // Set site on mount if prop provided
  useEffect(() => {
    if (propSiteId) {
      setSite(propSiteId, propSiteName || propSiteId);
    }
  }, [propSiteId, propSiteName, setSite]);

  // Get module dashboard component
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
          <Card>
            <Title>{moduleType.toUpperCase()} Module</Title>
            <Text className="text-gray-500">Module dashboard not implemented</Text>
          </Card>
        );
    }
  };

  // No modules active
  if (activeModules.length === 0) {
    return (
      <div className="space-y-4">
        <Card>
          <Title>Building Intelligence Dashboard</Title>
          <Text className="text-gray-500 mb-4">
            No modules are currently active. Activate modules to enable building monitoring.
          </Text>
        </Card>

        {showModuleSelector && <ModuleSelector />}
      </div>
    );
  }

  // Single module active - show full dashboard
  if (activeModules.length === 1) {
    const module = activeModules[0];
    return (
      <div className="space-y-4">
        <IntegrationStatusBar />

        {showRecommendations && criticalRecs.length > 0 && (
          <AIRecommendationsPanel compact maxItems={3} />
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

  // Build tabs array
  const buildTabs = () => {
    const tabs: React.ReactElement[] = [
      <Tab key="overview">
        <Flex alignItems="center" className="gap-2">
          Overview
          {criticalRecs.length > 0 && (
            <Badge color="red" size="xs">{criticalRecs.length}</Badge>
          )}
        </Flex>
      </Tab>
    ];

    activeModules.forEach(m => {
      tabs.push(
        <Tab key={m.module_type}>
          <Flex alignItems="center" className="gap-2">
            <Badge color={MODULE_COLORS[m.module_type] || 'gray'} size="xs">
              {m.module_type.toUpperCase()}
            </Badge>
            {m.health_score < thresholds.healthy && (
              <Badge color="amber" size="xs">{m.health_score.toFixed(0)}%</Badge>
            )}
          </Flex>
        </Tab>
      );
    });

    if (showModuleSelector) {
      tabs.push(<Tab key="modules">Modules</Tab>);
    }

    return tabs;
  };

  // Build panels array
  const buildPanels = () => {
    const panels: React.ReactElement[] = [
      <TabPanel key="overview">
        <Grid className="grid grid-cols-2 gap-4">
          <div className="col-span-2 lg:col-span-1">
            <AIRecommendationsPanel maxItems={5} />
          </div>
          <div className="space-y-4">
            {activeModules.map(m => (
              <Card
                key={m.module_type}
                decoration="left"
                decorationColor={MODULE_COLORS[m.module_type] || 'gray'}
              >
                <Flex justifyContent="between" alignItems="center">
                  <div>
                    <Text className="font-bold">{m.module_type.toUpperCase()}</Text>
                    <Text className="text-xs text-gray-500">
                      Last update: {m.last_telemetry
                        ? new Date(m.last_telemetry).toLocaleTimeString()
                        : 'N/A'}
                    </Text>
                  </div>
                  <div className="text-right">
                    <Badge color={
                      m.health_score >= thresholds.healthy ? 'green' :
                      m.health_score >= thresholds.warning ? 'amber' : 'red'
                    }>
                      Health: {m.health_score.toFixed(0)}%
                    </Badge>
                    <Badge color="green" size="xs" className="ml-2">
                      {m.status}
                    </Badge>
                  </div>
                </Flex>
              </Card>
            ))}
          </div>
        </Grid>
      </TabPanel>
    ];

    activeModules.forEach(m => {
      panels.push(
        <TabPanel key={m.module_type}>
          <Suspense fallback={<LoadingFallback />}>
            {getModuleDashboard(m.module_type)}
          </Suspense>
        </TabPanel>
      );
    });

    if (showModuleSelector) {
      panels.push(
        <TabPanel key="modules">
          <ModuleSelector />
        </TabPanel>
      );
    }

    return panels;
  };

  const tabs = buildTabs();
  const panels = buildPanels();

  // Multiple modules active - show tabbed view
  return (
    <div className="space-y-4">
      <IntegrationStatusBar />

      {/* Critical Recommendations Banner */}
      {criticalRecs.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <Flex justifyContent="between" alignItems="center">
            <div>
              <Text className="font-bold text-red-700">
                {criticalRecs.length} Critical Recommendation(s)
              </Text>
              <Text className="text-sm text-red-600">
                {criticalRecs[0].title}
              </Text>
            </div>
            <Badge color="red" size="lg">Action Required</Badge>
          </Flex>
        </div>
      )}

      {/* Tabbed Module Views */}
      <TabGroup index={activeTab} onIndexChange={setActiveTab}>
        <TabList className="mb-4 overflow-x-auto">
          {tabs as unknown as React.ReactElement}
        </TabList>
        <TabPanels>
          {panels as unknown as React.ReactElement}
        </TabPanels>
      </TabGroup>
    </div>
  );
}

export default ModularDashboard;

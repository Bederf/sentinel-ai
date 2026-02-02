/**
 * Integration Status Bar - Cross-Module Integration Indicator
 *
 * Shows which modules are active and their integration status.
 * Appears at the top of the dashboard when multiple modules are active.
 */

import { Badge, Flex, Text } from '@tremor/react';
import { useModules } from '../../contexts/ModuleContext';
import { MODULE_COLORS } from '../../lib/moduleRegistry';
import { useHealthThresholds } from '../../hooks/useHealthThresholds';

interface IntegrationStatusBarProps {
  compact?: boolean;
}

export function IntegrationStatusBar({ compact = false }: IntegrationStatusBarProps) {
  const { activeModules, integrationSummary } = useModules();
  const { thresholds } = useHealthThresholds();

  if (activeModules.length === 0) {
    return null;
  }

  const hasIntegrations = integrationSummary && integrationSummary.active_integrations.length > 0;

  if (compact) {
    return (
      <div className="flex items-center gap-2 px-3 py-1 bg-gray-50 rounded-full">
        {activeModules.map(m => (
          <Badge
            key={m.module_type}
            color={MODULE_COLORS[m.module_type] || 'gray'}
            size="xs"
          >
            {m.module_type.toUpperCase()}
          </Badge>
        ))}
        {hasIntegrations && (
          <Badge color="purple" size="xs">
            Integrated
          </Badge>
        )}
      </div>
    );
  }

  return (
    <div className="bg-gradient-to-r from-gray-50 to-gray-100 border-b border-gray-200 px-4 py-2">
      <Flex justifyContent="between" alignItems="center">
        <Flex alignItems="center" className="gap-3">
          <Text className="text-sm font-medium text-gray-600">Active Modules:</Text>
          <div className="flex gap-2">
            {activeModules.map(m => (
              <Badge
                key={m.module_type}
                color={MODULE_COLORS[m.module_type] || 'gray'}
              >
                {m.module_type.toUpperCase()}
                {m.health_score < thresholds.healthy && (
                  <span className="ml-1 text-xs">({m.health_score.toFixed(0)}%)</span>
                )}
              </Badge>
            ))}
          </div>
        </Flex>

        {hasIntegrations && (
          <Flex alignItems="center" className="gap-2">
            <Badge color="purple">
              {integrationSummary!.active_integrations.length} Integration(s) Active
            </Badge>
            <Text className="text-xs text-gray-500">
              {integrationSummary!.active_integrations.map(i => i.name).join(' | ')}
            </Text>
          </Flex>
        )}

        {integrationSummary && integrationSummary.pending_recommendations > 0 && (
          <Badge color="amber">
            {integrationSummary.pending_recommendations} AI Recommendations
          </Badge>
        )}
      </Flex>
    </div>
  );
}

export default IntegrationStatusBar;

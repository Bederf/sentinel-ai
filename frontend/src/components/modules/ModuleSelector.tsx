/**
 * Module Selector - Activate/Deactivate Bolt-on Modules
 *
 * Shows available modules and their integration status.
 * Allows activation of standalone modules that integrate when combined.
 */

import { useState } from 'react';
import { Card, Title, Text, Badge, Flex, Grid, Switch } from '@tremor/react';
import { useModules } from '../../contexts/ModuleHooks';
import { MODULE_COLORS } from '../../lib/moduleRegistry';
import type { ModuleType, ModuleDefinition } from '../../lib/moduleRegistry';

interface ModuleSelectorProps {
  onModuleActivated?: (moduleType: ModuleType) => void;
  onModuleDeactivated?: (moduleType: ModuleType) => void;
}

export function ModuleSelector({ onModuleActivated, onModuleDeactivated }: ModuleSelectorProps) {
  const {
    availableModules,
    activeModules,
    integrationSummary,
    activateModule,
    deactivateModule,
    isModuleActive,
  } = useModules();

  const [activating, setActivating] = useState<ModuleType | null>(null);

  async function handleToggle(moduleType: ModuleType, currentlyActive: boolean) {
    setActivating(moduleType);
    try {
      if (currentlyActive) {
        await deactivateModule(moduleType);
        onModuleDeactivated?.(moduleType);
      } else {
        await activateModule(moduleType);
        onModuleActivated?.(moduleType);
      }
    } catch (err) {
      console.error('Failed to toggle module:', err);
    } finally {
      setActivating(null);
    }
  }

  // Get potential integrations for showing what activating a module enables
  const getPotentialIntegrations = (moduleType: ModuleType): string[] => {
    const moduleDef = availableModules.find(m => m.module_type === moduleType);
    if (!moduleDef) return [];

    const activeTypes = activeModules.map(m => m.module_type);
    return moduleDef.integrates_with
      .filter(t => activeTypes.includes(t))
      .map(t => {
        const def = availableModules.find(m => m.module_type === t);
        return def?.name || t;
      });
  };

  return (
    <Card>
      <Title>Building Modules</Title>
      <Text className="text-xs text-gray-500 mb-4">
        Activate modules for standalone operation or combined integration
      </Text>

      {/* Integration Status */}
      {integrationSummary && integrationSummary.active_integrations.length > 0 && (
        <div className="mb-4 p-3 bg-purple-50 rounded-lg border border-purple-200">
          <Flex alignItems="center" className="gap-2 mb-2">
            <Badge color="purple">Cross-System Integration Active</Badge>
          </Flex>
          <div className="space-y-1">
            {integrationSummary.active_integrations.map(integration => (
              <Text key={integration.id} className="text-xs text-purple-700">
                {integration.name}: {integration.source.toUpperCase()} + {integration.target.toUpperCase()}
              </Text>
            ))}
          </div>
        </div>
      )}

      {/* Module Grid */}
      <Grid numItems={2} className="gap-4">
        {availableModules.map(moduleDef => {
          const isActive = isModuleActive(moduleDef.module_type);
          const isActivatingThis = activating === moduleDef.module_type;
          const potentialIntegrations = getPotentialIntegrations(moduleDef.module_type);
          const activeInstance = activeModules.find(m => m.module_type === moduleDef.module_type);

          return (
            <ModuleCard
              key={moduleDef.module_type}
              module={moduleDef}
              isActive={isActive}
              isLoading={isActivatingThis}
              healthScore={activeInstance?.health_score}
              potentialIntegrations={potentialIntegrations}
              onToggle={() => handleToggle(moduleDef.module_type, isActive)}
            />
          );
        })}
      </Grid>

      {/* Potential Integrations */}
      {integrationSummary && integrationSummary.potential_integrations.length > 0 && (
        <div className="mt-4 p-3 bg-gray-50 rounded-lg">
          <Text className="text-xs font-medium text-gray-700 mb-2">
            Unlock More Integrations
          </Text>
          <div className="space-y-1">
            {integrationSummary.potential_integrations.slice(0, 3).map(potential => (
              <Text key={potential.id} className="text-xs text-gray-600">
                Activate <Badge color="blue" size="xs">{potential.requires_module}</Badge> to enable{' '}
                <span className="font-medium">{potential.name}</span>
              </Text>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

interface ModuleCardProps {
  module: ModuleDefinition;
  isActive: boolean;
  isLoading: boolean;
  healthScore?: number;
  potentialIntegrations: string[];
  onToggle: () => void;
}

function ModuleCard({
  module,
  isActive,
  isLoading,
  healthScore,
  potentialIntegrations,
  onToggle,
}: ModuleCardProps) {
  const color = MODULE_COLORS[module.module_type] || 'gray';

  return (
    <Card
      decoration="left"
      decorationColor={isActive ? color : 'gray'}
      className={`transition-all ${isActive ? '' : 'opacity-75'}`}
    >
      <Flex justifyContent="between" alignItems="start">
        <div>
          <Flex alignItems="center" className="gap-2">
            <Text className="font-bold">{module.name}</Text>
            <Badge color={isActive ? 'green' : 'gray'} size="xs">
              {isActive ? 'Active' : 'Inactive'}
            </Badge>
          </Flex>
          <Text className="text-xs text-gray-500 mt-1">{module.description}</Text>
        </div>
        <Switch
          checked={isActive}
          onChange={onToggle}
          color={color as any}
          disabled={isLoading}
        />
      </Flex>

      {/* Health Score */}
      {isActive && healthScore !== undefined && (
        <Flex className="mt-2 gap-2" alignItems="center">
          <Text className="text-xs text-gray-500">Health:</Text>
          <Badge
            color={healthScore >= 80 ? 'green' : healthScore >= 50 ? 'amber' : 'red'}
            size="xs"
          >
            {healthScore.toFixed(0)}%
          </Badge>
        </Flex>
      )}

      {/* Capabilities Preview */}
      <div className="mt-2 flex flex-wrap gap-1">
        {module.capabilities.slice(0, 3).map(cap => (
          <Badge key={cap.id} color="gray" size="xs">
            {cap.name}
          </Badge>
        ))}
        {module.capabilities.length > 3 && (
          <Badge color="gray" size="xs">+{module.capabilities.length - 3}</Badge>
        )}
      </div>

      {/* AI Features */}
      <div className="mt-2">
        <Text className="text-xs text-gray-500">
          AI: {module.ai_features.slice(0, 2).join(', ')}
          {module.ai_features.length > 2 && ` +${module.ai_features.length - 2}`}
        </Text>
      </div>

      {/* Integration Opportunity */}
      {!isActive && potentialIntegrations.length > 0 && (
        <div className="mt-2 p-2 bg-purple-50 rounded text-xs text-purple-700">
          Activating enables integration with: {potentialIntegrations.join(', ')}
        </div>
      )}

      {/* Integrates With */}
      {isActive && module.integrates_with.length > 0 && (
        <div className="mt-2">
          <Text className="text-xs text-gray-400">
            Integrates with: {module.integrates_with.join(', ')}
          </Text>
        </div>
      )}
    </Card>
  );
}

export default ModuleSelector;

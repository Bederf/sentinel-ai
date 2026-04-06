/**
 * Module Selector - Activate/Deactivate Bolt-on Modules
 *
 * Shows available modules and their integration status.
 * Allows activation of standalone modules that integrate when combined.
 */

import { useState } from 'react';
import { Card, Text, Badge, Flex, Grid } from '@tremor/react';
import { useModules } from '../../contexts/ModuleHooks';
import { MODULE_COLORS } from '../../lib/moduleRegistry';
import type { ModuleType, ModuleDefinition } from '../../lib/moduleRegistry';
import { MANDATORY_MODULES } from '../../lib/mandatoryModules';
import {
  Wind, Zap, Lock, Lightbulb, Sun, Droplets, Flame,
  Brain, Leaf, FileText, Gamepad2, Package, Plug, Link2, Bell
} from 'lucide-react';
import { ModuleDependencyWarning } from './ModuleDependencyWarning';

const NON_DEACTIVATABLE_MODULES: ModuleType[] = MANDATORY_MODULES;

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
  const [showWarning, setShowWarning] = useState<ModuleType | null>(null);
  const [isDeactivating, setIsDeactivating] = useState(false);

  // No cascading dependencies in the new architecture — each add-on is independent
  const getDependentsToDisable = (_moduleType: ModuleType): ModuleType[] => {
    return [];
  };

  async function handleToggle(moduleType: ModuleType, currentlyActive: boolean) {
    if (currentlyActive && NON_DEACTIVATABLE_MODULES.includes(moduleType)) {
      return;
    }

    // If deactivating, check for cascading dependents
    if (currentlyActive) {
      const dependents = getDependentsToDisable(moduleType);
      if (dependents.length > 0) {
        setShowWarning(moduleType);
        return;
      }
    }

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

  async function handleConfirmDeactivate(moduleType: ModuleType) {
    setShowWarning(null);
    setIsDeactivating(true);
    try {
      await deactivateModule(moduleType);
      onModuleDeactivated?.(moduleType);
    } catch (err) {
      console.error('Failed to deactivate module:', err);
    } finally {
      setIsDeactivating(false);
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
    <div>
      {/* Dependency Warning Modal */}
      {showWarning && (
        <ModuleDependencyWarning
          moduleType={showWarning}
          onConfirm={() => handleConfirmDeactivate(showWarning)}
          onCancel={() => setShowWarning(null)}
          isLoading={isDeactivating}
        />
      )}

      {/* Integration Status */}
      {integrationSummary && integrationSummary.active_integrations.length > 0 && (
        <div
          className="mb-4 p-3 rounded-lg border"
          style={{
            background: 'rgba(99, 102, 241, 0.1)',
            borderColor: 'rgba(99, 102, 241, 0.3)',
          }}
        >
          <Flex alignItems="center" className="gap-2 mb-2">
            <Badge
              color="purple"
              style={{
                background: 'rgba(99, 102, 241, 0.2)',
                color: 'rgba(99, 102, 241, 0.9)',
              }}
            >
              Cross-System Integration Active
            </Badge>
          </Flex>
          <div className="space-y-1">
            {integrationSummary.active_integrations.map(integration => (
              <Text
                key={integration.id}
                className="text-xs"
                style={{ color: 'rgba(99, 102, 241, 0.8)' }}
              >
                {integration.name}: {integration.source.toUpperCase()} + {integration.target.toUpperCase()}
              </Text>
            ))}
          </div>
        </div>
      )}

      {/* Module Grid */}
      <Grid className="grid grid-cols-2 gap-4">
        {availableModules.map(moduleDef => {
          const isActive = isModuleActive(moduleDef.module_type);
          const isProtectedBasePack = NON_DEACTIVATABLE_MODULES.includes(moduleDef.module_type);
          const isActivatingThis = activating === moduleDef.module_type;
          const potentialIntegrations = getPotentialIntegrations(moduleDef.module_type);
          const activeInstance = activeModules.find(m => m.module_type === moduleDef.module_type);

          return (
            <ModuleCard
              key={moduleDef.module_type}
              module={moduleDef}
              isActive={isActive}
              isLoading={isActivatingThis}
              isProtectedBasePack={isProtectedBasePack}
              healthScore={activeInstance?.health_score}
              potentialIntegrations={potentialIntegrations}
              onToggle={() => handleToggle(moduleDef.module_type, isActive)}
            />
          );
        })}
      </Grid>

      {/* Potential Integrations */}
      {integrationSummary && integrationSummary.potential_integrations.length > 0 && (
        <div
          className="mt-4 p-3 rounded-lg"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            border: '1px solid var(--glass-border)',
          }}
        >
          <Text
            className="text-xs font-medium mb-2"
            style={{ color: 'var(--color-sentinel-text-primary)' }}
          >
            Unlock More Integrations
          </Text>
          <div className="space-y-1">
            {integrationSummary.potential_integrations.slice(0, 3).map(potential => (
              <Text key={potential.id} className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Activate{' '}
                <Badge
                  color="blue"
                  size="xs"
                  style={{
                    background: 'rgba(59, 130, 246, 0.15)',
                    color: 'var(--color-sentinel-blue)',
                  }}
                >
                  {potential.requires_module}
                </Badge>{' '}
                to enable <span className="font-medium">{potential.name}</span>
              </Text>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Map module types to icons
const MODULE_ICONS: Partial<Record<ModuleType, React.ComponentType<any>>> = {
  // Base Platform
  kpi: Package,
  ml: Brain,
  notifications: Bell,
  integrations: Link2,
  simbiot: Plug,
  logging: FileText,
  assets: Package,
  // Base Building Systems
  hvac: Wind,
  energy: Zap,
  lighting: Lightbulb,
  solar: Sun,
  water: Droplets,
  fire: Flame,
  security: Lock,
  digital_twin: Package,
  // Control Add-ons
  hvac_control: Gamepad2,
  energy_control: Gamepad2,
  lighting_control: Gamepad2,
  solar_control: Gamepad2,
  water_control: Gamepad2,
  security_control: Gamepad2,
  digital_twin_control: Gamepad2,
  // Standalone Add-ons
  maintenance: Package,
  financial: FileText,
  compliance: Leaf,
  fleet_ml: Brain,
};

interface ModuleCardProps {
  module: ModuleDefinition;
  isActive: boolean;
  isLoading: boolean;
  isProtectedBasePack: boolean;
  healthScore?: number;
  potentialIntegrations: string[];
  onToggle: () => void;
}

// SENTINEL custom switch component - defined outside ModuleCard to avoid re-creation
const SentinelSwitch = ({ checked, onChange, disabled }: { checked: boolean; onChange: () => void; disabled: boolean }) => (
  <button
    onClick={onChange}
    disabled={disabled}
    className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
    style={{
      background: checked ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-bg-secondary)',
      border: `1px solid ${checked ? 'var(--color-sentinel-green)' : 'var(--glass-border)'}`,
      opacity: disabled ? 0.5 : 1,
      cursor: disabled ? 'not-allowed' : 'pointer',
    }}
    aria-checked={checked}
    role="switch"
    type="button"
  >
    <span
      className="inline-block h-4 w-4 rounded-full bg-white transition-transform"
      style={{
        transform: checked ? 'translateX(22px)' : 'translateX(2px)',
      }}
    />
  </button>
);

function ModuleCard({
  module,
  isActive,
  isLoading,
  isProtectedBasePack,
  healthScore,
  potentialIntegrations,
  onToggle,
}: ModuleCardProps) {
  const color = MODULE_COLORS[module.module_type] || 'gray';
  const IconComponent = MODULE_ICONS[module.module_type] || Zap;

  return (
    <Card
      className={`transition-all overflow-hidden`}
      style={{
        background: 'var(--color-sentinel-bg-secondary)',
        border: `1px solid ${isActive ? `var(--color-sentinel-${color})` : 'var(--glass-border)'}`,
        opacity: isActive ? 1 : 0.75,
      }}
    >
      <Flex justifyContent="between" alignItems="start">
        <div className="flex items-start gap-3 flex-1">
          <div
            className="p-2 rounded-lg mt-0.5"
            style={{
              background: `rgba(${
                color === 'green' ? '16, 185, 129' :
                color === 'red' ? '220, 38, 38' :
                color === 'amber' ? '245, 158, 11' :
                color === 'blue' ? '59, 130, 246' :
                color === 'purple' ? '147, 51, 234' :
                color === 'cyan' ? '34, 211, 238' :
                color === 'emerald' ? '16, 185, 129' :
                '107, 114, 128'
              }, 0.15)`,
            }}
          >
            <IconComponent
              className="h-4 w-4"
              style={{
                color: color === 'green' ? 'var(--color-sentinel-green)' :
                  color === 'red' ? 'var(--color-sentinel-red)' :
                  color === 'amber' ? 'var(--color-sentinel-amber)' :
                  color === 'blue' ? 'var(--color-sentinel-blue)' :
                  'var(--color-sentinel-text-primary)',
              }}
            />
          </div>
          <div className="flex-1">
            <Flex alignItems="center" className="gap-2">
              <Text
                className="font-bold"
                style={{ color: 'var(--color-sentinel-text-primary)' }}
              >
                {module.name}
              </Text>
              <Badge
                color={isActive ? 'green' : 'gray'}
                size="xs"
                style={{
                  background: isActive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(107, 114, 128, 0.15)',
                  color: isActive ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-text-secondary)',
                }}
              >
                {isActive ? 'Active' : 'Inactive'}
              </Badge>
              {isProtectedBasePack && (
                <Badge
                  color="blue"
                  size="xs"
                  style={{
                    background: 'rgba(59, 130, 246, 0.15)',
                    color: 'var(--color-sentinel-blue)',
                  }}
                >
                  Base Pack
                </Badge>
              )}
            </Flex>
            <Text
              className="text-xs mt-1"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              {module.description}
            </Text>
          </div>
        </div>
        <SentinelSwitch
          checked={isActive}
          onChange={onToggle}
          disabled={isLoading || (isActive && isProtectedBasePack)}
        />
      </Flex>

      {/* Health Score */}
      {isActive && healthScore !== undefined && (
        <Flex className="mt-3 gap-2" alignItems="center">
          <Text
            className="text-xs"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            Health:
          </Text>
          <Badge
            color={healthScore >= 80 ? 'green' : healthScore >= 50 ? 'amber' : 'red'}
            size="xs"
            style={{
              background: healthScore >= 80 ? 'rgba(16, 185, 129, 0.15)' :
                healthScore >= 50 ? 'rgba(245, 158, 11, 0.15)' :
                'rgba(220, 38, 38, 0.15)',
              color: healthScore >= 80 ? 'var(--color-sentinel-green)' :
                healthScore >= 50 ? 'var(--color-sentinel-amber)' :
                'var(--color-sentinel-red)',
            }}
          >
            {healthScore.toFixed(0)}%
          </Badge>
        </Flex>
      )}

      {/* Capabilities Preview */}
      <div className="mt-2 flex flex-wrap gap-1">
        {module.capabilities.slice(0, 3).map(cap => (
          <Badge
            key={cap.id}
            size="xs"
            style={{
              background: 'rgba(107, 114, 128, 0.15)',
              color: 'var(--color-sentinel-text-secondary)',
            }}
          >
            {cap.name}
          </Badge>
        ))}
        {module.capabilities.length > 3 && (
          <Badge
            size="xs"
            style={{
              background: 'rgba(107, 114, 128, 0.15)',
              color: 'var(--color-sentinel-text-secondary)',
            }}
          >
            +{module.capabilities.length - 3}
          </Badge>
        )}
      </div>

      {/* AI Features */}
      <div className="mt-2">
        <Text
          className="text-xs"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          AI: {module.ai_features.slice(0, 2).join(', ')}
          {module.ai_features.length > 2 && ` +${module.ai_features.length - 2}`}
        </Text>
      </div>

      {/* Integration Opportunity */}
      {!isActive && potentialIntegrations.length > 0 && (
        <div
          className="mt-2 p-2 rounded text-xs"
          style={{
            background: 'rgba(99, 102, 241, 0.1)',
            border: '1px solid rgba(99, 102, 241, 0.3)',
            color: 'rgba(99, 102, 241, 0.8)',
          }}
        >
          Activating enables integration with: {potentialIntegrations.join(', ')}
        </div>
      )}

      {/* Integrates With */}
      {isActive && module.integrates_with.length > 0 && (
        <div className="mt-2">
          <Text
            className="text-xs"
            style={{ color: 'var(--color-sentinel-text-disabled)' }}
          >
            Integrates with: {module.integrates_with.join(', ')}
          </Text>
        </div>
      )}

      {isActive && isProtectedBasePack && (
        <Text className="text-xs mt-2" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          Base pack module: cannot be deactivated.
        </Text>
      )}
    </Card>
  );
}

export default ModuleSelector;

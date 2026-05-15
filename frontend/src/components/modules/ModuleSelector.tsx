/**
 * Module Selector - Activate/Deactivate Bolt-on Modules
 *
 * Shows available modules and their integration status.
 * Allows activation of standalone modules that integrate when combined.
 */

import { useState } from 'react';

import { useModules } from '../../contexts/ModuleHooks';
import { MODULE_COLORS } from '../../lib/moduleRegistry';
import type { ModuleType, ModuleDefinition } from '../../lib/moduleRegistry';
import {
  Wind, Zap, Lock, Lightbulb, Sun, Droplets, Flame,
  Brain, Leaf, FileText, Gamepad2, Package, Plug, Link2, Bell
} from 'lucide-react';
import { ModuleDependencyWarning } from './ModuleDependencyWarning';
import { Badge } from '../Badge';

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

  const getDependentsToDisable = (_moduleType: ModuleType): ModuleType[] => {
    return [];
  };

  async function handleToggle(moduleType: ModuleType, currentlyActive: boolean) {
    const moduleDef = availableModules.find((module) => module.module_type === moduleType);
    if (currentlyActive && moduleDef?.mandatory) {
      return;
    }

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
      {showWarning && (
        <ModuleDependencyWarning
          moduleType={showWarning}
          onConfirm={() => handleConfirmDeactivate(showWarning)}
          onCancel={() => setShowWarning(null)}
          isLoading={isDeactivating}
        />
      )}

      {integrationSummary && integrationSummary.active_integrations.length > 0 && (
        <div
          className="mb-4 p-3 rounded-lg border"
          style={{
            background: 'rgba(99, 102, 241, 0.1)',
            borderColor: 'rgba(99, 102, 241, 0.3)',
          }}
        >
          <div className="flex items-center gap-2 mb-2">
            <Badge
              style={{
                background: 'rgba(99, 102, 241, 0.2)',
                color: 'rgba(99, 102, 241, 0.9)',
              }}
            >
              Cross-System Integration Active
            </Badge>
          </div>
          <div className="space-y-1">
            {integrationSummary.active_integrations.map(integration => (
              <p
                key={integration.id}
                className="text-xs"
                style={{ color: 'rgba(99, 102, 241, 0.8)' }}
              >
                {integration.name}: {integration.source.toUpperCase()} + {integration.target.toUpperCase()}
              </p>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {availableModules.map(moduleDef => {
          const isActive = isModuleActive(moduleDef.module_type);
          const isProtectedBasePack = moduleDef.mandatory;
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
      </div>

      {integrationSummary && integrationSummary.potential_integrations.length > 0 && (
        <div
          className="mt-4 p-3 rounded-lg"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            border: '1px solid var(--glass-border)',
          }}
        >
          <p
            className="text-xs font-medium mb-2"
            style={{ color: 'var(--color-sentinel-text-primary)' }}
          >
            Unlock More Integrations
          </p>
          <div className="space-y-1">
            {integrationSummary.potential_integrations.slice(0, 3).map(potential => (
              <p key={potential.id} className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Activate{' '}
                <Badge
                  style={{
                    background: 'rgba(59, 130, 246, 0.15)',
                    color: 'var(--color-sentinel-blue)',
                  }}
                >
                  {potential.requires_module}
                </Badge>{' '}
                to enable <span className="font-medium">{potential.name}</span>
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const MODULE_ICONS: Partial<Record<ModuleType, React.ComponentType<any>>> = {
  kpi: Package,
  ml: Brain,
  notifications: Bell,
  integrations: Link2,
  simbiot: Plug,
  logging: FileText,
  assets: Package,
  hvac: Wind,
  energy: Zap,
  lighting: Lightbulb,
  solar: Sun,
  water: Droplets,
  fire: Flame,
  security: Lock,
  digital_twin: Package,
  hvac_control: Gamepad2,
  energy_control: Gamepad2,
  lighting_control: Gamepad2,
  solar_control: Gamepad2,
  water_control: Gamepad2,
  security_control: Gamepad2,
  digital_twin_control: Gamepad2,
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
    <div
      className="rounded-lg p-4 transition-all overflow-hidden"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: `1px solid ${isActive ? `var(--color-sentinel-${color})` : 'var(--color-sentinel-border)'}`,
        opacity: isActive ? 1 : 0.75,
      }}
    >
      <div className="flex items-start justify-between">
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
            <div className="flex items-center gap-2">
              <p
                className="font-bold"
                style={{ color: 'var(--color-sentinel-text-primary)' }}
              >
                {module.name}
              </p>
              <Badge
                style={{
                  background: isActive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(107, 114, 128, 0.15)',
                  color: isActive ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-text-secondary)',
                }}
              >
                {isActive ? 'Active' : 'Inactive'}
              </Badge>
              {isProtectedBasePack && (
                <Badge
                  style={{
                    background: 'rgba(59, 130, 246, 0.15)',
                    color: 'var(--color-sentinel-blue)',
                  }}
                >
                  Base Pack
                </Badge>
              )}
            </div>
            <p
              className="text-xs mt-1"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              {module.description}
            </p>
          </div>
        </div>
        <SentinelSwitch
          checked={isActive}
          onChange={onToggle}
          disabled={isLoading || (isActive && isProtectedBasePack)}
        />
      </div>

      {isActive && healthScore !== undefined && (
        <div className="flex items-center gap-2 mt-3">
          <span
            className="text-xs"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            Health:
          </span>
          <Badge
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
        </div>
      )}

      <div className="mt-2 flex flex-wrap gap-1">
        {module.capabilities.slice(0, 3).map(cap => (
          <Badge
            key={cap.id}
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
            style={{
              background: 'rgba(107, 114, 128, 0.15)',
              color: 'var(--color-sentinel-text-secondary)',
            }}
          >
            +{module.capabilities.length - 3}
          </Badge>
        )}
      </div>

      <div className="mt-2">
        <p
          className="text-xs"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          AI: {module.ai_features.slice(0, 2).join(', ')}
          {module.ai_features.length > 2 && ` +${module.ai_features.length - 2}`}
        </p>
      </div>

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

      {isActive && module.integrates_with.length > 0 && (
        <div className="mt-2">
          <p
            className="text-xs"
            style={{ color: 'var(--color-sentinel-text-disabled)' }}
          >
            Integrates with: {module.integrates_with.join(', ')}
          </p>
        </div>
      )}

      {isActive && isProtectedBasePack && (
        <p className="text-xs mt-2" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          Base pack module: cannot be deactivated.
        </p>
      )}
    </div>
  );
}

export default ModuleSelector;

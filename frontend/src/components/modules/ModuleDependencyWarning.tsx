/* eslint-disable react-refresh/only-export-components */
/**
 * Module Dependency Warning Modal
 *
 * Shows cascade warnings when deactivating modules that others depend on.
 * Example: Deactivating CONTROL will also disable SOLAR & LIGHTING
 */

import { AlertTriangle, CheckCircle2, X } from 'lucide-react';
import type { ModuleType } from '../../lib/moduleRegistry';

// Dependencies: per-discipline control add-ons have no cascading deps
const DEPENDENT_MODULES: Partial<Record<ModuleType, ModuleType[]>> = {
  // No cascading dependencies in the new architecture.
  // Each control add-on is independent of other modules.
};

// User-friendly module names
const MODULE_NAMES: Record<string, string> = {
  // Base Platform
  kpi: 'KPI Dashboard',
  ml: 'AI & ML',
  notifications: 'Notifications',
  integrations: 'System Integrations',
  simbiot: 'SIMBIOT Integration',
  logging: 'Logging & Diagnostics',
  assets: 'Asset Management',
  // Base Building Systems
  hvac: 'HVAC Monitoring',
  energy: 'Energy Monitoring',
  lighting: 'Lighting',
  solar: 'Solar & BESS',
  water: 'Water Management',
  fire: 'Fire Safety',
  security: 'Security',
  digital_twin: 'Digital Twin',
  // Control Add-ons
  hvac_control: 'HVAC Control',
  energy_control: 'Energy Control',
  lighting_control: 'Lighting Control',
  solar_control: 'Solar Control',
  water_control: 'Water Control',
  security_control: 'Security Control',
  digital_twin_control: 'Digital Twin Control',
  // Standalone Add-ons
  maintenance: 'Maintenance & Work Orders',
  financial: 'Financial & Contracts',
  compliance: 'Compliance & ESG',
  fleet_ml: 'Fleet ML Analytics',
};

interface ModuleDependencyWarningProps {
  moduleType: ModuleType;
  onConfirm: () => void;
  onCancel: () => void;
  isLoading?: boolean;
}

export function ModuleDependencyWarning({
  moduleType,
  onConfirm,
  onCancel,
  isLoading = false,
}: ModuleDependencyWarningProps) {
  const dependents = DEPENDENT_MODULES[moduleType] || [];

  // If no dependents, don't show modal
  if (dependents.length === 0) {
    onConfirm();
    return null;
  }

  const moduleName = MODULE_NAMES[moduleType] || moduleType;
  const dependentNames = dependents.map(m => MODULE_NAMES[m] || m);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div
        className="rounded-lg shadow-2xl max-w-sm w-full p-6 space-y-4"
        style={{
          background: 'var(--color-sentinel-bg-secondary)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        {/* Header */}
        <div className="flex items-start gap-3">
          <AlertTriangle
            className="h-6 w-6 flex-shrink-0 mt-0.5"
            style={{ color: 'var(--color-sentinel-amber)' }}
          />
          <div className="flex-1">
            <h3
              className="font-bold text-lg"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              Disable {moduleName}?
            </h3>
            <p
              className="text-sm mt-1"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              This will also disable the following modules:
            </p>
          </div>
          <button
            onClick={onCancel}
            disabled={isLoading}
            className="flex-shrink-0 -mr-1 -mt-1 p-1 hover:bg-white/10 rounded transition-colors"
            aria-label="Close"
          >
            <X className="h-5 w-5" style={{ color: 'var(--color-sentinel-text-secondary)' }} />
          </button>
        </div>

        {/* Dependent modules list */}
        <div className="space-y-2 bg-black/30 rounded p-3">
          {dependentNames.map(name => (
            <div key={name} className="flex items-center gap-2">
              <CheckCircle2
                className="h-4 w-4 flex-shrink-0"
                style={{ color: 'var(--color-sentinel-red)' }}
              />
              <span
                className="text-sm"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              >
                {name}
              </span>
            </div>
          ))}
        </div>

        {/* Warning message */}
        <p
          className="text-xs"
          style={{ color: 'var(--color-sentinel-text-disabled)' }}
        >
          These modules depend on {moduleName} to function. Users will lose access to these features.
        </p>

        {/* Actions */}
        <div className="flex gap-3 pt-2">
          <button
            onClick={onCancel}
            disabled={isLoading}
            className="flex-1 px-4 py-2 rounded font-medium transition-colors"
            style={{
              background: 'rgba(255, 255, 255, 0.1)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              color: 'var(--color-sentinel-text-primary)',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              opacity: isLoading ? 0.5 : 1,
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className="flex-1 px-4 py-2 rounded font-medium transition-colors"
            style={{
              background: 'rgba(220, 38, 38, 0.2)',
              border: '1px solid rgba(220, 38, 38, 0.5)',
              color: 'var(--color-sentinel-red)',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              opacity: isLoading ? 0.5 : 1,
            }}
          >
            {isLoading ? 'Disabling...' : 'Disable All'}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Check if a module has dependents that will be disabled
 */
export function getModuleDependents(moduleType: ModuleType): ModuleType[] {
  return DEPENDENT_MODULES[moduleType] || [];
}

/**
 * Check if disabling a module will cascade
 */
export function hasCascadingDependents(moduleType: ModuleType): boolean {
  return (DEPENDENT_MODULES[moduleType] || []).length > 0;
}

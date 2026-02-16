/**
 * Module Dependency Warning Modal
 *
 * Shows cascade warnings when deactivating modules that others depend on.
 * Example: Deactivating CONTROL will also disable SOLAR & LIGHTING
 */

import { useState } from 'react';
import { AlertTriangle, CheckCircle2, X } from 'lucide-react';
import type { ModuleType } from '../../lib/moduleRegistry';

// Dependencies: modules that cannot function without other modules
const DEPENDENT_MODULES: Record<ModuleType, ModuleType[]> = {
  // Core infrastructure
  kpi: [],
  ml: [],
  hvac: [],
  energy: [],
  assets: [],
  simbiot: [],
  integrations: [],
  notifications: [],
  // Paid add-ons
  control: ['solar', 'lighting'] as ModuleType[],
  maintenance: [],
  digital_twin: [],
  // Building system add-ons
  lighting: [],
  fire: [],
  security: [],
  solar: [],
  sustainability: [],
  water: [],
  contracts: [],
};

// User-friendly module names
const MODULE_NAMES: Record<string, string> = {
  control: 'Building Controls',
  solar: 'Solar & BESS',
  lighting: 'Lighting & Occupancy',
  hvac: 'HVAC Monitoring',
  energy: 'Energy Monitoring',
  ml: 'AI & ML',
  notifications: 'Notifications',
  integrations: 'System Integrations',
  security: 'Security',
  fire: 'Fire Safety',
  water: 'Water Management',
  sustainability: 'Sustainability & ESG',
  contracts: 'Contracts & SLA',
  maintenance: 'Maintenance & Work Orders',
  digital_twin: 'Digital Twin',
  assets: 'Asset Management',
  simbiot: 'SIMBIOT Integration',
  access: 'Access Control',
  kpi: 'KPI Dashboard',
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

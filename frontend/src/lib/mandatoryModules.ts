/**
 * Mandatory Base Modules
 *
 * These modules are always active and cannot be deactivated by users.
 * Every user has access to these core features as part of the base package.
 *
 * Base package includes:
 * - KPI: Dashboard KPI metrics
 * - ML: Risk Intelligence — equipment health and predictions
 * - HVAC: Building system monitoring (read-only, no control)
 * - Energy: Energy monitoring and consumption data
 * - Assets: Asset visibility and lifecycle
 * - SIMBIOT: Integration setup and onboarding
 * - Notifications: Alert notifications
 * - Integrations: System health / SIMBIOT connection status
 *
 * Note: Dashboard, Digital Twin, and System Health pages are always visible
 * in the sidebar (BASE_NAV_ITEMS) and don't need module gating.
 */

import type { ModuleType } from './moduleRegistry';

export const MANDATORY_MODULES: ModuleType[] = [
  'kpi',             // Dashboard KPI metrics
  'ml',              // Risk Intelligence - Equipment health and predictions
  'hvac',            // HVAC monitoring (read-only in base)
  'energy',          // Energy monitoring and consumption data
  'assets',          // Asset visibility and lifecycle
  'simbiot',         // BMS onboarding and integration setup
  'notifications',   // Alert notifications
  'integrations',    // System health / SIMBIOT connection status
];

/**
 * Check if a module is mandatory (cannot be deactivated)
 */
export function isMandatoryModule(moduleType: ModuleType): boolean {
  return MANDATORY_MODULES.includes(moduleType);
}

/**
 * Get display names for mandatory modules
 */
export const MANDATORY_MODULE_NAMES: Partial<Record<ModuleType, string>> = {
  'kpi': 'KPI Dashboard',
  'ml': 'Risk Intelligence',
  'hvac': 'HVAC Monitoring',
  'energy': 'Energy Monitoring',
  'assets': 'Asset Workflow',
  'simbiot': 'SIMBIOT',
  'notifications': 'Notifications',
  'integrations': 'System Health',
};

/**
 * Error message for attempting to deactivate mandatory module
 */
export function getMandatoryModuleErrorMessage(moduleType: ModuleType): string {
  const moduleName = MANDATORY_MODULE_NAMES[moduleType] || moduleType;
  return `${moduleName} is a mandatory base module and cannot be disabled.`;
}

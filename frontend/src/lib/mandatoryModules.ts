/**
 * Mandatory Base Modules (15 total)
 *
 * These modules are always active and cannot be deactivated by users.
 * Includes 7 platform modules + 8 building system modules.
 *
 * Platform (7):
 * - KPI, ML, Notifications, Integrations, SIMBIOT, Logging, Assets
 *
 * Building Systems (8):
 * - HVAC, Energy, Lighting, Solar, Water, Fire, Security, Digital Twin
 *
 * All monitoring is base — if BMS reads it, SENTINEL shows it.
 * Control features within each system are gated by {x}_control add-ons.
 */

import type { ModuleType } from './moduleRegistry';

export const MANDATORY_MODULES: ModuleType[] = [
  // Base Platform (7)
  'kpi',
  'ml',
  'notifications',
  'integrations',
  'simbiot',
  'logging',
  'assets',
  // Base Building Systems (8)
  'hvac',
  'energy',
  'lighting',
  'solar',
  'water',
  'fire',
  'security',
  'digital_twin',
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
  'ml': 'ML Intelligence',
  'notifications': 'Notifications',
  'integrations': 'System Health',
  'simbiot': 'SIMBIOT',
  'logging': 'Logging',
  'assets': 'Asset Workflow',
  'hvac': 'HVAC',
  'energy': 'Energy',
  'lighting': 'Lighting',
  'solar': 'Solar & BESS',
  'water': 'Water',
  'fire': 'Fire Safety',
  'security': 'Security',
  'digital_twin': 'Digital Twin',
};

/**
 * Error message for attempting to deactivate mandatory module
 */
export function getMandatoryModuleErrorMessage(moduleType: ModuleType): string {
  const moduleName = MANDATORY_MODULE_NAMES[moduleType] || moduleType;
  return `${moduleName} is a mandatory base module and cannot be disabled.`;
}

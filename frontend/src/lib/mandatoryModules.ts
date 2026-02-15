/**
 * Mandatory Base Modules
 * 
 * These modules are always active and cannot be deactivated by users.
 * Every user has access to these core features.
 */

import type { ModuleType } from './moduleRegistry';

export const MANDATORY_MODULES: ModuleType[] = [
  'kpi',           // KPI Overview - Core metrics and statistics
  'security',      // Site Protection - Building security status
  'ml',            // Risk Intelligence - Equipment health and predictions
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
export const MANDATORY_MODULE_NAMES: Record<ModuleType, string> = {
  'kpi': 'KPI Overview',
  'security': 'Site Protection',
  'ml': 'Risk Intelligence',
};

/**
 * Error message for attempting to deactivate mandatory module
 */
export function getMandatoryModuleErrorMessage(moduleType: ModuleType): string {
  const moduleName = MANDATORY_MODULE_NAMES[moduleType] || moduleType;
  return `${moduleName} is a mandatory base module and cannot be disabled.`;
}

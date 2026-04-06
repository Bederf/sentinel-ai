/**
 * Mandatory Base Modules (7 total — platform only)
 *
 * These modules are always active and cannot be deactivated.
 * They are the SENTINEL platform itself, not building systems.
 *
 * Platform (7):
 * - KPI, ML, Notifications, Integrations, SIMBIOT, Logging, Assets
 *
 * Building system monitoring modules (hvac, energy, lighting, water,
 * fire, security, solar, digital_twin) are included in base SENTINEL
 * but activated per-site based on what is physically connected to the BMS.
 * A tab only appears when that system is active for the site.
 *
 * Control add-ons (hvac_control, energy_control, etc.) are the commercial
 * upsell — monitoring is free, control is purchased per system.
 */

import type { ModuleType } from './moduleRegistry';

export const MANDATORY_MODULES: ModuleType[] = [
  // Platform — always on, every site (7)
  'kpi',
  'ml',
  'notifications',
  'integrations',
  'simbiot',
  'logging',
  'assets',
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
};

/**
 * Error message for attempting to deactivate mandatory module
 */
export function getMandatoryModuleErrorMessage(moduleType: ModuleType): string {
  const moduleName = MANDATORY_MODULE_NAMES[moduleType] || moduleType;
  return `${moduleName} is a mandatory base module and cannot be disabled.`;
}

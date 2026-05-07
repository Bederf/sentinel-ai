import type { ModuleDefinition, ModuleType } from './moduleRegistry';

const FALLBACK_MANDATORY_MODULES: ModuleType[] = [
  'kpi',
  'ml',
  'notifications',
  'integrations',
  'simbiot',
  'logging',
  'assets',
  'hvac',
  'energy',
  'lighting',
  'solar',
  'water',
  'fire',
  'security',
  'digital_twin',
];

let mandatoryModules = [...FALLBACK_MANDATORY_MODULES];
let mandatoryModuleSet = new Set<ModuleType>(mandatoryModules);
let mandatoryModuleNames: Partial<Record<ModuleType, string>> = {};

function buildMandatoryModuleNames(modules: ModuleDefinition[]): Partial<Record<ModuleType, string>> {
  return modules.reduce<Partial<Record<ModuleType, string>>>((acc, moduleDef) => {
    if (moduleDef.mandatory) {
      acc[moduleDef.module_type] = moduleDef.name;
    }
    return acc;
  }, {});
}

export function syncMandatoryModulesFromRegistry(modules: ModuleDefinition[]): void {
  const registryMandatoryModules = modules.filter((moduleDef) => moduleDef.mandatory).map((moduleDef) => moduleDef.module_type);
  if (!registryMandatoryModules.length) {
    return;
  }

  mandatoryModules = registryMandatoryModules;
  mandatoryModuleSet = new Set(registryMandatoryModules);
  mandatoryModuleNames = buildMandatoryModuleNames(modules);
}

export function getMandatoryModules(): ModuleType[] {
  return [...mandatoryModules];
}

export function isMandatoryModule(moduleType: ModuleType, modules?: ModuleDefinition[]): boolean {
  if (modules?.length) {
    return modules.some((moduleDef) => moduleDef.module_type === moduleType && moduleDef.mandatory);
  }
  return mandatoryModuleSet.has(moduleType);
}

export function getMandatoryModuleErrorMessage(moduleType: ModuleType, modules?: ModuleDefinition[]): string {
  const moduleName =
    modules?.find((moduleDef) => moduleDef.module_type === moduleType)?.name ||
    mandatoryModuleNames[moduleType] ||
    moduleType;
  return `${moduleName} is a mandatory base module and cannot be disabled.`;
}

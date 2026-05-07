import type { ModuleDefinition, ModuleType } from "../../lib/moduleRegistry";

export interface FeatureToggleCard {
  id: string;
  label: string;
  moduleType: ModuleType;
  description: string;
  note?: string;
  isControlToggle?: boolean;
}

export interface BuildingSystemCard {
  id: string;
  label: string;
  baseModule: ModuleType;
  controlModule?: ModuleType;
  description: string;
}

const PLATFORM_MODULE_TYPES = new Set<ModuleType>([
  "kpi",
  "ml",
  "notifications",
  "integrations",
  "simbiot",
  "logging",
  "assets",
]);

const BUILDING_SYSTEM_MODULE_TYPES = new Set<ModuleType>([
  "hvac",
  "energy",
  "lighting",
  "solar",
  "water",
  "fire",
  "security",
  "digital_twin",
]);

const CONTROL_MODULE_BY_BASE: Partial<Record<ModuleType, ModuleType>> = {
  hvac: "hvac_control",
  energy: "energy_control",
  lighting: "lighting_control",
  solar: "solar_control",
  water: "water_control",
  security: "security_control",
  digital_twin: "digital_twin_control",
};

function sortModules(modules: ModuleDefinition[]): ModuleDefinition[] {
  return [...modules].sort((left, right) => left.name.localeCompare(right.name));
}

export function getPlatformStatusCards(modules: ModuleDefinition[]): FeatureToggleCard[] {
  return sortModules(modules)
    .filter((moduleDef) => PLATFORM_MODULE_TYPES.has(moduleDef.module_type))
    .map((moduleDef) => ({
      id: moduleDef.module_type,
      label: moduleDef.name,
      moduleType: moduleDef.module_type,
      description: moduleDef.description,
      note: moduleDef.mandatory ? "Always on" : undefined,
    }));
}

export function getBuildingSystemCards(modules: ModuleDefinition[]): BuildingSystemCard[] {
  const moduleMap = new Map(modules.map((moduleDef) => [moduleDef.module_type, moduleDef]));
  return sortModules(modules)
    .filter((moduleDef) => BUILDING_SYSTEM_MODULE_TYPES.has(moduleDef.module_type))
    .map((moduleDef) => ({
      id: `${moduleDef.module_type}-system`,
      label: moduleDef.name,
      baseModule: moduleDef.module_type,
      controlModule: moduleMap.has(CONTROL_MODULE_BY_BASE[moduleDef.module_type] || "")
        ? CONTROL_MODULE_BY_BASE[moduleDef.module_type]
        : undefined,
      description: moduleDef.description,
    }));
}

export function getAddonToggleCards(modules: ModuleDefinition[]): FeatureToggleCard[] {
  return sortModules(modules)
    .filter((moduleDef) =>
      !moduleDef.mandatory &&
      !moduleDef.module_type.endsWith("_control") &&
      !PLATFORM_MODULE_TYPES.has(moduleDef.module_type) &&
      !BUILDING_SYSTEM_MODULE_TYPES.has(moduleDef.module_type)
    )
    .map((moduleDef) => ({
      id: `${moduleDef.module_type}-addon`,
      label: moduleDef.name,
      moduleType: moduleDef.module_type,
      description: moduleDef.description,
    }));
}

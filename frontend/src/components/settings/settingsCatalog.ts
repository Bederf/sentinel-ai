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
  licensed: boolean;
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

// All 7 building system modules — require licensing per site.
// Monitoring is always on when licensed; control is a separate toggle.
// Digital Twin is a visualization add-on (listed in Add-ons), not a building system.
const BUILDING_SYSTEM_MODULE_TYPES = new Set<ModuleType>([
  "hvac",
  "energy",
  "lighting",
  "solar",
  "water",
  "fire",
  "security",
]);

const CONTROL_MODULE_BY_BASE: Partial<Record<ModuleType, ModuleType>> = {
  hvac: "hvac_control",
  energy: "energy_control",
  lighting: "lighting_control",
  solar: "solar_control",
  water: "water_control",
  security: "security_control",
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

export function getBuildingSystemCards(modules: ModuleDefinition[], controller?: { isModuleActive: (type: ModuleType) => boolean }): BuildingSystemCard[] {
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
      licensed: controller ? controller.isModuleActive(moduleDef.module_type) : false,
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

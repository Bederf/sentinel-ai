import type { ModuleType } from "../../lib/moduleRegistry";
import { MANDATORY_MODULES } from "../../lib/mandatoryModules";

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

export const BASE_PACK_LOCKED_MODULES: ModuleType[] = MANDATORY_MODULES;

export const PLATFORM_STATUS_CARDS: FeatureToggleCard[] = [
  { id: "kpi", label: "KPI Dashboard", moduleType: "kpi", description: "Portfolio and site KPI scorecards.", note: "Always on" },
  { id: "ml", label: "ML Intelligence", moduleType: "ml", description: "Anomaly detection and predictive maintenance.", note: "Always on" },
  { id: "notifications", label: "Notifications", moduleType: "notifications", description: "Alert routing and acknowledgement.", note: "Always on" },
  { id: "integrations", label: "System Health", moduleType: "integrations", description: "Integration health and data quality.", note: "Always on" },
  { id: "simbiot", label: "SIMBIOT", moduleType: "simbiot", description: "BMS connection wizard and data discovery.", note: "Always on" },
  { id: "logging", label: "Logging", moduleType: "logging", description: "Audit trail and event logs.", note: "Always on" },
  { id: "assets", label: "Assets", moduleType: "assets", description: "Asset registry and lifecycle.", note: "Always on" },
];

export const BUILDING_SYSTEM_CARDS: BuildingSystemCard[] = [
  { id: "hvac-system", label: "HVAC", baseModule: "hvac", controlModule: "hvac_control", description: "Heating, ventilation, and air conditioning." },
  { id: "energy-system", label: "Energy", baseModule: "energy", controlModule: "energy_control", description: "Power metering, generators, UPS." },
  { id: "lighting-system", label: "Lighting", baseModule: "lighting", controlModule: "lighting_control", description: "DALI lighting and occupancy." },
  { id: "solar-system", label: "Solar & BESS", baseModule: "solar", controlModule: "solar_control", description: "Solar PV and battery storage." },
  { id: "water-system", label: "Water", baseModule: "water", controlModule: "water_control", description: "Water monitoring and leak detection." },
  { id: "security-system", label: "Security", baseModule: "security", controlModule: "security_control", description: "Access control and CCTV." },
  { id: "fire-system", label: "Fire", baseModule: "fire", description: "Fire alarm monitoring (always read-only)." },
  { id: "twin-system", label: "Digital Twin", baseModule: "digital_twin", controlModule: "digital_twin_control", description: "3D/2D building visualization." },
];

export const ADDON_TOGGLE_CARDS: FeatureToggleCard[] = [
  { id: "maintenance-addon", label: "Maintenance", moduleType: "maintenance", description: "Work orders, scheduling, technician dispatch." },
  { id: "financial-addon", label: "Financial", moduleType: "financial", description: "Contracts, profitability, budget, SLA." },
  { id: "compliance-addon", label: "Compliance", moduleType: "compliance", description: "Carbon Tax, Green Star, SANS, ESG." },
  { id: "simulation-addon", label: "Simulation", moduleType: "simulation", description: "What-if scenarios and ROI modelling." },
  { id: "fleet-ml-addon", label: "Fleet ML", moduleType: "fleet_ml", description: "Cross-portfolio analytics and benchmarking." },
  { id: "space-optimization-addon", label: "Space Optimization", moduleType: "space_optimization", description: "Ghost booking detection, room right-sizing, focus room analytics." },
];

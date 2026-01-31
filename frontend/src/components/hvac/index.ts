/**
 * HVAC Module Exports
 *
 * Sellable HVAC bolt-on module for SENTINEL BMS Intelligence Platform.
 *
 * Capabilities:
 * - Zone temperature monitoring and control
 * - AHU/FCU/Chiller equipment status and health
 * - Thermal runway calculations for load shedding
 * - Pre-cooling schedule visualization
 * - Comfort complaint handling
 * - Engineer-configurable health calculations
 */

// Main Dashboard
import { HVACDashboard } from "./HVACDashboard";
export { HVACDashboard, default as HVACDashboardDefault } from "./HVACDashboard";

// Zone Components
export { ZoneOverviewPanel } from "./ZoneOverviewPanel";

// Equipment Components
export { EquipmentStatusPanel } from "./EquipmentStatusPanel";
export { ChillerControlPanel } from "./ChillerControlPanel";

// Optimization Components
export { ThermalOptimizationPanel } from "./ThermalOptimizationPanel";

// Comfort Components
export { ComfortAssistant } from "./ComfortAssistant";

// Configuration Components
export { HealthConfigEditor } from "./HealthConfigEditor";

// Module Information
export const moduleInfo = {
  id: "hvac",
  name: "HVAC",
  description: "Heating, ventilation, and air conditioning control and monitoring",
  version: "1.0.0",
  capabilities: [
    "zone_control",
    "equipment_monitoring",
    "health_scoring",
    "thermal_optimization",
    "comfort_management",
    "load_shedding_prep",
  ],
  integrations: [
    {
      target: "energy",
      type: "load_shedding",
      description: "Reduce HVAC load during generator power",
    },
    {
      target: "energy",
      type: "demand_response",
      description: "Coordinate with peak demand management",
    },
    {
      target: "security",
      type: "occupancy_based",
      description: "Adjust HVAC based on occupancy",
    },
    {
      target: "lighting",
      type: "thermal_gain",
      description: "Coordinate with lighting heat load",
    },
  ],
};

// Default export for dynamic import
export default HVACDashboard;

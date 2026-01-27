/**
 * Demo Controls Data - SENTINEL demo scenarios and device configurations
 *
 * Features:
 * - Predefined demo scenarios for control panel demonstrations
 * - Device configurations for demo devices
 * - Safety status scenarios
 * - Demo narratives and success/failure stories
 */

import type { Device, SafetyStatus } from "../lib/api";

// Demo device configurations
export const demoDevices: Device[] = [
  {
    id: "chiller-gateway-01",
    name: "Gateway Chiller",
    device_type: "hvac",
    protocol: "mock",
    location: "Basement Plant Room",
    site_id: "fnb-gateway",
    description: "Main chiller for Gateway building, 21 years old. Critical for building cooling.",
    manufacturer: "Trane",
    model: "RTAC 200",
    points: {
      supply_temp: {
        name: "supply_temp",
        point_type: "analog_input",
        description: "Chilled water supply temperature",
        unit: "°C",
        min_value: 5.0,
        max_value: 15.0,
        default_value: 7.2,
        writable: false,
      },
      return_temp: {
        name: "return_temp",
        point_type: "analog_input",
        description: "Chilled water return temperature",
        unit: "°C",
        min_value: 10.0,
        max_value: 20.0,
        default_value: 12.5,
        writable: false,
      },
      chiller_status: {
        name: "chiller_status",
        point_type: "multistate_value",
        description: "Chiller operational status",
        unit: "",
        default_value: 1,
        writable: true,
        metadata: {
          states: {
            "0": "off",
            "1": "running",
            "2": "alarm",
            "3": "maintenance",
          },
        },
      },
      setpoint: {
        name: "setpoint",
        point_type: "analog_value",
        description: "Chilled water setpoint temperature",
        unit: "°C",
        min_value: 5.0,
        max_value: 10.0,
        default_value: 7.0,
        writable: true,
        priority: 10,
      },
    },
    metadata: {
      critical: true,
      safety_device: true,
      maintenance_due: "2026-02-15",
      age_years: 21,
    },
  },
  {
    id: "ahu-level3-01",
    name: "Level 3 AHU",
    device_type: "hvac",
    protocol: "mock",
    location: "Level 3 Plant Room",
    site_id: "fnb-gateway",
    description: "Air handling unit serving executive offices. Provides conditioned air to CTO office.",
    manufacturer: "Carrier",
    model: "39ER",
    points: {
      supply_air_temp: {
        name: "supply_air_temp",
        point_type: "analog_input",
        description: "Supply air temperature",
        unit: "°C",
        min_value: 15.0,
        max_value: 25.0,
        default_value: 18.5,
        writable: false,
      },
      return_air_temp: {
        name: "return_air_temp",
        point_type: "analog_input",
        description: "Return air temperature",
        unit: "°C",
        min_value: 20.0,
        max_value: 30.0,
        default_value: 23.5,
        writable: false,
      },
      fan_status: {
        name: "fan_status",
        point_type: "binary_value",
        description: "Fan on/off status",
        unit: "",
        default_value: true,
        writable: true,
      },
      damper_position: {
        name: "damper_position",
        point_type: "analog_value",
        description: "Outside air damper position",
        unit: "%",
        min_value: 0,
        max_value: 100,
        default_value: 30,
        writable: true,
      },
    },
    metadata: {
      zone: "executive",
      occupancy_schedule: "08:00-18:00",
      serves_cto_office: true,
    },
  },
  {
    id: "lighting-lobby-01",
    name: "Lobby Lighting Panel",
    device_type: "lighting",
    protocol: "mock",
    location: "Ground Floor Lobby",
    site_id: "fnb-gateway",
    description: "Lighting control panel for main lobby area. Includes emergency lighting circuit.",
    manufacturer: "Philips",
    model: "Dynalite",
    points: {
      circuit1_level: {
        name: "circuit1_level",
        point_type: "analog_value",
        description: "Main entrance lighting level",
        unit: "%",
        min_value: 0,
        max_value: 100,
        default_value: 75,
        writable: true,
      },
      circuit2_level: {
        name: "circuit2_level",
        point_type: "analog_value",
        description: "Reception desk lighting level",
        unit: "%",
        min_value: 0,
        max_value: 100,
        default_value: 100,
        writable: true,
      },
      emergency_lighting: {
        name: "emergency_lighting",
        point_type: "binary_value",
        description: "Emergency lighting circuit status",
        unit: "",
        default_value: false,
        writable: false,
      },
      occupancy_sensor: {
        name: "occupancy_sensor",
        point_type: "binary_input",
        description: "Occupancy sensor status",
        unit: "",
        default_value: true,
        writable: false,
      },
    },
    metadata: {
      emergency_circuit: true,
      schedule_enabled: true,
      audit_trail: true,
    },
  },
];

// Demo scenarios
export interface DemoScenario {
  id: string;
  name: string;
  description: string;
  deviceId: string;
  safetyStatus: "safe" | "warning" | "blocked";
  safetyMessage?: string;
  initialActions?: Array<{
    point: string;
    value: number | boolean;
    description: string;
  }>;
  expectedOutcome: string;
  narrative: string;
}

export const demoScenarios: DemoScenario[] = [
  {
    id: "scenario-1",
    name: "Adjust Chiller Temperature",
    description: "Safe operation - adjust chiller setpoint within safe limits",
    deviceId: "chiller-gateway-01",
    safetyStatus: "safe",
    safetyMessage: "All safety rules passed. Temperature adjustment within safe operating range.",
    initialActions: [
      {
        point: "setpoint",
        value: 7.5,
        description: "Increase chiller setpoint from 7.0°C to 7.5°C",
      },
    ],
    expectedOutcome: "Chiller setpoint successfully adjusted. System remains within safe operating parameters.",
    narrative: "As FM operator, you need to slightly increase chiller temperature to reduce energy consumption while maintaining comfort.",
  },
  {
    id: "scenario-2",
    name: "Override Safety Limits",
    description: "Safety warning - attempt to set chiller temperature outside safe range",
    deviceId: "chiller-gateway-01",
    safetyStatus: "warning",
    safetyMessage: "Warning: Temperature setpoint exceeds recommended safe operating range (5-10°C).",
    initialActions: [
      {
        point: "setpoint",
        value: 4.5,
        description: "Attempt to set chiller below minimum safe temperature",
      },
    ],
    expectedOutcome: "Control action allowed with warning. System logs safety override for audit trail.",
    narrative: "During emergency maintenance, you need to temporarily lower chiller temperature below normal limits. Safety system warns but allows override with audit trail.",
  },
  {
    id: "scenario-3",
    name: "Emergency Stop",
    description: "Safety blocked - attempt to stop critical chiller during peak cooling",
    deviceId: "chiller-gateway-01",
    safetyStatus: "blocked",
    safetyMessage: "Blocked: Cannot stop critical chiller during peak cooling hours (10:00-16:00).",
    initialActions: [
      {
        point: "chiller_status",
        value: 0,
        description: "Attempt to stop critical chiller",
      },
    ],
    expectedOutcome: "Control action blocked by safety system. Requires emergency override authorization.",
    narrative: "Attempting to stop the main chiller during business hours would cause building comfort issues. Safety system blocks this action to prevent disruption.",
  },
  {
    id: "scenario-4",
    name: "Lighting Schedule Override",
    description: "Audit trail example - override lighting schedule for special event",
    deviceId: "lighting-lobby-01",
    safetyStatus: "safe",
    safetyMessage: "Lighting override permitted. Audit trail will record override reason and duration.",
    initialActions: [
      {
        point: "circuit1_level",
        value: 100,
        description: "Set lobby lighting to 100% for evening event",
      },
      {
        point: "circuit2_level",
        value: 100,
        description: "Set reception lighting to 100%",
      },
    ],
    expectedOutcome: "Lighting successfully overridden. Audit trail records: 'Special event - executive dinner, 19:00-22:00'.",
    narrative: "The CTO is hosting an executive dinner in the lobby after hours. You need to override the lighting schedule and maintain full brightness for the event.",
  },
  {
    id: "scenario-5",
    name: "AHU Mode Change",
    description: "Change AHU operating mode based on occupancy",
    deviceId: "ahu-level3-01",
    safetyStatus: "safe",
    safetyMessage: "AHU mode change permitted. Occupancy sensor indicates office is occupied.",
    initialActions: [
      {
        point: "damper_position",
        value: 50,
        description: "Increase outside air damper to 50% for better ventilation",
      },
    ],
    expectedOutcome: "AHU ventilation increased. Improved indoor air quality for occupied executive offices.",
    narrative: "The CTO has requested better ventilation in the executive offices. You're adjusting the AHU to bring in more fresh air while maintaining comfort.",
  },
];

// Demo safety status configurations
export const demoSafetyStatuses: Record<string, any> = {
  "chiller-gateway-01": {
    safe: {
      status: "safe",
      message: "All safety rules passed. Chiller operating within normal parameters.",
      rules: [
        { rule: "Temperature range (5-10°C)", status: "passed", description: "Current setpoint: 7.0°C" },
        { rule: "Compressor pressure limits", status: "passed", description: "Pressure: 12.5 bar" },
        { rule: "Critical device protection", status: "passed", description: "Critical device monitoring active" },
      ],
    },
    warning: {
      status: "warning",
      message: "Warning: Temperature setpoint approaching minimum safe limit.",
      rules: [
        { rule: "Temperature range (5-10°C)", status: "warning", description: "Setpoint: 4.5°C (below minimum)" },
        { rule: "Compressor pressure limits", status: "passed", description: "Pressure: 12.5 bar" },
        { rule: "Critical device protection", status: "warning", description: "Operating outside normal range" },
      ],
    },
    blocked: {
      status: "blocked",
      message: "Blocked: Cannot stop critical chiller during peak cooling hours.",
      rules: [
        { rule: "Operational hours protection", status: "failed", description: "Peak hours: 10:00-16:00" },
        { rule: "Critical cooling requirement", status: "failed", description: "Building requires cooling" },
        { rule: "Emergency override required", status: "failed", description: "Requires Level 2 authorization" },
      ],
    },
  },
  "ahu-level3-01": {
    safe: {
      status: "safe",
      message: "AHU operating normally. Executive office occupied.",
      rules: [
        { rule: "Temperature comfort (18-26°C)", status: "passed", description: "Room temp: 22.5°C" },
        { rule: "Occupancy-based control", status: "passed", description: "Office occupied" },
        { rule: "Ventilation requirements", status: "passed", description: "Outside air: 30%" },
      ],
    },
  },
  "lighting-lobby-01": {
    safe: {
      status: "safe",
      message: "Lighting controls available. Audit trail active.",
      rules: [
        { rule: "Emergency lighting protection", status: "passed", description: "Emergency circuit ready" },
        { rule: "Schedule compliance", status: "passed", description: "Within scheduled hours" },
        { rule: "Audit trail recording", status: "passed", description: "All changes logged" },
      ],
    },
  },
};

// Demo narratives for chat integration
export const demoNarratives = {
  "chiller-gateway-01": {
    safe: "The Gateway Chiller is operating normally. You can adjust the temperature setpoint between 5-10°C. Current setting is 7.0°C, which provides optimal cooling with good efficiency.",
    warning: "You're attempting to set the chiller temperature below the recommended minimum of 5°C. This could cause icing in the evaporator. The system will allow this with a warning and audit trail entry.",
    blocked: "You cannot stop the main chiller during business hours (10:00-16:00) as it provides critical cooling to the building. An emergency override would require authorization from the facilities manager.",
  },
  "lighting-lobby-01": {
    safe: "The lobby lighting can be adjusted between 0-100%. Current settings are 75% for main entrance and 100% for reception. All changes are recorded in the audit trail for compliance.",
  },
};

// Quick control actions for demo
export const quickControls = [
  {
    label: "Increase Chiller Temp",
    deviceId: "chiller-gateway-01",
    point: "setpoint",
    value: 7.5,
    description: "Increase chiller setpoint by 0.5°C for energy savings",
  },
  {
    label: "Decrease Chiller Temp",
    deviceId: "chiller-gateway-01",
    point: "setpoint",
    value: 6.5,
    description: "Decrease chiller setpoint by 0.5°C for better cooling",
  },
  {
    label: "Turn On AHU Fan",
    deviceId: "ahu-level3-01",
    point: "fan_status",
    value: true,
    description: "Turn on Level 3 AHU fan",
  },
  {
    label: "Increase Lobby Lighting",
    deviceId: "lighting-lobby-01",
    point: "circuit1_level",
    value: 100,
    description: "Set lobby lighting to 100%",
  },
  {
    label: "Decrease Lobby Lighting",
    deviceId: "lighting-lobby-01",
    point: "circuit1_level",
    value: 50,
    description: "Set lobby lighting to 50% for energy savings",
  },
];
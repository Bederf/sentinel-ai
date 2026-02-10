/**
 * Demo Controls Data - SENTINEL demo scenarios and device configurations
 *
 * Features:
 * - Predefined demo scenarios for control panel demonstrations
 * - Device configurations for demo devices
 * - Safety status scenarios
 * - Demo narratives and success/failure stories
 */

import type { Device } from '@/lib/api';

// Demo device configurations
export const demoDevices: Device[] = [
  {
    id: "chiller-gateway-01",
    name: "Gateway Chiller",
    device_type: "hvac",
    protocol: "mock",
    location: "Basement Plant Room",
    site_id: "sandton",
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
    site_id: "sandton",
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
  // Sandton Zone FCUs - for desk comfort control
  {
    id: "FCU-L12-03",
    name: "Level 12 North FCU",
    device_type: "hvac",
    protocol: "mock",
    location: "Level 12 North Open Plan",
    site_id: "sandton",
    description: "Fan coil unit serving Level 12 North zone (50 desks). Controls temperature for desks 201-225.",
    manufacturer: "Trane",
    model: "WCVF-08",
    points: {
      room_temp: {
        name: "room_temp",
        point_type: "analog_input",
        description: "Room temperature",
        unit: "°C",
        min_value: 16.0,
        max_value: 32.0,
        default_value: 22.5,
        writable: false,
      },
      room_temp_setpoint: {
        name: "room_temp_setpoint",
        point_type: "analog_value",
        description: "Room temperature setpoint",
        unit: "°C",
        min_value: 18.0,
        max_value: 26.0,
        default_value: 22.0,
        writable: true,
      },
      fan_speed: {
        name: "fan_speed",
        point_type: "multistate_value",
        description: "Fan speed setting",
        unit: "",
        default_value: 2,
        writable: true,
        metadata: {
          states: { "0": "off", "1": "low", "2": "medium", "3": "high", "4": "auto" },
        },
      },
      valve_position: {
        name: "valve_position",
        point_type: "analog_value",
        description: "Chilled water valve position",
        unit: "%",
        min_value: 0,
        max_value: 100,
        default_value: 65,
        writable: true,
      },
    },
    metadata: {
      zone_id: "Zone-L12-N",
      zone_name: "Level 12 North",
      desks_served: "201-225",
      building_id: "sandton",
    },
  },
  {
    id: "FCU-L11-01",
    name: "Level 11 North FCU",
    device_type: "hvac",
    protocol: "mock",
    location: "Level 11 North Open Plan",
    site_id: "sandton",
    description: "Fan coil unit serving Level 11 North zone. Currently reading 21.5°C (slightly cool).",
    manufacturer: "Trane",
    model: "WCVF-08",
    points: {
      room_temp: {
        name: "room_temp",
        point_type: "analog_input",
        description: "Room temperature",
        unit: "°C",
        min_value: 16.0,
        max_value: 32.0,
        default_value: 21.5,
        writable: false,
      },
      room_temp_setpoint: {
        name: "room_temp_setpoint",
        point_type: "analog_value",
        description: "Room temperature setpoint",
        unit: "°C",
        min_value: 18.0,
        max_value: 26.0,
        default_value: 22.0,
        writable: true,
      },
      fan_speed: {
        name: "fan_speed",
        point_type: "multistate_value",
        description: "Fan speed setting",
        unit: "",
        default_value: 3,
        writable: true,
        metadata: {
          states: { "0": "off", "1": "low", "2": "medium", "3": "high", "4": "auto" },
        },
      },
      valve_position: {
        name: "valve_position",
        point_type: "analog_value",
        description: "Chilled water valve position",
        unit: "%",
        min_value: 0,
        max_value: 100,
        default_value: 70,
        writable: true,
      },
      reheat_valve: {
        name: "reheat_valve",
        point_type: "analog_value",
        description: "Reheat valve position (for heating)",
        unit: "%",
        min_value: 0,
        max_value: 100,
        default_value: 0,
        writable: true,
      },
    },
    metadata: {
      zone_id: "Zone-L11-N",
      zone_name: "Level 11 North",
      building_id: "sandton",
    },
  },
  {
    id: "AHU-L12-01",
    name: "Level 12 AHU",
    device_type: "hvac",
    protocol: "mock",
    location: "Level 12 Plant Room",
    site_id: "sandton",
    description: "Air handling unit serving all Level 12 zones. Controls supply air temperature.",
    manufacturer: "Carrier",
    model: "39ER-50",
    points: {
      supply_air_temp: {
        name: "supply_air_temp",
        point_type: "analog_input",
        description: "Supply air temperature",
        unit: "°C",
        min_value: 10.0,
        max_value: 25.0,
        default_value: 14.0,
        writable: false,
      },
      supply_air_temp_setpoint: {
        name: "supply_air_temp_setpoint",
        point_type: "analog_value",
        description: "Supply air temperature setpoint",
        unit: "°C",
        min_value: 12.0,
        max_value: 18.0,
        default_value: 14.0,
        writable: true,
      },
      fan_speed: {
        name: "fan_speed",
        point_type: "analog_value",
        description: "Fan speed",
        unit: "%",
        min_value: 0,
        max_value: 100,
        default_value: 75,
        writable: true,
      },
      outside_air_damper: {
        name: "outside_air_damper",
        point_type: "analog_value",
        description: "Outside air damper position",
        unit: "%",
        min_value: 10,
        max_value: 100,
        default_value: 25,
        writable: true,
      },
    },
    metadata: {
      serves: "All Level 12 zones",
      building_id: "sandton",
      critical: true,
    },
  },
  {
    id: "lighting-lobby-01",
    name: "Lobby Lighting Panel",
    device_type: "lighting",
    protocol: "mock",
    location: "Ground Floor Lobby",
    site_id: "sandton",
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

// Demo scenarios for Level 2 Manual Control
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
  level2Flow: string; // New field to describe Level 2 control flow
}

export const demoScenarios: DemoScenario[] = [
  {
    id: "scenario-1",
    name: "Operator adjusts HVAC setpoint",
    description: "Happy path: Adjust temperature within safe range → confirmation → success → audit entry",
    deviceId: "chiller-gateway-01",
    safetyStatus: "safe",
    safetyMessage: "All safety rules passed. Temperature adjustment within safe operating range (5-10°C).",
    initialActions: [
      {
        point: "setpoint",
        value: 7.5,
        description: "Increase chiller setpoint from 7.0°C to 7.5°C",
      },
    ],
    expectedOutcome: "Chiller setpoint successfully adjusted. System remains within safe operating parameters.",
    narrative: "As FM operator, you need to slightly increase chiller temperature to reduce energy consumption while maintaining comfort. This demonstrates the standard Level 2 control flow.",
    level2Flow: "1. Adjust slider → 2. Confirmation modal shows details → 3. Click Confirm → 4. See pending spinner → 5. Success feedback (green) → 6. Recent Actions updates",
  },
  {
    id: "scenario-2",
    name: "Operator overrides with safety acknowledgment",
    description: "Safety warning: Attempt value outside range → warning shown → operator acknowledges → logged",
    deviceId: "chiller-gateway-01",
    safetyStatus: "warning",
    safetyMessage: "Warning: Temperature setpoint (4.5°C) is below recommended minimum (5.0°C). Risk of evaporator icing.",
    initialActions: [
      {
        point: "setpoint",
        value: 4.5,
        description: "Set chiller below minimum safe temperature for emergency pre-cooling",
      },
    ],
    expectedOutcome: "Control action allowed with warning acknowledgment. Safety override recorded in audit trail.",
    narrative: "During load shedding preparation, you need to pre-cool the building below normal limits. The safety system warns you but allows override with full audit trail recording.",
    level2Flow: "1. Adjust to 4.5°C → 2. Modal shows WARNING badge → 3. Acknowledge warning → 4. Execute → 5. Audit logs override reason",
  },
  {
    id: "scenario-3",
    name: "System blocks unsafe operation",
    description: "Safety block: Attempt dangerous value → blocked → logged as rejected",
    deviceId: "chiller-gateway-01",
    safetyStatus: "blocked",
    safetyMessage: "BLOCKED: Cannot stop critical chiller during peak cooling hours (10:00-16:00). Building occupancy: 450 people.",
    initialActions: [
      {
        point: "chiller_status",
        value: 0,
        description: "Attempt to stop critical chiller during business hours",
      },
    ],
    expectedOutcome: "Control action blocked by safety system. Attempted action logged for compliance. Emergency override requires Level 3 authorization.",
    narrative: "Attempting to stop the main chiller during business hours would cause building comfort issues affecting 450 occupants. Safety system blocks this action and logs the attempt.",
    level2Flow: "1. Attempt to stop → 2. Modal shows BLOCKED badge → 3. Confirm button disabled → 4. Rejection logged in audit trail",
  },
  {
    id: "scenario-4",
    name: "Operator overrides lighting schedule",
    description: "Audit trail: Override lighting for special event → confirmation → success → audit entry",
    deviceId: "lighting-lobby-01",
    safetyStatus: "safe",
    safetyMessage: "Lighting override permitted. All changes will be recorded in compliance audit trail.",
    initialActions: [
      {
        point: "circuit1_level",
        value: 100,
        description: "Set lobby lighting to 100% for executive dinner",
      },
      {
        point: "circuit2_level",
        value: 100,
        description: "Set reception lighting to 100%",
      },
    ],
    expectedOutcome: "Lighting successfully overridden. Audit trail records: operator, timestamp, values, reason.",
    narrative: "The CTO is hosting an executive dinner in the lobby after hours. Every lighting change is recorded for energy compliance and billing allocation.",
    level2Flow: "1. Set 100% → 2. Confirmation modal → 3. Confirm → 4. Success → 5. Audit shows: 'circuit1_level: 75% → 100%'",
  },
  {
    id: "scenario-5",
    name: "Operator improves air quality",
    description: "Standard control: Increase ventilation → confirmation → success → audit entry",
    deviceId: "ahu-level3-01",
    safetyStatus: "safe",
    safetyMessage: "AHU adjustment permitted. Note: Filter pressure at 250 Pa (above 200 Pa warning threshold).",
    initialActions: [
      {
        point: "damper_position",
        value: 50,
        description: "Increase outside air damper to 50% for better ventilation",
      },
    ],
    expectedOutcome: "AHU ventilation increased. Improved indoor air quality for occupied executive offices. Filter maintenance recommended.",
    narrative: "The CTO has requested better ventilation in executive offices. The system shows a filter warning during the control - operators can see equipment health alongside controls.",
    level2Flow: "1. Adjust damper → 2. Modal shows details + filter warning → 3. Confirm → 4. Success → 5. Consider scheduling filter replacement",
  },
];

// Demo safety status configurations
export const demoSafetyStatuses: Record<string, any> = {
  "FCU-L12-03": {
    safe: {
      status: "safe",
      message: "FCU operating normally. Zone temperature within comfort range.",
      rules: [
        { rule: "Temperature range (18-26°C)", status: "passed", description: "Current: 22.5°C" },
        { rule: "Zone occupancy check", status: "passed", description: "Zone occupied" },
        { rule: "Setpoint limits", status: "passed", description: "Within safe range" },
      ],
    },
  },
  "FCU-L11-01": {
    safe: {
      status: "safe",
      message: "FCU operating normally but zone slightly cool (21.5°C vs 22°C setpoint).",
      rules: [
        { rule: "Temperature range (18-26°C)", status: "passed", description: "Current: 21.5°C" },
        { rule: "Zone occupancy check", status: "passed", description: "Zone occupied" },
        { rule: "Setpoint limits", status: "passed", description: "Within safe range" },
      ],
    },
    warning: {
      status: "warning",
      message: "Warning: Multiple cold complaints from this zone. Consider reducing cooling.",
      rules: [
        { rule: "Temperature comfort", status: "warning", description: "0.5°C below setpoint" },
        { rule: "Complaint threshold", status: "warning", description: "2+ complaints in 1hr" },
        { rule: "Setpoint limits", status: "passed", description: "Within safe range" },
      ],
    },
  },
  "AHU-L12-01": {
    safe: {
      status: "safe",
      message: "AHU operating normally. Changes affect all Level 12 zones.",
      rules: [
        { rule: "Supply air temp (12-18°C)", status: "passed", description: "Current: 14°C" },
        { rule: "Fan operation", status: "passed", description: "Running at 75%" },
        { rule: "Filter status", status: "passed", description: "Filter OK" },
      ],
    },
    warning: {
      status: "warning",
      message: "Warning: Changing AHU settings affects multiple zones (L12 North & South).",
      rules: [
        { rule: "Multi-zone impact", status: "warning", description: "Affects 100+ desks" },
        { rule: "Supply air temp", status: "passed", description: "Within range" },
      ],
    },
  },
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

// Demo narratives for chat integration - Level 2 Manual Control
export const demoNarratives = {
  "FCU-L12-03": {
    safe: "Level 12 North FCU is running normally at 22.5°C. This zone serves desks 201-225. You can adjust the setpoint, fan speed, or valve position to address comfort complaints.",
  },
  "FCU-L11-01": {
    safe: "Level 11 North FCU is reading 21.5°C (slightly below setpoint of 22°C). For 'too cold' complaints, you can: raise setpoint, reduce fan speed, close cooling valve, or open reheat valve.",
    warning: "Zone temperature is 0.5°C below setpoint. Multiple cold complaints received from this zone.",
  },
  "AHU-L12-01": {
    safe: "Level 12 AHU is operating normally with 14°C supply air. Adjusting this affects ALL zones on Level 12.",
    warning: "Changing AHU supply temperature affects multiple zones. Consider adjusting individual FCUs first.",
  },
  "chiller-gateway-01": {
    safe: "The Gateway Chiller is operating normally at 22°C setpoint. You can adjust the temperature between 5-10°C. All control actions require confirmation and are logged to the audit trail.",
    warning: "You're attempting to set the chiller temperature outside the recommended range (5-10°C). This triggers a safety warning. You can acknowledge the warning and proceed - the override will be logged with your operator ID.",
    blocked: "You cannot stop the main chiller during business hours (10:00-16:00) as it provides critical cooling to 450 building occupants. The attempted action has been logged. Emergency override requires Level 3 authorization.",
  },
  "lighting-lobby-01": {
    safe: "The lobby lighting can be adjusted between 0-100%. Current settings are 75% for main entrance and 100% for reception. All changes are recorded in the compliance audit trail with operator ID and timestamp.",
  },
  "ahu-level3-01": {
    safe: "The Level 3 AHU is running with filter pressure at 250 Pa (above 200 Pa warning threshold). You can control the damper position and fan status. Filter maintenance is recommended.",
  },
  "vav-office-01": {
    safe: "The Office VAV is currently at 26°C (above comfort range of 22-24°C). Temperature adjustment will help restore comfort. All changes go through confirmation workflow.",
  },
};

// Quick control actions for Level 2 demo
export const quickControls = [
  {
    label: "Fix Cold Desk (L11)",
    deviceId: "FCU-L11-01",
    point: "room_temp_setpoint",
    value: 23,
    description: "Raise L11 North setpoint from 22°C to 23°C for cold complaint",
  },
  {
    label: "Reduce Cooling (L11)",
    deviceId: "FCU-L11-01",
    point: "valve_position",
    value: 40,
    description: "Reduce CHW valve from 70% to 40% to warm up zone",
  },
  {
    label: "Add Reheat (L11)",
    deviceId: "FCU-L11-01",
    point: "reheat_valve",
    value: 30,
    description: "Open reheat valve 30% to add warmth for cold complaint",
  },
  {
    label: "Fix Hot Desk (L12)",
    deviceId: "FCU-L12-03",
    point: "room_temp_setpoint",
    value: 21,
    description: "Lower L12 North setpoint from 22°C to 21°C for hot complaint",
  },
  {
    label: "Adjust Chiller Setpoint",
    deviceId: "chiller-gateway-01",
    point: "setpoint",
    value: 24,
    description: "Adjust chiller setpoint from 22°C to 24°C (safe range)",
  },
  {
    label: "Fix Hot Office",
    deviceId: "001-vav-001",
    point: "setpoint",
    value: 22,
    description: "Lower VAV setpoint from 26°C to 22°C to restore comfort",
  },
  {
    label: "Increase Ventilation",
    deviceId: "ahu-level3-01",
    point: "damper_position",
    value: 50,
    description: "Increase outside air damper to 50% (note filter warning)",
  },
  {
    label: "Boost Lobby Lighting",
    deviceId: "lighting-lobby-01",
    point: "circuit1_level",
    value: 100,
    description: "Set lobby lighting to 100% for executive dinner",
  },
  {
    label: "Energy Save Mode",
    deviceId: "lighting-lobby-01",
    point: "circuit1_level",
    value: 50,
    description: "Reduce lobby lighting to 50% for energy savings",
  },
];
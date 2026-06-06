/**
 * CockpitModuleScope — canonical taxonomy for module-scoped cockpit views.
 *
 * Single source of truth for which voices, equipment, issues, telemetry, and
 * controls belong to each cockpit module. No module-specific filtering logic
 * should exist outside this file.
 */

import type { CockpitModuleId } from './types'

export interface CockpitModuleScope {
  /** Unique module identifier — matches CockpitModuleId */
  id: CockpitModuleId

  /** Human-readable label for tab UI */
  label: string

  /** Narrative voices that belong to this module */
  acceptedVoices: string[]

  /** Subsystem values on issues that belong to this module */
  subsystemAliases: string[]

  /** Equipment types that belong to this module */
  equipmentTypes: string[]

  /** Calm-state headline when no active issues exist */
  stableHeadline: string

  /** Calm-state detail paragraph */
  stableSummary: string

  /** Telemetry keys relevant to this module */
  relevantTelemetry: string[]

  /** Control actions relevant to this module */
  allowedControls: string[]
}

// ─── Overview — building-wide, all-inclusive ───────────────────────────────

const OVERVIEW_SCOPE: CockpitModuleScope = {
  id: 'overview',
  label: 'Overview',
  acceptedVoices: [],          // empty = all voices accepted
  subsystemAliases: [],        // empty = all subsystems accepted
  equipmentTypes: [],          // empty = all equipment accepted
  stableHeadline: 'Building is stable',
  stableSummary: 'All systems are within normal operating parameters.',
  relevantTelemetry: ['totalKw', 'hvacKw', 'lightingKw', 'powerKw'],
  allowedControls: [],
}

// ─── HVAC ─────────────────────────────────────────────────────────────────

const HVAC_SCOPE: CockpitModuleScope = {
  id: 'hvac',
  label: 'HVAC',
  acceptedVoices: ['comfort_stress', 'occupant_friction', 'asset_stress'],
  subsystemAliases: ['hvac', 'ahu', 'fcu', 'vav', 'chiller', 'boiler', 'hvac_control'],
  equipmentTypes: ['ahu', 'chiller', 'fcu', 'vav', 'boiler', 'cooling_tower', 'hvac_sensor', 'thermostat', 'duct_pressure_sensor'],
  stableHeadline: 'HVAC systems stable',
  stableSummary: 'All HVAC zones are within setpoint. No temperature, pressure, or air quality anomalies detected.',
  relevantTelemetry: ['hvacKw', 'dischargeTemp', 'ductPressure', 'zoneTemp', 'co2Ppm'],
  allowedControls: ['set_cooling_setpoint', 'set_heating_setpoint', 'set_fan_speed', 'hvac_emergency_stop'],
}

// ─── Energy ───────────────────────────────────────────────────────────────

const ENERGY_SCOPE: CockpitModuleScope = {
  id: 'energy',
  label: 'Energy',
  acceptedVoices: ['energy_pressure'],
  subsystemAliases: ['energy', 'power', 'solar', 'bess', 'metering', 'energy_control'],
  equipmentTypes: ['meter', 'solar_panel', 'inverter', 'bess', 'generator', 'power_meter', 'energy_meter', 'submeter'],
  stableHeadline: 'Energy systems stable',
  stableSummary: 'Power consumption within expected range. Solar generation and battery levels nominal.',
  relevantTelemetry: ['totalKw', 'solarKw', 'bessSoc', 'gridImportKw', 'powerFactor'],
  allowedControls: ['set_bess_target_soc', 'set_load_shed_priority', 'generator_start'],
}

// ─── Lighting ─────────────────────────────────────────────────────────────

const LIGHTING_SCOPE: CockpitModuleScope = {
  id: 'lighting',
  label: 'Lighting',
  acceptedVoices: [],
  subsystemAliases: ['lighting', 'dali', 'luminaire', 'lighting_control'],
  equipmentTypes: ['luminaire', 'dali_controller', 'light_sensor', 'occupancy_sensor'],
  stableHeadline: 'Lighting systems stable',
  stableSummary: 'All lighting zones operating normally. No DALI faults or occupancy mismatches detected.',
  relevantTelemetry: ['lightingKw', 'luminaireStatus', 'daliHealth'],
  allowedControls: ['set_dim_level', 'set_scene', 'lighting_emergency', 'schedule_override'],
}

// ─── Water ────────────────────────────────────────────────────────────────

const WATER_SCOPE: CockpitModuleScope = {
  id: 'water',
  label: 'Water',
  acceptedVoices: [],
  subsystemAliases: ['water', 'plumbing', 'irrigation', 'water_control'],
  equipmentTypes: [
    'water_meter',
    'water_pump',
    'water_tank',
    'valve',
    'leak_sensor',
    'pressure_sensor',
    'flow_meter',
    'water_treatment',
  ],
  stableHeadline: 'Water systems stable',
  stableSummary: 'Water pressure, flow, and tank levels within normal range. No leaks detected.',
  relevantTelemetry: ['waterConsumptionGpm', 'waterPressurePsi', 'tankLevelPct', 'flowGpm', 'leakDetected'],
  allowedControls: ['set_valve_position', 'pump_start_stop', 'irrigation_schedule'],
}

// ─── Fire ─────────────────────────────────────────────────────────────────

const FIRE_SCOPE: CockpitModuleScope = {
  id: 'fire',
  label: 'Fire',
  acceptedVoices: [],
  subsystemAliases: ['fire', 'sprinkler', 'smoke', 'fire_control', 'fire_safety'],
  equipmentTypes: ['fire_panel', 'smoke_detector', 'sprinkler', 'fire_pump', 'heat_detector', 'manual_call_point', 'fire_damper'],
  stableHeadline: 'Fire systems stable',
  stableSummary: 'No fire alarms, sprinkler flows, or panel faults detected.',
  relevantTelemetry: ['panelStatus', 'zoneAlarmActive', 'sprinklerFlowGpm', 'pumpStatus', 'batteryVoltage'],
  allowedControls: ['reset_panel', 'silence_alarm', 'fire_emergency_stop'],
}

// ─── Security ─────────────────────────────────────────────────────────────

const SECURITY_SCOPE: CockpitModuleScope = {
  id: 'security',
  label: 'Security',
  acceptedVoices: [],
  subsystemAliases: ['security', 'access', 'cctv', 'intrusion', 'security_control'],
  equipmentTypes: [
    'access_reader',
    'door_contact',
    'camera',
    'motion_sensor',
    'alarm_panel',
    'intercom',
    'gate_controller',
  ],
  stableHeadline: 'Security systems stable',
  stableSummary: 'No intrusion events, access anomalies, or camera faults detected.',
  relevantTelemetry: ['doorStatus', 'cameraOnline', 'alarmZoneState', 'motionEventCount'],
  allowedControls: ['unlock_door', 'lock_door', 'arm_zone', 'disarm_zone', 'suppress_alarm'],
}

// ─── Solar & BESS ─────────────────────────────────────────────────────────

const SOLAR_BESS_SCOPE: CockpitModuleScope = {
  id: 'solar_bess',
  label: 'Solar & BESS',
  acceptedVoices: ['energy_pressure'],
  subsystemAliases: ['solar', 'bess', 'battery', 'solar_control'],
  equipmentTypes: ['solar_panel', 'inverter', 'bess', 'meter', 'solar_charger'],
  stableHeadline: 'Solar & BESS systems stable',
  stableSummary: 'Solar generation within expected range. Battery charge/discharge cycling normally.',
  relevantTelemetry: ['solarKw', 'bessSoc', 'bessChargeKw', 'bessDischargeKw', 'gridImportKw', 'gridExportKw'],
  allowedControls: ['set_bess_target_soc', 'set_charge_rate', 'set_discharge_rate', 'solar_curtail'],
}

// ─── Occupancy ────────────────────────────────────────────────────────────

const OCCUPANCY_SCOPE: CockpitModuleScope = {
  id: 'occupancy',
  label: 'Occupancy',
  acceptedVoices: [],
  subsystemAliases: ['occupancy', 'space', 'desk_booking', 'tenant'],
  equipmentTypes: ['occupancy_sensor', 'people_counter', 'desk_sensor'],
  stableHeadline: 'Occupancy normal',
  stableSummary: 'Zone utilisation within expected ranges. No capacity anomalies detected.',
  relevantTelemetry: ['occupancyPct', 'peopleCount', 'deskUtilisation', 'zoneCapacity'],
  allowedControls: [],
}

// ─── Registry — single lookup table ────────────────────────────────────────

const MODULE_SCOPES: Record<CockpitModuleId, CockpitModuleScope> = {
  overview: OVERVIEW_SCOPE,
  hvac: HVAC_SCOPE,
  energy: ENERGY_SCOPE,
  lighting: LIGHTING_SCOPE,
  water: WATER_SCOPE,
  fire: FIRE_SCOPE,
  security: SECURITY_SCOPE,
  solar_bess: SOLAR_BESS_SCOPE,
  occupancy: OCCUPANCY_SCOPE,
  // controls is a meta-tab, not a scoped module
  controls: {
    id: 'controls',
    label: 'Controls',
    acceptedVoices: [],
    subsystemAliases: [],
    equipmentTypes: [],
    stableHeadline: 'Controls',
    stableSummary: 'Device control panel.',
    relevantTelemetry: [],
    allowedControls: [],
  },
}

/** Look up a module scope by ID. Falls back to overview scope for unknown IDs. */
export function getModuleScope(moduleId: CockpitModuleId | string | null | undefined): CockpitModuleScope {
  if (moduleId && moduleId in MODULE_SCOPES) {
    return MODULE_SCOPES[moduleId as CockpitModuleId]
  }
  return OVERVIEW_SCOPE
}

/** Check whether a given voice belongs to the specified module scope. */
export function voiceBelongsToModule(voice: string, moduleId: CockpitModuleId | null | undefined): boolean {
  if (!moduleId || moduleId === 'overview') return true
  const scope = MODULE_SCOPES[moduleId]
  if (!scope) return true
  return scope.acceptedVoices.length === 0 || scope.acceptedVoices.includes(voice)
}

/** Check whether a given subsystem belongs to the specified module scope. */
export function subsystemBelongsToModule(subsystem: string | null, moduleId: CockpitModuleId | null | undefined): boolean {
  if (!moduleId || moduleId === 'overview') return true
  if (!subsystem) return false
  const scope = MODULE_SCOPES[moduleId]
  if (!scope) return true
  return scope.subsystemAliases.length === 0 || scope.subsystemAliases.includes(subsystem)
}

/** Check whether a given equipment type belongs to the specified module scope. */
export function equipmentTypeBelongsToModule(
  equipmentType: string,
  moduleId: CockpitModuleId | null | undefined,
): boolean {
  if (!moduleId || moduleId === 'overview') return true
  const scope = MODULE_SCOPES[moduleId]
  if (!scope) return true
  const normalizedType = equipmentType.toLowerCase()
  return scope.equipmentTypes.length === 0 || scope.equipmentTypes.includes(normalizedType)
}

export { MODULE_SCOPES }

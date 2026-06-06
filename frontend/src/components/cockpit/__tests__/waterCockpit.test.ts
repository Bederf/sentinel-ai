import { expect, it } from 'vitest'
import { mapCockpitState, type BuildingStatePayload, type EquipmentWarningInput } from '../mapCockpitState'
import type { WaterTelemetry } from '../types'

const summary = {
  siteId: 'site-002',
  siteName: 'Sandton City Office Tower',
  posture: 'compensating',
  activeAlerts: 2,
  predictionsCount: 1,
  equipmentCount: 83,
  dataFreshnessLabel: 'Updated 12s ago',
}

function buildCalmPayload(): BuildingStatePayload {
  return {
    site_id: 'site-002',
    building_posture: 'calm',
    primary_narrative: null,
    secondary_tensions: [],
    operator_guidance: {
      headline: 'No action needed.',
      mode: 'none',
    },
  }
}

function buildActivePayload(): BuildingStatePayload {
  return {
    site_id: 'site-002',
    building_posture: 'compensating',
    primary_narrative: {
      voice: 'comfort_stress',
      message: 'Cooling drift is spreading upward from the basement plant.',
      location: {
        epicenter: 'B1',
        affected: ['L0', 'L1'],
        propagation: 'upward',
      },
      time_to_breach_min: 18,
      urgency: 'prepare',
      action: 'Prepare standby cooling.',
    },
    secondary_tensions: [{
      voice: 'energy_pressure',
      message: 'Load is rising as the building compensates.',
    }],
    operator_guidance: {
      headline: 'Prepare for intervention.',
      mode: 'prepare',
    },
  }
}

function buildWaterUnavailableTelemetry(): WaterTelemetry {
  return { flowLpm: null, pressureBar: null, totalM3: null, dailyM3: null, leakDetected: null, lastUpdated: null, sourceHealthy: false }
}

function buildWaterStableTelemetry(): WaterTelemetry {
  return { flowLpm: 15.2, pressureBar: 3.5, totalM3: 2450.7, dailyM3: 12.3, leakDetected: false, lastUpdated: '2026-06-06T10:00:00Z', sourceHealthy: true }
}

function buildWaterWarningTelemetry(): WaterTelemetry {
  return { flowLpm: 8.1, pressureBar: 0.8, totalM3: 2500.0, dailyM3: 14.0, leakDetected: false, lastUpdated: '2026-06-06T10:00:00Z', sourceHealthy: true }
}

function buildWaterCriticalTelemetry(): WaterTelemetry {
  return { flowLpm: 45.0, pressureBar: 0.3, totalM3: 2600.0, dailyM3: 18.5, leakDetected: true, lastUpdated: '2026-06-06T10:00:00Z', sourceHealthy: true }
}

function buildWaterEquipmentWarning(): EquipmentWarningInput[] {
  return [{
    id: 'eq-001',
    equipment_id: 'S002-WTR-PMP-001',
    code: 'WTR-PMP-001',
    equipment_type: 'water_pump',
    floor_id: 'B1',
    health_score: 45,
    health_state: 'critical',
    fault_type: 'low_pressure',
    zone_id: 'Zone-B1-1',
  }, {
    id: 'eq-002',
    equipment_id: 'S002-MTR-W-001',
    code: 'MTR-W-001',
    equipment_type: 'water_meter',
    floor_id: 'L0',
    health_score: 70,
    health_state: 'degraded',
    zone_id: 'Zone-L0-2',
  }]
}

// ─── Water unavailable state ───────────────────────────────────────────

it('renders water unavailable state when waterTelemetry is null', () => {
  const state = mapCockpitState(summary, buildCalmPayload(), undefined, undefined, undefined, 'water', [], undefined, null)

  expect(state.site.renderState).toBe('waiting')
  expect(state.visualTwin.headline).toBe('Water telemetry unavailable')
  expect(state.activeCondition.summary).toBe('Water telemetry unavailable')
  expect(state.primaryMetric.detail).toBe('Water telemetry unavailable. No flow, pressure, or consumption data received.')
  expect(state.visualTwin.motionProfile).toBe('waiting')
})

it('renders water unavailable state when sourceHealthy is false', () => {
  const state = mapCockpitState(summary, buildCalmPayload(), undefined, undefined, undefined, 'water', [], undefined, buildWaterUnavailableTelemetry())

  expect(state.site.renderState).toBe('waiting')
  expect(state.visualTwin.headline).toBe('Water telemetry unavailable')
  expect(state.activeCondition.summary).toBe('Water telemetry unavailable')
})

// ─── Water stable state ────────────────────────────────────────────────

it('renders water stable state with calm tone', () => {
  const state = mapCockpitState(summary, buildCalmPayload(), undefined, undefined, undefined, 'water', [], undefined, buildWaterStableTelemetry())

  expect(state.visualTwin.headline).toBe('Water systems stable')
  expect(state.primaryMetric.tone).toBe('normal')
  expect(state.visualTwin.motionProfile).toBe('calm')
  expect(state.sitePulse.tone).toBe('normal')
  expect(state.site.posture).toBe('Calm')
  expect(state.activeCondition.summary).toBe('Water systems stable. No leaks, pressure drops, or consumption anomalies detected.')
  expect(state.evidence.refs).toContain('module:water')
  expect(state.waterTelemetry).toBeDefined()
})

// ─── Water warning state ───────────────────────────────────────────────

it('renders water warning state with warning tone', () => {
  const state = mapCockpitState(summary, buildCalmPayload(), undefined, undefined, undefined, 'water', buildWaterEquipmentWarning(), undefined, buildWaterWarningTelemetry())

  expect(state.primaryMetric.tone).toBe('warning')
  expect(state.visualTwin.motionProfile).toBe('watch')
  expect(state.site.posture).toBe('Drifting — safe bounds')
  expect(state.site.posture).toContain('Drifting')
})

// ─── Water critical state (leak detected) ──────────────────────────────

it('renders water critical state with leak detected', () => {
  const state = mapCockpitState(summary, buildCalmPayload(), undefined, undefined, undefined, 'water', buildWaterEquipmentWarning(), undefined, buildWaterCriticalTelemetry())

  expect(state.primaryMetric.tone).toBe('critical')
  expect(state.visualTwin.motionProfile).toBe('alert')
  expect(state.site.posture).toBe('Critical')
  expect(state.visualTwin.headline).toBe('Water leak detected')
  expect(state.sitePulse.tone).toBe('critical')
  expect(state.evidence.refs).toContain('water:leak-active')
  expect(state.evidence.relatedModuleIds).toEqual(['water'])
  expect(state.emergingRisks.length).toBeGreaterThan(0)
  expect(state.emergingRisks[0].title).toBe('WTR-PMP-001')
})

// ─── HVAC-leakage prevention ───────────────────────────────────────────

it('does not leak HVAC data into water view', () => {
  const state = mapCockpitState(summary, buildActivePayload(), undefined, undefined, undefined, 'water', [], undefined, buildWaterStableTelemetry())

  expect(state.visualTwin.headline).toBe('Water systems stable')
  expect(state.visualTwin.energyCentre.online).toBe(false)
  expect(state.visualTwin.energyCentre.hvacKw).toBe(0)
  // HVAC narrative must not bleed through
  expect(state.activeCondition.summary).not.toContain('cooling')
  expect(state.activeCondition.summary).not.toContain('HVAC')
  // Water evidence refs should not include HVAC zone refs
  expect(state.evidence.refs).not.toContain('zone:')
})

it('does not use HVAC-derived values for water twin motion', () => {
  const stateStable = mapCockpitState(summary, buildActivePayload(), undefined, undefined, undefined, 'water', [], undefined, buildWaterStableTelemetry())
  const stateCritical = mapCockpitState(summary, buildActivePayload(), undefined, undefined, undefined, 'water', buildWaterEquipmentWarning(), undefined, buildWaterCriticalTelemetry())

  expect(stateStable.visualTwin.breathingIntensity).toBe(0.18)
  expect(stateStable.visualTwin.flowSpeed).toBe(1.05)
  expect(stateStable.visualTwin.consumptionIntensity).toBe(0.18)
  // Critical state uses water-only dynamics
  expect(stateCritical.visualTwin.breathingIntensity).toBe(0.18)
})

// ─── Water zone signals ────────────────────────────────────────────────

it('generates zone signals from water equipment warnings', () => {
  const criticalWarnings: EquipmentWarningInput[] = [{
    id: 'eq-003',
    equipment_id: 'S002-WTR-PMP-002',
    code: 'WTR-PMP-002',
    equipment_type: 'water_pump',
    floor_id: 'B1',
    health_score: 25,
    health_state: 'critical',
    fault_type: 'low_pressure',
    zone_id: 'Zone-B1-1',
  }]
  const state = mapCockpitState(summary, buildCalmPayload(), undefined, undefined, undefined, 'water', criticalWarnings, undefined, buildWaterCriticalTelemetry())

  expect(state.visualTwin.zoneSignals.length).toBeGreaterThan(0)
  const pumpSignal = state.visualTwin.zoneSignals.find((s) => s.zoneId === 'Zone-B1-1')
  expect(pumpSignal).toBeDefined()
  expect(pumpSignal?.floorId).toBe('B1')
  expect(pumpSignal?.level).toBe('critical')
})

// ─── Email cluster filtering for water ─────────────────────────────────

it('filters email clusters to water-related complaints only', () => {
  const payloadWithClusters: BuildingStatePayload = {
    ...buildCalmPayload(),
    email_clusters: [
      { cluster_id: 'c1', zone_id: 'Zone-L1-1', zone_name: 'Zone L1-1', floor: 'L1', email_count: 5, complaint_type: 'water leak in bathroom', severity: 'high', summary: 'Leak in bathroom' },
      { cluster_id: 'c2', zone_id: 'Zone-L2-1', zone_name: 'Zone L2-1', floor: 'L2', email_count: 3, complaint_type: 'plumbing issue', severity: 'medium', summary: 'Plumbing issue' },
      { cluster_id: 'c3', zone_id: 'Zone-L3-1', zone_name: 'Zone L3-1', floor: 'L3', email_count: 4, complaint_type: 'HVAC temperature', severity: 'medium', summary: 'Too hot' },
      { cluster_id: 'c4', zone_id: 'Zone-L0-1', zone_name: 'Zone L0-1', floor: 'L0', email_count: 6, complaint_type: 'flooded corridor', severity: 'critical', summary: 'Flooding' },
    ],
  }

  const state = mapCockpitState(summary, payloadWithClusters, undefined, undefined, undefined, 'water', [], undefined, buildWaterCriticalTelemetry())

  expect(state.emailClusters.length).toBe(3)
  const complaintTypes = state.emailClusters.map((c) => c.complaintType)
  expect(complaintTypes).toContain('water leak in bathroom')
  expect(complaintTypes).toContain('plumbing issue')
  expect(complaintTypes).toContain('flooded corridor')
  expect(complaintTypes).not.toContain('HVAC temperature')
})

// ─── Switching module clears selected zone ─────────────────────────────

it('switching from water to HVAC clears water zone signals', () => {
  const waterState = mapCockpitState(summary, buildCalmPayload(), undefined, undefined, undefined, 'water', buildWaterEquipmentWarning(), undefined, buildWaterCriticalTelemetry())
  const hvacState = mapCockpitState(summary, buildActivePayload(), undefined, undefined, undefined, 'hvac', [], undefined, undefined)

  expect(waterState.visualTwin.zoneSignals.length).toBeGreaterThan(0)
  expect(hvacState.visualTwin.zoneSignals[0]?.zoneId).toBe('B1')
  // HVAC zone signals come from narrative, not from water equipment
  const hvacZoneIds = hvacState.visualTwin.zoneSignals.map((s) => s.zoneId)
  expect(hvacZoneIds).toContain('B1')
  // HVAC should NOT contain water equipment-based zone signals
  expect(hvacState.equipmentWarnings.length).toBe(0)
})

// ─── Cross-system evidence with relatedModuleIds ───────────────────────

it('includes evidence with relatedModuleIds containing water', () => {
  const state = mapCockpitState(summary, buildCalmPayload(), undefined, undefined, undefined, 'water', [], undefined, buildWaterCriticalTelemetry())

  expect(state.evidence.relatedModuleIds).toBeDefined()
  expect(state.evidence.relatedModuleIds).toContain('water')
  expect(state.evidence.refs).toContain('module:water')
})

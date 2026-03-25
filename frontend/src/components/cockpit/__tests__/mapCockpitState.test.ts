import { expect, it } from 'vitest'
import { mapCockpitState, type CockpitDecisionPayload } from '../mapCockpitState'
import type { CockpitThresholdPolicy } from '../thresholdPolicy'

const summary = {
  siteId: 'site-002',
  siteName: 'Sandton City Office Tower',
  posture: 'comfort_priority',
  activeAlerts: 2,
  predictionsCount: 1,
  equipmentCount: 83,
  dataFreshnessLabel: 'Updated 12s ago',
}

function buildActivePayload(): CockpitDecisionPayload {
  return {
    building_id: 'site-002',
    alert_text: 'Cooling resilience is degrading across the executive zone.',
    reasoning_summary: 'Thermal runway and occupancy load are converging on the boardroom cluster.',
    active_posture: 'comfort_priority',
    time_to_discomfort: 12,
    time_confidence: 0.82,
    estimated_impact: 'Boardroom comfort at risk within the next meeting window.',
    recommended_action: 'Bring standby cooling capacity online.',
    urgency_score: 0.86,
    urgency_components: { comfort: 0.55, asset_risk: 0.21, cost: 0.1 },
    affected_zone_ids: ['Zone-L2-Boardroom'],
    primary_asset_id: 'S002-CHILLER-B1-001',
    building_metadata: { deployment_mode: 'supervised' },
  }
}

it('maps active intelligence payloads into a cockpit state', () => {
  const state = mapCockpitState(summary, buildActivePayload())

  expect(state.primaryMetric.label).toBe('Time to Comfort Breach')
  expect(state.primaryMetric.value).toBe('12 min')
  expect(state.site.mode).toBe('supervised')
  expect(state.decision.impact).toBe('Boardroom comfort at risk within the next meeting window.')
  expect(state.decision.confidence).toBe('82%')
  expect(state.decision.operatorPrompt).toBe('[HOLD TO APPROVE]')
  expect(state.evidence.refs).toContain('asset:S002-CHILLER-B1-001')
  expect(state.severity.riskBand).toBe('critical')
  expect(state.visualTwin.focusFloorId).toBe('L2')
  expect(state.visualTwin.motionProfile).toBe('alert')
  expect(state.visualTwin.zoneSignals[0]?.zoneId).toBe('Zone-L2-Boardroom')
  expect(state.visualTwin.zoneSignals[0]?.meshId).toBe('mesh:zone-l2-boardroom')
  expect(state.visualTwin.floors.find((floor) => floor.id === 'L2')?.level).toBe('critical')
})

it('uses threshold policy instead of hardcoded urgency bands', () => {
  const customPolicy: CockpitThresholdPolicy = {
    health: { healthy: 80, warning: 60, critical: 0 },
    risk: { medium: 40, high: 70, critical: 90 },
    source: 'settings',
  }

  const state = mapCockpitState(summary, buildActivePayload(), customPolicy)

  expect(state.severity.riskBand).toBe('high')
  expect(state.primaryMetric.tone).toBe('elevated')
  expect(state.severity.thresholdReason).toContain('high threshold of 70')
  expect(state.visualTwin.floors.find((floor) => floor.id === 'L2')?.level).toBe('approaching')
})

it('produces a stable quiet-state cockpit when there is no active payload', () => {
  const state = mapCockpitState(summary, null)

  expect(state.primaryMetric.value).toBe('Stable')
  expect(state.primaryMetric.label).toBe('Time to Comfort Breach')
  expect(state.activeCondition.summary).toContain('No comfort risk for the next 30 minutes')
  expect(state.emergingRisks).toHaveLength(2)
  expect(state.visualTwin.motionProfile).toBe('calm')
  expect(state.visualTwin.zoneSignals).toHaveLength(0)
  expect(state.visualTwin.floors.every((floor) => floor.level === 'stable')).toBe(true)
})

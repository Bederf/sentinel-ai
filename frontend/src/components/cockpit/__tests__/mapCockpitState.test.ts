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
    risk: {
      score: 0.86,
      band: 'critical',
      reason: 'Thermal drift is above the configured critical threshold.',
      policy_source: 'global.settings',
    },
    health: {
      score: 0.83,
      state: 'stable',
      trend: 'declining',
    },
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
  expect(state.severity.thresholdReason).toBe('Thermal drift is above the configured critical threshold.')
  expect(state.severity.policySource).toBe('global.settings')
  expect(state.severity.healthScore).toBe(83)
  expect(state.severity.healthState).toBe('stable')
  expect(state.severity.healthTrend).toBe('declining')
  expect(state.visualTwin.focusFloorId).toBe('L2')
  expect(state.visualTwin.motionProfile).toBe('alert')
  expect(state.visualTwin.zoneSignals[0]?.zoneId).toBe('Zone-L2-Boardroom')
  expect(state.visualTwin.zoneSignals[0]?.meshId).toBe('mesh:zone-l2-boardroom')
  expect(state.visualTwin.floors.find((floor) => floor.id === 'L2')?.level).toBe('critical')
})

it('uses backend-resolved risk semantics before frontend threshold fallback', () => {
  const payload = buildActivePayload()
  payload.risk = {
    score: 0.86,
    band: 'medium',
    reason: 'Backend policy resolved this as medium risk for the current rollout.',
    policy_source: 'site-002.office.default',
  }

  const state = mapCockpitState(summary, payload)

  expect(state.severity.riskBand).toBe('medium')
  expect(state.primaryMetric.tone).toBe('warning')
  expect(state.severity.thresholdReason).toBe('Backend policy resolved this as medium risk for the current rollout.')
  expect(state.severity.policySource).toBe('site-002.office.default')
})

it('uses threshold policy instead of hardcoded urgency bands when backend risk is absent', () => {
  const customPolicy: CockpitThresholdPolicy = {
    health: { healthy: 80, warning: 60, critical: 0 },
    risk: { medium: 40, high: 70, critical: 90 },
    source: 'settings',
  }

  const payload = buildActivePayload()
  payload.risk = null
  payload.health = null

  const state = mapCockpitState(summary, payload, customPolicy)

  expect(state.severity.riskBand).toBe('high')
  expect(state.primaryMetric.tone).toBe('elevated')
  expect(state.severity.thresholdReason).toContain('high threshold of 70')
  expect(state.severity.policySource).toBe('settings')
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
  expect(state.severity.healthScore).not.toBeNull()
})

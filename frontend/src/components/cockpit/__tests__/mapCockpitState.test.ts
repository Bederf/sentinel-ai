import { expect, it } from 'vitest'
import { mapCockpitState, type BuildingStatePayload } from '../mapCockpitState'

const summary = {
  siteId: 'site-002',
  siteName: 'Sandton City Office Tower',
  posture: 'compensating',
  activeAlerts: 2,
  predictionsCount: 1,
  equipmentCount: 83,
  dataFreshnessLabel: 'Updated 12s ago',
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
    secondary_tensions: [
      {
        voice: 'energy_pressure',
        message: 'Load is rising as the building compensates.',
      },
    ],
    operator_guidance: {
      headline: 'Prepare for intervention.',
      mode: 'prepare',
    },
  }
}

it('maps building-state payloads into a cockpit state', () => {
  const state = mapCockpitState(summary, buildActivePayload())

  expect(state.site.posture).toBe('Compensating')
  expect(state.site.mode).toBe('prepare')
  expect(state.primaryMetric.label).toBe('Time to Constraint')
  expect(state.primaryMetric.value).toBe('18 min')
  expect(state.primaryMetric.detail).toBe('Prepare for intervention.')
  expect(state.activeCondition.summary).toBe('Cooling drift is spreading upward from the basement plant.')
  expect(state.decision.impact).toBe('B1 · L0 → L1 · Upward')
  expect(state.decision.summary).toBe('Prepare standby cooling.')
  expect(state.decision.tradeoff).toContain('Energy Pressure')
  expect(state.visualTwin.focusFloorId).toBe('B1')
  expect(state.visualTwin.zoneSignals[0]?.zoneId).toBe('B1')
  expect(state.visualTwin.motionProfile).toBe('watch')
  expect(state.severity.riskBand).toBe('medium')
  expect(state.severity.timeToConstraintBreachMin).toBe(18)
})

it('renders an explicit calm payload without synthetic urgency', () => {
  const state = mapCockpitState(summary, {
    site_id: 'site-002',
    building_posture: 'calm',
    primary_narrative: null,
    secondary_tensions: [],
    operator_guidance: {
      headline: 'No action needed.',
      mode: 'none',
    },
  })

  expect(state.primaryMetric.value).toBe('Stable')
  expect(state.primaryMetric.detail).toBe('No action needed.')
  expect(state.activeCondition.summary).toBe('Building is calm.')
  expect(state.decision.summary).toBe('No action needed.')
  expect(state.visualTwin.motionProfile).toBe('calm')
  expect(state.visualTwin.zoneSignals).toHaveLength(0)
  expect(state.severity.affectedScope).toBeNull()
})

it('renders an unavailable state instead of inventing a calm story when payload is missing', () => {
  const state = mapCockpitState(summary, null)

  expect(state.site.renderState).toBe('waiting')
  expect(state.site.mode).toBe('waiting')
  expect(state.site.posture).toBe('Waiting')
  expect(state.primaryMetric.value).toBe('Waiting')
  expect(state.primaryMetric.label).toBe('Live State')
  expect(state.activeCondition.summary).toBe('Awaiting building signal')
  expect(state.decision.summary).toBe('Watch for live building state')
  expect(state.decision.tradeoff).toBe('No operator action required until live state arrives.')
  expect(state.visualTwin.motionProfile).toBe('waiting')
  expect(state.emergingRisks).toEqual([])
  expect(state.evidence.refs).toEqual([])
  expect(state.severity.riskScore).toBeNull()
  expect(state.severity.policySource).toBeNull()
  expect(state.severity.healthScore).toBeNull()
})

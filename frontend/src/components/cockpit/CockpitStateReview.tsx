import quietFixture from '@/lib/fixtures/site-002-quiet.json'
import crisisFixture from '@/lib/fixtures/site-002-crisis.json'
import { CockpitNervousSystemTwin } from './CockpitNervousSystemTwin'
import { CockpitView } from './CockpitView'
import { mapCockpitState, type CockpitDecisionPayload } from './mapCockpitState'

const summary = {
  siteId: 'site-002',
  siteName: 'Sandton City Office Tower',
  posture: 'comfort_priority',
  activeAlerts: 2,
  predictionsCount: 1,
  equipmentCount: 83,
  dataFreshnessLabel: 'Updated 12s ago',
}

const warningFixture: CockpitDecisionPayload = {
  building_id: 'site-002',
  alert_text: 'Boardroom A is drifting toward discomfort.',
  reasoning_summary: 'Cooling load is rising faster than the current air-side response. Intervene before the next meeting starts.',
  active_posture: 'comfort_priority',
  time_to_discomfort: 18,
  time_confidence: 0.64,
  estimated_impact: 'Boardroom comfort will tighten during the next occupied window.',
  recommended_action: 'Bring standby cooling online before the room loses comfort.',
  urgency_score: 0.58,
  urgency_components: { comfort: 0.34, asset_risk: 0.14, cost: 0.1 },
  affected_zone_ids: ['Zone-L2-Boardroom-A'],
  primary_asset_id: 'S002-AHU-L2-001',
  building_metadata: {
    deployment_mode: 'supervised',
    floor_labels: {
      R: 'Roof',
      L2: 'Level 2',
      L1: 'Level 1',
      L0: 'Ground',
      G: 'Ground Parking',
      B1: 'Basement',
    },
    floor_stack_order: ['R', 'L2', 'L1', 'L0', 'G', 'B1'],
  },
}

const reviewStates = [
  {
    id: 'stable',
    label: 'Stable',
    state: mapCockpitState(summary, quietFixture as CockpitDecisionPayload),
  },
  {
    id: 'warning',
    label: 'Warning',
    state: mapCockpitState(summary, warningFixture),
  },
  {
    id: 'critical',
    label: 'Critical',
    state: mapCockpitState(summary, crisisFixture as CockpitDecisionPayload),
  },
]

export function CockpitStateReview() {
  return (
    <main className="min-h-screen bg-slate-950 px-4 py-6 md:px-6">
      <div className="mx-auto max-w-[1800px]">
        <header className="mb-6">
          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Cockpit Review</div>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-white">Stable, Warning, Critical</h1>
          <p className="mt-3 max-w-3xl text-sm text-slate-400 md:text-base">
            Validate visual separation, message clarity, and eye movement side by side before any polish pass.
          </p>
        </header>

        <div className="grid gap-6 2xl:grid-cols-3">
          {reviewStates.map((review) => (
            <section key={review.id}>
              <div className="mb-3 flex items-center justify-between">
                <div className="text-xs uppercase tracking-[0.24em] text-slate-500">{review.label}</div>
                <div className="rounded-full border border-slate-800 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                  {review.state.site.mode}
                </div>
              </div>

              <CockpitView
                state={review.state}
                renderMode="embedded"
                spatialCanvas={<CockpitNervousSystemTwin state={review.state} />}
              />
            </section>
          ))}
        </div>
      </div>
    </main>
  )
}

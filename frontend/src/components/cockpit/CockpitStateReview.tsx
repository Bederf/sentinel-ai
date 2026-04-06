import { CockpitView } from './CockpitView'
import { mapCockpitState, type BuildingStatePayload } from './mapCockpitState'

const summary = {
  siteId: 'site-002',
  siteName: 'Sandton City Office Tower',
  posture: 'comfort_priority',
  activeAlerts: 2,
  predictionsCount: 1,
  equipmentCount: 83,
  dataFreshnessLabel: 'Updated 12s ago',
}

const calmFixture: BuildingStatePayload = {
  site_id: 'site-002',
  building_posture: 'calm',
  primary_narrative: null,
  secondary_tensions: [],
  operator_guidance: {
    headline: 'No action needed.',
    mode: 'none',
  },
}

const warningFixture: BuildingStatePayload = {
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

const criticalFixture: BuildingStatePayload = {
  site_id: 'site-002',
  building_posture: 'critical',
  primary_narrative: {
    voice: 'comfort_stress',
    message: 'Cooling capacity is collapsing across the occupied tower spine.',
    location: {
      epicenter: 'B1',
      affected: ['L0', 'L1', 'L2'],
      propagation: 'upward',
    },
    time_to_breach_min: 7,
    urgency: 'act_now',
    action: 'Act now to restore standby cooling.',
  },
  secondary_tensions: [
    {
      voice: 'operational_stability',
      message: 'Plant transition margin is nearly exhausted.',
    },
  ],
  operator_guidance: {
    headline: 'Immediate operator attention required.',
    mode: 'act_now',
  },
}

const reviewStates = [
  {
    id: 'stable',
    label: 'Stable',
    state: mapCockpitState(summary, calmFixture),
  },
  {
    id: 'warning',
    label: 'Warning',
    state: mapCockpitState(summary, warningFixture),
  },
  {
    id: 'critical',
    label: 'Critical',
    state: mapCockpitState(summary, criticalFixture),
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

              <CockpitView state={review.state} renderMode="embedded" />
            </section>
          ))}
        </div>
      </div>
    </main>
  )
}

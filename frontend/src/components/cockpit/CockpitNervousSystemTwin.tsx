import { useLayoutEffect, useRef } from 'react'
import gsap from 'gsap'
import type { CockpitState } from './types'
import { motionReduced } from './motionPreference'
import { CockpitBuildingThree } from './CockpitBuildingThree'
import { cockpitToneKey } from './cockpitTwinTheme'
import { AutoExecutionsPanel } from './AutoExecutionsPanel'

interface CockpitNervousSystemTwinProps {
  state: CockpitState
  onZoneSelect?: (zone: import('./types').CockpitTwinZoneSignal) => void
}

function moduleFlags(state: CockpitState) {
  const refs = state.evidence.refs || []
  const riskText = state.emergingRisks.map((r) => `${r.title} ${r.detail}`.toLowerCase()).join(' ')
  const has = (token: string) => refs.some((ref) => ref.toLowerCase().includes(token))

  return {
    lighting: has('module:lighting') || riskText.includes('lighting'),
    water: has('module:water') || riskText.includes('water'),
    fire: has('module:fire') || riskText.includes('fire'),
    security: has('module:security') || riskText.includes('security'),
    occupancy: has('module:occupancy') || riskText.includes('occupant') || riskText.includes('space'),
  }
}

export function CockpitNervousSystemTwin({ state, onZoneSelect: _onZoneSelect }: CockpitNervousSystemTwinProps) {
  const panelRef = useRef<HTMLDivElement | null>(null)
  const waiting = state.site.renderState === 'waiting'
  const tone = cockpitToneKey(state)
  const energyLayer = state.visualTwin.energyCentre
  const modules = moduleFlags(state)

  useLayoutEffect(() => {
    if (!panelRef.current) return
    if (motionReduced()) return
    const ctx = gsap.context(() => {
      gsap.fromTo(panelRef.current, { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.65, ease: 'power3.out' })
    }, panelRef)
    return () => ctx.revert()
  }, [])

  return (
    <div ref={panelRef} className="relative rounded-[24px] border border-white/8 bg-[radial-gradient(circle_at_50%_40%,rgba(14,165,233,0.14),transparent_35%),linear-gradient(180deg,rgba(2,6,23,0.7),rgba(2,6,23,0.95))] p-4 md:p-6">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500">Digital Twin</div>
          <div className="mt-2 text-lg font-medium text-slate-100">Spatial intelligence view</div>
          <div className="mt-1 text-sm text-slate-400">
            {waiting
              ? 'Quiet readiness while waiting for live building state'
              : state.site.id === 'site-002'
                ? 'Host tower in grey; Sentinel scope is L0–L3 + Roof only — non-scoped floors have no system tint.'
                : 'Host tower in grey; Sentinel indicators apply only on instrumented floors. Drag to orbit.'}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[10px] uppercase tracking-[0.22em] text-slate-300">
            {waiting ? 'Waiting' : state.site.posture}
          </div>
          <div
            className="rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.18em]"
            style={{
              borderColor: tone === 'critical' ? 'rgba(248,113,113,0.5)' : tone === 'warning' ? 'rgba(251,191,36,0.45)' : 'rgba(34,211,238,0.35)',
              background: tone === 'critical' ? 'rgba(248,113,113,0.14)' : tone === 'warning' ? 'rgba(251,191,36,0.14)' : 'rgba(34,211,238,0.12)',
              color: tone === 'critical' ? 'rgba(254,202,202,0.95)' : tone === 'warning' ? 'rgba(253,230,138,0.95)' : 'rgba(165,243,252,0.95)',
            }}
          >
            Energy Centre {energyLayer.online ? `${Math.round(energyLayer.totalKw)} kW` : 'Offline'}
          </div>
        </div>
      </div>

      <div className="relative overflow-hidden rounded-[24px] border border-white/8 bg-slate-950/60 p-1 md:p-2">
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(34,211,238,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,0.04)_1px,transparent_1px)] [background-size:36px_36px] opacity-40" />
        <div className="pointer-events-none absolute inset-x-12 bottom-10 h-40 rounded-full bg-cyan-500/10 blur-3xl" />

        <CockpitBuildingThree state={state} />

        {/* Module strip: same signals as before, now decoupled from the 2D SVG overlay.
            When a systemFilter is active, highlight that system and dim others. */}
        <div className="pointer-events-none absolute right-3 top-14 flex flex-col gap-1.5 text-[9px] uppercase tracking-[0.12em]">
          {modules.lighting || state.systemFilter === 'lighting' ? (
            <span className={state.systemFilter === 'lighting' ? 'text-amber-200 font-semibold' : state.systemFilter ? 'text-slate-600' : 'text-amber-200/90'}>Lighting trace</span>
          ) : null}
          {modules.water || state.systemFilter === 'water' ? (
            <span className={state.systemFilter === 'water' ? 'text-sky-300 font-semibold' : state.systemFilter ? 'text-slate-600' : 'text-sky-300/90'}>Water spine</span>
          ) : null}
          {modules.fire || state.systemFilter === 'fire' ? (
            <span className={state.systemFilter === 'fire' ? 'text-rose-300 font-semibold' : state.systemFilter ? 'text-slate-600' : 'text-rose-300/90'}>Fire watch</span>
          ) : null}
          {modules.security || state.systemFilter === 'security' ? (
            <span className={state.systemFilter === 'security' ? 'text-cyan-200 font-semibold' : state.systemFilter ? 'text-slate-600' : 'text-cyan-200/90'}>Security mesh</span>
          ) : null}
          {modules.occupancy || state.systemFilter === 'lighting' ? (
            <span className={state.systemFilter === 'lighting' ? 'text-violet-200 font-semibold' : state.systemFilter ? 'text-slate-600' : 'text-violet-200/90'}>Occupancy</span>
          ) : null}
          {state.systemFilter === 'hvac' ? (
            <span className="text-cyan-300 font-semibold">HVAC trace</span>
          ) : null}
          {state.systemFilter === 'energy' ? (
            <span className="text-orange-300 font-semibold">Energy pulse</span>
          ) : null}
          {state.systemFilter === 'solar_bess' ? (
            <span className="text-yellow-300 font-semibold">Solar & BESS</span>
          ) : null}
        </div>

        {/* Auto-execution rollback panel — only shown when site has advanced past shadow */}
        {state.site.onboardingPhase !== 'shadow' && (
          <div className="pointer-events-auto mt-4">
            <AutoExecutionsPanel state={state} />
          </div>
        )}
      </div>
    </div>
  )
}

import type { CockpitState } from './types'

interface CockpitLiteTwinProps {
  state: CockpitState
}

function toneClasses(level: string) {
  if (level === 'critical') {
    return {
      border: 'rgba(239, 68, 68, 0.5)',
      glow: 'rgba(248, 113, 113, 0.25)',
      text: 'text-red-300',
      badge: 'bg-red-500/15 text-red-200',
    }
  }
  if (level === 'approaching') {
    return {
      border: 'rgba(249, 115, 22, 0.45)',
      glow: 'rgba(251, 146, 60, 0.2)',
      text: 'text-orange-300',
      badge: 'bg-orange-500/15 text-orange-200',
    }
  }
  if (level === 'drift') {
    return {
      border: 'rgba(251, 191, 36, 0.4)',
      glow: 'rgba(253, 230, 138, 0.16)',
      text: 'text-amber-300',
      badge: 'bg-amber-500/15 text-amber-200',
    }
  }
  return {
    border: 'rgba(56, 189, 248, 0.35)',
    glow: 'rgba(125, 211, 252, 0.12)',
    text: 'text-sky-300',
    badge: 'bg-sky-500/15 text-sky-200',
  }
}

export function CockpitLiteTwin({ state }: CockpitLiteTwinProps) {
  const focusFloorId = state.visualTwin.focusFloorId
  const isWaiting = state.site.renderState === 'waiting'

  return (
    <div
      className="relative overflow-hidden rounded-2xl border border-slate-800/80 bg-[radial-gradient(circle_at_top,rgba(14,116,144,0.18),rgba(2,6,23,0.96)_52%)]"
      role="img"
      aria-label={`Lightweight intelligence twin for ${state.site.name}`}
    >
      <div className="flex h-[420px] w-full flex-col gap-3 overflow-hidden p-4 md:h-[520px] md:p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">
              {isWaiting ? 'Building Presence' : 'Lightweight Twin'}
            </div>
            <div className="mt-1 text-sm text-slate-300">
              {isWaiting ? 'Quietly waiting for live building state.' : 'Spatial building state view.'}
            </div>
          </div>
          <div className="rounded-full border border-slate-800/80 bg-slate-950/80 px-3 py-1 text-[11px] uppercase tracking-[0.22em] text-slate-400">
            {state.site.posture}
          </div>
        </div>

        <div className="grid min-h-0 flex-1 gap-3">
          {state.visualTwin.floors.map((floor) => {
            const palette = toneClasses(floor.level)
            const isFocus = floor.id === focusFloorId
            const zoneSignals = state.visualTwin.zoneSignals.filter((signal) => signal.floorId === floor.id)

            return (
              <section
                key={floor.meshId}
                className="rounded-2xl border p-4 shadow-[inset_0_0_0_1px_rgba(15,23,42,0.25)]"
                style={{
                  borderColor: palette.border,
                  background: `linear-gradient(135deg, ${palette.glow}, rgba(2,6,23,0.88) 72%)`,
                  boxShadow: isFocus ? `0 0 0 1px ${palette.border}, 0 0 32px ${palette.glow}` : undefined,
                }}
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">{floor.label}</div>
                    <div className={`mt-1 text-sm font-semibold ${palette.text}`}>
                      {isWaiting
                        ? (isFocus ? 'Awaiting signal' : 'Quiet readiness')
                        : (isFocus ? state.activeCondition.summary : `${floor.level} spatial tension`)}
                    </div>
                  </div>
                  <div className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${palette.badge}`}>
                    {floor.level}
                  </div>
                </div>

                {zoneSignals.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {zoneSignals.map((signal) => {
                      const signalPalette = toneClasses(signal.level)
                      return (
                        <div
                          key={signal.meshId}
                          className="min-w-[10rem] rounded-xl border px-3 py-2"
                          style={{
                            borderColor: signalPalette.border,
                            background: signal.isPrimary ? signalPalette.glow : 'rgba(15,23,42,0.45)',
                          }}
                        >
                          <div className={`text-xs font-semibold ${signalPalette.text}`}>{signal.label}</div>
                          <div className="mt-1 text-[11px] text-slate-400">{signal.actionLabel}</div>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <div className="mt-3 text-xs text-slate-500">
                    {isWaiting ? 'No live signals on this floor yet.' : 'No active spatial signals on this floor.'}
                  </div>
                )}
              </section>
            )
          })}
        </div>
      </div>
    </div>
  )
}

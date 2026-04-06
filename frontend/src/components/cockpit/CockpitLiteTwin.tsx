import type { CockpitState } from './types'

interface CockpitLiteTwinProps {
  state: CockpitState
}

/** CSS animations injected for equipment fault indicators */
const FLASH_STYLES = `
  @keyframes flash-critical {
    0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    50% { box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.55), 0 0 12px rgba(239, 68, 68, 0.3); }
  }
  @keyframes flash-approaching {
    0%, 100% { box-shadow: 0 0 0 0 rgba(249, 115, 22, 0); }
    50% { box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.45), 0 0 10px rgba(249, 115, 22, 0.25); }
  }
  @keyframes pulse-critical-badge {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  @keyframes pulse-approaching-badge {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.65; }
  }
`

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

function intakeBadgeClasses(severity: string) {
  if (severity === 'critical') {
    return { bg: 'rgba(239,68,68,0.25)', color: '#fca5a5', border: 'rgba(239,68,68,0.5)' }
  }
  if (severity === 'high') {
    return { bg: 'rgba(249,115,22,0.2)', color: '#fdba74', border: 'rgba(249,115,22,0.4)' }
  }
  return { bg: 'rgba(251,191,36,0.15)', color: '#fde047', border: 'rgba(251,191,36,0.35)' }
}

const COMPLAINT_LABELS: Record<string, string> = {
  hvac: 'HVAC',
  thermal: 'thermal',
  fault: 'fault',
  occupant: 'occupant',
  energy: 'energy',
  security: 'security',
  water: 'water',
  general: 'issue',
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
      <style>{FLASH_STYLES}</style>
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
            const intakeSignals = zoneSignals.filter((s) => s.intakeCluster)
            const worstSeverity = intakeSignals.reduce<string>((worst, s) => {
              const sev = s.intakeCluster?.severity ?? 'low'
              const rank: Record<string, number> = { critical: 3, high: 2, medium: 1, low: 0 }
              return (rank[sev] ?? 0) > (rank[worst] ?? 0) ? sev : worst
            }, 'low')

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
                  <div className="flex flex-col gap-1">
                    <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">{floor.label}</div>
                    <div className={`mt-1 text-sm font-semibold ${palette.text}`}>
                      {isWaiting
                        ? (isFocus ? 'Awaiting signal' : 'Quiet readiness')
                        : (isFocus ? state.activeCondition.summary : `${floor.level} spatial tension`)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {/* Heatmap bar: shows if any zone on this floor has email clusters */}
                    {intakeSignals.length > 0 && (
                      <div
                        className="flex items-center gap-1 rounded px-2 py-1 text-[10px] font-semibold"
                        style={intakeBadgeClasses(worstSeverity)}
                        title={`${intakeSignals.length} zone${intakeSignals.length !== 1 ? 's' : ''} with occupant complaints`}
                      >
                        🔥 {intakeSignals.length} heat
                      </div>
                    )}
                    <div className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${palette.badge}`}>
                      {floor.level}
                    </div>
                  </div>
                </div>

                {zoneSignals.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {zoneSignals.map((signal) => {
                      const signalPalette = toneClasses(signal.level)
                      const cluster = signal.intakeCluster
                      const badge = cluster ? intakeBadgeClasses(cluster.severity) : null
                      const complaintLabel = cluster
                        ? COMPLAINT_LABELS[cluster.complaintType] ?? cluster.complaintType
                        : null

                      const animClass =
                        signal.level === 'critical'
                          ? 'flash-critical'
                          : signal.level === 'approaching'
                            ? 'flash-approaching'
                            : ''
                      return (
                        <div
                          key={signal.meshId}
                          className={`min-w-[10rem] rounded-xl border px-3 py-2 ${animClass}`}
                          style={{
                            borderColor: badge ? badge.border : signalPalette.border,
                            background: signal.isPrimary ? signalPalette.glow : 'rgba(15,23,42,0.45)',
                          }}
                        >
                          <div className={`text-xs font-semibold ${badge ? '' : signalPalette.text}`} style={badge ? { color: badge.color } : undefined}>
                            {signal.label}
                            {signal.level === 'critical' && (
                              <span className="ml-1.5 inline-block h-2 w-2 rounded-full bg-red-500" style={{ animation: 'pulse-critical-badge 0.8s ease-in-out infinite' }} />
                            )}
                            {signal.level === 'approaching' && (
                              <span className="ml-1.5 inline-block h-2 w-2 rounded-full bg-orange-400" style={{ animation: 'pulse-approaching-badge 1.2s ease-in-out infinite' }} />
                            )}
                          </div>
                          {badge && cluster ? (
                            <div
                              className="mt-1.5 rounded px-1.5 py-0.5 text-[10px] font-semibold"
                              style={{ background: badge.bg, color: badge.color }}
                              title={cluster.summary}
                            >
                              🔥 {cluster.emailCount}x {complaintLabel}
                            </div>
                          ) : (
                            <div className="mt-1 text-[11px] text-slate-400">{signal.actionLabel}</div>
                          )}
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

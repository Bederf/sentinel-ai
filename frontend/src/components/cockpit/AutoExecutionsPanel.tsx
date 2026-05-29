import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronUp, RefreshCw, Shield, Zap } from 'lucide-react'
import { authorizedFetch } from '../../lib/api'
import type { CockpitState } from './types'

interface Tier3Decision {
  id: string
  recommendation_id: string
  equipment_code: string
  point_name: string
  original_value: string | number | null
  target_value: string | number | null
  audit_level: 'routine' | 'critical' | null
  rolled_back: boolean
  created_at: string
}

interface AutoExecutionsPanelProps {
  state: CockpitState
}

function formatRelativeTime(isoString: string): string {
  const now = Date.now()
  const then = new Date(isoString).getTime()
  const diff = Math.floor((now - then) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function formatPointLabel(code: string, point: string | null): string {
  if (!code || !point) return '—'
  // code like S002-FCU-007 → show just the zone/point part
  const zone = code.replace(/^[^_]+_/, '')
  return `${zone} / ${point}`
}

function formatValue(v: string | number | null): string {
  if (v === null || v === undefined) return '—'
  return String(v)
}

async function rollbackRecommendation(
  recommendationId: string,
  onDone: (success: boolean) => void
) {
  try {
    const res = await authorizedFetch(
      `/api/approvals/recommendations/${recommendationId}/rollback`,
      { method: 'POST' }
    )
    onDone(res.ok)
  } catch {
    onDone(false)
  }
}

export function AutoExecutionsPanel({ state }: AutoExecutionsPanelProps) {
  const siteId = state.site.id
  const [open, setOpen] = useState(false)
  const [decisions, setDecisions] = useState<Tier3Decision[]>([])
  const [loading, setLoading] = useState(false)
  const [rollingBack, setRollingBack] = useState<string | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open || siteId === 'waiting') return
    let cancelled = false
    setLoading(true)

    authorizedFetch(`/api/parasite/decisions?site_id=${siteId}&tier=tier3&limit=5`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return
        setDecisions((data.decisions ?? []).slice(0, 5))
      })
      .catch(() => {
        if (cancelled) return
        setDecisions([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [open, siteId])

  return (
    <div
      ref={panelRef}
      className="overflow-hidden rounded-md border border-white/10 bg-[linear-gradient(180deg,rgba(2,6,23,0.85),rgba(2,6,23,0.95))]"
    >
      {/* Header */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-white/4 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Zap size={12} style={{ color: "var(--color-sentinel-amber)" }} />
          <span className="text-[10px] uppercase tracking-[0.22em] text-slate-400">
            Auto-Exécutions
          </span>
          {decisions.length > 0 && (
            <span className="rounded-full border px-1.5 py-0.5 text-[9px]" style={{ borderColor: 'rgba(251,191,36,0.3)', background: 'rgba(251,191,36,0.1)', color: 'var(--color-sentinel-amber)' }}>
              {decisions.length}
            </span>
          )}
        </div>
        {open ? (
          <ChevronUp size={12} className="text-slate-500" />
        ) : (
          <ChevronDown size={12} className="text-slate-500" />
        )}
      </button>

      {/* Body */}
      {open && (
        <div className="border-t border-white/8">
          {loading ? (
            <div className="flex items-center justify-center px-4 py-6 text-[10px] uppercase tracking-widest text-slate-500">
              Loading…
            </div>
          ) : decisions.length === 0 ? (
            <div className="px-4 py-5 text-center text-[10px] uppercase tracking-widest text-slate-600">
              No Tier 3 auto-exécutions yet
            </div>
          ) : (
            <ul className="divide-y divide-white/6">
              {decisions.map((d) => (
                <li key={d.id} className="flex items-start gap-3 px-4 py-3">
                  {/* Left: info */}
                  <div className="min-w-0 flex-1">
                    <div className="text-[11px] font-medium text-slate-200 truncate">
                      {formatPointLabel(d.equipment_code, d.point_name)}
                    </div>
                    <div className="mt-1 flex items-center gap-1.5 text-[10px] text-slate-500">
                      <span className="text-slate-400">
                        {formatValue(d.original_value)}
                      </span>
                      <span className="text-slate-600">→</span>
                      <span className="text-slate-300">
                        {formatValue(d.target_value)}
                      </span>
                    </div>
                    <div className="mt-1.5 flex items-center gap-2">
                      <span className="text-[9px] text-slate-600">
                        {formatRelativeTime(d.created_at)}
                      </span>
                      {d.audit_level === 'critical' ? (
                        <span className="flex items-center gap-0.5 rounded border border-rose-400/30 bg-rose-400/10 px-1 py-0.5 text-[9px] uppercase tracking-widest text-rose-300">
                          <Shield size={7} />
                          Critical
                        </span>
                      ) : (
                        <span className="rounded border border-slate-600/50 bg-slate-600/10 px-1 py-0.5 text-[9px] uppercase tracking-widest text-slate-400">
                          Routine
                        </span>
                      )}
                      {d.rolled_back && (
                        <span className="rounded border px-1 py-0.5 text-[9px] uppercase tracking-widest" style={{ borderColor: 'rgba(251,191,36,0.4)', background: 'rgba(251,191,36,0.1)', color: 'var(--color-sentinel-amber)' }}>
                          Rolled back
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Right: rollback */}
                  <div className="mt-0.5 shrink-0">
                    {d.rolled_back ? (
                      <span className="cursor-default rounded border border-slate-700 bg-slate-800/50 px-2 py-1 text-[9px] uppercase tracking-widest text-slate-600">
                        Auto-done
                      </span>
                    ) : (
                      <button
                        type="button"
                        disabled={rollingBack === d.recommendation_id}
                        onClick={() => {
                          const recId = d.recommendation_id
                          if (!recId) return
                          setRollingBack(recId)
                          rollbackRecommendation(recId, (ok) => {
                            setRollingBack(null)
                            if (ok) {
                              setDecisions((prev) =>
                                prev.map((x) =>
                                  x.id === d.id ? { ...x, rolled_back: true } : x
                                )
                              )
                            }
                          })
                        }}
                        className="flex items-center gap-1 rounded border px-2 py-1 text-[9px] uppercase tracking-widest transition-colors"
                        style={{ borderColor: 'rgba(251,191,36,0.4)', background: 'rgba(251,191,36,0.1)', color: 'var(--color-sentinel-amber)' }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(251,191,36,0.7)'; e.currentTarget.style.background = 'rgba(251,191,36,0.2)' }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(251,191,36,0.4)'; e.currentTarget.style.background = 'rgba(251,191,36,0.1)' }}
                      >
                        <RefreshCw size={8} className={rollingBack === d.recommendation_id ? 'animate-spin' : ''} />
                        Rollback
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

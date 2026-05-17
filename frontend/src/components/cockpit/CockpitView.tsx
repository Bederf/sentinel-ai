import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import gsap from 'gsap'
import {
  ArrowRight,
  Brain,
  Clock3,
  Gauge,
  Layers3,
  Maximize2,
  Minimize2,
  Orbit,
  Shield,
  Sparkles,
  TimerReset,
} from 'lucide-react'
import type { CockpitRenderMode, CockpitRiskItem, CockpitState, CockpitTwinZoneSignal, ModelReadiness } from './types'
import { SupervisedConfirmBar } from './useHoldToConfirm'
import { motionReduced } from './motionPreference'
import { CockpitNervousSystemTwin } from './CockpitNervousSystemTwin'

interface CockpitViewProps {
  state: CockpitState
  renderMode: CockpitRenderMode
  spatialCanvas?: ReactNode
  onApprove?: () => void
  selectedZone?: CockpitTwinZoneSignal | null
  onZoneClose?: () => void
  modelReadiness?: ModelReadiness | null
  onAdvancePhase?: () => void
  onZoneSelect?: (zone: CockpitTwinZoneSignal) => void
}

const FRAMER_EASE: [number, number, number, number] = [0.4, 0, 0.2, 1]

const FULLSCREEN_STORAGE_KEY = 'sentinelCockpitFullscreen'
const ZOOM_MIN = 0.8
const ZOOM_MAX = 1.4
const ZOOM_STEP = 0.08

interface TonePalette {
  tone: 'cyan' | 'amber' | 'red'
  dot: string
  glow: string
  text: string
  border: string
  soft: string
  chip: string
  fill: string
  line: string
}

interface QueueItem {
  severity: 'Critical' | 'Escalating' | 'Monitor'
  title: string
  cause: string
  impact: string
  eta: string
  confidence: string
}

function activeModuleLabels(state: CockpitState): string[] {
  const labels = new Set<string>()
  // When a system filter is active, prioritize that system label first
  const filter = state.systemFilter
  if (filter === 'hvac') labels.add('HVAC')
  if (filter === 'energy') labels.add('Energy')
  if (filter === 'lighting') labels.add('Lighting')
  if (filter === 'water') labels.add('Water')
  if (filter === 'fire') labels.add('Fire')
  if (filter === 'security') labels.add('Security')
  if (filter === 'solar_bess') labels.add('Solar & BESS')
  if (state.evidence.refs.some((ref) => ref.startsWith('zone:'))) labels.add('HVAC')
  if (state.evidence.refs.some((ref) => ref.startsWith('energy-centre:'))) labels.add('Energy Centre')
  for (const risk of state.emergingRisks) {
    const title = risk.title.toLowerCase()
    if (title.includes('asset')) labels.add('Asset')
    if (title.includes('occupant')) labels.add('Occupancy')
    if (title.includes('operational')) labels.add('Operations')
    if (title.includes('energy')) labels.add('Energy')
    if (title.includes('comfort')) labels.add('Comfort')
  }
  if (labels.size === 0) labels.add('Telemetry')
  return Array.from(labels).slice(0, 3)
}

function isWaitingState(state: CockpitState) {
  return state.site.renderState === 'waiting'
}

function tonePalette(state: CockpitState): TonePalette {
  if (state.primaryMetric.tone === 'critical') {
    return {
      tone: 'red',
      dot: 'bg-red-400',
      glow: 'shadow-[0_0_40px_rgba(248,113,113,0.35)]',
      text: 'text-red-300',
      border: 'border-red-400/30',
      soft: 'bg-red-400/10',
      chip: 'bg-red-400/10 text-red-200 border-red-400/30',
      fill: 'from-red-500/80 to-red-900/40',
      line: 'from-red-400/70 via-red-300/30 to-transparent',
    }
  }

  if (state.primaryMetric.tone === 'warning' || state.primaryMetric.tone === 'elevated') {
    return {
      tone: 'amber',
      dot: 'bg-amber-400',
      glow: 'shadow-[0_0_40px_rgba(251,191,36,0.28)]',
      text: 'text-amber-300',
      border: 'border-amber-400/30',
      soft: 'bg-amber-400/10',
      chip: 'bg-amber-400/10 text-amber-200 border-amber-400/30',
      fill: 'from-amber-500/75 to-amber-900/30',
      line: 'from-amber-300/70 via-amber-200/30 to-transparent',
    }
  }

  return {
    tone: 'cyan',
    dot: 'bg-cyan-400',
    glow: 'shadow-[0_0_40px_rgba(34,211,238,0.25)]',
    text: 'text-cyan-300',
    border: 'border-cyan-400/30',
    soft: 'bg-cyan-400/10',
    chip: 'bg-cyan-400/10 text-cyan-200 border-cyan-400/30',
    fill: 'from-cyan-500/70 to-cyan-900/30',
    line: 'from-cyan-300/70 via-cyan-200/30 to-transparent',
  }
}

function modeLabel(mode: CockpitState['site']['mode']) {
  if (mode === 'act_now') return 'Act Now'
  if (mode === 'intervene_soon') return 'Intervene Soon'
  if (mode === 'prepare') return 'Prepare'
  if (mode === 'watch') return 'Watch'
  if (mode === 'none') return 'Stable'
  return 'Waiting'
}

function phaseLabel(phase: CockpitState['site']['onboardingPhase']) {
  if (phase === 'shadow') return 'Shadow'
  if (phase === 'advisory') return 'Advisory'
  if (phase === 'supervised') return 'Supervised'
  return 'Auto'
}

function systemLabel(filter: string | null | undefined): string | null {
  if (!filter) return null
  const map: Record<string, string> = {
    hvac: 'HVAC',
    energy: 'Energy',
    lighting: 'Lighting',
    water: 'Water',
    fire: 'Fire',
    security: 'Security',
    solar_bess: 'Solar & BESS',
  }
  return map[filter] ?? null
}

function railTitle(state: CockpitState) {
  const sys = systemLabel(state.systemFilter)
  if (sys) return `${sys} Focus`
  return state.site.onboardingPhase === 'shadow' ? 'Observation' : 'Decision'
}

function evidenceLabel(state: CockpitState) {
  if (isWaitingState(state)) return 'Waiting'
  const moduleCount = activeModuleLabels(state).length
  if (state.evidence.strength === 'strong') return 'Strong evidence'
  if (state.evidence.strength === 'moderate') return `Moderate evidence · ${moduleCount} modules`
  return 'Limited evidence'
}

function heroHeadline(state: CockpitState) {
  if (isWaitingState(state)) return 'Awaiting building signal'
  const sys = systemLabel(state.systemFilter)
  const prefix = sys ? `${sys} · ` : ''
  if (state.primaryMetric.value === 'Stable') return `${prefix}All systems nominal`
  // Truncate long summaries at word boundary to prevent mobile clipping
  const summary = state.activeCondition.summary
  const maxLen = 40
  if (summary.length > maxLen) {
    // Find last space before maxLen
    const lastSpace = summary.lastIndexOf(' ', maxLen)
    // If no space found (single long word) or space is too early, hard truncate at maxLen
    if (lastSpace === -1 || lastSpace < 10) {
      return `${prefix}${summary.slice(0, maxLen - 1)}…`
    }
    return `${prefix}${summary.slice(0, lastSpace)}…`
  }
  return `${prefix}${summary}`
}

function heroSubheadline(state: CockpitState) {
  if (isWaitingState(state)) return `Waiting for ${state.site.name} to begin reporting live state.`
  if (state.site.onboardingPhase === 'shadow') {
    return `${state.site.name} is in shadow training mode. Cockpit is rendering pure live telemetry flow with no SENTINEL intervention.`
  }
  if (state.primaryMetric.value === 'Stable') return `${state.site.name} remains within operating margin. SENTINEL is observing for cross-system drift.`
  return state.activeCondition.rationale
}

function siteSummary(state: CockpitState) {
  if (isWaitingState(state)) return 'Waiting for live state'
  const modules = activeModuleLabels(state).join(' + ')
  const energyKw = state.visualTwin.energyCentre?.online ? `${Math.round(state.visualTwin.energyCentre.totalKw)}kw` : 'energy n/a'
  return `${state.sitePulse.activeConditionCount} active, ${state.sitePulse.emergingRiskCount} secondary, ${modules}, ${energyKw}, ${state.site.dataFreshnessLabel.toLowerCase()}`
}

function timeToImpact(state: CockpitState) {
  if (isWaitingState(state)) return 'Waiting'
  if (state.primaryMetric.value === 'Stable') return 'No immediate breach'
  return `${state.primaryMetric.value} · ${state.primaryMetric.label.toLowerCase()}`
}

function telemetrySnapshot(state: CockpitState) {
  const ec = state.visualTwin.energyCentre
  if (!ec?.online) return 'Telemetry baseline only'
  return `${Math.round(ec.hvacKw)} kW HVAC · ${Math.round(ec.totalKw)} kW site · ${Math.round(ec.powerShareRatio * 100)}% electrical`
}

function freshnessLabel(state: CockpitState) {
  if (state.site.onboardingPhase === 'shadow') return 'Telemetry freshness'
  if (state.site.onboardingPhase === 'advisory') return 'Guidance freshness'
  if (state.site.onboardingPhase === 'supervised') return 'Control freshness'
  return 'Automation freshness'
}

function queueSeverity(state: CockpitState, item: CockpitRiskItem, index: number): QueueItem['severity'] {
  if (state.primaryMetric.tone === 'critical' && index === 0) return 'Critical'
  if (state.primaryMetric.tone === 'warning' || state.primaryMetric.tone === 'elevated') return index === 0 ? 'Escalating' : 'Monitor'
  return 'Monitor'
}

function buildQueue(state: CockpitState): QueueItem[] {
  const modules = activeModuleLabels(state).join(' + ')
  if (isWaitingState(state)) {
    return [
      {
        severity: 'Monitor',
        title: 'No live building signal yet',
        cause: `SENTINEL is waiting for ${state.site.name} to begin reporting a resolved building state.`,
        impact: 'No operator action is required until live state arrives.',
        eta: 'Waiting',
        confidence: 'Waiting',
      },
    ]
  }

  if (state.emergingRisks.length === 0) {
    return [
      {
        severity: state.primaryMetric.tone === 'critical' ? 'Critical' : state.primaryMetric.tone === 'normal' ? 'Monitor' : 'Escalating',
        title: state.primaryMetric.value === 'Stable' ? 'No secondary tensions rising' : 'Dominant signal remains primary',
        cause: state.activeCondition.rationale,
        impact: state.primaryMetric.value === 'Stable'
          ? 'No additional operator review is needed.'
          : `${modules} remains the primary focus.`,
        eta: timeToImpact(state),
        confidence: evidenceLabel(state),
      },
    ]
  }

  return state.emergingRisks.slice(0, 3).map((item, index) => ({
    severity: queueSeverity(state, item, index),
    title: item.title,
    cause: item.detail,
    impact: index === 0
      ? state.decision.summary
      : state.primaryMetric.value === 'Stable'
        ? 'Monitored only.'
        : `${modules} pressure under ${state.site.posture.toLowerCase()} posture.`,
    eta: index === 0 ? timeToImpact(state) : 'Ongoing',
    confidence: evidenceLabel(state),
  }))
}

function buildForecast(state: CockpitState) {
  const modules = activeModuleLabels(state).join(' + ')
  if (isWaitingState(state)) {
    return [
      { label: 'Signal', value: 'No live building signal yet' },
      { label: 'Guidance', value: 'Watch for live building state' },
      { label: 'Action', value: 'No operator action required' },
    ]
  }

  return [
    { label: 'Twin scope', value: state.site.id === 'site-002' ? 'L0-L3 + Roof occupied (host shell neutral)' : 'Occupied levels only' },
    { label: 'Guidance', value: `${state.decision.summary} · ${telemetrySnapshot(state)}` },
    {
      label: 'Modules',
      value: state.emergingRisks[0]?.detail ?? (state.primaryMetric.value === 'Stable'
        ? `${modules} stable with no secondary tensions rising above background`
        : state.decision.tradeoff),
    },
  ]
}

function severityClass(severity: QueueItem['severity']) {
  if (severity === 'Critical') return 'text-red-300 border-red-400/30 bg-red-400/10'
  if (severity === 'Escalating') return 'text-amber-300 border-amber-400/30 bg-amber-400/10'
  return 'text-cyan-300 border-cyan-400/30 bg-cyan-400/10'
}

function ForecastPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/8 bg-black/20 px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{label}</div>
      <div className="mt-2 text-sm leading-6 text-slate-200">{value}</div>
    </div>
  )
}

function InsightCard({ item }: { item: QueueItem }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: FRAMER_EASE }}
      className="rounded-2xl border border-white/8 bg-white/[0.03] p-4 backdrop-blur-sm transition hover:bg-white/[0.05]"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className={`rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-[0.2em] ${severityClass(item.severity)}`}>
          {item.severity}
        </span>
        <span className="text-xs text-slate-400">{item.confidence}</span>
      </div>

      <h3 className="text-sm font-medium text-slate-100">{item.title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-300">{item.cause}</p>
      <p className="mt-2 text-sm leading-6 text-slate-400">{item.impact}</p>

      <div className="mt-4 flex items-center justify-between text-xs uppercase tracking-[0.18em] text-slate-500">
        <span>Time to impact</span>
        <span className="text-slate-300">{item.eta}</span>
      </div>
    </motion.div>
  )
}

function DetailRow({
  icon,
  label,
  value,
  accent = false,
}: {
  icon: ReactNode
  label: string
  value: ReactNode
  accent?: boolean
}) {
  return (
    <div className="border-t border-white/8 px-5 py-4 first:border-t-0">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-slate-500">
        {icon}
        <span>{label}</span>
      </div>
      <div className={`mt-3 text-sm leading-6 ${accent ? 'font-medium text-slate-100' : 'text-slate-300'}`}>{value}</div>
    </div>
  )
}

function RailAction({ state, onApprove }: { state: CockpitState; onApprove?: () => void }) {
  if (isWaitingState(state)) {
    return (
      <div className="border-t border-white/8 px-5 py-4 text-sm leading-6 text-slate-300">
        No operator action required until live state arrives.
      </div>
    )
  }

  // Shadow + Advisory phase: no hold-to-confirm action UI (read-only observation)
  if (state.site.onboardingPhase === 'shadow' || state.site.onboardingPhase === 'advisory') {
    return null
  }

  // Supervised phase only: hold-to-confirm action UI
  if (state.site.onboardingPhase === 'supervised' && (state.site.mode === 'prepare' || state.site.mode === 'intervene_soon')) {
    return (
      <div className="border-t border-white/8 p-4">
        <SupervisedConfirmBar
          mode="supervised"
          onConfirm={onApprove ?? (() => {
            document
              .querySelector('[data-cockpit-root]')
              ?.dispatchEvent(new CustomEvent('sentinel:approve', { bubbles: true, detail: { siteId: state.site.id } }))
          })}
        />
      </div>
    )
  }

  return (
    <div className="border-t border-white/8 px-5 py-4">
      <div className="rounded-2xl border border-white/8 bg-black/20 px-4 py-4">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-slate-500">
          <PlayIcon />
          <span>Operator path</span>
        </div>
        <div className="mt-3 text-sm leading-6 text-slate-200">{state.decision.summary}</div>
      </div>
    </div>
  )
}

function PlayIcon() {
  return <PlayCircleIcon className="h-3.5 w-3.5" />
}

function PlayCircleIcon(props: React.ComponentProps<typeof Sparkles>) {
  return <Sparkles {...props} />
}

function ZoneEquipmentPanel({
  zone,
  onClose,
}: {
  zone: CockpitTwinZoneSignal
  onClose: () => void
}) {
  const panelRef = useRef<HTMLDivElement | null>(null)

  useLayoutEffect(() => {
    if (!panelRef.current) return
    if (motionReduced()) {
      gsap.set(panelRef.current, { opacity: 1, y: 0 })
      return
    }
    const ctx = gsap.context(() => {
      gsap.fromTo(panelRef.current, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.28, ease: 'power2.out' })
    })
    return () => ctx.revert()
  }, [zone.zoneId])

  const severity = zone.isPrimary ? 'Primary' : 'Secondary'
  const severityClass = zone.isPrimary
    ? 'text-red-300 border-red-400/30 bg-red-400/10'
    : 'text-amber-300 border-amber-400/30 bg-amber-400/10'

  return (
    <div
      ref={panelRef}
      className="rounded-2xl border border-white/8 bg-[linear-gradient(180deg,rgba(8,12,22,0.97),rgba(3,7,16,0.98))] p-5"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.28em] text-slate-500">Zone equipment</div>
            <div className="mt-2 text-lg font-medium text-white">{zone.label}</div>
            <div className="mt-1 flex items-center gap-2">
              <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] ${severityClass}`}>
                {severity}
              </span>
              <span className="text-xs text-slate-400">{zone.floorId}</span>
              {zone.actionLabel && (
                <span className="text-xs text-cyan-400">{zone.actionLabel}</span>
              )}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-full border border-white/20 bg-white/5 px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-slate-300 transition hover:border-white/50"
        >
          Close
        </button>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-white/8 bg-black/20 px-3 py-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Weight</div>
          <div className="mt-2 text-base font-medium text-white">{Math.round(zone.weight * 100)}%</div>
        </div>
        <div className="rounded-xl border border-white/8 bg-black/20 px-3 py-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Floor</div>
          <div className="mt-2 text-base font-medium text-white">{zone.level}</div>
        </div>
        <div className="rounded-xl border border-white/8 bg-black/20 px-3 py-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Slot</div>
          <div className="mt-2 text-base font-medium text-white">{zone.slot ?? '—'}</div>
        </div>
      </div>
    </div>
  )
}

export function CockpitView({ state, renderMode, spatialCanvas, onApprove, selectedZone, onZoneClose, modelReadiness, onAdvancePhase, onZoneSelect }: CockpitViewProps) {
  const shellRef = useRef<HTMLElement | null>(null)
  const headerRef = useRef<HTMLDivElement | null>(null)
  const railRef = useRef<HTMLDivElement | null>(null)
  const queueRef = useRef<HTMLDivElement | null>(null)
  const twinContainerRef = useRef<HTMLDivElement | null>(null)

  const palette = useMemo(() => tonePalette(state), [state])
  const waiting = isWaitingState(state)
  const summary = useMemo(() => siteSummary(state), [state])
  const queue = useMemo(() => buildQueue(state), [state])
  const forecast = useMemo(() => buildForecast(state), [state])
  const largeHeadline = renderMode === 'wall'
  const twinCanvas = useMemo(() => <CockpitNervousSystemTwin state={state} onZoneSelect={onZoneSelect} />, [state, onZoneSelect])
  const canvas = spatialCanvas ?? twinCanvas

  const [zoomLevel, setZoomLevel] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const clampZoom = (value: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, value))

  const handleZoom = (delta: number) => {
    setZoomLevel((prev) => clampZoom(prev + delta))
  }

  const resetZoom = () => setZoomLevel(1)

  const toggleFullscreen = () => {
    if (!shellRef.current) return
    if (!document.fullscreenElement) {
      shellRef.current.requestFullscreen().then(() => {
        setIsFullscreen(true)
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(FULLSCREEN_STORAGE_KEY, '1')
        }
      }).catch(() => {
        setIsFullscreen(true)
      })
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen()
      }
      setIsFullscreen(false)
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(FULLSCREEN_STORAGE_KEY, '0')
      }
    }
  }

  useEffect(() => {
    if (typeof window === 'undefined') return
    const stored = window.localStorage.getItem(FULLSCREEN_STORAGE_KEY)
    if (stored === '1') {
      setIsFullscreen(false)
    }

    const sync = () => {
      const active = document.fullscreenElement === shellRef.current
      setIsFullscreen(active)
      if (!active && typeof window !== 'undefined') {
        window.localStorage.setItem(FULLSCREEN_STORAGE_KEY, '0')
      }
    }

    document.addEventListener('fullscreenchange', sync)
    return () => document.removeEventListener('fullscreenchange', sync)
  }, [])

  useLayoutEffect(() => {
    if (!shellRef.current) return

    const targets = [headerRef.current, railRef.current, queueRef.current].filter(Boolean)
    if (motionReduced()) {
      gsap.set(targets, { opacity: 1, y: 0 })
      return
    }

    const ctx = gsap.context(() => {
      gsap.fromTo(
        shellRef.current,
        { opacity: 0, y: 20 },
        { opacity: 1, y: 0, duration: 0.85, ease: 'power3.out' },
      )

      gsap.fromTo(
        targets,
        { opacity: 0, y: 18 },
        { opacity: 1, y: 0, duration: 0.7, stagger: 0.08, ease: 'power2.out', delay: 0.14 },
      )
    }, shellRef)

    return () => ctx.revert()
  }, [state.site.id, state.site.mode, state.primaryMetric.value, waiting])

  return (
    <section
      ref={shellRef}
      className={`sentinel-shell rounded-[30px] border border-white/8 bg-[radial-gradient(circle_at_top,rgba(15,23,42,0.96),rgba(2,6,23,0.98)_58%)] p-5 text-slate-100 md:p-6 ${isFullscreen ? 'h-[100dvh] overflow-y-auto' : ''}`}
      data-render-mode={renderMode}
      data-site-id={state.site.id}
    >
      <motion.div
        ref={headerRef}
        initial={motionReduced() ? false : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: FRAMER_EASE }}
        className="rounded-[26px] border border-white/8 bg-[linear-gradient(180deg,rgba(10,16,28,0.94),rgba(4,9,20,0.92))] px-5 py-4 md:px-6"
      >
        {/* Row 1 — Hero */}
        <div className="flex items-start gap-4">
          <div className={`mt-1.5 h-2.5 w-2.5 rounded-full ${palette.dot} ${palette.glow}`} />
          <div className="min-w-0 flex-1">
            <div className="text-[10px] uppercase tracking-[0.34em] text-slate-500">
              Sentinel Cockpit · {state.site.name}
            </div>
            <h1
              className={`mt-3 max-w-none overflow-hidden text-ellipsis whitespace-nowrap font-semibold tracking-[-0.045em] text-white ${
                largeHeadline ? 'text-4xl' : 'text-[2rem] leading-[1.02]'
              }`}
            >
              {heroHeadline(state)}
            </h1>
            <p className="mt-3 max-w-4xl text-sm leading-7 text-slate-300 md:text-[15px]">
              {heroSubheadline(state)}
            </p>
          </div>
        </div>

        {/* Row 2 — Chrome strip: summary · status chips · zoom · fullscreen */}
        <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-white/8 pt-4">
          {/* Left: site summary + mode */}
          <div className="flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-[0.22em] text-slate-500">
            <span>{summary}</span>
            <span className="text-slate-700">/</span>
            <span className={palette.text}>{modeLabel(state.site.mode)}</span>
          </div>

          {/* Right: chips + zoom + fullscreen */}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {/* Status chips — deduped (drop redundant "Waiting" when posture already says it) */}
            {state.site.posture && state.site.posture !== state.primaryMetric.value && (
              <span className={`rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.22em] ${palette.chip}`}>
                {state.site.posture}
              </span>
            )}
            <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[10px] uppercase tracking-[0.22em] text-slate-300">
              {phaseLabel(state.site.onboardingPhase)}
            </span>
            {!waiting && (
              <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[10px] uppercase tracking-[0.22em] text-slate-300">
                {timeToImpact(state)}
              </span>
            )}
            {state.site.onboardingPhase === 'shadow' && modelReadiness && (
              <span
                className={`rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.22em] ${
                  modelReadiness.ready
                    ? 'border-cyan-400/40 bg-cyan-400/10 text-cyan-300'
                    : 'border-amber-400/40 bg-amber-400/10 text-amber-300'
                }`}
                title={modelReadiness.message}
              >
                {modelReadiness.ready ? 'ML Ready' : `Training (${modelReadiness.activeModelCount})`}
              </span>
            )}

            {/* Divider */}
            <span className="h-4 w-px bg-white/8" />

            {/* Zoom controls — keep ONE set. Remove duplicates from CockpitBuildingThree. */}
            <button
              type="button"
              onClick={() => handleZoom(-ZOOM_STEP)}
              className="rounded-full border border-white/15 bg-white/5 p-1.5 transition hover:border-white/40"
              aria-label="Zoom out"
            >
              <Minimize2 className="h-3 w-3" />
            </button>
            <button
              type="button"
              onClick={resetZoom}
              className="rounded-full border border-white/15 bg-white/5 px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-300 transition hover:border-white/40"
            >
              {Math.round(zoomLevel * 100)}%
            </button>
            <button
              type="button"
              onClick={() => handleZoom(ZOOM_STEP)}
              className="rounded-full border border-white/15 bg-white/5 p-1.5 transition hover:border-white/40"
              aria-label="Zoom in"
            >
              <Maximize2 className="h-3 w-3" />
            </button>

            {/* Divider */}
            <span className="h-4 w-px bg-white/8" />

            {/* Fullscreen */}
            <button
              type="button"
              onClick={toggleFullscreen}
              className="flex items-center gap-1.5 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[10px] uppercase tracking-[0.22em] text-slate-200 transition hover:border-white/40"
              aria-label={isFullscreen ? 'Exit full screen' : 'Enter full screen'}
            >
              {isFullscreen ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
              <span>{isFullscreen ? 'Exit' : 'Full screen'}</span>
            </button>
          </div>
        </div>
      </motion.div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <motion.div
          initial={motionReduced() ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.08, ease: FRAMER_EASE }}
          className="space-y-5"
        >
          <div
            ref={twinContainerRef}
            className="origin-top"
            style={{
              transform: `scale(${zoomLevel})`,
              transition: 'transform 0.2s cubic-bezier(0.4,0,0.2,1)',
              transformOrigin: '50% 0',
              width: '100%',
            }}
          >
            {canvas}
          </div>

          {selectedZone && (
            <ZoneEquipmentPanel zone={selectedZone} onClose={onZoneClose ?? (() => {})} />
          )}

          <div className="grid gap-3 md:grid-cols-3">
            {forecast.map((item) => (
              <ForecastPill key={item.label} label={item.label} value={item.value} />
            ))}
          </div>

          <motion.div
            ref={queueRef}
            initial={motionReduced() ? false : { opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.14, ease: FRAMER_EASE }}
            className="rounded-[28px] border border-white/8 bg-[linear-gradient(180deg,rgba(8,12,22,0.9),rgba(3,7,16,0.95))] p-5 md:p-6"
          >
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500">Signal queue</div>
                <div className="mt-2 text-lg font-medium text-slate-100">Secondary tensions and observed pressure</div>
              </div>
              <div className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1 text-[10px] uppercase tracking-[0.22em] text-slate-300">
                {queue.length} item{queue.length === 1 ? '' : 's'}
              </div>
            </div>

            <div className="mt-5 grid gap-4 xl:grid-cols-3">
              {queue.map((item) => (
                <InsightCard key={`${item.severity}-${item.title}`} item={item} />
              ))}
            </div>
          </motion.div>
        </motion.div>

        <motion.aside
          ref={railRef}
          initial={motionReduced() ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.1, ease: FRAMER_EASE }}
          className="overflow-hidden rounded-[28px] border border-white/8 bg-[linear-gradient(180deg,rgba(16,23,39,0.96),rgba(8,12,22,0.98))]"
        >
          <div className="flex items-center justify-between gap-3 border-b border-white/8 px-5 py-4">
            <div>
              <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500">{railTitle(state)}</div>
              <div className="mt-2 text-base font-medium text-slate-100">
                {waiting ? 'Waiting for live state' : state.decision.summary}
              </div>
            </div>
            <span className={`rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.22em] ${palette.chip}`}>
              {waiting ? 'Waiting' : state.site.posture}
            </span>
          </div>

          {state.site.onboardingPhase === 'shadow' && modelReadiness?.ready && (
            <div className="border-t border-white/8 px-5 py-4">
              <div className="rounded-xl border border-cyan-400/20 bg-cyan-400/5 px-4 py-3 text-center">
                <div className="text-[10px] uppercase tracking-[0.2em] text-cyan-400 mb-2">ML Training complete — site ready for advisory</div>
                <div className="text-xs text-slate-400 mb-3">
                  {modelReadiness.activeModelCount} model(s) covering {modelReadiness.equipmentTypesCovered.join(', ')}
                </div>
                <button
                  type="button"
                  onClick={onAdvancePhase}
                  className="w-full rounded-lg bg-cyan-500/20 border border-cyan-400/40 px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-cyan-300 transition hover:bg-cyan-500/30"
                >
                  Advance to Advisory →
                </button>
              </div>
            </div>
          )}

          {state.site.onboardingPhase === 'shadow' ? (
            <>
              {/* Shadow mode: replace decision fields with telemetry observation fields */}
              <DetailRow
                icon={<Brain className="h-3.5 w-3.5" />}
                label="Observation"
                value={state.activeCondition.summary}
                accent
              />
              <DetailRow
                icon={<Layers3 className="h-3.5 w-3.5" />}
                label="ML Training"
                value={state.emergingRisks.length > 0 ? `${state.emergingRisks.length} tension(s) under observation` : 'Model calibration in progress'}
              />
              <DetailRow
                icon={<Clock3 className="h-3.5 w-3.5" />}
                label="Observation window"
                value="Ongoing — no constraint breach predicted"
                accent
              />
              <DetailRow
                icon={<ArrowRight className="h-3.5 w-3.5" />}
                label="Mode"
                value={`Observation only · ${state.site.dataFreshnessLabel}`}
                accent
              />
              <DetailRow
                icon={<Gauge className="h-3.5 w-3.5" />}
                label="Load profile"
                value={telemetrySnapshot(state)}
              />
            </>
          ) : (
            <>
              {/* Advisory+: decision surface fields */}
              <DetailRow icon={<Brain className="h-3.5 w-3.5" />} label="Cause" value={waiting ? 'No live building signal yet.' : state.activeCondition.summary} accent />
              <DetailRow icon={<Layers3 className="h-3.5 w-3.5" />} label="Impact" value={waiting ? 'No operator action required until live state arrives.' : `${state.decision.impact} · ${activeModuleLabels(state).join(' + ')}`} />
              <DetailRow icon={<Clock3 className="h-3.5 w-3.5" />} label="Time to impact" value={timeToImpact(state)} accent />
              <DetailRow icon={<ArrowRight className="h-3.5 w-3.5" />} label="Action" value={waiting ? 'Watch for live building state.' : `${state.decision.summary} · ${state.site.dataFreshnessLabel}`} accent />
              <DetailRow icon={<Gauge className="h-3.5 w-3.5" />} label="Trade-off" value={waiting ? 'No intervention energy penalty while waiting.' : `${state.decision.tradeoff} · ${telemetrySnapshot(state)}`} />
            </>
          )}

          <div className="grid grid-cols-2 gap-3 border-t border-white/8 px-5 py-4">
            <div className={`rounded-2xl border ${palette.border} ${palette.soft} px-4 py-3`}>
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-slate-500">
                <Shield className="h-3.5 w-3.5" />
                <span>Evidence</span>
              </div>
              <div className="mt-3 text-sm text-slate-100">{evidenceLabel(state)}</div>
            </div>

            <div className="rounded-2xl border border-white/8 bg-black/20 px-4 py-3">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-slate-500">
                <TimerReset className="h-3.5 w-3.5" />
                <span>{freshnessLabel(state)}</span>
              </div>
              <div className="mt-3 text-sm text-slate-100">{state.site.dataFreshnessLabel}</div>
            </div>
          </div>

          <div className="border-t border-white/8 px-5 py-4">
            <div className="mb-3 flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-slate-500">
              <Orbit className="h-3.5 w-3.5" />
              <span>System posture</span>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-300">
                Mode: {modeLabel(state.site.mode)}
              </span>
              <span className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-300">
                Phase: {phaseLabel(state.site.onboardingPhase)}
              </span>
              <span className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-300">
                Signal: {waiting ? 'Waiting' : `Live · ${activeModuleLabels(state).join(' + ')}`}
              </span>
              <span className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-300">
                Secondary: {state.emergingRisks.length}
              </span>
            </div>
          </div>

          <RailAction state={state} onApprove={onApprove} />
        </motion.aside>
      </div>

      {!waiting && (
        <div className="mt-5 flex items-center gap-4 rounded-[20px] border border-white/8 bg-black/30 px-5 py-3">
          {/* Live telemetry — the one thing not shown elsewhere */}
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${palette.dot} animate-pulse`} />
            <span className="font-mono text-xs text-slate-200 tabular-nums">
              {telemetrySnapshot(state)}
            </span>
          </div>

          <span className="h-4 w-px bg-white/8" />

          {/* Freshness countdown */}
          <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.22em] text-slate-500">
            <TimerReset className="h-3 w-3" />
            <span className="text-slate-300 normal-case tracking-normal">
              {state.site.dataFreshnessLabel}
            </span>
          </div>

          <span className="h-4 w-px bg-white/8" />

          {/* System dots */}
          <div className="flex items-center gap-2">
            {activeModuleLabels(state).map((mod) => (
              <span
                key={mod}
                className="flex items-center gap-1 text-[10px] uppercase tracking-[0.18em] text-slate-400"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-cyan-400/70" />
                {mod}
              </span>
            ))}
          </div>

          {/* Right: only the actionable bit */}
          <div className="ml-auto text-[10px] uppercase tracking-[0.22em] text-slate-500">
            {state.evidence.refs.length} evidence refs
          </div>
        </div>
      )}
    </section>
  )
}

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type MutableRefObject, type RefObject } from 'react'
import gsap from 'gsap'
import type { CockpitState } from './types'

export type SignalStatus = 'online' | 'stale' | 'offline' | 'inferred'
export type TwinMode = 'overview' | 'hvac' | 'energy' | 'occupancy' | 'security'

export interface TwinState {
  mode: TwinMode
  headline: string
  summary: string
  siteName: string
  status: 'stable' | 'watch' | 'degraded' | 'drifting' | 'critical'
  confidence: number
  timeToConstraintMin?: number
  signals: {
    bms: SignalStatus
    energy: SignalStatus
    occupancy: SignalStatus
    weather?: SignalStatus
    helpdesk?: SignalStatus
  }
  reasoning: string[]
  prediction?: string
  recommendedAction?: string
}

const TABS: { id: TwinMode; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'hvac', label: 'HVAC' },
  { id: 'energy', label: 'Energy' },
  { id: 'occupancy', label: 'Occupancy' },
  { id: 'security', label: 'Security' },
]

const SIGNAL_LABELS: Record<keyof TwinState['signals'], string> = {
  bms: 'BMS feed',
  energy: 'Energy feed',
  occupancy: 'Occupancy feed',
  weather: 'Weather feed',
  helpdesk: 'Helpdesk feed',
}

const SIGNAL_ORDER: (keyof TwinState['signals'])[] = ['bms', 'energy', 'occupancy', 'weather', 'helpdesk']

const STATUS_TONE_CLASSES: Record<TwinState['status'], string> = {
  stable: 'from-slate-700 to-blue-900 border-blue-500/30 text-blue-200 bg-blue-500/5',
  watch: 'from-slate-700 to-amber-900 border-amber-500/30 text-amber-200 bg-amber-500/5',
  degraded: 'from-slate-800 to-amber-900 border-amber-500/30 text-amber-50 bg-amber-500/5',
  drifting: 'from-slate-900 to-slate-800 border-slate-400/30 text-slate-100 bg-slate-500/10',
  critical: 'from-slate-900 to-red-900 border-red-500/30 text-red-200 bg-red-500/5',
}

const SIGNAL_STATUS_STYLES: Record<SignalStatus, { text: string; border: string; bg: string }> = {
  online: { text: 'text-sky-200', border: 'border-sky-500/30', bg: 'bg-sky-500/5' },
  stale: { text: 'text-amber-200', border: 'border-amber-500/30', bg: 'bg-amber-500/5' },
  offline: { text: 'text-red-200', border: 'border-red-500/30', bg: 'bg-red-500/5' },
  inferred: { text: 'text-violet-200', border: 'border-violet-500/30', bg: 'bg-violet-500/5' },
}

const DEGRADE_STATUSES = new Set<SignalStatus>(['stale', 'offline', 'inferred'])

function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia === 'undefined') return
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setPrefersReducedMotion(mediaQuery.matches)
    update()
    mediaQuery.addEventListener('change', update)
    return () => mediaQuery.removeEventListener('change', update)
  }, [])

  return prefersReducedMotion
}

interface StatusPillProps {
  label: string
  value: string
  toneClass?: string
}

function StatusPill({ label, value, toneClass = 'border-white/20 text-slate-200 bg-white/5' }: StatusPillProps) {
  return (
    <div className={`flex flex-col rounded-2xl border px-4 py-2 text-[11px] uppercase tracking-[0.2em] shadow-[0_0_24px_rgba(2,6,23,0.65)] ${toneClass}`}>
      <span className="text-[8px] opacity-70">{label}</span>
      <span className="mt-1 font-semibold tracking-[0.1em] text-sm uppercase leading-none">{value}</span>
    </div>
  )
}

interface SignalChipProps {
  label: string
  status: SignalStatus
  onMount: (el: HTMLDivElement | null) => void
}

const SignalChip = ({ label, status, onMount }: SignalChipProps) => {
  const styles = SIGNAL_STATUS_STYLES[status]
  return (
    <div
      ref={onMount}
      className={`flex items-center gap-2 rounded-full border px-3 py-1 text-[9px] font-semibold uppercase tracking-[0.3em] ${styles.border} ${styles.text} ${styles.bg}`}
    >
      <span>{label}</span>
      <span className="text-[8px] text-white/70">{status}</span>
    </div>
  )
}

function clampConfidence(score: number) {
  return Math.min(100, Math.max(8, Math.round(score * 100)))
}

// eslint-disable-next-line react-refresh/only-export-components
export function mapCockpitStateToTwinState(state: CockpitState): TwinState {
  const isWaiting = state.site.renderState === 'waiting'
  const tone = state.primaryMetric.tone
  const status: TwinState['status'] =
    tone === 'critical' || state.severity.riskBand === 'critical'
      ? 'critical'
      : state.site.posture?.toLowerCase().includes('drift')
      ? 'drifting'
      : tone === 'warning' || state.site.posture?.toLowerCase().includes('prepare')
      ? 'degraded'
      : tone === 'elevated'
      ? 'watch'
      : 'stable'

  const confidence = clampConfidence(state.sitePulse.attentionScore)

  const signalEntries: TwinState['signals'] = {
    bms: isWaiting ? 'offline' : tone === 'critical' ? 'offline' : tone === 'warning' || tone === 'elevated' ? 'stale' : 'online',
    energy: state.severity.riskBand === 'high' || state.severity.riskBand === 'critical' ? 'stale' : 'online',
    occupancy: state.site.posture?.toLowerCase().includes('comfort') ? 'online' : 'online',
    weather: isWaiting ? 'offline' : 'online',
    helpdesk: state.emergingRisks.length > 0 ? 'inferred' : 'online',
  }

  const reasoning = [
    state.activeCondition.summary,
    state.activeCondition.rationale,
    state.decision.summary,
    state.evidence.summary,
    state.site.dataFreshnessLabel,
  ]
    .filter(Boolean)
    .slice(0, 4)

  return {
    mode: 'overview',
    headline: state.activeCondition.summary,
    summary: state.decision.summary,
    siteName: state.site.name,
    status,
    confidence,
    timeToConstraintMin: state.severity.timeToConstraintBreachMin ?? undefined,
    signals: signalEntries,
    reasoning,
    prediction: state.primaryMetric.detail,
    recommendedAction: state.decision.summary,
  }
}

function useGsapTwinMotion(
  state: TwinState,
  signalEntries: [keyof TwinState['signals'], SignalStatus][],
  heroRef: RefObject<HTMLDivElement>,
  glowRef: RefObject<HTMLDivElement>,
  tabsRef: RefObject<HTMLDivElement>,
  underlineRef: RefObject<HTMLSpanElement>,
  tabButtons: MutableRefObject<Record<TwinMode, HTMLButtonElement | null>>,
  signalRefs: MutableRefObject<(HTMLDivElement | null)[]>,
  countdownRef: RefObject<HTMLDivElement>,
  confidenceRef: RefObject<HTMLDivElement>,
  activeTab: TwinMode,
  reducedMotion: boolean,
) {
  useLayoutEffect(() => {
    if (!heroRef.current) return

    // Wrap in gsap.context scoped to heroRef — all tweens auto-cleaned on revert()
    const ctx = gsap.context(() => {
      const cleanSignalTweens = () => {
        signalRefs.current.forEach((el) => { if (el) gsap.killTweensOf(el) })
      }

      if (reducedMotion) {
        if (confidenceRef.current) confidenceRef.current.style.width = `${state.confidence}%`
        const target = tabButtons.current[activeTab]
        if (underlineRef.current && tabsRef.current && target) {
          const containerRect = tabsRef.current.getBoundingClientRect()
          const targetRect = target.getBoundingClientRect()
          gsap.set(underlineRef.current, {
            width: targetRect.width,
            x: targetRect.left - containerRect.left,
          })
        }
        cleanSignalTweens()
        return
      }

      if (!glowRef.current || !confidenceRef.current) return

      const power2Ease = gsap.parseEase('power2.out')
      const sineEase = gsap.parseEase('sine.inOut')

      // Hero entrance — GSAP owns this, no Framer conflict
      gsap.timeline()
        .fromTo(
          heroRef.current,
          { opacity: 0, y: 18 },
          { opacity: 1, y: 0, duration: 0.8, ease: 'power3.out' },
        )
        .to(
          glowRef.current,
          { opacity: 0.45, duration: 1.4, repeat: -1, yoyo: true, ease: sineEase },
          0,
        )
        .to(
          confidenceRef.current,
          { width: `${state.confidence}%`, duration: 0.9, ease: power2Ease },
          0.2,
        )

      const targetButton = tabButtons.current[activeTab]
      if (targetButton && underlineRef.current && tabsRef.current) {
        const containerRect = tabsRef.current.getBoundingClientRect()
        const targetRect = targetButton.getBoundingClientRect()
        gsap.to(underlineRef.current, {
          width: targetRect.width,
          x: targetRect.left - containerRect.left,
          duration: 0.55,
          ease: power2Ease,
        })
      }

      if (countdownRef.current) {
        gsap.fromTo(
          countdownRef.current,
          { opacity: 0, y: 6 },
          { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' },
        )
      }

      signalEntries.forEach(([, status], index) => {
        if (!DEGRADE_STATUSES.has(status)) return
        const el = signalRefs.current[index]
        if (!el) return
        gsap.to(el, {
          boxShadow: '0 0 20px rgba(245,158,11,0.45)',
          duration: 1.6,
          repeat: -1,
          yoyo: true,
          ease: 'sine.inOut',
        })
      })
    }, heroRef)

    return () => ctx.revert()
  }, [
    state,
    signalEntries,
    activeTab,
    reducedMotion,
    confidenceRef,
    countdownRef,
    glowRef,
    heroRef,
    signalRefs,
    tabButtons,
    tabsRef,
    underlineRef,
  ])
}

interface SentinelCockpitTwinProps {
  state: TwinState
}

export const SentinelCockpitTwin = ({ state }: SentinelCockpitTwinProps) => {
  const reducedMotion = usePrefersReducedMotion()
  const [activeTab, setActiveTab] = useState<TwinMode>(state.mode)
  const heroRef = useRef<HTMLDivElement>(null)
  const heroGlowRef = useRef<HTMLDivElement>(null)
  const tabsRef = useRef<HTMLDivElement>(null)
  const underlineRef = useRef<HTMLSpanElement>(null)
  const countdownRef = useRef<HTMLDivElement>(null)
  const confidenceBarRef = useRef<HTMLDivElement>(null)
  const signalRefs = useRef<(HTMLDivElement | null)[]>([])
  const tabButtons = useRef<Record<TwinMode, HTMLButtonElement | null>>({} as Record<TwinMode, HTMLButtonElement | null>)

  useEffect(() => { setActiveTab(state.mode) }, [state.mode])

  const signalEntries = useMemo(() => {
    const entries: [keyof TwinState['signals'], SignalStatus][] = []
    SIGNAL_ORDER.forEach((key) => {
      const value = state.signals[key]
      if (typeof value !== 'undefined') entries.push([key, value])
    })
    return entries
  }, [state.signals])

  useEffect(() => {
    signalRefs.current.length = signalEntries.length
  }, [signalEntries])

  useGsapTwinMotion(
    state, signalEntries,
    heroRef, heroGlowRef, tabsRef, underlineRef,
    tabButtons, signalRefs, countdownRef, confidenceBarRef,
    activeTab, reducedMotion,
  )

  const statusToneClass = STATUS_TONE_CLASSES[state.status]
  const confidenceTone =
    state.confidence > 70
      ? 'border-emerald-400/30 text-emerald-200 bg-emerald-500/5'
      : state.confidence > 45
      ? 'border-amber-400/30 text-amber-200 bg-amber-500/5'
      : 'border-red-500/30 text-red-200 bg-red-500/5'
  const finalPrediction = state.prediction ?? 'Awaiting reliable prediction'
  const action = state.recommendedAction ?? 'Monitor signal strip for updates.'

  return (
    <article className="sentinel-twin max-w-5xl rounded-[32px] border border-white/10 bg-gradient-to-b from-[#020B16] to-[#010409] p-4 text-slate-100 shadow-[0_20px_80px_rgba(2,6,23,0.65)] md:p-6">
      <div className="mb-4 flex w-full flex-wrap items-center justify-between gap-3">
        <div className="text-xs uppercase tracking-[0.4em] text-slate-500">Sentinel Cockpit — Building Spatial View</div>
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.4em] text-slate-400">
          <span className="text-slate-200">{state.siteName}</span>
          <span className="rounded-full border border-white/10 px-3 py-1 text-[9px] tracking-[0.3em] text-slate-300">{state.status}</span>
        </div>
      </div>

      {/* Plain div — GSAP owns entrance animation, no Framer conflict */}
      <div
        ref={heroRef}
        style={{ opacity: 0 }}
        className="relative rounded-3xl border border-white/10 bg-[radial-gradient(circle_at_top,rgba(15,23,42,0.9),rgba(2,6,23,0.95))] p-5 shadow-[0_40px_90px_rgba(2,6,23,0.6)]"
      >
        <div ref={heroGlowRef} className="pointer-events-none absolute inset-0 rounded-3xl bg-gradient-to-br from-sky-500/10 to-transparent opacity-20 blur-3xl" />
        <div className="relative">
          <div className="flex flex-wrap items-center gap-4 text-[10px] uppercase tracking-[0.3em] text-slate-400">
            <span className="text-white/80">{state.status.toUpperCase()}</span>
            <span className="mx-1 h-0.5 w-6 rounded-full bg-white/30" />
            <span>{state.summary}</span>
          </div>

          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white md:text-[2.8rem]">
            {state.headline}
          </h1>

          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-300 md:text-base">
            {state.summary}
          </p>

          <div className="mt-4 flex flex-wrap gap-3">
            <StatusPill label="State" value={state.status} toneClass={statusToneClass} />
            <StatusPill label="Confidence" value={`${state.confidence}%`} toneClass={confidenceTone} />
            <StatusPill label="Source health" value={state.siteName} />
          </div>

          <div className="mt-5 h-2 w-full overflow-hidden rounded-full border border-white/10 bg-white/5">
            <div ref={confidenceBarRef} className="h-full rounded-full bg-gradient-to-r from-amber-400 to-orange-500" style={{ width: 0 }} />
          </div>

          <div className="mt-4 flex items-end flex-wrap gap-4 text-sm">
            {typeof state.timeToConstraintMin === 'number' ? (
              <div className="flex items-center gap-2 text-lg font-semibold text-slate-50">
                <span ref={countdownRef}>{state.timeToConstraintMin} min</span>
                <span className="text-xs uppercase tracking-[0.4em] text-slate-500">time to constraint</span>
              </div>
            ) : (
              <div ref={countdownRef} className="text-base font-semibold text-slate-200">
                Awaiting signal clarity
              </div>
            )}
            <span className="text-xs uppercase tracking-[0.4em] text-slate-500">Reasoning-ready</span>
          </div>
        </div>
      </div>

      <div className="relative mt-5 flex flex-wrap items-center gap-3" ref={tabsRef}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            ref={(el) => { tabButtons.current[tab.id] = el }}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`rounded-full border px-4 py-2 text-[9px] uppercase tracking-[0.4em] transition ${
              activeTab === tab.id
                ? 'border-amber-400/60 bg-amber-500/10 text-amber-200'
                : 'border-white/10 bg-transparent text-slate-400 hover:border-white/40 hover:text-white'
            }`}
          >
            {tab.label}
          </button>
        ))}
        <span ref={underlineRef} className="absolute inset-x-0 bottom-0 mx-auto h-0.5 max-w-[180px] rounded-full bg-amber-500" />
      </div>

      <div className="mt-4 flex flex-col gap-3 rounded-3xl border border-white/10 bg-[linear-gradient(180deg,rgba(6,10,24,0.8),rgba(3,5,14,0.92))] p-5 shadow-[0_30px_60px_rgba(2,6,23,0.6)]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.3em] text-slate-500">Live signal strip</div>
            <div className="text-base font-semibold text-slate-100">Source health overview</div>
          </div>
          <div className="text-xs uppercase tracking-[0.4em] text-slate-400">{activeTab.toUpperCase()}</div>
        </div>
        <div className="flex flex-wrap gap-3">
          {signalEntries.map(([key, status], index) => (
            <SignalChip
              key={key}
              label={SIGNAL_LABELS[key]}
              status={status}
              onMount={(el) => { signalRefs.current[index] = el }}
            />
          ))}
        </div>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <section className="rounded-3xl border border-white/10 bg-black/40 p-5">
          <div className="text-[10px] uppercase tracking-[0.3em] text-slate-500">Reasoning</div>
          <ul className="mt-3 space-y-3 text-sm text-slate-300">
            {state.reasoning.map((fact, index) => (
              <li key={`${fact}-${index}`} className="rounded-2xl border border-white/5 bg-white/5 p-3 text-xs leading-5 text-slate-100">
                {fact}
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-3xl border border-white/10 bg-gradient-to-b from-slate-900/60 to-slate-900/20 p-5">
          <div className="text-[10px] uppercase tracking-[0.3em] text-slate-500">Prediction</div>
          <p className="mt-3 text-lg font-semibold text-slate-100">{finalPrediction}</p>
          {typeof state.timeToConstraintMin === 'number' && (
            <p className="mt-2 text-sm uppercase tracking-[0.4em] text-slate-400">Estimated window · {state.timeToConstraintMin} min</p>
          )}
        </section>

        <section className="rounded-3xl border border-white/10 bg-[radial-gradient(circle,rgba(24,58,115,0.25),rgba(2,6,23,0.9))] p-5">
          <div className="text-[10px] uppercase tracking-[0.3em] text-slate-500">Recommended action</div>
          <p className="mt-3 text-lg font-semibold text-slate-100">{action}</p>
          <p className="mt-2 text-sm text-slate-400">Calm, confident, and operator-ready.</p>
        </section>
      </div>
    </article>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export const sentinelTwinMock: TwinState = {
  headline: 'Building observability degraded',
  summary: 'Live telemetry loss detected across core systems',
  siteName: 'Sandton City Office Tower',
  mode: 'overview',
  status: 'drifting',
  confidence: 42,
  timeToConstraintMin: 18,
  signals: {
    bms: 'offline',
    energy: 'stale',
    occupancy: 'online',
    weather: 'online',
    helpdesk: 'inferred',
  },
  reasoning: [
    'Occupancy remains active in monitored zones',
    'BMS feed offline for 22 minutes',
    'Energy delta flat despite expected demand',
    'System confidence reduced due to source mismatch',
  ],
  prediction: 'Comfort breach likely within 18 minutes if live telemetry is not restored',
  recommendedAction: 'Verify source health and restore BMS feed integrity',
}

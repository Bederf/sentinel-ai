import { useLayoutEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode, type RefObject } from 'react'
import gsap from 'gsap'
import type { CockpitRenderMode, CockpitState } from './types'
import { useToneTransition } from './useToneTransition'
import { useAmbientDrift } from './useAmbientDrift'
import { useUrgencyPulse } from './useUrgencyPulse'
import { SupervisedConfirmBar } from './useHoldToConfirm'
import { useDecisionRowEntrance } from './useDecisionRowEntrance'
import { motionReduced } from './motionPreference'

interface CockpitViewProps {
  state: CockpitState
  renderMode: CockpitRenderMode
  spatialCanvas: ReactNode
}

interface CockpitStatusPillProps {
  children: ReactNode
}

function buildVoice(state: CockpitState) {
  if (state.primaryMetric.value === 'Stable') {
    return {
      headline: 'No comfort risk for the next 30 minutes',
      supporting: `No action needed at ${state.site.name}.`,
    }
  }

  if (state.primaryMetric.tone === 'critical') {
    return {
      headline: `${state.visualTwin.activeLabel} will breach comfort in ${state.primaryMetric.value}`,
      supporting: `Act now: ${state.decision.summary}`,
    }
  }

  if (state.primaryMetric.tone === 'warning') {
    return {
      headline: `${state.visualTwin.activeLabel} is drifting toward discomfort`,
      supporting: `${state.decision.summary} before ${state.primaryMetric.value}.`,
    }
  }

  if (state.primaryMetric.tone === 'elevated') {
    return {
      headline: `${state.visualTwin.activeLabel} needs intervention before comfort slips`,
      supporting: `${state.decision.summary} before ${state.primaryMetric.value}.`,
    }
  }

  return {
    headline: `No immediate comfort risk at ${state.site.name}`,
    supporting: 'No action needed. Keep watching for the next drift window.',
  }
}

function toneClass(tone: CockpitState['primaryMetric']['tone']) {
  if (tone === 'critical') return 'text-red-300'
  if (tone === 'elevated') return 'text-orange-300'
  if (tone === 'warning') return 'text-amber-300'
  return 'text-sky-300'
}

function SectionRow({
  label,
  value,
  emphasis = false,
}: {
  label: string
  value: ReactNode
  emphasis?: boolean
}) {
  return (
    <div className="border-t border-slate-800 py-3 first:border-t-0 first:pt-0" data-decision-row>
      <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">{label}</div>
      <div className={`mt-2 text-sm leading-relaxed ${emphasis ? 'font-medium text-white' : 'text-slate-300'}`}>
        {value}
      </div>
    </div>
  )
}

function CockpitStatusPill({ children }: CockpitStatusPillProps) {
  return <span className="rounded-full border border-slate-800 px-3 py-1">{children}</span>
}

function formatLabel(value: string) {
  return value.replace(/_/g, ' ')
}

function useEntranceAnimation(
  rootRef: RefObject<HTMLElement | null>,
  voiceRef: RefObject<HTMLDivElement | null>,
  twinRef: RefObject<HTMLDivElement | null>,
  decisionRef: RefObject<HTMLElement | null>,
  statusRef: RefObject<HTMLDivElement | null>,
) {
  useLayoutEffect(() => {
    if (!rootRef.current) return

    if (motionReduced()) {
      gsap.set([voiceRef.current, twinRef.current, decisionRef.current, statusRef.current], {
        autoAlpha: 1,
        y: 0,
      })
      return
    }

    const ctx = gsap.context(() => {
      gsap.set([voiceRef.current, twinRef.current, decisionRef.current, statusRef.current], {
        autoAlpha: 0,
        y: 18,
      })

      gsap.timeline({ defaults: { duration: 0.72, ease: 'power3.out' } })
        .to(voiceRef.current, { autoAlpha: 1, y: 0 })
        .to([twinRef.current, decisionRef.current], { autoAlpha: 1, y: 0, stagger: 0.08 }, '-=0.32')
        .to(statusRef.current, { autoAlpha: 1, y: 0 }, '-=0.28')
    }, rootRef)

    return () => ctx.revert()
  }, [decisionRef, rootRef, statusRef, twinRef, voiceRef])
}

function useRefreshAnimation(
  voiceRef: RefObject<HTMLDivElement | null>,
  decisionRef: RefObject<HTMLElement | null>,
  state: CockpitState,
  voice: ReturnType<typeof buildVoice>,
) {
  useLayoutEffect(() => {
    if (motionReduced()) return
    if (!voiceRef.current || !decisionRef.current) return

    const timeline = gsap.timeline({ defaults: { duration: 0.42, ease: 'power2.out' } })
    timeline
      .fromTo(voiceRef.current, { y: 10, autoAlpha: 0.88 }, { y: 0, autoAlpha: 1, clearProps: 'transform,opacity' })
      .fromTo(decisionRef.current, { y: 10, autoAlpha: 0.92 }, { y: 0, autoAlpha: 1, clearProps: 'transform,opacity' }, '-=0.24')

    return () => {
      timeline.kill()
    }
  }, [decisionRef, state.decision.summary, state.primaryMetric.value, state.site.mode, voice.headline, voiceRef])
}

interface CockpitHeroProps {
  voiceRef: MutableRefObject<HTMLDivElement | null>
  metricValueRef: MutableRefObject<HTMLDivElement | null>
  voice: ReturnType<typeof buildVoice>
  state: CockpitState
  isWall: boolean
  emphasisTone: string
  onFullscreenClick: () => void
  isFullscreen: boolean
}

function CockpitHero({
  voiceRef,
  metricValueRef,
  voice,
  state,
  isWall,
  emphasisTone,
  onFullscreenClick,
  isFullscreen,
}: CockpitHeroProps) {
  return (
    <div
      ref={(node) => {
        voiceRef.current = node
      }}
      className="border-b border-slate-800/80 pb-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Sentinel Cockpit</div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.22em] text-slate-400">
            <span>{state.site.name}</span>
            <span className="text-slate-600">/</span>
            <span>{state.site.mode}</span>
          </div>
          <button
            onClick={onFullscreenClick}
            className="ml-2 rounded p-1.5 hover:bg-slate-800/50 transition-colors"
            title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
            aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
          >
            {isFullscreen ? (
              <svg className="h-4 w-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="h-4 w-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 8V4m0 0h4m-4 0l5 5m11-5v4m0-4h-4m4 0l-5 5M4 20v-4m0 4h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5"
                />
              </svg>
            )}
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px] xl:items-end">
        <div>
          <h2 className={`${isWall ? 'text-6xl' : 'text-5xl'} font-semibold tracking-[-0.04em] text-white`}>
            {voice.headline}
          </h2>
          <p className="mt-3 max-w-3xl text-base leading-relaxed text-slate-300 md:text-lg">
            {voice.supporting}
          </p>
        </div>

        <div className="rounded-2xl border border-slate-800/80 bg-slate-900/60 px-4 py-3">
          <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">
            {state.primaryMetric.label}
          </div>
          <div
            ref={(node) => { metricValueRef.current = node }}
            className={`mt-2 text-3xl font-semibold ${emphasisTone}`}
          >
            {state.primaryMetric.value}
          </div>
          <div className="mt-1 text-sm text-slate-400">{state.primaryMetric.detail}</div>
        </div>
      </div>
    </div>
  )
}

interface CockpitDecisionPanelProps {
  decisionRef: MutableRefObject<HTMLElement | null>
  badgeRef: MutableRefObject<HTMLElement | null>
  decisionRowsRef: MutableRefObject<HTMLElement | null>
  state: CockpitState
  emphasisTone: string
}

function CockpitDecisionPanel({
  decisionRef,
  badgeRef,
  decisionRowsRef,
  state,
  emphasisTone,
}: CockpitDecisionPanelProps) {
  return (
    <aside
      ref={(node) => {
        decisionRef.current = node
        decisionRowsRef.current = node
      }}
      className="rounded-[24px] border border-slate-800/80 bg-slate-900/70 px-5 py-5"
    >
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Decision</div>
          <div className="mt-1 text-sm text-slate-300">{state.site.posture}</div>
        </div>
        <span
          ref={(node) => { badgeRef.current = node }}
          className={`rounded-full border border-slate-800 px-3 py-1 text-[11px] uppercase tracking-[0.18em] ${emphasisTone}`}
        >
          {state.site.mode}
        </span>
      </div>

      <SectionRow label="Cause" value={state.activeCondition.summary} emphasis />
      <SectionRow label="Impact" value={state.decision.impact} />
      <SectionRow label="Time" value={`${state.primaryMetric.value} · ${state.primaryMetric.label}`} emphasis />
      <SectionRow label="Action" value={state.decision.summary} emphasis />
      <SectionRow label="Trade-Off" value={state.decision.tradeoff} />
      <SectionRow label="Confidence" value={state.decision.confidence} />
      <CockpitDecisionModeState state={state} />
    </aside>
  )
}

function CockpitDecisionModeState({ state }: { state: CockpitState }) {
  if (state.site.mode === 'advisory') {
    return (
      <details className="mt-4 rounded-2xl border border-slate-800/80 bg-slate-950/40 px-4 py-3">
        <summary className="cursor-pointer list-none text-[11px] uppercase tracking-[0.22em] text-slate-400">
          Show control path
        </summary>
        <div className="mt-3 space-y-3">
          {state.decision.navigationPath.length > 0 && (
            <SectionRow label="BMS Path" value={state.decision.navigationPath.join(' → ')} />
          )}
          <SectionRow label="Command" value={state.decision.command} />
          <SectionRow label="Operator Prompt" value={state.decision.operatorPrompt} />
        </div>
      </details>
    )
  }

  if (state.site.mode === 'supervised') {
    return <SupervisedConfirmBar onConfirm={() => { /* operator confirmed — handled by parent */ }} />
  }

  if (state.site.mode === 'autonomous') {
    return (
      <div className="mt-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-4 text-sm text-emerald-100">
        <div className="font-semibold">Executed + verifying</div>
        <div className="mt-2 text-emerald-200/90">{state.decision.verification}</div>
      </div>
    )
  }

  return null
}

function CockpitStatusBar({
  statusRef,
  state,
}: {
  statusRef: MutableRefObject<HTMLDivElement | null>
  state: CockpitState
}) {
  return (
    <div
      ref={(node) => {
        statusRef.current = node
      }}
      className="mt-5 flex flex-wrap items-center gap-2 border-t border-slate-800/80 pt-4 text-xs text-slate-400"
    >
      <CockpitStatusPill>{state.site.dataFreshnessLabel}</CockpitStatusPill>
      <CockpitStatusPill>Mode: {state.site.mode}</CockpitStatusPill>
      <CockpitStatusPill>Confidence: {state.decision.confidence}</CockpitStatusPill>
      {state.severity.riskBand && (
        <CockpitStatusPill>Risk band: {state.severity.riskBand}</CockpitStatusPill>
      )}
      {state.severity.constraintType && (
        <CockpitStatusPill>
          Constraint: {formatLabel(state.severity.constraintType)}
          {state.severity.timeToConstraintBreachMin !== null ? ` · ${state.severity.timeToConstraintBreachMin} min` : ''}
        </CockpitStatusPill>
      )}
      {state.severity.affectedScope && (
        <CockpitStatusPill>
          Scope: {state.severity.affectedScope.zones.length} zones
          {state.severity.affectedScope.occupantsEstimate !== null
            ? ` · ~${state.severity.affectedScope.occupantsEstimate} occupants`
            : ''}
        </CockpitStatusPill>
      )}
      {state.severity.healthScore !== null && (
        <CockpitStatusPill>
          Health: {state.severity.healthScore}% · {state.severity.healthState ?? 'stable'} · {state.severity.healthTrend ?? 'flat'}
        </CockpitStatusPill>
      )}
      {state.severity.assetClass && state.severity.criticality && (
        <CockpitStatusPill>
          Asset: {formatLabel(state.severity.assetClass)} · {formatLabel(state.severity.criticality)}
        </CockpitStatusPill>
      )}
    </div>
  )
}

export function CockpitView({ state, renderMode, spatialCanvas }: CockpitViewProps) {
  const rootRef = useRef<HTMLElement | null>(null)
  const voiceRef = useRef<HTMLDivElement | null>(null)
  const twinRef = useRef<HTMLDivElement | null>(null)
  const decisionRef = useRef<HTMLElement | null>(null)
  const statusRef = useRef<HTMLDivElement | null>(null)
  const metricValueRef = useRef<HTMLDivElement | null>(null)
  const badgeRef = useRef<HTMLElement | null>(null)
  const decisionRowsRef = useRef<HTMLElement | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const voice = useMemo(() => buildVoice(state), [state])
  const emphasisTone = toneClass(state.primaryMetric.tone)
  const isWall = renderMode === 'wall'

  useEntranceAnimation(rootRef, voiceRef, twinRef, decisionRef, statusRef)
  useRefreshAnimation(voiceRef, decisionRef, state, voice)
  useToneTransition(metricValueRef, badgeRef, state.primaryMetric.tone)
  useAmbientDrift(twinRef, state.primaryMetric.tone)
  useUrgencyPulse(metricValueRef, state.primaryMetric.tone)
  useDecisionRowEntrance(decisionRowsRef, true)

  const handleFullscreen = () => {
    const elem = rootRef.current
    if (!elem) return

    if (!isFullscreen) {
      if (elem.requestFullscreen) {
        elem.requestFullscreen().catch(() => setIsFullscreen(true))
      } else {
        setIsFullscreen(true)
      }
      setIsFullscreen(true)
    } else {
      if (document.fullscreenElement) {
        document.exitFullscreen()
      }
      setIsFullscreen(false)
    }
  }

  return (
    <section
      ref={rootRef}
      className={`rounded-[28px] border border-slate-800/80 bg-slate-950/95 p-4 md:p-6 ${
        isFullscreen ? 'fixed inset-0 z-50 rounded-none' : ''
      }`}
      data-render-mode={renderMode}
      data-site-id={state.site.id}
    >
      <CockpitHero
        voiceRef={voiceRef}
        metricValueRef={metricValueRef}
        voice={voice}
        state={state}
        isWall={isWall}
        emphasisTone={emphasisTone}
        onFullscreenClick={handleFullscreen}
        isFullscreen={isFullscreen}
      />

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div ref={twinRef} className="min-h-[460px]">
          {spatialCanvas}
        </div>
        <CockpitDecisionPanel
          decisionRef={decisionRef}
          badgeRef={badgeRef}
          decisionRowsRef={decisionRowsRef}
          state={state}
          emphasisTone={emphasisTone}
        />
      </div>

      <CockpitStatusBar statusRef={statusRef} state={state} />
    </section>
  )
}

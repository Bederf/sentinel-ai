import { useLayoutEffect, useMemo, useRef, type ReactNode } from 'react'
import gsap from 'gsap'
import type { CockpitRenderMode, CockpitState } from './types'

interface CockpitViewProps {
  state: CockpitState
  renderMode: CockpitRenderMode
  spatialCanvas: ReactNode
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
    <div className="border-t border-slate-800 py-3 first:border-t-0 first:pt-0">
      <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">{label}</div>
      <div className={`mt-2 text-sm leading-relaxed ${emphasis ? 'font-medium text-white' : 'text-slate-300'}`}>
        {value}
      </div>
    </div>
  )
}

export function CockpitView({
  state,
  renderMode,
  spatialCanvas,
}: CockpitViewProps) {
  const rootRef = useRef<HTMLElement | null>(null)
  const voiceRef = useRef<HTMLDivElement | null>(null)
  const twinRef = useRef<HTMLDivElement | null>(null)
  const decisionRef = useRef<HTMLElement | null>(null)
  const statusRef = useRef<HTMLDivElement | null>(null)

  const voice = useMemo(() => buildVoice(state), [state])
  const emphasisTone = toneClass(state.primaryMetric.tone)
  const isWall = renderMode === 'wall'

  useLayoutEffect(() => {
    if (!rootRef.current) return

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
  }, [])

  useLayoutEffect(() => {
    if (!voiceRef.current || !decisionRef.current) return

    const timeline = gsap.timeline({ defaults: { duration: 0.42, ease: 'power2.out' } })
    timeline
      .fromTo(voiceRef.current, { y: 10, autoAlpha: 0.88 }, { y: 0, autoAlpha: 1, clearProps: 'transform,opacity' })
      .fromTo(decisionRef.current, { y: 10, autoAlpha: 0.92 }, { y: 0, autoAlpha: 1, clearProps: 'transform,opacity' }, '-=0.24')

    return () => {
      timeline.kill()
    }
  }, [voice.headline, state.decision.summary, state.primaryMetric.value, state.site.mode])

  return (
    <section
      ref={rootRef}
      className="rounded-[28px] border border-slate-800/80 bg-slate-950/95 p-4 md:p-6"
      data-render-mode={renderMode}
      data-site-id={state.site.id}
    >
      <div
        ref={voiceRef}
        className="border-b border-slate-800/80 pb-5"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">
            Sentinel Cockpit
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.22em] text-slate-400">
            <span>{state.site.name}</span>
            <span className="text-slate-600">/</span>
            <span>{state.site.mode}</span>
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
            <div className={`mt-2 text-3xl font-semibold ${emphasisTone}`}>
              {state.primaryMetric.value}
            </div>
            <div className="mt-1 text-sm text-slate-400">{state.primaryMetric.detail}</div>
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div ref={twinRef} className="min-h-[460px]">
          {spatialCanvas}
        </div>

        <aside
          ref={decisionRef}
          className="rounded-[24px] border border-slate-800/80 bg-slate-900/70 px-5 py-5"
        >
          <div className="mb-5 flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Decision</div>
              <div className="mt-1 text-sm text-slate-300">{state.site.posture}</div>
            </div>
            <div className={`rounded-full border border-slate-800 px-3 py-1 text-[11px] uppercase tracking-[0.18em] ${emphasisTone}`}>
              {state.site.mode}
            </div>
          </div>

          <SectionRow label="Cause" value={state.activeCondition.summary} emphasis />
          <SectionRow label="Impact" value={state.decision.impact} />
          <SectionRow label="Time" value={`${state.primaryMetric.value} · ${state.primaryMetric.label}`} emphasis />
          <SectionRow label="Action" value={state.decision.summary} emphasis />
          <SectionRow label="Trade-Off" value={state.decision.tradeoff} />
          <SectionRow label="Confidence" value={state.decision.confidence} />

          {state.site.mode === 'advisory' && (
            <details className="mt-4 rounded-2xl border border-slate-800/80 bg-slate-950/40 px-4 py-3">
              <summary className="cursor-pointer list-none text-[11px] uppercase tracking-[0.22em] text-slate-400">
                Show control path
              </summary>
              <div className="mt-3 space-y-3">
                {state.decision.navigationPath.length > 0 && (
                  <SectionRow
                    label="BMS Path"
                    value={state.decision.navigationPath.join(' → ')}
                  />
                )}
                <SectionRow label="Command" value={state.decision.command} />
                <SectionRow label="Operator Prompt" value={state.decision.operatorPrompt} />
              </div>
            </details>
          )}

          {state.site.mode === 'supervised' && (
            <div className="mt-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-4 text-sm font-semibold text-amber-200">
              Hold to confirm before SENTINEL executes the control path.
            </div>
          )}

          {state.site.mode === 'autonomous' && (
            <div className="mt-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-4 text-sm text-emerald-100">
              <div className="font-semibold">Executed + verifying</div>
              <div className="mt-2 text-emerald-200/90">{state.decision.verification}</div>
            </div>
          )}
        </aside>
      </div>

      <div
        ref={statusRef}
        className="mt-5 flex flex-wrap items-center gap-2 border-t border-slate-800/80 pt-4 text-xs text-slate-400"
      >
        <span className="rounded-full border border-slate-800 px-3 py-1">
          {state.site.dataFreshnessLabel}
        </span>
        <span className="rounded-full border border-slate-800 px-3 py-1">
          Mode: {state.site.mode}
        </span>
        <span className="rounded-full border border-slate-800 px-3 py-1">
          Confidence: {state.decision.confidence}
        </span>
        <span className="rounded-full border border-slate-800 px-3 py-1">
          Risk band: {state.severity.riskBand ?? 'low'}
        </span>
        {state.severity.thresholdReason && (
          <span className="rounded-full border border-slate-800 px-3 py-1">
            {state.severity.thresholdReason}
          </span>
        )}
      </div>
    </section>
  )
}

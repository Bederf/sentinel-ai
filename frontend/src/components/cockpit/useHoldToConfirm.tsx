/* eslint-disable react-refresh/only-export-components */
import { useCallback, useRef } from 'react'
import gsap from 'gsap'

const HOLD_DURATIONS: Record<'advisory' | 'supervised', number> = {
  advisory: 1.4,
  supervised: 2.2,
}

export function useHoldToConfirm(
  progressRef: React.RefObject<HTMLElement | null>,
  onConfirm: () => void,
  mode: 'advisory' | 'supervised' = 'advisory',
) {
  const tlRef = useRef<gsap.core.Timeline | null>(null)
  const confirmedRef = useRef(false)

  const onPressStart = useCallback(() => {
    const el = progressRef.current
    if (!el) return
    confirmedRef.current = false

    // Kill any previous timeline and reset position
    tlRef.current?.kill()
    gsap.set(el, { scaleX: 0, backgroundColor: 'var(--color-sentinel-amber)', transformOrigin: 'left center' })

    const duration = HOLD_DURATIONS[mode]

    tlRef.current = gsap.timeline()

    // Phase 1: linear fill across full duration
    tlRef.current.to(el, {
      scaleX: 1,
      duration,
      ease: 'none',
      transformOrigin: 'left center',
    })

    // Phase 2: color shift to orange at 50% progress
    tlRef.current.to(
      el,
      { backgroundColor: 'var(--color-sentinel-amber)', duration: duration * 0.3, ease: 'none' },
      duration * 0.35, // start slightly before 50%
    )

    // Phase 3: on complete — red flash → green → confirm
    tlRef.current.call(() => {
      if (!progressRef.current) return
      gsap.timeline()
        .to(progressRef.current, { backgroundColor: 'var(--color-sentinel-red)', duration: 0.12, ease: 'none' })
        .to(progressRef.current, { backgroundColor: 'var(--color-sentinel-green)', duration: 0.2, ease: 'power1.out' })
        .call(() => {
          confirmedRef.current = true
          onConfirm()
        })
    })
  }, [progressRef, onConfirm, mode])

  const onPressEnd = useCallback(() => {
    if (confirmedRef.current) return // already confirmed — don't cancel
    tlRef.current?.kill()

    // Snap back — decisive cancel with physical feel
    if (progressRef.current) {
      gsap.to(progressRef.current, {
        scaleX: 0,
        backgroundColor: 'var(--color-sentinel-amber)', // reset to amber
        duration: 0.32,
        ease: 'back.out(1.4)',
        transformOrigin: 'left center',
      })
    }
  }, [progressRef])

  return { onPressStart, onPressEnd }
}

interface SupervisedConfirmBarProps {
  onConfirm: () => void
  mode?: 'advisory' | 'supervised'
}

export function SupervisedConfirmBar({ onConfirm, mode = 'advisory' }: SupervisedConfirmBarProps) {
  const progressRef = useRef<HTMLDivElement | null>(null)
  const { onPressStart, onPressEnd } = useHoldToConfirm(progressRef, onConfirm, mode)

  const label = mode === 'supervised'
    ? 'Hold to approve SENTINEL action'
    : 'Hold to confirm'

  const borderColor = mode === 'supervised'
    ? 'border-amber-500/40'
    : 'border-amber-500/30'

  const bgColor = mode === 'supervised'
    ? 'bg-amber-500/15'
    : 'bg-amber-500/10'

  return (
    <div
      className={`mt-4 cursor-pointer select-none rounded-md border ${borderColor} ${bgColor} px-4 py-4`}
      onPointerDown={onPressStart}
      onPointerUp={onPressEnd}
      onPointerLeave={onPressEnd}
      role="button"
      aria-label={label}
    >
      <div className="text-sm font-semibold text-amber-200">{label}</div>
      {mode === 'supervised' && (
        <div className="mt-1 text-[11px] text-amber-400/70">
          {HOLD_DURATIONS.supervised}s hold — SENTINEL will execute on release
        </div>
      )}
      <div className="mt-3 h-[3px] overflow-hidden rounded-full bg-amber-500/20">
        <div
          ref={progressRef}
          className="h-full rounded-full"
          // GSAP owns fill color — no Tailwind bg class here
          style={{ transform: 'scaleX(0)', transformOrigin: 'left center', backgroundColor: 'var(--color-sentinel-amber)' }}
        />
      </div>
    </div>
  )
}

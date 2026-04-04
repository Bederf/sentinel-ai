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

    tlRef.current?.kill()

    const totalDuration = HOLD_DURATIONS[mode]
    const halfDuration = totalDuration / 2

    gsap.set(el, { scaleX: 0, transformOrigin: 'left center' })

    const tl = gsap.timeline()

    // Fill from 0 → 1 over full duration
    tl.to(el, {
      scaleX: 1,
      duration: totalDuration,
      ease: 'none',
    })

    // At 50%: transition fill color to orange
    tl.to(el, { backgroundColor: '#f97316', duration: halfDuration, ease: 'none' }, 0)

    // At onComplete: red flash → green → call onConfirm
    tl.call(() => {
      gsap.set(el, { backgroundColor: '#ef4444' })
    })
    tl.call(() => {
      gsap.delayedCall(0.12, () => {
        gsap.set(el, { backgroundColor: '#10b981' })
      })
    })
    tl.call(() => {
      confirmedRef.current = true
      onConfirm()
    })

    tlRef.current = tl
  }, [mode, onConfirm, progressRef])

  const onPressEnd = useCallback(() => {
    if (confirmedRef.current) return
    tlRef.current?.kill()

    const el = progressRef.current
    if (el) {
      gsap.to(el, {
        scaleX: 0,
        duration: 0.32,
        ease: 'back.out(1.4)',
        transformOrigin: 'left center',
      })
    }
  }, [progressRef])

  return { onPressStart, onPressEnd }
}

// SupervisedConfirmBar — drop-in replacement for the plain text supervised bar in CockpitView.tsx
// Usage: <SupervisedConfirmBar onConfirm={handleConfirm} mode="supervised" />

interface SupervisedConfirmBarProps {
  onConfirm: () => void
  mode: 'advisory' | 'supervised'
}

export function SupervisedConfirmBar({ onConfirm, mode }: SupervisedConfirmBarProps) {
  const progressRef = useRef<HTMLDivElement | null>(null)
  const { onPressStart, onPressEnd } = useHoldToConfirm(progressRef, onConfirm, mode)

  const ariaLabel = mode === 'supervised'
    ? 'Hold to approve SENTINEL action'
    : 'Hold to confirm'

  return (
    <div
      className="mt-4 cursor-pointer select-none rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-4"
      onPointerDown={onPressStart}
      onPointerUp={onPressEnd}
      onPointerLeave={onPressEnd}
      role="button"
      aria-label={ariaLabel}
    >
      <div className="text-sm font-semibold text-amber-200">Hold to confirm</div>
      <div className="mt-3 h-[3px] overflow-hidden rounded-full bg-amber-500/20">
        <div
          ref={progressRef}
          className="h-full rounded-full"
          style={{ transform: 'scaleX(0)', transformOrigin: 'left center', backgroundColor: '#f59e0b' }}
        />
      </div>
    </div>
  )
}

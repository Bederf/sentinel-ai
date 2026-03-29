/* eslint-disable react-refresh/only-export-components */
import { useRef, useCallback } from 'react'
import gsap from 'gsap'

const HOLD_DURATION_S = 1.8  // seconds — long enough to be deliberate

export function useHoldToConfirm(
  progressRef: React.RefObject<HTMLElement | null>,
  onConfirm: () => void,
) {
  const tweenRef = useRef<gsap.core.Tween | null>(null)
  const confirmedRef = useRef(false)

  const onPressStart = useCallback(() => {
    if (!progressRef.current) return
    confirmedRef.current = false

    // Linear fill — operator senses real time passing uniformly
    tweenRef.current = gsap.to(progressRef.current, {
      scaleX: 1,
      duration: HOLD_DURATION_S,
      ease: 'none',
      transformOrigin: 'left center',
      onComplete: () => {
        confirmedRef.current = true
        onConfirm()
      },
    })
  }, [progressRef, onConfirm])

  const onPressEnd = useCallback(() => {
    if (confirmedRef.current) return  // already confirmed — don't cancel
    tweenRef.current?.kill()

    // Snap back — release is decisive, cancels clearly
    if (progressRef.current) {
      gsap.to(progressRef.current, {
        scaleX: 0,
        duration: 0.22,
        ease: 'power2.in',
        transformOrigin: 'left center',
      })
    }
  }, [progressRef])

  return { onPressStart, onPressEnd }
}

// SupervisedConfirmBar — drop-in replacement for the plain text supervised bar in CockpitView.tsx
// Usage: <SupervisedConfirmBar onConfirm={handleConfirm} />

interface SupervisedConfirmBarProps {
  onConfirm: () => void
}

export function SupervisedConfirmBar({ onConfirm }: SupervisedConfirmBarProps) {
  const progressRef = useRef<HTMLDivElement | null>(null)
  const { onPressStart, onPressEnd } = useHoldToConfirm(progressRef, onConfirm)

  return (
    <div
      className="mt-4 cursor-pointer select-none rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-4"
      onPointerDown={onPressStart}
      onPointerUp={onPressEnd}
      onPointerLeave={onPressEnd}
      role="button"
      aria-label="Hold to confirm SENTINEL execution"
    >
      <div className="text-sm font-semibold text-amber-200">Hold to confirm</div>
      <div className="mt-3 h-[3px] overflow-hidden rounded-full bg-amber-500/20">
        <div
          ref={progressRef}
          className="h-full rounded-full bg-amber-400"
          style={{ transform: 'scaleX(0)', transformOrigin: 'left center' }}
        />
      </div>
    </div>
  )
}

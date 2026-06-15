/* eslint-disable react-refresh/only-export-components */
import { useCallback, useEffect, useRef, useState } from 'react'
import gsap from 'gsap'

const HOLD_DURATIONS: Record<'advisory' | 'supervised', number> = {
  advisory: 1.4,
  supervised: 2.2,
}

export function useHoldToConfirm(
  progressRef: React.RefObject<HTMLElement | null>,
  onConfirm: () => void | Promise<void>,
  mode: 'advisory' | 'supervised' = 'advisory',
) {
  const tlRef = useRef<gsap.core.Timeline | null>(null)
  const feedbackTlRef = useRef<gsap.core.Timeline | null>(null)
  const confirmedRef = useRef(false)
  const confirmingRef = useRef(false)
  const mountedRef = useRef(true)
  const [isHolding, setIsHolding] = useState(false)
  const [isConfirming, setIsConfirming] = useState(false)

  const resetProgress = useCallback((duration = 0.24) => {
    const el = progressRef.current
    if (!el) return

    gsap.killTweensOf(el)
    gsap.to(el, {
      scaleX: 0,
      backgroundColor: 'var(--color-sentinel-amber)',
      duration,
      ease: 'power1.out',
      transformOrigin: 'left center',
    })
  }, [progressRef])

  useEffect(() => {
    mountedRef.current = true
    const el = progressRef.current
    return () => {
      mountedRef.current = false
      tlRef.current?.kill()
      feedbackTlRef.current?.kill()
      if (el) gsap.killTweensOf(el)
    }
  }, [progressRef])

  const onPressStart = useCallback(() => {
    const el = progressRef.current
    if (!el || confirmingRef.current) return
    confirmedRef.current = false
    setIsHolding(true)

    // Kill any previous timeline and reset position
    tlRef.current?.kill()
    feedbackTlRef.current?.kill()
    gsap.killTweensOf(el)
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

    // Phase 3: on complete — red flash → green → confirm → reset
    tlRef.current.call(() => {
      const target = progressRef.current
      if (!target || confirmingRef.current) return

      confirmedRef.current = true
      confirmingRef.current = true
      setIsHolding(false)
      setIsConfirming(true)

      feedbackTlRef.current?.kill()
      feedbackTlRef.current = gsap.timeline()
        .to(target, { backgroundColor: 'var(--color-sentinel-red)', duration: 0.12, ease: 'none' })
        .to(target, { backgroundColor: 'var(--color-sentinel-green)', duration: 0.2, ease: 'power1.out' })
        .call(() => {
          Promise.resolve(onConfirm())
            .catch(() => {
              // The caller owns error reporting; keep the hold control reusable.
            })
            .finally(() => {
              if (!mountedRef.current) return
              confirmingRef.current = false
              confirmedRef.current = false
              setIsConfirming(false)
              resetProgress()
            })
        })
    })
  }, [progressRef, onConfirm, mode, resetProgress])

  const onPressEnd = useCallback(() => {
    setIsHolding(false)
    if (confirmedRef.current || confirmingRef.current) return // already confirmed — don't cancel
    tlRef.current?.kill()
    tlRef.current = null

    // Snap back — decisive cancel with physical feel
    resetProgress(0.32)
  }, [resetProgress])

  return { onPressStart, onPressEnd, isHolding, isConfirming }
}

interface SupervisedConfirmBarProps {
  onConfirm: () => void | Promise<void>
  mode?: 'advisory' | 'supervised'
}

export function SupervisedConfirmBar({ onConfirm, mode = 'advisory' }: SupervisedConfirmBarProps) {
  const progressRef = useRef<HTMLDivElement | null>(null)
  const { onPressStart, onPressEnd, isHolding, isConfirming } = useHoldToConfirm(progressRef, onConfirm, mode)

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
      className={`mt-4 select-none rounded-md border ${borderColor} ${bgColor} px-4 py-4 ${isConfirming ? 'cursor-wait opacity-80' : 'cursor-pointer'}`}
      onPointerDown={(event) => {
        if (isConfirming) return
        event.currentTarget.setPointerCapture?.(event.pointerId)
        onPressStart()
      }}
      onPointerUp={(event) => {
        if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
          event.currentTarget.releasePointerCapture(event.pointerId)
        }
        onPressEnd()
      }}
      onPointerCancel={onPressEnd}
      onLostPointerCapture={onPressEnd}
      role="button"
      aria-label={label}
      aria-busy={isConfirming}
      aria-disabled={isConfirming}
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.repeat) return
        if (event.key === ' ' || event.key === 'Enter') {
          event.preventDefault()
          onPressStart()
        }
      }}
      onKeyUp={(event) => {
        if (event.key === ' ' || event.key === 'Enter') {
          event.preventDefault()
          onPressEnd()
        }
      }}
    >
      <div className="text-sm font-semibold text-amber-200">
        {isConfirming ? 'Approving SENTINEL action...' : isHolding ? 'Keep holding...' : label}
      </div>
      {mode === 'supervised' && (
        <div className="mt-1 text-[11px] text-amber-400/70">
          {HOLD_DURATIONS.supervised}s hold — SENTINEL will execute after hold completes
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

import { useLayoutEffect, useRef } from 'react'
import gsap from 'gsap'
import type { CockpitState } from './types'
import { TONE_COLORS, motionReduced } from './motionPreference'

export function useToneTransition(
  metricRef: React.RefObject<HTMLElement | null>,
  badgeRef: React.RefObject<HTMLElement | null>,
  tone: CockpitState['primaryMetric']['tone'],
) {
  const prevTone = useRef(tone)

  useLayoutEffect(() => {
    if (prevTone.current === tone) return
    prevTone.current = tone

    const color = TONE_COLORS[tone] ?? TONE_COLORS.normal
    const isEscalating = tone === 'warning' || tone === 'elevated' || tone === 'critical'

    // Kill any in-flight tweens on both targets before starting — prevents bleed-through
    // on rapid state changes (e.g. warning → critical within a single poll cycle)
    if (metricRef.current) gsap.killTweensOf(metricRef.current)
    if (badgeRef.current) gsap.killTweensOf(badgeRef.current)

    const targets = [metricRef.current, badgeRef.current].filter(Boolean)
    if (!targets.length) return

    if (motionReduced()) {
      gsap.set(targets, { color })
      return
    }

    const tl = gsap.timeline()

    // Color transition on both refs
    tl.to(targets, {
      color,
      duration: isEscalating ? 0.28 : 0.48,
      ease: isEscalating ? 'power2.in' : 'power1.out',
    })

    // Scale pulse on metricRef only — escalation adds physical weight
    if (isEscalating && metricRef.current) {
      tl.to(
        metricRef.current,
        {
          scaleX: 1.04,
          scaleY: 1.04,
          duration: 0.19,
          ease: 'power2.out',
        },
        0, // run in parallel with color tween
      ).to(
        metricRef.current,
        {
          scaleX: 1,
          scaleY: 1,
          duration: 0.19,
          ease: 'back.out(1.7)',
        },
      )
    }
  }, [tone, metricRef, badgeRef])
}

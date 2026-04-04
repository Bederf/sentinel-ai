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

    if (!metricRef.current && !badgeRef.current) return

    if (motionReduced()) {
      if (metricRef.current) gsap.set(metricRef.current, { color })
      if (badgeRef.current) gsap.set(badgeRef.current, { color })
      return
    }

    // Kill previous tweens to prevent bleed-through on rapid state changes
    if (metricRef.current) gsap.killTweensOf(metricRef.current)
    if (badgeRef.current) gsap.killTweensOf(badgeRef.current)

    const tl = gsap.timeline()

    if (isEscalating && metricRef.current) {
      // Scale pulse gives physical weight to escalation — scale 1 → 1.04 → 1
      tl.to(metricRef.current, { scale: 1.04, duration: 0.38, ease: 'back.out(1.7)' }, 0)
      tl.to(metricRef.current, { scale: 1, duration: 0.38, ease: 'back.out(1.7)' }, 0.38)
    }

    // Color transition runs in parallel with scale pulse
    tl.to(
      [metricRef.current, badgeRef.current].filter(Boolean),
      { color, duration: isEscalating ? 0.28 : 0.48, ease: isEscalating ? 'power2.in' : 'power1.out' },
      0,
    )
  }, [tone, metricRef, badgeRef])
}

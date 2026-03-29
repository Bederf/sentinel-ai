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

    const targets = [metricRef.current, badgeRef.current].filter(Boolean)
    if (!targets.length) return

    if (motionReduced()) {
      gsap.set(targets, { color })
      return
    }

    gsap.to(targets, {
      color,
      duration: isEscalating ? 0.28 : 0.48,
      ease: isEscalating ? 'power2.in' : 'power1.out',
    })
  }, [tone, metricRef, badgeRef])
}

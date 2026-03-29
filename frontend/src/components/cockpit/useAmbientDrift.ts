import { useLayoutEffect, useRef } from 'react'
import gsap from 'gsap'
import type { CockpitState } from './types'
import { motionReduced } from './motionPreference'

export function useAmbientDrift(
  twinRef: React.RefObject<HTMLElement | null>,
  tone: CockpitState['primaryMetric']['tone'],
) {
  const tweenRef = useRef<gsap.core.Tween | null>(null)

  useLayoutEffect(() => {
    if (!twinRef.current) return

    tweenRef.current?.kill()
    gsap.set(twinRef.current, { y: 0 })

    // Drift only in warning/elevated — never in stable or critical
    if (tone !== 'warning' && tone !== 'elevated') return

    // Reduced motion: no ambient animation
    if (motionReduced()) return

    const amplitude = tone === 'elevated' ? 5 : 3   // px
    const duration  = tone === 'elevated' ? 4 : 6   // seconds per half-cycle

    const el = twinRef.current
    tweenRef.current = gsap.to(el, {
      y: amplitude,
      duration,
      ease: 'sine.inOut',
      yoyo: true,
      repeat: -1,
    })

    return () => {
      tweenRef.current?.kill()
      gsap.set(el, { y: 0 })
    }
  }, [tone, twinRef])
}

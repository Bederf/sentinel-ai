import { useLayoutEffect, useRef } from 'react'
import gsap from 'gsap'
import type { CockpitState } from './types'
import { motionReduced } from './motionPreference'

export function useUrgencyPulse(
  metricValueRef: React.RefObject<HTMLElement | null>,
  tone: CockpitState['primaryMetric']['tone'],
) {
  const tweenRef = useRef<gsap.core.Tween | null>(null)

  useLayoutEffect(() => {
    if (!metricValueRef.current) return

    tweenRef.current?.kill()
    gsap.set(metricValueRef.current, { opacity: 1 })

    if (tone !== 'critical') return

    // Reduced motion: color signals critical, no pulse
    if (motionReduced()) return

    const el = metricValueRef.current
    tweenRef.current = gsap.to(el, {
      opacity: 0.55,
      duration: 0.6,
      ease: 'sine.inOut',
      yoyo: true,
      repeat: -1,
    })

    return () => {
      tweenRef.current?.kill()
      gsap.set(el, { opacity: 1 })
    }
  }, [tone, metricValueRef])
}

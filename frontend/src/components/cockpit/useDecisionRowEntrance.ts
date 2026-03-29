import { useLayoutEffect } from 'react'
import gsap from 'gsap'
import { motionReduced } from './motionPreference'

export function useDecisionRowEntrance(
  rowsRef: React.RefObject<HTMLElement | null>,
  isReady: boolean,
) {
  useLayoutEffect(() => {
    if (!isReady || !rowsRef.current) return

    const rows = rowsRef.current.querySelectorAll('[data-decision-row]')
    if (!rows.length) return

    if (motionReduced()) {
      gsap.set(rows, { autoAlpha: 1, x: 0 })
      return
    }

    gsap.fromTo(
      rows,
      { autoAlpha: 0, x: -8 },
      {
        autoAlpha: 1,
        x: 0,
        duration: 0.36,
        ease: 'power2.out',
        stagger: 0.055,
        clearProps: 'transform,opacity',
      },
    )
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isReady])  // intentionally omit rowsRef — stable ref, fire only when isReady changes
}

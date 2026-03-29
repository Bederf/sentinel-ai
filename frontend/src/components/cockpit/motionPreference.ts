// Reduced motion utility — used by all GSAP animation hooks
// Pattern: check at animation callsite, not at component level

/**
 * Returns true when the user has requested reduced motion.
 * Every GSAP hook must call this before animating.
 * When true: set final state immediately via gsap.set(), skip tweens.
 */
export function motionReduced(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * Canonical tone → hex color map.
 * Used by useToneTransition to animate color changes.
 * Values match Tailwind palette: sky-400, amber-400, orange-400, red-400.
 */
export const TONE_COLORS = {
  normal:   '#38bdf8',  // sky-400   — stable / calm
  warning:  '#fbbf24',  // amber-400 — drift / approaching
  elevated: '#fb923c',  // orange-400 — needs action
  critical: '#f87171',  // red-400   — breach imminent
} as const

export type ToneColor = keyof typeof TONE_COLORS

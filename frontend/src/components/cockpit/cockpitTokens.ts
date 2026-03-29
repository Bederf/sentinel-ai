// SENTINEL Cockpit Design System v1.0 — token constants
// Source: session 2026-03-29 design system + motion spec

export const cockpitTokens = {
  surface: {
    base:   'bg-slate-950',
    panel:  'bg-slate-900/70',
    raised: 'bg-slate-900/60',
  },
  border: {
    default: 'border-slate-800/80',
    strong:  'border-slate-800',
  },
  text: {
    primary:   'text-white',
    secondary: 'text-slate-300',
    tertiary:  'text-slate-500',
    label:     'text-[11px] uppercase tracking-[0.22em] text-slate-500',
  },
  accent: {
    stable:   'text-sky-400',
    warning:  'text-amber-400',
    elevated: 'text-orange-400',
    critical: 'text-red-400',
    exec:     'text-emerald-400',
  },
  radius: {
    panel:   'rounded-[24px]',
    cockpit: 'rounded-[28px]',
    pill:    'rounded-full',
    card:    'rounded-2xl',
  },
} as const

export type CockpitTokens = typeof cockpitTokens

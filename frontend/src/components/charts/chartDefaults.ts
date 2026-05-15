import type { CSSProperties } from 'react'

export const chartColors = {
  amber: 'var(--color-sentinel-amber)',
  green: 'var(--color-sentinel-green)',
  red: 'var(--color-sentinel-red)',
  blue: 'var(--color-sentinel-blue)',
  cyan: 'var(--color-sentinel-cyan)',
  purple: 'var(--color-sentinel-purple)',
}

export const gridProps = {
  stroke: 'var(--color-sentinel-border)',
  strokeDasharray: '2 4' as const,
}

export const axisProps = {
  stroke: 'var(--color-sentinel-text-secondary)',
  tick: { fontSize: 11 },
}

export const tooltipContentStyle: CSSProperties = {
  background: 'var(--color-sentinel-bg-panel)',
  border: '1px solid var(--color-sentinel-border)',
  borderRadius: 6,
  fontSize: 12,
}

import type { CockpitState } from './types'

export type CockpitTone = 'waiting' | 'stable' | 'warning' | 'critical'

export function cockpitToneKey(state: CockpitState): CockpitTone {
  if (state.site.renderState === 'waiting') return 'waiting'
  const load = Math.max(0, Math.min(1, state.visualTwin.consumptionIntensity ?? 0))
  if (load >= 0.78) return 'critical'
  if (load >= 0.5) return 'warning'
  if (state.primaryMetric.tone === 'critical') return 'critical'
  if (state.primaryMetric.tone === 'warning' || state.primaryMetric.tone === 'elevated') return 'warning'
  return 'stable'
}

/** Emissive + base tint for a floor slab in the 3D twin */
export function cockpitFloorPalette(
  tone: CockpitTone,
  intensity: number,
  isManaged: boolean,
  riskLevel: string,
  systemFilter?: string | null,
): { base: string; emissive: string; emissiveIntensity: number; edge: string } {
  // System colour override when a tab is active — applies the system colour to managed slabs
  // regardless of posture tone, making the building shift colour when the operator
  // changes tab (e.g. Energy tab → orange tint, Lighting tab → amber tint).
  const SYSTEM_EMISSIVE: Record<string, string> = {
    hvac:      '#22d3ee',
    energy:    '#fb923c',
    lighting:  '#fbbf24',
    water:     '#38bdf8',
    fire:      '#fb7185',
    security:  '#06b6d4',
    solar_bess:'#facc15',
  }
  const sysColor = systemFilter ? (SYSTEM_EMISSIVE[systemFilter] ?? null) : null

  // Host-building floors outside Sentinel scope: neutral shell only (no posture / load tint).
  if (!isManaged) {
    return {
      base: '#64748b',
      emissive: '#334155',
      emissiveIntensity: 0.2,
      edge: '#cbd5e1',
    }
  }

  const i = Math.max(0.12, Math.min(1, intensity))
  const managedBoost = 0.22

  // System tab active: use system colour for managed slabs
  if (sysColor) {
    return {
      base: sysColor,
      emissive: sysColor,
      emissiveIntensity: 0.14 + i * 0.32 + managedBoost,
      edge: sysColor,
    }
  }

  if (tone === 'critical') {
    return {
      base: `hsl(0, ${38 + i * 42}%, ${28 + i * 12}%)`,
      emissive: '#f87171',
      emissiveIntensity: 0.12 + i * 0.45 + managedBoost,
      edge: '#fca5a5',
    }
  }
  if (tone === 'warning') {
    return {
      base: `hsl(43, ${42 + i * 28}%, ${26 + i * 14}%)`,
      emissive: '#fbbf24',
      emissiveIntensity: 0.1 + i * 0.38 + managedBoost,
      edge: '#fde047',
    }
  }
  if (tone === 'waiting') {
    return {
      base: '#1e293b',
      emissive: '#64748b',
      emissiveIntensity: 0.04,
      edge: '#475569',
    }
  }

  const drift = riskLevel === 'drift' || riskLevel === 'approaching'
  return {
    base: `hsl(195, ${22 + i * 18}%, ${22 + i * 10}%)`,
    emissive: drift ? '#38bdf8' : '#22d3ee',
    emissiveIntensity: 0.06 + i * 0.28 + managedBoost,
    edge: '#22d3ee',
  }
}

export function cockpitFlowColor(tone: CockpitTone): string {
  if (tone === 'critical') return '#f87171'
  if (tone === 'warning') return '#fbbf24'
  return '#22d3ee'
}

/**
 * LightingHeatmapOverlay — luminaire brightness heatmap for the cockpit 3D twin.
 *
 * Renders a zone-by-zone luminosity overlay showing lighting levels by floor
 * when the Lighting system tab is active. Opacity/brightness per zone
 * reflects lighting_kw intensity relative to peak.
 *
 * Stub: enhanced with real DALI luminaire positioning in future phases.
 */

import { useMemo } from 'react'
import * as THREE from 'three'
import type { CockpitState } from '../types'

interface LightingHeatmapOverlayProps {
  state: CockpitState
  tone: 'cyan' | 'amber' | 'red'
}

const LIGHTING_COLOR = {
  cyan: '#fef08a',   // warm yellow for lighting
  amber: '#fef08a',
  red: '#fca5a5',
} as const

export function LightingHeatmapOverlay({ state }: LightingHeatmapOverlayProps) {
  const consumption = state.visualTwin.consumptionIntensity
  const lightingKw = state.visualTwin.energyCentre.lightingKw
  const color = LIGHTING_COLOR['cyan']

  // Create floor-by-floor lighting plane overlays
  const floorOverlays = useMemo(() => {
    const floors = state.visualTwin.floors
    if (floors.length === 0) return []

    return floors.slice(0, 5).map((floor, index) => ({
      id: floor.id,
      elevation: floor.elevation,
      opacity: consumption * 0.25,
      brightness: Math.min(1, consumption * 1.4),
    }))
  }, [state.visualTwin.floors, consumption])

  return (
    <group>
      {floorOverlays.map((overlay) => (
        <mesh
          key={overlay.id}
          position={[0, overlay.elevation + 0.15, 0]}
          rotation={[-Math.PI / 2, 0, 0]}
        >
          <planeGeometry args={[1.1, 0.85]} />
          <meshStandardMaterial
            color={color}
            emissive={color}
            emissiveIntensity={overlay.brightness * 0.3}
            transparent
            opacity={overlay.opacity}
            depthWrite={false}
            side={THREE.DoubleSide}
          />
        </mesh>
      ))}
    </group>
  )
}

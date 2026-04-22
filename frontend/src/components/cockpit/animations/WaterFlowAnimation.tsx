/**
 * WaterFlowOverlay — water distribution flow animation for the cockpit 3D twin.
 *
 * Renders animated water flow through the building when the Water system
 * tab is active. Shows risers and branch pipes with animated flow indicators.
 *
 * Stub: enhanced with real pipe geometry and valve positions in future phases.
 */

import { useFrame } from '@react-three/fiber'
import { useRef } from 'react'
import * as THREE from 'three'
import type { CockpitState } from '../types'

interface WaterFlowOverlayProps {
  state: CockpitState
  tone: 'cyan' | 'amber' | 'red'
}

const WATER_COLOR = {
  cyan: '#38bdf8',
  amber: '#7dd3fc',
  red: '#67e8f9',
} as const

export function WaterFlowOverlay({ state, tone }: WaterFlowOverlayProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const intensity = state.visualTwin.breathingIntensity
  const color = WATER_COLOR[tone] ?? WATER_COLOR.cyan

  useFrame(({ clock }) => {
    if (!meshRef.current) return
    const t = clock.getElapsedTime()
    const phase = (t * 0.2 * state.visualTwin.flowSpeed) % 1
    const mat = meshRef.current.material as THREE.MeshStandardMaterial
    mat.opacity = 0.06 + Math.sin(phase * Math.PI * 2) * 0.04 * intensity
  })

  const floors = state.visualTwin.floors
  const height = floors.length > 0
    ? floors.reduce((max, f) => Math.max(max, f.elevation + 0.5), 0)
    : 2.5

  return (
    <group position={[-0.3, 0, 0.4]}>
      {/* Vertical water riser */}
      <mesh ref={meshRef}>
        <cylinderGeometry args={[0.025, 0.025, height * 0.85, 8]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.5 * intensity}
          transparent
          opacity={0.12}
          depthWrite={false}
        />
      </mesh>

      {/* Branch pipes per floor */}
      {[0.2, 0.4, 0.6, 0.8].map((fraction, i) => (
        <mesh
          key={i}
          position={[0.2, height * fraction, 0]}
          rotation={[0, 0, Math.PI / 2]}
        >
          <cylinderGeometry args={[0.015, 0.015, 0.4, 6]} />
          <meshStandardMaterial
            color={color}
            emissive={color}
            emissiveIntensity={0.3 * intensity}
            transparent
            opacity={0.08}
            depthWrite={false}
          />
        </mesh>
      ))}
    </group>
  )
}

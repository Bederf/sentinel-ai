/**
 * HVACFlowOverlay — system-specific thermal flow animation for the cockpit 3D twin.
 *
 * Renders animated coolant/power flow paths through the building when the HVAC
 * system tab is active. Shows heat distribution from chiller (B1) up through
 * AHU zones to occupied floors.
 *
 * Stub: enhanced with real GSAP/Three.js pipe geometry in future phases.
 */

import { useFrame } from '@react-three/fiber'
import { useRef } from 'react'
import * as THREE from 'three'
import type { CockpitState } from '../types'

interface HVACFlowOverlayProps {
  state: CockpitState
  tone: 'cyan' | 'amber' | 'red'
  yRange: { minY: number; maxY: number } | null
}

const TONE_COLORS = {
  cyan: '#22d3ee',
  amber: '#fbbf24',
  red: '#f87171',
} as const

export function HVACFlowOverlay({ state, tone, yRange }: HVACFlowOverlayProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const intensity = state.visualTwin.breathingIntensity
  const color = TONE_COLORS[tone] ?? TONE_COLORS.cyan

  useFrame(({ clock }) => {
    if (!meshRef.current) return
    const t = clock.getElapsedTime()
    const phase = (t * 0.3 * state.visualTwin.flowSpeed) % 1
    const mat = meshRef.current.material as THREE.MeshStandardMaterial
    mat.opacity = 0.08 + Math.sin(phase * Math.PI * 2) * 0.06 * intensity
  })

  if (!yRange) return null

  // Vertical flow column — chiller (B1) → roof
  const height = yRange.maxY - yRange.minY

  return (
    <group position={[0.55, yRange.minY, 0.3]}>
      {/* Vertical supply duct */}
      <mesh ref={meshRef}>
        <cylinderGeometry args={[0.04, 0.04, height * 0.85, 8]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.6 * intensity}
          transparent
          opacity={0.15}
          depthWrite={false}
        />
      </mesh>

      {/* Supply headers at each managed floor */}
      {[0.25, 0.5, 0.75].map((fraction, i) => (
        <mesh
          key={i}
          position={[0, height * fraction, 0]}
          rotation={[0, 0, Math.PI / 2]}
        >
          <cylinderGeometry args={[0.025, 0.025, 0.6, 6]} />
          <meshStandardMaterial
            color={color}
            emissive={color}
            emissiveIntensity={0.4 * intensity}
            transparent
            opacity={0.1}
            depthWrite={false}
          />
        </mesh>
      ))}
    </group>
  )
}

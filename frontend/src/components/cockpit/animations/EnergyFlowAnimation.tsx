/**
 * EnergyFlowOverlay — power distribution flow animation for the cockpit 3D twin.
 *
 * Renders animated power flow paths from generator/BESS (B1) to distribution
 * panels on each floor when the Energy system tab is active.
 *
 * Stub: enhanced with real busway/panel geometry in future phases.
 */

import { useFrame } from '@react-three/fiber'
import { useRef } from 'react'
import * as THREE from 'three'
import type { CockpitState } from '../types'

interface EnergyFlowOverlayProps {
  state: CockpitState
  tone: 'cyan' | 'amber' | 'red'
  yRange: { minY: number; maxY: number } | null
}

const TONE_COLORS = {
  cyan: '#fbbf24',   // amber for power
  amber: '#fbbf24',
  red: '#ef4444',
} as const

export function EnergyFlowOverlay({ state, tone, yRange }: EnergyFlowOverlayProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const loadRatio = state.visualTwin.energyCentre.loadRatio
  const color = TONE_COLORS[tone] ?? TONE_COLORS.cyan

  useFrame(({ clock }) => {
    if (!meshRef.current) return
    const t = clock.getElapsedTime()
    const phase = (t * 0.25 * (1 + loadRatio)) % 1
    const mat = meshRef.current.material as THREE.MeshStandardMaterial
    mat.emissiveIntensity = 0.3 + Math.abs(Math.sin(phase * Math.PI * 2)) * 0.5 * loadRatio
  })

  if (!yRange) return null

  const height = yRange.maxY - yRange.minY
  const totalKw = state.visualTwin.energyCentre.totalKw

  return (
    <group position={[-0.5, yRange.minY, -0.2]}>
      {/* Main busbar — vertical trunk from B1 to roof */}
      <mesh ref={meshRef}>
        <boxGeometry args={[0.06, height * 0.9, 0.03]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.5}
          transparent
          opacity={0.2}
          depthWrite={false}
        />
      </mesh>

      {/* Floor takeoffs — horizontal distribution to each floor */}
      {[0.2, 0.4, 0.6, 0.8].map((fraction, i) => (
        <mesh
          key={i}
          position={[0.25, height * fraction, 0]}
          rotation={[0, 0, 0]}
        >
          <boxGeometry args={[0.5, 0.025, 0.025]} />
          <meshStandardMaterial
            color={color}
            emissive={color}
            emissiveIntensity={0.3 * loadRatio}
            transparent
            opacity={0.12}
            depthWrite={false}
          />
        </mesh>
      ))}

      {/* Power meter indicator */}
      <mesh position={[0.15, height * 0.5, 0.05]}>
        <sphereGeometry args={[0.04, 8, 8]} />
        <meshStandardMaterial
          color="#fbbf24"
          emissive="#fbbf24"
          emissiveIntensity={0.8 * loadRatio}
          transparent
          opacity={0.9}
          depthWrite={false}
        />
      </mesh>
    </group>
  )
}

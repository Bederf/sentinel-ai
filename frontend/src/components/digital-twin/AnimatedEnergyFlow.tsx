/**
 * AnimatedEnergyFlow — renders animated energy flow paths between equipment
 * in the Digital Twin 3D view.
 *
 * Each flow is a tube with particles moving along it, direction and speed
 * driven by the EnergyFlow data from the backend.
 */

import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import type { EnergyFlow } from '@/lib/api'
import { calculatePathPoints, getAnimationSpeed } from '@/utils/energyFlowPaths'

interface AnimatedEnergyFlowProps {
  flows: EnergyFlow[]
  equipmentPositions: Map<string, [number, number, number]>
  visible: boolean
}

const MAX_PARTICLES_PER_FLOW = 8
const TUBE_RADIUS = 0.04
const PARTICLE_RADIUS = 0.07

/** Single flow path with tube and animated particles. */
function FlowPath({
  flow,
  fromPos,
  toPos,
}: {
  flow: EnergyFlow
  fromPos: [number, number, number]
  toPos: [number, number, number]
}) {
  const particlesRef = useRef<THREE.InstancedMesh>(null)
  const speed = getAnimationSpeed(flow.power_kw)

  // Build curve and tube geometry once
  const { curve, tubeGeometry, midpoint } = useMemo(() => {
    const points = calculatePathPoints(fromPos, toPos)
    const c = new THREE.CatmullRomCurve3(points, false, 'catmullrom', 0.5)
    const geom = new THREE.TubeGeometry(c, 32, TUBE_RADIUS, 6, false)
    const mid = c.getPointAt(0.5)
    return { curve: c, tubeGeometry: geom, midpoint: mid }
  }, [fromPos, toPos])

  // Pre-build dummy matrix
  const tempMatrix = useMemo(() => new THREE.Matrix4(), [])

  // Animate particles along the curve
  useFrame(() => {
    if (!particlesRef.current) return
    const time = performance.now() * 0.001 * speed

    for (let i = 0; i < MAX_PARTICLES_PER_FLOW; i++) {
      let t = ((time * 0.15 + i / MAX_PARTICLES_PER_FLOW) % 1)
      // Reverse direction if needed
      if (flow.direction === 'reverse') t = 1 - t

      const point = curve.getPointAt(t)
      tempMatrix.makeTranslation(point.x, point.y, point.z)
      particlesRef.current.setMatrixAt(i, tempMatrix)
    }
    particlesRef.current.instanceMatrix.needsUpdate = true
  })

  const tubeColor = new THREE.Color(flow.color)
  // Particles slightly brighter
  const particleColor = new THREE.Color(flow.color).offsetHSL(0, 0, 0.2)

  const label = `${flow.power_kw} kW`
  const typeLabel = flow.flow_type.replace(/_/g, ' ')

  return (
    <group>
      {/* Tube path */}
      <mesh geometry={tubeGeometry}>
        <meshBasicMaterial
          color={tubeColor}
          transparent
          opacity={0.35}
          depthWrite={false}
        />
      </mesh>

      {/* Animated particles */}
      <instancedMesh
        ref={particlesRef}
        args={[undefined, undefined, MAX_PARTICLES_PER_FLOW]}
      >
        <sphereGeometry args={[PARTICLE_RADIUS, 6, 4]} />
        <meshBasicMaterial
          color={particleColor}
          transparent
          opacity={0.9}
        />
      </instancedMesh>

      {/* Label at midpoint */}
      <Html
        position={[midpoint.x, midpoint.y + 0.4, midpoint.z]}
        scale={0.25}
        distanceFactor={10}
      >
        <div
          className="px-2 py-1 text-xs whitespace-nowrap font-mono rounded"
          style={{
            pointerEvents: 'none',
            background: 'rgba(15, 23, 42, 0.85)',
            border: `1px solid ${flow.color}`,
            color: flow.color,
            textShadow: '0 1px 2px rgba(0,0,0,0.5)',
          }}
        >
          <div className="font-semibold">{label}</div>
          <div style={{ fontSize: '0.65rem', opacity: 0.8 }}>{typeLabel}</div>
        </div>
      </Html>
    </group>
  )
}

export function AnimatedEnergyFlow({
  flows,
  equipmentPositions,
  visible,
}: AnimatedEnergyFlowProps) {
  if (!visible || flows.length === 0) return null

  return (
    <group>
      {flows.map((flow, index) => {
        const fromPos = equipmentPositions.get(flow.from_equipment)
        const toPos = equipmentPositions.get(flow.to_equipment)

        // Skip flows where we cannot resolve both positions
        if (!fromPos || !toPos) return null

        return (
          <FlowPath
            key={`${flow.from_equipment}-${flow.to_equipment}-${flow.flow_type}-${index}`}
            flow={flow}
            fromPos={fromPos}
            toPos={toPos}
          />
        )
      })}
    </group>
  )
}

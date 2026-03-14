/**
 * PredictiveFaultOverlay — renders LSTM predictions as pulsing 3D overlays
 * on equipment positions in the Digital Twin view.
 *
 * Colors: critical (red, opacity 0.6), warning (amber, opacity 0.4)
 * Pulse animation follows EquipmentMarker.tsx pattern.
 */

import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import type { PredictiveFault } from '@/lib/api'

interface PredictiveFaultOverlayProps {
  predictions: PredictiveFault[]
  equipmentPositions: Map<string, [number, number, number]>
}

const SEVERITY_CONFIG = {
  critical: { color: 0xef4444, opacity: 0.6, radius: 0.7, labelBg: 'rgba(239, 68, 68, 0.85)' },
  warning: { color: 0xf59e0b, opacity: 0.4, radius: 0.5, labelBg: 'rgba(245, 158, 11, 0.85)' },
} as const

function PredictionSphere({
  prediction,
  position,
}: {
  prediction: PredictiveFault
  position: [number, number, number]
}) {
  const meshRef = useRef<THREE.Mesh>(null)
  const config = SEVERITY_CONFIG[prediction.severity] || SEVERITY_CONFIG.warning

  // Pulse animation: 1 + Math.sin(time * 4) * 0.3 (matches EquipmentMarker)
  useFrame(() => {
    if (!meshRef.current) return
    const time = performance.now() * 0.001
    const s = 1 + Math.sin(time * 4) * 0.3
    meshRef.current.scale.set(s, s, s)
    const mat = meshRef.current.material as THREE.MeshBasicMaterial
    mat.opacity = config.opacity * (0.6 + Math.sin(time * 4) * 0.4)
  })

  const confidencePct = Math.round(prediction.confidence * 100)
  const timeframeLabel = `${prediction.timeframe_days}d`

  return (
    <group position={position}>
      {/* Pulsing prediction sphere */}
      <mesh ref={meshRef}>
        <sphereGeometry args={[config.radius, 12, 8]} />
        <meshBasicMaterial
          color={config.color}
          transparent
          opacity={config.opacity}
          depthWrite={false}
        />
      </mesh>

      {/* Prediction label */}
      <Html position={[0, 1.0, 0]} scale={0.3} distanceFactor={8}>
        <div
          className="px-2 py-1 text-xs whitespace-nowrap font-mono rounded"
          style={{
            pointerEvents: 'none',
            background: config.labelBg,
            border: `1px solid ${prediction.severity === 'critical' ? 'rgba(239, 68, 68, 0.8)' : 'rgba(245, 158, 11, 0.8)'}`,
            color: '#ffffff',
            textShadow: '0 1px 2px rgba(0,0,0,0.5)',
          }}
        >
          <div className="font-semibold">{prediction.prediction_type.replace(/_/g, ' ')}</div>
          <div>{confidencePct}% | {timeframeLabel}</div>
        </div>
      </Html>
    </group>
  )
}

export function PredictiveFaultOverlay({ predictions, equipmentPositions }: PredictiveFaultOverlayProps) {
  if (predictions.length === 0) return null

  return (
    <group>
      {predictions.map((pred, index) => {
        const position = equipmentPositions.get(pred.equipment_id)
        if (!position) return null

        return (
          <PredictionSphere
            key={`${pred.equipment_id}-${pred.prediction_type}-${index}`}
            prediction={pred}
            position={position}
          />
        )
      })}
    </group>
  )
}

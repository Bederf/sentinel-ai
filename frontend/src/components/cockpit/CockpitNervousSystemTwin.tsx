import { useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, type ThreeEvent } from '@react-three/fiber'
import { Html, PerspectiveCamera } from '@react-three/drei'
import * as THREE from 'three'
import type { CockpitState, CockpitTwinFloor, CockpitTwinRiskLevel, CockpitTwinZoneSignal } from './types'

interface CockpitNervousSystemTwinProps {
  state: CockpitState
}

const FLOOR_WIDTH = 10.5
const FLOOR_DEPTH = 5.6
const FLOOR_HEIGHT = 0.58

function riskPalette(level: CockpitTwinRiskLevel) {
  if (level === 'critical') {
    return {
      base: '#7f1d1d',
      edge: '#ef4444',
      glow: '#f87171',
      text: 'text-red-300',
    }
  }
  if (level === 'approaching') {
    return {
      base: '#7c2d12',
      edge: '#f97316',
      glow: '#fb923c',
      text: 'text-orange-300',
    }
  }
  if (level === 'drift') {
    return {
      base: '#92400e',
      edge: '#fbbf24',
      glow: '#fde68a',
      text: 'text-amber-300',
    }
  }
  return {
    base: '#0f3b66',
    edge: '#38bdf8',
    glow: '#7dd3fc',
    text: 'text-sky-300',
  }
}

function buildSignalPosition(floor: CockpitTwinFloor | undefined, slot: number) {
  const laneX = -3.1 + (slot % 4) * 2.05
  const laneZ = slot % 2 === 0 ? -0.75 : 0.95
  return new THREE.Vector3(laneX, (floor?.elevation ?? 0) + FLOOR_HEIGHT * 0.95, laneZ)
}

function FloorMass({
  floor,
  isFocus,
  motionProfile,
}: {
  floor: CockpitTwinFloor
  isFocus: boolean
  motionProfile: CockpitState['visualTwin']['motionProfile']
}) {
  const coreRef = useMemo(() => new THREE.Color(riskPalette(floor.level).base), [floor.level])
  const edgeRef = useMemo(() => new THREE.Color(riskPalette(floor.level).glow), [floor.level])
  const meshRef = useRef<THREE.Mesh | null>(null)
  const spreadRef = useRef<THREE.Mesh | null>(null)

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const body = meshRef.current
    const spread = spreadRef.current
    const isStable = motionProfile === 'calm' || floor.level === 'stable'

    let pulse = 1
    let spreadX = 1
    let spreadZ = 1
    let spreadOpacity = 0
    let emissiveIntensity = isFocus ? 0.18 : 0.08

    if (!isStable) {
      const isCritical = floor.level === 'critical'
      const speed = isCritical ? 4.2 : 1.9
      const strength = isCritical ? 0.16 : 0.045
      const wave = Math.sin(t * speed)
      pulse = 1 + wave * floor.spread * strength
      spreadX = 1 + floor.spread * (isCritical ? 0.36 : 0.12)
      spreadZ = 1 + floor.spread * (isCritical ? 0.42 : 0.16)
      spreadOpacity = isCritical ? 0.18 + floor.spread * 0.34 : 0.05 + floor.spread * 0.08
      emissiveIntensity = isCritical
        ? 0.42 + floor.intensity * (isFocus ? 1.45 : 0.72)
        : 0.2 + floor.intensity * (isFocus ? 0.65 : 0.28)
    }

    if (body) {
      body.scale.set(1, pulse, 1)
      const material = body.material as THREE.MeshStandardMaterial
      material.emissive.copy(edgeRef)
      material.emissiveIntensity = emissiveIntensity
    }

    if (spread) {
      spread.scale.set(spreadX, 1, spreadZ)
      const material = spread.material as THREE.MeshBasicMaterial
      material.opacity = spreadOpacity
    }
  })

  return (
    <group position={[0, floor.elevation, 0]}>
      <mesh
        ref={(node) => {
          meshRef.current = node
        }}
      >
        <boxGeometry args={[FLOOR_WIDTH, FLOOR_HEIGHT, FLOOR_DEPTH]} />
        <meshStandardMaterial color={coreRef} metalness={0.18} roughness={0.32} />
      </mesh>

      <mesh
        ref={(node) => {
          spreadRef.current = node
        }}
        position={[0, FLOOR_HEIGHT * 0.62, 0]}
      >
        <boxGeometry args={[FLOOR_WIDTH * 1.04, 0.08, FLOOR_DEPTH * 1.05]} />
        <meshBasicMaterial color={edgeRef} transparent opacity={0.1} />
      </mesh>

      <Html position={[-FLOOR_WIDTH / 2 - 1.1, FLOOR_HEIGHT * 0.35, 0]} center>
        <div className="rounded-full border border-slate-700/70 bg-slate-950/90 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-300 shadow-lg">
          {floor.label}
        </div>
      </Html>
    </group>
  )
}

function ZoneSignal({
  signal,
  floor,
  selected,
  onHover,
  onSelect,
}: {
  signal: CockpitTwinZoneSignal
  floor: CockpitTwinFloor | undefined
  selected: boolean
  onHover: (signal: CockpitTwinZoneSignal | null) => void
  onSelect: (signal: CockpitTwinZoneSignal) => void
}) {
  const palette = riskPalette(signal.level)
  const orbColor = useMemo(() => new THREE.Color(palette.glow), [palette.glow])
  const ringColor = useMemo(() => new THREE.Color(palette.edge), [palette.edge])
  const orbRef = useRef<THREE.Mesh | null>(null)
  const ringRef = useRef<THREE.Mesh | null>(null)
  const position = useMemo(() => buildSignalPosition(floor, signal.slot), [floor, signal.slot])

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const orb = orbRef.current
    const ring = ringRef.current
    const isCritical = signal.level === 'critical'
    const speed = isCritical ? 4.8 : 2
    const wave = (Math.sin(t * speed) + 1) / 2

    if (orb) {
      const scale = isCritical
        ? 0.96 + wave * (signal.isPrimary ? 1.1 : 0.55) + (selected ? 0.18 : 0)
        : 0.94 + wave * (signal.isPrimary ? 0.36 : 0.18) + (selected ? 0.08 : 0)
      orb.scale.setScalar(scale)
      const material = orb.material as THREE.MeshStandardMaterial
      material.emissive.copy(orbColor)
      material.emissiveIntensity = isCritical
        ? 0.75 + signal.weight * 1.8 + (selected ? 0.48 : 0)
        : 0.28 + signal.weight * 0.82 + (selected ? 0.22 : 0)
    }

    if (ring) {
      const ringScale = isCritical
        ? 1.24 + wave * (signal.isPrimary ? 1.9 : 1.15)
        : 1.08 + wave * (signal.isPrimary ? 0.62 : 0.34)
      ring.scale.set(ringScale, ringScale, ringScale)
      const material = ring.material as THREE.MeshBasicMaterial
      material.opacity = isCritical ? 0.28 + wave * 0.34 : 0.08 + wave * 0.12
    }
  })

  const handlePointerEnter = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation()
    onHover(signal)
  }

  const handlePointerLeave = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation()
    onHover(null)
  }

  const handleClick = (event: ThreeEvent<MouseEvent>) => {
    event.stopPropagation()
    onSelect(signal)
  }

  return (
    <group position={position}>
      <mesh
        ref={(node) => {
          orbRef.current = node
        }}
        onPointerEnter={handlePointerEnter}
        onPointerLeave={handlePointerLeave}
        onClick={handleClick}
      >
        <sphereGeometry args={[signal.isPrimary ? 0.33 : 0.22, 24, 24]} />
        <meshStandardMaterial color={orbColor} emissive={orbColor} emissiveIntensity={1} />
      </mesh>
      <mesh
        ref={(node) => {
          ringRef.current = node
        }}
        rotation={[-Math.PI / 2, 0, 0]}
      >
        <ringGeometry args={[0.38, 0.52, 48]} />
        <meshBasicMaterial color={ringColor} transparent opacity={0.24} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

function Scene({
  state,
  activeSignal,
  onHover,
  onSelect,
}: {
  state: CockpitState
  activeSignal: CockpitTwinZoneSignal | null
  onHover: (signal: CockpitTwinZoneSignal | null) => void
  onSelect: (signal: CockpitTwinZoneSignal) => void
}) {
  return (
    <>
      <color attach="background" args={['#020617']} />
      <fog attach="fog" args={['#020617', 18, 36]} />
      <PerspectiveCamera makeDefault position={[0, 8.4, 15.2]} fov={34} />
      <ambientLight intensity={0.65} color="#dbeafe" />
      <directionalLight position={[10, 18, 8]} intensity={1.1} color="#f8fafc" />
      <pointLight position={[0, 10, 0]} intensity={0.75} color="#7dd3fc" />

      <group position={[0, -5.4, 0]} rotation={[-0.28, 0.22, 0]}>
        {state.visualTwin.floors.map((floor) => (
          <FloorMass
            key={floor.meshId}
            floor={floor}
            isFocus={floor.id === state.visualTwin.focusFloorId}
            motionProfile={state.visualTwin.motionProfile}
          />
        ))}

        {state.visualTwin.zoneSignals.map((signal) => (
          <ZoneSignal
            key={signal.meshId}
            signal={signal}
            floor={state.visualTwin.floors.find((floor) => floor.id === signal.floorId)}
            selected={activeSignal?.meshId === signal.meshId}
            onHover={onHover}
            onSelect={onSelect}
          />
        ))}

        <mesh position={[0, -0.6, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[18, 18]} />
          <meshStandardMaterial color="#020617" metalness={0.05} roughness={0.95} />
        </mesh>
      </group>
    </>
  )
}

export function CockpitNervousSystemTwin({ state }: CockpitNervousSystemTwinProps) {
  const [hoveredSignal, setHoveredSignal] = useState<CockpitTwinZoneSignal | null>(null)
  const [selectedSignal, setSelectedSignal] = useState<CockpitTwinZoneSignal | null>(null)
  const activeSignal = hoveredSignal ?? selectedSignal

  return (
    <div
      className="relative overflow-hidden rounded-2xl border border-slate-800/80 bg-[radial-gradient(circle_at_top,rgba(14,116,144,0.22),rgba(2,6,23,0.96)_52%)]"
      role="img"
      aria-label={`3D intelligence twin for ${state.site.name}`}
    >
      <div className="h-[420px] w-full md:h-[520px]">
        <Canvas
          gl={{ antialias: true }}
          dpr={[1, 1.5]}
          onPointerMissed={() => setSelectedSignal(null)}
        >
          <Scene
            state={state}
            activeSignal={activeSignal}
            onHover={setHoveredSignal}
            onSelect={setSelectedSignal}
          />
        </Canvas>
      </div>

      <div className="absolute inset-x-0 bottom-0 z-10 flex justify-end p-4">
        {activeSignal && (
          <button
            type="button"
            onClick={() => setSelectedSignal(activeSignal)}
            className="max-w-sm rounded-2xl border border-slate-800/80 bg-slate-950/90 px-4 py-3 text-left shadow-xl backdrop-blur"
          >
            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Focused Zone</div>
            <div className="mt-1 text-sm font-semibold text-white">{activeSignal.label}</div>
            <div className="mt-1 text-xs text-slate-300">{activeSignal.zoneId}</div>
            <div className="mt-2 text-xs leading-relaxed text-slate-400">
              {activeSignal.actionLabel}
            </div>
          </button>
        )}
      </div>
    </div>
  )
}

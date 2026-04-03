import { useMemo, useRef, useState, type MutableRefObject } from 'react'
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
    return { base: '#7f1d1d', edge: '#ef4444', glow: '#f87171', text: 'text-red-300' }
  }
  if (level === 'approaching') {
    return { base: '#7c2d12', edge: '#f97316', glow: '#fb923c', text: 'text-orange-300' }
  }
  if (level === 'drift') {
    return { base: '#92400e', edge: '#fbbf24', glow: '#fde68a', text: 'text-amber-300' }
  }
  return { base: '#0f3b66', edge: '#38bdf8', glow: '#7dd3fc', text: 'text-sky-300' }
}

function buildSignalPosition(floor: CockpitTwinFloor | undefined, slot: number) {
  const laneX = -3.1 + (slot % 4) * 2.05
  const laneZ = slot % 2 === 0 ? -0.75 : 0.95
  return new THREE.Vector3(laneX, (floor?.elevation ?? 0) + FLOOR_HEIGHT * 0.95, laneZ)
}

function buildFloorAnimationState(
  floor: CockpitTwinFloor,
  motionProfile: CockpitState['visualTwin']['motionProfile'],
  isFocus: boolean,
  elapsedTime: number,
) {
  // 'calm' = stable state. Brief says "Calm must feel alive" — gentle ambient breathe, no pulsing.
  // Only freeze completely if floor level is explicitly stable AND motion is calm.
  if (motionProfile === 'calm' && floor.level === 'stable') {
    const ambientWave = Math.sin(elapsedTime * 0.4) // very slow, ~15s cycle
    return {
      pulse: 1 + ambientWave * 0.008, // barely perceptible scale breathe
      spreadX: 1,
      spreadZ: 1,
      spreadOpacity: 0.02 + ambientWave * 0.015, // faint living glow
      emissiveIntensity: (isFocus ? 0.18 : 0.08) + ambientWave * 0.04,
    }
  }

  // 'calm' but floor has non-stable risk level — show mild drift
  if (motionProfile === 'calm') {
    const wave = Math.sin(elapsedTime * 0.9)
    return {
      pulse: 1 + wave * floor.spread * 0.025,
      spreadX: 1 + floor.spread * 0.06,
      spreadZ: 1 + floor.spread * 0.08,
      spreadOpacity: 0.03 + floor.spread * 0.04,
      emissiveIntensity: isFocus ? 0.22 : 0.12,
    }
  }

  const isCritical = floor.level === 'critical'
  const speed = isCritical ? 4.2 : 1.9
  const strength = isCritical ? 0.16 : 0.045
  const wave = Math.sin(elapsedTime * speed)

  return {
    pulse: 1 + wave * floor.spread * strength,
    spreadX: 1 + floor.spread * (isCritical ? 0.36 : 0.12),
    spreadZ: 1 + floor.spread * (isCritical ? 0.42 : 0.16),
    spreadOpacity: isCritical ? 0.18 + floor.spread * 0.34 : 0.05 + floor.spread * 0.08,
    emissiveIntensity: isCritical
      ? 0.42 + floor.intensity * (isFocus ? 1.45 : 0.72)
      : 0.2 + floor.intensity * (isFocus ? 0.65 : 0.28),
  }
}

function applyFloorAnimation(
  mesh: THREE.Mesh | null,
  spread: THREE.Mesh | null,
  edgeRef: THREE.Color,
  animation: ReturnType<typeof buildFloorAnimationState>,
) {
  if (mesh) {
    mesh.scale.set(1, animation.pulse, 1)
    const material = mesh.material as THREE.MeshStandardMaterial
    material.emissive.copy(edgeRef)
    material.emissiveIntensity = animation.emissiveIntensity
  }

  if (spread) {
    spread.scale.set(animation.spreadX, 1, animation.spreadZ)
    const material = spread.material as THREE.MeshBasicMaterial
    material.opacity = animation.spreadOpacity
  }
}

function FloorMesh({
  meshRef,
  coreRef,
}: {
  meshRef: MutableRefObject<THREE.Mesh | null>
  coreRef: THREE.Color
}) {
  return (
    <mesh ref={(node) => { meshRef.current = node }}>
      <boxGeometry args={[FLOOR_WIDTH, FLOOR_HEIGHT, FLOOR_DEPTH]} />
      <meshStandardMaterial color={coreRef} metalness={0.18} roughness={0.32} />
    </mesh>
  )
}

function FloorSpread({
  spreadRef,
  edgeRef,
}: {
  spreadRef: MutableRefObject<THREE.Mesh | null>
  edgeRef: THREE.Color
}) {
  return (
    <mesh
      ref={(node) => { spreadRef.current = node }}
      position={[0, FLOOR_HEIGHT * 0.62, 0]}
    >
      <boxGeometry args={[FLOOR_WIDTH * 1.04, 0.08, FLOOR_DEPTH * 1.05]} />
      <meshBasicMaterial color={edgeRef} transparent opacity={0.1} />
    </mesh>
  )
}

function FloorLabel({ label }: { label: string }) {
  return (
    <Html position={[-FLOOR_WIDTH / 2 - 1.1, FLOOR_HEIGHT * 0.35, 0]} center>
      <div className="rounded-full border border-slate-700/70 bg-slate-950/90 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-300 shadow-lg">
        {label}
      </div>
    </Html>
  )
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
    const animation = buildFloorAnimationState(floor, motionProfile, isFocus, clock.getElapsedTime())
    applyFloorAnimation(meshRef.current, spreadRef.current, edgeRef, animation)
  })

  return (
    <group position={[0, floor.elevation, 0]}>
      <FloorMesh meshRef={meshRef} coreRef={coreRef} />
      <FloorSpread spreadRef={spreadRef} edgeRef={edgeRef} />
      <FloorLabel label={floor.label} />
    </group>
  )
}

function buildZoneAnimationState(
  signal: CockpitTwinZoneSignal,
  selected: boolean,
  elapsedTime: number,
) {
  const isCritical = signal.level === 'critical'
  const speed = isCritical ? 4.8 : 2
  const wave = (Math.sin(elapsedTime * speed) + 1) / 2

  return {
    orbScale: isCritical
      ? 0.96 + wave * (signal.isPrimary ? 1.1 : 0.55) + (selected ? 0.18 : 0)
      : 0.94 + wave * (signal.isPrimary ? 0.36 : 0.18) + (selected ? 0.08 : 0),
    ringScale: isCritical
      ? 1.24 + wave * (signal.isPrimary ? 1.9 : 1.15)
      : 1.08 + wave * (signal.isPrimary ? 0.62 : 0.34),
    ringOpacity: isCritical ? 0.28 + wave * 0.34 : 0.08 + wave * 0.12,
    emissiveIntensity: isCritical
      ? 0.75 + signal.weight * 1.8 + (selected ? 0.48 : 0)
      : 0.28 + signal.weight * 0.82 + (selected ? 0.22 : 0),
  }
}

function applyZoneAnimation(
  orb: THREE.Mesh | null,
  ring: THREE.Mesh | null,
  orbColor: THREE.Color,
  animation: ReturnType<typeof buildZoneAnimationState>,
) {
  if (orb) {
    orb.scale.setScalar(animation.orbScale)
    const material = orb.material as THREE.MeshStandardMaterial
    material.emissive.copy(orbColor)
    material.emissiveIntensity = animation.emissiveIntensity
  }

  if (ring) {
    ring.scale.set(animation.ringScale, animation.ringScale, animation.ringScale)
    const material = ring.material as THREE.MeshBasicMaterial
    material.opacity = animation.ringOpacity
  }
}

function ZoneOrb({
  orbRef,
  signal,
  orbColor,
  onPointerEnter,
  onPointerLeave,
  onClick,
}: {
  orbRef: MutableRefObject<THREE.Mesh | null>
  signal: CockpitTwinZoneSignal
  orbColor: THREE.Color
  onPointerEnter: (event: ThreeEvent<PointerEvent>) => void
  onPointerLeave: (event: ThreeEvent<PointerEvent>) => void
  onClick: (event: ThreeEvent<MouseEvent>) => void
}) {
  return (
    <mesh
      ref={(node) => { orbRef.current = node }}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
      onClick={onClick}
    >
      <sphereGeometry args={[signal.isPrimary ? 0.33 : 0.22, 24, 24]} />
      <meshStandardMaterial color={orbColor} emissive={orbColor} emissiveIntensity={1} />
    </mesh>
  )
}

function ZoneRing({
  ringRef,
  ringColor,
}: {
  ringRef: MutableRefObject<THREE.Mesh | null>
  ringColor: THREE.Color
}) {
  return (
    <mesh
      ref={(node) => { ringRef.current = node }}
      rotation={[-Math.PI / 2, 0, 0]}
    >
      <ringGeometry args={[0.38, 0.52, 48]} />
      <meshBasicMaterial color={ringColor} transparent opacity={0.24} side={THREE.DoubleSide} />
    </mesh>
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
    const animation = buildZoneAnimationState(signal, selected, clock.getElapsedTime())
    applyZoneAnimation(orbRef.current, ringRef.current, orbColor, animation)
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
      <ZoneOrb
        orbRef={orbRef}
        signal={signal}
        orbColor={orbColor}
        onPointerEnter={handlePointerEnter}
        onPointerLeave={handlePointerLeave}
        onClick={handleClick}
      />
      <ZoneRing ringRef={ringRef} ringColor={ringColor} />
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

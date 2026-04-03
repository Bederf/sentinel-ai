import { useMemo, useRef, useState, type MutableRefObject } from 'react'
import { Canvas, useFrame, type ThreeEvent } from '@react-three/fiber'
import { Html, PerspectiveCamera } from '@react-three/drei'
import * as THREE from 'three'
import type { CockpitState, CockpitTwinFloor, CockpitTwinRiskLevel, CockpitTwinZoneSignal } from './types'

interface CockpitNervousSystemTwinProps {
  state: CockpitState
}

// ---------------------------------------------------------------------------
// Sandton City Office Tower — structural geometry constants
// ~30 floors total. Setbacks at floors 10, 20, 26 matching the photo.
// Floor 0 = basement (ground level), floor 29 = crown.
// ---------------------------------------------------------------------------
const FLOOR_SPACING = 1.1          // vertical gap between structural floors
const BASE_WIDTH    = 11.2
const BASE_DEPTH    = 6.2
const FLOOR_HEIGHT  = 0.52

// Sentinel-monitored floor IDs mapped to their position in the 30-floor stack.
// B1 sits just below grade; Roof sits at the top.
const SENTINEL_FLOOR_STACK_INDEX: Record<string, number> = {
  B1: 0,
  L0: 0,
  L1: 3,
  L2: 6,
  L3: 9,
  R:  29,
}

// Per-floor structural profile: width scale, depth scale, emissive darkness.
// Mirrors the distinct setback bands visible on the real building.
function structuralProfile(stackIndex: number): {
  wScale: number
  dScale: number
  color: string
  emissive: string
} {
  if (stackIndex >= 26) return { wScale: 0.72, dScale: 0.70, color: '#1a1f2e', emissive: '#0a0d14' }
  if (stackIndex >= 20) return { wScale: 0.82, dScale: 0.80, color: '#1c2235', emissive: '#0c1018' }
  if (stackIndex >= 10) return { wScale: 0.92, dScale: 0.90, color: '#1e2540', emissive: '#0e1220' }
  return                       { wScale: 1.00, dScale: 1.00, color: '#202840', emissive: '#101420' }
}

// ---------------------------------------------------------------------------
// Risk palette for Sentinel floors
// ---------------------------------------------------------------------------
function riskPalette(level: CockpitTwinRiskLevel) {
  if (level === 'critical')   return { base: '#7f1d1d', edge: '#ef4444', glow: '#f87171', text: 'text-red-300' }
  if (level === 'approaching') return { base: '#7c2d12', edge: '#f97316', glow: '#fb923c', text: 'text-orange-300' }
  if (level === 'drift')      return { base: '#92400e', edge: '#fbbf24', glow: '#fde68a', text: 'text-amber-300' }
  return                             { base: '#0f3b66', edge: '#38bdf8', glow: '#7dd3fc', text: 'text-sky-300' }
}

function buildSignalPosition(elevation: number, slot: number) {
  const laneX = -3.1 + (slot % 4) * 2.05
  const laneZ = slot % 2 === 0 ? -0.75 : 0.95
  return new THREE.Vector3(laneX, elevation + FLOOR_HEIGHT * 0.95, laneZ)
}

// ---------------------------------------------------------------------------
// Inert structural floor — no animation, no label, just mass
// ---------------------------------------------------------------------------
function StructuralFloor({ stackIndex }: { stackIndex: number }) {
  const profile = useMemo(() => structuralProfile(stackIndex), [stackIndex])
  const w = BASE_WIDTH  * profile.wScale
  const d = BASE_DEPTH  * profile.dScale
  const y = stackIndex * (FLOOR_HEIGHT + FLOOR_SPACING)

  // Alternating glass / spandrel band — every 3rd floor slightly lighter
  const isSpandrel = stackIndex % 3 === 0
  const color   = isSpandrel ? '#252c42' : profile.color
  const emissive = isSpandrel ? '#121828' : profile.emissive

  return (
    <mesh position={[0, y, 0]}>
      <boxGeometry args={[w, FLOOR_HEIGHT, d]} />
      <meshStandardMaterial
        color={color}
        emissive={emissive}
        emissiveIntensity={0.06}
        metalness={0.35}
        roughness={0.55}
      />
    </mesh>
  )
}

// ---------------------------------------------------------------------------
// Sentinel intelligence floor — animated, labelled
// ---------------------------------------------------------------------------
function buildFloorAnimationState(
  floor: CockpitTwinFloor,
  motionProfile: CockpitState['visualTwin']['motionProfile'],
  isFocus: boolean,
  elapsedTime: number,
) {
  if (motionProfile === 'calm' && floor.level === 'stable') {
    const w = Math.sin(elapsedTime * 0.4)
    return {
      pulse: 1 + w * 0.008,
      spreadX: 1, spreadZ: 1,
      spreadOpacity: 0.02 + w * 0.015,
      emissiveIntensity: (isFocus ? 0.18 : 0.08) + w * 0.04,
    }
  }
  if (motionProfile === 'calm') {
    const w = Math.sin(elapsedTime * 0.9)
    return {
      pulse: 1 + w * floor.spread * 0.025,
      spreadX: 1 + floor.spread * 0.06,
      spreadZ: 1 + floor.spread * 0.08,
      spreadOpacity: 0.03 + floor.spread * 0.04,
      emissiveIntensity: isFocus ? 0.22 : 0.12,
    }
  }
  const isCritical = floor.level === 'critical'
  const speed    = isCritical ? 4.2 : 1.9
  const strength = isCritical ? 0.16 : 0.045
  const w = Math.sin(elapsedTime * speed)
  return {
    pulse: 1 + w * floor.spread * strength,
    spreadX: 1 + floor.spread * (isCritical ? 0.36 : 0.12),
    spreadZ: 1 + floor.spread * (isCritical ? 0.42 : 0.16),
    spreadOpacity: isCritical ? 0.18 + floor.spread * 0.34 : 0.05 + floor.spread * 0.08,
    emissiveIntensity: isCritical
      ? 0.42 + floor.intensity * (isFocus ? 1.45 : 0.72)
      : 0.2  + floor.intensity * (isFocus ? 0.65 : 0.28),
  }
}

function applyFloorAnimation(
  mesh: THREE.Mesh | null,
  spread: THREE.Mesh | null,
  edgeColor: THREE.Color,
  anim: ReturnType<typeof buildFloorAnimationState>,
) {
  if (mesh) {
    mesh.scale.set(1, anim.pulse, 1)
    ;(mesh.material as THREE.MeshStandardMaterial).emissive.copy(edgeColor)
    ;(mesh.material as THREE.MeshStandardMaterial).emissiveIntensity = anim.emissiveIntensity
  }
  if (spread) {
    spread.scale.set(anim.spreadX, 1, anim.spreadZ)
    ;(spread.material as THREE.MeshBasicMaterial).opacity = anim.spreadOpacity
  }
}

function SentinelFloorMass({
  floor,
  isFocus,
  motionProfile,
  elevation,
}: {
  floor: CockpitTwinFloor
  isFocus: boolean
  motionProfile: CockpitState['visualTwin']['motionProfile']
  elevation: number
}) {
  const stackIdx = SENTINEL_FLOOR_STACK_INDEX[floor.id] ?? 0
  const profile  = useMemo(() => structuralProfile(stackIdx), [stackIdx])
  const w = BASE_WIDTH  * profile.wScale
  const d = BASE_DEPTH  * profile.dScale

  const coreColor = useMemo(() => new THREE.Color(riskPalette(floor.level).base), [floor.level])
  const edgeColor = useMemo(() => new THREE.Color(riskPalette(floor.level).glow), [floor.level])
  const meshRef   = useRef<THREE.Mesh | null>(null)
  const spreadRef = useRef<THREE.Mesh | null>(null)

  useFrame(({ clock }) => {
    const anim = buildFloorAnimationState(floor, motionProfile, isFocus, clock.getElapsedTime())
    applyFloorAnimation(meshRef.current, spreadRef.current, edgeColor, anim)
  })

  return (
    <group position={[0, elevation, 0]}>
      {/* core slab */}
      <mesh ref={(n) => { meshRef.current = n }}>
        <boxGeometry args={[w, FLOOR_HEIGHT, d]} />
        <meshStandardMaterial color={coreColor} metalness={0.18} roughness={0.32} />
      </mesh>
      {/* spread glow layer */}
      <mesh
        ref={(n) => { spreadRef.current = n }}
        position={[0, FLOOR_HEIGHT * 0.62, 0]}
      >
        <boxGeometry args={[w * 1.04, 0.08, d * 1.05]} />
        <meshBasicMaterial color={edgeColor} transparent opacity={0.1} />
      </mesh>
      {/* label */}
      <Html position={[-w / 2 - 1.2, FLOOR_HEIGHT * 0.35, 0]} center>
        <div className="rounded-full border border-slate-600/80 bg-slate-950/90 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.22em] text-slate-200 shadow-lg">
          {floor.label}
        </div>
      </Html>
    </group>
  )
}

// ---------------------------------------------------------------------------
// Zone signal orb + ring
// ---------------------------------------------------------------------------
function buildZoneAnimationState(
  signal: CockpitTwinZoneSignal,
  selected: boolean,
  t: number,
) {
  const isCritical = signal.level === 'critical'
  const speed = isCritical ? 4.8 : 2
  const wave  = (Math.sin(t * speed) + 1) / 2
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

function ZoneSignal({
  signal,
  elevation,
  selected,
  onHover,
  onSelect,
}: {
  signal: CockpitTwinZoneSignal
  elevation: number
  selected: boolean
  onHover: (s: CockpitTwinZoneSignal | null) => void
  onSelect: (s: CockpitTwinZoneSignal) => void
}) {
  const palette  = riskPalette(signal.level)
  const orbColor = useMemo(() => new THREE.Color(palette.glow), [palette.glow])
  const ringColor = useMemo(() => new THREE.Color(palette.edge), [palette.edge])
  const orbRef   = useRef<THREE.Mesh | null>(null)
  const ringRef  = useRef<THREE.Mesh | null>(null)
  const position = useMemo(() => buildSignalPosition(elevation, signal.slot), [elevation, signal.slot])

  useFrame(({ clock }) => {
    const anim = buildZoneAnimationState(signal, selected, clock.getElapsedTime())
    if (orbRef.current) {
      orbRef.current.scale.setScalar(anim.orbScale)
      ;(orbRef.current.material as THREE.MeshStandardMaterial).emissive.copy(orbColor)
      ;(orbRef.current.material as THREE.MeshStandardMaterial).emissiveIntensity = anim.emissiveIntensity
    }
    if (ringRef.current) {
      ringRef.current.scale.setScalar(anim.ringScale)
      ;(ringRef.current.material as THREE.MeshBasicMaterial).opacity = anim.ringOpacity
    }
  })

  return (
    <group position={position}>
      <mesh
        ref={(n) => { orbRef.current = n }}
        onPointerEnter={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); onHover(signal) }}
        onPointerLeave={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); onHover(null) }}
        onClick={(e: ThreeEvent<MouseEvent>) => { e.stopPropagation(); onSelect(signal) }}
      >
        <sphereGeometry args={[signal.isPrimary ? 0.33 : 0.22, 24, 24]} />
        <meshStandardMaterial color={orbColor} emissive={orbColor} emissiveIntensity={1} />
      </mesh>
      <mesh ref={(n) => { ringRef.current = n }} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.38, 0.52, 48]} />
        <meshBasicMaterial color={ringColor} transparent opacity={0.24} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

// ---------------------------------------------------------------------------
// Total structural floors in the tower stack
// ---------------------------------------------------------------------------
const TOTAL_STRUCTURAL_FLOORS = 30

// Structural floors that are NOT sentinel-monitored (render as inert mass)
const SENTINEL_STACK_INDICES = new Set(Object.values(SENTINEL_FLOOR_STACK_INDEX))

function Scene({
  state,
  activeSignal,
  onHover,
  onSelect,
}: {
  state: CockpitState
  activeSignal: CockpitTwinZoneSignal | null
  onHover: (s: CockpitTwinZoneSignal | null) => void
  onSelect: (s: CockpitTwinZoneSignal) => void
}) {
  // Build a lookup: floorId → elevation within the structural stack
  const sentinelElevations = useMemo(() => {
    const map = new Map<string, number>()
    for (const [id, idx] of Object.entries(SENTINEL_FLOOR_STACK_INDEX)) {
      map.set(id, idx * (FLOOR_HEIGHT + FLOOR_SPACING))
    }
    return map
  }, [])

  const structuralIndices = useMemo(
    () => Array.from({ length: TOTAL_STRUCTURAL_FLOORS }, (_, i) => i)
              .filter((i) => !SENTINEL_STACK_INDICES.has(i)),
    [],
  )

  return (
    <>
      <color attach="background" args={['#020617']} />
      <fog attach="fog" args={['#020617', 28, 55]} />
      {/* Camera pulled back to show full tower height */}
      <PerspectiveCamera makeDefault position={[4.5, 12, 28]} fov={32} />
      <ambientLight intensity={0.55} color="#c8d8f0" />
      <directionalLight position={[12, 24, 10]} intensity={1.2} color="#f0f4ff" castShadow />
      <pointLight position={[0, 18, 4]} intensity={0.6} color="#7dd3fc" />
      {/* Subtle rim light from behind — mirrors Sandton afternoon sky */}
      <pointLight position={[-8, 22, -6]} intensity={0.4} color="#a5c8ff" />

      {/* Tower group — centred, slight angle matching photo perspective */}
      <group position={[0, -8, 0]} rotation={[0, 0.18, 0]}>

        {/* 1. Inert structural floors — full tower silhouette */}
        {structuralIndices.map((idx) => (
          <StructuralFloor key={`struct-${idx}`} stackIndex={idx} />
        ))}

        {/* 2. Sentinel intelligence floors — animated, on top of structural mass */}
        {state.visualTwin.floors.map((floor) => {
          const elevation = sentinelElevations.get(floor.id)
            ?? sentinelElevations.get('L0')
            ?? 0
          return (
            <SentinelFloorMass
              key={floor.meshId}
              floor={floor}
              isFocus={floor.id === state.visualTwin.focusFloorId}
              motionProfile={state.visualTwin.motionProfile}
              elevation={elevation}
            />
          )
        })}

        {/* 3. Zone signal orbs — positioned at their floor elevation */}
        {state.visualTwin.zoneSignals.map((signal) => {
          const elevation = sentinelElevations.get(signal.floorId)
            ?? sentinelElevations.get('L0')
            ?? 0
          return (
            <ZoneSignal
              key={signal.meshId}
              signal={signal}
              elevation={elevation}
              selected={activeSignal?.meshId === signal.meshId}
              onHover={onHover}
              onSelect={onSelect}
            />
          )
        })}

        {/* Ground plane */}
        <mesh position={[0, -0.6, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[24, 24]} />
          <meshStandardMaterial color="#060a14" metalness={0.05} roughness={0.95} />
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
      className="relative overflow-hidden rounded-2xl border border-slate-800/80 bg-[radial-gradient(circle_at_top,rgba(14,116,144,0.18),rgba(2,6,23,0.97)_55%)]"
      role="img"
      aria-label={`Sandton City Office Tower — SENTINEL spatial intelligence view`}
    >
      <div className="h-[520px] w-full md:h-[640px]">
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

      {/* Zone detail tooltip */}
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
            <div className="mt-2 text-xs leading-relaxed text-slate-400">{activeSignal.actionLabel}</div>
          </button>
        )}
      </div>

      {/* Sentinel floor legend — bottom left */}
      <div className="absolute bottom-4 left-4 z-10 flex flex-col gap-1">
        <div className="text-[8px] uppercase tracking-[0.35em] text-slate-600">Sentinel floors</div>
        {Object.keys(SENTINEL_FLOOR_STACK_INDEX).filter((k) => k !== 'L0').map((id) => (
          <div key={id} className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-sky-400/70" />
            <span className="text-[9px] uppercase tracking-[0.2em] text-slate-500">{id}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

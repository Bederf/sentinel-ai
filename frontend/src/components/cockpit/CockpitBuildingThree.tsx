import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Edges, Line, OrbitControls } from '@react-three/drei'
import type { MutableRefObject } from 'react'
import { Suspense, useCallback, useLayoutEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { MOUSE } from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import type { CockpitState } from './types'
import { cockpitFloorPalette, cockpitFlowColor, cockpitToneKey } from './cockpitTwinTheme'
import { motionReduced } from './motionPreference'

interface CockpitBuildingThreeProps {
  state: CockpitState
  className?: string
}

const SLAB_HEIGHT = 0.28
const BASE_WIDTH  = 1.35
const BASE_DEPTH  = 1.05

// Hard cap — twin represents a known building, not an infinite stack.
// 10 floors covers any realistic FNB REMS site.
const MAX_FLOORS = 10

// Occupied floor IDs for Sandton City Office Tower.
// ONLY these floors receive the amber intelligence glow (isManaged = true).
// B1 has equipment (chillers/pumps) and R has equipment (cooling towers)
// but neither is an occupied tenant space — they render as neutral host mass.
const OCCUPIED_FLOOR_IDS = new Set(['L0', 'L1', 'L2'])

function GridHelperMemo() {
  const grid = useMemo(() => new THREE.GridHelper(18, 18, 0x334155, 0x0c1222), [])
  return <primitive object={grid} position={[0, 0, 0]} />
}

type SlabInfo = {
  id: string
  intensity: number
  isManaged: boolean
  riskLevel: string
}

/** Local Y bounds (pre-scale) for Sentinel-managed slabs only */
function managedLocalYRange(floors: CockpitState['visualTwin']['floors']): { minY: number; maxY: number } | null {
  const reversed = [...floors].reverse()
  let yCursor = 0
  let minY = Infinity
  let maxY = -Infinity
  for (const f of reversed) {
    const h = SLAB_HEIGHT
    const cy = yCursor + h / 2
    yCursor += h
    if (f.isManaged) {
      minY = Math.min(minY, cy - h / 2)
      maxY = Math.max(maxY, cy + h / 2)
    }
  }
  if (!Number.isFinite(minY)) return null
  return { minY, maxY }
}

function ManagedSlab({
  floor,
  tone,
  y,
  w,
  d,
  h,
  breath,
  waiting,
  calm,
}: {
  floor: SlabInfo
  tone: ReturnType<typeof cockpitToneKey>
  y: number
  w: number
  d: number
  h: number
  breath: number
  waiting: boolean
  calm: boolean
}) {
  const groupRef = useRef<THREE.Group>(null)
  const pal = cockpitFloorPalette(tone, floor.intensity, floor.isManaged, floor.riskLevel)

  useFrame(() => {
    const g = groupRef.current
    if (!g || motionReduced() || waiting || calm) return
    const t = performance.now() * 0.001
    const s = 1 + Math.sin(t * 1.8) * breath * 0.014
    g.scale.setScalar(s)
  })

  return (
    <group ref={groupRef} position={[0, y, 0]}>
      <mesh castShadow receiveShadow>
        <boxGeometry args={[w, h, d]} />
        <meshStandardMaterial
          color={pal.base}
          transparent
          opacity={0.42}
          metalness={0.34}
          roughness={0.34}
          emissive={pal.emissive}
          emissiveIntensity={Math.max(0.26, pal.emissiveIntensity + 0.14)}
          depthWrite={false}
        />
        <Edges color={pal.edge} threshold={12} />
      </mesh>
    </group>
  )
}

function HostSlab({
  floor,
  tone,
  y,
  w,
  d,
  h,
}: {
  floor: SlabInfo
  tone: ReturnType<typeof cockpitToneKey>
  y: number
  w: number
  d: number
  h: number
}) {
  // Force isManaged=false so host slabs always get neutral palette
  const pal = cockpitFloorPalette(tone, floor.intensity, false, floor.riskLevel)
  return (
    <mesh position={[0, y, 0]} castShadow receiveShadow>
      <boxGeometry args={[w, h, d]} />
      <meshStandardMaterial
        color={pal.base}
        transparent
        opacity={0.16}
        metalness={0.2}
        roughness={0.46}
        emissive={pal.emissive}
        emissiveIntensity={Math.max(0.12, pal.emissiveIntensity)}
        depthWrite={false}
      />
      <Edges color={pal.edge} threshold={15} />
    </mesh>
  )
}

function BuildingStack({
  state,
  tone,
}: {
  state: CockpitState
  tone: ReturnType<typeof cockpitToneKey>
}) {
  const floors = state.visualTwin.floors
  const waiting = state.site.renderState === 'waiting'
  const calm = !waiting && state.primaryMetric.value === 'Stable'
  const breath = Math.max(0.12, Math.min(1, state.visualTwin.breathingIntensity || 0.2))

  const slabs: SlabInfo[] = useMemo(() => {
    const source = floors.length === 0
      ? Array.from({ length: 5 }).map((_, i) => ({
          id: `default-${i}`,
          intensity: 0.25,
          isManaged: OCCUPIED_FLOOR_IDS.has(`L${i}`),
          riskLevel: 'stable',
        }))
      : floors.map((f) => ({
          id: f.id,
          intensity: f.intensity,
          // isManaged drives amber glow — only occupied tenant floors qualify.
          // Equipment-only floors (B1, R) are host mass regardless of their
          // risk level in the payload.
          isManaged: OCCUPIED_FLOOR_IDS.has(f.id),
          riskLevel: f.level,
        }))
    // Never render more than MAX_FLOORS slabs
    return source.slice(0, MAX_FLOORS)
  }, [floors])

  const reversed = [...slabs].reverse()
  const totalHeight = reversed.length * SLAB_HEIGHT
  let yCursor = 0

  return (
    <group position={[0, 0, 0]}>
      {/* Full host-tower cage so overall mass stays readable on dark scenes */}
      <mesh position={[0, totalHeight / 2, 0]} receiveShadow>
        <boxGeometry args={[BASE_WIDTH * 1.04, totalHeight, BASE_DEPTH * 1.04]} />
        <meshStandardMaterial
          color="#94a3b8"
          transparent
          opacity={0.05}
          metalness={0.08}
          roughness={0.55}
          emissive="#64748b"
          emissiveIntensity={0.2}
          depthWrite={false}
        />
        <Edges color="#e2e8f0" threshold={10} />
      </mesh>

      {reversed.map((floor, index) => {
        const h = SLAB_HEIGHT
        const y = yCursor + h / 2
        yCursor += h
        const setback = 1 - index * 0.0045
        const w = BASE_WIDTH * setback
        const d = BASE_DEPTH * setback

        if (floor.isManaged) {
          return (
            <ManagedSlab
              key={floor.id}
              floor={floor}
              tone={tone}
              y={y}
              w={w}
              d={d}
              h={h}
              breath={breath}
              waiting={waiting}
              calm={calm}
            />
          )
        }
        return <HostSlab key={floor.id} floor={floor} tone={tone} y={y} w={w} d={d} h={h} />
      })}
    </group>
  )
}

function DriftPath({
  state,
  tone,
  visible,
  yRange,
}: {
  state: CockpitState
  tone: ReturnType<typeof cockpitToneKey>
  visible: boolean
  yRange: { minY: number; maxY: number } | null
}) {
  const color = cockpitFlowColor(tone)
  const points = useMemo(() => {
    const curves: THREE.Vector3[] = []
    const segs = 16
    const y0 = yRange ? yRange.minY + 0.04 : 0.12
    const y1 = yRange ? yRange.maxY - 0.04 : SLAB_HEIGHT * 5
    const span = Math.max(y1 - y0, SLAB_HEIGHT * 2)
    for (let i = 0; i <= segs; i++) {
      const t = i / segs
      const y = y0 + t * span * 0.95
      const spiral = t * Math.PI * 1.8
      const x = Math.sin(spiral) * 0.52 + 0.12
      const z = Math.cos(spiral) * 0.44 + 0.16
      curves.push(new THREE.Vector3(x, y, z))
    }
    return curves
  }, [yRange])

  const lineWidth = Math.max(1.5, 2 + (state.visualTwin.flowPaths[0]?.intensity ?? 0.3) * 3)

  if (!yRange) return null

  return (
    <Line
      points={points}
      color={color}
      lineWidth={lineWidth}
      transparent
      opacity={visible ? 0.98 : 0.1}
      depthWrite={false}
    />
  )
}

function AnimatedTracer({
  tone,
  yRange,
  active,
}: {
  tone: ReturnType<typeof cockpitToneKey>
  yRange: { minY: number; maxY: number } | null
  active: boolean
}) {
  const tracerRef = useRef<THREE.Mesh>(null)
  const haloRef = useRef<THREE.Mesh>(null)
  const color = cockpitFlowColor(tone)

  useFrame(() => {
    if (!tracerRef.current || !haloRef.current || !yRange) return
    const t = performance.now() * 0.001
    const speed = active ? 0.42 : 0.24
    const phase = (t * speed) % 1
    const y = yRange.minY + (yRange.maxY - yRange.minY) * phase
    const spiral = phase * Math.PI * 2.2
    const x = Math.sin(spiral) * 0.52 + 0.12
    const z = Math.cos(spiral) * 0.44 + 0.16
    tracerRef.current.position.set(x, y, z)
    haloRef.current.position.set(x, y, z)
    const pulse = 0.65 + 0.35 * Math.sin(t * 8)
    tracerRef.current.scale.setScalar(0.9 + pulse * 0.35)
    haloRef.current.scale.setScalar(1.6 + pulse * 0.5)
  })

  if (!yRange) return null

  return (
    <group>
      <mesh ref={tracerRef}>
        <sphereGeometry args={[0.085, 18, 18]} />
        <meshStandardMaterial color="#ffffff" emissive={color} emissiveIntensity={1.4} transparent opacity={0.98} depthWrite={false} />
      </mesh>
      <mesh ref={haloRef}>
        <sphereGeometry args={[0.14, 16, 16]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.9} transparent opacity={0.38} depthWrite={false} />
      </mesh>
    </group>
  )
}

function ZoneMarkers({
  state,
  buildingHeight,
}: {
  state: CockpitState
  buildingHeight: number
}) {
  const signals = state.visualTwin.zoneSignals.slice(0, 5)
  const floors = state.visualTwin.floors
  const n = Math.max(floors.length, 1)

  return (
    <group>
      {signals.map((sig, index) => {
        const fi = floors.findIndex((f) => f.id === sig.floorId)
        const targetFloor = fi >= 0 ? floors[fi] : null
        // Only render orbs on occupied floors
        if (!targetFloor || !OCCUPIED_FLOOR_IDS.has(targetFloor.id)) return null
        const idx = fi
        const yRatio = n > 1 ? idx / Math.max(n - 1, 1) : 0.5
        const y = 0.2 + yRatio * Math.max(buildingHeight - 0.4, SLAB_HEIGHT * 2)
        const angle = (index / Math.max(signals.length, 1)) * Math.PI * 2
        const x = Math.cos(angle) * 0.72
        const z = Math.sin(angle) * 0.58 + 0.1
        return (
          <mesh key={`${sig.zoneId}-${index}`} position={[x, y, z]}>
            <sphereGeometry args={[0.09, 16, 16]} />
            <meshStandardMaterial
              color="#f8fafc"
              emissive="#ffffff"
              emissiveIntensity={0.9}
              metalness={0.2}
              roughness={0.2}
              transparent
              opacity={0.98}
              depthWrite={false}
            />
          </mesh>
        )
      })}
    </group>
  )
}

function CameraToolbar({
  onZoomIn,
  onZoomOut,
  onReset,
}: {
  onZoomIn: () => void
  onZoomOut: () => void
  onReset: () => void
}) {
  const btn =
    'rounded-full border border-white/15 bg-slate-950/80 px-3 py-1.5 text-[10px] font-medium uppercase tracking-[0.14em] text-slate-200 backdrop-blur-sm transition hover:border-cyan-500/40 hover:text-white'
  return (
    <div className="pointer-events-auto absolute left-3 top-3 z-20 flex flex-wrap gap-2">
      <button type="button" className={btn} onClick={onZoomOut}>Zoom out</button>
      <button type="button" className={btn} onClick={onZoomIn}>Zoom in</button>
      <button type="button" className={btn} onClick={onReset}>Reset view</button>
    </div>
  )
}

function zoomCameraTowardTarget(oc: OrbitControlsImpl, factor: number) {
  const dir = oc.object.position.clone().sub(oc.target)
  const len = dir.length()
  if (len < 0.02) return
  dir.normalize()
  const minD = oc.minDistance ?? 2
  const maxD = oc.maxDistance ?? 50
  const nextLen = THREE.MathUtils.clamp(len * factor, minD, maxD)
  oc.object.position.copy(oc.target.clone().add(dir.multiplyScalar(nextLen)))
  oc.update()
}

function SceneR3F({
  state,
  controlsRef,
  defaultCam,
  computedTarget,
  modelScale,
}: {
  state: CockpitState
  controlsRef: MutableRefObject<OrbitControlsImpl | null>
  defaultCam: THREE.Vector3
  computedTarget: THREE.Vector3
  modelScale: number
}) {
  const tone = cockpitToneKey(state)
  const { camera } = useThree()

  // Apply MAX_FLOORS cap here too so buildingHeight is consistent
  const floorCount = Math.min(Math.max(state.visualTwin.floors.length, 5), MAX_FLOORS)
  const buildingHeight = floorCount * SLAB_HEIGHT
  const yRange = useMemo(() => managedLocalYRange(state.visualTwin.floors), [state.visualTwin.floors])

  useLayoutEffect(() => {
    camera.position.copy(defaultCam)
    camera.updateProjectionMatrix()
    const oc = controlsRef.current
    if (oc) {
      oc.target.copy(computedTarget)
      oc.update()
    }
  }, [camera, computedTarget, defaultCam, controlsRef])

  const waiting = state.site.renderState === 'waiting'
  const calm = !waiting && state.primaryMetric.value === 'Stable'
  const showFlow = !waiting && state.visualTwin.flowPaths.length > 0 && !calm

  const worldHalf = buildingHeight * modelScale * 0.5
  const fogFar = Math.max(18, worldHalf * 4.5)

  return (
    <>
      <color attach="background" args={['#020617']} />
      <fog attach="fog" args={['#020617', 12, fogFar]} />

      <ambientLight intensity={0.52} />
      <directionalLight position={[6, 14, 8]} intensity={1.3} castShadow shadow-mapSize-width={1024} shadow-mapSize-height={1024} />
      <directionalLight position={[-5, 6, -4]} intensity={0.6} color="#67e8f9" />
      <directionalLight position={[0, 4, -9]} intensity={0.44} color="#e2e8f0" />
      <hemisphereLight args={['#0ea5e9', '#0b1120', 0.3]} />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 0]} receiveShadow>
        <planeGeometry args={[32, 32]} />
        <meshStandardMaterial color="#020617" metalness={0.05} roughness={0.95} />
      </mesh>

      <GridHelperMemo />

      <group scale={[modelScale, modelScale, modelScale]}>
        <BuildingStack state={state} tone={tone} />
        <DriftPath state={state} tone={tone} visible={showFlow} yRange={yRange} />
        <AnimatedTracer tone={tone} yRange={yRange} active={showFlow} />
        <ZoneMarkers state={state} buildingHeight={buildingHeight} />
      </group>

      <OrbitControls
        ref={controlsRef}
        makeDefault
        enableDamping
        dampingFactor={0.08}
        minDistance={Math.max(1.4, worldHalf * 0.7)}
        maxDistance={Math.max(8, worldHalf * 3.2)}
        minPolarAngle={0.32}
        maxPolarAngle={Math.PI / 2 + 0.14}
        target={computedTarget}
        enablePan
        panSpeed={0.65}
        mouseButtons={{
          LEFT: MOUSE.ROTATE,
          MIDDLE: MOUSE.DOLLY,
          RIGHT: MOUSE.PAN,
        }}
      />
    </>
  )
}

export function CockpitBuildingThree({ state, className }: CockpitBuildingThreeProps) {
  const controlsRef = useRef<OrbitControlsImpl>(null)
  // Apply MAX_FLOORS cap so modelScale and camera are sized for a known building
  const floorCount = Math.min(Math.max(state.visualTwin.floors.length, 5), MAX_FLOORS)
  const buildingHeight = floorCount * SLAB_HEIGHT

  const modelScale = useMemo(
    () => THREE.MathUtils.clamp(4.2 / Math.max(buildingHeight, 2.8), 1.1, 2.2),
    [buildingHeight],
  )

  const layout = useMemo(() => {
    const wh = buildingHeight * modelScale * 0.5
    const target = new THREE.Vector3(0, wh, 0)
    const cam = new THREE.Vector3(wh * 1.05, wh * 0.78, wh * 1.45)
    return { computedTarget: target, defaultCam: cam }
  }, [buildingHeight, modelScale])

  const { computedTarget, defaultCam } = layout

  const zoomIn = useCallback(() => {
    const oc = controlsRef.current
    if (!oc) return
    zoomCameraTowardTarget(oc, 0.92)
  }, [])

  const zoomOut = useCallback(() => {
    const oc = controlsRef.current
    if (!oc) return
    zoomCameraTowardTarget(oc, 1.09)
  }, [])

  const reset = useCallback(() => {
    const oc = controlsRef.current
    if (!oc) return
    oc.object.position.copy(defaultCam)
    oc.target.copy(computedTarget)
    oc.update()
  }, [computedTarget, defaultCam])

  const viewportHeight = 'clamp(380px, 52vh, 580px)'

  return (
    <div className={`relative w-full ${className ?? ''}`} style={{ height: viewportHeight }}>
      <CameraToolbar onZoomIn={zoomIn} onZoomOut={zoomOut} onReset={reset} />
      <Canvas
        className="h-full w-full"
        style={{ width: '100%', height: '100%' }}
        shadows
        gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }}
        camera={{ fov: 42, near: 0.1, far: 180, position: [defaultCam.x, defaultCam.y, defaultCam.z] }}
        onDoubleClick={(e) => {
          e.preventDefault()
          reset()
        }}
      >
        <Suspense fallback={null}>
          <SceneR3F
            state={state}
            controlsRef={controlsRef}
            defaultCam={defaultCam}
            computedTarget={computedTarget}
            modelScale={modelScale}
          />
        </Suspense>
      </Canvas>
      <div className="pointer-events-none absolute bottom-2 left-3 max-w-[90%] text-[10px] uppercase tracking-[0.16em] text-slate-500">
        Drag orbit · Wheel zoom · Right-drag pan · Double-click reset · Sentinel scope: occupied levels only
      </div>
    </div>
  )
}

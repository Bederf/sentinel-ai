import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Edges, Line, OrbitControls, useTexture } from '@react-three/drei'
import { useQuery } from '@tanstack/react-query'
import type { MutableRefObject } from 'react'
import { Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { MOUSE } from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import type { CockpitState } from './types'
import { cockpitFloorPalette, cockpitFlowColor, cockpitToneKey } from './cockpitTwinTheme'
import { motionReduced } from './motionPreference'
import { fetchApi } from '@/lib/api/client'
import type { BuildingEquipmentResponse } from '@/lib/api/sites'
import { useHealthThresholds } from '@/hooks/useHealthThresholds'

interface CockpitBuildingThreeProps {
  state: CockpitState
  className?: string
  onZoneSelect?: (zone: import("./types").CockpitTwinZoneSignal | null) => void
}

const SLAB_HEIGHT = 0.28
const BASE_WIDTH  = 1.35
const BASE_DEPTH  = 1.05

/** Building-type slab proportions — hospital is wider/deeper than office. */
const BUILDING_TYPE_SCALE: Record<string, { w: number; d: number }> = {
  hospital: { w: BASE_WIDTH * 1.6, d: BASE_DEPTH * 1.4 },
  private_hospital: { w: BASE_WIDTH * 1.6, d: BASE_DEPTH * 1.4 },
  retail: { w: BASE_WIDTH * 1.3, d: BASE_DEPTH * 1.1 },
  industrial: { w: BASE_WIDTH * 1.8, d: BASE_DEPTH * 1.6 },
  warehouse: { w: BASE_WIDTH * 2.0, d: BASE_DEPTH * 1.8 },
  data_centre: { w: BASE_WIDTH * 1.2, d: BASE_DEPTH * 1.2 },
}

/** Per-site override takes priority, then falls back to building-type scale. */
const SITE_SLAB_SCALE: Record<string, { w: number; d: number }> = {
  'site-002': { w: BASE_WIDTH, d: BASE_DEPTH },
}

function siteSlabScale(siteId: string, buildingType?: string, geometry?: import('./types').BuildingGeometryData | null): { w: number; d: number } {
  // Geometry from photo extraction takes highest priority
  if (geometry) {
    const ratio = geometry.footprint_width_depth_ratio || 1.0
    return {
      w: BASE_WIDTH * (ratio >= 1.0 ? ratio : 1.0),
      d: BASE_DEPTH * (ratio < 1.0 ? 1.0 / ratio : 1.0),
    }
  }
  if (SITE_SLAB_SCALE[siteId]) return SITE_SLAB_SCALE[siteId]
  const typeScale = BUILDING_TYPE_SCALE[buildingType ?? '']
  if (typeScale) return typeScale
  return { w: BASE_WIDTH, d: BASE_DEPTH }
}
function siteWidth(siteId: string, buildingType?: string, geometry?: import('./types').BuildingGeometryData | null): number {
  return siteSlabScale(siteId, buildingType, geometry).w
}
function siteDepth(siteId: string, buildingType?: string, geometry?: import('./types').BuildingGeometryData | null): number {
  return siteSlabScale(siteId, buildingType, geometry).d
}

function geometryFloorCount(geometry?: import('./types').BuildingGeometryData | null): number | null {
  if (geometry?.floor_count && geometry.floor_count > 0) return geometry.floor_count
  return null
}

/** Tracer orbit speed per active system (units: cycles per second roughly) */
const TRACER_SPEEDS: Record<string, number> = {
  hvac: 0.42,
  energy: 0.58,
  lighting: 0.35,
  water: 0.30,
  fire: 0.50,
  security: 0.40,
  solar_bess: 0.45,
  default: 0.42,
}

// Hard cap — twin represents a known building, not an infinite stack.
// 10 floors covers any realistic FNB REMS site.
const MAX_FLOORS = 10

// Managed floors tracked by Sentinel — derived from floor.isManaged on each floor object.
// For Sandton: L0, L1, L2 only. For Busamed: all 10 floors (full hospital).
// The floor data comes from the site's tower profile in mapCockpitState.

/** Orb colour per active system tab — matches the tone palette used elsewhere */
const SYSTEM_ORB_COLORS: Record<string, { color: string; emissive: string }> = {
  hvac:      { color: '#22d3ee', emissive: '#22d3ee' },
  energy:    { color: '#fb923c', emissive: '#fb923c' },
  lighting:  { color: '#fbbf24', emissive: '#fbbf24' },
  water:     { color: '#38bdf8', emissive: '#38bdf8' },
  fire:      { color: '#fb7185', emissive: '#fb7185' },
  security:  { color: '#06b6d4', emissive: '#06b6d4' },
  solar_bess:{ color: '#facc15', emissive: '#facc15' },
}

function GridHelperMemo() {
  const grid = useMemo(() => new THREE.GridHelper(18, 18, 0x334155, 0x0c1222), [])
  return <primitive object={grid} position={[0, 0, 0]} />
}

const SITE_MAP_TEXTURES: Record<string, string> = {
  'site-002': '/images/sandton-map.png',
  'site-003': '/images/busamed-map.png',
}

function GroundPlane({ siteId, lat, lng }: { siteId?: string; lat?: number | null; lng?: number | null }) {
  const texPath = (siteId && SITE_MAP_TEXTURES[siteId]) || '/images/sandton-map.png'
  const mapTexture = useTexture(texPath)

  // For sites without a pre-downloaded map, overlay a GPS pin on a canvas
  const overlayTexture = useMemo(() => {
    if (siteId && SITE_MAP_TEXTURES[siteId]) return undefined
    if (!lat || !lng) return undefined
    const canvas = document.createElement('canvas')
    canvas.width = 512
    canvas.height = 512
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = '#0f172a'
    ctx.fillRect(0, 0, 512, 512)
    ctx.strokeStyle = '#1e293b'
    ctx.lineWidth = 1
    for (let x = 0; x <= 512; x += 64) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 512); ctx.stroke() }
    for (let y = 0; y <= 512; y += 64) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(512, y); ctx.stroke() }
    ctx.beginPath(); ctx.arc(256, 256, 12, 0, Math.PI * 2)
    ctx.fillStyle = '#22c55e'; ctx.fill()
    ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 3; ctx.stroke()
    ctx.fillStyle = '#94a3b8'; ctx.font = '14px sans-serif'; ctx.textAlign = 'center'
    ctx.fillText(siteId || '', 256, 440)
    ctx.fillText(`${lat?.toFixed(4)}, ${lng?.toFixed(4)}`, 256, 480)
    return new THREE.CanvasTexture(canvas)
  }, [lat, lng, siteId])

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 0]} receiveShadow>
      <planeGeometry args={[32, 32]} />
      <meshStandardMaterial
        map={mapTexture}
        color="#ffffff"
        metalness={0.05}
        roughness={0.95}
      />
    </mesh>
  )
}

type SlabInfo = {
  id: string
  intensity: number
  isManaged: boolean
  riskLevel: string
  equipmentHealth?: 'healthy' | 'degraded' | 'critical' | null
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
    // Gate on isManaged flag from the floor data — per-site managed floors.
    // Prevents the tracer from floating above the occupied stack.
    if (f.isManaged) {
      minY = Math.min(minY, cy - h / 2)
      maxY = Math.max(maxY, cy + h / 2)
    }
  }
  if (!Number.isFinite(minY)) return null
  return { minY, maxY }
}

function EquipmentHealthDot({ x, y, z, health }: { x: number; y: number; z: number; health: 'critical' | 'degraded' }) {
  const ref = useRef<THREE.Mesh>(null)
  const color = health === 'critical' ? '#ef4444' : '#facc15'
  useFrame(() => {
    if (!ref.current) return
    const t = performance.now() * 0.001
    ref.current.scale.setScalar(1 + Math.sin(t * 3) * 0.18)
  })
  return (
    <mesh ref={ref} position={[x, y, z]}>
      <sphereGeometry args={[0.09, 8, 8]} />
      <meshStandardMaterial
        color={color}
        emissive={color}
        emissiveIntensity={1.2}
        toneMapped={false}
      />
    </mesh>
  )
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
  systemFilter,
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
  systemFilter?: string | null
}) {
  const groupRef = useRef<THREE.Group>(null)
  const pal = cockpitFloorPalette(tone, floor.intensity, floor.isManaged, floor.riskLevel, systemFilter)

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
      {/* Equipment health dot: critical=red, degraded=amber at top-corner of slab */}
      {floor.equipmentHealth && floor.equipmentHealth !== 'healthy' && (
        <EquipmentHealthDot x={w * 0.38} y={h * 0.6} z={d * 0.38} health={floor.equipmentHealth} />
      )}
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
  systemFilter,
}: {
  floor: SlabInfo
  tone: ReturnType<typeof cockpitToneKey>
  y: number
  w: number
  d: number
  h: number
  systemFilter?: string | null
}) {
  // Force isManaged=false so host slabs always get neutral palette
  const pal = cockpitFloorPalette(tone, floor.intensity, false, floor.riskLevel, systemFilter)
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
  const siteId = state.site.id
  const geometry = state.site.buildingGeometry
  const slabW = siteWidth(siteId, undefined, geometry)
  const slabD = siteDepth(siteId, undefined, geometry)
  const geomFloorCount = geometryFloorCount(geometry)
  const floors = state.visualTwin.floors
  const waiting = state.site.renderState === 'waiting'
  const calm = !waiting && state.primaryMetric.value === 'Stable'
  const breath = Math.max(0.12, Math.min(1, state.visualTwin.breathingIntensity || 0.2))

  // Use the same health thresholds configured in Settings → Health Threshold panel
  const { thresholds } = useHealthThresholds()

  // Fetch equipment per site so we can show health indicators on floors
  const { data: equipmentData } = useQuery({
    queryKey: ['cockpit-equipment', state.site.id],
    queryFn: () => fetchApi<BuildingEquipmentResponse>(`/api/buildings/${state.site.id}/equipment`),
    enabled: state.site.id !== '',
    staleTime: 30_000,
  })

  // Build a floorId → worst equipment health map
  const floorEquipmentHealth = useMemo(() => {
    if (!equipmentData?.equipment) return new Map<string, 'healthy' | 'degraded' | 'critical' | null>()
    const map = new Map<string, 'healthy' | 'degraded' | 'critical' | null>()
    for (const eq of equipmentData.equipment) {
      const code = ((eq as { code?: string }).code || eq.id || '').toString()
      // Floor is 3rd segment e.g. S002-AHU-204 → floor L2 (office: 200-299 = floor N, zone = last 2)
      // or S002-AHU-L1-042 → floor L1 (hospital: explicit floor + zone)
      // or S002-FCU-B01 → floor B1 (basement)
      // or S002-INV-R01 → floor R (roof)
      const parts = code.split('-')
      let floorId = ''
      if (parts.length >= 3) {
        const thirdPart = parts[2]
        // Office 3-digit: 200-299 → L{floor}, e.g. 204 → L2
        const num = parseInt(thirdPart, 10)
        if (!isNaN(num) && num >= 200 && num <= 299) {
          floorId = `L${Math.floor(num / 100)}`
        }
        // Office 3-digit: 001-099 → L0 (ground floor)
        else if (!isNaN(num) && num >= 1 && num <= 99) {
          floorId = 'L0'
        }
        // Hospital: L{n}-ZZZ pattern, e.g. L1-042 → L1, L2-001 → L2
        else if (/^L\d+$/.test(thirdPart)) {
          floorId = thirdPart
        }
        // Basement: B01, B1, B2 → B1, B2
        else if (/^B\d+$/.test(thirdPart)) {
          floorId = `B${parseInt(thirdPart.slice(1), 10) || 1}`
        }
        // Roof: R01, ROOF → R
        else if (/^R\d*$/i.test(thirdPart) || thirdPart.toUpperCase() === 'ROOF') {
          floorId = 'R'
        }
      }
      if (!floorId) continue
      // Use thresholds from Settings → Health Score Thresholds panel
      const score = (eq as { health_score?: number }).health_score ?? 100
      const health: 'healthy' | 'degraded' | 'critical' =
        score >= thresholds.healthy ? 'healthy'
        : score >= thresholds.critical ? 'degraded'
        : 'critical'
      const worst = map.get(floorId)
      if (!worst) {
        map.set(floorId, health)
      } else if (worst !== 'critical' && health === 'critical') {
        map.set(floorId, 'critical')
      } else if (worst !== 'critical' && worst !== 'degraded' && health === 'degraded') {
        map.set(floorId, 'degraded')
      }
    }
    return map
  }, [equipmentData, thresholds])

  const slabs: SlabInfo[] = useMemo(() => {
    // When no floors from backend, render 5 generic placeholder slabs.
    // isManaged is driven by backend payload — all returned floors are occupied
    // tenant spaces (equipment-only floors like B1/R are excluded by the backend).
    const source = floors.length === 0
      ? Array.from({ length: 5 }).map((_, i) => ({
          id: `default-${i}`,
          intensity: 0.25,
          isManaged: true,
          riskLevel: 'stable',
        }))
      : floors.map((f) => ({
          id: f.id,
          intensity: f.intensity,
          isManaged: f.isManaged !== false,  // backend: false means equipment-only floor
          riskLevel: f.level,
        }))
    // Never render more than MAX_FLOORS slabs
    return source.slice(0, MAX_FLOORS)
  }, [floors, floorEquipmentHealth])

  // Derive slabs with equipment health attached
  const slabsWithEquipment: SlabInfo[] = useMemo(() => {
    return slabs.map((s) => ({
      ...s,
      equipmentHealth: floorEquipmentHealth.get(s.id),
    }))
  }, [slabs, floorEquipmentHealth])

  const reversed = [...slabsWithEquipment].reverse()
  const totalHeight = reversed.length * SLAB_HEIGHT

  // Compute cumulative Y positions for each floor (before render)
  const yPositions = reversed.reduce<number[]>((acc, _) => {
    const y = acc.length === 0 ? 0 : acc[acc.length - 1] + SLAB_HEIGHT
    return [...acc, y]
  }, [])

  return (
    <group position={[0, 0, 0]}>
      {/* Full host-tower cage so overall mass stays readable on dark scenes */}
      <mesh position={[0, totalHeight / 2, 0]} receiveShadow>
        <boxGeometry args={[slabW * 1.04, totalHeight, slabD * 1.04]} />
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
        const y = yPositions[index] + h / 2
        const setback = 1 - index * 0.0045
        const w = slabW * setback
        const d = slabD * setback

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
              systemFilter={state.systemFilter}
            />
          )
        }
        return <HostSlab key={floor.id} floor={floor} tone={tone} y={y} w={w} d={d} h={h} systemFilter={state.systemFilter} />
      })}
    </group>
  )
}

function DriftPath({
  state,
  tone,
  targetOpacity,
  yRange,
}: {
  state: CockpitState
  tone: ReturnType<typeof cockpitToneKey>
  targetOpacity: number
  yRange: { minY: number; maxY: number } | null
}) {
  const color = cockpitFlowColor(tone)

  // Always call useMemo — returning null before hooks violates Rules of Hooks
  const points = useMemo(() => {
    if (!yRange) return []
    const curves: THREE.Vector3[] = []
    const segs = 16
    const y0 = yRange.minY + 0.04
    const y1 = yRange.maxY - 0.04
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
      opacity={targetOpacity}
      depthWrite={false}
    />
  )
}

function AnimatedTracer({
  tone,
  yRange,
  active,
  speed = 0.42,
  opacity = 1,
}: {
  tone: ReturnType<typeof cockpitToneKey>
  yRange: { minY: number; maxY: number } | null
  active: boolean
  speed?: number
  opacity?: number
}) {
  const tracerRef = useRef<THREE.Mesh>(null)
  const haloRef = useRef<THREE.Mesh>(null)
  const color = cockpitFlowColor(tone)
  const currentOpacity = useRef(opacity)
  const targetRef = useRef(opacity)

  useEffect(() => {
    targetRef.current = opacity
  }, [opacity])

  useFrame(() => {
    if (!tracerRef.current || !haloRef.current || !yRange) return
    const t = performance.now() * 0.001
    const effectiveSpeed = active ? speed : speed * 0.57
    const phase = (t * effectiveSpeed) % 1
    const y = yRange.minY + (yRange.maxY - yRange.minY) * phase
    const spiral = phase * Math.PI * 2.2
    const x = Math.sin(spiral) * 0.52 + 0.12
    const z = Math.cos(spiral) * 0.44 + 0.16
    tracerRef.current.position.set(x, y, z)
    haloRef.current.position.set(x, y, z)
    const pulse = 0.65 + 0.35 * Math.sin(t * 8)
    tracerRef.current.scale.setScalar(0.9 + pulse * 0.35)
    haloRef.current.scale.setScalar(1.6 + pulse * 0.5)

    // Smooth opacity crossfade
    currentOpacity.current += (targetRef.current - currentOpacity.current) * 0.1
    const co = currentOpacity.current
    const tracerMat = tracerRef.current.material as THREE.MeshStandardMaterial
    const haloMat = haloRef.current.material as THREE.MeshStandardMaterial
    tracerMat.opacity = co * 0.98
    haloMat.opacity = co * 0.38
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

/** Energy busbar glow — vertical riser lines that pulse with load intensity */
function EnergyBusbarLayer({
  opacity,
  buildingHeight,
}: {
  opacity: number
  buildingHeight: number
}) {
  const lineRefs = useRef<THREE.Mesh[]>([])
  const currentOpacity = useRef(opacity)
  const targetRef = useRef(opacity)

  useEffect(() => {
    targetRef.current = opacity
  }, [opacity])

  useFrame(() => {
    currentOpacity.current += (targetRef.current - currentOpacity.current) * 0.1
    const co = currentOpacity.current
    const t = performance.now() * 0.001
    lineRefs.current.forEach((mesh, i) => {
      if (!mesh) return
      const mat = mesh.material as THREE.MeshStandardMaterial
      mat.opacity = co * (0.55 + 0.25 * Math.sin(t * 2.5 + i * 1.3))
      const pulse = 0.8 + 0.2 * Math.sin(t * 3 + i * 0.7)
      mat.emissiveIntensity = co * pulse * 1.2
    })
  })

  const lines = useMemo(() => {
    const items: { x: number; z: number; color: string }[] = [
      { x: -0.35, z: -0.25, color: '#fb923c' },
      { x: 0.35, z: -0.25, color: '#f97316' },
      { x: 0, z: 0.3, color: '#fdba74' },
    ]
    return items
  }, [])

  return (
    <group>
      {lines.map((line, i) => (
        <mesh
          key={`busbar-${i}`}
          ref={(el) => {
            if (el) lineRefs.current[i] = el
          }}
          position={[line.x, buildingHeight * 0.5, line.z]}
        >
          <cylinderGeometry args={[0.015, 0.015, buildingHeight * 0.9, 8]} />
          <meshStandardMaterial
            color={line.color}
            emissive={line.color}
            emissiveIntensity={1.2}
            transparent
            opacity={0}
            depthWrite={false}
          />
        </mesh>
      ))}
    </group>
  )
}

/** Deterministic hash for stable orb positioning — no Math.random(), no Date.now() */
function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash) + str.charCodeAt(i)
    hash |= 0
  }
  return hash
}

function ZoneMarkers({
  state,
  buildingHeight: _buildingHeight,
  onboardingPhase,
  onZoneSelect,
  slabW: zoneSlabW,
  slabD: zoneSlabD,
}: {
  state: CockpitState
  buildingHeight: number
  onboardingPhase: string | null
  onZoneSelect?: (sig: import('./types').CockpitTwinZoneSignal) => void
  slabW: number
  slabD: number
}) {
  // Shadow mode has no active conditions — no orbs
  if (onboardingPhase === 'shadow') return null

  const signals = state.visualTwin.zoneSignals
    .filter((sig) => (sig.weight ?? 0) > 0.15)
    .slice(0, 5)
  const floors = state.visualTwin.floors
  const totalFloors = Math.max(floors.length, 1)

  return (
    <group>
      {signals.map((sig, index) => {
        const fi = floors.findIndex((f) => f.id === sig.floorId)
        const targetFloor = fi >= 0 ? floors[fi] : null
        // Skip orbs whose floorId doesn't match any floor (would render outside the building)
        if (fi < 0 || !targetFloor || !targetFloor.isManaged) return null
        // reversedIndex: 0 = bottom floor (L0), increases upward — matches BuildingStack slab Y math
        const reversedIndex = totalFloors - 1 - fi
        const y = reversedIndex * SLAB_HEIGHT + SLAB_HEIGHT / 2

        // Deterministic hash-based position within floor footprint (70% of base)
        const seedA = hashString(sig.zoneId)
        const seedB = hashString(sig.meshId || sig.zoneId + '-b')
        const xNorm = ((seedA % 1000) / 1000) * 2 - 1 // -1 to 1
        const zNorm = ((seedB % 1000) / 1000) * 2 - 1 // -1 to 1
        const x = xNorm * (zoneSlabW * 0.35)
        const z = zNorm * (zoneSlabD * 0.35)

        // Primary signal gets larger, brighter orb
        const isPrimary = sig.isPrimary === true
        const radius = isPrimary ? 0.11 : 0.07
        const emissiveIntensity = isPrimary ? 1.4 : 0.9
        const orbColor = (state.systemFilter && SYSTEM_ORB_COLORS[state.systemFilter])
          ?? { color: '#f8fafc', emissive: '#ffffff' }

        return (
          <mesh
            key={`${sig.zoneId}-${index}`}
            position={[x, y, z]}
            onClick={(e) => {
              e.stopPropagation()
              onZoneSelect?.(sig)
            }}
          >
            <sphereGeometry args={[radius, 16, 16]} />
            <meshStandardMaterial
              color={orbColor.color}
              emissive={orbColor.emissive}
              emissiveIntensity={emissiveIntensity}
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

function SceneR3F({
  state,
  controlsRef,
  defaultCam,
  computedTarget,
  modelScale,
  onZoneSelect,
}: {
  state: CockpitState
  controlsRef: MutableRefObject<OrbitControlsImpl | null>
  defaultCam: THREE.Vector3
  computedTarget: THREE.Vector3
  modelScale: number
  onZoneSelect?: (sig: import('./types').CockpitTwinZoneSignal) => void
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

  // System-driven animation layer targets
  const systemFilter = state.systemFilter
  const isHVAC = systemFilter === 'hvac'
  const isEnergy = systemFilter === 'energy'
  const hvacTarget = isHVAC ? 1 : systemFilter ? 0 : showFlow ? 1 : 0
  const energyTarget = isEnergy ? 1 : 0
  const tracerSpeed = TRACER_SPEEDS[systemFilter ?? ''] ?? TRACER_SPEEDS.default

  const worldHalf = buildingHeight * modelScale * 0.5
  const fogFar = Math.max(18, worldHalf * 4.5)
  const siteId = state.siteId
  const buildingGeometry = state.site.buildingGeometry
  const mainSlabW = siteWidth(siteId, undefined, buildingGeometry)
  const mainSlabD = siteDepth(siteId, undefined, buildingGeometry)

  return (
    <>
      <color attach="background" args={['#020617']} />
      <fog attach="fog" args={['#020617', 12, fogFar]} />

      <ambientLight intensity={0.52} />
      <directionalLight position={[6, 14, 8]} intensity={1.3} castShadow shadow-mapSize-width={1024} shadow-mapSize-height={1024} />
      <directionalLight position={[-5, 6, -4]} intensity={0.6} color="#67e8f9" />
      <directionalLight position={[0, 4, -9]} intensity={0.44} color="#e2e8f0" />
      <hemisphereLight args={['#0ea5e9', '#0b1120', 0.3]} />

      <GroundPlane siteId={state.siteId} lat={state.site.latitude} lng={state.site.longitude} />

      <GridHelperMemo />

      <group scale={[modelScale, modelScale, modelScale]} rotation={[0, THREE.MathUtils.degToRad(state.site.orientationDegrees ?? 0), 0]}>
        <BuildingStack state={state} tone={tone} />
        <DriftPath state={state} tone={tone} targetOpacity={hvacTarget} yRange={yRange} />
        <AnimatedTracer tone={tone} yRange={yRange} active={showFlow} speed={tracerSpeed} opacity={hvacTarget} />
        <EnergyBusbarLayer opacity={energyTarget} buildingHeight={buildingHeight} />
        <ZoneMarkers
          state={state}
          buildingHeight={buildingHeight}
          onboardingPhase={state.site.onboardingPhase ?? null}
          onZoneSelect={onZoneSelect}
          slabW={mainSlabW}
          slabD={mainSlabD}
        />
      </group>

      <OrbitControls
        ref={controlsRef}
        makeDefault
        enableDamping
        dampingFactor={0.08}
        minDistance={Math.max(2.5, worldHalf * 0.7)}
        maxDistance={Math.max(14, worldHalf * 3.2)}
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

export function CockpitBuildingThree({ state, className, onZoneSelect }: CockpitBuildingThreeProps) {
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
    const cam = new THREE.Vector3(wh * 2.1, wh * 1.4, wh * 2.9)
    return { computedTarget: target, defaultCam: cam }
  }, [buildingHeight, modelScale])

  const { computedTarget, defaultCam } = layout

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
            onZoneSelect={onZoneSelect}
          />
        </Suspense>
      </Canvas>
      <div className="pointer-events-none absolute bottom-2 left-3 max-w-[90%] text-[10px] uppercase tracking-[0.16em] text-slate-500">
        Drag orbit · Wheel zoom · Right-drag pan · Double-click reset · Sentinel scope: occupied levels only
      </div>
    </div>
  )
}

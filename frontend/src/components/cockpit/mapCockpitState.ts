import type { CockpitGuidanceMode, CockpitHealthState, CockpitState, CockpitTwinRiskLevel } from './types'
import type { HVACOverview } from '@/lib/hvacApi'

export interface BuildingStateLocation {
  epicenter: string
  affected: string[]
  propagation: 'contained' | 'upward' | 'downward' | 'lateral' | 'building_wide'
}

export interface BuildingStateNarrative {
  voice: 'comfort_stress' | 'asset_stress' | 'energy_pressure' | 'operational_stability' | 'occupant_friction'
  message: string
  location: BuildingStateLocation
  time_to_breach_min?: number | null
  urgency: CockpitGuidanceMode
  action: string
}

export interface BuildingStateSecondaryTension {
  voice: BuildingStateNarrative['voice']
  message: string
}

export interface BuildingStatePayload {
  site_id: string
  building_posture: 'calm' | 'drifting' | 'compensating' | 'strained' | 'critical'
  primary_narrative: BuildingStateNarrative | null
  secondary_tensions: BuildingStateSecondaryTension[]
  operator_guidance: {
    headline: string
    mode: CockpitGuidanceMode
  }
  urgency_score?: number | null
  affected_zone_ids?: string[] | null
  /** Email complaint clusters with count >= 3 — rendered as heatmap signals */
  email_clusters?: EmailClusterRaw[]
}

export interface EmailClusterRaw {
  cluster_id: string
  zone_id: string
  zone_name: string
  floor: string
  email_count: number
  complaint_type: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  summary: string
}

export interface CockpitSiteSummary {
  siteId: string
  siteName: string
  gpsLat?: number | null
  gpsLon?: number | null
  orientationDegrees?: number | null
  onboardingPhase?: 'shadow' | 'advisory' | 'supervised' | 'auto'
  posture?: string | null
  activeAlerts: number
  predictionsCount: number
  equipmentCount: number
  dataFreshnessLabel: string
  siteFloors?: string[] | null // floors from building config (settings page)
  buildingGeometry?: Record<string, unknown> | null // geometry from photo extraction
}

export interface EnergyCentreTelemetry {
  totalKw: number
  hvacKw: number
  lightingKw: number
  powerKw: number
  powerPercent: number
  timestamp?: string
}

export interface RemoteSiteTelemetry {
  source?: string
  power?: Record<string, unknown>
  hvac?: Record<string, unknown>
  lighting?: Record<string, unknown>
  water?: Record<string, unknown>
  fire?: Record<string, unknown>
  security?: Record<string, unknown>
  [key: string]: unknown
}

const DEFAULT_FLOOR_ORDER = ['R', 'L2', 'L1', 'L0', 'G', 'B1']

type TowerProfile = {
  towerFloors: string[];
  managedFloors: string[];
  /** Slab width multiplier relative to BASE_WIDTH (1.0 = office default). */
  widthScale?: number;
  /** Slab depth multiplier relative to BASE_DEPTH (1.0 = office default). */
  depthScale?: number;
};

const SITE_TOWER_PROFILES: Record<string, TowerProfile> = {
  'site-002': {
    // Sandton City Office Tower: slender high-rise.
    towerFloors: ['R', 'L7', 'L6', 'L5', 'L4', 'L3', 'L2', 'L1', 'L0', 'B1'],
    managedFloors: ['L0', 'L1', 'L2'],
    widthScale: 1.0,
    depthScale: 1.0,
  },
  'site-005': {
    // Busamed Gateway Private Hospital: wider, lower hospital profile.
    towerFloors: ['L9', 'L8', 'L7', 'L6', 'L5', 'L4', 'L3', 'L2', 'L1', 'G'],
    managedFloors: ['G', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8', 'L9'],
    widthScale: 1.6,  // Hospital is wider
    depthScale: 1.4,  // Hospital is deeper
  },
};

function titleCase(value: string): string {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function formatPostureLabel(posture: BuildingStatePayload['building_posture'] | string | null | undefined): string {
  if (!posture) return 'Waiting'
  // Map internal posture states to clearer client-facing labels
  const postureMap: Record<string, string> = {
    'calm': 'Calm',
    'drifting': 'Drifting — safe bounds',
    'compensating': 'Compensating',
    'strained': 'Strained',
    'critical': 'Critical',
  }
  return postureMap[posture] || titleCase(posture)
}

function formatVoiceLabel(voice: BuildingStateNarrative['voice'] | string): string {
  return titleCase(voice)
}

function extractFloorCode(value: string | null | undefined): string | null {
  if (!value) return null
  const match = value.match(/(?:^|-|→)(R|L\d+|G|B\d+)(?:-|$|\s)/i)
  return match?.[1]?.toUpperCase() ?? null
}

function formatFloorLabel(floorId: string): string {
  if (floorId === 'B1') return 'Basement'
  if (floorId === 'L0') return 'Ground Floor'
  if (floorId === 'L1') return 'First Floor'
  if (floorId === 'L2') return 'Second Floor'
  if (floorId === 'L3') return 'Third Floor'
  if (floorId === 'R') return 'Roof'
  if (floorId === 'G') return 'Ground'
  if (floorId.startsWith('B')) return `Basement ${floorId.slice(1)}`
  if (floorId.startsWith('L')) return `Level ${floorId.slice(1)}`
  return floorId
}

function toneFromPosture(posture: BuildingStatePayload['building_posture'] | null | undefined): CockpitState['primaryMetric']['tone'] {
  if (posture === 'critical') return 'critical'
  if (posture === 'strained') return 'elevated'
  if (posture === 'drifting' || posture === 'compensating') return 'warning'
  return 'normal'
}

function riskBandFromPosture(posture: BuildingStatePayload['building_posture'] | null | undefined): CockpitState['severity']['riskBand'] {
  if (posture === 'critical') return 'critical'
  if (posture === 'strained') return 'high'
  if (posture === 'drifting' || posture === 'compensating') return 'medium'
  return 'low'
}

function riskLevelFromTone(tone: CockpitState['primaryMetric']['tone']): CockpitTwinRiskLevel {
  if (tone === 'critical') return 'critical'
  if (tone === 'elevated') return 'approaching'
  if (tone === 'warning') return 'drift'
  return 'stable'
}

function buildFloorOrder(siteId: string, focusFloorId: string | null, affectedFloors: string[], siteFloors?: string[] | null): string[] {
  // When siteFloors is provided (from building config / settings page), use it directly
  // as both the tower floor order and the managed scope. Each site defines its own floors.
  const baseOrder = siteFloors?.length
    ? [...siteFloors]
    : [...(SITE_TOWER_PROFILES[siteId]?.towerFloors ?? DEFAULT_FLOOR_ORDER)]
  const order = [...baseOrder]
  for (const floorId of affectedFloors) {
    if (!order.includes(floorId)) order.push(floorId)
  }
  if (focusFloorId && !order.includes(focusFloorId)) {
    order.unshift(focusFloorId)
  }
  return order
}

function locationSummary(narrative: BuildingStateNarrative | null): string {
  if (!narrative) return 'Whole building'
  const { epicenter, affected, propagation } = narrative.location
  // Avoid duplication: don't repeat epicenter when affected is empty
  if (affected.length === 0) {
    return `${epicenter} · ${titleCase(propagation)}`
  }
  const affectedSummary = affected.join(' → ')
  return `${epicenter} · ${affectedSummary} · ${titleCase(propagation)}`
}

function buildUnavailableState(summary: CockpitSiteSummary): CockpitState {
  return {
    site: {
      id: summary.siteId,
      name: summary.siteName,
      latitude: summary.gpsLat ?? null,
      longitude: summary.gpsLon ?? null,
      orientationDegrees: summary.orientationDegrees ?? null,
      onboardingPhase: summary.onboardingPhase ?? 'shadow',
      posture: 'Waiting',
      mode: 'waiting',
      renderState: 'waiting',
      dataFreshnessLabel: summary.dataFreshnessLabel,
      buildingGeometry: summary.buildingGeometry ?? null,
    },
    sitePulse: {
      tone: 'normal',
      attentionScore: 0.1,
      activeConditionCount: 0,
      emergingRiskCount: 0,
      equipmentWarningCount: 0,
      evidenceStrength: 'limited',
    },
    primaryMetric: {
      tone: 'normal',
      label: 'Live State',
      value: 'Waiting',
      detail: `Waiting for ${summary.siteName} to begin reporting live state.`,
    },
    activeCondition: {
      summary: 'Awaiting building signal',
      rationale: `No live state from ${summary.siteName} yet.`,
      confidenceLabel: 'Waiting',
    },
    decision: {
      impact: 'Waiting',
      summary: 'Watch for live building state',
      tradeoff: 'No operator action required until live state arrives.',
      confidence: 'Waiting',
    },
    visualTwin: {
      headline: 'Awaiting building signal',
      activeLabel: summary.siteName,
      modeLabel: 'Waiting',
      motionProfile: 'waiting',
      breathingIntensity: 0.12,
      flowSpeed: 0.9,
      consumptionIntensity: 0.12,
      focusFloorId: null,
      floors: buildFloorOrder(summary.siteId, null, [], summary.siteFloors).map((floorId, index, order) => ({
        id: floorId,
        label: formatFloorLabel(floorId),
        meshId: `floor:${floorId}`,
        level: 'stable',
        intensity: 0.14,
        spread: 0,
        elevation: (order.length - index - 1) * 2.25,
        isManaged: (summary.siteFloors ?? SITE_TOWER_PROFILES[summary.siteId]?.managedFloors ?? order).includes(floorId),
      })),
      zoneSignals: [],
      flowPaths: [],
      energyCentre: {
        online: false,
        totalKw: 0,
        hvacKw: 0,
        lightingKw: 0,
        powerKw: 0,
        loadRatio: 0.12,
        powerShareRatio: 0,
        stateLabel: 'low',
      },
    },
    evidence: {
      strength: 'limited',
      summary: 'Waiting for live building state.',
      refs: [],
    },
    severity: {
      riskScore: null,
      riskBand: 'medium',
      thresholdReason: null,
      policySource: null,
      policyLevel: null,
      constraintType: null,
      timeToConstraintBreachMin: null,
      affectedScope: null,
      healthScore: null,
      healthState: null,
      healthTrend: null,
      healthReason: null,
      assetClass: null,
      criticality: null,
    },
    emergingRisks: [],
    equipmentWarnings: [],
    emailClusters: [],
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}

function riskBandFromScore(
  score: number,
  bands: { low: number; medium: number; high: number; critical: number },
): string {
  if (score >= bands.critical) return 'critical'
  if (score >= bands.high) return 'high'
  if (score >= bands.medium) return 'medium'
  return 'low'
}

function riskLevelFromBand(band: string): CockpitTwinRiskLevel {
  if (band === 'critical') return 'critical'
  if (band === 'high') return 'approaching'
  if (band === 'medium') return 'drift'
  return 'stable'
}

function buildTwinFloors(
  siteId: string,
  floorOrder: string[],
  focusFloorId: string | null,
  urgencyScore: number,
  floorLabels: Record<string, string> | null | undefined,
  bands: { low: number; medium: number; high: number; critical: number },
  affectedZoneIds: string[],
  siteFloors?: string[] | null,
): Array<{
  id: string
  label: string
  meshId: string
  level: CockpitTwinRiskLevel
  intensity: number
  spread: number
  elevation: number
  isManaged: boolean
}> {
  // Floors with direct signals — only these receive non-stable risk levels.
  // All other floors render as inert host mass regardless of urgencyScore.
  const directlyAffectedFloors = new Set<string>()
  if (focusFloorId) directlyAffectedFloors.add(focusFloorId)
  for (const zoneId of affectedZoneIds) {
    const code = extractFloorCode(zoneId)
    if (code) directlyAffectedFloors.add(code)
  }

  const anchorIndex = focusFloorId ? floorOrder.indexOf(focusFloorId) : -1
  const managedFloors = siteFloors?.length ? siteFloors : (SITE_TOWER_PROFILES[siteId]?.managedFloors ?? [])

  return floorOrder.map((floorId, index) => {
    const isManaged = managedFloors.includes(floorId)
    const isDirectlyAffected = directlyAffectedFloors.has(floorId)

    // Spread calculated for directly affected floors only; non-affected floors
    // are hard-gated to stable regardless of urgencyScore.
    const distance = anchorIndex >= 0 ? Math.abs(index - anchorIndex) : Number.POSITIVE_INFINITY
    const spread = isDirectlyAffected && anchorIndex >= 0
      ? clamp01(urgencyScore - distance * 0.22)
      : 0
    const riskScore = index === anchorIndex ? urgencyScore : spread * 0.9

    const level = isDirectlyAffected
      ? riskLevelFromBand(riskBandFromScore(riskScore, bands))
      : 'stable'

    const intensity = isDirectlyAffected
      ? clamp01(0.18 + spread * 0.82)
      : 0.16

    return {
      id: floorId,
      label: floorLabels?.[floorId] ?? formatFloorLabel(floorId),
      meshId: `floor:${floorId}`,
      level,
      intensity,
      spread: isManaged ? spread : 0,
      elevation: (floorOrder.length - index - 1) * 2.25,
      isManaged,
    }
  })
}

function normalizeHvacSignal(
  hvacOverview?: HVACOverview | null,
  energyCentre?: EnergyCentreTelemetry | null,
): { intensity: number; flowSpeed: number } {
  if (!hvacOverview && !energyCentre) return { intensity: 0.22, flowSpeed: 1.05 }

  const hvacKw = hvacOverview?.raw_telemetry?.power?.hvac_kw ?? 0
  const zoneTotal = hvacOverview?.zones.total ?? 0
  const zoneFault = hvacOverview?.zones.fault ?? 0
  const zoneOffline = hvacOverview?.zones.offline ?? 0
  const faultRatio = zoneTotal > 0 ? (zoneFault + zoneOffline) / zoneTotal : 0
  const alertPressure = clamp((hvacOverview?.alerts.length ?? 0) / 8, 0, 1)
  const loadPressure = clamp(hvacKw / 1200, 0, 1)
  const energyLoadPressure = clamp((energyCentre?.totalKw ?? 0) / 1800, 0, 1)
  const electricalPressure = clamp((energyCentre?.powerPercent ?? 0) / 100, 0, 1)

  const intensity = clamp(
    0.18
      + faultRatio * 0.36
      + alertPressure * 0.24
      + loadPressure * 0.24
      + energyLoadPressure * 0.18
      + electricalPressure * 0.12,
    0.18,
    1,
  )
  const flowSpeed = clamp(0.9 + intensity * 2.2, 0.9, 3.2)
  return { intensity, flowSpeed }
}

function normalizeConsumptionIntensity(energyCentre?: EnergyCentreTelemetry | null): number {
  if (!energyCentre) return 0.22
  const siteLoad = clamp((energyCentre.totalKw || 0) / 1800, 0, 1)
  const powerShare = clamp((energyCentre.powerPercent || 0) / 100, 0, 1)
  return clamp(siteLoad * 0.78 + powerShare * 0.22, 0.12, 1)
}

function energyStateLabel(loadRatio: number): 'low' | 'moderate' | 'high' | 'critical' {
  if (loadRatio >= 0.82) return 'critical'
  if (loadRatio >= 0.62) return 'high'
  if (loadRatio >= 0.35) return 'moderate'
  return 'low'
}

function inferModuleRefsFromTelemetry(telemetry?: RemoteSiteTelemetry | null): string[] {
  if (!telemetry) return []
  const refs: string[] = []
  const push = (name: string) => refs.push(`module:${name}`)

  if (telemetry.hvac || 'zones' in telemetry) push('hvac')
  if (telemetry.power || 'energy' in telemetry) push('energy')
  if (telemetry.lighting || 'dali' in telemetry) push('lighting')
  if (telemetry.water) push('water')
  if (telemetry.fire) push('fire')
  if (telemetry.security) push('security')
  if (typeof telemetry.source === 'string' && telemetry.source.toLowerCase().includes('remote')) push('remote-bms')

  return Array.from(new Set(refs))
}

function buildShadowTelemetrySummary(
  hvacOverview?: HVACOverview | null,
  energyCentre?: EnergyCentreTelemetry | null,
): string {
  const hvacKw = Math.round(hvacOverview?.raw_telemetry?.power?.hvac_kw ?? 0)
  const zoneTotal = hvacOverview?.zones.total ?? 0
  const zoneFault = hvacOverview?.zones.fault ?? 0
  const zoneOffline = hvacOverview?.zones.offline ?? 0
  const totalKw = Math.round(energyCentre?.totalKw ?? 0)

  if (zoneTotal > 0) {
    if (zoneFault + zoneOffline >= Math.max(1, Math.floor(zoneTotal * 0.25))) {
      return `HVAC stress is rising: ${zoneFault + zoneOffline}/${zoneTotal} zones degraded, ${hvacKw} kW load.`
    }
    if (hvacKw >= 700) {
      return `HVAC demand is elevated at ${hvacKw} kW with stable zone coverage.`
    }
    if (totalKw >= 1200) {
      return `Building electrical demand is high (${totalKw} kW) while HVAC remains in observation.`
    }
  }

  if (hvacKw > 0) {
    return `HVAC is tracking at ${hvacKw} kW with telemetry-only observation active.`
  }
  if (totalKw > 0) {
    return `Energy Centre load is ${totalKw} kW under shadow observation mode.`
  }
  return 'Telemetry indicates stable operation.'
}

function flowPathsFromNarrative(narrative: BuildingStateNarrative | null): Array<{
  id: string
  d: string
  fromFloorId: string | null
  toFloorId: string | null
  direction: BuildingStateLocation['propagation']
}> {
  if (!narrative) return []

  const direction = narrative.location.propagation
  const fromFloorId = extractFloorCode(narrative.location.epicenter)
  const toFloorId = (narrative.location.affected || [])
    .map((zone) => extractFloorCode(zone))
    .find((floor): floor is string => Boolean(floor)) ?? fromFloorId

  const pathMap: Record<BuildingStateLocation['propagation'], string[]> = {
    contained: ['M356 387 C362 358 366 336 372 312'],
    upward: [
      'M356 390 C376 346 390 318 396 276 C400 238 405 206 416 172',
      'M344 396 C362 360 370 328 374 292 C378 248 380 210 388 176',
    ],
    downward: [
      'M402 174 C396 210 392 242 388 278 C382 322 374 354 356 390',
      'M388 176 C382 210 376 244 368 284 C364 326 358 358 344 396',
    ],
    lateral: [
      'M292 316 C332 290 366 286 408 294 C440 302 472 310 512 304',
      'M292 316 C336 332 370 334 412 326 C454 318 484 306 512 304',
    ],
    building_wide: [
      'M272 338 C314 290 350 260 392 238 C434 216 470 188 512 138',
      'M260 210 C312 220 356 244 392 278 C428 312 468 334 520 346',
    ],
  }

  return pathMap[direction].map((d, index) => ({
    id: `flow-${direction}-${index}`,
    d,
    fromFloorId,
    toFloorId,
    direction,
  }))
}

export interface EquipmentWarningInput {
  id: string
  equipment_id: string
  code: string
  equipment_type: string
  floor_id: string
  health_score: number
  health_state: 'healthy' | 'degraded' | 'critical'
  fault_type?: string
  zone_id?: string
}

export function mapCockpitState(
  summary: CockpitSiteSummary,
  payload?: BuildingStatePayload | null,
  hvacOverview?: HVACOverview | null,
  energyCentreTelemetry?: EnergyCentreTelemetry | null,
  remoteTelemetry?: RemoteSiteTelemetry | null,
  systemFilter?: string | null,
  equipmentWarnings?: EquipmentWarningInput[] | null,
): CockpitState {
  if (!payload) return buildUnavailableState(summary)

  const onboardingPhase = summary.onboardingPhase ?? 'shadow'
  const isShadowPhase = onboardingPhase === 'shadow'
  const tone = toneFromPosture(payload.building_posture)
  const riskBand = riskBandFromPosture(payload.building_posture)
  // --- System-filtered narrative selection ---
  // Map systemFilter to the voice types that belong to that system.
  // When a system tab is active, prefer a matching narrative; fall back to the
  // first available narrative so the right rail never goes blank.
  const SYSTEM_VOICE_MAP: Record<string, BuildingStateNarrative['voice'][]> = {
    hvac:     ['comfort_stress', 'occupant_friction', 'asset_stress'],
    energy:   ['energy_pressure'],
    lighting: [],
    water:    [],
    fire:     [],
    security: [],
     "solar-bess": ['energy_pressure'],
  }
  const matchVoices = systemFilter ? (SYSTEM_VOICE_MAP[systemFilter] ?? []) : []
  // When a tab is active but has no mapped voices (e.g. lighting, water),
  // suppress the fallback to primary_narrative so unrelated HVAC content
  // doesn't bleed into other system views.
  const systemNarrative = matchVoices.length > 0
    ? payload.primary_narrative
      ? matchVoices.includes(payload.primary_narrative.voice)
        ? payload.primary_narrative
        : null
      : null
    : null

  const narrative = systemFilter ? systemNarrative : (systemNarrative ?? payload.primary_narrative)

  // Filter secondary tensions by system voice when a system tab is active
  const secondaryTensions = matchVoices.length > 0
    ? payload.secondary_tensions.filter((t) => matchVoices.includes(t.voice))
    : payload.secondary_tensions
  const urgencyScore = payload.urgency_score ?? 0
  const bands = { low: 0.3, medium: 0.5, high: 0.7, critical: 0.9 }
  const timeToBreach = narrative?.time_to_breach_min ?? null
  const timeValue = timeToBreach === null ? 'Stable' : `${timeToBreach} min`
  const focusFloorId = extractFloorCode(narrative?.location.epicenter)
  const narrativeAffectedFloors = (narrative?.location.affected ?? [])
    .map((zone) => extractFloorCode(zone))
    .filter((floorId): floorId is string => floorId !== null)
  const floorOrder = buildFloorOrder(summary.siteId, focusFloorId, narrativeAffectedFloors, summary.siteFloors)
  const zoneSignals = narrative
    ? [narrative.location.epicenter, ...narrative.location.affected].map((zoneId, index) => {
        const floorId = extractFloorCode(zoneId) ?? focusFloorId ?? floorOrder[Math.min(index, floorOrder.length - 1)] ?? 'L0'
        return {
          zoneId,
          label: zoneId.replace(/^Zone-/, '').replace(/-/g, ' '),
          floorId,
          meshId: `mesh:${zoneId.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
          level: index === 0 ? riskLevelFromTone(tone) : tone === 'critical' ? 'approaching' : riskLevelFromTone(tone),
          weight: Math.max(0.2, 1 - index * 0.18),
          slot: index,
          isPrimary: index === 0,
          actionLabel: narrative.action,
        }
      })
    : []
  const hvacSignal = normalizeHvacSignal(hvacOverview, energyCentreTelemetry)
  const consumptionIntensity = normalizeConsumptionIntensity(energyCentreTelemetry)
  const energyLoadRatio = clamp((energyCentreTelemetry?.totalKw ?? 0) / 1800, 0, 1)
  const energyPowerShare = clamp((energyCentreTelemetry?.powerPercent ?? 0) / 100, 0, 1)
  const shadowSummary = buildShadowTelemetrySummary(hvacOverview, energyCentreTelemetry)
  const remoteModuleRefs = inferModuleRefsFromTelemetry(remoteTelemetry)
  const flowPaths = flowPathsFromNarrative(narrative).map((path, index) => ({
    ...path,
    intensity: clamp(hvacSignal.intensity - index * 0.1, 0.25, 1),
  }))

  // --- Email cluster heatmap: merge into zoneSignals ---
  const emailClusters = (payload.email_clusters ?? []).map((c) => ({
    clusterId: c.cluster_id,
    zoneId: c.zone_id,
    zoneName: c.zone_name,
    floor: c.floor,
    emailCount: c.email_count,
    complaintType: c.complaint_type,
    severity: c.severity,
    summary: c.summary,
  }))

  // Build a map of zoneId → cluster for quick lookup
  const clusterByZone: Record<string, (typeof emailClusters)[0]> = {}
  for (const c of emailClusters) {
    clusterByZone[c.zoneId] = c
  }

  // If a zone has an email cluster, add it as intakeCluster on the existing zoneSignal
  let zoneSignalsWithClusters = zoneSignals.map((signal) => {
    const cluster = clusterByZone[signal.zoneId]
    if (cluster && cluster.emailCount >= 3) {
      return { ...signal, intakeCluster: cluster }
    }
    return signal
  })

  // Add zone signals for clusters that don't have a BMS narrative yet (standalone clusters)
  const existingZoneIds = new Set(zoneSignals.map((s) => s.zoneId))
  const standaloneClusters = emailClusters.filter(
    (c) => c.emailCount >= 3 && !existingZoneIds.has(c.zoneId)
  )
  for (const cluster of standaloneClusters) {
    zoneSignalsWithClusters.push({
      zoneId: cluster.zoneId,
      label: cluster.zoneName.replace(/^Zone-/, '').replace(/-/g, ' '),
      floorId: cluster.floor,
      meshId: `mesh:${cluster.zoneId.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
      level: cluster.severity === 'critical' ? 'critical' : cluster.severity === 'high' ? 'approaching' : 'drift',
      weight: 1,
      slot: zoneSignalsWithClusters.length,
      isPrimary: false,
      actionLabel: `${cluster.emailCount}x occupant`,
      intakeCluster: cluster,
    })
  }

  // --- Inject representative equipment zone signals when system tab is active
  // but no matching narrative exists — ensures the 3D building always shows
  // relevant orbs regardless of which system the operator has selected.
  const SYSTEM_EQUIPMENT_ZONES: Record<string, Array<{ zoneId: string; floorId: string; label: string; level: CockpitTwinRiskLevel }>> = {
    energy: [
      { zoneId: 'Zone-B1-001', floorId: 'B1', label: 'Chiller & Meter', level: 'stable' },
    ],
    lighting: [
      { zoneId: 'Zone-L1-A', floorId: 'L1', label: 'DALI Controller L1', level: 'stable' },
      { zoneId: 'Zone-L2-B', floorId: 'L2', label: 'DALI Controller L2', level: 'stable' },
    ],
    "solar-bess": [
      { zoneId: 'Zone-B1-001', floorId: 'B1', label: 'Solar & BESS', level: 'stable' },
    ],
  }

  const equipZones = systemFilter ? (SYSTEM_EQUIPMENT_ZONES[systemFilter] ?? []) : []
  const equipZoneIds = new Set(zoneSignalsWithClusters.map((s) => s.zoneId))
  for (const ez of equipZones) {
    if (!equipZoneIds.has(ez.zoneId)) {
      zoneSignalsWithClusters.push({
        zoneId: ez.zoneId,
        label: ez.label,
        floorId: ez.floorId,
        meshId: `mesh:${ez.zoneId.toLowerCase()}`,
        level: ez.level,
        weight: 0.85,
        slot: zoneSignalsWithClusters.length,
        isPrimary: false,
        actionLabel: systemFilter === 'energy' ? 'Energy Centre' : systemFilter === 'lighting' ? 'Lighting' : 'Solar & BESS',
      })
    }
  }

  // Deduplicate by zoneId — keep last occurrence (equipZone version wins over standalone cluster).
  const seen = new Map<string, typeof zoneSignalsWithClusters[0]>()
  for (const s of zoneSignalsWithClusters) seen.set(s.zoneId, s)
  zoneSignalsWithClusters = [...seen.values()]

  const secondarySummary = secondaryTensions.length > 0
    ? secondaryTensions.map((tension) => `${formatVoiceLabel(tension.voice)}: ${tension.message}`).join(' | ')
    : 'No secondary tensions are currently rising above the building background.'

  return {
    site: {
      id: summary.siteId,
      name: summary.siteName,
      latitude: summary.gpsLat ?? null,
      longitude: summary.gpsLon ?? null,
      orientationDegrees: summary.orientationDegrees ?? null,
      onboardingPhase,
      posture: formatPostureLabel(payload.building_posture),
      mode: isShadowPhase ? 'watch' : payload.operator_guidance.mode,
      renderState: 'live',
      dataFreshnessLabel: summary.dataFreshnessLabel,
      buildingGeometry: summary.buildingGeometry ?? null,
    },
    sitePulse: {
      tone,
      attentionScore: tone === 'critical' ? 1 : tone === 'elevated' ? 0.8 : tone === 'warning' ? 0.6 : 0.2,
      activeConditionCount: narrative ? 1 : (secondaryTensions.length + equipmentWarnings.length),
      emergingRiskCount: secondaryTensions.length + (equipmentWarnings?.length ?? 0),
      equipmentWarningCount: equipmentWarnings.length,
      evidenceStrength: narrative ? 'moderate' : 'weak',
    },
    primaryMetric: {
      tone,
      label: 'Time to Constraint',
      value: timeValue,
      // Suppress HVAC operator_guidance headline when a non-HVAC system tab is active
      // without a matching narrative — prevents HVAC content from bleeding into
      // Energy, Lighting, Water, Fire, Security tabs.
      detail: systemFilter && !narrative
        ? (energyCentreTelemetry ? `Energy Centre ${energyCentreTelemetry.totalKw.toFixed(0)} kW` : '—')
        : (energyCentreTelemetry
            ? `${payload.operator_guidance.headline} · Energy Centre ${energyCentreTelemetry.totalKw.toFixed(0)} kW`
            : payload.operator_guidance.headline),
    },
    activeCondition: {
      summary: isShadowPhase
        ? shadowSummary
        : (narrative?.message
            ?? (equipmentWarnings.length > 0
              ? `${equipmentWarnings.length} equipment at health warning`
              : secondaryTensions.length > 0
                ? `${secondaryTensions.length} emerging risk${secondaryTensions.length !== 1 ? 's' : ''} detected`
                : 'Building is calm.')),
      rationale: isShadowPhase
        ? `Shadow training mode: telemetry-only observation across ${locationSummary(narrative)}.`
        : (
          narrative
            ? `${formatVoiceLabel(narrative.voice)} centered on ${locationSummary(narrative)}.`
            : equipmentWarnings.length > 0
              ? `${equipmentWarnings.map((e) => `${e.code} (${e.health_score}/100)`).join(', ')}.`
              : secondaryTensions.length > 0
                ? secondaryTensions.map((t) => t.message).join(' ')
                : 'No dominant narrative is active. The building is operating within margin.'
        ),
      confidenceLabel: isShadowPhase ? 'Observation only' : payload.operator_guidance.headline,
    },
    decision: {
      impact: locationSummary(narrative),
      summary: isShadowPhase
        ? 'Observe telemetry flow and model calibration.'
        : (narrative?.action
            ?? (equipmentWarnings.length > 0
              ? `Investigate ${equipmentWarnings.length} equipment with low health scores`
              : 'No action needed.')),
      tradeoff: equipmentWarnings.length > 0
      ? `${equipmentWarnings.length} equipment at health warning: ${equipmentWarnings.map((e) => `${e.code} (${e.health_score}/100)`).join(', ')}`
      : secondarySummary,
      confidence: isShadowPhase ? 'Shadow training mode' : payload.operator_guidance.headline,
    },
    visualTwin: {
      headline: narrative
        ? narrative.message
        : equipmentWarnings.length > 0
          ? `${equipmentWarnings.length} equipment at health warning`
          : 'Building calm. No active dominant narrative.',
      activeLabel: narrative?.location.epicenter ?? summary.siteName,
      modeLabel: titleCase(payload.operator_guidance.mode),
      motionProfile: tone === 'critical' ? 'alert' : tone === 'warning' || tone === 'elevated' ? 'watch' : 'calm',
      breathingIntensity: hvacSignal.intensity,
      flowSpeed: hvacSignal.flowSpeed,
      consumptionIntensity,
      focusFloorId,
      floors: buildTwinFloors(
        summary.siteId,
        floorOrder,
        focusFloorId,
        urgencyScore,
        null,
        bands,
        payload.affected_zone_ids ?? [],
        summary.siteFloors,
      ),
      zoneSignals: zoneSignalsWithClusters,
      flowPaths,
      energyCentre: {
        online: Boolean(energyCentreTelemetry) || Boolean(hvacOverview?.raw_telemetry?.power),
        totalKw: hvacOverview?.raw_telemetry?.power?.total_kw ?? energyCentreTelemetry?.totalKw ?? 0,
        hvacKw: hvacOverview?.raw_telemetry?.power?.hvac_kw ?? energyCentreTelemetry?.hvacKw ?? 0,
        lightingKw: hvacOverview?.raw_telemetry?.power?.lighting_kw ?? energyCentreTelemetry?.lightingKw ?? 0,
        powerKw: energyCentreTelemetry?.powerKw ?? 0,
        loadRatio: energyLoadRatio,
        powerShareRatio: energyPowerShare,
        stateLabel: energyStateLabel(energyLoadRatio),
      },
    },
    evidence: {
      strength: narrative ? 'moderate' : 'strong',
      summary: 'Rendered from the backend building-state contract.',
      refs: narrative
        ? [
            ...[narrative.location.epicenter, ...narrative.location.affected].map((zoneId) => `zone:${zoneId}`),
            ...(energyCentreTelemetry ? [`energy-centre:${energyCentreTelemetry.totalKw.toFixed(0)}kw`] : []),
            ...remoteModuleRefs,
          ]
        : [
            ...(energyCentreTelemetry ? [`energy-centre:${energyCentreTelemetry.totalKw.toFixed(0)}kw`] : []),
            ...remoteModuleRefs,
          ],
    },
    severity: {
      riskScore: null,
      riskBand,
      thresholdReason: null,
      policySource: null,
      policyLevel: null,
      constraintType: narrative?.voice === 'comfort_stress' ? 'comfort' : narrative?.voice === 'asset_stress' ? 'asset' : null,
      timeToConstraintBreachMin: timeToBreach,
      affectedScope: narrative
        ? {
            zones: [narrative.location.epicenter, ...narrative.location.affected],
            assets: [],
            occupantsEstimate: null,
          }
        : null,
      healthScore: null,
      healthState: null,
      healthTrend: null,
      healthReason: null,
      assetClass: null,
      criticality: null,
    },
    emergingRisks: secondaryTensions.map((tension, index) => ({
      id: `secondary-${index}-${tension.voice}`,
      title: formatVoiceLabel(tension.voice),
      detail: tension.message,
    })),
    emailClusters,
    equipmentWarnings: (equipmentWarnings ?? []).map((eq) => ({
      id: eq.id,
      equipmentId: eq.equipment_id,
      equipmentCode: eq.code,
      equipmentType: eq.equipment_type,
      floorId: eq.floor_id ?? extractFloorCode(eq.equipment_id ?? eq.code) ?? eq.zone_id ?? null,
      healthScore: eq.health_score,
      healthState: eq.health_state as CockpitHealthState,
      faultType: eq.fault_type,
      zoneId: eq.zone_id,
    })),
    systemFilter: (systemFilter ?? null) as 'hvac' | 'energy' | 'lighting' | 'water' | 'fire' | 'security' | 'solar-bess' | null,
  }
}

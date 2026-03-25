import { buildDecisionSurface } from '@/lib/decisionSurface'
import type { CockpitState, CockpitTwinRiskLevel } from './types'
import { DEFAULT_COCKPIT_THRESHOLD_POLICY, type CockpitThresholdPolicy } from './thresholdPolicy'

export interface CockpitDecisionPayload {
  risk?: {
    score?: number | null
    band?: CockpitState['severity']['riskBand'] | null
    reason?: string | null
    policy_source?: string | null
  } | null
  health?: {
    score?: number | null
    state?: CockpitState['severity']['healthState'] | null
    trend?: CockpitState['severity']['healthTrend'] | null
  } | null
  building_id: string
  alert_text?: string | null
  reasoning_summary?: string | null
  active_posture?: string | null
  time_to_discomfort?: number | null
  time_confidence?: string | number | null
  estimated_impact?: unknown
  recommended_action?: string | null
  urgency_score?: number | null
  urgency_components?: Record<string, number> | null
  affected_zone_ids?: string[] | null
  primary_asset_id?: string | null
  building_metadata?: {
    deployment_mode?: 'ghost' | 'advisory' | 'supervised' | 'autonomous'
    floor_labels?: Record<string, string>
    floor_stack_order?: string[]
  } | null
}

export interface CockpitSiteSummary {
  siteId: string
  siteName: string
  posture?: string | null
  activeAlerts: number
  predictionsCount: number
  equipmentCount: number
  dataFreshnessLabel: string
}

type DecisionSurface = ReturnType<typeof buildDecisionSurface>

const DEFAULT_FLOOR_ORDER = ['R', 'L2', 'L1', 'L0', 'G', 'B1']

function getTone(riskBand: CockpitState['severity']['riskBand']): CockpitState['primaryMetric']['tone'] {
  if (riskBand === 'critical') return 'critical'
  if (riskBand === 'high') return 'elevated'
  if (riskBand === 'medium') return 'warning'
  return 'normal'
}

function getEvidenceStrength(score: number): 'strong' | 'moderate' | 'limited' {
  if (score >= 0.75) return 'strong'
  if (score >= 0.45) return 'moderate'
  return 'limited'
}

function formatPostureLabel(posture: string | null | undefined): string {
  if (!posture) return 'Watch mode'

  const normalized = posture.trim().toLowerCase()
  if (normalized === 'comfort_priority') return 'Comfort first'
  if (normalized === 'energy_priority') return 'Energy first'
  if (normalized === 'asset_priority') return 'Asset protection'
  if (normalized === 'adaptive_intelligence') return 'Watch mode'

  return posture.replace(/_/g, ' ')
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value))
}

function toPercent(score: number): number {
  return Math.round(clamp01(score) * 100)
}

function normalizedRiskScore(payload: CockpitDecisionPayload): number {
  return clamp01(payload.risk?.score ?? payload.urgency_score ?? 0)
}

function fallbackHealthScore(riskScore: number): number {
  return clamp01(1 - (riskScore * 0.2))
}

function fallbackHealthState(score: number, thresholds: CockpitThresholdPolicy['health']): CockpitState['severity']['healthState'] {
  const percent = toPercent(score)
  if (percent >= thresholds.healthy) return 'stable'
  if (percent >= thresholds.warning) return 'watch'
  return 'degraded'
}

function fallbackHealthTrend(riskScore: number): CockpitState['severity']['healthTrend'] {
  if (riskScore >= 0.55) return 'declining'
  if (riskScore <= 0.2) return 'improving'
  return 'flat'
}

function extractFloorCode(value: string | null | undefined): string | null {
  if (!value) return null
  const match = value.match(/(?:^|-)(R|L\d+|G|B\d+)(?:-|$)/i)
  return match?.[1]?.toUpperCase() ?? null
}

function formatFloorLabel(floorId: string, customLabels?: Record<string, string> | null): string {
  if (customLabels?.[floorId]) return customLabels[floorId]
  if (floorId === 'R') return 'Roof'
  if (floorId === 'G') return 'Ground'
  if (floorId === 'B1') return 'Basement B1'
  if (floorId.startsWith('B')) return `Basement ${floorId.slice(1)}`
  if (floorId.startsWith('L')) return `Level ${floorId.slice(1)}`
  return floorId
}

function riskBandFromScore(
  score: number,
  thresholds: CockpitThresholdPolicy['risk'],
): CockpitState['severity']['riskBand'] {
  const riskScore = toPercent(score)

  if (riskScore >= thresholds.critical) return 'critical'
  if (riskScore >= thresholds.high) return 'high'
  if (riskScore >= thresholds.medium) return 'medium'
  return 'low'
}

function riskLevelFromBand(riskBand: CockpitState['severity']['riskBand']): CockpitTwinRiskLevel {
  if (riskBand === 'critical') return 'critical'
  if (riskBand === 'high') return 'approaching'
  if (riskBand === 'medium') return 'drift'
  return 'stable'
}

function motionProfileFromRiskBand(riskBand: CockpitState['severity']['riskBand']): CockpitState['visualTwin']['motionProfile'] {
  if (riskBand === 'critical') return 'alert'
  if (riskBand === 'high' || riskBand === 'medium') return 'watch'
  return 'calm'
}

function buildThresholdReason(
  score: number,
  riskBand: CockpitState['severity']['riskBand'],
  thresholds: CockpitThresholdPolicy['risk'],
): string {
  const riskScore = toPercent(score)

  if (riskBand === 'critical') return `Risk ${riskScore} is at or above the critical threshold of ${thresholds.critical}`
  if (riskBand === 'high') return `Risk ${riskScore} is at or above the high threshold of ${thresholds.high}`
  if (riskBand === 'medium') return `Risk ${riskScore} is at or above the medium threshold of ${thresholds.medium}`
  return `Risk ${riskScore} is below the medium threshold of ${thresholds.medium}`
}

function resolveFocusFloorId(payload: CockpitDecisionPayload): string | null {
  return (
    extractFloorCode(payload.affected_zone_ids?.[0] ?? null)
    ?? extractFloorCode(payload.primary_asset_id ?? null)
    ?? null
  )
}

function buildFloorOrder(configuredOrder: string[], focusFloorId: string | null): string[] {
  const floorOrder = [...configuredOrder]

  for (const fallback of DEFAULT_FLOOR_ORDER) {
    if (!floorOrder.includes(fallback)) {
      floorOrder.push(fallback)
    }
  }

  if (focusFloorId && !floorOrder.includes(focusFloorId)) {
    floorOrder.unshift(focusFloorId)
  }

  return floorOrder
}

function buildTwinFloors(
  floorOrder: string[],
  focusFloorId: string | null,
  urgencyScore: number,
  floorLabels: Record<string, string> | null | undefined,
  policy: CockpitThresholdPolicy,
) {
  const anchorIndex = focusFloorId ? floorOrder.indexOf(focusFloorId) : -1

  return floorOrder.map((floorId, index) => {
    const distance = anchorIndex >= 0 ? Math.abs(index - anchorIndex) : Number.POSITIVE_INFINITY
    const spread = anchorIndex >= 0 ? clamp01(urgencyScore - distance * 0.22) : 0
    const riskScore = index === anchorIndex ? urgencyScore : spread * 0.9
    const level = anchorIndex >= 0 ? riskLevelFromBand(riskBandFromScore(riskScore, policy.risk)) : 'stable'

    return {
      id: floorId,
      label: formatFloorLabel(floorId, floorLabels),
      meshId: `floor:${floorId}`,
      level,
      intensity: anchorIndex >= 0 ? clamp01(0.18 + spread * 0.82) : 0.16,
      spread,
      elevation: (floorOrder.length - index - 1) * 2.25,
    }
  })
}

function buildZoneSignals(
  payload: CockpitDecisionPayload,
  focusFloorId: string | null,
  floorOrder: string[],
  urgencyScore: number,
  policy: CockpitThresholdPolicy,
  actionLabel: string,
) {
  const sourceSignals = (payload.affected_zone_ids ?? []).length > 0
    ? (payload.affected_zone_ids ?? [])
    : payload.primary_asset_id
      ? [payload.primary_asset_id]
      : []

  const floorSlots = new Map<string, number>()

  return sourceSignals.map((sourceId, index) => {
    const fallbackFloor = floorOrder[Math.min(index, floorOrder.length - 1)] ?? 'L0'
    const floorId = extractFloorCode(sourceId) ?? focusFloorId ?? fallbackFloor
    const slot = floorSlots.get(floorId) ?? 0
    const weight = clamp01(urgencyScore - index * 0.12)
    floorSlots.set(floorId, slot + 1)

    return {
      zoneId: sourceId,
      label: sourceId.replace(/^Zone-/, '').replace(/-/g, ' '),
      floorId,
      meshId: `mesh:${sourceId.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
      level: riskLevelFromBand(riskBandFromScore(weight, policy.risk)),
      weight,
      slot,
      isPrimary: index === 0,
      actionLabel,
    }
  })
}

function buildVisualTwin(
  payload: CockpitDecisionPayload,
  surface: DecisionSurface,
  urgencyScore: number,
  policy: CockpitThresholdPolicy,
): CockpitState['visualTwin'] {
  const floorLabels = payload.building_metadata?.floor_labels ?? null
  const configuredOrder = payload.building_metadata?.floor_stack_order ?? []
  const focusFloorId = resolveFocusFloorId(payload)
  const floorOrder = buildFloorOrder(configuredOrder, focusFloorId)
  const floors = buildTwinFloors(floorOrder, focusFloorId, urgencyScore, floorLabels, policy)
  const zoneSignals = buildZoneSignals(payload, focusFloorId, floorOrder, urgencyScore, policy, surface.action.summary)

  return {
    headline: surface.time.value === 'Unknown'
      ? 'No comfort risk right now'
      : `${zoneSignals[0]?.label ?? 'This area'} will breach in ${surface.time.value}`,
    activeLabel: zoneSignals[0]?.label ?? surface.cause,
    modeLabel: surface.presentation.statusLabel,
    motionProfile: motionProfileFromRiskBand(riskBandFromScore(urgencyScore, policy.risk)),
    focusFloorId,
    floors,
    zoneSignals,
  }
}

function buildFallbackPayload(summary: CockpitSiteSummary): CockpitDecisionPayload {
  return {
    building_id: summary.siteId,
    alert_text: 'No comfort risk for the next 30 minutes.',
    reasoning_summary: 'Live signals are steady. Keep watching for the next drift or breach window.',
    active_posture: summary.posture ?? 'adaptive_intelligence',
    time_to_discomfort: null,
    time_confidence: 'steady',
    estimated_impact: 'No immediate comfort, uptime, or compliance impact.',
    recommended_action: 'No action needed. Keep watching the site.',
    urgency_score: 0.18,
    urgency_components: { comfort: 0.06, asset_risk: 0.06, cost: 0.06 },
    affected_zone_ids: [],
    primary_asset_id: null,
    building_metadata: {
      deployment_mode: 'advisory',
    },
  }
}

function buildEvidence(
  summary: CockpitSiteSummary,
  payload: CockpitDecisionPayload | null | undefined,
  resolvedPayload: CockpitDecisionPayload,
  evidenceStrength: CockpitState['evidence']['strength'],
): CockpitState['evidence'] {
  return {
    strength: evidenceStrength,
    summary: payload
      ? `Built from live site signals and ${summary.dataFreshnessLabel.toLowerCase()}.`
      : 'Built from live site signals and current watch rules.',
    refs: [
      ...(resolvedPayload.primary_asset_id ? [`asset:${resolvedPayload.primary_asset_id}`] : []),
      ...(resolvedPayload.affected_zone_ids ?? []).slice(0, 2).map((zoneId) => `zone:${zoneId}`),
      ...Object.keys(resolvedPayload.urgency_components ?? {}).slice(0, 3).map((key) => `signal:${key}`),
    ],
  }
}

function buildEmergingRisks(
  payload: CockpitDecisionPayload | null | undefined,
  resolvedPayload: CockpitDecisionPayload,
  surface: DecisionSurface,
): CockpitState['emergingRisks'] {
  if (!payload) {
    return [
      {
        id: 'risk-watch',
        title: 'No active breach forecast',
        detail: 'Keep watching for the next drift window.',
      },
      {
        id: 'risk-evidence',
        title: 'Keep telemetry fresh',
        detail: 'If telemetry freshness drops, trust the twin less before escalating action.',
      },
    ]
  }

  return [
    {
      id: 'risk-horizon',
      title: `${surface.time.label} is still the main risk clock`,
      detail: `If nothing changes, the next breach window is still set by ${surface.time.label.toLowerCase()}.`,
    },
    {
      id: 'risk-spread',
      title: 'Watch nearby zones next',
      detail: resolvedPayload.affected_zone_ids && resolvedPayload.affected_zone_ids.length > 0
        ? `Watch ${resolvedPayload.affected_zone_ids.slice(0, 2).join(', ')} for spillover or recovery drift.`
        : 'Watch neighboring zones and dependent systems for spillover or recovery drift.',
    },
  ]
}

function buildSiteState(summary: CockpitSiteSummary, resolvedPayload: CockpitDecisionPayload, surface: DecisionSurface) {
  return {
    id: summary.siteId,
    name: summary.siteName,
    posture: formatPostureLabel(resolvedPayload.active_posture ?? summary.posture),
    mode: surface.mode,
    dataFreshnessLabel: summary.dataFreshnessLabel,
  }
}

function buildSitePulse(
  summary: CockpitSiteSummary,
  payload: CockpitDecisionPayload | null | undefined,
  tone: CockpitState['sitePulse']['tone'],
  urgencyScore: number,
  evidenceStrength: CockpitState['sitePulse']['evidenceStrength'],
) {
  return {
    tone,
    attentionScore: urgencyScore,
    activeConditionCount: Math.max(summary.activeAlerts, payload ? 1 : 0),
    emergingRiskCount: Math.max(summary.predictionsCount, 0),
    evidenceStrength,
  }
}

function buildPrimaryMetric(surface: DecisionSurface, tone: CockpitState['primaryMetric']['tone'], confidenceLabel: string) {
  return {
    tone,
    label: 'Time to Comfort Breach',
    value: surface.time.value === 'Unknown' ? 'Stable' : surface.time.value,
    detail: confidenceLabel,
  }
}

function buildDecisionState(surface: DecisionSurface, confidenceLabel: string) {
  return {
    mode: surface.mode,
    impact: surface.impact,
    summary: surface.action.summary,
    command: surface.action.bmsGuide?.command ?? surface.action.operatorPrompt,
    operatorPrompt: surface.action.operatorPrompt,
    expectedOutcome: surface.action.expectedOutcome,
    tradeoff: surface.action.tradeoff,
    confidence: confidenceLabel,
    verification: surface.action.bmsGuide?.verification ?? surface.action.expectedOutcome,
    navigationPath: surface.action.bmsGuide?.navigationPath ?? [],
  }
}

function buildActiveCondition(surface: DecisionSurface, resolvedPayload: CockpitDecisionPayload, confidenceLabel: string) {
  return {
    summary: surface.cause,
    rationale: resolvedPayload.reasoning_summary?.trim()
      || 'Live signals are steady. Keep watching for the next drift window.',
    confidenceLabel,
  }
}

function buildSeverityState(
  resolvedPayload: CockpitDecisionPayload,
  riskScore: number,
  riskBand: CockpitState['severity']['riskBand'],
  policy: CockpitThresholdPolicy,
): CockpitState['severity'] {
  const healthScore = clamp01(resolvedPayload.health?.score ?? fallbackHealthScore(riskScore))
  return {
    riskScore: toPercent(riskScore),
    riskBand,
    thresholdReason: resolvedPayload.risk?.reason ?? buildThresholdReason(riskScore, riskBand, policy.risk),
    policySource: resolvedPayload.risk?.policy_source ?? policy.source,
    healthScore: toPercent(healthScore),
    healthState: resolvedPayload.health?.state ?? fallbackHealthState(healthScore, policy.health),
    healthTrend: resolvedPayload.health?.trend ?? fallbackHealthTrend(riskScore),
  }
}

export function mapCockpitState(
  summary: CockpitSiteSummary,
  payload?: CockpitDecisionPayload | null,
  policy: CockpitThresholdPolicy = DEFAULT_COCKPIT_THRESHOLD_POLICY,
): CockpitState {
  const resolvedPayload = payload ?? buildFallbackPayload(summary)
  const surface = buildDecisionSurface(resolvedPayload)
  const urgencyScore = normalizedRiskScore(resolvedPayload)
  const riskBand = resolvedPayload.risk?.band ?? riskBandFromScore(urgencyScore, policy.risk)
  const tone = getTone(riskBand)
  const evidenceStrength = getEvidenceStrength(urgencyScore)
  const confidenceLabel = surface.time.detail

  return {
    site: buildSiteState(summary, resolvedPayload, surface),
    sitePulse: buildSitePulse(summary, payload, tone, urgencyScore, evidenceStrength),
    primaryMetric: buildPrimaryMetric(surface, tone, confidenceLabel),
    activeCondition: buildActiveCondition(surface, resolvedPayload, confidenceLabel),
    decision: buildDecisionState(surface, confidenceLabel),
    visualTwin: buildVisualTwin(resolvedPayload, surface, urgencyScore, policy),
    evidence: buildEvidence(summary, payload, resolvedPayload, evidenceStrength),
    severity: buildSeverityState(resolvedPayload, urgencyScore, riskBand, policy),
    emergingRisks: buildEmergingRisks(payload, resolvedPayload, surface),
  }
}
